from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from src.features.draw_propensity import MODEL_CANDIDATES, OUTPUT_COLUMNS, load_j1_matches
from src.modeling import draw_propensity_evaluation as evaluation
from src.modeling import player_workload_evaluation as known_good


_FORMAL_DOC_INITIAL_BYTES = (
    evaluation.EVALUATION_DOC_PATH.read_bytes()
    if evaluation.EVALUATION_DOC_PATH.exists()
    else None
)


@pytest.fixture(scope="module")
def artifact() -> pd.DataFrame:
    return evaluation._read_artifact()


@pytest.fixture(scope="module")
def targets() -> pd.DataFrame:
    return load_j1_matches()


@pytest.fixture(scope="module")
def eligible_artifact(artifact, targets) -> pd.DataFrame:
    evaluation.validate_artifact(targets, artifact)
    return evaluation.add_primary_eligibility(artifact)


@pytest.fixture(scope="module")
def actual_preflight() -> evaluation.PreflightResult:
    return evaluation.preflight()


def _synthetic_model_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for index, label in enumerate((0, 1, 2, 0, 1, 2, 0, 1, 2)):
        rows.append({
            "match_id": f"m{index}",
            "elo_diff": float(index - 4),
            "mean_draw_rate_last5": index / 10,
            "abs_draw_rate_diff_last5": index / 20,
            "mean_season_prior_draw_rate": index / 12,
            "abs_season_prior_draw_rate_diff": index / 16,
            "result": label,
        })
    frame = pd.DataFrame(rows)
    return frame.iloc[:6].copy(), frame.iloc[6:].copy()


def _a_y_values() -> dict[int, dict]:
    return {
        year: {"metrics": {"log_loss": value}}
        for year, value in evaluation.EXPECTED_A_Y_LL.items()
    }


def _decision_folds(improved: int) -> dict:
    return {
        year: {
            "dp0": {"log_loss": 1.0, "brier": 1.0},
            "dp1": {
                "log_loss": 0.9 if index < improved else 1.1,
                "brier": 0.9,
            },
        }
        for index, year in enumerate(evaluation.FOLDS)
    }


def _preflight_result() -> evaluation.PreflightResult:
    return evaluation.PreflightResult(
        status=evaluation.PREFLIGHT_STATUS,
        artifact_sha256=evaluation.ARTIFACT_SHA256,
        schema_identity_gate="PASS",
        eligible_counts_gate="PASS",
        fold_counts=evaluation.EXPECTED_FOLD_COUNTS.copy(),
        pooled_eligible_validation=evaluation.EXPECTED_POOLED_ELIGIBLE,
        pooled_full_validation=evaluation.EXPECTED_POOLED_FULL,
        a_y_gate="PASS",
        a_y_log_loss=evaluation.EXPECTED_A_Y_LL.copy(),
    )


def _renderer_result() -> dict:
    metric = {"accuracy": 0.4, "log_loss": 1.1, "brier": 0.7, "count": 1}
    diagnostic = {
        "actual": [1, 0, 0],
        "dp0_argmax": [1, 0, 0],
        "dp1_argmax": [1, 0, 0],
        "dp0_mean_draw_probability": 0.2,
        "dp1_mean_draw_probability": 0.3,
        "delta_mean_draw_probability": 0.1,
    }
    folds = {
        year: {
            "total_train": counts[0],
            "eligible_train": counts[1],
            "total_validation": counts[2],
            "eligible_validation": counts[3],
            "dp0": metric,
            "dp1": metric,
            "delta": evaluation._metric_delta(metric, metric),
            "draw_diagnostic": diagnostic,
        }
        for year, counts in evaluation.EXPECTED_FOLD_COUNTS.items()
    }
    operational = {
        year: {"rows": counts[2], "a_y": metric, "fallback_dp1": metric}
        for year, counts in evaluation.EXPECTED_FOLD_COUNTS.items()
    }
    pooled_metric = {**metric, "count": 1631}
    operational_metric = {**metric, "count": 1678}
    return {
        "artifact_sha256": evaluation.ARTIFACT_SHA256,
        "artifact_sha_gate": "PASS",
        "baseline_sanity": "PASS",
        "a_y_log_loss": evaluation.EXPECTED_A_Y_LL.copy(),
        "folds": folds,
        "pooled": {
            "dp0": pooled_metric,
            "dp1": pooled_metric,
            "delta": evaluation._metric_delta(pooled_metric, pooled_metric),
            "draw_diagnostic": diagnostic,
        },
        "improved_log_loss_folds": 0,
        "operational": operational,
        "operational_pooled": {
            "a_y": operational_metric,
            "fallback_dp1": operational_metric,
        },
        "decision": "INCONCLUSIVE_NO_TUNING",
    }


