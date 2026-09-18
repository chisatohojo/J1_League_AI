"""Compare five fixed LightGBM feature sets using only 2024 validation."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.metrics import accuracy_score, log_loss

from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.time_split import split_training_dataset


CLASS_ORDER = (0, 1, 2)
H2H_COLUMNS = ("h2h_last5_matches", "h2h_last5_points_diff", "h2h_last5_goal_diff")
STADIUM_COLUMNS = (
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
)
PREVIOUS_MATCH_FLAGS = ("home_has_previous_match", "away_has_previous_match")
RAW_GAP_COLUMNS = ("home_days_since_last_match", "away_days_since_last_match")
CURRENT_CONTEXT_COLUMNS = ("elo_diff", *STADIUM_COLUMNS, *RAW_GAP_COLUMNS, *PREVIOUS_MATCH_FLAGS)
FEATURE_SETS = {
    "elo_only": ("elo_diff",),
    "current_context": CURRENT_CONTEXT_COLUMNS,
    "current_context_momentum": (*CURRENT_CONTEXT_COLUMNS, *ELO_MOMENTUM_COLUMNS),
    "current_context_h2h_momentum": (*CURRENT_CONTEXT_COLUMNS, *ELO_MOMENTUM_COLUMNS, *H2H_COLUMNS),
    "all_numeric": (
        "home_elo", "away_elo", "elo_diff",
        "home_last5_points", "away_last5_points",
        "home_last5_wins", "away_last5_wins",
        "home_last5_draws", "away_last5_draws",
        "home_last5_losses", "away_last5_losses",
        "home_last5_goals_for", "away_last5_goals_for",
        "home_last5_goals_against", "away_last5_goals_against",
        *H2H_COLUMNS, *STADIUM_COLUMNS,
        *RAW_GAP_COLUMNS, "days_since_last_match_diff", *PREVIOUS_MATCH_FLAGS,
        *ELO_MOMENTUM_COLUMNS,
    ),
}


@dataclass
class LightGBMMetrics:
    accuracy: float
    log_loss: float
    brier_score: float


def run_lightgbm_ablation(dataset: pd.DataFrame) -> dict[str, LightGBMMetrics]:
    """Fit five fixed models on train and return validation metrics without ranking.

    Pass only the original 24 columns to the existing splitter, then recover
    train/validation rows by unique match_id, including when indices repeat.
    Test/reserved partitions are never accessed. Use supplied features as-is,
    with no scaling, imputation, feature derivation, early stopping or tuning.
    Probability columns are [Away, Draw, Home]. Multiclass Brier score sums
    squared errors across classes and averages over validation matches.
    No input is modified, network accessed, or model/artifact written.
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
        model = LGBMClassifier(
            objective="multiclass",
            num_class=3,
            n_estimators=100,
            learning_rate=0.05,
            num_leaves=15,
            max_depth=-1,
            min_child_samples=20,
            subsample=1.0,
            colsample_bytree=1.0,
            reg_alpha=0.0,
            reg_lambda=0.0,
            random_state=0,
            n_jobs=1,
            verbosity=-1,
            deterministic=True,
            force_col_wise=True,
        )
        model.fit(train.loc[:, list(columns)], train_target)
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected model.classes_ in [0, 1, 2] (Away, Draw, Home) order.")
        probabilities = model.predict_proba(validation.loc[:, list(columns)])
        results[name] = LightGBMMetrics(
            accuracy=float(accuracy_score(validation_target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(validation_target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results
