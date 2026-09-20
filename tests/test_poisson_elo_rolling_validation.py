import numpy as np

from src.modeling.poisson_elo_rolling_validation import (
    HOME_ADVANTAGE,
    K_FACTOR,
    POISSON_COLUMNS,
    VALIDATION_SEASONS,
    attacker_elo_diff,
)
from src.modeling.poisson_score_rolling_validation import _score_probabilities


def test_attacker_view_elo_difference():
    assert attacker_elo_diff(1600, 1500, 1) == 100
    assert attacker_elo_diff(1600, 1500, 0) == -100
    assert attacker_elo_diff(1600, 1500, 1) == -attacker_elo_diff(1600, 1500, 0)
    assert HOME_ADVANTAGE == 175.0
    assert K_FACTOR == 30.0


def test_only_one_numeric_elo_feature_and_probability_contract():
    assert POISSON_COLUMNS == ("attacking_team", "defending_team", "is_home", "elo_diff_attacker")
    probabilities = _score_probabilities(2.0, 1.0)
    assert np.all(probabilities >= 0)
    assert np.isclose(probabilities.sum(), 1.0)
    assert probabilities[2] > probabilities[0]


def test_fixed_folds():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
