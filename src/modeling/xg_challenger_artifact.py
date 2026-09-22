"""Fit and persist the frozen X0/X1 artifacts without evaluating them.

This module deliberately has no metric or prediction API.  It validates the
fixed 594-row training population, fits each scaler and Logistic model once,
and writes immutable reproducibility metadata.  Model A is neither loaded nor
modified.
"""

import csv
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

from src.collect.jleague_ongoing import read_latest
from src.features.elo_history import load_elo_history_with_ongoing


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
XG_DIR = ROOT / "data/processed/jleague_match_xg"
FEATURE_PATH = ROOT / "data/processed/features/2025_2026_27_j1_rolling_xg_features.csv"
ARTIFACT_VERSION = "xg_challenger_20260922_v1"
X0_VERSION = "xg_x0_20260922_v1"
X1_VERSION = "xg_x1_20260922_v1"
OUTPUT_DIR = ROOT / "models/xg_challenger" / ARTIFACT_VERSION
FEATURE_SPEC_PATH = ROOT / "docs/ROLLING_XG_FEATURE_SPEC.md"
PROTOCOL_PATH = ROOT / "docs/XG_CHALLENGER_FREEZE_SPEC.md"
FEATURE_SPEC_VERSION = "rolling_xg_v1"
PROTOCOL_VERSION = "xg_challenger_freeze_v1"
TRAINING_CUTOFF = "2026-09-22T07:16:21+09:00"
PROSPECTIVE_BOUNDARY = TRAINING_CUTOFF
EXPECTED_COMPETITIONS = {
    "j1_2025": 328,
    "j1_hyakunen_2026": 186,
    "j1_2026_2027": 80,
}
CLASS_ORDER = (0, 1, 2)
TARGET_MAPPING = {"0": "Away", "1": "Draw", "2": "Home"}
X0_FEATURES = ("elo_diff",)
X1_FEATURES = (
    "elo_diff",
    "home_last5_xg_for",
    "home_last5_xg_against",
    "away_last5_xg_for",
    "away_last5_xg_against",
)
MANIFEST_COLUMNS = (
    "competition", "season", "match_id", "match_date",
    "home_team_id", "away_team_id", "target_class", *X1_FEATURES,
    "feature_row_sha256",
)
LOGISTIC_PARAMETERS = {
    "C": 1.0,
    "solver": "lbfgs",
    "max_iter": 1000,
    "random_state": 0,
}
MODEL_A_ACTION = "not_loaded_not_refit_not_modified"


class XGArtifactError(ValueError):
    """The frozen training or artifact contract was violated."""


@dataclass(frozen=True)
class FittedModel:
    """One fitted scaler/model pair with its immutable ordered feature list."""

    features: tuple[str, ...]
    scaler: StandardScaler
    model: LogisticRegression


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_row_hash(row: pd.Series) -> str:
    fields = [column for column in MANIFEST_COLUMNS if column != "feature_row_sha256"]
    values = {}
    for column in fields:
        value = row[column]
        if column in X1_FEATURES:
            values[column] = format(float(value), ".17g")
        elif column == "target_class":
            values[column] = int(value)
        else:
            values[column] = str(value)
    payload = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _boolean(series: pd.Series, label: str) -> pd.Series:
    if not series.isin(["True", "False"]).all():
        raise XGArtifactError(f"Invalid boolean values in {label}")
    return series.eq("True")


def _elo_rows(processed_dir: str | Path) -> pd.DataFrame:
    history = load_elo_history_with_ongoing(processed_dir)
    if (len(history.historical.matches), len(history.hyakunen.matches), len(history.ongoing.matches)) != (
        3588, 200, 80,
    ):
        raise XGArtifactError("Elo inputs must remain 3588 ordinary, 200 Hyakunen, and 80 ongoing")
    ordinary = history.historical.matches.loc[
        history.historical.matches["season"].eq(2025)
    ].copy(deep=True)
    if len(ordinary) != 380:
        raise XGArtifactError("Expected exactly 380 ordinary 2025 Elo rows")
    partitions = []
    for competition, season, frame in (
        ("j1_2025", "2025", ordinary),
        ("j1_hyakunen_2026", "2026", history.hyakunen.matches),
        ("j1_2026_2027", "2026/27", history.ongoing.matches),
    ):
        part = frame[[
            "match_id", "match_date", "home_team_id", "away_team_id", "result", "elo_diff",
        ]].copy(deep=True)
        part.insert(0, "season", season)
        part.insert(0, "competition", competition)
        part["match_id"] = part.match_id.astype(str)
        part["match_date"] = pd.to_datetime(part.match_date, errors="raise").dt.strftime("%Y-%m-%d")
        partitions.append(part)
    combined = pd.concat(partitions, ignore_index=True)
    if len(combined) != 660 or combined.match_id.duplicated().any():
        raise XGArtifactError("Elo target universe must contain 660 unique matches")
    return combined


