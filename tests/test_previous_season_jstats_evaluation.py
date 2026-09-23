import numpy as np
import pandas as pd
import pytest

from src.modeling.previous_season_jstats_evaluation import (
    EXPECTED_MATCHED,
    FOLDS,
    J1_FEATURES,
    _metrics,
    _validate_probabilities,
    MODEL_PARAMS,
    frozen_decision,
    evaluate,
)


def test_frozen_folds_and_expected_matched_rows():
    assert FOLDS == (2021, 2022, 2023, 2024)
    assert EXPECTED_MATCHED == {2021: 306, 2022: 240, 2023: 240, 2024: 272}


def test_feature_set_is_frozen():
    assert J1_FEATURES[0] == "elo_diff"
    assert len(J1_FEATURES) == 13
    assert MODEL_PARAMS == {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}


def test_project_multiclass_brier_scale():
    result = _metrics(np.array([0, 1, 2]), np.full((3, 3), 1 / 3))
    assert result.brier == 2 / 3


def test_evaluation_has_frozen_fold_and_operational_counts():
    result = evaluate()
    assert set(result["folds"]) == {2021, 2022, 2023, 2024}
    assert [result["folds"][year]["matched_rows"] for year in FOLDS] == [306, 240, 240, 272]
    assert [result["operational"][year]["rows"] for year in FOLDS] == [380, 306, 306, 380]
    assert result["pooled"]["j0"]["count"] == 1058
    assert result["pooled"]["j1"]["count"] == 1058
    assert result["pooled"]["operational_j1"]["count"] == 1372
    assert result["pooled"]["a_y"]["count"] == 1372


def test_opened_seasons_are_excluded_from_evaluation_input():
    frame = pd.read_csv("data/processed/features/previous_season_jstats_features.csv")
    assert set(frame["season"].astype(str)) == {"2020", "2021", "2022", "2023", "2024", "2025", "2026/27"}
    assert set(frame.loc[~frame["season"].astype(str).isin({"2025", "2026/27"}), "season"].astype(str)) == {"2020", "2021", "2022", "2023", "2024"}


def test_frozen_decision_rule_has_three_outcomes():
    def fold(value):
        return {year: {"j0": {"log_loss": 1.0, "count": 1}, "j1": {"log_loss": value, "count": 1}} for year in FOLDS}
    base = {"j0": {"log_loss": 1.0, "brier": 1.0}, "j1": {"log_loss": 0.9, "brier": 0.9}}
    assert frozen_decision(fold(0.9), base) == "CONTINUE_TO_PROSPECTIVE_FREEZE"
    assert frozen_decision(fold(1.1), {"j0": {"log_loss": 1.0, "brier": 1.0}, "j1": {"log_loss": 1.1, "brier": 1.1}}) == "CLOSE_RETROSPECTIVE_LANE"
    mixed = fold(0.9); mixed[2024]["j1"]["log_loss"] = 1.1
    assert frozen_decision(mixed, {"j0": {"log_loss": 1.0, "brier": 1.0}, "j1": {"log_loss": 0.9, "brier": 1.1}}) == "MIXED"
    two_two = fold(0.9); two_two[2023]["j1"]["log_loss"] = 1.1; two_two[2024]["j1"]["log_loss"] = 1.1
    assert frozen_decision(two_two, {"j0": {"log_loss": 1.0, "brier": 1.0}, "j1": {"log_loss": 1.1, "brier": 1.1}}) == "MIXED"


def test_probability_contract():
    _validate_probabilities(np.full((2, 3), 1 / 3))
    with pytest.raises(ValueError):
        _validate_probabilities(np.array([[0.5, 0.5, np.nan]]))


def test_frozen_metrics_and_decision_unchanged():
    result = evaluate()
    assert round(result["pooled"]["j0"]["log_loss"], 6) == 1.053432
    assert round(result["pooled"]["j1"]["log_loss"], 6) == 1.073160
    assert frozen_decision(result["folds"], result["pooled"]) == "CLOSE_RETROSPECTIVE_LANE"
