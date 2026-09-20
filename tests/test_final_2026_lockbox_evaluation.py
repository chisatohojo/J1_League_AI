import numpy as np
import pytest

from src.modeling.final_2026_lockbox_evaluation import FEATURE_A, FEATURE_B, metrics, preflight_inputs


def test_frozen_input_preflight_and_feature_contract():
    inputs=preflight_inputs()
    assert inputs["2026_cup"]["rows"] == 4
    assert inputs["2026_emperor"]["rows"] == 19
    assert inputs["target"]["rows"] == 70
    assert FEATURE_A == ("elo_diff",)
    assert FEATURE_B == ("elo_diff", "home_domestic_days_since_last_competitive_match",
                         "away_domestic_days_since_last_competitive_match",
                         "home_domestic_has_previous_competitive_match",
                         "away_domestic_has_previous_competitive_match")
def test_project_multiclass_brier_scale():
    p=np.full((1,3),1/3); y=np.array([0])
    assert metrics(y,p)["brier"] == pytest.approx(2/3)


def test_preflight_does_not_predict():
    assert "probabilities" not in preflight_inputs()
