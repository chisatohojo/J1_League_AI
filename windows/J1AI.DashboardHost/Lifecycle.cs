namespace J1AI.DashboardHost;

public enum HostState { STOPPED, STARTING, RUNNING, CLOSING, CLEANUP, FAILED }

public sealed class Lifecycle(IControls controls, Func<IServer> start, IReadiness readiness, IEvents events)
{
    public HostState State { get; private set; } = HostState.STOPPED;
    public bool ShowPending { get; private set; }

    public async Task<int> RunAsync(TimeSpan timeout)
    {
        if (timeout <= TimeSpan.Zero || timeout > TimeSpan.FromSeconds(120))
            throw new HostError(EventCode.InvalidArguments);
        IServer? server = null;
        bool failed = false;
        try
        {
            if (!controls.Acquire())
            { controls.RequestShow(); events.Record(EventCode.AlreadyRunning); return 0; }
            State = HostState.STARTING; events.Record(EventCode.Starting);
            if (controls.StopRequested) return 0;
            server = start();
            if (controls.StopRequested) return 0;
            using var deadline = new CancellationTokenSource(timeout);
            var ready = readiness.WaitAsync(server, deadline.Token);
            try
            {
                while (!ready.IsCompleted)
                {
                    if (controls.StopRequested) { deadline.Cancel(); return 0; }
                    deadline.Token.ThrowIfCancellationRequested();
                    CaptureShow();
                    if (server.Exited) throw new HostError(EventCode.ServerExited);
                    await Task.WhenAny(ready, Task.Delay(20, deadline.Token));
                }
                if (controls.StopRequested) { deadline.Cancel(); return 0; }
                await ready.WaitAsync(deadline.Token);
            }
            finally
            {
                deadline.Cancel(); // also cancel pending IO on crash/failure
                _ = ready.ContinueWith(t => { _ = t.Exception; }, CancellationToken.None,
                    TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
            }
            if (controls.StopRequested) return 0;
            State = HostState.RUNNING; events.Record(EventCode.Running);
            while (!controls.StopRequested)
            {
                if (server.Exited) throw new HostError(EventCode.ServerExited);
                CaptureShow();
                await Task.Delay(20);
            }
            return 0;
        }
        catch (Exception error)
        {
            failed = true; State = HostState.FAILED;
            events.Record(error is HostError h ? h.Code : error is OperationCanceledException
                ? EventCode.StartupTimeout : EventCode.UnexpectedFailure);
            return 1;
        }
        finally
        {
            if (server != null)
            {
                if (!failed) { State = HostState.CLOSING; events.Record(EventCode.Closing); }
                try { server.CloseAndWait(); }
                catch (Exception)
                {
                    controls.Dispose();
                    State = HostState.FAILED; events.Record(EventCode.CleanupFailed);
                    throw new HostError(EventCode.CleanupFailed);
                }
                State = HostState.CLEANUP; events.Record(EventCode.Cleanup);
            }
            // Child exit is confirmed first. On a failed wait, its inherited
            // gate continues to exclude a new server until Windows reclaims it.
            controls.Dispose();
            State = HostState.STOPPED; events.Record(EventCode.Stopped);
        }
    }

    private void CaptureShow()
    {
        if (!controls.StopRequested && controls.ConsumeShow() && !controls.StopRequested && !ShowPending)
        { ShowPending = true; events.Record(EventCode.ShowPending); }
    }
}
