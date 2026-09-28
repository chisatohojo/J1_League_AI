import pandas as pd
import pytest

from src.features.goal_timing_profile import (
    EVENT_PATH,
    OUTPUT_COLUMNS,
    SOURCE_SHA256,
    GoalTimingProfileError,
    _normalize_matches,
    _validate_result,
    _validate_source_sha,
    build_goal_timing_features,
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


def goal(
    event_id,
    match_id,
    day,
    season,
    team_id,
    side,
    minute_raw,
    minute_normalized,
    order_half,
    order_base,
    order_added=0,
    flags="",
):
    return (
        event_id,
        match_id,
        day,
        season,
        team_id,
        side,
        "GOAL",
        minute_raw,
        minute_normalized,
        order_half,
        order_base,
        order_added,
        flags,
    )


def goals(rows=()):
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def basic_matches():
    return matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )


def one_home_goal(minute=10):
    return goals(
        [
            goal(
                "e1",
                "m1",
                "2020-01-01",
                2020,
                "A",
                "home",
                f"{minute:02d}'",
                minute,
                0 if minute <= 45 else 1,
                minute,
            )
        ]
    )


def test_01_first_target_has_zero_denominators_null_means_and_unavailable():
    result = build_goal_timing_features(
        matches([("m1", "2020-01-01", 2020, "A", "B")]), goals()
    )
    assert tuple(result.columns) == OUTPUT_COLUMNS
    for side in ("home", "away"):
        assert not bool(result.loc[0, f"{side}_goal_timing_available"])
        assert result.loc[0, f"{side}_prior_first_goal_timing_observations"] == 0
        assert result.loc[0, f"{side}_prior_scoring_goal_events"] == 0
        assert result.loc[0, f"{side}_prior_conceding_goal_events"] == 0
        assert pd.isna(
            result.loc[0, f"{side}_mean_first_goal_minute_normalized_prior"]
        )
        assert pd.isna(result.loc[0, f"{side}_mean_scoring_minute_normalized_prior"])
        assert pd.isna(
            result.loc[0, f"{side}_mean_conceding_minute_normalized_prior"]
        )


def test_02_prior_home_goal_maps_first_scoring_and_conceding_semantics():
    row = build_goal_timing_features(basic_matches(), one_home_goal()).set_index(
        "match_id"
    ).loc["m2"]
    assert row.home_mean_first_goal_minute_normalized_prior == 10
    assert row.home_mean_scoring_minute_normalized_prior == 10
    assert pd.isna(row.home_mean_conceding_minute_normalized_prior)
    assert row.away_team_id == "C"
    # B's perspective is checked on a target where B appears again.
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "B", "C"),
        ]
    )
    away = build_goal_timing_features(target, one_home_goal()).set_index("match_id").loc[
        "m2"
    ]
    assert away.home_mean_first_goal_minute_normalized_prior == 10
    assert pd.isna(away.home_mean_scoring_minute_normalized_prior)
    assert away.home_mean_conceding_minute_normalized_prior == 10


def test_03_prior_no_goal_changes_no_timing_denominator():
    row = build_goal_timing_features(basic_matches(), goals()).set_index("match_id").loc[
        "m2"
    ]
    assert row.home_prior_first_goal_timing_observations == 0
    assert row.home_prior_scoring_goal_events == 0
    assert row.home_prior_conceding_goal_events == 0


def test_04_multiple_goals_use_event_weighted_scoring_mean():
    event_rows = [
        goal(f"e{i}", "m1", "2020-01-01", 2020, "A", "home", f"{m}'", m, 0, m)
        for i, m in enumerate((10, 20, 30), start=1)
    ]
    row = build_goal_timing_features(basic_matches(), goals(event_rows)).set_index(
        "match_id"
    ).loc["m2"]
    assert row.home_prior_scoring_goal_events == 3
    assert row.home_prior_scoring_minute_normalized_sum == 60
    assert row.home_mean_scoring_minute_normalized_prior == 20


def test_05_multiple_goals_in_one_match_add_one_first_goal_observation():
    event_rows = [
        goal(f"e{i}", "m1", "2020-01-01", 2020, "A", "home", f"{m}'", m, 0, m)
        for i, m in enumerate((10, 20, 30), start=1)
    ]
    row = build_goal_timing_features(basic_matches(), goals(event_rows)).set_index(
        "match_id"
    ).loc["m2"]
    assert row.home_prior_first_goal_timing_observations == 1
    assert row.home_prior_first_goal_minute_normalized_sum == 10


