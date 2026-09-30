from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal
import pytest

from src.features import draw_propensity as draw
from src.features.form import add_form_features


VALID_IDS = frozenset(chr(code) for code in range(ord("A"), ord("Z") + 1))


def _matches(*rows) -> pd.DataFrame:
    records = []
    for number, (match_id, match_date, home, away, home_score, away_score) in enumerate(rows, 1):
        season = int(match_date[:4])
        if season in (2015, 2016):
            competition, stage = "Ｊ１ １ｓｔ", "1st"
        else:
            competition, stage = "Ｊ１", "full_season"
        records.append(
            {
                "match_id": match_id,
                "season": season,
                "round": number,
                "match_date": match_date,
                "home_team": home,
                "away_team": away,
                "stadium": "S",
                "home_score": home_score,
                "away_score": away_score,
                "result": 2 if home_score > away_score else 0 if home_score < away_score else 1,
                "competition": competition,
                "stage": stage,
                "home_team_id": home,
                "away_team_id": away,
            }
        )
    return pd.DataFrame(records, columns=draw.REQUIRED_INPUT_COLUMNS)


def _build(*rows) -> pd.DataFrame:
    return draw.build_draw_propensity_features(
        _matches(*rows), valid_team_ids=VALID_IDS
    )


@pytest.fixture(scope="module")
def production() -> tuple[pd.DataFrame, pd.DataFrame]:
    matches = draw.load_j1_matches()
    return matches, draw.build_draw_propensity_features(matches)


def test_01_exact_source_scope(production) -> None:
    matches, _ = production
    assert set(matches.season) == set(range(2015, 2025))
    assert set(matches.competition) <= {"Ｊ１", "Ｊ１ １ｓｔ", "Ｊ１ ２ｎｄ"}


def test_02_exact_targets_and_team_sides(production) -> None:
    matches, result = production
    assert len(matches) == len(result) == 3208
    assert 2 * len(result) == 6416
    assert result.match_id.nunique() == 3208


def test_03_exact_season_counts(production) -> None:
    _, result = production
    assert result.groupby("season").size().to_dict() == draw.EXPECTED_SEASON_COUNTS


def test_04_duplicate_match_id_rejected() -> None:
    matches = _matches(
        ("same", "2017-03-01", "A", "B", 1, 0),
        ("same", "2017-03-02", "C", "D", 0, 0),
    )
    with pytest.raises(draw.DrawPropensityError, match="Duplicate match_id"):
        draw.build_draw_propensity_features(matches, valid_team_ids=VALID_IDS)


def test_05_team_identity_validation() -> None:
    matches = _matches(("m1", "2017-03-01", "A", "B", 1, 0))
    matches.loc[0, "away_team_id"] = "UNKNOWN"
    with pytest.raises(draw.DrawPropensityError, match="Unknown TeamMaster ID"):
        draw.build_draw_propensity_features(matches, valid_team_ids=VALID_IDS)


def test_06_invalid_result_rejected() -> None:
    matches = _matches(("m1", "2017-03-01", "A", "B", 1, 0))
    matches.loc[0, "result"] = 3
    with pytest.raises(draw.DrawPropensityError, match="result must be"):
        draw.build_draw_propensity_features(matches, valid_team_ids=VALID_IDS)


def test_07_result_score_inconsistency_rejected() -> None:
    matches = _matches(("m1", "2017-03-01", "A", "B", 1, 0))
    matches.loc[0, "result"] = 0
    with pytest.raises(draw.DrawPropensityError, match="contradicts"):
        draw.build_draw_propensity_features(matches, valid_team_ids=VALID_IDS)


def test_08_same_team_match_rejected() -> None:
    matches = _matches(("m1", "2017-03-01", "A", "B", 0, 0))
    matches.loc[0, ["away_team", "away_team_id"]] = "A"
    with pytest.raises(draw.DrawPropensityError, match="must differ"):
        draw.build_draw_propensity_features(matches, valid_team_ids=VALID_IDS)


def test_09_same_team_twice_same_date_rejected() -> None:
    matches = _matches(
        ("m1", "2017-03-01", "A", "B", 1, 0),
        ("m2", "2017-03-01", "A", "C", 0, 0),
    )
    with pytest.raises(draw.DrawPropensityError, match="appears twice"):
        draw.build_draw_propensity_features(matches, valid_team_ids=VALID_IDS)


def test_10_target_result_unavailable_before_emit() -> None:
    draw_target = _build(("m1", "2017-03-01", "A", "B", 0, 0)).iloc[0]
    win_target = _build(("m1", "2017-03-01", "A", "B", 1, 0)).iloc[0]
    assert_series_equal(draw_target, win_target)
    assert draw_target.home_season_prior_matches == 0


