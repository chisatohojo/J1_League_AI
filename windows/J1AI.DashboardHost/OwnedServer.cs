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
    private readonly KernelHandle job, process;
    private readonly StreamReader output;
    private bool closed;
    internal bool AssignedBeforeResume { get; }
    internal nint ProcessHandle => process.DangerousGetHandle();
    public TextReader Output => output;
    public bool Exited => Wait(0);

    private OwnedServer(KernelHandle job, KernelHandle process, StreamReader output, bool assigned)
    { this.job = job; this.process = process; this.output = output; AssignedBeforeResume = assigned; }

    public static OwnedServer Start(ServerCommand command, InstanceControls controls) =>
        Start(command, controls, null);

    // Test observer supplies only numeric handle values to a synthetic child's
    // argv; it cannot add inheritance. Production never has an observer.
    internal static OwnedServer Start(ServerCommand command, InstanceControls controls,
        Func<nint, nint, nint, nint, ServerCommand>? observer, SpawnCalls? calls = null)
    {
        calls ??= new SpawnCalls();
        KernelHandle? job = null;
        KernelHandle? process = null;
        try
        {
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
                return new OwnedServer(job, process, reader, inside);
            }
        }
        catch
        {
            job?.Dispose();
            bool reclaimed = true;
            if (process != null)
            {
                // Creation succeeded but validation may not have. This retained
                // handle is exclusively ours, including the suspended failure case.
                if (Native.WaitForSingleObject(process, 0) == Native.WaitTimeout)
                    Native.TerminateProcess(process, 1);
                reclaimed = Native.WaitForSingleObject(process, 5000) == Native.WaitObject;
                process.Dispose();
            }
            throw new HostError(reclaimed ? EventCode.SpawnFailed : EventCode.CleanupFailed);
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
        if (closed) return;
        job.Dispose(); // Never inherited; host crash also closes the last Job handle.
        if (!Wait(5000)) throw new HostError(EventCode.CleanupFailed);
        closed = true;
        try { output.Dispose(); }
        catch (Exception) { throw new HostError(EventCode.CleanupFailed); }
        finally { process.Dispose(); }
    }
    public void Dispose() => CloseAndWait();
}
