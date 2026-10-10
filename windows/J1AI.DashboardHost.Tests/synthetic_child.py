"""Disposable process fixture: no repository data/model/browser imports."""
import ctypes
from ctypes import wintypes
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.GetHandleInformation.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
kernel.GetHandleInformation.restype = wintypes.BOOL
kernel.GetCurrentProcess.restype = wintypes.HANDLE
kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel.CloseHandle.restype = wintypes.BOOL
kernel.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))
kernel.IsProcessInJob.restype = wintypes.BOOL

mode = sys.argv[1]
if mode == "--port":
    # This file can also be copied as a temporary scripts.serve_dashboard module
    # for exercising the real native CLI command, never the production server.
    assert sys.argv[1:3] == ["--port", "0"]
    assert len(sys.argv) == 3 or (len(sys.argv) == 5 and sys.argv[3] == "--data" and os.path.isabs(sys.argv[4]))
    mode = "ready"
if mode == "probe":
    handles = [int(value) for value in sys.argv[2:]]
    flags = wintypes.DWORD()
    valid = [bool(kernel.GetHandleInformation(value, ctypes.byref(flags))) for value in handles]
    inside = wintypes.BOOL()
    assert kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, ctypes.byref(inside))
    print(json.dumps({"valid": valid, "in_job": bool(inside.value), "pid": os.getpid()}), flush=True)
elif mode == "argv":
    print(json.dumps(sys.argv[2:], ensure_ascii=True), flush=True)
elif mode == "cwd":
    print(json.dumps(os.getcwd(), ensure_ascii=True), flush=True)
elif mode == "exit":
    raise SystemExit(7)
elif mode == "close-gate":
    # Test-only early child gate release: the host's cleanup lease must still
    # exclude duplicates until retained-process exit has been confirmed.
    assert kernel.CloseHandle(int(sys.argv[2]))
    print("READY", flush=True)
elif mode == "cleanup-probe":
    if len(sys.argv) == 3:
        assert kernel.CloseHandle(int(sys.argv[2]))
    print(json.dumps({"pid": os.getpid()}), flush=True)
elif mode == "ready":
    payload = {
        "schemaVersion": 1, "mode": "operational",
        "model": {"name": "Champion A", "version": "operational_champion_20260922_v1"},
        "updatedAt": None, "previousRound": {"label": "previous", "matches": []},
        "nextRound": {"label": "next", "matches": []},
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/api/dashboard"
            content = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    print(f"J1AI dashboard: http://127.0.0.1:{server.server_port}/", flush=True)
    server.serve_forever()
elif mode != "silent":
    raise SystemExit(2)

while True:
    time.sleep(0.1)
