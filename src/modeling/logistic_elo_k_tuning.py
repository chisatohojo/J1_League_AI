"""Compare fixed Elo K factors on the 2024 validation partition."""

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

K_CANDIDATES = (10.0, 15.0, 20.0, 30.0, 40.0)
FEATURE_COLUMNS = (
    "elo_diff",
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
    "home_days_since_last_match", "away_days_since_last_match",
    "home_has_previous_match", "away_has_previous_match",
)


def _replay(frames: tuple[pd.DataFrame, ...], k_factor: float) -> pd.DataFrame:
    ids = sorted(set().union(*(set(frame["home_team_id"]) | set(frame["away_team_id"]) for frame in frames)))
    elo = EloRatings(ids, k_factor=k_factor)
    rows = []
    for frame in frames:
        for row in frame[["match_id", "home_team_id", "away_team_id", "result"]].itertuples(index=False):
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            rows.append((row.match_id, before.home_rating, before.away_rating))
            elo.update(row.home_team_id, row.away_team_id, row.result)
    return pd.DataFrame(rows, columns=["match_id", "home_elo", "away_elo"]).assign(
        elo_diff=lambda value: value.home_elo - value.away_elo
    )


def run_logistic_elo_k_tuning(dataset: pd.DataFrame) -> dict[float, FormLogisticMetrics]:
    """Replay each fixed K from 1500 and evaluate only 2024 validation."""
    split = split_training_dataset(dataset.loc[:, list(DATASET_COLUMNS)])
    base_ids = pd.Index(dataset["match_id"])
    if base_ids.isna().any() or not base_ids.is_unique:
        raise ValueError("dataset match_id must be nonmissing and unique.")
    train = dataset.iloc[base_ids.get_indexer(split.train["match_id"])]
    validation = dataset.iloc[base_ids.get_indexer(split.validation["match_id"])]
    validation_target = validation["result"]
    if not validation_target.isin(CLASS_ORDER).all():
        raise ValueError("Validation targets must be 0=Away, 1=Draw or 2=Home.")
    one_hot = (validation_target.to_numpy()[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    results = {}
    for k_factor in K_CANDIDATES:
        history = load_elo_history_with_ongoing()
        frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
        replay = _replay(frames, k_factor)
        replay_ids = pd.Index(replay["match_id"])
        if replay_ids.isna().any() or not replay_ids.is_unique or len(replay) != len(dataset):
            raise ValueError("K-specific Elo history match_id count or uniqueness is invalid.")
        positions = replay_ids.get_indexer(base_ids)
        if (positions < 0).any():
            raise ValueError("K-specific Elo history match_ids do not match dataset.")
        aligned = replay.iloc[positions]
        train_features = train.loc[:, list(FEATURE_COLUMNS)].copy(deep=True)
        validation_features = validation.loc[:, list(FEATURE_COLUMNS)].copy(deep=True)
        for column in ("elo_diff",):
            train_features[column] = aligned.iloc[base_ids.get_indexer(train["match_id"])] [column].to_numpy(copy=True)
            validation_features[column] = aligned.iloc[base_ids.get_indexer(validation["match_id"])] [column].to_numpy(copy=True)
        model = Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0))])
        model.fit(train_features, train["result"])
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected model.classes_ in [0, 1, 2] order.")
        probabilities = model.predict_proba(validation_features)
        results[k_factor] = FormLogisticMetrics(
            accuracy=float(accuracy_score(validation_target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(validation_target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results
