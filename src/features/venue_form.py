"""Pre-match form with separate home and away histories for each club."""

from collections import defaultdict, deque
from numbers import Integral

import pandas as pd


VENUE_FORM_COLUMNS = (
    "home_last5_home_points", "away_last5_away_points",
    "home_last5_home_goal_diff", "away_last5_away_goal_diff",
)


def add_venue_form_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with four integer features, preserving all input row order.

    Supply chronologically ordered completed matches with stable team IDs and
    90-minute scores/result (0=away win, 1=draw, 2=home win). Completion and name
    resolution remain the caller's responsibility. Each call starts empty;
    only the previous five appearances in the same home/away role contribute.
    There is no sorting, season reset, file access or persistent state.
    """
    required = ("match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result")
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates or set(required) - set(matches.columns):
        raise ValueError(f"Expected unique columns including {required}.")
    if set(VENUE_FORM_COLUMNS) & set(matches.columns):
        raise ValueError("Venue form output columns already exist.")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Matches must be in chronological order with nonmissing dates.")

    histories = {side: defaultdict(lambda: deque(maxlen=5)) for side in ("home", "away")}
    last_dates = {}
    features = {column: [] for column in VENUE_FORM_COLUMNS}
    for day, row in zip(dates, matches.loc[:, list(required)].itertuples(index=False)):
        ids = (row.home_team_id, row.away_team_id)
        if any(not isinstance(team_id, str) or not team_id.strip() for team_id in ids) or ids[0] == ids[1]:
            raise ValueError("Each match needs two distinct, nonempty team IDs.")
        if any(last_dates.get(team_id) == day for team_id in ids):
            raise ValueError("A club cannot appear twice on the same match_date.")
        scores = (row.home_score, row.away_score)
        if any(isinstance(score, bool) or not isinstance(score, Integral) or score < 0 for score in scores):
            raise ValueError("Scores must be nonnegative integers.")
        expected_result = 2 if scores[0] > scores[1] else 0 if scores[0] < scores[1] else 1
        if isinstance(row.result, bool) or not isinstance(row.result, Integral) or row.result != expected_result:
            raise ValueError("result must be 0/1/2 and agree with the 90-minute scores.")

        # Read both pre-match histories before adding this match to either one.
        for side, team_id in zip(("home", "away"), ids):
            history = histories[side][team_id]
            features[f"{side}_last5_{side}_points"].append(sum(game[0] for game in history))
            features[f"{side}_last5_{side}_goal_diff"].append(sum(game[1] for game in history))
        goal_diff = scores[0] - scores[1]
        for side, team_id, win_result, difference in (
            ("home", ids[0], 2, goal_diff), ("away", ids[1], 0, -goal_diff),
        ):
            points = 3 if row.result == win_result else 1 if row.result == 1 else 0
            histories[side][team_id].append((points, difference))
            last_dates[team_id] = day

    output = matches.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output
