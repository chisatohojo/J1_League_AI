using System.Windows.Forms;

namespace J1AI.DashboardHost;

internal static class StaPump
{
    internal static Task<int> RunAsync(Func<Task<int>> action)
    {
        var result = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
        var thread = new Thread(() =>
        {
            try
            {
                using var context = new ApplicationContext(); // NOT MainForm: keep pump during cleanup.
                using var sync = new WindowsFormsSynchronizationContext();
                SynchronizationContext.SetSynchronizationContext(sync);
                sync.Post(async _ =>
                {
                    try { result.TrySetResult(await action()); }
                    catch (Exception error) { result.TrySetException(error); }
                    finally { context.ExitThread(); }
                }, null);
                Application.Run(context);
            }
            catch (Exception error) { result.TrySetException(error); }
            finally
            {
                SynchronizationContext.SetSynchronizationContext(null);
                // An unexpected pump exit is NOT a completed GUI lifecycle.
                result.TrySetException(new HostError(EventCode.WebViewFailed));
            }
        }) { IsBackground = false, Name = "J1AI owned STA window" };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        // Complete only after the pump thread has exited, not just action completion.
        return Finish();
        async Task<int> Finish()
        {
            try { return await result.Task.ConfigureAwait(false); }
            finally { await Task.Run(thread.Join).ConfigureAwait(false); }
        }
    }
}
