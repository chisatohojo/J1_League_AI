import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import src.modeling.model_architecture_evaluation as evaluation
from src.collect.teams import load_team_master


def _source() -> pd.DataFrame:
    team_ids = sorted({alias.team_id for alias in load_team_master().aliases})[:20]
    rows = []
    number = 0
    scores = ((0, 1), (1, 1), (2, 0))
    for season, count in evaluation.EXPECTED_SEASON_COUNTS.items():
        remaining = count
        day_number = 0
        while remaining:
            games = min(remaining, 10)
            day = (pd.Timestamp(f"{season}-01-01") + pd.Timedelta(days=day_number)).strftime(
                "%Y-%m-%d"
            )
            for game in range(games):
                home_score, away_score = scores[number % 3]
                rows.append(
                    {
                        "season": season,
                        "match_id": f"synthetic_{number:04d}",
                        "match_date": pd.Timestamp(day),
                        "home_team_id": team_ids[2 * game],
                        "away_team_id": team_ids[2 * game + 1],
                        "home_score": home_score,
                        "away_score": away_score,
                        "result": 0 if home_score < away_score else 1 if home_score == away_score else 2,
                    }
                )
                number += 1
            remaining -= games
            day_number += 1
    return pd.DataFrame(rows, columns=evaluation.SOURCE_COLUMNS).sort_values(
        ["match_date", "match_id"], kind="stable"
    ).reset_index(drop=True)


@pytest.fixture(scope="module")
def synthetic_source():
    return _source()


@pytest.fixture(scope="module")
def synthetic_state(synthetic_source):
    return evaluation.build_shared_state(synthetic_source)


def test_source_validation_exact_population_and_no_mutation(synthetic_source):
    candidate = synthetic_source.copy(deep=True)
    original = candidate.copy(deep=True)
    evaluation.validate_source(candidate)
    assert len(candidate) == 3208
    assert candidate["season"].value_counts().sort_index().to_dict() == (
        evaluation.EXPECTED_SEASON_COUNTS
    )
    assert_frame_equal(candidate, original, check_exact=True)


def test_source_loader_requests_exactly_2015_through_2024_and_never_2025(
    monkeypatch, synthetic_source
):
    requested = []
    real_master = load_team_master()

    class AlreadyResolvedMaster:
        aliases = real_master.aliases

        def add_team_ids(self, frame):
            return frame.copy(deep=True)

    def load(path):
        season = int(Path(path).name.split("_", 1)[0])
        requested.append(season)
        return synthetic_source.loc[synthetic_source["season"].eq(season)].copy(deep=True)

    monkeypatch.setattr(evaluation, "load_matches", load)
    result = evaluation.load_retrospective_source(
        "unused", team_master=AlreadyResolvedMaster()
    )
    assert requested == list(range(2015, 2025))
    assert 2025 not in requested
    assert_frame_equal(result, synthetic_source, check_exact=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.iloc[:-1].copy(), "exactly 3208"),
        (lambda frame: frame.assign(season=2015), "Season coverage mismatch"),
        (lambda frame: frame.assign(match_id=""), "nonblank"),
        (lambda frame: frame.assign(match_id="duplicate"), "unique"),
        (lambda frame: frame.assign(home_team_id="team_unknown"), "unknown TeamMaster"),
        (lambda frame: frame.assign(home_team_id=frame["away_team_id"]), "must differ"),
        (lambda frame: frame.assign(home_score=-1), "nonnegative"),
        (lambda frame: frame.assign(home_score=frame["home_score"].astype(float) + 0.5), "integers"),
        (lambda frame: frame.assign(result=4), "0, 1, or 2"),
        (lambda frame: frame.assign(result=2), "contradiction"),
        (lambda frame: frame.assign(match_date="not-a-date"), "match_date must be valid"),
        (lambda frame: frame.iloc[[1, 0, *range(2, len(frame))]].copy(), "canonical"),
        (lambda frame: frame.assign(season=np.where(frame.index == len(frame) - 1, 2025, frame["season"])), "Season coverage"),
    ],
)
def test_source_validation_rejects_contract_violations(synthetic_source, mutation, message):
    with pytest.raises(evaluation.ArchitectureEvaluationError, match=message):
        evaluation.validate_source(mutation(synthetic_source.copy(deep=True)))


def test_source_validation_rejects_same_team_twice_on_one_date(synthetic_source):
    candidate = synthetic_source.copy(deep=True)
    candidate.loc[1, "home_team_id"] = candidate.loc[0, "home_team_id"]
    with pytest.raises(evaluation.ArchitectureEvaluationError, match="more than once"):
        evaluation.validate_source(candidate)


