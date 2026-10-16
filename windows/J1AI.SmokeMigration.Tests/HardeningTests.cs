using System.Diagnostics;
using System.Text;
using System.Text.Json;
using J1AI.SmokeMigration;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeMigration.Tests;

internal sealed record SuiteCounts(int RegisteredLegacy, int RegisteredNew, int Selected, int Executed,
    int Pass, int Fail, int NotRun, int NotSelected, int LegacyExecuted, int NewExecuted);
internal sealed record TerminalEvent(string Step, string Phase, double Seconds, string? Type = null, string? Reason = null);
internal sealed record TerminalStep(string Name, Action Body, bool Evidence = false);
internal sealed record TerminalResult(string Test, string Evidence, string Terminal, string Gate, bool DeadlineSatisfied,
    SuiteCounts Counts, TerminalEvent[] Trace)
{
    public bool GateReleaseAuthorized => false;
    public string NextExecution => "NOT_AUTHORIZED";
    public bool AutomaticRetry => false;
    public bool Success => Test == "PASS" && Evidence == "VALID" && Terminal == "COMPLETE" && Gate == "RETAINED" && DeadlineSatisfied;
    public int Exit => Success ? 0 : Terminal == "TIMEOUT" ? 15 : Terminal == "UNKNOWN" ? 14 : Terminal == "FAILED" ? 13
        : Evidence == "UNAVAILABLE" ? 12 : Evidence == "INVALID" ? 11 : 2;
}

// Test-only terminal policy. No delete, retry, process-launch or gate-release
// capability is supplied. Native I/O remains cooperative/unbounded. The final
// check runs AFTER every owned-resource Dispose and the fallible report sink.
internal static class HardeningTerminal
{
    internal static readonly string[] Order = ["journal_finalization", "journal_flush_readback", "journal_dispose",
        "journal_sealed_readback", "gate_handle_dispose", "gate_retention", "directory_handle_dispose", "root_handle_dispose"];
    internal static TerminalResult Run(IObservationClock clock, SuiteCounts counts, IReadOnlyList<TerminalStep> steps,
        Action<TerminalResult> publish)
    {
        Contract.Require(steps.Select(s => s.Name).SequenceEqual(Order), "terminal_step_contract");
        var trace = new List<TerminalEvent>(); bool failed = false, unknown = false, clockUnknown = false, late = false, evidenceFailed = false;
        string evidence = "UNAVAILABLE", gate = "UNKNOWN";
        double Time() { double t = clock.Seconds; if (!double.IsFinite(t) || t < 0) clockUnknown = true; else if (t >= ObservationDeadline.Finalize) late = true; return t; }
        void Note(string step, string phase, Exception? error = null) => trace.Add(new(step, phase, Time(), error?.GetType().Name,
            error == null ? null : System.Text.RegularExpressions.Regex.IsMatch(error.Message, "\\A[a-z0-9_]+\\z") ? error.Message : "unexpected_terminal_exception"));
        void Fault(TerminalStep step, Exception error)
        {
            failed = true;
            if (step.Evidence) { evidenceFailed = true; evidence = error is IOException && error is not InvalidDataException ? "UNAVAILABLE" : "INVALID"; }
            if (step.Name == "gate_retention") unknown = true;
            Note(step.Name, "exception", error);
        }
        foreach (var step in steps)
        {
            Note(step.Name, "begin");
            try
            {
                step.Body(); Note(step.Name, "end");
                if (step.Name == "journal_sealed_readback" && !evidenceFailed) evidence = "VALID";
                if (step.Name == "gate_retention") gate = "RETAINED";
            }
            catch (Exception error) { Fault(step, error); }
            // Continue all resource-release attempts, never a test or I/O retry.
        }
        TerminalResult Classify() => new(counts.NotRun != 0 ? "UNKNOWN" : counts.Fail != 0 ? "FAIL" : "PASS", evidence,
            late ? "TIMEOUT" : unknown || clockUnknown ? "UNKNOWN" : failed ? "FAILED" : "COMPLETE", gate, !late && !clockUnknown, counts, trace.ToArray());
        Note("final_deadline_check", "begin"); Note("final_deadline_check", "end");
        Note("result_classification", "begin"); var candidate = Classify(); Note("result_classification", "end");
        // The raw report is PROVISIONAL. Its publication can itself fail or
        // cross the deadline; only the subsequent process exit code confirms
        // this last check. The external observer durably records that exit.
        Note("result_publication", "begin");
        try { publish(candidate with { Trace = trace.ToArray() }); Note("result_publication", "end"); }
        catch (Exception error) { failed = true; Note("result_publication", "exception", error); }
        Note("final_deadline_check_after_publication", "begin"); Note("final_deadline_check_after_publication", "end");
        Note("final_result_classification", "begin"); Note("final_result_classification", "end");
        // No filesystem, console or Dispose operation may follow this decision.
        return Classify();
    }
}

