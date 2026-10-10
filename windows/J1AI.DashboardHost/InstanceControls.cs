using System.Runtime.InteropServices;

namespace J1AI.DashboardHost;

public interface IControls : IDisposable
{
    bool Acquire();
    bool StopRequested { get; }
    bool ConsumeShow();
    void RequestShow();
}

public sealed class InstanceControls(RepositoryIdentity identity) : IControls
{
    private KernelHandle? gate, stop, show;
    internal nint Gate => gate is { IsInvalid: false, IsClosed: false }
        ? gate.DangerousGetHandle() : throw new HostError(EventCode.IpcFailed);

    public bool Acquire()
    {
        if (gate != null) throw new HostError(EventCode.IpcFailed);
        gate = Native.CreateMutexW(0, false, identity.Name);
        int error = Marshal.GetLastWin32Error();
        if (gate.IsInvalid) { Dispose(); throw new HostError(EventCode.IpcFailed); }
        if (error == 183) { Dispose(); return false; }
        try
        {
            stop = Native.CreateEventW(0, true, false, identity.Name + ".Stop");
            show = Native.CreateEventW(0, false, false, identity.Name + ".Show");
            Native.Require(!stop.IsInvalid && !show.IsInvalid, EventCode.IpcFailed);
            // Never reset STOP: that could erase a concurrent startup request.
            // A briefly retained old signalled event causes a safe immediate stop.
            return true;
        }
        catch { Dispose(); throw; }
    }

    public bool StopRequested => IsSignalled(stop);
    public void RequestShow() => Signal(identity, false);
    public bool ConsumeShow()
    {
        if (StopRequested) return false;
        bool requested = IsSignalled(show);
        return requested && !StopRequested;
    }
    private static bool IsSignalled(KernelHandle? handle)
    {
        if (handle == null) throw new HostError(EventCode.IpcFailed);
        uint value = Native.WaitForSingleObject(handle, 0);
        if (value is not (Native.WaitObject or Native.WaitTimeout)) throw new HostError(EventCode.IpcFailed);
        return value == Native.WaitObject;
    }

    public static bool Signal(RepositoryIdentity identity, bool stop)
    {
        using var handle = Native.OpenEventW(2, false, identity.Name + (stop ? ".Stop" : ".Show"));
        if (handle.IsInvalid)
        {
            if (Marshal.GetLastWin32Error() == 2) return false;
            throw new HostError(EventCode.IpcFailed);
        }
        Native.Require(Native.SetEvent(handle), EventCode.IpcFailed);
        return true;
    }

    public void Dispose()
    {
        show?.Dispose(); show = null;
        stop?.Dispose(); stop = null;
        gate?.Dispose(); gate = null;
    }
}
