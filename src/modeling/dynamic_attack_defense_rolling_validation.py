"""Walk-forward dynamic attack/defense Poisson baseline."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.benchmark_suite import _metrics
from src.modeling.poisson_score_rolling_validation import (
    VALIDATION_SEASONS,
    _load_scores,
    _score_probabilities,
)

UPDATE_RATE = 0.05
MAX_GOALS = 15


@dataclass(frozen=True)
class DynamicAttackDefenseResult:
    fold_metrics: dict[int, object]
    pooled_metrics: object
    fold_counts: dict[int, tuple[int, int]]
    diagnostics: dict[int, object]
    benchmark_pooled_metrics: dict[str, object]


def expected_goals(
    base_home_goals: float,
    base_away_goals: float,
    home_attack: float,
    away_defense: float,
    away_attack: float,
    home_defense: float,
) -> tuple[float, float]:
    home = base_home_goals * np.exp(home_attack - away_defense)
    away = base_away_goals * np.exp(away_attack - home_defense)
    if not np.isfinite((home, away)).all() or home <= 0 or away <= 0:
        raise ValueError("Expected goals must be finite and positive.")
    return float(home), float(away)


def update_ratings(
    ratings: dict[str, tuple[float, float]],
    home_team: str,
    away_team: str,
    home_score: float,
    away_score: float,
    base_home_goals: float,
    base_away_goals: float,
    update_rate: float = UPDATE_RATE,
) -> tuple[float, float]:
    """Update after prediction and return the pre-update lambdas."""
    _register(ratings, home_team)
    _register(ratings, away_team)
    home_attack, home_defense = ratings[home_team]
    away_attack, away_defense = ratings[away_team]
    lambdas = expected_goals(
        base_home_goals, base_away_goals, home_attack, away_defense,
        away_attack, home_defense,
    )
    home_residual = home_score - lambdas[0]
    away_residual = away_score - lambdas[1]
    ratings[home_team] = (home_attack + update_rate * home_residual,
                          home_defense - update_rate * away_residual)
    ratings[away_team] = (away_attack + update_rate * away_residual,
                          away_defense - update_rate * home_residual)
    _center_ratings(ratings)
    return lambdas


def run_dynamic_attack_defense_rolling_validation(dataset: pd.DataFrame) -> DynamicAttackDefenseResult:
    missing = set(DATASET_COLUMNS) - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if dataset["match_id"].isna().any() or not dataset["match_id"].is_unique:
        raise ValueError("match_id must be unique and nonmissing.")
    scores = _load_scores(dataset)
    dates = dataset.set_index("match_id")["match_date"]
    scores["match_date"] = pd.to_datetime(dates.loc[scores["match_id"]].to_numpy(), errors="raise")
    source = scores.loc[scores["season"].between(2015, 2024)].copy()
    fold_metrics, fold_counts, diagnostics = {}, {}, {}
    targets, probabilities = [], []
    for season in VALIDATION_SEASONS:
        train = source.loc[source["season"].between(2015, season - 1)].copy()
        validation = source.loc[source["season"].eq(season)].copy()
        train = _chronological(train)
        validation = _chronological(validation)
        fold_counts[season] = (len(train), len(validation))
        base_home = float(train["home_score"].mean())
        base_away = float(train["away_score"].mean())
        ratings = {}
        for row in train.itertuples(index=False):
            update_ratings(ratings, row.home_team_id, row.away_team_id,
                           row.home_score, row.away_score, base_home, base_away)
        initial_ratings = dict(ratings)
        fold_probabilities, fold_targets = [], []
        lambda_rows = []
        for row in validation.itertuples(index=False):
            _register(ratings, row.home_team_id)
            _register(ratings, row.away_team_id)
            ha, hd = ratings[row.home_team_id]
            aa, ad = ratings[row.away_team_id]
            lambdas = expected_goals(base_home, base_away, ha, ad, aa, hd)
            fold_probabilities.append(_score_probabilities(*lambdas))
            fold_targets.append(row.result)
            lambda_rows.append(lambdas)
            update_ratings(ratings, row.home_team_id, row.away_team_id,
                           row.home_score, row.away_score, base_home, base_away)
        fold_probabilities = np.asarray(fold_probabilities)
        fold_targets = np.asarray(fold_targets)
        fold_metrics[season] = _metrics(fold_targets, fold_probabilities)
        targets.append(fold_targets)
        probabilities.append(fold_probabilities)
        diagnostics[season] = _diagnostic(base_home, base_away, initial_ratings, lambda_rows, fold_targets)
    pooled_targets = np.concatenate(targets)
    pooled_probabilities = np.concatenate(probabilities)
    from src.modeling.poisson_score_rolling_validation import _benchmark_rolling
    return DynamicAttackDefenseResult(
        fold_metrics=fold_metrics,
        pooled_metrics=_metrics(pooled_targets, pooled_probabilities),
        fold_counts=fold_counts,
        diagnostics=diagnostics,
        benchmark_pooled_metrics=_benchmark_rolling(dataset),
    )


def _chronological(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.sort_values(["match_date", "match_id"], kind="mergesort").reset_index(drop=True)


def _register(ratings: dict[str, tuple[float, float]], team: str) -> None:
    if team not in ratings:
        ratings[team] = (0.0, 0.0)


def _center_ratings(ratings: dict[str, tuple[float, float]]) -> None:
    attacks = np.mean([value[0] for value in ratings.values()])
    defenses = np.mean([value[1] for value in ratings.values()])
    for team, (attack, defense) in list(ratings.items()):
        ratings[team] = (attack - attacks, defense - defenses)


def _diagnostic(base_home, base_away, ratings, lambdas, targets):
    values = list(ratings.values())
    lambdas = np.asarray(lambdas)
    probabilities = np.asarray([_score_probabilities(*pair) for pair in lambdas])
    return {
        "base_home_goals": base_home,
        "base_away_goals": base_away,
        "rating_summary": {
            "attack_min": float(min(x[0] for x in values)),
            "attack_median": float(np.median([x[0] for x in values])),
            "attack_max": float(max(x[0] for x in values)),
            "defense_min": float(min(x[1] for x in values)),
            "defense_median": float(np.median([x[1] for x in values])),
            "defense_max": float(max(x[1] for x in values)),
        },
        "lambda_summary": {
            "home_min": float(lambdas[:, 0].min()), "home_mean": float(lambdas[:, 0].mean()),
            "home_median": float(np.median(lambdas[:, 0])), "home_max": float(lambdas[:, 0].max()),
            "away_min": float(lambdas[:, 1].min()), "away_mean": float(lambdas[:, 1].mean()),
            "away_median": float(np.median(lambdas[:, 1])), "away_max": float(lambdas[:, 1].max()),
        },
        "mean_probabilities": probabilities.mean(axis=0),
        "actual_class_proportions": np.bincount(targets, minlength=3) / len(targets),
    }
