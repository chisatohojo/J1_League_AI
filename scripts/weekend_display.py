"""Read-only Saturday/Sunday display projection; no HTTP, models or publishers.

This optional sidecar is NOT a prediction batch or a schema-v1 replacement.
Only read_dashboard_projection's fully validated source/binding context enters it.
"""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
import struct
import io
import csv
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts import build_dashboard_feed as feed
from scripts.serve_dashboard import validate_dashboard_data, CHAMPION_MODEL, empty_dashboard, _team, _text, _timestamp, _unique_object

FORMAT = "champion-weekend-display-v1"
STATES = {"saved", "not_saved", "schedule_unconfirmed", "prediction_conflict"}


def read_saved_daily_projection(repository_root, runtime):
    """Read only the already deployed two-CSV daily manifest. Reject all new batch formats.

    Bytes are snapshotted and rechecked; no temporary CSV, publisher, collector,
    model or Weekend Batch execution path is involved.
    """
    runtime = Path(runtime).resolve()
    directory = runtime / "batches"
    feed.require(directory.is_dir() and not directory.is_symlink() and not directory.is_junction(), "Missing daily batch directory")
    entries = sorted(directory.iterdir())
    before, records, bindings = {}, [], []
    for batch in entries:
        feed.require(batch.is_dir() and not batch.is_symlink() and not batch.is_junction() and feed.HEX64.fullmatch(batch.name),
                     "Unsupported batch format; no fallback")
        feed.require({p.name for p in batch.iterdir()} == {"manifest.json", "predictions.csv", "bindings.csv"}, "Daily file set mismatch")
        for name in ("manifest.json", "predictions.csv", "bindings.csv"):
            path = batch / name
            feed.require(not path.is_symlink() and not path.is_junction(), "Reparse input refused")
            before[path] = path.read_bytes()
        manifest = json.loads(before[batch / "manifest.json"], object_pairs_hook=_unique_object)
        feed.require(type(manifest) is dict and set(manifest) == {"predictions.csv", "bindings.csv"}, "Unsupported daily manifest")
        for name, value in manifest.items():
            feed.require(type(value) is str and feed.HEX64.fullmatch(value) and feed.sha(before[batch / name]) == value, "Daily SHA mismatch")
        body = before[batch / "predictions.csv"]
        feed.read_champion_only_predictions(body)
        records.extend(feed.csv_frame(body, exact=feed.CHAMPION_COLUMNS).to_dict("records"))
        bindings.extend(feed.csv_frame(before[batch / "bindings.csv"], exact=feed.BINDING_COLUMNS).to_dict("records"))
    def encoded(rows, columns):
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader(); writer.writerows(rows)
        return stream.getvalue().encode("utf-8")
    projection = feed.read_dashboard_projection(repository_root,
        champion_body=encoded(records, feed.CHAMPION_COLUMNS),
        binding_body=encoded(bindings, feed.BINDING_COLUMNS), official_directory=runtime / "official")
    feed.require(sorted(directory.iterdir()) == entries and all(path.read_bytes() == body for path, body in before.items()),
                 "Daily store changed during read; HOLD")
    return projection


