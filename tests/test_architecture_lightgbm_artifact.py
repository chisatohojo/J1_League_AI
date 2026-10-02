import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMClassifier
from pandas.testing import assert_frame_equal

import src.modeling.architecture_lightgbm_artifact as artifact
from src.collect.teams import load_team_master
from src.modeling.architecture_lightgbm import FEATURE_COLUMNS, FittedLightGBMModel


@pytest.fixture(scope="module")
def real_base_manifest():
    return artifact.prepare_base_training_manifest()


@pytest.fixture(scope="module")
def real_state_manifest(real_base_manifest):
    return artifact.build_training_state_manifest(real_base_manifest)


def _synthetic_base_manifest() -> pd.DataFrame:
    team_ids = sorted({alias.team_id for alias in load_team_master().aliases})[:20]
    rows = []
    number = 0
    score_pairs = ((0, 1), (1, 1), (2, 0))
    for season, count in artifact.EXPECTED_SEASON_COUNTS.items():
        games_left = count
        day_number = 0
        while games_left:
            games_today = min(games_left, 10)
            if season == 2025 and games_left == games_today:
                day = artifact.TRAINING_CUTOFF
            else:
                day = (pd.Timestamp(f"{season}-01-01") + pd.Timedelta(days=day_number)).strftime(
                    "%Y-%m-%d"
                )
            for game in range(games_today):
                home_score, away_score = score_pairs[number % len(score_pairs)]
                rows.append(
                    {
                        "season": season,
                        "match_id": f"synthetic_{number:04d}",
                        "match_date": day,
                        "home_team_id": team_ids[2 * game],
                        "away_team_id": team_ids[2 * game + 1],
                        "home_score": home_score,
                        "away_score": away_score,
                        "result": (
                            0 if home_score < away_score else 1 if home_score == away_score else 2
                        ),
                        "elo_diff": float((number % 41) - 20),
                    }
                )
                number += 1
            games_left -= games_today
            day_number += 1
    return pd.DataFrame(rows, columns=artifact.BASE_MANIFEST_COLUMNS).sort_values(
        ["match_date", "match_id"], kind="stable"
    ).reset_index(drop=True)


@pytest.fixture(scope="module")
def synthetic_base_manifest():
    return _synthetic_base_manifest()


@pytest.fixture(scope="module")
def synthetic_state_manifest(synthetic_base_manifest):
    return artifact.build_training_state_manifest(synthetic_base_manifest)


@pytest.fixture(scope="module")
def synthetic_artifact(tmp_path_factory, synthetic_base_manifest):
    destination = tmp_path_factory.mktemp("lightgbm-artifact") / artifact.MODEL_VERSION
    patch = pytest.MonkeyPatch()
    patch.setattr(
        artifact,
        "prepare_base_training_manifest",
        lambda *_args, **_kwargs: synthetic_base_manifest.copy(deep=True),
    )
    try:
        metadata = artifact.create_lightgbm_artifact(output_dir=destination)
    finally:
        patch.undo()
    return destination, metadata


def _rewrite_metadata_and_checksums(path: Path, mutation) -> None:
    metadata_path = path / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    mutation(metadata)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    checksum_path = path / "checksums.sha256"
    checksum_path.unlink()
    artifact._write_checksums(
        checksum_path,
        tuple(path / filename for filename in artifact.PAYLOAD_FILENAMES),
    )


def test_real_base_manifest_reconstruction_is_exact_and_deterministic(real_base_manifest):
    second = artifact.prepare_base_training_manifest()
    assert_frame_equal(real_base_manifest, second, check_exact=True)
    assert tuple(real_base_manifest.columns) == artifact.BASE_MANIFEST_COLUMNS
    assert len(real_base_manifest) == artifact.EXPECTED_ROWS
    assert real_base_manifest["season"].value_counts().sort_index().to_dict() == (
        artifact.EXPECTED_SEASON_COUNTS
    )
    assert real_base_manifest.iloc[-1]["match_date"] == artifact.TRAINING_CUTOFF


