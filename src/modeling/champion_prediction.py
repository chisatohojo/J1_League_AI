"""Champion A only: immutable estimator, K=30 Elo replay, pre-match inputs.

No comparison lane, training, evaluation, network or append to research artifacts.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_dashboard_feed import CHAMPION_VERSION, CHAMPION_HASH, kickoff_at, timestamp, require, rooted
from src.collect.teams import load_team_master
from src.features.elo import EloRatings

ARTIFACT_PATH = f"models/model_a/{CHAMPION_VERSION}"
FILE_PINS = {
    "checksums.sha256": CHAMPION_HASH,
    "metadata.json": "bd1eb92c25bdb56a836ef7bfe3fcb13b0137a2ece01b6095e7d100e1f5afdd19",
    "model.joblib": "60636e4652bce98b76c394310947b1b8923a8bf18a640d9e7976497989ed54be",
    "scaler.joblib": "a8a5f176944049c6825071b580c5fe40f5a5fb28f504f8880d028deaf2494750",
    "training_manifest.csv": "eea7498fabac6acc79a9c297468b470702288b61736b63d90214d741ab8fb32a",
}
HYAKUNEN_PATH = "data/processed/jleague/2026_hyakunen/matches.csv"
HYAKUNEN_SHA = "9f871594e5216c1c89e69fcef835c641f3a4b5dbefce8d138e79881494c71f8c"
TARGET_COLUMNS = ("fixture_key", "match_id", "match_date", "kickoff_time",
                  "home_team_id", "away_team_id", "match_id_namespace")
HISTORY_PATHS = {f"data/processed/jleague/{year}_matches_probe.csv" for year in range(2015, 2026)}
HISTORY_PATHS.add("data/master/teams.csv")


@dataclass(frozen=True)
class ChampionArtifact:
    scaler: object
    model: object
    training: pd.DataFrame


def validate_source_data(root, metadata):
    # Documentation hashes in the frozen metadata describe its creation history;
    # later project-status/evaluation documents are not prediction inputs.
    pins = {item["path"]: item["sha256"] for item in metadata["source_datasets"]
            if item["path"].startswith("data/")}
    require(set(pins) == HISTORY_PATHS, "champion_source_contract")
    for path, digest in pins.items():
        require(hashlib.sha256(rooted(root, path).read_bytes()).hexdigest() == digest,
                "champion_source_changed")


def load_champion(root):
    directory = rooted(root, ARTIFACT_PATH)
    require(set(p.name for p in directory.iterdir()) == set(FILE_PINS), "champion_bundle_files")
    bodies = {}
    for name, digest in FILE_PINS.items():
        path = directory / name
        require(path.is_file() and not path.is_symlink(), "champion_bundle_file_type")
        bodies[name] = path.read_bytes()
        require(hashlib.sha256(bodies[name]).hexdigest() == digest, "champion_bundle_hash")
    checks = [f"{hashlib.sha256(bodies[n]).hexdigest()}  {n}"
              for n in sorted(set(FILE_PINS) - {"checksums.sha256"})]
    require(bodies["checksums.sha256"].decode("ascii").splitlines() == checks, "champion_checksums")
    metadata = json.loads(bodies["metadata.json"])
    require(metadata["model_version"] == CHAMPION_VERSION and metadata["role"] == "operational_champion"
            and metadata["feature_list"] == ["elo_diff"] and metadata["training_row_count"] == 3588
            and metadata["target_mapping"] == {"0": "Away", "1": "Draw", "2": "Home"}
            and metadata["elo_parameters"]["K"] == 30.0
            and metadata["elo_parameters"]["home_advantage"] == 175.0, "champion_contract")
    validate_source_data(root, metadata)
    for key, name in (("training_manifest_hash", "training_manifest.csv"),
                      ("model_hash", "model.joblib"), ("scaler_hash", "scaler.joblib")):
        require(metadata[key] == FILE_PINS[name], "champion_metadata_link")
    # All frozen hashes pass before deserializing executable estimator objects.
    import joblib
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    scaler = joblib.load(io.BytesIO(bodies["scaler.joblib"]))
    model = joblib.load(io.BytesIO(bodies["model.joblib"]))
    require(type(scaler) is StandardScaler and type(model) is LogisticRegression, "champion_estimator_type")
    require(scaler.n_features_in_ == model.n_features_in_ == 1
            and tuple(model.classes_) == (0, 1, 2), "champion_feature_class_order")
    require(model.coef_.shape == (3, 1) and model.intercept_.shape == (3,), "champion_estimator_shape")
    require(all(np.isfinite(v).all() for v in
                (scaler.mean_, scaler.scale_, model.coef_, model.intercept_))
            and (scaler.scale_ > 0).all(), "champion_estimator_finite")
    training = pd.read_csv(io.BytesIO(bodies["training_manifest.csv"]), dtype=str, keep_default_na=False)
    require(len(training) == 3588 and training.match_id.is_unique, "champion_training_manifest")
    return ChampionArtifact(scaler, model, training)


def replay_ratings(training, special, completed, master, target_date):
    """Replay only approved regulation results strictly before the target date."""
    elo = EloRatings(sorted({a.team_id for a in master.aliases}), k_factor=30.0, home_advantage=175.0)
    last_day = None
    for segment, frame, result_field in (
        ("training", training, "target_class"), ("special", special, "result"),
        ("ongoing", completed, "result"),
    ):
        ordered = frame.copy()
        ordered["match_date"] = pd.to_datetime(ordered.match_date).dt.strftime("%Y-%m-%d")
        if segment == "ongoing":
            ordered = ordered.loc[ordered.match_date.lt(target_date)]
        ordered = ordered.sort_values(["match_date", "match_id"], kind="stable")
        require(ordered.match_id.is_unique and ordered.match_date.lt(target_date).all(), "history_cutoff_or_id")
        require(ordered.empty or last_day is None or ordered.match_date.min() > last_day, "history_segment_order")
        appearances = pd.concat([ordered[["match_date", f"{s}_team_id"]].rename(
            columns={f"{s}_team_id": "team_id"}) for s in ("home", "away")])
        require(not appearances.duplicated(["match_date", "team_id"]).any(), "history_team_date_duplicate")
        for row in ordered.itertuples(index=False):
            outcome = str(getattr(row, result_field))
            require(outcome in {"0", "1", "2"}, "history_regulation_result")
            before = elo.pre_match(row.home_team_id, row.away_team_id)
            if segment == "training":
                require(2015 <= int(row.season) <= 2025 and
                        math.isclose(before.home_rating - before.away_rating, float(row.elo_diff),
                                     rel_tol=0, abs_tol=1e-8), "frozen_elo_replay_mismatch")
            elo.update(row.home_team_id, row.away_team_id, int(outcome))
        if not ordered.empty:
            last_day = ordered.match_date.max()
    return elo.ratings


def probability_rows(artifact, targets, ratings):
    """Transform/predict only. Outcome columns cannot enter this API."""
    require(tuple(targets.columns) == TARGET_COLUMNS, "prediction_target_allowlist")
    differences = np.asarray([ratings[r.home_team_id] - ratings[r.away_team_id]
                              for r in targets.itertuples(index=False)], dtype=float).reshape(-1, 1)
    require(np.isfinite(differences).all(), "prediction_feature_finite")
    require(tuple(artifact.model.classes_) == (0, 1, 2), "prediction_class_order")
    values = np.asarray(artifact.model.predict_proba(artifact.scaler.transform(differences)), dtype=float)
    require(values.shape == (len(targets), 3) and np.isfinite(values).all()
            and ((values >= 0) & (values <= 1)).all()
            and np.allclose(values.sum(axis=1), 1, rtol=0, atol=1e-12), "prediction_probability_contract")
    return values


def predict_champion(targets, official, source_root, now):
    now = timestamp(now.isoformat())
    master = load_team_master(Path(source_root) / "data/master/teams.csv")
    artifact = load_champion(source_root)
    from src.features.elo_history import _read_hyakunen_matches, _order_matches, _prepare_ongoing_matches
    from src.collect.jleague_hyakunen import validate_competition
    special_path = rooted(source_root, HYAKUNEN_PATH)
    special_bytes = special_path.read_bytes()
    require(hashlib.sha256(special_bytes).hexdigest() == HYAKUNEN_SHA, "hyakunen_frozen_hash")
    special = _read_hyakunen_matches(special_path)
    validate_competition(special)
    special = _order_matches(special, master)
    require(special_path.read_bytes() == special_bytes, "hyakunen_changed")
    completed = _prepare_ongoing_matches(official.completed, master, official.observed_at)
    target_date = targets.match_date.iloc[0]
    require(targets.match_date.eq(target_date).all(), "single_prediction_date")
    for row in targets.itertuples(index=False):
        require(now < timestamp(kickoff_at(row.match_date, row.kickoff_time)), "kickoff_elapsed")
    ratings = replay_ratings(artifact.training, special, completed, master, target_date)
    return probability_rows(artifact, targets, ratings)
