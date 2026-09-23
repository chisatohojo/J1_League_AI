"""Frozen retrospective evaluation for the previous-season J Stats challenger."""

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
from src.modeling.logistic_elo_home_advantage_tuning import _replay

ROOT = Path(__file__).resolve().parents[2]
MATCH_DIR = ROOT / "data/processed/jleague"
FEATURE_PATH = ROOT / "data/processed/features/previous_season_jstats_features.csv"
FOLDS = (2021, 2022, 2023, 2024)
EXPECTED_MATCHED = {2021: 306, 2022: 240, 2023: 240, 2024: 272}
CLASS_ORDER = (0, 1, 2)
MODEL_PARAMS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
J1_FEATURES = (
    "elo_diff", "home_previous_expected_goals_per_match", "away_previous_expected_goals_per_match",
    "home_previous_shoot_on_target_per_match", "away_previous_shoot_on_target_per_match",
    "home_previous_expected_goals_against_per_match", "away_previous_expected_goals_against_per_match",
    "home_previous_suffer_shoot_on_target_per_match", "away_previous_suffer_shoot_on_target_per_match",
    "home_previous_ball_rate", "away_previous_ball_rate",
    "home_previous_pass_rate", "away_previous_pass_rate",
)


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    log_loss: float
    brier: float
    count: int


def _metrics(y, probabilities) -> Metrics:
    y = np.asarray(y, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    one_hot = (y[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return Metrics(
        accuracy=float(accuracy_score(y, np.asarray(CLASS_ORDER)[p.argmax(axis=1)])),
        log_loss=float(log_loss(y, p, labels=list(CLASS_ORDER))),
        brier=float(np.mean(np.sum((p - one_hot) ** 2, axis=1))),
        count=len(y),
    )


def _fit(train, valid, columns):
    model = Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(
        **MODEL_PARAMS))])
    model.fit(train.loc[:, columns], train["result"])
    if not np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER):
        raise ValueError("Expected class order [0, 1, 2].")
    probabilities = model.predict_proba(valid.loc[:, columns])
    _validate_probabilities(probabilities)
    return probabilities


def _validate_probabilities(probabilities) -> None:
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 3:
        raise ValueError("Expected three-class probabilities.")
    if not np.isfinite(probabilities).all() or (probabilities < 0).any() or (probabilities > 1).any():
        raise ValueError("Probabilities must be finite and within [0, 1].")
    if not np.allclose(probabilities.sum(axis=1), 1.0):
        raise ValueError("Probability rows must sum to one.")


def _align_predictions(predictions, prediction_ids, target_ids):
    """Reindex probability rows by match_id; never rely on source row order."""
    source_ids = pd.Index(prediction_ids.astype(str))
    target_ids = pd.Index(target_ids.astype(str))
    if not source_ids.is_unique or not target_ids.is_unique:
        raise ValueError("Prediction and target match IDs must be unique.")
    if set(source_ids) != set(target_ids):
        raise ValueError("Prediction and target match ID sets differ.")
    aligned = pd.DataFrame(np.asarray(predictions), index=source_ids).reindex(target_ids)
    if aligned.isna().any().any() or len(aligned) != len(target_ids):
        raise ValueError("Prediction alignment has missing rows.")
    result = aligned.to_numpy()
    _validate_probabilities(result)
    return result


def frozen_decision(fold_results: dict, pooled: dict) -> str:
    """Apply the frozen primary decision rule without tuning or reinterpretation."""
    j0 = [fold_results[year]["j0"]["log_loss"] for year in FOLDS]
    j1 = [fold_results[year]["j1"]["log_loss"] for year in FOLDS]
    improved = sum(b < a for a, b in zip(j0, j1))
    non_improved = sum(b >= a for a, b in zip(j0, j1))
    if (pooled["j1"]["log_loss"] < pooled["j0"]["log_loss"]
            and pooled["j1"]["brier"] < pooled["j0"]["brier"]
            and improved >= 3):
        return "CONTINUE_TO_PROSPECTIVE_FREEZE"
    if (pooled["j1"]["log_loss"] >= pooled["j0"]["log_loss"]
            and pooled["j1"]["brier"] >= pooled["j0"]["brier"]
            and non_improved >= 3):
        return "CLOSE_RETROSPECTIVE_LANE"
    return "MIXED"


def _load_matches(match_dir: Path = MATCH_DIR) -> pd.DataFrame:
    master = load_team_master()
    frames = [master.add_team_ids(load_matches(Path(match_dir) / f"{season}_matches_probe.csv"))
              for season in range(2015, 2025)]
    return pd.concat(frames, ignore_index=True)


