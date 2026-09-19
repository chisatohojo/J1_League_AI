"""Synthetic checks for configurable, leakage-free team/stadium history."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features.matchup_context import add_matchup_context_features
from src.features.stadium_window import (
    STADIUM_WINDOW_COLUMNS,
    add_stadium_window_features,
)


EXPECTED_COLUMNS = [
    "home_stadium_window_matches",
    "home_stadium_window_points",
    "home_stadium_window_goal_diff",
    "away_stadium_window_matches",
    "away_stadium_window_points",
    "away_stadium_window_goal_diff",
]
SOURCE_COLUMNS = [
    "match_date", "home_team_id", "away_team_id", "stadium",
    "home_score", "away_score", "result",
]


def _matches(*games):
    records = []
    for i, (home, away, stadium, home_score, away_score) in enumerate(games):
        records.append({
            "match_date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=i),
            "home_team_id": home,
            "away_team_id": away,
            "stadium": stadium,
            "home_score": home_score,
            "away_score": away_score,
            "result": 2 if home_score > away_score else 0 if home_score < away_score else 1,
        })
    frame = pd.DataFrame(records, columns=SOURCE_COLUMNS)
    frame["match_date"] = pd.to_datetime(frame["match_date"])
    return frame.astype({"home_score": "int64", "away_score": "int64", "result": "int64"})


def _features(frame, window):
    return add_stadium_window_features(frame, window=window)[EXPECTED_COLUMNS]


def _rolling_fixture():
    # Values are from A's perspective, with home/away roles alternating.
    goal_differences = [7, 0, -3, 1, -2, 0, 4, -1, 2, 0, 5, -4]
    games = []
    for i, difference in enumerate(goal_differences):
        home, away = ("A", "B") if i % 2 == 0 else ("B", "A")
        home_difference = difference if home == "A" else -difference
        games.append((home, away, "Main", max(home_difference, 0), max(-home_difference, 0)))
    return _matches(*games)


def test_window_five_matches_existing_stadium_features_exactly():
    source = _rolling_fixture()
    source.loc[[2, 6], "stadium"] = "Other"
    source.loc[[3, 8], "away_team_id"] = "C"
    source.index = pd.Index([9, 9, 3, 2, 8, 4, 0, 6, 5, 1, 7, 10], name="row")
    oracle = add_matchup_context_features(source)
    old_columns = [name.replace("_window_", "_last5_") for name in EXPECTED_COLUMNS]
    expected = oracle[source.columns.tolist() + old_columns].rename(
        columns=dict(zip(old_columns, EXPECTED_COLUMNS))
    )
    assert_frame_equal(add_stadium_window_features(source, window=5), expected)


@pytest.mark.parametrize("window", [1, 3, 8, 10])
def test_windows_keep_only_the_requested_number_of_prior_appearances(window):
    actual = _features(_rolling_fixture(), window)
    a_points = [3, 1, 0, 3, 0, 1, 3, 0, 3, 1, 3, 0]
    b_points = [0, 1, 3, 0, 3, 1, 0, 3, 0, 1, 0, 3]
    a_goal_differences = [7, 0, -3, 1, -2, 0, 4, -1, 2, 0, 5, -4]
    for i in range(len(actual)):
        prior = slice(max(0, i - window), i)
        count = min(i, window)
        a = [count, sum(a_points[prior]), sum(a_goal_differences[prior])]
        b = [count, sum(b_points[prior]), -sum(a_goal_differences[prior])]
        assert actual.iloc[i].tolist() == (a + b if i % 2 == 0 else b + a)
    assert actual[EXPECTED_COLUMNS[0]].max() == window
    assert actual[EXPECTED_COLUMNS[3]].max() == window


def test_first_match_has_zero_history_and_exact_int64_column_contract():
    source = _matches(("A", "B", "Main", 4, 0))
    actual = add_stadium_window_features(source, window=3)
    assert list(STADIUM_WINDOW_COLUMNS) == EXPECTED_COLUMNS
    assert actual.columns.tolist() == SOURCE_COLUMNS + EXPECTED_COLUMNS
    assert actual[EXPECTED_COLUMNS].iloc[0].tolist() == [0] * 6
    assert all(actual[column].dtype == np.dtype("int64") for column in EXPECTED_COLUMNS)


def test_fewer_than_window_uses_all_available_games_without_padding():
    source = _matches(("A", "B", "Main", 2, 0), ("B", "A", "Main", 0, 0))
    assert _features(source, 10).iloc[-1].tolist() == [1, 0, -2, 1, 3, 2]


def test_history_is_keyed_by_both_team_and_stadium():
    source = _matches(
        ("A", "C", "Main", 2, 0),
        ("A", "D", "Other", 4, 0),
        ("E", "F", "Main", 1, 0),
        ("B", "G", "Main", 0, 3),
        ("A", "B", "Main", 0, 0),
    )
    assert _features(source, 8).iloc[-1].tolist() == [1, 3, 2, 1, 0, -3]


@pytest.mark.parametrize("home,away,expected", [
    ("A", "B", [2, 6, 4, 2, 3, 1]),
    ("B", "A", [2, 3, 1, 2, 6, 4]),
])
def test_both_roles_and_different_opponents_share_each_teams_stadium_history(home, away, expected):
    source = _matches(
        ("A", "C", "Main", 2, 0),
        ("D", "A", "Main", 1, 3),
        ("B", "E", "Main", 0, 1),
        ("F", "B", "Main", 0, 2),
        (home, away, "Main", 0, 0),
    )
    assert _features(source, 3).iloc[-1].tolist() == expected


@pytest.mark.parametrize("scores,expected", [
    ((4, 1), [1, 0, -3, 1, 3, 3]),
    ((2, 2), [1, 1, 0, 1, 1, 0]),
    ((0, 2), [1, 3, 2, 1, 0, -2]),
])
def test_points_and_goal_difference_follow_each_teams_perspective(scores, expected):
    source = _matches(("A", "B", "Main", *scores), ("B", "A", "Main", 0, 0))
    assert _features(source, 1).iloc[-1].tolist() == expected


def test_stadium_and_team_keys_preserve_case_and_spaces_exactly():
    source = _matches(
        ("A", "C", "Main", 1, 0),
        ("A", "D", "main", 5, 0),
        ("A", "E", "Main ", 6, 0),
        ("A ", "F", "Main", 7, 0),
        ("a", "G", "Main", 8, 0),
        ("A", "B", "Main", 0, 0),
    )
    assert _features(source, 10).iloc[-1].tolist() == [1, 3, 1, 0, 0, 0]


def test_no_history_is_distinct_from_a_full_window_of_losses():
    source = _matches(
        *(("A", f"Opponent{i}", "Main", 0, 1) for i in range(3)),
        ("A", "B", "Main", 0, 0),
    )
    assert _features(source, 3).iloc[-1].tolist() == [3, 0, -3, 0, 0, 0]


def test_current_result_is_excluded_from_both_teams_features():
    source = _rolling_fixture()
    changed = source.copy(deep=True)
    changed.loc[len(source) - 1, ["home_score", "away_score", "result"]] = [0, 9, 0]
    assert_frame_equal(_features(source, 3), _features(changed, 3))


def test_future_changes_and_appends_cannot_change_past_features():
    source = _rolling_fixture()
    extended = source.copy(deep=True)
    extended.loc[8:, ["home_score", "away_score", "result"]] = [9, 0, 2]
    last_game = _matches(("A", "B", "Main", 0, 8))
    last_game["match_date"] = pd.Timestamp("2025-02-01")
    extended = pd.concat([extended, last_game], ignore_index=True)
    assert_frame_equal(_features(source.iloc[:8], 3), _features(extended, 3).iloc[:8])


def test_penalties_extra_time_and_tie_winner_do_not_change_ninety_minute_history():
    source = _matches(("A", "B", "Main", 1, 1), ("B", "A", "Main", 0, 0))
    source["home_pk_score"] = [5, 0]
    source["away_pk_score"] = [3, 0]
    source["home_extra_time_score"] = [2, 0]
    source["away_extra_time_score"] = [0, 0]
    source["tie_winner"] = ["A", "B"]
    actual = add_stadium_window_features(source, window=3)
    assert actual[EXPECTED_COLUMNS].iloc[-1].tolist() == [1, 1, 0, 1, 1, 0]
    assert_frame_equal(actual[source.columns], source)


def test_source_dtypes_duplicate_index_order_and_determinism_are_preserved():
    source = _matches(
        ("A", "B", "Main", 1, 0),
        ("B", "A", "Main", 0, 0),
        ("A", "C", "Main", 2, 3),
    ).astype({
        "home_team_id": "string", "away_team_id": "string", "stadium": "string",
        "home_score": "int16", "away_score": "int32", "result": "int8",
    })
    source["note"] = pd.Categorical(["first", "second", "first"])
    source.index = pd.Index([7, 7, 2], name="original_row")
    before = source.copy(deep=True)
    actual = add_stadium_window_features(source, window=3)
    assert actual is not source
    assert_frame_equal(source, before)
    assert_frame_equal(actual[source.columns], before)
    assert actual.columns.tolist() == source.columns.tolist() + EXPECTED_COLUMNS
    assert actual[EXPECTED_COLUMNS].to_numpy().tolist() == [
        [0, 0, 0, 0, 0, 0], [1, 0, -1, 1, 3, 1], [2, 4, 1, 0, 0, 0],
    ]
    assert_frame_equal(actual, add_stadium_window_features(source, window=3))


def test_existing_last_five_and_h2h_columns_remain_unchanged():
    source = add_matchup_context_features(_rolling_fixture())
    before = source.copy(deep=True)
    actual = add_stadium_window_features(source, window=3)
    assert_frame_equal(actual[source.columns], before)
    assert_frame_equal(source, before)
    assert actual.columns.tolist() == source.columns.tolist() + EXPECTED_COLUMNS
    assert actual.iloc[-1]["home_stadium_last5_matches"] == 5
    assert actual.iloc[-1]["home_stadium_window_matches"] == 3


def test_empty_frame_preserves_schema_and_adds_int64_features():
    source = _matches()
    actual = add_stadium_window_features(source, window=3)
    assert_frame_equal(actual[SOURCE_COLUMNS], source)
    assert actual.columns.tolist() == SOURCE_COLUMNS + EXPECTED_COLUMNS
    assert all(actual[column].dtype == np.dtype("int64") for column in EXPECTED_COLUMNS)


@pytest.mark.parametrize("window", [0, -1, 1.5, 1.0, True, False, "3", None, np.bool_(True)])
def test_invalid_windows_are_rejected(window):
    with pytest.raises((TypeError, ValueError)):
        add_stadium_window_features(_matches(("A", "B", "Main", 0, 0)), window=window)


@pytest.mark.parametrize("window", [np.int32(1), np.int64(3)])
def test_numpy_integer_windows_are_accepted(window):
    source = _matches(("A", "B", "Main", 2, 0), ("B", "A", "Main", 0, 0))
    assert_frame_equal(_features(source, window), _features(source, int(window)))


@pytest.mark.parametrize("scores,result", [((2, 0), 0), ((0, 2), 2), ((1, 1), 2)])
def test_contradictory_results_are_rejected(scores, result):
    source = _matches(("A", "B", "Main", *scores))
    source["result"] = result
    with pytest.raises(ValueError):
        add_stadium_window_features(source, window=3)


@pytest.mark.parametrize("column,value", [
    ("match_date", pd.NaT), ("match_date", "not-a-date"),
    ("home_team_id", ""), ("home_team_id", "   "), ("home_team_id", None),
    ("home_team_id", 12), ("away_team_id", ""), ("away_team_id", "A"),
    ("stadium", ""), ("stadium", "   "), ("stadium", None), ("stadium", 12),
    ("home_score", -1), ("home_score", 0.5), ("home_score", 0.0),
    ("home_score", True), ("away_score", -1), ("away_score", False),
    ("away_score", None), ("result", 3), ("result", -1),
    ("result", 1.0), ("result", True), ("result", None),
])
def test_invalid_required_values_are_rejected(column, value):
    source = _matches(("A", "B", "Main", 0, 0))
    source[column] = value
    with pytest.raises(ValueError):
        add_stadium_window_features(source, window=3)


def test_unsorted_dates_are_rejected_without_sorting_or_mutating_input():
    source = _matches(("A", "B", "Main", 0, 0), ("C", "D", "Main", 0, 0)).iloc[::-1]
    before = source.copy(deep=True)
    with pytest.raises(ValueError):
        add_stadium_window_features(source, window=3)
    assert_frame_equal(source, before)


@pytest.mark.parametrize("second_kickoff", ["2025-01-01 10:00", "2025-01-01 20:00"])
def test_a_club_cannot_play_twice_on_the_same_calendar_day(second_kickoff):
    source = _matches(("A", "B", "Main", 0, 0), ("C", "A", "Other", 0, 0))
    source["match_date"] = pd.to_datetime(["2025-01-01 10:00", second_kickoff])
    with pytest.raises(ValueError):
        add_stadium_window_features(source, window=3)


def test_independent_matches_on_the_same_day_are_allowed():
    source = _matches(("A", "B", "Main", 0, 0), ("C", "D", "Main", 1, 0))
    source["match_date"] = pd.Timestamp("2025-01-01")
    assert _features(source, 3).to_numpy().tolist() == [[0] * 6, [0] * 6]


@pytest.mark.parametrize("missing_column", SOURCE_COLUMNS)
def test_each_required_column_is_checked(missing_column):
    source = _matches(("A", "B", "Main", 0, 0)).drop(columns=missing_column)
    with pytest.raises(ValueError):
        add_stadium_window_features(source, window=3)


@pytest.mark.parametrize("collision", EXPECTED_COLUMNS)
def test_each_new_output_column_collision_is_rejected(collision):
    source = _matches(("A", "B", "Main", 0, 0))
    source[collision] = 999
    with pytest.raises(ValueError):
        add_stadium_window_features(source, window=3)


def test_duplicate_input_columns_are_rejected():
    source = _matches(("A", "B", "Main", 0, 0))
    source = pd.concat([source, source[["stadium"]]], axis=1)
    with pytest.raises(ValueError):
        add_stadium_window_features(source, window=3)


def test_non_dataframe_input_is_rejected():
    with pytest.raises(TypeError):
        add_stadium_window_features([], window=3)