def test_06_scoring_and_conceding_updates_are_symmetric():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "B"),
        ]
    )
    result = build_goal_timing_features(target, one_home_goal()).set_index("match_id")
    row = result.loc["m2"]
    assert row.home_prior_scoring_goal_events == row.away_prior_conceding_goal_events == 1
    assert (
        row.home_prior_scoring_minute_normalized_sum
        == row.away_prior_conceding_minute_normalized_sum
        == 10
    )


def test_07_target_own_goal_is_not_used():
    target = matches([("m1", "2020-01-01", 2020, "A", "B")])
    row = build_goal_timing_features(target, one_home_goal()).iloc[0]
    assert row.home_prior_first_goal_timing_observations == 0
    assert row.home_prior_scoring_goal_events == 0


def test_08_same_date_peer_is_not_used():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-01", 2020, "C", "A"),
        ]
    )
    row = build_goal_timing_features(target, one_home_goal()).set_index("match_id").loc[
        "m2"
    ]
    assert row.away_prior_first_goal_timing_observations == 0
    assert row.away_prior_scoring_goal_events == 0


def test_09_prior_day_is_used_on_next_date():
    row = build_goal_timing_features(basic_matches(), one_home_goal()).set_index(
        "match_id"
    ).loc["m2"]
    assert row.home_prior_first_goal_timing_observations == 1
    assert row.home_mean_first_goal_minute_normalized_prior == 10


def test_10_season_boundary_resets_history():
    target = matches(
        [
            ("m1", "2020-12-01", 2020, "A", "B"),
            ("m2", "2021-03-01", 2021, "A", "C"),
        ]
    )
    event_rows = goals(
        [goal("e1", "m1", "2020-12-01", 2020, "A", "home", "10'", 10, 0, 10)]
    )
    row = build_goal_timing_features(target, event_rows).set_index("match_id").loc["m2"]
    assert row.home_prior_first_goal_timing_observations == 0
    assert pd.isna(row.home_mean_scoring_minute_normalized_prior)


def test_11_not_checkable_equivalent_target_exists_but_history_is_unchanged():
    result = build_goal_timing_features(
        basic_matches(), one_home_goal(), excluded_match_ids={"m1"}
    ).set_index("match_id")
    assert "m1" in result.index
    assert result.loc["m2", "home_prior_first_goal_timing_observations"] == 0
    assert result.loc["m2", "home_prior_scoring_goal_events"] == 0


def test_12_added_time_45_uses_value_45_and_full_order_key():
    event_rows = goals(
        [
            goal("e1", "m1", "2020-01-01", 2020, "A", "home", "45'+2", 45, 0, 45, 2),
            goal("e2", "m1", "2020-01-01", 2020, "B", "away", "46'", 46, 1, 46),
        ]
    )
    row = build_goal_timing_features(basic_matches(), event_rows).set_index("match_id").loc[
        "m2"
    ]
    assert row.home_mean_first_goal_minute_normalized_prior == 45
    assert row.home_mean_scoring_minute_normalized_prior == 45


def test_13_added_time_90_uses_value_90():
    event_rows = goals(
        [goal("e1", "m1", "2020-01-01", 2020, "A", "home", "90'+4", 90, 1, 90, 4)]
    )
    row = build_goal_timing_features(basic_matches(), event_rows).set_index("match_id").loc[
        "m2"
    ]
    assert row.home_mean_first_goal_minute_normalized_prior == 90
    assert row.home_mean_scoring_minute_normalized_prior == 90


def test_14_minute_46_is_value_46_and_not_excluded():
    event_rows = goals(
        [
            goal(
                "e1",
                "m1",
                "2020-01-01",
                2020,
                "A",
                "home",
                "46'",
                46,
                1,
                46,
                flags="MINUTE_46_BOUNDARY_AMBIGUOUS",
            )
        ]
    )
    row = build_goal_timing_features(basic_matches(), event_rows).set_index("match_id").loc[
        "m2"
    ]
    assert row.home_mean_first_goal_minute_normalized_prior == 46
    assert row.home_mean_scoring_minute_normalized_prior == 46


