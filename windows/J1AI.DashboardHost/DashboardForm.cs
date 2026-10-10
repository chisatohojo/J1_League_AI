using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Windows.Forms;

namespace J1AI.DashboardHost;

internal sealed class DashboardForm : Form, IGuiWindow
{
    private readonly int uiThread = Environment.CurrentManagedThreadId;
    private readonly WebViewConfiguration configuration;
    private readonly IEvents events;
    private readonly Label loading = new() { Dock = DockStyle.Fill, Text = "J1 AI Dashboardを準備しています…",
        TextAlign = System.Drawing.ContentAlignment.MiddleCenter };
    private WebView2? view;
    private CoreWebView2Environment? environment;
    private readonly CancellationTokenSource closing = new();
    private TaskCompletionSource<bool>? loaded;
    private bool disposingWindow;
    private bool controllerStarted;
    private Task? initialization;
    private readonly TaskCompletionSource disposed = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource runtimeExited = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public Task DisposalConfirmed => disposed.Task;
    internal Task RuntimeExited => runtimeExited.Task;
    internal bool RuntimeStarted => controllerStarted;
    internal CoreWebView2? Core { get { RequireUi(); return view?.CoreWebView2; } }
    internal int RestoreCalls { get; private set; }
    internal int BlockedRequests { get; private set; }
    internal int BlockedWindows { get; private set; }
    internal int BlockedPermissions { get; private set; }
    public bool CloseRequested { get; private set; }
    public EventCode? Failure { get; private set; }

    internal DashboardForm(WebViewConfiguration configuration, IEvents events)
    {
        RequireUi(); this.configuration = configuration; this.events = events;
        Text = "J1 AI Predict"; Width = 1100; Height = 800; MinimumSize = new(700, 500);
        Controls.Add(loading);
        FormClosing += (_, e) =>
        {
            if (!disposingWindow) { e.Cancel = true; CloseRequested = true; }
        };
        Disposed += (_, _) => { if (IsDisposed) disposed.TrySetResult(); };
        // No HandleDestroyed or FormClosing event is used as disposal evidence.
    }

    internal void RequireUi()
    {
        if (Environment.CurrentManagedThreadId != uiThread || Thread.CurrentThread.GetApartmentState() != ApartmentState.STA)
            throw new HostError(EventCode.WebViewFailed);
    }

    internal Task OnUiAsync(Action action)
    {
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (IsDisposed || !IsHandleCreated) return Task.FromException(new HostError(EventCode.WebViewFailed));
        void InvokeAction()
        {
            try { RequireUi(); if (IsDisposed) throw new HostError(EventCode.WebViewFailed); action(); completion.SetResult(); }
            catch (Exception error) { completion.SetException(error); }
        }
        // The handle is already created by Show, never force its creation off-STA.
        try { if (InvokeRequired) BeginInvoke((Action)InvokeAction); else InvokeAction(); }
        catch (Exception error) { completion.TrySetException(error); }
        return completion.Task;
    }

