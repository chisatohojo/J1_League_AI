from src.modeling.catboost_baseline_rolling_validation import (
    FEATURE_COLUMNS_FIXED,
    HOME_ADVANTAGE,
    K_FACTOR,
    VALIDATION_SEASONS,
)


def test_fixed_folds_and_features():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert len(FEATURE_COLUMNS_FIXED) == 11
    assert K_FACTOR == 30.0
    assert HOME_ADVANTAGE == 175.0
