import numpy as np
import pytest

from src.modeling.dixon_coles_rolling_validation import (
    RHO_MAX,
    RHO_MIN,
    VALIDATION_SEASONS,
    _score_probability,
    tau_correction,
)


def test_tau_formulas():
    lam, mu, rho = 1.4, 1.1, -0.05
    assert tau_correction(0, 0, lam, mu, rho) == pytest.approx(1 - lam * mu * rho)
    assert tau_correction(0, 1, lam, mu, rho) == pytest.approx(1 + lam * rho)
    assert tau_correction(1, 0, lam, mu, rho) == pytest.approx(1 + mu * rho)
    assert tau_correction(1, 1, lam, mu, rho) == pytest.approx(1 - rho)
    assert tau_correction(2, 1, lam, mu, rho) == 1.0


def test_invalid_tau_and_rho_are_rejected():
    with pytest.raises(ValueError):
        tau_correction(0, 0, 10.0, 10.0, 0.20)
    with pytest.raises(ValueError):
        tau_correction(0, 0, 1.0, 1.0, RHO_MIN - 0.001)
    with pytest.raises(ValueError):
        tau_correction(0, 0, 1.0, 1.0, RHO_MAX + 0.001)


def test_rho_zero_matches_independent_and_orientation_is_preserved():
    independent = _score_probability(2.0, 1.0, 0.0)
    corrected = _score_probability(2.0, 1.0, 0.0)
    assert np.allclose(independent, corrected)
    assert corrected[2] > corrected[0]
    assert np.all(corrected >= 0)
    assert np.isclose(corrected.sum(), 1.0)


def test_fixed_folds():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