def test_11_same_date_peer_unavailable_before_emit() -> None:
    result = _build(
        ("m1", "2017-03-01", "A", "B", 0, 0),
        ("m2", "2017-03-01", "C", "D", 2, 0),
        ("m3", "2017-03-08", "A", "C", 1, 0),
    ).set_index("match_id")
    assert result.loc[["m1", "m2"], "home_season_prior_matches"].eq(0).all()
    assert result.loc[["m1", "m2"], "home_last5_matches"].eq(0).all()
    assert result.loc["m3", "home_season_prior_draws"] == 1
    assert result.loc["m3", "away_season_prior_draws"] == 0


def test_12_season_state_reset() -> None:
    result = _build(
        ("old", "2019-12-01", "A", "B", 0, 0),
        ("new", "2020-02-01", "A", "C", 1, 0),
    ).set_index("match_id")
    assert result.loc["new", "home_season_prior_matches"] == 0
    assert pd.isna(result.loc["new", "home_season_prior_draw_rate"])


def test_13_last_five_cross_season_continuation() -> None:
    result = _build(
        ("old", "2019-12-01", "A", "B", 0, 0),
        ("new", "2020-02-01", "A", "C", 1, 0),
    ).set_index("match_id")
    assert result.loc["new", "home_last5_matches"] == 1
    assert result.loc["new", "home_last5_draws"] == 1


def test_14_2015_left_edge_cold_start() -> None:
    row = _build(("first", "2015-03-01", "A", "B", 0, 0)).iloc[0]
    assert row.home_last5_matches == row.away_last5_matches == 0
    assert pd.isna(row.home_last5_draw_rate)
    assert pd.isna(row.away_last5_draw_rate)


def test_15_returning_club_history_continuation() -> None:
    result = _build(
        ("old", "2017-03-01", "A", "B", 0, 0),
        ("gap", "2018-03-01", "C", "D", 1, 0),
        ("return", "2019-03-01", "A", "E", 2, 0),
    ).set_index("match_id")
    assert result.loc["return", "home_last5_matches"] == 1
    assert result.loc["return", "home_last5_draws"] == 1


@pytest.mark.parametrize("competition", ["Ｊ２", "J.League Cup"])
def test_16_j2_and_cup_not_included(competition) -> None:
    matches = _matches(("m1", "2017-03-01", "A", "B", 1, 0))
    matches.loc[0, "competition"] = competition
    with pytest.raises(draw.DrawPropensityError, match="Non-ordinary-J1"):
        draw.build_draw_propensity_features(matches, valid_team_ids=VALID_IDS)


def test_17_current_season_zero_history_semantics() -> None:
    row = _build(("m1", "2017-03-01", "A", "B", 1, 0)).iloc[0]
    assert (row.home_season_prior_draws, row.home_season_prior_matches) == (0, 0)
    assert pd.isna(row.home_season_prior_draw_rate)


def test_18_last_five_zero_history_semantics() -> None:
    row = _build(("m1", "2017-03-01", "A", "B", 1, 0)).iloc[0]
    assert (row.away_last5_draws, row.away_last5_matches) == (0, 0)
    assert pd.isna(row.away_last5_draw_rate)


def test_19_exact_last_five_max_denominator() -> None:
    rows = [
        (f"m{index}", f"2017-03-{index:02d}", "A", chr(65 + index), index % 2, 0)
        for index in range(1, 7)
    ]
    rows.append(("target", "2017-03-07", "A", "Z", 0, 0))
    row = _build(*rows).set_index("match_id").loc["target"]
    assert row.home_last5_matches == 5
    assert 0 <= row.home_last5_draws <= 5


def test_20_draw_count_never_exceeds_denominator(production) -> None:
    _, result = production
    for side in ("home", "away"):
        assert (result[f"{side}_last5_draws"] <= result[f"{side}_last5_matches"]).all()
        assert (
            result[f"{side}_season_prior_draws"]
            <= result[f"{side}_season_prior_matches"]
        ).all()


def test_21_rates_are_finite_and_in_unit_interval(production) -> None:
    _, result = production
    rate_columns = [column for column in result if "draw_rate" in column]
    for column in rate_columns:
        assert result[column].dropna().between(0, 1).all()


def test_22_side_rate_null_iff_denominator_zero(production) -> None:
    _, result = production
    for side in ("home", "away"):
        for prefix in ("last5", "season_prior"):
            assert result[f"{side}_{prefix}_draw_rate"].isna().equals(
                result[f"{side}_{prefix}_matches"].eq(0)
            )


def test_23_derived_null_propagation() -> None:
    row = _build(
        ("old", "2017-03-01", "A", "B", 0, 0),
        ("target", "2017-03-08", "A", "C", 1, 0),
    ).set_index("match_id").loc["target"]
    assert row.home_last5_draw_rate == 1.0
    assert pd.isna(row.away_last5_draw_rate)
    assert pd.isna(row.mean_draw_rate_last5)
    assert pd.isna(row.abs_draw_rate_diff_last5)


