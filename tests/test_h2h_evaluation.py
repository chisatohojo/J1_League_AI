from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import pytest

from src.features.h2h import OUTPUT_COLUMNS, load_j1_matches
from src.modeling import h2h_evaluation as evaluation
from src.modeling import player_workload_evaluation as known_good


@pytest.fixture(scope="module")
def artifact() -> pd.DataFrame:
    return evaluation._read_artifact()


@pytest.fixture(scope="module")
def targets() -> pd.DataFrame:
    return load_j1_matches()


def _model_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for index, label in enumerate((0, 1, 2, 0, 1, 2, 0, 1, 2)):
        rows.append({
            "match_id": f"m{index}",
            "elo_diff": float(index - 4),
            "prior_h2h_match_count": index % 4,
            "prior_h2h_home_team_win_count": index % 3,
            "prior_h2h_draw_count": index % 2,
            "result": label,
        })
    frame = pd.DataFrame(rows)
    return frame.iloc[:6].copy(), frame.iloc[6:].copy()


def _decision_folds(improved: int) -> dict:
    result = {}
    for index, season in enumerate(evaluation.FOLDS):
        result[season] = {
            "s0": {"log_loss": 1.0, "brier": 1.0},
            "s1": {"log_loss": 0.9 if index < improved else 1.1, "brier": 0.9},
        }
    return result


def test_01_class_order_is_exact() -> None:
    assert evaluation.CLASS_ORDER == (0, 1, 2)


def test_02_uniform_brier_is_two_thirds() -> None:
    probabilities = np.full((3, 3), 1 / 3)
    assert known_good._metrics(np.array([0, 1, 2]), probabilities).brier == 2 / 3


def test_03_known_good_elo_replay_is_used() -> None:
    rows = pd.DataFrame([
        {"match_id": "2", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "c", "away_team_id": "d", "result": 2},
        {"match_id": "1", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "a", "away_team_id": "b", "result": 2},
        {"match_id": "3", "match_date": pd.Timestamp("2020-01-02"), "home_team_id": "a", "away_team_id": "c", "result": 1},
    ])
    actual = evaluation._add_elo(rows)
    expected = known_good._add_elo(rows)
    pd.testing.assert_frame_equal(actual, expected)


def test_04_stored_and_legacy_elo_are_not_the_contract() -> None:
    assert evaluation._add_elo is known_good._add_elo
    assert known_good.EloRatings.__init__.__defaults__ == (20.0, 0.0)
    assert evaluation.MODEL_PARAMS == {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}


def test_05_same_date_elo_is_conservatively_batched() -> None:
    rows = pd.DataFrame([
        {"match_id": "2", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "c", "away_team_id": "d", "result": 2},
        {"match_id": "1", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "a", "away_team_id": "b", "result": 2},
    ])
    result = evaluation._add_elo(rows).set_index("match_id")
    assert result.loc["1", "elo_diff"] == result.loc["2", "elo_diff"] == 0.0


