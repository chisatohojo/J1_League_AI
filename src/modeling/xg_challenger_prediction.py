"""Prospective, append-only predictions for the frozen X0/X1 challenger.

This module never fits a scaler or model and never reads target outcomes.  It
selects only the nearest future calendar-date batch from the frozen 300-match
cohort, uses completed observations from earlier dates, and writes immutable
prediction records.  Model A is required only when the frozen xG branch is
unavailable; absence of a persisted Model A probability provider is a hard
failure rather than permission to refit it.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import joblib
import numpy as np
import pandas as pd

from src.collect.teams import load_team_master
from src.features.elo_history import load_elo_history_with_ongoing
from src.features.rolling_xg import (
    FEATURE_COLUMNS,
    REGULATION_SCOPE,
    build_rolling_xg_target_features,
)
from src.modeling.xg_challenger_artifact import (
    ARTIFACT_VERSION,
    CLASS_ORDER,
    OUTPUT_DIR as ARTIFACT_DIR,
    PROSPECTIVE_BOUNDARY,
    TRAINING_CUTOFF,
    X0_FEATURES,
    X1_FEATURES,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEDULE_PATH = ROOT / "data/processed/jleague/2026_27/schedule.csv"
XG_DIR = ROOT / "data/processed/jleague_match_xg"
J1_DIR = ROOT / "data/processed/jleague"
OUTPUT_PATH = ROOT / "data/processed/predictions/xg_challenger_prospective.csv"
EXPECTED_SCHEDULE_ROWS = 380
EXPECTED_PROSPECTIVE_ROWS = 300
TARGET_COMPETITION = "j1_2026_2027"
TARGET_SEASON = "2026/27"
PREDICTION_COLUMNS = (
    "match_id", "match_date", "kickoff", "home_team_id", "away_team_id",
    "home_team_name", "away_team_name", "prediction_generated_at",
    "prospective_boundary", "model_version", "artifact_hash",
    "xg_pair_available", "xg_history_count_home", "xg_history_count_away",
    "elo_diff", *FEATURE_COLUMNS,
    "x0_p_away", "x0_p_draw", "x0_p_home",
    "x1_raw_p_away", "x1_raw_p_draw", "x1_raw_p_home",
    "operational_p_away", "operational_p_draw", "operational_p_home",
    "prediction_source", "predicted_class",
)
SAFE_SCHEDULE_COLUMNS = (
    "match_id", "match_date", "kickoff_time", "home_team", "away_team",
    "fixture_key", "status",
)
ModelAPredictor = Callable[[pd.DataFrame], np.ndarray]


class XGPredictionError(ValueError):
    """A prospective identity, chronology, artifact, or append invariant failed."""


@dataclass(frozen=True)
class FrozenArtifacts:
    metadata: dict
    artifact_hash: str
    x0_scaler: object
    x0_model: object
    x1_scaler: object
    x1_model: object


@dataclass(frozen=True)
class PredictionRun:
    target_date: str
    target_count: int
    x1_eligible_count: int
    fallback_count: int
    x0_prediction_count: int
    appended_count: int
    already_predicted_count: int
    saved: bool
    records: pd.DataFrame


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_schedule_without_results(path: str | Path) -> pd.DataFrame:
    """Read only fixture identity/status columns; outcome columns are not loaded."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    missing = set(SAFE_SCHEDULE_COLUMNS) - set(header)
    if missing:
        raise XGPredictionError(f"Schedule is missing safe columns: {sorted(missing)}")
    frame = pd.read_csv(
        path, dtype=str, keep_default_na=False, encoding="utf-8-sig",
        usecols=list(SAFE_SCHEDULE_COLUMNS),
    )
    if len(frame) != EXPECTED_SCHEDULE_ROWS or frame.fixture_key.duplicated().any():
        raise XGPredictionError("Schedule must contain 380 unique fixture identities")
    return frame


