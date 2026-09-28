import pandas as pd
import pytest

from src.features.substitution_timing import (
    EVENT_PATH,
    EVENT_SUMMARY_PATH,
    EXPECTED_PAIR_AVAILABLE,
    OUTPUT_COLUMNS,
    SOURCE_SHA256,
    SubstitutionTimingError,
    _availability_summary,
    _load_event_metadata,
    _normalize_matches,
    _source_audit,
    _validate_result,
    _validate_source_sha,
    build_substitution_timing_features,
    load_j1_matches,
    load_substitution_events,
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
    "source_section",
)


def matches(rows):
    return pd.DataFrame(rows, columns=MATCH_COLUMNS)


def substitution(
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
    event_type="SUBSTITUTION",
    source_section="A7",
):
    return (
        event_id,
        match_id,
        day,
        season,
        team_id,
        side,
        event_type,
        minute_raw,
        minute_normalized,
        order_half,
        order_base,
        order_added,
        source_section,
    )


def substitutions(rows=()):
    return pd.DataFrame(rows, columns=EVENT_COLUMNS)


def basic_matches():
    return matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
        ]
    )


def one_home_sub(minute=60, *, raw=None, order_half=1, order_added=0):
    return substitutions(
        [
            substitution(
                "e1",
                "m1",
                "2020-01-01",
                2020,
                "A",
                "home",
                raw or f"{minute}'",
                minute,
                order_half,
                minute,
                order_added,
            )
        ]
    )


def target_row(events):
    return build_substitution_timing_features(basic_matches(), events).set_index(
        "match_id"
    ).loc["m2"]


def test_01_first_target_has_zero_sum_null_mean_and_unavailable():
    result = build_substitution_timing_features(
        matches([("m1", "2020-01-01", 2020, "A", "B")]), substitutions()
    )
    assert tuple(result.columns) == OUTPUT_COLUMNS
    for side in ("home", "away"):
        assert result.loc[0, f"{side}_prior_substitution_events"] == 0
        assert result.loc[0, f"{side}_prior_substitution_minute_normalized_sum"] == 0
        assert pd.isna(
            result.loc[0, f"{side}_mean_substitution_minute_normalized_prior"]
        )
        assert not bool(result.loc[0, f"{side}_substitution_timing_available"])


def test_02_one_prior_sub_at_60_yields_one_60_and_available():
    row = target_row(one_home_sub())
    assert row.home_prior_substitution_events == 1
    assert row.home_prior_substitution_minute_normalized_sum == 60
    assert row.home_mean_substitution_minute_normalized_prior == 60
    assert bool(row.home_substitution_timing_available)


def test_03_60_70_80_have_event_weighted_mean_70():
    events = substitutions(
        [
            substitution(f"e{i}", "m1", "2020-01-01", 2020, "A", "home", f"{m}'", m, 1, m)
            for i, m in enumerate((60, 70, 80), start=1)
        ]
    )
    row = target_row(events)
    assert row.home_prior_substitution_events == 3
    assert row.home_prior_substitution_minute_normalized_sum == 210
    assert row.home_mean_substitution_minute_normalized_prior == 70


def test_04_multiple_subs_in_one_match_are_all_counted():
    events = substitutions(
        [
            substitution("e1", "m1", "2020-01-01", 2020, "A", "home", "50'", 50, 1, 50),
            substitution("e2", "m1", "2020-01-01", 2020, "A", "home", "75'", 75, 1, 75),
        ]
    )
    row = target_row(events)
    assert row.home_prior_substitution_events == 2
    assert row.home_prior_substitution_minute_normalized_sum == 125


def test_05_three_same_time_subs_at_60_remain_three_events():
    events = substitutions(
        [
            substitution(f"e{i}", "m1", "2020-01-01", 2020, "A", "home", "60'", 60, 1, 60)
            for i in range(3)
        ]
    )
    row = target_row(events)
    assert row.home_prior_substitution_events == 3
    assert row.home_prior_substitution_minute_normalized_sum == 180
    assert row.home_mean_substitution_minute_normalized_prior == 60


