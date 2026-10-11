using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using J1AI.DashboardHost;
using Microsoft.Win32.SafeHandles;

namespace J1AI.DashboardHost.Tests;

internal sealed record SmokeHelperReport(bool AssignedBeforeResume, bool TreeEnded, bool ProcessClosed,
    bool StdoutClosed, bool StderrClosed, bool JobClosed, string Outcome,
    bool StartupExitedBeforeCleanup, bool StdoutEofBeforeCleanup, bool StderrEofBeforeCleanup);

// Test-assembly-only identity transport. A create-time Job owns the venv broker,
// actual interpreter AND inherited-pipe descendants. Never discover/kill by PID.
// Product OwnedServer/Job/IPC contracts are not modified.
internal sealed class SmokeIdentityHelper
{
    private KernelHandle? job, process;
    private StreamReader? stdout, stderr;
    private Task<string>? outputTask, errorTask;
    private Task? treeTask;
    private bool assigned, treeEnded;
    private static readonly System.Collections.Concurrent.ConcurrentDictionary<SmokeIdentityHelper, byte> pending = new();
    internal static int PendingCount => pending.Count;
    internal const int OutputLimit = 4095;
    private static readonly TimeSpan CleanupLimit = TimeSpan.FromSeconds(5);

    [StructLayout(LayoutKind.Sequential)]
    private struct Accounting
    {
        internal long User, Kernel, PeriodUser, PeriodKernel;
        internal uint Faults, Total, Active, Terminated;
    }
    [DllImport("kernel32", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool QueryInformationJobObject(KernelHandle job, int kind, out Accounting information, uint size, nint returned);
    [DllImport("kernel32", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool TerminateJobObject(KernelHandle job, uint code);
    [DllImport("kernel32", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetExitCodeProcess(KernelHandle process, out uint code);

    internal static async Task<(string Output, string Errors)> Run(ServerCommand command, Stopwatch clock,
        TimeSpan budget, Action<SmokeHelperReport>? report = null)
    {
        SmokeFixture.Require(budget > TimeSpan.Zero && budget <= TimeSpan.FromSeconds(10), "identity_deadline_invalid");
        var owner = new SmokeIdentityHelper();
        string outcome = "identity_failure";
        try
        {
            Remaining();
            owner.Start(command);
            using var deadline = new CancellationTokenSource(Remaining());
            owner.outputTask = ReadBounded(owner.stdout!, "identity_stdout_limit", deadline.Token);
            owner.errorTask = ReadBounded(owner.stderr!, "identity_stderr_limit", deadline.Token);
            owner.treeTask = owner.WaitForTree(deadline.Token);
            var tasks = new List<Task> { owner.outputTask, owner.errorTask, owner.treeTask };
            // WhenAll alone would wait for a silent sibling after an output limit
            // failure. Observe the first failure immediately, then reclaim the Job.
            try
            {
                while (tasks.Count != 0)
                {
                    var completed = await Task.WhenAny(tasks).WaitAsync(deadline.Token);
                    await completed;
                    tasks.Remove(completed);
                    Remaining();
                }
                SmokeFixture.Require(GetExitCodeProcess(owner.process!, out uint code) && code == 0, "identity_exit");
                Remaining();
                outcome = "success";
                return (await owner.outputTask, await owner.errorTask);
            }
            finally { deadline.Cancel(); }
        }
        catch (OperationCanceledException) { outcome = "identity_timeout"; throw new SmokeError(outcome); }
        catch (SmokeError error) { outcome = error.Message; throw; }
        catch { outcome = "identity_failure"; throw new SmokeError(outcome); }
        finally
        {
            bool rootExited = owner.process != null && Native.WaitForSingleObject(owner.process, 0) == Native.WaitObject;
            bool outputEof = owner.outputTask?.IsCompletedSuccessfully == true, errorEof = owner.errorTask?.IsCompletedSuccessfully == true;
            bool reclaimed = await owner.Cleanup();
            report?.Invoke(new(owner.assigned, owner.treeEnded, owner.process == null || owner.process.IsClosed,
                owner.stdout == null, owner.stderr == null, owner.job == null || owner.job.IsClosed,
                reclaimed ? outcome : "identity_cleanup_unconfirmed", rootExited, outputEof, errorEof));
            if (!reclaimed) throw new SmokeError("identity_cleanup_unconfirmed");
        }

        TimeSpan Remaining()
        {
            var remaining = budget - clock.Elapsed;
            if (remaining <= TimeSpan.Zero) throw new SmokeError("identity_timeout");
            return remaining;
        }
    }
    private static async Task<string> ReadBounded(StreamReader reader, string overflow, CancellationToken token)
    {
        var result = new StringBuilder(); var buffer = new char[256];
        int size;
        while ((size = await reader.ReadAsync(buffer.AsMemory(), token)) != 0)
        {
            SmokeFixture.Require(result.Length + size <= OutputLimit, overflow);
            result.Append(buffer, 0, size);
        }
        return result.ToString();
    }
    private void Start(ServerCommand command)
    {
        job = Native.CreateJobObjectW(0, null);
        SmokeFixture.Require(!job.IsInvalid, "identity_job_failed");
        var limits = new Native.ExtendedLimits { Basic = new Native.BasicLimits { Flags = Native.KillOnJobClose } };
        Native.Require(Native.SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<Native.ExtendedLimits>()));
        var security = Native.Security.Inheritable;
        Native.Require(Native.CreatePipe(out var outputRead, out var outputWrite, ref security, 0));
        using (outputRead)
        using (outputWrite)
        {
            Native.Require(Native.CreatePipe(out var errorRead, out var errorWrite, ref security, 0));
            using (errorRead)
            using (errorWrite)
            using (var nul = Native.CreateFileW("NUL", 0xc0000000, 3, ref security, 3, 0, 0))
            using (var attributes = new Attributes(2))
            {
                Native.Require(!nul.IsInvalid && Native.SetHandleInformation(outputRead, 1, 0) && Native.SetHandleInformation(errorRead, 1, 0));
                Native.Require(Native.GetHandleInformation(job.DangerousGetHandle(), out uint flags) && (flags & 1) == 0);
                attributes.Add(Native.HandleList, outputWrite.DangerousGetHandle(), errorWrite.DangerousGetHandle(), nul.DangerousGetHandle());
                attributes.Add(Native.JobList, job.DangerousGetHandle());
                var startup = new Native.StartupEx
                {
                    Info = new Native.Startup { Size = Marshal.SizeOf<Native.StartupEx>(), Flags = 0x100,
                        Input = nul.DangerousGetHandle(), Output = outputWrite.DangerousGetHandle(), Error = errorWrite.DangerousGetHandle() },
                    Attributes = attributes.Pointer
                };
                Native.Require(Native.CreateProcessW(command.Executable, command.CommandLine(), 0, 0, true,
                    Native.ExtendedStartup | Native.NoWindow | Native.Suspended, 0, command.WorkingDirectory, ref startup, out var info));
                process = new KernelHandle(info.Process);
                using var thread = new KernelHandle(info.Thread);
                Native.Require(Native.IsProcessInJob(process, job, out bool inside) && inside);
                assigned = true;
                stdout = Reader(outputRead); stderr = Reader(errorRead);
                Native.Require(Native.ResumeThread(thread) != uint.MaxValue);
            }
        }
    }
    private static StreamReader Reader(KernelHandle read)
    {
        using var duplicate = Native.Duplicate(read.DangerousGetHandle(), false);
        var safe = new SafeFileHandle(duplicate.Detach(), true);
        try { return new(new FileStream(safe, FileAccess.Read, 4096, false), new UTF8Encoding(false, true)); }
        catch { safe.Dispose(); throw; }
    }
    private bool TreeFinished()
    {
        if (job == null || job.IsInvalid) return process == null;
        if (!QueryInformationJobObject(job, 1, out var info, (uint)Marshal.SizeOf<Accounting>(), 0)) return false;
        bool rootExited = process == null || Native.WaitForSingleObject(process, 0) == Native.WaitObject;
        return treeEnded = info.Active == 0 && rootExited;
    }
    private async Task WaitForTree(CancellationToken token)
    {
        while (!TreeFinished()) await Task.Delay(10, token);
    }
    private bool ReadsFinished() => (outputTask == null || outputTask.IsCompleted) && (errorTask == null || errorTask.IsCompleted) &&
        (treeTask == null || treeTask.IsCompleted);
    private async Task<bool> Cleanup()
    {
        // Keep the Job handle while verifying ActiveProcesses=0, rather than
        // treating the venv startup process exit as proof about its descendants.
        if (!TreeFinished())
        {
            if (job is { IsInvalid: false }) _ = TerminateJobObject(job, 1);
            if (!assigned && process is { IsInvalid: false } && Native.WaitForSingleObject(process, 0) == Native.WaitTimeout)
                _ = Native.TerminateProcess(process, 1); // retained, newly created suspended process only
        }
        var clock = Stopwatch.StartNew();
        while (clock.Elapsed < CleanupLimit)
        {
            if (TreeFinished() && ReadsFinished())
            {
                try { Release(); return true; }
                catch { break; } // quarantine the still-owned resources below
            }
            await Task.Delay(10);
        }
        // Explicit quarantine: no indefinite wait is added to the caller and no
        // unconfirmed handle/pipe ownership is abandoned to GC.
        pending.TryAdd(this, 0);
        var reaper = Task.Run(async () =>
        {
            while (true)
            {
                if (TreeFinished() && ReadsFinished())
                {
                    try { Release(); pending.TryRemove(this, out _); return; }
                    catch { /* Retain, never disguise an incomplete release as success. */ }
                }
                await Task.Delay(100);
            }
        });
        _ = reaper.ContinueWith(t => { _ = t.Exception; }, TaskContinuationOptions.OnlyOnFaulted);
        return false;
    }
    private void Release()
    {
        _ = outputTask?.Exception; _ = errorTask?.Exception; _ = treeTask?.Exception;
        stdout?.Dispose(); stdout = null; stderr?.Dispose(); stderr = null;
        process?.Dispose(); job?.Dispose();
    }
}
