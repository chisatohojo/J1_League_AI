from src.modeling.logistic_match_stats_test_evaluation import (
    FEATURE_SETS,
    HOME_ADVANTAGE,
    K_FACTOR,
    STATS_WINDOW,
)


def test_holdout_conditions_are_fixed():
    assert list(FEATURE_SETS) == ["A_baseline", "B_baseline_plus_shots"]
    assert len(FEATURE_SETS["A_baseline"]) == 11
    assert len(FEATURE_SETS["B_baseline_plus_shots"]) == 17
    assert K_FACTOR == 30.0
    assert HOME_ADVANTAGE == 175.0
    assert STATS_WINDOW == 5
