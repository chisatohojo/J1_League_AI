"""Frozen saved_batches from 5ac9052, for synthetic compatibility tests only.

Function AST is checked against that local Git revision in the private audit.
This is not a runtime fallback or a production entry point.
"""
import hashlib
import json
from scripts import build_dashboard_feed as feed
from src.modeling.prediction_identity import BINDING_COLUMNS


def saved_batches(runtime):
    records, bindings = [], []
    for directory in sorted((runtime / "batches").glob("*")):
        feed.require(directory.is_dir() and feed.HEX64.fullmatch(directory.name), "invalid_batch_directory")
        manifest = json.loads((directory / "manifest.json").read_bytes())
        feed.require(set(manifest) == {"predictions.csv", "bindings.csv"}, "batch_manifest")
        for name, digest in manifest.items():
            feed.require(hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest,
                         "saved_prediction_modified")
        rows = feed.csv_frame((directory / "predictions.csv").read_bytes(), exact=feed.CHAMPION_COLUMNS)
        sidecar = feed.csv_frame((directory / "bindings.csv").read_bytes(), exact=BINDING_COLUMNS)
        feed.read_champion_only_predictions((directory / "predictions.csv").read_bytes())
        records.extend(rows.to_dict("records"))
        bindings.extend(sidecar.to_dict("records"))
    keys = [r["fixture_key"] for r in records]
    feed.require(len(keys) == len(set(keys)), "duplicate_saved_fixture")
    return records, bindings
