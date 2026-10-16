using System.Text;
using System.Runtime.ExceptionServices;
using J1AI.SmokeMigration;

namespace J1AI.SmokeMigration.Tests;

internal sealed record MockFile(int Index, string Name, byte[] OldBytes, byte[] NewBytes, string Role)
{
    internal string OldHash => Contract.Hash(OldBytes);
    internal string NewHash => Contract.Hash(NewBytes);
    internal bool Rewrite => Role is "RunnerReplace" or "Manifest" or "State" or "ObserverReplace";
}
internal sealed class Injected(string code) : IOException(code);
internal sealed class TransactionPolicy
{
    internal Action<string, int> At = (_, _) => { };
    // Post-cleanup injection runs AFTER the actual resource release. Never a
    // substitute for releasing a mock handle/mutex, and never a product hook.
    internal Action<string> AfterCleanup = _ => { };
    internal Action BeforePendingObservation = () => { };
    // Explicit mutation oracles in test assembly ONLY. No product flags.
    internal bool VerifyBackup = true, RequireMarker = true, VerifyFinal = true;
}
internal enum CommitDisposition { NOT_COMMITTED, COMMITTED, INDETERMINATE }
internal enum PendingDisposition { PRESENT, ABSENT, UNKNOWN }
internal sealed record TransactionProblem(string Stage, Exception Error);
internal sealed record TransactionResult(CommitDisposition Commit, PendingDisposition Pending,
    string Stage, TransactionProblem[] Problems)
{
    internal bool Successful => Commit == CommitDisposition.COMMITTED && Pending == PendingDisposition.ABSENT && Problems.Length == 0;
}
internal sealed class Transaction(MockSandbox sandbox, MockFile[] files, TransactionPolicy policy)
{
    internal readonly List<string> Events = [];
    internal TransactionResult? Result { get; private set; }
    private string stage = "start";
    private string attempt = "";
    private readonly string thread = Environment.CurrentManagedThreadId.ToString();
    private readonly string[] initialActive = files.Select(f => f.Name).Order(StringComparer.Ordinal).ToArray();
    internal static MockFile[] Fixture() => Enumerable.Range(0, 47).Select(i => new MockFile(i, $"file-{i:000}.bin",
        Encoding.UTF8.GetBytes("old-synthetic-" + i), Encoding.UTF8.GetBytes("new-synthetic-" + i),
        i < 6 ? "RunnerReplace" : i < 19 ? "RunnerMaintain" : i == 31 ? "Manifest" : i == 32 ? "State" : i >= 42 ? "ObserverReplace" : "Retain")).ToArray();
    internal static void Populate(MockSandbox s, MockFile[] files)
    { foreach (var f in files) { s.Put("active", f.Name, f.OldBytes); s.Put("candidate", f.Name, f.Rewrite ? f.NewBytes : f.OldBytes); } }
    private void Stage(string name, int index = -1)
    { stage = name; ObservationSession.Current?.AdvanceStage(attempt, name, index); Events.Add(name + ":" + index); policy.At(name, index); }
    internal TransactionResult Execute()
    {
        attempt = Guid.NewGuid().ToString("N");
        Mutex? gate = null, observer = null;
        FileStream? mockLock = null;
        bool owned = false, removalAttempted = false, committed = false;
        var problems = new List<TransactionProblem>();
        try
        {
            Contract.Require(thread == Environment.CurrentManagedThreadId.ToString(), "mutex_thread_affinity");
            stage = "gate";
            gate = new Mutex(false, @"Local\J1AI.Migration.MockGate." + sandbox.Identity, out bool created);
            Contract.Require(created, "mock_gate_busy");
            observer = new Mutex(false, @"Local\J1AI.Migration.MockObserver." + sandbox.Identity);
            Stage("preflight"); sandbox.Validate();
            Contract.Require(!sandbox.Exists("active", Contract.Pending), "pending_exists");
            Contract.Require(sandbox.Names("active").SequenceEqual(initialActive), "active_inventory");
            Contract.Require(sandbox.Names("candidate").SequenceEqual(initialActive), "candidate_inventory");
            Contract.Require(sandbox.Names("backup").Length == 0, "backup_collision");
            foreach (var f in files)
            { Contract.Require(Contract.Hash(sandbox.Read("active", f.Name)) == f.OldHash, "old_sha"); Contract.Require(Contract.Hash(sandbox.Read("candidate", f.Name)) == (f.Rewrite ? f.NewHash : f.OldHash), "source_sha"); }
            Stage("exclusion");
            try { owned = observer.WaitOne(0); }
            catch (AbandonedMutexException) { observer.ReleaseMutex(); throw new InvalidDataException("abandoned_review_required"); }
            Contract.Require(owned, "mock_observer_busy");
            // Mock lock is NOT the real smoke.lock and does not touch fixed IPC.
            mockLock = sandbox.AcquireLock();
            Stage("locked");
            foreach (var f in files)
            { Stage("backup", f.Index); sandbox.Put("backup", f.Name, sandbox.Read("active", f.Name)); }
            Stage("backup_flush");
            foreach (var f in files)
            {
                Stage("backup_readback", f.Index);
                if (policy.VerifyBackup) Contract.Require(Contract.Hash(sandbox.Read("backup", f.Name)) == f.OldHash, "backup_sha");
            }
            Stage("backups_verified");
            sandbox.Put("active", Contract.Pending, Encoding.UTF8.GetBytes("synthetic-transaction-pending:" + sandbox.Identity));
            Stage("pending_flushed");
            foreach (string role in new[] { "RunnerReplace", "Manifest", "State", "ObserverReplace" })
                foreach (var f in files.Where(f => f.Role == role))
                {
                    Stage("before_replace", f.Index); sandbox.Validate();
                    if (policy.RequireMarker) Contract.Require(sandbox.Exists("active", Contract.Pending), "marker_missing");
                    byte[] bytes = sandbox.Read("candidate", f.Name); Contract.Require(Contract.Hash(bytes) == f.NewHash, "source_sha");
                    sandbox.Replace(f.Name, bytes, f.OldHash); Stage("replaced", f.Index);
                }
            Stage("final_readback");
            foreach (var f in files)
            {
                string expected = f.Rewrite ? f.NewHash : f.OldHash;
                if (policy.VerifyFinal) Contract.Require(Contract.Hash(sandbox.Read("active", f.Name)) == expected, "final_sha");
            }
            Contract.Require(sandbox.Names("active").SequenceEqual(initialActive.Append(Contract.Pending).Order(StringComparer.Ordinal)), "final_inventory");
            sandbox.Validate(); Stage("final_verified");
            Stage("commit_permitted");
            Stage("pending_remove"); // Last fallible transaction hook BEFORE removal.
            removalAttempted = true;
            sandbox.Remove("active", Contract.Pending);
            policy.BeforePendingObservation();
            Contract.Require(!sandbox.Names("active").Contains(Contract.Pending), "pending_remove_unconfirmed");
            // Commit point: final validation succeeded AND removal was observed.
            // Completion is a record, not a fallible policy.At callback.
            committed = true; stage = "committed"; Events.Add("committed:-1");
        }
        catch (Exception e) { problems.Add(new(stage, e)); }
        finally
        {
            // Try EVERY actual release, recording rather than masking any error.
            // No rollback, pending recreation, CLEAN rewrite or retry.
            void Release(string name, Action release)
            {
                try { release(); policy.AfterCleanup(name); }
                catch (Exception e) { problems.Add(new("cleanup:" + name, e)); }
            }
            if (mockLock != null) Release("lock_dispose", mockLock.Dispose);
            if (owned) Release("mutex_release", () =>
            {
                Contract.Require(thread == Environment.CurrentManagedThreadId.ToString(), "mutex_thread_affinity"); observer!.ReleaseMutex();
            });
            if (observer != null) Release("observer_dispose", observer.Dispose);
            if (gate != null) Release("gate_dispose", gate.Dispose);
        }
        PendingDisposition pending;
        try { policy.BeforePendingObservation(); pending = sandbox.Names("active").Contains(Contract.Pending) ? PendingDisposition.PRESENT : PendingDisposition.ABSENT; }
        catch (Exception e) { pending = PendingDisposition.UNKNOWN; problems.Add(new("pending_observation", e)); }
        // A removal operation may throw after deletion/handle close. Inspect the
        // real mock namespace: absent means committed WITH errors, not rollback.
        var disposition = committed || (removalAttempted && pending == PendingDisposition.ABSENT)
            ? CommitDisposition.COMMITTED : removalAttempted && pending == PendingDisposition.UNKNOWN
                ? CommitDisposition.INDETERMINATE : CommitDisposition.NOT_COMMITTED;
        Result = new(disposition, pending, problems.Count == 0 ? stage : problems[0].Stage, problems.ToArray());
        ObservationSession.Current?.TransactionEnded(attempt, Result);
        if (problems.Count > 0) ExceptionDispatchInfo.Capture(problems[0].Error).Throw();
        Contract.Require(Result.Successful, "transaction_result_unconfirmed");
        return Result;
    }
}
