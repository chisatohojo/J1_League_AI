"""Independent Poisson score model with fixed 2020--2024 rolling folds."""

from dataclasses import dataclass
from math import factorial

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.collect.matches import load_matches
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.benchmark_suite import BENCHMARK_NAMES, _metrics, _predict_benchmarks, _with_replayed_elo

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
MAX_GOALS = 15
POISSON_COLUMNS = ("attacking_team", "defending_team", "is_home")


@dataclass(frozen=True)
class PoissonRollingValidationResult:
    fold_metrics: dict[int, object]
    pooled_metrics: object
    benchmark_pooled_metrics: dict[str, object]
    fold_counts: dict[int, tuple[int, int]]


def run_poisson_score_rolling_validation(dataset: pd.DataFrame) -> PoissonRollingValidationResult:
    """Evaluate independent Poisson probabilities without using future seasons."""
    missing = set(DATASET_COLUMNS) - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if dataset["match_id"].isna().any() or not dataset["match_id"].is_unique:
        raise ValueError("match_id must be unique and nonmissing.")
    if not dataset["season"].isin(range(2015, 2027)).all():
        raise ValueError("Unexpected season in input dataset.")
    scores = _load_scores(dataset)
    rolling = scores.loc[scores["season"].between(2015, 2024)].copy(deep=True)
    fold_metrics = {}
    fold_counts = {}
    pooled_targets = []
    pooled_probabilities = []
    for validation_season in VALIDATION_SEASONS:
        train = rolling.loc[rolling["season"].between(2015, validation_season - 1)].copy(deep=True)
        validation = rolling.loc[rolling["season"].eq(validation_season)].copy(deep=True)
        fold_counts[validation_season] = (len(train), len(validation))
        model = _fit(train)
        probabilities = _predict(model, validation)
        target = validation["result"].to_numpy(copy=True)
        fold_metrics[validation_season] = _metrics(target, probabilities)
        pooled_targets.append(target)
        pooled_probabilities.append(probabilities)
    pooled_metrics = _metrics(np.concatenate(pooled_targets), np.concatenate(pooled_probabilities))
    benchmark = _benchmark_rolling(dataset)
    return PoissonRollingValidationResult(
        fold_metrics=fold_metrics,
        pooled_metrics=pooled_metrics,
        benchmark_pooled_metrics=benchmark,
        fold_counts=fold_counts,
    )


def _benchmark_rolling(dataset: pd.DataFrame) -> dict[str, object]:
    """Compute benchmark OOF metrics without invoking the 2025 holdout path."""
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


def _fit(matches: pd.DataFrame) -> Pipeline:
    observations = pd.concat([
        matches.loc[:, ["home_team_id", "away_team_id", "home_score"]].rename(columns={
            "home_team_id": "attacking_team", "away_team_id": "defending_team", "home_score": "goals",
        }).assign(is_home=1),
        matches.loc[:, ["away_team_id", "home_team_id", "away_score"]].rename(columns={
            "away_team_id": "attacking_team", "home_team_id": "defending_team", "away_score": "goals",
        }).assign(is_home=0),
    ], ignore_index=True)
    preprocessor = ColumnTransformer([
        ("teams", OneHotEncoder(handle_unknown="ignore"), ["attacking_team", "defending_team"]),
        ("home", "passthrough", ["is_home"]),
    ])
    model = Pipeline([
        ("features", preprocessor),
        ("poisson", PoissonRegressor(alpha=1e-6, max_iter=1000)),
    ])
    model.fit(observations.loc[:, list(POISSON_COLUMNS)], observations["goals"])
    return model


def _predict(model: Pipeline, matches: pd.DataFrame) -> np.ndarray:
    home_rows = matches.loc[:, ["home_team_id", "away_team_id"]].rename(columns={
        "home_team_id": "attacking_team", "away_team_id": "defending_team",
    }).assign(is_home=1)
    away_rows = matches.loc[:, ["away_team_id", "home_team_id"]].rename(columns={
        "away_team_id": "attacking_team", "home_team_id": "defending_team",
    }).assign(is_home=0)
    lambdas = np.column_stack([model.predict(home_rows.loc[:, list(POISSON_COLUMNS)]),
                               model.predict(away_rows.loc[:, list(POISSON_COLUMNS)])])
    if not np.isfinite(lambdas).all() or (lambdas <= 0).any():
        raise ValueError("Poisson lambdas must be finite and positive.")
    return np.vstack([_score_probabilities(home, away) for home, away in lambdas])


def _score_probabilities(home_lambda: float, away_lambda: float) -> np.ndarray:
    goals = np.arange(MAX_GOALS + 1)
    home_pmf = np.exp(-home_lambda) * np.power(home_lambda, goals) / np.array([factorial(int(g)) for g in goals])
    away_pmf = np.exp(-away_lambda) * np.power(away_lambda, goals) / np.array([factorial(int(g)) for g in goals])
    matrix = np.outer(home_pmf, away_pmf)
    probabilities = np.array([
        np.triu(matrix, k=1).sum(),
        np.trace(matrix),
        np.tril(matrix, k=-1).sum(),
    ])
    return probabilities / probabilities.sum()


def _load_scores(dataset: pd.DataFrame) -> pd.DataFrame:
    frames = []
    ids = dataset.loc[:, ["match_id", "season", "home_team_id", "away_team_id"]].copy(deep=True)
    ids["match_id"] = ids["match_id"].astype(str)
    for season in range(2015, 2025):
        raw = load_matches(f"data/processed/jleague/{season}_matches_probe.csv")
        raw["match_id"] = raw["match_id"].astype(str)
        selected = raw.loc[:, ["match_id", "home_score", "away_score"]].merge(
            ids.loc[ids["season"].eq(season)], on="match_id", how="inner", validate="one_to_one",
        )
        if len(selected) != len(raw):
            raise ValueError(f"Score join mismatch in season {season}.")
        selected["result"] = np.select(
            [selected["home_score"] < selected["away_score"], selected["home_score"] == selected["away_score"]],
            [0, 1], default=2,
        )
        frames.append(selected)
    return pd.concat(frames, ignore_index=True)
