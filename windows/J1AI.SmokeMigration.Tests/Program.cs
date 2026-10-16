using System.Diagnostics;
using System.Text;
using J1AI.SmokeMigration;

namespace J1AI.SmokeMigration.Tests;

internal static class Program
{
    private sealed class AssertionFailure(string id) : Exception("ASSERT:" + id) { internal string Id => id; }
    private static readonly HashSet<string> nonFixture = new(StringComparer.Ordinal)
    {
        "real_apply_argument_rejected", "read_only_tool_no_write_imports", "all_mock_handles_closed",
        "negative_classifier_expected_assertion", "negative_classifier_setup_exception", "negative_classifier_native_exception",
        "negative_classifier_different_assertion", "negative_classifier_normal_return", "negative_classifier_message_spoof",
        "probe_failure_counts_all_without_running_followers", "cleanup_refusal_counts_remaining_without_execution", "cleanup_failure_invalidates_negative_detection"
    };
    private static readonly string[] negativeIds = ["oracle_missing_backup_verification", "oracle_missing_marker_guard", "oracle_missing_final_verification"];
    private sealed record Case(string Name, Action Body, string? ExpectedAssertion = null)
    { internal bool FixtureRequired => !nonFixture.Contains(Name); }
    private sealed record Counts(int Registered, int Executed, int Pass, int Fail, int Detected, int NotRun, int Exit);
    private static readonly List<Case> cases = [];
    private static bool negative;
    private static void Assert([System.Diagnostics.CodeAnalysis.DoesNotReturnIf(false)] bool condition, string message) { if (!condition) throw new AssertionFailure(message); }
    private static Exception Reject(Action action, string? expected = null)
    {
        try { action(); } catch (Exception e) { Assert(expected == null || e.Message == expected, "rejection_code:" + e.Message); return e; }
        throw new AssertionFailure("rejection_missing");
    }
    private static void Test(string name, Action test, string? expectedAssertion = null) => cases.Add(new(name, test, expectedAssertion));
    private static Counts RunCases(IReadOnlyList<Case> planned, bool negativeMode, Func<bool> cleanupBlocked, Action<string>? report = null)
    {
        Assert(planned.Select(c => c.Name).Distinct().Count() == planned.Count, "unique_registered_names");
        int executed = 0, pass = 0, fail = 0, detected = 0, notRun = 0;
        bool probeFailed = false;
        foreach (var item in planned)
        {
            if (probeFailed || cleanupBlocked()) { notRun++; report?.Invoke("NOT_RUN " + item.Name + " cleanup_failed_no_retry"); continue; }
            executed++;
            var timer = Stopwatch.StartNew();
            try
            {
                if (report != null) { ObservationSession.Current?.CheckCancellation(); ObservationSession.Current?.Event("test_start", new { item.Name, item.FixtureRequired, item.ExpectedAssertion }); }
                item.Body();
                if (report != null) ObservationSession.Current?.CheckCancellation();
                if (item.ExpectedAssertion != null) throw new AssertionFailure("negative_control_returned_normally");
                if (report != null) ObservationSession.Current?.Event("assertion_result", new { Result = "PASS", Expected = item.ExpectedAssertion, Actual = (string?)null });
                pass++; report?.Invoke("PASS " + item.Name);
            }
            catch (AssertionFailure e) when (item.ExpectedAssertion != null && e.Id == item.ExpectedAssertion)
            { if (report != null) ObservationSession.Current?.Event("assertion_result", new { Result = "DETECTED", Expected = item.ExpectedAssertion, Actual = e.Id }); detected++; report?.Invoke("DETECTED_ASSERTION " + item.Name + " " + e.Id); }
            catch (Exception e)
            {
                fail++; if (item.Name == "cleanup_probe") probeFailed = true;
                if (report != null) ObservationSession.Current?.Event("assertion_result", new { Result = "FAIL", Expected = item.ExpectedAssertion, Actual = (e as AssertionFailure)?.Id, Type = e.GetType().Name });
                report?.Invoke("FAIL " + item.Name + " " + e.GetType().Name + " " + e.Message);
            }
            finally { if (report != null) ObservationSession.Current?.Event("test_end", new { item.Name, ElapsedMs = timer.Elapsed.TotalMilliseconds, Handles = MockSandbox.LiveHandles, MockSandbox.CleanupFailed }); }
        }
        int expected = planned.Count(c => c.ExpectedAssertion != null);
        int exit = negativeMode ? fail == 0 && notRun == 0 && detected == expected && expected > 0 ? 1 : 2
            : fail == 0 && notRun == 0 && detected == 0 ? 0 : 1;
        Assert(planned.Count == pass + fail + detected + notRun && executed == pass + fail + detected, "counts_partition");
        return new(planned.Count, executed, pass, fail, detected, notRun, exit);
    }
    private static void InMock(Action<MockSandbox, MockFile[]> test)
    {
        using var s = MockSandbox.Create(); var f = Transaction.Fixture(); Transaction.Populate(s, f);
        try { test(s, f); }
        finally { s.RestoreForCleanup(); } // Only explicit test injection changes are reconciled; transaction never repairs/reuses.
    }
    public static int Main(string[] args)
    {
        var clock = ObservationClock.Start();
        try { return MainCore(args, clock); }
        catch (Exception e)
        {
            string code = e is InvalidDataException && System.Text.RegularExpressions.Regex.IsMatch(e.Message, "\\A[a-z0-9_]+(:[0-9]+)?\\z") ? e.Message : "unexpected_failure";
            Console.Error.WriteLine("MIGRATION_TEST_BLOCKED " + code); return 2;
        }
    }
    private static int MainCore(string[] args, ObservationClock clock)
    {
        if (args is ["--inspect-diagnostic"])
        {
            try { using var inspector = new Inspector(); inspector.Inspect(); Console.WriteLine("READ_ONLY_INSPECTION_PASS"); return 0; }
            catch (Exception e)
            {
                Console.Error.WriteLine(e.GetType().FullName + " HRESULT=" + e.HResult.ToString("x8"));
                foreach (var frame in new StackTrace(e, true).GetFrames())
                    Console.Error.WriteLine(frame.GetMethod()?.DeclaringType?.FullName + "." + frame.GetMethod()?.Name + " line=" + frame.GetFileLineNumber());
                return 1;
            }
        }
        if (args is ["--hardening-tests"]) throw new InvalidDataException("hardening_full_suite_not_authorized");
        if (args.Length > 0 && args[0] == "--hardening-precheck") return HardeningTests.Run(clock, args[1..]);
        if (args is not ["--tests"] and not ["--negative-control"] and not ["--probe-failure-control"] and not ["--list-tests"] and not ["--case", _] and not ["--worker", _, _])
        { Console.Error.WriteLine("Only registered test modes are accepted. --list-tests / --case ID. No path, method, assembly or apply override."); return 1; }
        cases.Clear();
        string? selected = args is ["--case", var id] ? id : args is ["--worker", _, var workerId] ? workerId : null;
        negative = args[0] == "--negative-control" || (selected != null && negativeIds.Contains(selected, StringComparer.Ordinal));
        if (!OperatingSystem.IsWindows() || !Environment.Is64BitProcess) return 1;
        Test("cleanup_probe", () => { string path; using (var s = MockSandbox.Create()) { path = s.Root; s.Put("active", "probe", [1]); } Assert(!Directory.Exists(path), "probe_cleanup"); });
        if (negative)
        {
            Test("oracle_missing_backup_verification", () => InMock((s, f) =>
            {
                var p = new TransactionPolicy { VerifyBackup = false, At = (stage, i) => { if (stage == "backup_readback" && i == 0) s.CorruptForTest("backup", f[0].Name); } };
                Reject(() => new Transaction(s, f, p).Execute(), "backup_sha");
            }), "rejection_missing");
            Test("oracle_missing_marker_guard", () => InMock((s, f) =>
            {
                var p = new TransactionPolicy { RequireMarker = false, At = (stage, i) => { if (stage == "before_replace" && i == 0) s.Remove("active", Contract.Pending); } };
                Reject(() => new Transaction(s, f, p).Execute(), "marker_missing");
            }), "rejection_code:final_inventory");
            Test("oracle_missing_final_verification", () => InMock((s, f) =>
            {
                var p = new TransactionPolicy { VerifyFinal = false, At = (stage, _) => { if (stage == "final_readback") s.CorruptForTest("active", f[0].Name); } };
                Reject(() => new Transaction(s, f, p).Execute(), "final_sha");
            }), "rejection_missing");
            return Dispatch(args, clock);
        }
        Test("normal_transaction_47_backups_13_replacements", () => InMock((s, f) =>
        {
            var t = new Transaction(s, f, new()); var result = t.Execute();
            Assert(result.Successful && result.Commit == CommitDisposition.COMMITTED && result.Pending == PendingDisposition.ABSENT, "committed_result");
            Assert(s.Names("backup").Length == 47 && !s.Exists("active", Contract.Pending), "complete_backup_pending");
            Assert(t.Events.Count(e => e.StartsWith("replaced:")) == 13, "replacement_count");
            Assert(t.Events.IndexOf("backups_verified:-1") < t.Events.IndexOf("pending_flushed:-1") && t.Events.IndexOf("pending_flushed:-1") < t.Events.IndexOf("before_replace:0"), "backup_before_active");
            Assert(t.Events.IndexOf("replaced:31") < t.Events.IndexOf("replaced:32") && t.Events.IndexOf("replaced:32") < t.Events.IndexOf("replaced:42"), "metadata_observer_order");
            Reject(() => t.Execute(), "backup_collision");
        }));
        foreach (var failure in new[] { ("backup", 0), ("backup", 23), ("backup_flush", -1), ("backup_readback", 10),
            ("backups_verified", -1), ("pending_flushed", -1), ("before_replace", 0), ("before_replace", 3),
            ("before_replace", 31), ("before_replace", 32), ("before_replace", 44), ("replaced", 0),
            ("final_readback", -1), ("final_verified", -1), ("locked", -1) })
        {
            var chosen = failure;
            Test("fault_" + chosen.Item1 + "_" + chosen.Item2, () => InMock((s, f) =>
            {
                var p = new TransactionPolicy { At = (stage, i) => { if (stage == chosen.Item1 && i == chosen.Item2) throw new Injected("fault:" + stage); } };
                var t = new Transaction(s, f, p); Reject(() => t.Execute(), "fault:" + chosen.Item1);
                bool after = t.Events.Contains("pending_flushed:-1"); Assert(s.Exists("active", Contract.Pending) == after, "pending_retained");
                if (!after) foreach (var x in f) Assert(Contract.Hash(s.Read("active", x.Name)) == x.OldHash, "no_active_before_backup");
                if (after) Reject(() => new Transaction(s, f, new()).Execute(), "pending_exists");
            }));
        }
        Test("backup_hash_rejection", () => InMock((s, f) =>
        {
            var p = new TransactionPolicy { At = (stage, i) => { if (stage == "backup_readback" && i == 0) s.CorruptForTest("backup", f[0].Name); } };
            Reject(() => new Transaction(s, f, p).Execute(), "backup_sha"); Assert(!s.Exists("active", Contract.Pending), "no_active_on_bad_backup");
        }));
        Test("backup_destination_collision", () => InMock((s, f) => { s.Put("backup", f[0].Name, [1]); Reject(() => new Transaction(s, f, new()).Execute(), "backup_collision"); }));
        foreach (string fault in new[] { "flush", "readback" })
            Test("io_fault_backup_" + fault, () => InMock((s, f) =>
            {
                s.IoFault = (stage, path) => { if (stage == fault && path == "backup/" + f[5].Name) throw new Injected("io:" + stage); };
                Reject(() => new Transaction(s, f, new()).Execute(), "io:" + fault);
                foreach (var x in f) Assert(Contract.Hash(s.Read("active", x.Name)) == x.OldHash, "io_backup_no_active_write");
            }));
        Test("io_fault_marker_flush_retains_pending", () => InMock((s, f) =>
        {
            s.IoFault = (stage, path) => { if (stage == "flush" && path == "active/" + Contract.Pending) throw new Injected("marker_flush"); };
            Reject(() => new Transaction(s, f, new()).Execute(), "marker_flush");
            Assert(s.Exists("active", Contract.Pending), "failed_marker_not_cleared");
            foreach (var x in f) Assert(Contract.Hash(s.Read("active", x.Name)) == x.OldHash, "marker_io_no_active_write");
        }));
        Test("final_content_readback_rejects_same_object_corruption", () => InMock((s, f) =>
        {
            var p = new TransactionPolicy { At = (stage, _) => { if (stage == "final_readback") s.CorruptForTest("active", f[0].Name); } };
            Reject(() => new Transaction(s, f, p).Execute(), "final_sha"); Assert(s.Exists("active", Contract.Pending), "final_bad_hash_pending");
        }));
        Test("native_atomic_replace_sharing_failure_retains_pending", () => InMock((s, f) =>
        {
            ReadPin? held = null;
            try
            {
                var p = new TransactionPolicy { At = (stage, i) => { if (stage == "before_replace" && i == 0) held = new ReadPin(Path.Combine(s.Root, "active", f[0].Name), false); } };
                var e = Reject(() => new Transaction(s, f, p).Execute());
                // On this NTFS/Windows build, a target held without delete
                // sharing returns STATUS_ACCESS_DENIED, not our initial
                // anticipated ERROR_SHARING_VIOLATION. Require the precise
                // native status AND translated code observed in the probe.
                Assert(e is NativeFailure { Api: "mock_atomic_replace", Win32: 5, Status: 0xc0000022 }, "actual_nt_rename_refusal:" + e.Message);
                Assert(s.Exists("active", Contract.Pending), "native_replace_failure_pending");
            }
            finally { held?.Dispose(); }
        }));
        Test("existing_pending_no_reuse", () => InMock((s, f) => { s.Put("active", Contract.Pending, [1]); Reject(() => new Transaction(s, f, new()).Execute(), "pending_exists"); }));
        foreach (string area in new[] { "active", "candidate" })
            Test("unknown_file_rejected_" + area, () => InMock((s, f) =>
            {
                s.Put(area, "extra.bin", [1]); Reject(() => new Transaction(s, f, new()).Execute(), area + "_inventory");
                Assert(s.Names("backup").Length == 0 && !s.Exists("active", Contract.Pending), "unknown_inventory_no_writes");
            }));
        Test("staging_readback_fault_retains_pending_and_stage", () => InMock((s, f) =>
        {
            s.IoFault = (stage, path) => { if (stage == "readback" && path.StartsWith("active/stage-", StringComparison.Ordinal)) throw new Injected("stage_readback"); };
            Reject(() => new Transaction(s, f, new()).Execute(), "stage_readback");
            Assert(s.Exists("active", Contract.Pending) && s.Names("active").Any(n => n.StartsWith("stage-", StringComparison.Ordinal)), "interrupted_stage_preserved");
        }));
        foreach (string area in new[] { "candidate", "active" })
            Test("same_bytes_file_identity_replacement_" + area, () => InMock((s, f) =>
            {
                var p = new TransactionPolicy { At = (stage, i) => { if (stage == "before_replace" && i == 0) s.ChangeFileForTest(area, f[0].Name, true); } };
                Reject(() => new Transaction(s, f, p).Execute(), "mock_file_replaced"); Assert(s.Exists("active", Contract.Pending), "retained_after_identity_fault");
            }));
        Test("marker_removed_is_blocked", () => InMock((s, f) =>
        {
            var p = new TransactionPolicy { At = (stage, i) => { if (stage == "before_replace" && i == 0) s.Remove("active", Contract.Pending); } };
            Reject(() => new Transaction(s, f, p).Execute(), "marker_missing");
        }));
        Test("same_thread_duplicate_gate_rejected", () => InMock((s, f) =>
        { using var gate = new Mutex(false, @"Local\J1AI.Migration.MockGate." + s.Identity); Reject(() => new Transaction(s, f, new()).Execute(), "mock_gate_busy"); }));
        Test("existing_mock_smoke_lock_exclusive_contention", () => InMock((s, f) =>
        {
            using var locked = s.AcquireLock(); var e = Reject(() => new Transaction(s, f, new()).Execute());
            Assert(e is NativeFailure { Win32: 32 }, "native_lock_contention");
            Assert(s.Names("backup").Length == 0 && !s.Exists("active", Contract.Pending), "lock_failure_no_backup_or_active");
        }));
        Test("observer_mutex_contention_cross_thread", () => InMock((s, f) =>
        {
            using var ready = new ManualResetEventSlim(); using var release = new ManualResetEventSlim();
            var worker = Task.Run(() => { using var mutex = new Mutex(false, @"Local\J1AI.Migration.MockObserver." + s.Identity); mutex.WaitOne(); ready.Set(); release.Wait(TimeSpan.FromSeconds(10)); mutex.ReleaseMutex(); });
            Assert(ready.Wait(TimeSpan.FromSeconds(5)), "mutex_ready");
            try { Reject(() => new Transaction(s, f, new()).Execute(), "mock_observer_busy"); }
            finally { release.Set(); Assert(worker.Wait(TimeSpan.FromSeconds(5)), "mutex_worker_end"); }
        }));
        Test("owner_sid_mismatch_rejected", () => InMock((s, _) => Reject(() => s.FaultSecurity("owner"), "owner_sid")));
        Test("unprotected_dacl_rejected", () => InMock((s, _) => { s.FaultSecurity("dacl"); Reject(s.Validate, "dacl_protected"); }));
        Test("directory_pin_prevents_replacement", () => InMock((s, _) =>
        { Reject(() => Directory.Move(Path.Combine(s.Root, "active"), Path.Combine(s.Root, "replaced"))); Assert(!Directory.Exists(Path.Combine(s.Root, "replaced")), "directory_rename_denied"); s.Validate(); }));
        Test("real_symlink_reparse_rejected", () =>
        {
            using var s = MockSandbox.Create(); string link = Path.Combine(s.Root, "active", "link");
            ObservationSession.Require().Intent("symlink", s.Identity + "/active/link");
            Assert(MockSandbox.CreateSymbolicLinkW(link, Path.Combine(s.Root, "candidate"), 3), "symlink_create:" + System.Runtime.InteropServices.Marshal.GetLastWin32Error());
            try { Assert(s.SymlinkTagForTest("link") == 0xa000000c, "actual_symlink_tag"); Reject(() => { using var pin = new ReadPin(link, true); }, "reparse"); Assert(s.Names("candidate").Length == 0, "symlink_target_empty"); }
            finally { s.RemoveTestSymlink("link"); } // Owned handle only; never recurse into target.
        });
        foreach (string invalid in new[] { "../outside", "C:\\Windows", "active/../../outside", "..", "file:stream" })
            Test("path_escape_rejected_" + invalid, () => InMock((s, _) => Reject(() => s.Put("active", invalid, [1]), "mock_component")));
        Test("real_apply_argument_rejected", () => Assert(J1AI.SmokeMigration.Program.Main(["--apply"]) == 1, "apply_absent"));
        Test("read_only_tool_no_write_imports", () =>
        {
            var imports = typeof(Inspector).Assembly.GetTypes().SelectMany(t => t.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)).Where(m => m.IsDefined(typeof(System.Runtime.InteropServices.DllImportAttribute), false)).Select(m => m.Name).ToArray();
            Assert(!imports.Contains("NtCreateFile") && !imports.Contains("NtSetInformationFile") && !imports.Contains("SetSecurityInfo") && !imports.Contains("CreateMutexW"), "writer_not_in_tool");
        });
        RegisterResultTests();
        RegisterHarnessTests();
        Test("all_mock_handles_closed", () => Assert(MockSandbox.LiveHandles == 0, "live_handles"));
        // Registration is complete BEFORE even the first probe can run. This
        // control throws without creating any mock object or changing ACLs.
        if (args[0] == "--probe-failure-control") cases[0] = new("cleanup_probe", () => throw new Injected("synthetic_probe_failure"));
        return Dispatch(args, clock);
    }
    private static int Dispatch(string[] args, ObservationClock clock)
    {
        if (args is ["--list-tests"])
        {
            Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { NormalRegistered = cases.Count, NegativeControls = negativeIds.Length, AddedDiagnostics = 0,
                Tests = cases.Select(c => new { ID = c.Name, Category = c.FixtureRequired ? "native-fixture" : "nonfixture", c.FixtureRequired }),
                NegativeIDs = negativeIds, NativeCasesAuthorized = ObservationPaths.NativeFixtureAuthorized, FullSuiteAuthorized = ObservationPaths.FullSuiteAuthorized })); return 0;
        }
        if (args is ["--case", var id])
        {
            var item = cases.SingleOrDefault(c => c.Name.Equals(id, StringComparison.Ordinal));
            Contract.Require(item != null, "unknown_test_id"); // Before ANY log/root creation.
            return CaseSupervisor.Run(item.Name, item.FixtureRequired, item.ExpectedAssertion, clock);
        }
        if (args is ["--worker", var run, var workerId])
        {
            var item = cases.SingleOrDefault(c => c.Name.Equals(workerId, StringComparison.Ordinal)); Contract.Require(item != null, "unknown_test_id");
            var request = CaseSupervisor.WorkerRequest(run, item.Name); Contract.Require(request.FixtureRequired == item.FixtureRequired, "fixture_classification");
            using var session = new ObservationSession(request);
            var counts = RunCases(new[] { item }, item.ExpectedAssertion != null, () => MockSandbox.CleanupFailed, Console.WriteLine);
            session.Event("cleanup_start", new { session.CreatedObjects, Handles = MockSandbox.LiveHandles, MockSandbox.CleanupFailed });
            // No Native fixture is authorized. Record the nonfixture cleanup
            // phase separately from test_end and OS process exit.
            Contract.Require(session.CreatedObjects == 0 && MockSandbox.LiveHandles == 0 && !MockSandbox.CleanupFailed, "nonfixture_cleanup");
            session.Event("cleanup_complete", new { session.CreatedObjects, Handles = MockSandbox.LiveHandles, MockSandbox.CleanupFailed });
            var summary = new { Run = run, Test = item.Name, RegisteredCatalogue = cases.Count, Selected = 1, NotSelected = cases.Count - 1,
                counts.Executed, counts.Pass, counts.Fail, counts.Detected, counts.NotRun, counts.Exit, Handles = MockSandbox.LiveHandles,
                MockSandbox.CleanupFailed, session.CreatedObjects, session.CleanedMocks,
                Commit = session.LastTransaction?.Commit.ToString() ?? "NOT_APPLICABLE", Pending = session.LastTransaction?.Pending.ToString() ?? "NOT_APPLICABLE",
                Cleanup = session.CreatedObjects == 0 ? "NO_MOCK_CREATED" : MockSandbox.CleanupFailed ? "FAILED" : "OBSERVED" };
            session.Event("worker_summary", summary);
            using var directory = new ReadPin(ObservationPaths.RunPath(run), true);
            CaseSupervisor.WriteFile(directory.Handle, "summary.json", System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(summary));
            return Summary(counts);
        }
        // Legacy entry names and all registrations are retained. A full/native
        // execution requires a separate reviewed authorization, not this gate.
        Contract.Require(ObservationPaths.FullSuiteAuthorized, "full_suite_not_authorized");
        return Summary(RunCases(cases, negative, () => MockSandbox.CleanupFailed, Console.WriteLine));
    }
    private static int Summary(Counts counts)
    {
        Console.WriteLine($"REGISTERED={counts.Registered} EXECUTED={counts.Executed} PASS={counts.Pass} FAIL={counts.Fail} DETECTED={counts.Detected} NOT_RUN={counts.NotRun} LIVE_HANDLES={MockSandbox.LiveHandles} EXIT={counts.Exit}"); return counts.Exit;
    }

    private static void RegisterResultTests()
    {
        foreach (string barrier in new[] { "final_verified", "commit_permitted", "pending_remove" })
            Test("commit_boundary_failure_" + barrier, () => InMock((s, f) =>
            {
                var t = new Transaction(s, f, new() { At = (stage, _) => { if (stage == barrier) throw new Injected("boundary:" + barrier); } });
                Reject(() => t.Execute(), "boundary:" + barrier);
                Assert(t.Result is { Commit: CommitDisposition.NOT_COMMITTED, Pending: PendingDisposition.PRESENT, Successful: false }, "boundary_result");
                Assert(t.Result.Stage == barrier && t.Result.Problems.Length == 1, "failure_stage");
                foreach (var x in f) Assert(Contract.Hash(s.Read("active", x.Name)) == (x.Rewrite ? x.NewHash : x.OldHash), "no_rollback");
                Reject(() => new Transaction(s, f, new()).Execute(), "pending_exists");
            }));
        Test("completion_record_has_no_fallible_hook", () => InMock((s, f) =>
        {
            var t = new Transaction(s, f, new() { At = (stage, _) => { if (stage == "committed") throw new Injected("obsolete_commit_hook"); } });
            Assert(t.Execute().Successful && t.Events[^1] == "committed:-1", "completion_record");
            Assert(t.Events.IndexOf("final_verified:-1") < t.Events.IndexOf("commit_permitted:-1") && t.Events.IndexOf("commit_permitted:-1") < t.Events.IndexOf("pending_remove:-1"), "commit_order");
        }));
        foreach (string boundary in new[] { "remove_before", "remove_after" })
            Test("pending_operation_failure_" + boundary, () => InMock((s, f) =>
            {
                s.IoFault = (stage, path) => { if (stage == boundary && path == "active/" + Contract.Pending) throw new Injected(boundary); };
                var t = new Transaction(s, f, new()); Reject(() => t.Execute(), boundary);
                bool removed = boundary == "remove_after";
                Assert(t.Result!.Commit == (removed ? CommitDisposition.COMMITTED : CommitDisposition.NOT_COMMITTED), "remove_commit_observed");
                Assert(t.Result.Pending == (removed ? PendingDisposition.ABSENT : PendingDisposition.PRESENT) && !t.Result.Successful, "remove_failure_not_success");
                Assert(t.Result.Stage == "pending_remove", "removal_stage");
                s.IoFault = (_, _) => { };
                Reject(() => new Transaction(s, f, new()).Execute(), removed ? "backup_collision" : "pending_exists");
            }));
        foreach (string resource in new[] { "lock_dispose", "mutex_release", "observer_dispose", "gate_dispose" })
            Test("committed_cleanup_failure_" + resource, () => InMock((s, f) =>
            {
                var released = new List<string>();
                var t = new Transaction(s, f, new() { AfterCleanup = name => { released.Add(name); if (name == resource) throw new Injected("cleanup:" + name); } });
                Reject(() => t.Execute(), "cleanup:" + resource);
                Assert(t.Result is { Commit: CommitDisposition.COMMITTED, Pending: PendingDisposition.ABSENT, Successful: false }, "cleanup_does_not_uncommit_or_succeed");
                Assert(t.Result.Stage == "cleanup:" + resource && released.SequenceEqual(new[] { "lock_dispose", "mutex_release", "observer_dispose", "gate_dispose" }), "all_releases_attempted");
                foreach (var x in f) Assert(Contract.Hash(s.Read("active", x.Name)) == (x.Rewrite ? x.NewHash : x.OldHash), "cleanup_no_rollback");
                Assert(!s.Exists("active", Contract.Pending), "no_pending_recreation");
                using var lockAgain = s.AcquireLock();
                using var gate = new Mutex(false, @"Local\J1AI.Migration.MockGate." + s.Identity, out bool created);
                Assert(created, "gate_released");
            }));
        Test("multiple_cleanup_errors_preserve_primary_and_commit", () => InMock((s, f) =>
        {
            var t = new Transaction(s, f, new() { AfterCleanup = name => throw new Injected(name) });
            Reject(() => t.Execute(), "lock_dispose"); Assert(t.Result!.Commit == CommitDisposition.COMMITTED && t.Result.Problems.Length == 4, "all_cleanup_errors_recorded");
        }));
        Test("precommit_error_not_masked_by_cleanup_error", () => InMock((s, f) =>
        {
            var t = new Transaction(s, f, new() { At = (stage, _) => { if (stage == "commit_permitted") throw new Injected("primary"); }, AfterCleanup = name => { if (name == "lock_dispose") throw new Injected("secondary"); } });
            Reject(() => t.Execute(), "primary"); Assert(t.Result is { Commit: CommitDisposition.NOT_COMMITTED, Pending: PendingDisposition.PRESENT } && t.Result.Problems.Length == 2, "both_errors_recorded");
        }));
        Test("removal_observation_failure_is_indeterminate", () => InMock((s, f) =>
        {
            var t = new Transaction(s, f, new() { BeforePendingObservation = () => throw new Injected("observation_failed") });
            Reject(() => t.Execute(), "observation_failed");
            Assert(t.Result is { Commit: CommitDisposition.INDETERMINATE, Pending: PendingDisposition.UNKNOWN, Successful: false }, "unknown_not_success_or_uncommitted");
            Assert(!s.Exists("active", Contract.Pending), "actual_removal_no_recreation");
        }));
        Test("incomplete_backup_has_zero_replacements", () => InMock((s, f) =>
        {
            var t = new Transaction(s, f, new() { At = (stage, i) => { if (stage == "backup" && i == 23) throw new Injected("incomplete_backup"); } });
            Reject(() => t.Execute(), "incomplete_backup");
            Assert(!t.Events.Any(e => e.StartsWith("replaced:")) && t.Result!.Commit == CommitDisposition.NOT_COMMITTED, "zero_replacements");
        }));
    }

    private static void RegisterHarnessTests()
    {
        var variations = new (string Name, Action Body, int Detected, int Fail)[]
        {
            ("expected_assertion", () => throw new AssertionFailure("expected"), 1, 0),
            ("setup_exception", () => throw new Injected("setup"), 0, 1),
            ("native_exception", () => throw new NativeFailure("fake_native", unchecked((int)0xc0000022), 5), 0, 1),
            ("different_assertion", () => throw new AssertionFailure("other"), 0, 1),
            ("normal_return", () => { }, 0, 1),
            ("message_spoof", () => throw new Exception("ASSERT:expected"), 0, 1)
        };
        foreach (var variant in variations)
            Test("negative_classifier_" + variant.Name, () =>
            {
                var result = RunCases(new Case[] { new("cleanup_probe", () => { }), new("oracle", variant.Body, "expected") }, true, () => false);
                Assert(result.Detected == variant.Detected && result.Fail == variant.Fail && result.Pass == 1 && result.NotRun == 0, "strict_negative_partition");
                Assert(result.Exit == (variant.Detected == 1 ? 1 : 2), "negative_exit_code");
            });
        Test("probe_failure_counts_all_without_running_followers", () =>
        {
            int generated = 0;
            var result = RunCases(new Case[] { new("cleanup_probe", () => throw new Injected("fake_probe")), new("would_generate_mock", () => generated++), new("last", () => generated++) }, false, () => false);
            Assert(result is { Registered: 3, Executed: 1, Pass: 0, Fail: 1, NotRun: 2, Exit: 1 } && generated == 0, "probe_stops_and_counts");
        });
        Test("cleanup_refusal_counts_remaining_without_execution", () =>
        {
            bool cleanupFailed = false; int generated = 0;
            var result = RunCases(new Case[] { new("cleanup_probe", () => { }), new("cleanup_failure", () => { cleanupFailed = true; throw new Injected("fake_cleanup"); }), new("not_run", () => generated++) }, false, () => cleanupFailed);
            Assert(result is { Registered: 3, Executed: 2, Pass: 1, Fail: 1, NotRun: 1, Exit: 1 } && generated == 0, "cleanup_stop_counts");
        });
        Test("cleanup_failure_invalidates_negative_detection", () =>
        {
            var result = RunCases(new Case[] { new("cleanup_probe", () => { }), new("oracle", () => { try { throw new AssertionFailure("expected"); } finally { throw new Injected("cleanup_failed"); } }, "expected") }, true, () => false);
            Assert(result is { Detected: 0, Fail: 1, Exit: 2 }, "cleanup_not_detected");
        });
    }
}
