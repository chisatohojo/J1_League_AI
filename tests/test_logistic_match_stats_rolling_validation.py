import pandas as pd

from src.modeling.logistic_match_stats_rolling_validation import (
    FEATURE_SETS,
    VALIDATION_SEASONS,
)


def test_fixed_folds_and_feature_sets():
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert list(FEATURE_SETS) == [
        "A_baseline", "B_baseline_plus_shots", "C_baseline_plus_ck",
        "D_baseline_plus_fk", "E_baseline_plus_all",
    ]
    assert all(len(columns) in (11, 17, 29) for columns in FEATURE_SETS.values())
