from pathlib import Path

import pandas as pd
import pytest

import src.collect.jleague_match_stats_season as season
import src.collect.jleague_match_stats as single
from src.collect.jleague_match_stats import OUTPUT_COLUMNS


def matches():
    return pd.DataFrame({
        "match_id": ["1", "2"], "season": [2015, 2015],
        "match_date": pd.to_datetime(["2015-03-07", "2015-03-14"]),
        "home_team": ["A", "C"], "away_team": ["B", "D"],
    })


def stats(match_id):
    even = int(match_id) % 2 == 0
    row = {
        "match_id": match_id, "home_team": "A" if even else "C",
        "away_team": "B" if even else "D",
        "home_shots": 1, "away_shots": 2, "home_ck": 3, "away_ck": 4,
        "home_fk": 5, "away_fk": 6,
        "source_url": f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}",
    }
    return pd.DataFrame([row], columns=OUTPUT_COLUMNS)


class RecordingTeamMaster:
    def __init__(self):
        self.calls = []

    def resolve_team_id(self, name, *, source, on):
        self.calls.append((name, source, on))
        return {"A": "team_0001", "B": "team_0002", "C": "team_0003", "D": "team_0004"}[name]


def test_wrapper_reuses_parser_fetch_and_preserves_input(monkeypatch, tmp_path):
    original = matches()
    calls = []
    monkeypatch.setattr(season, "fetch_match_stats", lambda match_id, raw_dir: calls.append(match_id) or stats(match_id))
    monkeypatch.setattr(season, "time", type("Clock", (), {"sleep": staticmethod(lambda _: None)}))
    # The production wrapper is fixed to 306; exercise validation with a patched source size.
    source = pd.concat([original] * 153, ignore_index=True)
    source["match_id"] = [str(i) for i in range(306)]
    source["home_team"] = ["A" if i % 2 == 0 else "C" for i in range(306)]
    source["away_team"] = ["B" if i % 2 == 0 else "D" for i in range(306)]
    def fake_fetch(match_id, raw_dir):
        calls.append(match_id)
        return stats(match_id)
    monkeypatch.setattr(season, "fetch_match_stats", fake_fetch)
    source["match_date"] = pd.Timestamp("2015-03-07")
    master = RecordingTeamMaster()
    result = season.collect_match_stats_for_season(source, season=2015, raw_dir=tmp_path, output_path=tmp_path / "out.csv", request_interval_seconds=0, team_master=master)
    assert len(result) == 306 and result["match_id"].is_unique
    assert set(result[["home_team_id", "away_team_id"]].columns) == {"home_team_id", "away_team_id"}
    assert {call[1] for call in master.calls} == {"jleague_data_site", "jleague_official"}
    assert all(call[2] == pd.Timestamp("2015-03-07") for call in master.calls)
    pd.testing.assert_frame_equal(original, matches())
    assert len(calls) == 306
    assert (tmp_path / "out.csv").exists()


def test_rejects_non_2015_or_wrong_count(tmp_path):
    with pytest.raises(ValueError):
        season.collect_match_stats_for_season(matches(), season=2016, raw_dir=tmp_path, output_path=tmp_path / "x.csv")


@pytest.mark.parametrize("column", ["home_shots", "home_ck", "home_fk"])
def test_validation_rejects_missing_stats(column):
    frame = stats("1").copy()
    frame.loc[0, column] = pd.NA
    with pytest.raises(ValueError):
        result = pd.concat([frame, stats("2")], ignore_index=True)
        result.insert(3, "home_team_id", ["team_0001", "team_0003"])
        result.insert(4, "away_team_id", ["team_0002", "team_0004"])
        season._validate_result(result, matches())


def test_validation_rejects_negative_and_url_mismatch():
    frame = pd.concat([stats("1"), stats("2")], ignore_index=True)
    frame.insert(3, "home_team_id", ["team_0001", "team_0003"])
    frame.insert(4, "away_team_id", ["team_0002", "team_0004"])
    frame.loc[0, "home_shots"] = -1
    with pytest.raises(ValueError):
        season._validate_result(frame, matches())
    frame.loc[0, "home_shots"] = 1
    frame.loc[0, "source_url"] = frame.loc[0, "source_url"].replace("=1", "=9")
    with pytest.raises(ValueError):
        season._validate_result(frame, matches())


def test_real_2015_cache_has_306_identity_safe_rows_without_refetch(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("cache validation attempted a refetch")
    monkeypatch.setattr(single, "urlopen", forbidden)
    result = season.collect_2015_match_stats(
        raw_dir="data/raw/jleague_match_stats",
        output_path=tmp_path / "2015_match_stats.csv",
        request_interval_seconds=0,
    )
    assert len(result) == 306
    assert result["match_id"].is_unique
    assert result[["home_team_id", "away_team_id"]].notna().all().all()
    assert len(pd.read_csv(tmp_path / "2015_match_stats.csv")) == 306
