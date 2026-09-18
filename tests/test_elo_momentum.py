import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS, add_elo_momentum_features


FEATURES = [
    "home_elo_change_last5",
    "away_elo_change_last5",
    "elo_change_last5_diff",
    "home_elo_change_last5_matches",
    "away_elo_change_last5_matches",
]


def _matches(rows):
    frame = pd.DataFrame(
        rows, columns=["home_team_id", "away_team_id", "home_elo", "away_elo"]
    )
    frame["match_date"] = pd.date_range("2025-01-01", periods=len(frame))
    return frame


def _features(frame, position):
    return frame[FEATURES].iloc[position].tolist()


def test_first_appearances_have_zero_changes_and_counts():
    result = add_elo_momentum_features(_matches([("A", "B", 1673.5, 1421)]))

    assert tuple(ELO_MOMENTUM_COLUMNS) == tuple(FEATURES)
    assert _features(result, 0) == [0.0, 0.0, 0.0, 0, 0]
    assert result[FEATURES].dtypes.astype(str).tolist() == ["float64"] * 3 + ["int64"] * 2


def test_second_match_subtracts_the_first_pre_match_ratings():
    result = add_elo_momentum_features(
        _matches([("A", "B", 1500, 1470), ("A", "B", 1517.5, 1463)])
    )

    assert _features(result, 1) == [17.5, -7.0, 24.5, 1, 1]


@pytest.mark.parametrize("home,away", [("A", "B"), ("B", "A")])
def test_history_follows_both_home_to_away_and_away_to_home_switches(home, away):
    result = add_elo_momentum_features(
        _matches([(home, away, 1550, 1400), (away, home, 1412, 1530)])
    )

    assert _features(result, 1) == [12.0, -20.0, 32.0, 1, 1]


def test_fewer_than_five_prior_matches_use_the_oldest_available_rating():
    result = add_elo_momentum_features(
        _matches([
            ("A", "B", 1500, 1400),
            ("A", "B", 1530, 1420),
            ("A", "B", 1490, 1440),
            ("A", "B", 1520, 1415),
        ])
    )

    assert result[FEATURES[3:]].values.tolist() == [[0, 0], [1, 1], [2, 2], [3, 3]]
    assert _features(result, 3) == [20.0, 15.0, 5.0, 3, 3]


def test_seventh_appearance_evicts_only_the_first_prior_rating():
    ratings = [(1000, 2000), (1200, 1900), (1250, 1850), (1300, 1800),
               (1400, 1750), (1500, 1700), (1600, 1650)]
    result = add_elo_momentum_features(_matches([("A", "B", *pair) for pair in ratings]))

    assert _features(result, 5) == [500.0, -300.0, 800.0, 5, 5]
    assert _features(result, 6) == [400.0, -250.0, 650.0, 5, 5]


def test_positive_negative_and_zero_changes_keep_home_minus_away_sign():
    result = add_elo_momentum_features(
        _matches([
            ("A", "B", 1500, 1500),
            ("A", "B", 1480, 1530),
            ("A", "B", 1500, 1500),
        ])
    )

    assert _features(result, 1) == [-20.0, 30.0, -50.0, 1, 1]
    assert _features(result, 2) == [0.0, 0.0, 0.0, 2, 2]


def test_current_ratings_are_not_appended_before_features_are_computed():
    result = add_elo_momentum_features(
        _matches([("A", "B", 1200, 1800), ("A", "C", 1700, 900)])
    )

    assert _features(result, 1) == [500.0, 0.0, 500.0, 1, 0]


@pytest.mark.parametrize(
    "next_match,expected",
    [
        (("A", "C", 1520, 1600), [20.0, 0.0, 20.0, 1, 0]),
        (("C", "A", 1600, 1520), [0.0, 20.0, -20.0, 0, 1]),
    ],
)
def test_first_appearance_of_one_team_does_not_zero_the_difference(next_match, expected):
    result = add_elo_momentum_features(_matches([("A", "B", 1500, 1500), next_match]))

    assert _features(result, 1) == expected


def test_future_elo_changes_do_not_affect_past_features():
    matches = _matches([
        ("A", "B", 1500, 1500), ("B", "A", 1490, 1510),
        ("A", "B", 1520, 1480), ("B", "A", 1470, 1530),
    ])
    changed = matches.copy(deep=True)
    changed.loc[2:, ["home_elo", "away_elo"]] = [[2100, 1100], [1000, 2200]]

    original_result = add_elo_momentum_features(matches)
    changed_result = add_elo_momentum_features(changed)

    assert_frame_equal(original_result[FEATURES].iloc[:2], changed_result[FEATURES].iloc[:2])
    assert not original_result[FEATURES].iloc[2:].equals(changed_result[FEATURES].iloc[2:])


def test_only_five_required_columns_are_needed_without_results_or_scores():
    matches = _matches([("A", "B", 1333, 1777), ("A", "B", 1444, 1888)])

    result = add_elo_momentum_features(matches)

    assert len(matches.columns) == 5
    assert _features(result, 1) == [111.0, 111.0, 0.0, 1, 1]


def test_invalid_unused_results_scores_and_competition_fields_are_ignored():
    matches = _matches([("A", "B", 1500, 1500), ("B", "A", 1510, 1470)])
    poisoned = matches.assign(
        result=["invalid", None], home_score=[-100, float("inf")],
        away_score=["invalid", None], elo_diff=[99999, -99999],
        season=[None, "invalid"], competition=["unknown", None],
    )

    expected = add_elo_momentum_features(matches)
    result = add_elo_momentum_features(poisoned)

    assert_frame_equal(result[FEATURES], expected[FEATURES])
    assert_frame_equal(result[poisoned.columns], poisoned)


