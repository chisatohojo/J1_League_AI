import pandas as pd
import pytest

from src.features.first_score_profile import (
    OUTPUT_COLUMNS,
    FirstScoreProfileError,
    build_first_score_features,
    classify_first_score,
)


MATCH_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
)
EVENT_COLUMNS = (
    "event_id",
    "match_id",
    "match_date",
    "season",
    "team_id",
    "side",
    "event_type",
    "minute_raw",
    "minute_normalized",
    "minute_order_half",
    "minute_order_base",
    "minute_order_added",
    "normalization_flags",
)


def matches(rows):
    return pd.DataFrame(rows, columns=MATCH_COLUMNS)


def goals(rows=()):
    values = []
    for event_id, match_id, day, season, team_id, side, minute in rows:
        half = 0 if minute <= 45 else 1
        flag = "MINUTE_46_BOUNDARY_AMBIGUOUS" if minute == 46 else ""
        values.append(
            (
                event_id,
                match_id,
                day,
                season,
                team_id,
                side,
                "GOAL",
                f"{minute:02d}'",
                minute,
                half,
                minute,
                0,
                flag,
            )
        )
    return pd.DataFrame(values, columns=EVENT_COLUMNS)


def test_01_first_target_is_unavailable_with_null_rates():
    target = matches([("m1", "2020-01-01", 2020, "A", "B")])
    result = build_first_score_features(target, goals())
    assert tuple(result.columns) == OUTPUT_COLUMNS
    for side in ("home", "away"):
        assert not bool(result.loc[0, f"{side}_first_score_available"])
        assert result.loc[0, f"{side}_prior_first_score_eligible_matches"] == 0
        assert pd.isna(result.loc[0, f"{side}_scored_first_rate_prior"])
        assert pd.isna(result.loc[0, f"{side}_conceded_first_rate_prior"])
        assert pd.isna(result.loc[0, f"{side}_no_goal_rate_prior"])


def test_02_prior_scored_first_gives_one_zero_zero():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )
    result = build_first_score_features(
        target, goals([("e1", "m1", "2020-01-01", 2020, "A", "home", 10)])
    ).set_index("match_id")
    assert result.loc["m2", "home_scored_first_rate_prior"] == 1.0
    assert result.loc["m2", "home_conceded_first_rate_prior"] == 0.0
    assert result.loc["m2", "home_no_goal_rate_prior"] == 0.0


def test_03_prior_conceded_first_gives_zero_one_zero():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )
    result = build_first_score_features(
        target, goals([("e1", "m1", "2020-01-01", 2020, "B", "away", 10)])
    ).set_index("match_id")
    assert result.loc["m2", "home_scored_first_rate_prior"] == 0.0
    assert result.loc["m2", "home_conceded_first_rate_prior"] == 1.0
    assert result.loc["m2", "home_no_goal_rate_prior"] == 0.0


def test_04_prior_no_goal_gives_zero_zero_one():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )
    result = build_first_score_features(target, goals()).set_index("match_id")
    assert result.loc["m2", "home_scored_first_rate_prior"] == 0.0
    assert result.loc["m2", "home_conceded_first_rate_prior"] == 0.0
    assert result.loc["m2", "home_no_goal_rate_prior"] == 1.0


def test_05_mixed_three_observations_give_one_third_each():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "C", "A"),
            ("m3", "2020-01-03", 2020, "A", "D"),
            ("m4", "2020-01-04", 2020, "A", "E"),
        ]
    )
    event_rows = [
        ("e1", "m1", "2020-01-01", 2020, "A", "home", 10),
        ("e2", "m2", "2020-01-02", 2020, "C", "home", 20),
    ]
    row = build_first_score_features(target, goals(event_rows)).set_index("match_id").loc["m4"]
    assert row.home_prior_first_score_eligible_matches == 3
    assert row.home_scored_first_rate_prior == pytest.approx(1 / 3)
    assert row.home_conceded_first_rate_prior == pytest.approx(1 / 3)
    assert row.home_no_goal_rate_prior == pytest.approx(1 / 3)


def test_06_target_own_goal_is_not_used():
    target = matches([("m1", "2020-01-01", 2020, "A", "B")])
    event_rows = [("e1", "m1", "2020-01-01", 2020, "A", "home", 1)]
    row = build_first_score_features(target, goals(event_rows)).iloc[0]
    assert row.home_prior_first_score_eligible_matches == 0
    assert pd.isna(row.home_scored_first_rate_prior)


def test_07_same_date_peer_is_not_used():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-01", 2020, "C", "A"),
        ]
    )
    event_rows = [("e1", "m1", "2020-01-01", 2020, "A", "home", 5)]
    result = build_first_score_features(target, goals(event_rows)).set_index("match_id")
    assert result.loc["m2", "away_prior_first_score_eligible_matches"] == 0
    assert pd.isna(result.loc["m2", "away_scored_first_rate_prior"])


