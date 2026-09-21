from pathlib import Path

import pandas as pd
import pytest

from src.collect.teams import TeamAlias, TeamMaster, UnknownTeamError
from src.features.rolling_xg import (
    FEATURE_COLUMNS,
    RollingXGError,
    _validate_exact_reference,
    build_rolling_xg_features,
    rolling_xg_history_audit,
)


def _row(
    match_id, day, home, away, home_xg, away_xg, *,
    competition="j1_2025", season="2025", scope="REGULATION",
):
    return {
        "competition": competition, "season": season, "match_id": str(match_id),
        "match_date": day, "home_team_id": home, "away_team_id": away,
        "home_xg": str(home_xg), "away_xg": str(away_xg), "xg_time_scope": scope,
    }


def _six_for_a():
    return pd.DataFrame([
        _row("m1", "2025-01-01", "A", "B", 1, 2),
        _row("m2", "2025-01-02", "C", "A", 3, 4),
        _row("m3", "2025-01-03", "A", "D", 5, 6),
        _row("m4", "2025-01-04", "E", "A", 7, 8),
        _row("m5", "2025-01-05", "A", "F", 9, 10),
        _row("m6", "2025-01-06", "G", "A", 11, 12),
    ])


def test_team_perspective_and_home_away_roles_share_history():
    result = build_rolling_xg_features(_six_for_a()).set_index("match_id")
    target = result.loc["m6"]
    assert target.away_last5_xg_for == pytest.approx((1 + 4 + 5 + 8 + 9) / 5)
    assert target.away_last5_xg_against == pytest.approx((2 + 3 + 6 + 7 + 10) / 5)


def test_exactly_last_five_and_history_ids_are_recoverable():
    rows = _six_for_a().to_dict("records")
    rows.append(_row("m7", "2025-01-07", "A", "H", 13, 14))
    result = build_rolling_xg_features(pd.DataFrame(rows))
    target = result.set_index("match_id").loc["m7"]
    assert target.home_last5_xg_for == pytest.approx((4 + 5 + 8 + 9 + 12) / 5)
    audit = rolling_xg_history_audit(result).set_index("match_id")
    assert audit.loc["m7", "home_history_match_ids"] == ("m2", "m3", "m4", "m5", "m6")


def test_four_history_is_null_without_imputation():
    result = build_rolling_xg_features(_six_for_a().iloc[:5]).iloc[-1]
    assert result.home_xg_history_count == 4
    assert result.home_xg_available == False  # noqa: E712
    assert pd.isna(result.home_last5_xg_for) and pd.isna(result.home_last5_xg_against)


def test_five_history_is_available_mean():
    target = build_rolling_xg_features(_six_for_a()).set_index("match_id").loc["m6"]
    assert target.away_xg_history_count == 5
    assert target.away_xg_available == True  # noqa: E712
    assert pd.notna(target.away_last5_xg_for)


def test_competition_transition_continues_without_season_reset():
    rows = _six_for_a().iloc[:5].to_dict("records")
    rows.append(_row(
        "h1", "2026-02-01", "A", "G", 2, 1,
        competition="j1_hyakunen_2026", season="2026",
    ))
    rows.append(_row(
        "o1", "2026-08-01", "H", "A", 3, 2,
        competition="j1_2026_2027", season="2026/27",
    ))
    result = build_rolling_xg_features(pd.DataFrame(rows)).set_index("match_id")
    assert result.loc["h1", "home_xg_history_count"] == 5
    assert result.loc["o1", "away_xg_history_count"] == 5
    audit = rolling_xg_history_audit(build_rolling_xg_features(pd.DataFrame(rows))).set_index("match_id")
    assert audit.loc["o1", "away_history_match_ids"][-1] == "h1"


def test_same_date_is_one_batch_even_if_team_appears_twice():
    rows = _six_for_a().iloc[:5].to_dict("records")
    rows.extend([
        _row("same1", "2025-01-06", "A", "G", 20, 1),
        _row("same2", "2025-01-06", "H", "A", 2, 30),
    ])
    result = build_rolling_xg_features(pd.DataFrame(rows))
    audit = rolling_xg_history_audit(result).set_index("match_id")
    expected = ("m1", "m2", "m3", "m4", "m5")
    assert audit.loc["same1", "home_history_match_ids"] == expected
    assert audit.loc["same2", "away_history_match_ids"] == expected


def test_future_rows_do_not_change_earlier_features():
    base = _six_for_a()
    future = pd.concat([base, pd.DataFrame([_row("future", "2025-12-31", "A", "Z", 99, 99)])])
    left = build_rolling_xg_features(base)
    right = build_rolling_xg_features(future).iloc[:len(base)].reset_index(drop=True)
    left.attrs = {}; right.attrs = {}
    pd.testing.assert_frame_equal(left, right)


