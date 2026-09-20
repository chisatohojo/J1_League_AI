"""Fixed Dixon--Coles correction on the independent Poisson score model."""

from dataclasses import dataclass
from math import factorial

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from src.modeling.benchmark_suite import BENCHMARK_NAMES, _metrics, _predict_benchmarks, _with_replayed_elo
from src.modeling.poisson_score_rolling_validation import (
    MAX_GOALS,
    VALIDATION_SEASONS,
    _fit,
    _load_scores,
)

RHO_MIN = -0.20
RHO_MAX = 0.20


@dataclass(frozen=True)
class DixonColesRollingValidationResult:
    fold_metrics: dict[int, dict[str, object]]
    pooled_metrics: dict[str, object]
    rhos: dict[int, float]
    benchmark_pooled_metrics: dict[str, object]
    fold_counts: dict[int, tuple[int, int]]


def tau_correction(home_goals: int, away_goals: int, lambda_home: float,
                   lambda_away: float, rho: float) -> float:
    """Return the Dixon--Coles low-score correction factor."""
    if not RHO_MIN <= rho <= RHO_MAX:
        raise ValueError("rho is outside the fixed range [-0.20, 0.20].")
    if (home_goals, away_goals) == (0, 0):
        tau = 1.0 - lambda_home * lambda_away * rho
    elif (home_goals, away_goals) == (0, 1):
        tau = 1.0 + lambda_home * rho
    elif (home_goals, away_goals) == (1, 0):
        tau = 1.0 + lambda_away * rho
    elif (home_goals, away_goals) == (1, 1):
        tau = 1.0 - rho
    else:
        tau = 1.0
    if tau <= 0:
        raise ValueError("Dixon-Coles tau must be positive.")
    return tau


def run_dixon_coles_rolling_validation(dataset: pd.DataFrame) -> DixonColesRollingValidationResult:
    """Compare independent Poisson and Dixon--Coles on 2020--2024 OOF folds."""
    scores = _load_scores(dataset)
    rolling = scores.loc[scores["season"].between(2015, 2024)].copy(deep=True)
    fold_metrics = {}
    fold_counts = {}
    rhos = {}
    pooled = {"independent_poisson": [], "dixon_coles": []}
    pooled_targets = []
    for season in VALIDATION_SEASONS:
        train = rolling.loc[rolling["season"].between(2015, season - 1)].copy(deep=True)
        validation = rolling.loc[rolling["season"].eq(season)].copy(deep=True)
        fold_counts[season] = (len(train), len(validation))
        model = _fit(train)
        train_lambdas = _predict_lambdas(model, train)
        validation_lambdas = _predict_lambdas(model, validation)
        rho = _estimate_rho(train, train_lambdas)
        rhos[season] = rho
        independent = _score_probabilities_for_lambdas(validation_lambdas, rho=0.0)
        corrected = _score_probabilities_for_lambdas(validation_lambdas, rho=rho)
        target = validation["result"].to_numpy(copy=True)
        fold_metrics[season] = {
            "independent_poisson": _metrics(target, independent),
            "dixon_coles": _metrics(target, corrected),
        }
        pooled["independent_poisson"].append(independent)
        pooled["dixon_coles"].append(corrected)
        pooled_targets.append(target)
    pooled_targets_array = np.concatenate(pooled_targets)
    pooled_metrics = {
        name: _metrics(pooled_targets_array, np.concatenate(values))
        for name, values in pooled.items()
    }
    benchmark_pooled = _benchmark_rolling(dataset)
    return DixonColesRollingValidationResult(
        fold_metrics=fold_metrics,
        pooled_metrics=pooled_metrics,
        rhos=rhos,
        benchmark_pooled_metrics=benchmark_pooled,
        fold_counts=fold_counts,
    )


def _estimate_rho(train: pd.DataFrame, lambdas: np.ndarray) -> float:
    def negative_log_likelihood(rho: float) -> float:
        total = 0.0
        try:
            for row, (lambda_home, lambda_away) in zip(train.itertuples(index=False), lambdas):
                tau = tau_correction(row.home_score, row.away_score, lambda_home, lambda_away, rho)
                pmf = _poisson_pmf(row.home_score, lambda_home) * _poisson_pmf(row.away_score, lambda_away)
                total -= np.log(pmf * tau)
        except (ValueError, FloatingPointError):
            return float("inf")
        return total if np.isfinite(total) else float("inf")

    result = minimize_scalar(negative_log_likelihood, bounds=(RHO_MIN, RHO_MAX), method="bounded")
    if not result.success or not np.isfinite(result.x):
        raise ValueError("Dixon-Coles rho optimization failed.")
    # Recheck the selected value, including all observed train scorelines.
    for row, (lambda_home, lambda_away) in zip(train.itertuples(index=False), lambdas):
        tau_correction(row.home_score, row.away_score, lambda_home, lambda_away, float(result.x))
    return float(result.x)


def _score_probabilities_for_lambdas(lambdas: np.ndarray, rho: float) -> np.ndarray:
    return np.vstack([_score_probability(home, away, rho) for home, away in lambdas])


def _score_probability(lambda_home: float, lambda_away: float, rho: float) -> np.ndarray:
    goals = np.arange(MAX_GOALS + 1)
    home_pmf = np.exp(-lambda_home) * np.power(lambda_home, goals) / np.array([factorial(int(g)) for g in goals])
    away_pmf = np.exp(-lambda_away) * np.power(lambda_away, goals) / np.array([factorial(int(g)) for g in goals])
    matrix = np.outer(home_pmf, away_pmf)
    for home_goals, away_goals in ((0, 0), (0, 1), (1, 0), (1, 1)):
        matrix[home_goals, away_goals] *= tau_correction(
            home_goals, away_goals, lambda_home, lambda_away, rho,
        )
    probabilities = np.array([
        np.triu(matrix, k=1).sum(),
        np.trace(matrix),
        np.tril(matrix, k=-1).sum(),
    ])
    return probabilities / probabilities.sum()


def _predict_lambdas(model, matches: pd.DataFrame) -> np.ndarray:
    home_rows = matches.loc[:, ["home_team_id", "away_team_id"]].rename(columns={
        "home_team_id": "attacking_team", "away_team_id": "defending_team",
    }).assign(is_home=1)
    away_rows = matches.loc[:, ["away_team_id", "home_team_id"]].rename(columns={
        "away_team_id": "attacking_team", "home_team_id": "defending_team",
    }).assign(is_home=0)
    lambdas = np.column_stack([
        model.predict(home_rows[["attacking_team", "defending_team", "is_home"]]),
        model.predict(away_rows[["attacking_team", "defending_team", "is_home"]]),
    ])
    if not np.isfinite(lambdas).all() or (lambdas <= 0).any():
        raise ValueError("Poisson lambdas must be finite and positive.")
    return lambdas


def _poisson_pmf(goals: int, lam: float) -> float:
    return float(np.exp(-lam) * lam ** goals / factorial(int(goals)))


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
    return {
        name: _metrics(np.concatenate(targets[name]), np.concatenate(probabilities[name]))
        for name in BENCHMARK_NAMES
    }
