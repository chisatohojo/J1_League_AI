"""Compare eight predeclared, conservative LightGBM models on 2024 validation."""

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, log_loss

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.lightgbm_ablation import CLASS_ORDER, LightGBMMetrics
from src.modeling.lightgbm_ablation import FEATURE_SETS as BASELINE_FEATURE_SETS
from src.modeling.time_split import split_training_dataset


FEATURE_SETS = {
    "current_context": BASELINE_FEATURE_SETS["current_context"],
    "all_numeric": BASELINE_FEATURE_SETS["all_numeric"],
}
PARAMETER_SETS = {
    "very_small": dict(
        n_estimators=80, learning_rate=0.03, num_leaves=3, max_depth=2,
        min_child_samples=80, reg_alpha=0.0, reg_lambda=5.0,
    ),
    "small": dict(
        n_estimators=120, learning_rate=0.03, num_leaves=5, max_depth=3,
        min_child_samples=60, reg_alpha=0.0, reg_lambda=3.0,
    ),
    "small_regularized": dict(
        n_estimators=150, learning_rate=0.03, num_leaves=7, max_depth=3,
        min_child_samples=50, reg_alpha=0.5, reg_lambda=5.0,
    ),
    "conservative": dict(
        n_estimators=100, learning_rate=0.05, num_leaves=5, max_depth=3,
        min_child_samples=100, reg_alpha=1.0, reg_lambda=10.0,
    ),
}
COMMON_PARAMETERS = dict(
    objective="multiclass", num_class=3, subsample=1.0, colsample_bytree=1.0,
    random_state=0, n_jobs=1, verbosity=-1, deterministic=True, force_col_wise=True,
)


def run_lightgbm_small_tuning(dataset: pd.DataFrame) -> dict[str, dict[str, LightGBMMetrics]]:
    """Return validation metrics by feature set and fixed parameter-set name.

    Reuse the 24-column splitter and recover train/validation by match_id,
    retaining row order even with duplicate input indices. Test/reserved are
    never accessed. Each of the two existing feature sets is fitted once per
    predeclared parameter set, using train only and unchanged feature values.
    No scaling, early stopping, adaptive search, ranking or winner selection
    occurs. Log loss is the primary comparison metric, Brier score secondary,
    and accuracy descriptive. Brier sums squared class errors, then averages rows.
    Inputs are unchanged; no network access or model/artifact writing occurs.
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
    for feature_name, columns in FEATURE_SETS.items():
        train_features = train.loc[:, list(columns)]
        validation_features = validation.loc[:, list(columns)]
        results[feature_name] = {}
        for parameter_name, parameters in PARAMETER_SETS.items():
            model = LGBMClassifier(**COMMON_PARAMETERS, **parameters)
            model.fit(train_features, train_target)
            if not np.array_equal(model.classes_, CLASS_ORDER):
                raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")
            probabilities = model.predict_proba(validation_features)
            results[feature_name][parameter_name] = LightGBMMetrics(
                accuracy=float(accuracy_score(validation_target, model.classes_[probabilities.argmax(axis=1)])),
                log_loss=float(log_loss(validation_target, probabilities, labels=list(CLASS_ORDER))),
                brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
            )
    return results