def test_24_derived_means_are_exact() -> None:
    row = _build(
        ("a", "2017-03-01", "A", "C", 0, 0),
        ("b", "2017-03-01", "B", "D", 1, 0),
        ("target", "2017-03-08", "A", "B", 0, 0),
    ).set_index("match_id").loc["target"]
    assert row.mean_draw_rate_last5 == 0.5
    assert row.mean_season_prior_draw_rate == 0.5


def test_25_derived_absolute_differences_are_exact() -> None:
    row = _build(
        ("a", "2017-03-01", "A", "C", 0, 0),
        ("b", "2017-03-01", "B", "D", 1, 0),
        ("target", "2017-03-08", "A", "B", 0, 0),
    ).set_index("match_id").loc["target"]
    assert row.abs_draw_rate_diff_last5 == 1.0
    assert row.abs_season_prior_draw_rate_diff == 1.0


def test_26_swap_invariance() -> None:
    history = (
        ("a", "2017-03-01", "A", "C", 0, 0),
        ("b", "2017-03-01", "B", "D", 1, 0),
    )
    first = _build(*history, ("target", "2017-03-08", "A", "B", 0, 0)).iloc[-1]
    second = _build(*history, ("target", "2017-03-08", "B", "A", 0, 0)).iloc[-1]
    assert first[list(draw.MODEL_CANDIDATES)].equals(second[list(draw.MODEL_CANDIDATES)])


def test_27_existing_form_draw_count_exact_reconciliation(production) -> None:
    matches, result = production
    form = add_form_features(matches)
    assert result.home_last5_draws.tolist() == form.home_last5_draws.tolist()
    assert result.away_last5_draws.tolist() == form.away_last5_draws.tolist()


def test_28_current_season_coverage_exact(production) -> None:
    _, result = production
    summary = draw.coverage_summary(result, frozen=True)
    assert summary["global"]["season_prior_0_1_4_5_plus"] == (184, 736, 5496)
    assert all(
        summary[str(season)]["season_prior_0_1_4_5_plus"] == expected[0]
        for season, expected in draw.EXPECTED_COVERAGE.items()
    )


def test_29_last_five_coverage_exact(production) -> None:
    _, result = production
    summary = draw.coverage_summary(result, frozen=True)
    assert summary["global"]["last5_0_1_4_5"] == (30, 120, 6266)
    assert all(
        summary[str(season)]["last5_0_1_4_5"] == expected[1]
        for season, expected in draw.EXPECTED_COVERAGE.items()
    )


def test_30_both_full_last_five_exact(production) -> None:
    _, result = production
    assert draw.coverage_summary(result, frozen=True)["global"]["both_full_last5"] == 3106


def test_31_reverse_input_order_identical(production) -> None:
    matches, expected = production
    actual = draw.build_draw_propensity_features(matches.iloc[::-1].reset_index(drop=True))
    assert_frame_equal(actual, expected)


def test_32_repeated_build_byte_identical(production) -> None:
    matches, expected = production
    repeated = draw.build_draw_propensity_features(matches.copy(deep=True))
    assert draw._csv_bytes(expected) == draw._csv_bytes(repeated)


def test_33_output_exact_ordered_schema(production) -> None:
    _, result = production
    assert tuple(result.columns) == draw.OUTPUT_COLUMNS
    assert len(result.columns) == 21


def test_34_model_candidates_exactly_four() -> None:
    assert draw.MODEL_CANDIDATES == (
        "mean_draw_rate_last5",
        "abs_draw_rate_diff_last5",
        "mean_season_prior_draw_rate",
        "abs_season_prior_draw_rate_diff",
    )


def test_35_no_target_result_or_score_field(production) -> None:
    _, result = production
    assert {"result", "home_score", "away_score"}.isdisjoint(result.columns)


def test_36_no_model_or_evaluation_dependency() -> None:
    source = inspect.getsource(draw)
    assert "sklearn" not in source
    assert "src.modeling" not in source
    assert "predict_proba" not in source
    assert "log_loss" not in source


def test_37_write_once_is_atomic_and_refuses_overwrite(tmp_path: Path) -> None:
    result = _build(("m1", "2017-03-01", "A", "B", 0, 0))
    output = tmp_path / "features.csv"
    digest = draw._write_once(result, output)
    assert output.read_bytes() == draw._csv_bytes(result)
    assert len(digest) == 64
    with pytest.raises(draw.DrawPropensityError, match="refusing overwrite"):
        draw._write_once(result, output)


def test_38_candidate_distribution_is_label_free_and_complete(production) -> None:
    _, result = production
    distributions = draw.candidate_distributions(result)
    assert tuple(distributions) == draw.MODEL_CANDIDATES
    for values in distributions.values():
        assert values["non_null"] + values["null"] == 3208
