using System.Reflection;
using System.Text.Json;
using System.Windows.Forms;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

// ONLY --synthetic-gui-tests runs these cases; normal dotnet test never opens GUI.
internal static class GuiIntegration
{
    private static string python = "", launcher = "", web = "";
    internal static async Task<int> RunAsync(string[] args)
    {
        if (args.Length != 4 || !OperatingSystem.IsWindows()) return 2;
        python = Path.GetFullPath(args[1]); launcher = Path.GetFullPath(args[2]); web = Path.GetFullPath(args[3]);
        var cases = new (string Name, Func<Task> Run)[]
        {
            ("sta_marshal_real_form_dispose_not_handle_recreation", StaOwnership),
            ("real_webview_ui_csp_resources_duplicate_show_stop", WebViewSecurity),
            ("real_window_x_server_reclaim_restart_unrelated_survives", CloseRestart),
            ("real_server_crash_is_failure_not_native_close", ServerCrash),
            ("real_startup_named_show_stop_race_cleanup", StartupStop),
        };
        int passed = 0, failed = 0;
        foreach (var item in cases)
        {
            try { await item.Run().WaitAsync(TimeSpan.FromSeconds(60)); passed++; Console.WriteLine("PASS " + item.Name); }
            catch (Exception error) { failed++; Console.WriteLine("FAIL " + item.Name + " " + (error is HostError h ? h.Code : error.GetType().Name)); }
        }
        Console.WriteLine($"Synthetic GUI assertions: {passed + failed} executed / {passed} passed / {failed} failed.");
        return passed == cases.Length && failed == 0 ? 0 : 1;
    }
    private static async Task StaOwnership()
    {
        int result = await StaPump.RunAsync(async () =>
        {
            Program.Check(Thread.CurrentThread.GetApartmentState() == ApartmentState.STA &&
                SynchronizationContext.Current is WindowsFormsSynchronizationContext);
            using var temp = new TempRepository();
            using var form = new DashboardForm(new(Path.Combine(temp.Root, "unused-profile"), "154.0.4258.62"), new RecordingEvents());
            form.Show(); int thread = Environment.CurrentManagedThreadId;
            await Task.Delay(20);
            Program.Check(thread == Environment.CurrentManagedThreadId && Thread.CurrentThread.GetApartmentState() == ApartmentState.STA);
            await Task.Run(async () =>
            {
                bool rejected = false;
                try { form.RequireUi(); } catch (HostError) { rejected = true; }
                Program.Check(rejected);
                await form.OnUiAsync(() => Program.Check(Environment.CurrentManagedThreadId == thread));
            });
            typeof(Control).GetMethod("RecreateHandle", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(form, null);
            Program.Check(!form.IsDisposed && !form.DisposalConfirmed.IsCompleted && !form.CloseRequested);
            form.WindowState = FormWindowState.Minimized; form.RestoreOwned();
            Program.Check(form.WindowState == FormWindowState.Normal && form.RestoreCalls == 1);
            form.Close(); form.Close();
            Program.Check(form.CloseRequested && !form.IsDisposed);
            await form.CloseAndConfirmAsync();
            Program.Check(form.IsDisposed && form.DisposalConfirmed.IsCompletedSuccessfully);
            return 0;
        });
        Program.Check(result == 0);
    }
    private static async Task WebViewSecurity()
    {
        using var fixture = await GuiFixture.Create();
        Task<int> run = fixture.Launch();
        try
        {
            var form = await fixture.Form.Task.WaitAsync(TimeSpan.FromSeconds(10));
            await fixture.Running();
            using var duplicate = new InstanceControls(fixture.Identity);
            int result = await GuiEntry.RunAsync(duplicate, () => throw new InvalidOperationException(),
                () => throw new InvalidOperationException(), new Readiness(), new RecordingEvents(), TimeSpan.FromSeconds(2),
                () => throw new InvalidOperationException());
            Program.Check(result == 0 && fixture.Starts == 1);
            await GuiTests.Until(() => form.RestoreCalls > 0);
            await form.OnUiAsync(() => form.WindowState = FormWindowState.Minimized);
            Program.Check(InstanceControls.Signal(fixture.Identity, false));
            await GuiTests.Until(() => form.RestoreCalls > 1);
            await form.OnUiAsync(() => Program.Check(form.WindowState == FormWindowState.Normal));
            await fixture.WaitJs("document.querySelector('#data-status')?.dataset.state === 'empty'");
            await form.OnUiAsync(() =>
            {
                var settings = form.Core!.Settings;
                Program.Check(!settings.AreDevToolsEnabled && !settings.AreHostObjectsAllowed && !settings.IsWebMessageEnabled &&
                    !settings.AreBrowserAcceleratorKeysEnabled && !settings.AreDefaultContextMenusEnabled && !settings.AreDefaultScriptDialogsEnabled);
            });
            using var handler = Readiness.CreateHandler(); using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(3) };
            using var counts = JsonDocument.Parse(await client.GetStringAsync(fixture.Url + "__counts"));
            Program.Check(counts.RootElement.GetProperty("/").GetInt32() == 1 &&
                counts.RootElement.GetProperty("/app.js").GetInt32() == 1 &&
                counts.RootElement.GetProperty("/api/dashboard").GetInt32() == 2);
            Console.WriteLine("INFO synthetic_security_single_fetch_confirmed");
            // Actual renderer CSP enforcement, not a check for a header string.
            await fixture.Js("window.__blocked = []; document.addEventListener('securitypolicyviolation', e => window.__blocked.push(e.violatedDirective)); " +
                "const s = document.createElement('script'); s.textContent = 'window.__inlineExecuted = true'; document.head.append(s); " +
                "const f = document.createElement('iframe'); f.src = '/'; document.body.append(f); " +
                "try { new Worker('/app.js'); } catch {};");
            await fixture.WaitJs("window.__blocked.some(x => x.startsWith('script-src')) && window.__blocked.some(x => x.startsWith('worker-src')) && !window.__inlineExecuted");
            Console.WriteLine("INFO synthetic_security_csp_inline_worker_confirmed");
            await fixture.Js("window.__popupBlocked = window.open('/', '_blank') === null; " +
                "fetch('/not-allowed').then(r => window.__resourceBlocked = r.status === 403); " +
                "fetch('http://127.0.0.1:54321/').catch(() => window.__connectBlocked = true); " +
                "Notification.requestPermission().then(x => window.__permissionDenied = x === 'denied'); " +
                "const a = document.createElement('a'); a.href = 'data:text/plain,synthetic'; a.download = 'must-not-download.txt'; a.click();");
            await fixture.WaitJs("window.__popupBlocked && window.__resourceBlocked && window.__connectBlocked && window.__permissionDenied && " +
                "window.__blocked.some(x => x.startsWith('connect-src'))");
            Console.WriteLine("INFO synthetic_security_popup_resource_connect_permission_confirmed");
            await form.OnUiAsync(() =>
            {
                Program.Check(Application.OpenForms.Count == 1 && form.BlockedPermissions > 0);
                string downloads = form.Core!.Profile.DefaultDownloadFolderPath;
                Program.Check(!Directory.Exists(downloads) || Directory.GetFiles(downloads).Length == 0);
            });
            using var after = JsonDocument.Parse(await client.GetStringAsync(fixture.Url + "__counts"));
            Program.Check(!after.RootElement.TryGetProperty("/not-allowed", out _));
            // An external URL string is policy-tested without performing a network request.
            await form.OnUiAsync(() => form.Core!.Navigate("http://127.0.0.1:1/"));
            await GuiTests.Until(() => form.BlockedRequests > 0);
            Program.Check(fixture.Starts == 1);
            // Explicit manual demo remains supported; no automatic fallback.
            await fixture.Js("document.querySelector('#preview-link').click()");
            await fixture.WaitJs("document.querySelector('#data-status')?.dataset.state === 'demo'");
            Program.Check(InstanceControls.Signal(fixture.Identity, true));
            Program.Check(await run.WaitAsync(TimeSpan.FromSeconds(15)) == 0);
            fixture.AssertReclaimed();
        }
        finally { await fixture.StopIfNeeded(run); }
    }
    private static async Task CloseRestart()
    {
        using var unrelated = await GuiFixture.Create();
        using var unrelatedControls = new InstanceControls(unrelated.Identity);
        Program.Check(unrelatedControls.Acquire());
        using var independent = OwnedServer.Start(unrelated.Command(), unrelatedControls);
        await new Readiness().WaitAsync(independent, new CancellationTokenSource(TimeSpan.FromSeconds(5)).Token);
        using var fixture = await GuiFixture.Create();
        for (int cycle = 0; cycle < 2; cycle++)
        {
            fixture.Form = new(TaskCreationOptions.RunContinuationsAsynchronously);
            var run = fixture.Launch();
            try
            {
                await fixture.Running(); var form = await fixture.Form.Task;
                await form.OnUiAsync(() => { form.Close(); form.Close(); });
                Program.Check(await run.WaitAsync(TimeSpan.FromSeconds(15)) == 0);
                fixture.AssertReclaimed(); Program.Check(!independent.Exited);
            }
            finally { await fixture.StopIfNeeded(run); }
        }
        Program.Check(fixture.Starts == 2);
    }
    private static async Task ServerCrash()
    {
        using var fixture = await GuiFixture.Create(); var run = fixture.Launch();
        try
        {
            await fixture.Running();
            // Only the self-created synthetic server's retained handle, never PID lookup.
            using var retained = Native.Duplicate(fixture.Server!.ProcessHandle, false);
            Native.Require(Native.TerminateProcess(retained, 8));
            Program.Check(await run.WaitAsync(TimeSpan.FromSeconds(15)) == 1 && fixture.Errors == 1);
            fixture.AssertReclaimed();
        }
        finally { await fixture.StopIfNeeded(run); }
    }
    private static async Task StartupStop()
    {
        using var fixture = await GuiFixture.Create(); fixture.HoldReady = true;
        var run = fixture.Launch();
        try
        {
            await fixture.ReadyArrived.Task.WaitAsync(TimeSpan.FromSeconds(10));
            Program.Check(InstanceControls.Signal(fixture.Identity, false));
            using var duplicate = new InstanceControls(fixture.Identity);
            Program.Check(await GuiEntry.RunAsync(duplicate, () => throw new InvalidOperationException(),
                () => throw new InvalidOperationException(), new Readiness(), new RecordingEvents(), TimeSpan.FromSeconds(2),
                () => throw new InvalidOperationException()) == 0);
            Program.Check(InstanceControls.Signal(fixture.Identity, true));
            Program.Check(await run.WaitAsync(TimeSpan.FromSeconds(15)) == 0 && fixture.Starts == 1);
            Program.Check(fixture.Form.Task.Result.RestoreCalls == 0);
            fixture.AssertReclaimed();
        }
        finally { await fixture.StopIfNeeded(run); }
    }
    private sealed class GuiFixture : IDisposable
    {
        private readonly TempRepository temp = new();
        internal RepositoryIdentity Identity = null!;
        internal OwnedServer? Server;
        internal TaskCompletionSource<DashboardForm> Form = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal int Starts, Errors;
        internal bool HoldReady;
        internal readonly TaskCompletionSource ReadyArrived = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal string Url = "";
        private InstanceControls? controls;
        private Task<int>? active;
        internal static async Task<GuiFixture> Create()
        {
            var fixture = new GuiFixture();
            try
            {
                fixture.Identity = await RepositoryIdentity.ResolveAsync(fixture.temp.Root, python, launcher);
                foreach (string route in DashboardNavigation.Routes.Where(r => r != "/" && r != "/api/dashboard"))
                {
                    string destination = Path.Combine(fixture.temp.Root, "web", route[1..]);
                    Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                    File.Copy(Path.Combine(web, route[1..]), destination);
                }
                return fixture;
            }
            catch { fixture.Dispose(); throw; }
        }
        internal ServerCommand Command() => new(python, ["-I", "-S", "-u",
            Path.Combine(AppContext.BaseDirectory, "synthetic_gui_server.py"), temp.Root,
            "--data", Path.Combine(temp.Root, "must-not-be-read.json")], temp.Root);
        internal Task<int> Launch()
        {
            controls = new InstanceControls(Identity);
            return active = GuiEntry.RunAsync(controls, () => WebViewPreflight.Check(Identity.Id), () =>
            { Starts++; return Server = OwnedServer.Start(Command(), controls); }, new CaptureReadiness(this),
                new RecordingEvents(), TimeSpan.FromSeconds(15), () => Errors++, f => Form.TrySetResult(f));
        }
        internal async Task Running()
        {
            await Form.Task.WaitAsync(TimeSpan.FromSeconds(10));
            await WaitJs("document.querySelector('#data-status')?.dataset.state === 'empty'");
        }
        internal async Task<string> Js(string script)
        {
            string result = ""; var form = await Form.Task;
            Task<string>? execution = null;
            await form.OnUiAsync(() => execution = form.Core!.ExecuteScriptAsync(script));
            result = await execution!;
            return result;
        }
        internal async Task WaitJs(string expression)
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            while (true)
            {
                timeout.Token.ThrowIfCancellationRequested();
                bool ready = false; var form = await Form.Task;
                await form.OnUiAsync(() => ready = form.Core != null);
                if (ready && await Js(expression) == "true") return;
                await Task.Delay(30, timeout.Token);
            }
        }
        internal void AssertReclaimed()
        {
            Program.Check(Server!.Exited && Form.Task.Result.IsDisposed &&
                (!Form.Task.Result.RuntimeStarted || Form.Task.Result.RuntimeExited.IsCompletedSuccessfully) &&
                !File.Exists(Path.Combine(temp.Root, "must-not-be-read.json")));
            using var again = new InstanceControls(Identity);
            Program.Check(again.Acquire());
        }
        internal async Task StopIfNeeded(Task<int> run)
        {
            if (!run.IsCompleted) InstanceControls.Signal(Identity, true);
            await run.WaitAsync(TimeSpan.FromSeconds(20));
        }
        public void Dispose()
        {
            if (active != null && !active.IsCompleted) throw new InvalidOperationException("synthetic_gui_still_active");
            controls?.Dispose(); Server?.Dispose(); temp.Dispose();
            // Dedicated synthetic WebView2 profiles deliberately NOT auto-deleted.
        }
        private sealed class CaptureReadiness(GuiFixture owner) : IReadiness
        {
            public async Task<string> WaitAsync(IServer server, CancellationToken token)
            {
                owner.Url = await new Readiness().WaitAsync(server, token);
                owner.ReadyArrived.TrySetResult();
                if (owner.HoldReady) await Task.Delay(Timeout.InfiniteTimeSpan, token);
                return owner.Url;
            }
        }
    }
}
