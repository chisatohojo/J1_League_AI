"""Pre-match form from each club's previous five completed matches; no I/O."""

from collections import defaultdict, deque
from numbers import Integral

import pandas as pd


METRICS = ("points", "wins", "draws", "losses", "goals_for", "goals_against")
FORM_COLUMNS = tuple(f"{side}_last5_{metric}" for metric in METRICS for side in ("home", "away"))
HISTORY_COLUMNS = (
    "match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result"
)
TARGET_COLUMNS = ("match_id", "match_date", "home_team_id", "away_team_id")


def _validate_columns(frame, required, name):
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame.")
    if frame.columns.has_duplicates or set(required) - set(frame.columns):
        raise ValueError(f"Expected unique {name} columns including {required}.")
    if set(FORM_COLUMNS) & set(frame.columns):
        raise ValueError("Form output columns already exist.")


def _validated_history(matches, *, validate_match_ids=False):
    _validate_columns(matches, HISTORY_COLUMNS, "history")
    dates = pd.to_datetime(matches["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("Matches must be in chronological order with nonmissing dates.")
    if validate_match_ids and "match_id" in matches:
        ids = matches["match_id"]
        if ids.isna().any() or ids.astype(str).str.strip().eq("").any() or ids.duplicated().any():
            raise ValueError("History match_id must be nonblank and unique.")

    validated = []
    last_dates = {}
    for day, row in zip(dates, matches.loc[:, list(HISTORY_COLUMNS)].itertuples(index=False)):
        team_ids = (row.home_team_id, row.away_team_id)
        if (
            any(not isinstance(team_id, str) or not team_id.strip() for team_id in team_ids)
            or team_ids[0] == team_ids[1]
        ):
            raise ValueError("Each match needs two distinct, nonempty team IDs.")
        if any(last_dates.get(team_id) == day for team_id in team_ids):
            raise ValueError("A club cannot appear twice on the same match_date.")
        scores = (row.home_score, row.away_score)
        if any(
            isinstance(score, bool) or not isinstance(score, Integral) or score < 0
            for score in scores
        ):
            raise ValueError("Scores must be nonnegative integers.")
        expected_result = 2 if scores[0] > scores[1] else 0 if scores[0] < scores[1] else 1
        if (
            isinstance(row.result, bool)
            or not isinstance(row.result, Integral)
            or row.result != expected_result
        ):
            raise ValueError("result must be 0/1/2 and agree with the 90-minute scores.")
        validated.append((day, team_ids, scores, row.result))
        for team_id in team_ids:
            last_dates[team_id] = day
    return dates, validated


def _append_result(histories, team_ids, scores, result):
    for team_id, goals_for, goals_against, win_result in (
        (team_ids[0], scores[0], scores[1], 2),
        (team_ids[1], scores[1], scores[0], 0),
    ):
        win, draw = int(result == win_result), int(result == 1)
        histories[team_id].append(
            (3 * win + draw, win, draw, 1 - win - draw, goals_for, goals_against)
        )


def _emit(features, histories, side, team_id):
    for position, metric in enumerate(METRICS):
        features[f"{side}_last5_{metric}"].append(
            sum(game[position] for game in histories[team_id])
        )


def add_form_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with twelve integer form columns, preserving row/index order.

    Supply completed matches in the existing chronological order, with stable
    home/away_team_id, match_date, home/away_score and 90-minute result (0/1/2).
    Completion checks and team-name resolution belong to the caller. Home and
    away appearances share one club history, across seasons and competitions.
    Each call starts empty; fewer than five prior matches use only those present.
    No sorting, Elo calculation, file access or persisted state is performed.
    """
    _dates, validated = _validated_history(matches)
    histories = defaultdict(lambda: deque(maxlen=5))
    features = {column: [] for column in FORM_COLUMNS}
    for _day, team_ids, scores, result in validated:
        # Record both clubs' features before appending this match's result.
        for side, team_id in zip(("home", "away"), team_ids):
            _emit(features, histories, side, team_id)
        _append_result(histories, team_ids, scores, result)

    output = matches.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output


def add_form_features_to_targets(history: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """Attach form from completed history to one read-only same-date target batch.

    Every history match must be strictly earlier than the shared target date.
    Targets never need or receive fabricated scores/results and cannot affect one
    another's state.
    """
    history_dates, validated = _validated_history(history, validate_match_ids=True)
    _validate_columns(targets, TARGET_COLUMNS, "target")
    if targets.empty:
        raise ValueError("Target batch must not be empty.")
    target_ids = targets["match_id"]
    if (
        target_ids.isna().any()
        or target_ids.astype(str).str.strip().eq("").any()
        or target_ids.duplicated().any()
    ):
        raise ValueError("Target match_id must be nonblank and unique.")
    target_dates = pd.to_datetime(targets["match_date"], errors="raise")
    if target_dates.isna().any() or target_dates.dt.normalize().nunique() != 1:
        raise ValueError("All targets must share one valid calendar date.")
    target_date = target_dates.dt.normalize().iloc[0]
    if not history_dates.empty and history_dates.dt.normalize().ge(target_date).any():
        raise ValueError("All history match_date values must be strictly before target_date.")

    appearances = []
    for row in targets.loc[:, list(TARGET_COLUMNS)].itertuples(index=False):
        team_ids = (row.home_team_id, row.away_team_id)
        if (
            any(not isinstance(team_id, str) or not team_id.strip() for team_id in team_ids)
            or team_ids[0] == team_ids[1]
        ):
            raise ValueError("Each target needs two distinct, nonempty team IDs.")
        appearances.extend(team_ids)
    if pd.Series(appearances, dtype="object").duplicated().any():
        raise ValueError("A club cannot appear twice in one target-date batch.")

    histories = defaultdict(lambda: deque(maxlen=5))
    for _day, team_ids, scores, result in validated:
        _append_result(histories, team_ids, scores, result)
    features = {column: [] for column in FORM_COLUMNS}
    for row in targets.loc[:, list(TARGET_COLUMNS)].itertuples(index=False):
        for side, team_id in zip(("home", "away"), (row.home_team_id, row.away_team_id)):
            _emit(features, histories, side, team_id)

    output = targets.copy(deep=True)
    for column, values in features.items():
        output[column] = pd.array(values, dtype="int64")
    return output
