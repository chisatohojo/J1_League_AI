namespace J1AI.SmokeCoordination;

// Linked into the test-only Smoke runner; no dependency on the product host.
public sealed record RunBinding(string Run, string Identity, string Udf, string ManifestSha,
    string ObserverSha, string RunnerSha, string DotnetSha, string RunnerExeSha,
    string RuntimeSha, string InterpreterSha, string BackendSha);
public sealed record BackendIdentity(string Address, int Port, int Pid, long Birth);
public enum CoordinationPhase { Waiting, Ready, Armed, Permitted, Initializing, Stopping, Ended, Blocked }
public interface ICoordinationJournal { void Save(string name, object record); }
internal class CoordinationPolicy
{
    internal virtual bool ReadyRequired => true;
    internal virtual bool PeerAlive(bool observed) => observed;
    internal virtual bool RetainAbort => true;
    internal virtual bool BackendRequired => true;
    internal virtual bool VerdictRequired => true;
    internal virtual bool ExitRequired => true;
    internal virtual bool PreserveFaultOnAck => true;
}

// All decisions, including the initialization CALL boundary, are serialized.
// This does not claim that an SDK task can be cancelled after that call.
public sealed class CoordinationSession
{
    public const string FixedIdentity = "8f96edbb39b7d4d47cdad47c";
    public static string FixedUdf => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "J1AI", "Dashboard", FixedIdentity, "webview2-profile");
    private readonly object sync = new();
    private readonly Func<long> now;
    private readonly Func<bool> alive;
    private readonly ICoordinationJournal journal;
    private readonly long deadline;
    private readonly CoordinationPolicy policy;
    private bool ready, armed, abort, initialized, stopStarted, stopAcknowledged, failed;
    private BackendIdentity? backend;
    private long raw, verdict, latest;
    private string? fixtureRun;
    private int receipts;
    public RunBinding Binding { get; }
    public CoordinationPhase Phase { get; private set; }
    public bool Aborted { get { lock (sync) return abort; } }
    public bool StopAcknowledged { get { lock (sync) return stopAcknowledged; } }
    public bool Failed { get { lock (sync) return failed; } }
    // Linearization boundary shared with Abort. No new normal send is admitted
    // after the latch. An already admitted write is bounded/cancelled by adapter.
    internal Task SendNormal(Func<Task> send, bool permit = false)
    { lock (sync) { Require(!abort && !failed && (!permit || Phase == CoordinationPhase.Permitted), "coord_send_after_abort_or_stop"); return send(); } }
    public string? FixtureRun { get { lock (sync) return fixtureRun; } }
    public CoordinationSession(RunBinding binding, Func<long> milliseconds, Func<bool> peerAlive,
        ICoordinationJournal journal, long lifetimeMs = 360000)
        : this(binding, milliseconds, peerAlive, journal, lifetimeMs, new CoordinationPolicy()) { }
    internal CoordinationSession(RunBinding binding, Func<long> milliseconds, Func<bool> peerAlive,
        ICoordinationJournal journal, long lifetimeMs, CoordinationPolicy policy)
    {
        Require(binding.Identity == FixedIdentity && binding.Udf == FixedUdf, "coord_fixed_identity");
        Require(Guid.TryParseExact(binding.Run, "N", out _) &&
            new[] { binding.ManifestSha, binding.ObserverSha, binding.RunnerSha, binding.DotnetSha, binding.RunnerExeSha,
                binding.RuntimeSha, binding.InterpreterSha, binding.BackendSha }
                .All(IsSha), "coord_binding");
        Require(lifetimeMs is > 0 and <= 360000, "coord_deadline");
        Binding = binding; now = milliseconds; alive = peerAlive; this.journal = journal; this.policy = policy;
        deadline = checked(now() + lifetimeMs);
    }
    public static bool IsSha(string value) => value.Length == 64 && value.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f');
    public static void Require(bool condition, string reason) { if (!condition) throw new IOException(reason); }
    public void Validate(RunBinding binding)
    { lock (sync) { Require(binding == Binding, "coord_stale_or_foreign_run"); Check(); } }
    private void Check()
    {
        if (now() >= deadline || !policy.PeerAlive(alive())) AbortLocked("lease_dead_or_expired");
        Require(!abort, "coord_aborted");
    }
    private void Record(string kind, object value)
    {
        try { journal.Save($"coord-{++receipts:D4}", new { Binding, Kind = kind, Utc = DateTimeOffset.UtcNow, Value = value }); }
        catch { failed = abort = true; Phase = CoordinationPhase.Blocked; throw; }
    }
    public void CollectorReady()
    { lock (sync) { Check(); Require(!ready, "coord_duplicate_ready"); Record("collector-ready", new { Scope = "OS TCP polling only; startup and inter-poll traffic not proven" }); ready = true; Phase = CoordinationPhase.Ready; } }
    public void ArmStop(string run)
    {
        lock (sync)
        {
            Check(); Require((ready || !policy.ReadyRequired) && !armed && Guid.TryParseExact(run, "N", out _), "coord_stop_not_ready");
            Record("stop-armed", new { FixtureRun = run }); fixtureRun = run; armed = true; Phase = CoordinationPhase.Armed;
        }
    }
    public void Backend(BackendIdentity? found)
    {
        lock (sync)
        {
            Check(); Require(ready && armed, "coord_not_armed");
            if (found == null || found.Address != "127.0.0.1" || found.Port is not (> 0 and <= 65535) || found.Pid <= 0 || found.Birth <= 0 ||
                backend != null && backend != found)
            { AbortLocked("backend_unknown_or_changed"); throw new IOException("coord_backend"); }
            backend = found;
        }
    }
    public string Permit(BackendIdentity workerEndpoint)
    {
        lock (sync)
        {
            Check(); Require(ready && armed && (!policy.BackendRequired || backend != null && backend == workerEndpoint) && Phase == CoordinationPhase.Armed, "coord_start_not_authorized");
            string permit = Guid.NewGuid().ToString("N");
            Record("start-permit", new { Permit = permit, Backend = backend, FixtureRun = fixtureRun });
            Phase = CoordinationPhase.Permitted; return permit;
        }
    }
    public Task Initialize(Func<Task> call)
    {
        lock (sync)
        {
            Check(); Require(Phase == CoordinationPhase.Permitted && !initialized, "coord_initialize_without_permit");
            initialized = true; Phase = CoordinationPhase.Initializing;
            // Abort ordered before this lock always wins; no await in the critical section.
            return call();
        }
    }
    public void Abort(string reason) { lock (sync) AbortLocked(reason); }
    private void AbortLocked(string reason)
    {
        if (!policy.RetainAbort) return;
        if (abort) return;
        abort = failed = true; Phase = CoordinationPhase.Blocked;
        // Latch BEFORE attempting a possibly broken journal. Never erase an abort.
        try { Record("abort", new { Reason = reason, FixtureRun = fixtureRun }); } catch { }
    }
    public void SnapshotStarted(long sequence)
    { lock (sync) { Require(sequence > latest, "coord_snapshot_sequence"); latest = sequence; } }
    public void RawCommitted(long sequence)
    { lock (sync) { Require(sequence == latest && sequence > raw, "coord_raw_sequence"); raw = sequence; } }
    public void VerdictCommitted(long sequence)
    { lock (sync) { Require(sequence == latest && raw == sequence && sequence > verdict, "coord_verdict_before_raw"); verdict = sequence; } }
    public void PrepareStop(bool failure)
    {
        lock (sync)
        {
            if (stopStarted) return;
            if (!failure) { Check(); Require(armed && raw > 0 && raw == latest && (!policy.VerdictRequired || verdict == raw), "coord_stop_before_durable_verdict"); }
            else { abort = failed = true; }
            try { Record("stop-before", new { Failure = failure, Sequence = latest, Raw = raw, Verdict = verdict, FixtureRun = fixtureRun }); }
            catch { if (!failure) throw; }
            stopStarted = true; Phase = failed ? CoordinationPhase.Blocked : CoordinationPhase.Stopping;
        }
    }
    public void StopResult(bool acknowledged)
    {
        lock (sync)
        {
            Require(stopStarted, "coord_stop_not_requested");
            stopAcknowledged |= acknowledged;
            if (acknowledged && !policy.PreserveFaultOnAck) { failed = abort = false; Phase = CoordinationPhase.Stopping; }
            Record("stop-after", new { Acknowledged = acknowledged, ProcessExitConfirmed = false, FixtureRun = fixtureRun });
            if (!acknowledged) AbortLocked("formal_stop_unconfirmed");
        }
    }
    public void End(bool runtime, bool backendEnded, bool job, bool clean, bool noPending)
    {
        lock (sync)
        {
            Require(stopStarted && stopAcknowledged && (!policy.ExitRequired || runtime) && backendEnded && job && clean && noPending, "coord_end_unconfirmed");
            Record("end-after", new { Runtime = runtime, Backend = backendEnded, Job = job, Clean = clean, NoPending = noPending, FixtureRun = fixtureRun });
            Phase = failed ? CoordinationPhase.Blocked : CoordinationPhase.Ended;
        }
    }
}