def test_15_cross_side_same_minimum_key_adds_one_first_goal_observation():
    event_rows = goals(
        [
            goal("e1", "m1", "2020-01-01", 2020, "A", "home", "10'", 10, 0, 10),
            goal("e2", "m1", "2020-01-01", 2020, "B", "away", "10'", 10, 0, 10),
        ]
    )
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "B"),
        ]
    )
    row = build_goal_timing_features(target, event_rows).set_index("match_id").loc["m2"]
    assert row.home_prior_first_goal_timing_observations == 1
    assert row.away_prior_first_goal_timing_observations == 1
    assert row.home_prior_scoring_goal_events == 1
    assert row.away_prior_scoring_goal_events == 1


def test_16_same_side_duplicate_minimum_adds_one_first_goal_observation():
    event_rows = goals(
        [
            goal("e1", "m1", "2020-01-01", 2020, "A", "home", "10'", 10, 0, 10),
            goal("e2", "m1", "2020-01-01", 2020, "A", "home", "10'", 10, 0, 10),
        ]
    )
    row = build_goal_timing_features(basic_matches(), event_rows).set_index("match_id").loc[
        "m2"
    ]
    assert row.home_prior_first_goal_timing_observations == 1
    assert row.home_prior_scoring_goal_events == 2


def test_17_rebuild_is_deterministic_and_inputs_are_not_mutated():
    target = basic_matches().iloc[::-1].reset_index(drop=True)
    event_rows = goals(
        [
            goal("e2", "m1", "2020-01-01", 2020, "A", "home", "20'", 20, 0, 20),
            goal("e1", "m1", "2020-01-01", 2020, "A", "home", "10'", 10, 0, 10),
        ]
    )
    before_target = target.copy(deep=True)
    before_events = event_rows.copy(deep=True)
    first = build_goal_timing_features(target, event_rows)
    second = build_goal_timing_features(
        target.iloc[::-1].reset_index(drop=True),
        event_rows.iloc[::-1].reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(first, second)
    assert first.to_csv(index=False, lineterminator="\n") == second.to_csv(
        index=False, lineterminator="\n"
    )
    pd.testing.assert_frame_equal(target, before_target)
    pd.testing.assert_frame_equal(event_rows, before_events)


def test_18_team_side_identity_mismatch_is_a_hard_failure():
    bad = goals(
        [goal("e1", "m1", "2020-01-01", 2020, "X", "home", "10'", 10, 0, 10)]
    )
    with pytest.raises(GoalTimingProfileError, match="team/side identity"):
        build_goal_timing_features(basic_matches(), bad)


def test_19_partial_denominator_mean_state_is_a_hard_failure():
    target = basic_matches()
    result = build_goal_timing_features(target, one_home_goal())
    broken = result.copy(deep=True)
    row = broken.match_id.eq("m2")
    broken.loc[row, "home_prior_scoring_goal_events"] = 0
    with pytest.raises(GoalTimingProfileError):
        _validate_result(
            broken,
            matches=_normalize_matches(target),
            observed_minute_max=10,
        )


def test_source_sha_matches_and_mismatch_is_rejected(tmp_path):
    assert _validate_source_sha(EVENT_PATH) == SOURCE_SHA256
    altered = tmp_path / "events.csv"
    altered.write_text("changed", encoding="utf-8")
    with pytest.raises(GoalTimingProfileError, match="SHA-256 mismatch"):
        _validate_source_sha(altered)


def test_duplicate_event_and_inconsistent_minimum_minute_are_rejected():
    duplicate = goals(
        [
            goal("e1", "m1", "2020-01-01", 2020, "A", "home", "10'", 10, 0, 10),
            goal("e1", "m1", "2020-01-01", 2020, "A", "home", "20'", 20, 0, 20),
        ]
    )
    with pytest.raises(GoalTimingProfileError, match="Duplicate GOAL"):
        build_goal_timing_features(basic_matches(), duplicate)
    inconsistent = goals(
        [
            goal("e1", "m1", "2020-01-01", 2020, "A", "home", "10'", 10, 0, 10),
            goal("e2", "m1", "2020-01-01", 2020, "B", "away", "11'", 11, 0, 10),
        ]
    )
    with pytest.raises(GoalTimingProfileError, match="inconsistent normalized"):
        build_goal_timing_features(basic_matches(), inconsistent)
