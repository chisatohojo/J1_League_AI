import numpy as np
import pytest

from src.modeling.poisson_time_decay_rolling_validation import (
    HALF_LIFE_CANDIDATES,
    VALIDATION_SEASONS,
    decay_weight,
)


def test_decay_formula():
    assert decay_weight(0, 180) == pytest.approx(1.0)
    assert decay_weight(180, 180) == pytest.approx(0.5)
    assert decay_weight(360, 180) == pytest.approx(0.25)


def test_invalid_age_and_half_life():
    with pytest.raises(ValueError):
        decay_weight(-1, 180)
    with pytest.raises(ValueError):
        decay_weight(1, 0)
    with pytest.raises(ValueError):
        decay_weight(1, True)
    with pytest.raises(ValueError):
        decay_weight(True, 180)


def test_fixed_candidates_and_folds():
    assert HALF_LIFE_CANDIDATES == (None, 180, 365, 730)
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
