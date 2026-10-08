"""Synthetic/mocked launcher checks: no GUI, Desktop, models or real data IO."""

import ast
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from scripts import launch_dashboard as launcher
from scripts.serve_dashboard import empty_dashboard


@pytest.fixture
def fake_root(tmp_path):
    root = tmp_path / "repo with spaces & 日本語"
    scripts = root / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "python.exe").touch()
    (scripts / "pythonw.exe").touch()
    return root


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    return tmp_path / "local"


def fake_process(output="J1AI dashboard: http://127.0.0.1:45678/\n", exit_code=None):
    return SimpleNamespace(
        stdout=io.StringIO(output), poll=Mock(return_value=exit_code),
        terminate=Mock(), wait=Mock(),
    )


def test_repository_root_ignores_cwd(tmp_path, monkeypatch):
    expected = Path(launcher.__file__).resolve().parents[1]
    monkeypatch.chdir(tmp_path)
    assert launcher.repository_root() == expected


@pytest.mark.parametrize("platform", ["linux", "darwin", "cygwin"])
def test_windows_only(monkeypatch, platform):
    monkeypatch.setattr(launcher.sys, "platform", platform)
    with pytest.raises(launcher.LauncherError, match="requires Windows"):
        launcher.require_windows()


def test_windows_accepted(monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    launcher.require_windows()


def test_venv_python_is_explicit(fake_root):
    assert launcher.find_python(fake_root) == fake_root / ".venv/Scripts/python.exe"


def test_missing_venv_rejected(tmp_path):
    with pytest.raises(launcher.LauncherError, match="Missing .venv"):
        launcher.find_python(tmp_path)


@pytest.mark.parametrize("location", ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"])
def test_edge_standard_locations(tmp_path, location):
    edge = tmp_path / "Microsoft/Edge/Application/msedge.exe"
    edge.parent.mkdir(parents=True)
    edge.touch()
    assert launcher.find_browser({location: str(tmp_path)}) == edge


def test_edge_priority_over_every_chrome_location(tmp_path):
    chrome = tmp_path / "programs/Google/Chrome/Application/chrome.exe"
    edge = tmp_path / "user/Microsoft/Edge/Application/msedge.exe"
    for target in (chrome, edge):
        target.parent.mkdir(parents=True)
        target.touch()
    assert launcher.find_browser({"ProgramFiles(x86)": str(tmp_path / "programs"), "LOCALAPPDATA": str(tmp_path / "user")}) == edge


@pytest.mark.parametrize("location", ["ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"])
def test_chrome_fallback(tmp_path, location):
    chrome = tmp_path / "Google/Chrome/Application/chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.touch()
    assert launcher.find_browser({location: str(tmp_path)}) == chrome


def test_browser_absent_is_error_not_tab_fallback():
    with pytest.raises(launcher.LauncherError, match="was not found"):
        launcher.find_browser({})


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:1234/", "http://localhost:1234/", "http://[::1]:1234/",
    "http://example.invalid:1234/", "http://127.0.0.1:0/", "http://127.0.0.1:65536/",
    "http://127.0.0.1:1234/?demo=1", "http://127.0.0.1:1234/path",
    "http://user@127.0.0.1:1234/", "http://127.0.0.1:1234/#x",
    "http://127.0.0.1:1234/\n", "http://127.0.0.1:1234\\", "http://127.0.0.2:1234/",
])
def test_only_exact_ipv4_loopback_url(url):
    with pytest.raises(launcher.LauncherError, match="loopback"):
        launcher.validate_url(url)


@pytest.mark.parametrize("port", [1, 8765, 45678, 65535])
def test_actual_valid_ports(port):
    url = f"http://127.0.0.1:{port}/"
    assert launcher.validate_url(url) == url