def _small_chronology() -> pd.DataFrame:
    ids = sorted({alias.team_id for alias in load_team_master().aliases})[:8]
    return pd.DataFrame(
        [
            (2022, "m1", "2022-12-30", ids[0], ids[1], 2, 0, 2),
            (2023, "m2", "2023-01-05", ids[0], ids[1], 1, 1, 1),
            (2023, "m3", "2023-01-05", ids[2], ids[3], 0, 1, 0),
            (2023, "m4", "2023-08-01", ids[0], ids[1], 0, 1, 0),
        ],
        columns=evaluation.SOURCE_COLUMNS,
    ).assign(match_date=lambda frame: pd.to_datetime(frame["match_date"]))


def test_shared_elo_full_stream_initial_no_reset_validation_history_and_no_target_leakage():
    matches = _small_chronology()
    state = evaluation.build_shared_state(matches, validate_population=False)
    assert state.loc[0, "elo_diff"] == 0.0
    assert state.loc[1, "elo_diff"] > 0.0  # 2022 state continues into 2023.
    assert state.loc[3, "elo_diff"] != state.loc[1, "elo_diff"]  # Earlier 2023 result applied.

    changed = matches.copy(deep=True)
    changed.loc[3, ["home_score", "away_score", "result"]] = [9, 0, 2]
    changed_state = evaluation.build_shared_state(changed, validate_population=False)
    assert changed_state.loc[3, "elo_diff"] == state.loc[3, "elo_diff"]

    peer_changed = matches.copy(deep=True)
    peer_changed.loc[2, ["home_score", "away_score", "result"]] = [5, 0, 2]
    peer_state = evaluation.build_shared_state(peer_changed, validate_population=False)
    assert peer_state.loc[1, "elo_diff"] == state.loc[1, "elo_diff"]


def test_g_form_is_built_on_full_stream_before_split_and_is_strictly_prior():
    matches = _small_chronology()
    state = evaluation.build_shared_state(matches, validate_population=False)
    assert tuple(state.columns[-len(evaluation.G_FEATURES) :]) == evaluation.G_FEATURES
    assert state.loc[0, "home_last5_matches_available"] == 0
    assert state.loc[1, "home_last5_matches_available"] == 1
    assert state.loc[1, "home_last5_points"] == 3
    assert state.loc[3, "home_last5_matches_available"] == 2
    assert state.loc[3, "home_last5_points"] == 4

    changed = matches.copy(deep=True)
    changed.loc[3, ["home_score", "away_score", "result"]] = [9, 0, 2]
    changed_state = evaluation.build_shared_state(changed, validate_population=False)
    assert_frame_equal(
        state.loc[[3], list(evaluation.G_FEATURES)].reset_index(drop=True),
        changed_state.loc[[3], list(evaluation.G_FEATURES)].reset_index(drop=True),
        check_exact=True,
    )
    peer_changed = matches.copy(deep=True)
    peer_changed.loc[2, ["home_score", "away_score", "result"]] = [5, 0, 2]
    peer_state = evaluation.build_shared_state(peer_changed, validate_population=False)
    assert_frame_equal(
        state.loc[[1], list(evaluation.G_FEATURES)].reset_index(drop=True),
        peer_state.loc[[1], list(evaluation.G_FEATURES)].reset_index(drop=True),
        check_exact=True,
    )


def test_exact_frozen_fold_contract(synthetic_state):
    assert evaluation.validate_fold_contract(synthetic_state) == evaluation.EXPECTED_FOLD_COUNTS
    assert sum(value[1] for value in evaluation.EXPECTED_FOLD_COUNTS.values()) == 1678


def test_candidate_a_exact_pipeline_fit_class_order_and_probabilities(synthetic_state):
    model = evaluation.build_candidate_a()
    assert isinstance(model, Pipeline)
    assert tuple(model.named_steps) == ("scaler", "logistic")
    assert isinstance(model.named_steps["scaler"], StandardScaler)
    assert isinstance(model.named_steps["logistic"], LogisticRegression)
    assert model.named_steps["logistic"].get_params(deep=False)["C"] == 1.0
    assert model.named_steps["logistic"].get_params(deep=False)["solver"] == "lbfgs"
    assert model.named_steps["logistic"].get_params(deep=False)["max_iter"] == 1000
    assert model.named_steps["logistic"].get_params(deep=False)["random_state"] == 0
    train = synthetic_state.iloc[:180]
    validation = synthetic_state.iloc[180:190]
    probabilities = evaluation._fit_predict_a(train, validation)
    assert probabilities.shape == (10, 3)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)


