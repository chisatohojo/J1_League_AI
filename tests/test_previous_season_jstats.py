import csv
from pathlib import Path

import pytest

from src.features.previous_season_jstats import TARGET_PROFILE_MAPPING, build_previous_season_jstats_features


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
    assert all(int(r["home_profile_season"]) < int(r["season"]) if r["season"] != "2026/27" else r["home_profile_season"] == "2025" for r in rows)


def test_hyakunen_is_not_a_target():
    assert all("hyakunen" not in str(key).lower() for key in TARGET_PROFILE_MAPPING)
