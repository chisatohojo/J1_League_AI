using System.Collections;
using System.Diagnostics;
using System.Globalization;
using System.Net;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace J1AI.SmokeNetworkObserver;

// OS-only observer. Never loads WebView2, starts a server or makes an HTTP call.
// WMI can stall: the single read-only query runs on a background thread; a
// bounded caller fails the session rather than starting another collector.
public sealed class WindowsCollector(ApprovalPlan plan) : ICollector
{
    private readonly Stopwatch clock = Stopwatch.StartNew();
    private readonly Dictionary<ProcessKey, WinHandle> retained = [];
    private readonly Dictionary<string, FileStream> verifiedImages = new(StringComparer.OrdinalIgnoreCase);
    private bool disposed;
    private string? observedRun;
    private Task<Snapshot>? inFlight;
    public Task<Snapshot> CollectAsync(long sequence, CancellationToken token)
    {
        if (disposed || inFlight is { IsCompleted: false }) throw new InvalidOperationException("collector_unavailable");
        inFlight = Task.Run(() => Collect(sequence), CancellationToken.None);
        return inFlight.WaitAsync(TimeSpan.FromMilliseconds(1500), token);
    }

    private Snapshot Collect(long sequence)
    {
        double started = clock.Elapsed.TotalMilliseconds; var utc = DateTimeOffset.UtcNow;
        var errors = new List<string>();
        // Manifest is immutable. State is only read; this observer never repairs it.
        Approval.Require(Approval.FileHash(Path.Combine(Approval.Control, "fixture-manifest.json")) == plan.ManifestSha, "manifest_changed");
        var candidates = ProcessMetadata();
        var relevant = candidates.Where(p => OwnershipRules.ExactUdf(p.Arguments, plan.Contract.Udf) ||
            OwnershipRules.Runner(p with { HandleVerified = true }, plan.Contract, "--smoke-worker") ||
            OwnershipRules.Runner(p with { HandleVerified = true }, plan.Contract, "--smoke-run") ||
            OwnershipRules.Backend(p with { HandleVerified = true }, plan.Contract)).ToList();
        // Preserve descendants even without a UDF argument so scope holes fail closed.
        bool added;
        do
        {
            added = false;
            foreach (var p in candidates.Except(relevant))
                if (relevant.Any(parent => parent.Key.Pid == p.ParentPid && parent.Key.CreatedFileTime <= p.Key.CreatedFileTime))
                { relevant.Add(p); added = true; }
        } while (added);
        var facts = new List<ProcessFact>();
        foreach (var fact in relevant)
        {
            try { facts.Add(Pin(fact)); }
            catch { facts.Add(fact with { HandleVerified = false }); errors.Add("process_pin_or_identity_failed"); }
        }
        var owner = OwnershipRules.Resolve(facts.ToArray(), plan.Contract);
        var selected = owner.Runtime.Concat(owner.Backend).ToHashSet();
        // Tables exist only transiently in memory. Only selected PIDs with
        // retained live handles on BOTH sides are copied into a Snapshot.
        var queried = ReadTcpTables();
        var raw = queried.Rows; errors.AddRange(queried.Errors);
        var rows = new List<TcpRow>();
        foreach (var key in selected)
        {
            try
            {
                if (!retained.TryGetValue(key, out var handle) || Win.WaitForSingleObject(handle, 0) != 258 || Win.Birth(handle) != key.CreatedFileTime)
                { errors.Add("process_changed_during_tcp_query"); continue; }
                rows.AddRange(raw.Where(r => r.Pid == key.Pid).Select(r => r with { CreatedFileTime = key.CreatedFileTime }));
            }
            catch { errors.Add("process_post_query_check_failed"); }
        }
        // Confirm removal against retained HANDLE, never against PID absence alone.
        foreach (var pair in retained.Where(p => !selected.Contains(p.Key)))
        {
            try
            {
                if (Win.WaitForSingleObject(pair.Value, 0) == 258 && owner.Runtime.All(k => k.Pid != pair.Key.Pid) &&
                    plan.Contract.RuntimeExecutable.Equals(Win.Image(pair.Value), StringComparison.OrdinalIgnoreCase))
                    errors.Add("live_retained_runtime_missing_from_metadata");
            }
            catch { errors.Add("retained_handle_check_failed"); }
        }
        bool end = false, runtimeEvent = false;
        try
        {
            var s = Approval.Read<FixtureState>(Path.Combine(Approval.Control, "run-state.json"));
            Approval.Require(s.ManifestHash == plan.ManifestSha && s.UdfIdentity == "a223b184:0171000000009673" &&
                s.RootIdentity == "a223b184:0357000000008b58", "state_identity_mismatch");
            string? run = s.Run;
            if (s.State == 2)
            {
                string intent = Path.Combine(Approval.Control, "run.intent");
                Approval.Require(run != null && File.ReadAllText(intent) == run, "run_journal_mismatch");
                observedRun ??= run;
                Approval.Require(observedRun == run, "run_changed");
            }
            else if (observedRun != null)
            {
                runtimeEvent = s.RuntimeEnded;
                end = s.State == 1 && run == observedRun && runtimeEvent &&
                    s.ServerEnded && s.WindowDisposed && s.InventoryValid &&
                    !File.Exists(Path.Combine(Approval.Control, "run.intent")) && !Directory.EnumerateFiles(Approval.Control, "*.pending").Any() &&
                    retained.Values.All(h => Win.WaitForSingleObject(h, 0) == 0);
                if (s.State != 1 || run != observedRun) errors.Add("runtime_or_cleanup_end_unconfirmed");
                if (end) Approval.Validate(plan, false); // Recheck all frozen assets/binaries/inventory, not just process exit.
            }
            else Approval.Require(Approval.FileHash(Path.Combine(Approval.Control, "run-state.json")) == plan.InitialStateSha,
                "baseline_state_changed_before_observation");
        }
        catch { end = false; errors.Add("fixture_state_read_or_validation_failed"); }
        var exited = new List<ProcessKey>();
        foreach (var pair in retained)
            try { if (Win.WaitForSingleObject(pair.Value, 0) == 0) exited.Add(pair.Key); }
            catch { errors.Add("process_exit_query_failed"); }
        return new(sequence, utc, DateTimeOffset.UtcNow, started, clock.Elapsed.TotalMilliseconds, facts.ToArray(), rows.ToArray(),
            errors.Distinct().ToArray(), end, observedRun, runtimeEvent, exited.ToArray());
    }

