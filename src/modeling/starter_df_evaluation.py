"""Single frozen rolling-OOF evaluation for previous-match starter DF counts."""

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
    ROOT / "data/processed/features/2015_2024_j1_starter_df_features.csv"
)
FEATURE_SHA256 = "056963dd4707f122754d596ac6865721052cc3a31589a3a02941faca683aa674"
FOLDS = (2020, 2021, 2022, 2023, 2024)
CLASS_ORDER = np.array([0, 1, 2])
MODEL_PARAMS = {
    "C": 1.0,
    "solver": "lbfgs",
    "max_iter": 1000,
    "random_state": 0,
}
EXPECTED_SEASON_COUNTS = {
    **{season: 306 for season in range(2015, 2021)},
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
EXPECTED_PAIR_ELIGIBLE = {
    **{season: 297 for season in range(2015, 2021)},
    2021: 370,
    2022: 297,
    2023: 297,
    2024: 370,
}
EXPECTED_COUNTS = {
    2020: (1530, 1485, 306, 297),
    2021: (1836, 1782, 380, 370),
    2022: (2216, 2152, 306, 297),
    2023: (2522, 2449, 306, 297),
    2024: (2828, 2746, 380, 370),
}
FEATURE_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
    "home_starter_df_available",
    "away_starter_df_available",
    "home_previous_match_id",
    "away_previous_match_id",
    "home_previous_match_date",
    "away_previous_match_date",
    "home_previous_match_starter_df_count",
    "away_previous_match_starter_df_count",
)
IDENTITY_COLUMNS = FEATURE_COLUMNS[:5]
STARTER_DF_FEATURES = (
    "home_previous_match_starter_df_count",
    "away_previous_match_starter_df_count",
)
S0_FEATURES = ("elo_diff",)
S1_FEATURES = ("elo_diff", *STARTER_DF_FEATURES)
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
EXISTING_MATCHED_BASELINE_REUSED = False


class StarterDFEvaluationError(ValueError):
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
        raise StarterDFEvaluationError(
            f"Missing feature artifact: {feature_path}"
        ) from exc
    if digest != expected_sha256:
        raise StarterDFEvaluationError(
            f"Feature artifact SHA-256 mismatch: {digest} != {expected_sha256}"
        )
    return digest


def _validate_probabilities(probabilities) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise StarterDFEvaluationError("Expected N x 3 probabilities")
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise StarterDFEvaluationError(
            "Probabilities must be finite and in [0, 1]"
        )
    if not np.allclose(values.sum(axis=1), 1.0):
        raise StarterDFEvaluationError("Probability rows must sum to one")
    return values


