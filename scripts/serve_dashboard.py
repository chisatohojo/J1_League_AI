"""Serve the dashboard locally without loading models or repository predictions.

Only an explicitly prepared, Champion A-only JSON payload can supply operational
data. With no ``--data`` argument the API is intentionally empty. This module
does not build exports, join outcomes, collect data, or generate predictions.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import unquote, urlsplit


CHAMPION_MODEL = {
    "name": "Champion A",
    "version": "operational_champion_20260922_v1",
}
WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
STATIC_ROUTES = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/styles.css": ("styles.css", "text/css"),
    "/app.js": ("app.js", "text/javascript"),
    "/components/prediction-probability-bar.js": (
        "components/prediction-probability-bar.js",
        "text/javascript",
    ),
    "/dashboard-data.js": ("dashboard-data.js", "text/javascript"),
    "/team-colors.js": ("team-colors.js", "text/javascript"),
    "/demo-data.js": ("demo-data.js", "text/javascript"),
}
TEAM_ID = re.compile(r"team_[0-9]{4}\Z")
MAX_TEXT_LENGTH = 200
MAX_MATCHES_PER_ROUND = 100
MAX_SAFE_INTEGER = 2**53 - 1
TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:Z|[+-]\d{2}:\d{2})\Z"
)


class DashboardDataError(ValueError):
    """The supplied dashboard data violates the operational-only contract."""


def empty_dashboard() -> dict[str, Any]:
    """Return a fresh, explicitly empty operational view, never synthetic scores."""
    return {
        "schemaVersion": 1,
        "mode": "operational",
        "model": dict(CHAMPION_MODEL),
        "updatedAt": None,
        "previousRound": {"label": "前節", "matches": []},
        "nextRound": {"label": "次節", "matches": []},
    }


def _object(value: Any, keys: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise DashboardDataError(f"{path}: exact keys required: {sorted(keys)}")
    return value


def _text(value: Any, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_TEXT_LENGTH
    ):
        raise DashboardDataError(f"{path}: nonempty string of at most {MAX_TEXT_LENGTH} characters required")
    return value


def _timestamp(value: Any, path: str) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise DashboardDataError(f"{path}: timezone-qualified ISO timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DashboardDataError(f"{path}: invalid timestamp") from exc
    if parsed.utcoffset() is None:
        raise DashboardDataError(f"{path}: timezone required")
    return parsed


def _team(value: Any, path: str) -> str:
    team = _object(value, {"id", "name"}, path)
    identity = _text(team["id"], f"{path}.id")
    if not TEAM_ID.fullmatch(identity):
        raise DashboardDataError(f"{path}.id: stable team_XXXX ID required")
    _text(team["name"], f"{path}.name")
    return identity


def validate_dashboard_data(payload: Any) -> dict[str, Any]:
    """Validate a strict saved-pre-match, current-Champion-only display schema.

    Extra fields are rejected recursively, including research model data. The
    probabilities are inspected, not normalized or rewritten.
    """
    data = _object(
        payload,
        {"schemaVersion", "mode", "model", "updatedAt", "previousRound", "nextRound"},
        "dashboard",
    )
    if type(data["schemaVersion"]) is not int or data["schemaVersion"] != 1:
        raise DashboardDataError("schemaVersion: expected 1")
    if data["mode"] != "operational":
        raise DashboardDataError("mode: only operational data is permitted")
    model = _object(data["model"], {"name", "version"}, "model")
    if model != CHAMPION_MODEL:
        raise DashboardDataError("model: only the frozen current Champion A is permitted")
    if data["updatedAt"] is not None:
        _timestamp(data["updatedAt"], "updatedAt")

    identities: set[str] = set()
    for section in ("previousRound", "nextRound"):
        round_data = _object(data[section], {"label", "matches"}, section)
        _text(round_data["label"], f"{section}.label")
        if not isinstance(round_data["matches"], list):
            raise DashboardDataError(f"{section}.matches: list required")
        if len(round_data["matches"]) > MAX_MATCHES_PER_ROUND:
            raise DashboardDataError(f"{section}.matches: at most {MAX_MATCHES_PER_ROUND} matches permitted")
        for index, value in enumerate(round_data["matches"]):
            path = f"{section}.matches[{index}]"
            keys = {"id", "homeTeam", "awayTeam", "kickoffAt", "prediction"}
            if section == "previousRound":
                keys.add("result")
            match = _object(value, keys, path)
            identity = _text(match["id"], f"{path}.id")
            if identity in identities:
                raise DashboardDataError(f"{path}.id: duplicate match ID")
            identities.add(identity)
            home = _team(match["homeTeam"], f"{path}.homeTeam")
            away = _team(match["awayTeam"], f"{path}.awayTeam")
            if home == away:
                raise DashboardDataError(f"{path}: home and away teams must differ")
            kickoff = _timestamp(match["kickoffAt"], f"{path}.kickoffAt")
            prediction = _object(
                match["prediction"],
                {"source", "generatedAt", "probabilities"},
                f"{path}.prediction",
            )
            if prediction["source"] != "saved_pre_match":
                raise DashboardDataError(f"{path}.prediction.source: saved_pre_match required")
            generated = _timestamp(
                prediction["generatedAt"], f"{path}.prediction.generatedAt"
            )
            if generated >= kickoff:
                raise DashboardDataError(f"{path}: saved prediction must precede kickoff")
            probabilities = _object(
                prediction["probabilities"],
                {"home", "draw", "away"},
                f"{path}.prediction.probabilities",
            )
            for outcome, probability in probabilities.items():
                if (
                    type(probability) not in (int, float)
                    or not 0 <= probability <= 100
                    or not math.isfinite(probability)
                ):
                    raise DashboardDataError(
                        f"{path}.prediction.probabilities.{outcome}: finite percentage required"
                    )
            if not math.isclose(sum(probabilities.values()), 100, rel_tol=0, abs_tol=0.02):
                raise DashboardDataError(f"{path}: probabilities must sum to 100 within 0.02")
            if section == "previousRound":
                result = _object(match["result"], {"homeScore", "awayScore"}, f"{path}.result")
                for name, score in result.items():
                    if type(score) is not int or not 0 <= score <= MAX_SAFE_INTEGER:
                        raise DashboardDataError(f"{path}.result.{name}: nonnegative safe integer required")
    return data


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise DashboardDataError(f"duplicate JSON key: {name}")
        result[name] = value
    return result


def load_dashboard_data(path: Path | None = None) -> dict[str, Any]:
    """Read only the explicit JSON file; absent input performs no file reads."""
    if path is None:
        return empty_dashboard()
    if path.suffix.lower() != ".json":
        raise DashboardDataError("--data must identify a prepared .json file, not a CSV/artifact")
    try:
        content = path.read_text(encoding="utf-8")
        payload = json.loads(content, object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DashboardDataError(f"Cannot read dashboard JSON: {exc}") from exc
    return validate_dashboard_data(payload)


def create_server(
    payload: dict[str, Any] | None = None,
    *,
    port: int = 8765,
    static_root: Path | None = None,
) -> ThreadingHTTPServer:
    """Create a loopback-only, GET-only server using an immutable JSON snapshot."""
    approved = validate_dashboard_data(empty_dashboard() if payload is None else payload)
    api_bytes = json.dumps(approved, ensure_ascii=False, allow_nan=False).encode("utf-8")
    root = (WEB_ROOT if static_root is None else static_root).resolve()

    class DashboardHandler(BaseHTTPRequestHandler):
        def _send(self, content: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            route = unquote(urlsplit(self.path).path)
            if route == "/api/dashboard":
                self._send(api_bytes, "application/json")
                return
            asset = STATIC_ROUTES.get(route)
            if asset is None:
                self.send_error(404, "Unknown dashboard route")
                return
            relative, content_type = asset
            target = (root / relative).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                self.send_error(404, "Dashboard asset not found")
                return
            try:
                content = target.read_bytes()
            except OSError:
                self.send_error(404, "Dashboard asset unavailable")
                return
            self._send(content, content_type)

        def _reject_method(self) -> None:
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_HEAD = _reject_method
        do_POST = _reject_method
        do_PUT = _reject_method
        do_PATCH = _reject_method
        do_DELETE = _reject_method
        do_OPTIONS = _reject_method

        def log_message(self, format: str, *args: Any) -> None:
            # No payload, team, probability, or result content is logged.
            super().log_message(format, *args)

    return ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765)")
    parser.add_argument("--data", type=Path, help="Explicit prepared Champion A-only JSON (read-only)")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        payload = load_dashboard_data(args.data)
        server = create_server(payload, port=args.port)
    except (DashboardDataError, OSError) as exc:
        print(f"Dashboard startup rejected: {exc}", file=sys.stderr)
        return 2
    address, port = server.server_address
    print(f"J1AI dashboard: http://{address}:{port}/", flush=True)
    if args.data is None:
        print("Operational view is empty; no prediction/history files were read.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
