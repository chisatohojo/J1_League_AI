"""Frozen previous-match A5 starter DF feature tests; no model evaluation."""

from __future__ import annotations

from collections import Counter
import hashlib

import pandas as pd
import pytest

from src.features.starter_df import (
    A5_FIELDS,
    EXPECTED_CURRENT_DF,
    EXPECTED_POSITION_TOTALS,
    EXPECTED_PREVIOUS_DF,
    OUTPUT_COLUMNS,
    StarterDFError,
    _csv_bytes,
    _parse_a5,
    _validate_raw_metadata,
    _validate_result,
    _write_once,
    availability_summary,
    build_starter_df_features,
    load_j1_matches,
    load_validated_a5,
    previous_df_distribution,
)


def _matches(rows):
    return pd.DataFrame(
        rows,
        columns=[
            "match_id",
            "match_date",
            "season",
            "home_team_id",
            "away_team_id",
        ],
    )


def _counts(rows):
    return pd.DataFrame(
        rows,
        columns=["match_id", "home_starter_df_count", "away_starter_df_count"],
    )


def _chronology_fixture():
    matches = _matches(
        [
            ("m1", "2020-01-01", 2020, "A", "B"),
            ("m2", "2020-01-02", 2020, "A", "C"),
            ("m3", "2020-01-02", 2020, "D", "E"),
            ("m4", "2020-01-03", 2020, "C", "A"),
            ("m5", "2021-01-01", 2021, "A", "B"),
            ("m6", "2021-01-02", 2021, "B", "A"),
        ]
    )
    counts = _counts(
        [
            ("m1", 4, 3),
            ("m2", 5, 4),
            ("m3", 2, 6),
            ("m4", 3, 4),
            ("m5", 3, 5),
            ("m6", 4, 6),
        ]
    )
    return matches, counts


def _row(position, number, name, time="", *, fields=A5_FIELDS):
    values = {"position": position, "number": number, "name": name, "time": time}
    return "<tr>" + "".join(
        f'<td class="{field}">{values.get(field, "x")}</td>' for field in fields
    ) + "</tr>"


def _side(prefix, *, df=4, gk=1, duplicate_name=False, time="", fields=A5_FIELDS):
    positions = ["GK"] * gk + ["DF"] * df
    remaining = 11 - len(positions)
    positions += ["MF"] * max(0, remaining - 2) + ["FW"] * min(2, remaining)
    positions = positions[:11]
    rows = []
    for index, position in enumerate(positions):
        name = f"{prefix}-{index}"
        if duplicate_name and index == 10:
            name = f"{prefix}-0"
        rows.append(_row(position, str(index + 1), name, time, fields=fields))
    return "".join(rows)


def _html(home=None, away=None, *, sections=None):
    home = _side("H") if home is None else home
    away = _side("A") if away is None else away
    fragments = [home, away] if sections is None else sections
    a5 = "".join(
        f"<!-- A5 Start --><table>{fragment}</table><!-- A5 End -->"
        for fragment in fragments
    )
    return (a5 + "<!-- A6 Start --><!-- A6 End -->").encode("utf-8")


