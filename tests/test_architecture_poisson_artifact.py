import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import src.modeling.architecture_poisson_artifact as artifact
from src.collect.teams import load_team_master


@pytest.fixture(scope="module")
def real_manifest():
    return artifact.prepare_training_manifest()


def _synthetic_manifest() -> pd.DataFrame:
    team_ids = sorted({alias.team_id for alias in load_team_master().aliases})[:4]
    rows = []
    number = 0
    score_pairs = ((0, 1), (1, 1), (2, 0))
    for season, count in artifact.EXPECTED_SEASON_COUNTS.items():
        day = artifact.TRAINING_CUTOFF if season == 2025 else f"{season}-01-01"
        for offset in range(count):
            home_score, away_score = score_pairs[number % len(score_pairs)]
            rows.append(
                {
                    "season": season,
                    "match_id": f"synthetic_{number:04d}",
                    "match_date": day,
                    "home_team_id": team_ids[number % len(team_ids)],
                    "away_team_id": team_ids[(number + 1) % len(team_ids)],
                    "home_score": home_score,
                    "away_score": away_score,
                    "result": 0 if home_score < away_score else 1 if home_score == away_score else 2,
                    "elo_diff": float((number % 21) - 10),
                }
            )
            number += 1
    return pd.DataFrame(rows, columns=artifact.MANIFEST_COLUMNS).sort_values(
        ["match_date", "match_id"], kind="stable"
    ).reset_index(drop=True)


@pytest.fixture(scope="module")
def synthetic_artifact(tmp_path_factory):
    destination = tmp_path_factory.mktemp("poisson-artifact") / artifact.MODEL_VERSION
    manifest = _synthetic_manifest()
    patch = pytest.MonkeyPatch()
    patch.setattr(
        artifact,
        "prepare_training_manifest",
        lambda *_args, **_kwargs: manifest.copy(deep=True),
    )
    try:
        metadata = artifact.create_poisson_artifact(output_dir=destination)
    finally:
        patch.undo()
    return destination, metadata, manifest


def test_real_manifest_exact_schema_population_order_and_season_coverage(real_manifest):
    assert tuple(real_manifest.columns) == artifact.MANIFEST_COLUMNS
    assert len(real_manifest) == real_manifest["match_id"].nunique() == artifact.EXPECTED_ROWS
    assert real_manifest["season"].value_counts().sort_index().to_dict() == (
        artifact.EXPECTED_SEASON_COUNTS
    )
    expected = real_manifest.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    assert_frame_equal(real_manifest, expected, check_exact=True)
    assert real_manifest.iloc[-1]["match_date"] == artifact.TRAINING_CUTOFF


def test_manifest_validation_does_not_mutate_input(real_manifest):
    candidate = real_manifest.copy(deep=True)
    original = candidate.copy(deep=True)
    artifact.validate_training_manifest(candidate)
    assert_frame_equal(candidate, original, check_exact=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.assign(match_id="duplicate"), "match_id must be unique"),
        (lambda frame: frame.assign(season=2015), "Season coverage mismatch"),
        (lambda frame: frame.assign(home_team_id="team_999999"), "unknown TeamMaster"),
        (lambda frame: frame.assign(home_score=-1), "nonnegative integers"),
        (lambda frame: frame.assign(result=2), "Score/result contradiction"),
    ],
)
def test_manifest_validation_rejects_contract_violations(real_manifest, mutation, message):
    with pytest.raises(artifact.PoissonArtifactError, match=message):
        artifact.validate_training_manifest(mutation(real_manifest.copy(deep=True)))


def test_same_date_elo_replay_emits_entire_day_before_applying_results(monkeypatch):
    events = []

    class RecordingElo:
        def __init__(self, _ids, **_kwargs):
            pass

        def pre_match(self, home, away):
            events.append(("pre", home, away))
            return SimpleNamespace(home_rating=1500.0, away_rating=1500.0)

        def update(self, home, away, result):
            events.append(("update", home, away, result))

    monkeypatch.setattr(artifact, "EloRatings", RecordingElo)
    frame = pd.DataFrame(
        {
            "match_date": ["2025-01-01", "2025-01-01", "2025-01-02"],
            "home_team_id": ["A", "C", "A"],
            "away_team_id": ["B", "D", "C"],
            "result": [2, 0, 1],
        }
    )
    original = frame.copy(deep=True)

    differences = artifact._replay_elo_same_date(frame)

    assert differences.tolist() == [0.0, 0.0, 0.0]
    assert [event[0] for event in events] == ["pre", "pre", "update", "update", "pre", "update"]
    assert_frame_equal(frame, original, check_exact=True)


