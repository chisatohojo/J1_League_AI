from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.features.rolling_xg import (
    RollingXGError,
    build_rolling_xg_target_features,
    rolling_xg_history_audit,
)
from src.modeling.xg_challenger_artifact import ARTIFACT_VERSION, OUTPUT_DIR
from src.modeling.xg_challenger_prediction import (
    PREDICTION_COLUMNS,
    FrozenArtifacts,
    XGPredictionError,
    append_predictions,
    generate_prediction_records,
    persist_predictions,
    select_next_date_batch,
    validate_artifacts,
)
import src.modeling.xg_challenger_prediction as prediction_module


class FrozenScaler:
    def transform(self, values):
        return np.asarray(values, dtype=float)

    def fit(self, *_args, **_kwargs):
        raise AssertionError("prediction must not fit a scaler")


class FrozenModel:
    def __init__(self, probabilities):
        self.probabilities = np.asarray(probabilities, dtype=float)

    def predict_proba(self, values):
        return np.repeat(self.probabilities[None, :], len(values), axis=0)

    def fit(self, *_args, **_kwargs):
        raise AssertionError("prediction must not fit a model")


def _artifacts():
    return FrozenArtifacts(
        metadata={}, artifact_hash="a" * 64,
        x0_scaler=FrozenScaler(), x0_model=FrozenModel([0.2, 0.3, 0.5]),
        x1_scaler=FrozenScaler(), x1_model=FrozenModel([0.1, 0.25, 0.65]),
    )


def _schedule():
    rows = [
        ("old", "2026-09-20", "19:00", "A", "B", "old", "completed"),
        ("n2", "2026-10-09", "19:00", "C", "D", "n2", "scheduled"),
        ("n1", "2026-10-09", "14:00", "A", "B", "n1", "scheduled"),
        ("later", "2026-10-10", "14:00", "A", "C", "later", "scheduled"),
    ]
    return pd.DataFrame(rows, columns=(
        "match_id", "match_date", "kickoff_time", "home_team", "away_team",
        "fixture_key", "status",
    ))


def _history():
    rows = []
    for index in range(5):
        rows.append({
            "competition": "j1_2025", "season": "2025", "match_id": f"h{index}",
            "match_date": f"2025-01-{index + 1:02d}",
            "home_team_id": "team_a", "away_team_id": "team_b",
            "home_xg": str(index + 1), "away_xg": "1",
            "xg_time_scope": "REGULATION",
        })
    return pd.DataFrame(rows)


def _targets(two=True):
    rows = [{
        "competition": "j1_2026_2027", "season": "2026/27", "match_id": "t1",
        "match_date": "2026-10-09", "kickoff": "19:00",
        "home_team_id": "team_a", "away_team_id": "team_b",
        "home_team_name": "A", "away_team_name": "B",
    }]
    if two:
        rows.append({**rows[0], "match_id": "t2", "home_team_id": "team_b",
                     "away_team_id": "team_a", "home_team_name": "B",
                     "away_team_name": "A"})
    return pd.DataFrame(rows)


def _joined_features(targets):
    feature_targets = targets[[
        "competition", "season", "match_id", "match_date", "home_team_id", "away_team_id",
    ]]
    return build_rolling_xg_target_features(_history(), feature_targets)


def test_next_date_batch_boundary_completed_and_later_exclusion():
    cohort, batch = select_next_date_batch(_schedule())
    assert cohort.match_id.tolist() == ["n1", "n2", "later"]
    assert batch.match_id.tolist() == ["n1", "n2"]
    assert batch.match_date.unique().tolist() == ["2026-10-09"]


def test_completed_prospective_row_stays_in_cohort_but_not_next_batch():
    schedule = _schedule()
    schedule.loc[schedule.match_id.eq("n1"), "status"] = "completed"
    cohort, batch = select_next_date_batch(schedule)
    assert "n1" in cohort.match_id.tolist()
    assert batch.match_id.tolist() == ["n2"]


