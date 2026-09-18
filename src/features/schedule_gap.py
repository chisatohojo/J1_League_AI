"""Calendar-day gaps since each team's previous match in the supplied stream."""

import pandas as pd


SCHEDULE_GAP_COLUMNS = (
    "home_days_since_last_match", "away_days_since_last_match",
    "days_since_last_match_diff", "home_has_previous_match", "away_has_previous_match",
)


def add_schedule_gap_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with five integer features for the supplied match history.

    These gaps describe previous recorded matches, not true physical rest days:
    unprovided cup, continental or other matches are outside this input stream.
    Supply completed matches chronologically. Home/away roles and season
    boundaries share one team history, which starts empty on each call.
    Calendar dates are used even when timestamps include times. Prior gaps
    must be positive; first appearances have gap/flag zero, and the difference
    is zero unless both teams have prior matches. No cap or transformation is
    applied. Source columns, dtypes, index and row order are preserved. Only
    dates and team IDs are read for calculation; no results or other features
    are used. Completion checks belong to the caller. No I/O is performed.
    """
    required = ("match_date", "home_team_id", "away_team_id")
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates or set(required) - set(matches.columns):
        raise ValueError(f"Expected unique columns including {required}.")
    if set(SCHEDULE_GAP_COLUMNS) & set(matches.columns):
        raise ValueError("Schedule gap output columns already exist.")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Matches must be in chronological order with nonmissing dates.")

    last_dates = {}
    features = {column: [] for column in SCHEDULE_GAP_COLUMNS}
    teams = matches.loc[:, ["home_team_id", "away_team_id"]]
    for timestamp, ids in zip(dates, teams.itertuples(index=False, name=None)):
        if any(not isinstance(team_id, str) or not team_id.strip() for team_id in ids) or ids[0] == ids[1]:
            raise ValueError("Each match needs two distinct, nonempty team IDs.")
        day = timestamp.date()
        gaps, has_previous = [], []
        for side, team_id in zip(("home", "away"), ids):
            previous = last_dates.get(team_id)
            present = int(previous is not None)
            gap = (day - previous).days if present else 0
            if present and gap <= 0:
                raise ValueError("A club's previous match must be on an earlier calendar date.")
            gaps.append(gap)
            has_previous.append(present)
            features[f"{side}_days_since_last_match"].append(gap)
            features[f"{side}_has_previous_match"].append(present)
        features["days_since_last_match_diff"].append(gaps[0] - gaps[1] if all(has_previous) else 0)

        # Both pre-match feature sets are recorded before either history changes.
        for team_id in ids:
            last_dates[team_id] = day

    output = matches.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output
