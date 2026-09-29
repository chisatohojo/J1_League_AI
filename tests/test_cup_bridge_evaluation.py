from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.modeling import cup_bridge_evaluation as evaluation
from src.modeling import player_workload_evaluation as known_good


@pytest.fixture(scope="module")
def artifacts() -> tuple[pd.DataFrame, pd.DataFrame]:
    return evaluation._read_artifacts(evaluation.CANDIDATE_PATH, evaluation.RESULT_PATH)


@pytest.fixture(scope="module")
def actual_context() -> evaluation._PreflightContext:
    # This intentionally stops after A/B.  It creates C's static event stream,
    # but never replays, fits, predicts, scores, decides, or writes for C.
    return evaluation._preflight_context()


def _model_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = pd.DataFrame({
        "match_id": [f"m{i}" for i in range(9)],
        "event_key": [f"j1:m{i}" for i in range(9)],
        "season": [2019] * 6 + [2020] * 3,
        "elo_diff": np.arange(9, dtype=float) - 4,
        "result": [0, 1, 2, 0, 1, 2, 0, 1, 2],
    })
    return frame.iloc[:6].copy(), frame.iloc[6:].copy()


def _event(
    key: str,
    date: str,
    home: str,
    away: str,
    result: int,
    event_type: str,
) -> dict:
    return {
        "event_key": key,
        "season": 2020,
        "match_date": pd.Timestamp(date),
        "home_team_id": home,
        "away_team_id": away,
        "result": result,
        "event_type": event_type,
        "home_advantage": evaluation.EVENT_HOME_ADVANTAGE[event_type],
    }


def _target(key: str, date: str, home: str = "a", away: str = "b") -> pd.DataFrame:
    return pd.DataFrame([{
        "match_id": key.removeprefix("j1:"),
        "event_key": key,
        "season": 2020,
        "match_date": pd.Timestamp(date),
        "home_team_id": home,
        "away_team_id": away,
        "result": 1,
    }])


def _variant(metrics: dict[str, float]) -> dict:
    probabilities = np.full((1, 3), 1 / 3)
    folds = {
        year: {
            "train_n": 1,
            "validation_n": 1,
            "train_ids": ["train"],
            "validation_ids": [f"v{year}"],
            "labels": np.array([1]),
            "probabilities": probabilities,
            "metrics": {**metrics, "count": 1},
        }
        for year in evaluation.FOLDS
    }
    return {
        "folds": folds,
        "pooled_labels": np.array([1]),
        "pooled_probabilities": probabilities,
        "pooled": {**metrics, "count": 1},
    }


# Freeze spec section 16.1
def test_01_candidate_sha_mismatch_blocks_before_any_fit(tmp_path, monkeypatch) -> None:
    wrong = tmp_path / "candidate.csv"
    wrong.write_bytes(b"not the frozen candidate")
    monkeypatch.setattr(evaluation, "_fit", lambda *args, **kwargs: pytest.fail("fit called"))
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="BLOCKED_ARTIFACT_MISMATCH"):
        evaluation.preflight(candidate_path=wrong)


def test_02_result_sha_mismatch_blocks_before_any_fit(tmp_path, monkeypatch) -> None:
    wrong = tmp_path / "result.csv"
    wrong.write_bytes(b"not the frozen result")
    monkeypatch.setattr(evaluation, "_fit", lambda *args, **kwargs: pytest.fail("fit called"))
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="BLOCKED_ARTIFACT_MISMATCH"):
        evaluation.preflight(result_path=wrong)


# Section 16.2
def test_03_exact_schemas_counts_distribution_and_keys(artifacts) -> None:
    candidate, result = artifacts
    cup = evaluation.validate_cup_artifacts(candidate, result)
    assert tuple(candidate.columns) == evaluation.CANDIDATE_COLUMNS
    assert tuple(result.columns) == evaluation.RESULT_COLUMNS
    assert len(candidate) == len(result) == len(cup) == 145
    assert candidate.candidate_key.is_unique and result.candidate_key.is_unique
    assert candidate.competition.value_counts().to_dict() == evaluation.EXPECTED_COMPETITION_COUNTS


