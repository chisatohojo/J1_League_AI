"""Pre-match team/stadium form over a caller-selected number of prior games."""

from collections import defaultdict, deque
from numbers import Integral

import pandas as pd


STADIUM_WINDOW_COLUMNS = (
    "home_stadium_window_matches", "home_stadium_window_points", "home_stadium_window_goal_diff",
    "away_stadium_window_matches", "away_stadium_window_points", "away_stadium_window_goal_diff",
)


def add_stadium_window_features(matches: pd.DataFrame, window: int) -> pd.DataFrame:
    """Return a copy with six integer features from prior team/stadium matches.

    Supply completed matches in chronological order with stable team IDs and
    90-minute scores/result (0=away win, 1=draw, 2=home win). A positive integer
    window limits each history, combining home/away appearances at the exact
    stadium string. Record both teams' features before adding the current
    match. A team cannot appear twice on the same calendar date. Every call
    starts with empty histories; existing columns, dtypes, index and order are
    preserved. No sorting, normalization, persistent state or I/O occurs.
    """
    if isinstance(window, bool) or not isinstance(window, Integral) or window < 1:
        raise ValueError("window must be a positive integer, excluding bool.")
    required = (
        "match_date", "home_team_id", "away_team_id", "stadium",
        "home_score", "away_score", "result",
    )
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates or set(required) - set(matches.columns):
        raise ValueError(f"Expected unique columns including {required}.")
    if set(STADIUM_WINDOW_COLUMNS) & set(matches.columns):
        raise ValueError("Stadium window output columns already exist.")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Matches must be in chronological order with nonmissing dates.")

    capacity = min(int(window), len(matches))
    histories = defaultdict(lambda: deque(maxlen=capacity))
    last_dates = {}
    features = {column: [] for column in STADIUM_WINDOW_COLUMNS}
    for timestamp, row in zip(dates, matches.loc[:, list(required)].itertuples(index=False)):
        ids = (row.home_team_id, row.away_team_id)
        if any(not isinstance(team_id, str) or not team_id.strip() for team_id in ids) or ids[0] == ids[1]:
            raise ValueError("Each match needs two distinct, nonempty team IDs.")
        day = timestamp.date()
        if any(last_dates.get(team_id) == day for team_id in ids):
            raise ValueError("A club cannot appear twice on the same calendar match_date.")
        if not isinstance(row.stadium, str) or not row.stadium.strip():
            raise ValueError("stadium must be a nonempty string.")
        scores = (row.home_score, row.away_score)
        if any(isinstance(score, bool) or not isinstance(score, Integral) or score < 0 for score in scores):
            raise ValueError("Scores must be nonnegative integers.")
        scores = tuple(int(score) for score in scores)
        expected_result = 2 if scores[0] > scores[1] else 0 if scores[0] < scores[1] else 1
        if isinstance(row.result, bool) or not isinstance(row.result, Integral) or row.result != expected_result:
            raise ValueError("result must be 0/1/2 and agree with the 90-minute scores.")

        for side, team_id in zip(("home", "away"), ids):
            history = histories[team_id, row.stadium]
            features[f"{side}_stadium_window_matches"].append(len(history))
            features[f"{side}_stadium_window_points"].append(sum(game[0] for game in history))
            features[f"{side}_stadium_window_goal_diff"].append(sum(game[1] for game in history))

        # Append only after recording both teams' pre-match features.
        home_points = 3 if row.result == 2 else 1 if row.result == 1 else 0
        away_points = 3 if row.result == 0 else 1 if row.result == 1 else 0
        goal_diff = scores[0] - scores[1]
        histories[ids[0], row.stadium].append((home_points, goal_diff))
        histories[ids[1], row.stadium].append((away_points, -goal_diff))
        for team_id in ids:
            last_dates[team_id] = day

    output = matches.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output
