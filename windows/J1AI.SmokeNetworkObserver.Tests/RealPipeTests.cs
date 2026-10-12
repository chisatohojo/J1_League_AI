using System.Diagnostics;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text.Json;
using J1AI.SmokeCoordination;
using J1AI.SmokeNetworkObserver;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeNetworkObserver.Tests;

// Real OS transport and peer processes. Collector facts, clock, storage and Stop
// remain Fakes. No UDF access, real events, GUI, backend or TCP enumeration.
internal static class RealPipeTests
{
    internal static readonly string[] Mutations = ["accept-foreign", "ignore-abort", "ignore-lease"];
    private static string? mutation;
    private static void Check(bool value, string reason) => Program.Check(value, "real_pipe_" + reason);
    private static TaskCompletionSource Signal() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static void Reject(Action action)
    {
        bool rejected = false;
        try { action(); } catch (IOException) { rejected = true; }
        Check(rejected, "expected_rejection");
    }
    private sealed class Tap(CoordinationPipe actual) : ICoordinationLink
    {
        private readonly object sync = new();
        private readonly List<(int Count, TaskCompletionSource Signal)> waiting = [];
        private int reads;
        internal readonly List<string> Sent = [];
        internal Func<string, CancellationToken, Task>? BeforeSend;
        public int PeerPid => actual.PeerPid;
        public long PeerBirth => actual.PeerBirth;
        public bool Alive => actual.Alive;
        internal Task WaitRead(int count)
        {
            lock (sync)
            {
                if (reads >= count) return Task.CompletedTask;
                var signal = Signal(); waiting.Add((count, signal)); return signal.Task.WaitAsync(TimeSpan.FromSeconds(5));
            }
        }
        public Task<CoordinationMessage> Read(CancellationToken token)
        {
            lock (sync)
            {
                reads++;
                foreach (var item in waiting.Where(item => reads >= item.Count)) item.Signal.TrySetResult();
            }
            return actual.Read(token);
        }
        public async Task Send(CoordinationMessage message, CancellationToken token)
        {
            // An independent real watchdog bounds OS backpressure even while
            // logical Stop/lease tests deliberately keep their Fake clock still.
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            deadline.CancelAfter(TimeSpan.FromSeconds(5));
            if (BeforeSend != null) await BeforeSend(message.Kind, deadline.Token);
            await actual.Send(message, deadline.Token);
            lock (sync) Sent.Add(message.Kind);
        }
        internal int SentCount { get { lock (sync) return Sent.Count; } }
        public void Dispose() => actual.Dispose();
    }
    private sealed class Stop : IStop
    {
        internal int Calls;
        internal readonly TaskCompletionSource Entered = Signal();
        internal Func<Task<bool>> Result = () => Task.FromResult(true);
        public Task<bool> RequestAsync(string identity, TimeSpan timeout)
        {
            Check(identity == CoordinationSession.FixedIdentity && timeout > TimeSpan.Zero && timeout <= TimeSpan.FromSeconds(10), "fake_stop_scope");
            Calls++; Entered.TrySetResult(); return Result();
        }
    }
    private sealed class Rig : IAsyncDisposable
    {
        internal readonly string Name = "J1AI.SmokeCoordination.Tests." + Guid.NewGuid().ToString("N");
        internal readonly string Challenge = Guid.NewGuid().ToString("N");
        internal readonly RunBinding Binding;
        internal readonly CoordinationAdapterTests.Clock Clock = new();
        internal readonly Stop Formal = new();
        internal readonly List<string> Trace = [];
        internal readonly MemoryEvidence Evidence;
        internal readonly NamedPipeServerStream Listener;
        internal readonly CoordinatedObservation Adapter;
        internal readonly Observation Observation;
        internal readonly Process Child;
        internal readonly SafeProcessHandle ChildHandle;
        internal readonly long ChildBirth;
        internal readonly TaskCompletionSource<Tap> Connected = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal Tap Link => Connected.Task.GetAwaiter().GetResult();
        private readonly Task<string> errors;
        private Rig(string mode, bool rejectImage)
        {
            string executable = Environment.ProcessPath ?? throw new IOException("test_dotnet_unknown");
            Check(Path.GetFileName(executable) == "dotnet.exe", "explicit_dotnet_required");
            string hash = Approval.FileHash(executable);
            Binding = new(Guid.NewGuid().ToString("N"), CoordinationSession.FixedIdentity, CoordinationSession.FixedUdf,
                new('a', 64), new('b', 64), Approval.FileHash(typeof(RealPipeTests).Assembly.Location), hash, hash,
                new('c', 64), new('d', 64), new('e', 64));
            Listener = CoordinationPipe.ListenForTest(Name);
            Evidence = new(Trace);
            var serverBinding = rejectImage ? Binding with { DotnetSha = new('0', 64), RunnerExeSha = new('0', 64) } : Binding;
            Adapter = new(Values.Contract, serverBinding, Evidence, async token =>
            {
                try { var tap = new Tap(await CoordinationPipe.Accept(Listener, serverBinding, token)); Connected.TrySetResult(tap); return tap; }
                catch (Exception error) { Connected.TrySetException(error); throw; }
            }, Formal, Clock);
            Observation = new(Values.Contract, Evidence, Adapter, new ObservationPolicy(), Adapter.Session, Clock);
            var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true,
                RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (string arg in new[] { typeof(RealPipeTests).Assembly.Location, "--real-pipe-peer", Name,
                Convert.ToBase64String(JsonSerializer.SerializeToUtf8Bytes(Binding)), Challenge, mode }) start.ArgumentList.Add(arg);
            try
            {
                Child = Process.Start(start) ?? throw new IOException("test_peer_start");
                ChildHandle = Child.SafeHandle; // own kernel process object from creation, never rediscover by PID
                ChildBirth = Child.StartTime.ToUniversalTime().ToFileTimeUtc();
                errors = Child.StandardError.ReadToEndAsync();
            }
            catch (Exception creationError)
            {
                var failures = new List<Exception> { creationError };
                try
                {
                    if (Child != null)
                    {
                        Child.StandardInput.Close();
                        if (!Child.WaitForExit(5000))
                        {
                            if (ChildHandle == null || ChildHandle.IsInvalid || !TerminateProcess(ChildHandle, 1) || !Child.WaitForExit(3000))
                                throw new IOException("test_peer_setup_cleanup_unconfirmed");
                        }
                    }
                }
                catch (Exception error) { failures.Add(error); }
                finally { Child?.Dispose(); }
                try { Adapter.DisposeAsync().AsTask().GetAwaiter().GetResult(); }
                catch (Exception error) { failures.Add(error); }
                finally { Listener.Dispose(); }
                throw new AggregateException("test_peer_setup_failed", failures);
            }
        }
        internal static async Task<Rig> Open(string mode = "worker", bool rejectImage = false)
        {
            var rig = new Rig(mode, rejectImage);
            try
            {
                var reply = await rig.Reply(); Check(reply.Ok && reply.Kind == "Connected", "client_connected");
                if (mode == "worker")
                {
                    using var self = Process.GetCurrentProcess();
                    Check(reply.Pid == self.Id && reply.Birth == self.StartTime.ToUniversalTime().ToFileTimeUtc(), "client_server_pid_birth");
                }
                if (!rejectImage)
                {
                    var link = await rig.Connected.Task.WaitAsync(TimeSpan.FromSeconds(5));
                    Check(link.PeerPid == rig.Child.Id && link.PeerBirth == rig.ChildBirth && link.Alive && !rig.ChildHandle.IsClosed, "server_client_pid_birth");
                }
                return rig;
            }
            catch { await rig.DisposeAsync(); throw; }
        }
        internal async Task<PeerReply> Reply()
        {
            string? line = await Child.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(6));
            Check(line != null && line.Length <= 8192, "peer_reply_bounded");
            return JsonSerializer.Deserialize<PeerReply>(line!) ?? throw new IOException("peer_reply_missing");
        }
        internal async Task<PeerReply> Command(string action, string value = "")
        {
            await Child.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new PeerCommand(action, value)));
            await Child.StandardInput.FlushAsync(); return await Reply();
        }
        internal async Task Require(string action, string expected, string value = "")
        { var reply = await Command(action, value); Check(reply.Ok && reply.Kind == expected, action + "_" + reply.Kind); }
        internal async Task Ready()
        {
            Adapter.CollectorReady(); await Require("hello", "hello"); await Require("read", "Ready"); await Link.WaitRead(2);
        }
        internal async Task Arm()
        { await Require("arm", "arm"); await Link.WaitRead(3); Check(Adapter.Session.FixtureRun?.Length == 32, "armed_after_ready"); }
        internal async Task Backend()
        { await Require("backend", "backend"); await Link.WaitRead(4); }
        internal Snapshot Snapshot(long sequence = 1)
        {
            // Explicitly fabricated collector facts. The worker key alone is
            // anchored to the real authenticated pipe peer; no OS TCP query.
            var c = Values.Contract; long b = ChildBirth;
            const int supervisor = 1900000000, runtime = 1900000001, python = 1900000002;
            ProcessFact[] facts = [
                new(new(supervisor, b - 1000), 1, c.Dotnet, [c.Dotnet, c.Runner, "--smoke-run"], true),
                new(new(Child.Id, b), supervisor, c.Dotnet, [c.Dotnet, c.Runner, "--smoke-worker"], true),
                new(new(runtime, b + 10), Child.Id, c.RuntimeExecutable, [c.RuntimeExecutable, "--user-data-dir=" + c.Udf], true),
                new(new(python, b + 20), Child.Id, c.PythonArgument, [c.PythonArgument, "-I", "-S", "-B", "-u", c.Backend, c.Root, "--data", Path.Combine(c.Root, "must-not-be-read.json")], true)
            ];
            TcpRow[] rows = [new(python, b + 20, "127.0.0.1", 45678, "0.0.0.0", 0, "LISTEN", 2),
                new(runtime, b + 10, "127.0.0.1", 54321, "127.0.0.1", 45678, "ESTABLISHED", 2)];
            return Values.Snapshot(sequence, rows) with { Processes = facts };
        }
        internal async Task Start()
        {
            await Ready(); await Arm(); await Backend();
            Observation.Ready(); await Observation.Accept(Snapshot());
            Task update = Adapter.Update(Snapshot());
            await Require("read", "Tick"); await Require("read", "Permit");
            await update.WaitAsync(TimeSpan.FromSeconds(5));
        }
        internal Task Send(string kind, RunBinding? binding = null, string? challenge = null) =>
            Link.Send(new(kind, binding ?? Binding, 0, challenge ?? Challenge, Port: 45678, Permit: Guid.NewGuid().ToString("N")), CancellationToken.None);
        internal async Task<PeerReply> Deliver(string kind, RunBinding? binding = null, string? challenge = null)
        {
            Task send = Send(kind, binding, challenge);
            var response = await Command("read"); await send.WaitAsync(TimeSpan.FromSeconds(5)); return response;
        }
        internal async Task AssertStopped()
        {
            var status = await Command("status");
            if (mutation == "ignore-abort") status = status with { Stopped = false };
            Check(status.Ok && status.Stopped, "worker_stop_latched");
            var init = await Command("initialize"); Check(!init.Ok && init.Initialized == 0, "no_initialization_after_abort");
        }
        public async ValueTask DisposeAsync()
        {
            Exception? failure = null;
            try { await Adapter.DisposeAsync(); } catch (Exception e) { failure = e; }
            Listener.Dispose();
            try
            {
                Child.StandardInput.Close();
                try { await Child.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5)); }
                catch (TimeoutException)
                {
                    // Only this retained, directly created non-spawning helper.
                    if (!TerminateProcess(ChildHandle, 1)) throw new IOException("test_peer_cleanup_terminate");
                    await Child.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(3));
                    throw new IOException("test_peer_required_forced_cleanup");
                }
                Check(Child.HasExited && (await errors.WaitAsync(TimeSpan.FromSeconds(1))).Length == 0, "peer_cleanup_exit");
                if (Connected.Task.IsFaulted) _ = Connected.Task.Exception;
            }
            catch (Exception e) { failure ??= e; }
            finally { Child.Dispose(); }
            Check(ChildHandle.IsClosed, "process_handle_released");
            if (failure != null) throw new IOException("real_pipe_cleanup_failed", failure);
        }
    }
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool TerminateProcess(SafeProcessHandle process, uint code);
    [DllImport("kernel32", SetLastError = true)] private static extern uint GetProcessId(SafeProcessHandle process);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateNamedPipeW(string name, uint open, uint mode, uint instances,
        uint output, uint input, uint timeout, nint security);
    [DllImport("advapi32", SetLastError = true)] private static extern uint GetSecurityInfo(SafeHandle handle, int kind,
        uint information, out nint owner, out nint group, out nint dacl, out nint sacl, out nint descriptor);
    [DllImport("advapi32")] private static extern uint GetSecurityDescriptorLength(nint descriptor);
    [DllImport("kernel32")] private static extern nint LocalFree(nint memory);
    [DllImport("advapi32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(SafeProcessHandle process, uint access, out SafeAccessTokenHandle token);
    [DllImport("advapi32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetTokenInformation(SafeAccessTokenHandle token, int kind, out int value, uint size, out uint needed);
    private static void CurrentUserPeer(SafeProcessHandle child)
    {
        using var self = Process.GetCurrentProcess();
        Check(OpenProcessToken(child, 8, out var childToken), "peer_query_token");
        using (childToken)
        {
            Check(OpenProcessToken(self.SafeHandle, 8, out var selfToken), "self_query_token");
            using (selfToken)
            using (var identity = new WindowsIdentity(childToken.DangerousGetHandle()))
            using (var current = WindowsIdentity.GetCurrent())
            {
                Check(identity.User == current.User, "peer_same_user_sid");
                Check(GetTokenInformation(childToken, 18, out int childElevation, 4, out uint childSize) && childSize == 4 &&
                    GetTokenInformation(selfToken, 18, out int selfElevation, 4, out uint selfSize) && selfSize == 4 &&
                    childElevation == selfElevation, "peer_same_elevation_type");
            }
        }
    }
    private static void CurrentUserAcl(NamedPipeServerStream listener)
    {
        uint error = GetSecurityInfo(listener.SafePipeHandle, 6, 5, out _, out _, out _, out _, out nint descriptor);
        try
        {
            Check(error == 0 && descriptor != 0, "pipe_security_readback");
            uint length = GetSecurityDescriptorLength(descriptor); Check(length is > 0 and <= 65536, "pipe_security_size");
            byte[] bytes = new byte[length]; Marshal.Copy(descriptor, bytes, 0, bytes.Length);
            var security = new RawSecurityDescriptor(bytes, 0);
            using var user = WindowsIdentity.GetCurrent();
            Check(security.Owner == user.User && security.DiscretionaryAcl is { Count: > 0 }, "pipe_owner_dacl");
            foreach (GenericAce ace in security.DiscretionaryAcl!)
                if (ace is QualifiedAce { AceQualifier: AceQualifier.AccessAllowed } allow)
                    Check(allow.SecurityIdentifier == user.User, "pipe_no_other_user_allow");
        }
        finally { if (descriptor != 0) LocalFree(descriptor); }
    }
    internal static void Register(Action<string, Action> add, Action<string, Func<Task>> async)
    {
        void test(string name, Func<Task> body) => async("real_pipe_" + name, body);
        add("real_pipe_test_namespace_rejects_fixed_and_arbitrary_names", () =>
        {
            foreach (string name in new[] { CoordinationPipe.Name, "other", "J1AI.SmokeCoordination.Tests.bad", "J1AI.SmokeCoordination.Tests." + Guid.NewGuid().ToString("N") + "x" })
                Reject(() => { using var listener = CoordinationPipe.ListenForTest(name); });
        });
        test("normal_order_pid_birth_and_initialization", async () =>
        {
            await using var r = await Rig.Open(); await r.Start();
            var result = await r.Command("initialize"); Check(result.Ok && result.Initialized == 1, "one_synthetic_initialization");
            Check(r.Adapter.Session.Phase == CoordinationPhase.Permitted, "server_permit_after_verified_fake_backend");
        });
        test("current_user_security_and_first_instance", async () =>
        {
            await using var r = await Rig.Open(); CurrentUserAcl(r.Listener); CurrentUserPeer(r.ChildHandle);
            bool refused = false;
            try { using var duplicate = CoordinationPipe.ListenForTest(r.Name); }
            catch (UnauthorizedAccessException) { refused = true; }
            catch (IOException error) when ((error.HResult & 0xffff) == 231) { refused = true; }
            Check(refused, "first_instance_access_denied_or_pipe_busy");
            Check(r.Link.Alive, "duplicate_does_not_replace_existing_pipe"); await r.Start();
        });
        add("real_pipe_native_first_instance_flag_counterfactual", () =>
        {
            // With two instances allowed, this isolates the OS flag from the
            // managed factory's independent max-instances=1 protection.
            string name = @"\\.\pipe\J1AI.SmokeCoordination.Tests." + Guid.NewGuid().ToString("N");
            using var first = CreateNamedPipeW(name, 0x40080003, 0, 2, 4096, 4096, 0, 0);
            Check(!first.IsInvalid, "native_first_listener_created");
            using var refused = CreateNamedPipeW(name, 0x40080003, 0, 2, 4096, 4096, 0, 0);
            int error = Marshal.GetLastWin32Error();
            Check(refused.IsInvalid && error == 5, "first_flag_denies_second_listener");
            using var counterfactual = CreateNamedPipeW(name, 0x40000003, 0, 2, 4096, 4096, 0, 0);
            Check(!counterfactual.IsInvalid, "removing_first_flag_changes_os_result");
        });
        test("os_peer_image_hash_rejected", async () =>
        {
            await using var r = await Rig.Open(rejectImage: true);
            bool rejected = false;
            try { await r.Connected.Task.WaitAsync(TimeSpan.FromSeconds(5)); }
            catch (IOException e) when (e.Message == "coord_peer_image_hash") { rejected = true; }
            Check(rejected, "os_image_not_just_message_hash"); await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5));
            Check(r.Adapter.Faulted && r.Adapter.Session.Aborted, "bad_image_fail_closed");
        });
        foreach (string value in new[] { "identity", "manifest", "binary" })
            test("hello_reject_" + value, async () =>
            {
                await using var r = await Rig.Open(); r.Adapter.CollectorReady(); await r.Require("hello", "hello", value);
                await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5));
                Check(r.Adapter.Faulted && r.Adapter.Session.Aborted && !r.Adapter.ReadySent, "hello_binding_rejected");
            });
        foreach (string value in new[] { "stale", "challenge", "fault" })
            test("post_ready_reject_" + value, async () =>
            {
                await using var r = await Rig.Open(); await r.Ready(); await r.Require(value, value);
                await r.Require("read", "Abort");
                await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5));
                Check(r.Adapter.Faulted && r.Adapter.Session.Aborted, "foreign_or_invalid_message_rejected");
                await r.AssertStopped();
            });
        foreach (string stage in new[] { "before-ready", "before-arm", "without-backend" })
            test("permit_rejected_" + stage, async () =>
            {
                await using var r = await Rig.Open();
                if (stage != "before-ready") await r.Ready();
                if (stage == "without-backend")
                {
                    await r.Arm(); Reject(() => r.Adapter.Session.Permit(new("127.0.0.1", 45678, 1, 1)));
                }
                else
                {
                    var response = await r.Deliver("Permit");
                    Check(!response.Ok && response.Stopped, "worker_rejects_early_wire_permit");
                }
                var init = await r.Command("initialize"); Check(!init.Ok && init.Initialized == 0, "early_init_rejected");
            });
        test("backend_before_arm_rejected", async () =>
        {
            await using var r = await Rig.Open(); await r.Ready(); await r.Require("backend", "backend");
            await r.Require("read", "Abort");
            await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5)); Check(r.Adapter.Faulted && r.Adapter.Session.Aborted, "unarmed_backend");
        });
        test("collector_ready_barrier", async () =>
        {
            await using var r = await Rig.Open(); await r.Require("hello", "hello");
            Check(!r.Adapter.ReadySent && r.Adapter.Session.Phase == CoordinationPhase.Waiting, "no_ready_before_collector");
            r.Adapter.CollectorReady(); await r.Require("read", "Ready"); await r.Link.WaitRead(2);
        });
        test("abort_after_permit_no_init_or_more_ticks", async () =>
        {
            await using var r = await Rig.Open(); await r.Start(); Task abort = r.Adapter.AbortAsync("test");
            await r.Require("read", "Abort"); await abort.WaitAsync(TimeSpan.FromSeconds(5)); await r.AssertStopped();
            int count = r.Link.SentCount; await r.Adapter.Update(r.Snapshot(2)); Check(r.Link.SentCount == count, "no_normal_send_after_abort");
        });
        foreach (string stale in new[] { "Ready", "Permit" })
            test("stale_" + stale + "_rejected", async () =>
            {
                await using var r = await Rig.Open(); await r.Start();
                var response = await r.Deliver(stale, r.Binding with { Run = Guid.NewGuid().ToString("N") });
                Check(!response.Ok && response.Stopped, "stale_grant_not_reusable");
            });
        test("duplicate_permit_rejected", async () =>
        {
            await using var r = await Rig.Open(); await r.Start();
            var response = await r.Deliver("Permit"); Check(!response.Ok && response.Stopped, "duplicate_grant_not_reusable");
        });
        foreach (string outcome in new[] { "success", "false", "throw", "timeout" })
            test("formal_stop_" + outcome, async () =>
            {
                await using var r = await Rig.Open(); await r.Start();
                r.Formal.Result = outcome switch
                {
                    "false" => () => Task.FromResult(false),
                    "throw" => () => Task.FromException<bool>(new IOException("synthetic_stop")),
                    "timeout" => () => new TaskCompletionSource<bool>().Task,
                    _ => () => Task.FromResult(true)
                };
                Task stop = r.Observation.RequestNormalStop(); await r.Formal.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
                if (outcome == "timeout") r.Clock.Advance(10000);
                if (outcome != "success") await r.Require("read", "Abort");
                await stop.WaitAsync(TimeSpan.FromSeconds(5)); Check(r.Formal.Calls == 1, "single_fake_stop");
                Check(r.Trace.IndexOf("durable:000001-raw") < r.Trace.IndexOf("durable:000001-verdict"), "raw_before_verdict");
                if (outcome == "success")
                {
                    Check(r.Adapter.Session.StopAcknowledged && !r.Adapter.Session.Aborted, "ack_not_abort");
                    Check(!r.Evidence.Saved.ContainsKey("result"), "ack_not_process_exit_or_result");
                    Reject(() => r.Adapter.Session.End(false, true, true, true, true));
                    await r.Require("disconnect", "disconnect"); await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5));
                    Check(!r.Adapter.Faulted && r.Adapter.ChannelEnded, "ack_then_boundary_eof_only");
                }
                else
                {
                    Check(!r.Adapter.Session.StopAcknowledged && r.Adapter.Session.Aborted && r.Adapter.AbortDelivered, "failed_stop_delivers_abort");
                    await r.AssertStopped();
                }
            });
        test("cached_stop_then_abort_fault_sticky", async () =>
        {
            await using var r = await Rig.Open(); await r.Start(); await r.Observation.RequestNormalStop();
            Task abort = r.Adapter.AbortAsync("synthetic_after_cached_stop"); await r.Require("read", "Abort"); await abort.WaitAsync(TimeSpan.FromSeconds(5));
            await r.AssertStopped();
            Check(await r.Adapter.RequestAsync(r.Binding.Identity, TimeSpan.FromSeconds(10)) && r.Formal.Calls == 1 && r.Adapter.Session.Failed, "cache_cannot_erase_abort");
            r.Adapter.Session.StopResult(true); r.Adapter.Session.End(true, true, true, true, true);
            Check(r.Adapter.Session.Failed && r.Adapter.Session.Aborted && r.Adapter.Session.Phase == CoordinationPhase.Blocked, "ack_cleanup_cannot_clear_fault");
        });
        test("protocol_fault_after_ack_not_eof", async () =>
        {
            await using var r = await Rig.Open(); await r.Start(); await r.Observation.RequestNormalStop();
            await r.Require("fault", "fault"); await r.Require("read", "Abort"); await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5));
            Check(r.Adapter.Faulted && r.Adapter.Session.Aborted && r.Adapter.Session.StopAcknowledged, "late_protocol_fault_sticky");
        });
        foreach (string partial in new[] { "partial-header", "partial-body" })
            test(partial + "_not_clean_eof", async () =>
            {
                await using var r = await Rig.Open("raw"); await r.Require(partial, partial);
                await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5));
                Check(r.Adapter.Faulted && r.Adapter.Session.Aborted, "truncated_frame_rejected");
            });
        test("early_boundary_eof_is_fault", async () =>
        {
            await using var r = await Rig.Open(); await r.Ready(); await r.Require("disconnect", "disconnect");
            await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5)); Check(r.Adapter.Faulted && r.Adapter.Session.Aborted, "unacknowledged_eof");
        });
        test("disconnect_during_abort_delivery", async () =>
        {
            await using var r = await Rig.Open(); await r.Start(); var entered = Signal(); var release = Signal();
            r.Link.BeforeSend = async (kind, token) => { if (kind == "Abort") { entered.TrySetResult(); await release.Task.WaitAsync(token); } };
            var abort = r.Adapter.AbortAsync("test"); await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            await r.Require("disconnect", "disconnect"); release.TrySetResult(); await abort.WaitAsync(TimeSpan.FromSeconds(5));
            Check(!r.Adapter.AbortDelivered && r.Adapter.Faulted && r.Adapter.Session.Aborted, "abort_write_failure_not_success"); await r.AssertStopped();
        });
        test("worker_lease_expiry_after_real_connection", async () =>
        {
            await using var r = await Rig.Open(); await r.Start(); await r.Require("advance", "advance", "1501");
            var result = await r.Command("status");
            if (mutation == "ignore-lease") result = result with { Stopped = false };
            Check(result.Stopped, "lease_requires_stop"); var init = await r.Command("initialize"); Check(!init.Ok, "lease_rejects_init");
        });
        test("peer_death_retained_identity_not_reusable", async () =>
        {
            await using var r = await Rig.Open(); await r.Start();
            int peerPid = r.Link.PeerPid; long peerBirth = r.Link.PeerBirth;
            r.Child.StandardInput.Close(); await r.Child.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
            Check(!r.Link.Alive && GetProcessId(r.ChildHandle) == peerPid && peerBirth == r.ChildBirth &&
                r.Child.StartTime.ToUniversalTime().ToFileTimeUtc() == peerBirth && !r.ChildHandle.IsClosed, "dead_peer_held_object");
            await r.Adapter.Receiver.WaitAsync(TimeSpan.FromSeconds(5)); Check(r.Adapter.Session.Aborted, "peer_death_abort");
            Reject(() => r.Adapter.Session.Permit(new("127.0.0.1", 45678, 1900000002, r.ChildBirth + 20)));
            Reject(() => r.Adapter.Session.Initialize(() => Task.CompletedTask));
        });
        test("foreign_server_grant_worker_rejected", async () =>
        {
            await using var r = await Rig.Open(); await r.Start();
            var response = await r.Deliver("Tick", challenge: Guid.NewGuid().ToString("N"));
            if (mutation == "accept-foreign") response = response with { Ok = true };
            Check(!response.Ok && response.Stopped, "foreign_challenge_fail_closed");
        });
    }
    internal static async Task<int> Negative(string value)
    {
        if (!Mutations.Contains(value)) return 2;
        mutation = value;
        var cases = new List<(string Name, Func<Task> Body)>();
        Register((name, body) => cases.Add((name, () => { body(); return Task.CompletedTask; })), (name, body) => cases.Add((name, body)));
        string target = value switch { "accept-foreign" => "foreign_server_grant_worker_rejected", "ignore-abort" => "abort_after_permit_no_init_or_more_ticks", _ => "worker_lease_expiry_after_real_connection" };
        try { await cases.Single(item => item.Name == "real_pipe_" + target).Body(); Console.WriteLine("MUTATION_NOT_DETECTED " + value); return 0; }
        catch (InvalidOperationException error) { Console.WriteLine("EXPECTED_ASSERTION_FAILURE " + value + " " + error.Message); return 1; }
        catch (Exception error) { Console.WriteLine("CONTROL_INFRASTRUCTURE_FAILURE " + error.GetType().Name); return 2; }
        finally { mutation = null; }
    }
}