def test_app_mode_and_isolated_profile_arguments(tmp_path):
    browser = tmp_path / "Program Files/msedge.exe"
    profile = tmp_path / "J1AI/profile with spaces & 日本語"
    command = launcher.browser_command(browser, "http://127.0.0.1:45678/", profile)
    assert command[:3] == [str(browser), "--app=http://127.0.0.1:45678/", f"--user-data-dir={profile}"]
    assert "--no-first-run" in command
    assert "--disable-background-networking" in command
    assert "--disable-sync" in command
    assert not profile.exists()


def test_default_server_command_does_not_discover_data(fake_root, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No discovery/read/generation of prediction or feed files")
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "glob", forbidden)
    command = launcher.server_command(fake_root / ".venv/Scripts/python.exe", None)
    assert command == [str(fake_root / ".venv/Scripts/python.exe"), "-u", "-m", "scripts.serve_dashboard", "--port", "0"]
    assert "--data" not in command
    data = empty_dashboard()
    assert not data["previousRound"]["matches"] and not data["nextRound"]["matches"]
    launcher.validate_ready_payload(data)


def test_explicit_json_passed_only_to_server_not_read(fake_root, monkeypatch):
    data = fake_root / 'prepared & 日本語.json'
    monkeypatch.setattr(Path, "read_text", Mock(side_effect=AssertionError("No launcher JSON file read")))
    command = launcher.server_command(fake_root / ".venv/Scripts/python.exe", data)
    assert command[-2:] == ["--data", str(data.resolve())]
    assert not data.exists()


def test_hidden_safe_process_launch_arguments(fake_root, isolated_env, monkeypatch):
    calls = []
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda args, **kwargs: calls.append((args, kwargs)) or fake_process())
    python = fake_root / ".venv/Scripts/python.exe"
    data = fake_root / "prepared & file.json"
    launcher.start_server(python, fake_root, data)
    browser = fake_root / "Program Files/msedge.exe"
    profile = launcher.local_directory(fake_root) / "edge-profile"
    launcher.start_browser(browser, "http://127.0.0.1:45678/", profile, fake_root)
    assert len(calls) == 2
    assert calls[0][0][-1] == str(data.resolve())
    for arguments, options in calls:
        assert isinstance(arguments, list)
        assert options["shell"] is False
        assert options["cwd"] == str(fake_root)
        assert options["creationflags"] == launcher.CREATE_NO_WINDOW
        assert options["stdin"] == subprocess.DEVNULL
        assert options["stderr"] == subprocess.DEVNULL
    assert calls[0][1]["stdout"] == subprocess.PIPE
    assert calls[1][1]["stdout"] == subprocess.DEVNULL
    assert profile.is_relative_to(isolated_env / "J1AI")


@pytest.mark.parametrize("which,code", [("server", "server_spawn_failed"), ("browser", "browser_spawn_failed")])
def test_spawn_errors_sanitized(which, code, fake_root, monkeypatch):
    monkeypatch.setattr(launcher.subprocess, "Popen", Mock(side_effect=OSError("sensitive synthetic payload")))
    with pytest.raises(launcher.LauncherError) as error:
        if which == "server":
            launcher.start_server(fake_root / "python.exe", fake_root, None)
        else:
            launcher.start_browser(fake_root / "msedge.exe", "http://127.0.0.1:1234/", fake_root / "profile", fake_root)
    assert error.value.code == code
    assert "sensitive" not in str(error.value)


