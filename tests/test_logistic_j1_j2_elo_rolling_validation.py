import numpy as np
import pandas as pd
import pytest

from src.modeling.logistic_j1_j2_elo_rolling_validation import (
    EXPECTED_VALIDATION_COUNTS,
    K_FACTOR,
    HOME_ADVANTAGE,
    VALIDATION_SEASONS,
    _metrics,
    _prepare_stream,
)


def _rows():
    return pd.DataFrame([
        {"event_key": "j1:a", "match_date": pd.Timestamp("2020-01-01"), "season": 2020, "home_team_id": "a", "away_team_id": "b", "result": 2},
        {"event_key": "j2:b", "match_date": pd.Timestamp("2020-01-03"), "season": 2020, "home_team_id": "b", "away_team_id": "c", "result": 1},
    ])


def test_fixed_parameters_and_folds():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert EXPECTED_VALIDATION_COUNTS == {2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}
    assert K_FACTOR == 30.0 and HOME_ADVANTAGE == 175.0


def test_j2_stream_is_not_a_logistic_target_and_same_day_duplicates_rejected():
    stream = _prepare_stream(_rows().iloc[[0]], _rows().iloc[[1]])
    assert set(stream.event_key) == {"j1:a", "j2:b"}
    duplicate = _rows().copy()
    duplicate.loc[1, "match_date"] = duplicate.loc[0, "match_date"]
    with pytest.raises(ValueError, match="same team"):
        _prepare_stream(duplicate.iloc[[0]], duplicate.iloc[[1]])


def test_metrics_keep_class_order_and_probability_sum():
    result = _metrics(np.array([0, 1, 2]), np.full((3, 3), 1 / 3))
    assert result.accuracy == pytest.approx(1 / 3)
