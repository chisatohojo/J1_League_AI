using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using J1AI.SmokeMigration;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeMigration.Tests;

internal sealed class OwnedCaseProcess : IDisposable
{
    [StructLayout(LayoutKind.Sequential)] private struct Startup
    {
        internal int Size; internal nint Reserved, Desktop, Title;
        internal uint X, Y, Width, Height, XChars, YChars, Fill, Flags;
        internal ushort Show, ReservedBytes; internal nint ReservedData, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)] private struct StartupEx { internal Startup Startup; internal nint Attributes; }
    [StructLayout(LayoutKind.Sequential)] private struct ProcessInfo { internal nint Process, Thread; internal uint Pid, Tid; }
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool InitializeProcThreadAttributeList(nint list, int count, uint flags, ref nuint bytes);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UpdateProcThreadAttribute(nint list, uint flags, nuint attribute, nint value, nuint size, nint previous, nint returned);
    [DllImport("kernel32")] private static extern void DeleteProcThreadAttributeList(nint list);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetHandleInformation(SafeFileHandle handle, uint mask, uint flags);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateProcessW(string application, StringBuilder command, nint processSecurity, nint threadSecurity,
        [MarshalAs(UnmanagedType.Bool)] bool inherit, uint flags, nint environment, string directory, ref StartupEx startup, out ProcessInfo info);
    [DllImport("kernel32", SetLastError = true)] private static extern uint WaitForSingleObject(SafeWaitHandle handle, uint milliseconds);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetExitCodeProcess(SafeWaitHandle handle, out uint code);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetProcessTimes(SafeWaitHandle handle, out long created, out long exited, out long kernel, out long user);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryFullProcessImageNameW(SafeWaitHandle handle, uint flags, StringBuilder name, ref uint size);
    private readonly SafeWaitHandle handle;
    internal WorkerBinding Binding { get; }
    private OwnedCaseProcess(nint process, int pid, string imageHash)
    {
        handle = new(process, true);
        try
        {
            Contract.Require(GetProcessTimes(handle, out long created, out _, out _, out _), "worker_creation_time");
            var path = new StringBuilder(32768); uint size = (uint)path.Capacity;
            Contract.Require(QueryFullProcessImageNameW(handle, 0, path, ref size) && path.ToString().Equals(ObservationPaths.Dotnet, StringComparison.OrdinalIgnoreCase), "worker_image_path");
            Binding = new(pid, created, imageHash);
        }
        catch { handle.Dispose(); throw; }
    }
    private static string Quote(string value)
    {
        Contract.Require(!value.Contains('\0'), "argument_nul");
        var b = new StringBuilder("\""); int slashes = 0;
        foreach (char c in value)
        {
            if (c == '\\') { slashes++; continue; }
            b.Append('\\', c == '"' ? slashes * 2 + 1 : slashes); b.Append(c); slashes = 0;
        }
        b.Append('\\', slashes * 2); return b.Append('"').ToString();
    }
    internal static OwnedCaseProcess Start(string run, string test, string imageHash, string environmentBlock, SafeFileHandle input, SafeFileHandle output, SafeFileHandle error)
    {
        var inherited = new[] { input, output, error }; nint list = 0, values = 0, environment = 0; bool initialized = false;
        OwnedCaseProcess? created = null;
        try
        {
            WorkerEnvironment.ValidateExact(WorkerEnvironment.Parse(environmentBlock), WorkerEnvironment.ValidatedExpected());
            byte[] environmentBytes = Encoding.Unicode.GetBytes(environmentBlock);
            environment = Marshal.AllocHGlobal(environmentBytes.Length);
            Marshal.Copy(environmentBytes, 0, environment, environmentBytes.Length);
            nuint bytes = 0; _ = InitializeProcThreadAttributeList(0, 1, 0, ref bytes);
            Contract.Require(bytes > 0, "worker_attributes_size"); list = Marshal.AllocHGlobal(checked((int)bytes));
            Contract.Require(InitializeProcThreadAttributeList(list, 1, 0, ref bytes), "worker_attributes_init"); initialized = true;
            values = Marshal.AllocHGlobal(IntPtr.Size * inherited.Length);
            for (int i = 0; i < inherited.Length; i++)
            { Contract.Require(SetHandleInformation(inherited[i], 1, 1), "worker_inherit_set"); Marshal.WriteIntPtr(values, i * IntPtr.Size, inherited[i].DangerousGetHandle()); }
            Contract.Require(UpdateProcThreadAttribute(list, 0, 0x20002, values, (nuint)(IntPtr.Size * inherited.Length), 0, 0), "worker_handle_list");
            var startup = new StartupEx { Startup = new Startup { Size = Marshal.SizeOf<StartupEx>(), Flags = 0x100,
                Input = input.DangerousGetHandle(), Output = output.DangerousGetHandle(), Error = error.DangerousGetHandle() }, Attributes = list };
            var command = new StringBuilder(string.Join(" ", new[] { ObservationPaths.Dotnet, ObservationPaths.Binary, "--worker", run, test }.Select(Quote)));
            // Explicit double-NUL Unicode block; NEVER inherit the parent block.
            Contract.Require(CreateProcessW(ObservationPaths.Dotnet, command, 0, 0, true, 0x08080400, environment, ObservationPaths.Root, ref startup, out var info), "worker_create_process");
            using var thread = new SafeWaitHandle(info.Thread, true);
            // Creation returned this exact process handle. Never reopen by PID
            // or terminate a process found by name. No termination API exists.
            created = new OwnedCaseProcess(info.Process, checked((int)info.Pid), imageHash); return created;
        }
        finally
        {
            bool reset = true;
            foreach (var h in inherited) if (!SetHandleInformation(h, 1, 0)) reset = false;
            if (initialized) DeleteProcThreadAttributeList(list);
            if (list != 0) Marshal.FreeHGlobal(list); if (values != 0) Marshal.FreeHGlobal(values);
            if (environment != 0) Marshal.FreeHGlobal(environment);
            if (!reset) { created?.Dispose(); throw new InvalidDataException("worker_inherit_reset"); }
        }
    }
    internal uint? Poll(uint milliseconds)
    {
        uint wait = WaitForSingleObject(handle, milliseconds);
        if (wait == 0x102) return null;
        Contract.Require(wait == 0 && GetExitCodeProcess(handle, out _), "worker_exit_unknown");
        Contract.Require(GetExitCodeProcess(handle, out uint code), "worker_exit_code"); return code;
    }
    public void Dispose() => handle.Dispose(); // Does NOT terminate a live worker.
}

