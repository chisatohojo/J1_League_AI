import hashlib
import json

import pandas as pd
import pytest

import src.collect.cup_regulation_results as cup_results
from src.collect.cup_regulation_results import (
    CupDatasetError,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_RAW_DIR,
    FROZEN_CANDIDATE_SHA256,
    MANIFEST_COLUMNS,
    OUTPUT_COLUMNS,
    build_dataset_from_cache,
    build_frozen_candidates,
    canonical_csv_bytes,
    canonical_dataset_bytes,
    freeze_candidates,
    read_valid_cache,
    required_official_lookups,
    sha256_bytes,
    validate_dataset,
    validate_frozen_candidates,
)
from src.collect.cup_regulation_result_prototype import CONFIRMED, UNRESOLVED


def _candidate_rows():
    rows = []
    for (competition, season), count in {
        ("emperors_cup", 2015): 6, ("emperors_cup", 2016): 5,
        ("emperors_cup", 2017): 8, ("emperors_cup", 2018): 12,
        ("emperors_cup", 2019): 7, ("emperors_cup", 2020): 1,
        ("emperors_cup", 2021): 6, ("emperors_cup", 2022): 14,
        ("emperors_cup", 2023): 13, ("emperors_cup", 2024): 5,
        ("jleague_cup", 2018): 16, ("jleague_cup", 2019): 14,
        ("jleague_cup", 2020): 1, ("jleague_cup", 2022): 12,
        ("jleague_cup", 2023): 12, ("jleague_cup", 2024): 13,
    }.items():
        for number in range(count):
            mid = f"{season}-{number:03d}"
            rows.append({
                "candidate_key": f"{competition}:{mid}", "competition": competition,
                "season": season, "source_match_id": mid,
                "match_date": f"{season}-01-{number + 1:02d}",
                "home_team": f"H-{competition}-{season}-{number}",
                "away_team": f"A-{competition}-{season}-{number}",
                "home_team_id": f"h-{competition}-{season}-{number}",
                "away_team_id": f"a-{competition}-{season}-{number}",
                "source_url": f"https://example.invalid/{competition}/{mid}",
            })
    return pd.DataFrame(rows, columns=MANIFEST_COLUMNS)


def test_candidate_membership_contract_is_exact_and_deterministic():
    frame = _candidate_rows()
    validate_frozen_candidates(frame)
    first = canonical_csv_bytes(frame, MANIFEST_COLUMNS)
    second = canonical_csv_bytes(frame.copy(deep=True), MANIFEST_COLUMNS)
    assert first == second
    assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()


def test_frozen_manifest_is_never_overwritten_on_mismatch(tmp_path, monkeypatch):
    frame = _candidate_rows()
    raw = canonical_csv_bytes(frame, MANIFEST_COLUMNS)
    monkeypatch.setattr(cup_results, "build_frozen_candidates", lambda **paths: frame)
    monkeypatch.setattr(cup_results, "FROZEN_CANDIDATE_SHA256", sha256_bytes(raw))
    path = tmp_path / "candidates.csv"
    path.write_bytes(b"already-frozen")
    with pytest.raises(CupDatasetError, match="saved candidate manifest differs"):
        freeze_candidates(path)
    assert path.read_bytes() == b"already-frozen"


def test_candidate_duplicate_and_same_day_identity_fail_closed():
    frame = _candidate_rows()
    frame.loc[1, "candidate_key"] = frame.loc[0, "candidate_key"]
    with pytest.raises(CupDatasetError, match="duplicate candidate_key"):
        validate_frozen_candidates(frame)
    frame = _candidate_rows()
    frame.loc[1, ["match_date", "home_team_id"]] = frame.loc[0, ["match_date", "home_team_id"]]
    with pytest.raises(CupDatasetError, match="multiple frozen candidates"):
        validate_frozen_candidates(frame)


def test_raw_cache_provenance_is_verified(tmp_path):
    raw = b"official"
    url = "https://data.j-league.or.jp/SFMS02/?match_card_id=1"
    expected = {
        "candidate_key": "jleague_cup:1", "competition": "jleague_cup",
        "season": 2018, "source_match_id": "1", "source_url": url,
    }
    raw_path = tmp_path / "source.html"
    metadata_path = tmp_path / "source.metadata.json"
    raw_path.write_bytes(raw)
    metadata = {
        "requested_url": url, "final_url": url, "status": 200,
        "retrieved_at_utc": "2026-09-29T00:00:00+00:00", "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(), "competition": "jleague_cup",
        "season": 2018, "source_match_id": "1",
    }
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    assert read_valid_cache(raw_path, metadata_path, expected=expected)[0] == raw
    metadata["sha256"] = "0" * 64
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(CupDatasetError, match="metadata mismatch"):
        read_valid_cache(raw_path, metadata_path, expected=expected)


