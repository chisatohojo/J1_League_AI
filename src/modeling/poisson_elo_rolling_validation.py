"""Independent Poisson with one pre-match attacker-view Elo feature."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.benchmark_suite import _metrics
from src.modeling.logistic_elo_home_advantage_tuning import _replay
from src.modeling.poisson_score_rolling_validation import (
    VALIDATION_SEASONS,
    _fit,
    _load_scores,
    _score_probabilities,
)
from src.modeling.poisson_time_decay_rolling_validation import _predict_lambdas
from src.modeling.poisson_time_decay_rolling_validation import _benchmark_rolling

K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0
POISSON_COLUMNS = ("attacking_team", "defending_team", "is_home", "elo_diff_attacker")


@dataclass(frozen=True)
class PoissonEloRollingValidationResult:
    fold_metrics: dict[int, dict[str, object]]
    pooled_metrics: dict[str, object]
    unseen_metrics: dict[str, object]
    known_metrics: dict[str, object]
    fold_counts: dict[int, tuple[int, int]]
    benchmark_pooled_metrics: dict[str, object]


def run_poisson_elo_rolling_validation(dataset: pd.DataFrame) -> PoissonEloRollingValidationResult:
    missing = set(DATASET_COLUMNS) - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if dataset["match_id"].isna().any() or not dataset["match_id"].is_unique:
        raise ValueError("match_id must be unique and nonmissing.")
    scores = _load_scores(dataset)
    metadata = dataset.set_index("match_id")
    scores["match_date"] = pd.to_datetime(metadata.loc[scores["match_id"], "match_date"].to_numpy())
    rolling = scores.loc[scores["season"].between(2015, 2024)].copy(deep=True)
    fold_metrics = {}
    fold_counts = {}
    pooled = {"independent_poisson": [], "elo_assisted_poisson": []}
    targets = []
    unseen_probabilities, unseen_targets = [], []
    known_probabilities, known_targets = [], []

    for season in VALIDATION_SEASONS:
        train = rolling.loc[rolling["season"].between(2015, season - 1)].copy(deep=True)
        validation = rolling.loc[rolling["season"].eq(season)].copy(deep=True)
        fold_counts[season] = (len(train), len(validation))
        train, validation = _add_pre_match_elo(rolling, train, validation, season)
        independent_model = _fit(train)
        independent_lambdas = _predict_lambdas(independent_model, validation)
        independent_probabilities = np.vstack([
            _score_probabilities(home, away) for home, away in independent_lambdas
        ])
        assisted_model = _fit_assisted(train)
        assisted_lambdas = _predict_assisted_lambdas(assisted_model, validation)
        assisted_probabilities = np.vstack([
            _score_probabilities(home, away) for home, away in assisted_lambdas
        ])
        target = validation["result"].to_numpy(copy=True)
        fold_metrics[season] = {
            "independent_poisson": _metrics(target, independent_probabilities),
            "elo_assisted_poisson": _metrics(target, assisted_probabilities),
        }
        pooled["independent_poisson"].append(independent_probabilities)
        pooled["elo_assisted_poisson"].append(assisted_probabilities)
        targets.append(target)
        known_teams = set(train["home_team_id"]) | set(train["away_team_id"])
        unseen = ~validation["home_team_id"].isin(known_teams) | ~validation["away_team_id"].isin(known_teams)
        unseen_probabilities.append(assisted_probabilities[unseen])
        unseen_targets.append(target[unseen])
        known_probabilities.append(assisted_probabilities[~unseen])
        known_targets.append(target[~unseen])

    target_array = np.concatenate(targets)
    pooled_metrics = {
        name: _metrics(target_array, np.concatenate(values)) for name, values in pooled.items()
    }
    return PoissonEloRollingValidationResult(
        fold_metrics=fold_metrics,
        pooled_metrics=pooled_metrics,
        unseen_metrics=_group_metrics(unseen_targets, unseen_probabilities),
        known_metrics=_group_metrics(known_targets, known_probabilities),
        fold_counts=fold_counts,
        benchmark_pooled_metrics=_benchmark_rolling(dataset),
    )


def attacker_elo_diff(home_elo: float, away_elo: float, is_home: int) -> float:
    if is_home == 1:
        return float(home_elo - away_elo)
    if is_home == 0:
        return float(away_elo - home_elo)
    raise ValueError("is_home must be 0 or 1.")


def _add_pre_match_elo(source, train, validation, season):
    base = source.loc[source["season"].between(2015, season)]
    frames = tuple(
        base.loc[base["season"].eq(year),
                  ["match_id", "home_team_id", "away_team_id", "result"]].copy(deep=True)
        for year in range(2015, season + 1)
    )
    replay = _replay(frames, HOME_ADVANTAGE).set_index("match_id")
    allowed = pd.concat([train, validation], ignore_index=True)
    if set(replay.index) != set(allowed["match_id"]):
        raise ValueError(f"Elo replay mismatch through season {season}.")
    allowed["elo_diff"] = replay.loc[allowed["match_id"], "elo_diff"].to_numpy()
    return _add_long_elo(allowed.iloc[:len(train)].copy(deep=True)), _add_long_elo(allowed.iloc[len(train):].copy(deep=True))


def _add_long_elo(matches):
    matches = matches.copy(deep=True)
    matches["home_elo_diff"] = matches["elo_diff"]
    matches["away_elo_diff"] = -matches["elo_diff"]
    return matches


def _fit_assisted(matches):
    observations = pd.concat([
        matches[["home_team_id", "away_team_id", "home_score", "home_elo_diff"]].rename(columns={
            "home_team_id": "attacking_team", "away_team_id": "defending_team",
            "home_score": "goals", "home_elo_diff": "elo_diff_attacker",
        }).assign(is_home=1),
        matches[["away_team_id", "home_team_id", "away_score", "away_elo_diff"]].rename(columns={
            "away_team_id": "attacking_team", "home_team_id": "defending_team",
            "away_score": "goals", "away_elo_diff": "elo_diff_attacker",
        }).assign(is_home=0),
    ], ignore_index=True)
    preprocessor = ColumnTransformer([
        ("teams", OneHotEncoder(handle_unknown="ignore"), ["attacking_team", "defending_team"]),
        ("numeric", "passthrough", ["is_home", "elo_diff_attacker"]),
    ])
    model = Pipeline([
        ("features", preprocessor),
        ("poisson", PoissonRegressor(alpha=1e-6, max_iter=1000)),
    ])
    model.fit(observations[list(POISSON_COLUMNS)], observations["goals"])
    return model


def _predict_assisted_lambdas(model, matches):
    home = matches[["home_team_id", "away_team_id", "elo_diff"]].rename(columns={
        "home_team_id": "attacking_team", "away_team_id": "defending_team",
        "elo_diff": "elo_diff_attacker",
    }).assign(is_home=1)
    away = matches[["away_team_id", "home_team_id", "elo_diff"]].rename(columns={
        "away_team_id": "attacking_team", "home_team_id": "defending_team",
    }).assign(is_home=0)
    away["elo_diff_attacker"] = -away["elo_diff"]
    lambdas = np.column_stack([
        model.predict(home[list(POISSON_COLUMNS)]), model.predict(away[list(POISSON_COLUMNS)]),
    ])
    if not np.isfinite(lambdas).all() or (lambdas <= 0).any():
        raise ValueError("Poisson lambdas must be finite and positive.")
    return lambdas


def _group_metrics(target_groups, probability_groups):
    targets = np.concatenate([x for x in target_groups if len(x)])
    probabilities = np.concatenate([x for x in probability_groups if len(x)], axis=0)
    return {"matches": int(len(targets)), "metrics": _metrics(targets, probabilities)}
