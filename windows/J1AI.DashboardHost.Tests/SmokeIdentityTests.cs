using System.Diagnostics;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

// Real Windows child/Job/pipe faults only; no WebView2, SDK environment or UDF.
internal static class SmokeIdentityTests
{
    internal static List<(string Name, Func<Task> Run)> Cases(string python, string launcher) =>
    [
        ("smoke_helper_normal_common_deadline_cleanup", () => Normal(python, launcher)),
        Fault("smoke_helper_never_exits_timeout", python, "import time; time.sleep(60)", "identity_timeout"),
        Fault("smoke_helper_exits_descendant_holds_stdout", python, Descendant(true, false), "identity_timeout", stdoutHeld: true),
        Fault("smoke_helper_exits_descendant_holds_stderr", python, Descendant(false, true), "identity_timeout", stderrHeld: true),
        Fault("smoke_helper_stdout_overflow_fail_fast", python, "import os,time; os.write(1,b'x'*65536); time.sleep(60)", "identity_stdout_limit"),
        Fault("smoke_helper_stderr_overflow_fail_fast", python, "import os,time; os.write(2,b'x'*65536); time.sleep(60)", "identity_stderr_limit"),
        Fault("smoke_helper_both_streams_overflow_fail_fast", python,
            "import os,threading,time; threading.Thread(target=lambda:os.write(1,b'x'*65536)).start(); os.write(2,b'x'*65536); time.sleep(60)", "either_limit"),
        Fault("smoke_helper_exact_output_limit_plus_one_rejected", python,
            $"import os,time; os.write(1,b'x'*{SmokeIdentityHelper.OutputLimit + 1}); time.sleep(60)", "identity_stdout_limit"),
        Fault("smoke_helper_partial_output_timeout", python, "import os,time; os.write(1,b'['); time.sleep(60)", "identity_timeout"),
        Fault("smoke_helper_nonzero_exit_cleanup", python, "raise SystemExit(7)", "identity_exit"),
        Fault("smoke_helper_nonempty_stderr_rejected", python, "import os; os.write(2,b'synthetic-error')", "identity_failure"),
        ("smoke_helper_old_twelve_second_pipe_rejected_at_ten_seconds", () => FaultRun(python,
            Descendant(true, true), "identity_timeout", TimeSpan.FromSeconds(10), true, true)),
        ("smoke_helper_timeout_then_identity_preflight_retry", () => Retry(python, launcher)),
        ("smoke_helper_timeout_does_not_kill_unrelated_child", () => Unrelated(python)),
        ("smoke_helper_failed_spawn_reclaims_handles", SpawnFailure),
        ("smoke_helper_repeated_timeouts_no_handle_growth", () => Handles(python)),
    ];
    private static (string, Func<Task>) Fault(string name, string python, string body, string expected,
        bool stdoutHeld = false, bool stderrHeld = false) =>
        (name, () => FaultRun(python, body, expected, TimeSpan.FromSeconds(1), stdoutHeld, stderrHeld));
    private static string Descendant(bool stdout, bool stderr) =>
        "import subprocess,sys; subprocess.Popen([sys.executable,'-I','-S','-B','-c','import time; time.sleep(12)']," +
        $"stdin=subprocess.DEVNULL,stdout={(stdout ? "None" : "subprocess.DEVNULL")},stderr={(stderr ? "None" : "subprocess.DEVNULL")},creationflags=subprocess.CREATE_NO_WINDOW)";
    private static string Script(string root, string body)
    {
        string script = Path.Combine(root, "synthetic_identity.py");
        File.WriteAllText(script, "import hashlib\ndef instance_id(root):\n" +
            "    " + body + "\n" +
            "    return hashlib.sha256(str(root).casefold().encode('utf-8')).hexdigest()[:24]\n");
        return script;
    }
    private static void Reclaimed(SmokeHelperReport? report)
    {
        Program.Check(report is { AssignedBeforeResume: true, TreeEnded: true, ProcessClosed: true,
            StdoutClosed: true, StderrClosed: true, JobClosed: true } && SmokeIdentityHelper.PendingCount == 0);
    }
    private static async Task FaultRun(string python, string body, string expected, TimeSpan budget, bool stdoutHeld, bool stderrHeld)
    {
        using var temp = new SmokeFixtureTests.SmokeTemp();
        string script = Script(temp.Root, body);
        SmokeHelperReport? report = null;
        var clock = Stopwatch.StartNew();
        try
        {
            await SmokeFixture.Identity(temp.Root, python, script, budget, value => report = value);
            throw new InvalidOperationException("identity_fault_not_rejected");
        }
        catch (SmokeError error)
        {
            Program.Check(expected == "either_limit" ? error.Message is "identity_stdout_limit" or "identity_stderr_limit" : error.Message == expected);
        }
        // Includes actual OS Job/tree/stream cleanup, not just task cancellation.
        Program.Check(clock.Elapsed < budget + TimeSpan.FromSeconds(2));
        if (expected == "identity_timeout") Program.Check(clock.Elapsed >= budget - TimeSpan.FromMilliseconds(100));
        Reclaimed(report);
        if (stdoutHeld || stderrHeld)
        {
            Program.Check(report!.StartupExitedBeforeCleanup);
            if (stdoutHeld) Program.Check(!report.StdoutEofBeforeCleanup);
            if (stderrHeld) Program.Check(!report.StderrEofBeforeCleanup);
        }
        Console.WriteLine($"INFO helper_fault expected={expected} elapsed_ms={clock.ElapsedMilliseconds}; owned_tree_and_streams_reclaimed");
    }
    private static async Task Normal(string python, string launcher)
    {
        using var temp = new SmokeFixtureTests.SmokeTemp();
        string root = Path.Combine(temp.Root, "missing-normal-root"); SmokeHelperReport? report = null;
        var identity = await SmokeFixture.Identity(root, python, launcher, report: value => report = value);
        Program.Check(identity.Root == root && !Directory.Exists(root) && report!.Outcome == "success"); Reclaimed(report);
    }
    private static async Task Retry(string python, string launcher)
    {
        await FaultRun(python, "import time; time.sleep(60)", "identity_timeout", TimeSpan.FromSeconds(1), false, false);
        await Normal(python, launcher);
    }
    private static async Task Unrelated(string python)
    {
        using var temp = new SmokeFixtureTests.SmokeTemp();
        using var other = TestProcess.Start(python, ["-I", "-S", "-B", "-c", "import time; time.sleep(60)"], temp.Root, []);
        await FaultRun(python, Descendant(true, true), "identity_timeout", TimeSpan.FromSeconds(1), true, true);
        Program.Check(!other.Wait(0)); // Only its own retained test handle will reclaim this child.
    }
    private static async Task SpawnFailure()
    {
        using var temp = new SmokeFixtureTests.SmokeTemp(); SmokeHelperReport? report = null;
        try
        {
            await SmokeFixture.Identity(temp.Root, Path.Combine(temp.Root, "missing.exe"), ScriptPath(),
                TimeSpan.FromSeconds(1), value => report = value);
            throw new InvalidOperationException("missing_executable_accepted");
        }
        catch (SmokeError error) { Program.Check(error.Message == "identity_failure"); }
        Program.Check(report is { AssignedBeforeResume: false, TreeEnded: true, ProcessClosed: true, StdoutClosed: true, StderrClosed: true, JobClosed: true });
        string ScriptPath() => Path.Combine(temp.Root, "missing-script.py");
    }
    private static async Task Handles(string python)
    {
        await FaultRun(python, "import time; time.sleep(60)", "identity_timeout", TimeSpan.FromMilliseconds(200), false, false);
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint before));
        for (int i = 0; i < 8; i++)
            await FaultRun(python, "import time; time.sleep(60)", "identity_timeout", TimeSpan.FromMilliseconds(200), false, false);
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint after));
        Console.WriteLine($"INFO helper_handle_counts {before} {after}");
        Program.Check(after <= before + 2 && SmokeIdentityHelper.PendingCount == 0);
    }
}
