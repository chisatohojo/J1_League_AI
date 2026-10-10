namespace J1AI.DashboardHost;

internal interface IGuiWindow
{
    bool CloseRequested { get; }
    EventCode? Failure { get; }
    Task DisposalConfirmed { get; }
    Task InitializeAsync(string url, CancellationToken token);
    void RestoreOwned();
    Task CloseAndConfirmAsync();
}

// Runs on the STA message pump. No native/window operation is dispatched to a
// threadpool continuation. Only server cleanup (bounded Win32 wait) runs there.
internal sealed class GuiLifecycle(IControls controls, Func<IServer> start, IReadiness readiness,
    IGuiWindow window, IEvents events)
{
    internal HostState State { get; private set; } = HostState.STARTING;
    internal bool ShowPending { get; private set; }
    internal async Task<int> RunAsync(TimeSpan timeout)
    {
        IServer? server = null;
        bool failed = false;
        using var deadline = new CancellationTokenSource(timeout);
        try
        {
            events.Record(EventCode.Starting);
            if (Closing()) return 0;
            server = start();
            string url = await AwaitStartup(readiness.WaitAsync(server, deadline.Token));
            if (Closing()) return 0;
            await AwaitStartup(window.InitializeAsync(url, deadline.Token).AsValue());
            if (Closing()) return 0;
            State = HostState.RUNNING; events.Record(EventCode.Running);
            if (ShowPending) { window.RestoreOwned(); ShowPending = false; }
            while (!Closing())
            {
                CheckFailures();
                if (controls.ConsumeShow() && !Closing()) window.RestoreOwned();
                await Task.Delay(20);
            }
            return 0;
        }
        catch (OperationCanceledException) when (Closing()) { return 0; }
        catch (Exception error)
        {
            failed = true; State = HostState.FAILED;
            events.Record(error is HostError h ? h.Code : error is OperationCanceledException
                ? EventCode.StartupTimeout : EventCode.WebViewFailed);
            return 1;
        }
        finally
        {
            deadline.Cancel();
            if (!failed) { State = HostState.CLOSING; events.Record(EventCode.Closing); }
            // If disposal is not confirmed, DO NOT release the live server/gate.
            bool disposalFailed = false;
            try { await window.CloseAndConfirmAsync(); }
            catch
            {
                disposalFailed = true; State = HostState.FAILED;
                events.Record(EventCode.CleanupFailed);
                // Keep pump/server/controls strongly owned until actual disposal.
                // A disposal exception is never permission to release a live gate.
                await window.DisposalConfirmed;
            }
            try
            {
                if (server != null) await Task.Run(server.CloseAndWait);
                events.Record(EventCode.Cleanup);
                controls.Dispose();
                State = failed || disposalFailed ? HostState.FAILED : HostState.STOPPED;
                if (!failed && !disposalFailed) events.Record(EventCode.Stopped);
                if (disposalFailed) throw new HostError(EventCode.CleanupFailed);
            }
            catch
            {
                // OwnedServer retains process/stdout/gate lease in its Phase 1
                // pending reaper. Never treat an unconfirmed exit as success.
                controls.Dispose(); State = HostState.FAILED;
                events.Record(EventCode.CleanupFailed);
                throw new HostError(EventCode.CleanupFailed);
            }
        }

        bool Closing() => controls.StopRequested || window.CloseRequested;
        void CheckFailures()
        {
            if (window.Failure is EventCode code) throw new HostError(code);
            if (server?.Exited == true) throw new HostError(EventCode.ServerExited);
        }
        async Task<T> AwaitStartup<T>(Task<T> operation)
        {
            try
            {
                while (!operation.IsCompleted)
                {
                    if (Closing()) { deadline.Cancel(); throw new OperationCanceledException(); }
                    CheckFailures(); deadline.Token.ThrowIfCancellationRequested();
                    if (controls.ConsumeShow() && !Closing()) ShowPending = true;
                    await Task.WhenAny(operation, Task.Delay(20, deadline.Token));
                }
                if (Closing()) throw new OperationCanceledException();
                CheckFailures();
                return await operation.WaitAsync(deadline.Token);
            }
            finally
            {
                _ = operation.ContinueWith(t => { _ = t.Exception; }, CancellationToken.None,
                    TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
            }
        }
    }
}

internal static class GuiTask
{
    internal static async Task<bool> AsValue(this Task operation) { await operation; return true; }
}
