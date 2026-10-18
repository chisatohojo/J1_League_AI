"""Windows app-mode launcher for the existing read-only dashboard.

No feed generation or model/data discovery. Browser lifetime is deliberately
not inferred from its startup PID: use --stop to stop this launcher's server.
Import and --help have no process, profile, log or desktop side effects.
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener


CHAMPION_VERSION = "operational_champion_20260922_v1"
CREATE_NO_WINDOW = 0x08000000
URL_PATTERN = re.compile(r"http://127\.0\.0\.1:([0-9]{1,5})/\Z")
MAX_RESPONSE_BYTES = 1024 * 1024
MESSAGES = {
    "windows_required": "This launcher requires Windows.",
    "venv_missing": "Missing .venv/Scripts/python.exe. Set up the repository venv first.",
    "browser_missing": "Microsoft Edge or Google Chrome was not found. Install it separately.",
    "local_appdata_missing": "LOCALAPPDATA is unavailable. A dedicated profile cannot be created.",
    "ipc_failed": "Cannot create or access the dashboard single-instance controls.",
    "server_spawn_failed": "Cannot start the dashboard server. Check the venv and repository.",
    "server_exited": "The dashboard server exited. Check the venv or explicit prepared JSON.",
    "startup_timeout": "Dashboard readiness timed out. No browser window was opened.",
    "invalid_url": "The server did not provide a valid loopback dashboard URL.",
    "invalid_response": "The dashboard response is not the expected operational Champion schema.",
    "browser_spawn_failed": "Cannot start the browser in app mode. No tab fallback was attempted.",
    "cleanup_failed": "The owned server could not be stopped. See the safe cleanup instructions.",
    "unexpected_failure": "Launcher setup failed. Check local permissions, venv and browser availability.",
    "runtime_missing": "The selected runtime must contain the selected view JSON and view/update-status.json. No empty or demo fallback was used.",
}
EVENTS = set(MESSAGES) | {"started", "stopped", "already_running", "stop_requested", "not_running", "open_requested", "reopened"}


class LauncherError(RuntimeError):
    """Only fixed, data-free diagnostics may escape to the UI/log."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(MESSAGES[code])


def repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def require_windows() -> None:
    if sys.platform != "win32":
        raise LauncherError("windows_required")


def find_python(root: Path, explicit: Path | None = None) -> Path:
    executable = explicit.resolve() if explicit is not None else root / ".venv" / "Scripts" / "python.exe"
    if not executable.is_file() or executable.name.lower() != "python.exe":
        raise LauncherError("venv_missing")
    return executable


def runtime_scope(root: Path, runtime: Path | None, view="legacy") -> Path:
    # A separate kernel/profile namespace; this path is never created.
    if view not in {"legacy", "rounds"} or view != "legacy" and runtime is None:
        raise LauncherError("runtime_missing")
    suffix = "-rounds" if view == "rounds" else ""
    return root if runtime is None else root / (".champion-" + instance_id(runtime) + suffix)


def runtime_files(runtime: Path, view="legacy") -> tuple[Path, Path]:
    if view not in {"legacy", "rounds"}:
        raise LauncherError("runtime_missing")
    path = runtime.absolute()
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise LauncherError("runtime_missing")
    data = path / "view" / ("champion_rounds.json" if view == "rounds" else "champion_home.json")
    status = path / "view/update-status.json"
    if not data.is_file() or not status.is_file() or any(
        p.is_symlink() or p.is_junction() for p in (data.parent, data, status)
    ):
        raise LauncherError("runtime_missing")
    return data.resolve(), status.resolve()


def find_browser(environ=None) -> Path:
    env = os.environ if environ is None else environ
    # Exhaust every standard Edge location before considering any Chrome location.
    for relative in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe"):
        for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            if env.get(variable):
                candidate = Path(env[variable]) / relative
                if candidate.is_file():
                    return candidate
    raise LauncherError("browser_missing")