def test_a_reference_constants_and_gate_without_real_preflight():
    result = {
        "folds": {
            year: {"metrics": {"log_loss": value}}
            for year, value in evaluation.EXPECTED_A_FOLD_LOG_LOSS.items()
        },
        "pooled": dict(evaluation.EXPECTED_A_POOLED),
    }
    evaluation.assert_a_reference(result)
    result["folds"][2020]["metrics"]["log_loss"] += 2e-12
    with pytest.raises(evaluation.ArchitectureEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation.assert_a_reference(result)


def _uniform_result(data: pd.DataFrame) -> dict:
    folds, labels, probabilities = {}, [], []
    for year in evaluation.FOLDS:
        train, validation = evaluation._fold_frames(data, year)
        p = np.full((len(validation), 3), 1.0 / 3.0)
        fold = evaluation._fold_output(train, validation, p)
        folds[year] = fold
        labels.append(fold["labels"])
        probabilities.append(fold["probabilities"])
    return evaluation._finish_candidate(folds, labels, probabilities)


def test_p_adapter_calls_frozen_fit_predict_and_preserves_identity(monkeypatch, synthetic_state):
    calls = {"fit": 0, "predict": 0}
    a_result = _uniform_result(synthetic_state)

    def fit(train):
        calls["fit"] += 1
        assert "elo_diff" in train
        return object()

    def predict(_model, validation):
        calls["predict"] += 1
        return pd.DataFrame(
            {
                "match_id": validation["match_id"].to_numpy(copy=True),
                "p_away": 1 / 3,
                "p_draw": 1 / 3,
                "p_home": 1 / 3,
            }
        )

    monkeypatch.setattr(evaluation, "fit_poisson_model", fit)
    monkeypatch.setattr(evaluation, "predict_p_proba", predict)
    result = evaluation._evaluate_p(synthetic_state, a_result)
    assert calls == {"fit": 5, "predict": 5}
    assert result["pooled"]["count"] == 1678
    assert result["pooled_ids"] == a_result["pooled_ids"]


def test_p_convergence_warning_is_candidate_failure_without_retry(monkeypatch, synthetic_state):
    calls = 0

    def fit(_train):
        nonlocal calls
        calls += 1
        warnings.warn("did not converge", ConvergenceWarning)
        return object()

    monkeypatch.setattr(evaluation, "fit_poisson_model", fit)
    with pytest.raises(evaluation.CandidateEvaluationFailure, match="Candidate P"):
        evaluation._evaluate_p(synthetic_state, _uniform_result(synthetic_state))
    assert calls == 1


def test_g_adapter_calls_frozen_fit_predict_exact_features_and_identity(monkeypatch, synthetic_state):
    calls = {"fit": 0, "predict": 0}
    a_result = _uniform_result(synthetic_state)

    def fit(train):
        calls["fit"] += 1
        assert tuple(train.loc[:, list(evaluation.G_FEATURES)].columns) == evaluation.G_FEATURES
        return object()

    def predict(_model, validation):
        calls["predict"] += 1
        assert tuple(validation.columns) == ("match_id", *evaluation.G_FEATURES)
        return pd.DataFrame(
            {
                "match_id": validation["match_id"].to_numpy(copy=True),
                "p_away": 1 / 3,
                "p_draw": 1 / 3,
                "p_home": 1 / 3,
            }
        )

    monkeypatch.setattr(evaluation, "fit_lightgbm_model", fit)
    monkeypatch.setattr(evaluation, "predict_g_proba", predict)
    result = evaluation._evaluate_g(synthetic_state, a_result)
    assert calls == {"fit": 5, "predict": 5}
    assert result["pooled_ids"] == a_result["pooled_ids"]


def test_exact_metrics_and_probability_tolerance():
    labels = np.array([0, 1, 2])
    probabilities = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1], [0.1, 0.1, 0.8]])
    metrics = evaluation.calculate_metrics(labels, probabilities)
    assert metrics.accuracy == 1.0
    assert metrics.log_loss == pytest.approx(-np.log(0.8), rel=0.0, abs=1e-15)
    assert metrics.brier == pytest.approx(0.06, rel=0.0, abs=1e-15)
    valid = probabilities.copy()
    valid[0, 0] += 5e-13
    evaluation.validate_probabilities(valid)
    invalid = probabilities.copy()
    invalid[0, 0] += 2e-12
    with pytest.raises(evaluation.ArchitectureEvaluationError, match="Invalid probability"):
        evaluation.validate_probabilities(invalid)


