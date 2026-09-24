import pandas as pd
import pytest

from src.features.team_discipline import (
    OUTPUT_COLUMNS,
    TeamDisciplineError,
    build_team_discipline_features,
)


def matches(rows):
    return pd.DataFrame(rows, columns=["match_id", "match_date", "season", "home_team_id", "away_team_id"])


def events(rows):
    return pd.DataFrame(rows, columns=["event_id", "match_id", "match_date", "season", "team_id", "side", "event_type"])


def test_first_match_missing_and_prior_cards_are_pre_match_only():
    m = matches([
        ("m1", "2020-01-01", 2020, "A", "B"),
        ("m2", "2020-01-08", 2020, "B", "A"),
    ])
    e = events([
        ("e1", "m1", "2020-01-01", 2020, "A", "home", "YELLOW_CARD"),
        ("e2", "m1", "2020-01-01", 2020, "A", "home", "YELLOW_CARD"),
        ("e3", "m1", "2020-01-01", 2020, "B", "away", "RED_CARD"),
    ])
    r = build_team_discipline_features(m, e).set_index("match_id")
    assert not r.loc["m1", "home_discipline_available"]
    assert pd.isna(r.loc["m1", "home_yellow_cards_per_match_prior"])
    assert r.loc["m2", "home_prior_j1_matches"] == 1
    assert r.loc["m2", "home_yellow_cards_per_match_prior"] == 0.0
    assert r.loc["m2", "home_red_cards_per_match_prior"] == 1.0


def test_same_date_matches_are_a_conservative_batch():
    m = matches([
        ("m1", "2020-01-01", 2020, "A", "B"),
        ("m2", "2020-01-01", 2020, "C", "A"),
        ("m3", "2020-01-02", 2020, "A", "D"),
    ])
    e = events([("e1", "m1", "2020-01-01", 2020, "A", "home", "YELLOW_CARD")])
    r = build_team_discipline_features(m, e).set_index("match_id")
    assert r.loc["m1", "home_prior_j1_matches"] == 0
    assert r.loc["m2", "away_prior_j1_matches"] == 0
    assert r.loc["m3", "home_prior_j1_matches"] == 2
    assert r.loc["m3", "home_yellow_cards_per_match_prior"] == 0.5


def test_season_boundary_resets_history():
    m = matches([
        ("m1", "2020-12-01", 2020, "A", "B"),
        ("m2", "2021-03-01", 2021, "A", "C"),
    ])
    e = events([("e1", "m1", "2020-12-01", 2020, "A", "home", "RED_CARD")])
    r = build_team_discipline_features(m, e).set_index("match_id")
    assert not r.loc["m2", "home_discipline_available"]
    assert pd.isna(r.loc["m2", "home_red_cards_per_match_prior"])


def test_current_match_cards_are_not_used_and_output_schema_is_frozen():
    m = matches([("m1", "2020-01-01", 2020, "A", "B")])
    e = events([("e1", "m1", "2020-01-01", 2020, "A", "home", "YELLOW_CARD")])
    r = build_team_discipline_features(m, e)
    assert tuple(r.columns) == OUTPUT_COLUMNS
    assert r.loc[0, "home_prior_j1_matches"] == 0
    assert pd.isna(r.loc[0, "home_yellow_cards_per_match_prior"])


def test_unknown_team_or_foreign_match_is_hard_fail():
    m = matches([("m1", "2020-01-01", 2020, "A", "B")])
    bad_team = events([("e1", "m1", "2020-01-01", 2020, "X", "home", "YELLOW_CARD")])
    with pytest.raises(TeamDisciplineError):
        build_team_discipline_features(m, bad_team)
    foreign = events([("e1", "other", "2020-01-01", 2020, "A", "home", "YELLOW_CARD")])
    with pytest.raises(TeamDisciplineError):
        build_team_discipline_features(m, foreign)


def test_deterministic_and_input_not_mutated():
    m = matches([
        ("m2", "2020-01-02", 2020, "B", "A"),
        ("m1", "2020-01-01", 2020, "A", "B"),
    ])
    e = events([])
    before = m.copy(deep=True)
    first = build_team_discipline_features(m, e)
    second = build_team_discipline_features(m.iloc[::-1], e)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(m, before)