def test_06_prior_zero_sub_match_leaves_state_unchanged():
    row = target_row(substitutions())
    assert row.home_prior_substitution_events == 0
    assert row.home_prior_substitution_minute_normalized_sum == 0
    assert pd.isna(row.home_mean_substitution_minute_normalized_prior)
    assert not bool(row.home_substitution_timing_available)


def test_07_target_own_sub_is_excluded():
    target = matches([("m1", "2020-01-01", 2020, "A", "B")])
    row = build_substitution_timing_features(target, one_home_sub()).iloc[0]
    assert row.home_prior_substitution_events == 0


def test_08_same_date_peer_sub_is_excluded():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-01", 2020, "C", "A"),
        ]
    )
    row = build_substitution_timing_features(target, one_home_sub()).set_index(
        "match_id"
    ).loc["m2"]
    assert row.away_prior_substitution_events == 0


def test_09_prior_day_sub_is_usable():
    row = target_row(one_home_sub())
    assert row.home_prior_substitution_events == 1
    assert row.home_mean_substitution_minute_normalized_prior == 60


def test_10_season_boundary_resets_history():
    target = matches(
        [
            ("m1", "2020-12-01", 2020, "A", "B"),
            ("m2", "2021-03-01", 2021, "A", "C"),
        ]
    )
    events = substitutions(
        [
            substitution("e1", "m1", "2020-12-01", 2020, "A", "home", "60'", 60, 1, 60)
        ]
    )
    row = build_substitution_timing_features(target, events).set_index("match_id").loc["m2"]
    assert row.home_prior_substitution_events == 0
    assert pd.isna(row.home_mean_substitution_minute_normalized_prior)


def test_11_added_time_45_contributes_45():
    row = target_row(one_home_sub(45, raw="45'+3", order_half=0, order_added=3))
    assert row.home_mean_substitution_minute_normalized_prior == 45


def test_12_added_time_90_contributes_90():
    row = target_row(one_home_sub(90, raw="90'+5", order_half=1, order_added=5))
    assert row.home_mean_substitution_minute_normalized_prior == 90


def test_13_minute_46_contributes_46_and_is_not_excluded():
    row = target_row(one_home_sub(46, raw="46'", order_half=1))
    assert row.home_prior_substitution_events == 1
    assert row.home_mean_substitution_minute_normalized_prior == 46


def test_14_home_and_away_histories_are_independent():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "B"),
        ]
    )
    events = substitutions(
        [
            substitution("e1", "m1", "2020-01-01", 2020, "A", "home", "60'", 60, 1, 60),
            substitution("e2", "m1", "2020-01-01", 2020, "A", "home", "80'", 80, 1, 80),
            substitution("e3", "m1", "2020-01-01", 2020, "B", "away", "50'", 50, 1, 50),
        ]
    )
    row = build_substitution_timing_features(target, events).set_index("match_id").loc["m2"]
    assert row.home_prior_substitution_events == 2
    assert row.home_mean_substitution_minute_normalized_prior == 70
    assert row.away_prior_substitution_events == 1
    assert row.away_mean_substitution_minute_normalized_prior == 50


