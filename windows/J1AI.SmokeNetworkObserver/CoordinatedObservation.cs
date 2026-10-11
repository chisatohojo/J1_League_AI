using System.Diagnostics;
using System.IO.Pipes;
using J1AI.SmokeCoordination;

namespace J1AI.SmokeNetworkObserver;

internal sealed class EvidenceJournal(IEvidence evidence) : ICoordinationJournal
{ public void Save(string name, object record) => evidence.SaveVerified(name, record); }

// Control plane only. Collector remains the authority for worker/backend identity.
internal sealed class CoordinatedObservation : IStop, IAsyncDisposable
{
    private readonly ApprovalPlan plan;
    private readonly NamedPipeServerStream listener;
    private readonly CancellationTokenSource lifetime = new(TimeSpan.FromSeconds(360));
    private readonly TaskCompletionSource ready = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource armed = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly Task transport;
    private CoordinationPipe? pipe;
    private string challenge = "";
    private volatile int port;
    private volatile bool close, fault, channelEnded, readySent;
    private readonly IStop formal;
    private readonly CoordinationDriver driver;
    public CoordinationSession Session { get; }
    public bool CloseRequested => close;
    public bool Faulted => fault;
    public static RunBinding Bind(ApprovalPlan plan) => new(Guid.NewGuid().ToString("N"), plan.Identity, plan.Contract.Udf,
        plan.ManifestSha, plan.ObserverHash, plan.FileHashes[plan.Contract.Runner], plan.FileHashes[plan.Contract.Dotnet], plan.FileHashes[plan.Contract.RunnerExe],
        plan.FileHashes[plan.Contract.RuntimeExecutable], plan.FileHashes[plan.Contract.PythonExecutable], plan.FileHashes[plan.Contract.Backend]);
    internal CoordinatedObservation(ApprovalPlan plan, RunBinding binding, IEvidence evidence)
    {
        this.plan = plan;
        var clock = Stopwatch.StartNew();
        Session = new(binding, () => clock.ElapsedMilliseconds, () => pipe?.Alive ?? !fault, new EvidenceJournal(evidence));
        formal = new FormalSmokeStop(plan, () => Session.FixtureRun);
        driver = new(Session, plan.Contract);
        listener = CoordinationPipe.Listen(); transport = Receive();
    }
    public void CollectorReady() { Session.CollectorReady(); ready.TrySetResult(); }
    private async Task Receive()
    {
        try
        {
            pipe = await CoordinationPipe.Accept(listener, Session.Binding, lifetime.Token);
            var hello = await pipe.Read(lifetime.Token);
            CoordinationSession.Require(hello.Kind == "Hello" && Guid.TryParseExact(hello.Challenge, "N", out _) &&
                hello.Binding with { Run = Session.Binding.Run } == Session.Binding, "coord_hello");
            challenge = hello.Challenge;
            await ready.Task.WaitAsync(lifetime.Token);
            await Send("Ready");
            readySent = true;
            while (!lifetime.IsCancellationRequested)
            {
                var message = await pipe.Read(lifetime.Token);
                CoordinationSession.Require(message.Binding == Session.Binding && message.Challenge == challenge, "coord_foreign_message");
                switch (message.Kind)
                {
                    case "Armed": Session.ArmStop(message.FixtureRun ?? ""); armed.TrySetResult(); break;
                    case "Backend": CoordinationSession.Require(message.Port is > 0 and <= 65535 && port == 0, "coord_backend_duplicate"); port = message.Port; break;
                    case "Close": close = true; break;
                    default: throw new IOException("coord_message_kind");
                }
            }
        }
        catch (OperationCanceledException) when (lifetime.IsCancellationRequested) { }
        catch
        {
            // EOF during an already requested normal Stop is not evidence of
            // cleanup. Continue OS/state observation until EndConfirmed/deadline.
            if (Session.Phase is CoordinationPhase.Stopping or CoordinationPhase.Ended) channelEnded = true;
            else { fault = true; Session.Abort("coord_disconnect_or_bad_message"); }
        }
    }
    private async Task Send(string kind, int backendPort = 0, string? permit = null)
    {
        var link = pipe;
        if (link == null || challenge.Length == 0) return;
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
        deadline.CancelAfter(1000);
        await link.Send(new(kind, Session.Binding, 0, challenge, Port: backendPort, Permit: permit), deadline.Token);
    }
    public async Task Update(Snapshot snapshot)
    {
        if (fault) throw new IOException("coord_transport_failed");
        if (!readySent || pipe == null || channelEnded) return;
        try { await Send("Tick"); }
        catch when (Session.Phase is CoordinationPhase.Stopping or CoordinationPhase.Ended) { channelEnded = true; return; }
        if (port == 0 || !armed.Task.IsCompletedSuccessfully || Session.Aborted) return;
        string? permit = null; int grantedPort = 0;
        driver.Update(snapshot, new(pipe.PeerPid, pipe.PeerBirth), port, (value, id) => { grantedPort = value; permit = id; });
        if (permit != null) await Send("Permit", grantedPort, permit);
    }
    public async Task<bool> RequestAsync(string identity, TimeSpan timeout)
    {
        if (identity != Session.Binding.Identity) return false;
        var elapsed = Stopwatch.StartNew();
        try
        {
            if (Session.Aborted)
            {
                try { await Send("Abort"); }
                catch { fault = true; } // delivery failure never suppresses formal Stop
            }
            await armed.Task.WaitAsync(TimeSpan.FromSeconds(5));
            var remaining = timeout - elapsed.Elapsed;
            return remaining >= TimeSpan.FromSeconds(2) && await formal.RequestAsync(identity, remaining);
        }
        catch { return false; }
    }
    public async ValueTask DisposeAsync()
    {
        lifetime.Cancel(); listener.Dispose(); pipe?.Dispose();
        try { await transport.WaitAsync(TimeSpan.FromSeconds(2)); }
        finally { lifetime.Dispose(); }
    }
}