def instance_id(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).casefold().encode("utf-8")).hexdigest()[:24]


def local_directory(root: Path) -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise LauncherError("local_appdata_missing")
    return Path(value) / "J1AI" / "Dashboard" / instance_id(root)


def record_event(root: Path, code: str) -> None:
    if code not in EVENTS:
        raise ValueError("Only fixed launcher event codes are permitted")
    directory = local_directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "launcher.log").open("a", encoding="utf-8") as stream:
        stream.write(f"{datetime.now(timezone.utc).isoformat()} {code}\n")


def show_message(message: str, *, error: bool = False) -> None:
    if sys.platform == "win32":
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.MessageBoxW.argtypes = (wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT)
        user32.MessageBoxW.restype = ctypes.c_int
        user32.MessageBoxW(None, message, "J1 AI Predict", 0x10 if error else 0x40)
    elif sys.stderr is not None:
        print(message, file=sys.stderr)


def kernel_api():
    require_windows()
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateMutexW": ((ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR), wintypes.HANDLE),
        "CreateEventW": ((ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR), wintypes.HANDLE),
        "OpenEventW": ((wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR), wintypes.HANDLE),
        "SetEvent": ((wintypes.HANDLE,), wintypes.BOOL),
        "WaitForSingleObject": ((wintypes.HANDLE, wintypes.DWORD), wintypes.DWORD),
        "CloseHandle": ((wintypes.HANDLE,), wintypes.BOOL),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = arguments, result
    return api


class WindowsInstance:
    """Kernel object lifetime, not PID files, owns this repository/session instance.

    The mutex handle remains open for the supervisor lifetime. Windows removes
    the objects when the final handle closes, including after a process crash.
    """

    def __init__(self, root: Path, *, api=None, last_error=None, reopen=False):
        self.api = kernel_api() if api is None else api
        self.last_error = ctypes.get_last_error if last_error is None else last_error
        self.name = "Local\\J1AI.Dashboard." + instance_id(root)
        self.mutex = None
        self.event = None
        self.open_event = None
        self.reopen = reopen

    def acquire(self) -> bool:
        self.mutex = self.api.CreateMutexW(None, False, self.name)
        error = self.last_error()
        if not self.mutex:
            raise LauncherError("ipc_failed")
        if error == 183:  # ERROR_ALREADY_EXISTS; do not start another process.
            self.close()
            return False
        self.event = self.api.CreateEventW(None, True, False, self.name + ".Stop")
        if not self.event:
            self.close()
            raise LauncherError("ipc_failed")
        if self.reopen:
            self.open_event = self.api.CreateEventW(None, False, False, self.name + ".Open")
            if not self.open_event:
                self.close()
                raise LauncherError("ipc_failed")
        return True

    def stop_requested(self, timeout_ms: int = 500) -> bool:
        result = self.api.WaitForSingleObject(self.event, timeout_ms)
        if result not in (0, 258):  # WAIT_OBJECT_0 / WAIT_TIMEOUT
            raise LauncherError("ipc_failed")
        return result == 0

    def signal_stop(self) -> bool:
        return self._signal(".Stop")

    def signal_open(self) -> bool:
        return self._signal(".Open")

    def open_requested(self) -> bool:
        result = self.api.WaitForSingleObject(self.open_event, 0)
        if result not in (0, 258):
            raise LauncherError("ipc_failed")
        return result == 0

    def _signal(self, suffix: str) -> bool:
        handle = self.api.OpenEventW(0x0002, False, self.name + suffix)
        if not handle:
            if self.last_error() == 2:  # ERROR_FILE_NOT_FOUND: no stale PID state.
                return False
            raise LauncherError("ipc_failed")
        try:
            if not self.api.SetEvent(handle):
                raise LauncherError("ipc_failed")
            return True
        finally:
            self.api.CloseHandle(handle)

    def close(self) -> None:
        for name in ("event", "open_event", "mutex"):
            handle = getattr(self, name)
            if handle:
                self.api.CloseHandle(handle)
                setattr(self, name, None)


