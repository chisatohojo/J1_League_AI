"""Read-only retrospective overlay. Never import an estimator or run a prediction."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import stat

from scripts import build_dashboard_feed as feed
from scripts.serve_dashboard import (CHAMPION_MODEL, _object, _timestamp, _unique_object,
                                     validate_dashboard_data)
from src.collect.teams import load_team_master

TYPE = "retrospective_reconstruction"
OUTCOMES = ("away", "draw", "home")
NOTE = "当時の試合前保存予測ではありません"


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)+"\n").encode()


def sha(body):
    return hashlib.sha256(body).hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            feed.require(not (item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                         if hasattr(item.lstat(), "st_file_attributes") else not item.is_symlink(),
                         "overlay_reparse_denied")
    return path.resolve()


def read_json(path):
    return json.loads(safe_path(path).read_bytes(), object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("overlay_nonfinite_json")))


def checked(root, relative, expected):
    feed.require(isinstance(relative, str) and not Path(relative).is_absolute()
                 and ".." not in Path(relative).parts, "overlay_ledger_path")
    path = safe_path(root / relative)
    feed.require(path.is_relative_to(root), "overlay_ledger_scope")
    body = path.read_bytes()
    feed.require(isinstance(expected, str) and feed.HEX64.fullmatch(expected)
                 and sha(body) == expected, "overlay_input_sha")
    return body


def read_reconstruction(root, expected_ledger_sha, master):
    """Anchor the existing ledger externally, then traverse seals down to daily predictions."""
    root = safe_path(root)
    body = (root / "SHA256-MANIFEST.json").read_bytes()
    feed.require(sha(body) == expected_ledger_sha, "overlay_ledger_sha")
    ledger = read_json(root / "SHA256-MANIFEST.json")
    paths = [entry["path"] for entry in ledger["files"]]
    feed.require(len(paths) == len(set(paths)), "overlay_ledger_duplicate")
    hashes = {entry["path"]: entry["sha256"] for entry in ledger["files"]}
    for name, digest in hashes.items():
        checked(root, name, digest)
    required = {"run.json", "prediction-seals/complete.json", "complete/manifest.json",
                "complete/results.json", "complete/summary.json"}
    feed.require(required <= hashes.keys(), "overlay_ledger_coverage")
    run = read_json(root / "run.json")
    contract = {k: v for k, v in run.items() if k not in {"run_id", "created_at_utc"}}
    feed.require(sha(encoded(contract)) == run["run_id"] == ledger["run_id"]
                 and run["prediction_type"] == TYPE, "overlay_run_identity")
    official = feed.read_official_revision(root / "inputs" / run["revision"], master,
                                          expected_sha=run["manifest_sha256"])
    expected_targets = official.completed[["fixture_key", "match_date"]].sort_values(
        ["match_date", "fixture_key"]).to_dict("records")
    feed.require(run["targets"] == expected_targets and run["target_count"] == len(expected_targets),
                 "overlay_run_targets")
    seal = read_json(root / "prediction-seals/complete.json")
    summary = read_json(root / "complete/summary.json")
    for name, digest in read_json(root / "complete/manifest.json").items():
        feed.require(Path(name).name == name, "overlay_manifest_path")
        checked(root / "complete", name, digest)
    feed.require(seal["run_id"] == summary["run_id"] == run["run_id"]
                 and seal["prediction_type"] == summary["prediction_type"] == TYPE
                 and seal["stage"] == summary["stage"] == "complete"
                 and summary["official_revision"] == run["revision"]
                 and summary["prediction_seal_sha256"] == hashes["prediction-seals/complete.json"]
                 and summary["target_count"] == summary["predicted_count"] == seal["predictions"] == len(expected_targets)
                 and summary["pending_count"] == 0, "overlay_complete_contract")
    feed.require(set(seal["days"]) == set(run["dates"]) == {r["match_date"] for r in expected_targets},
                 "overlay_seal_dates")
    predictions = {}
    for day, digest in seal["days"].items():
        feed.calendar_date(day)
        checked(root, f"days/{day}/manifest.json", digest)
        manifest = read_json(root / "days" / day / "manifest.json")
        feed.require(set(manifest) == {"predictions.json", "lineage.json"}, "overlay_day_manifest")
        for name, expected in manifest.items(): checked(root / "days" / day, name, expected)
        lineage = read_json(root / "days" / day / "lineage.json")
        feed.require(lineage["target_date"] == day and lineage["same_day_results_used"] == 0
                     and lineage["future_results_used"] == 0
                     and (lineage["history_max_date"] is None or lineage["history_max_date"] < day),
                     "overlay_history_cutoff")
        for row in read_json(root / "days" / day / "predictions.json"):
            feed.require(row["fixture_key"] not in predictions and row["match_date"] == day
                         and row["run_id"] == run["run_id"] and row["official_revision"] == run["revision"]
                         and row["prediction_type"] == TYPE
                         and not {"result", "home_score", "away_score", "correct"} & set(row),
                         "overlay_day_prediction")
            predictions[row["fixture_key"]] = row
    rows = read_json(root / "complete/results.json")
    feed.require(len(rows) == len(predictions) == len(expected_targets)
                 and len({r["fixture_key"] for r in rows}) == len(rows)
                 and set(predictions) == {r["fixture_key"] for r in expected_targets}, "overlay_result_set")
    schedule = official.schedule.set_index("fixture_key")
    for row in rows:
        p = predictions[row["fixture_key"]]
        original = schedule.loc[row["fixture_key"]]
        feed.require(all(row.get(k) == v for k, v in p.items()), "overlay_seal_prediction_changed")
        feed.require(row["artifact_hash"] == feed.CHAMPION_HASH and row["model_version"] == feed.CHAMPION_VERSION
                     and row["model_hash"] == run["source_sha256"][f"models/model_a/{feed.CHAMPION_VERSION}/model.joblib"]
                     and run["source_sha256"][f"models/model_a/{feed.CHAMPION_VERSION}/checksums.sha256"] == feed.CHAMPION_HASH,
                     "overlay_artifact")
        reason = identity_conflict(row, original)
        feed.require(reason is None, "overlay_original_" + str(reason))
        values = [row[f"p_{side}"] for side in OUTCOMES]
        feed.require(all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in values)
                     and abs(sum(values)-1) < 1e-12, "overlay_probabilities")
        pick = values.index(max(values))
        feed.require(type(row["prediction_class"]) is int and row["prediction_class"] == pick
                     and row["predicted_outcome"] == OUTCOMES[pick].upper()
                     and row["actual_class"] == int(original.result)
                     and row["actual_outcome"] == OUTCOMES[int(original.result)].upper()
                     and type(row["correct"]) is bool and row["correct"] == (pick == int(original.result)),
                     "overlay_outcome")
        feed.require(feed.timestamp(row["calculated_at_utc"]) >= feed.timestamp(run["official_observed_at"]),
                     "overlay_calculation_time")
    return run, rows


def identity_conflict(row, official):
    if official.status != "completed": return "official_not_completed"
    for key in ("match_date", "home_team_id", "away_team_id", "match_id", "match_id_namespace"):
        if row[key] != official[key]: return key + "_mismatch"
    if int(row["round"]) != int(official["round"]): return "round_mismatch"
    if row["kickoff_time"] != official.kickoff_time: return "kickoff_mismatch"
    if (row["home_score"], row["away_score"], row["actual_class"]) != (
            int(official.home_score), int(official.away_score), int(official.result)):
        return "official_result_corrected"
    return None


def build_overlay(dashboard, official, names, saved, run, rows):
    """Pure projection: saved predictions win; latest mismatches become explicit diagnostics."""
    validate_dashboard_data(dashboard)
    feed.require(dashboard["schemaVersion"] == 2 and dashboard["updatedAt"] == official.observed_at,
                 "overlay_dashboard_revision")
    keyed = official.schedule.set_index("fixture_key")
    feed.require(len(rows) == len({r["fixture_key"] for r in rows}), "overlay_duplicate_result")
    entries, diagnostics = [], []
    for row in rows:
        key = row["fixture_key"]
        reason = "fixture_missing" if key not in keyed.index else identity_conflict(row, keyed.loc[key])
        if reason:
            diagnostics.append(dict(fixtureKey=key, code=reason))
        elif key not in saved:
            entries.append(dict(fixtureKey=key, round=int(row["round"]), matchDate=row["match_date"],
                homeTeamId=row["home_team_id"], awayTeamId=row["away_team_id"],
                officialId=row["match_id"], officialNamespace=row["match_id_namespace"],
                result=dict(homeScore=row["home_score"], awayScore=row["away_score"]),
                reconstruction=dict(type=TYPE, calculatedAt=row["calculated_at_utc"],
                    probabilities={side: row[f"p_{side}"]*100 for side in ("home", "draw", "away")},
                    predictedOutcome=row["predicted_outcome"].lower(), hit=row["correct"],
                    modelHash=row["model_hash"], artifactHash=row["artifact_hash"])))
    history = []
    for number in sorted({int(r["round"]) for r in rows}):
        subset = official.schedule.loc[official.schedule["round"].astype(int).eq(number)]
        matches = []
        completed = official.completed.set_index("fixture_key")
        for item in subset.sort_values(["match_date", "kickoff_time", "fixture_key"]).itertuples(index=False):
            result = None
            if item.status == "completed":
                score = completed.loc[item.fixture_key]
                result = dict(homeScore=int(score.home_score), awayScore=int(score.away_score))
            matches.append(dict(id=item.fixture_key, round=number, status=item.status,
                homeTeam=dict(id=item.home_team_id, name=names[item.home_team_id]),
                awayTeam=dict(id=item.away_team_id, name=names[item.away_team_id]),
                kickoffAt=feed.kickoff_at(item.match_date, item.kickoff_time),
                prediction=deepcopy(saved.get(item.fixture_key, {}).get("prediction")), result=result))
        history.append(dict(number=number, label=f"第{number}節", kind="previous", matches=matches))
    overlay = dict(schemaVersion=1, type="retrospective_overlay", model=dict(CHAMPION_MODEL),
        runId=run["run_id"], reconstructionRevision=run["revision"], officialRevision=official.revision_id,
        officialObservedAt=official.observed_at, note=NOTE,
        dashboardSha256=sha(encoded(dashboard)), entries=entries, historyRounds=history, diagnostics=diagnostics,
        officialIdentities={match["id"]: dict(id=keyed.loc[match["id"]].match_id or None,
            namespace=keyed.loc[match["id"]].match_id_namespace or None)
            for section in history for match in section["matches"]})
    return validate_overlay(overlay, dashboard)


def validate_overlay(data, dashboard):
    """Separate display contract; never put reconstructed probabilities in v2 prediction.source."""
    validate_dashboard_data(dashboard)
    _object(data, {"schemaVersion", "type", "model", "runId", "reconstructionRevision", "officialRevision",
        "officialObservedAt", "note", "dashboardSha256", "entries", "historyRounds", "diagnostics", "officialIdentities"}, "overlay")
    feed.require(type(data["schemaVersion"]) is int and data["schemaVersion"] == 1
                 and data["type"] == "retrospective_overlay" and data["model"] == CHAMPION_MODEL
                 and data["note"] == NOTE and dashboard["schemaVersion"] == 2, "overlay_contract")
    for name in ("runId", "reconstructionRevision", "officialRevision", "dashboardSha256"):
        feed.require(isinstance(data[name], str) and feed.HEX64.fullmatch(data[name]), "overlay_hash")
    feed.require(data["dashboardSha256"] == sha(encoded(dashboard))
                 and data["officialObservedAt"] == dashboard["updatedAt"], "overlay_base_changed")
    _timestamp(data["officialObservedAt"], "overlay.observedAt")
    feed.require(type(data["historyRounds"]) is list and 0 < len(data["historyRounds"]) <= 38
                 and type(data["entries"]) is list and len(data["entries"]) <= 380
                 and type(data["diagnostics"]) is list and len(data["diagnostics"]) <= 380, "overlay_bounds")
    fixtures, rounds = {}, []
    for section in data["historyRounds"]:
        wrapper = dict(dashboard, previousRound=section,
                       nextRound=dict(label="次節", number=None, kind="next", matches=[]))
        validate_dashboard_data(wrapper)
        rounds.append(section["number"])
        for match in section["matches"]:
            feed.require(match["id"] not in fixtures, "overlay_history_duplicate")
            fixtures[match["id"]] = match
    feed.require(rounds == sorted(set(rounds)), "overlay_round_order")
    feed.require(isinstance(data["officialIdentities"], dict) and set(data["officialIdentities"]) == set(fixtures),
                 "overlay_official_identity_coverage")
    official_ids = set()
    for key,identity in data["officialIdentities"].items():
        _object(identity, {"id", "namespace"}, "overlay.officialIdentity")
        if identity == dict(id=None, namespace=None):
            feed.require(fixtures[key]["status"] != "completed", "overlay_missing_completed_id")
        else:
            pair = (identity["namespace"], identity["id"])
            feed.require(isinstance(identity["id"], str) and identity["id"].isdigit()
                         and identity["namespace"] in {feed.MATCH_PAGE_NAMESPACE, feed.DATA_SITE_NAMESPACE}
                         and pair not in official_ids, "overlay_official_id_collision")
            official_ids.add(pair)
    for section in ("previousRound", "nextRound"):
        for match in dashboard[section]["matches"]:
            if match["round"] in rounds:
                feed.require(fixtures.get(match["id"]) == match, "overlay_current_fixture_changed")
    seen = set()
    model_hashes = set()
    for entry in data["entries"]:
        _object(entry, {"fixtureKey", "round", "matchDate", "homeTeamId", "awayTeamId", "officialId",
            "officialNamespace", "result", "reconstruction"}, "overlay.entry")
        key = entry["fixtureKey"]
        feed.require(key not in seen and key in fixtures, "overlay_entry_duplicate_or_missing")
        seen.add(key)
        match = fixtures[key]
        feed.require(data["officialIdentities"][key] == dict(id=entry["officialId"],namespace=entry["officialNamespace"]),
                     "overlay_official_id_mismatch")
        _object(entry["result"], {"homeScore", "awayScore"}, "overlay.result")
        feed.require(all(type(v) is int and v >= 0 for v in entry["result"].values()), "overlay_score")
        feed.require(match["status"] == "completed" and match["prediction"] is None
                     and type(entry["round"]) is int and entry["round"] == match["round"] and entry["homeTeamId"] == match["homeTeam"]["id"]
                     and entry["awayTeamId"] == match["awayTeam"]["id"] and entry["result"] == match["result"]
                     and entry["matchDate"] == feed.timestamp(match["kickoffAt"]).astimezone(feed.ZoneInfo("Asia/Tokyo")).date().isoformat()
                     and isinstance(entry["officialId"], str) and entry["officialId"].isdigit()
                     and entry["officialNamespace"] in {feed.MATCH_PAGE_NAMESPACE, feed.DATA_SITE_NAMESPACE},
                     "overlay_fixture_contract")
        value = _object(entry["reconstruction"], {"type", "calculatedAt", "probabilities", "predictedOutcome",
            "hit", "modelHash", "artifactHash"}, "overlay.reconstruction")
        feed.require(value["type"] == TYPE and value["artifactHash"] == feed.CHAMPION_HASH
                     and isinstance(value["modelHash"], str) and feed.HEX64.fullmatch(value["modelHash"]), "overlay_model")
        model_hashes.add(value["modelHash"])
        feed.require(_timestamp(value["calculatedAt"], "calculatedAt") >=
                     _timestamp(match["kickoffAt"], "kickoffAt"), "overlay_not_retrospective")
        _object(value["probabilities"], {"home", "draw", "away"}, "overlay.probabilities")
        p = value["probabilities"]
        feed.require(all(type(v) in (int,float) and math.isfinite(v) and 0 <= v <= 100 for v in p.values())
                     and abs(sum(p.values())-100) < 1e-9, "overlay_probability")
        pick = max(OUTCOMES, key=lambda side:p[side])
        actual = "draw" if match["result"]["homeScore"] == match["result"]["awayScore"] else (
            "home" if match["result"]["homeScore"] > match["result"]["awayScore"] else "away")
        feed.require(value["predictedOutcome"] == pick and type(value["hit"]) is bool
                     and value["hit"] == (pick == actual), "overlay_hit")
    feed.require(len(model_hashes) <= 1, "overlay_mixed_model")
    diagnostic_keys = set()
    allowed = {"fixture_missing", "official_not_completed", "round_mismatch", "kickoff_mismatch", "official_result_corrected"}
    allowed.update(k+"_mismatch" for k in ("match_date","home_team_id","away_team_id","match_id","match_id_namespace"))
    for diagnostic in data["diagnostics"]:
        _object(diagnostic, {"fixtureKey", "code"}, "overlay.diagnostic")
        key = diagnostic["fixtureKey"]
        feed.require(isinstance(key,str) and 0 < len(key) <= 200 and key not in diagnostic_keys
                     and key not in seen and diagnostic["code"] in allowed, "overlay_diagnostic")
        diagnostic_keys.add(key)
    return data
