import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import src.modeling.goal_timing_evaluation as evaluation
from src.features.elo import EloRatings
from src.modeling.goal_timing_evaluation import (
    CLASS_ORDER,
    EXPECTED_COUNTS,
    FOLDS,
    GOAL_TIMING_FEATURES,
    KNOWN_A_Y_LL,
    KNOWN_A_Y_POOLED,
    T0_FEATURES,
    T1_FEATURES,
    FoldResult,
    GoalTimingEvaluationError,
    _add_eligibility,
    _add_elo,
    _align_predictions,
    _assert_a_y_sanity,
    _assert_same_labels,
    _assert_same_match_ids,
    _fit,
    _fold_frames,
    _load_inputs,
    _metrics,
    _observed_minute_max,
    _operational_probabilities,
    _pooled_metrics,
    _validate_fold_counts,
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
                "elo_diff": 999.0,
            },
            {
                "match_id": "1",
                "match_date": pd.Timestamp("2020-01-01"),
                "home_team_id": "a",
                "away_team_id": "b",
                "result": 2,
                "elo_diff": 999.0,
            },
            {
                "match_id": "3",
                "match_date": pd.Timestamp("2020-01-02"),
                "home_team_id": "a",
                "away_team_id": "c",
                "result": 1,
                "elo_diff": 999.0,
            },
        ]
    )


def _profile_row(*, home_available=True, away_available=True):
    row = {}
    values = {
        "first_goal": 10.0,
        "scoring": 20.0,
        "conceding": 30.0,
    }
    for side, available in (
        ("home", home_available),
        ("away", away_available),
    ):
        row[f"{side}_goal_timing_available"] = available
        for kind, value in values.items():
            denominator = (
                f"{side}_prior_first_goal_timing_observations"
                if kind == "first_goal"
                else f"{side}_prior_{kind}_goal_events"
            )
            sum_column = f"{side}_prior_{kind}_minute_normalized_sum"
            mean_column = f"{side}_mean_{kind}_minute_normalized_prior"
            row[denominator] = 1 if available else 0
            row[sum_column] = value if available else 0.0
            row[mean_column] = value if available else np.nan
    return row


def _fold_result(t0_ll, t1_ll):
    metrics = lambda ll: {
        "accuracy": 0.0,
        "log_loss": ll,
        "brier": 1.0,
        "count": 1,
    }
    return FoldResult(
        season=2020,
        train_total=1,
        train_eligible=1,
        validation_total=1,
        validation_eligible=1,
        t0=metrics(t0_ll),
        t1=metrics(t1_ll),
        delta_t1_minus_t0={
            "accuracy": 0.0,
            "log_loss": t1_ll - t0_ll,
            "brier": 0.0,
        },
        a_y=metrics(1.0),
        operational_t1=metrics(1.0),
    )


def test_01_class_order_and_exact_frozen_feature_sets():
    np.testing.assert_array_equal(CLASS_ORDER, np.array([0, 1, 2]))
    assert T0_FEATURES == ("elo_diff",)
    assert T1_FEATURES == (
        "elo_diff",
        "home_mean_first_goal_minute_normalized_prior",
        "away_mean_first_goal_minute_normalized_prior",
        "home_mean_scoring_minute_normalized_prior",
        "away_mean_scoring_minute_normalized_prior",
        "home_mean_conceding_minute_normalized_prior",
        "away_mean_conceding_minute_normalized_prior",
    )
    assert len(GOAL_TIMING_FEATURES) == 6


def test_02_project_uniform_multiclass_brier_is_two_thirds():
    probabilities = np.full((3, 3), 1 / 3)
    assert _metrics(np.array([0, 1, 2]), probabilities)["brier"] == pytest.approx(
        2 / 3
    )


def test_03_elo_replay_exactly_reuses_known_good_implementation():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff.sort_index()
    expected = known_good_add_elo(rows).set_index("match_id").elo_diff.sort_index()
    pd.testing.assert_series_equal(actual, expected)


def test_04_legacy_and_stored_elo_are_not_used():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff
    assert not actual.eq(999.0).any()
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
    second = _add_elo(rows.sample(frac=1, random_state=4)).set_index(
        "match_id"
    ).elo_diff
    assert first.loc["1"] == first.loc["2"] == 0.0
    pd.testing.assert_series_equal(first.sort_index(), second.sort_index())


