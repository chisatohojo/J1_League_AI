"""Synthetic checks for gaps between recorded, pre-match club appearances."""

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS, add_schedule_gap_features


REQUIRED = ("match_date", "home_team_id", "away_team_id")
EXPECTED_COLUMNS = (
    "home_days_since_last_match", "away_days_since_last_match",
    "days_since_last_match_diff", "home_has_previous_match", "away_has_previous_match",
)


def matches(*rows):
    return pd.DataFrame(rows, columns=REQUIRED)


def features(frame):
    return add_schedule_gap_features(frame).loc[:, list(EXPECTED_COLUMNS)]


def test_initial_appearances_are_zero_and_columns_are_in_contract_order():
    source = matches(("2024-01-01", "A", "B"), ("2024-01-02", "C", "D"))
    result = add_schedule_gap_features(source)
    assert tuple(SCHEDULE_GAP_COLUMNS) == EXPECTED_COLUMNS
    assert tuple(result.columns) == REQUIRED + EXPECTED_COLUMNS
    assert result.loc[:, list(EXPECTED_COLUMNS)].values.tolist() == [[0] * 5, [0] * 5]
    assert all(pd.api.types.is_integer_dtype(result[column]) for column in EXPECTED_COLUMNS)


def test_second_appearance_has_positive_gap_and_both_previous_flags():
    source = matches(("2024-01-01", "A", "B"), ("2024-01-08", "A", "B"))
    assert features(source).iloc[1].tolist() == [7, 7, 0, 1, 1]


def test_history_follows_both_clubs_when_home_and_away_switch():
    source = matches(("2024-01-01", "A", "B"), ("2024-01-08", "B", "A"))
    assert features(source).iloc[1].tolist() == [7, 7, 0, 1, 1]


@pytest.mark.parametrize("home,away,expected", [
    ("B", "C", [7, 5, 2, 1, 1]),
    ("C", "B", [5, 7, -2, 1, 1]),
])
def test_difference_is_signed_home_minus_away(home, away, expected):
    source = matches(
        ("2024-01-01", "A", "B"), ("2024-01-03", "C", "D"),
        ("2024-01-08", home, away),
    )
    assert features(source).iloc[2].tolist() == expected


@pytest.mark.parametrize("home,away,expected", [
    ("A", "C", [7, 0, 0, 1, 0]),
    ("C", "B", [0, 7, 0, 0, 1]),
])
def test_difference_is_zero_when_either_club_has_no_recorded_history(home, away, expected):
    source = matches(("2024-01-01", "A", "B"), ("2024-01-08", home, away))
    assert features(source).iloc[1].tolist() == expected


def test_cross_season_gap_is_uncapped_and_counts_leap_day():
    source = matches(("2019-12-31", "A", "B"), ("2021-01-01", "B", "A"))
    source["season"] = [2019, 2021]
    source["competition"] = ["first", "second"]
    assert features(source).iloc[1].tolist() == [367, 367, 0, 1, 1]


def test_current_match_is_excluded_and_only_latest_recorded_appearance_counts():
    source = matches(
        ("2024-01-01", "A", "B"), ("2024-01-03", "B", "A"),
        ("2024-01-08", "A", "B"),
    )
    assert features(source).values.tolist() == [[0, 0, 0, 0, 0], [2, 2, 0, 1, 1], [5, 5, 0, 1, 1]]


def test_changing_or_adding_future_dates_cannot_affect_past_features():
    source = matches(
        ("2024-01-01", "A", "B"), ("2024-01-03", "B", "C"),
        ("2024-01-08", "A", "C"),
    )
    changed = source.copy(deep=True)
    changed.loc[2, "match_date"] = "2025-08-01"
    assert_frame_equal(features(source).iloc[:2], features(changed).iloc[:2])
    assert_frame_equal(features(source).iloc[:2], features(source.iloc[:2]))


def test_gap_counts_calendar_dates_instead_of_elapsed_24_hour_periods():
    source = matches(
        ("2024-02-28 23:00:00", "A", "B"),
        ("2024-02-29 01:00:00", "B", "A"),
    )
    assert features(source).iloc[1].tolist() == [1, 1, 0, 1, 1]


@pytest.mark.parametrize("dates", [
    ("2024-01-02", "2024-01-01"),
    ("2024-01-01 20:00:00", "2024-01-01 10:00:00"),
])
def test_reversed_chronology_is_rejected_even_for_different_clubs(dates):
    with pytest.raises(ValueError):
        add_schedule_gap_features(matches((dates[0], "A", "B"), (dates[1], "C", "D")))


@pytest.mark.parametrize("home,away", [("A", "C"), ("C", "A"), ("B", "C"), ("C", "B")])
@pytest.mark.parametrize("later_time", ["10:00:00", "22:00:00"])
def test_repeated_club_on_same_calendar_date_is_rejected_in_either_role(home, away, later_time):
    source = matches(
        ("2024-01-01 10:00:00", "A", "B"),
        (f"2024-01-01 {later_time}", home, away),
    )
    with pytest.raises(ValueError):
        add_schedule_gap_features(source)


