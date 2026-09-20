"""Fixed time-decay comparison for the independent Poisson score model."""

from dataclasses import dataclass
from datetime import timedelta
import math

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.modeling.benchmark_suite import BENCHMARK_NAMES, _metrics, _predict_benchmarks, _with_replayed_elo
from src.modeling.poisson_score_rolling_validation import (
    VALIDATION_SEASONS,
    _fit,
    _load_scores,
    _score_probabilities,
)

HALF_LIFE_CANDIDATES = (None, 180, 365, 730)
POISSON_COLUMNS = ("attacking_team", "defending_team", "is_home")


@dataclass(frozen=True)
class TimeDecayRollingValidationResult:
    fold_metrics: dict[int, dict[object, object]]
    pooled_metrics: dict[object, object]
    benchmark_pooled_metrics: dict[str, object]
    weight_summaries: dict[int, dict[object, dict[str, float]]]
    fold_counts: dict[int, tuple[int, int]]


def decay_weight(age_days: int | float, half_life_days: int | float) -> float:
    if isinstance(age_days, bool) or age_days < 0:
        raise ValueError("age_days must be nonnegative and not bool.")
    if isinstance(half_life_days, bool) or half_life_days <= 0:
        raise ValueError("half_life_days must be positive and not bool.")
    return float(math.exp(-math.log(2.0) * age_days / half_life_days))


def run_poisson_time_decay_rolling_validation(dataset: pd.DataFrame) -> TimeDecayRollingValidationResult:
    scores = _load_scores(dataset)
    rolling = scores.loc[scores["season"].between(2015, 2024)].copy(deep=True)
    rolling["match_date"] = pd.to_datetime(
        dataset.set_index("match_id").loc[rolling["match_id"], "match_date"].to_numpy(), errors="raise",
    )
    fold_metrics = {}
    weight_summaries = {}
    fold_counts = {}
    pooled_targets = {candidate: [] for candidate in HALF_LIFE_CANDIDATES}
    pooled_probabilities = {candidate: [] for candidate in HALF_LIFE_CANDIDATES}
    for season in VALIDATION_SEASONS:
        train = rolling.loc[rolling["season"].between(2015, season - 1)].copy(deep=True)
        validation = rolling.loc[rolling["season"].eq(season)].copy(deep=True)
        fold_counts[season] = (len(train), len(validation))
        reference_date = validation["match_date"].min()
        fold_metrics[season] = {}
        weight_summaries[season] = {}
        target = validation["result"].to_numpy(copy=True)
        for half_life in HALF_LIFE_CANDIDATES:
            weights = _match_weights(train, reference_date, half_life)
            model = _fit_weighted(train, weights)
            lambdas = _predict_lambdas(model, validation)
            probabilities = np.vstack([_score_probabilities(home, away) for home, away in lambdas])
            fold_metrics[season][half_life] = _metrics(target, probabilities)
            pooled_targets[half_life].append(target.copy())
            pooled_probabilities[half_life].append(probabilities.copy())
            weight_summaries[season][half_life] = _weight_summary(weights)
    pooled_metrics = {
        candidate: _metrics(np.concatenate(pooled_targets[candidate]), np.concatenate(pooled_probabilities[candidate]))
        for candidate in HALF_LIFE_CANDIDATES
    }
    return TimeDecayRollingValidationResult(
        fold_metrics=fold_metrics,
        pooled_metrics=pooled_metrics,
        benchmark_pooled_metrics=_benchmark_rolling(dataset),
        weight_summaries=weight_summaries,
        fold_counts=fold_counts,
    )


def _match_weights(train: pd.DataFrame, reference_date: pd.Timestamp, half_life: int | None) -> np.ndarray:
    dates = pd.to_datetime(train["match_date"], errors="raise")
    ages = (reference_date - dates).dt.days.to_numpy()
    if (ages < 0).any():
        raise ValueError("Train match occurs after validation reference date.")
    if half_life is None:
        return np.ones(len(train), dtype=float)
    return np.array([decay_weight(age, half_life) for age in ages], dtype=float)


def _fit_weighted(matches: pd.DataFrame, match_weights: np.ndarray) -> Pipeline:
    observations = pd.concat([
        matches[["home_team_id", "away_team_id", "home_score"]].rename(columns={
            "home_team_id": "attacking_team", "away_team_id": "defending_team", "home_score": "goals",
        }).assign(is_home=1),
        matches[["away_team_id", "home_team_id", "away_score"]].rename(columns={
            "away_team_id": "attacking_team", "home_team_id": "defending_team", "away_score": "goals",
        }).assign(is_home=0),
    ], ignore_index=True)
    sample_weights = np.repeat(match_weights, 2)
    preprocessor = ColumnTransformer([
        ("teams", OneHotEncoder(handle_unknown="ignore"), ["attacking_team", "defending_team"]),
        ("home", "passthrough", ["is_home"]),
    ])
    model = Pipeline([
        ("features", preprocessor),
        ("poisson", PoissonRegressor(alpha=1e-6, max_iter=1000)),
    ])
    model.fit(observations.loc[:, list(POISSON_COLUMNS)], observations["goals"],
              poisson__sample_weight=sample_weights)
    return model


def _predict_lambdas(model: Pipeline, matches: pd.DataFrame) -> np.ndarray:
    home = matches[["home_team_id", "away_team_id"]].rename(columns={
        "home_team_id": "attacking_team", "away_team_id": "defending_team",
    }).assign(is_home=1)
    away = matches[["away_team_id", "home_team_id"]].rename(columns={
        "away_team_id": "attacking_team", "home_team_id": "defending_team",
    }).assign(is_home=0)
    lambdas = np.column_stack([
        model.predict(home[list(POISSON_COLUMNS)]), model.predict(away[list(POISSON_COLUMNS)]),
    ])
    if not np.isfinite(lambdas).all() or (lambdas <= 0).any():
        raise ValueError("Poisson lambdas must be finite and positive.")
    return lambdas


def _weight_summary(weights: np.ndarray) -> dict[str, float]:
    return {
        "min": float(weights.min()), "median": float(np.median(weights)), "max": float(weights.max()),
        "effective_sample_size": float(weights.sum() ** 2 / np.square(weights).sum()),
    }


def _benchmark_rolling(dataset: pd.DataFrame) -> dict[str, object]:
    source = dataset.loc[dataset["season"].between(2015, 2024)].copy(deep=True)
    targets = {name: [] for name in BENCHMARK_NAMES}
    probabilities = {name: [] for name in BENCHMARK_NAMES}
    for season in VALIDATION_SEASONS:
        train = source.loc[source["season"].between(2015, season - 1)].copy(deep=True)
        validation = source.loc[source["season"].eq(season)].copy(deep=True)
        train, validation = _with_replayed_elo(source, train, validation, season)
        predicted = _predict_benchmarks(train, validation)
        target = validation["result"].to_numpy(copy=True)
        for name, values in predicted.items():
            targets[name].append(target)
            probabilities[name].append(values)
    return {name: _metrics(np.concatenate(targets[name]), np.concatenate(probabilities[name])) for name in BENCHMARK_NAMES}