def validate_url(url: str) -> str:
    match = URL_PATTERN.fullmatch(url)
    if not match or not 1 <= int(match[1]) <= 65535:
        raise LauncherError("invalid_url")
    return url


def server_command(python: Path, data: Path | None, status: Path | None = None) -> list[str]:
    command = [str(python), "-u", "-m", "scripts.serve_dashboard", "--port", "0"]
    if data is not None:
        # Explicit JSON is read/validated ONLY by the existing server.
        command.extend(("--data", str(data.resolve())))
    if status is not None:
        if data is None:
            raise LauncherError("runtime_missing")
        command.insert(1, "-B")
        command.extend(("--reload", "--status", str(status.resolve()), "--poll-seconds", "60"))
    return command


def browser_command(browser: Path, url: str, profile: Path, *, software_rendering=False) -> list[str]:
    validate_url(url)
    return [
        str(browser), f"--app={url}", f"--user-data-dir={profile}",
        "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
        "--disable-component-update", "--disable-sync",
        *(["--disable-gpu"] if software_rendering else []),
    ]


def start_server(python: Path, root: Path, data: Path | None, status: Path | None = None):
    try:
        # Windows venv python.exe is a redirector that creates another process.
        # Run this stdlib-only server with its base interpreter so the retained
        # Popen handle owns the actual listener, not an intermediate redirector.
        probe = subprocess.run(
            [str(python), "-I", "-S", "-B", "-X", "utf8", "-c", "import sys;print(sys._base_executable)"],
            capture_output=True, text=True, encoding="utf-8", timeout=5, check=True,
            creationflags=CREATE_NO_WINDOW,
        )
        executable = Path(probe.stdout.strip())
        if not executable.is_absolute() or not executable.is_file() or executable.name.lower() != "python.exe":
            raise LauncherError("server_spawn_failed")
        return subprocess.Popen(
            server_command(executable, data, status), cwd=str(root), shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError):
        raise LauncherError("server_spawn_failed") from None


def start_browser(browser: Path, url: str, profile: Path, root: Path, *, software_rendering=False):
    try:
        profile.mkdir(parents=True, exist_ok=True)
        command = (browser_command(browser, url, profile, software_rendering=True) if software_rendering
                   else browser_command(browser, url, profile))
        return subprocess.Popen(
            command, cwd=str(root), shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError:
        raise LauncherError("browser_spawn_failed") from None


def _read_startup_url(stream, messages: queue.Queue) -> None:
    # Never forward stdout/stderr or data into a log or error message.
    try:
        for _ in range(16):
            line = stream.readline(4096)
            if not line:
                break
            prefix = "J1AI dashboard: "
            if line.startswith(prefix):
                messages.put(line[len(prefix):].strip())
                return
    except (OSError, ValueError):
        pass
    messages.put(None)


def validate_ready_payload(payload, *, require_data=False, expected_version=None) -> None:
    # Basic structural readiness only. Full recursive validation belongs to the
    # existing server before it can bind/print a URL; no probability inspection.
    keys = {"schemaVersion", "mode", "model", "updatedAt", "previousRound", "nextRound"}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise LauncherError("invalid_response")
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] not in (1, 2):
        raise LauncherError("invalid_response")
    if expected_version is not None and payload["schemaVersion"] != expected_version:
        raise LauncherError("invalid_response")
    if payload["mode"] != "operational" or payload["model"] != {"name": "Champion A", "version": CHAMPION_VERSION}:
        raise LauncherError("invalid_response")
    if payload["updatedAt"] is not None and not isinstance(payload["updatedAt"], str):
        raise LauncherError("invalid_response")
    for name in ("previousRound", "nextRound"):
        section = payload[name]
        if (
            not isinstance(section, dict) or set(section) !=
            ({"label", "matches", "number", "kind"} if payload["schemaVersion"] == 2 else {"label", "matches"})
            or not isinstance(section["label"], str) or not section["label"].strip()
            or not isinstance(section["matches"], list)
        ):
            raise LauncherError("invalid_response")
    if require_data and not any(payload[name]["matches"] for name in ("previousRound", "nextRound")):
        raise LauncherError("invalid_response")


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LauncherError("invalid_response")
        result[key] = value
    return result