def _metrics(target, probabilities) -> dict[str, float]:
    target = np.asarray(target, dtype=int)
    probabilities = _validate_probabilities(probabilities)
    if len(target) != len(probabilities) or not np.isin(target, CLASS_ORDER).all():
        raise StarterDFEvaluationError("Invalid target/probability alignment")
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
        raise StarterDFEvaluationError("Unfrozen model feature set")
    if (
        train.loc[:, features].isna().any().any()
        or validation.loc[:, features].isna().any().any()
    ):
        raise StarterDFEvaluationError("Model input contains null values")
    model = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("logistic", LogisticRegression(**MODEL_PARAMS)),
        ]
    )
    model.fit(train.loc[:, features], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise StarterDFEvaluationError("Expected class order [0, 1, 2]")
    return _validate_probabilities(model.predict_proba(validation.loc[:, features]))


def _load_target_matches(match_dir: str | Path = MATCH_DIR) -> pd.DataFrame:
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
    matches["match_id"] = matches.match_id.astype(str)
    matches["home_team_id"] = matches.home_team_id.astype(str)
    matches["away_team_id"] = matches.away_team_id.astype(str)
    if len(matches) != 3208 or not matches.match_id.is_unique:
        raise StarterDFEvaluationError(
            "Expected 3,208 unique ordinary-J1 target matches"
        )
    observed = matches.groupby("season").size().astype(int).to_dict()
    if observed != EXPECTED_SEASON_COUNTS:
        raise StarterDFEvaluationError(
            f"Target season counts differ: {observed} != {EXPECTED_SEASON_COUNTS}"
        )
    return matches


def _read_feature_artifact(feature_path: str | Path = FEATURE_PATH) -> pd.DataFrame:
    id_columns = {
        "match_id": "string",
        "home_team_id": "string",
        "away_team_id": "string",
        "home_previous_match_id": "string",
        "away_previous_match_id": "string",
    }
    try:
        return pd.read_csv(feature_path, dtype=id_columns)
    except (OSError, ValueError) as exc:
        raise StarterDFEvaluationError(
            f"Cannot read feature artifact: {feature_path}"
        ) from exc


def _validate_target_feature_identity(
    matches: pd.DataFrame, features: pd.DataFrame
) -> None:
    missing = set(IDENTITY_COLUMNS) - set(features.columns)
    if missing:
        raise StarterDFEvaluationError(
            f"Feature identity columns missing: {sorted(missing)}"
        )
    if len(features) != 3208 or not features.match_id.is_unique:
        raise StarterDFEvaluationError(
            "Expected 3,208 unique feature artifact match IDs"
        )
    match_ids = set(matches.match_id.astype(str))
    feature_ids = set(features.match_id.astype(str))
    if match_ids != feature_ids:
        raise StarterDFEvaluationError("Target and feature match-ID sets differ")
    identity = matches.loc[:, IDENTITY_COLUMNS].merge(
        features.loc[:, IDENTITY_COLUMNS],
        on="match_id",
        suffixes=("_target", "_feature"),
        validate="one_to_one",
    )
    for column in ("season", "home_team_id", "away_team_id"):
        if not identity[f"{column}_target"].astype(str).eq(
            identity[f"{column}_feature"].astype(str)
        ).all():
            raise StarterDFEvaluationError(f"Feature identity mismatch: {column}")
    target_dates = pd.to_datetime(identity.match_date_target, errors="coerce")
    feature_dates = pd.to_datetime(identity.match_date_feature, errors="coerce")
    if (
        target_dates.isna().any()
        or feature_dates.isna().any()
        or not target_dates.eq(feature_dates).all()
    ):
        raise StarterDFEvaluationError("Feature identity mismatch: match_date")


def _validate_exact_schema(features: pd.DataFrame) -> None:
    if tuple(features.columns) != FEATURE_COLUMNS:
        raise StarterDFEvaluationError(
            "Feature artifact schema differs from the frozen ordered 13 columns"
        )


def _merge_inputs(matches: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    feature_values = features.drop(
        columns=["season", "match_date", "home_team_id", "away_team_id"]
    )
    return matches.merge(feature_values, on="match_id", validate="one_to_one")


def _load_inputs(
    match_dir: str | Path = MATCH_DIR,
    feature_path: str | Path = FEATURE_PATH,
) -> pd.DataFrame:
    matches = _load_target_matches(match_dir)
    features = _read_feature_artifact(feature_path)
    _validate_target_feature_identity(matches, features)
    _validate_exact_schema(features)
    return _merge_inputs(matches, features)


def _add_elo(matches: pd.DataFrame) -> pd.DataFrame:
    """Directly reuse the frozen K=30/HA=175 same-date Elo replay."""
    return _known_good_add_elo(matches)


def _strict_bool(series: pd.Series, *, name: str) -> pd.Series:
    if not series.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise StarterDFEvaluationError(f"{name} must be boolean")
    return series.astype(bool)


def _add_eligibility(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy(deep=True)
    target_dates = pd.to_datetime(result["match_date"], errors="coerce")
    if target_dates.isna().any():
        raise StarterDFEvaluationError("Target match_date is invalid")

    available_by_side = {}
    valid_by_side = {}
    for side in ("home", "away"):
        available_column = f"{side}_starter_df_available"
        id_column = f"{side}_previous_match_id"
        date_column = f"{side}_previous_match_date"
        count_column = f"{side}_previous_match_starter_df_count"
        available = _strict_bool(result[available_column], name=available_column)
        unavailable = ~available
        raw_ids = result[id_column]
        raw_dates = result[date_column]
        raw_counts = result[count_column]
        previous_dates = pd.to_datetime(raw_dates, errors="coerce")
        counts = pd.to_numeric(raw_counts, errors="coerce")

        if (
            raw_ids.loc[unavailable].notna().any()
            or raw_dates.loc[unavailable].notna().any()
            or raw_counts.loc[unavailable].notna().any()
        ):
            raise StarterDFEvaluationError(
                f"Unavailable {side} side has non-null previous-match state"
            )

        valid_available = pd.Series(True, index=result.index)
        if available.any():
            available_ids = raw_ids.loc[available]
            available_counts = counts.loc[available]
            valid_available.loc[available] = (
                available_ids.notna()
                & available_ids.astype("string").str.strip().ne("")
                & previous_dates.loc[available].notna()
                & previous_dates.loc[available].lt(target_dates.loc[available])
                & available_counts.notna()
                & np.isfinite(available_counts)
                & available_counts.map(lambda value: float(value).is_integer())
                & available_counts.between(2, 6)
            )
        if not valid_available.loc[available].all():
            raise StarterDFEvaluationError(
                f"Available {side} side has invalid previous-match state"
            )

        result[count_column] = counts
        available_by_side[side] = available
        valid_by_side[side] = valid_available

    pair_available = available_by_side["home"] & available_by_side["away"]
    valid_pair = valid_by_side["home"] & valid_by_side["away"]
    if (pair_available & ~valid_pair).any():
        raise StarterDFEvaluationError("Available pair has invalid DF counts")
    result["primary_eligible"] = pair_available & valid_pair
    return result


def _align_predictions(probabilities, source_ids, target_ids) -> np.ndarray:
    source = pd.Index(pd.Series(source_ids, dtype="string"))
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    values = _validate_probabilities(probabilities)
    if len(values) != len(source):
        raise StarterDFEvaluationError("Prediction rows and source IDs differ")
    if not source.is_unique or not target.is_unique or set(source) != set(target):
        raise StarterDFEvaluationError("Prediction alignment IDs differ")
    aligned = pd.DataFrame(values, index=source).reindex(target)
    if len(aligned) != len(target) or aligned.isna().any().any():
        raise StarterDFEvaluationError("Prediction alignment is incomplete")
    return _validate_probabilities(aligned.to_numpy())


def _operational_probabilities(
    a_y_probabilities,
    a_y_ids,
    s1_probabilities,
    s1_ids,
    target_ids,
    eligible_ids,
) -> np.ndarray:
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    eligible = pd.Index(pd.Series(eligible_ids, dtype="string"))
    challenger_ids = pd.Index(pd.Series(s1_ids, dtype="string"))
    if (
        not target.is_unique
        or not eligible.is_unique
        or not challenger_ids.is_unique
        or not set(eligible).issubset(target)
        or set(challenger_ids) != set(eligible)
    ):
        raise StarterDFEvaluationError("Operational prediction IDs are invalid")
    operational = _align_predictions(a_y_probabilities, a_y_ids, target).copy()
    if len(eligible):
        challenger = _align_predictions(s1_probabilities, challenger_ids, eligible)
        mask = target.isin(eligible)
        operational[mask] = pd.DataFrame(challenger, index=eligible).reindex(
            target[mask]
        ).to_numpy()
    return _validate_probabilities(operational)


def _pooled_metrics(target_parts, probability_parts) -> dict[str, float]:
    if not target_parts or len(target_parts) != len(probability_parts):
        raise StarterDFEvaluationError("Invalid pooled metric parts")
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
        raise StarterDFEvaluationError(
            f"Fold-count mismatch for {season}: {observed} != {EXPECTED_COUNTS[season]}"
        )
    return {
        "train_all": train_all,
        "train": train,
        "validation_all": validation_all,
        "validation": validation,
    }


def _validate_frozen_counts(data: pd.DataFrame) -> None:
    home = data.home_starter_df_available.astype(bool)
    away = data.away_starter_df_available.astype(bool)
    eligible = data.primary_eligible.astype(bool)
    for season in range(2015, 2025):
        season_rows = data.season.eq(season)
        observed = (int(season_rows.sum()), int((season_rows & eligible).sum()))
        expected = (EXPECTED_SEASON_COUNTS[season], EXPECTED_PAIR_ELIGIBLE[season])
        if observed != expected:
            raise StarterDFEvaluationError(
                f"Season availability mismatch for {season}: {observed} != {expected}"
            )
    global_counts = (
        int(eligible.sum()),
        int((~eligible).sum()),
        int((home & ~away).sum()),
        int((~home & away).sum()),
        int((~home & ~away).sum()),
    )
    if global_counts != (3116, 92, 0, 0, 92):
        raise StarterDFEvaluationError(
            f"Global frozen availability mismatch: {global_counts}"
        )
    for season in FOLDS:
        _fold_frames(data, season)
    if sum(EXPECTED_COUNTS[season][3] for season in FOLDS) != 1631:
        raise StarterDFEvaluationError("Primary pooled count must be 1,631")
    if sum(EXPECTED_COUNTS[season][2] for season in FOLDS) != 1678:
        raise StarterDFEvaluationError("Operational pooled count must be 1,678")


def _assert_same_match_ids(expected_ids, actual_ids, *, context: str) -> None:
    expected = pd.Index(pd.Series(expected_ids, dtype="string"))
    actual = pd.Index(pd.Series(actual_ids, dtype="string"))
    if not expected.is_unique or not actual.is_unique or set(expected) != set(actual):
        raise StarterDFEvaluationError(f"S0/S1 matched IDs differ: {context}")


def _assert_same_labels(expected_labels, actual_labels, *, context: str) -> None:
    expected = np.asarray(expected_labels, dtype=int)
    actual = np.asarray(actual_labels, dtype=int)
    if not np.array_equal(expected, actual):
        raise StarterDFEvaluationError(f"S0/S1 matched labels differ: {context}")


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
        raise StarterDFEvaluationError("Operational pooled count must be 1,678")
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
            raise StarterDFEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: A_Y {season} Log Loss"
            )
    for metric, reference in KNOWN_A_Y_POOLED.items():
        if not np.isclose(a_y["pooled"][metric], reference, rtol=0, atol=1e-12):
            raise StarterDFEvaluationError(
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
        return "CONTINUE_STARTER_DF_LANE"
    if (
        pooled["s1"]["log_loss"] >= pooled["s0"]["log_loss"]
        and pooled["s1"]["brier"] >= pooled["s0"]["brier"]
        and non_improved >= 3
    ):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def _evaluate_matched_after_sanity(data: pd.DataFrame, a_y: dict) -> dict:
    """Fit the one frozen matched S0/S1 comparison after A_Y sanity passes."""
    folds = []
    pooled = {key: [] for key in ("y", "s0_p", "s1_p", "op_y", "op_p")}
    for context in a_y["contexts"]:
        season = context["season"]
        train = context["train"]
        validation = context["validation"]
        validation_all = context["validation_all"]

        s0_train = train.copy()
        s1_train = train.copy()
        s0_validation = validation.copy()
        s1_validation = validation.copy()
        _assert_same_match_ids(
            s0_train.match_id, s1_train.match_id, context=f"{season} train"
        )
        _assert_same_match_ids(
            s0_validation.match_id,
            s1_validation.match_id,
            context=f"{season} validation",
        )
        _assert_same_labels(
            s0_train.result, s1_train.result, context=f"{season} train"
        )
        _assert_same_labels(
            s0_validation.result,
            s1_validation.result,
            context=f"{season} validation",
        )

        s0_probabilities = _fit(s0_train, s0_validation, S0_FEATURES)
        s1_probabilities = _fit(s1_train, s1_validation, S1_FEATURES)
        _assert_same_match_ids(
            s0_train.match_id, s1_train.match_id, context=f"{season} train post-fit"
        )
        _assert_same_match_ids(
            s0_validation.match_id,
            s1_validation.match_id,
            context=f"{season} validation post-fit",
        )
        _assert_same_labels(
            s0_validation.result,
            s1_validation.result,
            context=f"{season} validation post-fit",
        )

        target = s0_validation.result.to_numpy(dtype=int)
        s0_metrics = _metrics(target, s0_probabilities)
        s1_metrics = _metrics(target, s1_probabilities)
        operational_probabilities = _operational_probabilities(
            context["probabilities"],
            validation_all.match_id,
            s1_probabilities,
            s1_validation.match_id,
            validation_all.match_id,
            validation.match_id,
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
        raise StarterDFEvaluationError("Primary S0 pooled count must be 1,631")
    if pooled_metrics["s1"]["count"] != 1631:
        raise StarterDFEvaluationError("Primary S1 pooled count must be 1,631")
    if pooled_metrics["operational_s1"]["count"] != 1678:
        raise StarterDFEvaluationError("Operational S1 count must be 1,678")
    improved = sum(fold.s1["log_loss"] < fold.s0["log_loss"] for fold in folds)
    return {
        "folds": folds,
        "pooled": pooled_metrics,
        "matched_pooled_n": 1631,
        "operational_pooled_n": 1678,
        "log_loss_improved_folds": improved,
        "baseline_sanity": "PASS",
        "existing_matched_baseline_reference_reused": (
            EXISTING_MATCHED_BASELINE_REUSED
        ),
        "decision": frozen_decision(folds, pooled_metrics),
    }


def evaluate_starter_df(
    *,
    match_dir: str | Path = MATCH_DIR,
    feature_path: str | Path = FEATURE_PATH,
) -> dict:
    # Mandatory gate order: digest, identity/schema/invariants/counts, Elo, A_Y.
    _validate_feature_sha(feature_path)
    data = _load_inputs(match_dir, feature_path)
    data = _add_eligibility(data)
    _validate_frozen_counts(data)
    data = _add_elo(data)

    # No matched S0 or S1 is fit until every frozen A_Y reference passes.
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
        "existing_matched_baseline_reference_reused": result[
            "existing_matched_baseline_reference_reused"
        ],
        "decision": result["decision"],
    }


if __name__ == "__main__":
    print(json.dumps(_json_result(evaluate_starter_df()), indent=2, sort_keys=True))
