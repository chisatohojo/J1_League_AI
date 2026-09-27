"""Single frozen rolling-OOF evaluation for the first-score profile family."""

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
from src.modeling.player_workload_evaluation import _add_elo as _known_good_add_elo


ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
FEATURE_PATH = ROOT / "data/processed/features/2015_2024_j1_first_score_features.csv"
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
F0_FEATURES = ("elo_diff",)
FIRST_SCORE_FEATURES = (
    "home_scored_first_rate_prior",
    "away_scored_first_rate_prior",
    "home_conceded_first_rate_prior",
    "away_conceded_first_rate_prior",
)
F1_FEATURES = ("elo_diff", *FIRST_SCORE_FEATURES)
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
KNOWN_F0_POOLED = {
    "accuracy": 0.46842427958307786,
    "log_loss": 1.0554404541978801,
    "brier": 0.6352814612200155,
}


class FirstScoreEvaluationError(ValueError):
    """Invalid frozen input, reference baseline, or evaluation state."""


@dataclass(frozen=True)
class FoldResult:
    season: int
    train_total: int
    train_eligible: int
    validation_total: int
    validation_eligible: int
    f0: dict[str, float]
    f1: dict[str, float]
    delta_f1_minus_f0: dict[str, float]
    a_y: dict[str, float]
    operational_f1: dict[str, float]


def _validate_probabilities(probabilities) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise FirstScoreEvaluationError("Expected N x 3 probabilities")
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise FirstScoreEvaluationError("Probabilities must be finite and in [0, 1]")
    if not np.allclose(values.sum(axis=1), 1.0):
        raise FirstScoreEvaluationError("Probability rows must sum to one")
    return values


