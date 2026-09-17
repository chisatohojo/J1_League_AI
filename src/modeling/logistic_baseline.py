"""Train an Elo-only three-class baseline on the fixed historical train split."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss

from src.modeling.time_split import split_training_dataset


FEATURE_COLUMNS = ("elo_diff",)
CLASS_ORDER = (0, 1, 2)  # Away win, Draw, Home win.


@dataclass
class BaselineMetrics:
    accuracy: float
    log_loss: float
    brier_score: float


@dataclass
class LogisticBaselineResult:
    model: LogisticRegression
    validation_metrics: BaselineMetrics
    test_metrics: BaselineMetrics


def _evaluate(model: LogisticRegression, matches: pd.DataFrame) -> BaselineMetrics:
    target = matches["result"]
    if not target.isin(CLASS_ORDER).all():
        raise ValueError("Evaluation targets must be 0=Away, 1=Draw or 2=Home.")
    probabilities = model.predict_proba(matches.loc[:, list(FEATURE_COLUMNS)])
    one_hot = (target.to_numpy()[:, None] == model.classes_).astype(float)
    return BaselineMetrics(
        accuracy=float(accuracy_score(target, model.classes_[probabilities.argmax(axis=1)])),
        log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
    )


def run_logistic_baseline(dataset: pd.DataFrame) -> LogisticBaselineResult:
    """Fit train once; evaluate validation/test without accessing reserved.

    Only elo_diff is used. The lbfgs solver fits multinomial logistic regression
    for the three classes, with fixed settings and no tuning or preprocessing.
    predict_proba columns are explicitly checked as [Away, Draw, Home]. Brier
    score is the mean per-match sum of squared errors across all three classes.
    Input data are unchanged; no files, predictions or models are persisted.
    """
    split = split_training_dataset(dataset)
    model = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=0)
    model.fit(split.train.loc[:, list(FEATURE_COLUMNS)], split.train["result"])
    if not np.array_equal(model.classes_, CLASS_ORDER):
        raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")
    return LogisticBaselineResult(
        model=model,
        validation_metrics=_evaluate(model, split.validation),
        test_metrics=_evaluate(model, split.test),
    )