def test_local_appdata_required(fake_root, monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    with pytest.raises(launcher.LauncherError, match="LOCALAPPDATA"):
        launcher.local_directory(fake_root)


def test_local_directory_and_instance_id_are_per_repository(fake_root, isolated_env):
    assert launcher.local_directory(fake_root).is_relative_to(isolated_env / "J1AI/Dashboard")
    assert launcher.instance_id(fake_root) == launcher.instance_id(fake_root)
    assert launcher.instance_id(fake_root) != launcher.instance_id(fake_root / "other")


def test_dynamic_url_readiness(fake_root, monkeypatch):
    process = fake_process("ignored data-free line\nJ1AI dashboard: http://127.0.0.1:53127/\n")
    check = Mock()
    monkeypatch.setattr(launcher, "check_ready", check)
    assert launcher.wait_for_ready(process, 2) == "http://127.0.0.1:53127/"
    assert check.call_args.args == ("http://127.0.0.1:53127/",)
    assert 0 < check.call_args.kwargs["timeout"] <= 1


def test_server_abnormal_exit_prevents_readiness(monkeypatch):
    monkeypatch.setattr(launcher, "check_ready", Mock(side_effect=AssertionError("must not request")))
    with pytest.raises(launcher.LauncherError) as error:
        launcher.wait_for_ready(fake_process(exit_code=2), 0.5)
    assert error.value.code == "server_exited"


@pytest.mark.parametrize("output", ["", "wrong prefix\n", "J1AI dashboard: http://external.invalid:1234/\n"])
def test_bad_startup_output(output, monkeypatch):
    monkeypatch.setattr(launcher, "check_ready", Mock(side_effect=AssertionError("must not request")))
    with pytest.raises(launcher.LauncherError) as error:
        launcher.wait_for_ready(fake_process(output), 0.5)
    assert error.value.code == "invalid_url"


def test_readiness_timeout_bounded(monkeypatch):
    monkeypatch.setattr(launcher, "check_ready", Mock(side_effect=URLError("connection refused")))
    start = launcher.time.monotonic()
    with pytest.raises(launcher.LauncherError) as error:
        launcher.wait_for_ready(fake_process(), 0.03)
    assert error.value.code == "startup_timeout"
    assert launcher.time.monotonic() - start < 1


def test_no_startup_output_times_out(monkeypatch):
    # Fake blocked reader without leaving a blocked IO thread in the test.
    monkeypatch.setattr(launcher, "_read_startup_url", lambda *args: None)
    with pytest.raises(launcher.LauncherError) as error:
        launcher.wait_for_ready(fake_process(), 0.01)
    assert error.value.code == "startup_timeout"


def test_http_probe_cannot_extend_supervisor_deadline(monkeypatch):
    released = threading.Event()
    completed = threading.Event()
    def stalled_probe(*args, **kwargs):
        try:
            released.wait(timeout=2)
        finally:
            completed.set()
    monkeypatch.setattr(launcher, "check_ready", stalled_probe)
    start = launcher.time.monotonic()
    try:
        with pytest.raises(launcher.LauncherError) as error:
            launcher.wait_for_ready(fake_process(), 0.03)
        assert error.value.code == "startup_timeout"
        assert launcher.time.monotonic() - start < 1
    finally:
        released.set()
        assert completed.wait(timeout=2)


def test_invalid_response_not_retried(monkeypatch):
    check = Mock(side_effect=launcher.LauncherError("invalid_response"))
    monkeypatch.setattr(launcher, "check_ready", check)
    with pytest.raises(launcher.LauncherError):
        launcher.wait_for_ready(fake_process(), 1)
    assert check.call_count == 1


@pytest.mark.parametrize("mutation", [
    lambda data: data.update(schemaVersion=True), lambda data: data.update(schemaVersion=2),
    lambda data: data.update(mode="demo"), lambda data: data.update(extra="forbidden"),
    lambda data: data["model"].update(version="wrong"), lambda data: data["model"].update(extra="forbidden"),
    lambda data: data.update(updatedAt=123), lambda data: data.update(nextRound=[]),
    lambda data: data["previousRound"].update(matches={}), lambda data: data["nextRound"].update(label=""),
    lambda data: data["nextRound"].update(extra="forbidden"),
])
def test_invalid_basic_readiness_schema(mutation):
    data = deepcopy(empty_dashboard())
    mutation(data)
    with pytest.raises(launcher.LauncherError) as error:
        launcher.validate_ready_payload(data)
    assert error.value.code == "invalid_response"


def test_readiness_no_proxy_no_redirect_and_bounded_bytes(monkeypatch):
    response = Mock()
    response.status = 200
    response.headers.get_content_type.return_value = "application/json"
    response.read.return_value = json.dumps(empty_dashboard()).encode()
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    captured = []
    monkeypatch.setattr(launcher, "build_opener", lambda *handlers: captured.extend(handlers) or opener)
    launcher.check_ready("http://127.0.0.1:1234/", 0.4)
    assert captured[0].proxies == {}
    with pytest.raises(launcher.LauncherError):
        captured[1].redirect_request(None, None, 302, "redirect", None, "http://external.invalid/")
    opener.open.assert_called_once_with("http://127.0.0.1:1234/api/dashboard", timeout=0.4)
    response.read.assert_called_once_with(launcher.MAX_RESPONSE_BYTES + 1)


@pytest.mark.parametrize("body,status,content_type", [
    (b"not json", 200, "application/json"), (b"{}", 200, "application/json"),
    (b'{"x":1,"x":2}', 200, "application/json"), (b"\xff", 200, "application/json"),
    (b"{}", 404, "application/json"), (b"{}", 200, "text/html"),
    (b"x" * (launcher.MAX_RESPONSE_BYTES + 1), 200, "application/json"),
], ids=["not-json", "bad-schema", "duplicate-keys", "bad-encoding", "bad-status", "bad-content-type", "too-large"])
def test_reject_bad_http_response(monkeypatch, body, status, content_type):
    class Response:
        headers = SimpleNamespace(get_content_type=lambda: content_type)
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, *args): return body
    response = Response()
    response.status = status
    monkeypatch.setattr(launcher, "build_opener", lambda *args: SimpleNamespace(open=lambda *args, **kwargs: response))
    with pytest.raises(launcher.LauncherError) as error:
        launcher.check_ready("http://127.0.0.1:1234/", 0.1)
    assert error.value.code == "invalid_response"