def prepare_training_data(
    *, processed_dir: str | Path = J1_DIR, feature_path: str | Path = FEATURE_PATH,
) -> pd.DataFrame:
    """Return the exact, deterministic 594-row X0/X1 training manifest in memory."""
    path = Path(feature_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    features = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {
        "competition", "season", "match_id", "match_date", "home_team_id", "away_team_id",
        "xg_pair_available", *X1_FEATURES[1:],
    }
    if features.columns.has_duplicates or required - set(features.columns):
        raise XGArtifactError("Rolling xG feature schema is incomplete or duplicated")
    if len(features) != 660 or features.match_id.duplicated().any():
        raise XGArtifactError("Rolling xG source must contain 660 unique matches")
    available = _boolean(features.xg_pair_available, "xg_pair_available")
    selected = features.loc[available, [
        "competition", "season", "match_id", "match_date", "home_team_id", "away_team_id",
        *X1_FEATURES[1:],
    ]].copy(deep=True)

    elo = _elo_rows(processed_dir)
    joined = selected.merge(
        elo, on="match_id", how="inner", validate="one_to_one", suffixes=("_xg", "_elo"),
    )
    if len(joined) != 594 or set(joined.match_id) != set(selected.match_id):
        raise XGArtifactError("Eligible rolling xG rows do not align one-to-one with Elo targets")
    for column in ("competition", "season", "match_date", "home_team_id", "away_team_id"):
        if not joined[f"{column}_xg"].eq(joined[f"{column}_elo"]).all():
            raise XGArtifactError(f"Exact XG/Elo identity mismatch: {column}")

    training = pd.DataFrame({
        "competition": joined.competition_xg,
        "season": joined.season_xg,
        "match_id": joined.match_id,
        "match_date": joined.match_date_xg,
        "home_team_id": joined.home_team_id_xg,
        "away_team_id": joined.away_team_id_xg,
        "target_class": pd.to_numeric(joined.result, errors="raise").astype("int64"),
        "elo_diff": pd.to_numeric(joined.elo_diff, errors="raise").astype("float64"),
    })
    for column in X1_FEATURES[1:]:
        training[column] = pd.to_numeric(joined[column], errors="raise").astype("float64")

    order = {name: position for position, name in enumerate(EXPECTED_COMPETITIONS)}
    training["_competition_order"] = training.competition.map(order)
    training = training.sort_values(
        ["match_date", "_competition_order", "match_id"], kind="stable",
    ).drop(columns="_competition_order").reset_index(drop=True)
    breakdown = training.competition.value_counts().to_dict()
    if breakdown != EXPECTED_COMPETITIONS or len(training) != 594:
        raise XGArtifactError(f"Frozen competition composition changed: {breakdown}")
    if training.match_id.duplicated().any() or training[list(X1_FEATURES)].isna().any().any():
        raise XGArtifactError("Duplicate ID or missing training feature")
    values = training[list(X1_FEATURES)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise XGArtifactError("Training features must be finite")
    if not set(training.target_class.unique()).issubset(CLASS_ORDER) or set(
        training.target_class.unique()
    ) != set(CLASS_ORDER):
        raise XGArtifactError("Training targets must contain exactly classes 0, 1, and 2")
    if not training.loc[training.match_id.eq("33017"), "target_class"].eq(1).all():
        raise XGArtifactError("Hyakunen match 33017 must retain its regulation draw target")
    training["feature_row_sha256"] = training.apply(_canonical_row_hash, axis=1)
    return training.loc[:, list(MANIFEST_COLUMNS)]


def fit_frozen_model(training: pd.DataFrame, features: tuple[str, ...]) -> FittedModel:
    """Fit one fixed scaler/model pair; calculate no prediction or metric."""
    if tuple(features) not in (X0_FEATURES, X1_FEATURES):
        raise XGArtifactError("Unknown frozen feature list")
    matrix = training.loc[:, list(features)].to_numpy(dtype=float)
    target = training.target_class.to_numpy(dtype=int)
    if matrix.shape != (594, len(features)) or not np.isfinite(matrix).all():
        raise XGArtifactError("Frozen training matrix shape or values changed")
    scaler = StandardScaler()
    scaled = scaler.fit_transform(matrix)
    model = LogisticRegression(**LOGISTIC_PARAMETERS)
    model.fit(scaled, target)
    if not np.array_equal(model.classes_, np.asarray(CLASS_ORDER)):
        raise XGArtifactError("Logistic class order must be [0, 1, 2]")
    if scaler.n_features_in_ != len(features) or model.n_features_in_ != len(features):
        raise XGArtifactError("Scaler/model feature shape mismatch")
    for state in (scaler.mean_, scaler.scale_, model.coef_, model.intercept_):
        if not np.isfinite(state).all():
            raise XGArtifactError("Scaler/model state must be finite")
    return FittedModel(tuple(features), scaler, model)


def _same_state(left: FittedModel, right: FittedModel) -> bool:
    return (
        left.features == right.features
        and np.array_equal(left.scaler.mean_, right.scaler.mean_)
        and np.array_equal(left.scaler.scale_, right.scaler.scale_)
        and np.array_equal(left.model.classes_, right.model.classes_)
        and np.array_equal(left.model.coef_, right.model.coef_)
        and np.array_equal(left.model.intercept_, right.model.intercept_)
    )


def _jsonable_parameters(parameters):
    result = {}
    for key, value in parameters.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            result[key] = value
        else:
            result[key] = str(value)
    return result


def _state(model: FittedModel) -> dict:
    return {
        "features": list(model.features),
        "scaler": {
            "n_features_in": int(model.scaler.n_features_in_),
            "n_samples_seen": int(model.scaler.n_samples_seen_),
            "mean": model.scaler.mean_.tolist(),
            "scale": model.scaler.scale_.tolist(),
        },
        "logistic": {
            "n_features_in": int(model.model.n_features_in_),
            "classes": model.model.classes_.tolist(),
            "coefficient_shape": list(model.model.coef_.shape),
            "intercept_shape": list(model.model.intercept_.shape),
            "coefficients": model.model.coef_.tolist(),
            "intercepts": model.model.intercept_.tolist(),
            "n_iter": model.model.n_iter_.tolist(),
            "parameters": _jsonable_parameters(model.model.get_params(deep=False)),
        },
    }


def _source_paths(processed_dir: Path, feature_path: Path) -> list[Path]:
    paths = [
        feature_path,
        ROOT / "data/master/teams.csv",
        FEATURE_SPEC_PATH,
        PROTOCOL_PATH,
        XG_DIR / "2025_j1_match_xg.csv",
        XG_DIR / "2026_hyakunen_j1_match_xg.csv",
        XG_DIR / "2026_27_j1_match_xg.csv",
        *(processed_dir / f"{season}_matches_probe.csv" for season in range(2015, 2026)),
        processed_dir / "2026_hyakunen/matches.csv",
        processed_dir / "2026_27/latest.json",
    ]
    latest = read_latest(processed_dir / "2026_27")
    if latest is None:
        raise XGArtifactError("No published 2026/27 revision")
    revision, _ = latest
    paths.extend((revision / "manifest.json", revision / "schedule.csv", revision / "completed_matches.csv"))
    if any(not path.is_file() for path in paths):
        missing = [str(path) for path in paths if not path.is_file()]
        raise XGArtifactError(f"Missing reproducibility sources: {missing}")
    return paths


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


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


def _write_manifest(path: Path, training: pd.DataFrame) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        training.to_csv(handle, index=False, lineterminator="\n", float_format="%.17g")


def _write_checksums(path: Path, files: list[Path]) -> None:
    lines = [f"{_sha256(item)}  {item.name}" for item in sorted(files, key=lambda p: p.name)]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def create_artifacts(
    *, processed_dir: str | Path = J1_DIR, feature_path: str | Path = FEATURE_PATH,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict:
    """Fit X0/X1 once and atomically publish their reproducibility bundle."""
    destination = Path(output_dir)
    if destination.exists():
        raise XGArtifactError(f"Artifact version already exists: {destination}")
    training = prepare_training_data(processed_dir=processed_dir, feature_path=feature_path)
    rebuilt = prepare_training_data(processed_dir=processed_dir, feature_path=feature_path)
    pd.testing.assert_frame_equal(training, rebuilt, check_exact=True)

    x0 = fit_frozen_model(training, X0_FEATURES)
    x1 = fit_frozen_model(training, X1_FEATURES)
    destination.mkdir(parents=True, exist_ok=False)
    manifest_path = destination / "training_manifest.csv"
    schema_path = destination / "feature_schema.json"
    paths = {
        "x0_scaler": destination / "x0_scaler.joblib",
        "x0_model": destination / "x0_model.joblib",
        "x1_scaler": destination / "x1_scaler.joblib",
        "x1_model": destination / "x1_model.joblib",
    }
    _write_manifest(manifest_path, training)
    schema = {
        "protocol_version": PROTOCOL_VERSION,
        "feature_spec_version": FEATURE_SPEC_VERSION,
        "class_order": list(CLASS_ORDER),
        "target_mapping": TARGET_MAPPING,
        "x0_features": list(X0_FEATURES),
        "x1_features": list(X1_FEATURES),
        "missing_policy": "x1_not_invoked; operational Model A exact fallback",
    }
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    joblib.dump(x0.scaler, paths["x0_scaler"])
    joblib.dump(x0.model, paths["x0_model"])
    joblib.dump(x1.scaler, paths["x1_scaler"])
    joblib.dump(x1.model, paths["x1_model"])

    reloaded_x0 = FittedModel(
        X0_FEATURES, joblib.load(paths["x0_scaler"]), joblib.load(paths["x0_model"]),
    )
    reloaded_x1 = FittedModel(
        X1_FEATURES, joblib.load(paths["x1_scaler"]), joblib.load(paths["x1_model"]),
    )
    if not _same_state(x0, reloaded_x0) or not _same_state(x1, reloaded_x1):
        raise XGArtifactError("Reloaded numerical model state differs from fitted state")

    hashed_artifacts = {name: _sha256(path) for name, path in paths.items()}
    hashed_artifacts.update({
        "training_manifest": _sha256(manifest_path),
        "feature_schema": _sha256(schema_path),
    })
    source_paths = _source_paths(Path(processed_dir), Path(feature_path))
    metadata = {
        "artifact_version": ARTIFACT_VERSION,
        "model_versions": {"x0": X0_VERSION, "x1": X1_VERSION},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "feature_spec": FEATURE_SPEC_VERSION,
        "feature_spec_hash": _sha256(FEATURE_SPEC_PATH),
        "protocol_version": PROTOCOL_VERSION,
        "protocol_hash": _sha256(PROTOCOL_PATH),
        "training_cutoff": TRAINING_CUTOFF,
        "prospective_boundary": PROSPECTIVE_BOUNDARY,
        "training_row_count": len(training),
        "competition_breakdown": training.competition.value_counts().to_dict(),
        "class_counts": {str(key): int(value) for key, value in training.target_class.value_counts().sort_index().items()},
        "future_rows_used": 0,
        "training_match_id_hash": hashlib.sha256(
            ("\n".join(training.match_id) + "\n").encode("ascii")
        ).hexdigest(),
        "training_manifest_hash": _sha256(manifest_path),
        "x0_feature_list": list(X0_FEATURES),
        "x1_feature_list": list(X1_FEATURES),
        "target_mapping": TARGET_MAPPING,
        "elo_parameters": {"initial_rating": 1500, "K": 30, "home_advantage": 175,
                           "elo_diff": "home_rating - away_rating"},
        "logistic_hyperparameters": LOGISTIC_PARAMETERS,
        "model_state": {"x0": _state(x0), "x1": _state(x1)},
        "artifact_hashes": hashed_artifacts,
        "source_datasets": [
            {"path": _relative(path), "sha256": _sha256(path)} for path in source_paths
        ],
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": importlib.metadata.version("scikit-learn"),
            "scipy": importlib.metadata.version("scipy"),
            "joblib": joblib.__version__,
        },
        "repository": _repository_state(),
        "reproducibility_checks": {
            "training_rebuild_exact": True,
            "serialized_x0_state_exact": True,
            "serialized_x1_state_exact": True,
        },
        "model_a_action": MODEL_A_ACTION,
        "metrics_calculated": False,
        "predictions_generated": False,
    }
    metadata_path = destination / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    checksum_path = destination / "checksums.sha256"
    _write_checksums(checksum_path, [manifest_path, schema_path, metadata_path, *paths.values()])
    return metadata


if __name__ == "__main__":
    result = create_artifacts()
    print(json.dumps({
        "artifact_version": result["artifact_version"],
        "training_row_count": result["training_row_count"],
        "competition_breakdown": result["competition_breakdown"],
        "class_counts": result["class_counts"],
        "future_rows_used": result["future_rows_used"],
        "output_dir": str(OUTPUT_DIR),
    }, ensure_ascii=False, indent=2))
