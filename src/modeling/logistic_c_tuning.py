"""Compare five fixed L2 regularization strengths on 2024 validation only."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_final_ablation import CURRENT_BEST_COLUMNS
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.time_split import split_training_dataset


FEATURE_COLUMNS = CURRENT_BEST_COLUMNS
C_VALUES = (0.1, 0.3, 1.0, 3.0, 10.0)


def run_logistic_c_tuning(dataset: pd.DataFrame) -> dict[float, FormLogisticMetrics]:
    """Return validation metrics for five predeclared C values and fixed inputs.

    Split only the existing 24 columns, then recover train/validation rows by
    unique match_id, preserving order even with duplicate source indices.
    Test/reserved partitions are never accessed. Each pipeline fits its scaler
    and L2 classifier on train only, using the same eleven supplied features.
    Only C varies; no feature derivation, adaptive search or winner selection
    occurs. Log loss is primary, Brier score secondary and accuracy descriptive.
    Brier sums squared class errors, then averages over validation matches.
    Inputs are unchanged; no network access or model/artifact writing occurs.
    """
    split = split_training_dataset(dataset.loc[:, list(DATASET_COLUMNS)])
    match_ids = pd.Index(dataset["match_id"])
    train = dataset.iloc[match_ids.get_indexer(split.train["match_id"])]
    validation = dataset.iloc[match_ids.get_indexer(split.validation["match_id"])]
    train_features = train.loc[:, list(FEATURE_COLUMNS)]
    validation_features = validation.loc[:, list(FEATURE_COLUMNS)]
    train_target = train["result"]
    validation_target = validation["result"]
    if not validation_target.isin(CLASS_ORDER).all():
        raise ValueError("Validation targets must be 0=Away, 1=Draw or 2=Home.")
    one_hot = (validation_target.to_numpy()[:, None] == np.asarray(CLASS_ORDER)).astype(float)

    results = {}
    for c_value in C_VALUES:
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(
                penalty="l2", C=c_value, solver="lbfgs", max_iter=1000, random_state=0,
            )),
        ])
        model.fit(train_features, train_target)
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")
        probabilities = model.predict_proba(validation_features)
        results[c_value] = FormLogisticMetrics(
            accuracy=float(accuracy_score(validation_target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(validation_target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results
