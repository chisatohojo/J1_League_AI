"""Synthetic checks for venue-specific, pre-match form features."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features.venue_form import add_venue_form_features


FEATURE_COLUMNS = (
    "home_last5_home_points",
    "away_last5_away_points",
    "home_last5_home_goal_diff",
    "away_last5_away_goal_diff",
)


def _matches(rows):
    matches = pd.DataFrame(rows, columns=["home_team_id", "away_team_id", "home_score", "away_score"])
    matches.insert(0, "match_date", pd.date_range("2025-01-01", periods=len(rows)))
    matches["result"] = [2 if home > away else 0 if home < away else 1 for _, _, home, away in rows]
    return matches


def test_first_match_has_zero_features():
    output = add_venue_form_features(_matches([("A", "B", 2, 0)]))

    assert output.loc[0, list(FEATURE_COLUMNS)].tolist() == [0, 0, 0, 0]


def test_second_match_uses_only_the_previous_match():
    output = add_venue_form_features(_matches([("A", "B", 2, 0), ("A", "B", 0, 1)]))

    assert output.loc[1, list(FEATURE_COLUMNS)].tolist() == [3, 0, 2, -2]


def test_home_history_excludes_past_away_matches():
    output = add_venue_form_features(_matches([
        ("B", "A", 0, 3),
        ("A", "C", 2, 1),
        ("D", "A", 0, 5),
        ("A", "E", 1, 1),
    ]))

    columns = ["home_last5_home_points", "home_last5_home_goal_diff"]
    assert output.loc[1, columns].tolist() == [0, 0]
    assert output.loc[3, columns].tolist() == [3, 1]


def test_away_history_excludes_past_home_matches():
    output = add_venue_form_features(_matches([
        ("A", "B", 4, 0),
        ("C", "A", 2, 1),
        ("A", "D", 3, 0),
        ("E", "A", 0, 1),
    ]))

    columns = ["away_last5_away_points", "away_last5_away_goal_diff"]
    assert output.loc[1, columns].tolist() == [0, 0]
    assert output.loc[3, columns].tolist() == [0, -1]


def test_uses_only_last_five_matches_at_each_venue():
    rows = []
    for home_score, away_score in [(9, 0), (0, 2), (1, 1), (3, 0), (0, 1), (2, 0)]:
        rows.extend([("A", "B", home_score, away_score), ("B", "A", 8, 0)])
    rows.append(("A", "B", 4, 4))

    output = add_venue_form_features(_matches(rows))

    assert output.loc[len(rows) - 1, list(FEATURE_COLUMNS)].tolist() == [7, 7, 2, -2]


def test_current_result_does_not_affect_its_own_features():
    matches = _matches([("A", "B", 1, 0), ("A", "B", 0, 0), ("A", "B", 2, 0)])
    changed = matches.copy(deep=True)
    changed.loc[1, ["home_score", "away_score", "result"]] = [0, 4, 0]

    original_output = add_venue_form_features(matches)
    changed_output = add_venue_form_features(changed)

    assert_frame_equal(original_output.loc[[1], list(FEATURE_COLUMNS)],
                       changed_output.loc[[1], list(FEATURE_COLUMNS)])
    assert original_output.loc[2, list(FEATURE_COLUMNS)].tolist() == [4, 1, 1, -1]
    assert changed_output.loc[2, list(FEATURE_COLUMNS)].tolist() == [3, 3, -3, 3]


def test_future_results_do_not_affect_past_features():
    matches = _matches([
        ("A", "B", 1, 0),
        ("B", "A", 2, 2),
        ("A", "B", 0, 1),
        ("B", "A", 3, 0),
        ("A", "B", 2, 0),
    ])
    changed = matches.copy(deep=True)
    changed.loc[3, ["home_score", "away_score", "result"]] = [0, 7, 0]
    changed.loc[4, ["home_score", "away_score", "result"]] = [0, 5, 0]

    original_output = add_venue_form_features(matches)
    changed_output = add_venue_form_features(changed)

    assert_frame_equal(original_output.loc[:2, list(FEATURE_COLUMNS)],
                       changed_output.loc[:2, list(FEATURE_COLUMNS)])


def test_returns_copy_preserving_input_columns_order_and_duplicate_index():
    matches = _matches([("A", "B", 2, 0), ("A", "B", 1, 1), ("A", "B", 0, 1)])
    matches["note"] = ["first", "second", "third"]
    matches.index = pd.Index([9, 2, 9], name="source_row")
    original = matches.copy(deep=True)

    output = add_venue_form_features(matches)

    assert output is not matches
    assert_frame_equal(matches, original)
    assert_frame_equal(output.loc[:, original.columns], original)
    assert output.columns.tolist() == original.columns.tolist() + list(FEATURE_COLUMNS)
    assert output.loc[:, list(FEATURE_COLUMNS)].values.tolist() == [
        [0, 0, 0, 0], [3, 0, 2, -2], [4, 1, 2, -2],
    ]
    assert all(output[column].dtype == "int64" for column in FEATURE_COLUMNS)


def test_same_input_produces_same_output():
    matches = _matches([("A", "B", 1, 0), ("B", "A", 1, 1), ("A", "B", 0, 2)])

    assert_frame_equal(add_venue_form_features(matches), add_venue_form_features(matches))


def test_rejects_score_result_conflict():
    matches = _matches([("A", "B", 2, 0)])
    matches.loc[0, "result"] = 0

    with pytest.raises(ValueError, match="result"):
        add_venue_form_features(matches)


def test_empty_input_returns_copy_with_integer_features():
    matches = _matches([])

    output = add_venue_form_features(matches)

    assert output is not matches
    assert output.empty
    assert_frame_equal(output.loc[:, matches.columns], matches)
    assert output.columns.tolist() == matches.columns.tolist() + list(FEATURE_COLUMNS)
    assert all(output[column].dtype == "int64" for column in FEATURE_COLUMNS)


def test_rejects_existing_output_column():
    matches = _matches([("A", "B", 2, 0)])
    matches[FEATURE_COLUMNS[0]] = 99

    with pytest.raises(ValueError, match="already exist"):
        add_venue_form_features(matches)
