"""One-fit persistence of frozen ST2; no prediction or evaluation path.

Import/help are stdlib-only and perform no evidence IO. Production execution
requires a separate reviewed authorization; implementation tests use tmp roots.
The seven-column manifest is immutable. Replay captures remain internal only.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import math
from numbers import Integral
import os
from pathlib import Path
import platform
import re
import subprocess
import warnings


ROOT = Path(__file__).parents[2]
MODULE_PATH = "src/modeling/season_transition_st2_artifact.py"
SPEC_PATH = "docs/CHAMPION_A_SEASON_TRANSITION_PROSPECTIVE_FREEZE_SPEC.md"
SPEC_COMMIT = "fb4cef5fea338b99d62f5b2a6c7be5079b4d6f33"
SPEC_SHA = "daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3"
MODEL_VERSION = "season_transition_st2_20261006_v1"
OUTPUT_PATH = f"models/model_season_transition/{MODEL_VERSION}"
OUTPUT_DIR = ROOT / OUTPUT_PATH
ROLE = "prospective_challenger"
FEATURES = ("elo_diff",)
CLASS_ORDER = (0, 1, 2)
TARGET_MAPPING = {"0": "Away", "1": "Draw", "2": "Home"}
TRAINING_SEASONS = tuple(range(2015, 2026))
EXPECTED_ROWS = 3588
SEASON_COUNTS = {y: 380 if y in (2021, 2024, 2025) else 306 for y in TRAINING_SEASONS}
MANIFEST_COLUMNS = (
    "season", "match_id", "match_date", "home_team_id", "away_team_id",
    "target_class", "elo_diff",
)
ELO_PARAMETERS = {
    "initial_rating": 1500.0, "home_advantage": 175.0,
    "expectation_scale": 400.0, "base_k": 30.0, "early_k": 45.0,
    "first_n_appearances": 5, "season_regression": None,
}
SCALER_PARAMETERS = {"copy": True, "with_mean": True, "with_std": True}
LOGISTIC_PARAMETERS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}
TEAM_MASTER_PATH = "data/master/teams.csv"
TEAM_MASTER_SHA = "ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f"
SOURCE_HASHES = {
    "data/processed/jleague/2015_matches_probe.csv": "ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353",
    "data/processed/jleague/2016_matches_probe.csv": "4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f",
    "data/processed/jleague/2017_matches_probe.csv": "d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b",
    "data/processed/jleague/2018_matches_probe.csv": "f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681",
    "data/processed/jleague/2019_matches_probe.csv": "3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f",
    "data/processed/jleague/2020_matches_probe.csv": "fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17",
    "data/processed/jleague/2021_matches_probe.csv": "298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6",
    "data/processed/jleague/2022_matches_probe.csv": "d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2",
    "data/processed/jleague/2023_matches_probe.csv": "6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9",
    "data/processed/jleague/2024_matches_probe.csv": "4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1",
    "data/processed/jleague/2025_matches_probe.csv": "c94411ed299ff90d86c3b55a3b17bd3e0dfc127d58c060109658d235bb24d18d",
}
REQUIREMENTS_HASHES = {
    "requirements.txt": "887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda",
    "requirements-lock.txt": "3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04",
}
CODE_HASHES = {
    "src/features/elo.py": "f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4",
    "src/features/elo_history.py": "e9a66cb8e6d905780fcd8dc88867b21a3de16865eb3c1ef35e3ae0cc5cc1c86a",
    "src/modeling/champion_a_season_transition_evaluation.py": "4c7a32be6d8f9d850c52b974bfb4d3117fb0ff8ba7ba6c908cd50ece5b27d32e",
    "src/modeling/champion_a_oof_diagnostic.py": "40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78",
    "src/modeling/model_a_artifact.py": "69ff3712d5e286b131687fa21b7804cdcc63abb7478bf218fe10a53f77800e8c",
    "src/modeling/xg_challenger_prediction.py": "d9a4fa3db1d4fa6ac090371cee4e0bc10918029de6c43be40af2934674b1aec4",
    "src/modeling/prediction_identity.py": "e9e31ce7b7cf079d8b10dd96a173d8fa31435196982361f2e612524f94177b41",
    "src/collect/matches.py": "0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c",
    "src/collect/teams.py": "b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c",
    "src/collect/jleague_ongoing.py": "5e91025142d583d09f2417724f9cbaeed50339275390d46000d3a73179cbe956",
    "src/collect/jleague_ongoing_source.py": "573a8c6fa4ada4d7d1c7efd64885c9caadb98faf142934e632c41a12811da1d2",
}
RUNTIME_VERSIONS = {
    "python": "3.12.14", "numpy": "2.5.3", "pandas": "3.0.5",
    "scipy": "1.18.1", "scikit-learn": "1.9.1", "joblib": "1.6.0",
}
ARTIFACT_FILES = ("checksums.sha256", "metadata.json", "model.joblib", "scaler.joblib", "training_manifest.csv")
CHECKSUM_FILES = ARTIFACT_FILES[1:]
ATTEMPT_PATH = "data/processed/model_season_transition/st2_prospective_artifact_attempt.json"
AUTHORIZATION_ENV = "CHAMPION_A_ST2_ARTIFACT_AUTHORIZATION"


class ST2ArtifactError(ValueError):
    """Technical STOP, never a research decision or retry authorization."""


def require(condition, message):
    if not condition:
        raise ST2ArtifactError(message)


def libs():
    import numpy as np
    import pandas as pd
    return np, pd


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def ordered_id_hash(ids):
    return sha256(("\n".join(ids) + "\n").encode("utf-8"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def pinned_inputs():
    expected = tuple(f"data/processed/jleague/{y}_matches_probe.csv" for y in TRAINING_SEASONS)
    require(tuple(SOURCE_HASHES) == expected, "Exact eleven ordinary source paths/order")
    return {**SOURCE_HASHES, TEAM_MASTER_PATH: TEAM_MASTER_SHA,
            **REQUIREMENTS_HASHES, **CODE_HASHES, SPEC_PATH: SPEC_SHA}


def rooted(root, relative):
    root = Path(root).resolve()
    path = root / relative
    require(path.resolve().is_relative_to(root), "Path escapes execution root")
    return path


def snapshot_inputs(root):
    """Read/hash ALL explicit bytes before parsing ANY source or master."""
    pins = pinned_inputs()
    snapshots = {p: rooted(root, p).read_bytes() for p in pins}
    for p, expected in pins.items():
        require(sha256(snapshots[p]) == expected, f"Frozen SHA mismatch: {p}")
    return snapshots


def parse_csv(body):
    values = list(csv.reader(io.StringIO(body.decode("utf-8-sig")), strict=True))
    require(bool(values) and bool(values[0]) and len(set(values[0])) == len(values[0]), "CSV header")
    require(all(len(row) == len(values[0]) for row in values[1:]), "CSV field count")
    return values[0], values[1:]


def parse_master(body):
    from src.collect.teams import MASTER_COLUMNS, TeamAlias, TeamMaster
    columns, values = parse_csv(body)
    require(set(columns) == set(MASTER_COLUMNS), "Exact TeamMaster schema")
    aliases = []
    for values_ in values:
        row = dict(zip(columns, values_))
        for field in ("valid_from", "valid_to"):
            require(not row[field] or re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[field]), "Master date")
            row[field] = date.fromisoformat(row[field]) if row[field] else None
        aliases.append(TeamAlias(**row))
    return TeamMaster(aliases)


def validate_source(matches, master):
    """Semantic validation and canonicalization only; no result filtering."""
    _, pd = libs()
    from src.collect.matches import validate_matches
    require(isinstance(matches, pd.DataFrame), "Source must be a DataFrame")
    require(not {"home_team_id", "away_team_id", "elo_diff"} & set(matches.columns), "Generated source columns")
    for column in ("match_id", "home_team", "away_team", "stadium"):
        require(column in matches and matches[column].map(
            lambda x: isinstance(x, str) and bool(x) and x == x.strip() and x.isprintable()
        ).all(), "Exact source text; no silent normalization")
    require("match_date" in matches and matches.match_date.map(
        lambda x: not isinstance(x, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", x) is not None
    ).all(), "Exact source date text; no silent normalization")
    normalized = validate_matches(matches)
    require({"competition", "stage"}.issubset(normalized.columns), "Ordinary competition/stage required")
    require(normalized.season.isin(TRAINING_SEASONS).all(), "Forbidden season")
    require(normalized.match_date.dt.year.eq(normalized.season).all(), "Season/calendar mismatch")
    for r in normalized[["season", "competition", "stage"]].itertuples(index=False):
        allowed = {("Ｊ１ １ｓｔ", "1st"), ("Ｊ１ ２ｎｄ", "2nd")} if r.season in (2015, 2016) else {("Ｊ１", "full_season")}
        require((r.competition, r.stage) in allowed, "Not ordinary J1")
    require(len(normalized) == EXPECTED_ROWS and normalized.season.value_counts().to_dict() == SEASON_COUNTS, "Exact source population/counts")
    ordered = master.add_team_ids(normalized).sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    require(not ordered.home_team_id.eq(ordered.away_team_id).any(), "Self-match after alias resolution")
    sides = pd.concat([ordered[["match_date", f"{side}_team_id"]].rename(columns={f"{side}_team_id": "team_id"}) for side in ("home", "away")])
    require(not sides.duplicated(["match_date", "team_id"]).any(), "Same-date team duplicate")
    return ordered


def load_sources(snapshots):
    _, pd = libs()
    master = parse_master(snapshots[TEAM_MASTER_PATH])
    frames = []
    for year, path in zip(TRAINING_SEASONS, SOURCE_HASHES):
        columns, values = parse_csv(snapshots[path])
        frame = pd.DataFrame(values, columns=columns)
        require("season" in frame and frame.season.eq(str(year)).all() and len(frame) == SEASON_COUNTS[year], "Per-file season/count")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True), master


def match_k(home_ordinal, away_ordinal):
    require(all(isinstance(n, Integral) and not isinstance(n, bool) and n > 0 for n in (home_ordinal, away_ordinal)), "Positive integer ordinal")
    return 45.0 if home_ordinal <= 5 or away_ordinal <= 5 else 30.0


def _capture(row, ratings, counts):
    from src.features.elo import expected_score
    home, away = ratings[row.home_team_id], ratings[row.away_team_id]
    hn, an = counts.get(row.home_team_id, 0) + 1, counts.get(row.away_team_id, 0) + 1
    return home, away, hn, an, match_k(hn, an), expected_score(home + 175.0, away)


def _apply(row, capture, ratings, counts):
    home, away, hn, an, k, expectation = capture
    delta = k * (int(row.result) / 2.0 - expectation)
    ratings[row.home_team_id], ratings[row.away_team_id] = home + delta, away - delta
    require(all(math.isfinite(v) for v in (home + delta, away - delta)), "Nonfinite Elo state")
    counts[row.home_team_id], counts[row.away_team_id] = hn, an


def serialize_manifest(frame):
    return frame.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode("utf-8")


def parse_manifest(body):
    _, pd = libs()
    require(not body.startswith(b"\xef\xbb\xbf") and b"\r" not in body, "Manifest UTF8/LF/no BOM")
    columns, _ = parse_csv(body)
    require(tuple(columns) == MANIFEST_COLUMNS, "Exact seven-column manifest")
    return pd.read_csv(io.BytesIO(body), keep_default_na=False, float_precision="round_trip",
                       dtype={"season": "int64", "target_class": "int64", "elo_diff": "float64",
                              **{c: str for c in MANIFEST_COLUMNS[1:5]}})


@dataclass(frozen=True)
class ValidatedTrainingManifest:
    """Immutable validated bytes, not a mutable caller-owned feature table."""
    csv_bytes: bytes
    registered_ids: tuple[str, ...]
    digest: str

    def to_frame(self):
        require(sha256(self.csv_bytes) == self.digest, "Manifest validation seal")
        frame = parse_manifest(self.csv_bytes)
        _validate_manifest_frame(frame, self.registered_ids)
        return frame


def _validate_manifest_frame(frame, registered_ids):
    np, pd = libs()
    require(tuple(frame.columns) == MANIFEST_COLUMNS, "Exact seven-column manifest")
    require(len(frame) == EXPECTED_ROWS and frame.season.value_counts().to_dict() == SEASON_COUNTS, "Exact manifest population/counts")
    require(frame.season.dtype == np.dtype("int64") and frame.target_class.dtype == np.dtype("int64"), "Integer manifest labels/seasons")
    require(frame.elo_diff.dtype == np.dtype("float64") and np.isfinite(frame.elo_diff).all(), "Finite float64 elo_diff")
    require(frame.season.isin(TRAINING_SEASONS).all() and frame.target_class.isin(CLASS_ORDER).all(), "Manifest season/class")
    roster = tuple(registered_ids)
    require(bool(roster) and len(set(roster)) == len(roster) and all(isinstance(s, str) and re.fullmatch(r"team_[0-9]{4,}", s) and int(s[5:]) > 0 for s in roster), "Exact registered roster")
    for c in MANIFEST_COLUMNS[1:5]:
        require(frame[c].map(lambda s: isinstance(s, str) and bool(s) and s == s.strip() and s.isprintable()).all(), "Exact manifest strings")
    require(frame.match_id.is_unique and not frame.home_team_id.eq(frame.away_team_id).any(), "Manifest identity/self-match")
    require((set(frame.home_team_id) | set(frame.away_team_id)).issubset(roster), "Unregistered manifest ID")
    require(frame.match_date.str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}").all(), "Exact date format")
    dates = pd.to_datetime(frame.match_date, format="%Y-%m-%d", errors="raise")
    require(dates.dt.year.eq(frame.season).all(), "Manifest season/date")
    require(frame.sort_values(["match_date", "match_id"], kind="stable").match_id.tolist() == frame.match_id.tolist(), "Canonical manifest order")
    sides = pd.concat([pd.DataFrame({"date": dates, "team": frame[f"{s}_team_id"]}) for s in ("home", "away")])
    require(not sides.duplicated(["date", "team"]).any(), "Same-date manifest team duplicate")


def validate_training_manifest(frame, registered_ids):
    _validate_manifest_frame(frame, registered_ids)
    body = serialize_manifest(frame)
    return ValidatedTrainingManifest(body, tuple(registered_ids), sha256(body))


def build_training_manifest(matches, master):
    """Pure full ST2 replay; capture state is NEVER persisted as row metadata."""
    _, pd = libs()
    source = validate_source(matches, master)
    roster = tuple(sorted({a.team_id for a in master.aliases}))
    ratings = {team: 1500.0 for team in roster}
    current_season, counts, records = None, {}, []
    for _, day in source.groupby("match_date", sort=False):
        year = int(day.season.iloc[0])
        if year != current_season:
            counts, current_season = {}, year  # No rating regression/reset.
        captures = [(row, _capture(row, ratings, counts)) for row in day.itertuples(index=False)]
        for row, values in captures:
            records.append((year, row.match_id, row.match_date.strftime("%Y-%m-%d"),
                            row.home_team_id, row.away_team_id, int(row.result), values[0] - values[1]))
        for row, values in captures:
            _apply(row, values, ratings, counts)
    frame = pd.DataFrame(records, columns=MANIFEST_COLUMNS).astype({"season": "int64", "target_class": "int64", "elo_diff": "float64"})
    return validate_training_manifest(frame, roster)


@dataclass(frozen=True)
class FittedST2:
    scaler: object
    model: object


def fitted_state(fitted, n):
    np, _ = libs()
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    scaler, model = fitted.scaler, fitted.model
    require(type(scaler) is StandardScaler and type(model) is LogisticRegression, "Exact estimator types")
    require(scaler.get_params() == SCALER_PARAMETERS, "Exact scaler parameters")
    require(model.get_params() == LogisticRegression(**LOGISTIC_PARAMETERS).get_params(), "Exact classifier/locked defaults")
    require(scaler.n_features_in_ == model.n_features_in_ == 1 and scaler.n_samples_seen_ == n, "Fitted feature/sample count")
    require(tuple(model.classes_) == CLASS_ORDER and model.coef_.shape == (3, 1) and model.intercept_.shape == (3,), "Fitted class/shape")
    require(all(np.isfinite(v).all() for v in (scaler.mean_, scaler.var_, scaler.scale_, model.coef_, model.intercept_)), "Finite fitted state")
    require(scaler.mean_.shape == scaler.var_.shape == scaler.scale_.shape == (1,) and (scaler.scale_ > 0).all() and (scaler.var_ >= 0).all(), "Scaler state shape/range")
    require(model.n_iter_.shape == (1,) and (model.n_iter_ > 0).all() and (model.n_iter_ <= 1000).all(), "Classifier convergence state")
    return {
        "scaler_state": {"n_features_in": int(scaler.n_features_in_), "n_samples_seen": int(scaler.n_samples_seen_),
                         "mean": scaler.mean_.tolist(), "var": scaler.var_.tolist(), "scale": scaler.scale_.tolist()},
        "model_state": {"n_features_in": int(model.n_features_in_), "classes": model.classes_.tolist(),
                        "coefficients": model.coef_.tolist(), "intercepts": model.intercept_.tolist(),
                        "n_iter": model.n_iter_.tolist(), "convergence_warning": False},
        "scaler_parameters": scaler.get_params(), "logistic_parameters": model.get_params(),
    }


def new_progress():
    return {"scaler_fit_attempts": 0, "scaler_fits_completed": 0,
            "classifier_fit_attempts": 0, "classifier_fits_completed": 0,
            "prediction_batches": 0, "retry_count": 0}


def fit_frozen_st2(training, *, progress=None):
    require(type(training) is ValidatedTrainingManifest, "Validated training manifest required")
    np, _ = libs()
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    frame = training.to_frame()
    require(set(frame.target_class) == set(CLASS_ORDER), "All three training classes required")
    matrix = frame.loc[:, list(FEATURES)].to_numpy(dtype=np.float64, copy=True)
    target = frame.target_class.to_numpy(dtype=np.int64, copy=True)
    progress = new_progress() if progress is None else progress
    require(progress == new_progress(), "Fit path already attempted; no retry")
    scaler, model = StandardScaler(**SCALER_PARAMETERS), LogisticRegression(**LOGISTIC_PARAMETERS)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        progress["scaler_fit_attempts"] += 1
        scaled = scaler.fit_transform(matrix)
        progress["scaler_fits_completed"] += 1
        require(np.isfinite(scaled).all(), "Finite scaled training matrix")
        progress["classifier_fit_attempts"] += 1
        try:
            model.fit(scaled, target)
        except ConvergenceWarning as exc:
            raise ST2ArtifactError("ConvergenceWarning: technical STOP; no retry") from exc
        progress["classifier_fits_completed"] += 1
    fitted = FittedST2(scaler, model)
    fitted_state(fitted, len(frame))
    return fitted


def runtime_provenance():
    actual = {"python": platform.python_version(), **{k: importlib.metadata.version(k) for k in RUNTIME_VERSIONS if k != "python"}}
    require(actual == RUNTIME_VERSIONS, "Locked runtime mismatch")
    return {**actual, "platform": platform.platform()}


def repository_state(root):
    def git(*args):
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()
    head, status = git("rev-parse", "HEAD"), git("status", "--porcelain")
    require(re.fullmatch(r"[0-9a-f]{40}", head) and not status, "Reviewed clean execution HEAD required")
    return {"commit": head, "dirty": False}


def validate_authorization(authorization, repository):
    require(isinstance(authorization, dict) and set(authorization) == {"approved_execution_head", "task_reference"}, "Separate reviewed artifact authorization required")
    require(authorization["approved_execution_head"] == repository["commit"] and isinstance(authorization["task_reference"], str)
            and bool(authorization["task_reference"].strip()) and authorization["task_reference"] == authorization["task_reference"].strip(), "Artifact authorization HEAD/reference")


def exclusive_write(path, body):
    with path.open("xb") as handle:
        handle.write(body)
        handle.flush()
        os.fsync(handle.fileno())


def create_artifact(*, root=ROOT, authorization=None):
    """Future separately authorized one-shot. NEVER call on real data in tests."""
    root = Path(root).resolve()
    output, marker = rooted(root, OUTPUT_PATH), rooted(root, ATTEMPT_PATH)
    require(not os.path.lexists(output) and not os.path.lexists(marker), "Existing artifact/consumed attempt; no repair")
    repository = repository_state(root)
    validate_authorization(authorization, repository)
    runtime = runtime_provenance()
    snapshots = snapshot_inputs(root)  # ALL hash gates before parse.
    builder_sha = sha256(rooted(root, MODULE_PATH).read_bytes())
    matches, master = load_sources(snapshots)
    training = build_training_manifest(matches, master)
    progress = new_progress()
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "st2_prospective_artifact_attempt_v1", "state": "ATTEMPT_CONSUMED",
               "created_at": datetime.now(timezone.utc).isoformat(), "model_version": MODEL_VERSION,
               "authorization": authorization, "repository": repository,
               "spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT, "sha256": SPEC_SHA},
               "input_hashes": pinned_inputs(), "builder_sha256": builder_sha, "runtime": runtime}
    exclusive_write(marker, json_bytes(payload))
    marker_sha = sha256(marker.read_bytes())
    try:
        output.mkdir(parents=True, exist_ok=False)
        fitted = fit_frozen_st2(training, progress=progress)  # Exactly ONE fit path.
        require(progress == {**new_progress(), "scaler_fit_attempts": 1, "scaler_fits_completed": 1,
                             "classifier_fit_attempts": 1, "classifier_fits_completed": 1}, "Exactly one scaler/classifier fit")
        exclusive_write(output / "training_manifest.csv", training.csv_bytes)
        import joblib
        for filename, estimator in (("scaler.joblib", fitted.scaler), ("model.joblib", fitted.model)):
            with (output / filename).open("xb") as handle:
                joblib.dump(estimator, handle)
                handle.flush()
                os.fsync(handle.fileno())
        # No model reconstruction or second fit after serialization.
        reloaded = FittedST2(joblib.load(output / "scaler.joblib"), joblib.load(output / "model.joblib"))
        state = fitted_state(fitted, EXPECTED_ROWS)
        require(fitted_state(reloaded, EXPECTED_ROWS) == state, "Reloaded state differs")
        frame = training.to_frame()
        metadata = {
            "schema_version": "season_transition_st2_artifact_v1", "model_version": MODEL_VERSION,
            "role": ROLE, "created_at": datetime.now(timezone.utc).isoformat(),
            "spec": payload["spec"], "builder": {"path": MODULE_PATH, "sha256": builder_sha, **repository},
            "authorization": authorization, "runtime": runtime,
            "training_period": {"start_season": 2015, "end_season": 2025},
            "training_row_count": len(frame), "season_coverage": {str(k): int(v) for k, v in frame.season.value_counts().sort_index().items()},
            "class_counts": {str(k): int(v) for k, v in frame.target_class.value_counts().sort_index().items()},
            "feature_list": list(FEATURES), "target_mapping": TARGET_MAPPING,
            "elo_parameters": ELO_PARAMETERS, **state,
            "training_manifest_hash": training.digest, "training_match_ids_hash": ordered_id_hash(frame.match_id),
            "manifest_columns": list(MANIFEST_COLUMNS), "manifest_serialization": {"encoding": "utf-8", "line_ending": "LF", "float_format": "%.17g", "index": False},
            "registered_team_ids": list(training.registered_ids), "source_byte_pins": SOURCE_HASHES,
            "team_master": {"path": TEAM_MASTER_PATH, "sha256": TEAM_MASTER_SHA},
            "requirements_pins": REQUIREMENTS_HASHES, "code_authority_pins": CODE_HASHES,
            "scaler_hash": sha256((output / "scaler.joblib").read_bytes()),
            "model_hash": sha256((output / "model.joblib").read_bytes()),
            "future_rows_used": 0, "metrics_calculated": False, "predictions_generated": False,
            "fit_count": 1, "scaler_fit_count": 1, "retry_count": 0, "fit_progress": progress,
            "attempt": {"path": ATTEMPT_PATH, "sha256": marker_sha, "state": "ATTEMPT_CONSUMED"},
        }
        require(repository_state(root) == repository, "Repository changed during attempt")
        for path, digest in pinned_inputs().items():
            require(sha256(rooted(root, path).read_bytes()) == digest, f"Immutable input changed: {path}")
        require(sha256(rooted(root, MODULE_PATH).read_bytes()) == builder_sha and sha256(marker.read_bytes()) == marker_sha, "Builder/marker changed")
        exclusive_write(output / "metadata.json", json_bytes(metadata))
        checksums = "".join(f"{sha256((output / name).read_bytes())}  {name}\n" for name in CHECKSUM_FILES)
        exclusive_write(output / "checksums.sha256", checksums.encode("ascii"))
        return load_artifact(output)
    except Exception as exc:
        raise ST2ArtifactError(f"ATTEMPT_CONSUMED; no retry/repair; counts={progress}; {type(exc).__name__}: {exc}") from exc


@dataclass(frozen=True)
class LoadedST2:
    fitted: FittedST2
    metadata: dict
    artifact_hash: str


def load_artifact(path, *, expected_artifact_hash=None):
    """Validate immutable linkage and reload, without fitting or prediction."""
    path = Path(path)
    require(path.is_dir() and set(p.name for p in path.iterdir()) == set(ARTIFACT_FILES), "Exact five artifact files")
    require(all((path / name).is_file() and not (path / name).is_symlink() for name in ARTIFACT_FILES), "Artifact file type")
    checksum_bytes = (path / "checksums.sha256").read_bytes()
    artifact_hash = sha256(checksum_bytes)
    require(expected_artifact_hash is None or artifact_hash == expected_artifact_hash, "Artifact bundle hash mismatch")
    lines = checksum_bytes.decode("ascii").splitlines()
    require(len(lines) == len(CHECKSUM_FILES) and checksum_bytes.endswith(b"\n") and b"\r" not in checksum_bytes, "Checksum serialization")
    for line, name in zip(lines, CHECKSUM_FILES):
        require(re.fullmatch(r"[0-9a-f]{64}  " + re.escape(name), line), "Exact checksum coverage/order")
        require(sha256((path / name).read_bytes()) == line[:64], f"Artifact checksum mismatch: {name}")
    metadata = json.loads((path / "metadata.json").read_bytes())
    require(metadata["schema_version"] == "season_transition_st2_artifact_v1" and metadata["model_version"] == MODEL_VERSION and metadata["role"] == ROLE, "Metadata identity")
    require(metadata["spec"] == {"path": SPEC_PATH, "commit": SPEC_COMMIT, "sha256": SPEC_SHA}, "Metadata spec linkage")
    require(metadata["training_period"] == {"start_season": 2015, "end_season": 2025} and metadata["training_row_count"] == EXPECTED_ROWS, "Metadata population")
    require(metadata["feature_list"] == list(FEATURES) and metadata["target_mapping"] == TARGET_MAPPING and metadata["elo_parameters"] == ELO_PARAMETERS, "Metadata model contract")
    require(metadata["source_byte_pins"] == SOURCE_HASHES and metadata["team_master"] == {"path": TEAM_MASTER_PATH, "sha256": TEAM_MASTER_SHA}
            and metadata["requirements_pins"] == REQUIREMENTS_HASHES and metadata["code_authority_pins"] == CODE_HASHES, "Metadata input linkage")
    require(all(metadata["runtime"].get(k) == v for k, v in RUNTIME_VERSIONS.items()), "Metadata runtime")
    require(metadata["future_rows_used"] == 0 and metadata["metrics_calculated"] is False and metadata["predictions_generated"] is False
            and metadata["fit_count"] == metadata["scaler_fit_count"] == 1 and metadata["retry_count"] == 0, "Metadata fit/firewall counts")
    require(metadata["fit_progress"] == {**new_progress(), "scaler_fit_attempts": 1, "scaler_fits_completed": 1,
                                       "classifier_fit_attempts": 1, "classifier_fits_completed": 1}, "Metadata completed fit counts")
    require(metadata["manifest_columns"] == list(MANIFEST_COLUMNS) and metadata["manifest_serialization"] == {"encoding": "utf-8", "line_ending": "LF", "float_format": "%.17g", "index": False}, "Manifest serialization contract")
    body = (path / "training_manifest.csv").read_bytes()
    require(sha256(body) == metadata["training_manifest_hash"], "Manifest metadata linkage")
    training = ValidatedTrainingManifest(body, tuple(metadata["registered_team_ids"]), metadata["training_manifest_hash"])
    frame = training.to_frame()
    require(serialize_manifest(frame) == body and ordered_id_hash(frame.match_id) == metadata["training_match_ids_hash"], "Canonical manifest/ordered ID linkage")
    require({str(k): int(v) for k, v in frame.season.value_counts().items()} == metadata["season_coverage"] and
            {str(k): int(v) for k, v in frame.target_class.value_counts().items()} == metadata["class_counts"], "Metadata population/class counts")
    require(sha256((path / "scaler.joblib").read_bytes()) == metadata["scaler_hash"] and sha256((path / "model.joblib").read_bytes()) == metadata["model_hash"], "Estimator metadata linkage")
    import joblib
    fitted = FittedST2(joblib.load(path / "scaler.joblib"), joblib.load(path / "model.joblib"))
    state = fitted_state(fitted, len(frame))
    require(all(metadata[k] == v for k, v in state.items()), "Reloaded state/metadata linkage")
    return LoadedST2(fitted, metadata, artifact_hash)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Frozen ST2 one-fit artifact builder; real creation needs separate reviewed authorization.")
    parser.add_argument("--create-artifact", action="store_true", help="Future authorized real one-shot ONLY (not implementation validation)")
    args = parser.parse_args(argv)
    if not args.create_artifact:
        parser.error("No default execution: explicit --create-artifact and separate authorization required")
    try:
        authorization = json.loads(os.environ.get(AUTHORIZATION_ENV, "null"))
        artifact = create_artifact(authorization=authorization)
    except Exception as exc:
        print(json.dumps({"status": "TECHNICAL_STOP", "error": str(exc), "retry_count": 0}))
        return 1
    print(json.dumps({"status": "COMPLETE", "model_version": MODEL_VERSION, "artifact_hash": artifact.artifact_hash,
                      "fit_count": 1, "scaler_fit_count": 1, "prediction_batches": 0, "retry_count": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