def _with_elo(matches: pd.DataFrame) -> pd.DataFrame:
    ordered = matches.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    frames = tuple(ordered.loc[ordered.season.eq(season),
                               ["match_id", "home_team_id", "away_team_id", "result"]].copy()
                   for season in range(2015, 2025))
    replay = _replay(frames, 175.0)
    return ordered.merge(replay, on="match_id", how="left", validate="one_to_one")


def evaluate(*, match_dir: Path = MATCH_DIR, feature_path: Path = FEATURE_PATH) -> dict:
    matches = _with_elo(_load_matches(Path(match_dir)))
    profiles = pd.read_csv(feature_path, dtype={"match_id": "string"})
    profiles = profiles.loc[profiles.season.astype(str).isin([str(y) for y in range(2020, 2025)])].copy()
    profiles = profiles.drop(columns=["season"])
    data = matches.merge(profiles, on="match_id", how="inner", validate="one_to_one")
    data["profile_pair"] = data.home_has_previous_j1_profile & data.away_has_previous_j1_profile
    data["j0_elo_diff"] = data.elo_diff
    for col in J1_FEATURES[1:]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    fold_results = {}
    operational_results = {}
    pooled = {"j0_y": [], "j0_p": [], "j1_y": [], "j1_p": [], "op_y": [], "op_p": [], "a_y_p": []}
    for year in FOLDS:
        train_all = data.loc[data.season.between(2020, year - 1)].copy()
        valid_all = data.loc[data.season.eq(year)].copy()
        train_pair = train_all.loc[train_all.profile_pair].copy()
        valid_pair = valid_all.loc[valid_all.profile_pair].copy()
        if len(valid_pair) != EXPECTED_MATCHED[year]:
            raise ValueError(f"Matched validation count mismatch for {year}: {len(valid_pair)}")
        j0_train = train_pair[["elo_diff", "result"]]
        j0_valid = valid_pair[["elo_diff", "result"]]
        j1_train = train_pair[list(J1_FEATURES[1:]) + ["elo_diff", "result"]]
        j1_valid = valid_pair[list(J1_FEATURES[1:]) + ["elo_diff", "result"]]
        j0_p = _fit(j0_train, j0_valid, ["elo_diff"])
        j1_p = _fit(j1_train, j1_valid, list(J1_FEATURES))
        y = valid_pair.result.to_numpy()
        fold_results[year] = {"j0": asdict(_metrics(y, j0_p)), "j1": asdict(_metrics(y, j1_p)),
                              "train_matched_rows": len(train_pair), "matched_rows": len(valid_pair)}
        for key, value in (("j0_y", y), ("j1_y", y), ("j0_p", j0_p), ("j1_p", j1_p)):
            pooled[key].append(value)

        a_train = matches.loc[matches.season.between(2015, year - 1)].copy()
        a_valid = matches.loc[matches.season.eq(year)].copy()
        if not a_valid.match_id.is_unique or not valid_all.match_id.is_unique:
            raise ValueError(f"Validation match IDs must be unique for {year}.")
        if set(a_valid.match_id) != set(valid_all.match_id):
            raise ValueError(f"Operational validation IDs are not aligned for {year}.")
        a_p = _fit(a_train[["elo_diff", "result"]], a_valid[["elo_diff", "result"]], ["elo_diff"])
        a_p_aligned = _align_predictions(a_p, a_valid.match_id, valid_all.match_id)
        op_p = np.empty((len(valid_all), 3))
        pair_p = _fit(j1_train, valid_all.loc[valid_all.profile_pair, list(J1_FEATURES[1:]) + ["elo_diff", "result"]], list(J1_FEATURES))
        op_p[valid_all.profile_pair.to_numpy()] = pair_p
        a_by_id = pd.DataFrame(a_p_aligned, index=valid_all.match_id.astype(str))
        fallback_ids = valid_all.loc[~valid_all.profile_pair, "match_id"].astype(str)
        op_p[~valid_all.profile_pair.to_numpy()] = a_by_id.loc[fallback_ids].to_numpy()
        op_y = valid_all.result.to_numpy()
        operational_results[year] = {"a_y": asdict(_metrics(op_y, a_p_aligned)), "operational_j1": asdict(_metrics(op_y, op_p)), "rows": len(valid_all)}
        pooled["op_y"].append(op_y); pooled["op_p"].append(op_p); pooled["a_y_p"].append(a_p_aligned)
    return {"folds": fold_results, "operational": operational_results,
            "pooled": {"j0": asdict(_metrics(np.concatenate(pooled["j0_y"]), np.concatenate(pooled["j0_p"]))),
                        "j1": asdict(_metrics(np.concatenate(pooled["j1_y"]), np.concatenate(pooled["j1_p"]))),
                        "operational_j1": asdict(_metrics(np.concatenate(pooled["op_y"]), np.concatenate(pooled["op_p"]))),
                        "a_y": asdict(_metrics(np.concatenate(pooled["op_y"]), np.concatenate(pooled["a_y_p"])))}}
