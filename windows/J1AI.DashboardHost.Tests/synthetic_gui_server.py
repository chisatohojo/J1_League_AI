"""Explicit synthetic GUI fixture. No production data, model or server imports."""
import json
import mimetypes
from pathlib import Path
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit

root = Path(sys.argv[1]).resolve()
assert root.name.startswith("J1AI-native-test-")
assert len(sys.argv) == 2 or (len(sys.argv) == 4 and sys.argv[2] == "--data" and Path(sys.argv[3]).is_absolute())
# --data is deliberately never opened. The only API response is synthetic empty.
counts = {}
counts_lock = Lock()
payload = {
    "schemaVersion": 1, "mode": "operational",
    "model": {"name": "Champion A", "version": "operational_champion_20260922_v1"},
    "updatedAt": None,
    "previousRound": {"label": "synthetic previous", "matches": []},
    "nextRound": {"label": "synthetic next", "matches": []},
}
routes = {"/index.html", "/styles.css", "/app.js", "/components/prediction-probability-bar.js",
          "/dashboard-data.js", "/team-colors.js", "/demo-data.js"}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        with counts_lock:
            counts[path] = counts.get(path, 0) + 1
        if path == "/api/dashboard":
            content, mime = json.dumps(payload).encode(), "application/json"
        elif path == "/__counts":
            with counts_lock:
                content, mime = json.dumps(counts).encode(), "application/json"
        else:
            route = "/index.html" if path == "/" else path
            if route not in routes:
                self.send_error(404)
                return
            content = (root / "web" / route.lstrip("/")).read_bytes()
            mime = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[Path(route).suffix]
        self.send_response(200)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Synthetic-Integrity", "retained")
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(f"J1AI dashboard: http://127.0.0.1:{server.server_port}/", flush=True)
server.serve_forever()