def check_ready(url: str, timeout: float, *, require_data=False, expected_version=None) -> None:
    validate_url(url)
    # Disable proxies AND redirects: a loopback request must not escape to a
    # configured external proxy or follow a server-supplied Location header.
    from urllib.request import HTTPRedirectHandler

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise LauncherError("invalid_response")

    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(url + "api/dashboard", timeout=timeout) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise LauncherError("invalid_response")
            content = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError:
        raise LauncherError("invalid_response") from None
    if len(content) > MAX_RESPONSE_BYTES:
        raise LauncherError("invalid_response")
    try:
        payload = json.loads(content, object_pairs_hook=_unique_json)
    except (UnicodeError, ValueError, RecursionError):
        raise LauncherError("invalid_response") from None
    validate_ready_payload(payload, require_data=require_data, expected_version=expected_version)


def _probe_ready(url: str, timeout: float, messages: queue.Queue, require_data=False, expected_version=None) -> None:
    try:
        if expected_version is not None:
            check_ready(url, timeout=timeout, require_data=require_data, expected_version=expected_version)
        elif require_data:
            check_ready(url, timeout=timeout, require_data=True)
        else:
            check_ready(url, timeout=timeout)
        messages.put("ready")
    except LauncherError:
        messages.put("invalid_response")
    except (URLError, TimeoutError, OSError):
        messages.put("retry")
    except Exception:
        messages.put("invalid_response")


