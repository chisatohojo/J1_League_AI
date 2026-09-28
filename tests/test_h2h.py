from __future__ import annotations

import hashlib
from pathlib import Path
import re

import pandas as pd
from pandas.api.types import is_integer_dtype
import pytest

from src.collect.teams import load_team_master
from src.features import h2h


def _matches(*rows) -> pd.DataFrame:
    records = []
    for match_id, match_date, home, away, result, *season in rows:
        records.append(
            {
                "match_id": match_id,
                "match_date": match_date,
                "season": season[0] if season else int(match_date[:4]),
                "home_team_id": home,
                "away_team_id": away,
                "result": result,
            }
        )
    return pd.DataFrame(records, columns=h2h.REQUIRED_INPUT_COLUMNS)


@pytest.fixture(scope="module")
def production() -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = h2h.load_j1_matches()
    return matches, h2h.build_h2h_features(matches)


def test_01_exact_pair_is_unordered() -> None:
    assert h2h._pair_key("team_0002", "team_0001") == (
        "team_0001",
        "team_0002",
    )
    assert h2h._pair_key("team_0001", "team_0002") == (
        "team_0001",
        "team_0002",
    )


def test_02_team_master_ids_only(production) -> None:
    matches, features = production
    master_ids = {alias.team_id for alias in load_team_master().aliases}
    observed = set(matches.home_team_id) | set(matches.away_team_id)
    assert observed <= master_ids
    assert all(re.fullmatch(r"team_[0-9]{4,}", value) for value in observed)
    assert features.home_team_id.tolist() == (
        matches.sort_values(["match_date", "match_id"]).home_team_id.tolist()
    )


def test_03_target_own_result_is_excluded() -> None:
    result = h2h.build_h2h_features(
        _matches(("m1", "2015-03-01", "A", "B", 2))
    ).iloc[0]
    assert result.prior_h2h_match_count == 0
    assert result.prior_h2h_home_team_win_count == 0


def test_04_same_date_results_are_excluded() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("m2", "2015-03-01", "C", "D", 0),
            ("m1", "2015-03-01", "A", "B", 2),
            ("m3", "2015-03-08", "A", "B", 1),
            ("m4", "2015-03-08", "C", "D", 1),
        )
    ).set_index("match_id")
    assert result.loc[["m1", "m2"], "prior_h2h_match_count"].eq(0).all()
    assert result.loc[["m3", "m4"], "prior_h2h_match_count"].eq(1).all()


def test_05_only_strictly_prior_history_is_used() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("past", "2015-03-01", "A", "B", 2),
            ("target", "2015-03-08", "B", "A", 0),
            ("future", "2015-03-15", "A", "B", 1),
        )
    ).set_index("match_id")
    assert result.loc["target", "prior_h2h_match_count"] == 1
    assert result.loc["target", "previous_h2h_match_id"] == "past"


def test_06_pair_state_carries_across_seasons() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("old", "2015-12-01", "A", "B", 2),
            ("new", "2016-02-01", "B", "A", 1),
        )
    ).set_index("match_id")
    assert result.loc["new", "prior_h2h_match_count"] == 1
    assert result.loc["new", "previous_h2h_match_id"] == "old"


def test_07_2015_left_edge_starts_empty() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("first-a", "2015-03-01", "A", "B", 2),
            ("first-b", "2015-03-01", "C", "D", 1),
        )
    )
    assert result.prior_h2h_match_count.eq(0).all()
    assert ~result.h2h_available.any()


def test_08_no_pre_2015_history_is_inferred() -> None:
    result = h2h.build_h2h_features(
        _matches(("first-scoped", "2015-12-01", "A", "B", 0))
    ).iloc[0]
    assert result.prior_h2h_match_count == 0
    assert pd.isna(result.previous_h2h_match_id)


def test_09_same_orientation_win_is_reoriented_to_target_home() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("old", "2015-03-01", "A", "B", 2),
            ("target", "2015-03-08", "A", "B", 1),
        )
    ).set_index("match_id")
    assert result.loc["target", "prior_h2h_home_team_win_count"] == 1


def test_10_reverse_orientation_win_is_reoriented_to_target_home() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("old", "2015-03-01", "A", "B", 0),
            ("target", "2015-03-08", "B", "A", 1),
        )
    ).set_index("match_id")
    assert result.loc["target", "prior_h2h_home_team_win_count"] == 1


def test_11_draw_count_is_orientation_invariant() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("old", "2015-03-01", "A", "B", 1),
            ("target", "2015-03-08", "B", "A", 2),
        )
    ).set_index("match_id")
    assert result.loc["target", "prior_h2h_draw_count"] == 1


def test_12_latest_previous_h2h_is_exact() -> None:
    result = h2h.build_h2h_features(
        _matches(
            ("old-1", "2015-03-01", "A", "B", 2),
            ("old-2", "2015-03-08", "B", "A", 0),
            ("target", "2015-03-15", "A", "B", 1),
        )
    ).set_index("match_id")
    assert result.loc["target", "previous_h2h_match_id"] == "old-2"
    assert result.loc["target", "previous_h2h_match_date"] == "2015-03-08"


def test_13_no_history_has_structural_zeros() -> None:
    row = h2h.build_h2h_features(
        _matches(("m1", "2015-03-01", "A", "B", 1))
    ).iloc[0]
    assert [row[column] for column in h2h.MODEL_CANDIDATES] == [0, 0, 0]
    assert not row.h2h_available


