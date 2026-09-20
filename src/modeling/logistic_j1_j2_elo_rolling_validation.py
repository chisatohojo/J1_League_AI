"""Compare J1-only Elo with a J1+J2 Elo state and J1-only Logistic targets.

J2 matches update the rating state but never become Logistic Regression training
rows or validation targets. AFC, J3, 2025, and 2026 data are intentionally not
read. The absence of J3 history remains a limitation for clubs entering J2 from
J3: their pre-J2 rating starts at the initial 1500 state.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.collect.teams import load_team_master
from src.features.elo import EloRatings
from src.modeling.logistic_form import CLASS_ORDER, FormLogisticMetrics


VALIDATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
EXPECTED_VALIDATION_COUNTS = {2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}
K_FACTOR = 30.0
HOME_ADVANTAGE = 175.0


@dataclass(frozen=True)
class J1J2EloResult:
    fold_metrics: dict
    pooled_metrics: dict
    fold_counts: dict
    promotion_metrics: dict
    appearance_metrics: dict
    transitions: pd.DataFrame


def _metrics(target, probabilities):
    target = np.asarray(target, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.ndim != 2 or probabilities.shape[1] != 3 or not np.allclose(probabilities.sum(axis=1), 1.0):
        raise ValueError("probabilities must be an Nx3 matrix summing to one")
    one_hot = (target[:, None] == np.asarray(CLASS_ORDER)).astype(float)
    return FormLogisticMetrics(
        float(accuracy_score(target, np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)])),
        float(log_loss(target, probabilities, labels=list(CLASS_ORDER))),
        float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1))),
    )


def _load_j1(processed_dir, master):
    frames = []
    for season in range(2015, 2025):
        frame = pd.read_csv(Path(processed_dir) / f"{season}_matches_probe.csv")
        frame["match_date"] = pd.to_datetime(frame["match_date"], errors="raise").dt.normalize()
        for side in ("home", "away"):
            frame[f"{side}_team_id"] = [
                master.resolve_team_id(name, source="jleague_data_site", on=day.date())
                for name, day in zip(frame[f"{side}_team"], frame["match_date"])
            ]
        frame["competition"] = "j1"
        frame["event_key"] = "j1:" + frame["match_id"].astype(str)
        frames.append(frame[["match_id", "event_key", "season", "match_date", "home_team_id", "away_team_id", "result"]])
    return pd.concat(frames, ignore_index=True)


def _load_j2(path):
    frame = pd.read_csv(path, dtype={"match_id": str, "home_team_id": str, "away_team_id": str})
    frame["match_date"] = pd.to_datetime(frame["match_date"], errors="raise").dt.normalize()
    if not frame["season"].isin(range(2015, 2025)).all():
        raise ValueError("J2 input contains a forbidden season")
    frame["competition"] = "j2"
    frame["event_key"] = "j2:" + frame["match_id"].astype(str)
    return frame[["match_id", "event_key", "season", "match_date", "home_team_id", "away_team_id", "result"]]


def _prepare_stream(j1, j2):
    stream = pd.concat([j1, j2], ignore_index=True)
    if stream["event_key"].duplicated().any():
        raise ValueError("duplicate competition-qualified match identity")
    appearances = pd.concat([
        stream[["match_date", "home_team_id"]].rename(columns={"home_team_id": "team_id"}),
        stream[["match_date", "away_team_id"]].rename(columns={"away_team_id": "team_id"}),
    ], ignore_index=True)
    repeated = appearances.duplicated(["match_date", "team_id"], keep=False)
    if repeated.any():
        raise ValueError(f"same team has multiple J1/J2 appearances on one date: {appearances.loc[repeated].head().to_dict('records')}")
    return stream.sort_values(["match_date", "event_key"], kind="stable").reset_index(drop=True)


def _replay_until(stream, end_season):
    selected = stream.loc[stream["season"].le(end_season)]
    teams = sorted(set(selected.home_team_id) | set(selected.away_team_id))
    elo = EloRatings(teams, k_factor=K_FACTOR, home_advantage=HOME_ADVANTAGE)
    rows = []
    for row in selected.itertuples(index=False):
        before = elo.pre_match(row.home_team_id, row.away_team_id)
        rows.append((row.event_key, before.home_rating, before.away_rating))
        elo.update(row.home_team_id, row.away_team_id, row.result)
    return pd.DataFrame(rows, columns=["event_key", "home_elo", "away_elo"])


def _fit(train, validation):
    model = Pipeline([
        ("scaler", StandardScaler()),
        ("logistic", LogisticRegression(C=1, solver="lbfgs", max_iter=1000, random_state=0)),
    ])
    model.fit(train[["elo_diff"]], train["result"])
    if not np.array_equal(model.classes_, CLASS_ORDER):
        raise ValueError("Expected class order [0, 1, 2]")
    return model.predict_proba(validation[["elo_diff"]])


def _with_features(j1, stream, end_season):
    replay = _replay_until(stream, end_season).set_index("event_key")
    out = j1.loc[j1["season"].le(end_season)].copy(deep=True)
    out["elo_diff"] = [replay.loc[key, "home_elo"] - replay.loc[key, "away_elo"] for key in out["event_key"]]
    return out


def _current_j1_reference(j1, end_season):
    stream = _prepare_stream(j1, j1.iloc[0:0].copy())
    return _with_features(j1, stream, end_season)


def run_logistic_j1_j2_elo_rolling_validation(
    *, processed_dir="data/processed/jleague",
    j2_path="data/processed/jleague_j2/2015_2024_j2_matches.csv",
):
    master = load_team_master()
    j1 = _load_j1(processed_dir, master)
    j2 = _load_j2(j2_path)
    stream = _prepare_stream(j1, j2)
    fold_metrics, fold_counts = {}, {}
    pooled = {"current": [], "j1_j2": []}
    pooled_targets = []
    rows = []
    for season in VALIDATION_SEASONS:
        current = _current_j1_reference(j1, season)
        combined = _with_features(j1, stream, season)
        train_current = current.loc[current.season < season]
        val_current = current.loc[current.season == season]
        train_combined = combined.loc[combined.season < season]
        val_combined = combined.loc[combined.season == season]
        if len(val_current) != EXPECTED_VALIDATION_COUNTS[season]:
            raise ValueError(f"Unexpected validation count for {season}")
        fold_counts[season] = (len(train_current), len(val_current))
        p_current = _fit(train_current, val_current)
        p_combined = _fit(train_combined, val_combined)
        target = val_current.result.to_numpy(copy=True)
        fold_metrics[season] = {"current": _metrics(target, p_current), "j1_j2": _metrics(target, p_combined)}
        pooled["current"].append(p_current)
        pooled["j1_j2"].append(p_combined)
        pooled_targets.append(target)
        for i, row in enumerate(val_current.itertuples(index=False)):
            rows.append((str(row.match_id), season, int(row.result), row.home_team_id, row.away_team_id, p_current[i], p_combined[i]))
    target = np.concatenate(pooled_targets)
    pooled_metrics = {name: _metrics(target, np.vstack(values)) for name, values in pooled.items()}
    prediction = pd.DataFrame(rows, columns=["match_id", "season", "result", "home_team_id", "away_team_id", "current_prob", "j1_j2_prob"])
    memberships = {year: set(j1.loc[j1.season.eq(year), "home_team_id"]) | set(j1.loc[j1.season.eq(year), "away_team_id"]) for year in range(2015, 2025)}
    promotion_metrics, appearance_metrics = _promotion_diagnostics(prediction, j1, memberships)
    transitions = _transition_sanity(stream, j1)
    return J1J2EloResult(fold_metrics, pooled_metrics, fold_counts, promotion_metrics, appearance_metrics, transitions)


def _promotion_diagnostics(prediction, j1, memberships):
    first_seen = {}
    for row in j1.sort_values(["match_date", "event_key"]).itertuples(index=False):
        first_seen.setdefault(row.home_team_id, row.season)
        first_seen.setdefault(row.away_team_id, row.season)
    prediction = prediction.copy()
    prediction["category"] = "none"
    prediction["appearance_no"] = 0
    for season in VALIDATION_SEASONS:
        promoted = memberships[season] - memberships[season - 1]
        counters = {team: 0 for team in promoted}
        for idx, row in prediction.loc[prediction.season.eq(season)].iterrows():
            involved = [team for team in (row.home_team_id, row.away_team_id) if team in promoted]
            if not involved:
                continue
            for team in involved:
                counters[team] += 1
            prediction.at[idx, "category"] = "first-time" if all(first_seen.get(team, season) == season for team in involved) else "returning"
            prediction.at[idx, "appearance_no"] = min(counters[team] for team in involved)
    result = {}
    for category in ("returning", "first-time", "none"):
        subset = prediction[prediction.category.eq(category)]
        result[category] = {name: _metrics(subset.result, np.vstack(subset[f"{name}_prob"])) for name in ("current", "j1_j2")} if not subset.empty else {}
    buckets = {}
    for label, mask in (
        ("1-3", prediction.appearance_no.between(1, 3)),
        ("4-10", prediction.appearance_no.between(4, 10)),
        ("11+", prediction.appearance_no.ge(11)),
    ):
        subset = prediction.loc[mask]
        buckets[label] = {name: _metrics(subset.result, np.vstack(subset[f"{name}_prob"])) for name in ("current", "j1_j2")} if not subset.empty else {}
    return result, buckets


def _transition_sanity(stream, j1):
    # Keep a compact audit of the J2-driven rating movement for returning clubs.
    memberships = {year: set(j1.loc[j1.season.eq(year), "home_team_id"]) | set(j1.loc[j1.season.eq(year), "away_team_id"]) for year in range(2015, 2025)}
    rows = []
    for season in range(2016, 2025):
        returning = (memberships[season] - memberships[season - 1]) & set().union(*[memberships[y] for y in range(2015, season)])
        before = _replay_until(stream, season - 1).set_index("event_key")
        current_before = _replay_until(j1, season).set_index("event_key")
        replay = _replay_until(stream, season).set_index("event_key")
        season_j1 = j1[j1.season.eq(season)]
        for team in sorted(returning):
            first = season_j1[(season_j1.home_team_id.eq(team)) | (season_j1.away_team_id.eq(team))].iloc[0]
            key = f"j1:{first.match_id}"
            rows.append({"season": season, "team_id": team, "first_match_id": first.match_id,
                         "j1_only_pre_match_elo_diff": current_before.loc[key, "home_elo"] - current_before.loc[key, "away_elo"],
                         "j1_j2_pre_match_elo_diff": replay.loc[key, "home_elo"] - replay.loc[key, "away_elo"],
                         "j2_state_changed": bool(key not in before.index or not np.isclose(replay.loc[key, "home_elo"], current_before.loc[key, "home_elo"])),
                         "first_match_date": first.match_date})
    return pd.DataFrame(rows)
