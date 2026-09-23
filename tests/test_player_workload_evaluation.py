import numpy as np
import pandas as pd
import pytest

from src.modeling.player_workload_evaluation import (
    EXPECTED_COUNTS,
    FOLDS,
    MODEL_PARAMS,
    W0_FEATURES,
    W1_FEATURES,
    WORKLOAD_FEATURES,
    _align_predictions,
    _add_eligibility,
    _add_elo,
    _load_inputs,
    _metrics,
    _validate_probabilities,
    evaluate,
    frozen_decision,
)


def test_frozen_folds_counts_and_features():
    assert FOLDS == (2020, 2021, 2022, 2023, 2024)
    assert EXPECTED_COUNTS == {
        2020: (1530, 1485, 306, 297), 2021: (1836, 1782, 380, 370),
        2022: (2216, 2152, 306, 297), 2023: (2522, 2449, 306, 297),
        2024: (2828, 2746, 380, 370),
    }
    assert W0_FEATURES == ("elo_diff",)
    assert len(WORKLOAD_FEATURES) == 12
    assert W1_FEATURES == ("elo_diff", *WORKLOAD_FEATURES)
    assert MODEL_PARAMS == {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}


def test_probability_and_brier_contract():
    probabilities = np.full((3, 3), 1 / 3)
    _validate_probabilities(probabilities)
    assert _metrics(np.array([0, 1, 2]), probabilities).brier == 2 / 3
    with pytest.raises(ValueError):
        _validate_probabilities(np.array([[0.5, 0.5, np.nan]]))


def test_match_id_alignment_ignores_row_order():
    probabilities = np.array([[0.1, 0.2, 0.7], [0.2, 0.3, 0.5], [0.4, 0.3, 0.3]])
    source = pd.Series(["a", "b", "c"])
    target = pd.Series(["c", "a", "b"])
    expected = probabilities[[2, 0, 1]]
    np.testing.assert_array_equal(_align_predictions(probabilities, source, target), expected)


def test_local_artifact_strict_join_and_opened_seasons_excluded():
    data = _load_inputs()
    assert len(data) == 3208
    assert data.match_id.is_unique
    assert set(data.season) == set(range(2015, 2025))
    assert not data.season.isin([2025, 2026]).any()


def test_true_partial_workload_is_a_hard_error():
    row = {column: 1.0 for column in WORKLOAD_FEATURES}
    row.update({"home_has_previous_j1_match": 1, "away_has_previous_j1_match": 1,
                "home_prev_reference_from_prior_season": 0,
                "away_prev_reference_from_prior_season": 0})
    row[WORKLOAD_FEATURES[0]] = np.nan
    with pytest.raises(ValueError, match="partial/invalid"):
        _add_eligibility(pd.DataFrame([row]))


def test_same_date_elo_is_batched_and_input_order_independent():
    rows = pd.DataFrame([
        {"match_id": "2", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "c", "away_team_id": "d", "result": 2},
        {"match_id": "1", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "a", "away_team_id": "b", "result": 2},
        {"match_id": "3", "match_date": pd.Timestamp("2020-01-02"), "home_team_id": "a", "away_team_id": "c", "result": 1},
    ])
    first = _add_elo(rows).set_index("match_id").elo_diff
    second = _add_elo(rows.sample(frac=1, random_state=7)).set_index("match_id").elo_diff
    pd.testing.assert_series_equal(first.sort_index(), second.sort_index())
    assert first.loc["1"] == first.loc["2"] == 0.0


def test_frozen_decision_three_cases():
    def folds(improved):
        result = {}
        for index, year in enumerate(FOLDS):
            result[year] = {"w0": {"log_loss": 1.0},
                            "w1": {"log_loss": 0.9 if index < improved else 1.1}}
        return result
    better = {"w0": {"log_loss": 1.0, "brier": 1.0}, "w1": {"log_loss": 0.9, "brier": 0.9}}
    worse = {"w0": {"log_loss": 1.0, "brier": 1.0}, "w1": {"log_loss": 1.1, "brier": 1.1}}
    assert frozen_decision(folds(3), better) == "CONTINUE_TO_PROSPECTIVE_FREEZE"
    assert frozen_decision(folds(2), worse) == "CLOSE_RETROSPECTIVE_LANE"
    assert frozen_decision(folds(2), better) == "MIXED"


def test_frozen_evaluation_is_deterministic_and_excludes_opened_data():
    first = evaluate()
    second = evaluate()
    assert first == second
    assert set(first["folds"]) == set(FOLDS)
    assert sum(first["folds"][year]["validation_eligible"] for year in FOLDS) == 1631
    assert sum(first["operational"][year]["rows"] for year in FOLDS) == 1678
    assert first["pooled"]["w0"]["count"] == first["pooled"]["w1"]["count"] == 1631
    assert first["pooled"]["a_y"]["count"] == first["pooled"]["operational_w1"]["count"] == 1678