def test_01_artifact_sha_is_exact(actual_preflight) -> None:
    assert actual_preflight.artifact_sha256 == evaluation.ARTIFACT_SHA256


def test_02_wrong_sha_rejects_before_source_load(tmp_path, monkeypatch) -> None:
    wrong = tmp_path / "wrong.csv"
    wrong.write_bytes(b"wrong")
    monkeypatch.setattr(
        evaluation,
        "load_j1_matches",
        lambda *args, **kwargs: pytest.fail("source loaded before SHA gate"),
    )
    with pytest.raises(
        evaluation.DrawPropensityEvaluationError,
        match="BLOCKED_REFERENCE_MISMATCH",
    ):
        evaluation.preflight(artifact_path=wrong)


def test_03_schema_is_exact(artifact) -> None:
    assert tuple(artifact.columns) == OUTPUT_COLUMNS
    assert len(artifact.columns) == 21


def test_04_wrong_schema_rejects(artifact, targets) -> None:
    with pytest.raises(evaluation.DrawPropensityEvaluationError, match="schema"):
        evaluation.validate_artifact(targets, artifact.drop(columns=[OUTPUT_COLUMNS[-1]]))


def test_05_row_count_is_exact(artifact) -> None:
    assert len(artifact) == 3208


def test_06_unique_match_ids_are_exact(artifact) -> None:
    assert artifact.match_id.nunique() == 3208


def test_07_duplicate_match_id_rejects(artifact, targets) -> None:
    altered = artifact.copy()
    altered.loc[1, "match_id"] = altered.loc[0, "match_id"]
    with pytest.raises(evaluation.DrawPropensityEvaluationError, match="unique-ID"):
        evaluation.validate_artifact(targets, altered)


def test_08_identity_join_is_match_id_keyed_and_order_independent(artifact, targets) -> None:
    shuffled = artifact.sample(frac=1, random_state=8).reset_index(drop=True)
    evaluation.validate_artifact(targets, shuffled)


@pytest.mark.parametrize("column", ["match_date", "season", "home_team_id", "away_team_id"])
def test_09_identity_mismatch_rejects(artifact, targets, column) -> None:
    altered = artifact.copy()
    if column == "match_date":
        altered.loc[0, column] = "2015-12-31"
    elif column == "season":
        altered.loc[0, column] = 2016
    else:
        altered.loc[0, column] = "wrong-team"
    with pytest.raises(evaluation.DrawPropensityEvaluationError, match="identity mismatch"):
        evaluation.validate_artifact(targets, altered)


def test_10_candidates_are_exact_and_ordered() -> None:
    assert evaluation.DP1_FEATURES == (
        "elo_diff",
        "mean_draw_rate_last5",
        "abs_draw_rate_diff_last5",
        "mean_season_prior_draw_rate",
        "abs_season_prior_draw_rate_diff",
    )
    assert evaluation.DP1_FEATURES[1:] == MODEL_CANDIDATES


@pytest.mark.parametrize("invalid", [np.inf, -0.01, 1.01, "not-a-number"])
def test_11_invalid_non_null_candidate_rejects(artifact, targets, invalid) -> None:
    altered = artifact.copy()
    if isinstance(invalid, str):
        altered[MODEL_CANDIDATES[0]] = altered[MODEL_CANDIDATES[0]].astype(object)
    altered.loc[100, MODEL_CANDIDATES[0]] = invalid
    with pytest.raises(
        evaluation.DrawPropensityEvaluationError,
        match="Invalid non-null candidate",
    ):
        evaluation.validate_artifact(targets, altered)