    private ProcessFact Pin(ProcessFact fact)
    {
        var approved = plan.FileHashes.Where(p => OwnershipRules.PathEquals(p.Key, fact.Executable)).ToArray();
        Approval.Require(approved.Length == 1, "executable_not_in_plan");
        if (!verifiedImages.ContainsKey(fact.Executable))
        {
            Approval.CheckPath(fact.Executable);
            // Hash the held file, disallowing write/delete/replacement throughout
            // observation. Checking a path hash once is not an image identity lease.
            var image = new FileStream(fact.Executable, FileMode.Open, FileAccess.Read, FileShare.Read);
            try
            {
                string hash = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(image)).ToLowerInvariant();
                Approval.Require(hash == approved[0].Value, "executable_hash_changed");
                lock (retained)
                {
                    if (disposed) throw new ObjectDisposedException(nameof(WindowsCollector));
                    verifiedImages.Add(fact.Executable, image); image = null!;
                }
            }
            finally { image?.Dispose(); }
        }
        var h = Win.OpenProcess(0x00100000 | 0x1000, false, fact.Key.Pid);
        try
        {
            Approval.Require(!h.IsInvalid && Win.WaitForSingleObject(h, 0) == 258, "process_not_live");
            long birth = Win.Birth(h);
            // WMI DMTF timestamp has microsecond precision; Win32 has 100ns precision.
            Approval.Require(birth / 10 == fact.Key.CreatedFileTime / 10 && OwnershipRules.PathEquals(Win.Image(h), fact.Executable),
                "process_handle_identity_mismatch");
            var key = new ProcessKey(fact.Key.Pid, birth);
            lock (retained)
            {
                if (disposed) throw new ObjectDisposedException(nameof(WindowsCollector));
                if (!retained.ContainsKey(key)) { retained.Add(key, h); h = null!; }
            }
            return fact with { Key = key, HandleVerified = true };
        }
        finally { h?.Dispose(); }
    }

    private static ProcessFact[] ProcessMetadata()
    {
        object? locator = null, service = null, rows = null;
        var result = new List<ProcessFact>();
        try
        {
            locator = Activator.CreateInstance(Type.GetTypeFromProgID("WbemScripting.SWbemLocator") ?? throw new IOException("wmi_unavailable"));
            service = ((dynamic)locator!).ConnectServer(".", @"root\cimv2");
            // Local process metadata only. Nothing from these command lines is persisted.
            rows = ((dynamic)service).ExecQuery("SELECT ProcessId,ParentProcessId,CreationDate,ExecutablePath,CommandLine FROM Win32_Process", "WQL", 48);
            foreach (object row in (IEnumerable)rows)
            {
                try
                {
                    dynamic p = row;
                    string? line = p.CommandLine, executable = p.ExecutablePath, birth = p.CreationDate;
                    string[] argv;
                    try { argv = line == null ? [] : Win.Argv(line); } catch { argv = []; }
                    int pid = Convert.ToInt32((object)p.ProcessId, CultureInfo.InvariantCulture);
                    int parent = Convert.ToInt32((object)p.ParentProcessId, CultureInfo.InvariantCulture);
                    result.Add(new(new(pid, birth == null ? 0 : WmiBirth(birth)), parent, executable ?? "", argv, false));
                    if (result.Count > 65536) throw new IOException("process_inventory_limit");
                }
                finally { Marshal.FinalReleaseComObject(row); }
            }
        }
        finally
        {
            foreach (var o in new[] { rows, service, locator }) if (o != null) Marshal.FinalReleaseComObject(o);
        }
        return result.ToArray();
    }
    internal static long WmiBirth(string s)
    {
        Approval.Require(s.Length == 25 && s[14] == '.' && s[21] is '+' or '-', "wmi_birth_invalid");
        var local = DateTime.ParseExact(s[..14], "yyyyMMddHHmmss", CultureInfo.InvariantCulture, DateTimeStyles.None)
            .AddTicks(long.Parse(s.Substring(15, 6), CultureInfo.InvariantCulture) * 10);
        int minutes = int.Parse(s[22..], CultureInfo.InvariantCulture) * (s[21] == '+' ? 1 : -1);
        return new DateTimeOffset(local, TimeSpan.FromMinutes(minutes)).UtcDateTime.ToFileTimeUtc();
    }

    public static TcpRow[] DecodeTable(byte[] buffer, int family)
    {
        Approval.Require(buffer.Length >= 4 && family is 2 or 23, "tcp_table_header");
        uint count = BitConverter.ToUInt32(buffer, 0); int stride = family == 2 ? 24 : 56;
        Approval.Require(count <= 1_000_000 && 4L + count * stride <= buffer.Length, "tcp_table_size");
        var result = new List<TcpRow>();
        uint U(int at) => BitConverter.ToUInt32(buffer, at);
        uint Scope(int at) => System.Buffers.Binary.BinaryPrimitives.ReadUInt32BigEndian(buffer.AsSpan(at, 4));
        int Port(int at) => (buffer[at] << 8) | buffer[at + 1];
        for (int i = 0; i < count; i++)
        {
            int p = 4 + i * stride;
            uint state = U(p + (family == 2 ? 0 : 48));
            string name = state switch { 1 => "CLOSED", 2 => "LISTEN", 3 => "SYN_SENT", 4 => "SYN_RECEIVED", 5 => "ESTABLISHED",
                6 => "FIN_WAIT1", 7 => "FIN_WAIT2", 8 => "CLOSE_WAIT", 9 => "CLOSING", 10 => "LAST_ACK", 11 => "TIME_WAIT", 12 => "DELETE_TCB", 100 => "BOUND", _ => "UNKNOWN" };
            string local = family == 2 ? new IPAddress(buffer.AsSpan(p + 4, 4)).ToString() : new IPAddress(buffer.AsSpan(p, 16), Scope(p + 16)).ToString();
            string remote = family == 2 ? new IPAddress(buffer.AsSpan(p + 12, 4)).ToString() : new IPAddress(buffer.AsSpan(p + 24, 16), Scope(p + 40)).ToString();
            result.Add(new(checked((int)U(p + (family == 2 ? 20 : 52))), null, local,
                Port(p + (family == 2 ? 8 : 20)), remote, Port(p + (family == 2 ? 16 : 44)), name, family,
                Convert.ToHexString(buffer.AsSpan(p, stride))));
        }
        return result.ToArray();
    }
    private static (TcpRow[] Rows, string[] Errors) ReadTcpTables()
    {
        var rows = new List<TcpRow>();
        var errors = new List<string>();
        foreach (uint family in new uint[] { 2, 23 })
        {
            try
            {
                uint bytes = 0; uint status = Win.GetExtendedTcpTable(0, ref bytes, false, family, 5, 0);
                Approval.Require(status == 122 && bytes is >= 4 and <= 32 * 1024 * 1024, "tcp_query_size");
                nint buffer = Marshal.AllocHGlobal((nint)bytes);
                try
                {
                    uint capacity = bytes;
                    status = Win.GetExtendedTcpTable(buffer, ref bytes, false, family, 5, 0);
                    // Growth/shrink races are reported as a missed snapshot, never retried silently.
                    Approval.Require(status == 0 && bytes <= capacity, "tcp_query_failed");
                    var data = new byte[bytes]; Marshal.Copy(buffer, data, 0, data.Length);
                    rows.AddRange(DecodeTable(data, (int)family));
                }
                finally { Marshal.FreeHGlobal(buffer); }
            }
            catch { errors.Add("tcp_family_" + family + "_query_failed"); }
        }
        // Preserve the successfully acquired family even if the other failed.
        // The caller persists these rows BEFORE marking this snapshot incomplete.
        return (rows.ToArray(), errors.ToArray());
    }
    public void Dispose()
    {
        lock (retained)
        {
            disposed = true;
            foreach (var h in retained.Values) h.Dispose(); retained.Clear();
            foreach (var image in verifiedImages.Values) image.Dispose(); verifiedImages.Clear();
        }
    }
}
