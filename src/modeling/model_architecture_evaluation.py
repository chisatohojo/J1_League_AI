"""Frozen one-shot historical evaluator for architecture candidates A, P, and G.

The default CLI is a read-only preflight which evaluates Candidate A only.
Candidate P and G are reachable only after the explicit formal one-shot gate.
Operational artifacts and prospective prediction data are never used here.
"""

from __future__ import annotations

import argparse
import json
import re
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.matches import load_matches
from src.collect.teams import TeamMaster, load_team_master
from src.modeling.architecture_lightgbm import (
    FEATURE_COLUMNS as G_FEATURES,
    build_lightgbm_state_features,
    fit_lightgbm_model,
    predict_proba as predict_g_proba,
)
from src.modeling.architecture_poisson import (
    build_goal_observations,
    fit_poisson_model,
    predict_proba as predict_p_proba,
)
from src.modeling.player_workload_evaluation import _add_elo


ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
ATTEMPT_MARKER_PATH = (
    ROOT / "data/processed/model_architecture/formal_benchmark_attempt.json"
)
RESULT_DOC_PATH = ROOT / "docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md"
FOLDS = (2020, 2021, 2022, 2023, 2024)
CLASS_ORDER = (0, 1, 2)
A_FEATURES = ("elo_diff",)
A_PARAMS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
EXPECTED_ROWS = 3208
EXPECTED_SEASON_COUNTS = {
    2015: 306,
    2016: 306,
    2017: 306,
    2018: 306,
    2019: 306,
    2020: 306,
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
EXPECTED_FOLD_COUNTS = {
    2020: (1530, 306),
    2021: (1836, 380),
    2022: (2216, 306),
    2023: (2522, 306),
    2024: (2828, 380),
}
EXPECTED_POOLED_VALIDATION = 1678
EXPECTED_A_FOLD_LOG_LOSS = {
    2020: 1.023119734659012,
    2021: 1.0253437210487792,
    2022: 1.0940186385371449,
    2023: 1.0604285568595655,
    2024: 1.079241181120235,
}
EXPECTED_A_POOLED = {
    "count": 1678,
    "accuracy": 0.466626936829559,
    "log_loss": 1.056065401323764,
    "brier": 0.6357323419292724,
}
PREFLIGHT_STATUS = "READY_FOR_ONE_FORMAL_MODEL_ARCHITECTURE_BENCHMARK"
FORMAL_STATUS = "FORMAL_MODEL_ARCHITECTURE_BENCHMARK_COMPLETE"
QUALIFIES = "QUALIFIES_FOR_PROSPECTIVE_ARCHITECTURE_TRACK"
CLOSE = "CLOSE_ARCHITECTURE_CANDIDATE"
INCONCLUSIVE = "INCONCLUSIVE_NO_TUNING"
SOURCE_COLUMNS = (
    "season",
    "match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "home_score",
    "away_score",
    "result",
)
STATE_COLUMNS = (*SOURCE_COLUMNS, *G_FEATURES)


class ArchitectureEvaluationError(ValueError):
    """A shared source, chronology, reference, or one-shot gate failed."""


class CandidateEvaluationFailure(RuntimeError):
    """One candidate failed after the shared formal one-shot began."""


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    log_loss: float
    brier: float
    count: int


@dataclass(frozen=True)
class PreflightResult:
    status: str
    source_rows: int
    season_counts: dict[int, int]
    fold_counts: dict[int, tuple[int, int]]
    pooled_validation_rows: int
    source_gate: str
    chronology_gate: str
    candidate_schema_gate: str
    a_reference_gate: str
    a_fold_log_loss: dict[int, float]
    a_pooled: dict


@dataclass(frozen=True)
class _PreflightContext:
    public: PreflightResult
    state: pd.DataFrame
    a_result: dict


def _integer_values(series: pd.Series, label: str) -> np.ndarray:
    try:
        values = pd.to_numeric(series, errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ArchitectureEvaluationError(f"{label} must contain integers") from exc
    if not np.isfinite(values).all() or not np.equal(values, np.floor(values)).all():
        raise ArchitectureEvaluationError(f"{label} must contain integers")
    return values.astype(np.int64)


def validate_source(matches: pd.DataFrame, *, team_master: TeamMaster | None = None) -> None:
    """Validate the exact canonical 2015--2024 ordinary-J1 population."""
    if not isinstance(matches, pd.DataFrame) or matches.columns.has_duplicates:
        raise ArchitectureEvaluationError("Source must be a DataFrame with unique columns")
    missing = set(SOURCE_COLUMNS) - set(matches.columns)
    if missing:
        raise ArchitectureEvaluationError(f"Source schema is missing columns: {sorted(missing)}")
    if len(matches) != EXPECTED_ROWS:
        raise ArchitectureEvaluationError(f"Source must contain exactly {EXPECTED_ROWS} rows")
    seasons = _integer_values(matches["season"], "season")
    counts = pd.Series(seasons).value_counts().sort_index().to_dict()
    if counts != EXPECTED_SEASON_COUNTS:
        raise ArchitectureEvaluationError(f"Season coverage mismatch: {counts}")

    match_ids = matches["match_id"]
    if match_ids.isna().any() or match_ids.astype(str).str.strip().eq("").any():
        raise ArchitectureEvaluationError("match_id must be nonblank")
    if match_ids.duplicated().any():
        raise ArchitectureEvaluationError("match_id must be unique")
    try:
        dates = pd.to_datetime(matches["match_date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ArchitectureEvaluationError("match_date must be valid") from exc
    if dates.isna().any():
        raise ArchitectureEvaluationError("match_date must be valid")
    expected_order = matches.assign(_date=dates).sort_values(
        ["_date", "match_id"], kind="stable"
    ).index.to_numpy()
    if not np.array_equal(expected_order, matches.index.to_numpy()):
        raise ArchitectureEvaluationError("Source must use canonical match_date, match_id order")

    master = load_team_master() if team_master is None else team_master
    master_ids = {alias.team_id for alias in master.aliases}
    for column in ("home_team_id", "away_team_id"):
        values = matches[column]
        if values.isna().any() or values.map(
            lambda value: not isinstance(value, str) or not value.strip()
        ).any():
            raise ArchitectureEvaluationError(f"{column} must contain nonblank TeamMaster IDs")
        if not set(values).issubset(master_ids):
            raise ArchitectureEvaluationError("Source contains an unknown TeamMaster ID")
    if matches["home_team_id"].eq(matches["away_team_id"]).any():
        raise ArchitectureEvaluationError("Home and away TeamMaster IDs must differ")

    home_scores = _integer_values(matches["home_score"], "home_score")
    away_scores = _integer_values(matches["away_score"], "away_score")
    if (home_scores < 0).any() or (away_scores < 0).any():
        raise ArchitectureEvaluationError("Scores must be nonnegative integers")
    results = _integer_values(matches["result"], "result")
    if not np.isin(results, CLASS_ORDER).all():
        raise ArchitectureEvaluationError("result must be 0, 1, or 2")
    expected_results = np.where(
        home_scores > away_scores, 2, np.where(home_scores < away_scores, 0, 1)
    )
    if not np.array_equal(results, expected_results):
        raise ArchitectureEvaluationError("Score/result contradiction")
    appearances = pd.concat(
        [
            pd.DataFrame({"match_date": dates, "team_id": matches[f"{side}_team_id"]})
            for side in ("home", "away")
        ],
        ignore_index=True,
    )
    if appearances.duplicated(["match_date", "team_id"]).any():
        raise ArchitectureEvaluationError("A team appears more than once on the same date")


def load_retrospective_source(
    match_dir: str | Path = MATCH_DIR,
    *,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Load only ordinary J1 seasons 2015--2024 and resolve exact TeamMaster IDs."""
    master = load_team_master() if team_master is None else team_master
    frames = []
    for season in range(2015, 2025):
        loaded = load_matches(Path(match_dir) / f"{season}_matches_probe.csv")
        frames.append(master.add_team_ids(loaded))
    ordered = pd.concat(frames, ignore_index=True).sort_values(
        ["match_date", "match_id"], kind="stable"
    ).reset_index(drop=True)
    result = ordered.loc[:, list(SOURCE_COLUMNS)].copy(deep=True)
    validate_source(result, team_master=master)
    return result


def build_shared_state(
    matches: pd.DataFrame,
    *,
    validate_population: bool = True,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Build Elo and G form once over the complete chronological stream."""
    source = matches.loc[:, list(SOURCE_COLUMNS)].copy(deep=True)
    if validate_population:
        validate_source(source, team_master=team_master)
    try:
        elo = _add_elo(source)
        g_state = build_lightgbm_state_features(elo)
    except (TypeError, ValueError) as exc:
        raise ArchitectureEvaluationError(f"Shared chronology construction failed: {exc}") from exc
    result = elo.copy(deep=True)
    for column in G_FEATURES[1:]:
        result[column] = g_state[column].to_numpy(copy=True)
    result = result.loc[:, list(STATE_COLUMNS)]
    if not np.isfinite(result.loc[:, list(G_FEATURES)].to_numpy(dtype=float)).all():
        raise ArchitectureEvaluationError("Shared state contains nonfinite features")
    return result


def validate_fold_contract(data: pd.DataFrame) -> dict[int, tuple[int, int]]:
    observed = {}
    for year in FOLDS:
        counts = (int(data["season"].lt(year).sum()), int(data["season"].eq(year).sum()))
        if counts != EXPECTED_FOLD_COUNTS[year]:
            raise ArchitectureEvaluationError(f"Fold count mismatch for {year}: {counts}")
        observed[year] = counts
    if sum(counts[1] for counts in observed.values()) != EXPECTED_POOLED_VALIDATION:
        raise ArchitectureEvaluationError("Pooled validation count mismatch")
    return observed


def build_candidate_a() -> Pipeline:
    """Return a fresh exact frozen Candidate A pipeline."""
    return Pipeline(
        [
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(**A_PARAMS)),
        ]
    )


def validate_probabilities(probabilities, *, expected_rows: int | None = None) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ArchitectureEvaluationError("Expected N x 3 probabilities")
    if expected_rows is not None and values.shape[0] != expected_rows:
        raise ArchitectureEvaluationError("Probability row count mismatch")
    if (
        not np.isfinite(values).all()
        or (values < 0).any()
        or (values > 1).any()
        or not np.allclose(values.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)
    ):
        raise ArchitectureEvaluationError("Invalid probability values")
    return values


def calculate_metrics(labels, probabilities) -> Metrics:
    y = np.asarray(labels, dtype=int)
    p = validate_probabilities(probabilities, expected_rows=len(y))
    if not np.isin(y, CLASS_ORDER).all():
        raise ArchitectureEvaluationError("Metrics labels must use classes [0, 1, 2]")
    one_hot = (y[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    predicted = np.asarray(CLASS_ORDER, dtype=int)[p.argmax(axis=1)]
    return Metrics(
        accuracy=float(np.mean(predicted == y)),
        log_loss=float(log_loss(y, p, labels=list(CLASS_ORDER))),
        brier=float(np.mean(np.sum((p - one_hot) ** 2, axis=1))),
        count=len(y),
    )


def _fold_frames(data: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = data.loc[data["season"].lt(year)].copy(deep=True)
    validation = data.loc[data["season"].eq(year)].copy(deep=True)
    if (len(train), len(validation)) != EXPECTED_FOLD_COUNTS[year]:
        raise ArchitectureEvaluationError(f"Fold count mismatch for {year}")
    return train, validation


def _fold_output(train, validation, probabilities) -> dict:
    p = validate_probabilities(probabilities, expected_rows=len(validation))
    return {
        "training_rows": len(train),
        "validation_rows": len(validation),
        "train_ids": train["match_id"].astype(str).tolist(),
        "validation_ids": validation["match_id"].astype(str).tolist(),
        "labels": validation["result"].to_numpy(dtype=int),
        "probabilities": p,
        "metrics": asdict(calculate_metrics(validation["result"], p)),
    }


def _fit_predict_a(train: pd.DataFrame, validation: pd.DataFrame) -> np.ndarray:
    model = build_candidate_a()
    model.fit(train.loc[:, list(A_FEATURES)], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, np.asarray(CLASS_ORDER)):
        raise ArchitectureEvaluationError("Candidate A class order mismatch")
    return validate_probabilities(
        model.predict_proba(validation.loc[:, list(A_FEATURES)]),
        expected_rows=len(validation),
    )


def _evaluate_a(data: pd.DataFrame) -> dict:
    folds = {}
    pooled_labels, pooled_probabilities = [], []
    for year in FOLDS:
        train, validation = _fold_frames(data, year)
        fold = _fold_output(train, validation, _fit_predict_a(train, validation))
        folds[year] = fold
        pooled_labels.append(fold["labels"])
        pooled_probabilities.append(fold["probabilities"])
    labels = np.concatenate(pooled_labels)
    probabilities = np.vstack(pooled_probabilities)
    if len(labels) != EXPECTED_POOLED_VALIDATION:
        raise ArchitectureEvaluationError("Candidate A pooled validation mismatch")
    return {
        "folds": folds,
        "pooled": asdict(calculate_metrics(labels, probabilities)),
        "pooled_ids": [match_id for year in FOLDS for match_id in folds[year]["validation_ids"]],
        "pooled_labels": labels,
        "pooled_probabilities": probabilities,
    }


def assert_a_reference(a_result: dict) -> None:
    for year in FOLDS:
        actual = a_result["folds"][year]["metrics"]["log_loss"]
        if not np.isclose(actual, EXPECTED_A_FOLD_LOG_LOSS[year], rtol=0.0, atol=1e-12):
            raise ArchitectureEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: Candidate A {year} Log Loss"
            )
    actual_pooled = a_result["pooled"]
    for key, expected in EXPECTED_A_POOLED.items():
        actual = actual_pooled[key]
        if key == "count":
            matched = actual == expected
        else:
            matched = np.isclose(actual, expected, rtol=0.0, atol=1e-12)
        if not matched:
            raise ArchitectureEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: Candidate A pooled {key}"
            )


def _validate_p_schema(data: pd.DataFrame) -> None:
    for year in FOLDS:
        train, validation = _fold_frames(data, year)
        observations = build_goal_observations(train)
        if len(observations) != 2 * len(train):
            raise ArchitectureEvaluationError("Candidate P observation count mismatch")
        if validation["match_id"].duplicated().any():
            raise ArchitectureEvaluationError("Candidate P validation identity mismatch")


def _preflight_context(
    *,
    match_dir: str | Path = MATCH_DIR,
    source: pd.DataFrame | None = None,
    team_master: TeamMaster | None = None,
) -> _PreflightContext:
    master = load_team_master() if team_master is None else team_master
    matches = (
        load_retrospective_source(match_dir, team_master=master)
        if source is None
        else source.copy(deep=True)
    )
    validate_source(matches, team_master=master)
    state = build_shared_state(matches, validate_population=False, team_master=master)
    fold_counts = validate_fold_contract(state)
    _validate_p_schema(state)
    a_result = _evaluate_a(state)
    assert_a_reference(a_result)
    public = PreflightResult(
        status=PREFLIGHT_STATUS,
        source_rows=len(state),
        season_counts=state["season"].value_counts().sort_index().to_dict(),
        fold_counts=fold_counts,
        pooled_validation_rows=EXPECTED_POOLED_VALIDATION,
        source_gate="PASS",
        chronology_gate="PASS",
        candidate_schema_gate="PASS",
        a_reference_gate="PASS",
        a_fold_log_loss={
            year: a_result["folds"][year]["metrics"]["log_loss"] for year in FOLDS
        },
        a_pooled=a_result["pooled"],
    )
    return _PreflightContext(public=public, state=state, a_result=a_result)


def preflight(**kwargs) -> PreflightResult:
    """Run read-only gates and Candidate A only; never fit P or G."""
    return _preflight_context(**kwargs).public


def _validate_candidate_alignment(candidate: dict, a_result: dict, label: str) -> None:
    for year in FOLDS:
        expected = a_result["folds"][year]
        actual = candidate["folds"][year]
        if actual["validation_ids"] != expected["validation_ids"] or not np.array_equal(
            actual["labels"], expected["labels"]
        ):
            raise CandidateEvaluationFailure(f"Candidate {label} fold identity mismatch")


def _evaluate_p(data: pd.DataFrame, a_result: dict) -> dict:
    folds, pooled_labels, pooled_probabilities = {}, [], []
    try:
        for year in FOLDS:
            train, validation = _fold_frames(data, year)
            with warnings.catch_warnings():
                warnings.simplefilter("error", ConvergenceWarning)
                model = fit_poisson_model(train)
            predicted = predict_p_proba(
                model,
                validation.loc[:, [
                    "match_id", "match_date", "home_team_id", "away_team_id", "elo_diff"
                ]],
            )
            if predicted["match_id"].astype(str).tolist() != validation["match_id"].astype(str).tolist():
                raise CandidateEvaluationFailure("Candidate P prediction identity/order mismatch")
            fold = _fold_output(
                train,
                validation,
                predicted.loc[:, ["p_away", "p_draw", "p_home"]].to_numpy(),
            )
            folds[year] = fold
            pooled_labels.append(fold["labels"])
            pooled_probabilities.append(fold["probabilities"])
    except CandidateEvaluationFailure:
        raise
    except Exception as exc:
        raise CandidateEvaluationFailure(f"Candidate P fit/prediction failed: {exc}") from exc
    result = _finish_candidate(folds, pooled_labels, pooled_probabilities)
    _validate_candidate_alignment(result, a_result, "P")
    return result


def _evaluate_g(data: pd.DataFrame, a_result: dict) -> dict:
    folds, pooled_labels, pooled_probabilities = {}, [], []
    try:
        for year in FOLDS:
            train, validation = _fold_frames(data, year)
            model = fit_lightgbm_model(train)
            predicted = predict_g_proba(
                model,
                validation.loc[:, ["match_id", *G_FEATURES]],
            )
            if predicted["match_id"].astype(str).tolist() != validation["match_id"].astype(str).tolist():
                raise CandidateEvaluationFailure("Candidate G prediction identity/order mismatch")
            fold = _fold_output(
                train,
                validation,
                predicted.loc[:, ["p_away", "p_draw", "p_home"]].to_numpy(),
            )
            folds[year] = fold
            pooled_labels.append(fold["labels"])
            pooled_probabilities.append(fold["probabilities"])
    except CandidateEvaluationFailure:
        raise
    except Exception as exc:
        raise CandidateEvaluationFailure(f"Candidate G fit/prediction failed: {exc}") from exc
    result = _finish_candidate(folds, pooled_labels, pooled_probabilities)
    _validate_candidate_alignment(result, a_result, "G")
    return result


def _finish_candidate(folds, pooled_labels, pooled_probabilities) -> dict:
    labels = np.concatenate(pooled_labels)
    probabilities = np.vstack(pooled_probabilities)
    if len(labels) != EXPECTED_POOLED_VALIDATION:
        raise CandidateEvaluationFailure("Candidate pooled validation count mismatch")
    return {
        "folds": folds,
        "pooled": asdict(calculate_metrics(labels, probabilities)),
        "pooled_ids": [match_id for year in FOLDS for match_id in folds[year]["validation_ids"]],
        "pooled_labels": labels,
        "pooled_probabilities": probabilities,
    }


def _metric_delta(candidate: dict, baseline: dict) -> dict:
    return {
        key: float(candidate[key] - baseline[key])
        for key in ("accuracy", "log_loss", "brier")
    }


def frozen_decision(
    a_folds: dict,
    a_pooled: dict,
    candidate_folds: dict | None,
    candidate_pooled: dict | None,
    *,
    failed: bool = False,
) -> tuple[str, int]:
    if failed or candidate_folds is None or candidate_pooled is None:
        return INCONCLUSIVE, 0
    improved = sum(
        candidate_folds[year]["log_loss"] < a_folds[year]["log_loss"] for year in FOLDS
    )
    qualifies = (
        candidate_pooled["log_loss"] < a_pooled["log_loss"]
        and improved >= 3
        and candidate_pooled["brier"] <= a_pooled["brier"]
    )
    return (QUALIFIES if qualifies else CLOSE), improved


def retained_candidate(p: dict, g: dict) -> str | None:
    p_qualifies = p.get("decision") == QUALIFIES
    g_qualifies = g.get("decision") == QUALIFIES
    if not p_qualifies and not g_qualifies:
        return None
    if p_qualifies and not g_qualifies:
        return "P"
    if g_qualifies and not p_qualifies:
        return "G"
    p_metrics, g_metrics = p["pooled"], g["pooled"]
    ll_difference = p_metrics["log_loss"] - g_metrics["log_loss"]
    if abs(ll_difference) > 1e-12:
        return "P" if ll_difference < 0 else "G"
    brier_difference = p_metrics["brier"] - g_metrics["brier"]
    if abs(brier_difference) > 1e-12:
        return "P" if brier_difference < 0 else "G"
    return "P"


def _public_candidate_result(candidate: dict, a_result: dict, label: str) -> dict:
    a_fold_metrics = {year: a_result["folds"][year]["metrics"] for year in FOLDS}
    candidate_fold_metrics = {year: candidate["folds"][year]["metrics"] for year in FOLDS}
    decision, improved = frozen_decision(
        a_fold_metrics, a_result["pooled"], candidate_fold_metrics, candidate["pooled"]
    )
    return {
        "status": "PASS",
        "folds": {
            year: {
                "training_rows": candidate["folds"][year]["training_rows"],
                "validation_rows": candidate["folds"][year]["validation_rows"],
                **candidate_fold_metrics[year],
                "delta_vs_a": _metric_delta(candidate_fold_metrics[year], a_fold_metrics[year]),
            }
            for year in FOLDS
        },
        "pooled": candidate["pooled"],
        "pooled_delta_vs_a": _metric_delta(candidate["pooled"], a_result["pooled"]),
        "improved_log_loss_folds": improved,
        "decision": decision,
        "candidate": label,
    }


def _failed_candidate(label: str, exc: CandidateEvaluationFailure) -> dict:
    message = re.sub(r"\s+", " ", str(exc)).strip()[:500]
    return {
        "candidate": label,
        "status": "FAILED",
        "failure_type": type(exc).__name__,
        "failure_message": message,
        "improved_log_loss_folds": 0,
        "decision": INCONCLUSIVE,
    }


def _formal_from_context(
    context: _PreflightContext,
    *,
    p_runner: Callable[[pd.DataFrame, dict], dict] = _evaluate_p,
    g_runner: Callable[[pd.DataFrame, dict], dict] = _evaluate_g,
) -> dict:
    candidate_results = {}
    for label, runner in (("P", p_runner), ("G", g_runner)):
        try:
            internal = runner(context.state, context.a_result)
            candidate_results[label] = _public_candidate_result(
                internal, context.a_result, label
            )
        except CandidateEvaluationFailure as exc:
            candidate_results[label] = _failed_candidate(label, exc)
    a_public = {
        "folds": {
            year: {
                "training_rows": context.a_result["folds"][year]["training_rows"],
                "validation_rows": context.a_result["folds"][year]["validation_rows"],
                **context.a_result["folds"][year]["metrics"],
            }
            for year in FOLDS
        },
        "pooled": context.a_result["pooled"],
        "role": "Champion/reference",
    }
    return {
        "status": FORMAL_STATUS,
        "source_rows": EXPECTED_ROWS,
        "season_counts": EXPECTED_SEASON_COUNTS,
        "fold_counts": EXPECTED_FOLD_COUNTS,
        "a_reference_gate": "PASS",
        "A": a_public,
        "P": candidate_results["P"],
        "G": candidate_results["G"],
        "retained_candidate": retained_candidate(
            candidate_results["P"], candidate_results["G"]
        ),
        "champion": "A remains Champion/reference",
        "formal_attempt_status": "ATTEMPTED_ONCE",
        "feature_changes": "NO",
        "parameter_changes": "NO",
        "tuning": "NOT RUN",
        "adaptive_follow_up": "NOT RUN",
    }


def render_evaluation_markdown(result: dict) -> str:
    retained = (
        "null" if result["retained_candidate"] is None else result["retained_candidate"]
    )
    lines = [
        "# Frozen Model Architecture Benchmark Result",
        "",
        f"- Formal status: **{result['status']}**",
        f"- Source rows: **{result['source_rows']}**",
        f"- A reference gate: **{result['a_reference_gate']}**",
        f"- P decision: **{result['P']['decision']}**",
        f"- G decision: **{result['G']['decision']}**",
        f"- Retained candidate: **{retained}**",
        f"- Champion: **{result['champion']}**",
        f"- Formal attempt status: **{result['formal_attempt_status']}**",
        "",
        "## Source and folds",
        "",
        "| Season | Rows |",
        "|---:|---:|",
        *[f"| {year} | {count} |" for year, count in result["season_counts"].items()],
        "",
        "| Validation season | Training rows | Validation rows |",
        "|---:|---:|---:|",
        *[
            f"| {year} | {counts[0]} | {counts[1]} |"
            for year, counts in result["fold_counts"].items()
        ],
        "",
        "## Per-fold metrics",
        "",
        "| Candidate | Fold | Train | Validation | Accuracy | Log Loss | Brier |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for candidate in ("A", "P", "G"):
        entry = result[candidate]
        if entry.get("status") == "FAILED":
            lines.append(f"| {candidate} | failure | - | - | - | - | - |")
            continue
        for year in FOLDS:
            fold = entry["folds"][year]
            lines.append(
                f"| {candidate} | {year} | {fold['training_rows']} | {fold['validation_rows']} "
                f"| {fold['accuracy']:.15f} | {fold['log_loss']:.15f} | {fold['brier']:.15f} |"
            )
    lines.extend(["", "## Pooled metrics", ""])
    for candidate in ("A", "P", "G"):
        entry = result[candidate]
        if entry.get("status") == "FAILED":
            lines.append(
                f"- {candidate}: {entry['decision']} ({entry['failure_type']}: {entry['failure_message']})"
            )
        else:
            pooled = entry["pooled"]
            lines.append(
                f"- {candidate}: n={pooled['count']}, Accuracy={pooled['accuracy']:.15f}, "
                f"Log Loss={pooled['log_loss']:.15f}, Brier={pooled['brier']:.15f}"
            )
    lines.extend(
        [
            "",
            "## Candidate deltas vs A",
            "",
            "| Candidate | Scope | Delta Accuracy | Delta Log Loss | Delta Brier |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for candidate in ("P", "G"):
        entry = result[candidate]
        if entry.get("status") == "FAILED":
            lines.append(f"| {candidate} | failure | - | - | - |")
            continue
        for year in FOLDS:
            delta = entry["folds"][year]["delta_vs_a"]
            lines.append(
                f"| {candidate} | {year} | {delta['accuracy']:.15f} "
                f"| {delta['log_loss']:.15f} | {delta['brier']:.15f} |"
            )
        delta = entry["pooled_delta_vs_a"]
        lines.append(
            f"| {candidate} | pooled | {delta['accuracy']:.15f} "
            f"| {delta['log_loss']:.15f} | {delta['brier']:.15f} |"
        )
    lines.extend(
        [
            "",
            f"- P improved Log Loss folds: {result['P']['improved_log_loss_folds']} / 5",
            f"- G improved Log Loss folds: {result['G']['improved_log_loss_folds']} / 5",
            f"- Feature changes = {result['feature_changes']}",
            f"- Parameter changes = {result['parameter_changes']}",
            f"- Tuning = {result['tuning']}",
            f"- Adaptive follow-up = {result['adaptive_follow_up']}",
            "",
        ]
    )
    return "\n".join(lines)


def write_evaluation_markdown(result: dict, path: str | Path = RESULT_DOC_PATH) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(render_evaluation_markdown(result))
    except FileExistsError as exc:
        raise ArchitectureEvaluationError("Formal result document already exists") from exc
    return output


def _create_attempt_marker(path: str | Path) -> Path:
    marker = Path(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {
                    "status": "FORMAL_MODEL_ARCHITECTURE_BENCHMARK_ATTEMPTED",
                    "one_shot": True,
                },
                handle,
                indent=2,
            )
            handle.write("\n")
    except FileExistsError as exc:
        raise ArchitectureEvaluationError(
            "FORMAL_MODEL_ARCHITECTURE_BENCHMARK_ALREADY_ATTEMPTED"
        ) from exc
    return marker


def formal_evaluate(
    *,
    marker_path: str | Path = ATTEMPT_MARKER_PATH,
    result_path: str | Path = RESULT_DOC_PATH,
    write_report: bool = True,
    p_runner: Callable[[pd.DataFrame, dict], dict] = _evaluate_p,
    g_runner: Callable[[pd.DataFrame, dict], dict] = _evaluate_g,
    **preflight_kwargs,
) -> dict:
    """Run exactly one formal attempt after the complete A-only preflight."""
    context = _preflight_context(**preflight_kwargs)
    result_document = Path(result_path)
    marker = Path(marker_path)
    if result_document.exists():
        raise ArchitectureEvaluationError("Formal result document already exists")
    if marker.exists():
        raise ArchitectureEvaluationError(
            "FORMAL_MODEL_ARCHITECTURE_BENCHMARK_ALREADY_ATTEMPTED"
        )
    _create_attempt_marker(marker)
    result = _formal_from_context(context, p_runner=p_runner, g_runner=g_runner)
    if write_report:
        write_evaluation_markdown(result, result_document)
    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--formal", action="store_true")
    parser.add_argument("--confirm-one-shot", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.formal != args.confirm_one_shot:
        parser.error("formal execution requires both --formal and --confirm-one-shot")
    if args.formal:
        result = formal_evaluate()
        print(result["status"])
        print(f"P_DECISION={result['P']['decision']}")
        print(f"G_DECISION={result['G']['decision']}")
        print(f"RETAINED_CANDIDATE={result['retained_candidate']}")
        return 0
    result = preflight()
    print(result.status)
    print(f"SOURCE_ROWS={result.source_rows}")
    print(f"A_REFERENCE_GATE={result.a_reference_gate}")
    print("FORMAL_MODEL_ARCHITECTURE_BENCHMARK_NOT_RUN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
