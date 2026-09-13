"""Offline checks for the verified 2017 single-stage format.

All HTML and seasons here are artificial; no downloaded data is needed.
The existing 2015/2016 golden outputs remain independent regression fixtures.
"""

from datetime import date, timedelta
import hashlib
from html import escape
import json
import socket
import sys
import urllib.request

import pandas as pd
import pytest

from scripts import inspect_jleague
from src.collect.jleague import (
    build_review_summary, parse_matches_html, read_cached_matches, summarize_matches,
)
from src.collect.matches import load_matches


HEADERS = (
    "シーズン", "大会", "節", "試合日", "K/O時刻", "ホーム", "スコア",
    "アウェイ", "スタジアム", "入場者数", "インターネット中継・TV放送",
)
MATCH_COLUMNS = [
    "match_id", "season", "round", "match_date", "home_team", "away_team",
    "stadium", "home_score", "away_score", "result", "stage", "competition",
    "round_label", "kickoff_time", "source_url",
]


def _html(rows):
    header = "".join(f"<th>{escape(value)}</th>" for value in HEADERS)
    body = []
    for match_id, values in rows:
        cells = [f"<td>{escape(value)}</td>" for value in values]
        cells[6] = (
            f'<td><a href="/SFMS02/?match_card_id={match_id}">'
            f'{escape(values[6])}</a></td>'
        )
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<table><tr><td>2018年の案内は試合データではない</td></tr></table>'
        f'<table class="table-base00 search-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


def _single_match_html(year=2017, **changes):
    values = {
        "season": str(year), "competition": "Ｊ１", "round_label": "第３４節第１日",
        "date_label": f"{year % 100}/12/02(土)", "kickoff": "14:03",
        "home": "人工Ｇ大阪", "score": "2-1", "away": "人工川崎Ｆ",
        "stadium": "人工ＢＭＷス", "attendance": "12,345", "broadcast": "人工放送",
    }
    values.update(changes)
    return _html([("002017123", list(values.values()))])


def _season_html(year):
    """A complete double round robin, reversing each fixture's home and away."""
    clubs = [f"人工クラブ{number:02d}" for number in range(18)]
    clubs[0:2] = ["人工Ｇ00", "人工Ｆ01"]
    rotating = clubs.copy()
    rounds = []
    for _ in range(17):
        rounds.append(list(zip(rotating[:9], reversed(rotating[9:]))))
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    rows = []
    for half in range(2):
        for local_round, pairs in enumerate(rounds, 1):
            annual_round = local_round + half * 17
            for pair_number, (home, away) in enumerate(pairs):
                if half:
                    home, away = away, home
                round_number = annual_round if year == 2017 else local_round
                competition = "Ｊ１" if year == 2017 else ("Ｊ１ １ｓｔ", "Ｊ１ ２ｎｄ")[half]
                match_date = date(year, 2, 25) + timedelta(days=(annual_round - 1) * 7)
                score = ("0-1", "1-1", "2-1")[pair_number % 3]
                rows.append((f"0{year}{len(rows) + 1:04d}", [
                    str(year), competition, f"第{round_number}節第１日",
                    match_date.strftime("%y/%m/%d") + "(土・祝)",
                    "14:03", home, score, away, f"人工会場|{home}", "12,345", "人工放送",
                ]))
    # Non-chronological order makes accidental sorting visible.
    return _html(rows[-3:] + rows[:-3])


def _write_cache(root, year):
    raw_dir = root / "data/raw/jleague"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{year}_j1_search.html"
    raw = _season_html(year).encode("utf-8")
    raw_path.write_bytes(raw)
    url = (
        "https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1"
        f"&competition_years={year}&tv_relay_station_name="
    )
    metadata = {
        "requested_url": url, "final_url": url, "status": 200,
        "fetched_at_utc": "2026-09-13T00:00:00+00:00",
        "content_type": "text/html;charset=UTF-8",
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
    }
    raw_path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return raw_dir


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Cached 2017 inspection attempted network access.")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)


@pytest.fixture
def season_2017():
    return parse_matches_html(_season_html(2017), expected_season=2017)


@pytest.fixture
def offline_cache(tmp_path):
    # A 2017 report needs the previous season, but no 2015 cache.
    for year in (2016, 2017):
        raw_dir = _write_cache(tmp_path, year)
    return tmp_path, raw_dir


