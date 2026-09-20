"""Fixed rolling comparison of Elo-only and pre-match recent form.

Only J1 league matches from 2015-2024 are read. Form is computed before each
match, so the current result and all future matches are excluded.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.teams import load_team_master
from src.features.form import add_form_features
from src.features.elo import EloRatings
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
EXPECTED_VALIDATION_COUNTS = {2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}
ELO_FEATURES = ("elo_diff",)
FORM_FEATURES = (
    "home_last5_points", "away_last5_points",
    "home_last5_goals_for", "away_last5_goals_for",
    "home_last5_goals_against", "away_last5_goals_against",
)
ALL_FEATURES = ELO_FEATURES + FORM_FEATURES
K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0


@dataclass(frozen=True)
class FormRollingResult:
    fold_metrics: dict[int, dict[str, FormLogisticMetrics]]
    pooled_metrics: dict[str, FormLogisticMetrics]
    fold_counts: dict[int, tuple[int, int]]


def _metrics(target, probabilities):
    target = np.asarray(target)
    probabilities = np.asarray(probabilities)
    if probabilities.shape[1] != 3 or not np.allclose(probabilities.sum(axis=1), 1.0):
        raise ValueError("Expected three-class probabilities summing to one.")
    one_hot = (target[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(
        accuracy=float(accuracy_score(target, np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)])),
        log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
    )


def _load_j1(processed_dir, master):
    frames = []
    for season in range(2015, 2025):
        frame = pd.read_csv(Path(processed_dir) / f"{season}_matches_probe.csv")
        frame["match_date"] = pd.to_datetime(frame.match_date, errors="raise").dt.normalize()
        frame["home_team_id"] = [master.resolve_team_id(n, source="jleague_data_site", on=d.date())
                                  for n, d in zip(frame.home_team, frame.match_date)]
        frame["away_team_id"] = [master.resolve_team_id(n, source="jleague_data_site", on=d.date())
                                  for n, d in zip(frame.away_team, frame.match_date)]
        frames.append(frame[["match_id", "season", "match_date", "home_team_id", "away_team_id",
                             "home_score", "away_score", "result"]])
    result = pd.concat(frames, ignore_index=True)
    if result.match_id.duplicated().any():
        raise ValueError("J1 match_id must be unique")
    return result.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)


def _replay_elo(matches):
    elo = EloRatings(sorted(set(matches.home_team_id) | set(matches.away_team_id)),
                     k_factor=K_FACTOR, home_advantage=HOME_ADVANTAGE)
    rows = []
    for row in matches.sort_values(["match_date", "match_id"], kind="stable").itertuples(index=False):
        before = elo.pre_match(row.home_team_id, row.away_team_id)
        rows.append((str(row.match_id), before.home_rating - before.away_rating))
        elo.update(row.home_team_id, row.away_team_id, row.result)
    return pd.DataFrame(rows, columns=["match_id", "elo_diff"])


def _fit_predict(train, validation, columns):
    model = Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(
        C=1.0, solver="lbfgs", max_iter=1000, random_state=0))])
    model.fit(train.loc[:, columns], train.result)
    if not np.array_equal(model.classes_, CLASS_ORDER):
        raise ValueError("Expected class order [0, 1, 2].")
    return model.predict_proba(validation.loc[:, columns])


def run_logistic_form_rolling_validation(*, processed_dir="data/processed/jleague"):
    """Evaluate the fixed five folds; 2025 and 2026 are never read."""
    master = load_team_master()
    matches = _load_j1(processed_dir, master)
    with_form = add_form_features(matches[["match_date", "home_team_id", "away_team_id",
                                            "home_score", "away_score", "result"]].assign(
                                                match_id=matches.match_id, season=matches.season
                                            ))
    with_form["match_id"] = matches.match_id.to_numpy(copy=True)
    with_form["season"] = matches.season.to_numpy(copy=True)
    with_form["elo_diff"] = _replay_elo(matches).set_index("match_id").loc[
        with_form.match_id.astype(str), "elo_diff"].to_numpy()
    fold_metrics, fold_counts = {}, {}
    pooled_targets, pooled_probs = {"elo_only": [], "elo_form": []}, {"elo_only": [], "elo_form": []}
    for year in VALIDATION_SEASONS:
        train = with_form.loc[with_form.season < year].copy()
        validation = with_form.loc[with_form.season == year].copy()
        if len(validation) != EXPECTED_VALIDATION_COUNTS[year]:
            raise ValueError(f"Unexpected validation count for {year}")
        fold_counts[year] = (len(train), len(validation))
        probabilities = {
            "elo_only": _fit_predict(train, validation, ELO_FEATURES),
            "elo_form": _fit_predict(train, validation, ALL_FEATURES),
        }
        target = validation.result.to_numpy(copy=True)
        fold_metrics[year] = {name: _metrics(target, p) for name, p in probabilities.items()}
        for name, p in probabilities.items():
            pooled_targets[name].append(target.copy())
            pooled_probs[name].append(p.copy())
    pooled = {name: _metrics(np.concatenate(pooled_targets[name]), np.concatenate(pooled_probs[name]))
              for name in pooled_targets}
    if sum(len(x) for x in pooled_targets["elo_only"]) != 1678:
        raise ValueError("Expected pooled OOF count 1,678")
    return FormRollingResult(fold_metrics, pooled, fold_counts)