def test_real_state_manifest_exact_schema_features_order_and_form_edges(
    real_base_manifest, real_state_manifest
):
    assert tuple(real_state_manifest.columns) == artifact.MANIFEST_COLUMNS
    assert tuple(real_state_manifest.columns[-len(FEATURE_COLUMNS) :]) == FEATURE_COLUMNS
    assert len(real_state_manifest) == artifact.EXPECTED_ROWS
    form_without_elo = [column for column in FEATURE_COLUMNS if column != "elo_diff"]
    assert real_state_manifest.loc[0, form_without_elo].eq(0).all()
    rows_2016 = real_state_manifest.loc[real_state_manifest["season"].eq(2016)]
    assert (
        rows_2016[["home_last5_matches_available", "away_last5_matches_available"]]
        .to_numpy()
        .max()
        > 0
    )
    assert not any(column.endswith(("_wins", "_draws", "_losses")) for column in FEATURE_COLUMNS)
    expected = real_state_manifest.sort_values(["match_date", "match_id"], kind="stable").reset_index(
        drop=True
    )
    assert_frame_equal(real_state_manifest, expected, check_exact=True)
    assert_frame_equal(
        real_base_manifest,
        real_state_manifest.loc[:, list(artifact.BASE_MANIFEST_COLUMNS)],
        check_exact=True,
    )


def test_feature_state_reconstruction_is_exact_and_does_not_mutate_input(real_base_manifest):
    candidate = real_base_manifest.copy(deep=True)
    original = candidate.copy(deep=True)
    first = artifact.build_training_state_manifest(candidate)
    second = artifact.build_training_state_manifest(candidate)
    assert_frame_equal(first, second, check_exact=True)
    assert_frame_equal(candidate, original, check_exact=True)


def test_manifest_validation_does_not_mutate_input(synthetic_state_manifest):
    candidate = synthetic_state_manifest.copy(deep=True)
    original = candidate.copy(deep=True)
    artifact.validate_training_manifest(candidate)
    assert_frame_equal(candidate, original, check_exact=True)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.assign(season=2015), "Season coverage mismatch"),
        (lambda frame: frame.assign(match_id="duplicate"), "match_id must be unique"),
        (lambda frame: frame.assign(home_team_id="team_999999"), "unknown TeamMaster"),
        (lambda frame: frame.assign(home_team_id=frame["away_team_id"]), "must differ"),
        (lambda frame: frame.assign(home_score=-1), "nonnegative integers"),
        (lambda frame: frame.assign(home_score=frame["home_score"].astype(float) + 0.5), "integers"),
        (lambda frame: frame.assign(result=2), "Score/result contradiction"),
        (lambda frame: frame.assign(elo_diff=np.inf), "elo_diff must be finite"),
        (
            lambda frame: frame.assign(home_last5_matches_available=6),
            "integers from 0 through 5",
        ),
        (
            lambda frame: frame.assign(home_last5_points=frame["home_last5_points"] + 1),
            "form chronology mismatch",
        ),
    ],
)
def test_manifest_validation_rejects_contract_violations(
    synthetic_state_manifest, mutation, message
):
    with pytest.raises(artifact.LightGBMArtifactError, match=message):
        artifact.validate_training_manifest(mutation(synthetic_state_manifest.copy(deep=True)))


def test_manifest_rejects_feature_order_and_duplicate_columns(synthetic_state_manifest):
    reordered = synthetic_state_manifest.loc[:, list(artifact.MANIFEST_COLUMNS[:-2]) + list(
        reversed(artifact.MANIFEST_COLUMNS[-2:])
    )]
    with pytest.raises(artifact.LightGBMArtifactError, match="schema or feature order"):
        artifact.validate_training_manifest(reordered)
    duplicated = pd.concat(
        [synthetic_state_manifest, synthetic_state_manifest[["elo_diff"]]], axis=1
    )
    with pytest.raises(artifact.LightGBMArtifactError, match="unique columns"):
        artifact.validate_training_manifest(duplicated)