// Separate, explicitly authorized nonfixture suite. Never calls the legacy
// catalogue, MockSandbox.Create, Transaction, GUI, IPC or a child process.
internal static class HardeningTests
{
    private sealed class CheckFailure(string id) : Exception(id);
    private sealed class FakeClock(double seconds) : IObservationClock { public double Seconds { get; set; } = seconds; }
    private sealed record Item(string Id, Action Body);
    private static void Check([System.Diagnostics.CodeAnalysis.DoesNotReturnIf(false)] bool value, string id) { if (!value) throw new CheckFailure(id); }
    private static void Reject(Action action, string reason, ObservationOutcome? outcome = null)
    {
        try { action(); }
        catch (EvidenceFailure e) { Check(e.Reason == reason && (outcome == null || outcome == e.Outcome), "wrong_evidence_rejection"); return; }
        catch (InvalidDataException e) when (outcome == null) { Check(e.Message == reason, "wrong_policy_rejection"); return; }
        throw new CheckFailure("expected_rejection_missing");
    }
    private static void RejectOracle(Action action)
    {
        try { action(); }
        catch (CheckFailure e) when (e.Message == "expected_rejection_missing") { return; }
        throw new CheckFailure("oracle_not_detected");
    }
    private static readonly JsonSerializerOptions json = new();
    private static byte[] Bytes(object data) => JsonSerializer.SerializeToUtf8Bytes(data, json);
    private static JsonElement Element(object data) => JsonSerializer.SerializeToElement(data, json);
    private sealed class Bundle : IDisposable
    {
        private readonly SafeFileHandle directory;
        internal readonly RunRequest Request;
        internal readonly WorkerSummary Summary;
        internal readonly WorkerBinding Process = new(1234, 123456, new string('c', 64));
        internal readonly JournalBinding Supervisor;
        private readonly string path;
        internal uint Exit = 0;
        internal Bundle(SafeFileHandle parent, string parentPath, string name,
            Action<List<JournalRecord>, List<JournalRecord>>? mutate = null, Func<WorkerSummary, WorkerSummary>? summaryMutation = null,
            Func<byte[], byte[]>? eventsBytes = null, Func<byte[], byte[]>? ownershipBytes = null, Action<JournalRecord[]>? supervisorMutation = null)
        {
            directory = MockSandbox.Open(parent, name, true, true); path = Path.Combine(parentPath, name);
            try
            {
                string run = Guid.NewGuid().ToString("N"), test = "negative_classifier_expected_assertion";
                var environment = WorkerEnvironment.ValidatedExpected(); string block = WorkerEnvironment.Build(environment, environment);
                var source = new SourceBinding("4d1c802a53a4f4d093f56376d8523ba25b316b26", new string('a', 64), new string('b', 64),
                    new string('c', 64), new string('d', 64), ObservationPaths.RootId, new(), new());
                Summary = new(run, test, 69, 1, 68, 1, 1, 0, 0, 0, 0, 0, false, 0, 0, "NOT_APPLICABLE", "NOT_APPLICABLE", "NO_MOCK_CREATED");
                object Wrap(object detail) => new { ElapsedMs = 1.0, Detail = detail };
                JournalRecord Row(int sequence, string stage, object data) => new(sequence, run, test, DateTimeOffset.UtcNow,
                    1 + sequence * Stopwatch.Frequency, stage, Element(data));
                var events = new List<JournalRecord>
                {
                    Row(1, "journal_prepared", source),
                    Row(2, "worker_started", Wrap(new { Source = source, FixtureRequired = false, Process = Process.Pid, Environment = environment })),
                    Row(3, "test_start", Wrap(new { Name = test, FixtureRequired = false, ExpectedAssertion = (string?)null })),
                    Row(4, "assertion_result", Wrap(new { Result = "PASS", Expected = (string?)null, Actual = (string?)null })),
                    Row(5, "test_end", Wrap(new { Name = test, Handles = 0, CleanupFailed = false })),
                    Row(6, "cleanup_start", Wrap(new { CreatedObjects = 0, Handles = 0, CleanupFailed = false })),
                    Row(7, "cleanup_complete", Wrap(new { CreatedObjects = 0, Handles = 0, CleanupFailed = false })),
                    Row(8, "worker_summary", Wrap(Summary))
                };
                var ownership = new List<JournalRecord> { Row(1, "journal_prepared", new { CreationIntentIsNotAtomicWithCreation = true, AutomaticRecoveryAuthorized = false }) };
                mutate?.Invoke(events, ownership);
                byte[] eventData = eventsBytes?.Invoke(Lines(events)) ?? Lines(events), ownData = ownershipBytes?.Invoke(Lines(ownership)) ?? Lines(ownership);
                var eventBinding = Write("test-events.jsonl", eventData); var ownBinding = Write("ownership.jsonl", ownData);
                Request = new(run, test, false, ReadPin.Identity(directory), eventBinding, ownBinding, source, 1, block);
                Write("summary.json", Bytes(summaryMutation?.Invoke(Summary) ?? Summary));
                var verified = new VerifiedWorker(Summary, new(5, 6, 7), Contract.Hash(eventData), Contract.Hash(ownData), true);
                var supervisor = new List<JournalRecord>
                {
                    Row(1, "before_worker", new { source, RunDirectory = Request.RunDirectoryIdentity }),
                    Row(2, "worker_created", Process), Row(3, "worker_permitted", new { }),
                    Row(4, "worker_exited", new { ActualExitCode = 0 }),
                    Row(5, "final_observation", new { Outcome = "VERIFIED_SUCCESS", StdoutSHA256 = Contract.Hash([]), StderrSHA256 = Contract.Hash([]),
                        verified.EventsSHA256, verified.OwnershipSHA256, SummarySHA256 = Contract.Hash(Bytes(Summary)), Summary }),
                    Row(6, "supervisor_complete", new { Outcome = "VERIFIED_SUCCESS" })
                };
                var supervisorRows = supervisor.ToArray(); supervisorMutation?.Invoke(supervisorRows);
                Supervisor = Write("supervisor.jsonl", Lines(supervisorRows));
                Write("creation-bindings.json", Bytes(new { Request.Events, Request.Ownership, Supervisor }));
            }
            catch { directory.Dispose(); throw; }
        }
        internal static byte[] Lines(IEnumerable<JournalRecord> rows) => Encoding.UTF8.GetBytes(string.Concat(rows.Select(r => JsonSerializer.Serialize(r) + "\n")));
        private JournalBinding Write(string name, byte[] bytes) => new(Path.Combine(path, name), CaseSupervisor.WriteFile(directory, name, bytes));
        internal VerifiedWorker Validate(Func<EvidenceSnapshot, EvidenceSnapshot>? eventsMutation = null, Func<EvidenceSnapshot, EvidenceSnapshot>? ownMutation = null)
        {
            using var events = new HeldEvidence(Request.Events); using var owns = new HeldEvidence(Request.Ownership);
            using var summary = new ReadPin(Path.Combine(path, "summary.json"), false);
            return JournalValidation.Worker(Request, eventsMutation?.Invoke(events.Snapshot) ?? events.Snapshot,
                ownMutation?.Invoke(owns.Snapshot) ?? owns.Snapshot, summary.Bytes(), Exit, Process.Pid);
        }
        internal void ValidateSupervisor(Action<JournalRecord[]>? mutate = null)
        {
            var verified = Validate(); using var held = new HeldEvidence(Supervisor);
            var snapshot = held.Snapshot;
            if (mutate != null)
            {
                var records = JournalValidation.Records(snapshot.Bytes, Request.Run, Request.Test); mutate(records);
                snapshot = snapshot with { Bytes = Lines(records) };
            }
            JournalValidation.Supervisor(Request, Supervisor, snapshot, verified, 0, Contract.Hash([]), Contract.Hash([]), Contract.Hash(Bytes(Summary)), Process);
        }
        internal void RemoveOwnership() => ObservationNative.DeleteOwned(directory, "ownership.jsonl", Request.Ownership.Receipt.Identity);
        public void Dispose() => directory.Dispose(); // Approved evidence artifacts are retained, not recursively deleted.
    }
    internal static readonly string[] ApprovedPrechecks = [
        "environment_actual_block_exact", "environment_allowed", "environment_duplicate_case", "environment_extra_path",
        "environment_block_duplicate", "environment_missing_equals", "environment_empty_entry", "journal_complete", "journal_final_lf",
        "environment_key_path_extra", "environment_key_userpath", "environment_key_path_lowercase", "environment_key_allowed_case",
        "environment_key_duplicate_exact", "environment_key_empty", "environment_key_equals", "environment_key_digit_initial", "environment_key_nul",
        "terminal_within_deadline", "terminal_journal_dispose_late", "terminal_gate_dispose_late", "terminal_journal_dispose_exception",
        "terminal_gate_dispose_exception", "terminal_readback_failure", "terminal_evidence_then_late", "terminal_at_deadline",
        "terminal_late_normal_return", "terminal_pass_gate_retained", "terminal_fail_gate_retained", "terminal_timeout_gate_retained",
        "terminal_unknown_no_retry", "terminal_counts_unchanged", "terminal_publication_late", "terminal_publication_exception",
        "terminal_root_dispose_late", "terminal_sealed_readback_failure", "terminal_arbitrary_exception_not_success"];
    internal static int Run(ObservationClock clock, string[] requested)
    {
        Contract.Require(requested.Length > 0 && requested.Distinct(StringComparer.Ordinal).Count() == requested.Length &&
            requested.All(id => ApprovedPrechecks.Contains(id, StringComparer.Ordinal)), "hardening_precheck_id_denied");
        Contract.Require(!ObservationPaths.NativeFixtureAuthorized && !ObservationPaths.FullSuiteAuthorized, "hardening_gates_closed");
        var expected = WorkerEnvironment.ValidatedExpected();
        WorkerEnvironment.SupervisorPreflight(WorkerEnvironment.Current(), expected);
        var source = CaseSupervisor.Source();
        ReadPin? root = null; SafeFileHandle? gate = null, directory = null; DurableLog? journal = null; bool terminalOwnsCleanup = false;
        try
        {
        root = ObservationPaths.PinRoot();
        Contract.Require(!File.Exists(Path.Combine(ObservationPaths.Root, "supervisor.lock")) && !File.Exists(Path.Combine(ObservationPaths.Root, "supervisor.pending")), "observation_quarantined");
        foreach (string control in new[] { "hardening.lock", "hardening.intent.json", "hardening-gate-receipt.json" })
            Contract.Require(!File.Exists(Path.Combine(ObservationPaths.Root, control)), "hardening_prior_attempt_retained");
        string run = Guid.NewGuid().ToString("N"), name = "hardening-" + run, path = Path.Combine(ObservationPaths.Root, name);
        string gatePath = Path.Combine(ObservationPaths.Root, "hardening.lock");
        var intent = CaseSupervisor.WriteFile(root.Handle, "hardening.intent.json", Bytes(new { Run = run, GatePath = gatePath,
            State = "CREATION_INTENT_NOT_OWNERSHIP", UTC = DateTimeOffset.UtcNow, GateReleaseAuthorized = false }));
        gate = MockSandbox.Open(root.Handle, "hardening.lock", false, true, shareOverride: 0);
        var gateReceipt = ObservationNative.Inspect(gate, "file"); string gateId = gateReceipt.Identity;
        var createdAt = ObservationNative.CreatedUTC(gate); var acquiredAt = DateTimeOffset.UtcNow;
        var receipt = new { Run = run, GatePath = gatePath, Receipt = gateReceipt, CreatedUTC = createdAt, ReceiptUTC = acquiredAt,
            IntentReceipt = intent, FlushReadbackConfirmed = true, GateReleaseAuthorized = false, NextExecution = "NOT_AUTHORIZED" };
        var persistedReceipt = CaseSupervisor.WriteFile(root.Handle, "hardening-gate-receipt.json", Bytes(receipt));
        // WriteFile has completed same-handle flush/readback. Confirm the
        // persisted ORIGINAL receipt before any test body can run.
        using (var receiptHeld = new HeldEvidence(new(Path.Combine(ObservationPaths.Root, "hardening-gate-receipt.json"), persistedReceipt)))
            Check(receiptHeld.Snapshot.Bytes.SequenceEqual(Bytes(receipt)), "gate_receipt_readback");
        directory = MockSandbox.Open(root.Handle, name, true, true);
        SafeFileHandle caseDirectory = directory;
        journal = new DurableLog(directory, "results.jsonl", true);
        var items = new List<Item>(); int serial = 0;
        void Add(string id, Action body) => items.Add(new(id, body));
        void JournalCase(string id, string? rejection = null, Action<List<JournalRecord>, List<JournalRecord>>? mutation = null,
            Func<WorkerSummary, WorkerSummary>? summaryMutation = null, Action<Bundle>? custom = null,
            Func<byte[], byte[]>? eventsBytes = null, Func<byte[], byte[]>? ownershipBytes = null, Action<JournalRecord[]>? supervisorMutation = null)
        {
            Add(id, () =>
            {
                using var b = new Bundle(caseDirectory, path, "journal-" + (++serial).ToString("D3"), mutation, summaryMutation, eventsBytes, ownershipBytes, supervisorMutation);
                Action validate = custom == null ? () => { _ = b.Validate(); } : () => custom(b);
                if (rejection == null) validate(); else Reject(validate, rejection);
            });
        }
        Add("environment_allowed", () => WorkerEnvironment.ValidateExact(expected, expected));
        Add("environment_unicode_roundtrip", () => { var e = WorkerEnvironment.Expected(@"C:\Windows", @"C:\合成\local", @"C:\合成\root"); WorkerEnvironment.ValidateExact(WorkerEnvironment.Parse(WorkerEnvironment.Build(e, e)), e); });
        Add("environment_actual_block_exact", () =>
        {
            string b = WorkerEnvironment.Build(expected, expected); var pairs = WorkerEnvironment.Parse(b);
            WorkerEnvironment.ValidateExact(pairs, expected);
            // Match complete keys. The approved DOTNET_ADD_GLOBAL_TOOLS_TO_PATH
            // switch is not a PATH search-path variable.
            Check(pairs.Count == 12 && !pairs.Any(p => p.Key.Equals("PATH", StringComparison.OrdinalIgnoreCase)), "minimal_environment");
        });
        Add("supervisor_post_start_allowed", () => WorkerEnvironment.SupervisorPreflight(expected, expected));
        string[] threats = ["DOTNET_STARTUP_HOOKS", "DOTNET_ADDITIONAL_DEPS", "DOTNET_SHARED_STORE", "DOTNET_ROOT", "DOTNET_ROOT_X64", "DOTNET_ROOT_ARM64", "DOTNET_HOST_PATH",
            "DOTNET_DiagnosticPorts", "DOTNET_BUNDLE_EXTRACT_BASE_DIR", "CORECLR_ENABLE_PROFILING", "CORECLR_PROFILER_PATH", "COMPlus_ReadyToRun", "COR_ENABLE_PROFILING",
            "COR_PROFILER", "COREHOST_TRACEFILE", "DOTNET_EventPipeOutputPath", "DOTNET_HOST_TRACEFILE"];
        foreach (string key in threats)
        {
            Add("environment_reject_" + key, () => Reject(() => WorkerEnvironment.ValidateExact(expected.Append(new(key, "synthetic-not-loaded")), expected), "environment_key_denied"));
            Add("supervisor_reject_" + key, () => Reject(() => WorkerEnvironment.SupervisorPreflight(expected.Append(new(key, "synthetic-not-loaded")), expected), "supervisor_runtime_environment_denied"));
        }
        Add("environment_case_bypass", () => Reject(() => WorkerEnvironment.ValidateExact(expected.Append(new("dotnet_startup_hooks", "x")), expected), "environment_key_denied"));
        Add("environment_duplicate_case", () => Reject(() => WorkerEnvironment.Build(expected.Append(new("temp", expected["TEMP"])), expected), "environment_duplicate_key"));
        Add("environment_missing_key", () => Reject(() => WorkerEnvironment.ValidateExact(expected.Where(p => p.Key != "TEMP"), expected), "environment_missing_key"));
        Add("environment_wrong_value", () => Reject(() => WorkerEnvironment.ValidateExact(expected.Select(p => p.Key == "TEMP" ? new(p.Key, "unapproved") : p), expected), "environment_value_denied"));
        Add("environment_extra_path", () => Reject(() => WorkerEnvironment.ValidateExact(expected.Append(new("PATH", "unapproved")), expected), "environment_key_denied"));
        Add("environment_nul_value", () => Reject(() => WorkerEnvironment.Build(expected.Select(p => p.Key == "TEMP" ? new(p.Key, "bad\0value") : p), expected), "environment_value_format"));
        Add("environment_bad_terminator", () => Reject(() => WorkerEnvironment.Parse("A=1\0"), "environment_block_terminator"));
        Add("environment_empty_entry", () => Reject(() => WorkerEnvironment.Parse("A=1\0\0B=2\0\0"), "environment_block_entry"));
        Add("environment_missing_equals", () => Reject(() => WorkerEnvironment.Parse("A\0\0"), "environment_block_entry"));
        Add("environment_bad_order", () => Reject(() => WorkerEnvironment.Parse("Z=1\0A=2\0\0"), "environment_block_order"));
        Add("environment_block_duplicate", () => Reject(() => WorkerEnvironment.Parse("A=1\0a=2\0\0"), "environment_duplicate_key"));
        Add("environment_unicode_invalid", () => Reject(() => WorkerEnvironment.Parse("A=\ud800\0\0"), "environment_unicode"));
        Add("environment_rejection_oracle", () => RejectOracle(() => Reject(() => { }, "environment_key_denied")));

        JournalCase("journal_complete");
        JournalCase("journal_sequence_gap", "journal_sequence", (e, _) => e[3] = e[3] with { Sequence = 5 });
        JournalCase("journal_sequence_duplicate", "journal_sequence", (e, _) => e[3] = e[3] with { Sequence = 3 });
        JournalCase("journal_sequence_reverse", "journal_sequence", (e, _) => (e[2], e[3]) = (e[3], e[2]));
        JournalCase("journal_run_mismatch", "journal_run", (e, _) => e[3] = e[3] with { Run = Guid.NewGuid().ToString("N") });
        JournalCase("journal_test_mismatch", "journal_test", (e, _) => e[3] = e[3] with { Test = "wrong-test" });
        JournalCase("journal_final_lf", "journal_final_lf", eventsBytes: b => b[..^1]);
        JournalCase("journal_broken_json", "journal_json", eventsBytes: _ => Encoding.UTF8.GetBytes("{broken}\n"));
        JournalCase("journal_start_missing", "journal_start", (e, _) => e[0] = e[0] with { Stage = "wrong_start" });
        JournalCase("journal_end_missing", "journal_end", (e, _) => e[^1] = e[^1] with { Stage = "wrong_end" });
        JournalCase("journal_summary_mismatch", "journal_summary", summaryMutation: s => s with { Pass = 0, Fail = 1, Exit = 1 });
        JournalCase("journal_exit_mismatch", "journal_exit", custom: b => { b.Exit = 1; b.Validate(); });
        JournalCase("ownership_missing", "journal_unavailable", custom: b => { b.RemoveOwnership(); b.Validate(); });
        JournalCase("ownership_corrupt", "journal_json", ownershipBytes: _ => Encoding.UTF8.GetBytes("{broken}\n"));
        JournalCase("journal_identity_mismatch", "journal_identity", custom: b => { using var h = new HeldEvidence(b.Request.Events with { Receipt = b.Request.Events.Receipt with { FileId = new string('0', 32) } }); });
        JournalCase("journal_unavailable", "journal_unavailable", custom: b => { using var h = new HeldEvidence(b.Request.Events, _ => throw new IOException("synthetic-reader-unavailable")); });
        JournalCase("journal_path_mismatch", "journal_path", custom: b => b.Validate(e => e with { Path = e.Path + ".wrong" }));
        JournalCase("journal_hardlink_rejected", "journal_hardlink", custom: b => b.Validate(e => e with { Receipt = e.Receipt with { Links = 2 } }));
        JournalCase("journal_reparse_rejected", "journal_reparse", custom: b => b.Validate(e => e with { Receipt = e.Receipt with { ReparseTag = 0xa000000c } }));
        JournalCase("journal_unknown_object_rejected", "ownership_zero_objects", (_, o) => o.Add(o[0] with { Sequence = 2, Stage = "object_created" }));
        JournalCase("journal_cleanup_commit_contradiction", "journal_summary", summaryMutation: s => s with { Commit = "COMMITTED" });
        foreach (string field in new[] { "Commit", "Pending", "Cleanup" })
            JournalCase("journal_consistent_but_forbidden_" + field, "summary_cleanup_commit", (e, _) =>
            {
                var summary = JournalValidation.Summary(Encoding.UTF8.GetBytes(e[^1].Data.GetProperty("Detail").GetRawText()));
                summary = field == "Commit" ? summary with { Commit = "COMMITTED" } : field == "Pending" ? summary with { Pending = "ABSENT" } : summary with { Cleanup = "OBSERVED" };
                e[^1] = e[^1] with { Data = Element(new { ElapsedMs = 1.0, Detail = summary }) };
            }, s => field == "Commit" ? s with { Commit = "COMMITTED" } : field == "Pending" ? s with { Pending = "ABSENT" } : s with { Cleanup = "OBSERVED" });
        JournalCase("journal_append_header_binding", "journal_test", custom: b => { var bytes = File.ReadAllBytes(b.Request.Events.Path); JournalValidation.ExistingHeader(bytes, b.Request.Run, "wrong-test"); });
        JournalCase("supervisor_complete", custom: b => b.ValidateSupervisor());
        JournalCase("raw_stdout_sha_mismatch", "raw_sha", custom: b => b.ValidateSupervisor(), supervisorMutation: e => e[4] = e[4] with { Data = Element(new { Outcome = "VERIFIED_SUCCESS", StdoutSHA256 = new string('0', 64), StderrSHA256 = Contract.Hash([]) }) });
        JournalCase("raw_stderr_sha_mismatch", "raw_sha", custom: b => b.ValidateSupervisor(), supervisorMutation: e => e[4] = e[4] with { Data = Element(new { Outcome = "VERIFIED_SUCCESS", StdoutSHA256 = Contract.Hash([]), StderrSHA256 = new string('0', 64) }) });
        JournalCase("supervisor_end_missing", "supervisor_end", custom: b => b.ValidateSupervisor(), supervisorMutation: e => e[^1] = e[^1] with { Stage = "UNKNOWN" });
        JournalCase("supervisor_pid_mismatch", "supervisor_process", custom: b => b.ValidateSupervisor(), supervisorMutation: e => e[1] = e[1] with { Data = Element(new WorkerBinding(4321, 123456, new string('c', 64))) });
        Add("journal_rejection_oracle", () => RejectOracle(() => Reject(() => { }, "journal_sequence")));
        Add("journal_arbitrary_exception_not_detection", () =>
        {
            bool escaped = false;
            try { Reject(() => throw new IOException("not-an-expected-rejection"), "journal_sequence"); }
            catch (IOException e) when (e is not EvidenceFailure) { escaped = true; }
            Check(escaped, "arbitrary_exception_not_detected");
        });
        var good = new PhaseTimes(5, 6, 7);
        void Deadline(string id, ObservationOutcome expectedOutcome, string expectedReason, PhaseTimes? phases = null,
            bool exited = true, double? exitedAt = 8, double now = 9, bool cancelled = false, bool success = true, bool valid = true, bool available = true) =>
            Add(id, () => { var d = ObservationDeadline.Evaluate(new FakeClock(now), phases ?? good, exited, exitedAt, cancelled, success, valid, available);
                Check(d.Outcome == expectedOutcome && d.Reason == expectedReason && d.ReleaseGate == (expectedOutcome == ObservationOutcome.VERIFIED_SUCCESS), "deadline_decision"); });
        Deadline("deadline_normal", ObservationOutcome.VERIFIED_SUCCESS, "verified");
        Deadline("deadline_case_late_exit", ObservationOutcome.TIMEOUT, "deadline_exceeded", new(30, 31, 32), exitedAt: 33, now: 34);
        Deadline("deadline_poll_success_at_limit", ObservationOutcome.TIMEOUT, "deadline_exceeded", new(30, 30, 30), exitedAt: 30, now: 30);
        Deadline("deadline_cleanup_start_unknown", ObservationOutcome.EVIDENCE_INVALID, "cleanup_start_unobserved", new(5, null, 7));
        Deadline("deadline_cleanup_end_unknown", ObservationOutcome.EVIDENCE_INVALID, "cleanup_end_unobserved", new(5, 6, null));
        Deadline("deadline_case_end_unknown", ObservationOutcome.EVIDENCE_INVALID, "case_end_unobserved", new(null, 6, 7));
        Deadline("deadline_exit_unknown", ObservationOutcome.WORKER_EXIT_UNCONFIRMED, "worker_exit_unconfirmed", exited: false, exitedAt: null, now: 60);
        Deadline("deadline_exit_late", ObservationOutcome.TIMEOUT, "deadline_exceeded", exitedAt: 60, now: 61);
        Deadline("deadline_cleanup_late", ObservationOutcome.TIMEOUT, "deadline_exceeded", new(5, 6, 45), exitedAt: 46, now: 47);
        Deadline("deadline_log_finalize_late", ObservationOutcome.TIMEOUT, "deadline_exceeded", now: 90);
        Deadline("deadline_cancel_not_retroactive_success", ObservationOutcome.TIMEOUT, "deadline_exceeded", cancelled: true);
        Deadline("deadline_test_failed", ObservationOutcome.TEST_FAILED, "test_failed", success: false);
        Deadline("deadline_evidence_invalid", ObservationOutcome.EVIDENCE_INVALID, "evidence_invalid", valid: false);
        Deadline("deadline_evidence_unavailable", ObservationOutcome.EVIDENCE_UNAVAILABLE, "evidence_unavailable", available: false);
        Deadline("deadline_phase_order", ObservationOutcome.EVIDENCE_INVALID, "phase_order", new(5, 4, 7));
        Deadline("deadline_phase_nan", ObservationOutcome.EVIDENCE_INVALID, "phase_order", new(double.NaN, 6, 7));
        Add("deadline_outer_margin", () => Check(ObservationDeadline.Case < ObservationDeadline.Cleanup && ObservationDeadline.Cleanup < ObservationDeadline.Exit &&
            ObservationDeadline.Exit < ObservationDeadline.Finalize && ObservationDeadline.Outer - ObservationDeadline.Finalize == 30, "deadline_margin"));
        Add("deadline_preparation_included", () => { bool failed = false; try { ObservationDeadline.RequireBefore(new FakeClock(30), ObservationDeadline.Case); } catch (TimeoutException) { failed = true; } Check(failed, "preparation_deadline"); });
        Add("deadline_cancellation_case_unknown", () => Check(ObservationDeadline.CancellationDue(new FakeClock(30), new(null, null, null)), "cancel_case"));
        Add("deadline_cleanup_separate", () => Check(!ObservationDeadline.CancellationDue(new FakeClock(35), new(5, 6, null)) && ObservationDeadline.CancellationDue(new FakeClock(45), new(5, 6, null)), "cleanup_independent"));
        Add("native_and_full_gates_closed", () => Check(!ObservationPaths.NativeFixtureAuthorized && !ObservationPaths.FullSuiteAuthorized, "closed_gates"));
        Add("no_mock_handles", () => Check(MockSandbox.LiveHandles == 0 && !MockSandbox.CleanupFailed, "no_mock_handles"));
        int legacyRegistered = items.Count;
        Check(legacyRegistered == 105, "legacy_hardening_catalogue");
        foreach (var item in new[] { ("path_extra", "PATH_EXTRA"), ("userpath", "USERPATH"), ("path_lowercase", "path") })
            Add("environment_key_" + item.Item1, () => Reject(() => WorkerEnvironment.ValidateExact(expected.Append(new(item.Item2, "unapproved")), expected), "environment_key_denied"));
        Add("environment_key_allowed_case", () => WorkerEnvironment.ValidateExact(WorkerEnvironment.Parse(WorkerEnvironment.Build(
            expected.Select(p => new KeyValuePair<string, string>(p.Key.ToLowerInvariant(), p.Value)), expected)), expected));
        Add("environment_key_duplicate_exact", () => Reject(() => WorkerEnvironment.ValidateExact(expected.Append(new("TEMP", expected["TEMP"])), expected), "environment_duplicate_key"));
        foreach (var item in new[] { ("empty", ""), ("equals", "PATH=EXTRA"), ("digit_initial", "1PATH"), ("nul", "PA\0TH") })
            Add("environment_key_" + item.Item1, () => Reject(() => WorkerEnvironment.ValidateExact(expected.Append(new(item.Item2, "x")), expected), "environment_key_format"));

        var fakeCounts = new SuiteCounts(105, 28, 1, 1, 1, 0, 0, 132, 1, 0);
        TerminalResult FakeTerminal(double at = 1, string? delayed = null, string? throwing = null, Exception? error = null,
            SuiteCounts? counts = null, bool unknownGate = false, bool publicationLate = false, bool publicationError = false)
        {
            var time = new FakeClock(at); var calls = new Dictionary<string, int>(StringComparer.Ordinal);
            var steps = HardeningTerminal.Order.Select(name => new TerminalStep(name, () =>
            {
                calls[name] = calls.GetValueOrDefault(name) + 1;
                if (name == delayed) time.Seconds = 91;
                if (name == throwing) throw error ?? new IOException("synthetic_dispose_failure");
                if (name == "gate_retention" && unknownGate) throw new InvalidDataException("synthetic_gate_unconfirmed");
            }, name is "journal_finalization" or "journal_flush_readback" or "journal_sealed_readback")).ToArray();
            var result = HardeningTerminal.Run(time, counts ?? fakeCounts, steps, _ =>
            {
                if (publicationLate) time.Seconds = 91;
                if (publicationError) throw new IOException("synthetic_publication_failure");
            });
            Check(calls.Count == HardeningTerminal.Order.Length && calls.Values.All(n => n == 1), "terminal_steps_no_retry");
            Check(!result.GateReleaseAuthorized && !result.AutomaticRetry && result.NextExecution == "NOT_AUTHORIZED", "terminal_no_release_or_retry");
            Check(result.Counts == (counts ?? fakeCounts), "terminal_counts_preserved");
            return result;
        }
        void TerminalCase(string id, Func<TerminalResult> runCase, string terminal, string evidence = "VALID", string gateState = "RETAINED",
            string? exceptionStep = null, string? exceptionType = null, string? exceptionReason = null, string test = "PASS") => Add(id, () =>
        {
            var result = runCase();
            Check(result.Test == test && result.Terminal == terminal && result.Evidence == evidence && result.Gate == gateState, "terminal_result");
            Check(result.Success == (test == "PASS" && terminal == "COMPLETE" && evidence == "VALID" && gateState == "RETAINED"), "terminal_success_contract");
            if (exceptionStep != null)
            {
                var failures = result.Trace.Where(e => e.Step == exceptionStep && e.Phase == "exception").ToArray();
                Check(failures.Length == 1 && failures[0].Type == exceptionType && failures[0].Reason == exceptionReason, "terminal_exact_exception");
            }
            Check(result.Trace.Any(e => e.Step == "final_deadline_check_after_publication" && e.Phase == "end"), "terminal_post_publication_check");
        });
        TerminalCase("terminal_within_deadline", () => FakeTerminal(), "COMPLETE");
        TerminalCase("terminal_journal_dispose_late", () => FakeTerminal(delayed: "journal_dispose"), "TIMEOUT");
        TerminalCase("terminal_gate_dispose_late", () => FakeTerminal(delayed: "gate_handle_dispose"), "TIMEOUT");
        TerminalCase("terminal_journal_dispose_exception", () => FakeTerminal(throwing: "journal_dispose"), "FAILED",
            exceptionStep: "journal_dispose", exceptionType: "IOException", exceptionReason: "synthetic_dispose_failure");
        TerminalCase("terminal_gate_dispose_exception", () => FakeTerminal(throwing: "gate_handle_dispose"), "FAILED",
            exceptionStep: "gate_handle_dispose", exceptionType: "IOException", exceptionReason: "synthetic_dispose_failure");
        TerminalCase("terminal_readback_failure", () => FakeTerminal(throwing: "journal_flush_readback", error: new IOException("synthetic_readback_failure")), "FAILED", "UNAVAILABLE",
            exceptionStep: "journal_flush_readback", exceptionType: "IOException", exceptionReason: "synthetic_readback_failure");
        TerminalCase("terminal_evidence_then_late", () => FakeTerminal(delayed: "gate_retention"), "TIMEOUT");
        TerminalCase("terminal_at_deadline", () => FakeTerminal(at: 90), "TIMEOUT");
        TerminalCase("terminal_late_normal_return", () => FakeTerminal(delayed: "journal_finalization"), "TIMEOUT");
        TerminalCase("terminal_pass_gate_retained", () => FakeTerminal(), "COMPLETE");
        TerminalCase("terminal_fail_gate_retained", () => FakeTerminal(counts: fakeCounts with { Pass = 0, Fail = 1 }), "COMPLETE", test: "FAIL");
        TerminalCase("terminal_timeout_gate_retained", () => FakeTerminal(at: 91), "TIMEOUT");
        TerminalCase("terminal_unknown_no_retry", () => FakeTerminal(unknownGate: true), "UNKNOWN", gateState: "UNKNOWN",
            exceptionStep: "gate_retention", exceptionType: "InvalidDataException", exceptionReason: "synthetic_gate_unconfirmed");
        TerminalCase("terminal_counts_unchanged", () => FakeTerminal(throwing: "journal_dispose", counts: fakeCounts with { Pass = 0, Fail = 1 }), "FAILED", test: "FAIL",
            exceptionStep: "journal_dispose", exceptionType: "IOException", exceptionReason: "synthetic_dispose_failure");
        TerminalCase("terminal_publication_late", () => FakeTerminal(publicationLate: true), "TIMEOUT");
        TerminalCase("terminal_publication_exception", () => FakeTerminal(publicationError: true), "FAILED",
            exceptionStep: "result_publication", exceptionType: "IOException", exceptionReason: "synthetic_publication_failure");
        TerminalCase("terminal_root_dispose_late", () => FakeTerminal(delayed: "root_handle_dispose"), "TIMEOUT");
        TerminalCase("terminal_sealed_readback_failure", () => FakeTerminal(throwing: "journal_sealed_readback", error: new InvalidDataException("synthetic_sealed_readback_failure")), "FAILED", "INVALID",
            exceptionStep: "journal_sealed_readback", exceptionType: "InvalidDataException", exceptionReason: "synthetic_sealed_readback_failure");
        TerminalCase("terminal_arbitrary_exception_not_success", () => FakeTerminal(throwing: "journal_dispose", error: new InvalidOperationException("synthetic_dispose_failure")), "FAILED",
            exceptionStep: "journal_dispose", exceptionType: "InvalidOperationException", exceptionReason: "synthetic_dispose_failure");
        Check(items.Select(i => i.Id).Distinct(StringComparer.Ordinal).Count() == items.Count, "unique_hardening_ids");
        Check(items.Count - legacyRegistered == 28 && ApprovedPrechecks.All(id => items.Any(i => i.Id == id)), "limited_catalogue");
        var selected = requested.Select(id => items.Single(i => i.Id == id)).ToArray();
        int executed = 0, pass = 0, fail = 0, notRun = 0, legacyExecuted = 0, newExecuted = 0; bool stopped = false;
        const string suiteId = "hardening_policy_suite";
        journal.Write(run, suiteId, "suite_start", new { RegisteredLegacy = legacyRegistered, RegisteredNew = items.Count - legacyRegistered,
            Selected = requested, NonfixtureOnly = true, PreCLRProtectionProven = false, HardStopGuaranteed = false,
            source, GateReceipt = receipt, PersistedReceipt = persistedReceipt, NextExecution = "NOT_AUTHORIZED" });
        journal.Write(run, suiteId, "catalogue", items.Select((i, index) => new { i.Id, Origin = index < legacyRegistered ? "LEGACY_105" : "NEW_TERMINAL_OR_KEY",
            Status = requested.Contains(i.Id, StringComparer.Ordinal) ? "SELECTED" : "NOT_SELECTED" }).ToArray());
        foreach (var item in selected)
        {
            if (stopped || clock.Seconds >= ObservationDeadline.Exit) { notRun++; stopped = true; journal.Write(run, suiteId, "test_not_run", new { item.Id }); continue; }
            journal.Write(run, suiteId, "test_start", new { item.Id }); executed++;
            if (items.FindIndex(i => i.Id == item.Id) < legacyRegistered) legacyExecuted++; else newExecuted++;
            Exception? failure = null;
            try { item.Body(); pass++; } catch (Exception error) { failure = error; fail++; }
            journal.Write(run, suiteId, failure == null ? "test_pass" : "test_fail", new { item.Id, Type = failure?.GetType().Name,
                Reason = failure == null ? null : failure is CheckFailure ? failure.Message : "unexpected_exception" });
        }
        var counts = new SuiteCounts(legacyRegistered, items.Count - legacyRegistered, selected.Length, executed, pass, fail, notRun,
            items.Count - selected.Length, legacyExecuted, newExecuted);
        Check(executed == pass + fail && selected.Length == executed + notRun && legacyExecuted + newExecuted == executed, "limited_counts");
        Check(MockSandbox.LiveHandles == 0 && !MockSandbox.CleanupFailed, "no_native_mock_handles");
        string journalPath = Path.Combine(path, "results.jsonl"); var journalBinding = new JournalBinding(journalPath, journal.Receipt);
        DurableLog terminalJournal = journal;
        SafeFileHandle terminalGate = gate, terminalDirectory = directory;
        ReadPin terminalRoot = root;
        EvidenceSnapshot? finalSnapshot = null;
        ObjectReceipt? summaryReceipt = null;
        var terminalSteps = new TerminalStep[]
        {
            new("journal_finalization", () => { terminalJournal.Write(run, suiteId, "suite_summary", counts); summaryReceipt = CaseSupervisor.WriteFile(terminalDirectory, "summary.json", Bytes(counts)); }, true),
            new("journal_flush_readback", () => { finalSnapshot = terminalJournal.FinalSnapshot(journalPath); ValidateSuite(finalSnapshot, run, requested, counts, source, gateReceipt); }, true),
            new("journal_dispose", () => { try { terminalJournal.Dispose(); Check(terminalJournal.ResourcesClosed, "journal_handles_unconfirmed"); } finally { journal = null; } }),
            new("journal_sealed_readback", () =>
            {
                using var held = new HeldEvidence(journalBinding);
                Check(finalSnapshot != null && held.Snapshot.Bytes.SequenceEqual(finalSnapshot.Bytes), "suite_sealed_bytes");
                ValidateSuite(held.Snapshot, run, requested, counts, source, gateReceipt);
            }, true),
            new("gate_handle_dispose", () => { try { terminalGate.Dispose(); Check(terminalGate.IsClosed, "gate_handle_unconfirmed"); } finally { gate = null; } }),
            new("gate_retention", () =>
            {
                using var held = new ReadPin(gatePath, false);
                Check(ObservationNative.Inspect(held.Handle, "file") == gateReceipt && ObservationNative.CreatedUTC(held.Handle) == createdAt, "gate_retention_identity");
            }),
            new("directory_handle_dispose", () => { try { terminalDirectory.Dispose(); Check(terminalDirectory.IsClosed, "directory_handle_unconfirmed"); } finally { directory = null; } }),
            new("root_handle_dispose", () => { try { terminalRoot.Dispose(); Check(terminalRoot.Handle.IsClosed, "root_handle_unconfirmed"); } finally { root = null; } })
        };
        terminalOwnsCleanup = true;
        var result = HardeningTerminal.Run(clock, counts, terminalSteps, candidate => Console.WriteLine(JsonSerializer.Serialize(new
        {
            Run = run, Mode = "LIMITED_PRECHECK_ONLY", Candidate = candidate, ProvisionalUntilProcessExit = true,
            FinalDeadlineRecheckedAfterPublication = true, GateReleaseAuthorized = false, NextExecution = "NOT_AUTHORIZED",
            GateIdentity = gateId, NativeFixtures = 0, ChildWorkerStarted = false, LegacyFullSuiteRun = false, PreCLRProtectionProven = false
            , JournalBinding = journalBinding, SummaryReceipt = summaryReceipt,
            JournalSHA256 = finalSnapshot == null ? null : Contract.Hash(finalSnapshot.Bytes), SummarySHA256 = Contract.Hash(Bytes(counts)),
            GateReceiptSHA256 = Contract.Hash(Bytes(receipt)), SourceFingerprint = source.AllChangesSHA256,
            OwnedHandlesConfirmedClosed = terminalJournal.ResourcesClosed && terminalGate.IsClosed && terminalDirectory.IsClosed && terminalRoot.Handle.IsClosed
        })));
        // Exit 0 is a LOCAL observation only. Overall success also requires the
        // external owner to observe this exact process exit, validate persisted
        // evidence/receipt and flush/read back its own final result record.
        return result.Exit; // No fallible I/O or owned-resource Dispose follows.
        }
        finally
        {
            if (!terminalOwnsCleanup)
            {
                // Setup/log failures never reach a success decision. Attempt
                // every release; leave intent, original receipt and gate intact.
                try { journal?.Dispose(); }
                finally { try { gate?.Dispose(); } finally { try { directory?.Dispose(); } finally { root?.Dispose(); } } }
            }
        }
    }