def test_unresolved_extra_time_target_remains_but_never_contributes():
    rows = _six_for_a().iloc[:5].to_dict("records")
    rows.extend([
        _row(
            "33017", "2026-06-06", "A", "G", 100, 100,
            competition="j1_hyakunen_2026", season="2026",
            scope="OFFICIAL_FINAL_SCOPE_UNRESOLVED",
        ),
        _row(
            "after", "2026-06-07", "H", "A", 2, 3,
            competition="j1_hyakunen_2026", season="2026",
        ),
    ])
    result = build_rolling_xg_features(pd.DataFrame(rows))
    by_id = result.set_index("match_id")
    assert "33017" in by_id.index
    assert by_id.loc["33017", "xg_history_excluded_source_match"] == True  # noqa: E712
    assert by_id.loc["after", "away_prior_xg_scope_exclusion_count"] == 1
    audit = rolling_xg_history_audit(result).set_index("match_id")
    assert "33017" not in audit.loc["after", "away_history_match_ids"]


def test_new_team_has_insufficient_history_and_pair_is_false():
    rows = _six_for_a().to_dict("records")
    rows.append(_row("new", "2025-01-07", "A", "NEW", 1, 1))
    row = build_rolling_xg_features(pd.DataFrame(rows)).set_index("match_id").loc["new"]
    assert row.home_xg_available == True  # noqa: E712
    assert row.away_xg_history_count == 0
    assert row.away_xg_available == False  # noqa: E712
    assert row.xg_pair_available == False  # noqa: E712
    assert pd.isna(row.away_last5_xg_for)


def test_pair_availability_requires_both_teams():
    rows = _six_for_a().to_dict("records")
    for index in range(5):
        rows.append(_row(f"z{index}", f"2025-02-0{index + 1}", "Z", f"Q{index}", 1, 1))
    rows.append(_row("pair", "2025-03-01", "A", "Z", 1, 1))
    row = build_rolling_xg_features(pd.DataFrame(rows)).set_index("match_id").loc["pair"]
    assert row.home_xg_available and row.away_xg_available and row.xg_pair_available


def test_output_has_only_frozen_numeric_feature_group():
    result = build_rolling_xg_features(_six_for_a())
    assert set(FEATURE_COLUMNS).issubset(result.columns)
    assert not any("shots" in column or "diff" in column for column in result.columns)


def test_duplicate_or_invalid_identity_is_rejected():
    duplicate = pd.concat([_six_for_a(), _six_for_a().iloc[[0]]], ignore_index=True)
    with pytest.raises(RollingXGError, match="Duplicate match_id"):
        build_rolling_xg_features(duplicate)
    invalid = _six_for_a(); invalid.loc[0, "away_team_id"] = "A"
    with pytest.raises(RollingXGError, match="Self-match"):
        build_rolling_xg_features(invalid)


def _master():
    return TeamMaster([
        TeamAlias("team_0001", "Alpha", "A", "jleague_data_site", None, None, "a"),
        TeamAlias("team_0002", "Beta", "B", "jleague_data_site", None, None, "b"),
    ])


def test_exact_match_identity_uses_team_master_without_fuzzy_matching():
    source = pd.DataFrame([_row("m", "2025-01-01", "team_0001", "team_0002", 1, 1)])
    reference = pd.DataFrame([{
        "match_id": "m", "match_date": "2025-01-01", "home_team": "A", "away_team": "B",
    }])
    _validate_exact_reference(source, reference, "j1_2025", _master())
    reference.loc[0, "home_team"] = "Alpha-ish"
    with pytest.raises(UnknownTeamError, match="Unknown team alias"):
        _validate_exact_reference(source, reference, "j1_2025", _master())


def test_identity_mismatch_is_fail_closed():
    source = pd.DataFrame([_row("m", "2025-01-01", "team_0002", "team_0001", 1, 1)])
    reference = pd.DataFrame([{
        "match_id": "m", "match_date": "2025-01-01", "home_team": "A", "away_team": "B",
    }])
    with pytest.raises(RollingXGError, match="Exact target identity mismatch"):
        _validate_exact_reference(source, reference, "j1_2025", _master())


def test_builder_does_not_mutate_input_and_is_deterministic():
    source = _six_for_a()
    original = source.copy(deep=True)
    first = build_rolling_xg_features(source.sample(frac=1, random_state=1))
    second = build_rolling_xg_features(source.sample(frac=1, random_state=2))
    pd.testing.assert_frame_equal(source, original)
    pd.testing.assert_frame_equal(first, second)


def test_no_model_dependency():
    source = Path("src/features/rolling_xg.py").read_text(encoding="utf-8")
    assert "src.modeling" not in source
    assert "sklearn" not in source
