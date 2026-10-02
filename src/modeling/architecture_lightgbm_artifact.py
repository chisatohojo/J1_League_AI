"""Build and validate the immutable operational Candidate G artifact.

This module reuses the verified ordinary-J1/Elo reconstruction and the frozen
Candidate G component.  It contains no prediction, metric, evaluation, tuning,
or prospective-data path.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from src.modeling.architecture_lightgbm import (
    CLASS_ORDER,
    FEATURE_COLUMNS,
    MODEL_VERSION,
    FittedLightGBMModel,
    build_lightgbm_state_features,
    fit_lightgbm_model,
    validate_lightgbm_features,
)
from src.modeling.architecture_poisson_artifact import (
    ELO_PARAMETERS,
    EXPECTED_ROWS,
    EXPECTED_SEASON_COUNTS,
    J1_DIR,
    TEAM_MASTER_PATH,
    TRAINING_CUTOFF,
    TRAINING_SEASONS,
    prepare_training_manifest as prepare_ordinary_j1_manifest,
    validate_training_manifest as validate_ordinary_j1_manifest,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "models/model_architecture/architecture_lightgbm_form_v1"
ROLE = "prospective_architecture_candidate"
BASE_MANIFEST_COLUMNS = (
    "season",
    "match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "home_score",
    "away_score",
    "result",
    "elo_diff",
)
MANIFEST_COLUMNS = (
    "season",
    "match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "home_score",
    "away_score",
    "result",
    *FEATURE_COLUMNS,
)
TARGET_MAPPING = {"0": "Away", "1": "Draw", "2": "Home"}
LIGHTGBM_PARAMETERS = {
    "boosting_type": "gbdt",
    "objective": "multiclass",
    "num_class": 3,
    "n_estimators": 100,
    "learning_rate": 0.05,
    "num_leaves": 4,
    "max_depth": 2,
    "min_child_samples": 40,
    "min_child_weight": 0.001,
    "min_split_gain": 0.0,
    "subsample": 1.0,
    "subsample_freq": 0,
    "colsample_bytree": 1.0,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "class_weight": None,
    "random_state": 0,
    "n_jobs": 1,
    "verbosity": -1,
    "deterministic": True,
    "force_col_wise": True,
}
FORM_SEMANTICS = {
    "history": "previous five completed ordinary-J1 matches",
    "home_away_history": "unified",
    "cross_season_continuation": True,
    "season_reset": False,
    "left_edge": "2015; no pre-2015 history",
    "availability": "wins + draws + losses; integer 0..5",
    "zero_prior": "availability, points, goals_for, goals_against are zero",
    "same_date_protection": "one appearance per team per calendar date",
}
FREEZE_DOCUMENTS = (
    ROOT / "docs/MODEL_ARCHITECTURE_FEASIBILITY.md",
    ROOT / "docs/MODEL_ARCHITECTURE_BENCHMARK_SPEC.md",
)
IMPLEMENTATION_PATH = ROOT / "src/modeling/architecture_lightgbm.py"
FORM_PATH = ROOT / "src/features/form.py"
BUILDER_PATH = ROOT / "src/modeling/architecture_lightgbm_artifact.py"
PAYLOAD_FILENAMES = ("metadata.json", "model.joblib", "training_manifest.csv")
ARTIFACT_FILENAMES = (*PAYLOAD_FILENAMES, "checksums.sha256")


class LightGBMArtifactError(ValueError):
    """The frozen Candidate G operational artifact contract was violated."""


@dataclass(frozen=True)
class LoadedLightGBMArtifact:
    model: FittedLightGBMModel
    manifest: pd.DataFrame
    metadata: dict
    artifact_hash: str


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _repository_state() -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, check=True, capture_output=True, text=True
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "status": []}
    return {"commit": commit, "dirty": bool(status), "status": status}


def prepare_base_training_manifest(
    processed_dir: str | Path = J1_DIR,
    *,
    team_master_path: str | Path = TEAM_MASTER_PATH,
) -> pd.DataFrame:
    """Reuse the verified 3,588-row ordinary-J1 and same-date Elo reconstruction."""
    base = prepare_ordinary_j1_manifest(processed_dir, team_master_path=team_master_path)
    validate_ordinary_j1_manifest(base)
    if tuple(base.columns) != BASE_MANIFEST_COLUMNS:
        raise LightGBMArtifactError("Base training manifest schema mismatch")
    return base.copy(deep=True)


def build_training_state_manifest(base_manifest: pd.DataFrame) -> pd.DataFrame:
    """Attach Candidate G state through its frozen public feature builder."""
    original = base_manifest.copy(deep=True)
    try:
        validate_ordinary_j1_manifest(base_manifest)
        state = build_lightgbm_state_features(base_manifest)
    except (TypeError, ValueError) as exc:
        raise LightGBMArtifactError(f"Unable to construct Candidate G state: {exc}") from exc
    result = pd.concat(
        [
            base_manifest.loc[:, list(BASE_MANIFEST_COLUMNS[:-1])].reset_index(drop=True),
            state.loc[:, list(FEATURE_COLUMNS)].reset_index(drop=True),
        ],
        axis=1,
    ).loc[:, list(MANIFEST_COLUMNS)]
    if not base_manifest.equals(original):
        raise LightGBMArtifactError("Candidate G state construction mutated the base manifest")
    validate_training_manifest(result)
    return result


def prepare_training_manifest(
    processed_dir: str | Path = J1_DIR,
    *,
    team_master_path: str | Path = TEAM_MASTER_PATH,
) -> pd.DataFrame:
    """Reconstruct the exact Candidate G operational training manifest."""
    base = prepare_base_training_manifest(processed_dir, team_master_path=team_master_path)
    return build_training_state_manifest(base)


def _base_from_state_manifest(manifest: pd.DataFrame) -> pd.DataFrame:
    return manifest.loc[:, list(BASE_MANIFEST_COLUMNS)].copy(deep=True)


def validate_training_manifest(manifest: pd.DataFrame) -> None:
    """Hard-fail on population, identity, chronology, feature, or form drift."""
    if not isinstance(manifest, pd.DataFrame) or manifest.columns.has_duplicates:
        raise LightGBMArtifactError("Training manifest must have unique columns")
    if tuple(manifest.columns) != MANIFEST_COLUMNS:
        raise LightGBMArtifactError("Training manifest schema or feature order mismatch")
    try:
        validate_ordinary_j1_manifest(_base_from_state_manifest(manifest))
        validate_lightgbm_features(manifest)
        rebuilt = build_lightgbm_state_features(_base_from_state_manifest(manifest))
    except (TypeError, ValueError) as exc:
        raise LightGBMArtifactError(f"Training manifest validation failed: {exc}") from exc
    try:
        pd.testing.assert_frame_equal(
            manifest.loc[:, list(FEATURE_COLUMNS)].reset_index(drop=True),
            rebuilt.loc[:, list(FEATURE_COLUMNS)].reset_index(drop=True),
            check_exact=True,
            check_dtype=False,
        )
    except AssertionError as exc:
        raise LightGBMArtifactError("Candidate G form chronology mismatch") from exc


def _validate_fitted_model(model: FittedLightGBMModel) -> LGBMClassifier:
    if not isinstance(model, FittedLightGBMModel) or not isinstance(
        model.classifier, LGBMClassifier
    ):
        raise LightGBMArtifactError("model.joblib does not contain a Candidate G wrapper")
    classifier = model.classifier
    actual = classifier.get_params(deep=False)
    if any(actual.get(name) != value for name, value in LIGHTGBM_PARAMETERS.items()):
        raise LightGBMArtifactError("Candidate G LightGBM parameters mismatch")
    if not hasattr(classifier, "booster_"):
        raise LightGBMArtifactError("Candidate G classifier is not fitted")
    if not np.array_equal(classifier.classes_, np.asarray(CLASS_ORDER)):
        raise LightGBMArtifactError("Candidate G class order mismatch")
    if classifier.n_features_in_ != len(FEATURE_COLUMNS):
        raise LightGBMArtifactError("Candidate G fitted feature width mismatch")
    if tuple(classifier.feature_name_) != FEATURE_COLUMNS:
        raise LightGBMArtifactError("Candidate G fitted feature order mismatch")
    booster = classifier.booster_
    bounds = np.asarray([booster.lower_bound(), booster.upper_bound()], dtype=float)
    if booster.num_feature() != len(FEATURE_COLUMNS) or not np.isfinite(bounds).all():
        raise LightGBMArtifactError("Candidate G booster fitted state is invalid")
    return classifier


def _fitted_state(model: FittedLightGBMModel) -> dict:
    classifier = _validate_fitted_model(model)
    booster = classifier.booster_
    model_text = booster.model_to_string()
    return {
        "classes": classifier.classes_.astype(int).tolist(),
        "n_features_in": int(classifier.n_features_in_),
        "feature_names": list(classifier.feature_name_),
        "booster_num_feature": int(booster.num_feature()),
        "booster_num_trees": int(booster.num_trees()),
        "booster_current_iteration": int(booster.current_iteration()),
        "booster_lower_bound": float(booster.lower_bound()),
        "booster_upper_bound": float(booster.upper_bound()),
        "booster_model_sha256": _sha256_bytes(model_text.encode("utf-8")),
    }


def _same_fitted_state(left: FittedLightGBMModel, right: FittedLightGBMModel) -> bool:
    left_classifier = _validate_fitted_model(left)
    right_classifier = _validate_fitted_model(right)
    return (
        _fitted_state(left) == _fitted_state(right)
        and left_classifier.booster_.model_to_string()
        == right_classifier.booster_.model_to_string()
    )


def _source_paths(processed_dir: Path, team_master_path: Path) -> list[Path]:
    paths = [
        *(processed_dir / f"{season}_matches_probe.csv" for season in TRAINING_SEASONS),
        team_master_path,
        *FREEZE_DOCUMENTS,
        IMPLEMENTATION_PATH,
        FORM_PATH,
        BUILDER_PATH,
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise LightGBMArtifactError(f"Missing frozen reproducibility sources: {missing}")
    return paths


def _write_manifest(path: Path, manifest: pd.DataFrame) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        manifest.to_csv(handle, index=False, lineterminator="\n", float_format="%.17g")


def _write_checksums(path: Path, files: tuple[Path, ...]) -> None:
    lines = [f"{_sha256(item)}  {item.name}" for item in sorted(files, key=lambda item: item.name)]
    with path.open("x", encoding="ascii", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def _json_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LightGBMArtifactError(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise LightGBMArtifactError("Unable to read checksums.sha256") from exc
    entries: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None or match.group(2) in entries:
            raise LightGBMArtifactError("Malformed or duplicate checksum entry")
        entries[match.group(2)] = match.group(1)
    if list(entries) != sorted(PAYLOAD_FILENAMES):
        raise LightGBMArtifactError("Checksum entries must use exact lexicographic payload ordering")
    return entries


def _read_manifest(path: Path) -> pd.DataFrame:
    try:
        manifest = pd.read_csv(
            path,
            dtype={"match_id": str, "match_date": str, "home_team_id": str, "away_team_id": str},
            keep_default_na=False,
            encoding="utf-8",
        )
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise LightGBMArtifactError("Unable to read training_manifest.csv") from exc
    validate_training_manifest(manifest)
    return manifest


def _validate_hash_record(record, expected_path: Path | None = None) -> None:
    if not isinstance(record, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("sha256", ""))):
        raise LightGBMArtifactError("Artifact metadata source hash record is invalid")
    if expected_path is not None and record.get("path") != _relative(expected_path):
        raise LightGBMArtifactError("Artifact metadata source path mismatch")


def _validate_metadata(metadata: dict, manifest_path: Path, model_path: Path) -> None:
    exact = {
        "model_version": MODEL_VERSION,
        "role": ROLE,
        "training_period": {"start_season": 2015, "end_season": 2025},
        "training_cutoff": TRAINING_CUTOFF,
        "training_row_count": EXPECTED_ROWS,
        "season_coverage": {str(k): v for k, v in EXPECTED_SEASON_COUNTS.items()},
        "class_order": list(CLASS_ORDER),
        "target_mapping": TARGET_MAPPING,
        "feature_list": list(FEATURE_COLUMNS),
        "form_semantics": FORM_SEMANTICS,
        "lightgbm_hyperparameters": LIGHTGBM_PARAMETERS,
        "elo_parameters": ELO_PARAMETERS,
        "metrics_calculated": False,
        "predictions_generated": False,
    }
    if any(metadata.get(key) != value for key, value in exact.items()):
        raise LightGBMArtifactError("Artifact metadata frozen contract mismatch")
    if metadata.get("training_manifest_hash") != _sha256(manifest_path):
        raise LightGBMArtifactError("Artifact metadata manifest hash mismatch")
    if metadata.get("model_hash") != _sha256(model_path):
        raise LightGBMArtifactError("Artifact metadata model hash mismatch")
    expected_ids_hash = _sha256_bytes(
        ("\n".join(_read_manifest(manifest_path)["match_id"].astype(str)) + "\n").encode("ascii")
    )
    if metadata.get("training_match_ids_hash") != expected_ids_hash:
        raise LightGBMArtifactError("Artifact metadata training match IDs hash mismatch")
    checks = metadata.get("reproducibility_checks")
    if checks != {
        "base_manifest_rebuild_exact": True,
        "feature_state_rebuild_exact": True,
        "fitted_state_exact": True,
        "serialized_state_exact": True,
    }:
        raise LightGBMArtifactError("Artifact reproducibility metadata mismatch")
    if not isinstance(metadata.get("repository"), dict):
        raise LightGBMArtifactError("Artifact repository provenance is invalid")
    environment = metadata.get("environment", {})
    required_environment = {"python", "numpy", "pandas", "scikit_learn", "lightgbm", "joblib"}
    if set(environment) != required_environment or not all(environment.values()):
        raise LightGBMArtifactError("Artifact environment metadata mismatch")
    source_hashes = metadata.get("source_dataset_hashes")
    if not isinstance(source_hashes, list) or len(source_hashes) != len(TRAINING_SEASONS):
        raise LightGBMArtifactError("Artifact source dataset hashes mismatch")
    for record in source_hashes:
        _validate_hash_record(record)
    _validate_hash_record(metadata.get("team_master"))
    freeze_hashes = metadata.get("freeze_documents")
    if not isinstance(freeze_hashes, list) or len(freeze_hashes) != len(FREEZE_DOCUMENTS):
        raise LightGBMArtifactError("Artifact freeze document hashes mismatch")
    for record, expected_path in zip(freeze_hashes, FREEZE_DOCUMENTS):
        _validate_hash_record(record, expected_path)
    for key, path in (
        ("implementation_module", IMPLEMENTATION_PATH),
        ("form_module", FORM_PATH),
        ("artifact_builder", BUILDER_PATH),
    ):
        _validate_hash_record(metadata.get(key), path)


def load_lightgbm_artifact(path: str | Path = OUTPUT_DIR) -> LoadedLightGBMArtifact:
    """Reload and fully validate an immutable Candidate G artifact bundle."""
    root = Path(path)
    if not root.is_dir():
        raise LightGBMArtifactError(f"Candidate G artifact directory is missing: {root}")
    if sorted(item.name for item in root.iterdir()) != sorted(ARTIFACT_FILENAMES):
        raise LightGBMArtifactError("Candidate G artifact must contain exactly four files")
    checksum_path = root / "checksums.sha256"
    entries = _read_checksums(checksum_path)
    for filename, expected in entries.items():
        payload = root / filename
        if not payload.is_file() or _sha256(payload) != expected:
            raise LightGBMArtifactError(f"Artifact checksum mismatch: {filename}")
    manifest_path = root / "training_manifest.csv"
    model_path = root / "model.joblib"
    metadata_path = root / "metadata.json"
    manifest = _read_manifest(manifest_path)
    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8"), object_pairs_hook=_json_no_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LightGBMArtifactError("Unable to read metadata.json") from exc
    _validate_metadata(metadata, manifest_path, model_path)
    try:
        model = joblib.load(model_path)
    except Exception as exc:
        raise LightGBMArtifactError("Unable to load model.joblib") from exc
    state = _fitted_state(model)
    if metadata.get("fitted_state") != state:
        raise LightGBMArtifactError("Serialized Candidate G state differs from metadata")
    return LoadedLightGBMArtifact(
        model=model,
        manifest=manifest,
        metadata=metadata,
        artifact_hash=_sha256_bytes(checksum_path.read_bytes()),
    )


def create_lightgbm_artifact(
    *,
    processed_dir: str | Path = J1_DIR,
    team_master_path: str | Path = TEAM_MASTER_PATH,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict:
    """Build the frozen artifact once, then reload and validate every payload."""
    destination = Path(output_dir)
    if destination.exists():
        raise LightGBMArtifactError(f"Artifact version already exists: {destination}")
    processed = Path(processed_dir)
    master_path = Path(team_master_path)

    first_base = prepare_base_training_manifest(processed, team_master_path=master_path)
    second_base = prepare_base_training_manifest(processed, team_master_path=master_path)
    try:
        pd.testing.assert_frame_equal(first_base, second_base, check_exact=True)
    except AssertionError as exc:
        raise LightGBMArtifactError("Deterministic base manifest reconstruction failed") from exc

    first_manifest = build_training_state_manifest(first_base)
    second_manifest = build_training_state_manifest(second_base)
    try:
        pd.testing.assert_frame_equal(first_manifest, second_manifest, check_exact=True)
    except AssertionError as exc:
        raise LightGBMArtifactError("Deterministic Candidate G feature-state reconstruction failed") from exc

    first_model = fit_lightgbm_model(first_manifest)
    second_model = fit_lightgbm_model(second_manifest)
    if not _same_fitted_state(first_model, second_model):
        raise LightGBMArtifactError("Deterministic Candidate G fitted state failed")

    source_paths = _source_paths(processed, master_path)
    destination.mkdir(parents=True, exist_ok=False)
    manifest_path = destination / "training_manifest.csv"
    model_path = destination / "model.joblib"
    metadata_path = destination / "metadata.json"
    checksum_path = destination / "checksums.sha256"
    _write_manifest(manifest_path, first_manifest)
    joblib.dump(first_model, model_path)

    source_datasets = source_paths[: len(TRAINING_SEASONS)]
    fitted_state = _fitted_state(first_model)
    metadata = {
        "model_version": MODEL_VERSION,
        "role": ROLE,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_period": {"start_season": 2015, "end_season": 2025},
        "training_cutoff": TRAINING_CUTOFF,
        "training_row_count": EXPECTED_ROWS,
        "season_coverage": {str(key): value for key, value in EXPECTED_SEASON_COUNTS.items()},
        "class_order": list(CLASS_ORDER),
        "target_mapping": TARGET_MAPPING,
        "feature_list": list(FEATURE_COLUMNS),
        "form_semantics": FORM_SEMANTICS,
        "lightgbm_hyperparameters": LIGHTGBM_PARAMETERS,
        "elo_parameters": ELO_PARAMETERS,
        "training_manifest_hash": _sha256(manifest_path),
        "training_match_ids_hash": _sha256_bytes(
            ("\n".join(first_manifest["match_id"].astype(str)) + "\n").encode("ascii")
        ),
        "model_hash": _sha256(model_path),
        "source_dataset_hashes": [
            {"path": _relative(path), "sha256": _sha256(path)} for path in source_datasets
        ],
        "team_master": {"path": _relative(master_path), "sha256": _sha256(master_path)},
        "freeze_documents": [
            {"path": _relative(path), "sha256": _sha256(path)} for path in FREEZE_DOCUMENTS
        ],
        "implementation_module": {
            "path": _relative(IMPLEMENTATION_PATH),
            "sha256": _sha256(IMPLEMENTATION_PATH),
        },
        "form_module": {"path": _relative(FORM_PATH), "sha256": _sha256(FORM_PATH)},
        "artifact_builder": {"path": _relative(BUILDER_PATH), "sha256": _sha256(BUILDER_PATH)},
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": importlib.metadata.version("scikit-learn"),
            "lightgbm": importlib.metadata.version("lightgbm"),
            "joblib": joblib.__version__,
        },
        "repository": _repository_state(),
        "fitted_state": fitted_state,
        "reproducibility_checks": {
            "base_manifest_rebuild_exact": True,
            "feature_state_rebuild_exact": True,
            "fitted_state_exact": True,
            "serialized_state_exact": True,
        },
        "excluded_training_sources": [
            "2026_hyakunen",
            "2026_27_opened",
            "future_cohort",
            "cups",
            "J2_J3",
            "AFC",
        ],
        "metrics_calculated": False,
        "predictions_generated": False,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_checksums(checksum_path, (manifest_path, model_path, metadata_path))
    loaded = load_lightgbm_artifact(destination)
    if not _same_fitted_state(first_model, loaded.model):
        raise LightGBMArtifactError("Reloaded Candidate G state differs from in-memory state")
    return {**metadata, "artifact_hash": loaded.artifact_hash, "artifact_path": str(destination)}


if __name__ == "__main__":
    created = create_lightgbm_artifact()
    print(
        json.dumps(
            {
                "model_version": created["model_version"],
                "training_row_count": created["training_row_count"],
                "season_coverage": created["season_coverage"],
                "training_cutoff": created["training_cutoff"],
                "artifact_path": created["artifact_path"],
                "artifact_hash": created["artifact_hash"],
                "training_manifest_hash": created["training_manifest_hash"],
                "model_hash": created["model_hash"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
