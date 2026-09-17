"""Synthetic, chronological checks for leakage-free matchup context."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features.matchup_context import (
    MATCHUP_CONTEXT_COLUMNS,
    add_matchup_context_features,
)


EXPECTED_COLUMNS = [
    "h2h_last5_matches",
    "h2h_last5_points_diff",
    "h2h_last5_goal_diff",
    "home_stadium_last5_matches",
    "home_stadium_last5_points",
    "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches",
    "away_stadium_last5_points",
    "away_stadium_last5_goal_diff",
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


def _last_features(frame, columns=EXPECTED_COLUMNS):
    return add_matchup_context_features(frame).iloc[-1][columns].tolist()


def test_first_match_is_all_zero_and_feature_contract_is_integer():
    source = _matches(("A", "B", "Main", 4, 0))
    actual = add_matchup_context_features(source)
    assert list(MATCHUP_CONTEXT_COLUMNS) == EXPECTED_COLUMNS
    assert actual.columns.tolist() == SOURCE_COLUMNS + EXPECTED_COLUMNS
    assert actual[EXPECTED_COLUMNS].iloc[0].tolist() == [0] * 9
    assert all(pd.api.types.is_integer_dtype(actual[column]) for column in EXPECTED_COLUMNS)


def test_second_direct_meeting_uses_previous_match_at_any_stadium():
    source = _matches(("A", "B", "Old", 2, 0), ("A", "B", "New", 0, 1))
    assert _last_features(source, EXPECTED_COLUMNS[:3]) == [1, 3, 2]


def test_reversed_home_away_roles_reverse_h2h_signs():
    source = _matches(("A", "B", "Main", 3, 1), ("B", "A", "Elsewhere", 0, 0))
    assert _last_features(source, EXPECTED_COLUMNS[:3]) == [1, -3, -2]


def test_h2h_excludes_other_opponents():
    source = _matches(
        ("A", "B", "Main", 2, 2),
        ("A", "C", "Main", 5, 0),
        ("D", "B", "Other", 0, 4),
        ("A", "B", "Main", 1, 0),
    )
    assert _last_features(source, EXPECTED_COLUMNS[:3]) == [1, 0, 0]


def test_h2h_keeps_only_the_last_five_direct_meetings():
    source = _matches(
        ("A", "B", "Main", 9, 0),
        ("A", "B", "Main", 1, 0),
        ("B", "A", "Other", 0, 0),
        ("A", "B", "Main", 0, 2),
        ("B", "A", "Other", 1, 2),
        ("A", "B", "Main", 0, 3),
        ("A", "B", "Main", 8, 0),
    )
    assert _last_features(source, EXPECTED_COLUMNS[:3]) == [5, 0, -3]


def test_home_stadium_history_includes_different_opponents():
    source = _matches(
        ("A", "C", "Main", 2, 0),
        ("A", "D", "Main", 1, 1),
        ("A", "B", "Main", 0, 1),
    )
    assert _last_features(source, EXPECTED_COLUMNS[3:6]) == [2, 4, 2]


def test_away_stadium_history_is_from_current_away_teams_perspective():
    source = _matches(
        ("B", "C", "Main", 3, 1),
        ("D", "B", "Main", 0, 0),
        ("A", "B", "Main", 0, 1),
    )
    assert _last_features(source, EXPECTED_COLUMNS[6:]) == [2, 4, 2]


def test_stadium_keys_match_exactly_without_case_or_whitespace_normalization():
    source = _matches(
        ("A", "C", "Main", 1, 0),
        ("A", "D", "main", 5, 0),
        ("A", "E", "Main ", 6, 0),
        ("F", "B", "Other", 0, 4),
        ("A", "B", "Main", 0, 0),
    )
    assert _last_features(source, EXPECTED_COLUMNS[3:]) == [1, 3, 1, 0, 0, 0]


def test_stadium_history_counts_both_roles_with_each_teams_points_and_goals():
    source = _matches(
        ("A", "B", "Main", 1, 3),
        ("B", "A", "Main", 2, 0),
        ("A", "B", "Main", 0, 0),
    )
    assert _last_features(source, EXPECTED_COLUMNS[3:]) == [2, 0, -4, 2, 6, 4]


def test_stadium_history_keeps_last_five_appearances_across_roles():
    source = _matches(
        ("A", "C", "Main", 9, 0),
        ("A", "D", "Main", 1, 0),
        ("E", "A", "Main", 0, 0),
        ("A", "F", "Main", 0, 2),
        ("G", "A", "Main", 1, 2),
        ("A", "H", "Main", 0, 3),
        ("A", "B", "Main", 8, 0),
    )
    assert _last_features(source, EXPECTED_COLUMNS[3:6]) == [5, 7, -3]


def test_counts_distinguish_no_history_from_five_losses():
    source = _matches(
        *(("A", f"Opponent{i}", "Main", 0, 1) for i in range(5)),
        ("A", "B", "Main", 0, 0),
    )
    assert _last_features(source, EXPECTED_COLUMNS[3:]) == [5, 0, -5, 0, 0, 0]


def test_current_result_never_enters_its_own_features():
    source = _matches(
        ("A", "B", "Main", 2, 0),
        ("A", "C", "Main", 1, 1),
        ("B", "A", "Main", 0, 3),
    )
    changed = source.copy(deep=True)
    changed.loc[2, ["home_score", "away_score", "result"]] = [4, 0, 2]
    assert _last_features(source) == _last_features(changed)


def test_future_result_changes_and_appends_do_not_change_past_features():
    source = _matches(
        ("A", "B", "Main", 2, 0),
        ("B", "A", "Main", 1, 1),
        ("A", "B", "Main", 0, 3),
    )
    extended = _matches(
        ("A", "B", "Main", 2, 0),
        ("B", "A", "Main", 1, 1),
        ("A", "B", "Main", 7, 0),
        ("B", "A", "Main", 9, 0),
    )
    assert_frame_equal(
        add_matchup_context_features(source)[EXPECTED_COLUMNS],
        add_matchup_context_features(extended).iloc[:len(source)][EXPECTED_COLUMNS],
    )


@pytest.mark.parametrize("scores,result", [((2, 0), 0), ((0, 2), 2), ((1, 1), 2)])
def test_inconsistent_score_and_result_are_rejected(scores, result):
    source = _matches(("A", "B", "Main", *scores))
    source.loc[0, "result"] = result
    with pytest.raises(ValueError):
        add_matchup_context_features(source)


def test_source_is_unmodified_and_original_dtypes_duplicate_index_and_order_survive():
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
    actual = add_matchup_context_features(source)
    assert actual is not source
    assert_frame_equal(source, before)
    assert_frame_equal(actual[source.columns], before)
    assert actual.columns.tolist() == source.columns.tolist() + EXPECTED_COLUMNS
    assert actual[EXPECTED_COLUMNS[:3]].to_numpy().tolist() == [[0, 0, 0], [1, -3, -1], [0, 0, 0]]


def test_repeated_calls_are_deterministic():
    source = _matches(("A", "B", "Main", 2, 0), ("B", "A", "Main", 0, 0))
    assert_frame_equal(add_matchup_context_features(source), add_matchup_context_features(source))


def test_empty_frame_preserves_schema_and_adds_integer_features():
    source = _matches()
    actual = add_matchup_context_features(source)
    assert_frame_equal(actual[SOURCE_COLUMNS], source)
    assert actual.columns.tolist() == SOURCE_COLUMNS + EXPECTED_COLUMNS
    assert all(pd.api.types.is_integer_dtype(actual[column]) for column in EXPECTED_COLUMNS)


@pytest.mark.parametrize("case", ["missing", "duplicate", "output_collision"])
def test_invalid_columns_are_rejected(case):
    source = _matches(("A", "B", "Main", 0, 0))
    if case == "missing":
        source = source.drop(columns="stadium")
    elif case == "duplicate":
        source = pd.concat([source, source[["stadium"]]], axis=1)
    else:
        source[EXPECTED_COLUMNS[0]] = 0
    with pytest.raises(ValueError):
        add_matchup_context_features(source)


@pytest.mark.parametrize("column,value", [
    ("match_date", pd.NaT),
    ("home_team_id", ""),
    ("away_team_id", "A"),
    ("stadium", ""),
    ("stadium", None),
    ("home_score", -1),
    ("home_score", 0.5),
    ("result", 3),
])
def test_invalid_required_values_are_rejected(column, value):
    source = _matches(("A", "B", "Main", 0, 0))
    source[column] = value
    with pytest.raises(ValueError):
        add_matchup_context_features(source)


def test_unsorted_dates_and_repeated_team_on_same_date_are_rejected():
    source = _matches(("A", "B", "Main", 0, 0), ("C", "A", "Other", 0, 0))
    with pytest.raises(ValueError):
        add_matchup_context_features(source.iloc[::-1])
    source.loc[1, "match_date"] = source.loc[0, "match_date"]
    with pytest.raises(ValueError):
        add_matchup_context_features(source)


def test_independent_matches_on_the_same_date_are_valid():
    source = _matches(("A", "B", "Main", 0, 0), ("C", "D", "Main", 1, 0))
    source.loc[1, "match_date"] = source.loc[0, "match_date"]
    actual = add_matchup_context_features(source)
    assert actual[EXPECTED_COLUMNS].to_numpy().tolist() == [[0] * 9, [0] * 9]
