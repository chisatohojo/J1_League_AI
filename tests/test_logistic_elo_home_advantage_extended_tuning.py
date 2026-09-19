import pytest

from src.features.elo import EloRatings
from src.modeling.logistic_elo_home_advantage_extended_tuning import (
    FEATURE_COLUMNS, HOME_ADVANTAGE_CANDIDATES, K_FACTOR, STADIUM_WINDOW,
)


def test_final_candidates_are_exactly_fixed():
    assert HOME_ADVANTAGE_CANDIDATES == (100.0, 125.0, 150.0, 175.0, 200.0)
    assert K_FACTOR == 30.0
    assert STADIUM_WINDOW == 5
    assert len(FEATURE_COLUMNS) == 11


def test_home_advantage_is_used_only_for_expectation():
    ratings = EloRatings(["home", "away"], k_factor=K_FACTOR, home_advantage=100.0)
    before = ratings.pre_match("home", "away")
    update = ratings.update("home", "away", 2)
    expected = 1 / (1 + 10 ** (-100 / 400))
    assert before.home_rating == before.away_rating == 1500.0
    assert before.home_expected == pytest.approx(expected)
    assert update.after.home_rating == pytest.approx(1500 + K_FACTOR * (1 - expected))
    assert update.after.away_rating == pytest.approx(1500 - K_FACTOR * (1 - expected))


def test_zero_home_advantage_remains_unmodified_behavior():
    plain = EloRatings(["home", "away"], k_factor=K_FACTOR)
    zero = EloRatings(["home", "away"], k_factor=K_FACTOR, home_advantage=0.0)
    assert plain.update("home", "away", 2) == zero.update("home", "away", 2)
