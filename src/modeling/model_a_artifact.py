"""Materialize the already-frozen operational Model A without evaluating it.

The artifact is a persistence form of the existing 2015-2025 ordinary-J1
Elo-only Logistic implementation.  No holdout, Hyakunen, 2026/27, future,
rest, xG, prediction, or metric path exists in this module.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.collect.teams import load_team_master
from src.features.elo import EloRatings


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
OUTPUT_DIR = ROOT / "models/model_a/operational_champion_20260922_v1"
MODEL_VERSION = "operational_champion_20260922_v1"
ROLE = "operational_champion"
FEATURES = ("elo_diff",)
CLASS_ORDER = (0, 1, 2)
TARGET_MAPPING = {"0": "Away", "1": "Draw", "2": "Home"}
TRAINING_SEASONS = tuple(range(2015, 2026))
EXPECTED_ROWS = 3588
ELO_PARAMETERS = {
    "initial_rating": 1500.0,
    "K": 30.0,
    "home_advantage": 175.0,
    "elo_diff": "home_rating - away_rating",
}
LOGISTIC_PARAMETERS = {
    "C": 1.0,
    "solver": "lbfgs",
    "max_iter": 1000,
    "random_state": 0,
}
FREEZE_DOCUMENTS = (
    ROOT / "docs/MODEL_FREEZE_BEFORE_2026.md",
    ROOT / "docs/2026_27_INTERIM_LOCKBOX_EVALUATION.md",
    ROOT / "docs/PROJECT_STATUS_2026_09_20.md",
)
MANIFEST_COLUMNS = (
    "season", "match_id", "match_date", "home_team_id", "away_team_id",
    "target_class", "elo_diff",
)


class ModelAArtifactError(ValueError):
    """The frozen Model A training or artifact contract was violated."""


@dataclass(frozen=True)
class FittedModelA:
    scaler: StandardScaler
    model: LogisticRegression


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_season(path: Path, season: int) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {"match_id", "season", "match_date", "home_team", "away_team", "result"}
    if frame.columns.has_duplicates or required - set(frame.columns):
        raise ModelAArtifactError(f"Invalid ordinary-J1 schema: {path.name}")
    if not frame.season.eq(str(season)).all():
        raise ModelAArtifactError(f"Season identity mismatch: {path.name}")
    return frame


def prepare_training_manifest(
    processed_dir: str | Path = J1_DIR,
) -> pd.DataFrame:
    """Reconstruct the exact frozen 3,588-row Model A training frame."""
    root = Path(processed_dir)
    master = load_team_master()
    frames = []
    for season in TRAINING_SEASONS:
        frame = _read_season(root / f"{season}_matches_probe.csv", season)
        dates = pd.to_datetime(frame.match_date, format="%Y-%m-%d", errors="raise")
        part = pd.DataFrame({
            "season": season,
            "match_id": frame.match_id.astype(str),
            "match_date": dates,
            "home_team_id": [
                master.resolve_team_id(name, source="jleague_data_site", on=day)
                for name, day in zip(frame.home_team, dates)
            ],
            "away_team_id": [
                master.resolve_team_id(name, source="jleague_data_site", on=day)
                for name, day in zip(frame.away_team, dates)
            ],
            "target_class": pd.to_numeric(frame.result, errors="raise").astype("int64"),
        })
        frames.append(part)
    ordered = pd.concat(frames, ignore_index=True).sort_values(
        ["match_date", "match_id"], kind="stable",
    ).reset_index(drop=True)
    if len(ordered) != EXPECTED_ROWS or ordered.match_id.duplicated().any():
        raise ModelAArtifactError("Model A requires 3,588 unique ordinary-J1 matches")
    if set(ordered.target_class.unique()) != set(CLASS_ORDER):
        raise ModelAArtifactError("Model A target classes must be exactly 0, 1, and 2")

    team_ids = sorted(set(ordered.home_team_id) | set(ordered.away_team_id))
    elo = EloRatings(
        team_ids, k_factor=ELO_PARAMETERS["K"],
        home_advantage=ELO_PARAMETERS["home_advantage"],
    )
    differences = []
    for row in ordered.itertuples(index=False):
        before = elo.pre_match(row.home_team_id, row.away_team_id)
        differences.append(before.home_rating - before.away_rating)
        elo.update(row.home_team_id, row.away_team_id, int(row.target_class))
    ordered["elo_diff"] = np.asarray(differences, dtype="float64")
    ordered["match_date"] = ordered.match_date.dt.strftime("%Y-%m-%d")
    result = ordered.loc[:, list(MANIFEST_COLUMNS)]
    if not np.isfinite(result[["elo_diff"]].to_numpy(dtype=float)).all():
        raise ModelAArtifactError("Model A feature values must be finite")
    return result


def fit_frozen_model_a(training: pd.DataFrame) -> FittedModelA:
    """Fit the fixed scaler and Logistic estimator; calculate no predictions."""
    if tuple(training.columns) != MANIFEST_COLUMNS or len(training) != EXPECTED_ROWS:
        raise ModelAArtifactError("Unexpected Model A training manifest")
    matrix = training.loc[:, list(FEATURES)].to_numpy(dtype=float, copy=True)
    target = training.target_class.to_numpy(dtype=int, copy=True)
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    model = LogisticRegression(**LOGISTIC_PARAMETERS)
    model.fit(scaled, target)
    if tuple(int(value) for value in model.classes_) != CLASS_ORDER:
        raise ModelAArtifactError("Model A class order mismatch")
    if scaler.n_samples_seen_ != EXPECTED_ROWS:
        raise ModelAArtifactError("Scaler was not fitted on exactly 3,588 rows")
    if scaler.n_features_in_ != len(FEATURES) or model.n_features_in_ != len(FEATURES):
        raise ModelAArtifactError("Model A feature width mismatch")
    for state in (scaler.mean_, scaler.scale_, model.coef_, model.intercept_):
        if not np.isfinite(state).all():
            raise ModelAArtifactError("Model A fitted state must be finite")
    return FittedModelA(scaler, model)


def _same_state(left: FittedModelA, right: FittedModelA) -> bool:
    return all((
        np.array_equal(left.scaler.mean_, right.scaler.mean_),
        np.array_equal(left.scaler.scale_, right.scaler.scale_),
        np.array_equal(left.model.classes_, right.model.classes_),
        np.array_equal(left.model.coef_, right.model.coef_),
        np.array_equal(left.model.intercept_, right.model.intercept_),
    ))


def _repository_state() -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, check=True,
            capture_output=True, text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "status": []}
    return {"commit": commit, "dirty": bool(status), "status": status}


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _write_manifest(path: Path, training: pd.DataFrame) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        training.to_csv(handle, index=False, lineterminator="\n", float_format="%.17g")


def _write_checksums(path: Path, files: tuple[Path, ...]) -> None:
    lines = [f"{_sha256(item)}  {item.name}" for item in sorted(files, key=lambda item: item.name)]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def create_model_a_artifact(
    *, processed_dir: str | Path = J1_DIR, output_dir: str | Path = OUTPUT_DIR,
) -> dict:
    """Create the immutable operational Model A persistence bundle once."""
    destination = Path(output_dir)
    if destination.exists():
        raise ModelAArtifactError(f"Artifact version already exists: {destination}")
    training = prepare_training_manifest(processed_dir)
    rebuilt = prepare_training_manifest(processed_dir)
    pd.testing.assert_frame_equal(training, rebuilt, check_exact=True)
    first = fit_frozen_model_a(training)
    second = fit_frozen_model_a(rebuilt)
    if not _same_state(first, second):
        raise ModelAArtifactError("Deterministic Model A reconstruction failed")

    destination.mkdir(parents=True, exist_ok=False)
    manifest_path = destination / "training_manifest.csv"
    scaler_path = destination / "scaler.joblib"
    model_path = destination / "model.joblib"
    metadata_path = destination / "metadata.json"
    checksum_path = destination / "checksums.sha256"
    _write_manifest(manifest_path, training)
    joblib.dump(first.scaler, scaler_path)
    joblib.dump(first.model, model_path)
    reloaded = FittedModelA(joblib.load(scaler_path), joblib.load(model_path))
    if not _same_state(first, reloaded):
        raise ModelAArtifactError("Reloaded Model A state differs from fitted state")

    source_paths = [
        *(Path(processed_dir) / f"{season}_matches_probe.csv" for season in TRAINING_SEASONS),
        ROOT / "data/master/teams.csv", *FREEZE_DOCUMENTS,
    ]
    if any(not path.is_file() for path in source_paths):
        raise ModelAArtifactError("A frozen Model A source document or dataset is missing")
    manifest_hash = _sha256(manifest_path)
    match_ids_hash = hashlib.sha256(
        ("\n".join(training.match_id.astype(str)) + "\n").encode("ascii")
    ).hexdigest()
    metadata = {
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "role": ROLE,
        "training_period": {"start_season": 2015, "end_season": 2025},
        "training_row_count": EXPECTED_ROWS,
        "season_coverage": {
            str(key): int(value) for key, value in training.season.value_counts().sort_index().items()
        },
        "class_counts": {
            str(key): int(value)
            for key, value in training.target_class.value_counts().sort_index().items()
        },
        "feature_list": list(FEATURES),
        "target_mapping": TARGET_MAPPING,
        "elo_parameters": ELO_PARAMETERS,
        "logistic_hyperparameters": LOGISTIC_PARAMETERS,
        "training_manifest_hash": manifest_hash,
        "training_match_ids_hash": match_ids_hash,
        "scaler_hash": _sha256(scaler_path),
        "model_hash": _sha256(model_path),
        "scaler_state": {
            "n_features_in": int(first.scaler.n_features_in_),
            "n_samples_seen": int(first.scaler.n_samples_seen_),
            "mean": first.scaler.mean_.tolist(),
            "scale": first.scaler.scale_.tolist(),
        },
        "model_state": {
            "classes": first.model.classes_.tolist(),
            "coefficient_shape": list(first.model.coef_.shape),
            "intercept_shape": list(first.model.intercept_.shape),
            "coefficients": first.model.coef_.tolist(),
            "intercepts": first.model.intercept_.tolist(),
        },
        "source_datasets": [
            {"path": _relative(path), "sha256": _sha256(path)} for path in source_paths
        ],
        "freeze_document_references": [_relative(path) for path in FREEZE_DOCUMENTS],
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__, "pandas": pd.__version__,
            "scikit_learn": importlib.metadata.version("scikit-learn"),
            "joblib": joblib.__version__,
        },
        "repository": _repository_state(),
        "reproducibility_checks": {
            "training_rebuild_exact": True,
            "fitted_state_exact": True,
            "serialized_state_exact": True,
        },
        "excluded_training_sources": [
            "2026_hyakunen", "2026_27_opened_80", "2026_27_future_300",
        ],
        "future_rows_used": 0,
        "metrics_calculated": False,
        "predictions_generated": False,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    _write_checksums(metadata_path.parent / "checksums.sha256", (
        manifest_path, scaler_path, model_path, metadata_path,
    ))
    return metadata


if __name__ == "__main__":
    created = create_model_a_artifact()
    print(json.dumps({
        "model_version": created["model_version"],
        "training_row_count": created["training_row_count"],
        "season_coverage": created["season_coverage"],
        "class_counts": created["class_counts"],
        "feature_count": len(created["feature_list"]),
        "future_rows_used": created["future_rows_used"],
        "output_dir": str(OUTPUT_DIR),
    }, ensure_ascii=False, indent=2))