@pytest.mark.parametrize("competition", ["Ｊ１", "J1"])
def test_2017_parser_preserves_single_stage_source_fields(competition):
    matches = parse_matches_html(
        _single_match_html(competition=competition), expected_season=2017
    )
    assert matches.columns.tolist() == MATCH_COLUMNS
    assert matches.loc[0].to_dict() == {
        "match_id": "002017123", "season": 2017, "round": 34,
        "match_date": pd.Timestamp("2017-12-02"), "home_team": "人工Ｇ大阪",
        "away_team": "人工川崎Ｆ", "stadium": "人工ＢＭＷス",
        "home_score": 2, "away_score": 1, "result": 2,
        "stage": "full_season", "competition": competition,
        "round_label": "第３４節第１日", "kickoff_time": "14:03",
        "source_url": "https://data.j-league.or.jp/SFMS02/?match_card_id=002017123",
    }
    assert matches.match_id.dtype == pd.StringDtype()
    assert str(matches.match_date.dtype) == "datetime64[ns]"
    for column in ("season", "round", "home_score", "away_score", "result"):
        assert str(matches[column].dtype) == "int64"


@pytest.mark.parametrize("changes", [
    {"competition": "Ｊ１ １ｓｔ"}, {"competition": "Ｊ１ ２ｎｄ"},
    {"competition": "Ｊ１チャンピオンシップ"}, {"competition": "Ｊ２"},
    {"round_label": "第０節第１日"}, {"round_label": "第３５節第１日"},
    {"round_label": "第１節第０日"}, {"season": "2016"},
    {"date_label": "16/12/02(土)"}, {"date_label": "17/02/29(水)"},
    {"score": "-1-0"}, {"score": "試合中止"}, {"home": "人工川崎Ｆ"},
    {"stadium": " "}, {"kickoff": "25:00"},
])
def test_2017_parser_rejects_incompatible_or_invalid_values(changes):
    with pytest.raises(ValueError):
        parse_matches_html(_single_match_html(**changes), expected_season=2017)


@pytest.mark.parametrize("year", [2015, 2016])
def test_single_stage_label_does_not_weaken_earlier_year_rules(year):
    html = _single_match_html(year, round_label="第１節第１日")
    with pytest.raises(ValueError):
        parse_matches_html(html, expected_season=year)
    legacy = parse_matches_html(_season_html(year), expected_season=year)
    summary = summarize_matches(legacy, expected_season=year)
    assert summary["matches"] == 306
    assert set(summary["stages"]) == {"1st", "2nd"}
    assert set(legacy["round"]) == set(range(1, 18))


def test_2017_review_covers_34_rounds_and_all_quality_fields(season_2017):
    original = season_2017.copy(deep=True)
    summary = build_review_summary(season_2017, expected_season=2017)
    assert summary["season"] == 2017
    assert summary["columns"] == MATCH_COLUMNS
    assert summary["matches"] == summary["match_id_count"] == 306
    assert summary["club_count"] == 18
    assert all(counts == {"total": 34, "home": 17, "away": 17}
               for counts in summary["club_match_counts"].values())
    assert summary["round_counts"] == dict.fromkeys(range(1, 35), 9)
    assert set(summary["stages"]) == {"full_season"}
    stage = summary["stages"]["full_season"]
    assert stage["matches"] == 306
    assert stage["round_counts"] == summary["round_counts"]
    assert set(stage["club_appearances"].values()) == {34}
    assert summary["result_counts"] == {0: 102, 1: 102, 2: 102}
    assert summary["missing_counts"] == summary["blank_counts"] == dict.fromkeys(MATCH_COLUMNS, 0)
    for field in (
        "duplicate_rows", "duplicate_match_ids", "duplicate_matches", "same_team_rows",
        "score_result_mismatches", "negative_score_rows",
    ):
        assert summary[field] == 0
    assert summary["date_min"] == "2017-02-25"
    assert summary["date_max"] == "2017-10-14"
    display = season_2017.copy(deep=True)
    display["match_date"] = display["match_date"].dt.strftime("%Y-%m-%d")
    assert summary["first_five"] == display.head(5).to_dict("records")
    assert summary["last_five"] == display.tail(5).to_dict("records")
    assert summary["random_ten"] == display.sample(n=10, random_state=42).to_dict("records")
    assert summary["random_state"] == 42
    assert summary["adjacent_date_decreases"] == 1
    pd.testing.assert_frame_equal(season_2017, original)


@pytest.mark.parametrize("column, value", [
    ("stage", "1st"), ("round", 35), ("stage", None), ("competition", None),
    ("round_label", " "), ("source_url", " "), ("stadium", None),
    ("home_score", -1), ("result", 2), ("match_id", "020170001"),
])
def test_2017_review_rejects_invalid_normalized_data(season_2017, column, value):
    if value is None:
        season_2017[column] = season_2017[column].astype(object)
    season_2017.loc[0, column] = value
    with pytest.raises(ValueError):
        build_review_summary(season_2017, expected_season=2017)


def test_2017_review_rejects_incomplete_round(season_2017):
    with pytest.raises(ValueError):
        build_review_summary(season_2017.iloc[:-1], expected_season=2017)


def test_2017_review_rejects_unbalanced_home_away(season_2017):
    home, away = season_2017.loc[0, ["home_team", "away_team"]]
    season_2017.loc[0, ["home_team", "away_team"]] = [away, home]
    with pytest.raises(ValueError):
        build_review_summary(season_2017, expected_season=2017)


