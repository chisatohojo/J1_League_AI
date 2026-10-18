"""Stdlib-only display validation and hash IO; never load a model or collect data."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import stat
from datetime import timezone, timedelta
from scripts.serve_dashboard import (CHAMPION_MODEL, _object, _timestamp, _unique_object, validate_dashboard_data)

TYPE = "retrospective_reconstruction"
OUTCOMES = ("away", "draw", "home")
NOTE = "当時の試合前保存予測ではありません"
CHAMPION_HASH = "2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1"
MATCH_PAGE_NAMESPACE = "jleague_match_page"
DATA_SITE_NAMESPACE = "jleague_data_site"
JST = timezone(timedelta(hours=9))
HEX64 = re.compile(r"[0-9a-f]{64}\Z")

def require(condition, code):
    if not condition:
        raise ValueError(code)

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)+"\n").encode()


def sha(body):
    return hashlib.sha256(body).hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            require(not (item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                         if hasattr(item.lstat(), "st_file_attributes") else not item.is_symlink(),
                         "overlay_reparse_denied")
    return path.resolve()


def read_json(path):
    return json.loads(safe_path(path).read_bytes(), object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("overlay_nonfinite_json")))


def checked(root, relative, expected):
    require(isinstance(relative, str) and not Path(relative).is_absolute()
                 and ".." not in Path(relative).parts, "overlay_ledger_path")
    path = safe_path(root / relative)
    require(path.is_relative_to(root), "overlay_ledger_scope")
    body = path.read_bytes()
    require(isinstance(expected, str) and HEX64.fullmatch(expected)
                 and sha(body) == expected, "overlay_input_sha")
    return body


def validate_overlay(data, dashboard):
    """Separate display contract; never put reconstructed probabilities in v2 prediction.source."""
    validate_dashboard_data(dashboard)
    _object(data, {"schemaVersion", "type", "model", "runId", "reconstructionRevision", "officialRevision",
        "officialObservedAt", "note", "dashboardSha256", "entries", "historyRounds", "diagnostics", "officialIdentities"}, "overlay")
    require(type(data["schemaVersion"]) is int and data["schemaVersion"] == 1
                 and data["type"] == "retrospective_overlay" and data["model"] == CHAMPION_MODEL
                 and data["note"] == NOTE and dashboard["schemaVersion"] == 2, "overlay_contract")
    for name in ("runId", "reconstructionRevision", "officialRevision", "dashboardSha256"):
        require(isinstance(data[name], str) and HEX64.fullmatch(data[name]), "overlay_hash")
    require(data["dashboardSha256"] == sha(encoded(dashboard))
                 and data["officialObservedAt"] == dashboard["updatedAt"], "overlay_base_changed")
    _timestamp(data["officialObservedAt"], "overlay.observedAt")
    require(type(data["historyRounds"]) is list and 0 < len(data["historyRounds"]) <= 38
                 and type(data["entries"]) is list and len(data["entries"]) <= 380
                 and type(data["diagnostics"]) is list and len(data["diagnostics"]) <= 380, "overlay_bounds")
    fixtures, rounds = {}, []
    for section in data["historyRounds"]:
        wrapper = dict(dashboard, previousRound=section,
                       nextRound=dict(label="次節", number=None, kind="next", matches=[]))
        validate_dashboard_data(wrapper)
        rounds.append(section["number"])
        for match in section["matches"]:
            require(match["id"] not in fixtures, "overlay_history_duplicate")
            fixtures[match["id"]] = match
    require(rounds == sorted(set(rounds)), "overlay_round_order")
    require(isinstance(data["officialIdentities"], dict) and set(data["officialIdentities"]) == set(fixtures),
                 "overlay_official_identity_coverage")
    official_ids = set()
    for key,identity in data["officialIdentities"].items():
        _object(identity, {"id", "namespace"}, "overlay.officialIdentity")
        if identity == dict(id=None, namespace=None):
            require(fixtures[key]["status"] != "completed", "overlay_missing_completed_id")
        else:
            pair = (identity["namespace"], identity["id"])
            require(isinstance(identity["id"], str) and identity["id"].isdigit()
                         and identity["namespace"] in {MATCH_PAGE_NAMESPACE, DATA_SITE_NAMESPACE}
                         and pair not in official_ids, "overlay_official_id_collision")
            official_ids.add(pair)
    for section in ("previousRound", "nextRound"):
        for match in dashboard[section]["matches"]:
            if match["round"] in rounds:
                require(fixtures.get(match["id"]) == match, "overlay_current_fixture_changed")
    seen = set()
    model_hashes = set()
    for entry in data["entries"]:
        _object(entry, {"fixtureKey", "round", "matchDate", "homeTeamId", "awayTeamId", "officialId",
            "officialNamespace", "result", "reconstruction"}, "overlay.entry")
        key = entry["fixtureKey"]
        require(key not in seen and key in fixtures, "overlay_entry_duplicate_or_missing")
        seen.add(key)
        match = fixtures[key]
        require(data["officialIdentities"][key] == dict(id=entry["officialId"],namespace=entry["officialNamespace"]),
                     "overlay_official_id_mismatch")
        _object(entry["result"], {"homeScore", "awayScore"}, "overlay.result")
        require(all(type(v) is int and v >= 0 for v in entry["result"].values()), "overlay_score")
        require(match["status"] == "completed" and match["prediction"] is None
                     and type(entry["round"]) is int and entry["round"] == match["round"] and entry["homeTeamId"] == match["homeTeam"]["id"]
                     and entry["awayTeamId"] == match["awayTeam"]["id"] and entry["result"] == match["result"]
                     and entry["matchDate"] == _timestamp(match["kickoffAt"], "kickoffAt").astimezone(JST).date().isoformat()
                     and isinstance(entry["officialId"], str) and entry["officialId"].isdigit()
                     and entry["officialNamespace"] in {MATCH_PAGE_NAMESPACE, DATA_SITE_NAMESPACE},
                     "overlay_fixture_contract")
        value = _object(entry["reconstruction"], {"type", "calculatedAt", "probabilities", "predictedOutcome",
            "hit", "modelHash", "artifactHash"}, "overlay.reconstruction")
        require(value["type"] == TYPE and value["artifactHash"] == CHAMPION_HASH
                     and isinstance(value["modelHash"], str) and HEX64.fullmatch(value["modelHash"]), "overlay_model")
        model_hashes.add(value["modelHash"])
        require(_timestamp(value["calculatedAt"], "calculatedAt") >=
                     _timestamp(match["kickoffAt"], "kickoffAt"), "overlay_not_retrospective")
        _object(value["probabilities"], {"home", "draw", "away"}, "overlay.probabilities")
        p = value["probabilities"]
        require(all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 100 for v in p.values())
                     and abs(sum(p.values())-100) < 1e-9, "overlay_probability")
        pick = max(OUTCOMES, key=lambda side:p[side])
        actual = "draw" if match["result"]["homeScore"] == match["result"]["awayScore"] else (
            "home" if match["result"]["homeScore"] > match["result"]["awayScore"] else "away")
        require(value["predictedOutcome"] == pick and type(value["hit"]) is bool
                     and value["hit"] == (pick == actual), "overlay_hit")
    require(len(model_hashes) <= 1, "overlay_mixed_model")
    diagnostic_keys = set()
    allowed = {"fixture_missing", "official_not_completed", "round_mismatch", "kickoff_mismatch", "official_result_corrected"}
    allowed.update(k+"_mismatch" for k in ("match_date","home_team_id","away_team_id","match_id","match_id_namespace"))
    for diagnostic in data["diagnostics"]:
        _object(diagnostic, {"fixtureKey", "code"}, "overlay.diagnostic")
        key = diagnostic["fixtureKey"]
        require(isinstance(key,str) and 0 < len(key) <= 200 and key not in diagnostic_keys
                     and key not in seen and diagnostic["code"] in allowed, "overlay_diagnostic")
        diagnostic_keys.add(key)
    return data
