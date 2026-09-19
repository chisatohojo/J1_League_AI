"""Evaluate fixed-K Elo home-advantage candidates on 2024 only."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.elo import EloRatings
from src.features.elo_history import load_elo_history_with_ongoing
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.time_split import split_training_dataset

HOME_ADVANTAGE_CANDIDATES = (0.0, 25.0, 50.0, 75.0, 100.0)
K_FACTOR = 30.0
FEATURE_COLUMNS = (
    "elo_diff", "home_stadium_last5_matches", "home_stadium_last5_points",
    "home_stadium_last5_goal_diff", "away_stadium_last5_matches",
    "away_stadium_last5_points", "away_stadium_last5_goal_diff",
    "home_days_since_last_match", "away_days_since_last_match",
    "home_has_previous_match", "away_has_previous_match",
)


def _replay(frames: tuple[pd.DataFrame, ...], home_advantage: float) -> pd.DataFrame:
    ids = sorted(set().union(*(set(f["home_team_id"]) | set(f["away_team_id"]) for f in frames)))
    elo = EloRatings(ids, k_factor=K_FACTOR, home_advantage=home_advantage)
    rows = []
    for frame in frames:
        for row in frame[["match_id", "home_team_id", "away_team_id", "result"]].itertuples(index=False):
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            rows.append((row.match_id, before.home_rating, before.away_rating))
            elo.update(row.home_team_id, row.away_team_id, row.result)
    return pd.DataFrame(rows, columns=["match_id", "home_elo", "away_elo"]).assign(
        elo_diff=lambda x: x.home_elo - x.away_elo
    )


def run_logistic_elo_home_advantage_tuning(dataset: pd.DataFrame) -> dict[float, FormLogisticMetrics]:
    """Replay one continuous 1500-based Elo stream through 2024 and score validation."""
    base = dataset.loc[:, list(DATASET_COLUMNS)].copy(deep=True)
    split = split_training_dataset(base)
    source = dataset.copy(deep=True)
    source_ids = pd.Index(source["match_id"])
    train = source.iloc[source_ids.get_indexer(split.train["match_id"])].copy(deep=True)
    validation = source.iloc[source_ids.get_indexer(split.validation["match_id"])].copy(deep=True)
    evaluated = pd.concat([train, validation], ignore_index=True)
    allowed = set(evaluated["match_id"])
    history = load_elo_history_with_ongoing()
    raw_frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    frames = tuple(f.loc[f["match_id"].isin(allowed)].copy() for f in raw_frames)
    replay_by_candidate = {candidate: _replay(frames, candidate) for candidate in HOME_ADVANTAGE_CANDIDATES}
    replay_ids = pd.Index(evaluated["match_id"])
    target = split.validation["result"]
    one_hot = (target.to_numpy()[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    results = {}
    for candidate, replay in replay_by_candidate.items():
        if len(replay) != len(evaluated) or not replay["match_id"].is_unique:
            raise ValueError("Elo replay does not match the train/validation rows.")
        aligned = replay.set_index("match_id").loc[replay_ids]
        train_features = train.loc[:, [c for c in FEATURE_COLUMNS if c != "elo_diff"]].copy()
        validation_features = validation.loc[:, [c for c in FEATURE_COLUMNS if c != "elo_diff"]].copy()
        train_features.insert(0, "elo_diff", aligned.iloc[:len(train)]["elo_diff"].to_numpy())
        validation_features.insert(0, "elo_diff", aligned.iloc[len(train):]["elo_diff"].to_numpy())
        model = Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0))])
        model.fit(train_features, train["result"])
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected class order [0, 1, 2].")
        probabilities = model.predict_proba(validation_features)
        results[candidate] = FormLogisticMetrics(
            accuracy=float(accuracy_score(target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results