def test_12_null_candidate_is_valid_but_ineligible(artifact, targets) -> None:
    altered = artifact.copy()
    altered.loc[100, MODEL_CANDIDATES[0]] = np.nan
    evaluation.validate_artifact(targets, altered)
    eligible = evaluation.add_primary_eligibility(altered)
    assert not bool(eligible.loc[100, "primary_eligible"])


def test_13_eligibility_does_not_impute(artifact) -> None:
    missing = artifact.loc[:, list(MODEL_CANDIDATES)].isna()
    eligible = evaluation.add_primary_eligibility(artifact)
    pd.testing.assert_frame_equal(
        eligible.loc[:, list(MODEL_CANDIDATES)].isna(), missing
    )
    assert "missing_indicator" not in eligible.columns
    assert "SimpleImputer" not in inspect.getsource(evaluation.add_primary_eligibility)


def test_14_frozen_fold_counts_are_exact(eligible_artifact) -> None:
    observed = evaluation.validate_fold_counts(eligible_artifact)
    assert observed == evaluation.EXPECTED_FOLD_COUNTS


@pytest.mark.parametrize(
    ("year", "expected"), sorted(evaluation.EXPECTED_FOLD_COUNTS.items())
)
def test_15_each_fold_count_is_exact(actual_preflight, year, expected) -> None:
    assert actual_preflight.fold_counts[year] == expected


def test_16_pooled_eligible_validation_is_exact(actual_preflight) -> None:
    assert actual_preflight.pooled_eligible_validation == 1631


def test_17_pooled_full_validation_is_exact(actual_preflight) -> None:
    assert actual_preflight.pooled_full_validation == 1678
    assert 1678 - 1631 == 47


def test_18_known_good_full_history_elo_is_directly_reused() -> None:
    assert evaluation._add_elo is known_good._add_elo


def test_19_preflight_replays_elo_before_eligibility_filter(monkeypatch) -> None:
    seen = []
    original = evaluation._add_elo

    def spy(matches):
        seen.append((len(matches), "primary_eligible" in matches.columns))
        return original(matches)

    monkeypatch.setattr(evaluation, "_add_elo", spy)
    monkeypatch.setattr(
        evaluation,
        "_evaluate_a_y",
        lambda data: {
            year: {
                "metrics": {"log_loss": value},
                "validation_ids": [],
                "probabilities": np.empty((0, 3)),
            }
            for year, value in evaluation.EXPECTED_A_Y_LL.items()
        },
    )
    evaluation.preflight()
    assert seen == [(3208, False)]


def test_20_same_date_elo_is_conservatively_batched() -> None:
    rows = pd.DataFrame([
        {"match_id": "2", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "c", "away_team_id": "d", "result": 2},
        {"match_id": "1", "match_date": pd.Timestamp("2020-01-01"), "home_team_id": "a", "away_team_id": "b", "result": 2},
    ])
    result = evaluation._add_elo(rows).set_index("match_id")
    assert result.loc["1", "elo_diff"] == result.loc["2", "elo_diff"] == 0.0


def test_21_dp0_dp1_training_ids_are_exact() -> None:
    train, validation = _synthetic_model_frames()
    evaluation.assert_same_fold_inputs(train, train.copy(), validation, validation.copy())
    altered = train.iloc[::-1].copy()
    with pytest.raises(evaluation.DrawPropensityEvaluationError, match="training match IDs"):
        evaluation.assert_same_fold_inputs(train, altered, validation, validation.copy())


def test_22_dp0_dp1_validation_ids_are_exact() -> None:
    train, validation = _synthetic_model_frames()
    altered = validation.iloc[::-1].copy()
    with pytest.raises(evaluation.DrawPropensityEvaluationError, match="validation match IDs"):
        evaluation.assert_same_fold_inputs(train, train.copy(), validation, altered)


