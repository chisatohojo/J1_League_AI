"""Compare four fixed feature sets using train and 2024 validation only."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics, build_feature_frame
from src.modeling.time_split import split_training_dataset


FEATURE_SETS = {
    "elo_only": ("elo_diff",),
    "elo_points": ("elo_diff", "last5_points_diff"),
    "elo_goals": ("elo_diff", "last5_goal_diff"),
    "elo_points_goals": ("elo_diff", "last5_points_diff", "last5_goal_diff"),
}


def run_logistic_ablation(dataset: pd.DataFrame) -> dict[str, FormLogisticMetrics]:
    """Return validation metrics in feature-set order, without choosing a model.

    Derive existing features once per allowed partition. Each independent
    pipeline fits its scaler and classifier on train only, including elo_only.
    Test/reserved are never accessed after splitting. Brier score is the mean
    per-match sum of squared errors over the three classes. No input mutation,
    file/network I/O, model persistence or hyperparameter search is performed.
    """
    split = split_training_dataset(dataset)
    train_features = build_feature_frame(split.train)
    validation_features = build_feature_frame(split.validation)
    train_target = split.train["result"]
    validation_target = split.validation["result"]
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
