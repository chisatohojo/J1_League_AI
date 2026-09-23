import csv
from pathlib import Path

import pytest

from src.features.previous_season_jstats import (
    TARGET_PROFILE_MAPPING,
    _load_profiles,
    _team_profiles,
    _validate_target_identities,
    build_previous_season_jstats_features,
)


def test_explicit_mapping_and_target_scope():
    assert TARGET_PROFILE_MAPPING == {2020: 2019, 2021: 2020, 2022: 2021,
                                      2023: 2022, 2024: 2023, 2025: 2024,
                                      "2026/27": 2025}
    assert "2026_hyakunen" not in str(TARGET_PROFILE_MAPPING)


def test_build_is_deterministic_and_excludes_same_season_profile(tmp_path):
    path1 = tmp_path / "one.csv"; path2 = tmp_path / "two.csv"
    first = build_previous_season_jstats_features(output_path=path1)
    second = build_previous_season_jstats_features(output_path=path2)
    assert first["row_count"] == second["row_count"]
    assert path1.read_bytes() == path2.read_bytes()
    with path1.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert "fixture_key" in rows[0]
    assert all(int(r["home_profile_season"]) < int(r["season"]) if r["season"] != "2026/27" else r["home_profile_season"] == "2025" for r in rows)
    future = [r for r in rows if r["season"] == "2026/27"]
    assert all(r["fixture_key"] for r in future)
    assert all(r["match_id"] != r["fixture_key"] for r in future)
    historical = [r for r in rows if r["season"] != "2026/27"]
    assert len({r["match_id"] for r in historical}) == len(historical)
    assert len({r["fixture_key"] for r in future}) == len(future)


def test_hyakunen_is_not_a_target():
    assert all("hyakunen" not in str(key).lower() for key in TARGET_PROFILE_MAPPING)


def _profile_row(**overrides):
    row = {"profile_season": "2019", "team_id": "team_0001", "stat_name": "expected_goals",
           "raw_value": "10", "derived_value": "0.5", "games_played_basis": "20",
           "retrieval_id": "test"}
    row.update(overrides)
    return row


def _write_profile(path, rows):
    fields = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def test_duplicate_profile_season_team_stat_hard_fails(tmp_path):
    path = tmp_path / "profiles.csv"; _write_profile(path, [_profile_row(), _profile_row()])
    with pytest.raises(ValueError, match="Duplicate profile"):
        _load_profiles(path)


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-1"])
def test_invalid_numeric_profile_hard_fails(tmp_path, raw):
    path = tmp_path / "profiles.csv"; _write_profile(path, [_profile_row(raw_value=raw)])
    with pytest.raises(ValueError): _load_profiles(path)


def test_derived_value_mismatch_hard_fails(tmp_path):
    path = tmp_path / "profiles.csv"; _write_profile(path, [_profile_row(derived_value="0.51")])
    with pytest.raises(ValueError): _load_profiles(path)


def test_invalid_games_played_basis_hard_fails(tmp_path):
    path = tmp_path / "profiles.csv"; _write_profile(path, [_profile_row(games_played_basis="0")])
    with pytest.raises(ValueError): _load_profiles(path)


def test_partial_profile_hard_fails():
    profiles = {("2019", "team_0001", "expected_goals"): _profile_row()}
    with pytest.raises(ValueError, match="Partial previous profile"):
        _team_profiles(profiles, "2019", "team_0001", 2020)


def test_duplicate_historical_match_id_hard_fails():
    rows = [{"match_id": "m1"}, {"match_id": "m1"}]
    with pytest.raises(ValueError, match="match_id"):
        _validate_target_identities(2020, rows)


def test_duplicate_2026_fixture_key_hard_fails():
    rows = [{"match_id": "", "fixture_key": "f1"}, {"match_id": "m2", "fixture_key": "f1"}]
    with pytest.raises(ValueError, match="fixture_key"):
        _validate_target_identities("2026/27", rows)
