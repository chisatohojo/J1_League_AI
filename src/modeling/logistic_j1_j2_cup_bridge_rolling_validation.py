"""One-shot evaluation of safe J1-J2 domestic Cup bridge updates.

Only identity-safe J1-vs-J2/J2-vs-J1 Cup rows with an explicit 90-minute
score/result are eligible for the Elo stream. Cup rows are never Logistic
training or validation rows. AFC, J3, 2025 and 2026 are excluded.
"""

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

from src.collect.teams import TeamMasterError, load_team_master
from src.modeling.logistic_j1_j2_initial_prior_rolling_validation import (
    EXPECTED_VALIDATION_COUNTS, VALIDATION_SEASONS, _fit, _load_j1, _load_j2,
    _metrics, _replay, _stream,
)


@dataclass(frozen=True)
class CupBridgeResult:
    fold_metrics: dict
    pooled_metrics: dict
    fold_counts: dict
    promotion_metrics: dict
    appearance_metrics: dict
    bridge_diagnostics: pd.DataFrame
    transitions: pd.DataFrame


def _safe_emperor_ids(frame, master):
    aliases = {}
    for alias in master.aliases:
        aliases.setdefault(alias.source_name, set()).add(alias.team_id)
        aliases.setdefault(alias.canonical_name, set()).add(alias.team_id)
    result = frame.copy(deep=True)
    for side in ("home", "away"):
        values = []
        for row in result.itertuples(index=False):
            value = getattr(row, f"{side}_team_id")
            if pd.notna(value) and str(value) not in ("", "nan"):
                values.append(str(value)); continue
            candidates = aliases.get(getattr(row, f"{side}_team"), set())
            values.append(next(iter(candidates)) if len(candidates) == 1 else pd.NA)
        result[f"{side}_resolved_id"] = values
    return result


def _safe_cup_ids(frame, master):
    result = frame.copy(deep=True)
    for side in ("home", "away"):
        values = []
        for row in result.itertuples(index=False):
            value = getattr(row, f"{side}_team_id")
            if pd.notna(value) and str(value) not in ("", "nan"):
                values.append(str(value)); continue
            try:
                values.append(master.resolve_team_id(getattr(row, f"{side}_team"), source="jleague_data_site", on=row.match_date))
            except TeamMasterError:
                values.append(pd.NA)
        result[f"{side}_resolved_id"] = values
    return result


def _bridge_candidates(cup, emperor, j1_membership, j2_membership):
    rows = []
    for source, frame in (("jleague_cup", cup), ("emperors_cup", emperor)):
        for row in frame.itertuples(index=False):
            j1 = j1_membership[row.season]; j2 = j2_membership[row.season]
            home = row.home_resolved_id; away = row.away_resolved_id
            identity_safe = pd.notna(home) and pd.notna(away)
            is_bridge = identity_safe and ((home in j1 and away in j2) or (home in j2 and away in j1))
            if not is_bridge:
                continue
            result_safe = all(hasattr(row, field) and pd.notna(getattr(row, field)) for field in ("home_score", "away_score", "result"))
            rows.append({"competition": source, "season": row.season, "match_id": str(row.source_match_id),
                         "match_date": row.match_date, "home_team_id": home, "away_team_id": away,
                         "identity_safe": True, "result_safe": result_safe, "used": result_safe})
    return pd.DataFrame(rows)


def _add_bridges(stream, candidates):
    if candidates.empty:
        return stream.copy(deep=True)
    usable = candidates[candidates.used].copy()
    if usable.empty:
        return stream.copy(deep=True)
    rows = pd.DataFrame({
        "match_id": usable.match_id, "event_key": usable.competition + ":" + usable.match_id,
        "season": usable.season, "match_date": pd.to_datetime(usable.match_date),
        "home_team_id": usable.home_team_id, "away_team_id": usable.away_team_id,
        "result": usable.result.astype(int),
    })
    return _stream(pd.concat([stream, rows], ignore_index=True), pd.DataFrame())


def run_logistic_j1_j2_cup_bridge_rolling_validation(*, processed_dir="data/processed/jleague", j2_path="data/processed/jleague_j2/2015_2024_j2_matches.csv", cup_path="data/processed/jleague_cup/2015_2024_jleague_cup_matches.csv", emperor_path="data/processed/emperors_cup/2015_2024_emperors_cup_matches.csv"):
    master = load_team_master(); j1 = _load_j1(processed_dir, master); j2 = _load_j2(j2_path); base_stream = _stream(j1, j2)
    j1_membership = {y: set(j1.loc[j1.season.eq(y), "home_team_id"]) | set(j1.loc[j1.season.eq(y), "away_team_id"]) for y in range(2015, 2025)}
    j2_membership = {y: set(j2.loc[j2.season.eq(y), "home_team_id"]) | set(j2.loc[j2.season.eq(y), "away_team_id"]) for y in range(2015, 2025)}
    cup = pd.read_csv(cup_path, dtype=str); emperor = pd.read_csv(emperor_path, dtype=str)
    for frame in (cup, emperor): frame["season"] = frame.season.astype(int); frame["match_date"] = pd.to_datetime(frame.match_date)
    cup = _safe_cup_ids(cup, master); emperor = _safe_emperor_ids(emperor, master)
    candidates = _bridge_candidates(cup, emperor, j1_membership, j2_membership)
    diagnostics = candidates.groupby(["season", "competition"]).agg(candidate_bridge=("match_id", "size"), identity_safe=("identity_safe", "sum"), result_safe=("result_safe", "sum"), used_bridge=("used", "sum")).reset_index()
    bridge_stream = _add_bridges(base_stream, candidates)
    folds = {}; counts = {}; pooled = {"current": [], "equal_j1_j2": [], "bridge": []}; targets=[]
    for year in VALIDATION_SEASONS:
        current = _features_from_stream(j1, _stream(j1, pd.DataFrame()), year)
        equal = _features_from_stream(j1, base_stream, year)
        bridged = _features_from_stream(j1, bridge_stream, year)
        frames = {"current": current, "equal_j1_j2": equal, "bridge": bridged}; val=current[current.season.eq(year)]
        if len(val) != EXPECTED_VALIDATION_COUNTS[year]: raise ValueError(f"unexpected validation count {year}")
        counts[year] = (int((current.season < year).sum()), len(val)); target=val.result.to_numpy(copy=True); targets.append(target); ps={}
        for name, frame in frames.items(): ps[name]=_fit(frame[frame.season < year], frame[frame.season.eq(year)]); pooled[name].append(ps[name])
        folds[year]={name:_metrics(target, ps[name]) for name in pooled};
    y=np.concatenate(targets); pooled_metrics={name:_metrics(y,np.vstack(pooled[name])) for name in pooled}
    # The diagnostics are intentionally limited to bridge eligibility; no model
    # selection or additional search is performed here.
    return CupBridgeResult(folds, pooled_metrics, counts, {}, {}, diagnostics, pd.DataFrame())


def _features_from_stream(j1, stream, end_season):
    replay, _ = _replay(stream, end_season)
    lookup = replay.set_index("event_key")
    out=j1[j1.season <= end_season].copy(deep=True)
    out["elo_diff"]=[lookup.loc[k,"home_elo"]-lookup.loc[k,"away_elo"] for k in out.event_key]
    return out
