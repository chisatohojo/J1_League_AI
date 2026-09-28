"""Frozen one-shot rolling OOF evaluation for the strict-prior H2H family.

The public ``evaluate`` entry point is intentionally not called by the test
suite in this lane.  It exists for the separately authorized formal run.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.h2h import (
    EXPECTED_AVAILABILITY,
    EXPECTED_PRIOR_COUNT_BINS,
    OUTPUT_COLUMNS,
    load_j1_matches,
)
from src.modeling.player_workload_evaluation import (
    CLASS_ORDER,
    _add_elo,
    _metrics,
    _validate_probabilities,
)


ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
H2H_PATH = ROOT / "data/processed/features/2015_2024_j1_h2h_features.csv"
H2H_SHA256 = "ab51fd674ee1665591e4b4b152a92f12ffd020211db3e541047c3066815784ff"
FOLDS = (2020, 2021, 2022, 2023, 2024)
S0_FEATURES = ("elo_diff",)
S1_FEATURES = (
    "elo_diff",
    "prior_h2h_match_count",
    "prior_h2h_home_team_win_count",
    "prior_h2h_draw_count",
)
MODEL_PARAMS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
EXPECTED_FOLD_COUNTS = {
    2020: (1530, 306),
    2021: (1836, 380),
    2022: (2216, 306),
    2023: (2522, 306),
    2024: (2828, 380),
}
EXPECTED_A_Y_LL = {
    2020: 1.023119734659012,
    2021: 1.0253437210487792,
    2022: 1.0940186385371449,
    2023: 1.0604285568595655,
    2024: 1.079241181120235,
}
EXPECTED_A_Y_POOLED = {
    "accuracy": 0.466626936829559,
    "log_loss": 1.056065401323764,
    "brier": 0.6357323419292724,
    "count": 1678,
}
TARGET_IDENTITY = ("match_id", "match_date", "season", "home_team_id", "away_team_id")
AUDIT_COLUMNS = ("h2h_available", "previous_h2h_match_id", "previous_h2h_match_date")
MODEL_CANDIDATES = S1_FEATURES[1:]
EXISTING_BASELINE_PREDICTION_REUSED = False


class H2HEvaluationError(ValueError):
    """A frozen H2H evaluation gate or invariant failed."""


def artifact_sha256(path: str | Path = H2H_PATH) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def assert_artifact_sha(path: str | Path = H2H_PATH) -> None:
    actual = artifact_sha256(path)
    if actual != H2H_SHA256:
        raise H2HEvaluationError("BLOCKED_REFERENCE_MISMATCH: artifact SHA-256")


def _read_artifact(path: str | Path = H2H_PATH) -> pd.DataFrame:
    return pd.read_csv(
        path,
        dtype={
            "match_id": "string",
            "home_team_id": "string",
            "away_team_id": "string",
            "previous_h2h_match_id": "string",
            "previous_h2h_match_date": "string",
        },
        keep_default_na=True,
    )


def _assert_bool(value, label: str) -> None:
    if pd.isna(value) or value not in (True, False):
        raise H2HEvaluationError(f"Invalid boolean: {label}")


def validate_artifact(targets: pd.DataFrame, artifact: pd.DataFrame) -> None:
    """Validate artifact identity, schema, structural zeros, and invariants."""
    if tuple(artifact.columns) != OUTPUT_COLUMNS or len(artifact.columns) != 11:
        raise H2HEvaluationError("H2H artifact schema mismatch")
    if len(artifact) != 3208 or not artifact.match_id.is_unique:
        raise H2HEvaluationError("H2H artifact row/unique-ID mismatch")
    if len(targets) != 3208 or not targets.match_id.is_unique:
        raise H2HEvaluationError("Target row/unique-ID mismatch")

    target_ids = set(targets.match_id.astype(str))
    feature_ids = set(artifact.match_id.astype(str))
    if target_ids != feature_ids:
        raise H2HEvaluationError("Target and feature match-ID sets differ")
    left = targets.loc[:, list(TARGET_IDENTITY)].copy()
    right = artifact.loc[:, list(TARGET_IDENTITY)].copy()
    left["match_id"] = left.match_id.astype(str)
    right["match_id"] = right.match_id.astype(str)
    if not artifact.match_date.astype(str).str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}").all():
        raise H2HEvaluationError("Artifact match_date is not ISO YYYY-MM-DD")
    prior_dates = artifact.previous_h2h_match_date.dropna().astype(str)
    if not prior_dates.str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}").all():
        raise H2HEvaluationError("Artifact previous_h2h_match_date is not ISO YYYY-MM-DD")
    right["match_date"] = pd.to_datetime(right.match_date, errors="raise")
    left["match_date"] = pd.to_datetime(left.match_date, errors="raise")
    joined = left.merge(right, on="match_id", suffixes=("_target", "_feature"), validate="one_to_one")
    for column in ("match_date", "season", "home_team_id", "away_team_id"):
        target_column = f"{column}_target"
        feature_column = f"{column}_feature"
        if not joined[target_column].eq(joined[feature_column]).all():
            raise H2HEvaluationError(f"Target/feature identity mismatch: {column}")

    for column in MODEL_CANDIDATES:
        values = artifact[column]
        if values.isna().any() or not pd.api.types.is_integer_dtype(values):
            raise H2HEvaluationError(f"Invalid candidate type/null: {column}")
        if values.lt(0).any():
            raise H2HEvaluationError(f"Negative candidate: {column}")
    total = artifact["prior_h2h_match_count"]
    wins = artifact["prior_h2h_home_team_win_count"]
    draws = artifact["prior_h2h_draw_count"]
    if (wins + draws > total).any():
        raise H2HEvaluationError("H2H W+D exceeds total")
    away_wins = total - wins - draws
    if away_wins.lt(0).any() or not pd.api.types.is_integer_dtype(away_wins):
        raise H2HEvaluationError("Invalid derived away wins")

    dates = pd.to_datetime(artifact.match_date, errors="raise")
    if (dates.dt.year != artifact.season).any():
        raise H2HEvaluationError("Artifact season/date mismatch")
    for row in artifact.itertuples(index=False):
        _assert_bool(row.h2h_available, row.match_id)
        if row.prior_h2h_match_count == 0:
            if row.h2h_available or pd.notna(row.previous_h2h_match_id) or pd.notna(row.previous_h2h_match_date):
                raise H2HEvaluationError(f"Structural zero mismatch: {row.match_id}")
            if row.prior_h2h_home_team_win_count != 0 or row.prior_h2h_draw_count != 0:
                raise H2HEvaluationError(f"Structural zero counts mismatch: {row.match_id}")
        else:
            if not row.h2h_available or pd.isna(row.previous_h2h_match_id) or pd.isna(row.previous_h2h_match_date):
                raise H2HEvaluationError(f"Available audit mismatch: {row.match_id}")
            if pd.Timestamp(row.previous_h2h_match_date) >= pd.Timestamp(row.match_date):
                raise H2HEvaluationError(f"Previous H2H is not strictly prior: {row.match_id}")


def validate_frozen_distributions(artifact: pd.DataFrame) -> None:
    availability = {}
    for season, rows in artifact.groupby("season", sort=True):
        available = rows.h2h_available.astype(bool)
        availability[int(season)] = (int(available.sum()), int((~available).sum()))
    if availability != EXPECTED_AVAILABILITY:
        raise H2HEvaluationError(f"Availability reference mismatch: {availability}")
    counts = artifact.prior_h2h_match_count
    bins = {
        "0": int(counts.eq(0).sum()),
        "1": int(counts.eq(1).sum()),
        "2": int(counts.eq(2).sum()),
        "3": int(counts.eq(3).sum()),
        "4": int(counts.eq(4).sum()),
        "5-9": int(counts.between(5, 9).sum()),
        "10+": int(counts.ge(10).sum()),
    }
    if bins != EXPECTED_PRIOR_COUNT_BINS:
        raise H2HEvaluationError(f"Prior-count reference mismatch: {bins}")


def _fit(train: pd.DataFrame, validation: pd.DataFrame, features) -> np.ndarray:
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(**MODEL_PARAMS)),
    ])
    model.fit(train.loc[:, features], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise H2HEvaluationError("Expected probability class order [0, 1, 2]")
    return _validate_probabilities(model.predict_proba(validation.loc[:, features]))


def _metric_dict(labels, probabilities) -> dict:
    return asdict(_metrics(labels, probabilities))


def assert_same_fold_inputs(
    s0_train: pd.DataFrame,
    s1_train: pd.DataFrame,
    s0_validation: pd.DataFrame,
    s1_validation: pd.DataFrame,
) -> None:
    """Require identical match IDs and labels for the matched S0/S1 folds."""
    for left, right, label in (
        (s0_train, s1_train, "training"),
        (s0_validation, s1_validation, "validation"),
    ):
        if left.match_id.astype(str).tolist() != right.match_id.astype(str).tolist():
            raise H2HEvaluationError(f"S0/S1 {label} match IDs differ")
        if left.result.astype(int).tolist() != right.result.astype(int).tolist():
            raise H2HEvaluationError(f"S0/S1 {label} labels differ")


def assert_a_y_references(folds: dict, pooled: dict) -> None:
    for season in FOLDS:
        actual = folds[season]["s0"]["log_loss"]
        if not np.isclose(actual, EXPECTED_A_Y_LL[season], rtol=0, atol=1e-12):
            raise H2HEvaluationError(f"BLOCKED_REFERENCE_MISMATCH: A_Y {season} Log Loss")
    for metric in ("accuracy", "log_loss", "brier"):
        if not np.isclose(pooled[metric], EXPECTED_A_Y_POOLED[metric], rtol=0, atol=1e-12):
            raise H2HEvaluationError(f"BLOCKED_REFERENCE_MISMATCH: pooled A_Y {metric}")
    if pooled["count"] != EXPECTED_A_Y_POOLED["count"]:
        raise H2HEvaluationError("BLOCKED_REFERENCE_MISMATCH: pooled A_Y count")


def frozen_decision(folds: dict, pooled: dict) -> str:
    improved = sum(folds[season]["s1"]["log_loss"] < folds[season]["s0"]["log_loss"] for season in FOLDS)
    non_improved = sum(folds[season]["s1"]["log_loss"] >= folds[season]["s0"]["log_loss"] for season in FOLDS)
    if pooled["s1"]["log_loss"] < pooled["s0"]["log_loss"] and pooled["s1"]["brier"] < pooled["s0"]["brier"] and improved >= 3:
        return "CONTINUE_H2H_LANE"
    if pooled["s1"]["log_loss"] >= pooled["s0"]["log_loss"] and pooled["s1"]["brier"] >= pooled["s0"]["brier"] and non_improved >= 3:
        return "CLOSE_RETROSPECTIVE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def _draw_diagnostic(labels, s0_probabilities, s1_probabilities) -> dict:
    labels = np.asarray(labels, dtype=int)
    return {
        "actual": np.bincount(labels, minlength=3).astype(int).tolist(),
        "s0_argmax": np.bincount(np.asarray(CLASS_ORDER)[s0_probabilities.argmax(axis=1)], minlength=3).astype(int).tolist(),
        "s1_argmax": np.bincount(np.asarray(CLASS_ORDER)[s1_probabilities.argmax(axis=1)], minlength=3).astype(int).tolist(),
        "s0_mean_draw_probability": float(s0_probabilities[:, 1].mean()),
        "s1_mean_draw_probability": float(s1_probabilities[:, 1].mean()),
        "delta_mean_draw_probability": float(s1_probabilities[:, 1].mean() - s0_probabilities[:, 1].mean()),
    }


def _validate_fold_counts(data: pd.DataFrame) -> None:
    for season, (train_n, validation_n) in EXPECTED_FOLD_COUNTS.items():
        observed = (int(data.season.lt(season).sum()), int(data.season.eq(season).sum()))
        if observed != (train_n, validation_n):
            raise H2HEvaluationError(f"Fold-count mismatch for {season}: {observed}")


def _prepare_data(match_dir: str | Path, artifact_path: str | Path) -> pd.DataFrame:
    assert_artifact_sha(artifact_path)
    targets = load_j1_matches(match_dir)
    artifact = _read_artifact(artifact_path)
    validate_artifact(targets, artifact)
    validate_frozen_distributions(artifact)
    _validate_fold_counts(targets)
    elo = _add_elo(targets)
    artifact_for_join = artifact.drop(columns=["match_date", "season", "home_team_id", "away_team_id"])
    data = elo.merge(artifact_for_join, on="match_id", validate="one_to_one")
    return data


def evaluate(*, match_dir: str | Path = MATCH_DIR, artifact_path: str | Path = H2H_PATH) -> dict:
    """Run the one frozen formal H2H evaluation.

    This function is intentionally not called by ``tests/test_h2h_evaluation.py``.
    Its gate order makes an A_Y reference mismatch fail before any S1 fit.
    """
    data = _prepare_data(match_dir, artifact_path)
    folds = {}
    pooled_labels = []
    pooled_s0 = []
    for season in FOLDS:
        train = data.loc[data.season.lt(season)].copy()
        validation = data.loc[data.season.eq(season)].copy()
        s0_probabilities = _fit(train, validation, S0_FEATURES)
        labels = validation.result.to_numpy()
        folds[season] = {
            "train_n": len(train),
            "validation_n": len(validation),
            "s0": _metric_dict(labels, s0_probabilities),
        }
        pooled_labels.append(labels)
        pooled_s0.append(s0_probabilities)
    pooled_labels_array = np.concatenate(pooled_labels)
    pooled_s0_array = np.concatenate(pooled_s0)
    pooled_s0_metrics = _metric_dict(pooled_labels_array, pooled_s0_array)
    assert_a_y_references(folds, pooled_s0_metrics)

    pooled_s1 = []
    for season in FOLDS:
        train = data.loc[data.season.lt(season)].copy()
        validation = data.loc[data.season.eq(season)].copy()
        assert_same_fold_inputs(train, train, validation, validation)
        s1_probabilities = _fit(train, validation, S1_FEATURES)
        labels = validation.result.to_numpy()
        folds[season]["s1"] = _metric_dict(labels, s1_probabilities)
        folds[season]["draw_diagnostic"] = _draw_diagnostic(labels, pooled_s0[ FOLDS.index(season) ], s1_probabilities)
        pooled_s1.append(s1_probabilities)
    pooled_s1_array = np.concatenate(pooled_s1)
    pooled_metrics = {"s0": pooled_s0_metrics, "s1": _metric_dict(pooled_labels_array, pooled_s1_array)}
    pooled_metrics["delta"] = {
        metric: pooled_metrics["s1"][metric] - pooled_metrics["s0"][metric]
        for metric in ("accuracy", "log_loss", "brier")
    }
    pooled_metrics["draw_diagnostic"] = _draw_diagnostic(pooled_labels_array, pooled_s0_array, pooled_s1_array)
    return {
        "status": "PASS",
        "baseline_sanity": "PASS",
        "folds": folds,
        "pooled": pooled_metrics,
        "decision": frozen_decision(folds, pooled_metrics),
        "s1_log_loss_improved_folds": sum(folds[season]["s1"]["log_loss"] < folds[season]["s0"]["log_loss"] for season in FOLDS),
        "existing_baseline_prediction_reused": False,
    }