class FakeKernel:
    def __init__(self):
        self.error = 0
        self.CreateMutexW = Mock(return_value=101)
        self.CreateEventW = Mock(return_value=102)
        self.OpenEventW = Mock(return_value=103)
        self.SetEvent = Mock(return_value=True)
        self.WaitForSingleObject = Mock(return_value=258)
        self.CloseHandle = Mock(return_value=True)


def controls(root):
    api = FakeKernel()
    instance = launcher.WindowsInstance(root, api=api, last_error=lambda: api.error)
    return instance, api


def test_named_mutex_lifetime_and_event(fake_root):
    instance, api = controls(fake_root)
    assert instance.acquire()
    assert api.CreateMutexW.call_args.args == (None, False, instance.name)
    assert api.CreateEventW.call_args.args == (None, True, False, instance.name + ".Stop")
    assert not instance.stop_requested()
    api.WaitForSingleObject.return_value = 0
    assert instance.stop_requested()
    instance.close()
    instance.close()
    assert [call.args[0] for call in api.CloseHandle.call_args_list] == [102, 101]


def test_duplicate_mutex_never_creates_stop_event(fake_root):
    instance, api = controls(fake_root)
    api.error = 183
    assert not instance.acquire()
    api.CreateEventW.assert_not_called()
    api.CloseHandle.assert_called_once_with(101)


def test_mutex_failure(fake_root):
    instance, api = controls(fake_root)
    api.CreateMutexW.return_value = None
    with pytest.raises(launcher.LauncherError): instance.acquire()
    api.CreateEventW.assert_not_called()


def test_stop_event_creation_failure_releases_mutex(fake_root):
    instance, api = controls(fake_root)
    api.CreateEventW.return_value = None
    with pytest.raises(launcher.LauncherError): instance.acquire()
    api.CloseHandle.assert_called_once_with(101)


def test_signal_only_own_named_event(fake_root):
    instance, api = controls(fake_root)
    assert instance.signal_stop()
    api.OpenEventW.assert_called_once_with(2, False, instance.name + ".Stop")
    api.SetEvent.assert_called_once_with(103)
    api.CloseHandle.assert_called_once_with(103)
    api.CreateMutexW.assert_not_called()


