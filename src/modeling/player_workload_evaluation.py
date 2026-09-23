"""Frozen retrospective evaluation of local-J1 player workload features."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
WORKLOAD_PATH = ROOT / "data/processed/features/2015_2024_j1_player_workload_features.csv"
FOLDS = (2020, 2021, 2022, 2023, 2024)
CLASS_ORDER = (0, 1, 2)
MODEL_PARAMS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
EXPECTED_COUNTS = {
    2020: (1530, 1485, 306, 297),
    2021: (1836, 1782, 380, 370),
    2022: (2216, 2152, 306, 297),
    2023: (2522, 2449, 306, 297),
    2024: (2828, 2746, 380, 370),
}
WORKLOAD_FEATURES = tuple(
    f"{side}_prev_{population}_mean_minutes_{window}d"
    for side in ("home", "away")
    for population in ("starters", "squad")
    for window in (7, 14, 30)
)
W0_FEATURES = ("elo_diff",)
W1_FEATURES = ("elo_diff", *WORKLOAD_FEATURES)


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    log_loss: float
    brier: float
    count: int


def _validate_probabilities(probabilities) -> np.ndarray:
    values = np.asarray(probabilities, dtype=float)
    if values.ndim != 2 or values.shape[1] != 3:
        raise ValueError("Expected N x 3 probabilities.")
    if not np.isfinite(values).all() or (values < 0).any() or (values > 1).any():
        raise ValueError("Probabilities must be finite and within [0, 1].")
    if not np.allclose(values.sum(axis=1), 1.0):
        raise ValueError("Probability rows must sum to one.")
    return values


def _metrics(target, probabilities) -> Metrics:
    y = np.asarray(target, dtype=int)
    p = _validate_probabilities(probabilities)
    one_hot = (y[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return Metrics(
        accuracy=float(accuracy_score(y, np.asarray(CLASS_ORDER)[p.argmax(axis=1)])),
        log_loss=float(log_loss(y, p, labels=list(CLASS_ORDER))),
        brier=float(np.mean(np.sum((p - one_hot) ** 2, axis=1))),
        count=len(y),
    )


def _fit(train: pd.DataFrame, validation: pd.DataFrame, features) -> np.ndarray:
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(**MODEL_PARAMS)),
    ])
    model.fit(train.loc[:, features], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise ValueError("Expected class order [0, 1, 2].")
    return _validate_probabilities(model.predict_proba(validation.loc[:, features]))


def _align_predictions(probabilities, source_ids, target_ids) -> np.ndarray:
    source = pd.Index(pd.Series(source_ids, dtype="string"))
    target = pd.Index(pd.Series(target_ids, dtype="string"))
    if not source.is_unique or not target.is_unique:
        raise ValueError("Prediction alignment IDs must be unique.")
    if set(source) != set(target):
        raise ValueError("Prediction alignment ID sets differ.")
    aligned = pd.DataFrame(probabilities, index=source).reindex(target)
    if len(aligned) != len(target) or aligned.isna().any().any():
        raise ValueError("Prediction alignment is incomplete.")
    return _validate_probabilities(aligned.to_numpy())


def _load_inputs(match_dir: Path = MATCH_DIR, workload_path: Path = WORKLOAD_PATH) -> pd.DataFrame:
    master = load_team_master()
    matches = pd.concat([
        master.add_team_ids(load_matches(Path(match_dir) / f"{season}_matches_probe.csv"))
        for season in range(2015, 2025)
    ], ignore_index=True)
    workload = pd.read_csv(workload_path, dtype={"match_id": "string"})
    if len(matches) != 3208 or len(workload) != 3208:
        raise ValueError("Expected 3,208 ordinary-J1 and workload rows.")
    if not matches.match_id.is_unique or not workload.match_id.is_unique:
        raise ValueError("match_id must be unique in both inputs.")
    matches["match_id"] = matches.match_id.astype(str)
    workload["match_id"] = workload.match_id.astype(str)
    if set(matches.match_id) != set(workload.match_id):
        raise ValueError("Ordinary-J1 and workload match ID sets differ.")
    check = matches[["match_id", "season", "match_date"]].merge(
        workload[["match_id", "season", "match_date"]], on="match_id",
        suffixes=("_match", "_workload"), validate="one_to_one")
    if not check.season_match.eq(check.season_workload).all():
        raise ValueError("Season identity mismatch.")
    if not pd.to_datetime(check.match_date_match).eq(pd.to_datetime(check.match_date_workload)).all():
        raise ValueError("Match-date identity mismatch.")
    workload = workload.drop(columns=["season", "match_date"])
    return matches.merge(workload, on="match_id", validate="one_to_one")


def _add_elo(matches: pd.DataFrame) -> pd.DataFrame:
    ordered = matches.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    appearances = pd.concat([
        ordered[["match_date", f"{side}_team_id"]].rename(columns={f"{side}_team_id": "team_id"})
        for side in ("home", "away")
    ], ignore_index=True)
    if appearances.duplicated(["match_date", "team_id"]).any():
        raise ValueError("A team appears more than once on the same date.")
    ids = sorted(set(ordered.home_team_id) | set(ordered.away_team_id))
    elo = EloRatings(ids, k_factor=30.0, home_advantage=175.0)
    elo_diff = pd.Series(index=ordered.index, dtype=float)
    for _, day_rows in ordered.groupby("match_date", sort=True):
        for row in day_rows.itertuples():
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            elo_diff.loc[row.Index] = before.home_rating - before.away_rating
        for row in day_rows.itertuples():
            elo.update(row.home_team_id, row.away_team_id, row.result)
    ordered["elo_diff"] = elo_diff
    return ordered


def _add_eligibility(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy(deep=True)
    for column in WORKLOAD_FEATURES:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    previous_pair = result[[f"{side}_has_previous_j1_match" for side in ("home", "away")]].eq(1).all(axis=1)
    prior_reference = result[[f"{side}_prev_reference_from_prior_season" for side in ("home", "away")]].eq(1).any(axis=1)
    values = result.loc[:, WORKLOAD_FEATURES]
    valid_values = values.notna().all(axis=1) & np.isfinite(values.to_numpy()).all(axis=1) & values.ge(0).all(axis=1)
    if ((previous_pair) & (~valid_values)).any():
        raise ValueError("True partial/invalid workload anomaly.")
    result["primary_eligible"] = previous_pair & ~prior_reference & valid_values
    return result


def frozen_decision(folds: dict, pooled: dict) -> str:
    improved = sum(folds[year]["w1"]["log_loss"] < folds[year]["w0"]["log_loss"] for year in FOLDS)
    non_improved = sum(folds[year]["w1"]["log_loss"] >= folds[year]["w0"]["log_loss"] for year in FOLDS)
    if (pooled["w1"]["log_loss"] < pooled["w0"]["log_loss"]
            and pooled["w1"]["brier"] < pooled["w0"]["brier"] and improved >= 3):
        return "CONTINUE_TO_PROSPECTIVE_FREEZE"
    if (pooled["w1"]["log_loss"] >= pooled["w0"]["log_loss"]
            and pooled["w1"]["brier"] >= pooled["w0"]["brier"] and non_improved >= 3):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "MIXED"


def evaluate(*, match_dir: Path = MATCH_DIR, workload_path: Path = WORKLOAD_PATH) -> dict:
    data = _add_eligibility(_add_elo(_load_inputs(match_dir, workload_path)))
    folds, operational = {}, {}
    pooled = {key: [] for key in ("w0_y", "w0_p", "w1_y", "w1_p", "op_y", "op_p", "a_y_p")}
    for year in FOLDS:
        train_all = data.loc[data.season.between(2015, year - 1)].copy()
        valid_all = data.loc[data.season.eq(year)].copy()
        train = train_all.loc[train_all.primary_eligible].copy()
        valid = valid_all.loc[valid_all.primary_eligible].copy()
        expected = EXPECTED_COUNTS[year]
        observed = (len(train_all), len(train), len(valid_all), len(valid))
        if observed != expected:
            raise ValueError(f"Fold-count mismatch for {year}: {observed} != {expected}")
        w0_p = _fit(train, valid, W0_FEATURES)
        w1_p = _fit(train, valid, W1_FEATURES)
        y = valid.result.to_numpy()
        folds[year] = {"training_rows": len(train_all), "training_eligible": len(train),
                       "validation_rows": len(valid_all), "validation_eligible": len(valid),
                       "w0": asdict(_metrics(y, w0_p)), "w1": asdict(_metrics(y, w1_p))}
        for key, value in (("w0_y", y), ("w1_y", y), ("w0_p", w0_p), ("w1_p", w1_p)):
            pooled[key].append(value)

        a_y_p = _fit(train_all, valid_all, W0_FEATURES)
        a_y_aligned = _align_predictions(a_y_p, valid_all.match_id, valid_all.match_id)
        op_p = a_y_aligned.copy()
        op_p[valid_all.primary_eligible.to_numpy()] = _align_predictions(
            w1_p, valid.match_id, valid_all.loc[valid_all.primary_eligible, "match_id"])
        op_y = valid_all.result.to_numpy()
        operational[year] = {"rows": len(valid_all), "a_y": asdict(_metrics(op_y, a_y_aligned)),
                             "operational_w1": asdict(_metrics(op_y, op_p))}
        pooled["op_y"].append(op_y); pooled["op_p"].append(op_p); pooled["a_y_p"].append(a_y_aligned)

    if sum(len(values) for values in pooled["w0_y"]) != 1631 or sum(len(values) for values in pooled["op_y"]) != 1678:
        raise ValueError("Pooled validation counts differ from the frozen artifact audit.")
    pooled_metrics = {
        "w0": asdict(_metrics(np.concatenate(pooled["w0_y"]), np.concatenate(pooled["w0_p"]))),
        "w1": asdict(_metrics(np.concatenate(pooled["w1_y"]), np.concatenate(pooled["w1_p"]))),
        "a_y": asdict(_metrics(np.concatenate(pooled["op_y"]), np.concatenate(pooled["a_y_p"]))),
        "operational_w1": asdict(_metrics(np.concatenate(pooled["op_y"]), np.concatenate(pooled["op_p"]))),
    }
    return {"folds": folds, "operational": operational, "pooled": pooled_metrics,
            "decision": frozen_decision(folds, pooled_metrics)}