def digest(payload):
    def canonical(value):
        if type(value) in (int, float):
            return {"$f64": struct.pack(">d", value).hex()}
        if type(value) is dict:
            return {k: canonical(v) for k, v in value.items()}
        if type(value) is list:
            return [canonical(v) for v in value]
        return value
    return hashlib.sha256(json.dumps(canonical(payload), sort_keys=True, ensure_ascii=False,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def weekend_bounds(day):
    day = date.fromisoformat(feed.calendar_date(day))
    feed.require(day.weekday() in (5, 6), "Saturday/Sunday required")
    saturday = day - timedelta(days=day.weekday() - 5)
    return saturday.isoformat(), (saturday + timedelta(days=1)).isoformat()


def project_weekend(projection):
    """Anchor to the next unfinished official weekend, using source UTC, not host date.

    A remaining Sunday retains its Saturday, including completed fixtures. Friday,
    Monday and postponed fixtures outside this explicit two-day view are not added.
    Legacy previousRound and its Friday--Monday selection are untouched.
    """
    source = projection.official
    today = feed.timestamp(source.observed_at).astimezone(ZoneInfo("Asia/Tokyo")).date()
    candidates = []
    for row in source.schedule.itertuples(index=False):
        day = date.fromisoformat(feed.calendar_date(row.match_date))
        if day.weekday() in (5, 6) and row.status != "completed":
            start, end = weekend_bounds(row.match_date)
            if date.fromisoformat(end) >= today:
                candidates.append((start, end))
    period = min(candidates) if candidates else None
    payload = {"formatVersion": FORMAT, "model": dict(CHAMPION_MODEL),
               "updatedAt": source.observed_at, "sourceRevision": source.revision_id,
               "baseFeedSha256": digest(projection.payload), "period": list(period) if period else None,
               "matches": [], "excludedSavedFixtureIds": []}
    predictions = projection.predictions.set_index("fixture_key")
    # Do not silently lose a formerly weekend fixture moved outside the selected
    # weekend. Warn without placing it on its obsolete date or moving probabilities.
    for saved in projection.predictions.itertuples(index=False):
        original = date.fromisoformat(saved.match_date)
        current = projection.matches[saved.fixture_key]
        current_day = feed.timestamp(current["kickoffAt"]).astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat()
        if original.weekday() in (5, 6) and current_day != saved.match_date:
            old_period = weekend_bounds(saved.match_date)
            relevant = old_period == period if period else date.fromisoformat(old_period[1]) >= today
            if relevant and not (old_period[0] <= current_day <= old_period[1]):
                payload["excludedSavedFixtureIds"].append(saved.fixture_key)
    payload["excludedSavedFixtureIds"].sort()
    if period:
        for row in source.schedule.itertuples(index=False):
            if not period[0] <= row.match_date <= period[1]:
                continue
            match = {"id": row.fixture_key,
                     "homeTeam": {"id": row.home_team_id, "name": projection.names[row.home_team_id]},
                     "awayTeam": {"id": row.away_team_id, "name": projection.names[row.away_team_id]},
                     "kickoffAt": feed.kickoff_at(row.match_date, row.kickoff_time),
                     "fixtureStatus": row.status, "predictionStatus": "not_saved",
                     "prediction": None, "warning": None}
            if row.status == "candidate":
                match.update(predictionStatus="schedule_unconfirmed", warning="日程未確認")
            elif row.fixture_key in predictions.index:
                saved = predictions.loc[row.fixture_key]
                if saved.match_date != row.match_date or saved.kickoff != row.kickoff_time:
                    match.update(predictionStatus="prediction_conflict", warning="保存時の日程と不一致・表示保留")
                else:
                    match.update(predictionStatus="saved",
                                 prediction=deepcopy(projection.matches[row.fixture_key]["prediction"]))
            payload["matches"].append(match)
    payload["matches"].sort(key=lambda m: (feed.timestamp(m["kickoffAt"]), m["id"]))
    return validate_weekend(payload, base=projection.payload)


def validate_weekend(payload, *, base=None):
    """Exact schema and optional binding to the unchanged legacy feed."""
    def keys(value, expected):
        feed.require(type(value) is dict and set(value) == set(expected), "Weekend display schema mismatch")
    keys(payload, {"formatVersion", "model", "updatedAt", "sourceRevision", "baseFeedSha256", "period", "matches", "excludedSavedFixtureIds"})
    feed.require(payload["formatVersion"] == FORMAT and payload["model"] == CHAMPION_MODEL,
                 "Weekend Champion/version mismatch")
    feed.timestamp(payload["updatedAt"])
    feed.require(all(type(payload[k]) is str and feed.HEX64.fullmatch(payload[k])
                     for k in ("sourceRevision", "baseFeedSha256")), "Weekend SHA/revision invalid")
    if base is not None:
        validate_dashboard_data(base)
        feed.require(base["mode"] == "operational" and payload["baseFeedSha256"] == digest(base)
                     and payload["updatedAt"] == base["updatedAt"], "Weekend/base feed mismatch")
    base_matches = {m["id"]: m for key in ("previousRound", "nextRound")
                    for m in base[key]["matches"]} if base is not None else {}
    rows = payload["matches"]
    feed.require(type(rows) is list and len(rows) <= 100, "Weekend rows invalid")
    excluded = payload["excludedSavedFixtureIds"]
    feed.require(type(excluded) is list and len(excluded) <= 100 and all(type(v) is str and 0 < len(v) <= 200 for v in excluded)
                 and excluded == sorted(set(excluded)), "Excluded identity warnings invalid")
    period = payload["period"]
    if period is None:
        feed.require(not rows, "Unknown schedule must not contain fixtures")
        return payload
    feed.require(type(period) is list and len(period) == 2 and list(weekend_bounds(period[0])) == period,
                 "Weekend period invalid")
    seen = set()
    for row in rows:
        keys(row, {"id", "homeTeam", "awayTeam", "kickoffAt", "fixtureStatus", "predictionStatus", "prediction", "warning"})
        day = feed.timestamp(row["kickoffAt"]).astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat()
        feed.require(period[0] <= day <= period[1], "Fixture outside weekend")
        feed.require(type(row["id"]) is str and row["id"] not in seen, "Duplicate weekend identity")
        seen.add(row["id"])
        feed.require(row["id"] not in excluded, "Included/excluded fixture conflict")
        feed.require(row["fixtureStatus"] in {"scheduled", "candidate", "completed"}
                     and row["predictionStatus"] in STATES, "Unknown display state")
        saved = row["predictionStatus"] == "saved"
        feed.require((row["prediction"] is not None) == saved, "Unstored probability forbidden")
        feed.require(row["warning"] == {"saved": None, "not_saved": None,
                     "schedule_unconfirmed": "日程未確認", "prediction_conflict": "保存時の日程と不一致・表示保留"}[row["predictionStatus"]],
                     "Warning/status mismatch")
        feed.require((row["fixtureStatus"] == "candidate") == (row["predictionStatus"] == "schedule_unconfirmed"),
                     "Unconfirmed schedule cannot carry predictions")
        _text(row["id"], "id")
        feed.require(_team(row["homeTeam"], "homeTeam") != _team(row["awayTeam"], "awayTeam"), "Same club")
        _timestamp(row["kickoffAt"], "kickoffAt")
        if saved:
            probe = empty_dashboard()
            probe["nextRound"]["matches"] = [{k: deepcopy(row[k]) for k in (
                "id", "homeTeam", "awayTeam", "kickoffAt", "prediction")}]
            validate_dashboard_data(probe)
            if row["id"] in base_matches:
                original = base_matches[row["id"]]
                feed.require(all(row[k] == original[k] for k in (
                    "homeTeam", "awayTeam", "kickoffAt", "prediction")), "Saved/base prediction mismatch")
    feed.require(rows == sorted(rows, key=lambda m: (feed.timestamp(m["kickoffAt"]), m["id"])), "Weekend order invalid")
    return payload