def _metrics(target, probabilities) -> dict[str, float]:
    target = np.asarray(target, dtype=int)
    probabilities = _validate_probabilities(probabilities)
    if len(target) != len(probabilities) or not np.isin(target, CLASS_ORDER).all():
        raise FirstScoreEvaluationError("Invalid target/probability alignment")
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
    if tuple(features) not in {F0_FEATURES, F1_FEATURES}:
        raise FirstScoreEvaluationError("Unfrozen model feature set")
    if train.loc[:, features].isna().any().any() or validation.loc[:, features].isna().any().any():
        raise FirstScoreEvaluationError("Model input contains null values")
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(**MODEL_PARAMS)),
        ]
    )
    model.fit(train.loc[:, features], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise FirstScoreEvaluationError("Expected class order [0, 1, 2]")
    return _validate_probabilities(
        model.predict_proba(validation.loc[:, features])
    )


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
        raise FirstScoreEvaluationError("Expected 3,208 match and feature rows")
    if not matches.match_id.is_unique or not features.match_id.is_unique:
        raise FirstScoreEvaluationError("match_id must be unique")
    if set(matches.match_id) != set(features.match_id):
        raise FirstScoreEvaluationError("Match and feature ID sets differ")
    if set(matches.season.astype(int)) != set(range(2015, 2025)):
        raise FirstScoreEvaluationError("Expected ordinary-J1 seasons 2015-2024")

    identity_columns = (
        "match_id",
        "season",
        "match_date",
        "home_team_id",
        "away_team_id",
    )
    missing = set(identity_columns) | {
        "home_first_score_available",
        "away_first_score_available",
        *FIRST_SCORE_FEATURES,
    }
    missing -= set(features.columns)
    if missing:
        raise FirstScoreEvaluationError(
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
            raise FirstScoreEvaluationError(f"Feature identity mismatch: {column}")
    if not pd.to_datetime(identity.match_date_match).eq(
        pd.to_datetime(identity.match_date_feature)
    ).all():
        raise FirstScoreEvaluationError("Feature identity mismatch: match_date")

    feature_values = features.drop(
        columns=["season", "match_date", "home_team_id", "away_team_id"]
    )
    return matches.merge(feature_values, on="match_id", validate="one_to_one")


def _add_elo(matches: pd.DataFrame) -> pd.DataFrame:
    """Directly reuse the frozen K=30/HA=175 same-date Elo replay."""
    return _known_good_add_elo(matches)


def _strict_bool(series: pd.Series, *, name: str) -> pd.Series:
    if not series.isin([True, False]).all():
        raise FirstScoreEvaluationError(f"{name} must be boolean")
    return series.astype(bool)


def _add_eligibility(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy(deep=True)
    home_available = _strict_bool(
        result.home_first_score_available, name="home_first_score_available"
    )
    away_available = _strict_bool(
        result.away_first_score_available, name="away_first_score_available"
    )
    if (home_available != away_available).any():
        raise FirstScoreEvaluationError("Partial first-score availability")

    values = result.loc[:, FIRST_SCORE_FEATURES].apply(pd.to_numeric, errors="coerce")
    home_columns = (
        "home_scored_first_rate_prior",
        "home_conceded_first_rate_prior",
    )
    away_columns = (
        "away_scored_first_rate_prior",
        "away_conceded_first_rate_prior",
    )
    for side, available, columns in (
        ("home", home_available, home_columns),
        ("away", away_available, away_columns),
    ):
        side_values = values.loc[:, columns]
        valid = (
            side_values.notna().all(axis=1)
            & np.isfinite(side_values.to_numpy(dtype=float)).all(axis=1)
            & side_values.ge(0).all(axis=1)
            & side_values.le(1).all(axis=1)
        )
        if (available & ~valid).any():
            raise FirstScoreEvaluationError(
                f"Available {side} first-score profile is partial or invalid"
            )
        if ((~available) & side_values.notna().any(axis=1)).any():
            raise FirstScoreEvaluationError(
                f"Unavailable {side} first-score profile has non-null rates"
            )
    result.loc[:, FIRST_SCORE_FEATURES] = values
    result["primary_eligible"] = home_available & away_available
    return result


def _align_predictions(probabilities, source_ids, target_ids) -> np.ndarray:
    source = pd.Index(pd.Series(source_ids, dtype="string"))
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    if not source.is_unique or not target.is_unique or set(source) != set(target):
        raise FirstScoreEvaluationError("Prediction alignment IDs differ")
    aligned = pd.DataFrame(
        _validate_probabilities(probabilities), index=source
    ).reindex(target)
    if len(aligned) != len(target) or aligned.isna().any().any():
        raise FirstScoreEvaluationError("Prediction alignment is incomplete")
    return _validate_probabilities(aligned.to_numpy())


def _operational_probabilities(
    a_y_probabilities,
    a_y_ids,
    f1_probabilities,
    f1_ids,
    target_ids,
) -> np.ndarray:
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    eligible = pd.Index(pd.Series(f1_ids, dtype="string"))
    if not target.is_unique or not eligible.is_unique or not set(eligible).issubset(target):
        raise FirstScoreEvaluationError("Operational prediction IDs are invalid")
    operational = _align_predictions(a_y_probabilities, a_y_ids, target).copy()
    if len(eligible):
        challenger = _align_predictions(f1_probabilities, eligible, eligible)
        challenger_by_id = pd.DataFrame(challenger, index=eligible)
        mask = target.isin(eligible)
        operational[mask] = challenger_by_id.reindex(target[mask]).to_numpy()
    return _validate_probabilities(operational)


def _pooled_metrics(target_parts, probability_parts) -> dict[str, float]:
    if not target_parts or len(target_parts) != len(probability_parts):
        raise FirstScoreEvaluationError("Invalid pooled metric parts")
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
        raise FirstScoreEvaluationError(
            f"Fold-count mismatch for {season}: {observed} != {EXPECTED_COUNTS[season]}"
        )
    return {
        "train_all": train_all,
        "train": train,
        "validation_all": validation_all,
        "validation": validation,
    }


def _assert_same_match_ids(expected_ids, actual_ids, *, context: str) -> None:
    expected = pd.Index(pd.Series(expected_ids, dtype="string"))
    actual = pd.Index(pd.Series(actual_ids, dtype="string"))
    if not expected.is_unique or not actual.is_unique or set(expected) != set(actual):
        raise FirstScoreEvaluationError(f"F0/F1 matched IDs differ: {context}")


def _evaluate_baselines(data: pd.DataFrame) -> dict:
    """Run only A_Y and matched F0; this function never fits F1."""
    contexts = []
    pooled = {key: [] for key in ("f0_y", "f0_p", "op_y", "a_y_p")}
    for season in FOLDS:
        frames = _fold_frames(data, season)
        train_all = frames["train_all"]
        train = frames["train"]
        validation_all = frames["validation_all"]
        validation = frames["validation"]

        a_y_probabilities = _fit(train_all, validation_all, F0_FEATURES)
        f0_probabilities = _fit(train, validation, F0_FEATURES)
        primary_target = validation.result.to_numpy(dtype=int)
        operational_target = validation_all.result.to_numpy(dtype=int)
        a_y_metrics = _metrics(operational_target, a_y_probabilities)
        f0_metrics = _metrics(primary_target, f0_probabilities)
        contexts.append(
            {
                "season": season,
                **frames,
                "train_ids": train.match_id.astype(str).tolist(),
                "validation_ids": validation.match_id.astype(str).tolist(),
                "primary_target": primary_target,
                "operational_target": operational_target,
                "a_y_probabilities": a_y_probabilities,
                "f0_probabilities": f0_probabilities,
                "a_y": a_y_metrics,
                "f0": f0_metrics,
            }
        )
        for key, value in (
            ("f0_y", primary_target),
            ("f0_p", f0_probabilities),
            ("op_y", operational_target),
            ("a_y_p", a_y_probabilities),
        ):
            pooled[key].append(value)

    pooled_metrics = {
        "f0": _pooled_metrics(pooled["f0_y"], pooled["f0_p"]),
        "a_y": _pooled_metrics(pooled["op_y"], pooled["a_y_p"]),
    }
    if pooled_metrics["f0"]["count"] != 1631:
        raise FirstScoreEvaluationError("Primary pooled count must be 1,631")
    if pooled_metrics["a_y"]["count"] != 1678:
        raise FirstScoreEvaluationError("Operational pooled count must be 1,678")
    return {"contexts": contexts, "pooled": pooled_metrics}


def _assert_baseline_sanity(baseline: dict) -> None:
    for context in baseline["contexts"]:
        season = context["season"]
        if not np.isclose(
            context["a_y"]["log_loss"],
            KNOWN_A_Y_LL[season],
            rtol=0,
            atol=1e-12,
        ):
            raise FirstScoreEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: A_Y {season} Log Loss"
            )
    for baseline_name, expected in (
        ("a_y", KNOWN_A_Y_POOLED),
        ("f0", KNOWN_F0_POOLED),
    ):
        for metric, reference in expected.items():
            if not np.isclose(
                baseline["pooled"][baseline_name][metric],
                reference,
                rtol=0,
                atol=1e-12,
            ):
                raise FirstScoreEvaluationError(
                    f"BLOCKED_REFERENCE_MISMATCH: pooled {baseline_name} {metric}"
                )


def frozen_decision(folds: list[FoldResult], pooled: dict) -> str:
    improved = sum(fold.f1["log_loss"] < fold.f0["log_loss"] for fold in folds)
    non_improved = len(folds) - improved
    if (
        pooled["f1"]["log_loss"] < pooled["f0"]["log_loss"]
        and pooled["f1"]["brier"] < pooled["f0"]["brier"]
        and improved >= 3
    ):
        return "CONTINUE_FIRST_SCORE_LANE"
    if (
        pooled["f1"]["log_loss"] >= pooled["f0"]["log_loss"]
        and pooled["f1"]["brier"] >= pooled["f0"]["brier"]
        and non_improved >= 3
    ):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def _evaluate_f1_after_sanity(baseline: dict) -> dict:
    """Fit F1 only after the caller has completed the reference gate."""
    folds = []
    pooled = {key: [] for key in ("y", "f1_p", "op_y", "op_p")}
    for context in baseline["contexts"]:
        train = context["train"]
        validation = context["validation"]
        validation_all = context["validation_all"]
        _assert_same_match_ids(
            context["train_ids"], train.match_id, context=f"{context['season']} train"
        )
        _assert_same_match_ids(
            context["validation_ids"],
            validation.match_id,
            context=f"{context['season']} validation",
        )
        f1_probabilities = _fit(train, validation, F1_FEATURES)
        operational_probabilities = _operational_probabilities(
            context["a_y_probabilities"],
            validation_all.match_id,
            f1_probabilities,
            validation.match_id,
            validation_all.match_id,
        )
        f1_metrics = _metrics(context["primary_target"], f1_probabilities)
        operational_metrics = _metrics(
            context["operational_target"], operational_probabilities
        )
        f0_metrics = context["f0"]
        delta = {
            metric: f1_metrics[metric] - f0_metrics[metric]
            for metric in ("accuracy", "log_loss", "brier")
        }
        folds.append(
            FoldResult(
                season=context["season"],
                train_total=len(context["train_all"]),
                train_eligible=len(train),
                validation_total=len(validation_all),
                validation_eligible=len(validation),
                f0=f0_metrics,
                f1=f1_metrics,
                delta_f1_minus_f0=delta,
                a_y=context["a_y"],
                operational_f1=operational_metrics,
            )
        )
        for key, value in (
            ("y", context["primary_target"]),
            ("f1_p", f1_probabilities),
            ("op_y", context["operational_target"]),
            ("op_p", operational_probabilities),
        ):
            pooled[key].append(value)

    pooled_metrics = {
        "f0": baseline["pooled"]["f0"],
        "f1": _pooled_metrics(pooled["y"], pooled["f1_p"]),
        "a_y": baseline["pooled"]["a_y"],
        "operational_f1": _pooled_metrics(pooled["op_y"], pooled["op_p"]),
    }
    if pooled_metrics["f1"]["count"] != 1631:
        raise FirstScoreEvaluationError("F1 pooled count must be 1,631")
    if pooled_metrics["operational_f1"]["count"] != 1678:
        raise FirstScoreEvaluationError("Operational F1 count must be 1,678")
    improved = sum(fold.f1["log_loss"] < fold.f0["log_loss"] for fold in folds)
    return {
        "folds": folds,
        "pooled": pooled_metrics,
        "matched_pooled_n": 1631,
        "operational_pooled_n": 1678,
        "log_loss_improved_folds": improved,
        "baseline_sanity": "PASS",
        "decision": frozen_decision(folds, pooled_metrics),
    }


def evaluate_first_score(
    *,
    match_dir: str | Path = MATCH_DIR,
    feature_path: str | Path = FEATURE_PATH,
) -> dict:
    data = _add_eligibility(_add_elo(_load_inputs(match_dir, feature_path)))
    baseline = _evaluate_baselines(data)
    _assert_baseline_sanity(baseline)
    # This call is intentionally unreachable after any baseline reference failure.
    return _evaluate_f1_after_sanity(baseline)


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
    print(json.dumps(_json_result(evaluate_first_score()), indent=2, sort_keys=True))
