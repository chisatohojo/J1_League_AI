import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.modeling.model_a_artifact import (
    CLASS_ORDER,
    ELO_PARAMETERS,
    EXPECTED_ROWS,
    FEATURES,
    LOGISTIC_PARAMETERS,
    MANIFEST_COLUMNS,
    MODEL_VERSION,
    OUTPUT_DIR,
    ModelAArtifactError,
    _same_state,
    fit_frozen_model_a,
    prepare_training_manifest,
)
from src.modeling.xg_challenger_prediction import (
    XGPredictionError,
    validate_model_a_artifact,
)


@pytest.fixture(scope="module")
def training():
    return prepare_training_manifest()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_model_a_training_rows_seasons_and_manifest_contract(training):
    assert len(training) == training.match_id.nunique() == EXPECTED_ROWS == 3588
    assert tuple(training.columns) == MANIFEST_COLUMNS
    assert training.season.value_counts().sort_index().to_dict() == {
        2015: 306, 2016: 306, 2017: 306, 2018: 306, 2019: 306,
        2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380, 2025: 380,
    }
    assert training.match_date.min().startswith("2015-")
    assert training.match_date.max().startswith("2025-")
    assert set(training.target_class) == set(CLASS_ORDER)


def test_feature_and_fixed_parameter_contract(training):
    assert FEATURES == ("elo_diff",)
    assert ELO_PARAMETERS == {
        "initial_rating": 1500.0, "K": 30.0, "home_advantage": 175.0,
        "elo_diff": "home_rating - away_rating",
    }
    assert LOGISTIC_PARAMETERS == {
        "C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0,
    }
    assert training[["elo_diff"]].notna().all().all()
    assert np.isfinite(training[["elo_diff"]].to_numpy(dtype=float)).all()


def test_scaler_train_only_shapes_and_deterministic_model_state(training):
    first = fit_frozen_model_a(training)
    second = fit_frozen_model_a(training.copy(deep=True))
    assert _same_state(first, second)
    assert first.scaler.n_samples_seen_ == 3588
    assert first.scaler.n_features_in_ == first.model.n_features_in_ == 1
    assert first.model.coef_.shape == (3, 1)
    assert first.model.intercept_.shape == (3,)
    assert tuple(first.model.classes_) == CLASS_ORDER
    for key, value in LOGISTIC_PARAMETERS.items():
        assert first.model.get_params()[key] == value


def test_published_metadata_hashes_and_exclusions():
    metadata = json.loads((OUTPUT_DIR / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["model_version"] == MODEL_VERSION
    assert metadata["role"] == "operational_champion"
    assert metadata["training_row_count"] == 3588
    assert metadata["feature_list"] == ["elo_diff"]
    assert metadata["future_rows_used"] == 0
    assert metadata["metrics_calculated"] is False
    assert metadata["predictions_generated"] is False
    assert metadata["excluded_training_sources"] == [
        "2026_hyakunen", "2026_27_opened_80", "2026_27_future_300",
    ]
    assert metadata["training_manifest_hash"] == _sha256(OUTPUT_DIR / "training_manifest.csv")
    assert metadata["scaler_hash"] == _sha256(OUTPUT_DIR / "scaler.joblib")
    assert metadata["model_hash"] == _sha256(OUTPUT_DIR / "model.joblib")


def test_prediction_pipeline_loads_model_a_and_fallback_predict_proba():
    artifact = validate_model_a_artifact(OUTPUT_DIR)
    values = pd.DataFrame({"elo_diff": [0.0, 100.0]})
    probabilities = artifact.predict_proba(values)
    assert probabilities.shape == (2, 3)
    assert np.all(probabilities >= 0)
    assert np.allclose(probabilities.sum(axis=1), 1.0)


def test_model_a_artifact_missing_and_checksum_mismatch_hard_fail(tmp_path):
    with pytest.raises(XGPredictionError, match="Missing frozen Model A artifact"):
        validate_model_a_artifact(tmp_path / "missing")
    copied = tmp_path / "artifact"
    shutil.copytree(OUTPUT_DIR, copied)
    (copied / "model.joblib").write_bytes(b"corrupt")
    with pytest.raises(XGPredictionError, match="checksum mismatch"):
        validate_model_a_artifact(copied)


def test_prediction_path_does_not_refit_model_a(monkeypatch):
    artifact = validate_model_a_artifact(OUTPUT_DIR)
    monkeypatch.setattr(artifact.scaler.__class__, "fit", lambda *_a, **_k: pytest.fail("fit called"))
    monkeypatch.setattr(artifact.model.__class__, "fit", lambda *_a, **_k: pytest.fail("fit called"))
    result = artifact.predict_proba(pd.DataFrame({"elo_diff": [10.0]}))
    assert result.shape == (1, 3)


def test_x0_x1_artifact_hashes_remain_unchanged():
    metadata = json.loads(Path(
        "models/xg_challenger/xg_challenger_20260922_v1/metadata.json"
    ).read_text(encoding="utf-8"))
    assert metadata["artifact_hashes"]["x0_scaler"] == (
        "110c3be2a16f4fd9a1f40970542112e688c0e480dfbeec2e0efe788742d68fb7"
    )
    assert metadata["artifact_hashes"]["x0_model"] == (
        "31b845726bdfcf17346a2071ee928b1b82bb7cf73fd1ab88851dc81fda27d2b9"
    )
    assert metadata["artifact_hashes"]["x1_scaler"] == (
        "3edcd3c42e912c5f0fbc2620dbcb7263ec7db05d412894968a158673e4750f3a"
    )
    assert metadata["artifact_hashes"]["x1_model"] == (
        "fda9c5992b34b269e3382063112222548985748505fdb2f2cc3aa329cb3d33cf"
    )


def test_artifact_and_prediction_modules_have_no_metrics_dependency():
    combined = "\n".join(Path(path).read_text(encoding="utf-8") for path in (
        "src/modeling/model_a_artifact.py",
        "src/modeling/xg_challenger_prediction.py",
    ))
    for forbidden in (
        "sklearn.metrics", "accuracy_score", "log_loss", "brier_score_loss",
        "confusion_matrix", "classification_report",
    ):
        assert forbidden not in combined