def test_missing_cache_is_not_treated_as_valid(tmp_path):
    assert read_valid_cache(
        tmp_path / "missing.html", tmp_path / "missing.metadata.json",
        expected={"candidate_key": "x", "source_url": "x", "competition": "x",
                  "season": 2015, "source_match_id": "x"},
    ) is None
    (tmp_path / "orphan.html").write_bytes(b"orphan")
    with pytest.raises(CupDatasetError, match="incomplete raw cache pair"):
        read_valid_cache(
            tmp_path / "orphan.html", tmp_path / "orphan.metadata.json",
            expected={"candidate_key": "x", "source_url": "x", "competition": "x",
                      "season": 2015, "source_match_id": "x"},
        )


def _result_dataset(candidates):
    rows = []
    for candidate in candidates.to_dict("records"):
        rows.append({
            "candidate_key": candidate["candidate_key"],
            "competition": candidate["competition"], "season": candidate["season"],
            "source_match_id": candidate["source_match_id"],
            "match_date": candidate["match_date"],
            "home_team_id": candidate["home_team_id"],
            "away_team_id": candidate["away_team_id"],
            "regulation_home_score": 0, "regulation_away_score": 0,
            "regulation_result": 1, "extra_time_played": None,
            "penalty_shootout_played": None, "final_home_score": 0,
            "final_away_score": 0, "source_url": candidate["source_url"],
            "source_type": "test", "raw_sha256": "a" * 64,
            "resolution_status": CONFIRMED,
            "resolution_reason": "explicit_first_and_second_half_scores",
        })
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def test_dataset_duplicate_identity_and_unresolved_values_fail_closed():
    candidates = _candidate_rows()
    dataset = _result_dataset(candidates)
    validate_dataset(dataset, candidates)
    duplicate = dataset.copy(deep=True)
    duplicate.loc[1, "candidate_key"] = duplicate.loc[0, "candidate_key"]
    with pytest.raises(CupDatasetError, match="duplicate result candidate_key"):
        validate_dataset(duplicate, candidates)
    mismatch = dataset.copy(deep=True)
    mismatch.loc[0, "home_team_id"] = "wrong"
    with pytest.raises(CupDatasetError, match="differs from frozen candidates"):
        validate_dataset(mismatch, candidates)
    unresolved = dataset.copy(deep=True)
    unresolved.loc[0, "resolution_status"] = UNRESOLVED
    with pytest.raises(CupDatasetError, match="unresolved score was populated"):
        validate_dataset(unresolved, candidates)


def test_dataset_canonical_serialization_is_deterministic():
    dataset = _result_dataset(_candidate_rows())
    first = canonical_dataset_bytes(dataset)
    second = canonical_dataset_bytes(dataset.copy(deep=True))
    assert first == second
    assert sha256_bytes(first) == sha256_bytes(second)


@pytest.mark.skipif(
    not DEFAULT_MANIFEST_PATH.exists() or not DEFAULT_OUTPUT_PATH.exists(),
    reason="local materialized Cup dataset is unavailable",
)
def test_saved_dataset_rebuilds_offline_from_frozen_sources():
    candidates = build_frozen_candidates()
    manifest = canonical_csv_bytes(candidates, MANIFEST_COLUMNS)
    assert manifest == DEFAULT_MANIFEST_PATH.read_bytes()
    assert sha256_bytes(manifest) == FROZEN_CANDIDATE_SHA256
    required = required_official_lookups(candidates)
    assert len(required) == 87
    rebuilt = build_dataset_from_cache(candidates, raw_dir=DEFAULT_RAW_DIR)
    rebuilt_again = build_dataset_from_cache(candidates, raw_dir=DEFAULT_RAW_DIR)
    expected = DEFAULT_OUTPUT_PATH.read_bytes()
    assert canonical_dataset_bytes(rebuilt) == expected
    assert canonical_dataset_bytes(rebuilt_again) == expected
    assert len(rebuilt) == 145
    assert rebuilt["resolution_status"].eq(CONFIRMED).all()
