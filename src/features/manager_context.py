"""Leakage-safe pre-match manager context features.

SFMS02 is a post-match official record. These historical features are suitable
for reconstruction only; production prediction needs a pre-kickoff manager source.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLUMNS = (
    "home_manager_known", "away_manager_known",
    "home_manager_change_known", "away_manager_change_known",
    "home_manager_changed", "away_manager_changed",
    "home_manager_prior_matches_in_charge", "away_manager_prior_matches_in_charge",
)


def add_manager_context_features(matches: pd.DataFrame, manager_history: pd.DataFrame) -> pd.DataFrame:
    required = {"match_id", "match_date", "home_team_id", "away_team_id"}
    if not isinstance(matches, pd.DataFrame) or not isinstance(manager_history, pd.DataFrame):
        raise TypeError("matches and manager_history must be DataFrames")
    if not required.issubset(matches.columns) or not required.issubset(manager_history.columns):
        raise ValueError("match/team/date columns are required")
    manager_cols = {"home_manager_staff_id", "away_manager_staff_id"}
    if not manager_cols.issubset(manager_history.columns):
        raise ValueError("resolved manager columns are required")
    if matches.columns.duplicated().any() or manager_history.columns.duplicated().any():
        raise ValueError("duplicate columns are not allowed")
    if set(FEATURE_COLUMNS) & set(matches.columns):
        raise ValueError("manager feature columns already exist")
    left = matches.copy(deep=True)
    history = manager_history.loc[:, ["match_id", "match_date", "home_team_id", "away_team_id", *manager_cols]].copy(deep=True)
    if left["match_id"].isna().any() or not left["match_id"].is_unique:
        raise ValueError("matches match_id must be unique and nonmissing")
    if history["match_id"].isna().any() or not history["match_id"].is_unique:
        raise ValueError("manager history match_id must be unique and nonmissing")
    left["match_date"] = pd.to_datetime(left["match_date"], errors="raise")
    history["match_date"] = pd.to_datetime(history["match_date"], errors="raise")
    if set(left.match_id) != set(history.match_id):
        raise ValueError("manager history match_id set mismatch")
    aligned = history.set_index("match_id").loc[left.match_id].reset_index()
    if not (left.home_team_id.to_numpy() == aligned.home_team_id.to_numpy()).all() or not (left.away_team_id.to_numpy() == aligned.away_team_id.to_numpy()).all():
        raise ValueError("manager history team IDs do not match")
    if not (left.match_date.to_numpy() == aligned.match_date.to_numpy()).all():
        raise ValueError("manager history dates do not match")

    values = {c: np.zeros(len(left), dtype=np.int64) for c in FEATURE_COLUMNS}
    events = {}
    for i, row in aligned.iterrows():
        events.setdefault(row.home_team_id, []).append((row.match_date, str(row.match_id), i, "home", row.home_manager_staff_id))
        events.setdefault(row.away_team_id, []).append((row.match_date, str(row.match_id), i, "away", row.away_manager_staff_id))
    for team, team_events in events.items():
        previous_id = None
        previous_known = False
        previous_count = 0
        seen = set()
        for date, match_id, i, side, current_id in sorted(team_events, key=lambda x: (x[0], x[1])):
            if (date, match_id) in seen:
                raise ValueError("team appears twice on the same match/date")
            seen.add((date, match_id))
            prefix = side + "_manager_"
            known = pd.notna(current_id)
            values[prefix + "known"][i] = int(known)
            change_known = int(known and previous_known)
            values[prefix + "change_known"][i] = change_known
            changed = int(change_known and current_id != previous_id)
            values[prefix + "changed"][i] = changed
            values[prefix + "prior_matches_in_charge"][i] = int(previous_count + 1 if known and previous_known and current_id == previous_id else 0)
            previous_count = values[prefix + "prior_matches_in_charge"][i]
            previous_id, previous_known = (current_id, known)
    output = left.copy(deep=True)
    for column in FEATURE_COLUMNS:
        output[column] = values[column]
    return output
