"""Pre-match rolling sums of official SH, CK and FK team statistics."""

from collections import defaultdict, deque
from numbers import Integral

import pandas as pd


STAT_COLUMNS = ("shots", "ck", "fk")
MATCH_STATS_FORM_COLUMNS = tuple(
    f"{side}_stats_lastn_{metric}_{kind}"
    for metric in STAT_COLUMNS
    for kind in ("for", "against", "diff")
    for side in ("home", "away")
)
REQUIRED_COLUMNS = (
    "match_date", "home_team_id", "away_team_id",
    "home_shots", "away_shots", "home_ck", "away_ck", "home_fk", "away_fk",
)


def add_match_stats_form_features(matches: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Return pre-match rolling statistic sums, preserving the input frame."""
    if isinstance(window, bool) or not isinstance(window, Integral) or window < 1:
        raise ValueError("window must be a positive integer, excluding bool.")
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates or set(REQUIRED_COLUMNS) - set(matches.columns):
        raise ValueError("Expected unique columns including all required match-stat columns.")
    if set(MATCH_STATS_FORM_COLUMNS) & set(matches.columns):
        raise ValueError("Match-stat form output columns already exist.")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("match_date must be nonmissing and chronologically ascending.")

    history = defaultdict(lambda: deque(maxlen=int(window)))
    last_dates = {}
    features = {column: [] for column in MATCH_STATS_FORM_COLUMNS}
    stat_pairs = tuple((f"home_{metric}", f"away_{metric}") for metric in STAT_COLUMNS)

    for day, row in zip(dates, matches.loc[:, list(REQUIRED_COLUMNS)].itertuples(index=False)):
        teams = (row.home_team_id, row.away_team_id)
        if any(not isinstance(team, str) or not team.strip() for team in teams):
            raise ValueError("Team IDs must be nonempty strings.")
        if teams[0] == teams[1]:
            raise ValueError("Home and away team IDs must differ.")
        calendar_day = day.date()
        if any(last_dates.get(team) == calendar_day for team in teams):
            raise ValueError("A team cannot appear twice on the same match_date.")

        values = {}
        for metric, (home_column, away_column) in zip(STAT_COLUMNS, stat_pairs):
            home_value, away_value = getattr(row, home_column), getattr(row, away_column)
            if any(isinstance(value, bool) or not isinstance(value, Integral) or value < 0
                   for value in (home_value, away_value)):
                raise ValueError(f"{metric} values must be nonnegative integers.")
            values[metric] = (int(home_value), int(away_value))

        # Read each team's history before appending the current match.
        for side, team in zip(("home", "away"), teams):
            totals = {metric: [0, 0] for metric in STAT_COLUMNS}
            for previous in history[team]:
                for index, metric in enumerate(STAT_COLUMNS):
                    totals[metric][0] += previous[index * 2]
                    totals[metric][1] += previous[index * 2 + 1]
            for metric in STAT_COLUMNS:
                prefix = f"{side}_stats_lastn_{metric}"
                features[f"{prefix}_for"].append(totals[metric][0])
                features[f"{prefix}_against"].append(totals[metric][1])
                features[f"{prefix}_diff"].append(totals[metric][0] - totals[metric][1])

        history[teams[0]].append(tuple(value for pair in values.values() for value in pair))
        history[teams[1]].append(tuple(value for pair in values.values() for value in (pair[1], pair[0])))
        last_dates[teams[0]] = calendar_day
        last_dates[teams[1]] = calendar_day

    output = matches.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output
