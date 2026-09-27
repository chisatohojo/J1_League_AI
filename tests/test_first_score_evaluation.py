import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import src.modeling.first_score_evaluation as evaluation
from src.features.elo import EloRatings
from src.modeling.first_score_evaluation import (
    CLASS_ORDER,
    EXPECTED_COUNTS,
    F0_FEATURES,
    F1_FEATURES,
    FOLDS,
    KNOWN_A_Y_LL,
    KNOWN_A_Y_POOLED,
    KNOWN_F0_POOLED,
    FirstScoreEvaluationError,
    FoldResult,
    _add_eligibility,
    _add_elo,
    _align_predictions,
    _assert_baseline_sanity,
    _assert_same_match_ids,
    _evaluate_baselines,
    _fit,
    _fold_frames,
    _load_inputs,
    _metrics,
    _operational_probabilities,
    _pooled_metrics,
    _validate_probabilities,
    frozen_decision,
)
from src.modeling.player_workload_evaluation import _add_elo as known_good_add_elo


def _elo_fixture():
    return pd.DataFrame(
        [
            {
                "match_id": "2",
                "match_date": pd.Timestamp("2020-01-01"),
                "home_team_id": "d",
                "away_team_id": "c",
                "result": 0,
            },
            {
                "match_id": "1",
                "match_date": pd.Timestamp("2020-01-01"),
                "home_team_id": "a",
                "away_team_id": "b",
                "result": 2,
            },
            {
                "match_id": "3",
                "match_date": pd.Timestamp("2020-01-02"),
                "home_team_id": "a",
                "away_team_id": "c",
                "result": 1,
            },
        ]
    )


def _valid_profile_row():
    return {
        "home_first_score_available": True,
        "away_first_score_available": True,
        "home_scored_first_rate_prior": 0.4,
        "away_scored_first_rate_prior": 0.3,
        "home_conceded_first_rate_prior": 0.5,
        "away_conceded_first_rate_prior": 0.6,
    }


def _fold_result(f0_ll, f1_ll):
    return FoldResult(
        season=2020,
        train_total=1,
        train_eligible=1,
        validation_total=1,
        validation_eligible=1,
        f0={"accuracy": 0.0, "log_loss": f0_ll, "brier": 1.0, "count": 1},
        f1={"accuracy": 0.0, "log_loss": f1_ll, "brier": 1.0, "count": 1},
        delta_f1_minus_f0={"accuracy": 0.0, "log_loss": f1_ll - f0_ll, "brier": 0.0},
        a_y={"accuracy": 0.0, "log_loss": 1.0, "brier": 1.0, "count": 1},
        operational_f1={"accuracy": 0.0, "log_loss": 1.0, "brier": 1.0, "count": 1},
    )


def test_01_class_order_and_frozen_feature_sets():
    np.testing.assert_array_equal(CLASS_ORDER, np.array([0, 1, 2]))
    assert F0_FEATURES == ("elo_diff",)
    assert F1_FEATURES == (
        "elo_diff",
        "home_scored_first_rate_prior",
        "away_scored_first_rate_prior",
        "home_conceded_first_rate_prior",
        "away_conceded_first_rate_prior",
    )


def test_02_project_uniform_multiclass_brier_is_two_thirds():
    probabilities = np.full((3, 3), 1 / 3)
    assert _metrics(np.array([0, 1, 2]), probabilities)["brier"] == pytest.approx(2 / 3)


def test_03_elo_replay_exactly_reuses_known_good_implementation():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff.sort_index()
    expected = known_good_add_elo(rows).set_index("match_id").elo_diff.sort_index()
    pd.testing.assert_series_equal(actual, expected)


def test_04_legacy_k20_ha0_elo_is_not_used():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff
    legacy = EloRatings(["a", "b", "c", "d"])
    legacy.update("a", "b", 2)
    legacy.update("d", "c", 0)
    legacy_diff = (
        legacy.pre_match("a", "c").home_rating
        - legacy.pre_match("a", "c").away_rating
    )
    assert legacy_diff == 0.0
    assert actual.loc["3"] != legacy_diff


