"""Single frozen rolling-OOF evaluation for the goal timing profile family."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.matches import load_matches
from src.collect.teams import load_team_master
from src.features.goal_timing_profile import EVENT_PATH, load_goal_events
from src.modeling.player_workload_evaluation import _add_elo as _known_good_add_elo


ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
FEATURE_PATH = ROOT / "data/processed/features/2015_2024_j1_goal_timing_features.csv"
FOLDS = (2020, 2021, 2022, 2023, 2024)
CLASS_ORDER = np.array([0, 1, 2])
MODEL_PARAMS = {
    "C": 1.0,
    "solver": "lbfgs",
    "max_iter": 1000,
    "random_state": 0,
}
EXPECTED_COUNTS = {
    2020: (1530, 1435, 306, 288),
    2021: (1836, 1723, 380, 356),
    2022: (2216, 2079, 306, 289),
    2023: (2522, 2368, 306, 286),
    2024: (2828, 2654, 380, 357),
}
T0_FEATURES = ("elo_diff",)
GOAL_TIMING_FEATURES = (
    "home_mean_first_goal_minute_normalized_prior",
    "away_mean_first_goal_minute_normalized_prior",
    "home_mean_scoring_minute_normalized_prior",
    "away_mean_scoring_minute_normalized_prior",
    "home_mean_conceding_minute_normalized_prior",
    "away_mean_conceding_minute_normalized_prior",
)
T1_FEATURES = ("elo_diff", *GOAL_TIMING_FEATURES)
TIMING_DEFINITIONS = (
    (
        "prior_first_goal_timing_observations",
        "prior_first_goal_minute_normalized_sum",
        "mean_first_goal_minute_normalized_prior",
    ),
    (
        "prior_scoring_goal_events",
        "prior_scoring_minute_normalized_sum",
        "mean_scoring_minute_normalized_prior",
    ),
    (
        "prior_conceding_goal_events",
        "prior_conceding_minute_normalized_sum",
        "mean_conceding_minute_normalized_prior",
    ),
)
KNOWN_A_Y_LL = {
    2020: 1.023119734659012,
    2021: 1.0253437210487792,
    2022: 1.0940186385371449,
    2023: 1.0604285568595655,
    2024: 1.079241181120235,
}
KNOWN_A_Y_POOLED = {
    "accuracy": 0.466626936829559,
    "log_loss": 1.056065401323764,
    "brier": 0.6357323419292724,
}


class GoalTimingEvaluationError(ValueError):
    """Invalid frozen input, reference baseline, or evaluation state."""


@dataclass(frozen=True)
class FoldResult:
    season: int
    train_total: int
    train_eligible: int
    validation_total: int
    validation_eligible: int
    t0: dict[str, float]
    t1: dict[str, float]
    delta_t1_minus_t0: dict[str, float]
    a_y: dict[str, float]
    operational_t1: dict[str, float]


def _validate_probabilities(probabilities) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise GoalTimingEvaluationError("Expected N x 3 probabilities")
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise GoalTimingEvaluationError("Probabilities must be finite and in [0, 1]")
    if not np.allclose(values.sum(axis=1), 1.0):
        raise GoalTimingEvaluationError("Probability rows must sum to one")
    return values


def _metrics(target, probabilities) -> dict[str, float]:
    target = np.asarray(target, dtype=int)
    probabilities = _validate_probabilities(probabilities)
    if len(target) != len(probabilities) or not np.isin(target, CLASS_ORDER).all():
        raise GoalTimingEvaluationError("Invalid target/probability alignment")
    one_hot = (target[:, None] == CLASS_ORDER).astype(float)
    return {
        "accuracy": float(
            accuracy_score(target, CLASS_ORDER[probabilities.argmax(axis=1)])
        ),
        "log_loss": float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        "brier": float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        "count": len(target),
    }


def _fit(
    train: pd.DataFrame, validation: pd.DataFrame, features: tuple[str, ...]
) -> np.ndarray:
    if tuple(features) not in {T0_FEATURES, T1_FEATURES}:
        raise GoalTimingEvaluationError("Unfrozen model feature set")
    if (
        train.loc[:, features].isna().any().any()
        or validation.loc[:, features].isna().any().any()
    ):
        raise GoalTimingEvaluationError("Model input contains null values")
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(**MODEL_PARAMS)),
        ]
    )
    model.fit(train.loc[:, features], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise GoalTimingEvaluationError("Expected class order [0, 1, 2]")
    return _validate_probabilities(model.predict_proba(validation.loc[:, features]))


def _load_inputs(
    match_dir: str | Path = MATCH_DIR,
    feature_path: str | Path = FEATURE_PATH,
) -> pd.DataFrame:
    master = load_team_master()
    matches = pd.concat(
        [
            master.add_team_ids(
                load_matches(Path(match_dir) / f"{season}_matches_probe.csv")
            )
            for season in range(2015, 2025)
        ],
        ignore_index=True,
    )
    features = pd.read_csv(feature_path, dtype={"match_id": "string"})
    matches["match_id"] = matches.match_id.astype(str)
    features["match_id"] = features.match_id.astype(str)
    if len(matches) != 3208 or len(features) != 3208:
        raise GoalTimingEvaluationError("Expected 3,208 match and feature rows")
    if not matches.match_id.is_unique or not features.match_id.is_unique:
        raise GoalTimingEvaluationError("match_id must be unique")
    if set(matches.match_id) != set(features.match_id):
        raise GoalTimingEvaluationError("Match and feature ID sets differ")
    if set(matches.season.astype(int)) != set(range(2015, 2025)):
        raise GoalTimingEvaluationError("Expected ordinary-J1 seasons 2015-2024")

    identity_columns = (
        "match_id",
        "season",
        "match_date",
        "home_team_id",
        "away_team_id",
    )
    audit_columns = {
        f"{side}_{name}"
        for side in ("home", "away")
        for definition in TIMING_DEFINITIONS
        for name in definition
    }
    required = set(identity_columns) | audit_columns | {
        "home_goal_timing_available",
        "away_goal_timing_available",
        *GOAL_TIMING_FEATURES,
    }
    missing = required - set(features.columns)
    if missing:
        raise GoalTimingEvaluationError(
            f"Feature artifact lacks frozen columns: {sorted(missing)}"
        )
    identity = matches.loc[:, identity_columns].merge(
        features.loc[:, identity_columns],
        on="match_id",
        suffixes=("_match", "_feature"),
        validate="one_to_one",
    )
    for column in ("season", "home_team_id", "away_team_id"):
        if not identity[f"{column}_match"].astype(str).eq(
            identity[f"{column}_feature"].astype(str)
        ).all():
            raise GoalTimingEvaluationError(f"Feature identity mismatch: {column}")
    if not pd.to_datetime(identity.match_date_match).eq(
        pd.to_datetime(identity.match_date_feature)
    ).all():
        raise GoalTimingEvaluationError("Feature identity mismatch: match_date")

    feature_values = features.drop(
        columns=["season", "match_date", "home_team_id", "away_team_id"]
    )
    return matches.merge(feature_values, on="match_id", validate="one_to_one")


def _observed_minute_max(event_path: str | Path = EVENT_PATH) -> float:
    events = load_goal_events(event_path=event_path)
    if len(events) != 8377:
        raise GoalTimingEvaluationError("Expected 8,377 frozen GOAL rows")
    maximum = float(events.minute_normalized.max())
    if not np.isfinite(maximum) or maximum < 0:
        raise GoalTimingEvaluationError("Invalid observed source minute range")
    return maximum


def _add_elo(matches: pd.DataFrame) -> pd.DataFrame:
    """Directly reuse the frozen K=30/HA=175 same-date Elo replay."""
    return _known_good_add_elo(matches)


def _strict_bool(series: pd.Series, *, name: str) -> pd.Series:
    if not series.isin([True, False]).all():
        raise GoalTimingEvaluationError(f"{name} must be boolean")
    return series.astype(bool)


def _add_eligibility(
    data: pd.DataFrame, *, observed_minute_max: float
) -> pd.DataFrame:
    result = data.copy(deep=True)
    available_by_side = {}
    for side in ("home", "away"):
        available = _strict_bool(
            result[f"{side}_goal_timing_available"],
            name=f"{side}_goal_timing_available",
        )
        positive_denominators = []
        for denominator_name, sum_name, mean_name in TIMING_DEFINITIONS:
            denominator_column = f"{side}_{denominator_name}"
            sum_column = f"{side}_{sum_name}"
            mean_column = f"{side}_{mean_name}"
            denominator = pd.to_numeric(result[denominator_column], errors="coerce")
            sums = pd.to_numeric(result[sum_column], errors="coerce")
            means = pd.to_numeric(result[mean_column], errors="coerce")
            if (
                denominator.isna().any()
                or not np.isfinite(denominator).all()
                or denominator.lt(0).any()
                or not denominator.map(lambda value: float(value).is_integer()).all()
            ):
                raise GoalTimingEvaluationError("Timing denominators are invalid")
            if sums.isna().any() or not np.isfinite(sums).all() or sums.lt(0).any():
                raise GoalTimingEvaluationError("Timing sums are invalid")
            zero = denominator.eq(0)
            positive = denominator.gt(0)
            positive_denominators.append(positive)
            if sums.loc[zero].ne(0).any() or means.loc[zero].notna().any():
                raise GoalTimingEvaluationError(
                    "Zero denominator has a nonzero sum or non-null mean"
                )
            valid_positive = (
                means.loc[positive].notna().all()
                and np.isfinite(means.loc[positive]).all()
                and means.loc[positive].ge(0).all()
                and means.loc[positive].le(observed_minute_max).all()
            )
            if not valid_positive:
                raise GoalTimingEvaluationError(
                    "Positive denominator has an invalid timing mean"
                )
            if positive.any() and not np.allclose(
                means.loc[positive],
                sums.loc[positive] / denominator.loc[positive],
                rtol=0,
                atol=1e-12,
            ):
                raise GoalTimingEvaluationError(
                    "Timing mean differs from sum/denominator"
                )
            result[denominator_column] = denominator
            result[sum_column] = sums
            result[mean_column] = means
        expected_available = (
            positive_denominators[0]
            & positive_denominators[1]
            & positive_denominators[2]
        )
        if not available.eq(expected_available).all():
            raise GoalTimingEvaluationError(
                f"{side} availability contradicts denominator semantics"
            )
        available_by_side[side] = available

    candidate_values = result.loc[:, GOAL_TIMING_FEATURES]
    valid_candidates = (
        candidate_values.notna().all(axis=1)
        & np.isfinite(candidate_values.to_numpy(dtype=float)).all(axis=1)
        & candidate_values.ge(0).all(axis=1)
        & candidate_values.le(observed_minute_max).all(axis=1)
    )
    pair_available = available_by_side["home"] & available_by_side["away"]
    if (pair_available & ~valid_candidates).any():
        raise GoalTimingEvaluationError("Available pair has invalid timing means")
    result["primary_eligible"] = pair_available & valid_candidates
    return result


def _align_predictions(probabilities, source_ids, target_ids) -> np.ndarray:
    source = pd.Index(pd.Series(source_ids, dtype="string"))
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    if not source.is_unique or not target.is_unique or set(source) != set(target):
        raise GoalTimingEvaluationError("Prediction alignment IDs differ")
    aligned = pd.DataFrame(
        _validate_probabilities(probabilities), index=source
    ).reindex(target)
    if len(aligned) != len(target) or aligned.isna().any().any():
        raise GoalTimingEvaluationError("Prediction alignment is incomplete")
    return _validate_probabilities(aligned.to_numpy())


def _operational_probabilities(
    a_y_probabilities,
    a_y_ids,
    t1_probabilities,
    t1_ids,
    target_ids,
) -> np.ndarray:
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    eligible = pd.Index(pd.Series(t1_ids, dtype="string"))
    if (
        not target.is_unique
        or not eligible.is_unique
        or not set(eligible).issubset(target)
    ):
        raise GoalTimingEvaluationError("Operational prediction IDs are invalid")
    operational = _align_predictions(a_y_probabilities, a_y_ids, target).copy()
    if len(eligible):
        challenger = _align_predictions(t1_probabilities, eligible, eligible)
        challenger_by_id = pd.DataFrame(challenger, index=eligible)
        mask = target.isin(eligible)
        operational[mask] = challenger_by_id.reindex(target[mask]).to_numpy()
    return _validate_probabilities(operational)


def _pooled_metrics(target_parts, probability_parts) -> dict[str, float]:
    if not target_parts or len(target_parts) != len(probability_parts):
        raise GoalTimingEvaluationError("Invalid pooled metric parts")
    targets = np.concatenate([np.asarray(part, dtype=int) for part in target_parts])
    probabilities = np.concatenate(
        [_validate_probabilities(part) for part in probability_parts]
    )
    return _metrics(targets, probabilities)


def _fold_frames(data: pd.DataFrame, season: int) -> dict[str, pd.DataFrame]:
    train_all = data.loc[data.season.between(2015, season - 1)].copy()
    validation_all = data.loc[data.season.eq(season)].copy()
    train = train_all.loc[train_all.primary_eligible].copy()
    validation = validation_all.loc[validation_all.primary_eligible].copy()
    observed = (len(train_all), len(train), len(validation_all), len(validation))
    if observed != EXPECTED_COUNTS[season]:
        raise GoalTimingEvaluationError(
            f"Fold-count mismatch for {season}: {observed} != {EXPECTED_COUNTS[season]}"
        )
    return {
        "train_all": train_all,
        "train": train,
        "validation_all": validation_all,
        "validation": validation,
    }


def _validate_fold_counts(data: pd.DataFrame) -> None:
    for season in FOLDS:
        _fold_frames(data, season)
    if sum(EXPECTED_COUNTS[season][3] for season in FOLDS) != 1576:
        raise GoalTimingEvaluationError("Primary pooled count must be 1,576")
    if sum(EXPECTED_COUNTS[season][2] for season in FOLDS) != 1678:
        raise GoalTimingEvaluationError("Operational pooled count must be 1,678")


def _assert_same_match_ids(expected_ids, actual_ids, *, context: str) -> None:
    expected = pd.Index(pd.Series(expected_ids, dtype="string"))
    actual = pd.Index(pd.Series(actual_ids, dtype="string"))
    if not expected.is_unique or not actual.is_unique or set(expected) != set(actual):
        raise GoalTimingEvaluationError(f"T0/T1 matched IDs differ: {context}")


def _assert_same_labels(expected_labels, actual_labels, *, context: str) -> None:
    expected = np.asarray(expected_labels, dtype=int)
    actual = np.asarray(actual_labels, dtype=int)
    if not np.array_equal(expected, actual):
        raise GoalTimingEvaluationError(f"T0/T1 matched labels differ: {context}")


def _evaluate_a_y(data: pd.DataFrame) -> dict:
    """Evaluate only operational all-row A_Y; never fit matched T0 or T1."""
    contexts = []
    pooled = {"y": [], "p": []}
    for season in FOLDS:
        frames = _fold_frames(data, season)
        train_all = frames["train_all"]
        validation_all = frames["validation_all"]
        probabilities = _fit(train_all, validation_all, T0_FEATURES)
        target = validation_all.result.to_numpy(dtype=int)
        metrics = _metrics(target, probabilities)
        contexts.append(
            {
                "season": season,
                **frames,
                "target": target,
                "probabilities": probabilities,
                "metrics": metrics,
            }
        )
        pooled["y"].append(target)
        pooled["p"].append(probabilities)
    pooled_metrics = _pooled_metrics(pooled["y"], pooled["p"])
    if pooled_metrics["count"] != 1678:
        raise GoalTimingEvaluationError("Operational pooled count must be 1,678")
    return {"contexts": contexts, "pooled": pooled_metrics}


def _assert_a_y_sanity(a_y: dict) -> None:
    for context in a_y["contexts"]:
        season = context["season"]
        if not np.isclose(
            context["metrics"]["log_loss"],
            KNOWN_A_Y_LL[season],
            rtol=0,
            atol=1e-12,
        ):
            raise GoalTimingEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: A_Y {season} Log Loss"
            )
    for metric, reference in KNOWN_A_Y_POOLED.items():
        if not np.isclose(a_y["pooled"][metric], reference, rtol=0, atol=1e-12):
            raise GoalTimingEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: pooled A_Y {metric}"
            )


def frozen_decision(folds: list[FoldResult], pooled: dict) -> str:
    improved = sum(fold.t1["log_loss"] < fold.t0["log_loss"] for fold in folds)
    non_improved = len(folds) - improved
    if (
        pooled["t1"]["log_loss"] < pooled["t0"]["log_loss"]
        and pooled["t1"]["brier"] < pooled["t0"]["brier"]
        and improved >= 3
    ):
        return "CONTINUE_GOAL_TIMING_LANE"
    if (
        pooled["t1"]["log_loss"] >= pooled["t0"]["log_loss"]
        and pooled["t1"]["brier"] >= pooled["t0"]["brier"]
        and non_improved >= 3
    ):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def _evaluate_matched_after_sanity(data: pd.DataFrame, a_y: dict) -> dict:
    """Fit the one frozen T0/T1 comparison only after A_Y sanity passes."""
    folds = []
    pooled = {key: [] for key in ("y", "t0_p", "t1_p", "op_y", "op_p")}
    for context in a_y["contexts"]:
        season = context["season"]
        train = context["train"]
        validation = context["validation"]
        validation_all = context["validation_all"]
        train_ids = train.match_id.astype(str).tolist()
        validation_ids = validation.match_id.astype(str).tolist()
        train_labels = train.result.to_numpy(dtype=int).copy()
        validation_labels = validation.result.to_numpy(dtype=int).copy()

        t0_probabilities = _fit(train, validation, T0_FEATURES)
        _assert_same_match_ids(train_ids, train.match_id, context=f"{season} train")
        _assert_same_match_ids(
            validation_ids, validation.match_id, context=f"{season} validation"
        )
        _assert_same_labels(train_labels, train.result, context=f"{season} train")
        _assert_same_labels(
            validation_labels, validation.result, context=f"{season} validation"
        )
        t1_probabilities = _fit(train, validation, T1_FEATURES)
        target = validation.result.to_numpy(dtype=int)
        t0_metrics = _metrics(target, t0_probabilities)
        t1_metrics = _metrics(target, t1_probabilities)
        operational_probabilities = _operational_probabilities(
            context["probabilities"],
            validation_all.match_id,
            t1_probabilities,
            validation.match_id,
            validation_all.match_id,
        )
        operational_metrics = _metrics(context["target"], operational_probabilities)
        delta = {
            metric: t1_metrics[metric] - t0_metrics[metric]
            for metric in ("accuracy", "log_loss", "brier")
        }
        folds.append(
            FoldResult(
                season=season,
                train_total=len(context["train_all"]),
                train_eligible=len(train),
                validation_total=len(validation_all),
                validation_eligible=len(validation),
                t0=t0_metrics,
                t1=t1_metrics,
                delta_t1_minus_t0=delta,
                a_y=context["metrics"],
                operational_t1=operational_metrics,
            )
        )
        for key, value in (
            ("y", target),
            ("t0_p", t0_probabilities),
            ("t1_p", t1_probabilities),
            ("op_y", context["target"]),
            ("op_p", operational_probabilities),
        ):
            pooled[key].append(value)

    pooled_metrics = {
        "t0": _pooled_metrics(pooled["y"], pooled["t0_p"]),
        "t1": _pooled_metrics(pooled["y"], pooled["t1_p"]),
        "a_y": a_y["pooled"],
        "operational_t1": _pooled_metrics(pooled["op_y"], pooled["op_p"]),
    }
    if pooled_metrics["t0"]["count"] != 1576:
        raise GoalTimingEvaluationError("Primary T0 pooled count must be 1,576")
    if pooled_metrics["t1"]["count"] != 1576:
        raise GoalTimingEvaluationError("Primary T1 pooled count must be 1,576")
    if pooled_metrics["operational_t1"]["count"] != 1678:
        raise GoalTimingEvaluationError("Operational T1 count must be 1,678")
    improved = sum(fold.t1["log_loss"] < fold.t0["log_loss"] for fold in folds)
    return {
        "folds": folds,
        "pooled": pooled_metrics,
        "matched_pooled_n": 1576,
        "operational_pooled_n": 1678,
        "log_loss_improved_folds": improved,
        "baseline_sanity": "PASS",
        "decision": frozen_decision(folds, pooled_metrics),
    }


def evaluate_goal_timing(
    *,
    match_dir: str | Path = MATCH_DIR,
    feature_path: str | Path = FEATURE_PATH,
    event_path: str | Path = EVENT_PATH,
) -> dict:
    # Identity, artifact invariants, and frozen counts are established before Elo.
    data = _load_inputs(match_dir, feature_path)
    data = _add_eligibility(
        data, observed_minute_max=_observed_minute_max(event_path)
    )
    _validate_fold_counts(data)
    data = _add_elo(data)

    # A_Y is the mandatory gate. No matched T0 or T1 is fit before it passes.
    a_y = _evaluate_a_y(data)
    _assert_a_y_sanity(a_y)
    return _evaluate_matched_after_sanity(data, a_y)


def _json_result(result: dict) -> dict:
    return {
        "folds": [asdict(fold) for fold in result["folds"]],
        "pooled": result["pooled"],
        "matched_pooled_n": result["matched_pooled_n"],
        "operational_pooled_n": result["operational_pooled_n"],
        "log_loss_improved_folds": result["log_loss_improved_folds"],
        "baseline_sanity": result["baseline_sanity"],
        "decision": result["decision"],
    }


if __name__ == "__main__":
    print(json.dumps(_json_result(evaluate_goal_timing()), indent=2, sort_keys=True))
