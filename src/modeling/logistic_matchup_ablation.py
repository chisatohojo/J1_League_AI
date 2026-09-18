"""Compare four fixed Elo/H2H/stadium feature sets on 2024 validation only."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.time_split import split_training_dataset


FEATURE_SETS = {
    "elo_only": ("elo_diff",),
    "elo_h2h": ("elo_diff", *MATCHUP_CONTEXT_COLUMNS[:3]),
    "elo_stadium": ("elo_diff", *MATCHUP_CONTEXT_COLUMNS[3:]),
    "elo_h2h_stadium": ("elo_diff", *MATCHUP_CONTEXT_COLUMNS),
}


def run_logistic_matchup_ablation(dataset: pd.DataFrame) -> dict[str, FormLogisticMetrics]:
    """Fit on train and return validation metrics without selecting a winner.

    Split only the original 24 columns, then recover the source rows by unique
    match_id, preserving partition order even with duplicate source indices.
    Use existing feature values directly, without deriving or recalculating
    them. Test/reserved partitions are never accessed. Brier score sums squared
    errors across the three classes and averages over validation matches.
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
    for name, columns in FEATURE_SETS.items():
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(solver="lbfgs", max_iter=1000, random_state=0)),
        ])
        model.fit(train.loc[:, list(columns)], train_target)
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")
        probabilities = model.predict_proba(validation.loc[:, list(columns)])
        results[name] = FormLogisticMetrics(
            accuracy=float(accuracy_score(validation_target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(validation_target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results