def test_05_same_date_elo_is_conservatively_batched_and_deterministic():
    rows = _elo_fixture()
    first = _add_elo(rows).set_index("match_id").elo_diff
    second = _add_elo(rows.sample(frac=1, random_state=4)).set_index("match_id").elo_diff
    assert first.loc["1"] == first.loc["2"] == 0.0
    pd.testing.assert_series_equal(first.sort_index(), second.sort_index())


def test_06_eligibility_requires_both_sides_and_rejects_partial_states():
    valid = pd.DataFrame([_valid_profile_row()])
    assert _add_eligibility(valid).primary_eligible.tolist() == [True]

    unavailable = {key: np.nan for key in F1_FEATURES[1:]}
    unavailable.update(
        {"home_first_score_available": False, "away_first_score_available": False}
    )
    assert _add_eligibility(pd.DataFrame([unavailable])).primary_eligible.tolist() == [False]

    with pytest.raises(FirstScoreEvaluationError, match="Partial"):
        _add_eligibility(
            pd.DataFrame([{**_valid_profile_row(), "away_first_score_available": False}])
        )
    with pytest.raises(FirstScoreEvaluationError, match="partial or invalid"):
        _add_eligibility(
            pd.DataFrame(
                [{**_valid_profile_row(), "home_scored_first_rate_prior": np.nan}]
            )
        )
    with pytest.raises(FirstScoreEvaluationError, match="non-null"):
        _add_eligibility(
            pd.DataFrame(
                [
                    {
                        **_valid_profile_row(),
                        "home_first_score_available": False,
                        "away_first_score_available": False,
                    }
                ]
            )
        )


def test_07_f0_f1_matched_ids_must_be_exactly_equal():
    _assert_same_match_ids(["a", "b"], ["b", "a"], context="fixture")
    with pytest.raises(FirstScoreEvaluationError, match="matched IDs differ"):
        _assert_same_match_ids(["a", "b"], ["a", "c"], context="fixture")


def test_08_expected_fold_counts_and_baseline_references_pass():
    assert FOLDS == (2020, 2021, 2022, 2023, 2024)
    assert EXPECTED_COUNTS == {
        2020: (1530, 1485, 306, 297),
        2021: (1836, 1782, 380, 370),
        2022: (2216, 2152, 306, 297),
        2023: (2522, 2449, 306, 297),
        2024: (2828, 2746, 380, 370),
    }
    data = _add_eligibility(_add_elo(_load_inputs()))
    for season in FOLDS:
        frames = _fold_frames(data, season)
        assert (
            len(frames["train_all"]),
            len(frames["train"]),
            len(frames["validation_all"]),
            len(frames["validation"]),
        ) == EXPECTED_COUNTS[season]
    baseline = _evaluate_baselines(data)
    _assert_baseline_sanity(baseline)
    for context in baseline["contexts"]:
        assert np.isclose(
            context["a_y"]["log_loss"],
            KNOWN_A_Y_LL[context["season"]],
            rtol=0,
            atol=1e-12,
        )
    for name, expected in (("a_y", KNOWN_A_Y_POOLED), ("f0", KNOWN_F0_POOLED)):
        for metric, reference in expected.items():
            assert np.isclose(
                baseline["pooled"][name][metric], reference, rtol=0, atol=1e-12
            )


def test_09_scaler_and_model_fit_training_rows_only(monkeypatch):
    train = pd.DataFrame(
        {
            "elo_diff": np.linspace(-2, 2, 9),
            "result": [0, 1, 2] * 3,
        }
    )
    validation = pd.DataFrame({"elo_diff": [-10.0, 10.0], "result": [0, 2]})
    scaler_fit = StandardScaler.fit
    logistic_fit = LogisticRegression.fit
    observed = []

    def spy_scaler(self, x, y=None, **kwargs):
        observed.append(("scaler", len(x)))
        return scaler_fit(self, x, y, **kwargs)

    def spy_logistic(self, x, y, **kwargs):
        observed.append(("logistic", len(x)))
        return logistic_fit(self, x, y, **kwargs)

    monkeypatch.setattr(StandardScaler, "fit", spy_scaler)
    monkeypatch.setattr(LogisticRegression, "fit", spy_logistic)
    _fit(train, validation, F0_FEATURES)
    assert observed == [("scaler", 9), ("logistic", 9)]


