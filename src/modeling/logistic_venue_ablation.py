"""Compare four fixed venue-form feature sets on 2024 validation only."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.time_split import split_training_dataset


FEATURE_SETS = {
    "elo_only": ("elo_diff",),
    "elo_venue_points": ("elo_diff", "venue_points_diff"),
    "elo_venue_goals": ("elo_diff", "venue_goal_diff"),
    "elo_venue_points_goals": ("elo_diff", "venue_points_diff", "venue_goal_diff"),
}


def build_feature_frame(matches: pd.DataFrame) -> pd.DataFrame:
    """Derive model inputs without modifying the source columns or index."""
    return pd.DataFrame({
        "elo_diff": matches["elo_diff"],
        "venue_points_diff": (
            matches["home_last5_home_points"] - matches["away_last5_away_points"]
        ),
        "venue_goal_diff": (
            matches["home_last5_home_goal_diff"] - matches["away_last5_away_goal_diff"]
        ),
    }, index=matches.index)


def run_logistic_venue_ablation(dataset: pd.DataFrame) -> dict[str, FormLogisticMetrics]:
    """Fit on train and return validation metrics without selecting a winner.

    Project the existing 24 columns for splitting, then recover the venue
    columns by unique match_id. This preserves partition order even with
    duplicate source indices. Test/reserved partitions are never accessed.
    Brier score sums squared errors over classes, then averages over matches.
    """
    split = split_training_dataset(dataset.loc[:, list(DATASET_COLUMNS)])
    match_ids = pd.Index(dataset["match_id"])
    train = dataset.iloc[match_ids.get_indexer(split.train["match_id"])]
    validation = dataset.iloc[match_ids.get_indexer(split.validation["match_id"])]
    train_features = build_feature_frame(train)
    validation_features = build_feature_frame(validation)
    train_target = train["result"]
    validation_target = validation["result"]
    if not validation_target.isin(CLASS_ORDER).all():
        raise ValueError("Validation targets must be 0=Away, 1=Draw or 2=Home.")
    one_hot = (validation_target.to_numpy()[:, None] == np.asarray(CLASS_ORDER)).astype(float)

    results = {}
    for name, columns in FEATURE_SETS.items():
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(solver="lbfgs", max_iter=1000, random_state=0)),
        ])
        model.fit(train_features.loc[:, list(columns)], train_target)
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")
        probabilities = model.predict_proba(validation_features.loc[:, list(columns)])
        results[name] = FormLogisticMetrics(
            accuracy=float(accuracy_score(validation_target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(validation_target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results