def test_15_rebuild_is_deterministic_and_inputs_are_not_mutated():
    target = basic_matches().iloc[::-1].reset_index(drop=True)
    events = substitutions(
        [
            substitution("e2", "m1", "2020-01-01", 2020, "A", "home", "80'", 80, 1, 80),
            substitution("e1", "m1", "2020-01-01", 2020, "A", "home", "60'", 60, 1, 60),
        ]
    )
    before_target = target.copy(deep=True)
    before_events = events.copy(deep=True)
    first = build_substitution_timing_features(target, events)
    second = build_substitution_timing_features(
        target.iloc[::-1].reset_index(drop=True),
        events.iloc[::-1].reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(first, second)
    assert first.to_csv(index=False, lineterminator="\n") == second.to_csv(
        index=False, lineterminator="\n"
    )
    pd.testing.assert_frame_equal(target, before_target)
    pd.testing.assert_frame_equal(events, before_events)


def test_16_team_side_identity_mismatch_hard_fails():
    bad = one_home_sub()
    bad.loc[0, "team_id"] = "X"
    with pytest.raises(SubstitutionTimingError, match="team/side identity"):
        build_substitution_timing_features(basic_matches(), bad)


def test_17_duplicate_sub_event_id_hard_fails():
    duplicate = substitutions(
        [
            substitution("e1", "m1", "2020-01-01", 2020, "A", "home", "60'", 60, 1, 60),
            substitution("e1", "m1", "2020-01-01", 2020, "A", "home", "70'", 70, 1, 70),
        ]
    )
    with pytest.raises(SubstitutionTimingError, match="Duplicate SUB"):
        build_substitution_timing_features(basic_matches(), duplicate)


def test_18_unresolved_minute_or_order_component_hard_fails():
    for field in (
        "minute_normalized",
        "minute_order_half",
        "minute_order_base",
        "minute_order_added",
    ):
        bad = one_home_sub()
        bad.loc[0, field] = None
        with pytest.raises(SubstitutionTimingError, match="Unresolved/noninteger"):
            build_substitution_timing_features(basic_matches(), bad)


def test_19_partial_state_inconsistency_hard_fails():
    target = basic_matches()
    result = build_substitution_timing_features(target, one_home_sub())
    broken = result.copy(deep=True)
    broken.loc[broken.match_id.eq("m2"), "home_prior_substitution_events"] = 0
    with pytest.raises(SubstitutionTimingError):
        _validate_result(
            broken,
            matches=_normalize_matches(target),
            observed_minute_min=3,
            observed_minute_max=90,
        )


def test_20_full_real_data_availability_matches_frozen_references():
    target = load_j1_matches()
    events = load_substitution_events()
    assert _source_audit(target, events) == {
        "target_rows": 3208,
        "total_normalized_event_rows": 39987,
        "normalized_substitution_rows": 23638,
        "substitution_covered_matches": 3208,
        "team_match_sides": 6416,
        "positive_substitution_sides": 6410,
        "zero_substitution_sides": 6,
        "observed_minute_min": 3,
        "observed_minute_max": 90,
    }
    result = build_substitution_timing_features(target, events)
    availability = _availability_summary(result)
    assert {
        int(season): values["pair_available"]
        for season, values in availability.items()
    } == EXPECTED_PAIR_AVAILABLE
    assert sum(row["pair_available"] for row in availability.values()) == 3116
    assert sum(
        row["home_available"] + row["away_available"]
        for row in availability.values()
    ) == 6232


def test_source_sha_and_raw_a7_metadata_reconciliation():
    assert _validate_source_sha(EVENT_PATH) == SOURCE_SHA256
    metadata = _load_event_metadata(EVENT_SUMMARY_PATH)
    assert metadata["raw_source_rows"]["A7"] == 47276
    assert metadata["event_types"]["SUBSTITUTION"]["rows"] == 23638


def test_invalid_event_type_and_source_section_hard_fail():
    wrong_type = one_home_sub()
    wrong_type.loc[0, "event_type"] = "GOAL"
    with pytest.raises(SubstitutionTimingError, match="SUBSTITUTION rows only"):
        build_substitution_timing_features(basic_matches(), wrong_type)
    wrong_section = one_home_sub()
    wrong_section.loc[0, "source_section"] = "A8"
    with pytest.raises(SubstitutionTimingError, match="must be A7"):
        build_substitution_timing_features(basic_matches(), wrong_section)


def test_duplicate_target_match_id_hard_fails():
    target = matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m1", "2020-01-02", 2020, "A", "C"),
        ]
    )
    with pytest.raises(SubstitutionTimingError, match="Duplicate target"):
        build_substitution_timing_features(target, substitutions())


def test_source_sha_mismatch_hard_fails(tmp_path):
    changed = tmp_path / "events.csv"
    changed.write_text("changed", encoding="utf-8")
    with pytest.raises(SubstitutionTimingError, match="SHA-256 mismatch"):
        _validate_source_sha(changed)
