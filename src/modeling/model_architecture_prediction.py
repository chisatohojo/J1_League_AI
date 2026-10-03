"""Append-only prospective predictions from frozen architecture artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from src.collect.teams import TeamMaster, load_team_master
from src.features.elo_history import (
    ADDED_COLUMNS,
    build_elo_history_with_ongoing,
    load_elo_history_with_ongoing,
)
from src.features.form import FORM_COLUMNS, add_form_features_to_targets
from src.modeling.architecture_lightgbm import (
    FEATURE_COLUMNS as LIGHTGBM_FEATURE_COLUMNS,
    predict_proba as predict_lightgbm_proba,
    validate_lightgbm_features,
)
from src.modeling.architecture_lightgbm_artifact import (
    EXPECTED_ROWS as LIGHTGBM_TRAINING_ROWS,
    MODEL_VERSION as LIGHTGBM_MODEL_VERSION,
    OUTPUT_DIR as LIGHTGBM_ARTIFACT_DIR,
    TRAINING_CUTOFF as LIGHTGBM_TRAINING_CUTOFF,
    LoadedLightGBMArtifact,
    load_lightgbm_artifact,
)
from src.modeling.architecture_poisson import CLASS_ORDER, predict_proba as predict_poisson_proba
from src.modeling.architecture_poisson_artifact import (
    EXPECTED_ROWS as POISSON_TRAINING_ROWS,
    MODEL_VERSION as POISSON_MODEL_VERSION,
    OUTPUT_DIR as POISSON_ARTIFACT_DIR,
    TRAINING_CUTOFF as POISSON_TRAINING_CUTOFF,
    LoadedPoissonArtifact,
    load_poisson_artifact,
)


ROOT = Path(__file__).resolve().parents[2]
SCHEDULE_PATH = ROOT / "data/processed/jleague/2026_27/schedule.csv"
J1_DIR = ROOT / "data/processed/jleague"
OUTPUT_PATH = ROOT / "data/processed/predictions/model_architecture_prospective.csv"
PROSPECTIVE_BOUNDARY = "2026-09-22T07:16:21+09:00"
EXPECTED_PROSPECTIVE_ROWS = 300
EXPECTED_SCHEDULE_ROWS = 380
POISSON_ARTIFACT_HASH = "655b5e46678c8ccce81b45b63833da5888fab94b4f5e267257c7496877b356f0"
LIGHTGBM_ARTIFACT_HASH = "767ae8bce062386079118994182d067f782ad98576e3351890edf7586cecc516"
# Backward-compatible Candidate P constant names.
MODEL_VERSION = POISSON_MODEL_VERSION
TRAINING_CUTOFF = POISSON_TRAINING_CUTOFF
ARTIFACT_DIR = POISSON_ARTIFACT_DIR
ARTIFACT_TRAINING_ROWS = POISSON_TRAINING_ROWS
EXPECTED_ARTIFACT_HASH = POISSON_ARTIFACT_HASH
SAFE_SCHEDULE_COLUMNS = (
    "match_id",
    "match_date",
    "kickoff_time",
    "home_team",
    "away_team",
    "fixture_key",
    "status",
)
TARGET_COLUMNS = (
    "match_id",
    "match_date",
    "kickoff",
    "home_team_id",
    "away_team_id",
    "elo_diff",
)
LIGHTGBM_TARGET_COLUMNS = (
    "match_id",
    "match_date",
    "kickoff",
    "home_team_id",
    "away_team_id",
    *LIGHTGBM_FEATURE_COLUMNS,
)
PREDICTION_COLUMNS = (
    "match_id",
    "match_date",
    "kickoff",
    "home_team_id",
    "away_team_id",
    "prediction_generated_at",
    "prospective_boundary",
    "model_version",
    "training_cutoff",
    "history_cutoff_exclusive",
    "artifact_hash",
    "p_away",
    "p_draw",
    "p_home",
    "predicted_class",
)


class ArchitecturePredictionError(ValueError):
    """A prospective identity, chronology, artifact, or append invariant failed."""


@dataclass(frozen=True)
class CandidateContract:
    selector: str
    model_version: str
    artifact_hash: str
    training_cutoff: str
    training_rows: int
    artifact_dir: Path


CANDIDATES = {
    "poisson": CandidateContract(
        "poisson",
        POISSON_MODEL_VERSION,
        POISSON_ARTIFACT_HASH,
        POISSON_TRAINING_CUTOFF,
        POISSON_TRAINING_ROWS,
        POISSON_ARTIFACT_DIR,
    ),
    "lightgbm": CandidateContract(
        "lightgbm",
        LIGHTGBM_MODEL_VERSION,
        LIGHTGBM_ARTIFACT_HASH,
        LIGHTGBM_TRAINING_CUTOFF,
        LIGHTGBM_TRAINING_ROWS,
        LIGHTGBM_ARTIFACT_DIR,
    ),
}


@dataclass(frozen=True)
class PredictionRun:
    status: str
    target_date: str
    target_count: int
    model_version: str
    appended_count: int
    already_predicted_count: int
    saved: bool
    dry_run: bool
    records: pd.DataFrame


def _candidate(selector: str) -> CandidateContract:
    try:
        return CANDIDATES[selector]
    except KeyError as exc:
        raise ArchitecturePredictionError(
            f"Unknown architecture candidate {selector!r}; expected poisson or lightgbm"
        ) from exc


def read_schedule_without_results(path: str | Path = SCHEDULE_PATH) -> pd.DataFrame:
    """Read only safe schedule identity/status fields, never outcomes."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    try:
        with source.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle, strict=True), [])
    except csv.Error as exc:
        raise ArchitecturePredictionError("Malformed schedule CSV") from exc
    if len(header) != len(set(header)):
        raise ArchitecturePredictionError("Schedule contains duplicate columns")
    missing = set(SAFE_SCHEDULE_COLUMNS) - set(header)
    if missing:
        raise ArchitecturePredictionError(f"Schedule is missing safe columns: {sorted(missing)}")
    frame = pd.read_csv(
        source,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
        usecols=list(SAFE_SCHEDULE_COLUMNS),
    )
    if len(frame) != EXPECTED_SCHEDULE_ROWS or frame["fixture_key"].duplicated().any():
        raise ArchitecturePredictionError("Schedule must contain 380 unique fixture identities")
    return frame.loc[:, list(SAFE_SCHEDULE_COLUMNS)]


