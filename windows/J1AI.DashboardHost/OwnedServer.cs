using System.Text;
using Microsoft.Win32.SafeHandles;

namespace J1AI.DashboardHost;

public sealed record ServerCommand(string Executable, IReadOnlyList<string> Arguments, string WorkingDirectory)
{
    public static ServerCommand Dashboard(RepositoryIdentity identity, string? data)
    {
        var args = new List<string> { "-u", "-m", "scripts.serve_dashboard", "--port", "0" };
        if (data != null) { args.Add("--data"); args.Add(Path.GetFullPath(data)); }
        return new(identity.Python, args, identity.Root);
    }

    // CreateProcessW takes a command line, not argv. Quote using the Windows
    // CRT rules (including backslashes preceding quotes and a trailing slash).
    internal static string Quote(string value)
    {
        if (value.Contains('\0')) throw new HostError(EventCode.SpawnFailed);
        var text = new StringBuilder("\"");
        int slashes = 0;
        foreach (char ch in value)
        {
            if (ch == '\\') { slashes++; continue; }
            text.Append('\\', ch == '"' ? slashes * 2 + 1 : slashes);
            text.Append(ch); slashes = 0;
        }
        text.Append('\\', slashes * 2); text.Append('"');
        return text.ToString();
    }
    internal StringBuilder CommandLine() => new(string.Join(" ",
        new[] { Executable }.Concat(Arguments).Select(Quote)));
}

public interface IServer : IDisposable
{
    TextReader Output { get; }
    bool Exited { get; }
    void CloseAndWait();
}

public sealed class OwnedServer : IServer
{
    private readonly KernelHandle job, process, gateLease;
    private readonly StreamReader? output;
    private readonly CleanupCalls cleanupCalls;
    private readonly object cleanupSync = new();
    private bool closed, outputClosed;
    private Task? deferredCleanup;
    // A failed wait must not leave ownership to GC/finalizer timing. Retain the
    // process, stdout and a non-inherited gate until a REAL wait confirms exit.
    private static readonly System.Collections.Concurrent.ConcurrentDictionary<OwnedServer, byte> pending = new();
    internal bool AssignedBeforeResume { get; }
    internal nint ProcessHandle => process.DangerousGetHandle();
    public TextReader Output => output ?? throw new HostError(EventCode.SpawnFailed);
    public bool Exited { get { lock (cleanupSync) return closed || Wait(0); } }
    internal Task DeferredCleanup { get { lock (cleanupSync) return deferredCleanup ?? Task.CompletedTask; } }
    internal (bool JobClosed, bool ProcessClosed, bool OutputClosed, bool GateClosed, bool Closed) Resources
    { get { lock (cleanupSync) return (job.IsClosed, process.IsClosed, outputClosed, gateLease.IsClosed, closed); } }

    private OwnedServer(KernelHandle job, KernelHandle process, StreamReader? output,
        KernelHandle gateLease, bool assigned, CleanupCalls cleanupCalls)
    {
        this.job = job; this.process = process; this.output = output;
        this.gateLease = gateLease; this.cleanupCalls = cleanupCalls; AssignedBeforeResume = assigned;
    }

    public static OwnedServer Start(ServerCommand command, InstanceControls controls) =>
        Start(command, controls, null);

