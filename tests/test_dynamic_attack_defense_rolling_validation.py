import numpy as np

from src.modeling.dynamic_attack_defense_rolling_validation import (
    UPDATE_RATE,
    expected_goals,
    update_ratings,
)
from src.modeling.poisson_score_rolling_validation import _score_probabilities


def test_initial_state_and_expected_goal_formulas():
    ratings = {}
    update_ratings(ratings, "a", "b", 2, 0, 1.5, 1.0)
    assert ratings
    home, away = expected_goals(1.5, 1.0, 0.2, -0.1, -0.3, 0.4)
    assert home == 1.5 * np.exp(0.3)
    assert away == np.exp(-0.7)


def test_update_uses_pre_match_lambda_and_fixed_rate():
    ratings = {"a": (0.0, 0.0), "b": (0.0, 0.0)}
    before = dict(ratings)
    update_ratings(ratings, "a", "b", 2, 0, 1.0, 1.0)
    assert ratings["a"][0] > before["a"][0]
    assert ratings["b"][1] < before["b"][1]
    assert UPDATE_RATE == 0.05


def test_probability_orientation_and_class_order():
    probabilities = _score_probabilities(2.0, 1.0)
    assert probabilities.shape == (3,)
    assert np.all(probabilities >= 0)
    assert np.isclose(probabilities.sum(), 1.0)
    assert probabilities[2] > probabilities[0]