def test_06_primary_eligibility_requires_both_teams_available():
    pair = pd.DataFrame([_profile_row()])
    assert _add_eligibility(
        pair, observed_minute_max=90
    ).primary_eligible.tolist() == [True]
    asymmetric = pd.DataFrame(
        [_profile_row(home_available=True, away_available=False)]
    )
    assert _add_eligibility(
        asymmetric, observed_minute_max=90
    ).primary_eligible.tolist() == [False]


def test_07_available_pair_requires_six_valid_range_bounded_means():
    row = _profile_row()
    row["home_mean_scoring_minute_normalized_prior"] = np.nan
    with pytest.raises(GoalTimingEvaluationError, match="invalid timing mean"):
        _add_eligibility(pd.DataFrame([row]), observed_minute_max=90)

    row = _profile_row()
    row["away_prior_conceding_minute_normalized_sum"] = 91.0
    row["away_mean_conceding_minute_normalized_prior"] = 91.0
    with pytest.raises(GoalTimingEvaluationError, match="invalid timing mean"):
        _add_eligibility(pd.DataFrame([row]), observed_minute_max=90)


def test_08_unavailable_team_may_retain_finite_means_but_pair_is_ineligible():
    row = _profile_row(home_available=False, away_available=True)
    for kind, value in (("first_goal", 10.0), ("scoring", 20.0)):
        denominator = (
            "home_prior_first_goal_timing_observations"
            if kind == "first_goal"
            else "home_prior_scoring_goal_events"
        )
        row[denominator] = 1
        row[f"home_prior_{kind}_minute_normalized_sum"] = value
        row[f"home_mean_{kind}_minute_normalized_prior"] = value
    result = _add_eligibility(pd.DataFrame([row]), observed_minute_max=90)
    assert result.primary_eligible.tolist() == [False]
    assert result.home_mean_first_goal_minute_normalized_prior.iloc[0] == 10.0


def test_09_t0_t1_matched_ids_and_labels_must_be_exactly_equal():
    _assert_same_match_ids(["a", "b"], ["b", "a"], context="fixture")
    _assert_same_labels([0, 1], [0, 1], context="fixture")
    with pytest.raises(GoalTimingEvaluationError, match="matched IDs differ"):
        _assert_same_match_ids(["a", "b"], ["a", "c"], context="fixture")
    with pytest.raises(GoalTimingEvaluationError, match="matched labels differ"):
        _assert_same_labels([0, 1], [0, 2], context="fixture")


def test_10_all_frozen_fold_and_pooled_counts_are_rederived():
    assert FOLDS == (2020, 2021, 2022, 2023, 2024)
    assert EXPECTED_COUNTS == {
        2020: (1530, 1435, 306, 288),
        2021: (1836, 1723, 380, 356),
        2022: (2216, 2079, 306, 289),
        2023: (2522, 2368, 306, 286),
        2024: (2828, 2654, 380, 357),
    }
    data = _add_eligibility(
        _load_inputs(), observed_minute_max=_observed_minute_max()
    )
    _validate_fold_counts(data)
    for season in FOLDS:
        frames = _fold_frames(data, season)
        assert (
            len(frames["train_all"]),
            len(frames["train"]),
            len(frames["validation_all"]),
            len(frames["validation"]),
        ) == EXPECTED_COUNTS[season]


def test_11_scaler_and_logistic_fit_training_rows_only(monkeypatch):
    train = pd.DataFrame(
        {"elo_diff": np.linspace(-2, 2, 9), "result": [0, 1, 2] * 3}
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
    _fit(train, validation, T0_FEATURES)
    assert observed == [("scaler", 9), ("logistic", 9)]


def test_12_probability_validation_rejects_shape_range_nan_and_bad_sum():
    _validate_probabilities(np.eye(3))
    for invalid in (
        np.array([[0.5, 0.5]]),
        np.array([[0.5, 0.5, np.nan]]),
        np.array([[1.1, -0.1, 0.0]]),
        np.array([[0.2, 0.2, 0.2]]),
    ):
        with pytest.raises(GoalTimingEvaluationError):
            _validate_probabilities(invalid)


def test_13_operational_fallback_aligns_same_match_a_y_by_id():
    a_y = np.array(
        [[0.1, 0.2, 0.7], [0.2, 0.3, 0.5], [0.4, 0.3, 0.3]]
    )
    t1 = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]])
    result = _operational_probabilities(
        a_y,
        ["m2", "m1", "m3"],
        t1,
        ["m3", "m1"],
        ["m1", "m2", "m3"],
    )
    np.testing.assert_array_equal(
        result,
        np.array(
            [[0.1, 0.8, 0.1], [0.1, 0.2, 0.7], [0.8, 0.1, 0.1]]
        ),
    )