# Section 16.3
def test_04_manifest_result_ordered_identity_mismatch_fails(artifacts) -> None:
    candidate, result = artifacts
    changed = result.copy()
    changed.loc[0, "home_team_id"] = "team_wrong"
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="identity mismatch"):
        evaluation.validate_cup_artifacts(candidate, changed)


# Section 16.4
def test_05_regulation_score_result_and_zero_unresolved(artifacts) -> None:
    candidate, result = artifacts
    changed = result.copy()
    changed.loc[0, "regulation_result"] = "2" if result.loc[0, "regulation_result"] != "2" else "0"
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="disagrees"):
        evaluation.validate_cup_artifacts(candidate, changed)
    changed = result.copy()
    changed.loc[0, "resolution_status"] = "UNRESOLVED"
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="unresolved"):
        evaluation.validate_cup_artifacts(candidate, changed)


# Section 16.5
def test_06_forbidden_cup_season_and_competition_are_rejected(artifacts) -> None:
    candidate, result = artifacts
    for column, value, message in (("season", "2025", "Forbidden"), ("competition", "afc", "competition distribution")):
        changed, changed_result = candidate.copy(), result.copy()
        changed.loc[0, column] = value
        changed_result.loc[0, column] = value
        with pytest.raises(evaluation.CupBridgeEvaluationError, match=message):
            evaluation.validate_cup_artifacts(changed, changed_result)


def test_07_forbidden_league_season_is_rejected() -> None:
    frame = pd.DataFrame([{
        "match_id": "x", "event_key": "j2:x", "season": 2025,
        "match_date": "2025-01-01", "home_team_id": "a",
        "away_team_id": "b", "result": 1,
    }])
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="Forbidden j2 season"):
        evaluation._validate_league_source(frame, "j2", 1)


# Section 16.6
def test_08_a_b_c_fold_rows_and_labels_must_be_identical() -> None:
    train, validation = _model_frames()
    combined = pd.concat([train, validation], ignore_index=True)
    evaluation.assert_same_fold_inputs(combined, combined.copy(), combined.copy())
    changed = combined.copy()
    changed.loc[0, "result"] = 2
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="result"):
        evaluation.assert_same_fold_inputs(combined, combined.copy(), changed)


# Section 16.7
def test_09_fold_and_pooled_counts_are_exact(actual_context) -> None:
    assert actual_context.public.fold_counts == evaluation.EXPECTED_FOLD_COUNTS
    assert sum(value[1] for value in actual_context.public.fold_counts.values()) == 1678
    assert actual_context.public.source_counts == {"j1": 3208, "j2": 4538, "cup": 145}


# Section 16.8
def test_10_class_and_probability_order_is_exact() -> None:
    train, validation = _model_frames()
    probabilities = evaluation._fit(train, validation)
    assert evaluation.CLASS_ORDER == (0, 1, 2)
    assert probabilities.shape == (3, 3)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


# Section 16.9
def test_11_uniform_three_class_brier_is_two_thirds() -> None:
    probabilities = np.full((3, 3), 1 / 3)
    assert known_good._metrics(np.array([0, 1, 2]), probabilities).brier == 2 / 3


# Section 16.10
def test_12_scaler_and_logistic_fit_training_rows_only(monkeypatch) -> None:
    train, validation = _model_frames()
    scaler_fits, logistic_fits = [], []

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
    evaluation._fit(train, validation)
    assert len(scaler_fits) == len(logistic_fits) == 1
    assert len(scaler_fits[0][0]) == len(logistic_fits[0][0]) == len(train)
    np.testing.assert_array_equal(scaler_fits[0][1], train.result.to_numpy())
    np.testing.assert_array_equal(logistic_fits[0][1], train.result.to_numpy())
    assert set(scaler_fits[0][0][:, 0]) == set(train.elo_diff)
    assert not set(scaler_fits[0][0][:, 0]) & set(validation.elo_diff)


