"""Fixed benchmark suite for the J1 probability model."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_elo_home_advantage_tuning import FEATURE_COLUMNS, _replay
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
BENCHMARK_NAMES = ("uniform", "train_prior", "elo_only", "champion")
ELO_FEATURES = ("elo_diff",)
K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0


@dataclass(frozen=True)
class BenchmarkResult:
    rolling_fold_metrics: dict[int, dict[str, FormLogisticMetrics]]
    rolling_pooled_metrics: dict[str, FormLogisticMetrics]
    test_metrics: dict[str, FormLogisticMetrics]
    fold_counts: dict[int, tuple[int, int]]
    test_counts: tuple[int, int]


def run_benchmark_suite(dataset: pd.DataFrame) -> BenchmarkResult:
    """Evaluate fixed benchmarks on rolling OOF and the one-time 2025 holdout."""
    missing = set(DATASET_COLUMNS) - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if dataset["match_id"].isna().any() or not dataset["match_id"].is_unique:
        raise ValueError("match_id must be unique and nonmissing.")
    if not dataset["season"].isin(range(2015, 2027)).all():
        raise ValueError("Unexpected season in input dataset.")

    rolling = dataset.loc[dataset["season"].between(2015, 2024)].copy(deep=True)
    fold_metrics = {}
    fold_counts = {}
    pooled_targets = {name: [] for name in BENCHMARK_NAMES}
    pooled_probabilities = {name: [] for name in BENCHMARK_NAMES}
    for validation_season in VALIDATION_SEASONS:
        train = rolling.loc[rolling["season"].between(2015, validation_season - 1)].copy(deep=True)
        validation = rolling.loc[rolling["season"].eq(validation_season)].copy(deep=True)
        fold_counts[validation_season] = (len(train), len(validation))
        train, validation = _with_replayed_elo(rolling, train, validation, validation_season)
        probabilities = _predict_benchmarks(train, validation)
        target = validation["result"].to_numpy(copy=True)
        fold_metrics[validation_season] = {name: _metrics(target, p) for name, p in probabilities.items()}
        for name, p in probabilities.items():
            pooled_targets[name].append(target.copy())
            pooled_probabilities[name].append(p.copy())

    pooled_metrics = {
        name: _metrics(np.concatenate(pooled_targets[name]), np.concatenate(pooled_probabilities[name]))
        for name in BENCHMARK_NAMES
    }

    full = dataset.loc[dataset["season"].between(2015, 2025)].copy(deep=True)
    train = full.loc[full["season"].between(2015, 2024)].copy(deep=True)
    test = full.loc[full["season"].eq(2025)].copy(deep=True)
    if len(train) != 3208 or len(test) != 380:
        raise ValueError(f"Expected 2025 split 3208/380, got {len(train)}/{len(test)}.")
    train, test = _with_replayed_elo(full, train, test, 2025)
    test_probabilities = _predict_benchmarks(train, test)
    test_metrics = {
        name: _metrics(test["result"].to_numpy(copy=True), p)
        for name, p in test_probabilities.items()
    }
    return BenchmarkResult(fold_metrics, pooled_metrics, test_metrics, fold_counts, (len(train), len(test)))


def _with_replayed_elo(source, train, validation, end_season):
    base = source.loc[source["season"].between(2015, end_season)]
    frames = tuple(
        base.loc[base["season"].eq(season),
                  ["match_id", "season", "home_team_id", "away_team_id", "result"]].copy(deep=True)
        for season in range(2015, end_season + 1)
    )
    replay = _replay(frames, HOME_ADVANTAGE).set_index("match_id")
    allowed = pd.concat([train, validation], ignore_index=True)
    if set(replay.index) != set(allowed["match_id"]):
        raise ValueError(f"Elo replay mismatch through season {end_season}.")
    allowed["elo_diff"] = replay.loc[allowed["match_id"], "elo_diff"].to_numpy()
    return allowed.iloc[:len(train)].copy(deep=True), allowed.iloc[len(train):].copy(deep=True)


def _predict_benchmarks(train, validation):
    count = len(validation)
    uniform = np.full((count, 3), 1.0 / 3.0)
    prior_counts = train["result"].value_counts().reindex(CLASS_ORDER, fill_value=0).to_numpy(dtype=float)
    prior = prior_counts / prior_counts.sum()
    prior_probabilities = np.tile(prior, (count, 1))
    return {
        "uniform": uniform,
        "train_prior": prior_probabilities,
        "elo_only": _fit_logistic(train, validation, ELO_FEATURES),
        "champion": _fit_logistic(train, validation, FEATURE_COLUMNS),
    }


def _fit_logistic(train, validation, columns):
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)),
    ])
    model.fit(train.loc[:, columns], train["result"])
    if not np.array_equal(model.classes_, CLASS_ORDER):
        raise ValueError("Expected class order [0, 1, 2].")
    return model.predict_proba(validation.loc[:, columns])


def _metrics(target, probabilities):
    one_hot = (target[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(
        accuracy=float(accuracy_score(target, np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)])),
        log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
    )