def test_same_date_xg_targets_do_not_become_mutual_history():
    targets = _targets()
    featured = _joined_features(targets)
    audit = rolling_xg_history_audit(featured)
    assert featured.xg_pair_available.tolist() == [True, True]
    assert audit.home_history_match_ids.apply(set).tolist() == [
        {"h0", "h1", "h2", "h3", "h4"}, {"h0", "h1", "h2", "h3", "h4"},
    ]
    history_columns = ["home_history_match_ids", "away_history_match_ids"]
    assert not audit[history_columns].astype(str).apply(
        lambda column: column.str.contains("t1|t2")
    ).any().any()


def test_target_outcomes_are_rejected_and_future_xg_is_not_accepted():
    targets = _targets(False)
    targets["result"] = 2
    with pytest.raises(RollingXGError, match="must not expose"):
        build_rolling_xg_target_features(_history(), targets)
    history = _history()
    history.loc[0, "match_date"] = "2026-10-09"
    with pytest.raises(RollingXGError, match="strictly before"):
        build_rolling_xg_target_features(history, _targets(False).drop(columns=["kickoff", "home_team_name", "away_team_name"]))


def test_x1_eligible_and_x0_same_population_probability_contract():
    targets = _targets()
    features = _joined_features(targets)
    elo = pd.DataFrame({"match_id": targets.match_id, "elo_diff": [10.0, -10.0]})
    records = generate_prediction_records(targets, features, elo, _artifacts(), generated_at="now")
    assert len(records) == 2
    assert records.prediction_source.tolist() == ["X1", "X1"]
    assert records[["x0_p_away", "x0_p_draw", "x0_p_home"]].notna().all().all()
    assert records[["operational_p_away", "operational_p_draw", "operational_p_home"]].sum(axis=1).to_list() == pytest.approx([1, 1])
    assert records.predicted_class.tolist() == [2, 2]


def test_model_a_fallback_is_exact_and_x0_x1_raw_are_null():
    targets = _targets(False)
    features = _joined_features(targets)
    features.loc[:, "away_xg_available"] = False
    features.loc[:, "xg_pair_available"] = False
    features.loc[:, "away_xg_history_count"] = 4
    for column in ("away_last5_xg_for", "away_last5_xg_against"):
        features.loc[:, column] = pd.NA
    expected = np.array([[0.55, 0.25, 0.20]])
    records = generate_prediction_records(
        targets, features, pd.DataFrame({"match_id": ["t1"], "elo_diff": [1.0]}),
        _artifacts(), model_a_predictor=lambda _: expected, generated_at="now",
    )
    assert records.prediction_source.item() == "MODEL_A_FALLBACK"
    assert records[["x0_p_away", "x0_p_draw", "x0_p_home",
                    "x1_raw_p_away", "x1_raw_p_draw", "x1_raw_p_home"]].isna().all().all()
    assert records[["operational_p_away", "operational_p_draw", "operational_p_home"]].to_numpy() == pytest.approx(expected)


def test_missing_model_a_provider_hard_fails_without_refit():
    targets = _targets(False)
    features = _joined_features(targets)
    features.loc[:, "xg_pair_available"] = False
    with pytest.raises(XGPredictionError, match="refit is prohibited"):
        generate_prediction_records(
            targets, features, pd.DataFrame({"match_id": ["t1"], "elo_diff": [1.0]}),
            _artifacts(), generated_at="now",
        )


def test_elo_features_use_completed_state_without_target_update(monkeypatch):
    class EndState:
        final_ratings = {"team_a": 1510.0, "team_b": 1490.0}

    class History:
        ongoing = EndState()

    monkeypatch.setattr(prediction_module, "load_elo_history_with_ongoing", lambda _: History())
    targets = _targets()
    before = targets.copy(deep=True)
    elo = prediction_module._elo_features(targets, "unused")
    assert elo.elo_diff.tolist() == [20.0, -20.0]
    pd.testing.assert_frame_equal(targets, before)


