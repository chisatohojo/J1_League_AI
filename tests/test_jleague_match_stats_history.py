from pathlib import Path

import pandas as pd
import pytest

import src.collect.jleague_match_stats_history as history
from src.collect.jleague_match_stats_season import EXPECTED_MATCH_COUNTS, SEASON_OUTPUT_COLUMNS


def test_expected_counts_and_supported_years_are_fixed():
    assert tuple(EXPECTED_MATCH_COUNTS) == tuple(range(2015, 2026))
    assert EXPECTED_MATCH_COUNTS[2021] == 380
    assert EXPECTED_MATCH_COUNTS[2024] == 380
    assert history.YEARS == tuple(range(2016, 2026))


def test_2015_is_not_collected_and_unknown_season_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        history.collect_match_stats_history(years=(2015,), raw_dir=tmp_path, output_dir=tmp_path)
    with pytest.raises(ValueError):
        history.collect_match_stats_history(years=(2026,), raw_dir=tmp_path, output_dir=tmp_path)


def test_history_reuses_season_collector_and_reports_cache_counts(monkeypatch, tmp_path):
    calls = []
    frame = pd.DataFrame([{
        "match_id": "1", "home_team": "A", "away_team": "B",
        "home_team_id": "team_0001", "away_team_id": "team_0002",
        "home_shots": 1, "away_shots": 2, "home_ck": 3, "away_ck": 4,
        "home_fk": 5, "away_fk": 6, "source_url": "https://x?match_card_id=1",
    }], columns=SEASON_OUTPUT_COLUMNS)
    monkeypatch.setattr(history, "load_matches", lambda path: pd.DataFrame())
    def fake_collect(*args, **kwargs):
        calls.append(kwargs["season"])
        return frame
    monkeypatch.setattr(history, "collect_match_stats_for_season", fake_collect)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "1.html").write_text("cached", encoding="utf-8")
    results, counts = history.collect_match_stats_history(
        years=(2016,), matches_dir=tmp_path, raw_dir=raw, output_dir=tmp_path,
        team_master=object(), request_interval_seconds=0,
    )
    assert calls == [2016]
    assert list(results) == [2016]
    assert counts["network_fetches"] == 0
    assert counts["cache_hits"] == 1
