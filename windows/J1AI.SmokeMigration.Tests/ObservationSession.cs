using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text.Json;
using J1AI.SmokeMigration;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeMigration.Tests;

internal static class ObservationPaths
{
    internal static readonly string Root = FixedPath(Environment.SpecialFolder.LocalApplicationData, "J1AI", "BuildCandidates", "coordination-migration-tests-observability-hardening-03");
    internal const string RootId = "84b123a2d023a25821c50200000083000000000000000000";
    internal static readonly string Repository = FixedPath(Environment.SpecialFolder.MyDocuments, "__SoftDev", "J1_League_AI");
    internal static readonly string Binary = Path.Combine(Root, "bin", "J1AI.SmokeMigration.Tests", "release", "J1AI.SmokeMigration.Tests.dll");
    internal static readonly string Dotnet = Path.Combine(KnownFolderPaths.Get(Environment.SpecialFolder.LocalApplicationData), "J1AI", "Toolchains", "dotnet", "dotnet.exe");
    // No fixture or full-suite execution is authorized by this initial logging gate.
    internal static bool NativeFixtureAuthorized => false;
    internal static bool FullSuiteAuthorized => false;
    private static string FixedPath(Environment.SpecialFolder folder, params string[] parts)
    {
        string basePath = KnownFolderPaths.Get(folder);
        Contract.Require(!string.IsNullOrWhiteSpace(basePath) && Path.IsPathFullyQualified(basePath), "observation_base_path_invalid");
        string resolved = Path.GetFullPath(Path.Combine(new[] { basePath }.Concat(parts).ToArray()));
        Contract.Require(Directory.Exists(resolved), "observation_path_unavailable");
        return resolved;
    }
    internal static string RunPath(string run)
    { Contract.Require(Guid.TryParseExact(run, "N", out _), "run_id"); return Path.Combine(Root, "run-" + run); }
    internal static ReadPin PinRoot()
    {
        var pin = new ReadPin(Root, true);
        try { Contract.Require(pin.ObjectId == RootId, "observation_root_identity"); ReadPin.RequirePrivate(pin.Handle); return pin; }
        catch { pin.Dispose(); throw; }
    }
}

internal sealed record SourceBinding(string Head, string TrackedDiffSHA256, string AllChangesSHA256,
    string BinarySHA256, string DotnetSHA256, string RootIdentity, Dictionary<string, string> Sources, Dictionary<string, string> RuntimeFiles);
internal sealed record RunRequest(string Run, string Test, bool FixtureRequired, string RunDirectoryIdentity,
    JournalBinding Events, JournalBinding Ownership, SourceBinding Source, long StartTimestamp, string EnvironmentBlock);
internal sealed record WorkerBinding(int Pid, long CreatedFileTime, string ImageSHA256);
internal sealed record ObjectReceipt(string Kind, string Identity, string VolumeId, string FileId,
    string Owner, bool ProtectedDacl, string DaclBase64, uint ReparseTag, uint Links);

