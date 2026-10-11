using System.Text.Json;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal static class SmokeFixtureTests
{
    internal static List<(string Name, Func<Task> Run)> Cases(string python, string launcher) =>
    [
        ("smoke_identity_python_authority_repeat_no_root_creation", async () =>
        {
            using var temp = new SmokeTemp();
            string root = Path.Combine(temp.Root, "日本語 fixed missing");
            var first = await SmokeFixture.Identity(root, python, launcher);
            var second = await SmokeFixture.Identity(root, python, launcher);
            Program.Check(first == second && !Directory.Exists(root));
            string expected = WebViewPreflight.ProfilePath(temp.Root, first.Id);
            Program.Check(expected == WebViewPreflight.ProfilePath(temp.Root, second.Id));
        }),
        Case("smoke_readonly_uninitialized_no_files_created", f =>
        {
            string before = f.Snapshot(); var result = f.Inspect();
            Program.Check(result.FirstUse && f.Snapshot() == before && !Directory.Exists(f.Fixture.Control));
        }),
        Case("smoke_first_use_requires_exact_approval", f =>
        {
            Reject(() => f.Fixture.Begin(f.Inspect(), null));
            Reject(() => f.Fixture.Begin(f.Inspect(), new string('0', 64)));
            Program.Check(!Directory.Exists(f.Fixture.Control));
        }),
        Case("smoke_first_allocation_one_then_reuse_zero", f =>
        {
            Reject(() => SmokeFixture.CheckInventory([], [f.Manifest.Udf, "unapproved-second-udf"], f.Manifest.Udf, true));
            f.Clean(); var initial = f.Fixture.Inventory(); var inspection = f.Inspect();
            Program.Check(initial.Length == 1 && !inspection.FirstUse);
            using (f.Fixture.Begin(inspection, null))
            { f.Fixture.BindDirectories(inspection); f.Fixture.Finish(inspection, new(true, true, true)); }
            Program.Check(initial.SequenceEqual(f.Fixture.Inventory(), StringComparer.OrdinalIgnoreCase));
            Program.Check(!f.Inspect().FirstUse);
        }),
        Case("smoke_manifest_mismatch_rejected", f =>
        {
            f.Clean(); File.WriteAllText(f.Fixture.ManifestPath, JsonSerializer.Serialize(f.Manifest with { Version = 2 }));
            Reject(() => f.Inspect());
        }),
        Case("smoke_previous_running_rejected", f =>
        {
            var inspection = f.Inspect(); using (f.Fixture.Begin(inspection, inspection.Fingerprint)) { }
            Program.Check(File.Exists(f.Fixture.IntentPath)); Reject(() => f.Inspect());
        }),
        Case("smoke_runtime_unconfirmed_blocks_clean", f => f.Failed(new(false, true, true))),
        Case("smoke_server_unconfirmed_blocks_clean", f => f.Failed(new(true, false, true))),
        Case("smoke_window_unconfirmed_blocks_clean", f => f.Failed(new(true, true, false))),
        Case("smoke_same_fixture_exclusive_lease", f =>
        {
            var inspection = f.Inspect(); using var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            Reject(() => f.Inspect());
            bool locked = false;
            try { using var second = new FileStream(f.Fixture.LockPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None); }
            catch (IOException) { locked = true; }
            Program.Check(locked);
        }),
        Case("smoke_cross_process_exclusive_lease", f =>
        {
            var inspection = f.Inspect(); using var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            using var child = TestProcess.Start(Environment.ProcessPath!,
                [typeof(Program).Assembly.Location, "--smoke-lock-probe", f.Fixture.LockPath], f.Temp.Root, []);
            Program.Check(child.Wait(5000));
            Program.Check(child.Output.ReadToEnd().Trim() == "SMOKE_LOCK_DENIED");
        }),
        Case("smoke_active_named_ipc_same_identity_no_server", f =>
        {
            var inspection = f.Inspect(); using var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            using var controls = new InstanceControls(new(f.Fixture.Root, f.Manifest.Identity));
            Program.Check(controls.Acquire());
            Program.Check(f.Fixture.SignalActive(f.Manifest, false) && controls.ConsumeShow());
            Program.Check(f.Fixture.SignalActive(f.Manifest, true) && controls.StopRequested && !controls.ConsumeShow());
            Reject(() => f.Fixture.SignalActive(f.Manifest with { ProductionIdentity = f.Manifest.Identity }, true));
        }),
        Case("smoke_inactive_ipc_does_not_create_control_files", f =>
        {
            try { f.Fixture.SignalActive(f.Manifest, true); } catch (SmokeError) { }
            Program.Check(!Directory.Exists(f.Fixture.Control));
        }),
        Case("smoke_path_traversal_and_ads_rejected", f =>
        {
            Reject(() => SmokeFixture.CheckPath(Path.Combine(f.Temp.Root, "child", "..", "escape")));
            Reject(() => SmokeFixture.CheckPath(Path.Combine(f.Temp.Root, "file:stream")));
            Reject(() => SmokeFixture.CheckPath(@"\\server\share\fixture"));
        }),
        Case("smoke_real_junction_rejected", f =>
        {
            string junction = Path.Combine(f.Temp.Root, "junction");
            try { TestLinks.Junction(junction, f.Inputs); Reject(() => SmokeFixture.CheckPath(junction)); }
            finally { if (Directory.Exists(junction)) Directory.Delete(junction); } // exact link, not target
        }),
        Case("smoke_existing_os_symlink_metadata_rejected", _ =>
        {
            string link = Path.Combine(Path.GetPathRoot(Environment.SystemDirectory)!, "Users", "All Users");
            Program.Check(new DirectoryInfo(link).LinkTarget != null);
            Reject(() => SmokeFixture.CheckPath(link)); // metadata only, no target traversal
        }),
        Case("smoke_profile_identity_layout_collision_rejected", f =>
        { Reject(() => f.Fixture.Inspect(f.Manifest with { Udf = Path.Combine(f.Temp.Root, "other") })); }),
        Case("smoke_production_identity_collision_rejected", f =>
        { Reject(() => f.Fixture.Inspect(f.Manifest with { ProductionIdentity = f.Manifest.Identity })); }),
        Case("smoke_existing_unapproved_udf_rejected", f =>
        { Directory.CreateDirectory(f.Manifest.Udf); Reject(() => f.Inspect()); }),
        Case("smoke_existing_unapproved_udf_parent_rejected", f =>
        { Directory.CreateDirectory(Path.GetDirectoryName(f.Manifest.Udf)!); Reject(() => f.Inspect()); }),
        Case("smoke_unapproved_control_directory_rejected", f =>
        { Directory.CreateDirectory(f.Fixture.Control); Reject(() => f.Inspect()); }),
        Case("smoke_unexpected_udf_added_rejected", f =>
        {
            f.Clean(); Directory.CreateDirectory(Path.Combine(f.Fixture.Local, "J1AI", "Dashboard", new string('c', 24), "webview2-profile"));
            Reject(() => f.Inspect());
        }),
        Case("smoke_baseline_udf_removed_rejected", f =>
        { Reject(() => SmokeFixture.CheckInventory(["existing"], [], f.Manifest.Udf, true)); }),
        Case("smoke_backend_hash_and_name_rejected", f =>
        {
            Reject(() => f.Fixture.Server(f.Manifest with { Root = f.Temp.Root }));
            string badBackend = Path.Combine(f.Inputs, "serve_dashboard.py"); File.WriteAllText(badBackend, "synthetic-only-not-executed");
            var other = new SmokeFixture(f.Fixture.Local, f.Fixture.Python, f.Fixture.Launcher, f.Fixture.Web, badBackend, f.Fixture.Runner);
            Reject(() => other.Server(f.Manifest with { Hashes = other.SourceHashes() }));
            File.AppendAllText(f.Fixture.Backend, "changed"); Reject(() => f.Fixture.Server(f.Manifest));
        }),
        Case("smoke_backend_exact_no_product_or_data_read_command", f =>
        {
            var command = f.Fixture.Server(f.Manifest);
            Program.Check(command.Arguments.SequenceEqual(new[] { "-I", "-S", "-B", "-u", f.Fixture.Backend, f.Fixture.Root,
                "--data", Path.Combine(f.Fixture.Root, "must-not-be-read.json") }));
            Program.Check(!command.Arguments.Contains("scripts.serve_dashboard"));
        }),
        Case("smoke_partial_state_write_rejected", f =>
        { f.Clean(); File.WriteAllText(f.Fixture.StatePath + ".pending", "partial"); Reject(() => f.Inspect()); }),
        Case("smoke_clean_state_with_intent_rejected", f =>
        { f.Clean(); File.WriteAllText(f.Fixture.IntentPath, "unfinished"); Reject(() => f.Inspect()); }),
        Case("smoke_malformed_duplicate_state_rejected", f =>
        { f.Clean(); File.WriteAllText(f.Fixture.StatePath, "{\"State\":1,\"State\":2}"); Reject(() => f.Inspect()); }),
        Case("smoke_asset_change_rejected", f =>
        { f.Clean(); File.AppendAllText(Path.Combine(f.Fixture.Root, "web", "app.js"), "changed"); Reject(() => f.Inspect()); }),
        Case("smoke_source_provenance_change_rejected", f =>
        { File.AppendAllText(f.Fixture.Runner, "changed"); Reject(() => f.Inspect()); Program.Check(!Directory.Exists(f.Fixture.Control)); }),
        Case("smoke_runtime_contract_change_rejected", f =>
        { f.Clean(); Reject(() => f.Fixture.Inspect(f.Manifest with { Runtime = "different" })); }),
        Case("smoke_readonly_clean_no_mutation", f =>
        { f.Clean(); string before = f.Snapshot(); Program.Check(!f.Inspect().FirstUse && f.Snapshot() == before); }),
        Case("smoke_directory_lease_blocks_rename", f =>
        {
            using var lease = SmokePathLease.Acquire(f.Inputs); bool denied = false;
            try { Directory.Move(f.Inputs, f.Inputs + "-moved"); } catch (IOException) { denied = true; }
            Program.Check(denied && Directory.Exists(f.Inputs));
        }),
        Case("smoke_directory_identity_replacement_rejected", f =>
        {
            f.Clean(); string old = f.Manifest.Udf + "-old";
            Directory.Move(f.Manifest.Udf, old); Directory.CreateDirectory(f.Manifest.Udf);
            Reject(() => f.Inspect());
        }),
        Case("smoke_negative_control_detects_all_missing_evidence", _ =>
        {
            var good = new SmokeRecord("hash", SmokeState.CLEAN, "run", true, true, true, true, "udf", "root");
            SmokeFixture.RequireClean(good, "hash");
            foreach (var bad in new[] { good with { RuntimeEnded = false }, good with { ServerEnded = false },
                good with { WindowDisposed = false }, good with { InventoryValid = false }, good with { State = SmokeState.RUNNING } })
                Reject(() => SmokeFixture.RequireClean(bad, "hash"));
        }),
        Case("smoke_parent_disconnect_before_acquire_not_lost", _ =>
        {
            var controls = new SmokeParentControls(new FakeControls());
            controls.Disconnected(); Program.Check(controls.Acquire() && controls.StopRequested);
        }),
        Case("smoke_parent_disconnect_prioritizes_stop_over_show", _ =>
        {
            var controls = new SmokeParentControls(new FakeControls { Shows = true });
            controls.Disconnected(); Program.Check(controls.StopRequested && !controls.ConsumeShow());
        }),
        ("smoke_supervisor_real_child_normal_exit", () => Supervisor(false)),
        ("smoke_supervisor_real_child_deadline_no_kill", () => Supervisor(true)),
    ];
    private static async Task Supervisor(bool timeout)
    {
        using var child = new System.Diagnostics.Process { StartInfo = new(Environment.ProcessPath!)
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true } };
        child.StartInfo.ArgumentList.Add(typeof(Program).Assembly.Location);
        child.StartInfo.ArgumentList.Add("--smoke-supervisor-probe");
        Program.Check(child.Start());
        int requests = 0;
        if (!timeout) await child.StandardInput.WriteLineAsync("stop");
        int result = await SmokeRunner.Watch(child, async () =>
            { requests++; await child.StandardInput.WriteLineAsync("stop"); },
            timeout ? TimeSpan.FromMilliseconds(100) : TimeSpan.FromSeconds(5), TimeSpan.FromSeconds(5));
        await child.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
        Program.Check(child.ExitCode == 0 && requests == (timeout ? 1 : 0) && result == (timeout ? 1 : 0));
    }
    private static (string, Func<Task>) Case(string name, Action<FakeFixture> check) =>
        (name, () => { using var fixture = new FakeFixture(); check(fixture); return Task.CompletedTask; });
    internal static void Reject(Action operation)
    {
        try { operation(); } catch (SmokeError) { return; }
        throw new InvalidOperationException("unsafe_operation_accepted");
    }
    private sealed class SmokeTemp : IDisposable
    {
        private static bool cleanupBlocked;
        private readonly TempRepository inner;
        internal string Root => inner.Root;
        internal SmokeTemp()
        {
            SmokeFixture.Require(!cleanupBlocked, "temporary_cleanup_blocked");
            inner = new TempRepository();
        }
        public void Dispose()
        {
            try { inner.Dispose(); }
            catch { cleanupBlocked = true; Console.WriteLine("SMOKE_TEMP_RETAINED " + Root); throw; }
        }
    }
    private sealed class FakeFixture : IDisposable
    {
        internal readonly SmokeTemp Temp;
        internal readonly string Inputs;
        internal readonly SmokeFixture Fixture;
        internal readonly SmokeManifest Manifest;
        internal FakeFixture()
        {
            Temp = new SmokeTemp();
            try
            {
                Inputs = Path.Combine(Temp.Root, "inputs"); Directory.CreateDirectory(Path.Combine(Inputs, "web", "components"));
                foreach (string asset in SmokeFixture.Assets) File.WriteAllText(Path.Combine(Inputs, "web", asset), "synthetic-only-" + asset);
                string backend = Path.Combine(Inputs, "synthetic_gui_server.py"); File.WriteAllText(backend, "not executed");
                Fixture = new(Temp.Root, Path.Combine(Inputs, "unused-python.exe"), Path.Combine(Inputs, "unused-launcher.py"),
                    Path.Combine(Inputs, "web"), backend, Path.Combine(Inputs, "unused-runner.dll"));
                foreach (string path in new[] { Fixture.Python, Fixture.Launcher, Fixture.Runner }) File.WriteAllText(path, "synthetic-only-not-executed");
                var hashes = Fixture.SourceHashes();
                // Constant fake identity is ONLY modelled test data; actual authority is exercised above.
                Manifest = new(1, Fixture.Root, new string('a', 24), WebViewPreflight.ProfilePath(Temp.Root, new string('a', 24)), new string('b', 24), hashes, []);
            }
            catch { Dispose(); throw; }
        }
        internal SmokeInspection Inspect() => Fixture.Inspect(Manifest);
        internal void Clean()
        {
            var inspection = Inspect(); using var lease = Fixture.Begin(inspection, inspection.Fingerprint);
            Fixture.BindDirectories(inspection); Fixture.Finish(inspection, new(true, true, true));
        }
        internal void Failed(SmokeEvidence evidence)
        {
            var inspection = Inspect();
            using (Fixture.Begin(inspection, inspection.Fingerprint))
            { Fixture.BindDirectories(inspection); Reject(() => Fixture.Finish(inspection, evidence)); }
            Program.Check(File.Exists(Fixture.IntentPath)); Reject(() => Inspect());
            using var state = JsonDocument.Parse(File.ReadAllText(Fixture.StatePath));
            Program.Check(state.RootElement.GetProperty("State").GetInt32() == (int)SmokeState.BLOCKED);
        }
        internal string Snapshot() => string.Join("|", Directory.EnumerateFiles(Temp.Root, "*", SearchOption.AllDirectories)
            .Order(StringComparer.Ordinal).Select(p => p + ":" + SmokeFixture.FileHash(p)));
        public void Dispose() => Temp.Dispose();
    }
}
