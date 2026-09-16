"""Pre-match form from each club's previous five completed matches; no I/O."""

from collections import defaultdict, deque
from numbers import Integral

import pandas as pd


METRICS = ("points", "wins", "draws", "losses", "goals_for", "goals_against")
FORM_COLUMNS = tuple(f"{side}_last5_{metric}" for metric in METRICS for side in ("home", "away"))


def add_form_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with twelve integer form columns, preserving row/index order.

    Supply completed matches in the existing chronological order, with stable
    home/away_team_id, match_date, home/away_score and 90-minute result (0/1/2).
    Completion checks and team-name resolution belong to the caller. Home and
    away appearances share one club history, across seasons and competitions.
    Each call starts empty; fewer than five prior matches use only those present.
    No sorting, Elo calculation, file access or persisted state is performed.
    """
    required = ("match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result")
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates or set(required) - set(matches.columns):
        raise ValueError(f"Expected unique columns including {required}.")
    if set(FORM_COLUMNS) & set(matches.columns):
        raise ValueError("Form output columns already exist.")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Matches must be in chronological order with nonmissing dates.")

    histories = defaultdict(lambda: deque(maxlen=5))
    last_dates = {}
    features = {column: [] for column in FORM_COLUMNS}
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

        # Record both clubs' features before appending this match's result.
        for side, team_id in zip(("home", "away"), ids):
            for position, metric in enumerate(METRICS):
                features[f"{side}_last5_{metric}"].append(sum(game[position] for game in histories[team_id]))
        for team_id, goals_for, goals_against, win_result in (
            (ids[0], scores[0], scores[1], 2), (ids[1], scores[1], scores[0], 0),
        ):
            win, draw = int(row.result == win_result), int(row.result == 1)
            histories[team_id].append((3 * win + draw, win, draw, 1 - win - draw, goals_for, goals_against))
            last_dates[team_id] = day

    output = matches.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output
