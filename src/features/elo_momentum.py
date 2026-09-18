"""Pre-match Elo momentum from each team's previous five recorded appearances."""

from collections import defaultdict, deque
import math
from numbers import Real

import pandas as pd


ELO_MOMENTUM_COLUMNS = (
    "home_elo_change_last5", "away_elo_change_last5", "elo_change_last5_diff",
    "home_elo_change_last5_matches", "away_elo_change_last5_matches",
)


def add_elo_momentum_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with three floating-point changes and two integer counts.

    Supply completed matches chronologically with their existing pre-match
    Elo values. For each team, subtract the oldest of up to five prior
    pre-match ratings from its current rating; no prior appearance gives zero.
    Home/away roles and seasons share a history, empty at the start of each
    call. Current ratings are appended only after both teams' features are
    recorded. Results and scores are unused, and no Elo updates, sorting,
    scaling or I/O occur. Original columns, dtypes, index and order remain.
    """
    required = ("match_date", "home_team_id", "away_team_id", "home_elo", "away_elo")
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates or set(required) - set(matches.columns):
        raise ValueError(f"Expected unique columns including {required}.")
    if set(ELO_MOMENTUM_COLUMNS) & set(matches.columns):
        raise ValueError("Elo momentum output columns already exist.")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Matches must be in chronological order with nonmissing dates.")

    histories = defaultdict(lambda: deque(maxlen=5))
    last_dates = {}
    features = {column: [] for column in ELO_MOMENTUM_COLUMNS}
    for timestamp, row in zip(dates, matches.loc[:, list(required)].itertuples(index=False)):
        ids = (row.home_team_id, row.away_team_id)
        if any(not isinstance(team_id, str) or not team_id.strip() for team_id in ids) or ids[0] == ids[1]:
            raise ValueError("Each match needs two distinct, nonempty team IDs.")
        day = timestamp.date()
        if any(last_dates.get(team_id) == day for team_id in ids):
            raise ValueError("A club cannot appear twice on the same calendar match_date.")
        ratings = (row.home_elo, row.away_elo)
        if any(isinstance(rating, bool) or not isinstance(rating, Real)
               or not math.isfinite(rating) for rating in ratings):
            raise ValueError("Pre-match Elo ratings must be finite real numbers.")
        ratings = tuple(float(rating) for rating in ratings)

        changes = []
        for side, team_id, rating in zip(("home", "away"), ids, ratings):
            history = histories[team_id]
            change = rating - history[0] if history else 0.0
            changes.append(change)
            features[f"{side}_elo_change_last5"].append(change)
            features[f"{side}_elo_change_last5_matches"].append(len(history))
        features["elo_change_last5_diff"].append(changes[0] - changes[1])

        # Retain supplied pre-match values without applying the current result.
        for team_id, rating in zip(ids, ratings):
            histories[team_id].append(rating)
            last_dates[team_id] = day

    output = matches.copy(deep=True)
    for column, values in features.items():
        dtype = "int64" if column.endswith("_matches") else "float64"
        output[column] = pd.array(values, dtype=dtype)
    return output
