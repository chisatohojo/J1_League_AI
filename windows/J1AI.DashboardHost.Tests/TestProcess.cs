using System.Runtime.InteropServices;
using System.Text;
using J1AI.DashboardHost;
using Microsoft.Win32.SafeHandles;

namespace J1AI.DashboardHost.Tests;

// ONLY for retained, self-created synthetic helper/host processes. Unlike the
// production server factory, a crash-test host MUST NOT be in a parent Job:
// otherwise the test would not prove that its own Job closes on host death.
internal sealed class TestProcess : IDisposable
{
    private readonly KernelHandle process;
    internal StreamReader Output { get; }
    private TestProcess(KernelHandle process, StreamReader output) { this.process = process; Output = output; }
    internal static TestProcess Start(string executable, string[] args, string cwd, nint[] additional)
    {
        var security = Native.Security.Inheritable;
        Native.Require(Native.CreatePipe(out var read, out var write, ref security, 0));
        using (read)
        using (write)
        using (var nul = Native.CreateFileW("NUL", 0xc0000000, 3, ref security, 3, 0, 0))
        using (var attributes = new Attributes(1))
        {
            Native.Require(!nul.IsInvalid && Native.SetHandleInformation(read, 1, 0));
            attributes.Add(Native.HandleList, new[] { write.DangerousGetHandle(), nul.DangerousGetHandle() }.Concat(additional).ToArray());
            var startup = new Native.StartupEx
            {
                Info = new Native.Startup { Size = Marshal.SizeOf<Native.StartupEx>(), Flags = 0x100,
                    Input = nul.DangerousGetHandle(), Output = write.DangerousGetHandle(), Error = nul.DangerousGetHandle() },
                Attributes = attributes.Pointer
            };
            Native.Require(Native.CreateProcessW(executable, new ServerCommand(executable, args, cwd).CommandLine(),
                0, 0, true, Native.ExtendedStartup | Native.NoWindow, 0, cwd, ref startup, out var info));
            var process = new KernelHandle(info.Process);
            using var thread = new KernelHandle(info.Thread);
            try
            {
                using var duplicate = Native.Duplicate(read.DangerousGetHandle(), false);
                var stream = new FileStream(new SafeFileHandle(duplicate.Detach(), true), FileAccess.Read, 4096, false);
                return new TestProcess(process, new StreamReader(stream, Encoding.UTF8));
            }
            catch
            {
                // Do not orphan a jobless synthetic helper if test setup fails.
                if (Native.WaitForSingleObject(process, 0) == Native.WaitTimeout) Native.TerminateProcess(process, 8);
                var result = Native.WaitForSingleObject(process, 5000);
                process.Dispose(); Program.Check(result == Native.WaitObject);
                throw;
            }
        }
    }
    internal bool Wait(uint milliseconds)
    {
        var value = Native.WaitForSingleObject(process, milliseconds);
        Program.Check(value is Native.WaitObject or Native.WaitTimeout);
        return value == Native.WaitObject;
    }
    internal void KillOwned() { if (!Wait(0)) Native.Require(Native.TerminateProcess(process, 8)); }
    public void Dispose()
    {
        KillOwned(); Program.Check(Wait(5000)); Output.Dispose(); process.Dispose();
    }
}
