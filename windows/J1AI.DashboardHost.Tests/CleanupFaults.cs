using System.Runtime.InteropServices;
using System.Text.Json;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal static class CleanupFaults
{
    // Declare before Start, not after it: the observer can acquire a duplicate
    // even when the factory never returns. Only this scope owns that duplicate.
    private sealed class CapturedJob : IDisposable
    {
        private KernelHandle? handle;
        private bool disposed;
        internal int Releases { get; private set; }
        internal KernelHandle Handle => handle ?? throw new InvalidOperationException("job_not_captured");
        internal void Capture(nint job)
        {
            Program.Check(!disposed && handle == null);
            handle = Native.Duplicate(job, false);
        }
        public void Dispose()
        {
            if (disposed) return;
            disposed = true;
            var owned = handle; handle = null;
            if (owned != null) { owned.Dispose(); Releases++; }
        }
    }

    [DllImport("kernel32", SetLastError = true)]
    private static extern KernelHandle OpenProcess(uint access, bool inherit, uint pid);

    private static KernelHandle Interpreter(string line, KernelHandle job)
    {
        using var metadata = JsonDocument.Parse(line);
        // PID comes only from our synthetic child's private stdout. Open for
        // observation, validate membership in our exact Job, then retain HANDLE.
        // Never terminate a process by PID or infer it from a process name.
        var process = OpenProcess(0x00101000, false, metadata.RootElement.GetProperty("pid").GetUInt32());
        try
        {
            Native.Require(!process.IsInvalid);
            Native.Require(Native.IsProcessInJob(process, job, out bool member) && member);
            return process;
        }
        catch { process.Dispose(); throw; }
    }
    // Fault routing is injected, but TIMEOUT / WAIT_FAILED below are actual
    // Win32 results. The owned process handle itself is NEVER invalidated.
    private sealed class WaitFault(int mode) : CleanupCalls
    {
        internal uint Result;
        internal int Error, Calls;
        internal override uint Wait(KernelHandle process, uint milliseconds)
        {
            if (++Calls != 1) return base.Wait(process, milliseconds);
            if (mode == 2) throw new InvalidOperationException("synthetic_wait_exception");
            using var invalid = new KernelHandle(0);
            Result = Native.WaitForSingleObject(mode == 1 ? invalid : process, 0);
            Error = Marshal.GetLastWin32Error();
            Program.Check(Result == (mode == 1 ? uint.MaxValue : Native.WaitTimeout));
            if (mode == 1) Program.Check(Error == 6); // ERROR_INVALID_HANDLE
            return Result;
        }
    }

    private static InstanceControls Gate(TempRepository temp)
    { var controls = new InstanceControls(temp.Identity); Program.Check(controls.Acquire()); return controls; }

    private static ServerCommand Command(string python, string script, TempRepository temp,
        string mode = "probe", params string[] args) =>
        new(python, new[] { "-I", "-S", "-u", script, mode }.Concat(args).ToArray(), temp.Root);

    private static void Fails(Action action)
    {
        try { action(); }
        catch (HostError error) { Program.Check(error.Code == EventCode.CleanupFailed); return; }
        throw new InvalidOperationException("expected_cleanup_failure");
    }

    private static void Excluded(TempRepository temp)
    { using var duplicate = new InstanceControls(temp.Identity); Program.Check(!duplicate.Acquire()); }

    private static void Retained(OwnedServer child)
    {
        Program.Check(child.Resources == (true, false, false, false, false));
        Program.Check(child.Output is StreamReader reader && reader.BaseStream.CanRead);
        using var retained = Native.Duplicate(child.ProcessHandle, false);
        Program.Check(Native.WaitForSingleObject(retained, 0) == Native.WaitTimeout);
    }

    private static async Task Reclaim(OwnedServer child, CapturedJob heldJob)
    {
        heldJob.Dispose();
        // On assertion/setup failure, still reclaim only this test's child.
        try { child.CloseAndWait(); }
        catch (HostError error) { Program.Check(error.Code == EventCode.CleanupFailed); }
        await child.DeferredCleanup.WaitAsync(TimeSpan.FromSeconds(7));
        child.CloseAndWait();
        Program.Check(child.Resources == (true, true, true, true, true));
        Program.Check(child.Output is StreamReader reader && !reader.BaseStream.CanRead);
    }

    private sealed class SetupCalls(int mode) : SpawnCalls
    {
        internal int Creations, Error;
        internal override bool CreateProcess(ServerCommand command, ref Native.StartupEx startup, out Native.ProcessInfo info)
        {
            Creations++;
            if (mode == 2) throw new IOException("synthetic_create_failure");
            bool success = base.CreateProcess(command, ref startup, out info);
            if (!success) Error = Marshal.GetLastWin32Error();
            return success;
        }
    }

    internal static Task SetupFailure(string python, string script, int mode)
    {
        using var temp = new TempRepository(); using var controls = Gate(temp);
        var captured = new CapturedJob();
        KernelHandle? borrowed = null; bool failed = false;
        var calls = new SetupCalls(mode);
        var command = Command(python, script, temp, "silent");
        // A real CreateProcessW failure, but no interpreter is ever resumed.
        if (mode == 1) command = command with { Executable = Path.Combine(temp.Root, "nonexistent-python.exe") };
        try
        {
            using (captured) // MUST cover observer and Start, not just its return.
            {
                using var unexpected = OwnedServer.Start(command, controls, (job, gate, output, nul) =>
                {
                    captured.Capture(job); borrowed = captured.Handle;
                    Program.Check(Native.GetHandleInformation(borrowed.DangerousGetHandle(), out uint flags) && (flags & 1) == 0);
                    if (mode == 0) throw new IOException("synthetic_observer_failure");
                    return command;
                }, calls);
                throw new InvalidOperationException("expected_setup_failure");
            }
        }
        catch (HostError error) { Program.Check(error.Code == EventCode.SpawnFailed); failed = true; }
        Program.Check(failed && borrowed != null && borrowed.IsClosed && captured.Releases == 1);
        // No GC/finalizer, delay, deletion retry or PID lookup is involved.
        Program.Check(!Native.GetHandleInformation(borrowed!.DangerousGetHandle(), out _));
        Program.Check(Marshal.GetLastWin32Error() == 6); // ERROR_INVALID_HANDLE
        captured.Dispose(); Program.Check(captured.Releases == 1); // no second OS close
        Program.Check(calls.Creations == (mode == 0 ? 0 : 1));
        if (mode == 1) Program.Check(calls.Error == 2); // real ERROR_FILE_NOT_FOUND
        controls.Dispose(); using var restarted = Gate(temp);
        return Task.CompletedTask;
    }

    internal static async Task WaitFailure(string python, string script, int mode)
    {
        using var temp = new TempRepository(); using var controls = Gate(temp);
        // An independent synthetic instance owns its own Job/process tree.
        // Stopping only a venv bootstrap PID can leave its interpreter running
        // with the temporary cwd open, so do not use a jobless broker fixture.
        using var otherTemp = new TempRepository(); using var otherControls = Gate(otherTemp);
        using var otherJob = new CapturedJob();
        using var heldJob = new CapturedJob();
        OwnedServer? other = null, child = null;
        KernelHandle? otherInterpreter = null, childInterpreter = null;
        try
        {
            other = OwnedServer.Start(Command(python, script, otherTemp, "cleanup-probe"), otherControls,
                (job, gate, output, nul) => { otherJob.Capture(job); return Command(python, script, otherTemp, "cleanup-probe"); });
            otherInterpreter = Interpreter((await other.Output.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5)))!, otherJob.Handle);
            otherJob.Dispose();
            var fault = new WaitFault(mode);
            // A test-only, NON-INHERITED duplicate delays actual Job termination.
            // Production never duplicates its Job. This is not a spontaneous OS
            // five-second shutdown timeout, nor corruption of the owned handle.
            child = OwnedServer.Start(Command(python, script, temp), controls,
                (job, gate, output, nul) =>
                {
                    heldJob.Capture(job);
                    return mode == 0 ? Command(python, script, temp, "cleanup-probe", gate.ToString())
                        : Command(python, script, temp);
                }, cleanupCalls: fault);
            var line = await child.Output.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5));
            Program.Check(mode == 0 ? line != null && line.Contains("pid") : line != null && line.Contains("in_job"));
            childInterpreter = Interpreter(line!, heldJob.Handle);
            Fails(child.CloseAndWait);
            controls.Dispose();
            Retained(child); Excluded(temp);
            await Task.Delay(150); // deferred observer must NOT release a live child
            Retained(child); Excluded(temp); Program.Check(!other.Exited);
            heldJob.Dispose();
            await child.DeferredCleanup.WaitAsync(TimeSpan.FromSeconds(7));
            Program.Check(child.Resources == (true, true, true, true, true));
            Program.Check(child.Exited && !other.Exited);
            child.CloseAndWait(); child.Dispose(); // idempotent after confirmed cleanup
            using var restarted = Gate(temp);
        }
        finally
        {
            try
            {
                heldJob.Dispose();
                if (child != null) await Reclaim(child, heldJob);
                if (childInterpreter != null)
                    Program.Check(Native.WaitForSingleObject(childInterpreter, 5000) == Native.WaitObject);
            }
            finally
            {
                childInterpreter?.Dispose();
                try
                {
                    otherJob.Dispose();
                    if (other != null) await Reclaim(other, otherJob);
                    // A venv redirector's exit does not prove its interpreter has
                    // released cwd. Wait on the validated interpreter HANDLE before
                    // deleting either fresh temp namespace. No deletion retries.
                    if (otherInterpreter != null)
                        Program.Check(Native.WaitForSingleObject(otherInterpreter, 5000) == Native.WaitObject);
                }
                finally { otherInterpreter?.Dispose(); }
            }
        }
    }

    internal static async Task LifecycleFailure(string python, string script)
    {
        using var temp = new TempRepository(); using var controls = new InstanceControls(temp.Identity);
        using var heldJob = new CapturedJob(); OwnedServer? child = null;
        var events = new RecordingEvents();
        var engine = new Lifecycle(controls, () => child = OwnedServer.Start(Command(python, script, temp), controls,
            (job, gate, output, nul) => { heldJob.Capture(job); return Command(python, script, temp); },
            cleanupCalls: new WaitFault(1)), new FakeReadiness(), events);
        try
        {
            var run = engine.RunAsync(TimeSpan.FromSeconds(5));
            while (engine.State == HostState.STARTING) await Task.Delay(10);
            Program.Check(engine.State == HostState.RUNNING);
            Program.Check(InstanceControls.Signal(temp.Identity, true));
            try { await run.WaitAsync(TimeSpan.FromSeconds(7)); throw new InvalidOperationException("expected_failure"); }
            catch (HostError error) { Program.Check(error.Code == EventCode.CleanupFailed); }
            Program.Check(engine.State == HostState.FAILED && events.Codes.Contains(EventCode.CleanupFailed));
            Program.Check(!events.Codes.Contains(EventCode.Stopped) && !events.Codes.Contains(EventCode.Cleanup));
            Retained(child!); Excluded(temp);
            await Reclaim(child!, heldJob);
            Program.Check(engine.State == HostState.FAILED); // deferred success does not rewrite the run
            using var restarted = Gate(temp);
        }
        finally { if (child != null) await Reclaim(child, heldJob); }
    }

    internal static async Task ConcurrentClose(string python, string script)
    {
        using var temp = new TempRepository(); using var controls = Gate(temp);
        using var child = OwnedServer.Start(Command(python, script, temp), controls);
        await Task.WhenAll(Enumerable.Range(0, 8).Select(_ => Task.Run(child.CloseAndWait)));
        Program.Check(child.Resources == (true, true, true, true, true));
        controls.Dispose(); using var restarted = Gate(temp);
    }

    internal static async Task GcOwnership(string python, string script)
    {
        using var temp = new TempRepository(); using var controls = Gate(temp);
        using var heldJob = new CapturedJob();
        KernelHandle? retainedProcess = null;
        WeakReference<OwnedServer> Quarantine()
        {
            var child = OwnedServer.Start(Command(python, script, temp), controls,
                (job, gate, output, nul) => { heldJob.Capture(job); return Command(python, script, temp); },
                cleanupCalls: new WaitFault(1));
            retainedProcess = Native.Duplicate(child.ProcessHandle, false);
            Fails(child.CloseAndWait);
            return new WeakReference<OwnedServer>(child);
        }
        WeakReference<OwnedServer>? weak = null;
        try
        {
            weak = Quarantine(); controls.Dispose();
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            Program.Check(weak.TryGetTarget(out var retained));
            Retained(retained!); Excluded(temp);
        }
        finally
        {
            heldJob.Dispose();
            if (weak != null && weak.TryGetTarget(out var retained)) await Reclaim(retained, heldJob);
            if (retainedProcess != null)
            {
                try { Program.Check(Native.WaitForSingleObject(retainedProcess, 5000) == Native.WaitObject); }
                finally { retainedProcess.Dispose(); }
            }
        }
        using var restarted = Gate(temp);
    }

    internal static async Task HandleLeaks(string python, string script)
    {
        async Task Cycle()
        {
            using var temp = new TempRepository(); using var controls = Gate(temp);
            using var heldJob = new CapturedJob();
            var child = OwnedServer.Start(Command(python, script, temp), controls,
                (job, gate, output, nul) => { heldJob.Capture(job); return Command(python, script, temp); },
                cleanupCalls: new WaitFault(1));
            try { Fails(child.CloseAndWait); }
            finally { await Reclaim(child, heldJob); }
        }
        await Cycle(); GC.Collect(); GC.WaitForPendingFinalizers();
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint before));
        for (int i = 0; i < 12; i++) await Cycle();
        GC.Collect(); GC.WaitForPendingFinalizers();
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint after));
        Console.WriteLine($"INFO failed_cleanup_handle_counts {before} {after}");
        Program.Check(after <= before + 2);
    }

    internal static async Task HostCrash(string python, string script)
    {
        using var temp = new TempRepository();
        using var parent = Native.Duplicate(Native.GetCurrentProcess(), true);
        using var host = TestProcess.Start(Environment.ProcessPath!,
            [System.Reflection.Assembly.GetExecutingAssembly().Location, "--synthetic-cleanup-owner", python, script,
                temp.Root, temp.Identity.Id, parent.DangerousGetHandle().ToString()], temp.Root, [parent.DangerousGetHandle()]);
        using var child = new KernelHandle(nint.Parse((await host.Output.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5)))!));
        Program.Check(Native.WaitForSingleObject(child, 0) == Native.WaitTimeout);
        Excluded(temp);
        host.KillOwned(); Program.Check(host.Wait(5000));
        Program.Check(Native.WaitForSingleObject(child, 5000) == Native.WaitObject);
        using var restarted = Gate(temp);
    }

    internal static async Task<int> CrashOwner(string[] args)
    {
        var identity = new RepositoryIdentity(args[3], args[4]);
        using var controls = new InstanceControls(identity); Program.Check(controls.Acquire());
        using var heldJob = new CapturedJob();
        var command = new ServerCommand(args[1], ["-I", "-S", "-u", args[2], "probe"], identity.Root);
        var child = OwnedServer.Start(command, controls,
            (job, gate, output, nul) => { heldJob.Capture(job); return command; },
            cleanupCalls: new WaitFault(1));
        try
        {
            Program.Check(await child.Output.ReadLineAsync() != null);
            Fails(child.CloseAndWait); controls.Dispose();
            Native.Require(Native.DuplicateHandle(Native.GetCurrentProcess(), child.ProcessHandle, nint.Parse(args[5]),
                out var remote, 0, false, 2));
            Console.WriteLine(remote); Console.Out.Flush();
            await Task.Delay(Timeout.Infinite);
            return 0;
        }
        finally { await Reclaim(child, heldJob); }
    }
}
