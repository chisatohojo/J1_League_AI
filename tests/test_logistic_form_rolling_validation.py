import numpy as np
import pandas as pd

from src.features.form import add_form_features
from src.modeling.logistic_form_rolling_validation import (
    ALL_FEATURES, ELO_FEATURES, EXPECTED_VALIDATION_COUNTS, FORM_FEATURES,
    HOME_ADVANTAGE, K_FACTOR, VALIDATION_SEASONS, _metrics, _replay_elo,
)


def test_fixed_folds_and_feature_sets():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert list(EXPECTED_VALIDATION_COUNTS.values()) == [306, 380, 306, 306, 380]
    assert ELO_FEATURES == ("elo_diff",)
    assert len(FORM_FEATURES) == 6
    assert ALL_FEATURES == ELO_FEATURES + FORM_FEATURES
    assert K_FACTOR == 30.0
    assert HOME_ADVANTAGE == 175.0


def test_current_match_is_not_in_form_and_input_is_unchanged():
    frame = pd.DataFrame({
        "match_date": pd.to_datetime(["2019-01-01", "2019-01-10"]),
        "home_team_id": ["team_0001", "team_0002"],
        "away_team_id": ["team_0002", "team_0001"],
        "home_score": [3, 0], "away_score": [0, 2], "result": [2, 0],
    })
    original = frame.copy(deep=True)
    result = add_form_features(frame)
    pd.testing.assert_frame_equal(frame, original)
    assert result.loc[0, "home_last5_goals_for"] == 0
    assert result.loc[1, "home_last5_goals_for"] == 0
    assert result.loc[1, "away_last5_goals_for"] == 3


def test_replay_is_deterministic_and_pre_match():
    frame = pd.DataFrame({
        "match_id": ["a", "b"], "match_date": pd.to_datetime(["2019-01-01", "2019-01-10"]),
        "home_team_id": ["team_0001", "team_0002"], "away_team_id": ["team_0002", "team_0001"],
        "result": [2, 0],
    })
    first, second = _replay_elo(frame), _replay_elo(frame)
    pd.testing.assert_frame_equal(first, second)
    assert first.loc[0, "elo_diff"] == 0
    assert first.loc[1, "elo_diff"] != 0


def test_class_order_and_probability_rows():
    metrics = _metrics(np.array([0, 1, 2]), np.eye(3))
    assert metrics.accuracy == 1.0
    assert np.isfinite(metrics.log_loss)