def _metadata(raw, match_id="123"):
    url = f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}"
    return {
        "requested_url": url,
        "final_url": url,
        "status": 200,
        "match_id": match_id,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@pytest.fixture(scope="module")
def real_data():
    matches = load_j1_matches()
    counts, audit = load_validated_a5(matches)
    result = build_starter_df_features(matches, counts)
    return matches, counts, audit, result


def test_01_first_current_season_target_is_unavailable_and_null():
    matches, counts = _chronology_fixture()
    row = build_starter_df_features(matches, counts).set_index("match_id").loc["m1"]
    assert row.home_starter_df_available is False or not row.home_starter_df_available
    assert row.away_starter_df_available is False or not row.away_starter_df_available
    for side in ("home", "away"):
        assert pd.isna(row[f"{side}_previous_match_id"])
        assert pd.isna(row[f"{side}_previous_match_date"])
        assert pd.isna(row[f"{side}_previous_match_starter_df_count"])


def test_02_prior_gk1_df4_mf4_fw2_yields_next_df4():
    counts, totals = _parse_a5(_html(), match_id="123")
    assert counts == (4, 4)
    assert totals == Counter({"MF": 8, "DF": 8, "FW": 4, "GK": 2})
    matches = _matches(
        [("a", "2020-01-01", 2020, "A", "B"), ("b", "2020-01-02", 2020, "A", "C")]
    )
    result = build_starter_df_features(matches, _counts([("a", 4, 4), ("b", 3, 3)]))
    assert result.set_index("match_id").loc["b", "home_previous_match_starter_df_count"] == 4


def test_03_prior_df3_yields_next_df3():
    home = _side("H", df=3)
    assert _parse_a5(_html(home=home), match_id="123")[0][0] == 3
    matches = _matches(
        [("a", "2020-01-01", 2020, "A", "B"), ("b", "2020-01-02", 2020, "A", "C")]
    )
    row = build_starter_df_features(matches, _counts([("a", 3, 4), ("b", 4, 4)])).iloc[1]
    assert row.home_previous_match_starter_df_count == 3


def test_04_latest_replaces_older_and_is_not_mean():
    matches, counts = _chronology_fixture()
    row = build_starter_df_features(matches, counts).set_index("match_id").loc["m4"]
    assert row.away_previous_match_id == "m2"
    assert row.away_previous_match_starter_df_count == 5
    assert row.away_previous_match_starter_df_count != 4


def test_05_target_own_a5_is_excluded():
    matches, counts = _chronology_fixture()
    baseline = build_starter_df_features(matches, counts).set_index("match_id")
    changed = counts.copy(deep=True)
    changed.loc[changed.match_id == "m2", "home_starter_df_count"] = 6
    alternate = build_starter_df_features(matches, changed).set_index("match_id")
    assert baseline.loc["m2", "home_previous_match_starter_df_count"] == 4
    assert alternate.loc["m2", "home_previous_match_starter_df_count"] == 4


def test_06_same_date_peer_a5_is_excluded():
    matches, counts = _chronology_fixture()
    baseline = build_starter_df_features(matches, counts).set_index("match_id")
    changed = counts.copy(deep=True)
    changed.loc[changed.match_id == "m3", ["home_starter_df_count", "away_starter_df_count"]] = [6, 2]
    alternate = build_starter_df_features(matches, changed).set_index("match_id")
    pd.testing.assert_series_equal(baseline.loc["m2"], alternate.loc["m2"])


def test_07_prior_day_a5_is_usable():
    matches, counts = _chronology_fixture()
    row = build_starter_df_features(matches, counts).set_index("match_id").loc["m2"]
    assert row.home_starter_df_available
    assert row.home_previous_match_date == "2020-01-01"
    assert row.home_previous_match_starter_df_count == 4


def test_08_season_boundary_resets_state():
    matches, counts = _chronology_fixture()
    row = build_starter_df_features(matches, counts).set_index("match_id").loc["m5"]
    assert not row.home_starter_df_available
    assert not row.away_starter_df_available
    assert pd.isna(row.home_previous_match_starter_df_count)


def test_09_home_and_away_histories_are_independent():
    matches, counts = _chronology_fixture()
    row = build_starter_df_features(matches, counts).set_index("match_id").loc["m6"]
    assert row.home_previous_match_id == "m5"
    assert row.home_previous_match_starter_df_count == 5
    assert row.away_previous_match_id == "m5"
    assert row.away_previous_match_starter_df_count == 3


def test_10_player_names_never_participate_in_cross_match_identity():
    first = _parse_a5(_html(), match_id="123")[0]
    renamed = _html(home=_side("Renamed"), away=_side("Other"))
    second = _parse_a5(renamed, match_id="123")[0]
    assert first == second == (4, 4)
    assert set(_counts([("m", 4, 4)]).columns) == {
        "match_id",
        "home_starter_df_count",
        "away_starter_df_count",
    }


def test_11_a5_side_not_11_rows_hard_fails():
    short = "".join(_row("GK" if i == 0 else "DF", str(i + 1), f"H-{i}") for i in range(10))
    with pytest.raises(StarterDFError, match="exactly 11"):
        _parse_a5(_html(home=short), match_id="123")


@pytest.mark.parametrize("position", ["", "CB"])
def test_12_blank_or_invalid_position_hard_fails(position):
    home = _row(position, "1", "H-0") + "".join(
        _row("DF" if i < 4 else "MF", str(i + 2), f"H-{i + 1}") for i in range(10)
    )
    with pytest.raises(StarterDFError, match="Invalid A5 position"):
        _parse_a5(_html(home=home), match_id="123")


def test_13_gk_count_other_than_one_hard_fails():
    with pytest.raises(StarterDFError, match="exactly one GK"):
        _parse_a5(_html(home=_side("H", gk=0, df=4)), match_id="123")


@pytest.mark.parametrize(
    "fields",
    [
        ("number", "position", "name", "time"),
        ("position", "name", "time"),
        ("position", "number", "name", "time", "extra"),
    ],
)
def test_14_nonexact_row_shape_hard_fails(fields):
    with pytest.raises(StarterDFError, match="row shape mismatch"):
        _parse_a5(_html(home=_side("H", fields=fields)), match_id="123")


def test_15_nonempty_a5_time_hard_fails():
    with pytest.raises(StarterDFError, match="Nonempty A5 time"):
        _parse_a5(_html(home=_side("H", time="10'")), match_id="123")


def test_16_duplicate_exact_name_within_team_match_hard_fails():
    with pytest.raises(StarterDFError, match="Duplicate exact A5 player name"):
        _parse_a5(_html(home=_side("H", duplicate_name=True)), match_id="123")


@pytest.mark.parametrize("section_count", [1, 3])
def test_17_missing_or_duplicate_a5_side_section_hard_fails(section_count):
    sections = [_side(f"S{i}") for i in range(section_count)]
    with pytest.raises(StarterDFError, match="exactly two A5"):
        _parse_a5(_html(sections=sections), match_id="123")


def test_18_metadata_sha_url_status_bytes_and_match_id_mismatch_hard_fail():
    raw = _html()
    valid = _metadata(raw)
    _validate_raw_metadata(raw, valid, "123")
    mutations = {
        "requested_url": "https://invalid.example/",
        "final_url": "https://invalid.example/",
        "status": 500,
        "match_id": "999",
        "bytes": len(raw) + 1,
        "sha256": "0" * 64,
    }
    for field, value in mutations.items():
        broken = dict(valid)
        broken[field] = value
        with pytest.raises(StarterDFError, match="Raw metadata mismatch"):
            _validate_raw_metadata(raw, broken, "123")


def test_19_duplicate_target_match_id_hard_fails():
    matches = _matches(
        [("m", "2020-01-01", 2020, "A", "B"), ("m", "2020-01-02", 2020, "A", "C")]
    )
    with pytest.raises(StarterDFError, match="Duplicate target match_id"):
        build_starter_df_features(matches, _counts([("m", 4, 4)]))


def test_20_same_team_twice_on_one_date_hard_fails():
    matches = _matches(
        [("a", "2020-01-01", 2020, "A", "B"), ("b", "2020-01-01", 2020, "A", "C")]
    )
    with pytest.raises(StarterDFError, match="Team appears twice"):
        build_starter_df_features(matches, _counts([("a", 4, 4), ("b", 4, 4)]))


def test_21_available_state_must_be_exact_latest_strictly_prior_same_season():
    matches, counts = _chronology_fixture()
    result = build_starter_df_features(matches, counts)
    broken = result.copy(deep=True)
    broken.loc[broken.match_id == "m4", "away_previous_match_id"] = "m1"
    with pytest.raises(StarterDFError, match="exact latest previous"):
        _validate_result(broken, matches=matches, current_counts=counts)


def test_22_unavailable_state_requires_all_audit_fields_null():
    matches, counts = _chronology_fixture()
    result = build_starter_df_features(matches, counts)
    broken = result.copy(deep=True)
    broken.loc[broken.match_id == "m1", "home_previous_match_id"] = "fabricated"
    with pytest.raises(StarterDFError, match="non-null audit state"):
        _validate_result(broken, matches=matches, current_counts=counts)


def test_23_frozen_season_side_and_pair_availability_reproduced(real_data):
    _, _, _, result = real_data
    summary = availability_summary(result, frozen=True)
    assert sum(row["side_available"] for row in summary.values()) == 6232
    assert sum(row["side_unavailable"] for row in summary.values()) == 184
    assert sum(row["pair_available"] for row in summary.values()) == 3116
    assert sum(row["pair_unavailable"] for row in summary.values()) == 92
    assert sum(row["home_only_available"] for row in summary.values()) == 0
    assert sum(row["away_only_available"] for row in summary.values()) == 0
    assert sum(row["both_unavailable"] for row in summary.values()) == 92


def test_24_frozen_season_and_global_previous_df_distributions_reproduced(real_data):
    _, _, _, result = real_data
    summary = previous_df_distribution(result, frozen=True)
    assert summary["by_season"] == {
        str(year): values for year, values in EXPECTED_PREVIOUS_DF.items()
    }
    assert summary["global"] == {2: 18, 3: 1869, 4: 4124, 5: 212, 6: 9}


def test_25_deterministic_rebuild_has_same_rows_values_order_and_bytes(real_data):
    matches, counts, _, result = real_data
    rebuilt = build_starter_df_features(
        matches.iloc[::-1].reset_index(drop=True),
        counts.iloc[::-1].reset_index(drop=True),
    )
    pd.testing.assert_frame_equal(result, rebuilt)
    assert _csv_bytes(result) == _csv_bytes(rebuilt)


def test_full_raw_source_audit_and_exact_output_schema(real_data):
    _, _, audit, result = real_data
    assert audit["matches"] == 3208
    assert audit["team_match_sides"] == 6416
    assert audit["a5_side_sections"] == 6416
    assert audit["a5_rows"] == 70576
    assert audit["position_totals"] == dict(sorted(EXPECTED_POSITION_TOTALS.items()))
    assert audit["current_source_df_distribution"] == dict(
        sorted(EXPECTED_CURRENT_DF.items())
    )
    assert audit["metadata_failures"] == 0
    assert audit["row_shape_failures"] == 0
    assert tuple(result.columns) == OUTPUT_COLUMNS
    assert len(result) == result.match_id.nunique() == 3208


def test_atomic_write_refuses_overwrite_and_preserves_bytes(tmp_path):
    matches, counts = _chronology_fixture()
    result = build_starter_df_features(matches, counts)
    output = tmp_path / "starter_df.csv"
    digest = _write_once(result, output)
    assert output.read_bytes() == _csv_bytes(result)
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    with pytest.raises(StarterDFError, match="already exists"):
        _write_once(result, output)
