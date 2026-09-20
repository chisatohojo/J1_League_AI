"""2020--2024 rolling comparison of fixed Elo Logistic and manager context."""
from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.manager_context import FEATURE_COLUMNS, add_manager_context_features
from src.modeling.benchmark_suite import VALIDATION_SEASONS, _metrics, _with_replayed_elo

K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0
ELO_ONLY_FEATURES = ("elo_diff",)
MANAGER_FEATURES = (*ELO_ONLY_FEATURES, *FEATURE_COLUMNS)


@dataclass(frozen=True)
class ManagerRollingResult:
    fold_metrics: dict[int, dict[str, object]]
    pooled_metrics: dict[str, object]
    diagnostics: dict[int, object]
    fold_counts: dict[int, tuple[int, int]]


def run_logistic_manager_rolling_validation(dataset: pd.DataFrame, manager_history: pd.DataFrame) -> ManagerRollingResult:
    source = add_manager_context_features(dataset.loc[dataset.season.between(2015, 2024)].copy(deep=True), manager_history)
    fold_metrics, diagnostics, counts = {}, {}, {}
    pooled_targets = {"elo_only": [], "elo_manager": []}; pooled_probs = {"elo_only": [], "elo_manager": []}
    for season in VALIDATION_SEASONS:
        train = source[source.season.between(2015, season - 1)].copy(deep=True)
        validation = source[source.season.eq(season)].copy(deep=True)
        counts[season] = (len(train), len(validation))
        train, validation = _with_replayed_elo(source, train, validation, season)
        target = validation.result.to_numpy(copy=True)
        fold_metrics[season] = {}
        for name, columns in (("elo_only", ELO_ONLY_FEATURES), ("elo_manager", MANAGER_FEATURES)):
            model = Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0))])
            model.fit(train.loc[:, columns], train.result)
            if not np.array_equal(model.classes_, np.array([0, 1, 2])): raise ValueError("class order mismatch")
            probabilities = model.predict_proba(validation.loc[:, columns])
            fold_metrics[season][name] = _metrics(target, probabilities)
            pooled_targets[name].append(target); pooled_probs[name].append(probabilities)
        app = pd.concat([validation[["home_manager_known", "home_manager_change_known", "home_manager_changed", "home_manager_prior_matches_in_charge"]].rename(columns=lambda x:x.replace("home_","")), validation[["away_manager_known", "away_manager_change_known", "away_manager_changed", "away_manager_prior_matches_in_charge"]].rename(columns=lambda x:x.replace("away_", ""))], ignore_index=True)
        diagnostics[season] = {"manager_known_rate": float(app.manager_known.mean()), "manager_change_known_rate": float(app.manager_change_known.mean()), "manager_changed": int(app.manager_changed.sum()), "prior_min": int(app.manager_prior_matches_in_charge.min()), "prior_median": float(app.manager_prior_matches_in_charge.median()), "prior_mean": float(app.manager_prior_matches_in_charge.mean()), "prior_max": int(app.manager_prior_matches_in_charge.max()), "changed_matches": int(((validation.home_manager_changed==1)|(validation.away_manager_changed==1)).sum()), "known_unchanged_matches": int(((validation.home_manager_change_known.eq(1)) & validation.home_manager_changed.eq(0)).sum()), "unknown_matches": int(((validation.home_manager_known.eq(0))|(validation.away_manager_known.eq(0))).sum())}
    pooled = {n: _metrics(np.concatenate(pooled_targets[n]), np.concatenate(pooled_probs[n])) for n in pooled_targets}
    return ManagerRollingResult(fold_metrics, pooled, diagnostics, counts)
