using System.Text.Json;
using J1AI.SmokeCoordination;
using J1AI.SmokeNetworkObserver;

namespace J1AI.SmokeNetworkObserver.Tests;

internal static class CoordinationTests
{
    internal static readonly string[] Mutations = ["ready-bypass", "dead-peer", "drop-abort", "backend-bypass", "stop-before-verdict", "ack-is-exit"];
    private static string? mutation;
    private static RunBinding Binding => new(new string('1', 32), CoordinationSession.FixedIdentity, CoordinationSession.FixedUdf,
        new string('a', 64), new string('b', 64), new string('c', 64), new string('d', 64), new string('e', 64), new string('f', 64), new string('a', 64), new string('b', 64));
    private static BackendIdentity Backend => new("127.0.0.1", 32123, 123, 456);
    private sealed class Mutant : CoordinationPolicy
    {
        internal override bool ReadyRequired => mutation != "ready-bypass";
        internal override bool PeerAlive(bool observed) => mutation == "dead-peer" || observed;
        internal override bool RetainAbort => mutation != "drop-abort";
        internal override bool BackendRequired => mutation != "backend-bypass";
        internal override bool VerdictRequired => mutation != "stop-before-verdict";
        internal override bool ExitRequired => mutation != "ack-is-exit";
    }
    private sealed class Journal : ICoordinationJournal
    {
        internal readonly Dictionary<string, object> Records = [];
        internal bool Fail;
        public void Save(string name, object value) { if (Fail) throw new IOException("injected_journal"); Records.Add(name, value); }
    }
    private sealed class Rig
    {
        internal long Now;
        internal bool Alive = true;
        internal readonly Journal Journal = new();
        internal readonly CoordinationSession Session;
        internal Rig() => Session = new(Binding, () => Now, () => Alive, Journal, 360000, new Mutant());
        internal void Arm() { Session.CollectorReady(); Session.ArmStop(new string('2', 32)); }
        internal void Permit() { Arm(); Session.Backend(Backend); Session.Permit(Backend); }
        internal void Durable() { Session.SnapshotStarted(1); Session.RawCommitted(1); Session.VerdictCommitted(1); }
    }
    private static void Check(bool condition) => Program.Check(condition, "coordination_assertion");
    private static void Reject(Action action)
    {
        bool rejected = false; try { action(); } catch (IOException) { rejected = true; }
        Check(rejected);
    }
    internal static void Register(Action<string, Action> add, Action<string, Func<Task>> async, string? mutant = null)
    {
        mutation = mutant;
        add("coord_ready_permit_initialize", () =>
        { var r = new Rig(); r.Permit(); int calls = 0; r.Session.Initialize(() => { calls++; return Task.CompletedTask; }).GetAwaiter().GetResult(); Check(calls == 1); });
        add("coord_ready_before_start_required", () =>
        { var r = new Rig(); Reject(() => r.Session.ArmStop(new string('2', 32))); });
        add("coord_ready_then_observer_death", () =>
        { var r = new Rig(); r.Permit(); r.Alive = false; Reject(() => r.Session.Initialize(() => Task.CompletedTask)); });
        add("coord_stale_run_ready", () => Reject(() => new Rig().Session.Validate(Binding with { Run = new string('3', 32) })));
        add("coord_foreign_identity", () => Reject(() => new CoordinationSession(Binding with { Identity = "other" }, () => 0, () => true, new Journal())));
        add("coord_other_udf_rejected", () => Reject(() => new CoordinationSession(Binding with { Udf = Binding.Udf + "-other" }, () => 0, () => true, new Journal())));
        add("coord_expired_run", () => { var r = new Rig { Now = 360000 }; Reject(r.Session.CollectorReady); });
        add("coord_abort_after_permit_before_initialize", () =>
        { var r = new Rig(); r.Permit(); r.Session.Abort("injected"); Reject(() => r.Session.Initialize(() => Task.CompletedTask)); });
        add("coord_abort_before_stop_event_retained", () =>
        { var r = new Rig(); r.Session.Abort("before-event"); Reject(r.Session.CollectorReady); Check(r.Session.Aborted); });
        add("coord_stop_not_armed_no_permit", () =>
        { var r = new Rig(); r.Session.CollectorReady(); Reject(() => r.Session.Backend(Backend)); });
        add("coord_backend_missing_no_permit", () =>
        { var r = new Rig(); r.Arm(); Reject(() => r.Session.Permit(Backend)); });
        add("coord_backend_multiple_or_unknown", () => { var r = new Rig(); r.Arm(); Reject(() => r.Session.Backend(null)); });
        foreach (var variant in new[] { Backend with { Port = 32124 }, Backend with { Birth = 999 }, Backend with { Pid = 999 }, Backend with { Address = "127.0.0.2" } })
            add("coord_backend_changed_" + variant, () => { var r = new Rig(); r.Permit(); Reject(() => r.Session.Backend(variant)); });
        add("coord_ipc_disconnect_no_init", () => { var r = new Rig(); r.Permit(); r.Session.Abort("disconnect"); Reject(() => r.Session.Initialize(() => Task.CompletedTask)); });
        add("coord_collector_failure_latches_abort", () => { var r = new Rig(); r.Permit(); r.Session.Abort("collector"); Check(r.Session.Aborted); });
        add("coord_stop_before_raw_rejected", () => { var r = new Rig(); r.Arm(); Reject(() => r.Session.PrepareStop(false)); });
        add("coord_stop_before_verdict_rejected", () =>
        { var r = new Rig(); r.Arm(); r.Session.SnapshotStarted(1); r.Session.RawCommitted(1); Reject(() => r.Session.PrepareStop(false)); });
        add("coord_new_snapshot_invalidates_stop_barrier", () => { var r = new Rig(); r.Arm(); r.Durable(); r.Session.SnapshotStarted(2); Reject(() => r.Session.PrepareStop(false)); });
        add("coord_verdict_before_raw_rejected", () => { var r = new Rig(); r.Session.SnapshotStarted(1); Reject(() => r.Session.VerdictCommitted(1)); });
        add("coord_failed_storage_abort_preserved", () => { var r = new Rig(); r.Journal.Fail = true; r.Session.PrepareStop(true); Check(r.Session.Aborted && r.Session.Phase == CoordinationPhase.Blocked); });
        add("coord_stop_ack_missing", () => { var r = new Rig(); r.Arm(); r.Durable(); r.Session.PrepareStop(false); r.Session.StopResult(false); Reject(() => r.Session.End(true, true, true, true, true)); });
        add("coord_ack_not_process_exit", () =>
        { var r = new Rig(); r.Arm(); r.Durable(); r.Session.PrepareStop(false); r.Session.StopResult(true); Reject(() => r.Session.End(false, true, true, true, true)); });
        for (int missing = 0; missing < 5; missing++)
        {
            int absent = missing;
            add("coord_cleanup_missing_" + missing, () => { var r = new Rig(); r.Arm(); r.Durable(); r.Session.PrepareStop(false); r.Session.StopResult(true); var f = Enumerable.Repeat(true, 5).ToArray(); f[absent] = false; Reject(() => r.Session.End(f[0], f[1], f[2], f[3], f[4])); });
        }
        add("coord_normal_stop_end_receipts_ordered", () =>
        {
            var r = new Rig(); r.Arm(); r.Durable(); r.Session.PrepareStop(false); int count = r.Journal.Records.Count;
            r.Session.PrepareStop(false); Check(r.Journal.Records.Count == count);
            r.Session.StopResult(true); r.Session.End(true, true, true, true, true);
            Check(r.Session.Phase == CoordinationPhase.Ended && r.Journal.Records.Count == count + 2);
        });
        add("worker_gate_requires_ready_and_stop_arm", () =>
        { var g = new WorkerGate(Binding, () => 0, () => true); Reject(() => g.Grant(Binding, Backend.Port, new string('4', 32))); });
        add("worker_gate_stale_ready_rejected", () =>
        { var g = new WorkerGate(Binding, () => 0, () => true); Reject(() => g.Ready(Binding with { Run = new string('4', 32) })); });
        add("worker_gate_abort_no_initialization", () =>
        { var g = new WorkerGate(Binding, () => 0, () => true); g.Ready(Binding); g.Arm(); g.Grant(Binding, Backend.Port, new string('4', 32)); g.Abort(); Reject(() => g.Initialize(Backend.Port, () => Task.CompletedTask)); });
        add("worker_abort_before_ready_cannot_be_cleared", () =>
        { var g = new WorkerGate(Binding, () => 0, () => true); g.Abort(); g.Ready(Binding); g.Pulse(Binding); Reject(g.Arm); Check(g.Aborted); });
        add("worker_gate_lost_heartbeat_not_revived", () =>
        { long now = 0; var g = new WorkerGate(Binding, () => now, () => true); g.Ready(Binding); g.Arm(); now = 1501; g.Pulse(Binding); Check(g.Aborted); });
        add("worker_gate_dead_peer", () =>
        { bool alive = true; var g = new WorkerGate(Binding, () => 0, () => alive); g.Ready(Binding); g.Arm(); g.Grant(Binding, Backend.Port, new string('4', 32)); alive = false; Reject(() => g.Initialize(Backend.Port, () => Task.CompletedTask)); });
        add("worker_gate_wrong_port", () =>
        { var g = new WorkerGate(Binding, () => 0, () => true); g.Ready(Binding); g.Arm(); g.Grant(Binding, Backend.Port, new string('4', 32)); Reject(() => g.Initialize(Backend.Port + 1, () => Task.CompletedTask)); });
        async("coord_abort_at_deterministic_barrier", async () =>
        { var r = new Rig(); r.Permit(); var barrier = new TaskCompletionSource(); var pending = Task.Run(async () => { await barrier.Task; Reject(() => r.Session.Initialize(() => Task.CompletedTask)); }); r.Session.Abort("before-init"); barrier.SetResult(); await pending; });
        async("coord_observation_normal_stop_single_delivery", async () =>
        { var trace = new List<string>(); var evidence = new MemoryEvidence(trace); var stop = new FakeStop(trace); var r = new Rig(); r.Arm(); var o = new Observation(Values.Contract, evidence, stop, new ObservationPolicy(), r.Session); o.Ready(); await o.Accept(Values.Snapshot()); await o.RequestNormalStop(); await o.RequestNormalStop(); Check(stop.Calls == 1 && trace.IndexOf("durable:000001-verdict") < trace.IndexOf("stop")); });
        async("coord_concurrent_stop_single_delivery", async () =>
        { var trace = new List<string>(); var stop = new FakeStop(trace); var r = new Rig(); r.Arm(); var o = new Observation(Values.Contract, new MemoryEvidence(trace), stop, new ObservationPolicy(), r.Session); await o.Accept(Values.Snapshot()); var begin = new TaskCompletionSource(); var requests = Enumerable.Range(0, 8).Select(_ => Task.Run(async () => { await begin.Task; await o.RequestNormalStop(); })).ToArray(); begin.SetResult(); await Task.WhenAll(requests); Check(stop.Calls == 1); });
        async("coord_snapshot_gap_stays_inconclusive", async () =>
        { var trace = new List<string>(); var o = new Observation(Values.Contract, new MemoryEvidence(trace), new FakeStop(trace)); await o.Accept(Values.Snapshot()); await o.Accept(Values.Snapshot(2, start: 2001)); Check((await o.Complete(false)).Result == Result.INCONCLUSIVE); });
        async("coord_fake_worker_collector_backend_stop_end_to_end", async () =>
        {
            var r = new Rig(); r.Arm(); var trace = new List<string>(); var stop = new FakeStop(trace);
            var observer = new Observation(Values.Contract, new MemoryEvidence(trace), stop, new ObservationPolicy(), r.Session);
            var worker = new WorkerGate(Binding, () => r.Now, () => r.Alive); worker.Ready(Binding); worker.Arm();
            observer.Ready(); await observer.Accept(Values.Snapshot());
            var driver = new CoordinationDriver(r.Session, Values.Contract);
            driver.Update(Values.Snapshot(), new(101, 1100), 45678, (port, permit) => worker.Grant(Binding, port, permit));
            int initialized = 0; await worker.Initialize(45678, () => { initialized++; return Task.CompletedTask; });
            await observer.RequestNormalStop(); await observer.Accept(Values.End());
            Check(initialized == 1 && stop.Calls == 1 && r.Session.Phase == CoordinationPhase.Ended &&
                (await observer.Complete(true)).Result == Result.PASS_OBSERVED_SCOPE);
        });
        add("coord_driver_foreign_worker_rejected", () =>
        { var r = new Rig(); r.Arm(); Reject(() => new CoordinationDriver(r.Session, Values.Contract).Update(Values.Snapshot(), new(101, 9999), 45678, (_, _) => throw new InvalidOperationException("unexpected_grant"))); });
        add("coord_driver_backend_multiple_rejected", () =>
        { var r = new Rig(); r.Arm(); var s = Values.Snapshot(rows: [Values.Listener, Values.Listener with { LocalPort = 33333 }]); Reject(() => new CoordinationDriver(r.Session, Values.Contract).Update(s, new(101, 1100), 45678, (_, _) => throw new InvalidOperationException("unexpected_grant"))); });
        add("coord_driver_url_port_mismatch_rejected", () =>
        { var r = new Rig(); r.Arm(); Reject(() => new CoordinationDriver(r.Session, Values.Contract).Update(Values.Snapshot(), new(101, 1100), 9999, (_, _) => throw new InvalidOperationException("unexpected_grant"))); });
        add("coord_stop_cleanup_does_not_regrant_missing_backend", () =>
        { var r = new Rig(); r.Arm(); r.Durable(); r.Session.PrepareStop(false); new CoordinationDriver(r.Session, Values.Contract).Update(Values.End(), new(101, 1100), 45678, (_, _) => throw new InvalidOperationException("unexpected_grant")); });
        add("coord_protocol_decode_bounded_message", () =>
        { var m = new CoordinationMessage("Ready", Binding, 1, new string('5', 32)); Check(CoordinationPipe.Decode(JsonSerializer.SerializeToUtf8Bytes(m), 1) == m); });
        add("coord_protocol_stale_sequence", () =>
        { var m = new CoordinationMessage("Ready", Binding, 1, new string('5', 32)); Reject(() => CoordinationPipe.Decode(JsonSerializer.SerializeToUtf8Bytes(m), 2)); });
        add("coord_protocol_oversize_rejected", () => Reject(() => CoordinationPipe.Decode(new byte[8193], 1)));
        add("coord_protocol_duplicate_binding_field", () =>
        { byte[] message = System.Text.Encoding.UTF8.GetBytes("{\"Binding\":{\"Run\":\"one\",\"Run\":\"two\"}}"); Reject(() => CoordinationPipe.Decode(message, 1)); });
        ReceiptTests(add);
    }
    private sealed class ReceiptStore : IBlobStore
    {
        internal readonly FakeBlobs Inner = new();
        internal bool WrongIdentity;
        public void CreatePending(string n, byte[] b) => Inner.CreatePending(n, b);
        public void FlushPending(string n) => Inner.FlushPending(n);
        public byte[] ReadPending(string n) => Inner.ReadPending(n);
        public void Commit(string n) => Inner.Commit(n);
        public byte[] ReadCommitted(string n) => Inner.ReadCommitted(n);
        public BlobIdentity Identity(string n) => WrongIdentity ? throw new IOException("receipt_file_identity_changed") : new(new string('1', 48), new string('1', 48));
    }
    private static void ReceiptTests(Action<string, Action> add)
    {
        add("coord_receipt_sha_file_identity_and_raw_pair", () =>
        {
            var store = new ReceiptStore(); var writer = new VerifiedEvidence(store, Binding);
            writer.SaveVerified("000001-raw", new { Test = true }); writer.SaveVerified("000001-verdict", new { Test = true });
            var r = JsonSerializer.Deserialize<FileReceipt>(store.Inner.Committed["000001-verdict-receipt"], Approval.Json)!;
            Check(r.Binding == Binding && r.Flushed && r.PendingReadback && r.FinalReadback && r.VolumeId.Length == 16 && r.FileId.Length == 32 && r.RawSha256 == Approval.Hash(store.Inner.Committed["000001-raw"]));
        });
        add("coord_receipt_file_identity_mismatch", () =>
        { var store = new ReceiptStore { WrongIdentity = true }; Reject(() => new VerifiedEvidence(store, Binding).SaveVerified("raw", new { Test = true })); });
        foreach (string fault in new[] { "flush", "read_pending", "read_committed" })
            add("coord_receipt_failure_" + fault, () =>
            { var store = new ReceiptStore(); store.Inner.Fault = fault; Reject(() => new VerifiedEvidence(store, Binding).SaveVerified("raw", new { Test = true })); Check(!store.Inner.Committed.ContainsKey("raw-receipt")); });
    }
}
