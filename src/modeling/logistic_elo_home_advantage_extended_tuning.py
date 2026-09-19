"""Final fixed home-advantage extension for 2024 validation."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.elo_history import load_elo_history_with_ongoing
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_elo_home_advantage_tuning import (
    FEATURE_COLUMNS, K_FACTOR, _replay,
)
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.time_split import split_training_dataset

HOME_ADVANTAGE_CANDIDATES = (100.0, 125.0, 150.0, 175.0, 200.0)
STADIUM_WINDOW = 5


def run_logistic_elo_home_advantage_extended_tuning(
    dataset: pd.DataFrame,
) -> dict[float, FormLogisticMetrics]:
    """Evaluate only the five final candidates on the 2024 validation split."""
    base = dataset.loc[:, list(DATASET_COLUMNS)].copy(deep=True)
    split = split_training_dataset(base)
    source = dataset.copy(deep=True)
    source_ids = pd.Index(source["match_id"])
    train_positions = source_ids.get_indexer(split.train["match_id"])
    validation_positions = source_ids.get_indexer(split.validation["match_id"])
    if (train_positions < 0).any() or (validation_positions < 0).any():
        raise ValueError("Dataset match IDs do not cover the split rows.")
    train = source.iloc[train_positions].copy(deep=True)
    validation = source.iloc[validation_positions].copy(deep=True)
    evaluated = pd.concat([train, validation], ignore_index=True)
    if len(train) != 2828 or len(validation) != 380:
        raise ValueError("Unexpected train/validation row counts.")
    if evaluated["match_id"].isna().any() or not evaluated["match_id"].is_unique:
        raise ValueError("Evaluation match_id values must be nonmissing and unique.")

    allowed = set(evaluated["match_id"])
    history = load_elo_history_with_ongoing()
    raw_frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    frames = tuple(frame.loc[frame["match_id"].isin(allowed)].copy() for frame in raw_frames)
    target = validation["result"]
    one_hot = (target.to_numpy()[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    results = {}
    for candidate in HOME_ADVANTAGE_CANDIDATES:
        replay = _replay(frames, candidate)
        if len(replay) != len(evaluated) or replay["match_id"].isna().any() or not replay["match_id"].is_unique:
            raise ValueError("Elo replay count, missing IDs or duplicates are invalid.")
        replay_ids = pd.Index(replay["match_id"])
        positions = replay_ids.get_indexer(evaluated["match_id"])
        if (positions < 0).any():
            raise ValueError("Elo replay contains unknown or missing match IDs.")
        aligned = replay.iloc[positions]
        context_columns = [column for column in FEATURE_COLUMNS if column != "elo_diff"]
        train_features = train.loc[:, context_columns].copy(deep=True)
        validation_features = validation.loc[:, context_columns].copy(deep=True)
        train_features.insert(0, "elo_diff", aligned.iloc[:len(train)]["elo_diff"].to_numpy(copy=True))
        validation_features.insert(0, "elo_diff", aligned.iloc[len(train):]["elo_diff"].to_numpy(copy=True))
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)),
        ])
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
