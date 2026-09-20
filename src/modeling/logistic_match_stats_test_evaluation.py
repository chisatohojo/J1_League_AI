"""One-time 2025 holdout evaluation for the preselected Shots ablation."""

from dataclasses import dataclass

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

K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0
STATS_WINDOW = 5
SHOTS_FEATURES = tuple(c for c in MATCH_STATS_FORM_COLUMNS if "shots" in c)
FEATURE_SETS = {
    "A_baseline": FEATURE_COLUMNS,
    "B_baseline_plus_shots": FEATURE_COLUMNS + SHOTS_FEATURES,
}


@dataclass(frozen=True)
class TestEvaluationResult:
    train_matches: int
    test_matches: int
    metrics: dict[str, FormLogisticMetrics]


def run_logistic_match_stats_test_evaluation(dataset: pd.DataFrame) -> TestEvaluationResult:
    """Fit on 2015--2024 and evaluate exactly the 2025 holdout."""
    required = set(DATASET_COLUMNS) | set(MATCH_STATS_FORM_COLUMNS)
    missing = required - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if not dataset["match_id"].is_unique or dataset["match_id"].isna().any():
        raise ValueError("match_id must be unique and nonmissing.")
    if not dataset["season"].isin(range(2015, 2027)).all():
        raise ValueError("Unexpected season in input dataset.")
    source = dataset.loc[dataset["season"].between(2015, 2025)].copy(deep=True)
    base = source.loc[:, list(DATASET_COLUMNS)].copy(deep=True)
    train = source.loc[source["season"].between(2015, 2024)].copy(deep=True)
    test = source.loc[source["season"].eq(2025)].copy(deep=True)
    if len(train) != 3208 or len(test) != 380:
        raise ValueError(f"Expected train=3208 and test=380, got {len(train)} and {len(test)}.")

    frames = tuple(
        base.loc[base["season"].eq(season),
                  ["match_id", "season", "home_team_id", "away_team_id", "result"]].copy(deep=True)
        for season in range(2015, 2026)
    )
    replay = _replay(frames, HOME_ADVANTAGE).set_index("match_id")
    if set(replay.index) != set(source["match_id"]):
        raise ValueError("Elo replay does not exactly cover 2015-2025.")
    source["elo_diff"] = replay.loc[source["match_id"], "elo_diff"].to_numpy()
    train = source.loc[source["season"].between(2015, 2024)].copy(deep=True)
    test = source.loc[source["season"].eq(2025)].copy(deep=True)
    metrics = {}
    for name, columns in FEATURE_SETS.items():
        model = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)),
        ])
        model.fit(train.loc[:, columns], train["result"])
        if not np.array_equal(model.classes_, CLASS_ORDER):
            raise ValueError("Expected class order [0, 1, 2].")
        probabilities = model.predict_proba(test.loc[:, columns])
        target = test["result"].to_numpy()
        one_hot = (target[:, None] == np.asarray(CLASS_ORDER)).astype(float)
        metrics[name] = FormLogisticMetrics(
            accuracy=float(accuracy_score(target, model.classes_[probabilities.argmax(axis=1)])),
            log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
            brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        )
    return TestEvaluationResult(len(train), len(test), metrics)
