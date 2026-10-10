using System.Windows.Forms;

namespace J1AI.DashboardHost;

internal static class GuiEntry
{
    internal static async Task<int> RunAsync(IControls controls, Func<WebViewConfiguration> preflight,
        Func<IServer> start, IReadiness readiness, IEvents events, TimeSpan timeout,
        Action? reportFailure = null, Action<DashboardForm>? created = null)
    {
        // Same ownership gate as Python/core. A duplicate never creates Form,
        // profile, environment, or server. Legacy owners safely ignore Show.
        if (!controls.Acquire())
        { controls.RequestShow(); events.Record(EventCode.AlreadyRunning); return 0; }
        try
        {
            var configuration = preflight(); // before server creation
            return await StaPump.RunAsync(async () =>
            {
                using var window = new DashboardForm(configuration, events);
                window.Show();
                created?.Invoke(window); // internal synthetic-test observer only; handle already exists
                var lifecycle = new GuiLifecycle(controls, start, readiness, window, events);
                int result;
                try { result = await lifecycle.RunAsync(timeout); }
                catch (HostError) { result = 1; }
                if (result != 0) Report();
                return result;
            });
        }
        catch (Exception error)
        {
            events.Record(error is HostError h ? h.Code : EventCode.WebViewFailed);
            Report(); return 1;
        }
        finally { controls.Dispose(); }

        void Report()
        {
            if (reportFailure != null) reportFailure();
            else MessageBox.Show("J1 AI Dashboardを起動・継続できませんでした。ローカルのnative-core.logを確認してください。",
                "J1 AI Predict", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
