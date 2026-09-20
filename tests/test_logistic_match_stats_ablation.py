import pandas as pd

from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS
from src.modeling.logistic_match_stats_ablation import FEATURE_SETS


def test_fixed_feature_sets_have_expected_structure():
    assert list(FEATURE_SETS) == [
        "A_baseline", "B_baseline_plus_shots", "C_baseline_plus_ck",
        "D_baseline_plus_fk", "E_baseline_plus_all",
    ]
    assert len(FEATURE_SETS["A_baseline"]) == 11
    assert len(FEATURE_SETS["B_baseline_plus_shots"]) == 17
    assert len(FEATURE_SETS["C_baseline_plus_ck"]) == 17
    assert len(FEATURE_SETS["D_baseline_plus_fk"]) == 17
    assert len(FEATURE_SETS["E_baseline_plus_all"]) == 29
    assert set(FEATURE_SETS["E_baseline_plus_all"]) - set(FEATURE_SETS["A_baseline"]) == set(MATCH_STATS_FORM_COLUMNS)