internal static class CaseSupervisor
{
    private static byte[] ReadPinned(string path) { using var p = new ReadPin(path, false); return p.Bytes(); }
    internal static ObjectReceipt WriteFile(SafeFileHandle directory, string name, byte[] bytes)
    {
        using var h = MockSandbox.Open(directory, name, false, true);
        var receipt = ObservationNative.Inspect(h, "file");
        using var borrowed = new SafeFileHandle(h.DangerousGetHandle(), false); using var s = new FileStream(borrowed, FileAccess.ReadWrite);
        s.Write(bytes); s.Flush(true); ObservationNative.Flush(h); s.Position = 0; var read = new byte[bytes.Length]; s.ReadExactly(read);
        Contract.Require(read.SequenceEqual(bytes) && s.Length == bytes.Length, "control_readback");
        Contract.Require(ObservationNative.Inspect(h, "file") == receipt, "control_identity");
        return receipt;
    }
    private static string RawHash(SafeFileHandle handle)
    {
        ObservationNative.Flush(handle); using var borrowed = new SafeFileHandle(handle.DangerousGetHandle(), false);
        using var s = new FileStream(borrowed, FileAccess.Read); Contract.Require(s.Length <= 16 * 1024 * 1024, "raw_log_limit");
        s.Position = 0; var bytes = new byte[(int)s.Length]; s.ReadExactly(bytes); return Contract.Hash(bytes);
    }
    internal static SourceBinding Source()
    {
        var source = Contract.Parse<SourceBinding>(ReadPinned(Path.Combine(ObservationPaths.Root, "source-binding.json")));
        Contract.Require(source.RootIdentity == ObservationPaths.RootId && source.Head == "4d1c802a53a4f4d093f56376d8523ba25b316b26", "source_binding");
        Contract.Require(Assembly.GetExecutingAssembly().Location.Equals(ObservationPaths.Binary, StringComparison.OrdinalIgnoreCase) &&
            Environment.ProcessPath!.Equals(ObservationPaths.Dotnet, StringComparison.OrdinalIgnoreCase), "supervisor_binary_path");
        foreach (string sha in new[] { source.TrackedDiffSHA256, source.AllChangesSHA256, source.BinarySHA256, source.DotnetSHA256 })
            Contract.Require(sha.Length == 64 && sha.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), "binding_sha");
        Contract.Require(Contract.Hash(ReadPinned(ObservationPaths.Binary)) == source.BinarySHA256 && Contract.Hash(ReadPinned(ObservationPaths.Dotnet)) == source.DotnetSHA256, "execution_binary_sha");
        // Sources are a fixed test/tool allowlist, never arbitrary file paths.
        string[] approved = ["windows/J1AI.SmokeMigration/Contracts.cs", "windows/J1AI.SmokeMigration/Inspector.cs", "windows/J1AI.SmokeMigration/NativeRead.cs", "windows/J1AI.SmokeMigration/Program.cs", "windows/J1AI.SmokeMigration/approved-catalog.json", "windows/J1AI.SmokeMigration/J1AI.SmokeMigration.csproj",
            "windows/J1AI.SmokeMigration.Tests/Program.cs", "windows/J1AI.SmokeMigration.Tests/Transaction.cs", "windows/J1AI.SmokeMigration.Tests/MockSandbox.cs", "windows/J1AI.SmokeMigration.Tests/J1AI.SmokeMigration.Tests.csproj", "windows/J1AI.SmokeMigration.Tests/ObservationSession.cs", "windows/J1AI.SmokeMigration.Tests/CaseSupervisor.cs",
            "windows/J1AI.SmokeMigration.Tests/WorkerEnvironment.cs", "windows/J1AI.SmokeMigration.Tests/ObservationDeadline.cs", "windows/J1AI.SmokeMigration.Tests/JournalValidation.cs", "windows/J1AI.SmokeMigration.Tests/HardeningTests.cs"];
        Contract.Require(source.Sources.Keys.ToHashSet(StringComparer.Ordinal).SetEquals(approved), "source_inventory");
        foreach (string p in approved) Contract.Require(Contract.Hash(ReadPinned(Path.Combine(ObservationPaths.Repository, p.Replace('/', '\\')))) == source.Sources[p], "source_bytes_changed");
        string[] support = ["J1AI.SmokeMigration.dll", "J1AI.SmokeMigration.Tests.deps.json", "J1AI.SmokeMigration.Tests.runtimeconfig.json"];
        Contract.Require(source.RuntimeFiles.Keys.ToHashSet(StringComparer.Ordinal).SetEquals(support), "runtime_inventory");
        foreach (string p in support) Contract.Require(Contract.Hash(ReadPinned(Path.Combine(Path.GetDirectoryName(ObservationPaths.Binary)!, p))) == source.RuntimeFiles[p], "runtime_file_sha");
        Contract.Require(typeof(Contract).Assembly.Location.Equals(Path.Combine(Path.GetDirectoryName(ObservationPaths.Binary)!, support[0]), StringComparison.OrdinalIgnoreCase), "loaded_tool_path");
        return source;
    }
    internal static int Run(string test, bool fixture, string? expectedAssertion, ObservationClock clock)
    {
        Contract.Require(!fixture || ObservationPaths.NativeFixtureAuthorized, "native_case_not_authorized");
        var environment = WorkerEnvironment.ValidatedExpected();
        WorkerEnvironment.SupervisorPreflight(WorkerEnvironment.Current(), environment); // Post-CLR boundary A only.
        string environmentBlock = WorkerEnvironment.Build(environment, environment);
        using var root = ObservationPaths.PinRoot(); var source = Source();
        ObservationDeadline.RequireBefore(clock, ObservationDeadline.Case);
        Contract.Require(!Directory.EnumerateFileSystemEntries(ObservationPaths.Root).Any(p => Path.GetFileName(p).StartsWith("migration-test-", StringComparison.Ordinal)), "unrecovered_observation_mock");
        Contract.Require(!File.Exists(Path.Combine(ObservationPaths.Root, "supervisor.pending")), "supervisor_pending");
        Contract.Require(!File.Exists(Path.Combine(ObservationPaths.Root, "hardening.lock")), "hardening_running");
        // Create-new exclusive gate. A live/failed prior attempt is not adopted.
        using var gate = MockSandbox.Open(root.Handle, "supervisor.lock", false, true, shareOverride: 0);
        string gateId = ReadPin.Identity(gate), run = Guid.NewGuid().ToString("N");
        using var directory = MockSandbox.Open(root.Handle, "run-" + run, true, true);
        _ = ObservationNative.Inspect(directory, "directory");
        using var supervisor = new DurableLog(directory, "supervisor.jsonl", true);
        string runPath = ObservationPaths.RunPath(run);
        var supervisorBinding = new JournalBinding(Path.Combine(runPath, "supervisor.jsonl"), supervisor.Receipt);
        try
        {
        JournalBinding eventsBinding, ownershipBinding;
        using (var events = new DurableLog(directory, "test-events.jsonl", true))
        { events.Write(run, test, "journal_prepared", source); eventsBinding = new(Path.Combine(runPath, "test-events.jsonl"), events.Receipt); }
        using (var ownership = new DurableLog(directory, "ownership.jsonl", true))
        { ownership.Write(run, test, "journal_prepared", new { CreationIntentIsNotAtomicWithCreation = true, AutomaticRecoveryAuthorized = false }); ownershipBinding = new(Path.Combine(runPath, "ownership.jsonl"), ownership.Receipt); }
        var request = new RunRequest(run, test, fixture, ReadPin.Identity(directory), eventsBinding, ownershipBinding, source, clock.Origin, environmentBlock);
        WriteFile(directory, "request.json", JsonSerializer.SerializeToUtf8Bytes(request));
        WriteFile(root.Handle, "supervisor.pending", JsonSerializer.SerializeToUtf8Bytes(new { Run = run, Test = test, State = "RUNNING", GateIdentity = gateId }));
        string pendingId;
        using (var p = new ReadPin(Path.Combine(ObservationPaths.Root, "supervisor.pending"), false)) pendingId = p.ObjectId;
        using var output = MockSandbox.Open(directory, "stdout.raw.log", false, true);
        using var error = MockSandbox.Open(directory, "stderr.raw.log", false, true);
        using var input = MockSandbox.Open(directory, "stdin.empty", false, true);
        supervisor.Write(run, test, "before_worker", new { source, RunDirectory = request.RunDirectoryIdentity,
            Environment = environment, EnvironmentBlockSHA256 = Contract.Hash(Encoding.Unicode.GetBytes(environmentBlock)),
            CaseDeadline = ObservationDeadline.Case, CleanupDeadline = ObservationDeadline.Cleanup, ExitDeadline = ObservationDeadline.Exit,
            FinalizeDeadline = ObservationDeadline.Finalize, OuterDeadline = ObservationDeadline.Outer, HardStopGuaranteed = false, PreCLRProtectionProven = false });
        using var binaryPin = new ReadPin(ObservationPaths.Binary, false); using var dotnetPin = new ReadPin(ObservationPaths.Dotnet, false);
        Contract.Require(Contract.Hash(binaryPin.Bytes()) == source.BinarySHA256 && Contract.Hash(dotnetPin.Bytes()) == source.DotnetSHA256, "launch_sha");
        var supportPins = new List<ReadPin>();
        try
        {
        foreach (var p in source.RuntimeFiles)
        { var pin = new ReadPin(Path.Combine(Path.GetDirectoryName(ObservationPaths.Binary)!, p.Key), false); supportPins.Add(pin); Contract.Require(Contract.Hash(pin.Bytes()) == p.Value, "launch_support_sha"); }
        ObservationDeadline.RequireBefore(clock, ObservationDeadline.Case);
        using var worker = OwnedCaseProcess.Start(run, test, source.DotnetSHA256, environmentBlock, input, output, error);
        supervisor.Write(run, test, "worker_created", worker.Binding);
        WriteFile(directory, "worker-binding.json", JsonSerializer.SerializeToUtf8Bytes(worker.Binding));
        supervisor.Write(run, test, "worker_permitted");
        uint? code = null; bool cancelled = false; double? exitAt = null;
        while (clock.Seconds < ObservationDeadline.Exit)
        {
            code = worker.Poll(100);
            // Never break before capturing the observed exit time. Final
            // classification also checks the worker's case/cleanup timestamps.
            if (code != null) { exitAt = clock.Seconds; break; }
            var progress = Progress(request);
            if (!cancelled && ObservationDeadline.CancellationDue(clock, progress))
            {
                cancelled = true;
                supervisor.Write(run, test, "deadline_observed", new { Outcome = "TIMEOUT", LastDurableStage = LastStage(runPath),
                    progress.CaseEnded, progress.CleanupStarted, progress.CleanupEnded, CleanupStartObserved = progress.CleanupStarted != null });
                WriteFile(directory, "cancel.request", []);
            }
        }
        if (code == null)
        {
            supervisor.Write(run, test, "BLOCKED_worker_exit_unknown", new { Outcome = "WORKER_EXIT_UNCONFIRMED", LastDurableStage = LastStage(runPath), NoTerminationAttempted = true, PendingRetained = true });
            Console.WriteLine("OBSERVATION_BLOCKED WORKER_EXIT_UNCONFIRMED; gate retained; no retry/termination."); return 2;
        }
        supervisor.Write(run, test, "worker_exited", new { ActualExitCode = code, ExitObservedAt = exitAt, Cancelled = cancelled });
        ObservationDeadline.RequireBefore(clock, ObservationDeadline.Finalize);
        var terminalProgress = Progress(request);
        if (cancelled || exitAt >= ObservationDeadline.Exit || terminalProgress.CaseEnded >= ObservationDeadline.Case || terminalProgress.CleanupEnded >= ObservationDeadline.Cleanup)
        { supervisor.Write(run, test, "final_non_success", new { Outcome = "TIMEOUT", terminalProgress, PendingRetained = true }); Console.WriteLine("OBSERVATION_BLOCKED TIMEOUT"); return 2; }
        using var eventsHeld = new HeldEvidence(eventsBinding); using var ownershipHeld = new HeldEvidence(ownershipBinding);
        using var summaryPin = new ReadPin(Path.Combine(runPath, "summary.json"), false);
        byte[] summaryBytes = summaryPin.Bytes();
        var verified = JournalValidation.Worker(request, eventsHeld.Snapshot, ownershipHeld.Snapshot, summaryBytes, code.Value, worker.Binding.Pid);
        var decision = ObservationDeadline.Evaluate(clock, verified.Phases, true, exitAt, cancelled, verified.TestSucceeded);
        if (!decision.ReleaseGate)
        { supervisor.Write(run, test, "final_non_success", new { Outcome = decision.Outcome.ToString(), decision.Reason, verified.Phases, PendingRetained = true }); Console.WriteLine("OBSERVATION_BLOCKED " + decision.Outcome); return 2; }
        Contract.Require(!Directory.EnumerateDirectories(ObservationPaths.Root, "migration-test-*").Any(), "mock_residue");
        string stdout = RawHash(output), stderr = RawHash(error), summaryHash = Contract.Hash(summaryBytes);
        supervisor.Write(run, test, "final_observation", new { Outcome = decision.Outcome.ToString(), ActualExitCode = code,
            StdoutSHA256 = stdout, StderrSHA256 = stderr, verified.EventsSHA256, verified.OwnershipSHA256, SummarySHA256 = summaryHash, Summary = verified.Summary, verified.Phases });
        supervisor.Write(run, test, "supervisor_complete", new { Outcome = "VERIFIED_SUCCESS", Scope = "worker_and_evidence_only_gate_release_not_yet_confirmed", FlushReadback = true });
        supervisor.Dispose(); // Seal write handle before final independent read.
        using var supervisorHeld = new HeldEvidence(supervisorBinding);
        JournalValidation.Supervisor(request, supervisorBinding, supervisorHeld.Snapshot, verified, code.Value, RawHash(output), RawHash(error), Contract.Hash(summaryPin.Bytes()), worker.Binding);
        // All three journal handles remain pinned through successful release.
        decision = ObservationDeadline.Evaluate(clock, verified.Phases, true, exitAt, cancelled, verified.TestSucceeded);
        if (!decision.ReleaseGate) throw new TimeoutException("finalize_deadline");
        // Deliberately quarantine even VERIFIED_SUCCESS in this limited gate:
        // pre-CLR protection and an independent hard-deadline owner have NOT
        // been established. Never delete the persistent gate and then discover
        // that an unbounded native deletion/flush returned after the deadline.
        // This is evidence success, NOT permission to start a subsequent case.
        WriteFile(directory, "verified-evidence.json", JsonSerializer.SerializeToUtf8Bytes(new
        { Outcome = "VERIFIED_SUCCESS", Scope = "worker_and_evidence_only", GateRetained = true,
            GateIdentity = gateId, PendingIdentity = pendingId, PreCLRProtectionProven = false, HardStopGuaranteed = false,
            SecondsAtValidation = clock.Seconds }));
        ObservationDeadline.RequireBefore(clock, ObservationDeadline.Finalize);
        Console.WriteLine("OBSERVATION_PASS VERIFIED_SUCCESS gate retained; Run=" + run + " Test=" + test); return 0;
        }
        finally { foreach (var pin in supportPins.AsEnumerable().Reverse()) pin.Dispose(); }
        }
        catch (Exception e)
        {
            // Retain every artifact and the control gate on failure. Never
            // silently interpret an unavailable log/exit status as PASS.
            ObservationOutcome outcome = e is EvidenceFailure failure ? failure.Outcome : e is TimeoutException ? ObservationOutcome.TIMEOUT :
                e is IOException && e is not InvalidDataException ? ObservationOutcome.EVIDENCE_UNAVAILABLE : ObservationOutcome.EVIDENCE_INVALID;
            string reason = e is EvidenceFailure detail ? detail.Reason : e is TimeoutException ? "deadline_exceeded" : "validation_failed";
            try
            {
                var result = new { Outcome = outcome.ToString(), Reason = reason, LastDurableStage = LastStage(runPath), NoAutomaticRetry = true };
                if (!supervisor.Failed && !supervisor.Closed) supervisor.Write(run, test, "supervisor_failed", result);
                else WriteFile(directory, "failure-outcome.json", JsonSerializer.SerializeToUtf8Bytes(result));
            }
            catch (Exception) { outcome = ObservationOutcome.EVIDENCE_UNAVAILABLE; } // Remains non-success; never unlock/retry.
            Console.Error.WriteLine("OBSERVATION_BLOCKED " + outcome); return 2;
        }
    }
    private static PhaseTimes Progress(RunRequest request)
    {
        // Best-effort progress can trigger conservative cancellation, NEVER
        // authorize success. Only the final pinned strict validator can do so.
        try
        {
            using var pin = new ReadPin(request.Events.Path, false, false);
            JournalValidation.Identity(request.Events, pin.Path, ObservationNative.Inspect(pin.Handle, "file"));
            byte[] bytes = pin.Bytes(); int tail = Array.LastIndexOf(bytes, (byte)10);
            if (tail < 0) return new(null, null, null);
            var rows = JournalValidation.Records(bytes[..(tail + 1)], request.Run, request.Test);
            double? At(string stage) => rows.LastOrDefault(r => r.Stage == stage) is { } row ? ObservationClock.At(request.StartTimestamp, row.Monotonic) : null;
            return new(At("test_end"), At("cleanup_start"), At("cleanup_complete"));
        }
        catch { return new(null, null, null); }
    }
    private static string LastStage(string runPath)
    {
        // Worker may be appending: share read/write/delete for OBSERVATION only.
        // Incomplete tail is never accepted as a completed event or PASS.
        try
        {
            using var file = new FileStream(Path.Combine(runPath, "test-events.jsonl"), FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            Contract.Require(file.Length <= 16 * 1024 * 1024, "event_limit");
            using var reader = new StreamReader(file); string last = "UNKNOWN";
            while (reader.ReadLine() is { } line) { try { using var d = JsonDocument.Parse(line); last = d.RootElement.GetProperty("Stage").GetString() ?? "UNKNOWN"; } catch (JsonException) { break; } }
            return last;
        }
        catch { return "UNKNOWN"; } // UNKNOWN is never a success verdict.
    }
    internal static RunRequest WorkerRequest(string run, string test)
    {
        using var root = ObservationPaths.PinRoot(); string path = ObservationPaths.RunPath(run);
        var request = Contract.Parse<RunRequest>(ReadPinned(Path.Combine(path, "request.json")));
        Contract.Require(request.Run == run && request.Test == test && (!request.FixtureRequired || ObservationPaths.NativeFixtureAuthorized), "worker_request");
        Contract.Require(request.StartTimestamp > 0 && request.StartTimestamp <= Stopwatch.GetTimestamp(), "worker_clock_origin");
        var expected = WorkerEnvironment.ValidatedExpected();
        WorkerEnvironment.RequireCurrentWorker(request.EnvironmentBlock, expected);
        Contract.Require(request.Events.Path == Path.Combine(path, "test-events.jsonl") && request.Ownership.Path == Path.Combine(path, "ownership.jsonl"), "worker_journal_paths");
        var clock = Stopwatch.StartNew(); WorkerBinding? binding = null;
        while (clock.Elapsed < TimeSpan.FromSeconds(10))
        {
            if (File.Exists(Path.Combine(path, "worker-binding.json")))
            {
                try { binding = Contract.Parse<WorkerBinding>(ReadPinned(Path.Combine(path, "worker-binding.json"))); break; }
                catch (InvalidDataException e) when (e.Message == "read_handle:32") { }
            }
            Thread.Sleep(20); // Bounded startup handshake, not test retry.
        }
        using var self = Process.GetCurrentProcess();
        Contract.Require(binding != null && binding.Pid == Environment.ProcessId && binding.CreatedFileTime == self.StartTime.ToFileTimeUtc(), "worker_process_binding");
        Contract.Require(JsonSerializer.SerializeToUtf8Bytes(request.Source).SequenceEqual(JsonSerializer.SerializeToUtf8Bytes(Source())), "worker_source_binding");
        Contract.Require(binding.ImageSHA256 == request.Source.DotnetSHA256, "worker_image_binding"); return request;
    }
}
