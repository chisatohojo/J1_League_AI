import math

import pytest

from src.features.elo import EloRatings
from src.modeling.logistic_elo_home_advantage_tuning import (
    FEATURE_COLUMNS, HOME_ADVANTAGE_CANDIDATES, K_FACTOR,
)


def test_candidates_k_and_features_are_fixed():
    assert HOME_ADVANTAGE_CANDIDATES == (0.0, 25.0, 50.0, 75.0, 100.0)
    assert K_FACTOR == 30.0
    assert len(FEATURE_COLUMNS) == 11


def test_zero_home_advantage_preserves_existing_elo_behavior():
    plain = EloRatings(["a", "b"], k_factor=30.0)
    zero = EloRatings(["a", "b"], k_factor=30.0, home_advantage=0.0)
    assert plain.update("a", "b", 2) == zero.update("a", "b", 2)


def test_home_advantage_changes_expectation_not_stored_rating():
    ratings = EloRatings(["a", "b"], k_factor=30.0, home_advantage=100.0)
    update = ratings.update("a", "b", 2)
    assert update.before.home_rating == 1500.0
    assert update.before.away_rating == 1500.0
    assert update.before.home_expected == pytest.approx(1 / (1 + 10 ** (-0.25)))
    assert update.after.home_rating == pytest.approx(1500 + 30 * (1 - update.before.home_expected))
    assert ratings.get_rating("a") - ratings.get_rating("b") == pytest.approx(
        2 * (ratings.get_rating("a") - 1500)
    )


@pytest.mark.parametrize("value", [True, False, -1, float("nan"), float("inf"), "25"])
def test_invalid_home_advantage_rejected(value):
    with pytest.raises(ValueError):
        EloRatings(["a", "b"], home_advantage=value)
