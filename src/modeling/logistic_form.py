"""Fit three pre-match inputs on train and evaluate only 2024 validation."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.modeling.time_split import split_training_dataset


FEATURE_COLUMNS = ("elo_diff", "last5_points_diff", "last5_goal_diff")
CLASS_ORDER = (0, 1, 2)  # Away win, Draw, Home win.


@dataclass
class FormLogisticMetrics:
    accuracy: float
    log_loss: float
    brier_score: float


@dataclass
class FormLogisticResult:
    model: Pipeline
    validation_metrics: FormLogisticMetrics


def build_feature_frame(matches: pd.DataFrame) -> pd.DataFrame:
    """Derive only the three model inputs without modifying the source frame."""
    return pd.DataFrame({
        "elo_diff": matches["elo_diff"],
        "last5_points_diff": matches["home_last5_points"] - matches["away_last5_points"],
        "last5_goal_diff": (
            (matches["home_last5_goals_for"] - matches["home_last5_goals_against"])
            - (matches["away_last5_goals_for"] - matches["away_last5_goals_against"])
        ),
    }, index=matches.index, columns=FEATURE_COLUMNS)


def run_logistic_form(dataset: pd.DataFrame) -> FormLogisticResult:
    """Fit scaler and classifier on train once; score validation only.

    The existing splitter owns season selection. Its test and reserved frames
    are never accessed here. Settings are fixed; no model selection, baseline
    rerun, calibration, persistence or file/network I/O is performed.
    """
    split = split_training_dataset(dataset)
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(solver="lbfgs", max_iter=1000, random_state=0)),
    ])
    model.fit(build_feature_frame(split.train), split.train["result"])
    if not np.array_equal(model.classes_, CLASS_ORDER):
        raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")

    target = split.validation["result"]
    if not target.isin(CLASS_ORDER).all():
        raise ValueError("Validation targets must be 0=Away, 1=Draw or 2=Home.")
    probabilities = model.predict_proba(build_feature_frame(split.validation))
    one_hot = (target.to_numpy()[:, None] == model.classes_).astype(float)
    metrics = FormLogisticMetrics(
        accuracy=float(accuracy_score(target, model.classes_[probabilities.argmax(axis=1)])),
        log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
    )
    return FormLogisticResult(model=model, validation_metrics=metrics)
