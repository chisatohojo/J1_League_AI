using System.Diagnostics;
using System.Net;
using System.Reflection;
using System.Text;
using System.Text.Json;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal static class Program
{
    private static string python = "", launcher = "";
    private static int passed, failed;
    private static readonly HashSet<string> executed = new(StringComparer.Ordinal);
    private const string Empty = """
        {"schemaVersion":1,"mode":"operational","model":{"name":"Champion A","version":"operational_champion_20260922_v1"},"updatedAt":null,"previousRound":{"label":"previous","matches":[]},"nextRound":{"label":"next","matches":[]}}
        """;

    public static async Task<int> Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--synthetic-gui-tests")
            return await GuiIntegration.RunAsync(args);
        if (args.Length > 0 && args[0] == "--synthetic-owner") return await CrashOwner(args);
        if (args.Length > 0 && args[0] == "--synthetic-cleanup-owner") return await CleanupFaults.CrashOwner(args);
        if (args is ["--runner-self-test"])
        {
            await Test("intentional_assertion_failure", () => { Check(false); return Task.CompletedTask; });
            await Test("intentional_exception_failure", () => throw new InvalidOperationException());
            return Summary(2); // MUST be nonzero; never a passing suite.
        }
        if (args.Length != 3 || args[0] != "--tests" || !OperatingSystem.IsWindows()) return 2;
        python = args[1]; launcher = args[2];
        await Test("identity_python_unicode_canonical", Identity);
        await Test("identity_junction_symlink", Links);
        await Test("unicode_junction_real_server_cwd_and_gate", UnicodeServer);
        await Test("native_cli_synthetic_start_duplicate_stop_restart", NativeCli);
        await Test("symlink_launch_fail_closed", () => Throws(() =>
            RepositoryIdentity.RequireLaunchable(new RepositoryIdentity("unused", "unused") { ViaSymbolicLink = true }), EventCode.IdentityFailed));
        await Test("named_gate_show_stop_restart", Ipc);
        await Test("legacy_python_gate_and_stop_interop", LegacyInterop);
        await Test("creation_job_membership_inheritance", JobAndHandles);
        await Test("inherited_gate_excludes_until_child_cleanup", GateLifetime);
        await Test("host_abnormal_exit_reclaims_child", HostCrash);
        await Test("job_cleanup_does_not_touch_unrelated_process", Unrelated);
        await Test("windows_argv_roundtrip_and_explicit_data", Arguments);
        await Test("synthetic_loopback_readiness", RealReadiness);
        await Test("silent_stdout_total_timeout_cleanup", SilentTimeout);
        await Test("server_crash_cleanup_restart", ServerCrash);
        await Test("running_server_crash_cleanup_restart", RunningCrash);
        await Test("spawn_failure_fail_closed_no_handles_leaked", SpawnFailure);
        await Test("job_creation_native_failure_cleanup", () => WindowsFaults.JobCreation(python, Child));
        await Test("job_configuration_failure_cleanup", () => WindowsFaults.JobConfiguration(python, Child));
        await Test("create_time_job_assignment_native_failure", () => WindowsFaults.Assignment(python, Child));
        await Test("missing_assignment_rejected_before_resume", () => WindowsFaults.MissingAssignment(python, Child));
        await Test("invalid_gate_inheritance_fail_closed", () => WindowsFaults.Inheritance(python, Child, false));
        await Test("inheritable_job_handle_fail_closed", () => WindowsFaults.Inheritance(python, Child, true));
        await Test("readiness_no_proxy_no_redirect", () =>
        {
            using var handler = Readiness.CreateHandler();
            Check(!handler.UseProxy && !handler.AllowAutoRedirect && !handler.UseCookies);
            return Task.CompletedTask;
        });
        await Test("kernel_handle_leak_regression", HandleLeaks);
        await Test("lifecycle_first_stop_show_coalescing", NormalLifecycle);
        await Test("duplicate_never_starts_server", Duplicate);
        await Test("stop_during_startup_dominates_show", StartupStop);
        await Test("startup_timeout_cleanup", MockTimeout);
        await Test("uncancellable_stdout_total_deadline_cleanup", UncancellableStdout);
        await Test("cleanup_failure_is_failure", CleanupFailure);
        await Test("cleanup_timeout_retains_resources_and_gate", () => CleanupFaults.WaitFailure(python, Child, 0));
        await Test("cleanup_wait_failed_retains_resources_and_gate", () => CleanupFaults.WaitFailure(python, Child, 1));
        await Test("cleanup_wait_exception_retains_resources_and_gate", () => CleanupFaults.WaitFailure(python, Child, 2));
        await Test("cleanup_lifecycle_failure_stays_failed", () => CleanupFaults.LifecycleFailure(python, Child));
        await Test("cleanup_concurrent_close_idempotent", () => CleanupFaults.ConcurrentClose(python, Child));
        await Test("cleanup_unconfirmed_owner_survives_gc", () => CleanupFaults.GcOwnership(python, Child));
        await Test("cleanup_failed_cycles_no_handle_leak", () => CleanupFaults.HandleLeaks(python, Child));
        await Test("cleanup_quarantined_host_crash_reclaims_child", () => CleanupFaults.HostCrash(python, Child));
        await Test("unexpected_failure_sanitized", Sanitized);
        await Test("help_default_and_options_no_side_effects", Help);
        await Test("bounded_startup_stdout", Stdout);
        int urlCase = 0;
        foreach (var url in new[] { "http://localhost:5/", "http://127.0.0.2:5/", "https://127.0.0.1:5/",
            "http://127.0.0.1:0/", "http://127.0.0.1:65536/", "http://127.0.0.1:5/?demo=1",
            "http://u@127.0.0.1:5/", "http://127.0.0.1:5/#x", "http://127.0.0.1:5/\n",
            "http://[::1]:5/", "http://127.0.0.1:5/path" })
            await Test("invalid_url_" + urlCase++, () => Throws(() => Readiness.ValidateUrl(url), EventCode.InvalidUrl));
        await Test("valid_dynamic_url", () => { Check(Readiness.ValidateUrl("http://127.0.0.1:65535/") != ""); return Task.CompletedTask; });
        int payloadCase = 0;
        foreach (var text in new[] { "{}", "bad-json", Empty.Replace("\"schemaVersion\":1", "\"schemaVersion\":true"),
            Empty.Replace("\"schemaVersion\":1", "\"schemaVersion\":1,\"schemaVersion\":1"),
            Empty.Replace("operational", "demo"), Empty.Replace("Champion A", "wrong"),
            Empty.Replace("operational_champion_20260922_v1", "wrong"),
            Empty.Replace("\"updatedAt\":null", "\"updatedAt\":5"),
            Empty.Replace("\"label\":\"next\"", "\"label\":\"\""),
            Empty.Replace("\"matches\":[]", "\"matches\":{}"),
            Empty.Replace("\"name\":\"Champion A\"", "\"extra\":0,\"name\":\"Champion A\"") })
            await Test("invalid_payload_" + payloadCase++, () => Throws(() => Readiness.ValidatePayload(Encoding.UTF8.GetBytes(text)), EventCode.InvalidResponse));
        await Test("bad_utf8_payload", () => Throws(() => Readiness.ValidatePayload([0xff]), EventCode.InvalidResponse));
        await Test("http_status_content_type_size_redirect", Responses);
        await Test("http_unknown_content_length_body_cap", UnknownLength);
        var guiCases = GuiTests.Cases();
        foreach (var item in guiCases) await Test(item.Name, item.Run);
        return Summary(68 + guiCases.Count);
    }

    private static int Summary(int expected)
    {
        Console.WriteLine($"Native core + GUI-policy assertions: {passed + failed} executed / {passed} passed / {failed} failed (no GUI).");
        return failed == 0 && passed > 0 && executed.Count == passed + failed && executed.Count == expected ? 0 : 1;
    }

    private static async Task Test(string name, Func<Task> run)
    {
        if (!executed.Add(name)) throw new InvalidOperationException("duplicate_test_name");
        try { await run().WaitAsync(TimeSpan.FromSeconds(40)); passed++; Console.WriteLine("PASS " + name); }
        catch (Exception error)
        {
            failed++;
            // Deliberately no exception messages/stack traces or captured output.
            Console.WriteLine("FAIL " + name + " " + (error is HostError h ? h.Code.ToString() : error.GetType().Name));
        }
    }
    internal static void Check(bool value) { if (!value) throw new InvalidOperationException("assertion_failed"); }
    private static Task Throws(Action run, EventCode expected)
    {
        try { run(); } catch (HostError error) { Check(error.Code == expected); return Task.CompletedTask; }
        throw new InvalidOperationException("expected_failure");
    }
    private static async Task ThrowsAsync(Func<Task> run, EventCode expected)
    {
        try { await run(); } catch (HostError error) { Check(error.Code == expected); return; }
        throw new InvalidOperationException("expected_failure");
    }
    private static string Child => Path.Combine(AppContext.BaseDirectory, "synthetic_child.py");
    private static ServerCommand Command(string root, string mode, params string[] args) =>
        new(python, new[] { "-I", "-S", "-u", Child, mode }.Concat(args).ToArray(), root);
    private static InstanceControls Gate(RepositoryIdentity identity)
    { var gate = new InstanceControls(identity); Check(gate.Acquire()); return gate; }
    private static async Task<string> Line(TextReader reader) =>
        await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(5)) ?? throw new InvalidOperationException();

    private static async Task Identity()
    {
        using var temp = new TempRepository();
        foreach (string name in new[] { "ascii", "日本語 & spaces", "Straße-Σςσ-İ", "ＡＢＣ" })
        {
            string root = Path.Combine(temp.Root, name); Directory.CreateDirectory(root);
            var actual = await RepositoryIdentity.ResolveAsync(root, python, launcher);
            var expected = await Python(root, "import hashlib,sys; from pathlib import Path; " +
                "print(hashlib.sha256(str(Path(sys.argv[1]).resolve()).casefold().encode('utf-8')).hexdigest()[:24])", root);
            Check(actual.Id == expected.Trim());
            // Change only ASCII spelling of an actual alias. Modern .NET Unicode
            // uppercasing is NOT the NTFS case table (nor Python casefold).
            string alias = Path.Combine(temp.Root.ToUpperInvariant(), name);
            Check(actual.Id == (await RepositoryIdentity.ResolveAsync(alias, python, launcher)).Id);
            Check(actual.Id == (await RepositoryIdentity.ResolveAsync(Path.Combine(root, "..", name), python, launcher)).Id);
        }
    }
    private static async Task Links()
    {
        using var temp = new TempRepository();
        string junction = temp.Root + "-junction", symlink = temp.Root + "-symlink";
        try
        {
            TestLinks.Junction(junction, temp.Root);
            TestLinks.TrySymlink(symlink, temp.Root);
            Check(Directory.Exists(junction));
            var expected = await RepositoryIdentity.ResolveAsync(temp.Root, python, launcher);
            foreach (string alias in Directory.Exists(symlink) ? new[] { junction, symlink } : new[] { junction })
            {
                var actual = await RepositoryIdentity.ResolveAsync(alias, python, launcher);
                Check(actual.Id == expected.Id && actual.Root == expected.Root);
            }
            if (!Directory.Exists(symlink))
            {
                // No elevation/developer-policy change: validate an existing OS
                // symbolic link using path metadata ONLY. No IPC or files under
                // its target are opened. A missing true symlink is a test failure.
                string systemLink = Path.Combine(Path.GetPathRoot(Environment.SystemDirectory)!, "Users", "All Users");
                Check((await Python(temp.Root, "import sys; from pathlib import Path; " +
                    "assert Path(sys.argv[1]).is_symlink(); print('PASS')", systemLink)).Trim() == "PASS");
                var linked = await RepositoryIdentity.ResolveAsync(systemLink, python, launcher);
                var direct = await RepositoryIdentity.ResolveAsync(linked.Root, python, launcher);
                Check(linked.Id == direct.Id && linked.ViaSymbolicLink);
                await Throws(() => RepositoryIdentity.RequireLaunchable(linked), EventCode.IdentityFailed);
                Console.WriteLine("INFO symlink_metadata_only_existing_OS_link_no_elevation");
            }
        }
        finally
        {
            // Nonrecursive removal of these exact reparse links, never targets.
            if (Directory.Exists(junction)) Directory.Delete(junction);
            if (Directory.Exists(symlink)) Directory.Delete(symlink);
        }
    }
    private static async Task UnicodeServer()
    {
        using var temp = new TempRepository();
        string root = Path.Combine(temp.Root, "日本語 & Straße-Σςσ-İ"); Directory.CreateDirectory(root);
        string junction = temp.Root + "-unicode-junction";
        try
        {
            TestLinks.Junction(junction, root);
            var direct = await RepositoryIdentity.ResolveAsync(root, python, launcher);
            var alias = await RepositoryIdentity.ResolveAsync(junction, python, launcher);
            RepositoryIdentity.RequireLaunchable(direct); RepositoryIdentity.RequireLaunchable(alias);
            Check(direct.Id == alias.Id && direct.Root == alias.Root);
            using var gate = Gate(alias);
            using var duplicate = new InstanceControls(direct); Check(!duplicate.Acquire());
            using var server = OwnedServer.Start(Command(alias.Root, "cwd"), gate);
            string actual = JsonSerializer.Deserialize<string>(await Line(server.Output))!;
            Check(actual == direct.Root && server.AssignedBeforeResume);
        }
        finally { if (Directory.Exists(junction)) Directory.Delete(junction); }
    }
    private static async Task NativeCli()
    {
        using var temp = new TempRepository();
        string root = Path.Combine(temp.Root, "日本語 & native CLI");
        string scripts = Path.Combine(root, "scripts"), venv = Path.Combine(root, ".venv");
        Directory.CreateDirectory(scripts);
        File.Copy(launcher, Path.Combine(scripts, "launch_dashboard.py")); // implementation only
        File.Copy(Child, Path.Combine(scripts, "serve_dashboard.py")); // synthetic server only
        TestLinks.Junction(venv, Directory.GetParent(Path.GetDirectoryName(python)!)!.FullName);
        var identity = await RepositoryIdentity.ResolveAsync(root);
        string logDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "J1AI", "Dashboard", identity.Id);
        string log = Path.Combine(logDirectory, "native-core.log");
        int RunningCount() => File.Exists(log) ? File.ReadAllLines(log).Count(l => l.EndsWith(" Running", StringComparison.Ordinal)) : 0;
        Task<int>? run = null;
        try
        {
            string data = Path.Combine(root, "explicit-not-read.json");
            run = J1AI.DashboardHost.Program.Main(["--core", "--repository", root, "--data", data]);
            await Until(() => RunningCount() == 1);
            Check(await J1AI.DashboardHost.Program.Main(["--core", "--repository", root]) == 0);
            Check(RunningCount() == 1 && !File.Exists(data));
            Check(await J1AI.DashboardHost.Program.Main(["--stop", "--repository", root]) == 0);
            Check(await run.WaitAsync(TimeSpan.FromSeconds(7)) == 0);
            run = J1AI.DashboardHost.Program.Main(["--core", "--repository", root]);
            await Until(() => RunningCount() == 2);
            Check(await J1AI.DashboardHost.Program.Main(["--stop", "--repository", root]) == 0);
            Check(await run.WaitAsync(TimeSpan.FromSeconds(7)) == 0);
        }
        finally
        {
            if (run != null && !run.IsCompleted)
            { InstanceControls.Signal(identity, true); await run.WaitAsync(TimeSpan.FromSeconds(7)); }
            Directory.Delete(venv); // unlink exact junction, never recursive/target
            if (File.Exists(log)) File.Delete(log);
            if (Directory.Exists(logDirectory)) Directory.Delete(logDirectory);
        }
    }
    private static Task Ipc()
    {
        using var temp = new TempRepository();
        using (var first = Gate(temp.Identity))
        {
            using var duplicate = new InstanceControls(temp.Identity); Check(!duplicate.Acquire());
            Check(InstanceControls.Signal(temp.Identity, false)); Check(first.ConsumeShow()); Check(!first.ConsumeShow());
            Check(InstanceControls.Signal(temp.Identity, false)); Check(InstanceControls.Signal(temp.Identity, true));
            Check(first.StopRequested && !first.ConsumeShow());
        }
        using var restarted = Gate(temp.Identity); Check(!restarted.StopRequested && !restarted.ConsumeShow());
        return Task.CompletedTask;
    }
    private static async Task LegacyInterop()
    {
        using var temp = new TempRepository();
        var identity = await RepositoryIdentity.ResolveAsync(temp.Root, python, launcher);
        using (var native = Gate(identity))
        {
            var result = await Python(temp.Root,
                "import runpy,sys; from pathlib import Path; m=runpy.run_path(sys.argv[1]); " +
                "c=m['WindowsInstance'](Path(sys.argv[2])); assert not c.acquire(); " +
                "assert c.signal_stop(); c.close(); print('PASS')", launcher, temp.Root);
            Check(result.Trim() == "PASS" && native.StopRequested);
        }
        // Reverse direction: a real old Python gate prevents native server start.
        using var legacy = TestProcess.Start(python, new[] { "-I", "-S", "-u", "-c",
            "import runpy,sys,time; from pathlib import Path; m=runpy.run_path(sys.argv[1]); " +
            "c=m['WindowsInstance'](Path(sys.argv[2])); assert c.acquire(); print('READY',flush=True); " +
            "exec('while not c.stop_requested(20): time.sleep(.01)'); c.close()", launcher, temp.Root }, temp.Root, []);
        Check(await Line(legacy.Output) == "READY");
        int starts = 0;
        using var duplicate = new InstanceControls(identity);
        var engine = new Lifecycle(duplicate, () => { starts++; throw new InvalidOperationException(); },
            new FakeReadiness(), new RecordingEvents());
        Check(await engine.RunAsync(TimeSpan.FromSeconds(2)) == 0 && starts == 0);
        Check(InstanceControls.Signal(identity, true));
        Check(legacy.Wait(5000));
        using var recovered = Gate(identity);
    }

    private static async Task JobAndHandles()
    {
        using var temp = new TempRepository(); using var gate = Gate(temp.Identity);
        using var unwanted = Native.CreateEventW(0, true, false, @"Local\J1AI.Test." + Guid.NewGuid());
        Native.Require(Native.SetHandleInformation(unwanted, 1, 1));
        using var child = OwnedServer.Start(Command(temp.Root, "probe"), gate, (job, inheritedGate, output, nul) =>
            Command(temp.Root, "probe", job.ToString(), inheritedGate.ToString(), output.ToString(), nul.ToString(),
                unwanted.DangerousGetHandle().ToString(), gate.Gate.ToString()));
        Check(child.AssignedBeforeResume);
        using var result = JsonDocument.Parse(await Line(child.Output));
        Check(result.RootElement.GetProperty("in_job").GetBoolean());
        Check(result.RootElement.GetProperty("valid").EnumerateArray().Select(x => x.GetBoolean())
            .SequenceEqual(new[] { false, true, true, true, false, false }));
        using var retained = Native.Duplicate(child.ProcessHandle, false);
        child.CloseAndWait(); Check(Native.WaitForSingleObject(retained, 0) == Native.WaitObject);
    }
    private static Task GateLifetime()
    {
        using var temp = new TempRepository(); var gate = Gate(temp.Identity);
        using var child = OwnedServer.Start(Command(temp.Root, "silent"), gate);
        gate.Dispose(); // Deliberate host-handle loss while its server is live.
        for (int i = 0; i < 50; i++)
        {
            Check(!child.Exited);
            using var duplicate = new InstanceControls(temp.Identity); Check(!duplicate.Acquire());
        }
        child.CloseAndWait();
        using var recovered = Gate(temp.Identity);
        return Task.CompletedTask;
    }

    private static async Task HostCrash()
    {
        using var temp = new TempRepository();
        using var parent = Native.Duplicate(Native.GetCurrentProcess(), true);
        using var host = TestProcess.Start(Environment.ProcessPath!,
            new[] { Assembly.GetExecutingAssembly().Location, "--synthetic-owner", python, temp.Root, temp.Identity.Id,
                parent.DangerousGetHandle().ToString() }, temp.Root, [parent.DangerousGetHandle()]);
        using var child = new KernelHandle(nint.Parse(await Line(host.Output)));
        Check(Native.WaitForSingleObject(child, 0) == Native.WaitTimeout);
        using (var duplicate = new InstanceControls(temp.Identity)) Check(!duplicate.Acquire());
        host.KillOwned(); Check(host.Wait(5000));
        Check(Native.WaitForSingleObject(child, 5000) == Native.WaitObject);
        using var recovered = Gate(temp.Identity);
    }
    private static async Task<int> CrashOwner(string[] args)
    {
        python = args[1];
        var identity = new RepositoryIdentity(args[2], args[3]);
        using var gate = Gate(identity);
        using var child = OwnedServer.Start(Command(identity.Root, "silent"), gate);
        Native.Require(Native.DuplicateHandle(Native.GetCurrentProcess(), child.ProcessHandle, nint.Parse(args[4]),
            out var remote, 0, false, 2));
        Console.WriteLine(remote.ToString()); Console.Out.Flush();
        await Task.Delay(Timeout.Infinite);
        return 0;
    }
    private static Task Unrelated()
    {
        using var temp = new TempRepository();
        using var other = TestProcess.Start(python, new[] { "-I", "-S", "-u", Child, "silent" }, temp.Root, []);
        using var gate = Gate(temp.Identity);
        using var owned = OwnedServer.Start(Command(temp.Root, "silent"), gate);
        owned.CloseAndWait(); Check(!other.Wait(0));
        return Task.CompletedTask;
    }
    private static async Task Arguments()
    {
        using var temp = new TempRepository(); using var gate = Gate(temp.Identity);
        string[] values = ["", "a b & 日本語", "quote\"inside", "C:\\trailing\\", "slash\\\"quote", "--data", "not-read.json"];
        using var child = OwnedServer.Start(Command(temp.Root, "argv", values), gate);
        Check(JsonSerializer.Deserialize<string[]>(await Line(child.Output))!.SequenceEqual(values));
        var command = ServerCommand.Dashboard(temp.Identity, null);
        Check(command.Executable == temp.Identity.Python && command.WorkingDirectory == temp.Root);
        Check(command.Arguments.SequenceEqual(new[] { "-u", "-m", "scripts.serve_dashboard", "--port", "0" }));
        string data = Path.Combine(temp.Root, "never-created & 日本語.json");
        Check(ServerCommand.Dashboard(temp.Identity, data).Arguments.TakeLast(2).SequenceEqual(new[] { "--data", data }));
        Check(!File.Exists(data));
    }
    private static async Task RealReadiness()
    {
        using var temp = new TempRepository(); using var gate = Gate(temp.Identity);
        using var server = OwnedServer.Start(Command(temp.Root, "ready"), gate);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        var url = await new Readiness().WaitAsync(server, deadline.Token);
        Check(url == Readiness.ValidateUrl(url) && !server.Exited);
    }
    private static async Task SilentTimeout()
    {
        using var temp = new TempRepository(); using var gate = new InstanceControls(temp.Identity);
        var events = new RecordingEvents();
        var engine = new Lifecycle(gate, () => OwnedServer.Start(Command(temp.Root, "silent"), gate), new Readiness(), events);
        var elapsed = Stopwatch.StartNew();
        Check(await engine.RunAsync(TimeSpan.FromMilliseconds(150)) == 1);
        Check(elapsed.Elapsed < TimeSpan.FromSeconds(7) && events.Codes.Contains(EventCode.StartupTimeout));
        using var recovered = Gate(temp.Identity);
    }
    private static async Task ServerCrash()
    {
        using var temp = new TempRepository(); using var gate = new InstanceControls(temp.Identity);
        var events = new RecordingEvents();
        var engine = new Lifecycle(gate, () => OwnedServer.Start(Command(temp.Root, "exit"), gate), new Readiness(), events);
        Check(await engine.RunAsync(TimeSpan.FromSeconds(3)) == 1);
        Check(events.Codes.Any(c => c is EventCode.ServerExited or EventCode.InvalidUrl));
        using var recovered = Gate(temp.Identity);
    }
    private static async Task RunningCrash()
    {
        using var temp = new TempRepository(); using var gate = new InstanceControls(temp.Identity);
        OwnedServer? server = null; var events = new RecordingEvents();
        var engine = new Lifecycle(gate, () => server = OwnedServer.Start(Command(temp.Root, "ready"), gate),
            new Readiness(), events);
        var run = engine.RunAsync(TimeSpan.FromSeconds(5));
        await Until(() => engine.State == HostState.RUNNING);
        using var retained = Native.Duplicate(server!.ProcessHandle, false);
        Native.Require(Native.TerminateProcess(retained, 7)); // exclusively this synthetic server
        Check(await run == 1 && events.Codes.Contains(EventCode.ServerExited));
        Check(Native.WaitForSingleObject(retained, 0) == Native.WaitObject);
        using var recovered = Gate(temp.Identity);
    }
    private static async Task SpawnFailure()
    {
        using var temp = new TempRepository(); using var gate = Gate(temp.Identity);
        var absent = new ServerCommand(Path.Combine(temp.Root, "absent.exe"), [], temp.Root);
        // Prime the CLR exception/interop path before measuring persistent growth.
        await Throws(() => OwnedServer.Start(absent, gate), EventCode.SpawnFailed);
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint before));
        for (int i = 0; i < 32; i++) await Throws(() => OwnedServer.Start(absent, gate), EventCode.SpawnFailed);
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint after));
        Console.WriteLine($"INFO failed_spawn_handle_counts {before} {after}");
        Check(after <= before + 1);
    }
    private static Task HandleLeaks()
    {
        using var temp = new TempRepository();
        void Cycle()
        {
            using var gate = Gate(temp.Identity);
            using var server = OwnedServer.Start(Command(temp.Root, "silent"), gate);
        }
        Cycle(); GC.Collect(); GC.WaitForPendingFinalizers();
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint before));
        for (int i = 0; i < 20; i++) Cycle();
        GC.Collect(); GC.WaitForPendingFinalizers();
        Native.Require(Native.GetProcessHandleCount(Native.GetCurrentProcess(), out uint after));
        Check(after <= before + 2);
        return Task.CompletedTask;
    }

    private static async Task NormalLifecycle()
    {
        var controls = new FakeControls { Shows = true };
        var server = new FakeServer(); var events = new RecordingEvents();
        var ready = new FakeReadiness { Delay = 80 };
        int starts = 0;
        var engine = new Lifecycle(controls, () => { starts++; return server; }, ready, events);
        var run = engine.RunAsync(TimeSpan.FromSeconds(2));
        await Until(() => engine.State == HostState.RUNNING);
        controls.Stop = true;
        Check(await run == 0 && starts == 1 && engine.State == HostState.STOPPED);
        Check(events.Codes.Count(c => c == EventCode.ShowPending) == 1 && engine.ShowPending);
        Check(server.Closed && controls.Disposed);
        Check(events.Codes.Contains(EventCode.Closing) && events.Codes.Contains(EventCode.Cleanup));
    }
    private static async Task Duplicate()
    {
        var controls = new FakeControls { Owned = false };
        int starts = 0; var ready = new FakeReadiness();
        var engine = new Lifecycle(controls, () => { starts++; return new FakeServer(); }, ready, new RecordingEvents());
        Check(await engine.RunAsync(TimeSpan.FromSeconds(1)) == 0);
        Check(starts == 0 && ready.Calls == 0 && controls.ShowSignals == 1);
    }
    private static async Task StartupStop()
    {
        var controls = new FakeControls { Shows = true }; var server = new FakeServer();
        var engine = new Lifecycle(controls, () => { controls.Stop = true; return server; },
            new FakeReadiness { Delay = 10000 }, new RecordingEvents());
        Check(await engine.RunAsync(TimeSpan.FromSeconds(1)) == 0 && !engine.ShowPending && server.Closed);
    }
    private static async Task MockTimeout()
    {
        var server = new FakeServer(); var controls = new FakeControls();
        var events = new RecordingEvents();
        var engine = new Lifecycle(controls, () => server, new FakeReadiness { Delay = 10000 }, events);
        Check(await engine.RunAsync(TimeSpan.FromMilliseconds(50)) == 1);
        Check(server.Closed && controls.Disposed && events.Codes.Contains(EventCode.StartupTimeout));
    }
    private static async Task UncancellableStdout()
    {
        var reader = new StalledReader();
        var server = new FakeServer { Reader = reader };
        var events = new RecordingEvents();
        var engine = new Lifecycle(new FakeControls(), () => server, new Readiness(), events);
        var elapsed = Stopwatch.StartNew();
        Check(await engine.RunAsync(TimeSpan.FromMilliseconds(50)) == 1);
        Check(elapsed.Elapsed < TimeSpan.FromSeconds(2) && server.Closed && reader.Released);
        Check(events.Codes.Contains(EventCode.StartupTimeout));
    }
    private static async Task CleanupFailure()
    {
        var controls = new FakeControls();
        var server = new FakeServer { FailCleanup = true };
        var engine = new Lifecycle(controls, () => { controls.Stop = true; return server; }, new FakeReadiness(), new RecordingEvents());
        await ThrowsAsync(async () => { await engine.RunAsync(TimeSpan.FromSeconds(1)); }, EventCode.CleanupFailed);
        Check(controls.Disposed && engine.State == HostState.FAILED);
    }
    private static async Task Sanitized()
    {
        var events = new RecordingEvents();
        var engine = new Lifecycle(new FakeControls(), () => throw new Exception("secret synthetic data"), new FakeReadiness(), events);
        Check(await engine.RunAsync(TimeSpan.FromSeconds(1)) == 1);
        Check(events.Codes.Contains(EventCode.UnexpectedFailure));
        Check(new HostError(EventCode.InvalidResponse).Message == "InvalidResponse");
        using var temp = new TempRepository();
        var logger = new FileEvents(temp.Identity.Id);
        logger.Record(EventCode.Running);
        var path = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "J1AI", "Dashboard", temp.Identity.Id, "native-core.log");
        Check(File.ReadAllText(path).Split(' ').Last().Trim() == "Running");
        File.Delete(path); Directory.Delete(Path.GetDirectoryName(path)!); // exact fresh namespace, nonrecursive
    }
    private static async Task Help()
    {
        Check(await J1AI.DashboardHost.Program.Main(["--help"]) == 0);
        Check(await J1AI.DashboardHost.Program.Main([]) == 0);
        Check(Options.Parse(["--core", "--data", "synthetic.json"]).Data != null);
        foreach (var value in new[] { "0", "121", "NaN", "Infinity", "oops" })
            await Throws(() => Options.Parse(["--core", "--startup-timeout", value]), EventCode.InvalidArguments);
        await Throws(() => Options.Parse(["--stop", "--data", "synthetic.json"]), EventCode.InvalidArguments);
    }
    private static async Task Stdout()
    {
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(1));
        Check(await Readiness.ReadUrlAsync(new StringReader("ignored\nJ1AI dashboard: http://127.0.0.1:12345/\r\n"), deadline.Token)
            == "http://127.0.0.1:12345/");
        foreach (string text in new[] { "", "wrong prefix\n", "J1AI dashboard: http://127.0.0.1:5/?demo=1\n", new string('x', 4097) })
            await ThrowsAsync(async () => { await Readiness.ReadUrlAsync(new StringReader(text), deadline.Token); }, EventCode.InvalidUrl);
    }
    private static async Task Responses()
    {
        foreach (var item in new[] { (HttpStatusCode.Found, "application/json", Empty),
            (HttpStatusCode.NotFound, "application/json", Empty), (HttpStatusCode.OK, "text/html", Empty),
            (HttpStatusCode.OK, "application/json", new string('x', Readiness.MaxBytes + 1)) })
        {
            using var response = new HttpResponseMessage(item.Item1) { Content = new StringContent(item.Item3, Encoding.UTF8, item.Item2) };
            await ThrowsAsync(() => Readiness.ValidateResponseAsync(response, CancellationToken.None), EventCode.InvalidResponse);
        }
        using var valid = new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(Empty, Encoding.UTF8, "application/json") };
        await Readiness.ValidateResponseAsync(valid, CancellationToken.None);
    }
    private static async Task UnknownLength()
    {
        using var stream = new NonSeekStream(new byte[Readiness.MaxBytes + 1]);
        using var response = new HttpResponseMessage(HttpStatusCode.OK) { Content = new StreamContent(stream) };
        response.Content.Headers.ContentType = new("application/json");
        Check(response.Content.Headers.ContentLength == null);
        await ThrowsAsync(() => Readiness.ValidateResponseAsync(response, CancellationToken.None), EventCode.InvalidResponse);
    }

    private static async Task Until(Func<bool> predicate)
    {
        var elapsed = Stopwatch.StartNew();
        while (!predicate()) { Check(elapsed.Elapsed < TimeSpan.FromSeconds(5)); await Task.Delay(10); }
    }
    private static async Task<string> Python(string root, string code, params string[] args)
    {
        using var process = TestProcess.Start(python, new[] { "-I", "-S", "-u", "-c", code }.Concat(args).ToArray(), root, []);
        string output = await process.Output.ReadToEndAsync().WaitAsync(TimeSpan.FromSeconds(10));
        Check(process.Wait(5000)); return output;
    }
}

