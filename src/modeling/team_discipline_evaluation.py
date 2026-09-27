"""Single frozen rolling-OOF evaluation for the team-discipline feature family."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.matches import load_matches
from src.collect.teams import load_team_master
from src.features.elo import EloRatings


ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
FEATURE_PATH = ROOT / "data/processed/features/2015_2024_j1_team_discipline_features.csv"
VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
CLASS_ORDER = np.array([0, 1, 2])
MODEL_PARAMS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
EXPECTED_COUNTS = {
    2020: (1530, 1485, 306, 297), 2021: (1836, 1782, 380, 370),
    2022: (2216, 2152, 306, 297), 2023: (2522, 2449, 306, 297),
    2024: (2828, 2746, 380, 370),
}
D0_FEATURES = ("elo_diff",)
D1_FEATURES = (
    "elo_diff", "home_yellow_cards_per_match_prior",
    "away_yellow_cards_per_match_prior", "home_red_cards_per_match_prior",
    "away_red_cards_per_match_prior",
)
KNOWN_A_Y_LL = {
    2020: 1.023119734659012, 2021: 1.0253437210487792,
    2022: 1.0940186385371449, 2023: 1.0604285568595655,
    2024: 1.079241181120235,
}
KNOWN_A_Y_POOLED = {
    "accuracy": 0.466626936829559, "log_loss": 1.056065401323764,
    "brier": 0.6357323419292724,
}
KNOWN_D0_POOLED = {
    "accuracy": 0.46842427958307786, "log_loss": 1.0554404541978801,
    "brier": 0.6352814612200155,
}


class TeamDisciplineEvaluationError(ValueError):
    """Invalid frozen input, baseline, or evaluation contract."""


@dataclass(frozen=True)
class FoldResult:
    season: int
    train_total: int
    train_eligible: int
    validation_total: int
    validation_eligible: int
    d0: dict[str, float]
    d1: dict[str, float]
    a_y: dict[str, float]
    operational_d1: dict[str, float]


def _validate_probabilities(probabilities) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise TeamDisciplineEvaluationError("Expected N x 3 probabilities")
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise TeamDisciplineEvaluationError("Invalid probability matrix")
    if not np.allclose(values.sum(axis=1), 1.0):
        raise TeamDisciplineEvaluationError("Probability rows must sum to one")
    return values


def _metrics(target, probabilities) -> dict[str, float]:
    target = np.asarray(target, dtype=int)
    probabilities = _validate_probabilities(probabilities)
    one_hot = (target[:, None] == CLASS_ORDER).astype(float)
    return {
        "accuracy": float(accuracy_score(target, CLASS_ORDER[probabilities.argmax(axis=1)])),
        "log_loss": float(log_loss(target, probabilities, labels=[0, 1, 2])),
        "brier": float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
        "count": len(target),
    }


def _load_inputs(match_dir: str | Path = MATCH_DIR,
                 feature_path: str | Path = FEATURE_PATH) -> pd.DataFrame:
    master = load_team_master()
    matches = pd.concat([
        master.add_team_ids(load_matches(Path(match_dir) / f"{season}_matches_probe.csv"))
        for season in range(2015, 2025)
    ], ignore_index=True)
    features = pd.read_csv(feature_path, dtype={"match_id": "string"})
    matches["match_id"] = matches.match_id.astype(str)
    features["match_id"] = features.match_id.astype(str)
    if len(matches) != 3208 or len(features) != 3208:
        raise TeamDisciplineEvaluationError("Expected 3,208 ordinary-J1 and feature rows")
    if not matches.match_id.is_unique or not features.match_id.is_unique:
        raise TeamDisciplineEvaluationError("match_id must be unique")
    if set(matches.match_id) != set(features.match_id):
        raise TeamDisciplineEvaluationError("Match and feature ID sets differ")
    identity = matches[["match_id", "season", "match_date", "home_team_id", "away_team_id"]].merge(
        features[["match_id", "season", "match_date", "home_team_id", "away_team_id"]],
        on="match_id", suffixes=("_match", "_feature"), validate="one_to_one",
    )
    for column in ("season", "home_team_id", "away_team_id"):
        if not identity[f"{column}_match"].astype(str).eq(identity[f"{column}_feature"].astype(str)).all():
            raise TeamDisciplineEvaluationError(f"Feature identity mismatch: {column}")
    if not pd.to_datetime(identity.match_date_match).eq(pd.to_datetime(identity.match_date_feature)).all():
        raise TeamDisciplineEvaluationError("Feature identity mismatch: match_date")
    feature_values = features.drop(
        columns=["season", "match_date", "home_team_id", "away_team_id"]
    )
    return matches.merge(feature_values, on="match_id", validate="one_to_one")


def _add_elo(matches: pd.DataFrame) -> pd.DataFrame:
    """Replay frozen K=30/HA=175 Elo and batch all same-date updates."""
    ordered = matches.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    appearances = pd.concat([
        ordered[["match_date", f"{side}_team_id"]].rename(columns={f"{side}_team_id": "team_id"})
        for side in ("home", "away")
    ], ignore_index=True)
    if appearances.duplicated(["match_date", "team_id"]).any():
        raise TeamDisciplineEvaluationError("A team appears more than once on the same date")
    team_ids = sorted(set(ordered.home_team_id) | set(ordered.away_team_id))
    elo = EloRatings(team_ids, k_factor=30.0, home_advantage=175.0)
    elo_diff = pd.Series(index=ordered.index, dtype=float)
    for _, day_rows in ordered.groupby("match_date", sort=True):
        for row in day_rows.itertuples():
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            elo_diff.loc[row.Index] = before.home_rating - before.away_rating
        for row in day_rows.itertuples():
            elo.update(row.home_team_id, row.away_team_id, int(row.result))
    ordered["elo_diff"] = elo_diff
    return ordered


def _eligible(frame: pd.DataFrame) -> pd.Series:
    values = frame.loc[:, D1_FEATURES[1:]].apply(pd.to_numeric, errors="coerce")
    return (
        frame.home_discipline_available.astype(bool)
        & frame.away_discipline_available.astype(bool)
        & values.notna().all(axis=1)
        & np.isfinite(values.to_numpy(dtype=float)).all(axis=1)
        & values.ge(0).all(axis=1)
    )


def _fit(train: pd.DataFrame, validation: pd.DataFrame,
         columns: tuple[str, ...]) -> np.ndarray:
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(**MODEL_PARAMS)),
    ])
    model.fit(train.loc[:, columns], train.result)
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise TeamDisciplineEvaluationError("Expected class order [0, 1, 2]")
    return _validate_probabilities(model.predict_proba(validation.loc[:, columns]))


def _align_predictions(probabilities, source_ids, target_ids) -> np.ndarray:
    source = pd.Index(pd.Series(source_ids, dtype="string"))
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    if not source.is_unique or not target.is_unique or set(source) != set(target):
        raise TeamDisciplineEvaluationError("Prediction alignment IDs differ")
    aligned = pd.DataFrame(probabilities, index=source).reindex(target)
    if aligned.isna().any().any() or len(aligned) != len(target):
        raise TeamDisciplineEvaluationError("Prediction alignment is incomplete")
    return _validate_probabilities(aligned.to_numpy())


def _assert_baseline_sanity(folds: list[FoldResult], pooled: dict) -> None:
    for fold in folds:
        if not np.isclose(fold.a_y["log_loss"], KNOWN_A_Y_LL[fold.season], rtol=0, atol=1e-12):
            raise TeamDisciplineEvaluationError(
                f"BLOCKED_REFERENCE_MISMATCH: A_Y {fold.season} Log Loss"
            )
    for baseline, expected in (("a_y", KNOWN_A_Y_POOLED), ("d0", KNOWN_D0_POOLED)):
        for key, value in expected.items():
            if not np.isclose(pooled[baseline][key], value, rtol=0, atol=1e-12):
                raise TeamDisciplineEvaluationError(
                    f"BLOCKED_REFERENCE_MISMATCH: pooled {baseline} {key}"
                )


def frozen_decision(folds: list[FoldResult], pooled: dict) -> str:
    improved = sum(fold.d1["log_loss"] < fold.d0["log_loss"] for fold in folds)
    non_improved = len(folds) - improved
    if (pooled["d1"]["log_loss"] < pooled["d0"]["log_loss"]
            and pooled["d1"]["brier"] < pooled["d0"]["brier"] and improved >= 3):
        return "CONTINUE_DISCIPLINE_LANE"
    if (pooled["d1"]["log_loss"] >= pooled["d0"]["log_loss"]
            and pooled["d1"]["brier"] >= pooled["d0"]["brier"] and non_improved >= 3):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "INCONCLUSIVE_NO_TUNING"


def evaluate_team_discipline(*, match_dir: str | Path = MATCH_DIR,
                             feature_path: str | Path = FEATURE_PATH) -> dict:
    data = _add_elo(_load_inputs(match_dir, feature_path))
    data["primary_eligible"] = _eligible(data)
    folds: list[FoldResult] = []
    pooled = {key: [] for key in ("d0_y", "d0_p", "d1_p", "op_y", "a_y_p", "op_p")}
    for season in VALIDATION_SEASONS:
        train_all = data.loc[data.season.between(2015, season - 1)].copy()
        valid_all = data.loc[data.season.eq(season)].copy()
        train = train_all.loc[train_all.primary_eligible].copy()
        valid = valid_all.loc[valid_all.primary_eligible].copy()
        observed = (len(train_all), len(train), len(valid_all), len(valid))
        if observed != EXPECTED_COUNTS[season]:
            raise TeamDisciplineEvaluationError(
                f"Fold-count mismatch for {season}: {observed} != {EXPECTED_COUNTS[season]}"
            )
        d0_p = _fit(train, valid, D0_FEATURES)
        d1_p = _fit(train, valid, D1_FEATURES)
        target = valid.result.to_numpy(dtype=int)
        a_y_p = _fit(train_all, valid_all, D0_FEATURES)
        a_y_aligned = _align_predictions(a_y_p, valid_all.match_id, valid_all.match_id)
        operational = a_y_aligned.copy()
        mask = valid_all.primary_eligible.to_numpy()
        operational[mask] = _align_predictions(
            d1_p, valid.match_id, valid_all.loc[mask, "match_id"]
        )
        op_target = valid_all.result.to_numpy(dtype=int)
        fold = FoldResult(
            season, len(train_all), len(train), len(valid_all), len(valid),
            _metrics(target, d0_p), _metrics(target, d1_p),
            _metrics(op_target, a_y_aligned), _metrics(op_target, operational),
        )
        folds.append(fold)
        for key, value in (
            ("d0_y", target), ("d0_p", d0_p), ("d1_p", d1_p),
            ("op_y", op_target), ("a_y_p", a_y_aligned), ("op_p", operational),
        ):
            pooled[key].append(value)
    pooled_metrics = {
        "d0": _metrics(np.concatenate(pooled["d0_y"]), np.concatenate(pooled["d0_p"])),
        "d1": _metrics(np.concatenate(pooled["d0_y"]), np.concatenate(pooled["d1_p"])),
        "a_y": _metrics(np.concatenate(pooled["op_y"]), np.concatenate(pooled["a_y_p"])),
        "operational_d1": _metrics(np.concatenate(pooled["op_y"]), np.concatenate(pooled["op_p"])),
    }
    _assert_baseline_sanity(folds, pooled_metrics)
    return {
        "folds": folds, "pooled": pooled_metrics,
        "matched_pooled_n": pooled_metrics["d0"]["count"],
        "operational_pooled_n": pooled_metrics["a_y"]["count"],
        "log_loss_improved_folds": sum(f.d1["log_loss"] < f.d0["log_loss"] for f in folds),
        "baseline_sanity": "PASS",
        "decision": frozen_decision(folds, pooled_metrics),
    }


if __name__ == "__main__":
    import json
    result = evaluate_team_discipline()
    print(json.dumps({
        "pooled": result["pooled"],
        "log_loss_improved_folds": result["log_loss_improved_folds"],
        "baseline_sanity": result["baseline_sanity"],
        "decision": result["decision"],
    }, indent=2))