def test_23_dp0_dp1_labels_are_exact() -> None:
    train, validation = _synthetic_model_frames()
    altered = validation.copy()
    altered.loc[altered.index[0], "result"] = 2
    with pytest.raises(evaluation.DrawPropensityEvaluationError, match="validation labels"):
        evaluation.assert_same_fold_inputs(train, train.copy(), validation, altered)


def test_24_dp0_input_is_exact() -> None:
    assert evaluation.DP0_FEATURES == ("elo_diff",)


def test_25_pipeline_and_model_parameters_are_exact() -> None:
    assert evaluation.MODEL_PARAMS == {
        "C": 1.0,
        "solver": "lbfgs",
        "max_iter": 1000,
        "random_state": 0,
    }


def test_26_scaler_and_logistic_fit_training_only(monkeypatch) -> None:
    train, validation = _synthetic_model_frames()
    scaler_rows = []
    logistic_rows = []

    class SpyScaler(evaluation.StandardScaler):
        def fit(self, X, y=None, **params):
            scaler_rows.append(len(X))
            return super().fit(X, y, **params)

    class SpyLogistic(evaluation.LogisticRegression):
        def fit(self, X, y, sample_weight=None):
            logistic_rows.append(len(X))
            return super().fit(X, y, sample_weight=sample_weight)

    monkeypatch.setattr(evaluation, "StandardScaler", SpyScaler)
    monkeypatch.setattr(evaluation, "LogisticRegression", SpyLogistic)
    evaluation._fit(train, validation, evaluation.DP0_FEATURES)
    assert scaler_rows == logistic_rows == [len(train)]


def test_27_class_order_is_exact() -> None:
    assert evaluation.CLASS_ORDER == (0, 1, 2)


def test_28_probability_validation_is_reused() -> None:
    assert evaluation._validate_probabilities is known_good._validate_probabilities
    valid = np.full((2, 3), 1 / 3)
    np.testing.assert_array_equal(evaluation._validate_probabilities(valid), valid)
    with pytest.raises(ValueError):
        evaluation._validate_probabilities(np.array([[0.2, 0.2, 0.2]]))


def test_29_pooled_metrics_use_concatenated_rows() -> None:
    first = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]])
    second = np.array([[1 / 3, 1 / 3, 1 / 3]])
    first_y, second_y = np.array([0, 1]), np.array([2])
    pooled = known_good._metrics(
        np.concatenate([first_y, second_y]), np.concatenate([first, second])
    )
    fold_average = np.mean([
        known_good._metrics(first_y, first).log_loss,
        known_good._metrics(second_y, second).log_loss,
    ])
    assert pooled.count == 3
    assert pooled.log_loss != fold_average


@pytest.mark.parametrize("year", evaluation.FOLDS)
def test_30_each_a_y_exact_reference_passes(year) -> None:
    values = _a_y_values()
    values[year]["metrics"]["log_loss"] += 5e-13
    evaluation.assert_a_y_references(values)


def test_31_a_y_outside_exact_tolerance_rejects() -> None:
    values = _a_y_values()
    values[2023]["metrics"]["log_loss"] += 2e-12
    with pytest.raises(
        evaluation.DrawPropensityEvaluationError,
        match="BLOCKED_REFERENCE_MISMATCH",
    ):
        evaluation.assert_a_y_references(values)


def test_32_a_y_failure_blocks_dp1_and_report(monkeypatch, tmp_path) -> None:
    report = tmp_path / "forbidden.md"
    monkeypatch.setattr(
        evaluation,
        "_preflight_context",
        lambda **kwargs: (_ for _ in ()).throw(
            evaluation.DrawPropensityEvaluationError("BLOCKED_REFERENCE_MISMATCH")
        ),
    )
    monkeypatch.setattr(
        evaluation,
        "_formal_from_context",
        lambda context: pytest.fail("DP1 formal path called after A_Y failure"),
    )
    monkeypatch.setattr(evaluation, "EVALUATION_DOC_PATH", report)
    with pytest.raises(
        evaluation.DrawPropensityEvaluationError,
        match="BLOCKED_REFERENCE_MISMATCH",
    ):
        evaluation.formal_evaluate()
    assert not report.exists()


