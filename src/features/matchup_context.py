"""Pre-match head-to-head and team/stadium form from up to five prior games."""

from collections import defaultdict, deque
from numbers import Integral

import pandas as pd


MATCHUP_CONTEXT_COLUMNS = (
    "h2h_last5_matches", "h2h_last5_points_diff", "h2h_last5_goal_diff",
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
)


def add_matchup_context_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with nine integer features, preserving columns and row order.

    Supply completed matches in chronological order with stable team IDs and
    90-minute scores/result (0=away win, 1=draw, 2=home win). H2H differences
    use the current home team's perspective, including reversed past fixtures.
    Stadium histories combine both roles, keyed by the exact stadium string.
    Each call starts empty. No sorting, normalization, file/network access or
    persistent state is performed; completion checks belong to the caller.
    """
    required = (
        "match_date", "home_team_id", "away_team_id", "stadium",
        "home_score", "away_score", "result",
    )
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates or set(required) - set(matches.columns):
        raise ValueError(f"Expected unique columns including {required}.")
    if set(MATCHUP_CONTEXT_COLUMNS) & set(matches.columns):
        raise ValueError("Matchup context output columns already exist.")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Matches must be in chronological order with nonmissing dates.")

    h2h_histories = defaultdict(lambda: deque(maxlen=5))
    stadium_histories = defaultdict(lambda: deque(maxlen=5))
    last_dates = {}
    features = {column: [] for column in MATCHUP_CONTEXT_COLUMNS}
    for day, row in zip(dates, matches.loc[:, list(required)].itertuples(index=False)):
        ids = (row.home_team_id, row.away_team_id)
        if any(not isinstance(team_id, str) or not team_id.strip() for team_id in ids) or ids[0] == ids[1]:
            raise ValueError("Each match needs two distinct, nonempty team IDs.")
        if any(last_dates.get(team_id) == day for team_id in ids):
            raise ValueError("A club cannot appear twice on the same match_date.")
        if not isinstance(row.stadium, str) or not row.stadium.strip():
            raise ValueError("stadium must be a nonempty string.")
        scores = (row.home_score, row.away_score)
        if any(isinstance(score, bool) or not isinstance(score, Integral) or score < 0 for score in scores):
            raise ValueError("Scores must be nonnegative integers.")
        expected_result = 2 if scores[0] > scores[1] else 0 if scores[0] < scores[1] else 1
        if isinstance(row.result, bool) or not isinstance(row.result, Integral) or row.result != expected_result:
            raise ValueError("result must be 0/1/2 and agree with the 90-minute scores.")

        # Store pair history in a stable team order; orient it for this fixture.
        pair = tuple(sorted(ids))
        direction = 1 if ids[0] == pair[0] else -1
        h2h = h2h_histories[pair]
        features["h2h_last5_matches"].append(len(h2h))
        features["h2h_last5_points_diff"].append(direction * sum(game[0] for game in h2h))
        features["h2h_last5_goal_diff"].append(direction * sum(game[1] for game in h2h))
        for side, team_id in zip(("home", "away"), ids):
            history = stadium_histories[team_id, row.stadium]
            features[f"{side}_stadium_last5_matches"].append(len(history))
            features[f"{side}_stadium_last5_points"].append(sum(game[0] for game in history))
            features[f"{side}_stadium_last5_goal_diff"].append(sum(game[1] for game in history))

        # Update only after every feature for the current match is captured.
        home_points = 3 if row.result == 2 else 1 if row.result == 1 else 0
        away_points = 3 if row.result == 0 else 1 if row.result == 1 else 0
        goal_diff = scores[0] - scores[1]
        h2h.append((direction * (home_points - away_points), direction * goal_diff))
        stadium_histories[ids[0], row.stadium].append((home_points, goal_diff))
        stadium_histories[ids[1], row.stadium].append((away_points, -goal_diff))
        for team_id in ids:
            last_dates[team_id] = day

    output = matches.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output