def test_08_prior_day_is_used_on_next_day():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-01", 2020, "C", "A"),
            ("m3", "2020-01-02", 2020, "A", "D"),
        ]
    )
    event_rows = [("e1", "m1", "2020-01-01", 2020, "A", "home", 5)]
    row = build_first_score_features(target, goals(event_rows)).set_index("match_id").loc["m3"]
    assert row.home_prior_first_score_eligible_matches == 2
    assert row.home_scored_first_rate_prior == 0.5
    assert row.home_no_goal_rate_prior == 0.5


def test_09_season_boundary_resets_history():
    target = matches(
        [
            ("m1", "2020-12-01", 2020, "A", "B"),
            ("m2", "2021-03-01", 2021, "A", "C"),
        ]
    )
    event_rows = [("e1", "m1", "2020-12-01", 2020, "A", "home", 5)]
    row = build_first_score_features(target, goals(event_rows)).set_index("match_id").loc["m2"]
    assert row.home_prior_first_score_eligible_matches == 0
    assert pd.isna(row.home_scored_first_rate_prior)


def test_10_not_checkable_target_exists_but_denominator_does_not_change():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )
    event_rows = [("e1", "m1", "2020-01-01", 2020, "A", "home", 5)]
    result = build_first_score_features(
        target, goals(event_rows), not_checkable_match_ids={"m1"}
    ).set_index("match_id")
    assert "m1" in result.index
    assert result.loc["m2", "home_prior_first_score_eligible_matches"] == 0


def test_11_cross_side_same_first_key_is_ambiguous_and_excluded():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )
    event_rows = [
        ("e1", "m1", "2020-01-01", 2020, "A", "home", 10),
        ("e2", "m1", "2020-01-01", 2020, "B", "away", 10),
    ]
    event_frame = goals(event_rows)
    classification = classify_first_score(target, event_frame).set_index("match_id")
    assert classification.loc["m1", "classification"] == "AMBIGUOUS_FIRST_SIDE"
    result = build_first_score_features(target, event_frame).set_index("match_id")
    assert result.loc["m2", "home_prior_first_score_eligible_matches"] == 0


def test_12_same_side_same_first_key_is_unique_and_eligible():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )
    event_rows = [
        ("e1", "m1", "2020-01-01", 2020, "A", "home", 10),
        ("e2", "m1", "2020-01-01", 2020, "A", "home", 10),
    ]
    event_frame = goals(event_rows)
    classification = classify_first_score(target, event_frame).set_index("match_id")
    assert classification.loc["m1", "classification"] == "SCORED_FIRST_HOME"
    result = build_first_score_features(target, event_frame).set_index("match_id")
    assert result.loc["m2", "home_scored_first_rate_prior"] == 1.0


def test_13_minute_46_first_goal_is_valid_for_first_side():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )
    event_frame = goals([("e1", "m1", "2020-01-01", 2020, "A", "home", 46)])
    classification = classify_first_score(target, event_frame).set_index("match_id")
    assert classification.loc["m1", "classification"] == "SCORED_FIRST_HOME"
    result = build_first_score_features(target, event_frame).set_index("match_id")
    assert result.loc["m2", "home_scored_first_rate_prior"] == 1.0


def test_14_deterministic_rebuild_and_inputs_not_mutated():
    target = matches(
        [
            ("m2", "2020-01-02", 2020, "B", "A"),
            ("m1", "2020-01-01", 2020, "A", "B"),
        ]
    )
    event_frame = goals(
        [
            ("e2", "m2", "2020-01-02", 2020, "A", "away", 20),
            ("e1", "m1", "2020-01-01", 2020, "A", "home", 10),
        ]
    )
    target_before = target.copy(deep=True)
    events_before = event_frame.copy(deep=True)
    first = build_first_score_features(target, event_frame)
    second = build_first_score_features(
        target.iloc[::-1].reset_index(drop=True),
        event_frame.iloc[::-1].reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(target, target_before)
    pd.testing.assert_frame_equal(event_frame, events_before)


def test_invalid_event_identity_and_duplicate_match_are_hard_failures():
    target = matches([("m1", "2020-01-01", 2020, "A", "B")])
    bad = goals([("e1", "m1", "2020-01-01", 2020, "X", "home", 10)])
    with pytest.raises(FirstScoreProfileError):
        build_first_score_features(target, bad)
    duplicate = pd.concat([target, target], ignore_index=True)
    with pytest.raises(FirstScoreProfileError):
        build_first_score_features(duplicate, goals())
