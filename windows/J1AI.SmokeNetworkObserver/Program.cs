using System.Diagnostics;
using System.Text.Json;

namespace J1AI.SmokeNetworkObserver;

public sealed class FormalSmokeStop(ApprovalPlan plan) : IStop
{
    public async Task<bool> RequestAsync(string identity, TimeSpan timeout)
    {
        if (identity != Observation.Identity || identity != plan.Identity || timeout > TimeSpan.FromSeconds(10) || timeout < TimeSpan.FromSeconds(2)) return false;
        // No raw event creation/signaling or PID discovery. The unchanged runner
        // validates manifest, RUNNING+intent, identity and opens its existing event.
        Approval.Validate(plan, false);
        using var command = OwnedStopCommand.Start(plan.Contract.Dotnet, plan.Contract.Runner);
        bool acknowledged = await command.Wait(timeout - TimeSpan.FromSeconds(1));
        bool helperEnded = await command.CloseAndConfirm(TimeSpan.FromSeconds(1));
        return acknowledged && helperEnded;
    }
}

public static class Program
{
    public static int Main(string[] args)
    {
        try
        {
            if (args is ["--help"] or [])
            {
                Console.WriteLine("Independent fixed-synthetic TCP observer. Does not launch GUI/backend.\n" +
                    "--plan <approved-future-absolute-evidence-directory> : read-only JSON plan and SHA; no monitoring/files.\n" +
                    "--observe <plan.json> --approve <exact-plan-file-sha256> : separately authorized monitoring only.\n" +
                    "Wait for OBSERVER_READY before manually launching the frozen Smoke runner.\n" +
                    "This implementation task does NOT authorize --observe or another GUI run.");
                return 0;
            }
            Approval.Require(OperatingSystem.IsWindows(), "windows_only");
            if (args is ["--plan", var evidence])
            {
                var plan = Approval.Describe(FindRepository(), evidence);
                byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(plan, Approval.Json);
                Console.WriteLine(System.Text.Encoding.UTF8.GetString(bytes));
                Console.WriteLine("PLAN_SHA256=" + Approval.Hash(bytes));
                return 0;
            }
            if (args is ["--observe", var path, "--approve", var sha])
            {
                Approval.Require(Approval.FileHash(path) == sha, "approval_sha_mismatch");
                var plan = Approval.Read<ApprovalPlan>(path);
                Approval.Validate(plan, true);
                // One observer per fixed identity. Mutex ownership stays on this
                // dedicated thread (async continuations must not release a Mutex).
                using var single = new Mutex(false, @"Local\J1AI.SmokeNetworkObserver." + Observation.Identity);
                bool owned;
                try { owned = single.WaitOne(0); }
                catch (AbandonedMutexException) { single.ReleaseMutex(); throw new IOException("observer_abandoned_review_required"); }
                Approval.Require(owned, "observer_busy_or_abandoned");
                try { return Observe(plan).GetAwaiter().GetResult(); }
                finally { single.ReleaseMutex(); }
            }
            throw new InvalidDataException("arguments_invalid");
        }
        catch { Console.Error.WriteLine("OBSERVER_INCONCLUSIVE: preparation or observation failed; no success receipt implied."); return 1; }
    }
    private static string FindRepository()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d != null; d = d.Parent)
            if (Directory.Exists(Path.Combine(d.FullName, ".git")) && File.Exists(Path.Combine(d.FullName, "scripts", "launch_dashboard.py"))) return d.FullName;
        throw new IOException("repository_not_found");
    }
    private static async Task<int> Observe(ApprovalPlan plan)
    {
        using var evidence = new FileEvidence(plan);
        using var collector = new WindowsCollector(plan);
        var observation = new Observation(plan.Contract, evidence, new FormalSmokeStop(plan));
        var clock = Stopwatch.StartNew();
        long sequence = 0;
        try
        {
            observation.Ready();
            // Demonstrate collector readiness BEFORE inviting the operator to
            // launch. Baseline must contain no existing fixed worker/runtime.
            var baseline = await collector.CollectAsync(++sequence, CancellationToken.None);
            await observation.Accept(baseline);
            if (baseline.Processes.Length != 0 || baseline.Run != null || baseline.CollectionErrors.Length != 0 || observation.State != Phase.OBSERVING)
                throw new IOException("baseline_not_empty_or_unavailable");
            Console.WriteLine("OBSERVER_READY: bounded OS TCP scope, fixed synthetic identity only.");
            while (clock.Elapsed < TimeSpan.FromSeconds(plan.MaximumSessionSeconds))
            {
                await Task.Delay(plan.PeriodMs);
                var snapshot = await collector.CollectAsync(++sequence, CancellationToken.None);
                await observation.Accept(snapshot);
                if (snapshot.EndConfirmed)
                {
                    var summary = await observation.Complete(snapshot.RuntimeEventConfirmed);
                    Console.WriteLine(summary.Result.ToString());
                    return summary.Result == Result.PASS_OBSERVED_SCOPE ? 0 : 1;
                }
            }
            await observation.Fail(Phase.GAP, "session_deadline");
        }
        catch { await observation.Fail(Phase.CRASH, "collector_stopped_or_exception"); }
        await observation.Complete(false);
        return 1;
    }
}