def test_blank_official_match_id_is_never_replaced_by_fixture_key():
    batch = _schedule().loc[lambda frame: frame.match_id.eq("n1")].copy()
    batch.loc[:, "match_id"] = ""
    with pytest.raises(XGPredictionError, match="fixture_key is not a substitute"):
        prediction_module._require_official_target_ids(batch)


def test_artifact_checksum_feature_order_cutoff_and_class_order_validation(tmp_path):
    validated = validate_artifacts(OUTPUT_DIR)
    assert validated.metadata["training_row_count"] == 594
    assert validated.metadata["future_rows_used"] == 0
    assert tuple(validated.metadata["x1_feature_list"]) == (
        "elo_diff", "home_last5_xg_for", "home_last5_xg_against",
        "away_last5_xg_for", "away_last5_xg_against",
    )
    assert tuple(validated.x1_model.classes_) == (0, 1, 2)
    bad = tmp_path / "artifact"
    import shutil
    shutil.copytree(OUTPUT_DIR, bad)
    (bad / "x1_model.joblib").write_bytes(b"broken")
    with pytest.raises(XGPredictionError, match="checksum"):
        validate_artifacts(bad)


def test_append_only_duplicate_protection_and_dry_run_write_boundary(tmp_path):
    targets = _targets(False)
    records = generate_prediction_records(
        targets, _joined_features(targets),
        pd.DataFrame({"match_id": ["t1"], "elo_diff": [1.0]}),
        _artifacts(), generated_at="now",
    )
    output = tmp_path / "predictions.csv"
    assert persist_predictions(records, dry_run=True, path=output) == (0, 0)
    assert not output.exists()
    assert append_predictions(records, output) == (1, 0)
    original = output.read_bytes()
    assert append_predictions(records, output) == (0, 1)
    assert output.read_bytes() == original
    saved = pd.read_csv(output, dtype=str, keep_default_na=False)
    assert saved.model_version.tolist() == [ARTIFACT_VERSION]
    assert tuple(saved.columns) == PREDICTION_COLUMNS


def test_schedule_reader_has_no_result_dependency(tmp_path):
    schedule = prediction_module._read_schedule_without_results(
        "data/processed/jleague/2026_27/schedule.csv"
    )
    schedule["home_score"] = "9"
    schedule["away_score"] = "1"
    schedule["result"] = "2"
    path = tmp_path / "schedule.csv"
    schedule.to_csv(path, index=False, encoding="utf-8-sig")
    first = prediction_module._read_schedule_without_results(path)
    schedule[["home_score", "away_score", "result"]] = "SECRET"
    schedule.to_csv(path, index=False, encoding="utf-8-sig")
    second = prediction_module._read_schedule_without_results(path)
    pd.testing.assert_frame_equal(first, second)
    assert not {"home_score", "away_score", "result"} & set(first.columns)


def test_match_33017_remains_excluded_from_future_history():
    history = _history()
    history.loc[4, "match_id"] = "33017"
    history.loc[4, "xg_time_scope"] = "OFFICIAL_FINAL_SCOPE_UNRESOLVED"
    featured = build_rolling_xg_target_features(
        history, _targets(False)[["competition", "season", "match_id", "match_date", "home_team_id", "away_team_id"]],
    )
    assert featured.home_xg_history_count.item() == 4
    assert featured.away_xg_history_count.item() == 4
    assert not featured.xg_pair_available.item()
    audit = rolling_xg_history_audit(featured).iloc[0]
    assert "33017" not in audit.home_history_match_ids
    assert "33017" not in audit.away_history_match_ids


def test_prediction_module_has_no_evaluation_metric_dependency():
    source = Path("src/modeling/xg_challenger_prediction.py").read_text(encoding="utf-8")
    for forbidden in ("accuracy_score", "log_loss", "brier_score_loss", ".fit("):
        assert forbidden not in source
