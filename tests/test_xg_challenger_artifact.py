import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from src.modeling.xg_challenger_artifact import (
    ARTIFACT_VERSION,
    CLASS_ORDER,
    EXPECTED_COMPETITIONS,
    LOGISTIC_PARAMETERS,
    MODEL_A_ACTION,
    OUTPUT_DIR,
    X0_FEATURES,
    X1_FEATURES,
    _same_state,
    _sha256,
    fit_frozen_model,
    prepare_training_data,
)


@pytest.fixture(scope="module")
def training():
    return prepare_training_data()


def test_exact_training_population_and_competition_breakdown(training):
    assert len(training) == training.match_id.nunique() == 594
    assert training.competition.value_counts().to_dict() == EXPECTED_COMPETITIONS
    assert training.match_id.is_unique


def test_x0_and_x1_use_the_same_exact_match_ids(training):
    x0_ids = training.loc[training[list(X0_FEATURES)].notna().all(axis=1), "match_id"]
    x1_ids = training.loc[training[list(X1_FEATURES)].notna().all(axis=1), "match_id"]
    assert x0_ids.tolist() == x1_ids.tolist() == training.match_id.tolist()


def test_feature_lists_are_exact_and_training_values_are_complete(training):
    assert X0_FEATURES == ("elo_diff",)
    assert X1_FEATURES == (
        "elo_diff", "home_last5_xg_for", "home_last5_xg_against",
        "away_last5_xg_for", "away_last5_xg_against",
    )
    assert not training[list(X1_FEATURES)].isna().any().any()
    assert np.isfinite(training[list(X1_FEATURES)].to_numpy(dtype=float)).all()


def test_regulation_target_semantics_include_hyakunen_draw(training):
    assert set(training.target_class) == set(CLASS_ORDER)
    row = training.loc[training.match_id.eq("33017")].squeeze()
    assert row.competition == "j1_hyakunen_2026"
    assert row.target_class == 1


def test_no_future_rows_enter_training(training):
    assert training.competition.value_counts().to_dict()["j1_2026_2027"] == 80
    assert training.match_date.max() == "2026-09-20"
    assert not training.match_id.duplicated().any()


def _synthetic_training():
    index = np.arange(594, dtype=float)
    return pd.DataFrame({
        "target_class": (index.astype(int) % 3),
        "elo_diff": index - 297,
        "home_last5_xg_for": 0.5 + index / 1000,
        "home_last5_xg_against": 1.5 - index / 2000,
        "away_last5_xg_for": 0.7 + index / 1500,
        "away_last5_xg_against": 1.7 - index / 2500,
    })


def test_scaler_uses_all_and_only_594_training_rows_and_fixed_shapes():
    frame = _synthetic_training()
    x0 = fit_frozen_model(frame, X0_FEATURES)
    x1 = fit_frozen_model(frame, X1_FEATURES)
    assert x0.scaler.n_samples_seen_ == x1.scaler.n_samples_seen_ == 594
    assert x0.scaler.n_features_in_ == x0.model.n_features_in_ == 1
    assert x1.scaler.n_features_in_ == x1.model.n_features_in_ == 5
    assert x0.model.coef_.shape == (3, 1)
    assert x1.model.coef_.shape == (3, 5)


def test_fixed_hyperparameters_and_deterministic_model_state():
    frame = _synthetic_training()
    first = fit_frozen_model(frame, X1_FEATURES)
    second = fit_frozen_model(frame, X1_FEATURES)
    assert _same_state(first, second)
    for key, value in LOGISTIC_PARAMETERS.items():
        assert first.model.get_params()[key] == value
    assert first.model.class_weight is None


def test_published_artifact_metadata_and_hashes():
    metadata_path = OUTPUT_DIR / "metadata.json"
    assert metadata_path.is_file()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["artifact_version"] == ARTIFACT_VERSION
    assert metadata["training_row_count"] == 594
    assert metadata["competition_breakdown"] == EXPECTED_COMPETITIONS
    assert metadata["future_rows_used"] == 0
    assert metadata["metrics_calculated"] is False
    assert metadata["predictions_generated"] is False
    assert metadata["model_a_action"] == MODEL_A_ACTION
    for name, expected in metadata["artifact_hashes"].items():
        filename = {
            "x0_scaler": "x0_scaler.joblib", "x0_model": "x0_model.joblib",
            "x1_scaler": "x1_scaler.joblib", "x1_model": "x1_model.joblib",
            "training_manifest": "training_manifest.csv", "feature_schema": "feature_schema.json",
        }[name]
        assert _sha256(OUTPUT_DIR / filename) == expected
    assert _sha256(OUTPUT_DIR / "training_manifest.csv") == metadata["training_manifest_hash"]


def test_saved_scaler_and_model_shapes_and_class_order():
    x0_scaler = joblib.load(OUTPUT_DIR / "x0_scaler.joblib")
    x0_model = joblib.load(OUTPUT_DIR / "x0_model.joblib")
    x1_scaler = joblib.load(OUTPUT_DIR / "x1_scaler.joblib")
    x1_model = joblib.load(OUTPUT_DIR / "x1_model.joblib")
    assert (x0_scaler.n_features_in_, x0_model.coef_.shape) == (1, (3, 1))
    assert (x1_scaler.n_features_in_, x1_model.coef_.shape) == (5, (3, 5))
    assert np.array_equal(x0_model.classes_, CLASS_ORDER)
    assert np.array_equal(x1_model.classes_, CLASS_ORDER)
    assert all(np.isfinite(value).all() for value in (
        x0_scaler.mean_, x0_scaler.scale_, x0_model.coef_, x0_model.intercept_,
        x1_scaler.mean_, x1_scaler.scale_, x1_model.coef_, x1_model.intercept_,
    ))


def test_training_manifest_hash_and_row_hashes(training):
    saved = pd.read_csv(OUTPUT_DIR / "training_manifest.csv", dtype=str, keep_default_na=False)
    assert len(saved) == 594
    assert saved.match_id.tolist() == training.match_id.tolist()
    assert saved.feature_row_sha256.tolist() == training.feature_row_sha256.tolist()
    assert saved.feature_row_sha256.str.fullmatch(r"[0-9a-f]{64}").all()


def test_model_a_is_untouched_and_module_has_no_metrics_or_prediction_dependency():
    assert MODEL_A_ACTION == "not_loaded_not_refit_not_modified"
    source = Path("src/modeling/xg_challenger_artifact.py").read_text(encoding="utf-8")
    assert "sklearn.metrics" not in source
    assert ".predict(" not in source
    assert ".predict_proba(" not in source
    assert "final_2026_lockbox_evaluation" not in source
