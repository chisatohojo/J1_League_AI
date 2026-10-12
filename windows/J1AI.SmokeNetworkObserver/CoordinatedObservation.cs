using System.Diagnostics;
using System.IO.Pipes;
using J1AI.SmokeCoordination;

namespace J1AI.SmokeNetworkObserver;

internal sealed class EvidenceJournal(IEvidence evidence) : ICoordinationJournal
{ public void Save(string name, object record) => evidence.SaveVerified(name, record); }
internal interface IAbortStop : IStop
{
    Task AbortAsync(string reason);
    Task FinishAsync();
    bool Faulted { get; }
}
internal class CoordinationAdapterPolicy
{
    internal virtual bool DeliverFailedStopAbort => true;
    internal virtual bool SuppressAbortedTick => true;
    internal virtual bool RejectStoppingProtocol => true;
    internal virtual bool PreserveFaultOnAck => true;
}

// Control plane only. Collector remains the authority for worker/backend identity.
internal sealed class CoordinatedObservation : IAbortStop, IAsyncDisposable
{
    private readonly NamedPipeServerStream? listener;
    private readonly CancellationTokenSource lifetime = new(TimeSpan.FromSeconds(360));
    private readonly CancellationTokenSource normalSends = new();
    private readonly TaskCompletionSource ready = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource armed = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly SemaphoreSlim output = new(1);
    private readonly object abortSync = new(), stopSync = new();
    private readonly Task transport;
    private ICoordinationLink? pipe;
    private string challenge = "";
    private volatile int port;
    private volatile bool close, fault, channelEnded, readySent;
    private Task? abortDelivery;
    private Task<bool>? formalDelivery;
    private readonly IStop formal;
    private readonly CoordinationDriver driver;
    private readonly TimeProvider time;
    private readonly CoordinationAdapterPolicy policy;
    public CoordinationSession Session { get; }
    public bool CloseRequested => close;
    public bool Faulted => fault && (policy.PreserveFaultOnAck || !Session.StopAcknowledged);
    internal bool ChannelEnded => channelEnded;
    internal bool ReadySent => readySent;
    internal Task Receiver => transport;
    internal bool AbortDelivered { get; private set; }
    public static RunBinding Bind(ApprovalPlan plan) => new(Guid.NewGuid().ToString("N"), plan.Identity, plan.Contract.Udf,
        plan.ManifestSha, plan.ObserverHash, plan.FileHashes[plan.Contract.Runner], plan.FileHashes[plan.Contract.Dotnet], plan.FileHashes[plan.Contract.RunnerExe],
        plan.FileHashes[plan.Contract.RuntimeExecutable], plan.FileHashes[plan.Contract.PythonExecutable], plan.FileHashes[plan.Contract.Backend]);

