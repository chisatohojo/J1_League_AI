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
from threading import Lock
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
    "/retrospective-data.js": ("retrospective-data.js", "text/javascript"),
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
    if type(data["schemaVersion"]) is not int or data["schemaVersion"] not in (1, 2):
        raise DashboardDataError("schemaVersion: expected 1 or 2")
    rounds = data["schemaVersion"] == 2
    if data["mode"] != "operational":
        raise DashboardDataError("mode: only operational data is permitted")
    model = _object(data["model"], {"name", "version"}, "model")
    if model != CHAMPION_MODEL:
        raise DashboardDataError("model: only the frozen current Champion A is permitted")
    if data["updatedAt"] is not None:
        _timestamp(data["updatedAt"], "updatedAt")

    identities: set[str] = set()
    for section in ("previousRound", "nextRound"):
        round_data = _object(data[section], {"label", "matches", "number", "kind"} if rounds else {"label", "matches"}, section)
        _text(round_data["label"], f"{section}.label")
        if not isinstance(round_data["matches"], list):
            raise DashboardDataError(f"{section}.matches: list required")
        if len(round_data["matches"]) > MAX_MATCHES_PER_ROUND:
            raise DashboardDataError(f"{section}.matches: at most {MAX_MATCHES_PER_ROUND} matches permitted")
        if rounds:
            number = round_data["number"]
            if not (number is None and not round_data["matches"] or
                    type(number) is int and 1 <= number <= 38 and len(round_data["matches"]) == 10):
                raise DashboardDataError(f"{section}: full official round required")
            if round_data["kind"] not in ({"previous"} if section == "previousRound" else {"current", "next"}):
                raise DashboardDataError(f"{section}: invalid round kind")
        teams, order = set(), []
        for index, value in enumerate(round_data["matches"]):
            path = f"{section}.matches[{index}]"
            keys = {"id", "homeTeam", "awayTeam", "kickoffAt", "prediction"}
            if rounds:
                keys.update({"round", "status", "result"})
            elif section == "previousRound":
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
            if rounds:
                if type(match["round"]) is not int or match["round"] != round_data["number"]:
                    raise DashboardDataError(f"{path}: round mismatch")
                if match["status"] not in {"scheduled", "candidate", "completed"}:
                    raise DashboardDataError(f"{path}: invalid official status")
                if home in teams or away in teams:
                    raise DashboardDataError(f"{path}: duplicate team in round")
                teams.update((home, away))
                order.append((kickoff, identity))
            if not rounds or match["prediction"] is not None:
                _validate_prediction(match["prediction"], kickoff, path)
            finished = match["status"] == "completed" if rounds else section == "previousRound"
            if finished:
                result = _object(match["result"], {"homeScore", "awayScore"}, f"{path}.result")
                for name, score in result.items():
                    if type(score) is not int or not 0 <= score <= MAX_SAFE_INTEGER:
                        raise DashboardDataError(f"{path}.result.{name}: nonnegative safe integer required")
            elif rounds and match["result"] is not None:
                raise DashboardDataError(f"{path}: unconfirmed score forbidden")
        if rounds and order != sorted(order):
            raise DashboardDataError(f"{section}: chronological fixture order required")
    if rounds and data["previousRound"]["number"] is not None and data["nextRound"]["number"] is not None:
        if data["previousRound"]["number"] + 1 != data["nextRound"]["number"]:
            raise DashboardDataError("Adjacent official rounds required")
    return data