def test_artifact_write_exact_files_checksums_metadata_and_reload(synthetic_artifact):
    destination, created = synthetic_artifact
    assert sorted(path.name for path in destination.iterdir()) == sorted(artifact.ARTIFACT_FILENAMES)
    checksum_bytes = (destination / "checksums.sha256").read_bytes()
    lines = checksum_bytes.decode("ascii").splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == sorted(artifact.PAYLOAD_FILENAMES)
    assert created["artifact_hash"] == artifact._sha256_bytes(checksum_bytes)

    loaded = artifact.load_lightgbm_artifact(destination)
    assert isinstance(loaded.model, FittedLightGBMModel)
    assert isinstance(loaded.model.classifier, LGBMClassifier)
    assert loaded.artifact_hash == created["artifact_hash"]
    assert created["training_manifest_hash"] == artifact._sha256(
        destination / "training_manifest.csv"
    )
    assert created["model_hash"] == artifact._sha256(destination / "model.joblib")
    assert artifact._same_fitted_state(loaded.model, loaded.model)


def test_metadata_freezes_complete_operational_contract(synthetic_artifact):
    destination, _created = synthetic_artifact
    metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["model_version"] == "architecture_lightgbm_form_v1"
    assert metadata["role"] == "prospective_architecture_candidate"
    assert metadata["training_cutoff"] == "2025-12-06"
    assert metadata["training_row_count"] == 3588
    assert metadata["season_coverage"] == {
        str(key): value for key, value in artifact.EXPECTED_SEASON_COUNTS.items()
    }
    assert metadata["feature_list"] == list(FEATURE_COLUMNS)
    assert metadata["lightgbm_hyperparameters"] == artifact.LIGHTGBM_PARAMETERS
    assert metadata["reproducibility_checks"] == {
        "base_manifest_rebuild_exact": True,
        "feature_state_rebuild_exact": True,
        "fitted_state_exact": True,
        "serialized_state_exact": True,
    }
    assert set(metadata["environment"]) == {
        "python",
        "numpy",
        "pandas",
        "scikit_learn",
        "lightgbm",
        "joblib",
    }
    assert metadata["metrics_calculated"] is False
    assert metadata["predictions_generated"] is False


def test_existing_destination_rejects_before_reconstruction(synthetic_artifact, monkeypatch):
    destination, _created = synthetic_artifact
    monkeypatch.setattr(
        artifact,
        "prepare_base_training_manifest",
        lambda *_args, **_kwargs: pytest.fail("reconstruction must not run"),
    )
    with pytest.raises(artifact.LightGBMArtifactError, match="already exists"):
        artifact.create_lightgbm_artifact(output_dir=destination)


@pytest.mark.parametrize("filename", ["model.joblib", "training_manifest.csv", "metadata.json"])
def test_corrupt_payload_is_rejected_by_checksum(synthetic_artifact, tmp_path, filename):
    source, _created = synthetic_artifact
    copied = tmp_path / "artifact"
    shutil.copytree(source, copied)
    with (copied / filename).open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(artifact.LightGBMArtifactError, match="checksum mismatch"):
        artifact.load_lightgbm_artifact(copied)


def test_corrupt_checksum_is_rejected(synthetic_artifact, tmp_path):
    source, _created = synthetic_artifact
    copied = tmp_path / "artifact"
    shutil.copytree(source, copied)
    (copied / "checksums.sha256").write_text("corrupt\n", encoding="ascii")
    with pytest.raises(artifact.LightGBMArtifactError, match="Malformed"):
        artifact.load_lightgbm_artifact(copied)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda metadata: metadata.__setitem__("model_version", "wrong"), "frozen contract"),
        (lambda metadata: metadata.__setitem__("feature_list", []), "frozen contract"),
        (lambda metadata: metadata.__setitem__("training_cutoff", "2025-12-05"), "frozen contract"),
    ],
)
def test_semantically_corrupt_metadata_is_rejected(
    synthetic_artifact, tmp_path, mutation, message
):
    source, _created = synthetic_artifact
    copied = tmp_path / "artifact"
    shutil.copytree(source, copied)
    _rewrite_metadata_and_checksums(copied, mutation)
    with pytest.raises(artifact.LightGBMArtifactError, match=message):
        artifact.load_lightgbm_artifact(copied)


def test_artifact_module_has_no_metric_prediction_or_tuning_path():
    source = Path("src/modeling/architecture_lightgbm_artifact.py").read_text(encoding="utf-8")
    for forbidden in (
        "sklearn.metrics",
        "accuracy_score",
        "log_loss",
        "brier",
        "GridSearchCV",
        "RandomizedSearchCV",
        "lightgbm.cv",
        "eval_set",
        "early_stopping",
        "schedule.csv",
    ):
        assert forbidden not in source