    private static void ValidateSuite(EvidenceSnapshot snapshot, string run, string[] selected, SuiteCounts counts,
        SourceBinding source, ObjectReceipt gate)
    {
        var rows = JournalValidation.Records(snapshot.Bytes, run, "hardening_policy_suite");
        Check(rows[0].Stage == "suite_start" && rows[1].Stage == "catalogue" && rows[^1].Stage == "suite_summary", "suite_journal_boundaries");
        Check(rows[0].Data.GetProperty("Selected").EnumerateArray().Select(v => v.GetString()).SequenceEqual(selected), "suite_selection_binding");
        Check(Bytes(Contract.Parse<SourceBinding>(Encoding.UTF8.GetBytes(rows[0].Data.GetProperty("source").GetRawText()))).SequenceEqual(Bytes(source)), "suite_source_binding");
        Check(Contract.Parse<ObjectReceipt>(Encoding.UTF8.GetBytes(rows[0].Data.GetProperty("GateReceipt").GetProperty("Receipt").GetRawText())) == gate, "suite_gate_binding");
        Check(Contract.Parse<SuiteCounts>(Encoding.UTF8.GetBytes(rows[^1].Data.GetRawText())) == counts, "suite_summary_binding");
        var catalogue = rows[1].Data.EnumerateArray().ToArray();
        Check(catalogue.Length == counts.RegisteredLegacy + counts.RegisteredNew && catalogue.Select(v => v.GetProperty("Id").GetString()).Distinct().Count() == catalogue.Length, "suite_catalogue");
        Check(catalogue.Count(v => v.GetProperty("Status").GetString() == "NOT_SELECTED") == counts.NotSelected &&
            catalogue.Where(v => v.GetProperty("Status").GetString() == "SELECTED").Select(v => v.GetProperty("Id").GetString()).ToHashSet().SetEquals(selected), "suite_not_selected");
        int index = 2, observedPass = 0, observedFail = 0, observedNotRun = 0;
        foreach (string id in selected)
        {
            var start = rows[index++]; Check(start.Data.GetProperty("Id").GetString() == id, "suite_test_id");
            if (start.Stage == "test_not_run") { observedNotRun++; continue; }
            Check(start.Stage == "test_start", "suite_test_start"); var end = rows[index++];
            Check(end.Data.GetProperty("Id").GetString() == id && end.Stage is "test_pass" or "test_fail", "suite_test_result");
            if (end.Stage == "test_pass") observedPass++; else observedFail++;
        }
        Check(index == rows.Length - 1 && observedPass == counts.Pass && observedFail == counts.Fail && observedNotRun == counts.NotRun, "suite_result_counts");
    }
}
