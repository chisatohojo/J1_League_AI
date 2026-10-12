using System.Text;
using System.Text.Json;
using System.Threading.Channels;
using J1AI.SmokeCoordination;
using J1AI.SmokeNetworkObserver;

namespace J1AI.SmokeNetworkObserver.Tests;

// Actual adapter receive/send/stop paths, with no OS pipe, GUI or collector.
internal static class CoordinationAdapterTests
{
    internal static readonly string[] Mutations = ["stop-failure-drop-abort", "tick-after-abort", "stopping-protocol-as-eof", "fault-cleared-by-ack"];
    private static string? mutation;
    private static readonly string Challenge = new('5', 32);
    private static RunBinding Binding => new(new string('1', 32), CoordinationSession.FixedIdentity, CoordinationSession.FixedUdf,
        new string('a', 64), new string('b', 64), new string('c', 64), new string('d', 64), new string('e', 64), new string('f', 64), new string('a', 64), new string('b', 64));
    private static void Check(bool value, string reason) => Program.Check(value, "adapter_" + reason);
    private static TaskCompletionSource Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static void Reject(Action call)
    { bool rejected = false; try { call(); } catch (IOException) { rejected = true; } Check(rejected, "initialization_must_be_rejected"); }
    private sealed class AdapterMutant : CoordinationAdapterPolicy
    {
        internal override bool DeliverFailedStopAbort => mutation != "stop-failure-drop-abort";
        internal override bool SuppressAbortedTick => mutation != "tick-after-abort";
        internal override bool RejectStoppingProtocol => mutation != "stopping-protocol-as-eof";
        internal override bool PreserveFaultOnAck => mutation != "fault-cleared-by-ack";
    }
    private sealed class SessionMutant : CoordinationPolicy
    { internal override bool PreserveFaultOnAck => mutation != "fault-cleared-by-ack"; }