def test_stale_state_absence_does_not_block(fake_root):
    instance, api = controls(fake_root)
    api.OpenEventW.return_value = None
    api.error = 2
    assert not instance.signal_stop()
    api.error = 0
    assert instance.acquire()
    instance.close()


@pytest.mark.parametrize("failure", ["open", "set", "wait"])
def test_control_errors(fake_root, failure):
    instance, api = controls(fake_root)
    if failure == "open":
        api.OpenEventW.return_value = None
        api.error = 5
    elif failure == "set":
        api.SetEvent.return_value = False
    else:
        api.WaitForSingleObject.return_value = 0xFFFFFFFF
    with pytest.raises(launcher.LauncherError):
        instance.stop_requested() if failure == "wait" else instance.signal_stop()
    if failure == "set": api.CloseHandle.assert_called_once_with(103)


@pytest.mark.skipif(launcher.sys.platform != "win32", reason="real kernel-object integration is Windows-only")
def test_windows_kernel_duplicate_stop_and_recovery(tmp_path):
    # Only temporary-repository IPC names; no actual dashboard/browser/desktop.
    first = launcher.WindowsInstance(tmp_path)
    duplicate = launcher.WindowsInstance(tmp_path)
    stopper = launcher.WindowsInstance(tmp_path)
    recovered = launcher.WindowsInstance(tmp_path)
    try:
        assert first.acquire()
        assert not duplicate.acquire()
        assert stopper.signal_stop()
        assert first.stop_requested(100)
        first.close()
        assert recovered.acquire()
        assert not recovered.stop_requested(0)
    finally:
        for instance in (first, duplicate, stopper, recovered): instance.close()


@pytest.mark.skipif(launcher.sys.platform != "win32", reason="hidden server process is Windows-only")
def test_windows_empty_server_smoke_in_synthetic_repository(fake_root):
    # Copy implementation code, NOT a production file, into a disposable repo.
    # The server's default empty payload performs no data/model reads.
    scripts = fake_root / "scripts"
    scripts.mkdir()
    shutil.copyfile(Path(launcher.__file__).parent / "serve_dashboard.py", scripts / "serve_dashboard.py")
    process = launcher.start_server(Path(launcher.sys.executable), fake_root, None)
    try:
        url = launcher.wait_for_ready(process, 5)
        assert launcher.validate_url(url) == url
        opener = launcher.build_opener(launcher.ProxyHandler({}))
        with opener.open(url + "api/dashboard", timeout=2) as response:
            payload = json.loads(response.read(1024 * 1024))
        assert payload == empty_dashboard()
        assert process.poll() is None
    finally:
        launcher.stop_owned_server(process)
    assert process.poll() is not None


@pytest.fixture
def runtime(fake_root, monkeypatch):
    state = Mock()
    state.acquire.return_value = True
    state.stop_requested.return_value = True
    process = fake_process()
    browser_process = Mock()
    browser_process.poll.side_effect = AssertionError("Startup PID is NOT window lifetime")
    browser_process.wait.side_effect = AssertionError("Startup PID is NOT window lifetime")
    monkeypatch.setattr(launcher, "require_windows", lambda: None)
    monkeypatch.setattr(launcher, "WindowsInstance", lambda root: state)
    monkeypatch.setattr(launcher, "find_browser", lambda: fake_root / "msedge.exe")
    monkeypatch.setattr(launcher, "local_directory", lambda root: fake_root / "local")
    start = Mock(return_value=process)
    ready = Mock(return_value="http://127.0.0.1:45678/")
    browser = Mock(return_value=browser_process)
    events, messages = [], []
    monkeypatch.setattr(launcher, "start_server", start)
    monkeypatch.setattr(launcher, "wait_for_ready", ready)
    monkeypatch.setattr(launcher, "start_browser", browser)
    monkeypatch.setattr(launcher, "record_event", lambda root, code: events.append(code))
    monkeypatch.setattr(launcher, "show_message", lambda text, **kwargs: messages.append(text))
    return SimpleNamespace(state=state, server=process, start=start, ready=ready, browser=browser,
                           browser_process=browser_process, events=events, messages=messages)