def test_same_date_duplicate_team_is_rejected():
    frame = pd.DataFrame(
        {
            "match_date": ["2025-01-01", "2025-01-01"],
            "home_team_id": ["A", "A"],
            "away_team_id": ["B", "C"],
            "result": [2, 1],
        }
    )
    with pytest.raises(artifact.PoissonArtifactError, match="more than once"):
        artifact._replay_elo_same_date(frame)


def test_artifact_write_files_checksums_metadata_and_reload(synthetic_artifact):
    destination, created, manifest = synthetic_artifact
    assert sorted(path.name for path in destination.iterdir()) == [
        "checksums.sha256",
        "metadata.json",
        "model.joblib",
        "training_manifest.csv",
    ]
    lines = (destination / "checksums.sha256").read_text(encoding="ascii").splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == sorted(artifact.PAYLOAD_FILENAMES)

    loaded = artifact.load_poisson_artifact(destination)
    assert_frame_equal(loaded.manifest, manifest, check_exact=False, check_dtype=False)
    assert loaded.artifact_hash == artifact._sha256(destination / "checksums.sha256")
    assert created["artifact_hash"] == loaded.artifact_hash
    assert created["training_manifest_hash"] == artifact._sha256(
        destination / "training_manifest.csv"
    )
    assert created["model_hash"] == artifact._sha256(destination / "model.joblib")
    assert loaded.metadata["reproducibility_checks"] == {
        "training_rebuild_exact": True,
        "fitted_state_exact": True,
        "serialized_state_exact": True,
    }


def test_saved_model_is_exact_frozen_candidate_p_pipeline(synthetic_artifact):
    destination, _created, _manifest = synthetic_artifact
    model = artifact.load_poisson_artifact(destination).model.pipeline
    assert isinstance(model.named_steps["features"], ColumnTransformer)
    assert isinstance(model.named_steps["poisson"], PoissonRegressor)
    transformers = model.named_steps["features"].transformers
    assert isinstance(transformers[0][1], OneHotEncoder)
    assert isinstance(transformers[1][1], StandardScaler)
    assert transformers[1][2] == ("attacker_elo_diff",)
    assert transformers[2] == ("home", "passthrough", ("is_home",))
    assert model.named_steps["poisson"].get_params(deep=False) == artifact.POISSON_PARAMETERS


def test_metadata_freezes_required_operational_contract(synthetic_artifact):
    destination, _created, _manifest = synthetic_artifact
    metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["model_version"] == "architecture_independent_poisson_v1"
    assert metadata["training_cutoff"] == "2025-12-06"
    assert metadata["MAX_GOALS"] == 15
    assert metadata["class_order"] == [0, 1, 2]
    assert metadata["training_row_count"] == 3588
    assert metadata["season_coverage"] == {
        str(key): value for key, value in artifact.EXPECTED_SEASON_COUNTS.items()
    }
    assert metadata["metrics_calculated"] is False
    assert metadata["predictions_generated"] is False


def test_existing_destination_is_rejected_before_reconstruction(synthetic_artifact, monkeypatch):
    destination, _created, _manifest = synthetic_artifact
    monkeypatch.setattr(
        artifact,
        "prepare_training_manifest",
        lambda *_args, **_kwargs: pytest.fail("reconstruction must not run"),
    )
    with pytest.raises(artifact.PoissonArtifactError, match="already exists"):
        artifact.create_poisson_artifact(output_dir=destination)


@pytest.mark.parametrize("filename", ["model.joblib", "training_manifest.csv", "metadata.json"])
def test_corrupt_payload_is_rejected_by_checksum(synthetic_artifact, tmp_path, filename):
    source, _created, _manifest = synthetic_artifact
    copied = tmp_path / "artifact"
    shutil.copytree(source, copied)
    with (copied / filename).open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(artifact.PoissonArtifactError, match="checksum mismatch"):
        artifact.load_poisson_artifact(copied)


def test_corrupt_checksum_is_rejected(synthetic_artifact, tmp_path):
    source, _created, _manifest = synthetic_artifact
    copied = tmp_path / "artifact"
    shutil.copytree(source, copied)
    (copied / "checksums.sha256").write_text("corrupt\n", encoding="ascii")
    with pytest.raises(artifact.PoissonArtifactError, match="Malformed"):
        artifact.load_poisson_artifact(copied)


def test_artifact_module_has_no_metric_prediction_or_tuning_path():
    source = Path("src/modeling/architecture_poisson_artifact.py").read_text(encoding="utf-8")
    for forbidden in (
        "sklearn.metrics",
        "accuracy_score",
        "log_loss",
        "brier",
        "predict_proba(",
        "GridSearchCV",
        "RandomizedSearchCV",
        "lightgbm",
    ):
        assert forbidden not in source
