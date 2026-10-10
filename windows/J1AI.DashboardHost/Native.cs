using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace J1AI.DashboardHost;

internal sealed class KernelHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    internal KernelHandle() : base(true) { }
    internal KernelHandle(nint value) : base(true) { SetHandle(value); }
    internal nint Detach() { var value = handle; SetHandleAsInvalid(); return value; }
    protected override bool ReleaseHandle() => Native.CloseHandle(handle);
}

internal static class Native
{
    internal const uint WaitObject = 0, WaitTimeout = 258, Infinite = 0xffffffff;
    internal const uint ExtendedStartup = 0x00080000, NoWindow = 0x08000000, Suspended = 4;
    internal const nuint HandleList = 0x00020002, JobList = 0x0002000d;
    internal const uint KillOnJobClose = 0x2000;

    [StructLayout(LayoutKind.Sequential)] internal struct Security
    {
        internal int Length; internal nint Descriptor;
        [MarshalAs(UnmanagedType.Bool)] internal bool Inherit;
        internal static Security Inheritable => new() { Length = Marshal.SizeOf<Security>(), Inherit = true };
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] internal struct Startup
    {
        internal int Size; internal nint Reserved, Desktop, Title;
        internal uint X, Y, XSize, YSize, XChars, YChars, Fill, Flags;
        internal ushort Show, ReservedSize; internal nint ReservedBytes, Input, Output, Error;
    }
    [StructLayout(LayoutKind.Sequential)] internal struct StartupEx
    { internal Startup Info; internal nint Attributes; }
    [StructLayout(LayoutKind.Sequential)] internal struct ProcessInfo
    { internal nint Process, Thread; internal uint ProcessId, ThreadId; }
    [StructLayout(LayoutKind.Sequential)] internal struct BasicLimits
    {
        internal long ProcessTime, JobTime; internal uint Flags;
        internal nuint MinWorkingSet, MaxWorkingSet; internal uint ActiveProcesses;
        internal nuint Affinity; internal uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] internal struct IoCounters
    { internal ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes; }
    [StructLayout(LayoutKind.Sequential)] internal struct ExtendedLimits
    {
        internal BasicLimits Basic; internal IoCounters Io;
        internal nuint ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }

    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CloseHandle(nint handle);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern KernelHandle CreateMutexW(nint security, bool initialOwner, string name);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern KernelHandle CreateEventW(nint security, bool manualReset, bool initialState, string name);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern KernelHandle OpenEventW(uint access, bool inherit, string name);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetEvent(KernelHandle handle);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool ResetEvent(KernelHandle handle);
    [DllImport("kernel32", SetLastError = true)]
    internal static extern uint WaitForSingleObject(KernelHandle handle, uint milliseconds);
    [DllImport("kernel32", SetLastError = true)]
    internal static extern uint WaitForMultipleObjects(uint count, nint[] handles, bool all, uint milliseconds);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern KernelHandle CreateJobObjectW(nint security, string? name);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetInformationJobObject(KernelHandle job, int infoClass, ref ExtendedLimits value, uint size);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool IsProcessInJob(KernelHandle process, KernelHandle job, [MarshalAs(UnmanagedType.Bool)] out bool inside);
    [DllImport("kernel32")] internal static extern nint GetCurrentProcess();
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool DuplicateHandle(nint sourceProcess, nint source, nint targetProcess,
        out nint target, uint access, bool inherit, uint options);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetHandleInformation(nint handle, out uint flags);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool SetHandleInformation(KernelHandle handle, uint mask, uint flags);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreatePipe(out KernelHandle read, out KernelHandle write, ref Security security, uint size);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern KernelHandle CreateFileW(string path, uint access, uint share, ref Security security,
        uint disposition, uint flags, nint template);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool InitializeProcThreadAttributeList(nint list, int count, uint flags, ref nuint bytes);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool UpdateProcThreadAttribute(nint list, uint flags, nuint attribute,
        nint value, nuint size, nint previous, nint returnedSize);
    [DllImport("kernel32")] internal static extern void DeleteProcThreadAttributeList(nint list);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateProcessW(string application, StringBuilder command, nint processSecurity,
        nint threadSecurity, bool inherit, uint flags, nint environment, string cwd,
        ref StartupEx startup, out ProcessInfo info);
    [DllImport("kernel32", SetLastError = true)] internal static extern uint ResumeThread(KernelHandle thread);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool TerminateProcess(KernelHandle process, uint exitCode);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetProcessHandleCount(nint process, out uint count);

    internal static void Require(bool success, EventCode code = EventCode.SpawnFailed)
    { if (!success) throw new HostError(code); }
    internal static KernelHandle Duplicate(nint source, bool inherit)
    {
        Require(DuplicateHandle(GetCurrentProcess(), source, GetCurrentProcess(), out var result, 0, inherit, 2));
        return new KernelHandle(result);
    }
}

internal sealed class Attributes : IDisposable
{
    internal nint Pointer { get; private set; }
    private readonly List<nint> values = [];
    internal Attributes(int count)
    {
        nuint size = 0;
        Native.InitializeProcThreadAttributeList(0, count, 0, ref size);
        if (size == 0) throw new HostError(EventCode.SpawnFailed);
        Pointer = Marshal.AllocHGlobal(checked((nint)size));
        if (!Native.InitializeProcThreadAttributeList(Pointer, count, 0, ref size))
        { Marshal.FreeHGlobal(Pointer); Pointer = 0; throw new HostError(EventCode.SpawnFailed); }
    }
    internal void Add(nuint attribute, params nint[] handles)
    {
        var value = Marshal.AllocHGlobal(checked(handles.Length * nint.Size));
        values.Add(value);
        Marshal.Copy(handles, 0, value, handles.Length);
        Native.Require(Native.UpdateProcThreadAttribute(Pointer, 0, attribute, value,
            (nuint)(handles.Length * nint.Size), 0, 0));
    }
    public void Dispose()
    {
        if (Pointer == 0) return;
        Native.DeleteProcThreadAttributeList(Pointer);
        Marshal.FreeHGlobal(Pointer); Pointer = 0;
        foreach (var value in values) Marshal.FreeHGlobal(value);
        values.Clear();
    }
}

// Narrow, instance-scoped test seam. Public production startup always uses
// these concrete Win32 calls; no environment/CLI can replace them. Membership
// verification and ResumeThread remain non-overridable in OwnedServer.
internal class SpawnCalls
{
    internal virtual KernelHandle CreateJob() => Native.CreateJobObjectW(0, null);
    internal virtual bool ConfigureJob(KernelHandle job, ref Native.ExtendedLimits limits) =>
        Native.SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<Native.ExtendedLimits>());
    internal virtual void AddJob(Attributes attributes, KernelHandle job) =>
        attributes.Add(Native.JobList, job.DangerousGetHandle());
    internal virtual bool CreateProcess(ServerCommand command, ref Native.StartupEx startup, out Native.ProcessInfo info) =>
        Native.CreateProcessW(command.Executable, command.CommandLine(), 0, 0, true,
            Native.ExtendedStartup | Native.NoWindow | Native.Suspended, 0,
            command.WorkingDirectory, ref startup, out info);
}