def select_next_date_batch(
    schedule: pd.DataFrame, *, boundary: str = PROSPECTIVE_BOUNDARY,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return the frozen future cohort and its nearest scheduled date batch."""
    required = set(SAFE_SCHEDULE_COLUMNS)
    if not isinstance(schedule, pd.DataFrame) or schedule.columns.has_duplicates:
        raise XGPredictionError("schedule must be a DataFrame with unique columns")
    if required - set(schedule.columns):
        raise XGPredictionError("Schedule identity/status schema is incomplete")
    if not schedule.status.isin(["completed", "scheduled", "candidate"]).all():
        raise XGPredictionError("Unknown schedule status")
    dates = pd.to_datetime(schedule.match_date, format="%Y-%m-%d", errors="raise")
    boundary_day = pd.Timestamp(boundary).tz_convert("Asia/Tokyo").tz_localize(None).normalize()
    # Cohort membership is frozen by the boundary, while target selection uses
    # current status.  Completed prospective rows stay in the 300-row manifest
    # universe but can never be selected again.
    cohort = schedule.loc[dates.ge(boundary_day)].copy(deep=True)
    cohort = cohort.sort_values(["match_date", "fixture_key"], kind="stable").reset_index(drop=True)
    remaining = cohort.loc[cohort.status.ne("completed")]
    if remaining.empty:
        raise XGPredictionError("No unplayed prospective fixtures remain")
    target_date = remaining.match_date.min()
    batch = remaining.loc[remaining.match_date.eq(target_date)].copy(deep=True).reset_index(drop=True)
    return cohort, batch


def _require_official_target_ids(batch: pd.DataFrame) -> None:
    ids = batch.match_id.astype(str)
    if ids.str.strip().eq("").any():
        raise XGPredictionError(
            "Official match_id is unavailable for the next-date batch; fixture_key is not a substitute"
        )
    if ids.duplicated().any():
        raise XGPredictionError("Duplicate official match_id in next-date batch")


def validate_artifacts(path: str | Path = ARTIFACT_DIR) -> FrozenArtifacts:
    """Validate all serialized hashes and the frozen prediction contract."""
    root = Path(path)
    required = {
        "metadata.json", "checksums.sha256", "feature_schema.json",
        "x0_scaler.joblib", "x0_model.joblib", "x1_scaler.joblib", "x1_model.joblib",
    }
    if not root.is_dir() or any(not (root / name).is_file() for name in required):
        raise XGPredictionError(f"Incomplete X0/X1 artifact directory: {root}")
    checksums = {}
    for line in (root / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        checksums[name.strip()] = digest
    for name, expected in checksums.items():
        file_path = root / name
        if not file_path.is_file() or _sha256(file_path) != expected:
            raise XGPredictionError(f"Artifact checksum mismatch: {name}")
    metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    if (
        metadata.get("artifact_version") != ARTIFACT_VERSION
        or metadata.get("training_cutoff") != TRAINING_CUTOFF
        or metadata.get("prospective_boundary") != PROSPECTIVE_BOUNDARY
        or tuple(metadata.get("x0_feature_list", ())) != X0_FEATURES
        or tuple(metadata.get("x1_feature_list", ())) != X1_FEATURES
        or tuple(int(key) for key in metadata.get("target_mapping", {})) != CLASS_ORDER
        or metadata.get("future_rows_used") != 0
    ):
        raise XGPredictionError("Artifact metadata does not match the frozen prediction contract")
    pairs = {}
    for branch in ("x0", "x1"):
        scaler = joblib.load(root / f"{branch}_scaler.joblib")
        model = joblib.load(root / f"{branch}_model.joblib")
        features = X0_FEATURES if branch == "x0" else X1_FEATURES
        if scaler.n_features_in_ != len(features) or model.n_features_in_ != len(features):
            raise XGPredictionError(f"{branch} feature width mismatch")
        if tuple(int(value) for value in model.classes_) != CLASS_ORDER:
            raise XGPredictionError(f"{branch} class order mismatch")
        pairs[branch] = (scaler, model)
    return FrozenArtifacts(
        metadata=metadata,
        artifact_hash=_sha256(root / "checksums.sha256"),
        x0_scaler=pairs["x0"][0], x0_model=pairs["x0"][1],
        x1_scaler=pairs["x1"][0], x1_model=pairs["x1"][1],
    )


def _load_completed_xg(xg_dir: str | Path = XG_DIR) -> pd.DataFrame:
    root = Path(xg_dir)
    specs = (
        ("j1_2025", "2025", "2025_j1_match_xg.csv"),
        ("j1_hyakunen_2026", "2026", "2026_hyakunen_j1_match_xg.csv"),
        (TARGET_COMPETITION, TARGET_SEASON, "2026_27_j1_match_xg.csv"),
    )
    frames = []
    for competition, season, name in specs:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(path)
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if "competition" not in frame:
            frame.insert(0, "competition", competition)
        if "xg_time_scope" not in frame:
            frame["xg_time_scope"] = REGULATION_SCOPE
        if not frame.competition.eq(competition).all() or not frame.season.eq(season).all():
            raise XGPredictionError(f"xG partition identity mismatch: {name}")
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if combined.match_id.astype(str).duplicated().any():
        raise XGPredictionError("Duplicate completed xG match_id")
    unresolved = combined.loc[combined.xg_time_scope.ne(REGULATION_SCOPE), "match_id"].tolist()
    if unresolved != ["33017"]:
        raise XGPredictionError(f"Unexpected unresolved xG scope: {unresolved}")
    return combined


def _resolve_targets(batch: pd.DataFrame) -> pd.DataFrame:
    master = load_team_master()
    rows = []
    for row in batch.itertuples(index=False):
        rows.append({
            "competition": TARGET_COMPETITION, "season": TARGET_SEASON,
            "match_id": row.match_id, "match_date": row.match_date,
            "kickoff": row.kickoff_time,
            "home_team_name": row.home_team, "away_team_name": row.away_team,
            "home_team_id": master.resolve_team_id(
                row.home_team, source="jleague_data_site", on=row.match_date,
            ),
            "away_team_id": master.resolve_team_id(
                row.away_team, source="jleague_data_site", on=row.match_date,
            ),
        })
    return pd.DataFrame(rows)


def _elo_features(targets: pd.DataFrame, processed_dir: str | Path = J1_DIR) -> pd.DataFrame:
    history = load_elo_history_with_ongoing(processed_dir)
    ratings = history.ongoing.final_ratings
    return pd.DataFrame({
        "match_id": targets.match_id,
        "elo_diff": [ratings[h] - ratings[a] for h, a in zip(
            targets.home_team_id, targets.away_team_id,
        )],
    })


def _predict_pair(scaler, model, frame: pd.DataFrame, features: tuple[str, ...]) -> np.ndarray:
    values = frame.loc[:, list(features)].to_numpy(dtype=float, copy=True)
    probabilities = model.predict_proba(scaler.transform(values))
    if probabilities.shape != (len(frame), 3) or not np.isfinite(probabilities).all():
        raise XGPredictionError("Invalid probability matrix")
    if (probabilities < 0).any() or not np.allclose(probabilities.sum(axis=1), 1.0):
        raise XGPredictionError("Probabilities must be nonnegative and sum to one")
    return probabilities


def generate_prediction_records(
    targets: pd.DataFrame,
    xg_features: pd.DataFrame,
    elo_features: pd.DataFrame,
    artifacts: FrozenArtifacts,
    *,
    model_a_predictor: ModelAPredictor | None = None,
    generated_at: str | None = None,
) -> pd.DataFrame:
    """Generate frozen probabilities; no fitting or outcome columns are accepted."""
    forbidden = {"result", "actual_class", "home_score", "away_score"}
    if forbidden & set(targets.columns):
        raise XGPredictionError("Target outcomes must be isolated from prediction")
    merged = targets.merge(xg_features, on=[
        "competition", "season", "match_id", "match_date", "home_team_id", "away_team_id",
    ], how="left", validate="one_to_one").merge(
        elo_features, on="match_id", how="left", validate="one_to_one",
    )
    if merged.elo_diff.isna().any() or merged.xg_pair_available.isna().any():
        raise XGPredictionError("Feature linkage is incomplete")
    eligible = merged.xg_pair_available.astype(bool)
    x0 = np.full((len(merged), 3), np.nan)
    x1 = np.full((len(merged), 3), np.nan)
    operational = np.full((len(merged), 3), np.nan)
    if eligible.any():
        selected = merged.loc[eligible]
        x0[eligible] = _predict_pair(artifacts.x0_scaler, artifacts.x0_model, selected, X0_FEATURES)
        x1[eligible] = _predict_pair(artifacts.x1_scaler, artifacts.x1_model, selected, X1_FEATURES)
        operational[eligible] = x1[eligible]
    if (~eligible).any():
        if model_a_predictor is None:
            raise XGPredictionError(
                "Frozen Model A artifact/provider is required for unavailable-xG fallback; refit is prohibited"
            )
        fallback = np.asarray(model_a_predictor(merged.loc[~eligible, ["elo_diff"]].copy()), dtype=float)
        if fallback.shape != ((~eligible).sum(), 3) or not np.allclose(fallback.sum(axis=1), 1.0):
            raise XGPredictionError("Invalid frozen Model A fallback probabilities")
        if not np.isfinite(fallback).all() or (fallback < 0).any():
            raise XGPredictionError("Invalid frozen Model A fallback probabilities")
        operational[~eligible] = fallback
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    records = pd.DataFrame({
        "match_id": merged.match_id, "match_date": merged.match_date,
        "kickoff": merged.kickoff, "home_team_id": merged.home_team_id,
        "away_team_id": merged.away_team_id,
        "home_team_name": merged.home_team_name, "away_team_name": merged.away_team_name,
        "prediction_generated_at": timestamp,
        "prospective_boundary": PROSPECTIVE_BOUNDARY,
        "model_version": ARTIFACT_VERSION,
        "artifact_hash": artifacts.artifact_hash,
        "xg_pair_available": eligible,
        "xg_history_count_home": merged.home_xg_history_count.astype(int),
        "xg_history_count_away": merged.away_xg_history_count.astype(int),
        "elo_diff": merged.elo_diff.astype(float),
    })
    for column in FEATURE_COLUMNS:
        records[column] = merged[column]
    for prefix, values in (("x0", x0), ("x1_raw", x1), ("operational", operational)):
        for index, label in enumerate(("away", "draw", "home")):
            records[f"{prefix}_p_{label}"] = values[:, index]
    records["prediction_source"] = np.where(eligible, "X1", "MODEL_A_FALLBACK")
    records["predicted_class"] = np.argmax(operational, axis=1).astype(int)
    return records.loc[:, list(PREDICTION_COLUMNS)]


def append_predictions(records: pd.DataFrame, path: str | Path = OUTPUT_PATH) -> tuple[int, int]:
    """Append new `(match_id, model_version)` rows and never overwrite history."""
    output = Path(path)
    if tuple(records.columns) != PREDICTION_COLUMNS:
        raise XGPredictionError("Prediction output schema mismatch")
    if records.duplicated(["match_id", "model_version"]).any():
        raise XGPredictionError("Duplicate prediction key in generated records")
    existing = pd.DataFrame(columns=PREDICTION_COLUMNS)
    if output.is_file():
        existing = pd.read_csv(output, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if tuple(existing.columns) != PREDICTION_COLUMNS:
            raise XGPredictionError("Existing prediction output schema mismatch")
        if existing.duplicated(["match_id", "model_version"]).any():
            raise XGPredictionError("Existing prediction output contains duplicate keys")
    keys = set(zip(existing.match_id, existing.model_version))
    duplicate = records.apply(lambda row: (str(row.match_id), row.model_version) in keys, axis=1)
    new = records.loc[~duplicate]
    if not new.empty:
        output.parent.mkdir(parents=True, exist_ok=True)
        new.to_csv(output, mode="a" if output.exists() else "x", header=not output.exists(), index=False)
    return len(new), int(duplicate.sum())


def persist_predictions(
    records: pd.DataFrame, *, dry_run: bool, path: str | Path = OUTPUT_PATH,
) -> tuple[int, int]:
    """Keep dry-run and production on one explicit write boundary."""
    if dry_run:
        return 0, 0
    return append_predictions(records, path)


def run_prediction(
    *, dry_run: bool = False, schedule_path: str | Path = SCHEDULE_PATH,
    output_path: str | Path = OUTPUT_PATH, artifact_dir: str | Path = ARTIFACT_DIR,
    model_a_predictor: ModelAPredictor | None = None,
) -> PredictionRun:
    schedule = _read_schedule_without_results(schedule_path)
    cohort, batch = select_next_date_batch(schedule)
    if len(cohort) != EXPECTED_PROSPECTIVE_ROWS:
        raise XGPredictionError(
            f"Frozen prospective cohort must contain {EXPECTED_PROSPECTIVE_ROWS} rows, got {len(cohort)}"
        )
    _require_official_target_ids(batch)
    targets = _resolve_targets(batch)
    artifacts = validate_artifacts(artifact_dir)
    completed_xg = _load_completed_xg()
    xg_features = build_rolling_xg_target_features(
        completed_xg,
        targets[["competition", "season", "match_id", "match_date", "home_team_id", "away_team_id"]],
    )
    elo_features = _elo_features(targets)
    records = generate_prediction_records(
        targets, xg_features, elo_features, artifacts,
        model_a_predictor=model_a_predictor,
    )
    appended, duplicates = persist_predictions(
        records, dry_run=dry_run, path=output_path,
    )
    eligible = int(records.xg_pair_available.sum())
    return PredictionRun(
        target_date=str(batch.match_date.iloc[0]), target_count=len(batch),
        x1_eligible_count=eligible, fallback_count=len(batch) - eligible,
        x0_prediction_count=eligible, appended_count=appended,
        already_predicted_count=duplicates, saved=bool(appended), records=records,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run = run_prediction(dry_run=args.dry_run)
    status = (
        "DRY_RUN" if args.dry_run else
        "ALREADY_PREDICTED" if run.already_predicted_count == run.target_count else
        "SAVED"
    )
    print(json.dumps({
        "status": status,
        "target_date": run.target_date, "target_count": run.target_count,
        "x1_eligible_count": run.x1_eligible_count,
        "fallback_count": run.fallback_count,
        "x0_prediction_count": run.x0_prediction_count,
        "appended_count": run.appended_count,
        "already_predicted_count": run.already_predicted_count,
        "saved": run.saved, "dry_run": args.dry_run,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
