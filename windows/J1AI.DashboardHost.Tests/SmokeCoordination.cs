using System.Diagnostics;
using J1AI.DashboardHost;
using J1AI.SmokeCoordination;

namespace J1AI.DashboardHost.Tests;

// Test-only client. The frozen binary is NOT rebuilt/adopted by this source change.
internal sealed class SmokeCoordination : IAsyncDisposable
{
    private readonly CoordinationPipe pipe;
    private readonly CancellationTokenSource lifetime = new(TimeSpan.FromSeconds(360));
    private readonly TaskCompletionSource permitted = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly string challenge;
    private readonly Task receive;
    private int closeRequested;
    internal WorkerGate Gate { get; }
    internal RunBinding Binding { get; }
    private SmokeCoordination(CoordinationPipe pipe, RunBinding binding, string challenge)
    {
        this.pipe = pipe; Binding = binding; this.challenge = challenge;
        var clock = Stopwatch.StartNew();
        Gate = new(binding, () => clock.ElapsedMilliseconds, () => pipe.Alive);
        Gate.Ready(binding); receive = Receive();
    }
    internal static async Task<SmokeCoordination> Connect(SmokeManifest manifest, SmokeFixture fixture)
    {
        string root = RepositoryIdentity.FindRoot(AppContext.BaseDirectory);
        string dotnet = Path.Combine(fixture.Local, "J1AI", "Toolchains", "dotnet", "dotnet.exe");
        string observer = Path.Combine(root, "windows", "J1AI.SmokeNetworkObserver", "bin", "Release", "net10.0-windows", "J1AI.SmokeNetworkObserver.dll");
        string runtime = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Microsoft", "EdgeWebView", "Application", "154.0.4258.62", "msedgewebview2.exe");
        string[] interpreter = File.ReadAllLines(Path.Combine(root, ".venv", "pyvenv.cfg"))
            .Where(line => line.StartsWith("executable = ", StringComparison.Ordinal)).Select(line => line[13..]).ToArray();
        SmokeFixture.Require(interpreter.Length == 1, "coord_interpreter_unknown");
        var expected = new RunBinding("", manifest.Identity, manifest.Udf, SmokeFixture.Fingerprint(manifest),
            SmokeFixture.FileHash(observer), manifest.Hashes["runner"], SmokeFixture.FileHash(dotnet),
            SmokeFixture.FileHash(Path.ChangeExtension(fixture.Runner, ".exe")), SmokeFixture.FileHash(runtime),
            SmokeFixture.FileHash(interpreter[0]), manifest.Hashes["backend"]);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var pipe = await CoordinationPipe.Connect(expected, deadline.Token);
        try
        {
            string challenge = Guid.NewGuid().ToString("N");
            await pipe.Send(new("Hello", expected, 0, challenge), deadline.Token);
            var ready = await pipe.Read(deadline.Token);
            CoordinationSession.Require(ready.Kind == "Ready" && ready.Challenge == challenge && Guid.TryParseExact(ready.Binding.Run, "N", out _) &&
                ready.Binding with { Run = "" } == expected && pipe.Alive, "smoke_ready_invalid");
            return new(pipe, ready.Binding, challenge);
        }
        catch { pipe.Dispose(); throw; }
    }
    private async Task Receive()
    {
        try
        {
            while (!lifetime.IsCancellationRequested)
            {
                using var lease = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                lease.CancelAfter(1500);
                var message = await pipe.Read(lease.Token);
                CoordinationSession.Require(message.Binding == Binding && message.Challenge == challenge, "smoke_foreign_run");
                Gate.Pulse(message.Binding);
                switch (message.Kind)
                {
                    case "Tick": break;
                    case "Permit": Gate.Grant(message.Binding, message.Port, message.Permit ?? ""); permitted.TrySetResult(); break;
                    case "Abort": Gate.Abort(); permitted.TrySetException(new IOException("smoke_abort")); break;
                    default: throw new IOException("smoke_coord_message");
                }
            }
        }
        catch { Gate.Abort(); permitted.TrySetException(new IOException("smoke_coord_disconnected")); }
    }
    private Task Send(string kind, string? run = null, int port = 0) =>
        pipe.Send(new(kind, Binding, 0, challenge, run, port), lifetime.Token);
    internal async Task Armed(string run)
    { Gate.Arm(); await Send("Armed", run); }
    internal async Task Permit(string url, CancellationToken token)
    {
        Readiness.ValidateUrl(url);
        await Send("Backend", port: new Uri(url).Port);
        await permitted.Task.WaitAsync(token);
        CoordinationSession.Require(!Gate.Aborted, "smoke_abort_before_permit");
    }
    internal void CloseRequested()
    {
        if (Interlocked.Exchange(ref closeRequested, 1) != 0) return;
        _ = SendClose();
        async Task SendClose() { try { await Send("Close"); } catch { Gate.Abort(); } }
    }
    internal Task Initialize(string url, Func<Task> call) => Gate.Initialize(new Uri(url).Port, call);
    public async ValueTask DisposeAsync()
    {
        lifetime.Cancel(); pipe.Dispose();
        try { await receive.WaitAsync(TimeSpan.FromSeconds(2)); }
        finally { lifetime.Dispose(); }
        // Observe a grant wait which was never reached because startup aborted.
        _ = permitted.Task.Exception;
    }
}