def test_06_artifact_sha_mismatch_hard_fails(tmp_path) -> None:
    path = tmp_path / "wrong.csv"
    path.write_bytes(b"wrong")
    with pytest.raises(evaluation.H2HEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation.assert_artifact_sha(path)


def test_07_artifact_schema_is_exact(artifact) -> None:
    assert tuple(artifact.columns) == OUTPUT_COLUMNS
    assert len(OUTPUT_COLUMNS) == 11


def test_08_target_feature_identity_is_keyed_by_match_id(artifact, targets) -> None:
    altered = artifact.copy()
    altered.loc[0, "home_team_id"] = "wrong-team"
    with pytest.raises(evaluation.H2HEvaluationError, match="identity mismatch"):
        evaluation.validate_artifact(targets, altered)


def test_09_candidates_are_integer_nonnegative_and_nonnull(artifact) -> None:
    for column in evaluation.MODEL_CANDIDATES:
        assert pd.api.types.is_integer_dtype(artifact[column])
        assert artifact[column].notna().all()
        assert artifact[column].ge(0).all()


def test_10_home_wins_plus_draws_do_not_exceed_total(artifact) -> None:
    assert (
        artifact.prior_h2h_home_team_win_count + artifact.prior_h2h_draw_count
        <= artifact.prior_h2h_match_count
    ).all()


def test_11_derived_away_wins_are_nonnegative_integers(artifact) -> None:
    derived = artifact.prior_h2h_match_count - artifact.prior_h2h_home_team_win_count - artifact.prior_h2h_draw_count
    assert pd.api.types.is_integer_dtype(derived)
    assert derived.ge(0).all()


def test_12_zero_history_structural_zero_invariants(artifact) -> None:
    rows = artifact.loc[artifact.prior_h2h_match_count.eq(0)]
    assert rows.prior_h2h_home_team_win_count.eq(0).all()
    assert rows.prior_h2h_draw_count.eq(0).all()
    assert (~rows.h2h_available).all()
    assert rows.previous_h2h_match_id.isna().all()
    assert rows.previous_h2h_match_date.isna().all()


def test_13_positive_history_audit_invariants(artifact) -> None:
    rows = artifact.loc[artifact.prior_h2h_match_count.gt(0)]
    assert rows.h2h_available.all()
    assert rows.previous_h2h_match_id.notna().all()
    assert rows.previous_h2h_match_date.notna().all()
    assert (pd.to_datetime(rows.previous_h2h_match_date) < pd.to_datetime(rows.match_date)).all()


def test_14_frozen_season_availability_is_exact(artifact) -> None:
    evaluation.validate_frozen_distributions(artifact)
    observed = {
        int(season): (int(rows.h2h_available.sum()), int((~rows.h2h_available).sum()))
        for season, rows in artifact.groupby("season")
    }
    assert observed == evaluation.EXPECTED_AVAILABILITY


def test_15_global_availability_is_exact(artifact) -> None:
    assert int(artifact.h2h_available.sum()) == 2832
    assert int((~artifact.h2h_available).sum()) == 376


def test_16_prior_count_bins_are_exact(artifact) -> None:
    evaluation.validate_frozen_distributions(artifact)
    counts = artifact.prior_h2h_match_count
    assert {
        "0": int(counts.eq(0).sum()), "1": int(counts.eq(1).sum()),
        "2": int(counts.eq(2).sum()), "3": int(counts.eq(3).sum()),
        "4": int(counts.eq(4).sum()), "5-9": int(counts.between(5, 9).sum()),
        "10+": int(counts.ge(10).sum()),
    } == evaluation.EXPECTED_PRIOR_COUNT_BINS


def test_17_frozen_fold_counts_are_exact() -> None:
    assert evaluation.EXPECTED_FOLD_COUNTS == {
        2020: (1530, 306), 2021: (1836, 380), 2022: (2216, 306),
        2023: (2522, 306), 2024: (2828, 380),
    }


def test_18_pooled_validation_count_is_1678() -> None:
    assert sum(validation for _, validation in evaluation.EXPECTED_FOLD_COUNTS.values()) == 1678


def test_19_s0_and_s1_training_ids_can_be_identical() -> None:
    train, validation = _model_frames()
    evaluation.assert_same_fold_inputs(train, train.copy(), validation, validation.copy())
    altered = train.copy()
    altered.loc[0, "match_id"] = "different"
    with pytest.raises(evaluation.H2HEvaluationError, match="training match IDs differ"):
        evaluation.assert_same_fold_inputs(train, altered, validation, validation.copy())


def test_20_s0_and_s1_validation_ids_can_be_identical() -> None:
    train, validation = _model_frames()
    evaluation.assert_same_fold_inputs(train, train.copy(), validation, validation.copy())
    altered = validation.iloc[::-1].copy()
    with pytest.raises(evaluation.H2HEvaluationError, match="validation match IDs differ"):
        evaluation.assert_same_fold_inputs(train, train.copy(), validation, altered)


def test_21_s0_and_s1_labels_are_identical() -> None:
    train, validation = _model_frames()
    evaluation.assert_same_fold_inputs(train, train.copy(), validation, validation.copy())
    altered = validation.copy()
    altered.loc[altered.index[0], "result"] = 2
    with pytest.raises(evaluation.H2HEvaluationError, match="validation labels differ"):
        evaluation.assert_same_fold_inputs(train, train.copy(), validation, altered)


def test_22_pipeline_fits_training_rows_only(monkeypatch) -> None:
    train, validation = _model_frames()
    scaler_fits = []
    logistic_fits = []

    class SpyScaler(evaluation.StandardScaler):
        def fit(self, X, y=None, **params):
            scaler_fits.append((np.asarray(X).copy(), None if y is None else np.asarray(y).copy()))
            return super().fit(X, y, **params)

    class SpyLogistic(evaluation.LogisticRegression):
        def fit(self, X, y, sample_weight=None):
            logistic_fits.append((np.asarray(X).copy(), np.asarray(y).copy()))
            return super().fit(X, y, sample_weight=sample_weight)

    monkeypatch.setattr(evaluation, "StandardScaler", SpyScaler)
    monkeypatch.setattr(evaluation, "LogisticRegression", SpyLogistic)
    evaluation._fit(train, validation, evaluation.S0_FEATURES)
    assert len(scaler_fits) == len(logistic_fits) == 1
    assert scaler_fits[0][0].shape[0] == logistic_fits[0][0].shape[0] == len(train)
    np.testing.assert_array_equal(logistic_fits[0][1], train.result.to_numpy())
    assert set(scaler_fits[0][0][:, 0]) == set(train.elo_diff.to_numpy())
    assert not set(scaler_fits[0][0][:, 0]) & set(validation.elo_diff.to_numpy())


def test_23_s0_features_are_exact() -> None:
    assert evaluation.S0_FEATURES == ("elo_diff",)


def test_24_s1_features_are_exact_and_ordered() -> None:
    assert evaluation.S1_FEATURES == (
        "elo_diff", "prior_h2h_match_count",
        "prior_h2h_home_team_win_count", "prior_h2h_draw_count",
    )


def test_25_probability_validation_contract() -> None:
    probabilities = np.full((4, 3), 1 / 3)
    np.testing.assert_array_equal(evaluation._validate_probabilities(probabilities), probabilities)
    with pytest.raises(ValueError):
        evaluation._validate_probabilities(np.array([[0.2, 0.2, 0.2]]))


def test_26_pooled_metrics_use_concatenated_oof_rows() -> None:
    first = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]])
    second = np.array([[1 / 3, 1 / 3, 1 / 3]])
    labels_first = np.array([0, 1])
    labels_second = np.array([2])
    pooled = known_good._metrics(np.concatenate([labels_first, labels_second]), np.concatenate([first, second]))
    assert pooled.count == 3
    assert pooled.log_loss != np.mean([
        known_good._metrics(labels_first, first).log_loss,
        known_good._metrics(labels_second, second).log_loss,
    ])


