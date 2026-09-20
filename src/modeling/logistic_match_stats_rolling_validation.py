"""Expanding-window validation for the fixed match-stat ablation."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_elo_home_advantage_tuning import FEATURE_COLUMNS, _replay
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.logistic_match_stats_ablation import (
    CK_FEATURES,
    FK_FEATURES,
    HOME_ADVANTAGE,
    SHOTS_FEATURES,
)

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
FEATURE_SETS = {
    "A_baseline": FEATURE_COLUMNS,
    "B_baseline_plus_shots": FEATURE_COLUMNS + SHOTS_FEATURES,
    "C_baseline_plus_ck": FEATURE_COLUMNS + CK_FEATURES,
    "D_baseline_plus_fk": FEATURE_COLUMNS + FK_FEATURES,
    "E_baseline_plus_all": FEATURE_COLUMNS + MATCH_STATS_FORM_COLUMNS,
}


@dataclass(frozen=True)
class RollingValidationResult:
    fold_metrics: dict[int, dict[str, FormLogisticMetrics]]
    pooled_metrics: dict[str, FormLogisticMetrics]
    fold_counts: dict[int, tuple[int, int]]


def run_logistic_match_stats_rolling_validation(
    dataset: pd.DataFrame,
) -> RollingValidationResult:
    """Run fixed 2020--2024 expanding-window validation and pooled OOF scoring."""
    required = set(DATASET_COLUMNS) | set(MATCH_STATS_FORM_COLUMNS)
    missing = required - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    base = dataset.loc[:, list(DATASET_COLUMNS)].copy(deep=True)
    if not base["season"].isin(range(2015, 2026)).all():
        raise ValueError("Rolling validation accepts ordinary seasons 2015-2025 only.")
    if not base["match_id"].is_unique or base["match_id"].isna().any():
        raise ValueError("match_id must be unique and nonmissing.")
    if not pd.to_datetime(base["match_date"], errors="raise").is_monotonic_increasing:
        raise ValueError("match_date must be chronological.")

    # 2025 may be present in the supplied training dataset, but is excluded
    # before any fit, replay, prediction, or aggregate calculation.
    source = dataset.loc[dataset["season"].between(2015, 2024)].copy(deep=True)
    base = base.loc[base["season"].between(2015, 2024)].copy(deep=True)
    fold_metrics = {}
    fold_counts = {}
    pooled_targets = {name: [] for name in FEATURE_SETS}
    pooled_probabilities = {name: [] for name in FEATURE_SETS}

    for validation_season in VALIDATION_SEASONS:
        train_mask = source["season"].between(2015, validation_season - 1)
        validation_mask = source["season"].eq(validation_season)
        train = source.loc[train_mask].copy(deep=True)
        validation = source.loc[validation_mask].copy(deep=True)
        fold_counts[validation_season] = (len(train), len(validation))
        frames = tuple(
            base.loc[base["season"].between(2015, validation_season) & base["season"].eq(season),
                       ["match_id", "season", "home_team_id", "away_team_id", "result"]].copy(deep=True)
            for season in range(2015, validation_season + 1)
        )
        replay = _replay(frames, HOME_ADVANTAGE).set_index("match_id")
        allowed = pd.concat([train, validation], ignore_index=True)
        if set(replay.index) != set(allowed["match_id"]):
            raise ValueError(f"Elo replay mismatch in validation season {validation_season}.")
        replay_ids = allowed["match_id"]
        allowed = allowed.copy(deep=True)
        allowed["elo_diff"] = replay.loc[replay_ids, "elo_diff"].to_numpy()
        train = allowed.iloc[:len(train)].copy(deep=True)
        validation = allowed.iloc[len(train):].copy(deep=True)
        fold_metrics[validation_season] = {}
        for name, columns in FEATURE_SETS.items():
            metrics, probabilities = _fit_and_score(train, validation, columns)
            fold_metrics[validation_season][name] = metrics
            pooled_targets[name].append(validation["result"].to_numpy(copy=True))
            pooled_probabilities[name].append(probabilities)

    pooled_metrics = {}
    for name in FEATURE_SETS:
        targets = np.concatenate(pooled_targets[name])
        probabilities = np.concatenate(pooled_probabilities[name], axis=0)
        pooled_metrics[name] = _metrics(targets, probabilities)
    return RollingValidationResult(fold_metrics, pooled_metrics, fold_counts)


def _fit_and_score(train: pd.DataFrame, validation: pd.DataFrame, columns: tuple[str, ...]):
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)),
    ])
    model.fit(train.loc[:, columns], train["result"])
    if not np.array_equal(model.classes_, CLASS_ORDER):
        raise ValueError("Expected class order [0, 1, 2].")
    probabilities = model.predict_proba(validation.loc[:, columns])
    return _metrics(validation["result"].to_numpy(), probabilities), probabilities


def _metrics(target: np.ndarray, probabilities: np.ndarray) -> FormLogisticMetrics:
    one_hot = (target[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(
        accuracy=float(accuracy_score(target, np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)])),
        log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
    )
