using System.Diagnostics;

namespace J1AI.SmokeMigration.Tests;

internal enum ObservationOutcome { VERIFIED_SUCCESS, TEST_FAILED, EVIDENCE_INVALID, EVIDENCE_UNAVAILABLE, WORKER_EXIT_UNCONFIRMED, TIMEOUT }
internal sealed record ObservationDecision(ObservationOutcome Outcome, string Reason)
{ internal bool ReleaseGate => Outcome == ObservationOutcome.VERIFIED_SUCCESS; }
internal interface IObservationClock { double Seconds { get; } }
internal sealed class ObservationClock(long origin) : IObservationClock
{
    internal long Origin => origin;
    public double Seconds => Stopwatch.GetElapsedTime(origin).TotalSeconds;
    internal static ObservationClock Start() => new(Stopwatch.GetTimestamp());
    internal static double At(long origin, long timestamp) => Stopwatch.GetElapsedTime(origin, timestamp).TotalSeconds;
}
internal sealed record PhaseTimes(double? CaseEnded, double? CleanupStarted, double? CleanupEnded);
internal static class ObservationDeadline
{
    // Absolute offsets from managed Main entry, including preparation. These
    // diagnostic limits authorize NO Native/full-suite execution. Native I/O
    // may block: these are observation deadlines, not a hard-stop guarantee.
    internal const double Case = 30, Cleanup = 45, Exit = 60, Finalize = 90, Outer = 120;
    internal static ObservationDecision Evaluate(IObservationClock clock, PhaseTimes phases, bool exitConfirmed,
        double? exitObservedAt, bool cancelled, bool testSucceeded, bool evidenceValid = true, bool evidenceAvailable = true)
    {
        if (!exitConfirmed) return new(ObservationOutcome.WORKER_EXIT_UNCONFIRMED, "worker_exit_unconfirmed");
        if (!evidenceAvailable) return new(ObservationOutcome.EVIDENCE_UNAVAILABLE, "evidence_unavailable");
        if (!evidenceValid) return new(ObservationOutcome.EVIDENCE_INVALID, "evidence_invalid");
        if (cancelled || clock.Seconds >= Finalize || exitObservedAt == null || exitObservedAt >= Exit ||
            phases.CaseEnded >= Case || phases.CleanupEnded >= Cleanup)
            return new(ObservationOutcome.TIMEOUT, "deadline_exceeded");
        if (phases.CaseEnded == null) return new(ObservationOutcome.EVIDENCE_INVALID, "case_end_unobserved");
        if (phases.CleanupStarted == null) return new(ObservationOutcome.EVIDENCE_INVALID, "cleanup_start_unobserved");
        if (phases.CleanupEnded == null) return new(ObservationOutcome.EVIDENCE_INVALID, "cleanup_end_unobserved");
        double[] times = [phases.CaseEnded.Value, phases.CleanupStarted.Value, phases.CleanupEnded.Value, exitObservedAt.Value, clock.Seconds];
        if (times.Any(t => !double.IsFinite(t) || t < 0) || !times.SequenceEqual(times.Order()))
            return new(ObservationOutcome.EVIDENCE_INVALID, "phase_order");
        return testSucceeded ? new(ObservationOutcome.VERIFIED_SUCCESS, "verified") : new(ObservationOutcome.TEST_FAILED, "test_failed");
    }
    internal static bool CancellationDue(IObservationClock clock, PhaseTimes observed) =>
        clock.Seconds >= Case && observed.CaseEnded == null || clock.Seconds >= Cleanup && observed.CleanupEnded == null;
    internal static void RequireBefore(IObservationClock clock, double deadline)
    { if (clock.Seconds >= deadline) throw new TimeoutException("observation_deadline"); }
}
