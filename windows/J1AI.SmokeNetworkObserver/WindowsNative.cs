using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeNetworkObserver;

internal sealed class WinHandle : SafeHandleZeroOrMinusOneIsInvalid
{
    public WinHandle() : base(true) { }
    public WinHandle(nint h) : base(true) { SetHandle(h); }
    protected override bool ReleaseHandle() => Win.CloseHandle(handle);
}

internal static class Win
{
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool CloseHandle(nint h);
    [DllImport("kernel32", SetLastError = true)] internal static extern WinHandle OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32", SetLastError = true)] internal static extern uint WaitForSingleObject(WinHandle h, uint timeout);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetProcessTimes(WinHandle h, out long creation, out long exit, out long kernel, out long user);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool QueryFullProcessImageNameW(WinHandle h, uint flags, StringBuilder path, ref uint size);
    [DllImport("shell32", CharSet = CharSet.Unicode, SetLastError = true)] internal static extern nint CommandLineToArgvW(string line, out int count);
    [DllImport("kernel32")] internal static extern nint LocalFree(nint h);
    [DllImport("iphlpapi")] internal static extern uint GetExtendedTcpTable(nint buffer, ref uint size, bool order, uint family, int tableClass, uint reserved);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern WinHandle CreateFileW(string name, uint access, uint share, nint security, uint creation, uint flags, nint template);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    internal static extern uint GetFinalPathNameByHandleW(WinHandle handle, StringBuilder name, uint size, uint flags);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateDirectoryW(string name, nint security);

    internal static string[] Argv(string line)
    {
        if (line.Length is 0 or > 32768) throw new InvalidDataException("command_line_missing");
        nint p = CommandLineToArgvW(line, out int count);
        if (p == 0) throw new InvalidDataException("command_line_parse");
        try
        {
            if (count is < 1 or > 512) throw new InvalidDataException("command_line_count");
            return Enumerable.Range(0, count).Select(i => Marshal.PtrToStringUni(Marshal.ReadIntPtr(p, i * nint.Size))!).ToArray();
        }
        finally { LocalFree(p); }
    }
    internal static string Image(WinHandle h)
    {
        var path = new StringBuilder(32768); uint size = 32768;
        if (!QueryFullProcessImageNameW(h, 0, path, ref size)) throw new InvalidDataException("process_image_unavailable");
        return path.ToString();
    }
    internal static long Birth(WinHandle h)
    {
        if (!GetProcessTimes(h, out long birth, out _, out _, out _) || birth <= 0)
            throw new InvalidDataException("process_birth_unavailable");
        return birth;
    }
}

