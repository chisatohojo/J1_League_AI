"""Build and validate the immutable operational Candidate P artifact.

This module only reconstructs the frozen 2015--2025 ordinary-J1 training
manifest and fits Candidate P.  It contains no prediction, evaluation, metric,
or prospective-data path.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.collect.teams import load_team_master
from src.features.elo import EloRatings
from src.modeling.architecture_poisson import (
    CLASS_ORDER,
    FEATURE_COLUMNS,
    MAX_GOALS,
    FittedPoissonModel,
    build_goal_observations,
    fit_poisson_model,
)


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
TEAM_MASTER_PATH = ROOT / "data/master/teams.csv"
OUTPUT_DIR = ROOT / "models/model_architecture/architecture_independent_poisson_v1"
MODEL_VERSION = "architecture_independent_poisson_v1"
ROLE = "prospective_architecture_candidate"
TRAINING_SEASONS = tuple(range(2015, 2026))
TRAINING_CUTOFF = "2025-12-06"
EXPECTED_ROWS = 3588
EXPECTED_SEASON_COUNTS = {
    2015: 306,
    2016: 306,
    2017: 306,
    2018: 306,
    2019: 306,
    2020: 306,
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
    2025: 380,
}
MANIFEST_COLUMNS = (
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
TARGET_MAPPING = {"0": "Away", "1": "Draw", "2": "Home"}
ELO_PARAMETERS = {
    "initial_rating": 1500.0,
    "K": 30.0,
    "home_advantage": 175.0,
    "elo_diff": "home pre-match rating - away pre-match rating",
    "season_reset": False,
    "same_date_batching": True,
}
POISSON_PARAMETERS = {
    "alpha": 1.0,
    "fit_intercept": True,
    "solver": "lbfgs",
    "max_iter": 1000,
    "tol": 1e-4,
    "warm_start": False,
    "verbose": 0,
}
FREEZE_DOCUMENTS = (
    ROOT / "docs/MODEL_ARCHITECTURE_FEASIBILITY.md",
    ROOT / "docs/MODEL_ARCHITECTURE_BENCHMARK_SPEC.md",
)
IMPLEMENTATION_PATH = ROOT / "src/modeling/architecture_poisson.py"
PAYLOAD_FILENAMES = ("metadata.json", "model.joblib", "training_manifest.csv")


class PoissonArtifactError(ValueError):
    """The frozen Candidate P artifact contract was violated."""


@dataclass(frozen=True)
class LoadedPoissonArtifact:
    model: FittedPoissonModel
    manifest: pd.DataFrame
    metadata: dict
    artifact_hash: str


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _repository_state() -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None, "status": []}
    return {"commit": commit, "dirty": bool(status), "status": status}


def _read_season(path: Path, season: int) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    required = {
        "season",
        "match_id",
        "match_date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "result",
    }
    if frame.columns.has_duplicates or required - set(frame.columns):
        raise PoissonArtifactError(f"Invalid ordinary-J1 schema: {path.name}")
    if not frame["season"].eq(str(season)).all():
        raise PoissonArtifactError(f"Season identity mismatch: {path.name}")
    return frame


def _integer_column(values: pd.Series, name: str) -> np.ndarray:
    try:
        numeric = pd.to_numeric(values, errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise PoissonArtifactError(f"{name} must contain integers") from exc
    if not np.isfinite(numeric).all() or not np.equal(numeric, np.floor(numeric)).all():
        raise PoissonArtifactError(f"{name} must contain integers")
    return numeric.astype(np.int64)


def _replay_elo_same_date(matches: pd.DataFrame) -> np.ndarray:
    """Emit a day's Elo differences before applying any result from that day."""
    required = {"match_date", "home_team_id", "away_team_id", "result"}
    if matches.columns.has_duplicates or required - set(matches.columns):
        raise PoissonArtifactError("Elo replay input schema mismatch")
    frame = matches.copy(deep=True)
    dates = pd.to_datetime(frame["match_date"], format="%Y-%m-%d", errors="raise")
    team_ids = sorted(set(frame["home_team_id"]) | set(frame["away_team_id"]))
    elo = EloRatings(
        team_ids,
        k_factor=ELO_PARAMETERS["K"],
        home_advantage=ELO_PARAMETERS["home_advantage"],
    )
    differences = np.empty(len(frame), dtype=np.float64)
    for _day, positions in pd.Series(np.arange(len(frame)), index=dates).groupby(level=0, sort=False):
        indices = positions.to_numpy(dtype=int)
        day = frame.iloc[indices]
        appearances = pd.concat([day["home_team_id"], day["away_team_id"]], ignore_index=True)
        if appearances.duplicated().any():
            raise PoissonArtifactError("A team appears more than once on one calendar date")
        for position in indices:
            row = frame.iloc[position]
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            differences[position] = before.home_rating - before.away_rating
        for position in indices:
            row = frame.iloc[position]
            elo.update(row.home_team_id, row.away_team_id, int(row.result))
    return differences


