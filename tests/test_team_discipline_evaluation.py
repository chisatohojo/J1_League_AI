import numpy as np
import pandas as pd
import pytest

from src.features.elo import EloRatings
from src.modeling.player_workload_evaluation import _add_elo as known_good_add_elo
from src.modeling.team_discipline_evaluation import (
    KNOWN_A_Y_LL,
    KNOWN_A_Y_POOLED,
    KNOWN_D0_POOLED,
    TeamDisciplineEvaluationError,
    _add_elo,
    _eligible,
    _metrics,
    evaluate_team_discipline,
)


def test_project_multiclass_brier_uniform_is_two_thirds():
    target = np.array([0, 1, 2])
    probabilities = np.full((3, 3), 1 / 3)
    assert np.isclose(_metrics(target, probabilities)["brier"], 2 / 3)


def test_eligibility_requires_both_profiles_and_valid_rates():
    row = {
        "home_discipline_available": True, "away_discipline_available": True,
        "home_yellow_cards_per_match_prior": 0.0, "away_yellow_cards_per_match_prior": 1.0,
        "home_red_cards_per_match_prior": 0.0, "away_red_cards_per_match_prior": 0.0,
    }
    frame = pd.DataFrame([row, {**row, "away_discipline_available": False},
                          {**row, "home_red_cards_per_match_prior": np.nan}])
    assert _eligible(frame).tolist() == [True, False, False]


def test_metrics_use_class_order_away_draw_home():
    target = np.array([0, 1, 2])
    probabilities = np.eye(3)
    assert _metrics(target, probabilities)["accuracy"] == 1.0


def _elo_fixture():
    return pd.DataFrame([
        {"match_id": "2", "match_date": pd.Timestamp("2020-01-01"),
         "home_team_id": "d", "away_team_id": "c", "result": 0},
        {"match_id": "1", "match_date": pd.Timestamp("2020-01-01"),
         "home_team_id": "a", "away_team_id": "b", "result": 2},
        {"match_id": "3", "match_date": pd.Timestamp("2020-01-02"),
         "home_team_id": "a", "away_team_id": "c", "result": 1},
    ])


def test_elo_contract_matches_known_good_and_batches_same_date():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff
    expected = known_good_add_elo(rows).set_index("match_id").elo_diff
    pd.testing.assert_series_equal(actual.sort_index(), expected.sort_index())
    assert actual.loc["1"] == actual.loc["2"] == 0.0
    shuffled = _add_elo(rows.sample(frac=1, random_state=3)).set_index("match_id").elo_diff
    pd.testing.assert_series_equal(actual.sort_index(), shuffled.sort_index())


def test_elo_does_not_reuse_old_k20_ha0_values():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff
    legacy = EloRatings(["a", "b", "c", "d"])
    legacy.update("a", "b", 2)
    legacy.update("d", "c", 0)
    old_diff = legacy.pre_match("a", "c").home_rating - legacy.pre_match("a", "c").away_rating
    assert old_diff == 0.0
    assert actual.loc["3"] != old_diff


def test_frozen_baseline_sanity_and_counts_pass():
    result = evaluate_team_discipline()
    assert result["baseline_sanity"] == "PASS"
    assert result["matched_pooled_n"] == 1631
    assert result["operational_pooled_n"] == 1678
    for fold in result["folds"]:
        assert np.isclose(fold.a_y["log_loss"], KNOWN_A_Y_LL[fold.season], atol=1e-12)
    for key, expected in KNOWN_A_Y_POOLED.items():
        assert np.isclose(result["pooled"]["a_y"][key], expected, atol=1e-12)
    for key, expected in KNOWN_D0_POOLED.items():
        assert np.isclose(result["pooled"]["d0"][key], expected, atol=1e-12)


def test_invalid_probability_shape_is_rejected():
    with pytest.raises(TeamDisciplineEvaluationError):
        _metrics(np.array([0]), np.array([[0.5, 0.5]]))