internal sealed class CoordinatedControls(IControls inner, SmokeCoordination link) : IControls
{
    public bool Acquire() => inner.Acquire();
    public bool StopRequested => link.Gate.Aborted || inner.StopRequested;
    public bool ConsumeShow() => !StopRequested && inner.ConsumeShow();
    public void RequestShow() => inner.RequestShow();
    public void Dispose() => inner.Dispose();
}
internal sealed class CoordinatedReadiness(IReadiness inner, SmokeCoordination link) : IReadiness
{
    public async Task<string> WaitAsync(IServer server, CancellationToken token)
    { string url = await inner.WaitAsync(server, token); await link.Permit(url, token); return url; }
}
internal sealed class CoordinatedWindow(DashboardForm inner, SmokeCoordination link) : IGuiWindow
{
    // Native FormClosing is cancelled by DashboardForm. Normal Close requests
    // the observer's durable Stop barrier rather than bypassing it.
    public bool CloseRequested { get { if (inner.CloseRequested) link.CloseRequested(); return link.Gate.Aborted; } }
    public EventCode? Failure => inner.Failure;
    public Task DisposalConfirmed => inner.DisposalConfirmed;
    public Task InitializeAsync(string url, CancellationToken token)
    {
        if (inner.CloseRequested)
        {
            link.CloseRequested();
            // Let GuiLifecycle observe the formally delivered Stop. Its startup
            // deadline bounds this wait; do not initialize SDK after a native X.
            return Task.Delay(Timeout.Infinite, token);
        }
        return link.Initialize(url, () => inner.InitializeAsync(url, token));
    }
    public void RestoreOwned() => inner.RestoreOwned();
    public Task CloseAndConfirmAsync() => inner.CloseAndConfirmAsync();
}
internal static class CoordinatedGuiEntry
{
    internal static Task<int> Run(IControls controls, WebViewConfiguration configuration, Func<IServer> start,
        IEvents events, SmokeCoordination link, Action<DashboardForm> created, Action notify) => StaPump.RunAsync(async () =>
    {
        if (controls.StopRequested) return 1;
        using var form = new DashboardForm(configuration, events);
        form.Show(); created(form);
        var lifecycle = new GuiLifecycle(controls, start, new CoordinatedReadiness(new Readiness(), link), new CoordinatedWindow(form, link), events);
        int result = await lifecycle.RunAsync(TimeSpan.FromSeconds(20));
        if (result != 0) new GuiFailureNotification(notify).Show();
        return result;
    });
}
