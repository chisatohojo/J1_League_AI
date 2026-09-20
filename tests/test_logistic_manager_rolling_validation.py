from src.features.manager_context import FEATURE_COLUMNS
from src.modeling.logistic_manager_rolling_validation import (
    ELO_ONLY_FEATURES, HOME_ADVANTAGE, K_FACTOR, MANAGER_FEATURES,
)
from src.modeling.benchmark_suite import VALIDATION_SEASONS

def test_fixed_model_scope():
    assert ELO_ONLY_FEATURES == ('elo_diff',)
    assert MANAGER_FEATURES == ('elo_diff', *FEATURE_COLUMNS)
    assert K_FACTOR == 30.0
    assert HOME_ADVANTAGE == 175.0
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
