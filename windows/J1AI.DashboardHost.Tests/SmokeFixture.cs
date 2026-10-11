using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal enum SmokeState { UNINITIALIZED, CLEAN, RUNNING, BLOCKED }
internal sealed class SmokeError(string code) : Exception(code);
internal sealed record SmokeManifest(int Version, string Root, string Identity, string Udf,
    string ProductionIdentity, SortedDictionary<string, string> Hashes, string[] BaselineUdfs, string Runtime = "synthetic-only");
internal sealed record SmokeRecord(string ManifestHash, SmokeState State, string Run,
    bool RuntimeEnded, bool ServerEnded, bool WindowDisposed, bool InventoryValid,
    string UdfIdentity = "", string RootIdentity = "");
internal sealed record SmokeInspection(SmokeManifest Manifest, string Fingerprint, bool FirstUse);
internal sealed record SmokeEvidence(bool RuntimeEnded, bool ServerEnded, bool WindowDisposed);

// This is a test-assembly facility, never a product configuration override.
internal sealed class SmokeFixture
{
    internal readonly string Local, Control, Root, StatePath, ManifestPath, IntentPath, LockPath;
    internal readonly string Python, Launcher, Web, Backend, Runner;
    internal static readonly string[] Assets = ["index.html", "styles.css", "app.js", "dashboard-data.js",
        "team-colors.js", "demo-data.js", "components/prediction-probability-bar.js"];
    private static readonly JsonSerializerOptions Json = new() { UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow };
    internal SmokeFixture(string local, string python, string launcher, string web, string backend, string runner)
    {
        Local = Path.GetFullPath(local);
        Control = Path.Combine(Local, "J1AI", "Smoke", "dashboard-v1");
        Root = Path.Combine(Control, "fixtures", "J1AI-native-test-dashboard-smoke-v1");
        StatePath = Path.Combine(Control, "run-state.json"); ManifestPath = Path.Combine(Control, "fixture-manifest.json");
        IntentPath = Path.Combine(Control, "run.intent"); LockPath = Path.Combine(Control, "smoke.lock");
        Python = Path.GetFullPath(python); Launcher = Path.GetFullPath(launcher); Web = Path.GetFullPath(web);
        Backend = Path.GetFullPath(backend); Runner = Path.GetFullPath(runner);
    }
    internal static void Require(bool condition, string code) { if (!condition) throw new SmokeError(code); }
    internal static string Hash(byte[] value) => Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant();
    internal static string FileHash(string path) => Hash(File.ReadAllBytes(path));
    private static string AssetPath(string root, string asset) => Path.Combine(root, asset.Replace('/', Path.DirectorySeparatorChar));
    internal static string Fingerprint(SmokeManifest manifest) => Hash(JsonSerializer.SerializeToUtf8Bytes(manifest, Json));
    internal static void RequireClean(SmokeRecord state, string fingerprint)
    {
        Require(state.ManifestHash == fingerprint && state.State == SmokeState.CLEAN && !string.IsNullOrEmpty(state.Run) &&
            state.RuntimeEnded && state.ServerEnded && state.WindowDisposed && state.InventoryValid &&
            !string.IsNullOrEmpty(state.UdfIdentity) && !string.IsNullOrEmpty(state.RootIdentity), "unclean_state");
    }
    private static T Read<T>(string path)
    {
        try
        {
            Require(new FileInfo(path).Length <= 1024 * 1024, "metadata_size");
            // Duplicate property names are not accepted as alternate state interpretations.
            var bytes = File.ReadAllBytes(path);
            using var document = JsonDocument.Parse(bytes);
            void Unique(JsonElement item)
            {
                if (item.ValueKind == JsonValueKind.Object)
                {
                    var names = new HashSet<string>(StringComparer.Ordinal);
                    foreach (var p in item.EnumerateObject()) { Require(names.Add(p.Name), "metadata_duplicate"); Unique(p.Value); }
                }
                else if (item.ValueKind == JsonValueKind.Array) foreach (var child in item.EnumerateArray()) Unique(child);
            }
            Unique(document.RootElement);
            return JsonSerializer.Deserialize<T>(bytes, Json) ?? throw new SmokeError("metadata_null");
        }
        catch (SmokeError) { throw; }
        catch { throw new SmokeError("metadata_invalid"); }
    }
    internal static void AtomicWrite<T>(string path, T value)
    {
        string pending = path + ".pending";
        using (var stream = new FileStream(pending, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
        { stream.Write(JsonSerializer.SerializeToUtf8Bytes(value, Json)); stream.Flush(true); }
        File.Move(pending, path, true);
        // Any interrupted write leaves .pending or run.intent and fails closed.
    }
    internal static void CheckPath(string path)
    {
        Require(Path.IsPathFullyQualified(path) && !path.StartsWith(@"\\", StringComparison.Ordinal), "path_not_local");
        string full = Path.GetFullPath(path);
        Require(full.Equals(path, StringComparison.OrdinalIgnoreCase) && path.IndexOf(':', 2) < 0, "path_not_canonical");
        for (var part = new DirectoryInfo(Path.GetDirectoryName(full) ?? full); part != null; part = part.Parent)
        {
            Require(part.LinkTarget == null, "path_link");
            if (part.Exists) Require((part.Attributes & FileAttributes.ReparsePoint) == 0, "path_reparse");
        }
        if (File.Exists(full) || Directory.Exists(full))
            Require((File.GetAttributes(full) & FileAttributes.ReparsePoint) == 0, "path_reparse");
        // Exists=false is not permission to follow a dangling link.
        var info = new FileInfo(full);
        Require(info.LinkTarget == null, "path_link");
    }
    internal static void CheckTree(string root)
    {
        CheckPath(root);
        if (!Directory.Exists(root)) return;
        foreach (string entry in Directory.EnumerateFileSystemEntries(root))
        { CheckPath(entry); if (Directory.Exists(entry)) CheckTree(entry); }
    }
    internal string[] Inventory()
    {
        string parent = Path.Combine(Local, "J1AI", "Dashboard"); CheckPath(parent);
        if (!Directory.Exists(parent)) return [];
        var paths = new List<string>();
        foreach (string directory in Directory.EnumerateDirectories(parent))
        {
            // Metadata only: never enter any old UDF.
            CheckPath(directory);
            string profile = Path.Combine(directory, "webview2-profile"); CheckPath(profile);
            if (Directory.Exists(profile)) paths.Add(Path.GetFullPath(profile));
        }
        return paths.Order(StringComparer.OrdinalIgnoreCase).ToArray();
    }
    internal static void CheckInventory(string[] baseline, string[] current, string udf, bool first)
    {
        var before = new HashSet<string>(baseline, StringComparer.OrdinalIgnoreCase);
        var after = new HashSet<string>(current, StringComparer.OrdinalIgnoreCase);
        Require(before.Count == baseline.Length && after.Count == current.Length && !before.Contains(udf), "inventory_invalid");
        Require(before.IsSubsetOf(after), "udf_removed");
        after.ExceptWith(before);
        Require(after.Count <= 1 && after.All(p => p.Equals(udf, StringComparison.OrdinalIgnoreCase)), "udf_added");
        if (!first) Require(after.SetEquals([udf]), "udf_missing");
    }
    internal static async Task<RepositoryIdentity> Identity(string root, string python, string launcher)
    {
        CheckPath(root); CheckPath(python); CheckPath(launcher);
        using var helper = new Process { StartInfo = new(python) { UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true, WorkingDirectory = Path.GetDirectoryName(launcher)! } };
        // Reuse the actual Python authority even BEFORE the fixed root exists.
        // There is intentionally no independent hash/casing implementation here.
        const string code = "import json,runpy,sys;from pathlib import Path;p=Path(sys.argv[1]).resolve();f=runpy.run_path(sys.argv[2],run_name='j1ai_smoke_identity_only')['instance_id'];print(json.dumps([str(p),f(p)]))";
        foreach (string arg in new[] { "-I", "-S", "-B", "-u", "-c", code, root, launcher }) helper.StartInfo.ArgumentList.Add(arg);
        Require(helper.Start(), "identity_start");
        var stdout = helper.StandardOutput.ReadToEndAsync(); var stderr = helper.StandardError.ReadToEndAsync();
        try
        {
            await helper.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(10));
            string output = await stdout, errors = await stderr;
            Require(helper.ExitCode == 0 && output.Length < 4096 && errors.Length == 0, "identity_failure");
            var parts = JsonSerializer.Deserialize<string[]>(output)!;
            Require(parts.Length == 2 && parts[0].Equals(root, StringComparison.OrdinalIgnoreCase) &&
                System.Text.RegularExpressions.Regex.IsMatch(parts[1], "\\A[0-9a-f]{24}\\z"), "identity_invalid");
            return new(parts[0], parts[1]);
        }
        catch
        {
            // Only our retained helper handle, never a PID/name lookup.
            if (!helper.HasExited) { helper.Kill(); Require(helper.WaitForExit(5000), "identity_cleanup"); }
            throw;
        }
    }
    internal async Task<SmokeManifest> Describe()
    {
        CheckPath(Control); CheckPath(Root);
        var identity = await Identity(Root, Python, Launcher);
        string production = RepositoryIdentity.FindRoot(Path.GetDirectoryName(Launcher)!);
        var productionIdentity = await Identity(production, Python, Launcher);
        string udf = WebViewPreflight.ProfilePath(Local, identity.Id);
        Require(identity.Id != productionIdentity.Id, "production_identity_collision");
        var baseline = Inventory().Where(p => !p.Equals(udf, StringComparison.OrdinalIgnoreCase)).ToArray();
        var hashes = SourceHashes();
        string runtime = Microsoft.Web.WebView2.Core.CoreWebView2Environment.GetAvailableBrowserVersionString();
        WebViewPreflight.RequireRuntime(runtime);
        return new(1, identity.Root, identity.Id, udf, productionIdentity.Id, hashes, baseline, runtime);
    }
    internal SortedDictionary<string, string> SourceHashes()
    {
        var hashes = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (string asset in Assets)
        { string file = AssetPath(Web, asset); CheckPath(file); hashes.Add("web/" + asset, FileHash(file)); }
        foreach (var item in new[] { ("backend", Backend), ("runner", Runner), ("identity_authority", Launcher), ("python", Python),
            ("product", typeof(OwnedServer).Assembly.Location), ("webview_sdk", typeof(Microsoft.Web.WebView2.Core.CoreWebView2Environment).Assembly.Location) })
        { CheckPath(item.Item2); hashes.Add(item.Item1, FileHash(item.Item2)); }
        return hashes;
    }
    internal SmokeInspection Inspect(SmokeManifest expected)
    {
        CheckPath(Control); CheckPath(Root); CheckPath(expected.Udf);
        Require(expected.Root == Root && expected.Udf == WebViewPreflight.ProfilePath(Local, expected.Identity), "layout_mismatch");
        Require(expected.Identity != expected.ProductionIdentity, "production_identity_collision");
        Require(JsonSerializer.Serialize(expected.Hashes, Json) == JsonSerializer.Serialize(SourceHashes(), Json), "source_hash_mismatch");
        string fingerprint = Fingerprint(expected);
        if (!Directory.Exists(Control))
        {
            Require(!Directory.Exists(Root) && !Directory.Exists(expected.Udf) &&
                !Directory.Exists(Path.GetDirectoryName(expected.Udf)), "unapproved_directory");
            CheckInventory(expected.BaselineUdfs, Inventory(), expected.Udf, true);
            return new(expected, fingerprint, true);
        }
        CheckTree(Control);
        foreach (string file in new[] { ManifestPath, StatePath, LockPath }) Require(File.Exists(file), "incomplete_fixture");
        Require(!File.Exists(IntentPath) && !Directory.EnumerateFiles(Control, "*.pending").Any(), "unfinished_run");
        // Open existing only; no lock/state/fixture creation in this method.
        try { using var probe = new FileStream(LockPath, FileMode.Open, FileAccess.Read, FileShare.ReadWrite); }
        catch (IOException) { throw new SmokeError("fixture_busy"); }
        Require(Fingerprint(Read<SmokeManifest>(ManifestPath)) == fingerprint, "manifest_mismatch");
        var state = Read<SmokeRecord>(StatePath);
        RequireClean(state, fingerprint);
        CheckTree(expected.Udf);
        Require(state.UdfIdentity == SmokePathLease.DirectoryIdentity(expected.Udf) &&
            state.RootIdentity == SmokePathLease.DirectoryIdentity(Root), "directory_replaced");
        CheckInventory(expected.BaselineUdfs, Inventory(), expected.Udf, false);
        ValidateAssets(expected);
        return new(expected, fingerprint, false);
    }
    internal void ValidateAssets(SmokeManifest manifest)
    {
        foreach (string asset in Assets)
        { string path = AssetPath(Path.Combine(Root, "web"), asset); CheckPath(path); Require(FileHash(path) == manifest.Hashes["web/" + asset], "asset_mismatch"); }
        Require(!File.Exists(Path.Combine(Root, "must-not-be-read.json")), "data_must_not_exist");
    }
    internal FileStream Begin(SmokeInspection inspection, string? approval)
    {
        // Recheck immediately before mutation; a first-use token is exact plan approval,
        // not authentication or permission to overwrite unknown directories.
        Inspect(inspection.Manifest);
        Require(!inspection.FirstUse || approval == inspection.Fingerprint, "first_use_approval_required");
        if (inspection.FirstUse) Directory.CreateDirectory(Control);
        var lease = new FileStream(LockPath, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        try
        {
            using var anchors = SmokePathLease.Acquire(Control);
            if (inspection.FirstUse)
                Require(!Directory.EnumerateFileSystemEntries(Control).Any(p => p != LockPath), "initialization_race");
            else
            {
                Require(!File.Exists(IntentPath), "unfinished_run");
                var previous = Read<SmokeRecord>(StatePath);
                RequireClean(previous, inspection.Fingerprint);
            }
            string run = Guid.NewGuid().ToString("N");
            using (var intent = new FileStream(IntentPath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1, FileOptions.WriteThrough))
            { intent.Write(Encoding.UTF8.GetBytes(run)); intent.Flush(true); }
            AtomicWrite(StatePath, new SmokeRecord(inspection.Fingerprint, SmokeState.RUNNING, run, false, false, false, false));
            if (inspection.FirstUse)
            {
                AtomicWrite(ManifestPath, inspection.Manifest);
                Directory.CreateDirectory(Path.Combine(Root, "web", "components"));
                foreach (string asset in Assets) File.Copy(AssetPath(Web, asset), AssetPath(Path.Combine(Root, "web"), asset), false);
            }
            ValidateAssets(inspection.Manifest);
            return lease;
        }
        catch { lease.Dispose(); throw; } // intent/partial initialization deliberately remains fail-closed
    }
    internal bool SignalActive(SmokeManifest expected, bool stop)
    {
        CheckTree(Control);
        Require(expected.Root == Root && expected.Udf == WebViewPreflight.ProfilePath(Local, expected.Identity) &&
            expected.Identity != expected.ProductionIdentity, "layout_mismatch");
        string hash = Fingerprint(expected);
        Require(Fingerprint(Read<SmokeManifest>(ManifestPath)) == hash, "manifest_mismatch");
        var state = Read<SmokeRecord>(StatePath);
        Require(state.State == SmokeState.RUNNING && state.ManifestHash == hash &&
            File.ReadAllText(IntentPath) == state.Run, "not_active");
        // No new gate or event: Signal opens an existing event only.
        return InstanceControls.Signal(new(Root, expected.Identity), stop);
    }
    internal void Finish(SmokeInspection inspection, SmokeEvidence evidence)
    {
        var record = Read<SmokeRecord>(StatePath);
        Require(record.State == SmokeState.RUNNING && record.ManifestHash == inspection.Fingerprint &&
            File.ReadAllText(IntentPath) == record.Run, "run_identity_mismatch");
        bool valid = false;
        try { CheckInventory(inspection.Manifest.BaselineUdfs, Inventory(), inspection.Manifest.Udf, inspection.FirstUse); valid = true; }
        catch (SmokeError) { }
        bool clean = evidence.RuntimeEnded && evidence.ServerEnded && evidence.WindowDisposed && valid && Directory.Exists(inspection.Manifest.Udf) &&
            record.UdfIdentity == SmokePathLease.DirectoryIdentity(inspection.Manifest.Udf) && record.RootIdentity == SmokePathLease.DirectoryIdentity(Root);
        AtomicWrite(StatePath, record with { State = clean ? SmokeState.CLEAN : SmokeState.BLOCKED,
            RuntimeEnded = evidence.RuntimeEnded, ServerEnded = evidence.ServerEnded, WindowDisposed = evidence.WindowDisposed, InventoryValid = valid });
        if (clean) File.Delete(IntentPath); // only our fixed control file, never a UDF
        Require(clean, "cleanup_unconfirmed");
    }
    internal void BindDirectories(SmokeInspection inspection)
    {
        CheckPath(inspection.Manifest.Udf);
        if (inspection.FirstUse) Directory.CreateDirectory(inspection.Manifest.Udf);
        Require(Directory.Exists(inspection.Manifest.Udf), "udf_missing");
        CheckTree(inspection.Manifest.Udf);
        var record = Read<SmokeRecord>(StatePath);
        Require(record.State == SmokeState.RUNNING && record.ManifestHash == inspection.Fingerprint, "run_identity_mismatch");
        AtomicWrite(StatePath, record with { UdfIdentity = SmokePathLease.DirectoryIdentity(inspection.Manifest.Udf),
            RootIdentity = SmokePathLease.DirectoryIdentity(Root) });
    }
    internal ServerCommand Server(SmokeManifest manifest)
    {
        Require(JsonSerializer.Serialize(manifest.Hashes, Json) == JsonSerializer.Serialize(SourceHashes(), Json), "source_hash_mismatch");
        Require(manifest.Root == Root && manifest.Hashes["backend"] == FileHash(Backend), "backend_mismatch");
        Require(Path.GetFileName(Backend) == "synthetic_gui_server.py", "backend_not_synthetic");
        return new(Python, ["-I", "-S", "-B", "-u", Backend, Root, "--data", Path.Combine(Root, "must-not-be-read.json")], Root);
    }
}

// Retain verified ancestry handles without FILE_SHARE_DELETE while using paths.
// This guards namespace replacement, not a hostile process with the same user SID.
internal sealed class SmokePathLease : IDisposable
{
    private readonly List<KernelHandle> handles = [];
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandleW(KernelHandle file, StringBuilder path, uint size, uint flags);
    [StructLayout(LayoutKind.Sequential)]
    private struct FileInformation
    {
        internal uint Attributes, CreationLow, CreationHigh, AccessLow, AccessHigh, WriteLow, WriteHigh;
        internal uint Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
    }
    [DllImport("kernel32", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(KernelHandle handle, out FileInformation information);
    internal static string DirectoryIdentity(string path)
    {
        SmokeFixture.CheckPath(path);
        var security = new Native.Security { Length = Marshal.SizeOf<Native.Security>() };
        using var handle = Native.CreateFileW(path, 0x80, 3, ref security, 3, 0x02200000, 0);
        Native.Require(!handle.IsInvalid);
        Native.Require(GetFileInformationByHandle(handle, out var information));
        SmokeFixture.Require((information.Attributes & (uint)FileAttributes.ReparsePoint) == 0 &&
            (information.Attributes & (uint)FileAttributes.Directory) != 0, "handle_not_directory");
        return $"{information.Volume:x8}:{information.IndexHigh:x8}{information.IndexLow:x8}";
    }
    internal static SmokePathLease Acquire(string path)
    {
        var lease = new SmokePathLease();
        try
        {
            SmokeFixture.CheckPath(path);
            for (var part = new DirectoryInfo(path); part != null; part = part.Parent)
            {
                if (!part.Exists) continue;
                var security = new Native.Security { Length = Marshal.SizeOf<Native.Security>() };
                var handle = Native.CreateFileW(part.FullName, 0x81, 3, ref security, 3, 0x02200000, 0); // list/read attributes; no share-delete
                Native.Require(!handle.IsInvalid); lease.handles.Add(handle);
                Native.Require(GetFileInformationByHandle(handle, out var information));
                SmokeFixture.Require((information.Attributes & (uint)FileAttributes.ReparsePoint) == 0 &&
                    (information.Attributes & (uint)FileAttributes.Directory) != 0, "handle_not_directory");
                SmokeFixture.CheckPath(part.FullName);
                var final = new StringBuilder(32768);
                uint size = GetFinalPathNameByHandleW(handle, final, (uint)final.Capacity, 0);
                SmokeFixture.Require(size > 0 && size < final.Capacity && final.ToString().StartsWith(@"\\?\", StringComparison.Ordinal) &&
                    Path.GetFullPath(final.ToString()[4..]).Equals(Path.GetFullPath(part.FullName), StringComparison.OrdinalIgnoreCase), "path_changed");
            }
            return lease;
        }
        catch { lease.Dispose(); throw; }
    }
    public void Dispose() { foreach (var handle in handles) handle.Dispose(); handles.Clear(); }
}
