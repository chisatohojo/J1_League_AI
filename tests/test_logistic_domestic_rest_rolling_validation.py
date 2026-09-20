import numpy as np
import pandas as pd
import pytest

from src.modeling.logistic_domestic_rest_rolling_validation import (
    ALL_FEATURES,
    DOMESTIC_FEATURES,
    ELO_FEATURES,
    EXPECTED_VALIDATION_COUNTS,
    HOME_ADVANTAGE,
    K_FACTOR,
    VALIDATION_SEASONS,
    _metrics,
    _replay_elo,
)


def test_fixed_folds_and_features():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert list(EXPECTED_VALIDATION_COUNTS.values()) == [306, 380, 306, 306, 380]
    assert ELO_FEATURES == ("elo_diff",)
    assert len(DOMESTIC_FEATURES) == 4
    assert ALL_FEATURES == ELO_FEATURES + DOMESTIC_FEATURES
    assert K_FACTOR == 30.0
    assert HOME_ADVANTAGE == 175.0


def test_pre_match_elo_and_deterministic_replay():
    frame = pd.DataFrame({
        "match_id": ["a", "b"],
        "match_date": pd.to_datetime(["2019-01-01", "2019-01-10"]),
        "home_team_id": ["team_0001", "team_0002"],
        "away_team_id": ["team_0002", "team_0001"],
        "result": [2, 0],
    })
    first = _replay_elo(frame)
    second = _replay_elo(frame)
    pd.testing.assert_frame_equal(first, second)
    assert first.loc[0, "elo_diff"] == 0.0
    assert first.loc[1, "elo_diff"] != 0.0


def test_metrics_class_order_and_probability_sum():
    target = np.array([0, 1, 2])
    probabilities = np.eye(3)
    metrics = _metrics(target, probabilities)
    assert metrics.accuracy == 1.0
    assert np.isfinite(metrics.log_loss)


def test_metrics_rejects_invalid_probability_rows():
    with pytest.raises(ValueError):
        _metrics(np.array([0]), np.array([[0.2, 0.2, 0.2]]))