internal sealed class TempRepository : IDisposable
{
    internal string Root { get; } = Path.Combine(Path.GetTempPath(), "J1AI-native-test-" + Guid.NewGuid().ToString("N"));
    internal RepositoryIdentity Identity { get; }
    internal TempRepository()
    {
        Directory.CreateDirectory(Root);
        Identity = new(Root, Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(Root))).ToLowerInvariant()[..24]);
    }
    public void Dispose()
    {
        // Root is a fresh OS-temp namespace, never a repository or user input.
        var path = Path.GetFullPath(Root);
        if (!path.StartsWith(Path.GetFullPath(Path.GetTempPath()), StringComparison.OrdinalIgnoreCase) ||
            !Path.GetFileName(path).StartsWith("J1AI-native-test-", StringComparison.Ordinal)) throw new InvalidOperationException();
        Directory.Delete(path, true);
    }
}

internal sealed class FakeControls : IControls
{
    internal bool Owned = true, Stop, Shows, Disposed;
    internal int ShowSignals;
    public bool Acquire() => Owned;
    public bool StopRequested => Stop;
    public bool ConsumeShow() => Shows;
    public void RequestShow() => ShowSignals++;
    public void Dispose() => Disposed = true;
}
internal sealed class FakeServer : IServer
{
    internal bool Closed, FailCleanup;
    internal TextReader? Reader;
    public TextReader Output => Reader ?? new StringReader("");
    public bool Exited => false;
    public void CloseAndWait()
    { if (FailCleanup) throw new Exception("private synthetic failure"); Closed = true; Reader?.Dispose(); }
    public void Dispose() => CloseAndWait();
}

internal sealed class StalledReader : TextReader
{
    private readonly TaskCompletionSource<int> source = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal bool Released;
    public override ValueTask<int> ReadAsync(Memory<char> buffer, CancellationToken token = default) => new(source.Task);
    protected override void Dispose(bool disposing) { Released = true; source.TrySetResult(0); base.Dispose(disposing); }
}
internal sealed class NonSeekStream(byte[] bytes) : MemoryStream(bytes)
{
    public override bool CanSeek => false;
}
internal sealed class FakeReadiness : IReadiness
{
    internal int Calls, Delay;
    public async Task<string> WaitAsync(IServer server, CancellationToken token)
    { Calls++; await Task.Delay(Delay, token); return "http://127.0.0.1:1234/"; }
}
internal sealed class RecordingEvents : IEvents
{
    internal List<EventCode> Codes = [];
    public void Record(EventCode code) => Codes.Add(code);
}