internal static class ObservationNative
{
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle h, byte[] data);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(SafeFileHandle h, int kind, byte[] data, uint size);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool FlushFileBuffers(SafeFileHandle h);
    internal static ObjectReceipt Inspect(SafeFileHandle h, string kind, bool permitTestSymlink = false, bool requireProtected = true)
    {
        var attrs = new byte[8]; var legacy = new byte[52];
        Contract.Require(GetFileInformationByHandleEx(h, 9, attrs, 8) && GetFileInformationByHandle(h, legacy), "receipt_native_query");
        uint tag = BitConverter.ToUInt32(attrs, 4), bits = BitConverter.ToUInt32(attrs), links = BitConverter.ToUInt32(legacy, 40);
        Contract.Require(permitTestSymlink ? tag == 0xa000000c : tag == 0 && (bits & 0x400) == 0, "receipt_reparse");
        Contract.Require(((bits & 0x10) != 0) == (kind is "directory" or "symlink"), "receipt_type");
        Contract.Require(links == 1, "receipt_hardlink");
        ReadPin.RequirePrivate(h, requireProtected: kind == "directory" && requireProtected);
        string identity = ReadPin.Identity(h); var security = ReadPin.Security(h); var raw = new byte[security.BinaryLength]; security.GetBinaryForm(raw, 0);
        return new(kind, identity, BitConverter.ToUInt64(Convert.FromHexString(identity)).ToString("x16"), identity[16..],
            security.Owner!.Value, security.ControlFlags.HasFlag(System.Security.AccessControl.ControlFlags.DiscretionaryAclProtected), Convert.ToBase64String(raw), tag, links);
    }
    internal static void Flush(SafeFileHandle h) => Contract.Require(FlushFileBuffers(h), "journal_flush");
    internal static DateTimeOffset CreatedUTC(SafeFileHandle h)
    {
        var data = new byte[52]; Contract.Require(GetFileInformationByHandle(h, data), "creation_time_query");
        return new(DateTime.FromFileTimeUtc(BitConverter.ToInt64(data, 4)));
    }
    internal static void DeleteOwned(SafeFileHandle parent, string name, string identity)
    {
        using var h = MockSandbox.Open(parent, name, false, false, delete: true, shareOverride: 0);
        Contract.Require(Inspect(h, "file").Identity == identity, "control_file_identity");
        // IO_STATUS_BLOCK has two pointer-sized fields, not a single pointer.
        nint io = Marshal.AllocHGlobal(IntPtr.Size * 2);
        try
        {
            int status = NtSetInformationFileRaw(h, io, [1], 1, 13);
            Contract.Require(status >= 0, "control_file_delete");
        }
        finally { Marshal.FreeHGlobal(io); }
    }
    [DllImport("ntdll", EntryPoint = "NtSetInformationFile")]
    private static extern int NtSetInformationFileRaw(SafeFileHandle h, nint status, byte[] data, uint size, int kind);
}

// Each log is a create-new, handle-relative file. Appends are bounded, flushed
// and read back on the SAME handle; no arbitrary log/root override exists.
internal sealed class DurableLog : IDisposable
{
    private readonly SafeFileHandle handle;
    private readonly FileStream stream = null!;
    private readonly SafeFileHandle borrowed = null!;
    private long sequence;
    private bool disposed;
    private string? boundRun, boundTest;
    internal readonly string Identity;
    internal readonly ObjectReceipt Receipt;
    internal bool Closed => disposed;
    internal bool ResourcesClosed => disposed && handle.IsClosed && borrowed.IsClosed;
    internal bool Failed { get; private set; }
    internal int Records => checked((int)sequence);
    internal DurableLog(SafeFileHandle parent, string name, bool create, JournalBinding? expected = null, string? run = null, string? test = null)
    {
        handle = MockSandbox.Open(parent, name, false, create, write: true, shareOverride: 1);
        try
        {
            Receipt = ObservationNative.Inspect(handle, "file"); Identity = Receipt.Identity;
            Contract.Require(expected == null || Receipt == expected.Receipt, "journal_identity");
            borrowed = new(handle.DangerousGetHandle(), false); stream = new(borrowed, FileAccess.ReadWrite);
            Contract.Require(stream.Length <= 16 * 1024 * 1024, "journal_limit");
            if (!create)
            {
                var existing = new byte[(int)stream.Length]; stream.ReadExactly(existing);
                Contract.Require(expected != null && run != null && test != null, "journal_binding_required");
                JournalValidation.ExistingHeader(existing, run, test); sequence = 1; boundRun = run; boundTest = test;
            }
        }
        catch { try { stream?.Dispose(); } finally { try { borrowed?.Dispose(); } finally { handle.Dispose(); } } throw; }
    }
    internal void Write(string run, string test, string stage, object? data = null)
    {
        Contract.Require(!Failed && !disposed, "journal_failed");
        try
        {
            boundRun ??= run; boundTest ??= test;
            Contract.Require(run == boundRun && test == boundTest, "journal_write_binding");
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(new { Sequence = sequence + 1, Run = run, Test = test,
                UTC = DateTimeOffset.UtcNow, Monotonic = Stopwatch.GetTimestamp(), Stage = stage, Data = data });
            Contract.Require(stream.Length + bytes.Length + 1 <= 16 * 1024 * 1024, "journal_limit");
            long start = stream.Length; stream.Position = start; stream.Write(bytes); stream.WriteByte(10); stream.Flush(true); ObservationNative.Flush(handle);
            stream.Position = start; var actual = new byte[bytes.Length + 1]; stream.ReadExactly(actual);
            Contract.Require(actual.AsSpan(0, bytes.Length).SequenceEqual(bytes) && actual[^1] == 10 && ReadPin.Identity(handle) == Identity, "journal_readback");
            stream.Position = stream.Length; sequence++;
        }
        catch { Failed = true; throw; }
    }
    internal EvidenceSnapshot FinalSnapshot(string path)
    {
        Contract.Require(!Failed && !disposed, "journal_failed");
        try
        {
            stream.Flush(true); ObservationNative.Flush(handle);
            Contract.Require(stream.Length is > 0 and <= 16 * 1024 * 1024, "journal_limit");
            stream.Position = 0; var bytes = new byte[(int)stream.Length]; stream.ReadExactly(bytes);
            JournalValidation.Identity(new(path, Receipt), path, ObservationNative.Inspect(handle, "file"));
            return new(path, Receipt, bytes);
        }
        catch { Failed = true; throw; }
    }
    public void Dispose()
    {
        if (disposed) return; disposed = true;
        try { stream.Dispose(); } finally { try { borrowed.Dispose(); } finally { handle.Dispose(); } }
    }
}