def _decision_metrics(ll, brier):
    return {"accuracy": 0.5, "log_loss": ll, "brier": brier, "count": 10}


@pytest.mark.parametrize(
    ("candidate_ll", "improved_folds", "candidate_brier", "failed", "expected"),
    [
        (0.9, 3, 0.6, False, evaluation.QUALIFIES),
        (1.1, 5, 0.6, False, evaluation.CLOSE),
        (0.9, 2, 0.6, False, evaluation.CLOSE),
        (0.9, 5, 0.8, False, evaluation.CLOSE),
        (0.9, 3, 0.7, False, evaluation.QUALIFIES),
        (0.9, 5, 0.6, True, evaluation.INCONCLUSIVE),
    ],
)
def test_frozen_individual_decision_rule(
    candidate_ll, improved_folds, candidate_brier, failed, expected
):
    a_folds = {year: _decision_metrics(1.0, 0.7) for year in evaluation.FOLDS}
    candidate_folds = {
        year: _decision_metrics(0.9 if index < improved_folds else 1.0, candidate_brier)
        for index, year in enumerate(evaluation.FOLDS)
    }
    decision, improved = evaluation.frozen_decision(
        a_folds,
        _decision_metrics(1.0, 0.7),
        candidate_folds,
        _decision_metrics(candidate_ll, candidate_brier),
        failed=failed,
    )
    assert decision == expected
    assert improved == (0 if failed else improved_folds)


def _retention_entry(decision, ll=1.0, brier=0.7):
    return {"decision": decision, "pooled": _decision_metrics(ll, brier)}


@pytest.mark.parametrize(
    ("p", "g", "expected"),
    [
        (_retention_entry(evaluation.CLOSE), _retention_entry(evaluation.CLOSE), None),
        (_retention_entry(evaluation.QUALIFIES), _retention_entry(evaluation.CLOSE), "P"),
        (_retention_entry(evaluation.CLOSE), _retention_entry(evaluation.QUALIFIES), "G"),
        (_retention_entry(evaluation.QUALIFIES, 0.8), _retention_entry(evaluation.QUALIFIES, 0.9), "P"),
        (_retention_entry(evaluation.QUALIFIES, 0.9), _retention_entry(evaluation.QUALIFIES, 0.8), "G"),
        (_retention_entry(evaluation.QUALIFIES, 0.8, 0.6), _retention_entry(evaluation.QUALIFIES, 0.8, 0.7), "P"),
        (_retention_entry(evaluation.QUALIFIES, 0.8, 0.7), _retention_entry(evaluation.QUALIFIES, 0.8, 0.6), "G"),
        (_retention_entry(evaluation.QUALIFIES, 0.8, 0.6), _retention_entry(evaluation.QUALIFIES, 0.8, 0.6), "P"),
        (
            _retention_entry(evaluation.QUALIFIES, 0.8, 0.7),
            _retention_entry(evaluation.QUALIFIES, 0.8 + 5e-13, 0.6),
            "G",
        ),
        (
            _retention_entry(evaluation.QUALIFIES, 0.8, 0.6 + 5e-13),
            _retention_entry(evaluation.QUALIFIES, 0.8, 0.6),
            "P",
        ),
    ],
)
def test_retention_rule(p, g, expected):
    assert evaluation.retained_candidate(p, g) == expected


def _context(data: pd.DataFrame) -> evaluation._PreflightContext:
    a_result = _uniform_result(data)
    public = evaluation.PreflightResult(
        status=evaluation.PREFLIGHT_STATUS,
        source_rows=3208,
        season_counts=evaluation.EXPECTED_SEASON_COUNTS,
        fold_counts=evaluation.EXPECTED_FOLD_COUNTS,
        pooled_validation_rows=1678,
        source_gate="PASS",
        chronology_gate="PASS",
        candidate_schema_gate="PASS",
        a_reference_gate="PASS",
        a_fold_log_loss={year: a_result["folds"][year]["metrics"]["log_loss"] for year in evaluation.FOLDS},
        a_pooled=a_result["pooled"],
    )
    return evaluation._PreflightContext(public, data, a_result)