def test_27_a_y_mismatch_blocks_s1_and_decision(monkeypatch) -> None:
    data = pd.DataFrame({
        "season": list(range(2015, 2025)),
        "match_id": [f"m{index}" for index in range(10)],
        "result": [0, 1, 2, 0, 1, 2, 0, 1, 2, 0],
    })
    fit_features = []
    decision_called = []

    def fake_prepare_data(*args, **kwargs):
        return data

    def fake_fit(train, validation, features):
        fit_features.append(tuple(features))
        return np.tile([1 / 3, 1 / 3, 1 / 3], (len(validation), 1))

    def forbidden_decision(*args, **kwargs):
        decision_called.append(True)
        raise AssertionError("frozen_decision must not be called after A_Y mismatch")

    monkeypatch.setattr(evaluation, "_prepare_data", fake_prepare_data)
    monkeypatch.setattr(evaluation, "_fit", fake_fit)
    monkeypatch.setattr(evaluation, "frozen_decision", forbidden_decision)
    with pytest.raises(evaluation.H2HEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation.evaluate()
    assert fit_features == [evaluation.S0_FEATURES] * 5
    assert evaluation.S1_FEATURES not in fit_features
    assert decision_called == []


def test_28_continue_decision_branch_is_exact() -> None:
    folds = _decision_folds(3)
    pooled = {"s0": {"log_loss": 1.0, "brier": 1.0}, "s1": {"log_loss": 0.9, "brier": 0.9}}
    assert evaluation.frozen_decision(folds, pooled) == "CONTINUE_H2H_LANE"


def test_29_close_decision_branch_is_exact() -> None:
    folds = _decision_folds(2)
    pooled = {"s0": {"log_loss": 1.0, "brier": 1.0}, "s1": {"log_loss": 1.1, "brier": 1.1}}
    assert evaluation.frozen_decision(folds, pooled) == "CLOSE_RETROSPECTIVE_LANE"


def test_30_inconclusive_decision_branch_is_exact() -> None:
    folds = _decision_folds(3)
    pooled = {"s0": {"log_loss": 1.0, "brier": 1.0}, "s1": {"log_loss": 0.9, "brier": 1.1}}
    assert evaluation.frozen_decision(folds, pooled) == "INCONCLUSIVE_NO_TUNING"


def test_31_actual_class_counts_diagnostic_is_exact() -> None:
    labels = np.array([0, 1, 2, 1])
    probabilities = np.full((4, 3), 1 / 3)
    diagnostic = evaluation._draw_diagnostic(labels, probabilities, probabilities)
    assert diagnostic["actual"] == [1, 2, 1]


def test_32_s0_argmax_counts_diagnostic_is_exact() -> None:
    labels = np.array([0, 1, 2])
    s0 = np.array([[0.8, 0.1, 0.1], [0.7, 0.2, 0.1], [0.1, 0.2, 0.7]])
    diagnostic = evaluation._draw_diagnostic(labels, s0, s0)
    assert diagnostic["s0_argmax"] == [2, 0, 1]


def test_33_s1_argmax_counts_diagnostic_is_exact() -> None:
    labels = np.array([0, 1, 2])
    s0 = np.full((3, 3), 1 / 3)
    s1 = np.array([[0.1, 0.8, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]])
    diagnostic = evaluation._draw_diagnostic(labels, s0, s1)
    assert diagnostic["s1_argmax"] == [0, 2, 1]


def test_34_mean_draw_probability_and_delta_are_exact() -> None:
    labels = np.array([0, 1])
    s0 = np.array([[0.8, 0.1, 0.1], [0.1, 0.3, 0.6]])
    s1 = np.array([[0.7, 0.2, 0.1], [0.1, 0.5, 0.4]])
    diagnostic = evaluation._draw_diagnostic(labels, s0, s1)
    assert diagnostic["s0_mean_draw_probability"] == pytest.approx(0.2)
    assert diagnostic["s1_mean_draw_probability"] == pytest.approx(0.35)
    assert diagnostic["delta_mean_draw_probability"] == pytest.approx(0.15)


def test_35_draw_diagnostics_do_not_enter_decision() -> None:
    folds = _decision_folds(3)
    pooled = {"s0": {"log_loss": 1.0, "brier": 1.0}, "s1": {"log_loss": 0.9, "brier": 0.9}, "draw_diagnostic": {"actual": [0, 999, 0]}}
    assert evaluation.frozen_decision(folds, pooled) == "CONTINUE_H2H_LANE"


def test_36_existing_baseline_prediction_reuse_is_no() -> None:
    assert evaluation.EXISTING_BASELINE_PREDICTION_REUSED is False


def test_37_each_fold_delta_has_accuracy_log_loss_and_brier() -> None:
    s0 = {"accuracy": 0.4, "log_loss": 1.1, "brier": 0.7}
    s1 = {"accuracy": 0.5, "log_loss": 1.0, "brier": 0.6}
    assert evaluation._metric_delta(s1, s0) == pytest.approx({
        "accuracy": 0.1, "log_loss": -0.1, "brier": -0.1,
    })


def test_38_markdown_renderer_contains_frozen_result_sections() -> None:
    metric = {"accuracy": 0.4, "log_loss": 1.1, "brier": 0.7, "count": 1678}
    diagnostic = {
        "actual": [1, 0, 0], "s0_argmax": [1, 0, 0], "s1_argmax": [1, 0, 0],
        "s0_mean_draw_probability": 0.2, "s1_mean_draw_probability": 0.3,
        "delta_mean_draw_probability": 0.1,
    }
    folds = {
        season: {
            "train_n": 1, "validation_n": 1, "s0": metric, "s1": metric,
            "delta": evaluation._metric_delta(metric, metric),
            "draw_diagnostic": diagnostic,
        }
        for season in evaluation.FOLDS
    }
    result = {
        "baseline_sanity": "PASS", "folds": folds,
        "pooled": {"s0": metric, "s1": metric, "delta": evaluation._metric_delta(metric, metric), "draw_diagnostic": diagnostic},
        "s1_log_loss_improved_folds": 0, "decision": "INCONCLUSIVE_NO_TUNING",
        "existing_baseline_prediction_reused": False,
    }
    markdown = evaluation.render_evaluation_markdown(result)
    assert "Baseline sanity" in markdown
    assert "Primary fold results" in markdown
    assert "Primary pooled" in markdown and "1,678" in markdown
    assert "Draw diagnostic" in markdown
    assert "Final decision" in markdown
    assert "adaptive follow-up = **NOT RUN**" in markdown