def _validate_prediction(value, kickoff, path):
    prediction = _object(
        value,
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
    data_path: Path | None = None,
    status_path: Path | None = None,
    reload_data: bool = False,
    poll_seconds: int = 60,
    retrospective_path: Path | None = None,
    retrospective_sha: str | None = None,
    generation_store: Path | None = None,
    store_sha: str | None = None,
) -> ThreadingHTTPServer:
    """Create a loopback-only, GET-only server using an immutable JSON snapshot."""
    generation = None
    if generation_store is not None:
        if data_path or status_path or retrospective_path or payload is not None:
            raise DashboardDataError("Generation store cannot be mixed with independent display inputs")
        from scripts.retrospective_generations import read_current
        generation = read_current(generation_store, store_sha)
        payload = generation["dashboard"]
        reload_data = True
    approved = validate_dashboard_data(empty_dashboard() if payload is None else payload)
    api_bytes = json.dumps(approved, ensure_ascii=False, allow_nan=False).encode("utf-8")
    root = (WEB_ROOT if static_root is None else static_root).resolve()
    if reload_data and data_path is None and generation_store is None:
        raise DashboardDataError("Reload requires an explicit JSON input")
    if type(poll_seconds) is not int or not 10 <= poll_seconds <= 3600:
        raise DashboardDataError("Poll interval must be 10..3600 seconds")
    snapshot_lock = Lock()
    reload_error = None
    last_observed = approved["updatedAt"]

    def read_overlay():
        # Optional separate lane: ordinary v1/v2 servers never import or read it.
        from scripts.dashboard_retrospective import read_json, sha, validate_overlay, safe_path
        if not retrospective_sha or sha(safe_path(retrospective_path).read_bytes()) != retrospective_sha:
            raise DashboardDataError("Retrospective display SHA mismatch")
        return validate_overlay(read_json(retrospective_path), json.loads(api_bytes))

    if retrospective_path is not None:
        read_overlay()  # Refuse a broken explicit preview before opening a listener.

    def refresh():
        nonlocal api_bytes, reload_error, last_observed, generation
        if generation_store is not None:
            from scripts.retrospective_generations import read_current
            try:
                before=read_update_state()
                if before["state"] != "ready": return
                incoming=read_current(generation_store,store_sha)
                pointer=incoming["pointer"]; previous=generation["pointer"]
                if pointer["sequence"] < previous["sequence"] or (pointer["sequence"] == previous["sequence"]
                        and pointer["generation"] != previous["generation"]):
                    raise DashboardDataError("Display generation rollback")
                if _timestamp(incoming["dashboard"]["updatedAt"],"updatedAt") < _timestamp(last_observed,"updatedAt"):
                    raise DashboardDataError("Display publication rollback")
                if read_update_state() != before: return
                generation=incoming
                api_bytes=json.dumps(incoming["dashboard"],ensure_ascii=False,allow_nan=False).encode("utf-8")
                last_observed=incoming["dashboard"]["updatedAt"]; reload_error=None
            except (OSError,ValueError,KeyError,TypeError):
                reload_error="display_reload_failed"
            return
        if reload_data:
            try:
                before = read_update_state()
                if status_path is not None and before["state"] != "ready":
                    return  # Never ingest one half of an updating/failed dual-feed publication.
                incoming = load_dashboard_data(data_path)
                if incoming["schemaVersion"] != approved["schemaVersion"]:
                    raise DashboardDataError("Display schema changed")
                if status_path is not None and read_update_state() != before:
                    return
                if last_observed and (incoming["updatedAt"] is None or
                        _timestamp(incoming["updatedAt"], "updatedAt") <
                        _timestamp(last_observed, "updatedAt")):
                    raise DashboardDataError("Display publication rollback")
                api_bytes = json.dumps(incoming, ensure_ascii=False, allow_nan=False).encode("utf-8")
                last_observed = incoming["updatedAt"]
                reload_error = None
            except (OSError, ValueError, TypeError, KeyError):
                reload_error = "display_reload_failed"

    def read_update_state():
        if generation_store is not None:
            from scripts.retrospective_generations import read_status
            return read_status(generation_store)
        state = dict(state="idle", startedAt=None, finishedAt=None, lastSuccessAt=None, errorCode=None)
        if reload_data and status_path is not None:
            candidate = json.loads(status_path.read_bytes(), object_pairs_hook=_unique_object)
            if set(candidate) != set(state) or candidate["state"] not in {"idle", "updating", "ready", "error"}:
                raise DashboardDataError("Update status schema")
            if candidate["errorCode"] not in {None, "update_failed"}:
                raise DashboardDataError("Update status code")
            for key in ("startedAt", "finishedAt", "lastSuccessAt"):
                if candidate[key] is not None:
                    _timestamp(candidate[key], key)
            state = candidate
        return state

    def update_status():
        try:
            state = read_update_state()
        except (OSError, ValueError, TypeError, KeyError):
            state = dict(state="error", startedAt=None, finishedAt=None, lastSuccessAt=None,
                         errorCode="update_status_invalid")
            return dict(state, pollEnabled=reload_data, pollSeconds=poll_seconds, feedUpdatedAt=last_observed)
        if reload_error:
            state.update(state="error", errorCode=reload_error)
        return dict(state, pollEnabled=reload_data, pollSeconds=poll_seconds, feedUpdatedAt=last_observed)

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
            if route == "/api/presentation":
                if generation_store is None:
                    self.send_error(404,"Coherent presentation not connected")
                    return
                with snapshot_lock:
                    refresh()
                    content=json.dumps(dict(schemaVersion=1,generationId=generation["pointer"]["generation"],
                        sequence=generation["pointer"]["sequence"],dashboard=generation["dashboard"],
                        overlay=generation["overlay"],status=update_status()),ensure_ascii=False,allow_nan=False).encode("utf-8")
                self._send(content,"application/json")
                return
            if route == "/api/retrospective":
                if generation_store is not None:
                    with snapshot_lock:
                        refresh()
                        content=json.dumps(generation["overlay"],ensure_ascii=False,allow_nan=False).encode("utf-8")
                    self._send(content,"application/json")
                    return
                if retrospective_path is None:
                    self.send_error(404, "Retrospective overlay not connected")
                    return
                try:
                    with snapshot_lock:
                        refresh()
                        content = json.dumps(read_overlay(), ensure_ascii=False, allow_nan=False).encode("utf-8")
                except (OSError, ValueError, KeyError, TypeError):
                    self.send_error(503, "Retrospective overlay unavailable")
                    return
                self._send(content, "application/json")
                return
            if route == "/api/dashboard":
                with snapshot_lock:
                    refresh()
                    content = api_bytes
                self._send(content, "application/json")
                return
            if route == "/api/update-status":
                with snapshot_lock:
                    refresh()
                    content = json.dumps(update_status(), ensure_ascii=False).encode("utf-8")
                self._send(content, "application/json")
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
    parser.add_argument("--reload", action="store_true", help="Validate and reload only the explicitly supplied JSON; retain last good data on failure")
    parser.add_argument("--status", type=Path, help="Explicit update-status JSON, used only with --reload")
    parser.add_argument("--poll-seconds", type=int, default=60, help="Browser refresh interval, 10..3600 (default 60)")
    parser.add_argument("--retrospective", type=Path, help="Explicit independent preview overlay; never replaces saved prediction.source")
    parser.add_argument("--retrospective-sha", help="Required SHA-256 anchor for the immutable preview overlay")
    parser.add_argument("--generation-store",type=Path,help="Separate coherent display generations; read-only server")
    parser.add_argument("--store-sha",help="Immutable store.json SHA-256 anchor")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if (args.reload or args.status) and not args.data:
        parser.error("--reload/--status require --data")
    if args.status and not args.reload:
        parser.error("--status requires --reload")
    if bool(args.retrospective) != bool(args.retrospective_sha) or args.retrospective and not args.data:
        parser.error("--retrospective requires --data and --retrospective-sha")
    if bool(args.generation_store) != bool(args.store_sha) or args.generation_store and (args.data or args.status or args.retrospective):
        parser.error("--generation-store requires --store-sha and cannot mix other data inputs")
    try:
        payload = None if args.generation_store else load_dashboard_data(args.data)
        server = create_server(payload, port=args.port, data_path=args.data,
                               status_path=args.status, reload_data=args.reload,
                               poll_seconds=args.poll_seconds, retrospective_path=args.retrospective,
                               retrospective_sha=args.retrospective_sha,generation_store=args.generation_store,store_sha=args.store_sha)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"Dashboard startup rejected: {exc}", file=sys.stderr)
        return 2
    address, port = server.server_address
    print(f"J1AI dashboard: http://{address}:{port}/", flush=True)
    if args.data is None and args.generation_store is None:
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