internal sealed class ObservationSession : IDisposable
{
    internal static ObservationSession? Current { get; private set; }
    internal static ObservationSession Require() => Current ?? throw new InvalidDataException("observation_session_required");
    private readonly ReadPin root;
    private readonly ReadPin runDirectory = null!;
    private readonly DurableLog events = null!, ownership = null!;
    private readonly Dictionary<string, ObjectReceipt> receipts = new(StringComparer.Ordinal);
    private readonly Stopwatch clock = Stopwatch.StartNew();
    private readonly Dictionary<string, (string Name, int Index, long Tick)> stages = new(StringComparer.Ordinal);
    internal RunRequest Request { get; }
    internal int CreatedObjects { get; private set; }
    internal int CleanedMocks { get; private set; }
    internal TransactionResult? LastTransaction { get; private set; }
    internal bool Failed => events.Failed || ownership.Failed;
    internal ObservationSession(RunRequest request)
    {
        Contract.Require(Current == null, "single_worker_session"); Request = request; root = ObservationPaths.PinRoot();
        try
        {
            runDirectory = new(ObservationPaths.RunPath(request.Run), true);
            Contract.Require(runDirectory.ObjectId == request.RunDirectoryIdentity, "run_directory_identity"); ReadPin.RequirePrivate(runDirectory.Handle);
            events = new(runDirectory.Handle, "test-events.jsonl", false, request.Events, request.Run, request.Test);
            ownership = new(runDirectory.Handle, "ownership.jsonl", false, request.Ownership, request.Run, request.Test);
            Current = this;
            Event("worker_started", new { request.Source, request.FixtureRequired, Process = Environment.ProcessId,
                Environment = WorkerEnvironment.Current().ToDictionary(p => p.Key, p => p.Value, StringComparer.OrdinalIgnoreCase) });
        }
        catch { Current = null; try { ownership?.Dispose(); } finally { try { events?.Dispose(); } finally { try { runDirectory?.Dispose(); } finally { root.Dispose(); } } } throw; }
    }
    internal void Event(string stage, object? data = null)
    { root.Verify(); runDirectory.Verify(); events.Write(Request.Run, Request.Test, stage, new { ElapsedMs = clock.Elapsed.TotalMilliseconds, Detail = data }); }
    internal void CheckCancellation()
    {
        Contract.Require(!Failed, "observation_log_failed");
        if (ObservationClock.At(Request.StartTimestamp, Stopwatch.GetTimestamp()) >= ObservationDeadline.Case)
        { Event("case_deadline_observed"); throw new OperationCanceledException("case_deadline"); }
        if (File.Exists(Path.Combine(runDirectory.Path, "cancel.request")))
        { Event("cancellation_observed"); throw new OperationCanceledException("supervisor_cancel_requested"); }
    }
    internal void AdvanceStage(string attempt, string name, int index)
    {
        CheckCancellation(); long now = Stopwatch.GetTimestamp();
        if (stages.TryGetValue(attempt, out var prior)) Event("transaction_stage_end", new { Attempt = attempt, prior.Name, prior.Index, ElapsedMs = Stopwatch.GetElapsedTime(prior.Tick, now).TotalMilliseconds });
        Event("transaction_stage_start", new { Attempt = attempt, Name = name, Index = index }); stages[attempt] = (name, index, now);
    }
    internal void TransactionEnded(string attempt, TransactionResult result)
    {
        LastTransaction = result;
        if (stages.Remove(attempt, out var prior)) Event("transaction_stage_end", new { Attempt = attempt, prior.Name, prior.Index, ElapsedMs = Stopwatch.GetElapsedTime(prior.Tick).TotalMilliseconds });
        Event("transaction_result", new { Attempt = attempt, Commit = result.Commit.ToString(), Pending = result.Pending.ToString(), result.Stage, result.Successful,
            Problems = result.Problems.Select(p => new { p.Stage, Type = p.Error.GetType().Name }) });
    }
    internal void Intent(string kind, string relative)
    {
        CheckCancellation(); Contract.Require(Request.FixtureRequired && ObservationPaths.NativeFixtureAuthorized, "fixture_not_authorized");
        Contract.Require(relative.Split('/').All(p => p.Length > 0 && p is not "." and not ".." && !p.Contains('\\') && !p.Contains(':')), "receipt_path");
        ownership.Write(Request.Run, Request.Test, "creation_intent", new { Kind = kind, Relative = relative });
    }
    internal void Created(string kind, string relative, SafeFileHandle h)
    {
        var receipt = ObservationNative.Inspect(h, kind, permitTestSymlink: kind == "symlink");
        ownership.Write(Request.Run, Request.Test, "object_created", new { Relative = relative, Receipt = receipt });
        // Set only AFTER durable write/readback. Missing receipts never confer
        // cleanup authority, including a crash between creation and this write.
        receipts[relative] = receipt; CreatedObjects++;
    }
    internal void VerifyOwned(string relative, SafeFileHandle h)
    {
        Contract.Require(!Failed && receipts.TryGetValue(relative, out _), "ownership_receipt_missing");
        var expected = receipts[relative]; var actual = ObservationNative.Inspect(h, expected.Kind, expected.ReparseTag != 0, expected.ProtectedDacl);
        Contract.Require(actual == expected, "ownership_receipt_mismatch");
        ownership.Write(Request.Run, Request.Test, "cleanup_object_verified", new { Relative = relative, Receipt = actual });
    }
    internal void Renamed(string from, string to, SafeFileHandle h)
    {
        VerifyOwned(from, h); var receipt = receipts[from];
        ownership.Write(Request.Run, Request.Test, "rename_completed", new { From = from, To = to, Receipt = receipt });
        receipts.Remove(from); receipts[to] = receipt;
    }
    internal void RecordTestDaclMutation(string relative, SafeFileHandle h)
    {
        Contract.Require(Request.Test == "unprotected_dacl_rejected" && receipts.TryGetValue(relative, out var old) && old.Identity == ReadPin.Identity(h), "test_dacl_mutation_scope");
        var receipt = ObservationNative.Inspect(h, "directory", requireProtected: false);
        ownership.Write(Request.Run, Request.Test, "controlled_test_dacl_mutation", new { Relative = relative, Receipt = receipt }); receipts[relative] = receipt;
    }
    internal void CleanupStart(string identity) => Event("mock_cleanup_start", new { Identity = identity });
    internal void CleanupEnd(string identity)
    {
        Contract.Require(!Directory.Exists(Path.Combine(ObservationPaths.Root, identity)), "mock_cleanup_unconfirmed");
        Event("mock_cleanup_end", new { Identity = identity, Handles = MockSandbox.LiveHandles }); CleanedMocks++;
    }
    public void Dispose()
    {
        Current = null;
        try { ownership.Dispose(); } finally { try { events.Dispose(); } finally { try { runDirectory.Dispose(); } finally { root.Dispose(); } } }
    }
}