def test_full_empty_start_stop_and_browser_not_killed(runtime, fake_root):
    assert launcher.run_launcher(fake_root) == 0
    runtime.start.assert_called_once_with(fake_root / ".venv/Scripts/python.exe", fake_root, None)
    runtime.browser.assert_called_once_with(fake_root / "msedge.exe", "http://127.0.0.1:45678/", fake_root / "local/edge-profile", fake_root)
    assert runtime.events == ["started", "stopped"]
    runtime.server.terminate.assert_called_once()
    runtime.server.wait.assert_called_once_with(timeout=5)
    runtime.browser_process.terminate.assert_not_called()
    runtime.browser_process.poll.assert_not_called()
    runtime.browser_process.wait.assert_not_called()
    runtime.state.close.assert_called_once()


def test_runtime_data_is_explicit_server_argument_only(runtime, fake_root):
    data = fake_root / "explicit.json"
    launcher.run_launcher(fake_root, data=data)
    assert runtime.start.call_args.args[2] == data
    assert not data.exists()


def test_duplicate_instance_no_process_or_regeneration(runtime, fake_root):
    runtime.state.acquire.return_value = False
    assert launcher.run_launcher(fake_root) == 0
    runtime.start.assert_not_called()
    runtime.ready.assert_not_called()
    runtime.browser.assert_not_called()
    assert runtime.events == ["already_running"]
    runtime.server.terminate.assert_not_called()
    runtime.state.close.assert_called_once()


@pytest.mark.parametrize("running", [True, False])
def test_stop_does_not_load_browser_start_server_or_kill_unrelated(runtime, fake_root, running):
    runtime.state.signal_stop.return_value = running
    assert launcher.run_launcher(fake_root, stop=True) == 0
    runtime.state.acquire.assert_not_called()
    runtime.start.assert_not_called()
    runtime.browser.assert_not_called()
    runtime.server.terminate.assert_not_called()
    assert runtime.events == ["stop_requested" if running else "not_running"]


def test_browser_broker_exit_keeps_server_until_stop(runtime, fake_root):
    runtime.state.stop_requested.side_effect = [False, False, True]
    launcher.run_launcher(fake_root)
    assert runtime.state.stop_requested.call_count == 3
    runtime.browser_process.poll.assert_not_called()
    runtime.browser_process.terminate.assert_not_called()
    runtime.server.terminate.assert_called_once()


@pytest.mark.parametrize("failure", ["ready", "browser"])
def test_startup_failure_cleans_only_owned_server(runtime, fake_root, failure):
    target = getattr(runtime, failure)
    target.side_effect = launcher.LauncherError("startup_timeout" if failure == "ready" else "browser_spawn_failed")
    with pytest.raises(launcher.LauncherError): launcher.run_launcher(fake_root)
    runtime.server.terminate.assert_called_once()
    runtime.state.close.assert_called_once()
    runtime.browser_process.terminate.assert_not_called()
    if failure == "ready": runtime.browser.assert_not_called()


def test_supervisor_server_crash_closes_controls(runtime, fake_root):
    runtime.state.stop_requested.return_value = False
    runtime.server.poll.return_value = 2
    with pytest.raises(launcher.LauncherError) as error: launcher.run_launcher(fake_root)
    assert error.value.code == "server_exited"
    runtime.server.terminate.assert_not_called()
    runtime.state.close.assert_called_once()


def test_pre_server_failure_does_not_kill_anyone(runtime, fake_root, monkeypatch):
    monkeypatch.setattr(launcher, "find_browser", Mock(side_effect=launcher.LauncherError("browser_missing")))
    with pytest.raises(launcher.LauncherError): launcher.run_launcher(fake_root)
    runtime.start.assert_not_called()
    runtime.server.terminate.assert_not_called()
    runtime.state.close.assert_called_once()


