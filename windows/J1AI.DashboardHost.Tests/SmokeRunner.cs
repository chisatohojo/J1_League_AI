using System.Diagnostics;
using System.Reflection;
using System.Windows.Forms;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal static class SmokeRunner
{
    // Only these test-assembly entry points can reach the fixed fixture. There is
    // no arbitrary repository, backend, data or UDF parameter.
    internal static async Task<int> Run(string[] args)
    {
        try
        {
            bool readOnly = args is ["--smoke-preflight"];
            bool worker = args.Length > 0 && args[0] == "--smoke-worker";
            bool run = args.Length > 0 && args[0] == "--smoke-run";
            bool signal = args is ["--smoke-stop"] or ["--smoke-show"];
            string? approval = args is [_, "--approve-first-use", var token] ? token : null;
            SmokeFixture.Require(OperatingSystem.IsWindows() && (readOnly || worker || run || signal) &&
                (args.Length == 1 || !readOnly && args.Length == 3 && approval != null), "smoke_arguments");
            string root = RepositoryIdentity.FindRoot(AppContext.BaseDirectory);
            var fixture = new SmokeFixture(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                Path.Combine(root, ".venv", "Scripts", "python.exe"), Path.Combine(root, "scripts", "launch_dashboard.py"),
                Path.Combine(root, "web"), Path.Combine(AppContext.BaseDirectory, "synthetic_gui_server.py"), Assembly.GetExecutingAssembly().Location);
            WebViewPreflight.CheckInputs(Environment.GetEnvironmentVariables(), WebViewPreflight.ReadPolicies());
            var manifest = await fixture.Describe();
            if (signal)
            {
                SmokeFixture.Require(fixture.SignalActive(manifest, args[0] == "--smoke-stop"), "not_running");
                Console.WriteLine("SMOKE_IPC_SIGNALED"); return 0;
            }
            var inspection = fixture.Inspect(manifest);
            if (readOnly)
            {
                Console.WriteLine("SMOKE_PREFLIGHT_PASS " + (inspection.FirstUse ? "UNINITIALIZED" : "CLEAN"));
                Console.WriteLine("Plan SHA-256: " + inspection.Fingerprint);
                Console.WriteLine("Fixture: " + inspection.Manifest.Root);
                Console.WriteLine("UDF: " + inspection.Manifest.Udf);
                Console.WriteLine("First-use UDF allocation <= 1; reuse allocation = 0. No files created.");
                return 0;
            }
            SmokeFixture.Require(!inspection.FirstUse || approval == inspection.Fingerprint, "first_use_approval_required");
            if (!worker) return await Supervise(args, inspection.Manifest);
            return await Worker(fixture, inspection, approval);
        }
        catch (Exception error)
        {
            Console.WriteLine("SMOKE_BLOCKED " + (error is SmokeError ? error.Message : error is HostError h ? h.Code : "unexpected_failure"));
            return 1;
        }
    }
    private static async Task<int> Supervise(string[] args, SmokeManifest manifest)
    {
        using var child = new Process { StartInfo = new(Environment.ProcessPath!) { UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true } };
        if (string.Equals(Path.GetFileNameWithoutExtension(Environment.ProcessPath), "dotnet", StringComparison.OrdinalIgnoreCase))
            child.StartInfo.ArgumentList.Add(Assembly.GetExecutingAssembly().Location);
        child.StartInfo.ArgumentList.Add("--smoke-worker");
        foreach (var arg in args.Skip(1)) child.StartInfo.ArgumentList.Add(arg);
        SmokeFixture.Require(child.Start(), "worker_start");
        // Drain only fixed test-runner messages; never propagate stderr contents.
        var output = Drain(child.StandardOutput, true); var errors = Drain(child.StandardError, false);
        _ = output.ContinueWith(t => { _ = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted);
        _ = errors.ContinueWith(t => { _ = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted);
        int result = await Watch(child, () =>
        { InstanceControls.Signal(new(manifest.Root, manifest.Identity), true); return Task.CompletedTask; },
            TimeSpan.FromMinutes(5), TimeSpan.FromSeconds(20));
        if (child.HasExited) await Task.WhenAll(output, errors).WaitAsync(TimeSpan.FromSeconds(5));
        return result;
    }
    internal static async Task<int> Watch(Process child, Func<Task> stop, TimeSpan deadline, TimeSpan grace)
    {
        try { await child.WaitForExitAsync().WaitAsync(deadline); return child.ExitCode; }
        catch (TimeoutException)
        {
            // Retained worker owns its GUI, server Job, fixture lease and RUNNING
            // journal. Never kill it or mark CLEAN from the supervisor.
            await stop().WaitAsync(grace);
            try { await child.WaitForExitAsync().WaitAsync(grace); } catch (TimeoutException) { }
            Console.WriteLine("SMOKE_BLOCKED worker_timeout; no forced termination; unfinished state prohibits reuse");
            return 1;
        }
    }
    private static async Task Drain(StreamReader reader, bool forward)
    {
        // Worker protocol is fixed text. Reject unbounded lines/output.
        var buffer = new char[1]; int total = 0; var line = new System.Text.StringBuilder();
        while (await reader.ReadAsync(buffer) != 0)
        {
            if (++total > 65536 || line.Length >= 4096) throw new SmokeError("worker_output_limit");
            if (buffer[0] == '\n') { if (forward && line.ToString().StartsWith("SMOKE_", StringComparison.Ordinal)) Console.WriteLine(line.ToString()); line.Clear(); }
            else line.Append(buffer[0]);
        }
    }
    private static async Task<int> Worker(SmokeFixture fixture, SmokeInspection inspection, string? approval)
    {
        using var lease = fixture.Begin(inspection, approval);
        fixture.BindDirectories(inspection, lease);
        var identity = new RepositoryIdentity(fixture.Root, inspection.Manifest.Identity);
        using var controls = new InstanceControls(identity);
        var parentControls = new SmokeParentControls(controls);
        OwnedServer? server = null; DashboardForm? form = null;
        bool mapped = false, initializationEntered = false, notified = false;
        using var monitorStop = new CancellationTokenSource();
        // Parent crash closes stdin. Request the SAME fixture's Stop, never kill.
        var parentMonitor = Task.Run(async () =>
        {
            try { await Console.In.ReadLineAsync(monitorStop.Token); if (!monitorStop.IsCancellationRequested) parentControls.Disconnected(); }
            catch (OperationCanceledException) { }
        });
        _ = parentMonitor.ContinueWith(t => { _ = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted);
        int result;
        try
        {
            result = await GuiEntry.RunAsync(parentControls, () =>
                {
                    var configuration = WebViewPreflight.Check(identity.Id);
                    SmokeFixture.Require(configuration.Profile == inspection.Manifest.Udf && configuration.Runtime == inspection.Manifest.Runtime, "runtime_configuration_changed");
                    return configuration;
                },
                () => server = OwnedServer.Start(fixture.Server(inspection.Manifest), controls),
                new Readiness(), new RecordingEvents(), TimeSpan.FromSeconds(20), () =>
                {
                    notified = true;
                    new GuiFailureNotification().Show(); // actual fixed-text notification in manual smoke
                }, created =>
                {
                    form = created;
                    var timer = new System.Windows.Forms.Timer { Interval = 20 };
                    timer.Tick += (_, _) =>
                    {
                        try
                        {
                            initializationEntered |= created.RuntimeStarted;
                            if (created.Core is { } core)
                            {
                                mapped = Path.GetFullPath(core.Environment.UserDataFolder).Equals(inspection.Manifest.Udf, StringComparison.OrdinalIgnoreCase);
                                if (!mapped) created.Fail(EventCode.UnsafeWebViewOverride);
                            }
                        }
                        catch { mapped = false; created.Fail(EventCode.WebViewFailed); }
                    };
                    created.Disposed += (_, _) => { timer.Stop(); timer.Dispose(); };
                    timer.Start();
                });
        }
        finally { monitorStop.Cancel(); }
        // A missing server/controller is NOT evidence of a failed SDK task's
        // absence. Only a successful Runtime exit plus exact mapping is enough.
        bool runtimeEnded = mapped && form?.RuntimeExited.IsCompletedSuccessfully == true;
        if (form == null && server == null && !initializationEntered) runtimeEnded = true;
        var evidence = new SmokeEvidence(runtimeEnded, server != null && server.Resources is (true, true, true, true, true),
            form?.DisposalConfirmed.IsCompletedSuccessfully == true);
        fixture.Finish(inspection, evidence, lease);
        Console.WriteLine($"SMOKE_FINISHED exit={result}; cleanup_confirmed; notification={(notified ? "attempted" : "none")}");
        return result;
    }
}

// Remember disconnect before IPC acquisition too; a one-shot event signal could
// otherwise be lost while the worker is still starting.
internal sealed class SmokeParentControls(IControls inner) : IControls
{
    private int disconnected;
    internal void Disconnected() => Interlocked.Exchange(ref disconnected, 1);
    public bool Acquire() => inner.Acquire();
    public bool StopRequested => Volatile.Read(ref disconnected) != 0 || inner.StopRequested;
    public bool ConsumeShow() => !StopRequested && inner.ConsumeShow() && !StopRequested;
    public void RequestShow() => inner.RequestShow();
    public void Dispose() => inner.Dispose();
}