def test_10_probability_validation_rejects_shape_range_nan_and_bad_sum():
    _validate_probabilities(np.eye(3))
    for invalid in (
        np.array([[0.5, 0.5]]),
        np.array([[0.5, 0.5, np.nan]]),
        np.array([[1.1, -0.1, 0.0]]),
        np.array([[0.2, 0.2, 0.2]]),
    ):
        with pytest.raises(FirstScoreEvaluationError):
            _validate_probabilities(invalid)


def test_11_operational_fallback_aligns_same_match_by_id():
    a_y = np.array(
        [[0.1, 0.2, 0.7], [0.2, 0.3, 0.5], [0.4, 0.3, 0.3]]
    )
    f1 = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]])
    result = _operational_probabilities(
        a_y,
        ["m2", "m1", "m3"],
        f1,
        ["m3", "m1"],
        ["m1", "m2", "m3"],
    )
    np.testing.assert_array_equal(
        result,
        np.array(
            [
                [0.1, 0.8, 0.1],
                [0.1, 0.2, 0.7],
                [0.8, 0.1, 0.1],
            ]
        ),
    )


def test_12_prediction_alignment_mismatch_is_a_hard_failure():
    probabilities = np.array([[0.2, 0.3, 0.5], [0.4, 0.3, 0.3]])
    with pytest.raises(FirstScoreEvaluationError, match="IDs differ"):
        _align_predictions(probabilities, ["a", "b"], ["a", "c"])
    with pytest.raises(FirstScoreEvaluationError, match="IDs are invalid"):
        _operational_probabilities(
            probabilities,
            ["a", "b"],
            np.array([[0.2, 0.3, 0.5]]),
            ["c"],
            ["a", "b"],
        )


def test_13_pooled_metrics_are_computed_from_concatenated_predictions():
    targets = [np.array([0]), np.array([0, 0, 0])]
    probabilities = [
        np.array([[0.01, 0.49, 0.50]]),
        np.array([[0.90, 0.05, 0.05]] * 3),
    ]
    pooled = _pooled_metrics(targets, probabilities)
    simple_mean = np.mean(
        [_metrics(y, p)["log_loss"] for y, p in zip(targets, probabilities)]
    )
    expected = _metrics(np.concatenate(targets), np.concatenate(probabilities))
    assert pooled == expected
    assert pooled["log_loss"] != pytest.approx(simple_mean)


def test_14_baseline_mismatch_blocks_before_f1(monkeypatch):
    marker = {"f1_called": False}
    monkeypatch.setattr(evaluation, "_load_inputs", lambda *args: pd.DataFrame())
    monkeypatch.setattr(evaluation, "_add_elo", lambda frame: frame)
    monkeypatch.setattr(evaluation, "_add_eligibility", lambda frame: frame)
    monkeypatch.setattr(evaluation, "_evaluate_baselines", lambda frame: {"bad": True})

    def reject(_baseline):
        raise FirstScoreEvaluationError("BLOCKED_REFERENCE_MISMATCH")

    def forbidden(_baseline):
        marker["f1_called"] = True
        return {}

    monkeypatch.setattr(evaluation, "_assert_baseline_sanity", reject)
    monkeypatch.setattr(evaluation, "_evaluate_f1_after_sanity", forbidden)
    with pytest.raises(FirstScoreEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation.evaluate_first_score()
    assert not marker["f1_called"]


def test_15_frozen_decision_continue_close_and_inconclusive():
    def folds(improved):
        return [
            _fold_result(1.0, 0.9 if index < improved else 1.1)
            for index in range(5)
        ]

    better = {
        "f0": {"log_loss": 1.0, "brier": 1.0},
        "f1": {"log_loss": 0.9, "brier": 0.9},
    }
    worse = {
        "f0": {"log_loss": 1.0, "brier": 1.0},
        "f1": {"log_loss": 1.1, "brier": 1.1},
    }
    mixed = {
        "f0": {"log_loss": 1.0, "brier": 1.0},
        "f1": {"log_loss": 0.9, "brier": 1.1},
    }
    assert frozen_decision(folds(3), better) == "CONTINUE_FIRST_SCORE_LANE"
    assert frozen_decision(folds(2), worse) == "CLOSE_RETROSPECTIVE_LANE"
    assert frozen_decision(folds(3), mixed) == "INCONCLUSIVE_NO_TUNING"
