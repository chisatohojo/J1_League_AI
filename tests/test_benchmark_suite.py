from src.modeling.benchmark_suite import (
    BENCHMARK_NAMES,
    FEATURE_COLUMNS,
    HOME_ADVANTAGE,
    K_FACTOR,
    VALIDATION_SEASONS,
)


def test_benchmark_contract():
    assert BENCHMARK_NAMES == ("uniform", "train_prior", "elo_only", "champion")
    assert VALIDATION_SEASONS == (2020, 2021, 2022, 2023, 2024)
    assert len(FEATURE_COLUMNS) == 11
    assert K_FACTOR == 30.0
    assert HOME_ADVANTAGE == 175.0