    internal sealed class Clock : TimeProvider
    {
        internal long Now;
        private readonly List<Timer> timers = [];
        public override long TimestampFrequency => 1000;
        public override long GetTimestamp() => Now;
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch.AddMilliseconds(Now);
        public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
        { var timer = new Timer(this, callback, state); lock (timers) timers.Add(timer); timer.Change(dueTime, period); return timer; }
        internal void Advance(long milliseconds)
        {
            Now += milliseconds;
            Timer[] due; lock (timers) due = timers.ToArray();
            foreach (var timer in due) timer.Fire();
        }
        private sealed class Timer(Clock owner, TimerCallback callback, object? state) : ITimer
        {
            private long due = long.MaxValue;
            private long repeat = -1;
            public bool Change(TimeSpan time, TimeSpan period)
            { due = time == Timeout.InfiniteTimeSpan ? long.MaxValue : owner.Now + (long)time.TotalMilliseconds; repeat = (long)period.TotalMilliseconds; return true; }
            internal void Fire()
            { if (due > owner.Now) return; due = repeat < 0 ? long.MaxValue : owner.Now + repeat; callback(state); }
            public void Dispose() => due = long.MaxValue;
            public ValueTask DisposeAsync() { Dispose(); return ValueTask.CompletedTask; }
        }
    }
    private sealed class Stop(List<string> trace) : IStop
    {
        internal int Calls;
        internal Func<Task<bool>> Result = () => Task.FromResult(true);
        internal readonly TaskCompletionSource Entered = Signal();
        public Task<bool> RequestAsync(string identity, TimeSpan timeout)
        {
            Check(identity == Binding.Identity && timeout <= TimeSpan.FromSeconds(10), "formal_scope");
            Calls++; trace.Add("formal"); Entered.TrySetResult(); return Result();
        }
    }
    private sealed record Input(byte[]? Bytes = null, Exception? Error = null);
    private sealed class Link : ICoordinationLink
    {
        private readonly Channel<Input> inputs = Channel.CreateUnbounded<Input>();
        private readonly List<(int Count, TaskCompletionSource Signal)> readers = [];
        private int reads;
        private long sequence;
        internal bool Disposed, PeerLive = true, NotifyDisconnect = true;
        internal Func<CancellationToken, Task>? AbortWrite;
        internal Func<string, CancellationToken, Task>? NormalWrite;
        internal int AbortAttempts;
        internal readonly List<string> Sent = [];
        internal readonly TaskCompletionSource Ready = Signal();
        internal readonly WorkerGate Gate;
        internal readonly WorkerMessageReceiver Worker;
        public int PeerPid => 101;
        public long PeerBirth => 1100;
        public bool Alive => PeerLive && !Disposed;
        internal Link(Clock clock)
        { Gate = new(Binding, () => clock.Now, () => PeerLive); Worker = new(Binding, Challenge, Gate); }
        internal void Feed(string kind, RunBinding? binding = null, string? challenge = null, string? run = null, int port = 0, long? seq = null)
        {
            var message = new CoordinationMessage(kind, binding ?? Binding, seq ?? ++sequence, challenge ?? Challenge, run, port);
            inputs.Writer.TryWrite(new(JsonSerializer.SerializeToUtf8Bytes(message)));
        }
        internal void Error(Exception exception) => inputs.Writer.TryWrite(new(Error: exception));
        internal void Raw(string value) => inputs.Writer.TryWrite(new(Encoding.UTF8.GetBytes(value)));
        internal Task WaitReads(int count)
        {
            lock (readers)
            {
                if (reads >= count) return Task.CompletedTask;
                var signal = Signal(); readers.Add((count, signal)); return signal.Task;
            }
        }
        public async Task<CoordinationMessage> Read(CancellationToken token)
        {
            lock (readers)
            { reads++; foreach (var item in readers.Where(item => reads >= item.Count)) item.Signal.TrySetResult(); }
            Input input = await inputs.Reader.ReadAsync(token);
            if (input.Error != null) throw input.Error;
            byte[] framed = BitConverter.GetBytes(input.Bytes!.Length).Concat(input.Bytes).ToArray();
            using var bytes = new MemoryStream(framed);
            var message = await CoordinationPipe.ReadFrame(bytes, reads, token);
            CoordinationSession.Require(Alive, "coord_peer_dead");
            return message;
        }
        public async Task Send(CoordinationMessage message, CancellationToken token)
        {
            CoordinationSession.Require(Alive, "write_on_closed_or_dead_peer");
            if (message.Kind == "Abort")
            {
                AbortAttempts++;
                if (AbortWrite != null) await AbortWrite(token);
            }
            else if (NormalWrite != null) await NormalWrite(message.Kind, token);
            token.ThrowIfCancellationRequested();
            Sent.Add(message.Kind);
            if (message.Kind == "Ready") { Gate.Ready(Binding); Ready.TrySetResult(); }
            else Worker.Accept(message);
        }
        public void Dispose()
        {
            if (Disposed) return;
            Disposed = true; inputs.Writer.TryComplete();
            if (NotifyDisconnect) Worker.Disconnect();
        }
    }
    private sealed class Rig : IAsyncDisposable
    {
        internal readonly Clock Clock = new();
        internal readonly List<string> Trace = [];
        internal readonly MemoryEvidence Evidence;
        internal readonly Stop Formal;
        internal readonly Link Link;
        internal readonly CoordinatedObservation Adapter;
        internal readonly Observation Observation;
        internal Rig()
        {
            Evidence = new(Trace); Formal = new(Trace); Link = new(Clock);
            Link.Feed("Hello", Binding with { Run = "" });
            Adapter = new(Values.Contract, Binding, Evidence, _ => Task.FromResult<ICoordinationLink>(Link), Formal, Clock, new AdapterMutant(), new SessionMutant());
            Observation = new(Values.Contract, Evidence, Adapter, new ObservationPolicy(), Adapter.Session, Clock);
        }
        internal async Task Start(bool permit = true)
        {
            Adapter.CollectorReady(); await Link.Ready.Task; await Link.WaitReads(2);
            Link.Gate.Arm(); Link.Feed("Armed", run: new string('2', 32)); await Link.WaitReads(3);
            Link.Feed("Backend", port: 45678); await Link.WaitReads(4);
            Observation.Ready(); await Observation.Accept(Values.Snapshot());
            if (permit) await Adapter.Update(Values.Snapshot());
        }
        internal async Task<Summary> End()
        {
            if (!Link.Disposed) { Link.Error(new CoordinationEofException()); await Adapter.Receiver; }
            await Observation.Accept(Values.End()); return await Observation.Complete(true);
        }
        internal void AssertStopped()
        {
            Check(Adapter.Session.Aborted, "observer_abort_latched");
            Check(Link.Worker.StopRequested, "worker_running_stop_requested");
            Reject(() => Link.Gate.Initialize(45678, () => throw new InvalidOperationException("SDK must not start")));
        }
        public ValueTask DisposeAsync() => Adapter.DisposeAsync();
    }
    internal static void Register(Action<string, Func<Task>> register, string? mutant = null)
    {
        mutation = mutant;
        // Watchdog detects a broken test/barrier; logical deadlines use Clock.
        // No native resources or GUI are owned by these in-memory test tasks.
        void add(string name, Func<Task> test) => register(name, () => test().WaitAsync(TimeSpan.FromSeconds(5)));
        add("adapter_normal_stop_success", async () =>
        {
            await using var r = new Rig(); await r.Start();
            r.Link.Feed("Close"); await r.Link.WaitReads(5);
            Check(r.Adapter.CloseRequested, "native_close_reaches_adapter");
            await r.Observation.RequestNormalStop();
            var result = await r.End();
            Check(r.Formal.Calls == 1 && r.Adapter.Session.StopAcknowledged && result.RuntimeEndConfirmed && result.Result == Result.PASS_OBSERVED_SCOPE, "normal_end");
            Check(!r.Adapter.Faulted && !r.Adapter.Session.Aborted && r.Adapter.ChannelEnded, "normal_eof");
            Check(r.Trace.IndexOf("durable:000001-verdict") < r.Trace.IndexOf("formal"), "raw_verdict_before_stop");
        });
        foreach (string outcome in new[] { "false", "throw", "timeout" })
            add("adapter_stop_" + outcome, async () =>
            {
                await using var r = new Rig(); await r.Start();
                r.Formal.Result = outcome == "throw" ? () => throw new IOException("injected_stop") :
                    outcome == "timeout" ? () => new TaskCompletionSource<bool>().Task : () => Task.FromResult(false);
                Task stop = r.Observation.RequestNormalStop();
                if (outcome == "timeout") { await r.Formal.Entered.Task; r.Clock.Advance(10000); }
                await stop;
                Check(r.Formal.Calls == 1 && !r.Adapter.Session.StopAcknowledged, "one_failed_stop");
                Check(r.Adapter.AbortDelivered && r.Link.AbortAttempts == 1 && r.Link.Disposed, "abort_delivered_and_channel_revoked");
                r.AssertStopped(); Check((await r.End()).Result == Result.INCONCLUSIVE, "stop_failure_not_pass");
                Check(r.Clock.Now <= 10000, "bounded_stop_deadline");
            });
        add("adapter_cached_stop_then_fail", async () =>
        {
            await using var r = new Rig(); await r.Start(); await r.Observation.RequestNormalStop();
            await r.Observation.Fail(Phase.CRASH, "later_fault");
            Check(r.Formal.Calls == 1 && r.Link.AbortAttempts == 1, "cache_does_not_suppress_escalation"); r.AssertStopped();
            Check((await r.End()).Result == Result.INCONCLUSIVE, "late_failure");
        });
        add("adapter_previous_80_tick_probe_rejected", async () =>
        {
            await using var r = new Rig(); await r.Start(); r.Formal.Result = () => Task.FromResult(false);
            await r.Observation.RequestNormalStop(); int ticks = r.Link.Sent.Count(kind => kind == "Tick");
            for (int i = 0; i < 80; i++) { r.Clock.Advance(250); await r.Adapter.Update(Values.Snapshot()); }
            Check(r.Clock.Now == 20000 && r.Link.Sent.Count(kind => kind == "Tick") == ticks && r.Link.AbortAttempts == 1, "no_80_lease_renewals");
            r.AssertStopped(); Check((await r.End()).Result == Result.INCONCLUSIVE, "probe_not_pass");
        });
        foreach (string mode in new[] { "write-failure", "disconnect", "write-timeout" })
            add("adapter_abort_" + mode, async () =>
            {
                await using var r = new Rig(); await r.Start(); r.Formal.Result = () => Task.FromResult(false);
                var entered = Signal();
                r.Link.AbortWrite = token =>
                {
                    entered.TrySetResult();
                    if (mode == "disconnect") r.Link.Dispose();
                    return mode == "write-timeout" ? Task.Delay(Timeout.Infinite, token) : Task.FromException(new IOException("injected_abort_write"));
                };
                Task stop = r.Observation.RequestNormalStop(); await Task.WhenAny(entered.Task, stop);
                Check(entered.Task.IsCompletedSuccessfully, "abort_write_attempt_required");
                if (mode == "write-timeout") r.Clock.Advance(1000);
                await stop; Check(!r.Adapter.AbortDelivered && r.Adapter.Faulted && r.Link.Disposed, "failed_abort_revokes_pipe");
                r.AssertStopped(); Check((await r.End()).Result == Result.INCONCLUSIVE, "abort_write_failure");
            });
        add("adapter_disconnected_worker_lease_expires", async () =>
        {
            await using var r = new Rig(); await r.Start(); r.Link.NotifyDisconnect = false;
            r.Link.AbortWrite = _ => Task.FromException(new IOException("dropped_abort"));
            await r.Adapter.AbortAsync("injected"); r.Clock.Advance(1501);
            Check(r.Link.Disposed && r.Link.Worker.StopRequested, "lease_expired_while_running"); r.AssertStopped();
        });
        add("adapter_abort_no_tick_or_permit", async () =>
        {
            await using var r = new Rig(); await r.Start(false);
            r.Adapter.Session.Abort("before_update"); int sent = r.Link.Sent.Count;
            await r.Adapter.Update(Values.Snapshot());
            Check(!r.Link.Sent.Skip(sent).Any(kind => kind is "Tick" or "Permit"), "no_normal_send_after_abort"); r.AssertStopped();
        });
        add("adapter_abort_and_stop_barrier_concurrent", async () =>
        {
            await using var r = new Rig(); await r.Start(); var completion = new TaskCompletionSource<bool>();
            r.Formal.Result = () => completion.Task;
            Task stop = r.Observation.RequestNormalStop(); await r.Formal.Entered.Task;
            await r.Adapter.AbortAsync("during_formal_stop"); completion.SetResult(true); await stop;
            r.AssertStopped(); Check(r.Formal.Calls == 1 && r.Adapter.Session.StopAcknowledged && (await r.End()).Result == Result.INCONCLUSIVE, "abort_wins_ack");
        });
        add("adapter_duplicate_abort_stop", async () =>
        {
            await using var r = new Rig(); await r.Start(); var completion = new TaskCompletionSource<bool>();
            r.Formal.Result = () => completion.Task;
            var begin = Signal();
            var stops = Enumerable.Range(0, 8).Select(_ => Task.Run(async () => { await begin.Task; await r.Observation.RequestNormalStop(); })).ToArray();
            begin.SetResult(); await r.Formal.Entered.Task;
            await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => Task.Run(() => r.Adapter.AbortAsync("duplicate"))));
            completion.SetResult(false); await Task.WhenAll(stops);
            Check(r.Formal.Calls == 1 && r.Link.AbortAttempts == 1, "deduplicated_stop_and_abort"); r.AssertStopped();
        });
        foreach (string stage in new[] { "before-initialize", "during-initialize", "after-initialize", "running-lease" })
            add("adapter_worker_" + stage, async () =>
            {
                await using var r = new Rig(); await r.Start(); var sdk = Signal(); int started = 0;
                Task? initialization = null;
                if (stage != "before-initialize") initialization = r.Link.Gate.Initialize(45678, () => { started++; return sdk.Task; });
                if (stage is "after-initialize" or "running-lease") { sdk.SetResult(); await initialization!; }
                if (stage == "running-lease") r.Clock.Advance(1501);
                else await r.Adapter.AbortAsync("stage_fault");
                Check(r.Link.Worker.StopRequested, "continuous_running_stop_monitor");
                Reject(() => r.Link.Gate.Initialize(45678, () => Task.CompletedTask));
                if (stage == "during-initialize") { sdk.SetResult(); await initialization!; }
                Check(started == (stage == "before-initialize" ? 0 : 1), "no_extra_sdk_call");
            });
        add("adapter_unconfirmed_runtime_cleanup", async () =>
        {
            await using var r = new Rig(); await r.Start(); await r.Observation.RequestNormalStop();
            Check((await r.Observation.Complete(false)).Result == Result.INCONCLUSIVE && r.Adapter.Session.StopAcknowledged, "ack_not_exit");
        });
        add("adapter_end_channel_timeout", async () =>
        {
            await using var r = new Rig(); await r.Start(); await r.Observation.RequestNormalStop();
            Task end = r.Observation.Accept(Values.End()); r.Clock.Advance(2000); await end;
            r.AssertStopped(); Check((await r.Observation.Complete(true)).Result == Result.INCONCLUSIVE, "end_requires_settled_receiver");
        });
        foreach (string kind in new[] { "Tick", "Permit" })
            add("adapter_abort_during_queued_" + kind, async () =>
            {
                await using var r = new Rig(); await r.Start(false); var entered = Signal();
                r.Link.NormalWrite = (value, token) =>
                { if (value != kind) return Task.CompletedTask; entered.TrySetResult(); return Task.Delay(Timeout.Infinite, token); };
                Task update = r.Adapter.Update(Values.Snapshot()); await entered.Task;
                await r.Adapter.AbortAsync("normal_write_race");
                Check(r.Link.AbortAttempts == 1, "queued_write_requires_abort");
                bool failed = false; try { await update; } catch (Exception e) when (e is IOException or OperationCanceledException) { failed = true; }
                Check(failed && r.Link.AbortAttempts == 1 && !r.Link.Sent.Contains(kind), "inflight_write_cancelled_" + kind);
                r.AssertStopped();
            });
        foreach (string input in new[] { "empty", "header", "body", "valid" })
            add("adapter_actual_frame_" + input, async () =>
            {
                byte[] payload = JsonSerializer.SerializeToUtf8Bytes(new CoordinationMessage("Close", Binding, 1, Challenge));
                byte[] bytes = input switch { "empty" => [], "header" => [1, 2], "body" => BitConverter.GetBytes(payload.Length).Concat(payload[..^1]).ToArray(), _ => BitConverter.GetBytes(payload.Length).Concat(payload).ToArray() };
                using var stream = new MemoryStream(bytes);
                Exception? error = null;
                try { await CoordinationPipe.ReadFrame(stream, 1, CancellationToken.None); } catch (IOException e) { error = e; }
                Check(input switch { "empty" => error is CoordinationEofException, "valid" => error == null, _ => error is EndOfStreamException }, "exact_frame_eof_" + input);
            });
        foreach (string input in new[] { "early-eof", "malformed", "unknown", "sequence", "foreign-run", "challenge", "peer", "armed", "backend", "duplicate", "partial-frame", "unknown-io", "ended" })
            add("adapter_stopping_" + input, async () =>
            {
                await using var r = new Rig(); await r.Start();
                var formal = new TaskCompletionSource<bool>(); r.Formal.Result = () => formal.Task;
                Task stop = r.Observation.RequestNormalStop(); await r.Formal.Entered.Task;
                if (input == "ended") { formal.SetResult(true); await stop; r.Adapter.Session.End(true, true, true, true, true); }
                switch (input)
                {
                    case "early-eof": r.Link.Error(new CoordinationEofException()); break;
                    case "malformed": r.Link.Raw("{invalid"); break;
                    case "sequence": r.Link.Feed("Close", seq: 99); break;
                    case "foreign-run": r.Link.Feed("Close", Binding with { Run = new string('8', 32) }); break;
                    case "challenge": r.Link.Feed("Close", challenge: new string('8', 32)); break;
                    case "peer": r.Link.PeerLive = false; r.Link.Feed("Close"); break;
                    case "armed": r.Link.Feed("Armed", run: new string('2', 32)); break;
                    case "backend": r.Link.Feed("Backend", port: 45678); break;
                    case "duplicate": r.Link.Feed("Backend", port: 45678); break;
                    case "partial-frame": r.Link.Error(new EndOfStreamException("truncated_frame")); break;
                    case "unknown-io": r.Link.Error(new IOException("unclassified_transport")); break;
                    default: r.Link.Feed("Unexpected"); break;
                }
                await r.Adapter.Receiver;
                Check(r.Adapter.Faulted && r.Adapter.ChannelEnded && r.Adapter.Session.Aborted, "protocol_fault_latched_" + input);
                if (!formal.Task.IsCompleted) { formal.SetResult(true); await stop; }
                Check(r.Adapter.Faulted && r.Adapter.Session.Aborted && r.Adapter.Session.Failed, "fault_not_cleared_by_ack");
                Check((await r.End()).Result == Result.INCONCLUSIVE, "fault_not_cleared_by_cleanup"); r.AssertStopped();
            });
        foreach (string kind in new[] { "Armed", "Backend", "Close" })
            add("adapter_duplicate_active_" + kind, async () =>
            {
                await using var r = new Rig(); await r.Start();
                if (kind == "Close") { r.Link.Feed("Close"); await r.Link.WaitReads(5); }
                r.Link.Feed(kind, run: new string('2', 32), port: 45678);
                await r.Adapter.Receiver;
                await r.Observation.Fail(Phase.CRASH, "protocol_fault");
                r.AssertStopped(); Check(r.Adapter.Faulted && r.Formal.Calls == 1 && (await r.End()).Result == Result.INCONCLUSIVE, "active_duplicate_rejected");
            });
        foreach (string stage in new[] { "raw-write", "raw-flush", "raw-readback", "verdict", "stop-before", "stop-after", "cleanup" })
            add("adapter_storage_" + stage, async () =>
            {
                await using var r = new Rig(); await r.Start();
                if (stage == "cleanup")
                { await r.Observation.RequestNormalStop(); Check((await r.Observation.Complete(false)).Result == Result.INCONCLUSIVE, "cleanup_unconfirmed"); return; }
                if (stage.StartsWith("raw-", StringComparison.Ordinal) || stage == "verdict")
                {
                    r.Evidence.FailName = stage == "verdict" ? "000002-verdict" : "000002-raw";
                    r.Evidence.FailStage = stage switch { "raw-flush" => "flush", "raw-readback" => "verify", _ => "write" };
                    await r.Observation.Accept(Values.Snapshot(2));
                }
                else
                {
                    // Collector-ready, Armed, Permit, then Stop-before/Stop-after.
                    r.Evidence.FailName = stage == "stop-before" ? "coord-0004" : "coord-0005";
                    r.Evidence.FailStage = "write"; await r.Observation.RequestNormalStop();
                }
                Check(r.Formal.Calls == 1 && r.Adapter.Session.Aborted && r.Link.Worker.StopRequested, "storage_failure_still_stops");
                Check((await r.Observation.Complete(false)).Result == Result.INCONCLUSIVE, "storage_failure_not_pass");
            });
        add("adapter_end_receipt_failure", async () =>
        {
            await using var r = new Rig(); await r.Start(); await r.Observation.RequestNormalStop();
            r.Evidence.FailName = "coord-0006"; r.Evidence.FailStage = "write";
            Check((await r.End()).Result == Result.INCONCLUSIVE && r.Adapter.Session.Failed && r.Formal.Calls == 1, "end_receipt_failure_not_pass");
        });
    }
}