def test_33_actual_a_y_gate_passes(actual_preflight) -> None:
    assert actual_preflight.a_y_gate == "PASS"
    for year, expected in evaluation.EXPECTED_A_Y_LL.items():
        assert actual_preflight.a_y_log_loss[year] == pytest.approx(expected, abs=1e-12)


def test_34_operational_fallback_is_exact_and_match_id_aligned() -> None:
    a_ids = ["a", "b", "c"]
    a_probabilities = np.array([
        [0.7, 0.2, 0.1],
        [0.1, 0.8, 0.1],
        [0.1, 0.2, 0.7],
    ])
    dp1_ids = ["c", "a"]
    dp1_probabilities = np.array([
        [0.2, 0.7, 0.1],
        [0.2, 0.1, 0.7],
    ])
    result = evaluation._operational_fallback(
        a_y_probabilities=a_probabilities,
        a_y_ids=a_ids,
        dp1_probabilities=dp1_probabilities,
        dp1_ids=dp1_ids,
        validation_ids=["b", "c", "a"],
        eligible_ids=["a", "c"],
    )
    np.testing.assert_array_equal(
        result,
        np.array([
            [0.1, 0.8, 0.1],
            [0.2, 0.7, 0.1],
            [0.2, 0.1, 0.7],
        ]),
    )


def test_35_operational_alignment_rejects_id_set_mismatch() -> None:
    with pytest.raises(ValueError, match="ID sets differ"):
        evaluation._operational_fallback(
            a_y_probabilities=np.full((2, 3), 1 / 3),
            a_y_ids=["a", "b"],
            dp1_probabilities=np.full((1, 3), 1 / 3),
            dp1_ids=["a"],
            validation_ids=["a", "c"],
            eligible_ids=["a"],
        )


def test_36_continue_decision_branch_is_exact() -> None:
    folds = _decision_folds(3)
    pooled = {
        "dp0": {"log_loss": 1.0, "brier": 1.0},
        "dp1": {"log_loss": 0.9, "brier": 0.9},
    }
    assert evaluation.frozen_decision(folds, pooled) == "CONTINUE_DRAW_PROPENSITY_LANE"


def test_37_close_decision_branch_is_exact() -> None:
    folds = _decision_folds(2)
    pooled = {
        "dp0": {"log_loss": 1.0, "brier": 1.0},
        "dp1": {"log_loss": 1.1, "brier": 1.1},
    }
    assert evaluation.frozen_decision(folds, pooled) == "CLOSE_RETROSPECTIVE_LANE"


def test_38_inconclusive_decision_branch_is_exact() -> None:
    folds = _decision_folds(3)
    pooled = {
        "dp0": {"log_loss": 1.0, "brier": 1.0},
        "dp1": {"log_loss": 0.9, "brier": 1.1},
    }
    assert evaluation.frozen_decision(folds, pooled) == "INCONCLUSIVE_NO_TUNING"


def test_39_draw_diagnostics_do_not_affect_decision() -> None:
    folds = _decision_folds(3)
    pooled = {
        "dp0": {"log_loss": 1.0, "brier": 1.0, "accuracy": 0.99},
        "dp1": {"log_loss": 0.9, "brier": 0.9, "accuracy": 0.01},
        "draw_diagnostic": {"actual": [0, 999, 0]},
        "operational": {"log_loss": 999},
    }
    assert evaluation.frozen_decision(folds, pooled) == "CONTINUE_DRAW_PROPENSITY_LANE"


