"""Fixed MLP versus Logistic baseline on 2020--2024 OOF folds."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling.logistic_elo_home_advantage_tuning import FEATURE_COLUMNS, _replay
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics

VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0
FEATURE_COLUMNS_FIXED = FEATURE_COLUMNS


@dataclass(frozen=True)
class MlpRollingValidationResult:
    fold_metrics: dict[int, dict[str, FormLogisticMetrics]]
    pooled_metrics: dict[str, FormLogisticMetrics]
    fold_counts: dict[int, tuple[int, int]]


def run_mlp_baseline_rolling_validation(dataset: pd.DataFrame) -> MlpRollingValidationResult:
    """Fit fresh Logistic/MLP models per fold and score validation only."""
    missing = set(DATASET_COLUMNS) - set(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if dataset["match_id"].isna().any() or not dataset["match_id"].is_unique:
        raise ValueError("match_id must be unique and nonmissing.")
    if not dataset["season"].isin(range(2015, 2027)).all():
        raise ValueError("Unexpected season in input dataset.")
    source = dataset.loc[dataset["season"].between(2015, 2024)].copy(deep=True)
    base = source.loc[:, list(DATASET_COLUMNS)].copy(deep=True)
    fold_metrics = {}
    fold_counts = {}
    pooled_targets = {name: [] for name in ("logistic", "mlp")}
    pooled_probabilities = {name: [] for name in ("logistic", "mlp")}

    for validation_season in VALIDATION_SEASONS:
        train = source.loc[source["season"].between(2015, validation_season - 1)].copy(deep=True)
        validation = source.loc[source["season"].eq(validation_season)].copy(deep=True)
        fold_counts[validation_season] = (len(train), len(validation))
        frames = tuple(
            base.loc[base["season"].eq(season),
                      ["match_id", "season", "home_team_id", "away_team_id", "result"]].copy(deep=True)
            for season in range(2015, validation_season + 1)
        )
        replay = _replay(frames, HOME_ADVANTAGE).set_index("match_id")
        allowed = pd.concat([train, validation], ignore_index=True)
        if set(replay.index) != set(allowed["match_id"]):
            raise ValueError(f"Elo replay mismatch in validation season {validation_season}.")
        allowed["elo_diff"] = replay.loc[allowed["match_id"], "elo_diff"].to_numpy()
        train = allowed.iloc[:len(train)].copy(deep=True)
        validation = allowed.iloc[len(train):].copy(deep=True)
        fold_metrics[validation_season] = {}

        logistic = Pipeline([
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)),
        ])
        logistic.fit(train.loc[:, FEATURE_COLUMNS_FIXED], train["result"])
        if not np.array_equal(logistic.classes_, CLASS_ORDER):
            raise ValueError("Expected Logistic class order [0, 1, 2].")
        logistic_probabilities = logistic.predict_proba(validation.loc[:, FEATURE_COLUMNS_FIXED])

        mlp = Pipeline([
            ("scaler", StandardScaler()),
            ("mlp", MLPClassifier(
                hidden_layer_sizes=(16,), activation="relu", solver="adam", alpha=0.01,
                learning_rate_init=0.001, max_iter=1000, random_state=0,
                early_stopping=False,
            )),
        ])
        mlp.fit(train.loc[:, FEATURE_COLUMNS_FIXED], train["result"])
        classifier = mlp.named_steps["mlp"]
        if not np.array_equal(classifier.classes_, CLASS_ORDER):
            raise ValueError("Expected MLP class order [0, 1, 2].")
        mlp_probabilities = mlp.predict_proba(validation.loc[:, FEATURE_COLUMNS_FIXED])
        target = validation["result"].to_numpy(copy=True)
        fold_metrics[validation_season]["logistic"] = _metrics(target, logistic_probabilities)
        fold_metrics[validation_season]["mlp"] = _metrics(target, mlp_probabilities)
        for name, probabilities in (("logistic", logistic_probabilities), ("mlp", mlp_probabilities)):
            pooled_targets[name].append(target.copy())
            pooled_probabilities[name].append(probabilities.copy())

    pooled_metrics = {
        name: _metrics(np.concatenate(pooled_targets[name]), np.concatenate(pooled_probabilities[name]))
        for name in pooled_targets
    }
    return MlpRollingValidationResult(fold_metrics, pooled_metrics, fold_counts)


def _metrics(target: np.ndarray, probabilities: np.ndarray) -> FormLogisticMetrics:
    one_hot = (target[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(
        accuracy=float(accuracy_score(target, np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)])),
        log_loss=float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        brier_score=float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
    )
