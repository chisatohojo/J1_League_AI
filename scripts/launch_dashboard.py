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
}
EVENTS = set(MESSAGES) | {"started", "stopped", "already_running", "stop_requested", "not_running"}


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


def find_python(root: Path) -> Path:
    executable = root / ".venv" / "Scripts" / "python.exe"
    if not executable.is_file():
        raise LauncherError("venv_missing")
    return executable


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

    def __init__(self, root: Path, *, api=None, last_error=None):
        self.api = kernel_api() if api is None else api
        self.last_error = ctypes.get_last_error if last_error is None else last_error
        self.name = "Local\\J1AI.Dashboard." + instance_id(root)
        self.mutex = None
        self.event = None

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
        return True

    def stop_requested(self, timeout_ms: int = 500) -> bool:
        result = self.api.WaitForSingleObject(self.event, timeout_ms)
        if result not in (0, 258):  # WAIT_OBJECT_0 / WAIT_TIMEOUT
            raise LauncherError("ipc_failed")
        return result == 0

    def signal_stop(self) -> bool:
        handle = self.api.OpenEventW(0x0002, False, self.name + ".Stop")
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
        for name in ("event", "mutex"):
            handle = getattr(self, name)
            if handle:
                self.api.CloseHandle(handle)
                setattr(self, name, None)


def validate_url(url: str) -> str:
    match = URL_PATTERN.fullmatch(url)
    if not match or not 1 <= int(match[1]) <= 65535:
        raise LauncherError("invalid_url")
    return url


def server_command(python: Path, data: Path | None) -> list[str]:
    command = [str(python), "-u", "-m", "scripts.serve_dashboard", "--port", "0"]
    if data is not None:
        # Explicit JSON is read/validated ONLY by the existing server.
        command.extend(("--data", str(data.resolve())))
    return command


def browser_command(browser: Path, url: str, profile: Path) -> list[str]:
    validate_url(url)
    return [
        str(browser), f"--app={url}", f"--user-data-dir={profile}",
        "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
        "--disable-component-update", "--disable-sync",
    ]


def start_server(python: Path, root: Path, data: Path | None):
    try:
        return subprocess.Popen(
            server_command(python, data), cwd=str(root), shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW,
        )
    except OSError:
        raise LauncherError("server_spawn_failed") from None


def start_browser(browser: Path, url: str, profile: Path, root: Path):
    try:
        profile.mkdir(parents=True, exist_ok=True)
        return subprocess.Popen(
            browser_command(browser, url, profile), cwd=str(root), shell=False,
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


def validate_ready_payload(payload) -> None:
    # Basic structural readiness only. Full recursive validation belongs to the
    # existing server before it can bind/print a URL; no probability inspection.
    keys = {"schemaVersion", "mode", "model", "updatedAt", "previousRound", "nextRound"}
    if not isinstance(payload, dict) or set(payload) != keys:
        raise LauncherError("invalid_response")
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        raise LauncherError("invalid_response")
    if payload["mode"] != "operational" or payload["model"] != {"name": "Champion A", "version": CHAMPION_VERSION}:
        raise LauncherError("invalid_response")
    if payload["updatedAt"] is not None and not isinstance(payload["updatedAt"], str):
        raise LauncherError("invalid_response")
    for name in ("previousRound", "nextRound"):
        section = payload[name]
        if (
            not isinstance(section, dict) or set(section) != {"label", "matches"}
            or not isinstance(section["label"], str) or not section["label"].strip()
            or not isinstance(section["matches"], list)
        ):
            raise LauncherError("invalid_response")


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LauncherError("invalid_response")
        result[key] = value
    return result


def check_ready(url: str, timeout: float) -> None:
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
    validate_ready_payload(payload)


def _probe_ready(url: str, timeout: float, messages: queue.Queue) -> None:
    try:
        check_ready(url, timeout=timeout)
        messages.put("ready")
    except LauncherError:
        messages.put("invalid_response")
    except (URLError, TimeoutError, OSError):
        messages.put("retry")
    except Exception:
        messages.put("invalid_response")


def wait_for_ready(process, timeout: float = 20.0) -> str:
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
                args=(url, min(1.0, max(0.001, deadline - time.monotonic())), probes),
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


def run_launcher(root: Path, *, data: Path | None = None, timeout: float = 20.0, stop=False) -> int:
    require_windows()
    controls = WindowsInstance(root)
    server = None
    try:
        if stop:
            signalled = controls.signal_stop()
            record_event(root, "stop_requested" if signalled else "not_running")
            show_message("Stop requested for this launcher's server only. Browser windows are untouched."
                         if signalled else "No dashboard launcher is running.")
            return 0
        if not controls.acquire():
            record_event(root, "already_running")
            show_message("J1 AI Predict is already running. No new server or window was opened.\n"
                         "If the app window is closed, run the documented --stop command before restarting.")
            return 0
        python = find_python(root)
        browser = find_browser()
        profile = local_directory(root) / ("edge-profile" if browser.name.lower() == "msedge.exe" else "chrome-profile")
        server = start_server(python, root, data)
        url = wait_for_ready(server, timeout)
        start_browser(browser, url, profile, root)
        record_event(root, "started")
        # No browser poll()/wait(), window manipulation, taskkill, or profile
        # deletion. Chromium's startup PID is not a window-lifetime witness.
        while not controls.stop_requested():
            if server.poll() is not None:
                raise LauncherError("server_exited")
        record_event(root, "stopped")
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
    parser.add_argument("--startup-timeout", type=positive_timeout, default=20.0, help="Bounded server readiness wait in seconds (default: 20)")
    args = parser.parse_args(argv)
    root = repository_root()
    try:
        return run_launcher(root, data=args.data, timeout=args.startup_timeout, stop=args.stop)
    except (Exception, KeyboardInterrupt) as exc:
        code = exc.code if isinstance(exc, LauncherError) else "unexpected_failure"
        # No exception string, traceback, server output or response body is logged.
        try:
            record_event(root, code)
        except Exception:
            pass
        show_message(MESSAGES[code] + "\nSee docs/UI_WINDOWS_LAUNCHER.md for troubleshooting.", error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