    // Test observer supplies only numeric handle values to a synthetic child's
    // argv; it cannot add inheritance. Production never has an observer.
    internal static OwnedServer Start(ServerCommand command, InstanceControls controls,
        Func<nint, nint, nint, nint, ServerCommand>? observer, SpawnCalls? calls = null,
        CleanupCalls? cleanupCalls = null)
    {
        calls ??= new SpawnCalls();
        cleanupCalls ??= new CleanupCalls();
        KernelHandle? job = null;
        KernelHandle? process = null;
        KernelHandle? gateLease = null;
        try
        {
            gateLease = Native.Duplicate(controls.Gate, false);
            job = calls.CreateJob();
            Native.Require(!job.IsInvalid);
            var limits = new Native.ExtendedLimits
            { Basic = new Native.BasicLimits { Flags = Native.KillOnJobClose } };
            Native.Require(calls.ConfigureJob(job, ref limits));
            // Original gate and Job are non-inheritable. Only this gate duplicate
            // and the two standard IO handles are eligible in HANDLE_LIST.
            using var gate = Native.Duplicate(controls.Gate, true);
            var security = Native.Security.Inheritable;
            Native.Require(Native.CreatePipe(out var read, out var write, ref security, 0));
            using (read)
            using (write)
            using (var nul = Native.CreateFileW("NUL", 0xc0000000, 3, ref security, 3, 0, 0))
            using (var attributes = new Attributes(2))
            {
                Native.Require(!nul.IsInvalid);
                Native.Require(Native.SetHandleInformation(read, 1, 0));
                attributes.Add(Native.HandleList, gate.DangerousGetHandle(), write.DangerousGetHandle(), nul.DangerousGetHandle());
                calls.AddJob(attributes, job);
                if (observer != null) command = observer(job.DangerousGetHandle(), gate.DangerousGetHandle(),
                    write.DangerousGetHandle(), nul.DangerousGetHandle());
                // Recheck the exact allowlist and non-inherited Job immediately
                // before creation. An invalid inheritance plan is fail-closed.
                foreach (var handle in new[] { gate, write, nul })
                    Native.Require(Native.GetHandleInformation(handle.DangerousGetHandle(), out uint flags) && (flags & 1) != 0);
                Native.Require(Native.GetHandleInformation(job.DangerousGetHandle(), out uint jobFlags) && (jobFlags & 1) == 0);
                var startup = new Native.StartupEx
                {
                    Info = new Native.Startup
                    {
                        Size = System.Runtime.InteropServices.Marshal.SizeOf<Native.StartupEx>(),
                        Flags = 0x100, Input = nul.DangerousGetHandle(),
                        Output = write.DangerousGetHandle(), Error = nul.DangerousGetHandle()
                    },
                    Attributes = attributes.Pointer
                };
                Native.Require(calls.CreateProcess(command, ref startup, out var info));
                process = new KernelHandle(info.Process);
                using var thread = new KernelHandle(info.Thread);
                // Suspended creation lets us verify assignment before ANY child
                // instruction runs. No post-create assignment or fallback exists.
                Native.Require(Native.IsProcessInJob(process, job, out bool inside) && inside);
                Native.Require(Native.ResumeThread(thread) != uint.MaxValue);
                using var duplicateRead = Native.Duplicate(read.DangerousGetHandle(), false);
                var streamHandle = new SafeFileHandle(duplicateRead.Detach(), true);
                var stream = new FileStream(streamHandle, FileAccess.Read, 4096, false);
                var reader = new StreamReader(stream, new UTF8Encoding(false, true));
                return new OwnedServer(job, process, reader, gateLease, inside, cleanupCalls);
            }
        }
        catch
        {
            if (process != null)
            {
                // Creation succeeded but validation may not have. This retained
                // handle is exclusively ours, including the suspended failure case.
                if (Native.WaitForSingleObject(process, 0) == Native.WaitTimeout)
                    Native.TerminateProcess(process, 1);
                var failedOwner = new OwnedServer(job!, process, null, gateLease!, false, cleanupCalls);
                failedOwner.CloseAndWait(); // Also quarantines an unconfirmed spawn.
            }
            else { job?.Dispose(); gateLease?.Dispose(); }
            throw new HostError(EventCode.SpawnFailed);
        }
    }

    private bool Wait(uint milliseconds)
    {
        uint result = Native.WaitForSingleObject(process, milliseconds);
        if (result is not (Native.WaitObject or Native.WaitTimeout)) throw new HostError(EventCode.CleanupFailed);
        return result == Native.WaitObject;
    }
    public void CloseAndWait()
    {
        lock (cleanupSync)
        {
            if (closed) return;
            try
            {
                job.Dispose(); // Never inherited; host crash also closes the last Job handle.
                if (cleanupCalls.Wait(process, 5000) != Native.WaitObject)
                    throw new HostError(EventCode.CleanupFailed);
                ReleaseConfirmedExit();
            }
            catch (Exception)
            {
                if (!closed && deferredCleanup == null)
                {
                    pending.TryAdd(this, 0);
                    deferredCleanup = Task.Run(ReapAsync);
                    _ = deferredCleanup.ContinueWith(t => { _ = t.Exception; }, CancellationToken.None,
                        TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
                }
                // The original caller/Lifecycle must still fail, even when the
                // reaper subsequently confirms exit and releases resources.
                throw new HostError(EventCode.CleanupFailed);
            }
        }
    }

    private async Task ReapAsync()
    {
        while (true)
        {
            lock (cleanupSync)
            {
                if (closed) { pending.TryRemove(this, out _); return; }
                // No injected wait here and no PID lookup/kill. A failed native
                // observation keeps ownership + exclusion; it is never success.
                if (Native.WaitForSingleObject(process, 0) == Native.WaitObject)
                {
                    try { ReleaseConfirmedExit(); }
                    finally { pending.TryRemove(this, out _); }
                    return;
                }
            }
            await Task.Delay(100);
        }
    }

    private void ReleaseConfirmedExit()
    {
        try { output?.Dispose(); }
        finally
        {
            outputClosed = true;
            process.Dispose();
            gateLease.Dispose();
            closed = true;
        }
    }
    public void Dispose() => CloseAndWait();
}

// Instance-scoped fault seam only; public startup always uses the concrete
// retained-process Win32 wait. Deferred confirmation is not overridable.
internal class CleanupCalls
{
    internal virtual uint Wait(KernelHandle process, uint milliseconds) =>
        Native.WaitForSingleObject(process, milliseconds);
}
