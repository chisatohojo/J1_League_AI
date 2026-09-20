import numpy as np
import pytest

from src.modeling.elo_davidson_rolling_validation import davidson_probabilities


def test_probability_sum_and_class_order():
    p=davidson_probabilities(np.array([1500.0]),np.array([1675.0]),1.0)
    assert p.shape==(1,3)
    assert p.sum()==pytest.approx(1.0)
    assert p[0,0]==pytest.approx(p[0,2])


def test_nu_increases_draw_probability():
    low=davidson_probabilities(1500,1500,0.5)[0,1]
    high=davidson_probabilities(1500,1500,2.0)[0,1]
    assert high>low


def test_nu_must_be_positive():
    with pytest.raises(ValueError): davidson_probabilities(1500,1500,0)