def test_history_continues_across_seasons_and_competitions():
    matches = _matches([("A", "B", 1500, 1500), ("B", "A", 1460, 1540)])
    matches["match_date"] = pd.to_datetime(["2025-12-01", "2026-02-01"])
    matches["season"] = [2025, 2026]
    matches["competition"] = ["ordinary", "special"]

    result = add_elo_momentum_features(matches)

    assert _features(result, 1) == [-40.0, 40.0, -80.0, 1, 1]


def test_preserves_input_columns_dtypes_order_and_duplicate_indices_without_mutation():
    matches = _matches([("A", "B", 1500, 1400), ("B", "A", 1410, 1490)])
    matches["home_team_id"] = matches["home_team_id"].astype("string")
    matches["away_team_id"] = matches["away_team_id"].astype("string")
    matches["home_elo"] = matches["home_elo"].astype("Float64")
    matches["away_elo"] = matches["away_elo"].astype("Int64")
    matches["nullable"] = pd.Series([pd.NA, 7], dtype="Int64")
    matches["category"] = pd.Categorical(["cup", "league"])
    matches.index = pd.Index([9, 9], name="source_row")
    original = matches.copy(deep=True)

    result = add_elo_momentum_features(matches)

    assert result is not matches
    assert_frame_equal(matches, original)
    assert_frame_equal(result[original.columns], original)
    assert list(result.columns) == list(original.columns) + FEATURES
    assert _features(result, 1) == [10.0, -10.0, 20.0, 1, 1]
    result.iloc[0, result.columns.get_loc("home_elo")] = 9999
    assert_frame_equal(matches, original)


def test_repeated_calls_are_deterministic_and_start_with_empty_history():
    matches = _matches([("A", "B", 1500, 1500), ("B", "A", 1490, 1510)])

    first = add_elo_momentum_features(matches)
    second = add_elo_momentum_features(matches)
    isolated = add_elo_momentum_features(matches.iloc[[1]])

    assert_frame_equal(first, second)
    assert _features(isolated, 0) == [0.0, 0.0, 0.0, 0, 0]


def test_empty_valid_input_preserves_schema_and_adds_typed_features():
    matches = _matches([]).astype({"home_team_id": "string", "away_team_id": "string",
                                  "home_elo": "Float64", "away_elo": "Float64"})
    matches.index = pd.Index([], dtype="int64", name="source_row")

    result = add_elo_momentum_features(matches)

    assert_frame_equal(result[matches.columns], matches)
    assert list(result.columns) == list(matches.columns) + FEATURES
    assert result[FEATURES].dtypes.astype(str).tolist() == ["float64"] * 3 + ["int64"] * 2


@pytest.mark.parametrize(
    "column,bad_rating",
    [("home_elo", float("nan")), ("away_elo", float("inf")),
     ("home_elo", float("-inf")), ("away_elo", True),
     ("home_elo", "1500"), ("away_elo", 1500 + 0j), ("home_elo", pd.NA)],
)
def test_invalid_ratings_are_rejected(column, bad_rating):
    matches = _matches([("A", "B", 1500, 1500)])
    matches[column] = pd.Series([bad_rating], dtype=object)

    with pytest.raises(ValueError):
        add_elo_momentum_features(matches)


def test_unsorted_dates_are_rejected_without_reordering_input():
    matches = _matches([("A", "B", 1500, 1500), ("A", "B", 1510, 1490)]).iloc[::-1]
    original = matches.copy(deep=True)

    with pytest.raises(ValueError):
        add_elo_momentum_features(matches)
    assert_frame_equal(matches, original)


def test_missing_date_is_rejected():
    matches = _matches([("A", "B", 1500, 1500)])
    matches["match_date"] = pd.NaT

    with pytest.raises(ValueError):
        add_elo_momentum_features(matches)


def test_repeated_team_on_same_calendar_day_is_rejected_across_roles():
    matches = _matches([("A", "B", 1500, 1500), ("C", "A", 1500, 1510)])
    matches["match_date"] = pd.to_datetime(["2025-01-01 12:00", "2025-01-01 19:00"])

    with pytest.raises(ValueError):
        add_elo_momentum_features(matches)


def test_independent_teams_can_play_on_the_same_day():
    matches = _matches([("A", "B", 1500, 1500), ("C", "D", 1510, 1490)])
    matches["match_date"] = pd.Timestamp("2025-01-01")

    result = add_elo_momentum_features(matches)

    assert result[FEATURES].eq(0).all().all()


def test_self_play_is_rejected():
    with pytest.raises(ValueError):
        add_elo_momentum_features(_matches([("A", "A", 1500, 1500)]))


@pytest.mark.parametrize("bad_id", ["", " ", None, 7])
def test_team_ids_must_be_nonempty_strings(bad_id):
    with pytest.raises(ValueError):
        add_elo_momentum_features(_matches([("A", bad_id, 1500, 1500)]))


def test_missing_required_column_is_rejected():
    matches = _matches([("A", "B", 1500, 1500)]).drop(columns="away_elo")

    with pytest.raises(ValueError):
        add_elo_momentum_features(matches)


def test_existing_output_column_is_rejected():
    matches = _matches([("A", "B", 1500, 1500)])
    matches[FEATURES[0]] = 999

    with pytest.raises(ValueError):
        add_elo_momentum_features(matches)


def test_duplicate_input_columns_are_rejected():
    matches = _matches([("A", "B", 1500, 1500)])
    matches = pd.concat([matches, matches[["home_elo"]]], axis=1)

    with pytest.raises(ValueError):
        add_elo_momentum_features(matches)


def test_non_dataframe_input_is_rejected():
    with pytest.raises(TypeError):
        add_elo_momentum_features([])
