using System.Text;
using System.Text.Json;
using J1AI.SmokeMigration;

namespace J1AI.SmokeMigration.Tests;

internal sealed class EvidenceFailure(ObservationOutcome outcome, string reason) : IOException(reason)
{ internal ObservationOutcome Outcome => outcome; internal string Reason => Message; }
internal sealed record JournalBinding(string Path, ObjectReceipt Receipt);
internal sealed record EvidenceSnapshot(string Path, ObjectReceipt Receipt, byte[] Bytes);
internal sealed record JournalRecord(long Sequence, string Run, string Test, DateTimeOffset UTC, long Monotonic, string Stage, JsonElement Data);
internal sealed record WorkerSummary(string Run, string Test, int RegisteredCatalogue, int Selected, int NotSelected,
    int Executed, int Pass, int Fail, int Detected, int NotRun, int Exit, int Handles, bool CleanupFailed,
    int CreatedObjects, int CleanedMocks, string Commit, string Pending, string Cleanup);
internal sealed record VerifiedWorker(WorkerSummary Summary, PhaseTimes Phases, string EventsSHA256, string OwnershipSHA256, bool TestSucceeded);

// Held across final validation AND successful gate removal. ReadPin denies new
// write/delete sharing; compare the ORIGINAL creation receipt, not a fresh ID.
// This does not claim protection against every same-SID/native bypass or edits
// after the handles are released.
internal sealed class HeldEvidence : IDisposable
{
    private readonly ReadPin pin;
    internal EvidenceSnapshot Snapshot { get; }
    internal HeldEvidence(JournalBinding expected, Func<JournalBinding, ReadPin>? testOpen = null)
    {
        try { pin = testOpen == null ? new(expected.Path, false) : testOpen(expected); }
        catch (InvalidDataException e) when (e.Message.StartsWith("read_handle:", StringComparison.Ordinal))
        { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_UNAVAILABLE, "journal_unavailable"); }
        catch (InvalidDataException) { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, "journal_file_attributes"); }
        catch (IOException) { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_UNAVAILABLE, "journal_unavailable"); }
        try
        {
            var receipt = ObservationNative.Inspect(pin.Handle, "file");
            JournalValidation.Identity(expected, pin.Path, receipt);
            byte[] bytes = pin.Bytes();
            JournalValidation.Identity(expected, pin.Path, ObservationNative.Inspect(pin.Handle, "file"));
            Snapshot = new(pin.Path, receipt, bytes);
        }
        catch { pin.Dispose(); throw; }
    }
    public void Dispose() => pin.Dispose();
}

