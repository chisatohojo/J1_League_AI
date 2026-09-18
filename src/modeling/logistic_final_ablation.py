"""Compare four fixed Logistic Regression feature sets on 2024 validation."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.logistic_schedule_gap_ablation import FEATURE_SETS as SCHEDULE_FEATURE_SETS
from src.modeling.time_split import split_training_dataset


CURRENT_BEST_COLUMNS = SCHEDULE_FEATURE_SETS["elo_stadium_gap_raw"]
FEATURE_SETS = {
    "current_best": CURRENT_BEST_COLUMNS,
    "current_best_momentum": (*CURRENT_BEST_COLUMNS, *ELO_MOMENTUM_COLUMNS),
    "current_best_momentum_h2h": (
        *CURRENT_BEST_COLUMNS, *ELO_MOMENTUM_COLUMNS, *MATCHUP_CONTEXT_COLUMNS[:3],
    ),
    "all_numeric": (
        "home_elo", "away_elo", "elo_diff",
        "home_last5_points", "away_last5_points",
        "home_last5_wins", "away_last5_wins",
        "home_last5_draws", "away_last5_draws",
        "home_last5_losses", "away_last5_losses",
        "home_last5_goals_for", "away_last5_goals_for",
        "home_last5_goals_against", "away_last5_goals_against",
        *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS, *ELO_MOMENTUM_COLUMNS,
    ),
}


def run_logistic_final_ablation(dataset: pd.DataFrame) -> dict[str, FormLogisticMetrics]:
    """Fit four train-only pipelines and return validation metrics without ranking.

    Split only the existing 24 columns, then recover train/validation rows by
    unique match_id, preserving order even when source indices repeat. Never
    access test/reserved partitions. Select existing features unchanged; fit
    both StandardScaler and LogisticRegression on train within each pipeline.
    Brier score sums squared class errors and averages validation matches.
    Compare log loss primarily, Brier secondarily and accuracy descriptively;
    no winner selection or tuning occurs. No inputs are modified, new features
    calculated, files written or network accessed.
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