# Section 16.11-12
def test_13_frozen_elo_constants_and_event_home_advantages() -> None:
    assert evaluation.INITIAL_RATING == 1500.0
    assert evaluation.K_FACTOR == 30.0
    assert evaluation.EVENT_HOME_ADVANTAGE == {
        "j1": 175.0, "j2": 175.0, "jleague_cup": 0.0, "emperors_cup": 0.0,
    }


# Section 16.13
def test_14_cup_regulation_result_not_final_or_pk_drives_updates(artifacts) -> None:
    candidate, result = artifacts
    changed = result.copy()
    changed["final_home_score"] = "999"
    changed["final_away_score"] = "0"
    changed["extra_time_played"] = "True"
    changed["penalty_shootout_played"] = "True"
    original_cup = evaluation.validate_cup_artifacts(candidate, result)
    changed_cup = evaluation.validate_cup_artifacts(candidate, changed)
    pd.testing.assert_series_equal(original_cup.result, changed_cup.result)


# Section 16.14
def test_15_same_date_events_are_conservatively_batched() -> None:
    j1 = pd.concat([_target("j1:one", "2020-01-01"), _target("j1:two", "2020-01-01")], ignore_index=True)
    stream = pd.DataFrame([
        _event("j1:one", "2020-01-01", "a", "b", 2, "j1"),
        _event("j1:two", "2020-01-01", "a", "b", 0, "j1"),
    ])
    features = evaluation._replay_features(j1, stream).set_index("event_key")
    assert features.loc["j1:one", "elo_diff"] == 0.0
    assert features.loc["j1:two", "elo_diff"] == 0.0


def test_16_same_team_multiple_events_on_date_hard_fails() -> None:
    j1 = pd.concat([_target("j1:one", "2020-01-01"), _target("j1:two", "2020-01-01")], ignore_index=True)
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="multiple combined stream"):
        evaluation._make_stream(j1)


# Section 16.15
def test_17_same_date_cup_cannot_change_j1_target_feature() -> None:
    j1 = _target("j1:target", "2020-01-01")
    stream = pd.DataFrame([
        _event("emperors_cup:cup", "2020-01-01", "a", "b", 2, "emperors_cup"),
        _event("j1:target", "2020-01-01", "a", "b", 1, "j1"),
    ])
    assert evaluation._replay_features(j1, stream).iloc[0].elo_diff == 0.0


# Section 16.16
def test_18_only_strictly_prior_cup_can_change_later_target() -> None:
    j1 = _target("j1:target", "2020-01-02")
    stream = pd.DataFrame([
        _event("emperors_cup:cup", "2020-01-01", "a", "b", 2, "emperors_cup"),
        _event("j1:target", "2020-01-02", "a", "b", 1, "j1"),
    ])
    assert evaluation._replay_features(j1, stream).iloc[0].elo_diff == pytest.approx(30.0)


# Section 16.17 and 16.19
def test_19_fresh_a_and_b_references_pass(actual_context) -> None:
    assert actual_context.public.status == evaluation.READY_STATUS
    assert actual_context.public.a_reference == "PASS"
    assert actual_context.public.b_reference == "PASS"
    evaluation.assert_a_reference(actual_context.variants["a"])
    evaluation.assert_b_reference(actual_context.variants["b"])