def test_14_no_history_audit_fields_are_null() -> None:
    row = h2h.build_h2h_features(
        _matches(("m1", "2015-03-01", "A", "B", 1))
    ).iloc[0]
    assert pd.isna(row.previous_h2h_match_id)
    assert pd.isna(row.previous_h2h_match_date)


def test_15_available_history_audit_fields_are_non_null() -> None:
    row = h2h.build_h2h_features(
        _matches(
            ("old", "2015-03-01", "A", "B", 1),
            ("target", "2015-03-08", "A", "B", 2),
        )
    ).set_index("match_id").loc["target"]
    assert row.h2h_available
    assert row.previous_h2h_match_id == "old"
    assert row.previous_h2h_match_date < row.match_date


def test_16_home_wins_plus_draws_do_not_exceed_total(production) -> None:
    _, features = production
    assert (
        features.prior_h2h_home_team_win_count
        + features.prior_h2h_draw_count
        <= features.prior_h2h_match_count
    ).all()


def test_17_derived_away_wins_are_nonnegative(production) -> None:
    _, features = production
    derived = (
        features.prior_h2h_match_count
        - features.prior_h2h_home_team_win_count
        - features.prior_h2h_draw_count
    )
    assert is_integer_dtype(derived.dtype)
    assert derived.ge(0).all()


def test_18_candidates_are_integer_and_non_null(production) -> None:
    _, features = production
    for column in h2h.MODEL_CANDIDATES:
        assert is_integer_dtype(features[column].dtype)
        assert features[column].notna().all()
        assert features[column].ge(0).all()


def test_19_output_has_exact_11_column_schema(production) -> None:
    _, features = production
    assert tuple(features.columns) == h2h.OUTPUT_COLUMNS
    assert len(features.columns) == 11


def test_20_output_has_exactly_3208_rows(production) -> None:
    _, features = production
    assert len(features) == 3208


def test_21_output_has_exactly_3208_unique_match_ids(production) -> None:
    _, features = production
    assert features.match_id.nunique() == 3208


def test_22_frozen_season_counts_are_exact(production) -> None:
    _, features = production
    assert features.groupby("season").size().to_dict() == h2h.EXPECTED_SEASON_COUNTS


def test_23_frozen_season_availability_is_exact(production) -> None:
    _, features = production
    summary = h2h.availability_summary(features, frozen=True)
    assert {
        int(season): (values["available"], values["unavailable"])
        for season, values in summary.items()
    } == h2h.EXPECTED_AVAILABILITY


def test_24_global_availability_is_exactly_2832_and_376(production) -> None:
    _, features = production
    assert int(features.h2h_available.sum()) == 2832
    assert int((~features.h2h_available).sum()) == 376


def test_25_frozen_prior_count_bins_are_exact(production) -> None:
    _, features = production
    assert h2h.prior_count_bins(features, frozen=True) == h2h.EXPECTED_PRIOR_COUNT_BINS


def test_26_input_row_order_does_not_change_output() -> None:
    matches = _matches(
        ("m3", "2016-03-01", "A", "B", 1),
        ("m1", "2015-03-01", "A", "B", 2),
        ("m2", "2015-03-01", "C", "D", 0),
        ("m4", "2016-03-01", "D", "C", 2),
    )
    expected = h2h.build_h2h_features(matches)
    actual = h2h.build_h2h_features(matches.iloc[::-1].reset_index(drop=True))
    pd.testing.assert_frame_equal(actual, expected)


def test_27_rebuild_serialization_is_byte_identical_and_write_safe(tmp_path: Path) -> None:
    matches = _matches(
        ("m2", "2016-03-01", "B", "A", 1),
        ("m1", "2015-03-01", "A", "B", 2),
    )
    first = h2h.build_h2h_features(matches)
    second = h2h.build_h2h_features(matches.copy(deep=True))
    first_bytes = h2h._csv_bytes(first)
    assert first_bytes == h2h._csv_bytes(second)
    assert b"\r\n" not in first_bytes
    output = tmp_path / "h2h.csv"
    digest = h2h._write_once(first, output)
    assert output.read_bytes() == first_bytes
    assert digest == hashlib.sha256(first_bytes).hexdigest()
    with pytest.raises(h2h.H2HError, match="refusing overwrite"):
        h2h._write_once(first, output)


def test_28_duplicate_match_id_hard_fails() -> None:
    matches = _matches(
        ("duplicate", "2015-03-01", "A", "B", 2),
        ("duplicate", "2015-03-08", "C", "D", 1),
    )
    with pytest.raises(h2h.H2HError, match="Duplicate target match_id"):
        h2h.build_h2h_features(matches)


def test_29_same_team_twice_on_one_date_hard_fails() -> None:
    matches = _matches(
        ("m1", "2015-03-01", "A", "B", 2),
        ("m2", "2015-03-01", "A", "C", 1),
    )
    with pytest.raises(h2h.H2HError, match="Team appears twice"):
        h2h.build_h2h_features(matches)


def test_30_model_candidate_family_is_exactly_the_three_frozen_columns() -> None:
    assert h2h.MODEL_CANDIDATES == (
        "prior_h2h_match_count",
        "prior_h2h_home_team_win_count",
        "prior_h2h_draw_count",
    )