def wait_for_ready(process, timeout: float = 20.0, *, require_data=False, expected_version=None) -> str:
    deadline = time.monotonic() + timeout
    messages = queue.Queue()
    threading.Thread(target=_read_startup_url, args=(process.stdout, messages), daemon=True).start()
    url = None
    probes = queue.Queue()
    probing = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherError("server_exited")
        if url is None:
            try:
                value = messages.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if value is None:
                raise LauncherError("invalid_url")
            url = validate_url(value)
        if not probing:
            # The supervisor deadline remains bounded even if a response trickles
            # bytes forever or a socket implementation ignores its own timeout.
            threading.Thread(
                target=_probe_ready,
                args=(url, min(1.0, max(0.001, deadline - time.monotonic())), probes, require_data, expected_version),
                daemon=True,
            ).start()
            probing = True
        try:
            result = probes.get(timeout=min(0.1, max(0.001, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if result == "ready":
            if process.poll() is not None:
                raise LauncherError("server_exited")
            return url
        if result == "invalid_response":
            raise LauncherError("invalid_response")
        probing = False
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    raise LauncherError("startup_timeout")


def stop_owned_server(process) -> None:
    """Only the Popen handle created by THIS launcher, never PID/name discovery."""
    if process.poll() is None:
        # On Windows Popen.terminate uses the retained process handle, preventing
        # PID reuse from targeting an unrelated process. Never kill a browser.
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise LauncherError("cleanup_failed") from None
    if process.stdout is not None:
        process.stdout.close()


def run_launcher(root: Path, *, data: Path | None = None, timeout: float = 20.0, stop=False,
                 runtime: Path | None = None, python: Path | None = None, view="legacy") -> int:
    require_windows()
    owner = runtime_scope(root, runtime, view)
    controls = WindowsInstance(root) if runtime is None else WindowsInstance(owner, reopen=True)
    server = None
    try:
        if stop:
            signalled = controls.signal_stop()
            record_event(owner, "stop_requested" if signalled else "not_running")
            show_message("Stop requested for this launcher's server only. Browser windows are untouched."
                         if signalled else "No dashboard launcher is running.")
            return 0
        if not controls.acquire():
            if runtime is not None:
                deadline = time.monotonic() + timeout
                while not controls.signal_open():
                    if time.monotonic() >= deadline:
                        raise LauncherError("ipc_failed")
                    time.sleep(0.05)
                record_event(owner, "open_requested")
                return 0
            record_event(root, "already_running")
            show_message("J1 AI Predict is already running. No new server or window was opened.\n"
                         "If the app window is closed, run the documented --stop command before restarting.")
            return 0
        python = find_python(root) if python is None else find_python(root, python)
        browser = find_browser()
        profile = local_directory(owner) / ("edge-profile" if browser.name.lower() == "msedge.exe" else "chrome-profile")
        if runtime is not None:
            data, status = runtime_files(runtime, view)
            server = start_server(python, root, data, status=status)
            if view == "rounds":
                url = wait_for_ready(server, timeout, require_data=True, expected_version=2)
            else:
                url = wait_for_ready(server, timeout, require_data=True)
        else:
            server = start_server(python, root, data)
            url = wait_for_ready(server, timeout)
        # A fresh v2 app window otherwise rendered white after close/reopen on
        # the supported Windows PC. Keep the legacy browser command unchanged.
        browser_options = {"software_rendering": True} if view == "rounds" else {}
        start_browser(browser, url, profile, root, **browser_options)
        record_event(owner, "started")
        # No browser poll()/wait(), window manipulation, taskkill, or profile
        # deletion. Chromium's startup PID is not a window-lifetime witness.
        while not controls.stop_requested():
            if server.poll() is not None:
                raise LauncherError("server_exited")
            if runtime is not None and controls.open_requested():
                start_browser(browser, url, profile, root, **browser_options)
                record_event(owner, "reopened")
        record_event(owner, "stopped")
        return 0
    finally:
        try:
            if server is not None:
                stop_owned_server(server)
        finally:
            controls.close()


def positive_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout must be a finite number in (0, 120]") from None
    if not math.isfinite(parsed) or not 0 < parsed <= 120:
        raise argparse.ArgumentTypeError("timeout must be a finite number in (0, 120]")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--data", type=Path, help="Explicit prepared Champion-only JSON; never generated or searched for")
    group.add_argument("--stop", action="store_true", help="Signal the owning launcher to stop its server; do not close browsers")
    parser.add_argument("--runtime", type=Path, help="Explicit Champion runtime; enables status and 60-second reload, no acquisition")
    parser.add_argument("--view", choices=("legacy", "rounds"), default="legacy", help="Runtime view: legacy v1 (default) or complete official rounds v2; separate instance/profile")
    parser.add_argument("--python", type=Path, help="Explicit existing python.exe when code and venv are in separate worktrees")
    parser.add_argument("--startup-timeout", type=positive_timeout, default=20.0, help="Bounded server readiness wait in seconds (default: 20)")
    args = parser.parse_args(argv)
    if args.runtime is not None and args.data is not None:
        parser.error("--runtime and --data are mutually exclusive")
    if args.view != "legacy" and args.runtime is None:
        parser.error("--view rounds requires --runtime")
    root = repository_root()
    try:
        return run_launcher(root, data=args.data, timeout=args.startup_timeout, stop=args.stop,
                            runtime=args.runtime, python=args.python, view=args.view)
    except (Exception, KeyboardInterrupt) as exc:
        code = exc.code if isinstance(exc, LauncherError) else "unexpected_failure"
        # No exception string, traceback, server output or response body is logged.
        try:
            record_event(runtime_scope(root, args.runtime, args.view), code)
        except Exception:
            pass
        show_message(MESSAGES[code] + "\nSee docs/UI_WINDOWS_LAUNCHER.md for troubleshooting.", error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
