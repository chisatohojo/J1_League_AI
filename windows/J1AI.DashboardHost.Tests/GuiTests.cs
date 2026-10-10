using System.Collections;
using System.Net;
using System.Text;
using Microsoft.Win32;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal static class GuiTests
{
    internal static IReadOnlyList<(string Name, Func<Task> Run)> Cases()
    {
        var cases = new List<(string, Func<Task>)>
        {
            ("gui_options_explicit_only_and_data_passthrough", OptionsContract),
            ("gui_duplicate_no_form_profile_or_server", Duplicate),
            ("gui_preflight_failure_before_server", PreflightFailure),
            ("gui_override_environment_denied", EnvironmentOverrides),
            ("gui_override_registry_denied_legacy_classified", RegistryOverrides),
            ("gui_profile_runtime_path_validation", Profiles),
            ("gui_profile_file_access_failure", ProfileFailure),
            ("gui_navigation_all_routes_and_anchors", Routes),
            ("gui_html_proxy_exact_bytes_headers_single_fetch", HtmlIntegrity),
            ("gui_html_proxy_no_external_api_or_redirect", HtmlBoundary),
            ("gui_loading_ready_show_then_close", Normal),
            ("gui_startup_show_coalesces_once", CoalescedShow),
            ("gui_help_does_not_activate_gui", GuiHelp),
            ("gui_startup_stop_prioritizes_show", StartupStop),
            ("gui_actual_disposal_before_cleanup", DisposalOrder),
            ("gui_disposal_failure_retains_ownership", DisposalFailure),
            ("gui_cleanup_failure_never_success", CleanupFailure),
        };
        foreach (var code in new[] { EventCode.InvalidResponse, EventCode.WebViewFailed, EventCode.ProfileFailed,
            EventCode.RendererFailed, EventCode.BrowserFailed, EventCode.ServerExited, EventCode.StartupTimeout })
        {
            EventCode current = code;
            cases.Add(("gui_failure_cleanup_" + current, () => Failure(current)));
        }
        foreach (string url in new[] { "https://127.0.0.1:1234/", "http://localhost:1234/", "http://127.0.0.1:1235/",
            "http://127.0.0.1:1234.evil/", "http://127.0.0.1:1234@evil.invalid/", "http://u@127.0.0.1:1234/",
            "http://127.0.0.1:1234/evil", "http://127.0.0.1:1234/?demo=2", "http://127.0.0.1:1234/?demo=1&x=1",
            "http://127.0.0.1:1234/index.html?demo=1", "http://127.0.0.1:1234/%2e%2e/", "http://127.0.0.1:1234/\\evil",
            "http://127.1:1234/", "http://2130706433:1234/", "http://127.0.0.1:01234/", "file:///C:/secret",
            "data:text/html,bad", "javascript:alert(1)", "edge://settings", "http://[::1]:1234/", " http://127.0.0.1:1234/" })
        {
            string value = url;
            cases.Add(("gui_navigation_reject_" + cases.Count, () =>
            { Program.Check(!new DashboardNavigation(Url).Allows(value, true)); return Task.CompletedTask; }));
        }
        return cases;
    }
    private const string Url = "http://127.0.0.1:1234/";
    private static void Reject(Action action, EventCode code)
    {
        try { action(); } catch (HostError error) { Program.Check(error.Code == code); return; }
        throw new InvalidOperationException("expected_rejection");
    }
    private static async Task RejectAsync(Func<Task> action, EventCode code)
    {
        try { await action(); } catch (HostError error) { Program.Check(error.Code == code); return; }
        throw new InvalidOperationException("expected_rejection");
    }
    internal static async Task Until(Func<bool> predicate)
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        while (!predicate()) await Task.Delay(10, deadline.Token);
    }
    private static Task OptionsContract()
    {
        var options = Options.Parse(["--gui", "--data", "synthetic-never-opened.json"]);
        Program.Check(options.Gui && !options.Core && !options.Stop && Path.IsPathFullyQualified(options.Data!));
        Program.Check(!Options.Parse([]).Gui && !Options.Parse(["--help"]).Gui);
        foreach (var args in new[] { new[] { "--gui", "--core" }, ["--gui", "--stop"], ["--data", "x"] })
            Reject(() => Options.Parse(args), EventCode.InvalidArguments);
        var command = ServerCommand.Dashboard(new RepositoryIdentity("C:\\synthetic", new string('a', 24)), options.Data);
        Program.Check(command.Arguments.Take(5).SequenceEqual(new[] { "-u", "-m", "scripts.serve_dashboard", "--port", "0" }) &&
            command.Arguments[^2] == "--data" && command.Arguments[^1] == options.Data && !File.Exists(options.Data));
        return Task.CompletedTask;
    }
    private static async Task Duplicate()
    {
        var controls = new FakeControls { Owned = false };
        int result = await GuiEntry.RunAsync(controls, () => throw new InvalidOperationException(),
            () => throw new InvalidOperationException(), new FakeReadiness(), new RecordingEvents(), TimeSpan.FromSeconds(1),
            () => throw new InvalidOperationException());
        Program.Check(result == 0 && controls.ShowSignals == 1);
    }
    private static async Task PreflightFailure()
    {
        var controls = new FakeControls(); int errors = 0;
        int result = await GuiEntry.RunAsync(controls, () => throw new HostError(EventCode.ProfileFailed),
            () => throw new InvalidOperationException(), new FakeReadiness(), new RecordingEvents(), TimeSpan.FromSeconds(1), () => errors++);
        Program.Check(result == 1 && errors == 1 && controls.Disposed);
    }
    private static Task EnvironmentOverrides()
    {
        foreach (string name in new[] { "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "WEBVIEW2_BROWSER_EXECUTABLE_FOLDER",
            "WEBVIEW2_USER_DATA_FOLDER", "WEBVIEW2_RELEASE_CHANNELS", "WEBVIEW2_CHANNEL_SEARCH_KIND",
            "WEBVIEW2_RELEASE_CHANNEL_PREFERENCE", "WEBVIEW2_WAIT_FOR_SCRIPT_DEBUGGER", "WEBVIEW2_PIPE_FOR_SCRIPT_DEBUGGER",
            "WEBVIEW2_FUTURE_UNKNOWN_OVERRIDE" })
            Reject(() => WebViewPreflight.CheckInputs(new Hashtable { [name] = "unsafe" }, []), EventCode.UnsafeWebViewOverride);
        WebViewPreflight.CheckInputs(new Hashtable { ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "" }, []);
        return Task.CompletedTask;
    }
    private static Task RegistryOverrides()
    {
        var legacy = new PolicyValue(WebViewPreflight.PolicyRoot, "RendererCodeIntegrityEnabled", RegistryValueKind.DWord, 0);
        WebViewPreflight.CheckInputs(new Hashtable(), [legacy]);
        foreach (var bad in new[] { legacy with { Kind = RegistryValueKind.String, Value = "0" }, legacy with { Value = 2 },
            legacy with { Name = "UnknownSecurityPolicy" } })
            Reject(() => WebViewPreflight.CheckInputs(new Hashtable(), [bad]), EventCode.UnsafeWebViewOverride);
        foreach (string key in new[] { "AdditionalBrowserArguments", "UserDataFolder", "BrowserExecutableFolder",
            "ReleaseChannels", "ChannelSearchKind", "ReleaseChannelPreference", "DowngradeVersion" })
        foreach (string app in new[] { "*", "J1AI.DashboardHost.exe", "other.app.id" })
            Reject(() => WebViewPreflight.CheckInputs(new Hashtable(), [new(WebViewPreflight.PolicyRoot + "\\" + key,
                app, RegistryValueKind.String, "unsafe")]), EventCode.UnsafeWebViewOverride);
        return Task.CompletedTask;
    }
    private static Task Profiles()
    {
        string path = WebViewPreflight.ProfilePath("C:\\synthetic", new string('a', 24));
        Program.Check(path.EndsWith("webview2-profile") && !path.Contains("edge-profile") && !path.Contains("chrome-profile"));
        Reject(() => WebViewPreflight.ProfilePath("C:\\synthetic", "../bad"), EventCode.ProfileFailed);
        WebViewPreflight.RequireRuntime("154.0.4258.62");
        foreach (string version in new[] { "153.1.2.3", "154.1.2.3 beta", "bad", "" })
            Reject(() => WebViewPreflight.RequireRuntime(version), EventCode.WebViewFailed);
        return Task.CompletedTask;
    }
    private static Task ProfileFailure()
    {
        using var temp = new TempRepository();
        string path = Path.Combine(temp.Root, "file-not-profile"); File.WriteAllText(path, "synthetic");
        Reject(() => WebViewPreflight.CheckProfile(path), EventCode.ProfileFailed);
        return Task.CompletedTask;
    }
    private static Task Routes()
    {
        var policy = new DashboardNavigation(Url);
        foreach (string route in DashboardNavigation.Routes) Program.Check(policy.Allows(policy.Origin + route, false));
        foreach (string anchor in new[] { "#main", "#previous-round", "#next-round" }) Program.Check(policy.Allows(Url + anchor, true));
        Program.Check(policy.Allows(Url + "?demo=1", true) && !policy.Allows(Url + "?demo=1", false));
        Program.Check(!policy.Allows(Url + "app.js", true));
        Program.Check(policy.ContentSecurityPolicy.Contains("worker-src 'none'") && policy.ContentSecurityPolicy.Contains("frame-src 'none'"));
        return Task.CompletedTask;
    }
    private sealed class HtmlHandler(HttpStatusCode status = HttpStatusCode.OK, string mime = "text/html") : HttpMessageHandler
    {
        internal int Calls;
        internal readonly byte[] Bytes = Encoding.UTF8.GetBytes("<!doctype html><p>synthetic 日本語</p>");
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            Calls++; Program.Check(request.Method == HttpMethod.Get && request.RequestUri!.Host == "127.0.0.1");
            var response = new HttpResponseMessage(status) { Content = new ByteArrayContent(Bytes) };
            response.Content.Headers.ContentType = new(mime) { CharSet = "utf-8" };
            response.Headers.Add("X-Synthetic-Integrity", "retained");
            response.Headers.Location = new Uri("https://blocked.invalid");
            return Task.FromResult(response);
        }
    }
    private static async Task HtmlIntegrity()
    {
        using var handler = new HtmlHandler(); using var client = new HttpClient(handler);
        var policy = new DashboardNavigation(Url);
        var response = await HtmlResponse.FetchAsync(client, policy, Url, CancellationToken.None);
        Program.Check(handler.Calls == 1 && response.Bytes.SequenceEqual(handler.Bytes) &&
            response.Headers.Contains("Content-Type: text/html; charset=utf-8") &&
            response.Headers.Contains("X-Synthetic-Integrity: retained") && response.Headers.Contains(policy.ContentSecurityPolicy));
    }
    private static async Task HtmlBoundary()
    {
        using var handler = new HtmlHandler(); using var client = new HttpClient(handler);
        var policy = new DashboardNavigation(Url);
        foreach (string url in new[] { "https://blocked.invalid/", Url + "api/dashboard", Url + "app.js" })
            await RejectAsync(() => HtmlResponse.FetchAsync(client, policy, url, CancellationToken.None), EventCode.InvalidUrl);
        Program.Check(handler.Calls == 0);
        foreach (var pair in new[] { (HttpStatusCode.Redirect, "text/html"), (HttpStatusCode.OK, "application/json") })
        {
            using var bad = new HtmlHandler(pair.Item1, pair.Item2); using var badClient = new HttpClient(bad);
            await RejectAsync(() => HtmlResponse.FetchAsync(badClient, policy, Url, CancellationToken.None), EventCode.InvalidResponse);
        }
    }
    private static async Task Normal()
    {
        var controls = new FakeControls { Shows = true }; var server = new FakeServer(); var window = new ProbeWindow { InitDelay = 50 };
        var life = new GuiLifecycle(controls, () => server, new FakeReadiness { Delay = 50 }, window, new RecordingEvents());
        var run = life.RunAsync(TimeSpan.FromSeconds(2));
        await Until(() => life.State == HostState.RUNNING);
        Program.Check(window.Initialized && window.Restored > 0 && !server.Closed);
        controls.Shows = false; window.Requested = true; window.Requested = true;
        Program.Check(await run == 0 && window.Closed && server.Closed && controls.Disposed && life.State == HostState.STOPPED);
    }
    private static async Task StartupStop()
    {
        var controls = new FakeControls { Shows = true }; var server = new FakeServer(); var window = new ProbeWindow();
        var life = new GuiLifecycle(controls, () => server, new FakeReadiness { Delay = 2000 }, window, new RecordingEvents());
        var run = life.RunAsync(TimeSpan.FromSeconds(3)); controls.Stop = true;
        Program.Check(await run == 0 && !window.Initialized && window.Restored == 0 && server.Closed && controls.Disposed);
    }
    private static async Task CoalescedShow()
    {
        var controls = new FakeControls { Shows = true }; var server = new FakeServer(); var window = new ProbeWindow();
        var life = new GuiLifecycle(controls, () => server, new FakeReadiness { Delay = 100 }, window, new RecordingEvents());
        var run = life.RunAsync(TimeSpan.FromSeconds(2));
        await Until(() => life.ShowPending); controls.Shows = false;
        await Until(() => life.State == HostState.RUNNING);
        Program.Check(window.Restored == 1 && !life.ShowPending);
        window.Requested = true; Program.Check(await run == 0);
    }
    private static async Task GuiHelp()
    {
        Program.Check(await J1AI.DashboardHost.Program.Main(["--gui", "--help", "--repository", "Z:\\missing-identity-no-lookup"]) == 0);
        Program.Check(await J1AI.DashboardHost.Program.Main(["--gui", "--core"]) == 1);
    }
    private static async Task DisposalOrder()
    {
        var controls = new FakeControls(); var server = new FakeServer(); var window = new ProbeWindow { HoldDisposal = true };
        var life = new GuiLifecycle(controls, () => server, new FakeReadiness(), window, new RecordingEvents());
        var run = life.RunAsync(TimeSpan.FromSeconds(2)); window.Requested = true;
        await Until(() => window.Closed);
        Program.Check(!server.Closed && !controls.Disposed && !run.IsCompleted);
        window.Disposed.TrySetResult();
        Program.Check(await run == 0 && server.Closed && controls.Disposed);
    }
    private static async Task DisposalFailure()
    {
        var controls = new FakeControls(); var server = new FakeServer();
        var window = new ProbeWindow { HoldDisposal = true, FailDisposal = true };
        var life = new GuiLifecycle(controls, () => server, new FakeReadiness(), window, new RecordingEvents());
        var run = life.RunAsync(TimeSpan.FromSeconds(2)); window.Requested = true;
        await Until(() => life.State == HostState.FAILED);
        Program.Check(!server.Closed && !controls.Disposed && !run.IsCompleted);
        window.Disposed.TrySetResult();
        await RejectAsync(async () => await run, EventCode.CleanupFailed);
        Program.Check(server.Closed && controls.Disposed && life.State == HostState.FAILED);
    }
    private static async Task CleanupFailure()
    {
        var controls = new FakeControls(); var server = new FakeServer { FailCleanup = true }; var window = new ProbeWindow();
        var life = new GuiLifecycle(controls, () => server, new FakeReadiness(), window, new RecordingEvents());
        var run = life.RunAsync(TimeSpan.FromSeconds(2)); window.Requested = true;
        await RejectAsync(async () => await run, EventCode.CleanupFailed);
        Program.Check(window.Closed && controls.Disposed && life.State == HostState.FAILED);
    }
    private static async Task Failure(EventCode code)
    {
        var controls = new FakeControls(); var server = new FakeServer(); var window = new ProbeWindow(); var events = new RecordingEvents();
        IReadiness readiness = code is EventCode.InvalidResponse or EventCode.StartupTimeout ? new ErrorReadiness(code) : new FakeReadiness();
        if (code is EventCode.WebViewFailed or EventCode.ProfileFailed) window.InitFailure = code;
        var life = new GuiLifecycle(controls, () => server, readiness, window, events);
        var run = life.RunAsync(TimeSpan.FromMilliseconds(250));
        if (code is EventCode.RendererFailed or EventCode.BrowserFailed or EventCode.ServerExited)
        { await Until(() => life.State == HostState.RUNNING); window.Error = code; }
        Program.Check(await run == 1 && server.Closed && window.Closed && controls.Disposed &&
            life.State == HostState.FAILED && events.Codes.Contains(code));
    }
    private sealed class ErrorReadiness(EventCode code) : IReadiness
    {
        public async Task<string> WaitAsync(IServer server, CancellationToken token)
        {
            if (code == EventCode.StartupTimeout) await Task.Delay(2000, token);
            throw new HostError(code);
        }
    }
    private sealed class ProbeWindow : IGuiWindow
    {
        internal bool Requested, Initialized, Closed, HoldDisposal, FailDisposal;
        internal int Restored, InitDelay;
        internal EventCode? Error, InitFailure;
        internal readonly TaskCompletionSource Disposed = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool CloseRequested => Requested;
        public EventCode? Failure => Error;
        public Task DisposalConfirmed => Disposed.Task;
        public async Task InitializeAsync(string url, CancellationToken token)
        { await Task.Delay(InitDelay, token); if (InitFailure is EventCode c) throw new HostError(c); Initialized = true; }
        public void RestoreOwned() => Restored++;
        public Task CloseAndConfirmAsync()
        {
            Closed = true;
            if (FailDisposal) throw new HostError(EventCode.CleanupFailed);
            if (!HoldDisposal) Disposed.TrySetResult();
            return Disposed.Task;
        }
    }
}
