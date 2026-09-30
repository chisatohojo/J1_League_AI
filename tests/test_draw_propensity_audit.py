from __future__ import annotations

import pandas as pd
from pandas.api.types import is_float_dtype, is_integer_dtype
import pytest

from src.collect.matches import load_matches
from src.collect.teams import load_team_master
from src.features import draw_propensity_audit as draw
from src.features.elo import EloRatings
from src.features.form import add_form_features


def _matches(*rows) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "match_id": match_id,
                "match_date": match_date,
                "season": season if season is not None else int(match_date[:4]),
                "home_team_id": home,
                "away_team_id": away,
                "result": result,
            }
            for match_id, match_date, home, away, result, season in rows
        ],
        columns=draw.h2h.REQUIRED_INPUT_COLUMNS,
    )


def test_target_result_is_not_visible_before_feature_read() -> None:
    result = draw.build_draw_propensity_audit(
        _matches(("target", "2015-03-01", "A", "B", 1, None))
    ).iloc[0]
    assert result.home_matches_last_5 == 0
    assert result.home_draws_last_5 == 0
    assert pd.isna(result.home_draw_rate_last_5)


def test_same_date_peer_result_is_not_visible() -> None:
    result = draw.build_draw_propensity_audit(
        _matches(
            ("m1", "2015-03-01", "A", "B", 1, None),
            ("m2", "2015-03-01", "C", "D", 1, None),
            ("m3", "2015-03-08", "A", "C", 2, None),
        )
    ).set_index("match_id")
    assert result.loc[["m1", "m2"], "home_matches_last_5"].eq(0).all()
    assert result.loc["m3", "home_draws_last_5"] == 1
    assert result.loc["m3", "away_draws_last_5"] == 1


def test_current_season_state_resets() -> None:
    result = draw.build_draw_propensity_audit(
        _matches(
            ("old", "2015-12-01", "A", "B", 1, None),
            ("new", "2016-02-01", "A", "C", 2, None),
        )
    ).set_index("match_id")
    assert result.loc["new", "home_season_prior_matches"] == 0
    assert pd.isna(result.loc["new", "home_season_prior_draw_rate"])


def test_last_five_continues_across_seasons() -> None:
    result = draw.build_draw_propensity_audit(
        _matches(
            ("old", "2015-12-01", "A", "B", 1, None),
            ("new", "2016-02-01", "A", "C", 2, None),
        )
    ).set_index("match_id")
    assert result.loc["new", "home_matches_last_5"] == 1
    assert result.loc["new", "home_draw_rate_last_5"] == 1.0


def test_zero_history_is_count_zero_and_rate_null() -> None:
    row = draw.build_draw_propensity_audit(
        _matches(("first", "2015-03-01", "A", "B", 2, None))
    ).iloc[0]
    for side in ("home", "away"):
        assert row[f"{side}_matches_last_5"] == 0
        assert row[f"{side}_season_prior_matches"] == 0
        assert pd.isna(row[f"{side}_draw_rate_last_5"])
        assert pd.isna(row[f"{side}_season_prior_draw_rate"])


def test_one_to_four_history_uses_available_denominator_without_padding() -> None:
    rows = [("m1", "2015-03-01", "A", "B", 1, None)]
    rows += [(f"m{i}", f"2015-03-{i:02d}", "A", chr(65 + i), 2, None) for i in range(2, 5)]
    result = draw.build_draw_propensity_audit(_matches(*rows)).set_index("match_id")
    assert result.loc["m2", "home_matches_last_5"] == 1
    assert result.loc["m2", "home_draw_rate_last_5"] == 1.0
    assert result.loc["m4", "home_matches_last_5"] == 3
    assert result.loc["m4", "home_draw_rate_last_5"] == pytest.approx(1 / 3)


def test_exact_five_match_window_drops_the_sixth_prior_event() -> None:
    rows = []
    outcomes = [1, 2, 1, 0, 2, 1]
    for index, outcome in enumerate(outcomes, start=1):
        rows.append((f"m{index}", f"2015-03-{index:02d}", "A", f"T{index}", outcome, None))
    rows.append(("target", "2015-03-07", "A", "Z", 2, None))
    result = draw.build_draw_propensity_audit(_matches(*rows)).set_index("match_id")
    assert result.loc["target", "home_matches_last_5"] == 5
    assert result.loc["target", "home_draws_last_5"] == 2
    assert result.loc["target", "home_draw_rate_last_5"] == 0.4


def test_draw_counting_and_win_loss_exclusion() -> None:
    result = draw.build_draw_propensity_audit(
        _matches(
            ("draw", "2015-03-01", "A", "B", 1, None),
            ("home-win", "2015-03-02", "A", "C", 2, None),
            ("away-win", "2015-03-03", "A", "D", 0, None),
            ("target", "2015-03-04", "A", "E", 2, None),
        )
    ).set_index("match_id")
    assert result.loc["target", "home_draws_last_5"] == 1
    assert result.loc["target", "home_season_prior_draws"] == 1
    assert result.loc["target", "home_season_prior_matches"] == 3