# Section 16.18
def test_20_a_mismatch_blocks_b_c_metrics_and_decision(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(evaluation, "_evaluate_variant", lambda frame: calls.append("fit/evaluate") or {})
    monkeypatch.setattr(
        evaluation, "assert_a_reference",
        lambda result: (_ for _ in ()).throw(evaluation.CupBridgeEvaluationError("BLOCKED_REFERENCE_MISMATCH: A")),
    )
    monkeypatch.setattr(evaluation, "assert_b_reference", lambda result: pytest.fail("B reference called"))
    monkeypatch.setattr(evaluation, "frozen_decision", lambda *args: pytest.fail("decision called"))
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation._preflight_context()
    assert calls == ["fit/evaluate"]


# Section 16.20
def test_21_b_mismatch_blocks_c_metrics_and_decision(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(evaluation, "_evaluate_variant", lambda frame: calls.append("fit/evaluate") or {})
    monkeypatch.setattr(evaluation, "assert_a_reference", lambda result: None)
    monkeypatch.setattr(evaluation, "_assert_evaluation_rows_equal", lambda *args: None)
    monkeypatch.setattr(
        evaluation, "assert_b_reference",
        lambda result: (_ for _ in ()).throw(evaluation.CupBridgeEvaluationError("BLOCKED_REFERENCE_MISMATCH: B")),
    )
    monkeypatch.setattr(evaluation, "_formal_from_context", lambda context: pytest.fail("C called"))
    monkeypatch.setattr(evaluation, "frozen_decision", lambda *args: pytest.fail("decision called"))
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation._preflight_context()
    assert calls == ["fit/evaluate", "fit/evaluate"]


# Section 16.21
def test_22_c_differs_from_b_only_by_frozen_145_events(actual_context) -> None:
    b_keys = set(actual_context.b_stream.event_key)
    c_keys = set(actual_context.c_stream.event_key)
    assert c_keys - b_keys == set(actual_context.cup.event_key)
    assert len(c_keys) - len(b_keys) == 145
    assert not any(key.startswith(("jleague_cup:", "emperors_cup:")) for key in b_keys)


# Section 16.22
def test_23_pooled_metric_is_once_over_concatenated_rows() -> None:
    first_p = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]])
    second_p = np.array([[1 / 3, 1 / 3, 1 / 3]])
    first_y, second_y = np.array([0, 1]), np.array([2])
    pooled = known_good._metrics(np.concatenate([first_y, second_y]), np.concatenate([first_p, second_p]))
    fold_average = np.mean([
        known_good._metrics(first_y, first_p).log_loss,
        known_good._metrics(second_y, second_p).log_loss,
    ])
    assert pooled.count == 3
    assert pooled.log_loss != fold_average


# Section 16.23; exercise only a synthetic formal context.
def test_24_fold_and_pooled_c_b_and_c_a_deltas_are_retained(monkeypatch) -> None:
    a = _variant({"accuracy": 0.4, "log_loss": 1.0, "brier": 0.7})
    b = _variant({"accuracy": 0.5, "log_loss": 0.9, "brier": 0.6})
    c = _variant({"accuracy": 0.6, "log_loss": 0.8, "brier": 0.5})
    context = evaluation._PreflightContext(
        evaluation.PreflightResult("READY", {}, {}, {}, "PASS", "PASS"),
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
        pd.DataFrame({"match_date": pd.to_datetime([])}), {"a": a, "b": b},
    )
    monkeypatch.setattr(evaluation, "_replay_features", lambda *args: pd.DataFrame())
    monkeypatch.setattr(evaluation, "_a_features", lambda *args: pd.DataFrame())
    monkeypatch.setattr(evaluation, "assert_same_fold_inputs", lambda *args: None)
    monkeypatch.setattr(evaluation, "_assert_evaluation_rows_equal", lambda *args: None)
    monkeypatch.setattr(evaluation, "_evaluate_variant", lambda *args: c)
    monkeypatch.setattr(evaluation, "_promotion_diagnostics", lambda *args: {})
    result = evaluation._formal_from_context(context)
    assert result["pooled"]["c_minus_b"]["log_loss"] == pytest.approx(-0.1)
    assert result["pooled"]["c_minus_a"]["brier"] == pytest.approx(-0.2)
    assert all("c_minus_b" in result["folds"][year] and "c_minus_a" in result["folds"][year] for year in evaluation.FOLDS)