def test_only_live_owned_handle_is_terminated():
    dead = fake_process(exit_code=0)
    launcher.stop_owned_server(dead)
    dead.terminate.assert_not_called()
    live = fake_process()
    launcher.stop_owned_server(live)
    live.terminate.assert_called_once()
    live.wait.assert_called_once_with(timeout=5)


def test_cleanup_timeout_no_escalation_to_browser_or_taskkill():
    process = fake_process()
    process.wait.side_effect = subprocess.TimeoutExpired(["owned python"], 5)
    with pytest.raises(launcher.LauncherError) as error: launcher.stop_owned_server(process)
    assert error.value.code == "cleanup_failed"
    process.terminate.assert_called_once()


def test_log_contains_only_fixed_event_codes(fake_root, isolated_env):
    launcher.record_event(fake_root, "started")
    launcher.record_event(fake_root, "invalid_response")
    content = (launcher.local_directory(fake_root) / "launcher.log").read_text(encoding="utf-8")
    assert len(content.splitlines()) == 2
    assert content.splitlines()[0].endswith(" started")
    assert content.splitlines()[1].endswith(" invalid_response")
    with pytest.raises(ValueError): launcher.record_event(fake_root, "synthetic sensitive cell")


def test_main_error_message_and_log_do_not_echo_exception(fake_root, monkeypatch):
    monkeypatch.setattr(launcher, "repository_root", lambda: fake_root)
    monkeypatch.setattr(launcher, "run_launcher", Mock(side_effect=ValueError("secret synthetic probability/class/Elo/ST2")))
    log = Mock()
    message = Mock()
    monkeypatch.setattr(launcher, "record_event", log)
    monkeypatch.setattr(launcher, "show_message", message)
    assert launcher.main([]) == 1
    log.assert_called_once_with(fake_root, "unexpected_failure")
    assert "secret" not in message.call_args.args[0]
    assert message.call_args.kwargs["error"] is True


def test_error_still_shown_when_log_unwritable(monkeypatch):
    monkeypatch.setattr(launcher, "run_launcher", Mock(side_effect=launcher.LauncherError("venv_missing")))
    monkeypatch.setattr(launcher, "record_event", Mock(side_effect=OSError("denied")))
    message = Mock()
    monkeypatch.setattr(launcher, "show_message", message)
    assert launcher.main([]) == 1
    assert "Missing .venv" in message.call_args.args[0]


def test_help_no_process_log_profile_or_shortcut(monkeypatch, capsys):
    for name in ("run_launcher", "record_event", "kernel_api", "local_directory", "show_message"):
        monkeypatch.setattr(launcher, name, Mock(side_effect=AssertionError("Help has no side effects")))
    with pytest.raises(SystemExit) as exit_result: launcher.main(["--help"])
    assert exit_result.value.code == 0
    assert "--stop" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-1", "121", "nan", "inf", "oops"])
def test_timeout_cli_rejects_invalid_values(value):
    with pytest.raises(SystemExit) as result: launcher.main(["--startup-timeout", value])
    assert result.value.code == 2


def test_data_and_stop_mutually_exclusive():
    with pytest.raises(SystemExit) as result: launcher.main(["--stop", "--data", "synthetic.json"])
    assert result.value.code == 2