def validate_training_manifest(manifest: pd.DataFrame) -> None:
    """Hard-fail on any deviation from the frozen operational population."""
    if not isinstance(manifest, pd.DataFrame) or manifest.columns.has_duplicates:
        raise PoissonArtifactError("Training manifest must have unique columns")
    if tuple(manifest.columns) != MANIFEST_COLUMNS:
        raise PoissonArtifactError("Training manifest schema mismatch")
    if len(manifest) != EXPECTED_ROWS:
        raise PoissonArtifactError(f"Training manifest must contain exactly {EXPECTED_ROWS} rows")
    if manifest["match_id"].isna().any() or manifest["match_id"].astype(str).str.strip().eq("").any():
        raise PoissonArtifactError("match_id must be nonmissing and nonblank")
    if manifest["match_id"].duplicated().any():
        raise PoissonArtifactError("match_id must be unique")

    seasons = _integer_column(manifest["season"], "season")
    counts = pd.Series(seasons).value_counts().sort_index().to_dict()
    if counts != EXPECTED_SEASON_COUNTS:
        raise PoissonArtifactError(f"Season coverage mismatch: {counts}")
    try:
        dates = pd.to_datetime(manifest["match_date"], format="%Y-%m-%d", errors="raise")
    except (TypeError, ValueError) as exc:
        raise PoissonArtifactError("match_date must be ISO YYYY-MM-DD") from exc
    if dates.dt.strftime("%Y-%m-%d").tolist() != manifest["match_date"].astype(str).tolist():
        raise PoissonArtifactError("match_date must be canonical ISO YYYY-MM-DD")
    if dates.max().strftime("%Y-%m-%d") != TRAINING_CUTOFF:
        raise PoissonArtifactError("Training cutoff mismatch")

    for column in ("home_team_id", "away_team_id"):
        values = manifest[column]
        if values.isna().any() or values.astype(str).str.strip().eq("").any():
            raise PoissonArtifactError(f"{column} must contain TeamMaster identities")
    if manifest["home_team_id"].eq(manifest["away_team_id"]).any():
        raise PoissonArtifactError("Home and away TeamMaster identities must differ")
    master_ids = {alias.team_id for alias in load_team_master(TEAM_MASTER_PATH).aliases}
    observed_ids = set(manifest["home_team_id"]) | set(manifest["away_team_id"])
    if not observed_ids.issubset(master_ids):
        raise PoissonArtifactError("Training manifest contains an unknown TeamMaster identity")

    home_scores = _integer_column(manifest["home_score"], "home_score")
    away_scores = _integer_column(manifest["away_score"], "away_score")
    if (home_scores < 0).any() or (away_scores < 0).any():
        raise PoissonArtifactError("Scores must be nonnegative integers")
    results = _integer_column(manifest["result"], "result")
    if not np.isin(results, CLASS_ORDER).all():
        raise PoissonArtifactError("result must be 0, 1, or 2")
    derived = np.select([home_scores < away_scores, home_scores == away_scores], [0, 1], default=2)
    if not np.array_equal(results, derived):
        raise PoissonArtifactError("Score/result contradiction")
    try:
        elo = pd.to_numeric(manifest["elo_diff"], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise PoissonArtifactError("elo_diff must be finite") from exc
    if not np.isfinite(elo).all():
        raise PoissonArtifactError("elo_diff must be finite")

    expected_order = manifest.assign(_date=dates).sort_values(
        ["_date", "match_id"], kind="stable"
    ).index.to_numpy()
    if not np.array_equal(expected_order, manifest.index.to_numpy()):
        raise PoissonArtifactError("Training manifest chronology/order mismatch")


def prepare_training_manifest(
    processed_dir: str | Path = J1_DIR,
    *,
    team_master_path: str | Path = TEAM_MASTER_PATH,
) -> pd.DataFrame:
    """Reconstruct the exact 3,588-row ordinary-J1 Candidate P manifest."""
    root = Path(processed_dir)
    master = load_team_master(team_master_path)
    frames: list[pd.DataFrame] = []
    for season in TRAINING_SEASONS:
        raw = _read_season(root / f"{season}_matches_probe.csv", season)
        try:
            dates = pd.to_datetime(raw["match_date"], format="%Y-%m-%d", errors="raise")
        except (TypeError, ValueError) as exc:
            raise PoissonArtifactError(f"Malformed match_date in season {season}") from exc
        home_scores = _integer_column(raw["home_score"], "home_score")
        away_scores = _integer_column(raw["away_score"], "away_score")
        results = _integer_column(raw["result"], "result")
        part = pd.DataFrame(
            {
                "season": np.full(len(raw), season, dtype=np.int64),
                "match_id": raw["match_id"].astype(str),
                "match_date": dates.dt.strftime("%Y-%m-%d"),
                "home_team_id": [
                    master.resolve_team_id(name, source="jleague_data_site", on=day)
                    for name, day in zip(raw["home_team"], dates)
                ],
                "away_team_id": [
                    master.resolve_team_id(name, source="jleague_data_site", on=day)
                    for name, day in zip(raw["away_team"], dates)
                ],
                "home_score": home_scores,
                "away_score": away_scores,
                "result": results,
            }
        )
        frames.append(part)
    ordered = pd.concat(frames, ignore_index=True).sort_values(
        ["match_date", "match_id"], kind="stable"
    ).reset_index(drop=True)
    ordered["elo_diff"] = _replay_elo_same_date(ordered)
    result = ordered.loc[:, list(MANIFEST_COLUMNS)]
    validate_training_manifest(result)
    return result


def _validate_pipeline(model: FittedPoissonModel) -> None:
    if not isinstance(model, FittedPoissonModel) or not isinstance(model.pipeline, Pipeline):
        raise PoissonArtifactError("model.joblib does not contain a Candidate P wrapper")
    pipeline = model.pipeline
    if tuple(pipeline.named_steps) != ("features", "poisson"):
        raise PoissonArtifactError("Candidate P pipeline step mismatch")
    preprocessor = pipeline.named_steps["features"]
    estimator = pipeline.named_steps["poisson"]
    if not isinstance(preprocessor, ColumnTransformer) or not isinstance(estimator, PoissonRegressor):
        raise PoissonArtifactError("Candidate P fitted component types mismatch")
    if preprocessor.remainder != "drop" or preprocessor.sparse_threshold != 1.0:
        raise PoissonArtifactError("Candidate P ColumnTransformer parameters mismatch")
    if len(preprocessor.transformers) != 3:
        raise PoissonArtifactError("Candidate P transformer count mismatch")
    teams_name, encoder, team_columns = preprocessor.transformers[0]
    elo_name, scaler, elo_columns = preprocessor.transformers[1]
    home_transform = preprocessor.transformers[2]
    if (
        teams_name != "teams"
        or not isinstance(encoder, OneHotEncoder)
        or tuple(team_columns) != ("attacking_team_id", "defending_team_id")
        or encoder.categories != "auto"
        or encoder.drop is not None
        or encoder.sparse_output is not True
        or encoder.dtype != np.float64
        or encoder.handle_unknown != "ignore"
        or elo_name != "elo"
        or not isinstance(scaler, StandardScaler)
        or tuple(elo_columns) != ("attacker_elo_diff",)
        or home_transform != ("home", "passthrough", ("is_home",))
    ):
        raise PoissonArtifactError("Candidate P preprocessing contract mismatch")
    actual = estimator.get_params(deep=False)
    if any(actual[name] != value for name, value in POISSON_PARAMETERS.items()):
        raise PoissonArtifactError("Candidate P Poisson parameters mismatch")


def _fitted_state(model: FittedPoissonModel) -> dict:
    _validate_pipeline(model)
    pipeline = model.pipeline
    fitted = pipeline.named_steps["features"]
    encoder = fitted.named_transformers_["teams"]
    scaler = fitted.named_transformers_["elo"]
    estimator = pipeline.named_steps["poisson"]
    arrays = (scaler.mean_, scaler.scale_, scaler.var_, estimator.coef_, np.asarray(estimator.intercept_))
    if not all(np.isfinite(value).all() for value in arrays):
        raise PoissonArtifactError("Candidate P fitted state must be finite")
    width = sum(len(category) for category in encoder.categories_) + 2
    if estimator.n_features_in_ != width or fitted.n_features_in_ != len(FEATURE_COLUMNS):
        raise PoissonArtifactError("Candidate P fitted feature width mismatch")
    return {
        "encoder_categories": [[str(value) for value in values] for values in encoder.categories_],
        "scaler_mean": scaler.mean_.tolist(),
        "scaler_scale": scaler.scale_.tolist(),
        "scaler_var": scaler.var_.tolist(),
        "scaler_n_samples_seen": int(scaler.n_samples_seen_),
        "poisson_coefficients": estimator.coef_.tolist(),
        "poisson_intercept": float(estimator.intercept_),
        "poisson_n_iter": int(estimator.n_iter_),
        "input_width": int(fitted.n_features_in_),
        "transformed_width": int(width),
    }


def _same_fitted_state(left: FittedPoissonModel, right: FittedPoissonModel) -> bool:
    return _fitted_state(left) == _fitted_state(right)


def _source_paths(processed_dir: Path, team_master_path: Path) -> list[Path]:
    paths = [
        *(processed_dir / f"{season}_matches_probe.csv" for season in TRAINING_SEASONS),
        team_master_path,
        *FREEZE_DOCUMENTS,
        IMPLEMENTATION_PATH,
    ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise PoissonArtifactError(f"Missing frozen reproducibility sources: {missing}")
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
            raise PoissonArtifactError(f"Duplicate metadata key: {key}")
        result[key] = value
    return result


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as exc:
        raise PoissonArtifactError("Unable to read checksums.sha256") from exc
    expected_names = sorted(PAYLOAD_FILENAMES)
    entries: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        if match is None or match.group(2) in entries:
            raise PoissonArtifactError("Malformed or duplicate checksum entry")
        entries[match.group(2)] = match.group(1)
    if list(entries) != expected_names:
        raise PoissonArtifactError("Checksum entries must use exact lexicographic payload ordering")
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
        raise PoissonArtifactError("Unable to read training_manifest.csv") from exc
    validate_training_manifest(manifest)
    return manifest


def _validate_metadata(metadata: dict, manifest_path: Path, model_path: Path) -> None:
    exact = {
        "model_version": MODEL_VERSION,
        "role": ROLE,
        "training_cutoff": TRAINING_CUTOFF,
        "training_row_count": EXPECTED_ROWS,
        "class_order": list(CLASS_ORDER),
        "target_mapping": TARGET_MAPPING,
        "input_contract": list(FEATURE_COLUMNS),
        "poisson_hyperparameters": POISSON_PARAMETERS,
        "MAX_GOALS": MAX_GOALS,
    }
    if any(metadata.get(key) != value for key, value in exact.items()):
        raise PoissonArtifactError("Artifact metadata frozen contract mismatch")
    if metadata.get("season_coverage") != {str(k): v for k, v in EXPECTED_SEASON_COUNTS.items()}:
        raise PoissonArtifactError("Artifact metadata season coverage mismatch")
    if metadata.get("training_manifest_hash") != _sha256(manifest_path):
        raise PoissonArtifactError("Artifact metadata manifest hash mismatch")
    if metadata.get("model_hash") != _sha256(model_path):
        raise PoissonArtifactError("Artifact metadata model hash mismatch")
    checks = metadata.get("reproducibility_checks", {})
    if checks != {
        "training_rebuild_exact": True,
        "fitted_state_exact": True,
        "serialized_state_exact": True,
    }:
        raise PoissonArtifactError("Artifact reproducibility metadata mismatch")
    if metadata.get("metrics_calculated") is not False or metadata.get("predictions_generated") is not False:
        raise PoissonArtifactError("Artifact metadata claims a forbidden metric or prediction action")


def load_poisson_artifact(path: str | Path = OUTPUT_DIR) -> LoadedPoissonArtifact:
    """Reload and fully validate an immutable Candidate P artifact bundle."""
    root = Path(path)
    if not root.is_dir():
        raise PoissonArtifactError(f"Candidate P artifact directory is missing: {root}")
    checksum_path = root / "checksums.sha256"
    entries = _read_checksums(checksum_path)
    for filename, expected in entries.items():
        payload = root / filename
        if not payload.is_file() or _sha256(payload) != expected:
            raise PoissonArtifactError(f"Artifact checksum mismatch: {filename}")
    manifest_path = root / "training_manifest.csv"
    model_path = root / "model.joblib"
    metadata_path = root / "metadata.json"
    manifest = _read_manifest(manifest_path)
    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8"),
            object_pairs_hook=_json_no_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PoissonArtifactError("Unable to read metadata.json") from exc
    _validate_metadata(metadata, manifest_path, model_path)
    try:
        model = joblib.load(model_path)
    except Exception as exc:
        raise PoissonArtifactError("Unable to load model.joblib") from exc
    state = _fitted_state(model)
    if metadata.get("fitted_state") != state:
        raise PoissonArtifactError("Serialized model state differs from metadata")
    return LoadedPoissonArtifact(
        model=model,
        manifest=manifest,
        metadata=metadata,
        artifact_hash=_sha256(checksum_path),
    )


def create_poisson_artifact(
    *,
    processed_dir: str | Path = J1_DIR,
    team_master_path: str | Path = TEAM_MASTER_PATH,
    output_dir: str | Path = OUTPUT_DIR,
) -> dict:
    """Build the frozen artifact once, then reload and validate every payload."""
    destination = Path(output_dir)
    if destination.exists():
        raise PoissonArtifactError(f"Artifact version already exists: {destination}")
    processed = Path(processed_dir)
    master_path = Path(team_master_path)
    first_manifest = prepare_training_manifest(processed, team_master_path=master_path)
    second_manifest = prepare_training_manifest(processed, team_master_path=master_path)
    try:
        pd.testing.assert_frame_equal(first_manifest, second_manifest, check_exact=True)
    except AssertionError as exc:
        raise PoissonArtifactError("Deterministic manifest reconstruction failed") from exc

    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        first_model = fit_poisson_model(first_manifest)
        second_model = fit_poisson_model(second_manifest)
    if not _same_fitted_state(first_model, second_model):
        raise PoissonArtifactError("Deterministic Candidate P fitted state failed")

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
        "input_contract": list(FEATURE_COLUMNS),
        "poisson_hyperparameters": POISSON_PARAMETERS,
        "MAX_GOALS": MAX_GOALS,
        "score_grid_semantics": {
            "axis": "0..15 inclusive",
            "class_order": ["Away", "Draw", "Home"],
            "tail": "discard outside grid; renormalize retained mass",
        },
        "elo_parameters": ELO_PARAMETERS,
        "training_manifest_hash": _sha256(manifest_path),
        "training_match_ids_hash": hashlib.sha256(
            ("\n".join(first_manifest["match_id"].astype(str)) + "\n").encode("ascii")
        ).hexdigest(),
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
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "scikit_learn": importlib.metadata.version("scikit-learn"),
            "scipy": importlib.metadata.version("scipy"),
            "joblib": joblib.__version__,
        },
        "repository": _repository_state(),
        "fitted_state": fitted_state,
        "reproducibility_checks": {
            "training_rebuild_exact": True,
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
    loaded = load_poisson_artifact(destination)
    if not _same_fitted_state(first_model, loaded.model):
        raise PoissonArtifactError("Reloaded Candidate P state differs from in-memory state")
    return {**metadata, "artifact_hash": loaded.artifact_hash, "artifact_path": str(destination)}


if __name__ == "__main__":
    created = create_poisson_artifact()
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