    public Task InitializeAsync(string url, CancellationToken token)
    {
        RequireUi();
        if (initialization != null) throw new HostError(EventCode.WebViewFailed);
        return initialization = InitializeCoreAsync(url, token);
    }
    private async Task InitializeCoreAsync(string url, CancellationToken token)
    {
        RequireUi();
        var policy = new DashboardNavigation(url);
        WebViewPreflight.CheckInputs(Environment.GetEnvironmentVariables(), WebViewPreflight.ReadPolicies());
        WebViewPreflight.CheckProfile(configuration.Profile);
        view = new WebView2 { Dock = DockStyle.Fill, Visible = false, AllowExternalDrop = false };
        Controls.Add(view);
        var options = new CoreWebView2EnvironmentOptions
        {
            ExclusiveUserDataFolderAccess = true, AreBrowserExtensionsEnabled = false,
            AllowSingleSignOnUsingOSPrimaryAccount = false, ReleaseChannels = CoreWebView2ReleaseChannels.Stable,
            AdditionalBrowserArguments = ""
        };
        environment = await CoreWebView2Environment.CreateAsync(null, configuration.Profile, options);
        environment.BrowserProcessExited += OnBrowserExited;
        RequireUi(); token.ThrowIfCancellationRequested(); closing.Token.ThrowIfCancellationRequested();
        WebViewPreflight.RequireRuntime(environment.BrowserVersionString);
        if (!Path.GetFullPath(environment.UserDataFolder).Equals(Path.GetFullPath(configuration.Profile), StringComparison.OrdinalIgnoreCase))
            throw new HostError(EventCode.UnsafeWebViewOverride);
        controllerStarted = true;
        await view.EnsureCoreWebView2Async(environment);
        RequireUi(); token.ThrowIfCancellationRequested(); closing.Token.ThrowIfCancellationRequested();
        var core = view.CoreWebView2;
        var settings = core.Settings;
        settings.AreDevToolsEnabled = false; settings.AreDefaultContextMenusEnabled = false;
        settings.AreBrowserAcceleratorKeysEnabled = false; settings.AreDefaultScriptDialogsEnabled = false;
        settings.AreHostObjectsAllowed = false; settings.IsWebMessageEnabled = false;
        settings.IsStatusBarEnabled = false; settings.IsBuiltInErrorPageEnabled = false;
        settings.IsPasswordAutosaveEnabled = false; settings.IsGeneralAutofillEnabled = false;
        core.Profile.AreWebViewScriptApisEnabledForServiceWorkers = false;
        // Even an unexpected runtime download cannot default into personal Downloads.
        core.Profile.DefaultDownloadFolderPath = Path.Combine(configuration.Profile, "downloads-blocked");
        core.NavigationStarting += (_, e) => { if (e.IsRedirected || !policy.Allows(e.Uri, true)) { e.Cancel = true; Block(); } };
        core.FrameNavigationStarting += (_, e) => { e.Cancel = true; Block(); };
        core.NewWindowRequested += (_, e) => { e.Handled = true; BlockedWindows++; Block(); };
        core.DownloadStarting += (_, e) => { e.Cancel = true; e.Handled = true; Block(); };
        core.PermissionRequested += (_, e) =>
        { e.State = CoreWebView2PermissionState.Deny; e.SavesInProfile = false; e.Handled = true; BlockedPermissions++; Block(); };
        core.LaunchingExternalUriScheme += (_, e) => { e.Cancel = true; Block(); };
        core.BasicAuthenticationRequested += (_, e) => e.Cancel = true;
        core.ClientCertificateRequested += (_, e) => { e.Cancel = true; e.Handled = true; };
        core.ServerCertificateErrorDetected += (_, e) => e.Action = CoreWebView2ServerCertificateErrorAction.Cancel;
        core.ContextMenuRequested += (_, e) => e.Handled = true;
        core.ProcessFailed += (_, e) => Fail(e.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited
            ? EventCode.BrowserFailed : EventCode.RendererFailed);
        core.AddWebResourceRequestedFilter("*", CoreWebView2WebResourceContext.All, CoreWebView2WebResourceRequestSourceKinds.All);
        core.WebResourceRequested += async (_, e) =>
        {
            RequireUi();
            bool document = e.ResourceContext == CoreWebView2WebResourceContext.Document;
            if (e.Request.Method != "GET" || !policy.Allows(e.Request.Uri, document) ||
                e.RequestedSourceKind != CoreWebView2WebResourceRequestSourceKinds.Document)
            { e.Response = environment.CreateWebResourceResponse(null, 403, "Blocked", "Content-Length: 0"); Block(); return; }
            if (!document) return; // no NativeHost read of JSON/scripts/styles
            // Supplying Response replaces the pending request: ONE upstream GET,
            // never a response-received mutation or a duplicate browser fetch.
            var deferral = e.GetDeferral();
            try
            {
                using var handler = Readiness.CreateHandler();
                using var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(5) };
                var html = await HtmlResponse.FetchAsync(client, policy, e.Request.Uri, closing.Token);
                RequireUi();
                if (!disposingWindow)
                    e.Response = environment.CreateWebResourceResponse(new MemoryStream(html.Bytes, writable: false), 200, "OK", html.Headers);
            }
            catch
            {
                if (!disposingWindow)
                {
                    e.Response = environment.CreateWebResourceResponse(null, 403, "Blocked", "Content-Length: 0");
                    Fail(EventCode.InvalidResponse);
                }
            }
            finally
            {
                // Completion can race controller disposal. Never let an async-void
                // event's late COM exception escape the STA message pump.
                try { deferral.Complete(); }
                catch { if (!disposingWindow) Fail(EventCode.WebViewFailed); }
            }
        };
        loaded = new(TaskCreationOptions.RunContinuationsAsynchronously);
        core.NavigationCompleted += (_, e) =>
        {
            if (disposingWindow) return;
            if (e.IsSuccess) loaded.TrySetResult(true);
            else if (e.WebErrorStatus != CoreWebView2WebErrorStatus.OperationCanceled)
            { loaded.TrySetException(new HostError(EventCode.WebViewFailed)); Fail(EventCode.WebViewFailed); }
        };
        core.Navigate(url);
        await loaded.Task.WaitAsync(token);
        RequireUi(); if (disposingWindow) throw new OperationCanceledException();
        loading.Visible = false; view.Visible = true; view.BringToFront();
    }

    private void Block() { BlockedRequests++; events.Record(EventCode.NavigationBlocked); }
    private void OnBrowserExited(object? sender, CoreWebView2BrowserProcessExitedEventArgs args)
    {
        RequireUi(); runtimeExited.TrySetResult();
        if (!disposingWindow) Fail(EventCode.BrowserFailed);
    }
    internal void Fail(EventCode code)
    {
        RequireUi(); if (disposingWindow) return;
        Failure ??= code;
        loading.Text = "J1 AI Dashboardを継続できませんでした。";
    }
    public void RestoreOwned()
    {
        RequireUi(); if (disposingWindow || IsDisposed || CloseRequested) return;
        RestoreCalls++;
        if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
        Show(); Activate(); // best effort, this Form only; no foreign-window API.
    }
    public async Task CloseAndConfirmAsync()
    {
        RequireUi();
        if (!disposingWindow)
        {
            disposingWindow = true; closing.Cancel();
            loaded?.TrySetCanceled(closing.Token);
            // Dispose controller via WinForms WebView2 BEFORE actual Form disposal.
            try { view?.Dispose(); }
            finally { view = null; Dispose(); }
        }
        if (!IsDisposed) throw new HostError(EventCode.CleanupFailed);
        disposed.TrySetResult();
        if (initialization != null)
        {
            try { await initialization.WaitAsync(TimeSpan.FromSeconds(5)); }
            catch (TimeoutException) { throw new HostError(EventCode.CleanupFailed); }
            catch { /* startup failure is already recorded; disposal still required */ }
        }
        // Keep the STA pump alive for the runtime's own exit notification. Never
        // identify/kill Chromium by PID. Failure is reported, not disguised as close.
        if (controllerStarted) await runtimeExited.Task.WaitAsync(TimeSpan.FromSeconds(5));
        if (environment != null) environment.BrowserProcessExited -= OnBrowserExited;
    }
}
