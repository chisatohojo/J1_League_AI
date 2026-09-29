"""Frozen one-shot evaluator for the J1-J2 Cup bridge Elo experiment.

The normal CLI supports a read-only preflight which stops after freshly
replaying and checking references A and B.  Challenger C is reachable only
through the explicit formal entry point and is never exercised by this
module's tests or preflight command.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.teams import load_team_master
from src.features.elo import expected_score
from src.modeling.logistic_j1_j2_initial_prior_rolling_validation import (
    _load_j1,
    _load_j2,
)
from src.modeling.player_workload_evaluation import (
    CLASS_ORDER,
    _add_elo,
    _metrics,
    _validate_probabilities,
)


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
J2_PATH = ROOT / "data/processed/jleague_j2/2015_2024_j2_matches.csv"
CANDIDATE_PATH = ROOT / "data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_candidates.csv"
RESULT_PATH = ROOT / "data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_regulation.csv"
EVALUATION_DOC_PATH = ROOT / "docs/CUP_BRIDGE_EVALUATION.md"

CANDIDATE_SHA256 = "f44aa8785c80b48dc03acc4c206cbd59c4acc048d22d59579c865fbe990b5dc3"
RESULT_SHA256 = "f7dc0151299a01d8dcad5e0a1235759cad53d9784740bf81320cc0b5fb985b64"
CANDIDATE_COLUMNS = (
    "candidate_key", "competition", "season", "source_match_id", "match_date",
    "home_team", "away_team", "home_team_id", "away_team_id", "source_url",
)
RESULT_COLUMNS = (
    "candidate_key", "competition", "season", "source_match_id", "match_date",
    "home_team_id", "away_team_id", "regulation_home_score",
    "regulation_away_score", "regulation_result", "extra_time_played",
    "penalty_shootout_played", "final_home_score", "final_away_score",
    "source_url", "source_type", "raw_sha256", "resolution_status",
    "resolution_reason",
)
IDENTITY_COLUMNS = (
    "competition", "season", "source_match_id", "match_date",
    "home_team_id", "away_team_id",
)
EXPECTED_CUP_DISTRIBUTION = {
    (2015, "emperors_cup"): 6,
    (2016, "emperors_cup"): 5,
    (2017, "emperors_cup"): 8,
    (2018, "jleague_cup"): 16, (2018, "emperors_cup"): 12,
    (2019, "jleague_cup"): 14, (2019, "emperors_cup"): 7,
    (2020, "jleague_cup"): 1, (2020, "emperors_cup"): 1,
    (2021, "emperors_cup"): 6,
    (2022, "jleague_cup"): 12, (2022, "emperors_cup"): 14,
    (2023, "jleague_cup"): 12, (2023, "emperors_cup"): 13,
    (2024, "jleague_cup"): 13, (2024, "emperors_cup"): 5,
}
EXPECTED_COMPETITION_COUNTS = {"jleague_cup": 68, "emperors_cup": 77}
EXPECTED_SOURCE_COUNTS = {"j1": 3208, "j2": 4538, "cup": 145}

FOLDS = (2020, 2021, 2022, 2023, 2024)
EXPECTED_FOLD_COUNTS = {
    2020: (1530, 306), 2021: (1836, 380), 2022: (2216, 306),
    2023: (2522, 306), 2024: (2828, 380),
}
EXPECTED_POOLED_COUNT = 1678
FEATURES = ("elo_diff",)
MODEL_PARAMS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
INITIAL_RATING = 1500.0
K_FACTOR = 30.0
LEAGUE_HOME_ADVANTAGE = 175.0
CUP_HOME_ADVANTAGE = 0.0
EVENT_HOME_ADVANTAGE = {
    "j1": LEAGUE_HOME_ADVANTAGE,
    "j2": LEAGUE_HOME_ADVANTAGE,
    "jleague_cup": CUP_HOME_ADVANTAGE,
    "emperors_cup": CUP_HOME_ADVANTAGE,
}
A_FOLD_LOG_LOSS = {
    2020: 1.023119734659012,
    2021: 1.0253437210487792,
    2022: 1.0940186385371449,
    2023: 1.0604285568595655,
    2024: 1.079241181120235,
}
A_POOLED_REFERENCE = {
    "accuracy": 0.466626936829559,
    "log_loss": 1.056065401323764,
    "brier": 0.6357323419292724,
    "count": EXPECTED_POOLED_COUNT,
}
B_POOLED_PRESENTATION = {
    "accuracy": "0.460072",
    "log_loss": "1.057002",
    "brier": "0.636552",
}
READY_STATUS = "READY_FOR_ONE_FORMAL_CUP_BRIDGE_RUN"


class CupBridgeEvaluationError(ValueError):
    """A frozen artifact, source, reference, or evaluation invariant failed."""


@dataclass(frozen=True)
class PreflightResult:
    status: str
    artifact_sha256: dict[str, str]
    source_counts: dict[str, int]
    fold_counts: dict[int, tuple[int, int]]
    a_reference: str
    b_reference: str


@dataclass
class _PreflightContext:
    public: PreflightResult
    j1: pd.DataFrame
    b_stream: pd.DataFrame
    c_stream: pd.DataFrame
    cup: pd.DataFrame
    variants: dict[str, dict]


def artifact_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _assert_artifact_hash(path: str | Path, expected: str, label: str) -> str:
    try:
        actual = artifact_sha256(path)
    except OSError as exc:
        raise CupBridgeEvaluationError(f"BLOCKED_ARTIFACT_MISMATCH: {label} unavailable") from exc
    if actual != expected:
        raise CupBridgeEvaluationError(f"BLOCKED_ARTIFACT_MISMATCH: {label} SHA-256")
    return actual


def assert_artifact_hashes(
    candidate_path: str | Path = CANDIDATE_PATH,
    result_path: str | Path = RESULT_PATH,
) -> dict[str, str]:
    """Hash both frozen byte artifacts before any source load or model fit."""
    return {
        "candidate": _assert_artifact_hash(candidate_path, CANDIDATE_SHA256, "candidate"),
        "result": _assert_artifact_hash(result_path, RESULT_SHA256, "result"),
    }


def _read_artifacts(candidate_path: str | Path, result_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    candidate = pd.read_csv(candidate_path, dtype="string", keep_default_na=True)
    result = pd.read_csv(result_path, dtype="string", keep_default_na=True)
    return candidate, result


def _strict_nonnegative_integer(series: pd.Series, label: str) -> pd.Series:
    text = series.astype("string")
    if text.isna().any() or not text.str.fullmatch(r"[0-9]+").all():
        raise CupBridgeEvaluationError(f"Invalid nonnegative integer: {label}")
    return text.astype("int64")


def _assert_no_team_date_duplicates(frame: pd.DataFrame, label: str) -> None:
    appearances = pd.concat([
        frame[["match_date", "home_team_id"]].rename(columns={"home_team_id": "team_id"}),
        frame[["match_date", "away_team_id"]].rename(columns={"away_team_id": "team_id"}),
    ], ignore_index=True)
    if appearances.duplicated(["match_date", "team_id"], keep=False).any():
        raise CupBridgeEvaluationError(f"Same team has multiple {label} events on one date")


def validate_cup_artifacts(candidate: pd.DataFrame, result: pd.DataFrame) -> pd.DataFrame:
    """Validate exact frozen membership, identity, and regulation-score invariants."""
    if tuple(candidate.columns) != CANDIDATE_COLUMNS:
        raise CupBridgeEvaluationError("Candidate schema/column order mismatch")
    if tuple(result.columns) != RESULT_COLUMNS:
        raise CupBridgeEvaluationError("Result schema/column order mismatch")
    if len(candidate) != 145 or len(result) != 145:
        raise CupBridgeEvaluationError("Frozen Cup artifact row count mismatch")
    for frame, label in ((candidate, "candidate"), (result, "result")):
        if frame.candidate_key.isna().any() or not frame.candidate_key.is_unique:
            raise CupBridgeEvaluationError(f"Duplicate/null {label} candidate_key")
    if set(candidate.candidate_key) != set(result.candidate_key):
        raise CupBridgeEvaluationError("Candidate/result key sets differ")

    candidate_indexed = candidate.set_index("candidate_key", drop=False).sort_index()
    result_indexed = result.set_index("candidate_key", drop=False).sort_index()
    for column in IDENTITY_COLUMNS:
        if not candidate_indexed[column].eq(result_indexed[column]).all():
            raise CupBridgeEvaluationError(f"Candidate/result identity mismatch: {column}")

    seasons = _strict_nonnegative_integer(candidate["season"], "candidate season")
    if not seasons.between(2015, 2024).all():
        raise CupBridgeEvaluationError("Forbidden Cup season")
    competitions = candidate.competition.value_counts().to_dict()
    if competitions != EXPECTED_COMPETITION_COUNTS:
        raise CupBridgeEvaluationError(f"Frozen Cup competition distribution mismatch: {competitions}")
    distribution = {
        (int(season), str(competition)): int(count)
        for (season, competition), count in (
            candidate.assign(season_int=seasons)
            .groupby(["season_int", "competition"], sort=True).size().items()
        )
    }
    if distribution != EXPECTED_CUP_DISTRIBUTION:
        raise CupBridgeEvaluationError(f"Frozen Cup season distribution mismatch: {distribution}")

    if not result.resolution_status.eq("CONFIRMED_REGULATION_SCORE").all():
        raise CupBridgeEvaluationError("Cup result has unresolved rows")
    home_score = _strict_nonnegative_integer(result.regulation_home_score, "regulation_home_score")
    away_score = _strict_nonnegative_integer(result.regulation_away_score, "regulation_away_score")
    regulation_result = _strict_nonnegative_integer(result.regulation_result, "regulation_result")
    if not regulation_result.isin(CLASS_ORDER).all():
        raise CupBridgeEvaluationError("Cup regulation_result outside {0,1,2}")
    derived = pd.Series(np.where(home_score.gt(away_score), 2, np.where(home_score.lt(away_score), 0, 1)), index=result.index)
    if not regulation_result.eq(derived).all():
        raise CupBridgeEvaluationError("Cup regulation_result disagrees with regulation score")
    for frame, label in ((candidate, "candidate"), (result, "result")):
        if frame.home_team_id.isna().any() or frame.away_team_id.isna().any():
            raise CupBridgeEvaluationError(f"Null {label} stable team identity")
        if frame.home_team_id.eq(frame.away_team_id).any():
            raise CupBridgeEvaluationError(f"Self-match in {label}")

    cup = result.copy(deep=True)
    cup["season"] = _strict_nonnegative_integer(cup.season, "result season")
    cup["match_date"] = pd.to_datetime(cup.match_date, format="%Y-%m-%d", errors="raise").dt.normalize()
    cup["result"] = regulation_result
    cup["event_key"] = cup.competition + ":" + cup.source_match_id
    if not cup.event_key.eq(cup.candidate_key).all() or not cup.event_key.is_unique:
        raise CupBridgeEvaluationError("Cup competition-qualified event key mismatch")
    _assert_no_team_date_duplicates(cup, "Cup")
    return cup


def _validate_league_source(frame: pd.DataFrame, competition: str, expected_count: int) -> pd.DataFrame:
    required = {"match_id", "event_key", "season", "match_date", "home_team_id", "away_team_id", "result"}
    if not required.issubset(frame.columns) or len(frame) != expected_count:
        raise CupBridgeEvaluationError(f"{competition} source schema/count mismatch")
    result = frame.loc[:, list(required)].copy()
    for column in ("match_id", "event_key", "home_team_id", "away_team_id"):
        values = result[column].astype("string")
        if values.isna().any() or values.str.strip().eq("").any():
            raise CupBridgeEvaluationError(f"Null/blank {competition} identity: {column}")
    result["match_id"] = result.match_id.astype(str)
    result["event_key"] = result.event_key.astype(str)
    result["home_team_id"] = result.home_team_id.astype("string")
    result["away_team_id"] = result.away_team_id.astype("string")
    result["match_date"] = pd.to_datetime(result.match_date, errors="raise").dt.normalize()
    result["season"] = pd.to_numeric(result.season, errors="raise").astype(int)
    result["result"] = pd.to_numeric(result.result, errors="raise").astype(int)
    if not result.season.between(2015, 2024).all():
        raise CupBridgeEvaluationError(f"Forbidden {competition} season")
    if not result.result.isin(CLASS_ORDER).all():
        raise CupBridgeEvaluationError(f"Invalid {competition} result")
    if (result.home_team_id.isna().any() or result.away_team_id.isna().any()
            or result.home_team_id.eq(result.away_team_id).any()):
        raise CupBridgeEvaluationError(f"Invalid {competition} team identity")
    expected_prefix = f"{competition}:"
    if not result.event_key.str.startswith(expected_prefix).all() or not result.event_key.is_unique:
        raise CupBridgeEvaluationError(f"Invalid {competition} event key")
    _assert_no_team_date_duplicates(result, competition)
    return result


def _load_sources(j1_dir: str | Path, j2_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    master = load_team_master()
    j1 = _validate_league_source(_load_j1(j1_dir, master), "j1", EXPECTED_SOURCE_COUNTS["j1"])
    j2 = _validate_league_source(_load_j2(j2_path), "j2", EXPECTED_SOURCE_COUNTS["j2"])
    return j1, j2


def _assert_bridge_membership(cup: pd.DataFrame, j1: pd.DataFrame, j2: pd.DataFrame) -> None:
    j1_membership = {
        season: set(j1.loc[j1.season.eq(season), "home_team_id"]) | set(j1.loc[j1.season.eq(season), "away_team_id"])
        for season in range(2015, 2025)
    }
    j2_membership = {
        season: set(j2.loc[j2.season.eq(season), "home_team_id"]) | set(j2.loc[j2.season.eq(season), "away_team_id"])
        for season in range(2015, 2025)
    }
    for row in cup.itertuples(index=False):
        home_j1, away_j1 = row.home_team_id in j1_membership[row.season], row.away_team_id in j1_membership[row.season]
        home_j2, away_j2 = row.home_team_id in j2_membership[row.season], row.away_team_id in j2_membership[row.season]
        if not ((home_j1 and away_j2) or (home_j2 and away_j1)):
            raise CupBridgeEvaluationError(f"Cup row is not an exact J1-J2 bridge: {row.candidate_key}")


def _event_rows(frame: pd.DataFrame, competition: str) -> pd.DataFrame:
    rows = frame[["event_key", "season", "match_date", "home_team_id", "away_team_id", "result"]].copy()
    rows["event_type"] = competition if competition in ("j1", "j2") else frame.competition.astype(str).to_numpy()
    rows["home_advantage"] = rows.event_type.map(EVENT_HOME_ADVANTAGE)
    return rows


def _make_stream(j1: pd.DataFrame, j2: pd.DataFrame | None = None, cup: pd.DataFrame | None = None) -> pd.DataFrame:
    parts = [_event_rows(j1, "j1")]
    if j2 is not None:
        parts.append(_event_rows(j2, "j2"))
    if cup is not None:
        parts.append(_event_rows(cup, "cup"))
    stream = pd.concat(parts, ignore_index=True).sort_values(["match_date", "event_key"], kind="stable").reset_index(drop=True)
    if stream.event_key.duplicated().any():
        raise CupBridgeEvaluationError("Duplicate competition-qualified event key")
    if stream.home_advantage.isna().any():
        raise CupBridgeEvaluationError("Unknown event type/home advantage")
    _assert_no_team_date_duplicates(stream, "combined stream")
    return stream


def _replay_features(j1: pd.DataFrame, stream: pd.DataFrame) -> pd.DataFrame:
    """Replay one common Elo population using conservative calendar-day batches."""
    ratings = {team: INITIAL_RATING for team in set(stream.home_team_id) | set(stream.away_team_id)}
    target_keys = set(j1.event_key)
    feature_by_key: dict[str, float] = {}
    ordered = stream.sort_values(["match_date", "event_key"], kind="stable")
    for _, day in ordered.groupby("match_date", sort=True):
        snapshots = []
        for row in day.itertuples(index=False):
            home_rating = ratings[row.home_team_id]
            away_rating = ratings[row.away_team_id]
            if row.event_key in target_keys:
                feature_by_key[row.event_key] = home_rating - away_rating
            snapshots.append((row, home_rating, away_rating))
        for row, home_rating, away_rating in snapshots:
            home_expected = expected_score(home_rating + float(row.home_advantage), away_rating)
            delta = K_FACTOR * (int(row.result) / 2.0 - home_expected)
            ratings[row.home_team_id] = home_rating + delta
            ratings[row.away_team_id] = away_rating - delta
    if set(feature_by_key) != target_keys:
        raise CupBridgeEvaluationError("J1 target feature replay is incomplete")
    features = j1.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True).copy(deep=True)
    features["elo_diff"] = features.event_key.map(feature_by_key)
    if features.elo_diff.isna().any() or not np.isfinite(features.elo_diff).all():
        raise CupBridgeEvaluationError("Invalid replayed elo_diff")
    return features


def _a_features(j1: pd.DataFrame) -> pd.DataFrame:
    known_good = _add_elo(j1.copy(deep=True))
    if not known_good.event_key.is_unique:
        raise CupBridgeEvaluationError("A feature event keys are not unique")
    return known_good


def _validate_fold_counts(j1: pd.DataFrame) -> dict[int, tuple[int, int]]:
    counts = {}
    for year, expected in EXPECTED_FOLD_COUNTS.items():
        observed = (int(j1.season.lt(year).sum()), int(j1.season.eq(year).sum()))
        if observed != expected:
            raise CupBridgeEvaluationError(f"Fold count mismatch for {year}: {observed}")
        counts[year] = observed
    if sum(count[1] for count in counts.values()) != EXPECTED_POOLED_COUNT:
        raise CupBridgeEvaluationError("Pooled validation count mismatch")
    return counts


def assert_same_fold_inputs(*frames: pd.DataFrame) -> None:
    """Require all variant frames to retain ordered J1 row identity and labels."""
    if len(frames) < 2:
        raise ValueError("At least two variant frames are required")
    reference = frames[0]
    columns = ("match_id", "event_key", "season", "result")
    for frame in frames[1:]:
        for column in columns:
            if reference[column].astype(str).tolist() != frame[column].astype(str).tolist():
                raise CupBridgeEvaluationError(f"Variant fold input differs: {column}")


def _fit(train: pd.DataFrame, validation: pd.DataFrame) -> np.ndarray:
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(**MODEL_PARAMS)),
    ])
    model.fit(train.loc[:, FEATURES], train.result)
    if not np.array_equal(model.named_steps["logistic"].classes_, np.asarray(CLASS_ORDER)):
        raise CupBridgeEvaluationError("Expected probability class order [0, 1, 2]")
    return _validate_probabilities(model.predict_proba(validation.loc[:, FEATURES]))


def _metric_dict(labels: Iterable[int], probabilities: np.ndarray) -> dict:
    return asdict(_metrics(labels, probabilities))


def _evaluate_variant(features: pd.DataFrame) -> dict:
    folds = {}
    pooled_labels, pooled_probabilities = [], []
    for year in FOLDS:
        train = features.loc[features.season.lt(year)].copy()
        validation = features.loc[features.season.eq(year)].copy()
        probabilities = _fit(train, validation)
        labels = validation.result.to_numpy(dtype=int)
        folds[year] = {
            "train_n": len(train), "validation_n": len(validation),
            "train_ids": train.match_id.astype(str).tolist(),
            "validation_ids": validation.match_id.astype(str).tolist(),
            "labels": labels,
            "probabilities": probabilities,
            "metrics": _metric_dict(labels, probabilities),
        }
        pooled_labels.append(labels)
        pooled_probabilities.append(probabilities)
    labels = np.concatenate(pooled_labels)
    probabilities = np.concatenate(pooled_probabilities)
    return {
        "folds": folds,
        "pooled_labels": labels,
        "pooled_probabilities": probabilities,
        "pooled": _metric_dict(labels, probabilities),
    }


def assert_a_reference(result: dict) -> None:
    for year in FOLDS:
        actual = result["folds"][year]["metrics"]["log_loss"]
        if not np.isclose(actual, A_FOLD_LOG_LOSS[year], rtol=0, atol=1e-12):
            raise CupBridgeEvaluationError(f"BLOCKED_REFERENCE_MISMATCH: A {year} Log Loss")
    for metric, expected in A_POOLED_REFERENCE.items():
        actual = result["pooled"][metric]
        if metric == "count":
            if actual != expected:
                raise CupBridgeEvaluationError("BLOCKED_REFERENCE_MISMATCH: A pooled count")
        elif not np.isclose(actual, expected, rtol=0, atol=1e-12):
            raise CupBridgeEvaluationError(f"BLOCKED_REFERENCE_MISMATCH: A pooled {metric}")


def assert_b_reference(result: dict) -> None:
    for metric, expected in B_POOLED_PRESENTATION.items():
        if format(result["pooled"][metric], ".6f") != expected:
            raise CupBridgeEvaluationError(f"BLOCKED_REFERENCE_MISMATCH: B pooled {metric}")


def _assert_evaluation_rows_equal(*variants: dict) -> None:
    for year in FOLDS:
        baseline = variants[0]["folds"][year]
        for variant in variants[1:]:
            candidate = variant["folds"][year]
            if baseline["train_ids"] != candidate["train_ids"]:
                raise CupBridgeEvaluationError(f"Variant training IDs differ for {year}")
            if baseline["validation_ids"] != candidate["validation_ids"]:
                raise CupBridgeEvaluationError(f"Variant validation IDs differ for {year}")
            if not np.array_equal(baseline["labels"], candidate["labels"]):
                raise CupBridgeEvaluationError(f"Variant labels differ for {year}")


def _preflight_context(
    *,
    candidate_path: str | Path = CANDIDATE_PATH,
    result_path: str | Path = RESULT_PATH,
    j1_dir: str | Path = J1_DIR,
    j2_path: str | Path = J2_PATH,
) -> _PreflightContext:
    hashes = assert_artifact_hashes(candidate_path, result_path)
    candidate, result = _read_artifacts(candidate_path, result_path)
    cup = validate_cup_artifacts(candidate, result)
    j1, j2 = _load_sources(j1_dir, j2_path)
    _assert_bridge_membership(cup, j1, j2)
    fold_counts = _validate_fold_counts(j1)
    a_stream = _make_stream(j1)
    b_stream = _make_stream(j1, j2)
    c_stream = _make_stream(j1, j2, cup)
    if set(c_stream.event_key) - set(b_stream.event_key) != set(cup.event_key):
        raise CupBridgeEvaluationError("C differs from B by other than the frozen 145 Cup events")
    if len(c_stream) - len(b_stream) != 145:
        raise CupBridgeEvaluationError("C stream does not add exactly 145 Cup events")

    a_features = _a_features(j1)
    # Replaying A through the event-specific implementation is a static
    # chronology check; the known-good replay remains the evaluated A source.
    a_replayed = _replay_features(j1, a_stream)
    if not np.allclose(a_features.elo_diff, a_replayed.elo_diff, rtol=0, atol=1e-12):
        raise CupBridgeEvaluationError("A replay chronology differs from known-good Elo")
    a_result = _evaluate_variant(a_features)
    assert_a_reference(a_result)

    b_features = _replay_features(j1, b_stream)
    assert_same_fold_inputs(a_features, b_features)
    b_result = _evaluate_variant(b_features)
    _assert_evaluation_rows_equal(a_result, b_result)
    assert_b_reference(b_result)

    public = PreflightResult(
        status=READY_STATUS,
        artifact_sha256=hashes,
        source_counts=EXPECTED_SOURCE_COUNTS.copy(),
        fold_counts=fold_counts,
        a_reference="PASS",
        b_reference="PASS",
    )
    return _PreflightContext(public, j1, b_stream, c_stream, cup, {"a": a_result, "b": b_result})


def preflight(**kwargs) -> PreflightResult:
    """Run all frozen gates through B, without replaying or fitting C."""
    return _preflight_context(**kwargs).public


def _delta(challenger: dict, baseline: dict) -> dict:
    return {name: challenger[name] - baseline[name] for name in ("accuracy", "log_loss", "brier")}


def frozen_decision(a_folds: dict, a_pooled: dict, c_folds: dict, c_pooled: dict) -> str:
    improved = sum(c_folds[year]["log_loss"] < a_folds[year]["log_loss"] for year in FOLDS)
    non_improved = sum(c_folds[year]["log_loss"] >= a_folds[year]["log_loss"] for year in FOLDS)
    if c_pooled["log_loss"] < a_pooled["log_loss"] and c_pooled["brier"] < a_pooled["brier"] and improved >= 3:
        return "ADOPT_CUP_BRIDGED_ELO"
    if c_pooled["log_loss"] >= a_pooled["log_loss"] and c_pooled["brier"] >= a_pooled["brier"] and non_improved >= 3:
        return "CLOSE_CUP_BRIDGE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def _prediction_diagnostic(labels: np.ndarray, probabilities: np.ndarray) -> dict:
    return {
        "actual": np.bincount(labels, minlength=3).astype(int).tolist(),
        "argmax": np.bincount(np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)], minlength=3).astype(int).tolist(),
        "mean_draw_probability": float(probabilities[:, 1].mean()),
    }


def _promotion_diagnostics(j1: pd.DataFrame, variants: dict[str, dict]) -> dict:
    """Build the frozen descriptive promotion subgroups for the formal report."""
    memberships = {
        year: set(j1.loc[j1.season.eq(year), "home_team_id"]) | set(j1.loc[j1.season.eq(year), "away_team_id"])
        for year in range(2015, 2025)
    }
    first_seen: dict[str, int] = {}
    for row in j1.sort_values(["match_date", "event_key"], kind="stable").itertuples(index=False):
        first_seen.setdefault(row.home_team_id, int(row.season))
        first_seen.setdefault(row.away_team_id, int(row.season))

    rows = []
    for year in FOLDS:
        validation = (
            j1.loc[j1.season.eq(year)]
            .sort_values(["match_date", "match_id"], kind="stable")
            .reset_index(drop=True)
        )
        promoted = memberships[year] - memberships[year - 1]
        appearances = {team: 0 for team in promoted}
        probabilities = {
            name: variants[name]["folds"][year]["probabilities"]
            for name in ("a", "b", "c")
        }
        for position, row in enumerate(validation.itertuples(index=False)):
            involved = [team for team in (row.home_team_id, row.away_team_id) if team in promoted]
            if not involved:
                continue
            for team in involved:
                appearances[team] += 1
            category = (
                "first_time_promoted"
                if all(first_seen.get(team, year) == year for team in involved)
                else "returning_promoted"
            )
            rows.append({
                "season": year,
                "result": int(row.result),
                "category": category,
                "first_1_3_appearances": min(appearances[team] for team in involved) <= 3,
                **{f"{name}_probability": probabilities[name][position] for name in probabilities},
            })

    frame = pd.DataFrame(rows)
    output = {}
    masks = {
        "returning_promoted": frame.category.eq("returning_promoted"),
        "first_time_promoted": frame.category.eq("first_time_promoted"),
        "first_1_3_appearances": frame.first_1_3_appearances,
    }
    for label, mask in masks.items():
        subset = frame.loc[mask]
        output[label] = {
            "count": len(subset),
            "metrics": {
                name: _metric_dict(subset.result.to_numpy(dtype=int), np.vstack(subset[f"{name}_probability"]))
                for name in ("a", "b", "c")
            } if len(subset) else {},
        }
    return output


def _formal_from_context(context: _PreflightContext) -> dict:
    """The sole code path which replays, fits, and evaluates challenger C."""
    c_features = _replay_features(context.j1, context.c_stream)
    b_features = _replay_features(context.j1, context.b_stream)
    a_features = _a_features(context.j1)
    assert_same_fold_inputs(a_features, b_features, c_features)
    c_result = _evaluate_variant(c_features)
    a_result, b_result = context.variants["a"], context.variants["b"]
    _assert_evaluation_rows_equal(a_result, b_result, c_result)

    folds = {}
    for year in FOLDS:
        a_metrics = a_result["folds"][year]["metrics"]
        b_metrics = b_result["folds"][year]["metrics"]
        c_metrics = c_result["folds"][year]["metrics"]
        folds[year] = {
            "train_n": a_result["folds"][year]["train_n"],
            "validation_n": a_result["folds"][year]["validation_n"],
            "a": a_metrics, "b": b_metrics, "c": c_metrics,
            "c_minus_b": _delta(c_metrics, b_metrics),
            "c_minus_a": _delta(c_metrics, a_metrics),
            "cup_history_events": int(context.cup.match_date.lt(pd.Timestamp(f"{year}-01-01")).sum()),
            "diagnostics": {
                name: _prediction_diagnostic(variant["folds"][year]["labels"], variant["folds"][year]["probabilities"])
                for name, variant in (("a", a_result), ("b", b_result), ("c", c_result))
            },
        }
    pooled = {
        "a": a_result["pooled"], "b": b_result["pooled"], "c": c_result["pooled"],
        "c_minus_b": _delta(c_result["pooled"], b_result["pooled"]),
        "c_minus_a": _delta(c_result["pooled"], a_result["pooled"]),
        "diagnostics": {
            name: _prediction_diagnostic(variant["pooled_labels"], variant["pooled_probabilities"])
            for name, variant in (("a", a_result), ("b", b_result), ("c", c_result))
        },
    }
    a_folds = {year: folds[year]["a"] for year in FOLDS}
    c_folds = {year: folds[year]["c"] for year in FOLDS}
    decision = frozen_decision(a_folds, pooled["a"], c_folds, pooled["c"])
    variants = {"a": a_result, "b": b_result, "c": c_result}
    return {
        "status": "FORMAL_CUP_BRIDGE_EVALUATION_COMPLETE",
        "folds": folds,
        "pooled": pooled,
        "decision": decision,
        "promotion_diagnostics": _promotion_diagnostics(context.j1, variants),
        "diagnostics_are_decision_inputs": False,
        "feature_changes": False,
        "parameter_changes": False,
        "adaptive_follow_up": False,
    }


def render_evaluation_markdown(result: dict) -> str:
    """Render the future formal result deterministically (no timestamp)."""
    lines = [
        "# Cup Bridge Evaluation", "",
        "Formal frozen A/B/C result.", "",
        "## Fold metrics and deltas", "",
        "| Season | Train n | Validation n | A Acc | A LL | A Brier | B Acc | B LL | B Brier | C Acc | C LL | C Brier | C-B Acc | C-B LL | C-B Brier | C-A Acc | C-A LL | C-A Brier | Cup history |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for year in FOLDS:
        fold = result["folds"][year]
        lines.append(
            f"| {year} | {fold['train_n']} | {fold['validation_n']} | "
            f"{fold['a']['accuracy']!r} | {fold['a']['log_loss']!r} | {fold['a']['brier']!r} | "
            f"{fold['b']['accuracy']!r} | {fold['b']['log_loss']!r} | {fold['b']['brier']!r} | "
            f"{fold['c']['accuracy']!r} | {fold['c']['log_loss']!r} | {fold['c']['brier']!r} | "
            f"{fold['c_minus_b']['accuracy']!r} | {fold['c_minus_b']['log_loss']!r} | {fold['c_minus_b']['brier']!r} | "
            f"{fold['c_minus_a']['accuracy']!r} | {fold['c_minus_a']['log_loss']!r} | {fold['c_minus_a']['brier']!r} | "
            f"{fold['cup_history_events']} |"
        )
    pooled = result["pooled"]
    lines.extend([
        "", "## Pooled metrics", "",
        "| Variant | Accuracy | Log Loss | Brier | n |",
        "|---|---:|---:|---:|---:|",
    ])
    for name in ("a", "b", "c"):
        metric = pooled[name]
        lines.append(f"| {name.upper()} | {metric['accuracy']!r} | {metric['log_loss']!r} | {metric['brier']!r} | {metric['count']} |")
    for name in ("c_minus_b", "c_minus_a"):
        metric = pooled[name]
        lines.append(f"| {name.upper().replace('_', ' ')} | {metric['accuracy']!r} | {metric['log_loss']!r} | {metric['brier']!r} | - |")
    lines.extend([
        "", "## Diagnostic-only outputs", "", "```json",
        json.dumps({
            "fold_class_and_draw": {str(year): result["folds"][year]["diagnostics"] for year in FOLDS},
            "pooled_class_and_draw": pooled["diagnostics"],
            "promotion_subgroups": result["promotion_diagnostics"],
        }, ensure_ascii=False, sort_keys=True, indent=2),
        "```", "", "Diagnostics do not enter the frozen decision.", "",
        "## Final decision", "", f"**{result['decision']}**", "",
        "feature changes = **NO**", "parameter changes = **NO**",
        "tuning = **NOT RUN**", "adaptive follow-up = **NOT RUN**", "",
    ])
    return "\n".join(lines)


def write_evaluation_markdown(result: dict, path: str | Path = EVALUATION_DOC_PATH) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_evaluation_markdown(result), encoding="utf-8", newline="\n")
    return output


def formal_evaluate(*, write_report: bool = True, **kwargs) -> dict:
    """Run the separately authorized one-shot C evaluation after all gates."""
    context = _preflight_context(**kwargs)
    result = _formal_from_context(context)
    if write_report:
        write_evaluation_markdown(result)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true", help="run gates through A/B only")
    mode.add_argument("--formal", action="store_true", help="run the separately authorized one-shot C evaluation")
    parser.add_argument(
        "--confirm-one-shot", action="store_true",
        help="required with --formal to prevent accidental challenger execution",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.formal:
        if not args.confirm_one_shot:
            parser.error("--formal requires --confirm-one-shot")
        result = formal_evaluate()
        print(result["status"])
        print(result["decision"])
        return 0
    if args.confirm_one_shot:
        parser.error("--confirm-one-shot is valid only with --formal")
    if not args.preflight:
        parser.print_help()
        return 0
    result = preflight()
    print(result.status)
    print(f"A_REFERENCE={result.a_reference}")
    print(f"B_REFERENCE={result.b_reference}")
    print("FORMAL_C=NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
