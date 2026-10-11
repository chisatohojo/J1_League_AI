namespace J1AI.SmokeNetworkObserver;

public sealed class Observation
{
    private readonly IdentityContract contract;
    private readonly IEvidence evidence;
    private readonly IStop stop;
    private readonly ObservationPolicy policy;
    public Observation(IdentityContract contract, IEvidence evidence, IStop stop) : this(contract, evidence, stop, new ObservationPolicy()) { }
    internal Observation(IdentityContract contract, IEvidence evidence, IStop stop, ObservationPolicy policy)
    { this.contract = contract; this.evidence = evidence; this.stop = stop; this.policy = policy; }
    public const string Identity = "8f96edbb39b7d4d47cdad47c";
    public const string Scope = "Periodic OS TCP snapshots for exact-UDF/executable/lineage and retained PID+birth identities; not all network traffic or SDK process identity.";
    private readonly Dictionary<int, long> births = [];
    private readonly HashSet<ProcessKey> seen = [];
    private HashSet<ProcessKey> previous = [];
    private double? lastStart, lastEnd;
    private string? run;
    private Endpoint? endpoint;
    private long count;
    private bool stopped, stopOk, fault, denied, finished, sawWorker, sawRuntime, endEvidenceConfirmed;
    private Summary? final;
    private Phase phase = Phase.READY;
    private readonly List<string> reasons = [];
    public Phase State => phase;

    public void Ready()
    {
        if (count != 0 || phase != Phase.READY) throw new InvalidOperationException("already_started");
        evidence.SaveVerified("ready", new { Identity, Scope, PeriodMs = 250, MaximumGapMs = 1500 });
    }

    public async Task Accept(Snapshot snapshot)
    {
        if (finished) throw new InvalidOperationException("already_finished");
        count++;
        Ownership ownership;
        try { ownership = OwnershipRules.Resolve(snapshot.Processes, contract); }
        catch { ownership = new([], [], null, ["ownership_exception"]); }
        var errors = snapshot.CollectionErrors.Concat(ownership.Errors).ToList();
        bool gap = snapshot.Sequence != count || !double.IsFinite(snapshot.MonotonicStartMs) || !double.IsFinite(snapshot.MonotonicEndMs) ||
            snapshot.MonotonicStartMs < 0 || snapshot.MonotonicEndMs < snapshot.MonotonicStartMs ||
            snapshot.MonotonicEndMs - snapshot.MonotonicStartMs > 1500 ||
            snapshot.QueryStartUtc.Offset != TimeSpan.Zero || snapshot.QueryEndUtc.Offset != TimeSpan.Zero ||
            snapshot.QueryEndUtc < snapshot.QueryStartUtc ||
            lastStart != null && (snapshot.MonotonicStartMs - lastStart > 1500 || snapshot.MonotonicStartMs <= lastStart ||
                snapshot.MonotonicStartMs < lastEnd);
        gap = policy.Gap(gap);
        if (gap) errors.Add("snapshot_gap");
        var current = ownership.Runtime.ToHashSet();
        foreach (var key in ownership.Runtime.Concat(ownership.Backend).Concat(ownership.Worker is { } w ? [w] : []))
        {
            if (births.TryGetValue(key.Pid, out long birth) && birth != key.CreatedFileTime) errors.Add("pid_reuse");
            births[key.Pid] = key.CreatedFileTime;
        }
        // Require a verified identity on both sides of the OS TCP query. Rows for
        // unrelated/unknown processes NEVER enter the persisted raw document.
        var rows = snapshot.Rows.Where(r => current.Any(k => policy.KeyMatches(k, r))).ToArray();
        if (snapshot.Rows.Any(r => current.Any(k => k.Pid == r.Pid) && !current.Any(k => policy.KeyMatches(k, r))))
            errors.Add("tcp_birth_mismatch");
        var raw = new RawSnapshot(snapshot.Sequence, snapshot.QueryStartUtc, snapshot.QueryEndUtc,
            lastStart is { } last ? snapshot.MonotonicStartMs - last : 0,
            snapshot.MonotonicEndMs - snapshot.MonotonicStartMs, gap,
            current.ToArray(), current.Except(previous).ToArray(), previous.Except(current).ToArray(),
            (snapshot.ConfirmedExited ?? []).Where(seen.Contains).ToArray(), rows,
            errors.Distinct().ToArray(), errors.Count == 0 ? "OS_IDENTITY_VERIFIED_SDK_IDENTITY_NOT_ASSERTED" : "UNKNOWN",
            snapshot.RuntimeEventConfirmed);
        lastStart = snapshot.MonotonicStartMs; lastEnd = snapshot.MonotonicEndMs;
        previous = current; seen.UnionWith(current);
        sawWorker |= ownership.Worker != null; sawRuntime |= current.Count > 0;
        if (snapshot.Run != null)
        {
            if (run != null && run != snapshot.Run) errors.Add("run_changed");
            run = snapshot.Run;
        }
        // Raw durability is ALWAYS attempted before endpoint/classification/Stop.
        try { await policy.BeforeRaw(stop); evidence.SaveVerified($"{count:D6}-raw", raw); }
        catch { await Fail(Phase.WRITE_FAILED, "raw_write_or_flush_failed"); return; }
        try
        {
            Endpoint? found = OwnershipRules.DiscoverBackend(snapshot.Rows, ownership);
            if (found != null)
            {
                if (endpoint != null && endpoint != found) errors.Add("backend_changed");
                endpoint = found;
            }
            // Startup may have no worker. Once runtime exists, no guessed port or grace allowance.
            if (policy.BackendRequired && current.Count > 0 && found == null) errors.Add("verified_backend_unavailable");
            var decisions = rows.Select(r => policy.Classify(r, endpoint)).ToArray();
            if (decisions.Any(d => d.Disposition == Disposition.Denied))
            { denied = true; phase = Phase.UNAUTHORIZED; reasons.Add("unauthorized_candidate"); }
            else if (errors.Count != 0 || decisions.Any(d => d.Disposition == Disposition.Unknown))
            { fault = true; phase = gap ? Phase.GAP : Phase.OWNERSHIP_UNKNOWN; reasons.AddRange(errors); reasons.AddRange(decisions.Where(d => d.Disposition == Disposition.Unknown).Select(d => d.Reason)); }
            else if (!fault && !denied) phase = Phase.OBSERVING;
            evidence.SaveVerified($"{count:D6}-verdict", new SnapshotVerdict(count, endpoint, decisions, phase, errors.ToArray()));
            if (denied || fault) await RequestStop();
            if (snapshot.EndConfirmed)
            {
                bool complete = count >= 2 && sawWorker && sawRuntime && run != null &&
                    snapshot.RuntimeEventConfirmed && current.Count == 0 && ownership.Worker == null && ownership.Backend.Length == 0;
                if (!complete) { fault = true; reasons.Add("end_evidence_incomplete"); }
                endEvidenceConfirmed = snapshot.RuntimeEventConfirmed && complete;
                await Complete(endEvidenceConfirmed);
            }
        }
        catch { await Fail(Phase.WRITE_FAILED, "classification_or_verdict_write_failed"); }
    }

