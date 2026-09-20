"""Fixed logistic ablation for pre-match SH/CK/FK rolling features."""

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_elo_home_advantage_tuning import FEATURE_COLUMNS, _replay
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics
from src.modeling.time_split import split_training_dataset

K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0
SHOTS_FEATURES = tuple(c for c in MATCH_STATS_FORM_COLUMNS if "shots" in c)
CK_FEATURES = tuple(c for c in MATCH_STATS_FORM_COLUMNS if "_ck_" in c)
FK_FEATURES = tuple(c for c in MATCH_STATS_FORM_COLUMNS if "_fk_" in c)
FEATURE_SETS = {
    "A_baseline": FEATURE_COLUMNS,
    "B_baseline_plus_shots": FEATURE_COLUMNS + SHOTS_FEATURES,
    "C_baseline_plus_ck": FEATURE_COLUMNS + CK_FEATURES,
    "D_baseline_plus_fk": FEATURE_COLUMNS + FK_FEATURES,
    "E_baseline_plus_all": FEATURE_COLUMNS + MATCH_STATS_FORM_COLUMNS,
}


def run_logistic_match_stats_ablation(dataset: pd.DataFrame) -> dict[str, FormLogisticMetrics]:
    """Fit each fixed feature set on 2015--2023 and score 2024 only."""
    required = set(DATASET_COLUMNS) | set(MATCH_STATS_FORM_COLUMNS)
    missing = required - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    base = dataset.loc[:, list(DATASET_COLUMNS)].copy(deep=True)
    split = split_training_dataset(base)
    train_ids = set(split.train["match_id"])
    valid_ids = set(split.validation["match_id"])
    evaluated = dataset.loc[dataset["match_id"].isin(train_ids | valid_ids)].copy(deep=True)
    frames = _ordinary_frames_until_2024(base)
    replay = _replay(frames, HOME_ADVANTAGE).set_index("match_id")
    if set(replay.index) != set(evaluated["match_id"]):
        raise ValueError("Elo replay does not exactly cover train and validation.")
    elo = replay.loc[evaluated["match_id"], "elo_diff"].to_numpy()
    evaluated = evaluated.copy(deep=True)
    evaluated["elo_diff"] = elo
    train = evaluated.loc[evaluated["match_id"].isin(train_ids)]
    validation = evaluated.loc[evaluated["match_id"].isin(valid_ids)]
    target = validation["result"]
    one_hot = (target.to_numpy()[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    results = {}
    for name, columns in FEATURE_SETS.items():
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)),
        ])
        model.fit(train.loc[:, columns], train["result"])
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected class order [0, 1, 2].")
        probabilities = model.predict_proba(validation.loc[:, columns])
        results[name] = FormLogisticMetrics(
            accuracy=float(accuracy_score(target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return results


def _ordinary_frames_until_2024(base: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
    """Build replay inputs from the already loaded dataset, through 2024 only."""
    allowed = base.loc[base["season"].between(2015, 2024),
                       ["match_id", "season", "home_team_id", "away_team_id", "result"]]
    return tuple(
        allowed.loc[allowed["season"].eq(season)].copy(deep=True)
        for season in range(2015, 2025)
    )