def test_40_draw_diagnostic_values_are_exact() -> None:
    labels = np.array([0, 1, 2, 1])
    dp0 = np.array([
        [0.8, 0.1, 0.1], [0.7, 0.2, 0.1],
        [0.1, 0.2, 0.7], [0.1, 0.3, 0.6],
    ])
    dp1 = np.array([
        [0.1, 0.8, 0.1], [0.1, 0.8, 0.1],
        [0.1, 0.1, 0.8], [0.6, 0.3, 0.1],
    ])
    result = evaluation._draw_diagnostic(labels, dp0, dp1)
    assert result["actual"] == [1, 2, 1]
    assert result["dp0_argmax"] == [2, 0, 2]
    assert result["dp1_argmax"] == [1, 2, 1]
    assert result["delta_mean_draw_probability"] == pytest.approx(0.3)


def test_41_existing_baseline_prediction_is_not_reused() -> None:
    assert evaluation.EXISTING_BASELINE_PREDICTION_REUSED is False


def test_42_2025_is_inaccessible(targets) -> None:
    assert int(targets.season.max()) == 2024
    assert not targets.season.eq(2025).any()


def test_43_2026_27_is_inaccessible(targets) -> None:
    assert set(targets.season.unique()) == set(range(2015, 2025))


def test_44_no_candidate_variants_are_present() -> None:
    assert evaluation.DP1_FEATURES == ("elo_diff", *MODEL_CANDIDATES)
    source = inspect.getsource(evaluation)
    assert "SimpleImputer" not in source
    assert "class_weight" not in source


def test_45_default_cli_runs_preflight_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(evaluation, "preflight", _preflight_result)
    monkeypatch.setattr(
        evaluation,
        "formal_evaluate",
        lambda **kwargs: pytest.fail("formal evaluation called by default CLI"),
    )
    assert evaluation.main([]) == 0
    output = capsys.readouterr().out
    assert evaluation.PREFLIGHT_STATUS in output
    assert "FORMAL_DRAW_PROPENSITY_EVALUATION_NOT_RUN" in output


@pytest.mark.parametrize("argv", [["--formal"], ["--confirm-one-shot"]])
def test_46_one_formal_flag_is_insufficient(monkeypatch, argv) -> None:
    monkeypatch.setattr(
        evaluation,
        "formal_evaluate",
        lambda **kwargs: pytest.fail("formal evaluation called with one flag"),
    )
    with pytest.raises(SystemExit):
        evaluation.main(argv)


def test_47_both_formal_flags_are_required(monkeypatch, capsys) -> None:
    calls = []
    monkeypatch.setattr(
        evaluation,
        "formal_evaluate",
        lambda **kwargs: calls.append(True) or {
            "status": "MOCK_FORMAL",
            "decision": "MOCK_DECISION",
        },
    )
    assert evaluation.main(["--formal", "--confirm-one-shot"]) == 0
    assert calls == [True]
    assert "MOCK_FORMAL" in capsys.readouterr().out


def test_48_renderer_is_deterministic_and_complete() -> None:
    result = _renderer_result()
    first = evaluation.render_evaluation_markdown(result)
    second = evaluation.render_evaluation_markdown(result)
    assert first == second
    for required in (
        "Artifact SHA gate",
        "A_Y baseline sanity",
        "Primary matched fold results",
        "Primary matched pooled result",
        "Operational full-validation diagnostic",
        "Draw diagnostics",
        "Final decision",
        "feature changes = **NO**",
        "parameter changes = **NO**",
        "tuning = **NOT RUN**",
        "adaptive follow-up = **NOT RUN**",
        "existing baseline prediction reused = **NO**",
    ):
        assert required in first


def test_49_preflight_status_and_gates_are_machine_readable(actual_preflight) -> None:
    assert actual_preflight.status == "PREFLIGHT_PASS"
    assert actual_preflight.schema_identity_gate == "PASS"
    assert actual_preflight.eligible_counts_gate == "PASS"
    assert actual_preflight.a_y_gate == "PASS"


def test_50_tests_do_not_create_or_modify_formal_result_document() -> None:
    if _FORMAL_DOC_INITIAL_BYTES is None:
        assert not evaluation.EVALUATION_DOC_PATH.exists()
    else:
        assert evaluation.EVALUATION_DOC_PATH.read_bytes() == _FORMAL_DOC_INITIAL_BYTES
