from pathlib import Path

import pandas as pd
import pytest

import src.features.match_stats_form_history as history
from src.collect.jleague_match_stats_season import SEASON_OUTPUT_COLUMNS
from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS


def frame(season, ids, dates, home, away):
    return pd.DataFrame({
        "match_id": ids, "match_date": pd.to_datetime(dates), "season": season,
        "home_team_id": home, "away_team_id": away,
    })


def stats(ids, home, away, season):
    return pd.DataFrame({
        "match_id": ids, "home_team": ["x"] * len(ids), "away_team": ["y"] * len(ids),
        "home_team_id": home, "away_team_id": away,
        "home_shots": [10] * len(ids), "away_shots": [4] * len(ids),
        "home_ck": [3] * len(ids), "away_ck": [1] * len(ids),
        "home_fk": [5] * len(ids), "away_fk": [2] * len(ids),
        "source_url": [f"https://x?match_card_id={i}" for i in ids],
    }, columns=SEASON_OUTPUT_COLUMNS)


def test_loads_by_match_id_and_continues_history_across_seasons(monkeypatch, tmp_path):
    matches = {
        2015: frame(2015, ["1", "2"], ["2015-12-01", "2015-12-02"], ["A", "B"], ["B", "A"]),
        2016: frame(2016, ["3", "4"], ["2016-01-01", "2016-01-02"], ["A", "C"], ["C", "A"]),
    }
    monkeypatch.setattr(history, "SEASONS", (2015, 2016))
    monkeypatch.setattr(history, "EXPECTED_MATCH_COUNTS", {2015: 2, 2016: 2})
    monkeypatch.setattr(history, "load_matches", lambda path: matches[int(Path(path).stem.split("_")[0])])
    for year, values in ((2015, (["1", "2"], ["A", "B"], ["B", "A"])), (2016, (["3", "4"], ["A", "C"], ["C", "A"]))):
        stats(values[0], values[1], values[2], year).to_csv(tmp_path / f"{year}_match_stats.csv", index=False)
    result = history.load_match_stats_form_history(window=5, matches_dir=tmp_path, stats_dir=tmp_path)
    assert len(result) == 4
    assert result.columns.tolist() == list(history.OUTPUT_COLUMNS)
    assert result.loc[2, "home_stats_lastn_shots_for"] == 14
    assert result.loc[2, "home_stats_lastn_shots_against"] == 14
    assert result.loc[2, "home_stats_lastn_shots_diff"] == 0
    assert all(result[column].dtype == "int64" for column in MATCH_STATS_FORM_COLUMNS)


def test_invalid_match_id_join_is_rejected(monkeypatch, tmp_path):
    matches = frame(2015, ["1", "2"], ["2015-01-01", "2015-01-02"], ["A", "B"], ["B", "A"])
    monkeypatch.setattr(history, "SEASONS", (2015,))
    monkeypatch.setattr(history, "EXPECTED_MATCH_COUNTS", {2015: 2})
    monkeypatch.setattr(history, "load_matches", lambda path: matches)
    stats(["1", "9"], ["A", "B"], ["B", "A"], 2015).to_csv(tmp_path / "2015_match_stats.csv", index=False)
    with pytest.raises(ValueError, match="match_id"):
        history.load_match_stats_form_history(stats_dir=tmp_path, matches_dir=tmp_path)