internal static class JournalValidation
{
    internal static void Require(bool condition, string code)
    { if (!condition) throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, code); }
    internal static void Identity(JournalBinding expected, string path, ObjectReceipt actual)
    {
        Require(path.Equals(expected.Path, StringComparison.Ordinal), "journal_path");
        Require(actual.ReparseTag == 0, "journal_reparse"); Require(actual.Links == 1, "journal_hardlink");
        Require(actual == expected.Receipt, "journal_identity");
    }
    private static void Keys(JsonElement value, params string[] names) => Require(value.ValueKind == JsonValueKind.Object &&
        value.EnumerateObject().Select(p => p.Name).ToHashSet(StringComparer.Ordinal).SetEquals(names) && value.EnumerateObject().Count() == names.Length, "journal_schema");
    internal static JournalRecord[] Records(byte[] bytes, string run, string test)
    {
        Require(bytes.Length is > 0 and <= 16 * 1024 * 1024, "journal_size");
        Require(bytes[^1] == 10, "journal_final_lf"); string text;
        try { text = new UTF8Encoding(false, true).GetString(bytes); }
        catch (DecoderFallbackException) { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, "journal_utf8"); }
        string[] lines = text[..^1].Split('\n'); var rows = new List<JournalRecord>(); long prior = -1;
        foreach (string line in lines)
        {
            Require(line.Length > 0, "journal_empty_record"); JournalRecord row;
            try
            {
                using var d = JsonDocument.Parse(line);
                Keys(d.RootElement, "Sequence", "Run", "Test", "UTC", "Monotonic", "Stage", "Data");
                row = Contract.Parse<JournalRecord>(Encoding.UTF8.GetBytes(line));
            }
            catch (JsonException) { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, "journal_json"); }
            catch (InvalidDataException) { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, "journal_json"); }
            Require(row.Sequence == rows.Count + 1, "journal_sequence");
            Require(row.Run == run, "journal_run"); Require(row.Test == test, "journal_test");
            Require(row.UTC.Offset == TimeSpan.Zero && row.UTC > DateTimeOffset.UnixEpoch && row.Monotonic >= 0 && row.Monotonic >= prior, "journal_time");
            Require(!string.IsNullOrEmpty(row.Stage), "journal_stage"); prior = row.Monotonic; rows.Add(row);
        }
        return rows.ToArray();
    }
    internal static void ExistingHeader(byte[] bytes, string run, string test)
    {
        var rows = Records(bytes, run, test);
        Require(rows.Length == 1 && rows[0].Stage == "journal_prepared", "journal_existing_header");
    }
    private static JsonElement Detail(JournalRecord row)
    {
        Require(row.Data.ValueKind == JsonValueKind.Object && row.Data.TryGetProperty("ElapsedMs", out var elapsed) &&
            elapsed.TryGetDouble(out double value) && double.IsFinite(value) && value >= 0 && row.Data.TryGetProperty("Detail", out _), "journal_detail");
        return row.Data.GetProperty("Detail");
    }
    internal static WorkerSummary Summary(byte[] bytes)
    {
        try
        {
            using var d = JsonDocument.Parse(bytes);
            Keys(d.RootElement, "Run", "Test", "RegisteredCatalogue", "Selected", "NotSelected", "Executed", "Pass", "Fail", "Detected", "NotRun", "Exit", "Handles", "CleanupFailed", "CreatedObjects", "CleanedMocks", "Commit", "Pending", "Cleanup");
            return Contract.Parse<WorkerSummary>(bytes);
        }
        catch (JsonException) { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, "summary_json"); }
        catch (InvalidDataException) { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, "summary_json"); }
    }
    internal static VerifiedWorker Worker(RunRequest request, EvidenceSnapshot events, EvidenceSnapshot ownership, byte[] summaryBytes, uint actualExit, int expectedPid)
    {
        try { return WorkerCore(request, events, ownership, summaryBytes, actualExit, expectedPid); }
        catch (EvidenceFailure) { throw; }
        catch (Exception e) when (e is JsonException or KeyNotFoundException or InvalidOperationException or InvalidDataException or ArgumentException)
        { throw new EvidenceFailure(ObservationOutcome.EVIDENCE_INVALID, "journal_record_contract"); }
    }
    private static VerifiedWorker WorkerCore(RunRequest request, EvidenceSnapshot events, EvidenceSnapshot ownership, byte[] summaryBytes, uint actualExit, int expectedPid)
    {
        Require(!request.FixtureRequired && !ObservationPaths.NativeFixtureAuthorized, "validator_nonfixture_only");
        Identity(request.Events, events.Path, events.Receipt); Identity(request.Ownership, ownership.Path, ownership.Receipt);
        var rows = Records(events.Bytes, request.Run, request.Test); var owns = Records(ownership.Bytes, request.Run, request.Test);
        Require(rows[0].Stage == "journal_prepared", "journal_start"); Require(rows[^1].Stage == "worker_summary", "journal_end");
        string[] stages = ["journal_prepared", "worker_started", "test_start", "assertion_result", "test_end", "cleanup_start", "cleanup_complete", "worker_summary"];
        Require(rows.Select(r => r.Stage).SequenceEqual(stages), "journal_stage_order");
        Require(owns.Length == 1 && owns[0].Stage == "journal_prepared", "ownership_zero_objects");
        Require(owns[0].Data.GetProperty("CreationIntentIsNotAtomicWithCreation").GetBoolean() && !owns[0].Data.GetProperty("AutomaticRecoveryAuthorized").GetBoolean(), "ownership_header");
        Require(JsonSerializer.SerializeToUtf8Bytes(Contract.Parse<SourceBinding>(Encoding.UTF8.GetBytes(rows[0].Data.GetRawText())))
            .SequenceEqual(JsonSerializer.SerializeToUtf8Bytes(request.Source)), "journal_source");
        var started = Detail(rows[1]);
        Require(!started.GetProperty("FixtureRequired").GetBoolean(), "journal_fixture");
        Require(started.GetProperty("Process").GetInt32() == expectedPid, "journal_worker_pid");
        Require(JsonSerializer.SerializeToUtf8Bytes(Contract.Parse<SourceBinding>(Encoding.UTF8.GetBytes(started.GetProperty("Source").GetRawText())))
            .SequenceEqual(JsonSerializer.SerializeToUtf8Bytes(request.Source)), "journal_worker_source");
        var environment = Contract.Parse<Dictionary<string, string>>(Encoding.UTF8.GetBytes(started.GetProperty("Environment").GetRawText()));
        var approved = WorkerEnvironment.Parse(request.EnvironmentBlock).ToDictionary(p => p.Key, p => p.Value, StringComparer.OrdinalIgnoreCase);
        WorkerEnvironment.ValidateExact(environment, approved);
        Require(WorkerEnvironment.Build(environment, approved) == request.EnvironmentBlock, "journal_environment");
        var start = Detail(rows[2]); Require(start.GetProperty("Name").GetString() == request.Test && !start.GetProperty("FixtureRequired").GetBoolean() && start.GetProperty("ExpectedAssertion").ValueKind == JsonValueKind.Null, "journal_test_start");
        var result = Detail(rows[3]); string? assertion = result.GetProperty("Result").GetString();
        Require(assertion is "PASS" or "FAIL", "journal_assertion");
        var ended = Detail(rows[4]); Require(ended.GetProperty("Name").GetString() == request.Test && ended.GetProperty("Handles").GetInt32() == 0 && !ended.GetProperty("CleanupFailed").GetBoolean(), "journal_test_end");
        foreach (var row in rows.Skip(5).Take(2))
        { var detail = Detail(row); Require(detail.GetProperty("CreatedObjects").GetInt32() == 0 && detail.GetProperty("Handles").GetInt32() == 0 && !detail.GetProperty("CleanupFailed").GetBoolean(), "journal_cleanup"); }
        var summary = Summary(summaryBytes); var terminal = Summary(Encoding.UTF8.GetBytes(Detail(rows[^1]).GetRawText()));
        Require(summary == terminal, "journal_summary");
        Require(summary.Run == request.Run && summary.Test == request.Test && summary.RegisteredCatalogue == 69 && summary.Selected == 1 && summary.NotSelected == 68, "summary_binding");
        Require(summary.Exit == actualExit, "journal_exit");
        Require(summary.Executed == 1 && summary.Pass is 0 or 1 && summary.Fail is 0 or 1 && summary.Pass + summary.Fail == 1 && summary.Detected == 0 && summary.NotRun == 0, "summary_counts");
        Require(summary.Handles == 0 && !summary.CleanupFailed && summary.CreatedObjects == 0 && summary.CleanedMocks == 0 && summary.Commit == "NOT_APPLICABLE" && summary.Pending == "NOT_APPLICABLE" && summary.Cleanup == "NO_MOCK_CREATED", "summary_cleanup_commit");
        bool success = summary.Pass == 1;
        Require(assertion == (success ? "PASS" : "FAIL") && summary.Exit == (success ? 0 : 1), "summary_result");
        return new(summary, new(ObservationClock.At(request.StartTimestamp, rows[4].Monotonic), ObservationClock.At(request.StartTimestamp, rows[5].Monotonic), ObservationClock.At(request.StartTimestamp, rows[6].Monotonic)), Contract.Hash(events.Bytes), Contract.Hash(ownership.Bytes), success);
    }
    internal static void Supervisor(RunRequest request, JournalBinding binding, EvidenceSnapshot snapshot, VerifiedWorker verified,
        uint actualExit, string stdout, string stderr, string summaryHash, WorkerBinding process)
    {
        Identity(binding, snapshot.Path, snapshot.Receipt); var rows = Records(snapshot.Bytes, request.Run, request.Test);
        Require(rows[0].Stage == "before_worker", "supervisor_start"); Require(rows[^1].Stage == "supervisor_complete", "supervisor_end");
        Require(rows.Select(r => r.Stage).SequenceEqual(new[] { "before_worker", "worker_created", "worker_permitted", "worker_exited", "final_observation", "supervisor_complete" }), "supervisor_stage_order");
        Require(rows[0].Data.GetProperty("RunDirectory").GetString() == request.RunDirectoryIdentity &&
            JsonSerializer.SerializeToUtf8Bytes(Contract.Parse<SourceBinding>(Encoding.UTF8.GetBytes(rows[0].Data.GetProperty("source").GetRawText())))
            .SequenceEqual(JsonSerializer.SerializeToUtf8Bytes(request.Source)), "supervisor_source");
        Require(Contract.Parse<WorkerBinding>(Encoding.UTF8.GetBytes(rows[1].Data.GetRawText())) == process, "supervisor_process");
        Require(rows[3].Data.GetProperty("ActualExitCode").GetUInt32() == actualExit, "supervisor_exit");
        var final = rows[4].Data;
        Require(final.GetProperty("StdoutSHA256").GetString() == stdout && final.GetProperty("StderrSHA256").GetString() == stderr, "raw_sha");
        Require(final.GetProperty("EventsSHA256").GetString() == verified.EventsSHA256 && final.GetProperty("OwnershipSHA256").GetString() == verified.OwnershipSHA256 && final.GetProperty("SummarySHA256").GetString() == summaryHash, "evidence_sha");
        Require(Summary(Encoding.UTF8.GetBytes(final.GetProperty("Summary").GetRawText())) == verified.Summary, "supervisor_summary");
        Require(final.GetProperty("Outcome").GetString() == "VERIFIED_SUCCESS" && rows[^1].Data.GetProperty("Outcome").GetString() == "VERIFIED_SUCCESS", "supervisor_outcome");
        Require(verified.TestSucceeded, "supervisor_test_failed");
    }
}