def test_preflight_orchestration_creates_no_marker_or_report(monkeypatch, synthetic_state, tmp_path):
    context = _context(synthetic_state)
    monkeypatch.setattr(evaluation, "_preflight_context", lambda **_kwargs: context)
    marker = tmp_path / "attempt.json"
    report = tmp_path / "result.md"
    assert evaluation.preflight().status == evaluation.PREFLIGHT_STATUS
    assert not marker.exists() and not report.exists()


def test_cli_formal_requires_both_explicit_flags():
    with pytest.raises(SystemExit):
        evaluation.main(["--formal"])
    with pytest.raises(SystemExit):
        evaluation.main(["--confirm-one-shot"])


def test_formal_marker_exists_before_candidates_and_success_report_is_exclusive(
    monkeypatch, synthetic_state, tmp_path
):
    context = _context(synthetic_state)
    monkeypatch.setattr(evaluation, "_preflight_context", lambda **_kwargs: context)
    marker = tmp_path / "attempt.json"
    report = tmp_path / "result.md"

    def runner(_data, _a):
        assert marker.is_file()
        return _uniform_result(synthetic_state)

    result = evaluation.formal_evaluate(
        marker_path=marker,
        result_path=report,
        p_runner=runner,
        g_runner=runner,
    )
    assert marker.is_file() and report.is_file()
    assert json.loads(marker.read_text(encoding="utf-8"))["one_shot"] is True
    assert result["formal_attempt_status"] == "ATTEMPTED_ONCE"
    report_text = report.read_text(encoding="utf-8")
    assert "## Source and folds" in report_text
    assert "## Candidate deltas vs A" in report_text
    assert "Retained candidate: **null**" in report_text
    assert "Feature changes = NO" in report_text
    assert "Tuning = NOT RUN" in report_text
    with pytest.raises(evaluation.ArchitectureEvaluationError, match="ALREADY_ATTEMPTED"):
        evaluation.formal_evaluate(
            marker_path=marker,
            result_path=tmp_path / "second.md",
            p_runner=runner,
            g_runner=runner,
        )
    with pytest.raises(evaluation.ArchitectureEvaluationError, match="already exists"):
        evaluation.write_evaluation_markdown(result, report)


def test_existing_report_refuses_before_marker(monkeypatch, synthetic_state, tmp_path):
    monkeypatch.setattr(evaluation, "_preflight_context", lambda **_kwargs: _context(synthetic_state))
    marker = tmp_path / "attempt.json"
    report = tmp_path / "result.md"
    report.write_text("existing", encoding="utf-8")
    with pytest.raises(evaluation.ArchitectureEvaluationError, match="already exists"):
        evaluation.formal_evaluate(marker_path=marker, result_path=report)
    assert not marker.exists()


def test_candidate_failure_is_inconclusive_continues_other_and_leaves_marker(
    monkeypatch, synthetic_state, tmp_path
):
    monkeypatch.setattr(evaluation, "_preflight_context", lambda **_kwargs: _context(synthetic_state))
    marker = tmp_path / "attempt.json"
    called = []

    def fail(_data, _a):
        called.append("P")
        raise evaluation.CandidateEvaluationFailure("synthetic failure")

    def pass_g(_data, _a):
        called.append("G")
        return _uniform_result(synthetic_state)

    result = evaluation.formal_evaluate(
        marker_path=marker,
        result_path=tmp_path / "unused.md",
        write_report=False,
        p_runner=fail,
        g_runner=pass_g,
    )
    assert called == ["P", "G"]
    assert result["P"]["decision"] == evaluation.INCONCLUSIVE
    assert result["G"]["status"] == "PASS"
    assert marker.is_file()
    with pytest.raises(evaluation.ArchitectureEvaluationError, match="ALREADY_ATTEMPTED"):
        evaluation.formal_evaluate(
            marker_path=marker,
            result_path=tmp_path / "second.md",
            write_report=False,
            p_runner=pass_g,
            g_runner=pass_g,
        )


def test_evaluator_source_has_no_operational_or_tuning_path():
    source = Path("src/modeling/model_architecture_evaluation.py").read_text(encoding="utf-8")
    for forbidden in (
        "architecture_poisson_artifact",
        "architecture_lightgbm_artifact",
        "model_architecture_prediction",
        "model_architecture_prospective.csv",
        "xg_challenger_prospective.csv",
        "2026_hyakunen",
        "2026_27",
        "range(2015, 2026)",
        "GridSearchCV",
        "RandomizedSearchCV",
        "Optuna",
        "lightgbm.cv",
        "feature_importance",
        "SHAP",
        "calibration",
    ):
        assert forbidden not in source