    private async Task RequestStop()
    {
        if (stopped) return;
        stopped = true;
        try { stopOk = await stop.RequestAsync(Identity, TimeSpan.FromSeconds(10)).WaitAsync(TimeSpan.FromSeconds(10)); }
        catch { stopOk = false; }
        if (!stopOk) { fault = true; reasons.Add("formal_stop_unconfirmed"); }
    }
    public async Task Fail(Phase failure, string reason)
    {
        fault = true; phase = failure; reasons.Add(reason);
        // Even collector exceptions get a raw diagnostic first. It contains no
        // unknown socket data. Failure to persist it still cannot become success.
        try { evidence.SaveVerified($"{count:D6}-failure", new { Phase = failure, Reason = reason, Utc = DateTimeOffset.UtcNow }); }
        catch { phase = Phase.WRITE_FAILED; reasons.Add("failure_evidence_write_failed"); }
        await RequestStop();
    }
    public async Task<Summary> Complete(bool runtimeEndConfirmed)
    {
        if (finished) return final!;
        runtimeEndConfirmed &= endEvidenceConfirmed;
        if (!runtimeEndConfirmed || !sawRuntime || count < 2) { fault = true; reasons.Add("observation_incomplete"); }
        if (!fault && !denied) phase = Phase.NORMAL_END;
        var result = Summary(runtimeEndConfirmed);
        try { evidence.SaveVerified("result", result); }
        catch
        {
            await Fail(Phase.WRITE_FAILED, "result_write_failed");
            result = Summary(runtimeEndConfirmed);
        }
        finished = true; final = result; return result;
    }
    private Summary Summary(bool ended) => new(fault ? Result.INCONCLUSIVE : denied ? Result.BLOCKED : Result.PASS_OBSERVED_SCOPE,
        phase, count, Scope, reasons.Distinct().ToArray(), stopped, stopOk, ended);
}
