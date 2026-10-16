using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Runtime.InteropServices;

namespace J1AI.SmokeMigration;

// No input path, output path, root override, apply flag, lock acquisition,
// process launch, IPC signal or mutation interface is accepted by this class.
public sealed class Inspector : IDisposable
{
    private readonly List<ReadPin> pins = [];
    private readonly string local = SpecialFolderPath(Environment.SpecialFolder.LocalApplicationData);
    private ReadPin Pin(string path, bool directory = false)
    { var p = new ReadPin(path, directory); pins.Add(p); return p; }
    private byte[] Read(string path)
    {
        if (Path.GetFileName(path) == "smoke.lock")
        { var p = new ReadPin(path, false, false); pins.Add(p); return p.Bytes(); }
        return Pin(path).Bytes();
    }
    private string Hash(string path) => Contract.Hash(Read(path));
    private static string SpecialFolderPath(Environment.SpecialFolder folder)
    {
        string path = Environment.GetFolderPath(folder);
        Contract.Require(!string.IsNullOrWhiteSpace(path), "catalog_base_unavailable");
        ReadPin.Canonical(path);
        Contract.Require(Directory.Exists(path), "catalog_base_unavailable");
        return path;
    }
    private static string Relative(string path)
    {
        Contract.Require(!string.IsNullOrWhiteSpace(path) && !Path.IsPathRooted(path) && !path.Contains('\\') &&
            path.Split('/').All(p => p.Length > 0 && p != "." && p != ".." &&
                p.IndexOfAny(Path.GetInvalidFileNameChars()) < 0 && !p.EndsWith(' ') && !p.EndsWith('.')), "catalog_relative_path");
        return path;
    }
    private static string Under(string root, string relative)
    {
        string path = Path.Combine(root, Relative(relative).Replace('/', '\\'));
        ReadPin.Canonical(path);
        Contract.Require(path.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase), "catalog_path_escape");
        return path;
    }
    private static Catalog Approved(string local)
    {
        using var resource = typeof(Inspector).Assembly.GetManifestResourceStream("J1AI.SmokeMigration.approved-catalog.json")!;
        using var memory = new MemoryStream(); resource.CopyTo(memory);
        var c = Contract.Parse<Catalog>(memory.ToArray());
        Contract.Require(c.Version == 2 && c.Repository == "@documents/__SoftDev/J1_League_AI", "catalog_bindings");
        string repository = Under(SpecialFolderPath(Environment.SpecialFolder.MyDocuments), "__SoftDev/J1_League_AI");
        string desktop = SpecialFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string Resolve(string path, bool repositoryOnly = false)
        {
            if (path.StartsWith("@repository/", StringComparison.Ordinal)) return Under(repository, path["@repository/".Length..]);
            Contract.Require(!repositoryOnly, "catalog_path_scope");
            if (path.StartsWith("@local/", StringComparison.Ordinal)) return Under(local, path["@local/".Length..]);
            if (path.StartsWith("@desktop/", StringComparison.Ordinal)) return Under(desktop, path["@desktop/".Length..]);
            throw new InvalidDataException("catalog_path_anchor");
        }
        return c with
        {
            Repository = repository,
            Fixed = c.Fixed.Select(f => f with { Path = Resolve(f.Path) }).ToArray(),
            OldObserver = c.OldObserver.Select(f => f with { Path = Resolve(f.Path, true) }).ToArray(),
            Runner = c.Runner.Select(f => f with { FixedPath = Resolve(f.FixedPath, true), CandidatePath = Relative(f.CandidatePath) }).ToArray(),
            Protected = c.Protected.Select(f => f with { Path = Relative(f.Path) }).ToArray()
        };
    }
    private string[] Tree(string root)
    {
        Pin(root, true); var files = new List<string>();
        void Walk(string path)
        {
            foreach (string item in Directory.EnumerateFileSystemEntries(path))
            {
                if (Directory.Exists(item)) { Pin(item, true); Walk(item); }
                else { Pin(item); files.Add(item); }
            }
        }
        Walk(root); return files.Order(StringComparer.Ordinal).ToArray();
    }
    private void Ledger(string root, string expected, int count)
    {
        string ledger = Path.Combine(root, "candidate-inventory.json"); byte[] bytes = Read(ledger);
        Contract.Require(Contract.Hash(bytes) == expected, "candidate_ledger_sha");
        using var d = JsonDocument.Parse(bytes);
        var found = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { ledger };
        foreach (var f in d.RootElement.GetProperty("Files").EnumerateArray())
        {
            string rel = f.GetProperty("Path").GetString()!;
            Contract.Require(!Path.IsPathRooted(rel) && !rel.Contains('\\') && rel.Split('/').All(c => c != ".." && c != "." && c.Length > 0), "ledger_path");
            string p = Path.Combine(root, rel.Replace('/', '\\')); Contract.Require(found.Add(p), "ledger_duplicate");
            byte[] content = Read(p);
            long size = f.TryGetProperty("Bytes", out var b) ? b.GetInt64() : f.GetProperty("Length").GetInt64();
            Contract.Require(content.LongLength == size && Contract.Hash(content) == f.GetProperty("SHA256").GetString(), "candidate_file_sha");
        }
        var actual = Tree(root);
        Contract.Require(found.Count == count && actual.Length == count && found.SetEquals(actual), "candidate_inventory");
        ReadPin.RequirePrivate(Pin(root, true).Handle);
    }
    private static void ProcessesAbsent()
    {
        // Query only the relevant executable families; command lines are never
        // logged, retained, or emitted. Unreadable candidate process => STOP.
        Type type = Type.GetTypeFromProgID("WbemScripting.SWbemLocator") ?? throw new InvalidDataException("process_query_unavailable");
        dynamic locator = Activator.CreateInstance(type)!;
        object? servicesObject = null, rowsObject = null;
        static void Release(object? o) { if (o != null && Marshal.IsComObject(o)) Marshal.ReleaseComObject(o); }
        static object? Property(dynamic row, string name)
        {
            object? props = null, item = null;
            try { props = row.Properties_; item = ((dynamic)props).Item(name); return ((dynamic)item).Value; }
            finally { Release(item); Release(props); }
        }
        try
        {
            dynamic services = locator.ConnectServer(".", "root\\cimv2"); servicesObject = services;
            dynamic rows = services.ExecQuery("SELECT Name,CommandLine FROM Win32_Process WHERE Name='dotnet.exe' OR Name='python.exe' OR Name='pythonw.exe' OR Name='msedgewebview2.exe' OR Name LIKE 'J1AI.%'"); rowsObject = rows;
            foreach (dynamic row in rows)
                try
                {
                    string name = Property(row, "Name") as string ?? throw new InvalidDataException("process_name_unknown");
                    if (name.StartsWith("J1AI.DashboardHost", StringComparison.OrdinalIgnoreCase) || name.StartsWith("J1AI.SmokeNetworkObserver", StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("related_process");
                    string? cmd = Property(row, "CommandLine") as string;
                    Contract.Require(cmd != null, "process_ownership_unknown");
                    Contract.Require(!Regex.IsMatch(cmd, @"(?i)J1AI\.(DashboardHost|SmokeNetworkObserver)|synthetic_(gui_server|child)\.py|8f96edbb39b7d4d47cdad47c|J1AI-native-test-"), "related_process");
                }
                finally { Release(row); }
        }
        finally { Release(rowsObject); Release(servicesObject); Release(locator); }
    }
    public MigrationPlan Inspect()
    {
        Contract.Require(OperatingSystem.IsWindows() && Environment.Is64BitProcess, "windows_x64_only");
        var c = Approved(local); Contract.Require(c.Version == 2 && c.Fixed.Length == 42 && c.OldObserver.Length == 5 && c.Runner.Length == 19 && c.Protected.Length == 5, "catalog_counts");
        string control = Path.Combine(local, "J1AI", "Smoke", "dashboard-v1");
        string candidates = Path.Combine(local, "J1AI", "BuildCandidates");
        string runnerRoot = Path.Combine(candidates, "coordination-refreeze-01"), observerRoot = Path.Combine(candidates, "coordination-observer-final-01");
        ProcessesAbsent();
        foreach (string absent in new[] { Path.Combine(local, "J1AI", "RefreezeBackups"), Path.Combine(local, "J1AI", "Diagnostics"), Path.Combine(control, "run.intent") })
            Contract.Require(!File.Exists(absent) && !Directory.Exists(absent) && new FileInfo(absent).LinkTarget == null, "unexpected_existing_path");
        Contract.Require(!Directory.EnumerateFileSystemEntries(control).Any(p => p.EndsWith(".pending", StringComparison.OrdinalIgnoreCase)), "pending_exists");
        foreach (var f in c.Fixed.Concat(c.OldObserver)) Contract.Require(Hash(f.Path) == f.SHA256, "fixed_file_changed");
        foreach (var f in c.Protected) Contract.Require(Hash(Path.Combine(c.Repository, f.Path.Replace('/', '\\'))) == f.SHA256, "protected_input_changed");
        // Exact shipping/control inventories, not just expected-file presence.
        var expectedFixed = c.Fixed.Concat(c.OldObserver).Select(f => f.Path).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (string root in new[] { control, Path.Combine(c.Repository, "windows", "J1AI.DashboardHost", "bin", "Release", "net10.0-windows"),
            Path.Combine(c.Repository, "windows", "J1AI.DashboardHost.Tests", "bin", "Release", "net10.0-windows"),
            Path.Combine(c.Repository, "windows", "J1AI.SmokeNetworkObserver", "bin", "Release", "net10.0-windows") })
            Contract.Require(Tree(root).ToHashSet(StringComparer.OrdinalIgnoreCase).SetEquals(expectedFixed.Where(p => p.StartsWith(root + "\\", StringComparison.OrdinalIgnoreCase))), "fixed_inventory");
        Ledger(runnerRoot, "63237ce6b202e265c26702a9884c5daf9fe2cb0cb5045938e354afdf19fb1149", 111);
        Ledger(observerRoot, "35a8381a39e47d65650f512f7357d10186bd14d266909a47da06d8c3ad29b7cb", 39);
        Contract.Require(Hash(Path.Combine(observerRoot, "directory-audit.tsv")) == "cf17438f4ad1a1a51ddabc1817d9de8ad6dc2ba0600ab842275994605fc5c39b", "directory_audit_sha");
        byte[] oldM = Read(Path.Combine(control, "fixture-manifest.json")), oldS = Read(Path.Combine(control, "run-state.json"));
        Contract.Require(Contract.Hash(oldM) == Contract.OldM && Contract.Hash(oldS) == Contract.OldS, "old_metadata_sha");
        var m = Contract.Parse<Manifest>(oldM); var s = Contract.Parse<FrozenState>(oldS);
        Contract.Require(m.Identity == Contract.Identity && m.ProductionIdentity != m.Identity && m.Root == Path.Combine(control, "fixtures", "J1AI-native-test-dashboard-smoke-v1") &&
            m.Udf == Path.Combine(local, "J1AI", "Dashboard", Contract.Identity, "webview2-profile") && m.Runtime == "154.0.4258.62", "manifest_identity");
        Contract.Require(s.ManifestHash == Contract.OldM && s.State == 1 && s.Run.Length == 32 && s.RuntimeEnded && s.ServerEnded && s.WindowDisposed && s.InventoryValid, "not_clean");
        Contract.Require(s.RootIdentity == "a223b184:0357000000008b58" && s.UdfIdentity == "a223b184:0171000000009673" &&
            Pin(m.Root, true).LegacyId == s.RootIdentity && Pin(m.Udf, true).LegacyId == s.UdfIdentity, "directory_identity");
        string dashboard = Path.Combine(local, "J1AI", "Dashboard");
        string[] udfs = Directory.EnumerateDirectories(dashboard).Select(d => Path.Combine(d, "webview2-profile")).Where(Directory.Exists).ToArray();
        Contract.Require(udfs.Length == 32 && m.BaselineUdfs.Length == 31 && udfs.ToHashSet(StringComparer.OrdinalIgnoreCase).SetEquals(m.BaselineUdfs.Append(m.Udf)), "udf_inventory");
        // Only the approved fixed UDF's top-level metadata is opened; never enumerate its contents.
        var hashes = new SortedDictionary<string, string>(m.Hashes, StringComparer.Ordinal) { ["runner"] = Contract.Runner, ["product"] = Contract.Product };
        var newM = m with { Hashes = hashes };
        byte[] mb = JsonSerializer.SerializeToUtf8Bytes(newM, Contract.Json), sb = JsonSerializer.SerializeToUtf8Bytes(s with { ManifestHash = Contract.M }, Contract.Json);
        Contract.Require(mb.Length == 4449 && sb.Length == 302 && Contract.Hash(mb) == Contract.M && Contract.Hash(sb) == Contract.S, "new_metadata_bytes");
        var files = new List<PlanFile>();
        foreach (var f in c.Fixed.Concat(c.OldObserver))
        {
            string? candidate = null; string next = f.SHA256, role = "Retain", reason = "Frozen legacy/control/asset retained; not an adopted execution target";
            bool rewrite = false;
            var runner = c.Runner.SingleOrDefault(r => r.FixedPath == f.Path);
            if (runner != null)
            {
                candidate = Path.Combine(runnerRoot, runner.CandidatePath.Replace('/', '\\')); next = runner.CandidateSHA256;
                rewrite = runner.Changed; role = rewrite ? "RunnerReplace" : "RunnerMaintain"; reason = "Reviewed revision R execution bundle";
                Contract.Require(Hash(candidate) == next && (f.SHA256 != next) == rewrite, "runner_binding");
            }
            if (c.OldObserver.Any(x => x.Path == f.Path))
            {
                candidate = Path.Combine(observerRoot, "bin", "J1AI.SmokeNetworkObserver", "release", Path.GetFileName(f.Path)); next = Hash(candidate);
                rewrite = true; role = "ObserverReplace"; reason = "Complete reviewed revision O Observer bundle (including unchanged support files)";
            }
            if (f.Path == Path.Combine(control, "fixture-manifest.json")) { next = Contract.M; rewrite = true; role = "Manifest"; reason = "In-memory M; only runner/product hashes changed"; }
            if (f.Path == Path.Combine(control, "run-state.json")) { next = Contract.S; rewrite = true; role = "State"; reason = "In-memory S; only ManifestHash changed; all old proofs preserved"; }
            files.Add(new(files.Count, f.Path, candidate, f.Path, f.SHA256, next, rewrite, role,
                role == "State" ? ["Manifest"] : role == "ObserverReplace" ? ["RunnerReplace", "Manifest", "State"] : [], reason));
        }
        Contract.Require(files.Count == 47 && files.Count(f => f.Role == "RunnerReplace") == 6 && files.Count(f => f.Role == "RunnerMaintain") == 13 && files.Count(f => f.Role == "ObserverReplace") == 5, "plan_counts");
        Contract.Require(Hash(Path.Combine(observerRoot, "bin", "J1AI.SmokeNetworkObserver", "release", "J1AI.SmokeNetworkObserver.dll")) == Contract.Observer, "observer_binding");
        foreach (var p in pins) p.Verify(); ProcessesAbsent();
        return new(1, Contract.R, Contract.O, m.Identity, files.ToArray(), mb, sb, Contract.M, Contract.S, Contract.Observer,
            Path.Combine(control, Contract.Pending), Path.Combine(local, "J1AI", "RefreezeBackups", "coordination-refreeze-01-O") + "\\000..046.bin (index-to-original-path/SHA mapping in this plan); no backup created by Phase A",
            ["Preflight", "Exclusion", "Backup47", "VerifyBackup47", "PendingFlush", "RunnerReplace6", "Manifest", "State", "ObserverReplace5", "FinalReadback47", "PendingRemove"],
            ["Smoke instance existence gate Local\\J1AI.Dashboard.<identity> (not mutex ownership wait)", "Existing smoke.lock exclusive open", "Observer mutex Local\\J1AI.SmokeNetworkObserver.<identity> owned/released on same thread", "No worker/runtime/server/observer processes", "Phase A DOES NOT acquire any real gate, mutex, lock or signal"]);
    }
    public void Dispose() { foreach (var p in pins.AsEnumerable().Reverse()) p.Dispose(); pins.Clear(); }
}
