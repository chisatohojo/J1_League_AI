import numpy as np

from src.modeling.poisson_score_rolling_validation import MAX_GOALS, VALIDATION_SEASONS


def test_poisson_contract():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert MAX_GOALS == 15


def test_probability_aggregation_is_valid():
    from src.modeling.poisson_score_rolling_validation import _score_probabilities
    probabilities = _score_probabilities(1.4, 1.1)
    assert np.all(probabilities >= 0)
    assert np.isclose(probabilities.sum(), 1.0)


def test_home_lambda_higher_means_home_probability_higher():
    from src.modeling.poisson_score_rolling_validation import _score_probabilities
    probabilities = _score_probabilities(2.0, 1.0)
    assert probabilities[2] > probabilities[0]


def test_away_lambda_higher_means_away_probability_higher():
    from src.modeling.poisson_score_rolling_validation import _score_probabilities
    probabilities = _score_probabilities(1.0, 2.0)
    assert probabilities[0] > probabilities[2]


def test_equal_lambdas_have_symmetric_home_away_probability():
    from src.modeling.poisson_score_rolling_validation import _score_probabilities
    probabilities = _score_probabilities(1.5, 1.5)
    assert np.isclose(probabilities[0], probabilities[2])


def test_swapping_lambdas_swaps_home_away_probabilities():
    from src.modeling.poisson_score_rolling_validation import _score_probabilities
    original = _score_probabilities(2.0, 1.0)
    swapped = _score_probabilities(1.0, 2.0)
    assert np.isclose(original[2], swapped[0])
    assert np.isclose(original[0], swapped[2])