    internal CoordinatedObservation(ApprovalPlan plan, RunBinding binding, IEvidence evidence)
    {
        time = TimeProvider.System; policy = new();
        var clock = Stopwatch.StartNew();
        Session = new(binding, () => clock.ElapsedMilliseconds, () => pipe?.Alive ?? !fault, new EvidenceJournal(evidence));
        formal = new FormalSmokeStop(plan, () => Session.FixtureRun);
        driver = new(Session, plan.Contract);
        listener = CoordinationPipe.Listen(); transport = Receive(Accept);
        async Task<ICoordinationLink> Accept(CancellationToken token) => await CoordinationPipe.Accept(listener, binding, token);
    }
    // In-memory transport/clock/receiver seam; same Receive/Send/Update/Stop code.
    internal CoordinatedObservation(IdentityContract contract, RunBinding binding, IEvidence evidence,
        Func<CancellationToken, Task<ICoordinationLink>> accept, IStop formal, TimeProvider time,
        CoordinationAdapterPolicy? policy = null, CoordinationPolicy? sessionPolicy = null)
    {
        this.time = time; this.policy = policy ?? new(); this.formal = formal;
        long start = time.GetTimestamp();
        Session = new(binding, () => (long)time.GetElapsedTime(start).TotalMilliseconds,
            () => pipe?.Alive ?? !fault, new EvidenceJournal(evidence), 360000, sessionPolicy ?? new());
        driver = new(Session, contract); transport = Receive(accept);
    }
    public void CollectorReady() { Session.CollectorReady(); ready.TrySetResult(); }
    private async Task Receive(Func<CancellationToken, Task<ICoordinationLink>> accept)
    {
        try
        {
            pipe = await accept(lifetime.Token);
            var hello = await pipe.Read(lifetime.Token);
            CoordinationSession.Require(hello.Kind == "Hello" && Guid.TryParseExact(hello.Challenge, "N", out _) &&
                hello.Binding with { Run = Session.Binding.Run } == Session.Binding, "coord_hello");
            challenge = hello.Challenge;
            await ready.Task.WaitAsync(lifetime.Token);
            await Send("Ready"); readySent = true;
            while (!lifetime.IsCancellationRequested)
            {
                var message = await pipe.Read(lifetime.Token);
                CoordinationSession.Require(pipe.Alive && message.Binding == Session.Binding && message.Challenge == challenge, "coord_foreign_message_or_peer");
                CoordinationSession.Require(Session.Phase is not (CoordinationPhase.Stopping or CoordinationPhase.Ended or CoordinationPhase.Blocked), "coord_message_after_stop");
                switch (message.Kind)
                {
                    case "Armed": Session.ArmStop(message.FixtureRun ?? ""); armed.TrySetResult(); break;
                    case "Backend": CoordinationSession.Require(message.Port is > 0 and <= 65535 && port == 0 && armed.Task.IsCompletedSuccessfully, "coord_backend_duplicate_or_unarmed"); port = message.Port; break;
                    case "Close": CoordinationSession.Require(!close && armed.Task.IsCompletedSuccessfully, "coord_duplicate_or_unarmed_close"); close = true; break;
                    default: throw new IOException("coord_message_kind");
                }
            }
        }
        catch (OperationCanceledException) when (lifetime.IsCancellationRequested) { }
        catch (CoordinationEofException) when (Session.StopAcknowledged && !Session.Aborted &&
            Session.Phase is CoordinationPhase.Stopping or CoordinationPhase.Ended)
        { CloseChannel(); } // NOT cleanup proof
        catch
        {
            if (!policy.RejectStoppingProtocol && Session.Phase is CoordinationPhase.Stopping or CoordinationPhase.Ended)
            { channelEnded = true; return; }
            fault = true; await AbortAsync("coord_disconnect_or_bad_message");
        }
    }
    private async Task Send(string kind, int backendPort = 0, string? permit = null)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(1), time);
        using var token = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token, deadline.Token,
            kind == "Abort" ? CancellationToken.None : normalSends.Token);
        await output.WaitAsync(token.Token);
        try
        {
            var link = pipe;
            CoordinationSession.Require(link != null && challenge.Length != 0 && !channelEnded, "coord_channel_unavailable");
            var message = new CoordinationMessage(kind, Session.Binding, 0, challenge, Port: backendPort, Permit: permit);
            if (kind == "Abort") await link!.Send(message, token.Token).WaitAsync(token.Token);
            else if (kind == "Tick" && !policy.SuppressAbortedTick) await link!.Send(message, token.Token).WaitAsync(token.Token);
            else await Session.SendNormal(() => link!.Send(message, token.Token), kind == "Permit").WaitAsync(token.Token);
        }
        finally { output.Release(); }
    }
    public Task AbortAsync(string reason)
    {
        lock (abortSync)
        {
            Session.Abort(reason);
            if (!policy.DeliverFailedStopAbort) return Task.CompletedTask;
            normalSends.Cancel(); return abortDelivery ??= DeliverAbort();
        }
    }
    private async Task DeliverAbort()
    {
        try { await Send("Abort"); AbortDelivered = true; }
        catch { fault = true; AbortDelivered = false; }
        finally
        {
            // Revoke lease even after successful Abort; never renew a revoked permit.
            CloseChannel();
        }
    }
    private void CloseChannel()
    {
        channelEnded = true;
        bool closeFailed = false;
        try { pipe?.Dispose(); } catch { closeFailed = fault = true; }
        try { listener?.Dispose(); } catch { closeFailed = fault = true; }
        // A failed close is NOT delivery success. With normal sends revoked,
        // worker receive timeout/lease monitoring still requires local Stop.
        if (closeFailed) AbortDelivered = false;
    }
    public async Task Update(Snapshot snapshot)
    {
        if (Session.Aborted && policy.SuppressAbortedTick) { await AbortAsync("coord_update_aborted"); return; }
        if (Session.Phase == CoordinationPhase.Ended) return;
        if (Faulted) throw new IOException("coord_transport_failed");
        if (!readySent || pipe == null || channelEnded) return;
        try
        {
            await Send("Tick");
            if (port == 0 || !armed.Task.IsCompletedSuccessfully || Session.Aborted) return;
            string? permit = null; int grantedPort = 0;
            driver.Update(snapshot, new(pipe.PeerPid, pipe.PeerBirth), port, (value, id) => { grantedPort = value; permit = id; });
            if (permit != null) await Send("Permit", grantedPort, permit);
        }
        catch { fault = true; await AbortAsync("coord_update_failed"); throw; }
    }
    public Task<bool> RequestAsync(string identity, TimeSpan timeout)
    {
        if (identity != Session.Binding.Identity) return Task.FromResult(false);
        lock (stopSync) return formalDelivery ??= DeliverFormal(identity, timeout);
    }
    private async Task<bool> DeliverFormal(string identity, TimeSpan timeout)
    {
        long started = time.GetTimestamp(); bool acknowledged = false;
        try
        {
            if (Session.Aborted) await AbortAsync("coord_stop_aborted");
            await armed.Task.WaitAsync(TimeSpan.FromSeconds(5), time);
            var remaining = timeout - time.GetElapsedTime(started);
            acknowledged = remaining >= TimeSpan.FromSeconds(2) &&
                await formal.RequestAsync(identity, remaining).WaitAsync(remaining, time);
            return acknowledged;
        }
        catch { return false; }
        finally { if (!acknowledged) await AbortAsync("formal_stop_unconfirmed"); }
    }
    public async Task FinishAsync()
    {
        // Do not publish PASS while Receive can still discard a queued violation.
        try { await transport.WaitAsync(TimeSpan.FromSeconds(2), time); }
        catch { fault = true; await AbortAsync("coord_end_channel_unconfirmed"); }
    }
    public async ValueTask DisposeAsync()
    {
        lifetime.Cancel(); normalSends.Cancel(); CloseChannel();
        try
        {
            await transport.WaitAsync(TimeSpan.FromSeconds(2));
            if (abortDelivery != null) await abortDelivery.WaitAsync(TimeSpan.FromSeconds(2));
        }
        finally { normalSends.Dispose(); lifetime.Dispose(); }
    }
}
