"""Artifact integration checks using the artificial competition, without network or real data."""

import copy
import json
import socket

import pandas as pd
import pytest

from scripts import inspect_jleague_hyakunen as inspection
from tests.test_jleague_hyakunen import synthetic_sources


def test_export_roundtrip_summary_and_repeatability(tmp_path, monkeypatch):
    records, details = synthetic_sources()
    metadata = {"fixture": {"sha256": "synthetic", "requested_url": "fixture"}}
    monkeypatch.setattr(
        inspection, "read_cached_sources",
        lambda **kwargs: (copy.deepcopy(records), copy.deepcopy(details), copy.deepcopy(metadata)),
    )
    def no_network(*args, **kwargs):
        raise AssertionError("Offline inspection must not open network connections")
    monkeypatch.setattr(socket, "create_connection", no_network)
    summary = inspection.run_inspection(root=tmp_path)
    output = tmp_path / "data/processed/jleague/2026_hyakunen"
    files = {path.name: path.read_bytes() for path in output.iterdir()}
    assert set(files) == {"matches.csv", "playoff_ties.csv", "summary.json", "review.md"}
    assert summary["matches"] == 200
    assert summary["playoff_tie_count"] == 10
    assert summary["csv_roundtrip_validated"]
    assert summary["network_requests"] == 0
    assert summary["quality"]["score_result_mismatches"] == 0
    assert sum(summary["result_90_counts"].values()) == 200
    assert sum(summary["match_outcome_counts"].values()) == 200
    assert sum(summary["quality"]["required_missing"].values()) == 0
    assert len(summary["first_five"]) == len(summary["last_five"]) == 5
    assert len(summary["random_ten"]) == 10
    assert json.loads(files["summary.json"].decode("utf-8")) == summary
    frame = pd.read_csv(output / "matches.csv", keep_default_na=False)
    assert frame.loc[frame.stage == "playoff", "round"].eq("").all()
    assert frame.loc[frame.stage == "regional", "leg"].eq("").all()
    assert "tie_winner_team" not in frame.columns
    assert "random_state=42" in files["review.md"].decode("utf-8")
    inspection.run_inspection(root=tmp_path)
    assert {path.name: path.read_bytes() for path in output.iterdir()} == files


def test_incomplete_competition_preserves_existing_artifact(tmp_path, monkeypatch):
    records, details = synthetic_sources()
    monkeypatch.setattr(inspection, "read_cached_sources", lambda **kwargs: (records[:-1], details, {}))
    output = tmp_path / "artifacts"
    output.mkdir()
    marker = output / "matches.csv"
    marker.write_bytes(b"existing content\n")
    with pytest.raises(ValueError):
        inspection.run_inspection(root=tmp_path, output_dir=output)
    assert marker.read_bytes() == b"existing content\n"
    assert len(list(output.iterdir())) == 1


def test_raw_output_directory_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="raw data"):
        inspection.run_inspection(root=tmp_path, output_dir=tmp_path / "data/raw/nested")
    assert not (tmp_path / "data/raw").exists()


def test_csv_roundtrip_preserves_ids_literal_na_and_nullable_values(tmp_path):
    frame = pd.DataFrame({
        "match_id": pd.Series(["0001", "0020"], dtype="string"),
        "team": pd.Series(["NA", "クラブ"], dtype="string"),
        "score": pd.Series([0, None], dtype="Int64"),
        "played": pd.Series([True, False], dtype="bool"),
        "date": pd.to_datetime(["2026-02-06", "2026-06-06"]).astype("datetime64[ns]"),
    })
    path = tmp_path / "roundtrip.csv"
    frame.to_csv(path, index=False, date_format="%Y-%m-%d")
    pd.testing.assert_frame_equal(frame, inspection._read_csv_like(path, frame))
    assert inspection._records(frame)[1]["score"] is None