def test_2017_review_rejects_missing_pairs_despite_balanced_counts(season_2017):
    matches = season_2017.sort_values("match_id").reset_index(drop=True)
    for offset, column in ((0, "away_team"), (153, "home_team")):
        matches.loc[[offset, offset + 1], column] = (
            matches.loc[[offset, offset + 1], column].tolist()[::-1]
        )
    assert matches.home_team.value_counts().eq(17).all()
    assert matches.away_team.value_counts().eq(17).all()
    assert matches["round"].value_counts().eq(9).all()
    with pytest.raises(ValueError):
        build_review_summary(matches, expected_season=2017)


def test_2017_comparison_uses_explicit_years_and_observes_stage_change(season_2017):
    before = parse_matches_html(_season_html(2016), expected_season=2016)
    original = before.copy(deep=True)
    comparison = inspect_jleague.compare_years(
        before, season_2017, before_season=2016, after_season=2017
    )
    assert comparison["2016"]["matches"] == comparison["2017"]["matches"] == 306
    assert "2015" not in comparison
    assert comparison["columns_equal"] is True
    assert comparison["stage_labels_equal"] is False
    assert comparison["names_preserved"] is True
    assert comparison["shared_match_ids"] == []
    pd.testing.assert_frame_equal(before, original)


def test_2017_cache_reused_and_originals_preserved(offline_cache):
    _, raw_dir = offline_cache
    before = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    actual, metadata = read_cached_matches(2017, raw_dir=raw_dir)
    expected = parse_matches_html(_season_html(2017), expected_season=2017)
    pd.testing.assert_frame_equal(actual, expected)
    assert metadata["fetched_at_utc"] == "2026-09-13T00:00:00+00:00"
    assert metadata["sha256"] == hashlib.sha256(before["2017_j1_search.html"]).hexdigest()
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == before


@pytest.mark.parametrize("field, value", [
    ("requested_url", "https://data.j-league.or.jp/SFMS01/search?competition_years=2016"),
    ("final_url", "https://example.com/2017"), ("status", 404),
    ("bytes", 0), ("sha256", "0" * 64), ("fetched_at_utc", ""),
    ("fetched_at_utc", None),
])
def test_2017_cache_rejects_invalid_metadata_without_writing(offline_cache, field, value):
    root, raw_dir = offline_cache
    metadata_path = raw_dir / "2017_j1_search.metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    before = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    with pytest.raises(ValueError):
        inspect_jleague.run_inspection(2017, root=root)
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == before
    assert not (root / "data/processed/jleague").exists()


@pytest.mark.parametrize("filename", [
    "2017_j1_search.html", "2017_j1_search.metadata.json", "2016_j1_search.html",
])
def test_2017_inspection_requires_complete_cache_without_fetch(offline_cache, filename):
    root, raw_dir = offline_cache
    (raw_dir / filename).unlink()
    before = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    with pytest.raises(FileNotFoundError):
        inspect_jleague.run_inspection(2017, root=root)
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == before
    assert not (root / "data/processed/jleague").exists()


def test_2017_cli_writes_valid_reproducible_outputs_without_2015_cache(offline_cache, monkeypatch):
    root, raw_dir = offline_cache
    original = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    run_inspection = inspect_jleague.run_inspection
    monkeypatch.setattr(inspect_jleague, "run_inspection", lambda year: run_inspection(year, root=root))
    monkeypatch.setattr(sys, "argv", ["inspect_jleague", "--year", "2017"])
    inspect_jleague.main()
    output_dir = root / "data/processed/jleague"
    expected = parse_matches_html(_season_html(2017), expected_season=2017)
    pd.testing.assert_frame_equal(load_matches(output_dir / "2017_matches_probe.csv"), expected)
    summary = json.loads((output_dir / "2017_matches_probe.summary.json").read_text(encoding="utf-8"))
    assert summary["season"] == 2017
    assert summary["network_requests"] == 0
    assert summary["csv_roundtrip_validated"] is True
    assert summary["metadata_sha256_verified"] is True
    assert "2016" in summary["comparison"] and "2017" in summary["comparison"]
    assert summary["baseline_2016_sha256"] == hashlib.sha256(original["2016_j1_search.html"]).hexdigest()
    review = (output_dir / "2017_matches_probe.review.md").read_text(encoding="utf-8")
    assert "2017年J1" in review
    assert "2016年との差分" in review
    assert "full_season" in review
    assert "random_state=42" in review
    assert "人工会場\\|" in review
    outputs = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    assert set(outputs) == {
        "2017_matches_probe.csv", "2017_matches_probe.summary.json", "2017_matches_probe.review.md",
    }
    inspect_jleague.main()
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == outputs
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == original