# Section 16.24
@pytest.mark.parametrize(
    ("improved", "c_ll", "c_brier", "expected"),
    [
        (3, 0.9, 0.9, "ADOPT_CUP_BRIDGED_ELO"),
        (2, 1.1, 1.1, "CLOSE_CUP_BRIDGE_LANE"),
        (3, 0.9, 1.1, "INCONCLUSIVE_NO_TUNING"),
    ],
)
def test_25_all_three_decision_branches_are_exact(improved, c_ll, c_brier, expected) -> None:
    a_folds = {year: {"log_loss": 1.0} for year in evaluation.FOLDS}
    c_folds = {
        year: {"log_loss": 0.9 if index < improved else 1.1}
        for index, year in enumerate(evaluation.FOLDS)
    }
    assert evaluation.frozen_decision(
        a_folds, {"log_loss": 1.0, "brier": 1.0},
        c_folds, {"log_loss": c_ll, "brier": c_brier},
    ) == expected


# Section 16.25
def test_26_diagnostics_accuracy_and_c_b_cannot_change_decision() -> None:
    a_folds = {year: {"log_loss": 1.0, "diagnostic": -999} for year in evaluation.FOLDS}
    c_folds = {year: {"log_loss": 0.9, "diagnostic": 999} for year in evaluation.FOLDS}
    first = evaluation.frozen_decision(
        a_folds, {"log_loss": 1.0, "brier": 1.0, "accuracy": 0.99, "c_minus_b": 999},
        c_folds, {"log_loss": 0.9, "brier": 0.9, "accuracy": 0.01, "c_minus_b": -999},
    )
    second = evaluation.frozen_decision(
        a_folds, {"log_loss": 1.0, "brier": 1.0, "accuracy": 0.01, "c_minus_b": -999},
        c_folds, {"log_loss": 0.9, "brier": 0.9, "accuracy": 0.99, "c_minus_b": 999},
    )
    assert first == second == "ADOPT_CUP_BRIDGED_ELO"


def test_27_preflight_never_replays_c(monkeypatch, actual_context) -> None:
    assert actual_context.public.status == evaluation.READY_STATUS
    original = evaluation._preflight_context
    # The public entry point must return the context's public result only; its
    # implementation has no call to _formal_from_context.
    monkeypatch.setattr(evaluation, "_preflight_context", lambda **kwargs: actual_context)
    monkeypatch.setattr(evaluation, "_formal_from_context", lambda context: pytest.fail("formal C called"))
    assert evaluation.preflight().status == evaluation.READY_STATUS
    assert original is not evaluation._preflight_context


def test_28_default_cli_and_unconfirmed_formal_do_not_run_c(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(evaluation, "formal_evaluate", lambda **kwargs: calls.append("formal"))
    assert evaluation.main([]) == 0
    with pytest.raises(SystemExit):
        evaluation.main(["--formal"])
    assert calls == []


def test_29_preflight_cli_reports_c_not_run(monkeypatch, capsys) -> None:
    result = evaluation.PreflightResult(evaluation.READY_STATUS, {}, {}, {}, "PASS", "PASS")
    monkeypatch.setattr(evaluation, "preflight", lambda: result)
    monkeypatch.setattr(evaluation, "formal_evaluate", lambda **kwargs: pytest.fail("formal C called"))
    assert evaluation.main(["--preflight"]) == 0
    assert "FORMAL_C=NOT_RUN" in capsys.readouterr().out


def test_30_formal_entry_gate_failure_prevents_c_and_report(monkeypatch, tmp_path) -> None:
    report = tmp_path / "report.md"
    monkeypatch.setattr(
        evaluation, "_preflight_context",
        lambda **kwargs: (_ for _ in ()).throw(evaluation.CupBridgeEvaluationError("BLOCKED_REFERENCE_MISMATCH")),
    )
    monkeypatch.setattr(evaluation, "_formal_from_context", lambda context: pytest.fail("C called"))
    monkeypatch.setattr(evaluation, "EVALUATION_DOC_PATH", report)
    with pytest.raises(evaluation.CupBridgeEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation.formal_evaluate()
    assert not report.exists()


def test_31_formal_result_document_has_not_been_created() -> None:
    assert not Path(evaluation.EVALUATION_DOC_PATH).exists()