def test_import_and_launcher_dependency_boundary():
    # Source-code inspection only, never repository production files/artifacts.
    source = Path(launcher.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): imported.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom): imported.add((node.module or "").split(".")[0])
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "shell": assert isinstance(keyword.value, ast.Constant) and keyword.value.value is False
    assert imported <= {"__future__", "argparse", "ctypes", "datetime", "hashlib", "json", "math", "os", "pathlib", "queue", "re", "subprocess", "sys", "threading", "time", "urllib"}
    assert "build_dashboard_feed" not in source
    assert "src." not in source
    assert "prediction_fixture_bindings" not in source
    assert "season_transition_st2_prospective.csv" not in source
    assert "CreateShortcut" not in source
    # Import-time nodes are imports, constants, function/class declarations only.
    for node in tree.body:
        if isinstance(node, ast.Expr): assert isinstance(node.value, ast.Constant)
        elif isinstance(node, ast.If): assert ast.unparse(node.test) == "__name__ == '__main__'"
        else: assert isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.ClassDef, ast.FunctionDef))


def test_installer_contract_source_only():
    source = (Path(launcher.__file__).parent / "install_dashboard_shortcut.ps1").read_text(encoding="utf-8")
    assert "SpecialFolder]::DesktopDirectory" in source
    assert "pythonw.exe" in source
    assert "J1 AI Predict.lnk" in source
    assert "$shortcut.WorkingDirectory = $repositoryRoot" in source
    assert "$Shortcut.Description -ceq $Marker" in source
    assert "$Shortcut.TargetPath -ieq $Pythonw" in source
    assert "STOP: An unrelated" in source
    assert "shell32.dll" in source
    assert "Start-Process" not in source
    assert "RunAs" not in source
    assert "build_dashboard_feed" not in source


@pytest.mark.skipif(launcher.sys.platform != "win32", reason="installer is Windows-only")
def test_powershell_installer_ownership_function_without_desktop_writes():
    # Parse and execute ONLY the pure ownership function, not the installer.
    installer = Path(launcher.__file__).parent / "install_dashboard_shortcut.ps1"
    command = r'''
    param([string]$Installer)
    $tokens = $null; $errors = $null
    $tree = [System.Management.Automation.Language.Parser]::ParseFile($Installer, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw 'Installer syntax failed' }
    $function = $tree.Find({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-DashboardShortcutOwnership'}, $true)
    if ($null -eq $function) { throw 'Missing pure ownership predicate' }
    . ([scriptblock]::Create($function.Extent.Text))
    $root = 'C:\synthetic repo'; $pythonw = $root + '\pythonw.exe'; $launcher = $root + '\launch_dashboard.py'
    $marker = 'J1AI Windows dashboard launcher v1 | ' + $root
    $prefix = '"' + $launcher + '"'
    $shortcut = [pscustomobject]@{Description=$marker; TargetPath=$pythonw; WorkingDirectory=$root; Arguments=$prefix}
    if (-not (Test-DashboardShortcutOwnership $shortcut $marker $pythonw $root $launcher)) { throw 'Own shortcut refused' }
    $shortcut.Arguments = $prefix + ' --data "C:\synthetic prepared.json"'
    if (-not (Test-DashboardShortcutOwnership $shortcut $marker $pythonw $root $launcher)) { throw 'Own explicit data refused' }
    foreach ($field in @('Description','TargetPath','WorkingDirectory','Arguments')) {
        $old = $shortcut.$field
        $shortcut.$field = 'unrelated'
        if (Test-DashboardShortcutOwnership $shortcut $marker $pythonw $root $launcher) { throw 'Unrelated shortcut accepted' }
        $shortcut.$field = $old
    }
    foreach ($arguments in @($prefix + ' --data "C:\file.json" --unexpected', $prefix + ' --data "unterminated')) {
        $shortcut.Arguments = $arguments
        if (Test-DashboardShortcutOwnership $shortcut $marker $pythonw $root $launcher) { throw 'Unexpected arguments accepted' }
    }
    'Installer ownership: PASS (no COM / Desktop writes)'
    '''
    # -Command scriptblock parameters require expression invocation, not a file.
    escaped_path = str(installer).replace("'", "''")
    script = "& {" + command + "} '" + escaped_path + "'"
    powershell = Path(launcher.os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True, shell=False,
                            creationflags=launcher.CREATE_NO_WINDOW, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "Installer ownership: PASS" in result.stdout