def test_duplicate_match_and_team_date_identity_hard_fail() -> None:
    with pytest.raises(draw.DrawPropensityAuditError, match="Duplicate target"):
        draw.build_draw_propensity_audit(
            _matches(
                ("same", "2015-03-01", "A", "B", 1, None),
                ("same", "2015-03-02", "C", "D", 2, None),
            )
        )
    with pytest.raises(draw.DrawPropensityAuditError, match="Team appears twice"):
        draw.build_draw_propensity_audit(
            _matches(
                ("m1", "2015-03-01", "A", "B", 1, None),
                ("m2", "2015-03-01", "A", "C", 2, None),
            )
        )


@pytest.fixture(scope="module")
def production():
    matches = draw.load_j1_matches()
    return matches, draw.build_draw_propensity_audit(matches)


def test_production_scope_schema_types_and_invariants(production) -> None:
    matches, result = production
    assert len(matches) == len(result) == 3208
    assert matches.match_id.nunique() == result.match_id.nunique() == 3208
    assert tuple(result.columns) == draw.OUTPUT_COLUMNS
    assert result.groupby("season").size().to_dict() == draw.EXPECTED_SEASON_COUNTS
    for side in ("home", "away"):
        for draws_name, matches_name, rate_name in (
            ("draws_last_5", "matches_last_5", "draw_rate_last_5"),
            ("season_prior_draws", "season_prior_matches", "season_prior_draw_rate"),
        ):
            counts = result[f"{side}_{matches_name}"]
            draws = result[f"{side}_{draws_name}"]
            rates = result[f"{side}_{rate_name}"]
            assert is_integer_dtype(counts.dtype)
            assert is_integer_dtype(draws.dtype)
            assert is_float_dtype(rates.dtype)
            assert (draws <= counts).all()
            assert rates[counts.eq(0)].isna().all()
            assert rates[counts.gt(0)].between(0, 1).all()


def test_input_order_does_not_change_date_batched_output(production) -> None:
    matches, expected = production
    actual = draw.build_draw_propensity_audit(
        matches.iloc[::-1].reset_index(drop=True)
    )
    pd.testing.assert_frame_equal(actual, expected)


def test_raw_rate_is_deterministic_from_draws_and_available_count(production) -> None:
    _, result = production
    for side in ("home", "away"):
        for draws_name, matches_name, rate_name in (
            ("draws_last_5", "matches_last_5", "draw_rate_last_5"),
            ("season_prior_draws", "season_prior_matches", "season_prior_draw_rate"),
        ):
            matches = result[f"{side}_{matches_name}"]
            expected = result[f"{side}_{draws_name}"] / matches.mask(matches.eq(0))
            pd.testing.assert_series_equal(
                result[f"{side}_{rate_name}"].astype(float),
                expected.astype(float),
                check_names=False,
            )


def test_full_scope_audit_is_read_only_and_complete() -> None:
    result, audit = draw.full_scope_audit()
    assert len(result) == audit["targets"] == 3208
    assert audit["team_sides"] == 6416
    assert audit["same_date_chronology_violations"] == 0
    assert audit["target_result_uses"] == 0
    assert audit["impossible_rates"] == 0
    assert audit["deterministic_rebuild"] == "PASS"
    assert audit["coverage"]["global"]["season_prior"] == {
        "0": 184,
        "1-4": 736,
        "5+": 5496,
    }
    assert audit["coverage"]["global"]["last_5"] == {
        "0": 30,
        "1-4": 120,
        "5": 6266,
    }
    assert audit["coverage"]["global"]["both_teams_full_last_5"] == 3106


def test_existing_form_draw_counts_are_exact_duplicates(production) -> None:
    _, result = production
    master = load_team_master()
    raw = pd.concat(
        [
            master.add_team_ids(
                load_matches(draw.J1_DIR / f"{season}_matches_probe.csv")
            )
            for season in range(2015, 2025)
        ],
        ignore_index=True,
    ).sort_values(["match_date", "match_id"], kind="mergesort")
    form = add_form_features(
        raw[
            [
                "match_date",
                "home_team_id",
                "away_team_id",
                "home_score",
                "away_score",
                "result",
            ]
        ].reset_index(drop=True)
    )
    assert result.home_draws_last_5.tolist() == form.home_last5_draws.tolist()
    assert result.away_draws_last_5.tolist() == form.away_last5_draws.tolist()


def test_no_contract_value_column_is_exactly_model_a_elo_diff(production) -> None:
    matches, result = production
    ordered = matches.sort_values(["match_date", "match_id"], kind="mergesort")
    team_ids = sorted(set(matches.home_team_id) | set(matches.away_team_id))
    ratings = EloRatings(team_ids, k_factor=30, home_advantage=175)
    values = {}
    for _, day_rows in ordered.groupby("match_date", sort=True):
        for match in day_rows.itertuples(index=False):
            before = ratings.pre_match(match.home_team_id, match.away_team_id)
            values[match.match_id] = before.home_rating - before.away_rating
        for match in day_rows.itertuples(index=False):
            ratings.update(match.home_team_id, match.away_team_id, match.result)
    elo_diff = pd.Series(values).reindex(result.match_id).reset_index(drop=True)
    value_columns = result.columns[5:]
    for column in value_columns:
        values = result[column]
        if values.notna().all():
            assert not values.astype(float).reset_index(drop=True).equals(elo_diff)