def select_next_date_batch(
    schedule: pd.DataFrame,
    *,
    boundary: str = PROSPECTIVE_BOUNDARY,
    expected_cohort_rows: int = EXPECTED_PROSPECTIVE_ROWS,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Freeze cohort membership, then select the nearest unfinished date batch."""
    if not isinstance(schedule, pd.DataFrame) or schedule.columns.has_duplicates:
        raise ArchitecturePredictionError("schedule must be a DataFrame with unique columns")
    if set(SAFE_SCHEDULE_COLUMNS) - set(schedule.columns):
        raise ArchitecturePredictionError("Schedule identity/status schema is incomplete")
    if not schedule["status"].isin(["completed", "scheduled", "candidate"]).all():
        raise ArchitecturePredictionError("Unknown schedule status")
    try:
        dates = pd.to_datetime(schedule["match_date"], format="%Y-%m-%d", errors="raise")
        boundary_day = pd.Timestamp(boundary).tz_convert("Asia/Tokyo").tz_localize(None).normalize()
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError("Invalid schedule date or prospective boundary") from exc
    cohort = schedule.loc[dates.ge(boundary_day)].copy(deep=True)
    cohort = cohort.sort_values(["match_date", "fixture_key"], kind="stable").reset_index(drop=True)
    if len(cohort) != expected_cohort_rows:
        raise ArchitecturePredictionError(
            f"Frozen prospective cohort must contain {expected_cohort_rows} rows, got {len(cohort)}"
        )
    remaining = cohort.loc[cohort["status"].ne("completed")]
    if remaining.empty:
        raise ArchitecturePredictionError("No unplayed prospective fixtures remain")
    target_date = remaining["match_date"].min()
    batch = remaining.loc[remaining["match_date"].eq(target_date)].copy(deep=True)
    batch = batch.sort_values(["match_date", "fixture_key"], kind="stable").reset_index(drop=True)
    return cohort, batch


def require_official_target_ids(batch: pd.DataFrame) -> None:
    ids = batch["match_id"].astype(str)
    if ids.str.strip().eq("").any():
        raise ArchitecturePredictionError(
            "Official match_id is unavailable; fixture_key is never a substitute"
        )
    if ids.duplicated().any():
        raise ArchitecturePredictionError("Duplicate official match_id in target batch")


def resolve_targets(batch: pd.DataFrame, *, team_master: TeamMaster | None = None) -> pd.DataFrame:
    """Resolve the selected batch through exact source/date-aware TeamMaster aliases."""
    require_official_target_ids(batch)
    master = load_team_master() if team_master is None else team_master
    rows = []
    for row in batch.itertuples(index=False):
        home_id = master.resolve_team_id(
            row.home_team, source="jleague_data_site", on=row.match_date
        )
        away_id = master.resolve_team_id(
            row.away_team, source="jleague_data_site", on=row.match_date
        )
        if home_id == away_id:
            raise ArchitecturePredictionError("Target home and away TeamMaster IDs must differ")
        rows.append(
            {
                "match_id": row.match_id,
                "match_date": row.match_date,
                "kickoff": row.kickoff_time,
                "home_team_id": home_id,
                "away_team_id": away_id,
            }
        )
    targets = pd.DataFrame(rows, columns=TARGET_COLUMNS[:-1])
    if targets["match_id"].duplicated().any():
        raise ArchitecturePredictionError("Duplicate official match_id after target resolution")
    return targets


def _without_elo_columns(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(columns=[column for column in ADDED_COLUMNS if column in frame.columns]).copy(deep=True)


def _strictly_prior_history(
    targets: pd.DataFrame,
    *,
    processed_dir: str | Path,
    team_master: TeamMaster,
) -> tuple[pd.Timestamp, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if tuple(targets.columns) != TARGET_COLUMNS[:-1] or targets.empty:
        raise ArchitecturePredictionError("Target identity frame schema mismatch")
    if targets["match_date"].nunique() != 1:
        raise ArchitecturePredictionError("Targets must be one calendar-date batch")
    try:
        target_date = pd.to_datetime(targets["match_date"].iloc[0], format="%Y-%m-%d", errors="raise")
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError("Invalid target match_date") from exc
    verified = load_elo_history_with_ongoing(processed_dir, team_master=team_master)
    ordinary = verified.historical.matches.copy(deep=True)
    hyakunen = verified.hyakunen.matches.copy(deep=True)
    ongoing = verified.ongoing.matches.copy(deep=True)
    try:
        ongoing_dates = pd.to_datetime(ongoing["match_date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError("Malformed ongoing history match_date") from exc
    strictly_prior = ongoing.loc[ongoing_dates.lt(target_date)].copy(deep=True)
    return target_date, ordinary, hyakunen, strictly_prior


def _attach_elo_from_history(
    targets: pd.DataFrame,
    target_date: pd.Timestamp,
    ordinary: pd.DataFrame,
    hyakunen: pd.DataFrame,
    strictly_prior: pd.DataFrame,
    *,
    team_master: TeamMaster,
) -> pd.DataFrame:
    replayed = build_elo_history_with_ongoing(
        _without_elo_columns(ordinary),
        _without_elo_columns(hyakunen),
        _without_elo_columns(strictly_prior),
        team_master=team_master,
        observed_at=f"{target_date.strftime('%Y-%m-%d')}T00:00:00+09:00",
    )
    ratings = replayed.ongoing.final_ratings
    try:
        differences = np.asarray(
            [ratings[home] - ratings[away] for home, away in zip(
                targets["home_team_id"], targets["away_team_id"]
            )],
            dtype=float,
        )
    except KeyError as exc:
        raise ArchitecturePredictionError("Target TeamMaster ID is absent from Elo state") from exc
    if not np.isfinite(differences).all():
        raise ArchitecturePredictionError("Target elo_diff must be finite")
    result = targets.copy(deep=True)
    result["elo_diff"] = differences
    return result.loc[:, list(TARGET_COLUMNS)]


def add_strictly_prior_elo(
    targets: pd.DataFrame,
    *,
    processed_dir: str | Path = J1_DIR,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Attach Elo from the verified chain using only dates before the target date."""
    master = load_team_master() if team_master is None else team_master
    target_date, ordinary, hyakunen, strictly_prior = _strictly_prior_history(
        targets, processed_dir=processed_dir, team_master=master
    )
    return _attach_elo_from_history(
        targets,
        target_date,
        ordinary,
        hyakunen,
        strictly_prior,
        team_master=master,
    )


def _canonical_form_history(
    ordinary: pd.DataFrame,
    hyakunen: pd.DataFrame,
    strictly_prior: pd.DataFrame,
    *,
    target_date: pd.Timestamp,
    team_master: TeamMaster,
) -> pd.DataFrame:
    required = (
        "match_id",
        "match_date",
        "home_team_id",
        "away_team_id",
        "home_score",
        "away_score",
        "result",
    )
    segments = (ordinary, hyakunen, strictly_prior)
    if any(not isinstance(frame, pd.DataFrame) or frame.columns.has_duplicates for frame in segments):
        raise ArchitecturePredictionError("Verified history segments must have unique columns")
    if any(set(required) - set(frame.columns) for frame in segments):
        raise ArchitecturePredictionError("Verified history segment schema mismatch")
    history = pd.concat(
        [frame.loc[:, list(required)] for frame in segments], ignore_index=True
    )
    if history["match_id"].isna().any() or history["match_id"].astype(str).str.strip().eq("").any():
        raise ArchitecturePredictionError("History match_id must be nonblank")
    if history["match_id"].duplicated().any():
        raise ArchitecturePredictionError("Duplicate match_id across Candidate G history")
    try:
        dates = pd.to_datetime(history["match_date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError("Malformed Candidate G history match_date") from exc
    if dates.isna().any() or dates.ge(target_date).any():
        raise ArchitecturePredictionError("Candidate G history must be strictly before target date")
    history = history.assign(_date=dates).sort_values(
        ["_date", "match_id"], kind="stable"
    ).drop(columns="_date").reset_index(drop=True)
    master_ids = {alias.team_id for alias in team_master.aliases}
    observed = set(history["home_team_id"]) | set(history["away_team_id"])
    if not observed.issubset(master_ids):
        raise ArchitecturePredictionError("Candidate G history contains an unknown TeamMaster ID")
    return history


def add_strictly_prior_lightgbm_state(
    targets: pd.DataFrame,
    *,
    processed_dir: str | Path = J1_DIR,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Attach the exact frozen Candidate G state from strictly-prior history."""
    master = load_team_master() if team_master is None else team_master
    target_date, ordinary, hyakunen, strictly_prior = _strictly_prior_history(
        targets, processed_dir=processed_dir, team_master=master
    )
    with_elo = _attach_elo_from_history(
        targets,
        target_date,
        ordinary,
        hyakunen,
        strictly_prior,
        team_master=master,
    )
    history = _canonical_form_history(
        ordinary,
        hyakunen,
        strictly_prior,
        target_date=target_date,
        team_master=master,
    )
    try:
        with_form = add_form_features_to_targets(
            history,
            targets.loc[:, ["match_id", "match_date", "home_team_id", "away_team_id"]],
        )
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError(f"Candidate G form state construction failed: {exc}") from exc
    for side in ("home", "away"):
        with_form[f"{side}_last5_matches_available"] = sum(
            with_form[f"{side}_last5_{outcome}"] for outcome in ("wins", "draws", "losses")
        )
    result = targets.copy(deep=True)
    result["elo_diff"] = with_elo["elo_diff"].to_numpy(copy=True)
    for column in LIGHTGBM_FEATURE_COLUMNS[1:]:
        result[column] = with_form[column].to_numpy(copy=True)
    try:
        validate_lightgbm_features(result)
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError(f"Candidate G feature validation failed: {exc}") from exc
    if set(FORM_COLUMNS) & set(LIGHTGBM_FEATURE_COLUMNS):
        allowed = {
            "home_last5_points",
            "away_last5_points",
            "home_last5_goals_for",
            "away_last5_goals_for",
            "home_last5_goals_against",
            "away_last5_goals_against",
        }
        if (set(FORM_COLUMNS) & set(LIGHTGBM_FEATURE_COLUMNS)) != allowed:
            raise ArchitecturePredictionError("Candidate G feature vector contains forbidden form fields")
    return result.loc[:, list(LIGHTGBM_TARGET_COLUMNS)]


def load_frozen_artifact(
    path: str | Path | None = None,
    *,
    model: str = "poisson",
) -> LoadedPoissonArtifact | LoadedLightGBMArtifact:
    """Load one selected candidate only through its full artifact validator."""
    contract = _candidate(model)
    source = contract.artifact_dir if path is None else Path(path)
    try:
        loaded = (
            load_poisson_artifact(source)
            if model == "poisson"
            else load_lightgbm_artifact(source)
        )
    except Exception as exc:
        raise ArchitecturePredictionError(
            f"Candidate {model} artifact validation failed: {exc}"
        ) from exc
    metadata = loaded.metadata
    if (
        metadata.get("model_version") != contract.model_version
        or metadata.get("training_cutoff") != contract.training_cutoff
        or metadata.get("training_row_count") != contract.training_rows
        or loaded.artifact_hash != contract.artifact_hash
    ):
        raise ArchitecturePredictionError(
            f"Candidate {model} artifact does not match the frozen prospective contract"
        )
    return loaded


def _generation_timestamp(value: str | datetime | None) -> pd.Timestamp:
    timestamp = pd.Timestamp(datetime.now(timezone.utc) if value is None else value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ArchitecturePredictionError("prediction_generated_at must be timezone-aware")
    return timestamp


def validate_pre_kickoff(targets: pd.DataFrame, generated_at: str | datetime | None = None) -> str:
    """Require a timezone-aware generation instant strictly before every JST kickoff."""
    generated = _generation_timestamp(generated_at)
    jst = ZoneInfo("Asia/Tokyo")
    for row in targets.itertuples(index=False):
        if re.fullmatch(r"[0-9]{2}:[0-9]{2}", str(row.kickoff)) is None:
            raise ArchitecturePredictionError("Kickoff chronology cannot be proven safely")
        try:
            kickoff = datetime.strptime(
                f"{row.match_date} {row.kickoff}", "%Y-%m-%d %H:%M"
            ).replace(tzinfo=jst)
        except (TypeError, ValueError) as exc:
            raise ArchitecturePredictionError("Kickoff chronology cannot be proven safely") from exc
        if generated.tz_convert("Asia/Tokyo") >= pd.Timestamp(kickoff):
            raise ArchitecturePredictionError("Prediction generation must be strictly before kickoff")
    return generated.isoformat()


def _validate_probabilities(records: pd.DataFrame) -> None:
    columns = ["p_away", "p_draw", "p_home"]
    try:
        probabilities = records.loc[:, columns].to_numpy(dtype=float)
        predicted = pd.to_numeric(records["predicted_class"], errors="raise").to_numpy(dtype=int)
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError("Prediction probability values are malformed") from exc
    if (
        probabilities.shape != (len(records), 3)
        or not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or (probabilities > 1).any()
        or not np.allclose(probabilities.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)
    ):
        raise ArchitecturePredictionError("Probabilities must be finite, bounded, and sum to one")
    expected = np.asarray(CLASS_ORDER, dtype=int)[probabilities.argmax(axis=1)]
    if not np.array_equal(predicted, expected):
        raise ArchitecturePredictionError("predicted_class must use plain Away/Draw/Home argmax")


def generate_prediction_records(
    targets: pd.DataFrame,
    artifact: LoadedPoissonArtifact | LoadedLightGBMArtifact,
    *,
    model: str = "poisson",
    generated_at: str | datetime | None = None,
) -> pd.DataFrame:
    """Generate one candidate's records without exposing internal model state."""
    contract = _candidate(model)
    expected_columns = TARGET_COLUMNS if model == "poisson" else LIGHTGBM_TARGET_COLUMNS
    if tuple(targets.columns) != expected_columns:
        raise ArchitecturePredictionError(f"Candidate {model} target feature schema mismatch")
    if {"result", "home_score", "away_score", "actual_class"} & set(targets.columns):
        raise ArchitecturePredictionError("Target outcomes must not enter prospective prediction")
    metadata = artifact.metadata
    if (
        metadata.get("model_version") != contract.model_version
        or metadata.get("training_cutoff") != contract.training_cutoff
        or metadata.get("training_row_count") != contract.training_rows
        or artifact.artifact_hash != contract.artifact_hash
    ):
        raise ArchitecturePredictionError(f"Candidate {model} artifact provenance mismatch")
    timestamp = validate_pre_kickoff(targets, generated_at)
    try:
        if model == "poisson":
            predicted = predict_poisson_proba(
                artifact.model,
                targets.loc[:, [
                    "match_id", "match_date", "home_team_id", "away_team_id", "elo_diff"
                ]],
            )
        else:
            predicted = predict_lightgbm_proba(
                artifact.model,
                targets.loc[:, ["match_id", *LIGHTGBM_FEATURE_COLUMNS]],
            )
    except Exception as exc:
        raise ArchitecturePredictionError(
            f"Candidate {model} probability generation failed: {exc}"
        ) from exc
    if not predicted["match_id"].astype(str).equals(targets["match_id"].astype(str)):
        raise ArchitecturePredictionError(f"Candidate {model} prediction identity/order mismatch")
    target_date = targets["match_date"].iloc[0]
    records = pd.DataFrame(
        {
            "match_id": targets["match_id"].to_numpy(copy=True),
            "match_date": targets["match_date"].to_numpy(copy=True),
            "kickoff": targets["kickoff"].to_numpy(copy=True),
            "home_team_id": targets["home_team_id"].to_numpy(copy=True),
            "away_team_id": targets["away_team_id"].to_numpy(copy=True),
            "prediction_generated_at": timestamp,
            "prospective_boundary": PROSPECTIVE_BOUNDARY,
            "model_version": contract.model_version,
            "training_cutoff": contract.training_cutoff,
            "history_cutoff_exclusive": target_date,
            "artifact_hash": artifact.artifact_hash,
            "p_away": predicted["p_away"].to_numpy(),
            "p_draw": predicted["p_draw"].to_numpy(),
            "p_home": predicted["p_home"].to_numpy(),
            "predicted_class": predicted["predicted_class"].to_numpy(),
        }
    ).loc[:, list(PREDICTION_COLUMNS)]
    _validate_prediction_frame(records, require_frozen_model=True)
    return records


def _validate_prediction_frame(records: pd.DataFrame, *, require_frozen_model: bool) -> None:
    if not isinstance(records, pd.DataFrame) or tuple(records.columns) != PREDICTION_COLUMNS:
        raise ArchitecturePredictionError("Prediction output schema mismatch")
    if records.duplicated(["match_id", "model_version"]).any():
        raise ArchitecturePredictionError("Duplicate prediction key")
    for column in ("match_id", "model_version", "artifact_hash"):
        if records[column].isna().any() or records[column].astype(str).str.strip().eq("").any():
            raise ArchitecturePredictionError(f"Prediction output has blank {column}")
    try:
        dates = pd.to_datetime(records["match_date"], format="%Y-%m-%d", errors="raise")
        cutoffs = pd.to_datetime(
            records["history_cutoff_exclusive"], format="%Y-%m-%d", errors="raise"
        )
        generated = pd.to_datetime(records["prediction_generated_at"], errors="raise", utc=True)
    except (TypeError, ValueError) as exc:
        raise ArchitecturePredictionError("Prediction chronology fields are malformed") from exc
    if generated.isna().any() or not dates.equals(cutoffs):
        raise ArchitecturePredictionError("Prediction history cutoff must equal target match_date")
    contracts_by_version = {value.model_version: value for value in CANDIDATES.values()}
    for row in records.itertuples(index=False):
        contract = contracts_by_version.get(row.model_version)
        if require_frozen_model and contract is None:
            raise ArchitecturePredictionError("Generated candidate provenance mismatch")
        if contract is not None and (
            row.training_cutoff != contract.training_cutoff
            or row.prospective_boundary != PROSPECTIVE_BOUNDARY
            or row.artifact_hash != contract.artifact_hash
        ):
            raise ArchitecturePredictionError("Frozen candidate provenance mismatch")
    _validate_probabilities(records)


def _read_existing(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=PREDICTION_COLUMNS)
    if not path.is_file():
        raise ArchitecturePredictionError("Prediction output path is not a file")
    try:
        existing = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise ArchitecturePredictionError("Malformed existing prediction CSV") from exc
    _validate_prediction_frame(existing, require_frozen_model=False)
    return existing


def persist_predictions(
    records: pd.DataFrame,
    *,
    dry_run: bool,
    path: str | Path = OUTPUT_PATH,
) -> tuple[int, int]:
    """Validate an append plan and optionally append only previously unseen keys."""
    _validate_prediction_frame(records, require_frozen_model=True)
    output = Path(path)
    existing = _read_existing(output)
    keys = set(zip(existing["match_id"], existing["model_version"]))
    duplicate = np.asarray(
        [(str(match_id), str(version)) in keys for match_id, version in zip(
            records["match_id"], records["model_version"]
        )],
        dtype=bool,
    )
    new = records.loc[~duplicate]
    if not dry_run and not new.empty:
        output.parent.mkdir(parents=True, exist_ok=True)
        exists = output.exists()
        new.to_csv(output, mode="a" if exists else "x", header=not exists, index=False, lineterminator="\n")
    return (0 if dry_run else len(new)), int(duplicate.sum())


def run_prediction(
    *,
    model: str = "poisson",
    dry_run: bool = False,
    schedule_path: str | Path = SCHEDULE_PATH,
    output_path: str | Path = OUTPUT_PATH,
    artifact_dir: str | Path | None = None,
    processed_dir: str | Path = J1_DIR,
    generated_at: str | datetime | None = None,
) -> PredictionRun:
    contract = _candidate(model)
    schedule = read_schedule_without_results(schedule_path)
    _cohort, batch = select_next_date_batch(schedule)
    require_official_target_ids(batch)
    master = load_team_master()
    identities = resolve_targets(batch, team_master=master)
    targets = (
        add_strictly_prior_elo(identities, processed_dir=processed_dir, team_master=master)
        if model == "poisson"
        else add_strictly_prior_lightgbm_state(
            identities, processed_dir=processed_dir, team_master=master
        )
    )
    artifact = load_frozen_artifact(artifact_dir, model=model)
    records = generate_prediction_records(
        targets, artifact, model=model, generated_at=generated_at
    )
    appended, existing = persist_predictions(records, dry_run=dry_run, path=output_path)
    status = (
        "DRY_RUN"
        if dry_run
        else "ALREADY_PREDICTED"
        if existing == len(records)
        else "SAVED"
    )
    return PredictionRun(
        status=status,
        target_date=str(batch["match_date"].iloc[0]),
        target_count=len(batch),
        model_version=contract.model_version,
        appended_count=appended,
        already_predicted_count=existing,
        saved=bool(appended),
        dry_run=dry_run,
        records=records,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=tuple(CANDIDATES), default="poisson")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run = run_prediction(model=args.model, dry_run=args.dry_run)
    print(
        json.dumps(
            {
                "status": run.status,
                "target_date": run.target_date,
                "target_count": run.target_count,
                "model_version": run.model_version,
                "appended_count": run.appended_count,
                "already_predicted_count": run.already_predicted_count,
                "saved": run.saved,
                "dry_run": run.dry_run,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
