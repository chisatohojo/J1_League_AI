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
            using (var lease = f.Fixture.Begin(inspection, null))
            { f.Fixture.BindDirectories(inspection, lease); f.Fixture.Finish(inspection, new(true, true, true), lease); }
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
        Case("smoke_inspect_then_udf_replace_rejected_before_running", f =>
        {
            f.Clean(); var inspection = f.Inspect();
            f.ReplaceUdf();
            Expect("directory_replaced", () => f.Fixture.Begin(inspection, null));
            Program.Check(f.State().State == SmokeState.CLEAN && f.State().UdfIdentity == inspection.UdfIdentity && !File.Exists(f.Fixture.IntentPath));
            Expect("directory_replaced", () => f.Inspect());
        }),
        Case("smoke_old_review_begin_bind_replacement_never_clean", f =>
        {
            f.Clean(); var inspection = f.Inspect();
            var lease = f.Fixture.Begin(inspection, null);
            try
            {
                Program.Check(f.State().UdfIdentity == inspection.UdfIdentity && f.State().RootIdentity == inspection.RootIdentity);
                f.ReplaceUdf();
                Expect("directory_replaced", () => f.Fixture.BindDirectories(inspection, lease));
                Program.Check(lease.Profile!.Identity != inspection.UdfIdentity);
                Expect("directory_lease_unbound", () => f.Fixture.Finish(inspection, new(true, true, true), lease));
                Program.Check(f.State().State == SmokeState.RUNNING && f.State().UdfIdentity == inspection.UdfIdentity && File.Exists(f.Fixture.IntentPath));
            }
            finally { lease.Dispose(); }
            Program.Check(lease.Root!.Closed && lease.Profile!.Closed);
            Directory.Move(f.Manifest.Udf, f.Manifest.Udf + "-replacement-released");
            Expect("unfinished_run", () => f.Inspect());
        }),
        Case("smoke_inspect_then_root_replace_rejected", f =>
        {
            f.Clean(); var inspection = f.Inspect();
            Directory.Move(f.Fixture.Root, f.Fixture.Root + "-old"); Directory.CreateDirectory(f.Fixture.Root);
            Expect("directory_replaced", () => f.Fixture.Begin(inspection, null));
            Program.Check(f.State().RootIdentity == inspection.RootIdentity && f.State().State == SmokeState.CLEAN);
        }),
        Case("smoke_bound_udf_root_ancestry_rename_delete_denied", f =>
        {
            var inspection = f.Inspect(); var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            try
            {
                f.Fixture.BindDirectories(inspection, lease);
                foreach (string path in new[] { f.Manifest.Udf, f.Fixture.Root, Path.GetDirectoryName(f.Manifest.Udf)!, f.Fixture.Control })
                {
                    SharingDenied(() => Directory.Move(path, path + "-moved"));
                    var security = new Native.Security { Length = System.Runtime.InteropServices.Marshal.SizeOf<Native.Security>() };
                    using var deletion = Native.CreateFileW(path, 0x10000, 7, ref security, 3, 0x02200000, 0);
                    Program.Check(deletion.IsInvalid && System.Runtime.InteropServices.Marshal.GetLastWin32Error() == 32);
                }
                SharingDenied(() => Directory.Delete(f.Manifest.Udf));
                lease.ValidateBound();
                f.Fixture.Finish(inspection, new(true, true, true), lease);
                // CLEAN does not release the handles before the owner finishes.
                SharingDenied(() => Directory.Move(f.Manifest.Udf, f.Manifest.Udf + "-early"));
            }
            finally { lease.Dispose(); }
            Program.Check(lease.Root!.Closed && lease.Profile!.Closed);
            using (var reopened = new FileStream(f.Fixture.LockPath, FileMode.Open, FileAccess.ReadWrite, FileShare.None)) { }
            Directory.Move(f.Manifest.Udf, f.Manifest.Udf + "-released");
        }),
        Case("smoke_bind_reparse_replacement_rejected", f =>
        {
            f.Clean(); var inspection = f.Inspect();
            using var lease = f.Fixture.Begin(inspection, null);
            Directory.Move(f.Manifest.Udf, f.Manifest.Udf + "-old");
            try
            {
                TestLinks.Junction(f.Manifest.Udf, f.Inputs);
                Expect("path_reparse", () => f.Fixture.BindDirectories(inspection, lease));
                Program.Check(f.State().State == SmokeState.RUNNING && f.State().UdfIdentity == inspection.UdfIdentity && !lease.Bound);
                Expect("directory_lease_unbound", () => f.Fixture.Finish(inspection, new(true, true, true), lease));
            }
            finally { if (Directory.Exists(f.Manifest.Udf)) Directory.Delete(f.Manifest.Udf); } // exact isolated junction only
        }),
        Case("smoke_inspection_identity_cannot_be_overridden", f =>
        {
            f.Clean(); var inspection = f.Inspect();
            Expect("inspection_changed", () => f.Fixture.Begin(inspection with { UdfIdentity = "unapproved" }, null));
            Program.Check(f.State().State == SmokeState.CLEAN && !File.Exists(f.Fixture.IntentPath));
        }),
        Case("smoke_missing_directory_handle_fails_closed", f =>
        {
            Expect("directory_handle_failed", () => SmokePathLease.Acquire(Path.Combine(f.Temp.Root, "missing")));
            Program.Check(!Directory.Exists(f.Fixture.Control));
        }),
        Case("smoke_bind_native_handle_sharing_failure_retains_state", f =>
        {
            f.Clean(); var inspection = f.Inspect();
            using var lease = f.Fixture.Begin(inspection, null);
            var security = new Native.Security { Length = System.Runtime.InteropServices.Marshal.SizeOf<Native.Security>() };
            // FILE_READ_ATTRIBUTES alone does not participate in data-sharing
            // conflicts. Include FILE_LIST_DIRECTORY for a real OS denial.
            using (var exclusive = Native.CreateFileW(f.Manifest.Udf, 0x81, 0, ref security, 3, 0x02200000, 0))
            {
                Program.Check(!exclusive.IsInvalid);
                Expect("directory_handle_failed", () => f.Fixture.BindDirectories(inspection, lease));
            }
            Program.Check(lease.Profile == null && !lease.Bound && f.State().State == SmokeState.RUNNING && f.State().UdfIdentity == inspection.UdfIdentity);
            Expect("directory_lease_unbound", () => f.Fixture.Finish(inspection, new(true, true, true), lease));
        }),
        Case("smoke_bound_identity_mismatch_and_closed_handle_rejected", f =>
        {
            var inspection = f.Inspect(); using var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            f.Fixture.BindDirectories(inspection, lease);
            Expect("directory_replaced", () => lease.Profile!.RequireIdentity("wrong-volume-file-id"));
            lease.Profile!.Dispose();
            Expect("directory_lease_closed", () => f.Fixture.Finish(inspection, new(true, true, true), lease));
            Program.Check(f.State().State == SmokeState.RUNNING && File.Exists(f.Fixture.IntentPath));
        }),
        Case("smoke_first_use_does_not_adopt_directory_created_after_begin", f =>
        {
            var inspection = f.Inspect(); using var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            Directory.CreateDirectory(f.Manifest.Udf);
            Expect("unapproved_directory", () => f.Fixture.BindDirectories(inspection, lease));
            Program.Check(f.State().State == SmokeState.RUNNING && f.State().UdfIdentity == "" && !lease.Bound);
        }),
        Case("smoke_directory_pin_allows_read_write_child_files", f =>
        {
            var inspection = f.Inspect(); using var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            f.Fixture.BindDirectories(inspection, lease);
            var security = new Native.Security { Length = System.Runtime.InteropServices.Marshal.SizeOf<Native.Security>() };
            using var peer = Native.CreateFileW(f.Manifest.Udf, 0x81, 7, ref security, 3, 0x02200000, 0);
            Program.Check(!peer.IsInvalid);
            string file = Path.Combine(f.Manifest.Udf, "synthetic-write-probe");
            File.WriteAllText(file, "synthetic-only"); Program.Check(File.ReadAllText(file) == "synthetic-only"); File.Delete(file);
            lease.ValidateBound(); f.Fixture.Finish(inspection, new(true, true, true), lease);
        }),
        Case("smoke_cleanup_failure_keeps_pins_until_owner_disposes", f =>
        {
            var inspection = f.Inspect(); var lease = f.Fixture.Begin(inspection, inspection.Fingerprint);
            try
            {
                f.Fixture.BindDirectories(inspection, lease);
                Expect("cleanup_unconfirmed", () => f.Fixture.Finish(inspection, new(false, true, true), lease));
                SharingDenied(() => Directory.Move(f.Manifest.Udf, f.Manifest.Udf + "-early"));
                Program.Check(f.State().State == SmokeState.BLOCKED && File.Exists(f.Fixture.IntentPath));
            }
            finally { lease.Dispose(); }
            Program.Check(lease.Profile!.Closed && lease.Root!.Closed);
        }),
        .. SmokeIdentityTests.Cases(python, launcher),
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
    internal static void Expect(string code, Action operation)
    {
        try { operation(); } catch (SmokeError error) { Program.Check(error.Message == code); return; }
        throw new InvalidOperationException("expected_smoke_stop_missing");
    }
    private static void SharingDenied(Action operation)
    {
        try { operation(); }
        catch (IOException error) { Program.Check((error.HResult & 0xffff) == 32); return; }
        throw new InvalidOperationException("directory_pin_did_not_prevent_mutation");
    }
    internal sealed class SmokeTemp : IDisposable
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
        internal SmokeRecord State() => JsonSerializer.Deserialize<SmokeRecord>(File.ReadAllText(Fixture.StatePath))!;
        internal void ReplaceUdf()
        { Directory.Move(Manifest.Udf, Manifest.Udf + "-old"); Directory.CreateDirectory(Manifest.Udf); }
        internal void Clean()
        {
            var inspection = Inspect(); using var lease = Fixture.Begin(inspection, inspection.Fingerprint);
            Fixture.BindDirectories(inspection, lease); Fixture.Finish(inspection, new(true, true, true), lease);
        }
        internal void Failed(SmokeEvidence evidence)
        {
            var inspection = Inspect();
            using (var lease = Fixture.Begin(inspection, inspection.Fingerprint))
            { Fixture.BindDirectories(inspection, lease); Reject(() => Fixture.Finish(inspection, evidence, lease)); }
            Program.Check(File.Exists(Fixture.IntentPath)); Reject(() => Inspect());
            using var state = JsonDocument.Parse(File.ReadAllText(Fixture.StatePath));
            Program.Check(state.RootElement.GetProperty("State").GetInt32() == (int)SmokeState.BLOCKED);
        }
        internal string Snapshot() => string.Join("|", Directory.EnumerateFiles(Temp.Root, "*", SearchOption.AllDirectories)
            .Order(StringComparer.Ordinal).Select(p => p + ":" + SmokeFixture.FileHash(p)));
        public void Dispose() => Temp.Dispose();
    }
}
