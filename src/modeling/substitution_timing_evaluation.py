"""Single frozen rolling-OOF evaluation for substitution timing features."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
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
from src.modeling.player_workload_evaluation import _add_elo as _known_good_add_elo


ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
FEATURE_PATH = (
    ROOT / "data/processed/features/2015_2024_j1_substitution_timing_features.csv"
)
FEATURE_SHA256 = "898c7d53ed429d36920fd67b218333d837f5d2604c99c3556e47584721b9161f"
FOLDS = (2020, 2021, 2022, 2023, 2024)
CLASS_ORDER = np.array([0, 1, 2])
MODEL_PARAMS = {
    "C": 1.0,
    "solver": "lbfgs",
    "max_iter": 1000,
    "random_state": 0,
}
EXPECTED_COUNTS = {
    2020: (1530, 1485, 306, 297),
    2021: (1836, 1782, 380, 370),
    2022: (2216, 2152, 306, 297),
    2023: (2522, 2449, 306, 297),
    2024: (2828, 2746, 380, 370),
}
S0_FEATURES = ("elo_diff",)
SUBSTITUTION_TIMING_FEATURES = (
    "home_mean_substitution_minute_normalized_prior",
    "away_mean_substitution_minute_normalized_prior",
)
S1_FEATURES = ("elo_diff", *SUBSTITUTION_TIMING_FEATURES)
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


class SubstitutionTimingEvaluationError(ValueError):
    """Invalid frozen input, reference baseline, or evaluation state."""


@dataclass(frozen=True)
class FoldResult:
    season: int
    train_total: int
    train_eligible: int
    validation_total: int
    validation_eligible: int
    s0: dict[str, float]
    s1: dict[str, float]
    delta_s1_minus_s0: dict[str, float]
    a_y: dict[str, float]
    operational_s1: dict[str, float]


def _validate_feature_sha(
    path: str | Path, *, expected_sha256: str = FEATURE_SHA256
) -> str:
    feature_path = Path(path)
    try:
        digest = hashlib.sha256(feature_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise SubstitutionTimingEvaluationError(
            f"Missing feature artifact: {feature_path}"
        ) from exc
    if digest != expected_sha256:
        raise SubstitutionTimingEvaluationError(
            f"Feature artifact SHA-256 mismatch: {digest} != {expected_sha256}"
        )
    return digest


def _validate_probabilities(probabilities) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise SubstitutionTimingEvaluationError("Expected N x 3 probabilities")
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise SubstitutionTimingEvaluationError(
            "Probabilities must be finite and in [0, 1]"
        )
    if not np.allclose(values.sum(axis=1), 1.0):
        raise SubstitutionTimingEvaluationError(
            "Probability rows must sum to one"
        )
    return values


def _metrics(target, probabilities) -> dict[str, float]:
    target = np.asarray(target, dtype=int)
    probabilities = _validate_probabilities(probabilities)
    if len(target) != len(probabilities) or not np.isin(target, CLASS_ORDER).all():
        raise SubstitutionTimingEvaluationError(
            "Invalid target/probability alignment"
        )
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
    if tuple(features) not in {S0_FEATURES, S1_FEATURES}:
        raise SubstitutionTimingEvaluationError("Unfrozen model feature set")
    if (
        train.loc[:, features].isna().any().any()
        or validation.loc[:, features].isna().any().any()
    ):
        raise SubstitutionTimingEvaluationError("Model input contains null values")
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(**MODEL_PARAMS)),
        ]
    )
    model.fit(train.loc[:, features], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise SubstitutionTimingEvaluationError("Expected class order [0, 1, 2]")
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
        raise SubstitutionTimingEvaluationError(
            "Expected 3,208 match and feature rows"
        )
    if not matches.match_id.is_unique or not features.match_id.is_unique:
        raise SubstitutionTimingEvaluationError("match_id must be unique")
    if set(matches.match_id) != set(features.match_id):
        raise SubstitutionTimingEvaluationError("Match and feature ID sets differ")
    if set(matches.season.astype(int)) != set(range(2015, 2025)):
        raise SubstitutionTimingEvaluationError(
            "Expected ordinary-J1 seasons 2015-2024"
        )

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
        for name in (
            "substitution_timing_available",
            "prior_substitution_events",
            "prior_substitution_minute_normalized_sum",
            "mean_substitution_minute_normalized_prior",
        )
    }
    missing = set(identity_columns) | audit_columns
    missing -= set(features.columns)
    if missing:
        raise SubstitutionTimingEvaluationError(
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
            raise SubstitutionTimingEvaluationError(
                f"Feature identity mismatch: {column}"
            )
    if not pd.to_datetime(identity.match_date_match).eq(
        pd.to_datetime(identity.match_date_feature)
    ).all():
        raise SubstitutionTimingEvaluationError(
            "Feature identity mismatch: match_date"
        )

    feature_values = features.drop(
        columns=["season", "match_date", "home_team_id", "away_team_id"]
    )
    return matches.merge(feature_values, on="match_id", validate="one_to_one")


def _add_elo(matches: pd.DataFrame) -> pd.DataFrame:
    """Directly reuse the frozen K=30/HA=175 same-date Elo replay."""
    return _known_good_add_elo(matches)


def _strict_bool(series: pd.Series, *, name: str) -> pd.Series:
    if not series.isin([True, False]).all():
        raise SubstitutionTimingEvaluationError(f"{name} must be boolean")
    return series.astype(bool)


def _add_eligibility(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy(deep=True)
    available_by_side = {}
    for side in ("home", "away"):
        available_column = f"{side}_substitution_timing_available"
        denominator_column = f"{side}_prior_substitution_events"
        sum_column = f"{side}_prior_substitution_minute_normalized_sum"
        mean_column = f"{side}_mean_substitution_minute_normalized_prior"
        available = _strict_bool(result[available_column], name=available_column)
        denominator = pd.to_numeric(result[denominator_column], errors="coerce")
        sums = pd.to_numeric(result[sum_column], errors="coerce")
        means = pd.to_numeric(result[mean_column], errors="coerce")
        if (
            denominator.isna().any()
            or not np.isfinite(denominator).all()
            or denominator.lt(0).any()
            or not denominator.map(lambda value: float(value).is_integer()).all()
        ):
            raise SubstitutionTimingEvaluationError(
                "Timing denominators are invalid"
            )
        if sums.isna().any() or not np.isfinite(sums).all() or sums.lt(0).any():
            raise SubstitutionTimingEvaluationError("Timing sums are invalid")
        zero = denominator.eq(0)
        positive = denominator.gt(0)
        if (
            sums.loc[zero].ne(0).any()
            or means.loc[zero].notna().any()
            or available.loc[zero].any()
        ):
            raise SubstitutionTimingEvaluationError(
                "Unavailable side contradicts zero-denominator semantics"
            )
        valid_positive = (
            means.loc[positive].notna().all()
            and np.isfinite(means.loc[positive]).all()
            and means.loc[positive].ge(3).all()
            and means.loc[positive].le(90).all()
        )
        if not valid_positive:
            raise SubstitutionTimingEvaluationError(
                "Available side has an invalid timing mean"
            )
        if positive.any() and not np.allclose(
            means.loc[positive],
            sums.loc[positive] / denominator.loc[positive],
            rtol=0,
            atol=1e-12,
        ):
            raise SubstitutionTimingEvaluationError(
                "Timing mean differs from sum/denominator"
            )
        if not available.eq(positive).all():
            raise SubstitutionTimingEvaluationError(
                f"{side} availability contradicts denominator semantics"
            )
        result[denominator_column] = denominator
        result[sum_column] = sums
        result[mean_column] = means
        available_by_side[side] = available

    values = result.loc[:, SUBSTITUTION_TIMING_FEATURES]
    valid_values = (
        values.notna().all(axis=1)
        & np.isfinite(values.to_numpy(dtype=float)).all(axis=1)
        & values.ge(3).all(axis=1)
        & values.le(90).all(axis=1)
    )
    pair_available = available_by_side["home"] & available_by_side["away"]
    if (pair_available & ~valid_values).any():
        raise SubstitutionTimingEvaluationError(
            "Available pair has invalid timing means"
        )
    result["primary_eligible"] = pair_available & valid_values
    return result


def _align_predictions(probabilities, source_ids, target_ids) -> np.ndarray:
    source = pd.Index(pd.Series(source_ids, dtype="string"))
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    if not source.is_unique or not target.is_unique or set(source) != set(target):
        raise SubstitutionTimingEvaluationError("Prediction alignment IDs differ")
    aligned = pd.DataFrame(
        _validate_probabilities(probabilities), index=source
    ).reindex(target)
    if len(aligned) != len(target) or aligned.isna().any().any():
        raise SubstitutionTimingEvaluationError(
            "Prediction alignment is incomplete"
        )
    return _validate_probabilities(aligned.to_numpy())


def _operational_probabilities(
    a_y_probabilities,
    a_y_ids,
    s1_probabilities,
    s1_ids,
    target_ids,
) -> np.ndarray:
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    eligible = pd.Index(pd.Series(s1_ids, dtype="string"))
    if (
        not target.is_unique
        or not eligible.is_unique
        or not set(eligible).issubset(target)
    ):
        raise SubstitutionTimingEvaluationError(
            "Operational prediction IDs are invalid"
        )
    operational = _align_predictions(a_y_probabilities, a_y_ids, target).copy()
    if len(eligible):
        challenger = _align_predictions(s1_probabilities, eligible, eligible)
        challenger_by_id = pd.DataFrame(challenger, index=eligible)
        mask = target.isin(eligible)
        operational[mask] = challenger_by_id.reindex(target[mask]).to_numpy()
    return _validate_probabilities(operational)


def _pooled_metrics(target_parts, probability_parts) -> dict[str, float]:
    if not target_parts or len(target_parts) != len(probability_parts):
        raise SubstitutionTimingEvaluationError("Invalid pooled metric parts")
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
        raise SubstitutionTimingEvaluationError(
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
    if sum(EXPECTED_COUNTS[season][3] for season in FOLDS) != 1631:
        raise SubstitutionTimingEvaluationError(
            "Primary pooled count must be 1,631"
        )
    if sum(EXPECTED_COUNTS[season][2] for season in FOLDS) != 1678:
        raise SubstitutionTimingEvaluationError(
            "Operational pooled count must be 1,678"
        )


def _assert_same_match_ids(expected_ids, actual_ids, *, context: str) -> None:
    expected = pd.Index(pd.Series(expected_ids, dtype="string"))
    actual = pd.Index(pd.Series(actual_ids, dtype="string"))
    if not expected.is_unique or not actual.is_unique or set(expected) != set(actual):
        raise SubstitutionTimingEvaluationError(
            f"S0/S1 matched IDs differ: {context}"
        )


def _assert_same_labels(expected_labels, actual_labels, *, context: str) -> None:
    expected = np.asarray(expected_labels, dtype=int)
    actual = np.asarray(actual_labels, dtype=int)
    if not np.array_equal(expected, actual):
        raise SubstitutionTimingEvaluationError(
            f"S0/S1 matched labels differ: {context}"
        )


def _evaluate_a_y(data: pd.DataFrame) -> dict:
    """Evaluate only operational all-row A_Y; never fit matched S0 or S1."""
    contexts = []
    pooled = {"y": [], "p": []}
    for season in FOLDS:
        frames = _fold_frames(data, season)
        train_all = frames["train_all"]
        validation_all = frames["validation_all"]
        probabilities = _fit(train_all, validation_all, S0_FEATURES)
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
        raise SubstitutionTimingEvaluationError(
            "Operational pooled count must be 1,678"
        )
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
            raise SubstitutionTimingEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: A_Y {season} Log Loss"
            )
    for metric, reference in KNOWN_A_Y_POOLED.items():
        if not np.isclose(a_y["pooled"][metric], reference, rtol=0, atol=1e-12):
            raise SubstitutionTimingEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: pooled A_Y {metric}"
            )


def frozen_decision(folds: list[FoldResult], pooled: dict) -> str:
    improved = sum(fold.s1["log_loss"] < fold.s0["log_loss"] for fold in folds)
    non_improved = len(folds) - improved
    if (
        pooled["s1"]["log_loss"] < pooled["s0"]["log_loss"]
        and pooled["s1"]["brier"] < pooled["s0"]["brier"]
        and improved >= 3
    ):
        return "CONTINUE_SUBSTITUTION_TIMING_LANE"
    if (
        pooled["s1"]["log_loss"] >= pooled["s0"]["log_loss"]
        and pooled["s1"]["brier"] >= pooled["s0"]["brier"]
        and non_improved >= 3
    ):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def _evaluate_matched_after_sanity(data: pd.DataFrame, a_y: dict) -> dict:
    """Fit the one frozen S0/S1 comparison only after A_Y sanity passes."""
    folds = []
    pooled = {key: [] for key in ("y", "s0_p", "s1_p", "op_y", "op_p")}
    for context in a_y["contexts"]:
        season = context["season"]
        train = context["train"]
        validation = context["validation"]
        validation_all = context["validation_all"]
        train_ids = train.match_id.astype(str).tolist()
        validation_ids = validation.match_id.astype(str).tolist()
        train_labels = train.result.to_numpy(dtype=int).copy()
        validation_labels = validation.result.to_numpy(dtype=int).copy()

        s0_probabilities = _fit(train, validation, S0_FEATURES)
        _assert_same_match_ids(train_ids, train.match_id, context=f"{season} train")
        _assert_same_match_ids(
            validation_ids, validation.match_id, context=f"{season} validation"
        )
        _assert_same_labels(train_labels, train.result, context=f"{season} train")
        _assert_same_labels(
            validation_labels, validation.result, context=f"{season} validation"
        )
        s1_probabilities = _fit(train, validation, S1_FEATURES)
        target = validation.result.to_numpy(dtype=int)
        s0_metrics = _metrics(target, s0_probabilities)
        s1_metrics = _metrics(target, s1_probabilities)
        operational_probabilities = _operational_probabilities(
            context["probabilities"],
            validation_all.match_id,
            s1_probabilities,
            validation.match_id,
            validation_all.match_id,
        )
        operational_metrics = _metrics(context["target"], operational_probabilities)
        delta = {
            metric: s1_metrics[metric] - s0_metrics[metric]
            for metric in ("accuracy", "log_loss", "brier")
        }
        folds.append(
            FoldResult(
                season=season,
                train_total=len(context["train_all"]),
                train_eligible=len(train),
                validation_total=len(validation_all),
                validation_eligible=len(validation),
                s0=s0_metrics,
                s1=s1_metrics,
                delta_s1_minus_s0=delta,
                a_y=context["metrics"],
                operational_s1=operational_metrics,
            )
        )
        for key, value in (
            ("y", target),
            ("s0_p", s0_probabilities),
            ("s1_p", s1_probabilities),
            ("op_y", context["target"]),
            ("op_p", operational_probabilities),
        ):
            pooled[key].append(value)

    pooled_metrics = {
        "s0": _pooled_metrics(pooled["y"], pooled["s0_p"]),
        "s1": _pooled_metrics(pooled["y"], pooled["s1_p"]),
        "a_y": a_y["pooled"],
        "operational_s1": _pooled_metrics(pooled["op_y"], pooled["op_p"]),
    }
    if pooled_metrics["s0"]["count"] != 1631:
        raise SubstitutionTimingEvaluationError(
            "Primary S0 pooled count must be 1,631"
        )
    if pooled_metrics["s1"]["count"] != 1631:
        raise SubstitutionTimingEvaluationError(
            "Primary S1 pooled count must be 1,631"
        )
    if pooled_metrics["operational_s1"]["count"] != 1678:
        raise SubstitutionTimingEvaluationError(
            "Operational S1 count must be 1,678"
        )
    improved = sum(fold.s1["log_loss"] < fold.s0["log_loss"] for fold in folds)
    return {
        "folds": folds,
        "pooled": pooled_metrics,
        "matched_pooled_n": 1631,
        "operational_pooled_n": 1678,
        "log_loss_improved_folds": improved,
        "baseline_sanity": "PASS",
        "decision": frozen_decision(folds, pooled_metrics),
    }


def evaluate_substitution_timing(
    *,
    match_dir: str | Path = MATCH_DIR,
    feature_path: str | Path = FEATURE_PATH,
) -> dict:
    _validate_feature_sha(feature_path)
    data = _load_inputs(match_dir, feature_path)
    data = _add_eligibility(data)
    _validate_fold_counts(data)
    data = _add_elo(data)

    # A_Y is mandatory. No matched S0 or S1 is fit before all references pass.
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
    print(
        json.dumps(
            _json_result(evaluate_substitution_timing()),
            indent=2,
            sort_keys=True,
        )
    )
