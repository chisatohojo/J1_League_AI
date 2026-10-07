"""Frozen ST2/A prospective comparison. Import/help perform no evidence IO.

Only persisted estimators are used: transform then predict_proba. No training,
evaluation, network, xG dependency, or artifact reconstruction. Real execution
(including dry-run) requires a separately reviewed task.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
from numbers import Integral
import os
from pathlib import Path
import re
import subprocess
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
PROSPECTIVE_BOUNDARY = "2026-10-06T18:24:19+09:00"
COMPARISON_VERSION = "season_transition_st2_vs_a_20261006_v1"
MODEL_VERSION = COMPARISON_VERSION
PREDICTION_ARTIFACT = "data/processed/predictions/season_transition_st2_prospective.csv"
OUTPUT_PATH = ROOT / PREDICTION_ARTIFACT
ST2_MODEL_VERSION = "season_transition_st2_20261006_v1"
ST2_ARTIFACT_HASH = "f20359a1c12a4508d1a593e266a92f25fb8cab597bbbe3ace7a19ae5b0160c82"
ST2_ARTIFACT_PATH = f"models/model_season_transition/{ST2_MODEL_VERSION}"
CHAMPION_A_MODEL_VERSION = "operational_champion_20260922_v1"
CHAMPION_A_ARTIFACT_HASH = "2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1"
CHAMPION_A_ARTIFACT_PATH = f"models/model_a/{CHAMPION_A_MODEL_VERSION}"
A_FILE_PINS = {
    "checksums.sha256": CHAMPION_A_ARTIFACT_HASH,
    "metadata.json": "bd1eb92c25bdb56a836ef7bfe3fcb13b0137a2ece01b6095e7d100e1f5afdd19",
    "model.joblib": "60636e4652bce98b76c394310947b1b8923a8bf18a640d9e7976497989ed54be",
    "scaler.joblib": "a8a5f176944049c6825071b580c5fe40f5a5fb28f504f8880d028deaf2494750",
    "training_manifest.csv": "eea7498fabac6acc79a9c297468b470702288b61736b63d90214d741ab8fb32a",
}
BOUNDARY_REVISION = "71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538"
BOUNDARY_MANIFEST_SHA = "c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34"
BOUNDARY_SNAPSHOT_ID = "20261003T230410579984Z-794e906d"
BOUNDARY_RAW_MANIFEST = f"data/raw/jleague/2026_27/snapshots/{BOUNDARY_SNAPSHOT_ID}/manifest.json"
BOUNDARY_RAW_MANIFEST_SHA = "dfbb3fd9ddaaf066bb4e8da027e2dda304b9dc0569cf406d15f05c9d1d1ab27e"
BOUNDARY_FILE_PINS = {
    "schedule.csv": "599ad3dad9b30bf440d5e50b9867fd55d796b0a5a7bcc5a9d13a5b44526f1bd0",
    "completed_matches.csv": "ba9f96d4cbdf4a85e57a578ef46b358d77fbd94669c8c849bfdbf26bd262614d",
    "fixture_identity.csv": "953537cdc3418dad978b0ddbc0cf289876bade1ebb35a1adbdb6af53edc1d739",
    "observations.json": "5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc",
    "update_summary.json": "7e5b4d0f0fb27be566cdfdd286ab73ace56cf59931bd73767beb76a78510cbcb",
}
COHORT_HASH = "b63bce0289b80d096599a2f6343c48073c3617d919b3bf7153683e2089dfdcbf"
EXPECTED_COHORT_ROWS = 300
EXPECTED_SCHEDULE_ROWS = 380
ONGOING_PATH = "data/processed/jleague/2026_27"
HYAKUNEN_PATH = "data/processed/jleague/2026_hyakunen/matches.csv"
HYAKUNEN_SHA = "9f871594e5216c1c89e69fcef835c641f3a4b5dbefce8d138e79881494c71f8c"
AUTHORIZATION_ENV = "CHAMPION_A_ST2_PREDICTION_AUTHORIZATION"
CLASS_ORDER = (0, 1, 2)
PREDICTION_COLUMNS = (
    "fixture_key", "match_id", "match_date", "kickoff", "home_team_id",
    "away_team_id", "home_team_name", "away_team_name", "prediction_generated_at",
    "prospective_boundary", "comparison_version", "model_version", "source_revision",
    "source_observed_at", "champion_a_model_version", "champion_a_artifact_hash",
    "st2_model_version", "st2_artifact_hash", "a_elo_diff", "st2_elo_diff",
    "a_p_away", "a_p_draw", "a_p_home", "st2_p_away", "st2_p_draw", "st2_p_home",
    "a_predicted_class", "st2_predicted_class",
)
SAFE_SCHEDULE_COLUMNS = (
    "fixture_key", "match_id", "match_date", "kickoff_time", "home_team",
    "away_team", "home_club", "away_club", "status", "competition_key", "season",
    "match_id_namespace", "match_page_id", "data_site_match_id", "evidence_type",
    "evidence_url", "evidence_sha256", "evidence_fetched_at_utc",
)


class ST2PredictionError(ValueError):
    """Technical STOP; no fallback, repair, refit or performance decision."""


def require(condition, message):
    if not condition:
        raise ST2PredictionError(message)


def libs():
    import numpy as np
    import pandas as pd
    return np, pd


def sha(body):
    return hashlib.sha256(body).hexdigest()


def exact_text(value):
    return isinstance(value, str) and bool(value) and value == value.strip() and value.isprintable()


def timestamp(value):
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    require(isinstance(parsed, datetime) and parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "Timezone-aware timestamp required")
    return parsed


def calendar_date(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value), "Exact calendar date")
    date.fromisoformat(value)
    return value


def rooted(root, relative):
    root = Path(root).resolve()
    path = root / relative
    require(path.resolve().is_relative_to(root), "Evidence path escapes repository")
    return path


def read_csv(body, *, safe=False):
    _, pd = libs()
    # Parse no score/result columns from a schedule (not even temporary frames).
    import csv
    header = next(csv.reader(io.StringIO(body.decode("utf-8-sig"))), [])
    require(bool(header) and len(header) == len(set(header)), "CSV header duplicate/empty")
    return pd.read_csv(io.BytesIO(body), dtype=str, keep_default_na=False,
                       usecols=(lambda c: c in SAFE_SCHEDULE_COLUMNS) if safe else None)


@dataclass(frozen=True)
class Revision:
    revision_id: str
    manifest_sha: str
    manifest: dict
    files: dict


def read_revision(directory, *, expected_sha=None):
    directory = Path(directory)
    body = (directory / "manifest.json").read_bytes()
    digest = sha(body)
    require(expected_sha is None or digest == expected_sha, "Revision manifest hash mismatch")
    manifest = json.loads(body)
    from src.collect.jleague_ongoing import COMPLETION_POLICY
    require(manifest.get("format_version") in {"ongoing-v1", "ongoing-v2"}
            and manifest.get("completion_policy") == COMPLETION_POLICY
            and manifest.get("summary", {}).get("publication_status") == "published", "Unaccepted revision")
    require({"schedule.csv", "completed_matches.csv", "fixture_identity.csv"} <= set(manifest["files"]), "Revision coverage")
    files = {}
    for name, expected in manifest["files"].items():
        require(re.fullmatch(r"[A-Za-z0-9_.-]+", name) and name not in {".", ".."}, "Unsafe revision filename")
        files[name] = (directory / name).read_bytes()
        require(sha(files[name]) == expected, f"Revision file hash mismatch: {name}")
    timestamp(manifest["summary"]["observed_at_utc"])
    return Revision(directory.name, digest, manifest, files)


def read_current_revision(root):
    directory = rooted(root, ONGOING_PATH)
    pointer = json.loads((directory / "latest.json").read_bytes())
    require(re.fullmatch(r"[0-9a-f]{64}", pointer["revision_id"]), "Published revision ID")
    return read_revision(directory / "revisions" / pointer["revision_id"], expected_sha=pointer["manifest_sha256"])


def validate_schedule(schedule):
    require({"fixture_key", "match_id", "match_date", "kickoff_time", "home_team", "away_team",
             "home_club", "away_club", "status", "competition_key", "season"} <= set(schedule), "Safe schedule schema")
    require(len(schedule) == EXPECTED_SCHEDULE_ROWS and schedule.fixture_key.is_unique, "Exact full schedule population")
    require(schedule.status.isin(["scheduled", "candidate", "completed"]).all(), "Unknown schedule status")
    require(schedule.competition_key.eq("j1_2026_2027").all() and schedule.season.eq("2026").all(), "Ordinary ongoing identity")
    for row in schedule.itertuples(index=False):
        calendar_date(row.match_date)
        require("2026-08-01" <= row.match_date <= "2027-06-30", "Ongoing season date")
        require(row.fixture_key == f"j1_2026_2027:{row.home_club}:{row.away_club}"
                and row.home_club != row.away_club
                and re.fullmatch(r"j1_2026_2027:[a-z0-9_-]+:[a-z0-9_-]+", row.fixture_key), "Directional fixture identity")
    return schedule


def validate_revision_schedule(revision):
    schedule = validate_schedule(read_csv(revision.files["schedule.csv"], safe=True))
    identity = read_csv(revision.files["fixture_identity.csv"])
    cols = ["fixture_key", "match_id", "home_club", "away_club"]
    require(set(cols) <= set(identity) and identity.fixture_key.is_unique, "Published fixture identity schema")
    require(schedule[cols].sort_values("fixture_key").reset_index(drop=True).equals(
        identity[cols].sort_values("fixture_key").reset_index(drop=True)), "Published fixture identity mismatch")
    completed = read_csv(revision.files["completed_matches.csv"])
    require("status" in completed and completed.status.eq("completed").all(), "Separate completed subset required")
    expected = schedule.loc[schedule.status.eq("completed")].reset_index(drop=True)
    require(set(schedule) <= set(completed) and expected.equals(completed[list(schedule)].reset_index(drop=True)),
            "Completed subset/schedule identity mismatch")
    return schedule, completed


def frozen_cohort(root):
    revision = read_revision(rooted(root, f"{ONGOING_PATH}/revisions/{BOUNDARY_REVISION}"), expected_sha=BOUNDARY_MANIFEST_SHA)
    require(revision.manifest["snapshot_id"] == BOUNDARY_SNAPSHOT_ID, "Boundary snapshot identity")
    require(sha(rooted(root, BOUNDARY_RAW_MANIFEST).read_bytes()) == BOUNDARY_RAW_MANIFEST_SHA, "Boundary raw manifest hash")
    for name, digest in BOUNDARY_FILE_PINS.items():
        require(sha(revision.files[name]) == digest, f"Boundary byte pin: {name}")
    # No boundary outcome parsing; completed status/identity alone define exclusion.
    schedule = validate_schedule(read_csv(revision.files["schedule.csv"], safe=True))
    require(schedule.status.isin(["scheduled", "completed"]).all(), "Frozen unexplained status")
    cohort = schedule.loc[schedule.status.eq("scheduled")].sort_values(["match_date", "fixture_key"], kind="stable").reset_index(drop=True)
    require(len(cohort) == EXPECTED_COHORT_ROWS, "Frozen cohort count")
    require(sha(("\n".join(cohort.fixture_key) + "\n").encode("utf-8")) == COHORT_HASH, "Frozen cohort sequence hash")
    require(cohort.match_date.gt(timestamp(PROSPECTIVE_BOUNDARY).date().isoformat()).all(), "Frozen cohort crosses boundary")
    return schedule, cohort


def select_next_date_batch(schedule, frozen_schedule, cohort):
    validate_schedule(schedule)
    require(set(schedule.fixture_key) == set(frozen_schedule.fixture_key), "Changed full schedule fixture population")
    columns = ["fixture_key", "home_club", "away_club", "home_team", "away_team"]
    require(schedule[columns].sort_values("fixture_key").reset_index(drop=True).equals(
        frozen_schedule[columns].sort_values("fixture_key").reset_index(drop=True)), "Changed frozen fixture identity")
    selected = schedule.loc[schedule.fixture_key.isin(cohort.fixture_key)].copy()
    require(len(selected) == len(cohort), "Frozen cohort one-to-one resolution")
    require(selected.match_date.gt(timestamp(PROSPECTIVE_BOUNDARY).date().isoformat()).all(), "Current cohort crosses boundary")
    # Completed baseline fixtures cannot silently revert into a new target.
    baseline = set(frozen_schedule.fixture_key) - set(cohort.fixture_key)
    require(schedule.loc[schedule.fixture_key.isin(baseline), "status"].eq("completed").all(), "Frozen completed baseline reverted")
    unfinished = selected.loc[~selected.status.eq("completed")]
    if unfinished.empty:
        return unfinished.reset_index(drop=True)
    return unfinished.loc[unfinished.match_date.eq(unfinished.match_date.min())].sort_values("fixture_key", kind="stable").reset_index(drop=True)


def resolve_team_ids(frame, master):
    output = frame.copy()
    for side in ("home", "away"):
        output[f"{side}_team_id"] = [master.resolve_team_id(name, on=day)
                                      for name, day in zip(frame[f"{side}_team"], frame.match_date)]
    require(not output.home_team_id.eq(output.away_team_id).any(), "Resolved self-match")
    return output


def validate_witness(root, revision_id, manifest_sha, target, namespace, master):
    require(re.fullmatch(r"[0-9a-f]{64}", revision_id) and re.fullmatch(r"[0-9a-f]{64}", manifest_sha), "Immutable witness identity")
    witness = read_revision(rooted(root, f"{ONGOING_PATH}/revisions/{revision_id}"), expected_sha=manifest_sha)
    schedule = resolve_team_ids(read_csv(witness.files["schedule.csv"], safe=True), master)
    rows = schedule.loc[schedule.fixture_key.eq(target.fixture_key)]
    require(len(rows) == 1, "Witness fixture cardinality")
    row = rows.iloc[0]
    observed = timestamp(witness.manifest["summary"]["observed_at_utc"])
    if row.get("evidence_fetched_at_utc", ""):
        require(timestamp(row.evidence_fetched_at_utc) <= observed, "Witness evidence after publication")
    require(all(str(row[c]) == str(target[c]) for c in ("match_date", "home_team_id", "away_team_id")), "Witness fixture identity mismatch")
    if witness.manifest["format_version"] == "ongoing-v2":
        require(row.match_id == target.match_id and row.match_id_namespace == namespace, "Witness explicit namespace mismatch")
    else:
        require(namespace == "jleague_match_page" and row.match_id == target.match_id, "Witness v1 official ID mismatch")
        require(row.evidence_type in {"official_completion_unconfirmed", "official_scheduled_identity", "official_game_over_section"}
                and re.fullmatch(r"https://www\.jleague\.jp/match/j1/(2026|2027)/" + re.escape(target.match_id) + r"/", row.evidence_url), "Witness official page evidence")
    return witness


def resolve_target_identity(targets, bindings, revision, *, root, master):
    from src.modeling.prediction_identity import validate_prediction_bindings
    validate_prediction_bindings(bindings)
    resolved = targets.copy()
    witnesses = []
    for index, target in resolved.iterrows():
        require(exact_text(target.match_id), "Every target needs official nonblank match ID; no ID-available subset")
        namespace = target.get("match_id_namespace", "")
        if revision.manifest["format_version"] == "ongoing-v2":
            require(namespace in {"jleague_match_page", "jleague_data_site"}, "Explicit v2 namespace required")
            from src.collect.jleague_ongoing_source import apply_operational_identity
            typed = target.to_dict()
            for field in ("match_page_id", "data_site_match_id"):
                typed[field] = typed.get(field) or None
            apply_operational_identity(typed)
            require(typed["match_id"] == target.match_id and typed["match_id_namespace"] == namespace, "v2 typed identity mismatch")
            witness_id, witness_sha = revision.revision_id, revision.manifest_sha
        else:
            require(not namespace, "v1 namespace must come only from reviewed bindings")
            evidence = bindings.loc[bindings.fixture_key.eq(target.fixture_key)]
            cols = ["prediction_match_id", "prediction_id_namespace", "fixture_key", "match_date", "home_team_id", "away_team_id",
                    "identity_witness_revision_id", "identity_witness_manifest_sha256"]
            require(not evidence.empty and len(evidence[cols].drop_duplicates()) == 1, "Missing or conflicting v1 binding evidence")
            agreed = evidence.iloc[0]
            require(agreed.prediction_match_id == target.match_id
                    and all(agreed[c] == target[c] for c in ("fixture_key", "match_date", "home_team_id", "away_team_id")), "v1 binding identity conflicts")
            namespace = agreed.prediction_id_namespace
            witness_id, witness_sha = agreed.identity_witness_revision_id, agreed.identity_witness_manifest_sha256
        witness = validate_witness(root, witness_id, witness_sha, target, namespace, master)
        require(timestamp(witness.manifest["summary"]["observed_at_utc"])
                <= timestamp(revision.manifest["summary"]["observed_at_utc"]), "Identity witness unavailable at current publication")
        resolved.loc[index, "match_id_namespace"] = namespace
        witnesses.append((witness_id, witness_sha))
    require(resolved.match_id.is_unique, "Duplicate target match ID")
    reject_date_team_duplicates(resolved)
    return resolved, witnesses


def reject_date_team_duplicates(frame):
    _, pd = libs()
    sides = pd.concat([frame[["match_date", f"{s}_team_id"]].rename(columns={f"{s}_team_id": "team_id"}) for s in ("home", "away")])
    require(not sides.duplicated(["match_date", "team_id"]).any(), "Duplicate (match_date, team_id)")


@dataclass
class LiveStates:
    a: dict
    st2: dict
    ordinals: dict
    captures: list


def replay_live_states(ordinary, hyakunen, ongoing, registered_ids, *, target_date):
    """Pure date-batched replay. Captures are internal, never output columns."""
    _, pd = libs()
    from src.features.elo import expected_score
    from src.modeling.season_transition_st2_artifact import match_k
    roster = tuple(registered_ids)
    require(bool(roster) and len(set(roster)) == len(roster), "Exact unique registered roster")
    a, st2 = {t: 1500.0 for t in roster}, {t: 1500.0 for t in roster}
    calendar_date(target_date)
    ordinals, captures, last_date, ids = {}, [], None, set()
    for segment, frame in (("ordinary", ordinary), ("hyakunen", hyakunen), ("ongoing", ongoing)):
        require({"match_date", "match_id", "season", "home_team_id", "away_team_id", "result"} <= set(frame), "History schema")
        ordered = frame.copy()
        ordered["match_date"] = pd.to_datetime(ordered.match_date).dt.strftime("%Y-%m-%d")
        ordered = ordered.sort_values(["match_date", "match_id"], kind="stable")
        reject_date_team_duplicates(ordered)
        require(ordered.match_id.is_unique and not ids.intersection(ordered.match_id), "Duplicate history ID")
        ids.update(ordered.match_id)
        if not ordered.empty:
            require(last_date is None or ordered.match_date.min() > last_date, "History segment ordering")
            last_date = ordered.match_date.max()
        require(ordered.match_date.lt(target_date).all(), "History must be strictly earlier than target date")
        if segment == "ongoing":
            ordinals = {}  # Carry ratings; one ordinary season, including 2027.
        current_season = None
        for day, batch in ordered.groupby("match_date", sort=False):
            seasons = set(batch.season.astype(int))
            require(len(seasons) == 1, "Mixed season on one date")
            season = next(iter(seasons))
            require((2015 <= season <= 2025 and int(day[:4]) == season) if segment == "ordinary"
                    else season == 2026, "History segment season")
            if segment == "ordinary" and season != current_season:
                ordinals, current_season = {}, season
            before = []
            for row in batch.itertuples(index=False):
                h, w = row.home_team_id, row.away_team_id
                require(h in a and w in a and h != w, "Unknown history team/self-match")
                require(isinstance(row.result, Integral) and not isinstance(row.result, bool)
                        and row.result in (0, 1, 2), "Regulation-time result class")
                hn, wn = ordinals.get(h, 0) + 1, ordinals.get(w, 0) + 1
                k = 30.0 if segment == "hyakunen" else match_k(hn, wn)
                capture = (row, a[h], a[w], st2[h], st2[w], hn, wn, k,
                           expected_score(a[h] + 175.0, a[w]), expected_score(st2[h] + 175.0, st2[w]))
                before.append(capture)
                captures.append({"segment": segment, "match_id": row.match_id, "a_elo_diff": a[h] - a[w],
                                 "st2_elo_diff": st2[h] - st2[w], "home_ordinal": hn, "away_ordinal": wn, "st2_k": k})
            # Every day's pre-match capture above precedes every result below.
            for row, ah, aw, sh, sw, hn, wn, k, ae, se in before:
                delta_a, delta_st2 = 30.0 * (int(row.result) / 2.0 - ae), k * (int(row.result) / 2.0 - se)
                a[row.home_team_id], a[row.away_team_id] = ah + delta_a, aw - delta_a
                st2[row.home_team_id], st2[row.away_team_id] = sh + delta_st2, sw - delta_st2
                if segment != "hyakunen":
                    ordinals[row.home_team_id], ordinals[row.away_team_id] = hn, wn
    require(all(math.isfinite(v) for v in (*a.values(), *st2.values())), "Finite live ratings")
    return LiveStates(a, st2, ordinals, captures)


def load_live_history(root, revision, completed, master, *, target_date):
    """All explicit historical hashes pass before any historical source parsing."""
    from src.modeling import season_transition_st2_artifact as authority
    from src.features.elo_history import _read_hyakunen_matches, _order_matches, _prepare_ongoing_matches
    from src.collect.jleague_hyakunen import validate_competition
    pins = {**authority.SOURCE_HASHES, authority.TEAM_MASTER_PATH: authority.TEAM_MASTER_SHA, HYAKUNEN_PATH: HYAKUNEN_SHA}
    snapshots = {p: rooted(root, p).read_bytes() for p in pins}
    for path, digest in pins.items():
        require(sha(snapshots[path]) == digest, f"Historical source hash mismatch: {path}")
    matches, pinned_master = authority.load_sources(snapshots)
    require(pinned_master.aliases == master.aliases, "TeamMaster changed")
    ordinary = authority.validate_source(matches, master)
    # Existing typed special parser; recheck bytes after its read (no tie table).
    special = _read_hyakunen_matches(rooted(root, HYAKUNEN_PATH))
    require(rooted(root, HYAKUNEN_PATH).read_bytes() == snapshots[HYAKUNEN_PATH], "Hyakunen changed during parse")
    validate_competition(special)
    special = _order_matches(special, master)
    observed = timestamp(revision.manifest["summary"]["observed_at_utc"])
    for row in completed.itertuples(index=False):
        require(timestamp(row.evidence_fetched_at_utc) <= observed, "Completed evidence after publication")
    # Validate ALL official completed rows before selecting strictly prior history.
    ongoing = _prepare_ongoing_matches(completed, master, revision.manifest["summary"]["observed_at_utc"])
    ongoing = ongoing.loc[ongoing.match_date.lt(libs()[1].Timestamp(target_date))].copy()
    return ordinary, special, ongoing


@dataclass(frozen=True)
class FrozenModel:
    scaler: object
    model: object
    artifact_hash: str
    metadata: dict


def validate_model_a_artifact(path):
    """Non-xG-specific read-only validator; every frozen byte pin before load."""
    np, _ = libs()
    path = Path(path)
    require(set(p.name for p in path.iterdir()) == set(A_FILE_PINS), "A exact five files")
    bodies = {}
    for name, digest in A_FILE_PINS.items():
        require((path / name).is_file() and not (path / name).is_symlink(), "A artifact file type")
        bodies[name] = (path / name).read_bytes()
        require(sha(bodies[name]) == digest, f"A artifact hash/pin mismatch: {name}")
    require(sha(bodies["checksums.sha256"]) == CHAMPION_A_ARTIFACT_HASH, "A expected artifact hash")
    # Preserve original A writer's platform newline semantics. Exact byte pins
    # above lock the actual bundle; parsing never rewrites/normalizes its bytes.
    checksum_lines = [f"{sha(bodies[n])}  {n}" for n in sorted(set(bodies) - {"checksums.sha256"})]
    require(bodies["checksums.sha256"].decode("ascii").splitlines() == checksum_lines, "A exact checksum coverage/order")
    metadata = json.loads(bodies["metadata.json"])
    require(metadata.get("model_version") == CHAMPION_A_MODEL_VERSION and metadata.get("role") == "operational_champion"
            and metadata.get("training_row_count") == 3588 and metadata.get("feature_list") == ["elo_diff"]
            and metadata.get("target_mapping") == {"0": "Away", "1": "Draw", "2": "Home"}
            and metadata.get("future_rows_used") == 0 and metadata.get("metrics_calculated") is False
            and metadata.get("predictions_generated") is False, "A frozen metadata contract")
    for key, name in (("training_manifest_hash", "training_manifest.csv"), ("model_hash", "model.joblib"), ("scaler_hash", "scaler.joblib")):
        require(metadata.get(key) == sha(bodies[name]), "A metadata file linkage")
    import joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    scaler, model = joblib.load(io.BytesIO(bodies["scaler.joblib"])), joblib.load(io.BytesIO(bodies["model.joblib"]))
    require(type(scaler) is StandardScaler and type(model) is LogisticRegression, "A persisted estimator types")
    require(scaler.n_features_in_ == model.n_features_in_ == 1 and tuple(model.classes_) == CLASS_ORDER, "A class order/width")
    require(model.coef_.shape == (3, 1) and model.intercept_.shape == (3,), "A fitted shape")
    require(all(np.isfinite(v).all() for v in (scaler.mean_, scaler.scale_, model.coef_, model.intercept_))
            and (scaler.scale_ > 0).all(), "A finite fitted state")
    return FrozenModel(scaler, model, CHAMPION_A_ARTIFACT_HASH, metadata)


def load_model_pair(root):
    from src.modeling.season_transition_st2_artifact import load_artifact
    st2 = load_artifact(rooted(root, ST2_ARTIFACT_PATH), expected_artifact_hash=ST2_ARTIFACT_HASH)
    require(st2.artifact_hash == ST2_ARTIFACT_HASH and st2.metadata["model_version"] == ST2_MODEL_VERSION, "ST2 model identity/hash")
    a = validate_model_a_artifact(rooted(root, CHAMPION_A_ARTIFACT_PATH))
    return a, FrozenModel(st2.fitted.scaler, st2.fitted.model, st2.artifact_hash, st2.metadata)


def validate_probabilities(values, n):
    np, _ = libs()
    values = np.asarray(values, dtype=np.float64)
    require(values.shape == (n, 3) and np.isfinite(values).all() and ((0 <= values) & (values <= 1)).all(), "Probability shape/range/finite")
    require(np.allclose(values.sum(axis=1), 1.0, rtol=0, atol=1e-12), "Probability sum; no renormalization")
    return values


def predict_branch(branch, differences):
    np, _ = libs()
    require(tuple(branch.model.classes_) == CLASS_ORDER and branch.model.n_features_in_ == branch.scaler.n_features_in_ == 1, "Prediction class order/feature width")
    matrix = np.asarray(differences, dtype=np.float64).reshape(-1, 1)
    require(np.isfinite(matrix).all(), "Finite raw Elo feature")
    scaled = branch.scaler.transform(matrix)
    require(np.isfinite(scaled).all(), "Finite scaled Elo")
    return validate_probabilities(branch.model.predict_proba(scaled), len(matrix))


def validate_target_time(targets, now):
    now = timestamp(now)
    require(now > timestamp(PROSPECTIVE_BOUNDARY), "Prediction must follow exact boundary")
    for row in targets.itertuples(index=False):
        require(row.status == "scheduled", "Target must be officially scheduled, not candidate/completed")
        calendar_date(row.match_date)
        require(re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", row.kickoff_time), "Exact official HH:MM kickoff required")
        kickoff = datetime.fromisoformat(f"{row.match_date}T{row.kickoff_time}").replace(tzinfo=ZoneInfo("Asia/Tokyo"))
        require(now < kickoff, "Kickoff elapsed; never backdate")
    return now


def generate_prediction_records(targets, states, a, st2, *, now, source_revision, source_observed_at):
    np, pd = libs()
    require(not {"result", "home_score", "away_score", "winner", "correctness", "accuracy", "log_loss", "brier"} & set(targets), "Outcome/metric fields forbidden in prediction API")
    now = validate_target_time(targets, now)
    require(timestamp(source_observed_at) <= now, "Source observed after prediction time")
    require(exact_text(source_revision), "Source revision required")
    require(a.artifact_hash == CHAMPION_A_ARTIFACT_HASH and st2.artifact_hash == ST2_ARTIFACT_HASH, "Pinned branch artifact hash")
    reject_date_team_duplicates(targets)
    differences = [[ratings[r.home_team_id] - ratings[r.away_team_id] for r in targets.itertuples(index=False)] for ratings in (states.a, states.st2)]
    pa, ps = predict_branch(a, differences[0]), predict_branch(st2, differences[1])
    rows = []
    for i, row in enumerate(targets.itertuples(index=False)):
        rows.append((row.fixture_key, row.match_id, row.match_date, row.kickoff_time,
                     row.home_team_id, row.away_team_id, row.home_team, row.away_team,
                     now.isoformat(), PROSPECTIVE_BOUNDARY, COMPARISON_VERSION, MODEL_VERSION,
                     source_revision, source_observed_at, CHAMPION_A_MODEL_VERSION,
                     CHAMPION_A_ARTIFACT_HASH, ST2_MODEL_VERSION, ST2_ARTIFACT_HASH,
                     differences[0][i], differences[1][i], *pa[i], *ps[i], int(np.argmax(pa[i])), int(np.argmax(ps[i]))))
    records = pd.DataFrame(rows, columns=PREDICTION_COLUMNS)
    validate_prediction_records(records)
    return records


def validate_prediction_records(records):
    np, _ = libs()
    require(tuple(records.columns) == PREDICTION_COLUMNS and not records.isna().any().any(), "Exact 28-column prediction schema")
    require(not records.duplicated(["match_id", "model_version"]).any()
            and not records.duplicated(["fixture_key", "model_version"]).any(), "Duplicate comparison key")
    for c in PREDICTION_COLUMNS[:18]:
        require(records[c].map(exact_text).all(), f"Nonblank exact prediction field: {c}")
    pins = {"prospective_boundary": PROSPECTIVE_BOUNDARY, "comparison_version": COMPARISON_VERSION,
            "model_version": MODEL_VERSION, "champion_a_model_version": CHAMPION_A_MODEL_VERSION,
            "champion_a_artifact_hash": CHAMPION_A_ARTIFACT_HASH, "st2_model_version": ST2_MODEL_VERSION,
            "st2_artifact_hash": ST2_ARTIFACT_HASH}
    require(all(records[c].eq(v).all() for c, v in pins.items()), "Prediction constant/model version alias")
    for row in records.itertuples(index=False):
        require(timestamp(row.source_observed_at) <= timestamp(row.prediction_generated_at), "Prediction source time")
        validate_target_time(libs()[1].DataFrame([{"status": "scheduled", "match_date": row.match_date, "kickoff_time": row.kickoff}]), row.prediction_generated_at)
    for prefix in ("a", "st2"):
        require(np.isfinite(records[f"{prefix}_elo_diff"].astype(float)).all(), "Finite saved Elo difference")
        values = validate_probabilities(records[[f"{prefix}_p_{s}" for s in ("away", "draw", "home")]].to_numpy(dtype=float), len(records))
        require(np.array_equal(records[f"{prefix}_predicted_class"].astype(str).to_numpy(), np.argmax(values, axis=1).astype(str)), "Plain argmax class")


def make_comparison_bindings(records, targets, witnesses):
    _, pd = libs()
    from src.modeling.prediction_identity import BINDING_COLUMNS, make_binding_rows, validate_prediction_bindings
    require(len(records) == len(targets) == len(witnesses), "Comparison witness cardinality")
    frames = [make_binding_rows(records.iloc[[i]], targets.iloc[[i]], prediction_artifact=PREDICTION_ARTIFACT,
                               identity_witness_revision_id=w[0], identity_witness_manifest_sha256=w[1]) for i, w in enumerate(witnesses)]
    return validate_prediction_bindings(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=BINDING_COLUMNS))


def append_records(records):
    """Round-trip numeric strings keep the common journal's JSON lossless.

    The reviewed common writer uses pandas.to_json (float precision defaults).
    Supplying exact float64 round-trip strings avoids rounding journal suffixes,
    while leaving estimator values and the frozen CSV schema unchanged.
    """
    validate_prediction_records(records)
    serialized = records.copy()
    for column in PREDICTION_COLUMNS[18:26]:
        serialized[column] = records[column].map(lambda value: repr(float(value)))
    for column in PREDICTION_COLUMNS[26:]:
        serialized[column] = records[column].map(lambda value: str(int(value)))
    validate_prediction_records(serialized)
    return serialized


def existing_comparisons(root, bindings):
    _, pd = libs()
    from src.modeling.prediction_identity import validate_complete_sidecar
    path = rooted(root, PREDICTION_ARTIFACT)
    selected = bindings.loc[bindings.prediction_artifact.eq(PREDICTION_ARTIFACT)]
    if not path.exists():
        require(selected.empty, "Orphan ST2 bindings/partial append")
        return pd.DataFrame(columns=PREDICTION_COLUMNS)
    records = read_csv(path.read_bytes())
    validate_prediction_records(records)
    from src.modeling.prediction_identity import DEFAULT_BINDING_PATH
    validate_complete_sidecar(repository_root=root, binding_path=rooted(root, DEFAULT_BINDING_PATH), prediction_artifacts=(PREDICTION_ARTIFACT,))
    indexed = selected.set_index(["prediction_match_id", "model_version"])
    require(indexed.index.is_unique, "ST2 binding primary key")
    for row in records.itertuples(index=False):
        require(indexed.loc[(row.match_id, row.model_version), "fixture_key"] == row.fixture_key, "ST2 binding fixture conflict")
    return records


def repository_state(root):
    def git(*args):
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    head = git("rev-parse", "HEAD")
    require(re.fullmatch(r"[0-9a-f]{40}", head) and not git("status", "--porcelain"), "Current clean HEAD required")
    return head


def validate_authorization(authorization, head, *, target_date=None):
    require(isinstance(authorization, dict) and set(authorization) == {"approved_execution_head", "target_date", "task_reference"}, "Separate production authorization required")
    require(authorization["approved_execution_head"] == head and exact_text(authorization["task_reference"]), "Authorization HEAD/reference mismatch")
    calendar_date(authorization["target_date"])
    require(target_date is None or authorization["target_date"] == target_date, "Authorization target date mismatch")


def run_prediction(*, root=ROOT, dry_run=False, authorization=None, clock=None):
    """Future operational entry. Tests inject only tmp repositories and clocks."""
    _, pd = libs()
    from src.modeling import season_transition_st2_artifact as authority
    from src.modeling.prediction_identity import (DEFAULT_BINDING_PATH, validate_complete_sidecar,
        append_prediction_and_bindings, recover_prediction_append)
    root = Path(root).resolve()
    head = None
    if not dry_run:
        head = repository_state(root)
        validate_authorization(authorization, head)
    clock = (lambda: datetime.now(timezone.utc)) if clock is None else clock
    now = timestamp(clock())
    frozen, cohort = frozen_cohort(root)
    revision = read_current_revision(root)
    require(timestamp(revision.manifest["summary"]["observed_at_utc"]) <= now, "Future published source")
    schedule, completed = validate_revision_schedule(revision)
    batch = select_next_date_batch(schedule, frozen, cohort)
    target_date = None if batch.empty else str(batch.match_date.iloc[0])
    if not dry_run:
        validate_authorization(authorization, head, target_date=target_date)
    sidecar = rooted(root, DEFAULT_BINDING_PATH)
    output = rooted(root, PREDICTION_ARTIFACT)
    journal = sidecar.with_name(f".{sidecar.name}.journal.json")
    require(not sidecar.with_name(f".{sidecar.name}.lock").exists(), "Prediction writer lock exists")
    if journal.exists():
        require(not dry_run, "Pending journal: dry-run cannot recover/write")
        frozen_journal = json.loads(journal.read_bytes())
        desired = pd.DataFrame(frozen_journal["prediction_rows"], columns=PREDICTION_COLUMNS)
        validate_prediction_records(desired)
        require(not desired.empty and desired.match_date.eq(authorization["target_date"]).all(), "Recovery authorization date")
        require(set(desired.fixture_key).issubset(set(batch.fixture_key)), "Recovery outside frozen target batch")
        from src.modeling.prediction_identity import BINDING_COLUMNS, validate_prediction_bindings
        desired_bindings = validate_prediction_bindings(pd.DataFrame(frozen_journal["binding_rows"], columns=BINDING_COLUMNS))
        require(len(desired) == len(desired_bindings), "Recovery binding cardinality")
        validate_complete_sidecar(repository_root=root, binding_path=sidecar)
        master_body = rooted(root, authority.TEAM_MASTER_PATH).read_bytes()
        require(sha(master_body) == authority.TEAM_MASTER_SHA, "Recovery TeamMaster hash")
        recovery_master = authority.parse_master(master_body)
        current_targets = resolve_team_ids(batch, recovery_master).set_index("fixture_key")
        by_key = desired_bindings.set_index(["prediction_match_id", "model_version"])
        require(by_key.index.is_unique, "Recovery binding primary key")
        for _, record in desired.iterrows():
            require((record.match_id, record.model_version) in by_key.index, "Recovery binding missing")
            binding = by_key.loc[(record.match_id, record.model_version)]
            require(binding.prediction_artifact == PREDICTION_ARTIFACT and all(binding[c] == record[c]
                    for c in ("fixture_key", "match_date", "home_team_id", "away_team_id", "prediction_generated_at")), "Recovery binding conflicts")
            require(all(current_targets.loc[record.fixture_key, c] == record[c]
                    for c in ("match_date", "home_team_id", "away_team_id")), "Recovery target identity changed")
            target = record.copy()
            target["match_id_namespace"] = binding.prediction_id_namespace
            witness = validate_witness(root, binding.identity_witness_revision_id,
                                       binding.identity_witness_manifest_sha256, target, binding.prediction_id_namespace, recovery_master)
            require(timestamp(witness.manifest["summary"]["observed_at_utc"]) <= timestamp(record.prediction_generated_at), "Recovery witness after prediction")
        # Recovery only appends exact missing suffixes; NO model/state/prediction.
        added, bound = recover_prediction_append(prediction_path=output, binding_path=sidecar,
                                                  prediction_columns=PREDICTION_COLUMNS, prediction_validator=validate_prediction_records)
        return {"status": "RECOVERED", "target_date": target_date, "target_count": len(desired),
                "already_predicted_count": 0, "would_append_count": added, "source_revision": revision.revision_id,
                "bindings_recovered": bound}
    bindings = validate_complete_sidecar(repository_root=root, binding_path=sidecar)
    existing = existing_comparisons(root, bindings)
    require(set(existing.fixture_key).issubset(set(cohort.fixture_key)), "Existing comparison outside frozen cohort")
    summary = {"status": "DRY_RUN" if dry_run else "COMPLETE", "target_date": target_date,
               "target_count": len(batch), "already_predicted_count": 0, "would_append_count": 0,
               "source_revision": revision.revision_id}
    if batch.empty:
        return summary
    master_bytes = rooted(root, authority.TEAM_MASTER_PATH).read_bytes()
    require(sha(master_bytes) == authority.TEAM_MASTER_SHA, "Exact TeamMaster hash")
    master = authority.parse_master(master_bytes)
    targets = resolve_team_ids(batch, master)
    targets, witnesses = resolve_target_identity(targets, bindings, revision, root=root, master=master)
    frozen_teams = resolve_team_ids(cohort, master).set_index("fixture_key")
    for record in existing.itertuples(index=False):
        require(all(getattr(record, c) == frozen_teams.loc[record.fixture_key, c]
                    for c in ("home_team_id", "away_team_id")), "Existing comparison frozen team identity mismatch")
    validate_target_time(targets, now)  # ENTIRE date batch, never ID-available subset.
    already = targets.fixture_key.isin(existing.fixture_key)
    # A same-ID/different-fixture key is conflict, not a duplicate skip.
    id_to_fixture = dict(zip(existing.match_id, existing.fixture_key))
    require(all(id_to_fixture.get(r.match_id, r.fixture_key) == r.fixture_key
                for r in targets.itertuples(index=False)), "Existing match ID belongs to another fixture")
    summary["already_predicted_count"] = int(already.sum())
    if already.all():
        return summary  # No probabilities regenerated for existing rows.
    history = load_live_history(root, revision, completed, master, target_date=target_date)
    states = replay_live_states(*history, sorted({a.team_id for a in master.aliases}), target_date=target_date)
    a, st2 = load_model_pair(root)
    indices = [i for i in range(len(targets)) if not already.iloc[i]]
    targets = targets.iloc[indices].reset_index(drop=True)
    witnesses = [witnesses[i] for i in indices]
    generated_at = timestamp(clock())
    require(generated_at >= now, "Trusted clock moved backwards")
    records = generate_prediction_records(targets, states, a, st2, now=generated_at,
                                          source_revision=revision.revision_id, source_observed_at=revision.manifest["summary"]["observed_at_utc"])
    binding_rows = make_comparison_bindings(records, targets, witnesses)
    summary["would_append_count"] = len(records)
    if not dry_run:
        require(repository_state(root) == head, "Execution HEAD changed")
        current = read_current_revision(root)
        require(current.revision_id == revision.revision_id and current.manifest_sha == revision.manifest_sha, "Published revision changed")
        validate_target_time(targets, timestamp(clock()))
        added, skipped = append_prediction_and_bindings(append_records(records), binding_rows, prediction_path=output, binding_path=sidecar,
                                                       prediction_columns=PREDICTION_COLUMNS, prediction_validator=validate_prediction_records)
        summary["would_append_count"] = added
        summary["already_predicted_count"] += skipped
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Frozen ST2/A comparison; real dry-run/append needs separate reviewed task.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Read-only probability generation; writes nothing")
    mode.add_argument("--append", action="store_true", help="Production append with separate environment authorization")
    args = parser.parse_args(argv)
    try:
        authorization = None if args.dry_run else json.loads(os.environ.get(AUTHORIZATION_ENV, "null"))
        result = run_prediction(dry_run=args.dry_run, authorization=authorization)
    except Exception as exc:
        print(json.dumps({"status": "TECHNICAL_STOP", "error": str(exc)}))
        return 1
    print(json.dumps(result))  # Operational fields only, never probabilities/metrics.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
