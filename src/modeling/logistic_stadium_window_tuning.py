"""Compare four fixed stadium history windows on 2024 validation only."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.stadium_window import STADIUM_WINDOW_COLUMNS
from src.features.stadium_window_history import load_stadium_window_history_with_ongoing
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.time_split import split_training_dataset


WINDOWS = (3, 5, 8, 10)
BASE_FEATURE_COLUMNS = (
    "elo_diff",
    "home_days_since_last_match", "away_days_since_last_match",
    "home_has_previous_match", "away_has_previous_match",
)
FEATURE_COLUMNS = (
    "elo_diff", *STADIUM_WINDOW_COLUMNS, *BASE_FEATURE_COLUMNS[1:],
)


def _feature_frame(matches: pd.DataFrame, stadium: pd.DataFrame) -> pd.DataFrame:
    """Attach stadium values by match ID to selected train or validation rows."""
    positions = pd.Index(stadium["match_id"]).get_indexer(matches["match_id"])
    aligned = stadium.iloc[positions]
    features = matches.loc[:, list(BASE_FEATURE_COLUMNS)].copy(deep=True)
    for column in STADIUM_WINDOW_COLUMNS:
        features[column] = aligned[column].array.copy()
    return features.loc[:, list(FEATURE_COLUMNS)]


def run_logistic_stadium_window_tuning(dataset: pd.DataFrame) -> dict[int, FormLogisticMetrics]:
    """Fit windows 3/5/8/10 on train and return validation metrics without ranking.

    Reuse the 24-column splitter and recover train/validation rows by match_id.
    Validate complete ID correspondence with each stadium history, but select
    model inputs only for train and validation; never access split.test or
    split.reserved. Elo, stream schedule gaps and flags remain unchanged.
    Only the six stadium columns vary. No input mutation, feature calculation,
    additional window search, file writes or network access occurs here.
    """
    split = split_training_dataset(dataset.loc[:, list(DATASET_COLUMNS)])
    match_ids = pd.Index(dataset["match_id"])
    train = dataset.iloc[match_ids.get_indexer(split.train["match_id"])]
    validation = dataset.iloc[match_ids.get_indexer(split.validation["match_id"])]
    train_target = train["result"]
    validation_target = validation["result"]
    if not validation_target.isin(CLASS_ORDER).all():
        raise ValueError("Validation targets must be 0=Away, 1=Draw or 2=Home.")
    one_hot = (validation_target.to_numpy()[:, None] == np.asarray(CLASS_ORDER)).astype(float)

    results = {}
    for window in WINDOWS:
        history = load_stadium_window_history_with_ongoing(window)
        columns = ["match_id", *STADIUM_WINDOW_COLUMNS]
        stadium = pd.concat([
            frame.loc[:, columns]
            for frame in (history.historical, history.hyakunen, history.ongoing)
        ], ignore_index=True)
        ids = stadium["match_id"]
        if ids.isna().any() or not ids.is_unique or ids.astype("string").str.strip().eq("").any():
            raise ValueError("Stadium history match_id must be nonmissing, nonempty and unique.")
        if len(stadium) != len(dataset):
            raise ValueError("Row count does not match between dataset and stadium history.")
        if (pd.Index(ids).get_indexer(match_ids) < 0).any():
            raise ValueError("match_id correspondence differs between dataset and stadium history.")

        model = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)),
        ])
        model.fit(_feature_frame(train, stadium), train_target)
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")
        probabilities = model.predict_proba(_feature_frame(validation, stadium))
        results[window] = FormLogisticMetrics(
            accuracy=float(accuracy_score(validation_target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(validation_target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results