def test_disjoint_clubs_can_play_on_the_same_date():
    source = matches(("2024-01-01", "A", "B"), ("2024-01-01", "C", "D"))
    assert features(source).values.tolist() == [[0] * 5, [0] * 5]


def test_same_home_and_away_team_is_rejected():
    with pytest.raises(ValueError):
        add_schedule_gap_features(matches(("2024-01-01", "A", "A")))


def test_source_values_dtypes_column_order_and_duplicate_custom_index_are_preserved():
    source = matches(("2024-01-01", "A", "B"), ("2024-01-08", "B", "A"))
    source["match_date"] = source["match_date"].astype("string")
    source["home_team_id"] = source["home_team_id"].astype("category")
    source["away_team_id"] = source["away_team_id"].astype("string")
    source["season"] = pd.array([2024, None], dtype="Int64")
    source["source_score"] = pd.array([None, 2.5], dtype="Float64")
    source = source.loc[:, ["season", "away_team_id", "match_date", "source_score", "home_team_id"]]
    source.index = pd.Index([19, 19], name="source_row")
    before = source.copy(deep=True)
    result = add_schedule_gap_features(source)
    assert result is not source
    assert tuple(result.columns) == tuple(source.columns) + EXPECTED_COLUMNS
    assert_frame_equal(result.loc[:, source.columns], before)
    assert_frame_equal(source, before)
    assert result.loc[:, list(EXPECTED_COLUMNS)].values.tolist() == [[0] * 5, [7, 7, 0, 1, 1]]
    result.iloc[0, result.columns.get_loc("season")] = 1999
    assert_frame_equal(source, before)


def test_calls_are_deterministic_and_do_not_share_history():
    source = matches(("2024-01-01", "A", "B"), ("2024-01-08", "B", "A"))
    expected = add_schedule_gap_features(source)
    add_schedule_gap_features(matches(("2030-01-01", "A", "B")))
    assert_frame_equal(add_schedule_gap_features(source), expected)


def test_scores_results_elo_form_and_other_unused_columns_are_ignored():
    source = matches(("2024-01-01", "A", "B"), ("2024-01-08", "B", "A"))
    expected = features(source)
    for column in ("home_score", "away_score", "result", "home_elo", "away_elo", "elo_diff",
                   "home_last5_points", "away_last5_points", "stadium", "season", "completed"):
        source[column] = [object(), None]
    assert_frame_equal(features(source), expected)


@pytest.mark.parametrize("column", REQUIRED)
def test_missing_required_column_is_rejected(column):
    source = matches(("2024-01-01", "A", "B"))
    with pytest.raises(ValueError):
        add_schedule_gap_features(source.drop(columns=column))


def test_duplicate_input_columns_are_rejected():
    source = matches(("2024-01-01", "A", "B"))
    source = pd.concat([source, source[["home_team_id"]]], axis=1)
    with pytest.raises(ValueError):
        add_schedule_gap_features(source)


@pytest.mark.parametrize("column", EXPECTED_COLUMNS)
def test_existing_feature_column_is_rejected(column):
    source = matches(("2024-01-01", "A", "B"))
    source[column] = 0
    with pytest.raises(ValueError):
        add_schedule_gap_features(source)


@pytest.mark.parametrize("date", [None, pd.NaT, "", "not-a-date"])
def test_missing_or_invalid_date_is_rejected(date):
    with pytest.raises(ValueError):
        add_schedule_gap_features(matches((date, "A", "B")))


@pytest.mark.parametrize("column", ["home_team_id", "away_team_id"])
@pytest.mark.parametrize("team_id", ["", "  ", None, pd.NA, 42])
def test_team_ids_must_be_nonempty_strings(column, team_id):
    source = matches(("2024-01-01", "A", "B"))
    source[column] = pd.Series([team_id], dtype=object)
    with pytest.raises(ValueError):
        add_schedule_gap_features(source)


def test_empty_valid_input_preserves_schema_and_adds_five_integer_columns():
    source = pd.DataFrame({
        "match_date": pd.Series(dtype="datetime64[ns]"),
        "home_team_id": pd.Series(dtype="string"),
        "away_team_id": pd.Series(dtype="string"),
    }, index=pd.Index([], dtype="int64", name="source_row"))
    result = add_schedule_gap_features(source)
    assert result.empty
    assert tuple(result.columns) == REQUIRED + EXPECTED_COLUMNS
    assert_frame_equal(result.loc[:, list(REQUIRED)], source)
    assert all(pd.api.types.is_integer_dtype(result[column]) for column in EXPECTED_COLUMNS)


def test_non_dataframe_input_is_rejected():
    with pytest.raises(TypeError):
        add_schedule_gap_features([])
