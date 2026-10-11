using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace J1AI.SmokeNetworkObserver;

public sealed record ApprovalPlan(int Version, string Identity, string ManifestSha, string InitialStateSha,
    IdentityContract Contract, string EvidenceDirectory, SortedDictionary<string, string> FileHashes,
    string ObserverHash, string[] UdfInventory, int PeriodMs = 250, int MaximumGapMs = 1500, int MaximumSessionSeconds = 360);
internal sealed record FixtureState(string ManifestHash, int State, string Run, bool RuntimeEnded,
    bool ServerEnded, bool WindowDisposed, bool InventoryValid, string UdfIdentity, string RootIdentity);

public static class Approval
{
    public const string ManifestSha = "ce8e230e4deb35b67298f0dcdfecb421cf282125b7ae509de794df91b599cf67";
    public const string InitialStateSha = "f7f87885a0b5f66f65e065295bc60a9c989a63ce654b5502dac014a36e1d04a7";
    public static readonly JsonSerializerOptions Json = new() { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow };
    public static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    public static string FileHash(string path) => Hash(File.ReadAllBytes(path));
    public static void Require(bool condition, string code) { if (!condition) throw new InvalidDataException(code); }
    public static T Read<T>(string path)
    {
        CheckPath(path); Require(new FileInfo(path).Length <= 1024 * 1024, "metadata_limit");
        byte[] bytes = File.ReadAllBytes(path);
        using var doc = JsonDocument.Parse(bytes);
        void Unique(JsonElement e)
        {
            if (e.ValueKind == JsonValueKind.Object)
            {
                var names = new HashSet<string>();
                foreach (var p in e.EnumerateObject()) { Require(names.Add(p.Name), "duplicate_metadata"); Unique(p.Value); }
            }
            else if (e.ValueKind == JsonValueKind.Array) foreach (var child in e.EnumerateArray()) Unique(child);
        }
        Unique(doc.RootElement);
        return JsonSerializer.Deserialize<T>(bytes, Json) ?? throw new InvalidDataException("metadata_null");
    }
    public static void CheckPath(string path)
    {
        CheckCanonical(path);
        for (var info = new DirectoryInfo(path); info != null; info = info.Parent)
        {
            Require(info.LinkTarget == null, "path_link");
            if (Directory.Exists(info.FullName) || File.Exists(info.FullName))
                Require((File.GetAttributes(info.FullName) & FileAttributes.ReparsePoint) == 0, "path_reparse");
        }
    }
    internal static void CheckCanonical(string path)
    {
        Require(Path.IsPathFullyQualified(path) && !path.StartsWith(@"\\", StringComparison.Ordinal) &&
            path == Path.GetFullPath(path) && path.IndexOf(':', 2) < 0, "path_not_canonical_local");
        Require(!path.Contains('/') && path.Split('\\').All(part => !part.EndsWith(' ') && !part.EndsWith('.')),
            "path_ambiguous_spelling");
    }
    public static string Control => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "J1AI", "Smoke", "dashboard-v1");
    public static string[] Inventory()
    {
        string root = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "J1AI", "Dashboard");
        CheckPath(root);
        return Directory.EnumerateDirectories(root).Select(d => Path.Combine(d, "webview2-profile"))
            .Where(Directory.Exists).Order(StringComparer.OrdinalIgnoreCase).ToArray();
    }
    public static ApprovalPlan Describe(string repo, string evidence)
    {
        string root = Path.Combine(Control, "fixtures", "J1AI-native-test-dashboard-smoke-v1");
        string udf = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "J1AI", "Dashboard", Observation.Identity, "webview2-profile");
        string output = Path.Combine(repo, "windows", "J1AI.DashboardHost.Tests", "bin", "Release", "net10.0-windows");
        string runner = Path.Combine(output, "J1AI.DashboardHost.Tests.dll");
        string dotnet = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "J1AI", "Toolchains", "dotnet", "dotnet.exe");
        string python = Path.Combine(repo, ".venv", "Scripts", "python.exe");
        string[] executable = File.ReadAllLines(Path.Combine(repo, ".venv", "pyvenv.cfg"))
            .Where(s => s.StartsWith("executable = ", StringComparison.Ordinal)).Select(s => s[13..]).ToArray();
        Require(executable.Length == 1, "python_executable_unknown");
        string runtime = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86), "Microsoft", "EdgeWebView", "Application", "154.0.4258.62", "msedgewebview2.exe");
        var c = new IdentityContract(udf, root, runner, Path.Combine(output, "synthetic_gui_server.py"), python,
            dotnet, Path.ChangeExtension(runner, ".exe"), executable[0], runtime);
        var files = new SortedDictionary<string, string>(StringComparer.Ordinal);
        foreach (string path in new[] { c.Runner, c.Backend, c.PythonArgument, c.PythonExecutable, c.Dotnet, c.RunnerExe, c.RuntimeExecutable,
            Path.Combine(output, "J1AI.DashboardHost.dll"), Path.Combine(output, "Microsoft.Web.WebView2.Core.dll"), Path.Combine(repo, "scripts", "launch_dashboard.py") })
        { CheckPath(path); files.Add(path, FileHash(path)); }
        var plan = new ApprovalPlan(1, Observation.Identity, ManifestSha, InitialStateSha, c, evidence,
            files, FileHash(typeof(Approval).Assembly.Location), Inventory());
        Validate(plan, true); return plan;
    }
    public static void Validate(ApprovalPlan p, bool initial)
    {
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        Require(p.Version == 1 && p.Identity == Observation.Identity && p.ManifestSha == ManifestSha &&
            p.InitialStateSha == InitialStateSha && p.PeriodMs == 250 && p.MaximumGapMs == 1500 && p.MaximumSessionSeconds == 360,
            "plan_contract");
        Require(p.Contract.Root == Path.Combine(Control, "fixtures", "J1AI-native-test-dashboard-smoke-v1") &&
            p.Contract.Udf == Path.Combine(local, "J1AI", "Dashboard", Observation.Identity, "webview2-profile"), "fixed_paths");
        string diagnostics = Path.Combine(local, "J1AI", "Diagnostics", "NetworkObserver");
        CheckPath(p.EvidenceDirectory);
        Require(Path.GetDirectoryName(p.EvidenceDirectory) == diagnostics &&
            System.Text.RegularExpressions.Regex.IsMatch(Path.GetFileName(p.EvidenceDirectory), "\\A[a-zA-Z0-9_-]{1,64}\\z"), "evidence_outside_approval_area");
        if (initial) Require(!Directory.Exists(p.EvidenceDirectory) && !File.Exists(p.EvidenceDirectory), "evidence_already_exists");
        CheckPath(Control); CheckPath(p.Contract.Root); CheckPath(p.Contract.Udf);
        string manifestPath = Path.Combine(Control, "fixture-manifest.json");
        Require(FileHash(manifestPath) == ManifestSha, "manifest_changed");
        using var manifest = JsonDocument.Parse(File.ReadAllBytes(manifestPath));
        var m = manifest.RootElement;
        Require(m.GetProperty("Identity").GetString() == p.Identity && m.GetProperty("Udf").GetString() == p.Contract.Udf &&
            m.GetProperty("Root").GetString() == p.Contract.Root && m.GetProperty("ProductionIdentity").GetString() != p.Identity,
            "manifest_identity");
        foreach (var item in p.FileHashes) { CheckPath(item.Key); Require(FileHash(item.Key) == item.Value, "approved_binary_changed"); }
        string output = Path.GetDirectoryName(p.Contract.Runner)!;
        string repo = Path.GetFullPath(Path.Combine(output, "..", "..", "..", "..", ".."));
        Require(Directory.Exists(Path.Combine(repo, ".git")), "runner_repository_unknown");
        Require(output == Path.Combine(repo, "windows", "J1AI.DashboardHost.Tests", "bin", "Release", "net10.0-windows") &&
            p.Contract.Runner == Path.Combine(output, "J1AI.DashboardHost.Tests.dll") &&
            p.Contract.RunnerExe == Path.Combine(output, "J1AI.DashboardHost.Tests.exe") &&
            p.Contract.Backend == Path.Combine(output, "synthetic_gui_server.py") &&
            p.Contract.PythonArgument == Path.Combine(repo, ".venv", "Scripts", "python.exe") &&
            p.Contract.Dotnet == Path.Combine(local, "J1AI", "Toolchains", "dotnet", "dotnet.exe") &&
            p.Contract.RuntimeExecutable == Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
                "Microsoft", "EdgeWebView", "Application", "154.0.4258.62", "msedgewebview2.exe"), "executable_layout_mismatch");
        string[] python = File.ReadAllLines(Path.Combine(repo, ".venv", "pyvenv.cfg"))
            .Where(s => s.StartsWith("executable = ", StringComparison.Ordinal)).Select(s => s[13..]).ToArray();
        Require(python.Length == 1 && python[0] == p.Contract.PythonExecutable, "interpreter_layout_mismatch");
        string[] required = [p.Contract.Runner, p.Contract.RunnerExe, p.Contract.Backend, p.Contract.PythonArgument,
            p.Contract.PythonExecutable, p.Contract.Dotnet, p.Contract.RuntimeExecutable,
            Path.Combine(output, "J1AI.DashboardHost.dll"), Path.Combine(output, "Microsoft.Web.WebView2.Core.dll"),
            Path.Combine(repo, "scripts", "launch_dashboard.py")];
        Require(p.FileHashes.Count == required.Length && required.All(p.FileHashes.ContainsKey), "required_hashes_missing_or_extra");
        Require(p.ObserverHash == FileHash(typeof(Approval).Assembly.Location), "observer_changed");
        var frozen = m.GetProperty("Hashes");
        Require(FileHash(p.Contract.Runner) == frozen.GetProperty("runner").GetString() &&
            FileHash(p.Contract.Backend) == frozen.GetProperty("backend").GetString() &&
            FileHash(p.Contract.PythonArgument) == frozen.GetProperty("python").GetString() &&
            FileHash(Path.Combine(output, "J1AI.DashboardHost.dll")) == frozen.GetProperty("product").GetString() &&
            FileHash(Path.Combine(output, "Microsoft.Web.WebView2.Core.dll")) == frozen.GetProperty("webview_sdk").GetString() &&
            FileHash(Path.Combine(repo, "scripts", "launch_dashboard.py")) == frozen.GetProperty("identity_authority").GetString(), "frozen_source_changed");
        foreach (var property in frozen.EnumerateObject().Where(prop => prop.Name.StartsWith("web/", StringComparison.Ordinal)))
        {
            string asset = Path.Combine(p.Contract.Root, property.Name.Replace('/', Path.DirectorySeparatorChar));
            CheckPath(asset); Require(FileHash(asset) == property.Value.GetString(), "fixture_asset_changed");
        }
        Require(Inventory().SequenceEqual(p.UdfInventory, StringComparer.OrdinalIgnoreCase) && p.UdfInventory.Length == 32,
            "udf_inventory_changed");
        if (initial)
        {
            Require(FileHash(Path.Combine(Control, "run-state.json")) == InitialStateSha &&
                !File.Exists(Path.Combine(Control, "run.intent")) && !Directory.EnumerateFiles(Control, "*.pending").Any(), "initial_state_changed");
        }
        var state = Read<FixtureState>(Path.Combine(Control, "run-state.json"));
        Require(state.ManifestHash == ManifestSha && state.UdfIdentity == "a223b184:0171000000009673" &&
            state.RootIdentity == "a223b184:0357000000008b58" && state.Run.Length == 32, "state_identity_mismatch");
        if (initial) Require(state.State == 1 && state.RuntimeEnded && state.ServerEnded && state.WindowDisposed && state.InventoryValid, "state_not_clean");
    }
}