def test_14_duplicate_missing_extra_or_misaligned_prediction_ids_hard_fail():
    probabilities = np.array([[0.2, 0.3, 0.5], [0.4, 0.3, 0.3]])
    for source, target in (
        (["a", "a"], ["a", "b"]),
        (["a", "b"], ["a", "c"]),
        (["a", "b"], ["a"]),
    ):
        with pytest.raises(GoalTimingEvaluationError, match="IDs differ"):
            _align_predictions(probabilities, source, target)
    with pytest.raises(GoalTimingEvaluationError, match="IDs are invalid"):
        _operational_probabilities(
            probabilities,
            ["a", "b"],
            np.array([[0.2, 0.3, 0.5]]),
            ["c"],
            ["a", "b"],
        )


def test_15_pooled_metrics_use_concatenated_oof_predictions():
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


def test_16_a_y_mismatch_blocks_before_matched_t0_or_t1(monkeypatch):
    marker = {"matched_called": False}
    monkeypatch.setattr(evaluation, "_load_inputs", lambda *args: pd.DataFrame())
    monkeypatch.setattr(evaluation, "_observed_minute_max", lambda *args: 90.0)
    monkeypatch.setattr(evaluation, "_add_eligibility", lambda frame, **kwargs: frame)
    monkeypatch.setattr(evaluation, "_validate_fold_counts", lambda frame: None)
    monkeypatch.setattr(evaluation, "_add_elo", lambda frame: frame)
    monkeypatch.setattr(evaluation, "_evaluate_a_y", lambda frame: {"bad": True})

    def reject(_a_y):
        raise GoalTimingEvaluationError("BLOCKED_REFERENCE_MISMATCH")

    def forbidden(_data, _a_y):
        marker["matched_called"] = True
        return {}

    monkeypatch.setattr(evaluation, "_assert_a_y_sanity", reject)
    monkeypatch.setattr(evaluation, "_evaluate_matched_after_sanity", forbidden)
    with pytest.raises(GoalTimingEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation.evaluate_goal_timing()
    assert not marker["matched_called"]


def test_17_frozen_decision_continue_close_and_inconclusive():
    def folds(improved):
        return [
            _fold_result(1.0, 0.9 if index < improved else 1.1)
            for index in range(5)
        ]

    better = {
        "t0": {"log_loss": 1.0, "brier": 1.0},
        "t1": {"log_loss": 0.9, "brier": 0.9},
    }
    worse = {
        "t0": {"log_loss": 1.0, "brier": 1.0},
        "t1": {"log_loss": 1.1, "brier": 1.1},
    }
    mixed = {
        "t0": {"log_loss": 1.0, "brier": 1.0},
        "t1": {"log_loss": 0.9, "brier": 1.1},
    }
    assert frozen_decision(folds(3), better) == "CONTINUE_GOAL_TIMING_LANE"
    assert frozen_decision(folds(2), worse) == "CLOSE_RETROSPECTIVE_LANE"
    assert frozen_decision(folds(3), mixed) == "INCONCLUSIVE_NO_TUNING"


def test_frozen_a_y_reference_constants_are_exact():
    assert KNOWN_A_Y_LL == {
        2020: 1.023119734659012,
        2021: 1.0253437210487792,
        2022: 1.0940186385371449,
        2023: 1.0604285568595655,
        2024: 1.079241181120235,
    }
    assert KNOWN_A_Y_POOLED == {
        "accuracy": 0.466626936829559,
        "log_loss": 1.056065401323764,
        "brier": 0.6357323419292724,
    }
    with pytest.raises(GoalTimingEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        _assert_a_y_sanity(
            {
                "contexts": [
                    {
                        "season": season,
                        "metrics": {
                            "log_loss": value + (1e-6 if season == 2020 else 0)
                        },
                    }
                    for season, value in KNOWN_A_Y_LL.items()
                ],
                "pooled": KNOWN_A_Y_POOLED,
            }
        )
