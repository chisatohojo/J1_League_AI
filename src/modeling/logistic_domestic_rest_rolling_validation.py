"""Rolling evaluation of Elo-only versus domestic competitive rest.

Domestic means J1, J.League Cup and Emperor's Cup only. AFC fixtures are
intentionally excluded; for AFC participants these features can therefore be
longer than their true all-competition rest.
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
from src.features.domestic_competitive_rest import (
    FEATURE_COLUMNS as DOMESTIC_FEATURES,
    add_domestic_competitive_rest_features,
)
from src.features.elo import EloRatings
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
EXPECTED_VALIDATION_COUNTS = {2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}
ELO_FEATURES = ("elo_diff",)
ALL_FEATURES = ELO_FEATURES + DOMESTIC_FEATURES
K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0


@dataclass(frozen=True)
class DomesticRestRollingResult:
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
        frame["match_date"] = pd.to_datetime(frame["match_date"], errors="raise").dt.normalize()
        frame["home_team_id"] = [master.resolve_team_id(n, source="jleague_data_site", on=d.date())
                                  for n, d in zip(frame.home_team, frame.match_date)]
        frame["away_team_id"] = [master.resolve_team_id(n, source="jleague_data_site", on=d.date())
                                  for n, d in zip(frame.away_team, frame.match_date)]
        if len(frame) != EXPECTED_VALIDATION_COUNTS.get(season, 0) and season in EXPECTED_VALIDATION_COUNTS:
            raise ValueError(f"Unexpected J1 count for {season}: {len(frame)}")
        frames.append(frame[["match_id", "season", "match_date", "home_team_id", "away_team_id", "result"]])
    result = pd.concat(frames, ignore_index=True)
    if result.match_id.duplicated().any():
        raise ValueError("J1 match_id must be unique.")
    return result.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)


def _load_csv(path):
    frame = pd.read_csv(path)
    frame["match_date"] = pd.to_datetime(frame["match_date"], errors="raise").dt.normalize()
    return frame


def _replay_elo(frame):
    ids = sorted(set(frame.home_team_id) | set(frame.away_team_id))
    elo = EloRatings(ids, k_factor=K_FACTOR, home_advantage=HOME_ADVANTAGE)
    rows = []
    for row in frame.sort_values(["match_date", "match_id"], kind="stable").itertuples(index=False):
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


def run_logistic_domestic_rest_rolling_validation(
    j1_matches=None, league_cup_matches=None, emperors_cup_matches=None, *,
    processed_dir="data/processed/jleague",
    league_cup_path="data/processed/jleague_cup/2015_2024_jleague_cup_matches.csv",
    emperors_cup_path="data/processed/emperors_cup/2015_2024_emperors_cup_matches.csv",
):
    """Run the five fixed expanding folds without reading AFC, 2025 or 2026."""
    master = load_team_master()
    j1 = _load_j1(processed_dir, master) if j1_matches is None else j1_matches.copy(deep=True)
    cup = _load_csv(league_cup_path) if league_cup_matches is None else league_cup_matches.copy(deep=True)
    emperor = _load_csv(emperors_cup_path) if emperors_cup_matches is None else emperors_cup_matches.copy(deep=True)
    j1 = j1.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    fold_metrics, fold_counts = {}, {}
    pooled_targets, pooled_probs = {"elo_only": [], "elo_domestic": []}, {"elo_only": [], "elo_domestic": []}
    for year in VALIDATION_SEASONS:
        end = pd.Timestamp(f"{year}-12-31")
        eligible_j1 = j1.loc[j1.match_date <= end].copy()
        features = add_domestic_competitive_rest_features(
            eligible_j1,
            cup.loc[cup.match_date <= end].copy(),
            emperor.loc[emperor.match_date <= end].copy(),
        )
        replay = _replay_elo(eligible_j1).set_index("match_id")
        features["elo_diff"] = features.match_id.astype(str).map(replay.elo_diff)
        train = features.loc[features.season < year].copy()
        validation = features.loc[features.season == year].copy()
        if len(validation) != EXPECTED_VALIDATION_COUNTS[year]:
            raise ValueError(f"Unexpected validation count for {year}: {len(validation)}")
        fold_counts[year] = (len(train), len(validation))
        p_a = _fit_predict(train, validation, ELO_FEATURES)
        p_b = _fit_predict(train, validation, ALL_FEATURES)
        target = validation.result.to_numpy(copy=True)
        fold_metrics[year] = {"elo_only": _metrics(target, p_a), "elo_domestic": _metrics(target, p_b)}
        for name, probs in (("elo_only", p_a), ("elo_domestic", p_b)):
            pooled_targets[name].append(target.copy())
            pooled_probs[name].append(probs.copy())
    pooled = {name: _metrics(np.concatenate(pooled_targets[name]), np.concatenate(pooled_probs[name]))
              for name in pooled_targets}
    if sum(len(x) for x in pooled_targets["elo_only"]) != 1678:
        raise ValueError("Expected 1,678 pooled validation matches.")
    return DomesticRestRollingResult(fold_metrics, pooled, fold_counts)