// A bounded command we CREATE ourselves, not a discovered PID. Used only for
// the frozen --smoke-stop CLI. Nothing here can kill a runtime/browser process.
internal sealed class OwnedStopCommand : IDisposable
{
    [StructLayout(LayoutKind.Sequential)] private struct Basic
    { internal long ProcessTime, JobTime; internal uint Flags; internal nuint Min, Max; internal uint Count; internal nuint Affinity; internal uint Priority, Scheduling; }
    [StructLayout(LayoutKind.Sequential)] private struct Limits
    { internal Basic Basic; internal ulong A, B, C, D, E, F; internal nuint M, J, PM, PJ; }
    [StructLayout(LayoutKind.Sequential)] private struct Startup
    {
        internal int Size; internal nint Reserved, Desktop, Title; internal uint X, Y, XS, YS, XC, YC, Fill, Flags;
        internal ushort Show, ReservedSize; internal nint Bytes, Input, Output, Error, Attributes;
    }
    [StructLayout(LayoutKind.Sequential)] private struct Info { internal nint Process, Thread; internal uint Pid, Tid; }
    [StructLayout(LayoutKind.Sequential)] private struct Accounting
    { internal long A, B, C, D; internal uint PageFaults, Total, Active, Terminated; }
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] private static extern WinHandle CreateJobObjectW(nint sa, string? name);
    [DllImport("kernel32", SetLastError = true)] private static extern bool SetInformationJobObject(WinHandle job, int type, ref Limits limits, uint size);
    [DllImport("kernel32", SetLastError = true)] private static extern bool InitializeProcThreadAttributeList(nint list, int count, uint flags, ref nuint size);
    [DllImport("kernel32", SetLastError = true)] private static extern bool UpdateProcThreadAttribute(nint list, uint flags, nuint type, nint value, nuint size, nint prev, nint ret);
    [DllImport("kernel32")] private static extern void DeleteProcThreadAttributeList(nint list);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool CreateProcessW(string exe, StringBuilder args,
        nint psec, nint tsec, bool inherit, uint flags, nint env, string cwd, ref Startup start, out Info info);
    [DllImport("kernel32", SetLastError = true)] private static extern bool IsProcessInJob(WinHandle process, WinHandle job, out bool inside);
    [DllImport("kernel32", SetLastError = true)] private static extern uint ResumeThread(WinHandle thread);
    [DllImport("kernel32", SetLastError = true)] private static extern bool GetExitCodeProcess(WinHandle process, out uint code);
    [DllImport("kernel32", SetLastError = true)] private static extern bool TerminateJobObject(WinHandle job, uint code);
    [DllImport("kernel32", SetLastError = true)] private static extern bool QueryInformationJobObject(WinHandle job, int type,
        out Accounting info, uint size, nint returned);
    private readonly WinHandle job;
    private WinHandle? process;
    private static readonly System.Collections.Concurrent.ConcurrentDictionary<OwnedStopCommand, byte> Pending = new();
    private bool closed;
    private OwnedStopCommand(WinHandle j) { job = j; }

    internal static OwnedStopCommand Start(string dotnet, string runner)
    {
        var job = CreateJobObjectW(0, null);
        var owner = new OwnedStopCommand(job);
        nint list = 0, value = 0; bool initialized = false;
        try
        {
            var limits = new Limits { Basic = new Basic { Flags = 0x2000 } };
            if (job.IsInvalid || !SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<Limits>())) throw new IOException("stop_job");
            nuint size = 0; InitializeProcThreadAttributeList(0, 1, 0, ref size);
            if (size is 0 or > 65536) throw new IOException("stop_attributes");
            list = Marshal.AllocHGlobal((nint)size); value = Marshal.AllocHGlobal(nint.Size);
            initialized = InitializeProcThreadAttributeList(list, 1, 0, ref size);
            Marshal.WriteIntPtr(value, job.DangerousGetHandle());
            if (!initialized || !UpdateProcThreadAttribute(list, 0, 0x0002000d, value, (nuint)nint.Size, 0, 0)) throw new IOException("stop_attributes");
            var startup = new Startup { Size = Marshal.SizeOf<Startup>(), Attributes = list };
            var command = new StringBuilder(string.Join(" ", new[] { dotnet, runner, "--smoke-stop" }.Select(Quote)));
            if (!CreateProcessW(dotnet, command, 0, 0, false, 0x00080000 | 0x08000000 | 4, 0,
                Path.GetDirectoryName(runner)!, ref startup, out var info)) throw new IOException("stop_spawn");
            owner.process = new(info.Process);
            using var thread = new WinHandle(info.Thread);
            if (!IsProcessInJob(owner.process, job, out bool inside) || !inside || ResumeThread(thread) == uint.MaxValue)
                throw new IOException("stop_assignment");
            return owner;
        }
        catch { owner.Dispose(); throw; }
        finally
        {
            if (initialized) DeleteProcThreadAttributeList(list);
            if (list != 0) Marshal.FreeHGlobal(list);
            if (value != 0) Marshal.FreeHGlobal(value);
        }
    }
    internal static string Quote(string s)
    {
        if (s.Contains('\0')) throw new InvalidDataException("nul_argument");
        var value = new StringBuilder("\""); int slashes = 0;
        foreach (char ch in s)
        {
            if (ch == '\\') { slashes++; continue; }
            value.Append('\\', ch == '"' ? 2 * slashes + 1 : slashes).Append(ch); slashes = 0;
        }
        return value.Append('\\', 2 * slashes).Append('"').ToString();
    }
    internal async Task<bool> Wait(TimeSpan timeout)
    {
        var clock = System.Diagnostics.Stopwatch.StartNew();
        while (clock.Elapsed < timeout)
        {
            uint status = Win.WaitForSingleObject(process!, 0);
            if (status == 0) return GetExitCodeProcess(process!, out uint code) && code == 0;
            if (status != 258) return false;
            await Task.Delay(25);
        }
        return false;
    }
    internal async Task<bool> CloseAndConfirm(TimeSpan timeout)
    {
        // The only assigned process is the exact frozen --smoke-stop command
        // and its helper descendants. No GUI/browser is ever assigned here.
        if (!TerminateJobObject(job, 1)) { Dispose(); return false; }
        var clock = System.Diagnostics.Stopwatch.StartNew();
        while (process != null && clock.Elapsed < timeout)
        {
            uint status = Win.WaitForSingleObject(process, 0);
            if (status == 0 && QueryInformationJobObject(job, 1, out var accounting, (uint)Marshal.SizeOf<Accounting>(), 0) && accounting.Active == 0)
            { job.Dispose(); process.Dispose(); closed = true; return true; }
            if (status is not (0 or 258)) break;
            await Task.Delay(25);
        }
        Dispose(); // If unconfirmed, retain only OUR command's handle in pending reaper.
        return false;
    }
    public void Dispose()
    {
        if (closed) return;
        job.Dispose(); // Only our create-time Job; never a browser Job.
        if (process == null || Win.WaitForSingleObject(process, 0) == 0)
        { process?.Dispose(); closed = true; return; }
        if (Pending.TryAdd(this, 0)) _ = Task.Run(async () =>
        {
            while (Win.WaitForSingleObject(process, 0) != 0) await Task.Delay(100);
            process.Dispose(); closed = true; Pending.TryRemove(this, out _);
        });
    }
}
