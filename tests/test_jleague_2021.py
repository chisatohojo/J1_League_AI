"""Shared full-season checks and the verified 20-club 2021 format.

All schedules are artificial. Expected counts are written independently of the
production format settings. The 2017 golden was captured from commit 3116b12.
"""

from datetime import date, timedelta
import hashlib
from html import escape
import json
import os
from pathlib import Path
import socket
import sys
import urllib.request

import pandas as pd
import pytest

from scripts import inspect_jleague
from src.collect.jleague import (
    build_review_summary, parse_matches_html, read_cached_matches, summarize_matches,
)
from src.collect.matches import load_matches, validate_matches


HEADERS = (
    "シーズン", "大会", "節", "試合日", "K/O時刻", "ホーム", "スコア",
    "アウェイ", "スタジアム", "入場者数", "インターネット中継・TV放送",
)
MATCH_COLUMNS = [
    "match_id", "season", "round", "match_date", "home_team", "away_team",
    "stadium", "home_score", "away_score", "result", "stage", "competition",
    "round_label", "kickoff_time", "source_url",
]
GOLDEN_PATH = Path(__file__).parent / "fixtures/jleague_refactor/2017_output_hashes.json"


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
        '<table><tr><td>試合データ以外の案内</td></tr></table>'
        f'<table class="table-base00 search-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table>'
    )


def _single_match_html(**changes):
    values = {
        "season": "2021", "competition": "Ｊ１", "round_label": "第３８節第１日",
        "date_label": "21/12/04(土)", "kickoff": "14:03",
        "home": "人工Ｇ大阪", "score": "2-1", "away": "人工川崎Ｆ",
        "stadium": "人工ＢＭＷス", "attendance": "12,345", "broadcast": "人工放送",
    }
    values.update(changes)
    return _html([("002021123", list(values.values()))])


def _season_html(year, club_count=20):
    """Circle-method schedule with two legs and no production configuration."""
    clubs = [f"人工クラブ{number:02d}" for number in range(club_count)]
    clubs[0:2] = ["人工Ｇ00", "人工Ｆ01"]
    rotating = clubs.copy()
    rounds = []
    for _ in range(club_count - 1):
        middle = club_count // 2
        rounds.append(list(zip(rotating[:middle], reversed(rotating[middle:]))))
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    rows = []
    for leg in range(2):
        for local_round, pairs in enumerate(rounds, 1):
            annual_round = local_round + leg * (club_count - 1)
            for pair_number, (home, away) in enumerate(pairs):
                if leg:
                    home, away = away, home
                round_number = local_round if year == 2016 else annual_round
                competition = ("Ｊ１ １ｓｔ", "Ｊ１ ２ｎｄ")[leg] if year == 2016 else "Ｊ１"
                match_date = date(year, 2, 27) + timedelta(days=(annual_round - 1) * 7)
                score = ("0-1", "1-1", "2-1")[pair_number % 3]
                rows.append((f"0{year}{len(rows) + 1:04d}", [
                    str(year), competition, f"第{round_number}節第１日",
                    match_date.strftime("%y/%m/%d") + "(土・祝)",
                    "14:03", home, score, away, f"人工会場|{home}", "12,345", "人工放送",
                ]))
    # Sorting by date or ID must remain detectable in both data and golden tests.
    return _html(rows[-3:] + rows[:-3])


def _write_cache(root, year, club_count):
    raw_dir = root / "data/raw/jleague"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{year}_j1_search.html"
    raw = _season_html(year, club_count).encode("utf-8")
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
        pytest.fail("Cached season inspection attempted network access.")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)


@pytest.fixture
def season_2021():
    return parse_matches_html(_season_html(2021), expected_season=2021)


@pytest.fixture
def offline_cache(tmp_path):
    _write_cache(tmp_path, 2017, 18)
    raw_dir = _write_cache(tmp_path, 2021, 20)
    return tmp_path, raw_dir


@pytest.mark.parametrize("competition", ["Ｊ１", "J1"])
def test_2021_parser_accepts_round_38_and_preserves_source_fields(competition):
    matches = parse_matches_html(_single_match_html(competition=competition), expected_season=2021)
    assert matches.columns.tolist() == MATCH_COLUMNS
    assert matches.loc[0].to_dict() == {
        "match_id": "002021123", "season": 2021, "round": 38,
        "match_date": pd.Timestamp("2021-12-04"), "home_team": "人工Ｇ大阪",
        "away_team": "人工川崎Ｆ", "stadium": "人工ＢＭＷス",
        "home_score": 2, "away_score": 1, "result": 2,
        "stage": "full_season", "competition": competition,
        "round_label": "第３８節第１日", "kickoff_time": "14:03",
        "source_url": "https://data.j-league.or.jp/SFMS02/?match_card_id=002021123",
    }
    assert matches.match_id.dtype == pd.StringDtype()
    assert str(matches.match_date.dtype) == "datetime64[ns]"
    for column in ("season", "round", "home_score", "away_score", "result"):
        assert str(matches[column].dtype) == "int64"


@pytest.mark.parametrize("changes", [
    {"round_label": "第３９節第１日"}, {"round_label": "第０節第１日"},
    {"competition": "Ｊ１ １ｓｔ"}, {"competition": "Ｊ１ ２ｎｄ"},
    {"season": "2017"}, {"date_label": "17/12/04(土)"},
])
def test_2021_parser_rejects_unverified_format_values(changes):
    with pytest.raises(ValueError):
        parse_matches_html(_single_match_html(**changes), expected_season=2021)


@pytest.mark.parametrize("broadcast", [
    "人工放送 ※懲罰決定により試合結果を2-3から0-3に変更",
    "人工放送 ※ホームとアウェイを入れ替えて開催",
])
def test_2021_source_cells_take_precedence_over_broadcast_annotations(broadcast):
    matches = parse_matches_html(
        _single_match_html(score="0-3", broadcast=broadcast), expected_season=2021
    )
    assert matches.loc[0, ["home_score", "away_score", "result"]].tolist() == [0, 3, 0]
    assert matches.loc[0, ["home_team", "away_team"]].tolist() == ["人工Ｇ大阪", "人工川崎Ｆ"]
    assert matches.columns.tolist() == MATCH_COLUMNS


@pytest.mark.parametrize("year, club_count, rounds, match_count", [
    (2018, 18, 34, 306), (2019, 18, 34, 306), (2020, 18, 34, 306),
    (2021, 20, 38, 380),
])
def test_full_season_passes_existing_validation_and_review(year, club_count, rounds, match_count):
    matches = parse_matches_html(_season_html(year, club_count), expected_season=year)
    original = matches.copy(deep=True)
    pd.testing.assert_frame_equal(validate_matches(matches), original)
    summary = build_review_summary(matches, expected_season=year)
    assert summary["columns"] == MATCH_COLUMNS
    assert summary["season"] == year
    assert summary["matches"] == summary["match_id_count"] == match_count
    assert summary["club_count"] == club_count
    assert all(counts == {"total": rounds, "home": rounds // 2, "away": rounds // 2}
               for counts in summary["club_match_counts"].values())
    assert summary["round_counts"] == dict.fromkeys(range(1, rounds + 1), club_count // 2)
    assert set(summary["stages"]) == {"full_season"}
    assert set(matches.competition) == {"Ｊ１"}
    stage = summary["stages"]["full_season"]
    assert stage["matches"] == match_count
    assert stage["round_counts"] == summary["round_counts"]
    assert set(stage["club_appearances"].values()) == {rounds}
    assert summary["result_counts"] == (
        {0: 152, 1: 114, 2: 114} if club_count == 20 else {0: 102, 1: 102, 2: 102}
    )
    assert summary["missing_counts"] == summary["blank_counts"] == dict.fromkeys(MATCH_COLUMNS, 0)
    for field in (
        "duplicate_rows", "duplicate_match_ids", "duplicate_matches", "same_team_rows",
        "score_result_mismatches", "negative_score_rows",
    ):
        assert summary[field] == 0
    assert summary["date_min"] == f"{year}-02-27"
    assert summary["date_max"] == (date(year, 2, 27) + timedelta(days=(rounds - 1) * 7)).isoformat()
    display = matches.copy(deep=True)
    display["match_date"] = display["match_date"].dt.strftime("%Y-%m-%d")
    assert summary["first_five"] == display.head(5).to_dict("records")
    assert summary["last_five"] == display.tail(5).to_dict("records")
    assert summary["random_ten"] == display.sample(n=10, random_state=42).to_dict("records")
    assert summary["random_state"] == 42
    assert summary["adjacent_date_decreases"] == 1
    assert matches.match_id.tolist() == (
        [f"0{year}{number:04d}" for number in range(match_count - 2, match_count + 1)]
        + [f"0{year}{number:04d}" for number in range(1, match_count - 2)]
    )
    assert matches.source_url.tolist() == [
        f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}"
        for match_id in matches.match_id
    ]
    assert {"人工Ｇ00", "人工Ｆ01"} <= set(summary["clubs"])
    assert summary["stadiums"] == sorted(f"人工会場|{club}" for club in summary["clubs"])
    pd.testing.assert_frame_equal(matches, original)


def test_2021_does_not_infer_expected_club_count_from_incomplete_source():
    matches = parse_matches_html(_season_html(2021, 18), expected_season=2021)
    assert len(matches) == 306
    pd.testing.assert_frame_equal(validate_matches(matches), matches)
    with pytest.raises(ValueError):
        summarize_matches(matches, expected_season=2021)
    with pytest.raises(ValueError):
        build_review_summary(matches, expected_season=2021)


@pytest.mark.parametrize("failure", ["one_match", "whole_round", "wrong_stage", "round_39"])
def test_2021_review_rejects_incomplete_or_wrong_structure(season_2021, failure):
    if failure == "one_match":
        season_2021 = season_2021.iloc[:-1]
    elif failure == "whole_round":
        season_2021 = season_2021.loc[season_2021["round"] != 20]
    elif failure == "wrong_stage":
        season_2021.loc[0, "stage"] = "1st"
    else:
        season_2021.loc[season_2021["round"] == 38, "round"] = 39
    with pytest.raises(ValueError):
        build_review_summary(season_2021, expected_season=2021)


def test_2021_review_rejects_uneven_home_away(season_2021):
    home, away = season_2021.loc[0, ["home_team", "away_team"]]
    season_2021.loc[0, ["home_team", "away_team"]] = [away, home]
    assert len(season_2021) == 380
    with pytest.raises(ValueError):
        build_review_summary(season_2021, expected_season=2021)


def test_2021_rejects_round_club_repeats_even_with_all_annual_counts_preserved(season_2021):
    matches = season_2021.sort_values("match_id").reset_index(drop=True)
    # Swapping round membership leaves every fixture, annual club count, venue
    # split and each round's ten-row count intact, but two clubs miss a round.
    matches.loc[[0, 10], "round"] = [2, 1]
    matches.loc[[0, 10], "round_label"] = ["第2節第１日", "第1節第１日"]
    assert matches.home_team.value_counts().eq(19).all()
    assert matches.away_team.value_counts().eq(19).all()
    assert matches["round"].value_counts().eq(10).all()
    assert len(matches[["home_team", "away_team"]].drop_duplicates()) == 380
    pd.testing.assert_frame_equal(validate_matches(matches), matches)
    with pytest.raises(ValueError):
        build_review_summary(matches, expected_season=2021)


def test_2021_rejects_missing_pairs_even_with_balanced_clubs_and_rounds(season_2021):
    matches = season_2021.sort_values("match_id").reset_index(drop=True)
    # Swap two away opponents and their return-leg home clubs. All club and
    # round counts stay valid, but some unordered opponents are repeated.
    for offset, column in ((0, "away_team"), (190, "home_team")):
        matches.loc[[offset, offset + 1], column] = (
            matches.loc[[offset, offset + 1], column].tolist()[::-1]
        )
    assert matches.home_team.value_counts().eq(19).all()
    assert matches.away_team.value_counts().eq(19).all()
    assert matches["round"].value_counts().eq(10).all()
    pd.testing.assert_frame_equal(validate_matches(matches), matches)
    with pytest.raises(ValueError):
        build_review_summary(matches, expected_season=2021)


def test_2021_rejects_repeated_host_direction_despite_balanced_annual_counts(season_2021):
    matches = season_2021.copy(deep=True)
    clubs = sorted(set(matches.home_team))[:3]
    # Reversing a directed triangle changes no club's annual home/away count.
    # Each pair still meets twice but now both meetings have the same host.
    for home, away in zip(clubs, clubs[1:] + clubs[:1]):
        index = matches.index[(matches.home_team == home) & (matches.away_team == away)]
        assert len(index) == 1
        matches.loc[index, ["home_team", "away_team"]] = [away, home]
    assert matches.home_team.value_counts().eq(19).all()
    assert matches.away_team.value_counts().eq(19).all()
    pd.testing.assert_frame_equal(validate_matches(matches), matches)
    with pytest.raises(ValueError):
        build_review_summary(matches, expected_season=2021)


def test_2021_comparison_uses_2017_without_assuming_adjacent_seasons(season_2021):
    before = parse_matches_html(_season_html(2017, 18), expected_season=2017)
    comparison = inspect_jleague.compare_years(
        before, season_2021, before_season=2017, after_season=2021
    )
    assert comparison["2017"]["matches"] == 306
    assert comparison["2021"]["matches"] == 380
    assert "2020" not in comparison
    assert comparison["columns_equal"] is True
    assert comparison["stage_labels_equal"] is True
    assert comparison["clubs_added"] == ["人工クラブ18", "人工クラブ19"]
    assert comparison["clubs_removed"] == []
    assert comparison["shared_match_ids"] == []
    assert comparison["names_preserved"] is True


@pytest.mark.parametrize("year, club_count", [(2018, 18), (2019, 18), (2020, 18), (2021, 20)])
def test_full_season_reuses_verified_cache_without_changing_originals(tmp_path, year, club_count):
    raw_dir = _write_cache(tmp_path, year, club_count)
    original = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    matches, metadata = read_cached_matches(year, raw_dir=raw_dir)
    pd.testing.assert_frame_equal(
        matches, parse_matches_html(_season_html(year, club_count), expected_season=year)
    )
    assert metadata["sha256"] == hashlib.sha256(original[f"{year}_j1_search.html"]).hexdigest()
    assert metadata["bytes"] == len(original[f"{year}_j1_search.html"])
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == original


@pytest.mark.parametrize("field, value", [
    ("requested_url", "https://data.j-league.or.jp/SFMS01/search?competition_years=2020"),
    ("final_url", "https://example.com/2021"), ("status", 404),
    ("bytes", 0), ("sha256", "0" * 64), ("fetched_at_utc", ""),
])
def test_2021_invalid_metadata_stops_before_outputs(offline_cache, field, value):
    root, raw_dir = offline_cache
    path = raw_dir / "2021_j1_search.metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata[field] = value
    path.write_text(json.dumps(metadata), encoding="utf-8")
    original = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    with pytest.raises(ValueError):
        inspect_jleague.run_inspection(2021, root=root)
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == original
    assert not (root / "data/processed/jleague").exists()


@pytest.mark.parametrize("filename", [
    "2021_j1_search.html", "2021_j1_search.metadata.json", "2017_j1_search.html",
])
def test_2021_missing_cache_stops_without_fetch(offline_cache, filename):
    root, raw_dir = offline_cache
    (raw_dir / filename).unlink()
    original = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    with pytest.raises(FileNotFoundError):
        inspect_jleague.run_inspection(2021, root=root)
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == original
    assert not (root / "data/processed/jleague").exists()


@pytest.mark.parametrize("year, before_year, club_count", [
    (2018, 2017, 18), (2019, 2018, 18), (2020, 2019, 18), (2021, 2017, 20),
])
def test_full_season_cli_preserves_baseline_outputs_and_is_reproducible(
    tmp_path, monkeypatch, year, before_year, club_count,
):
    root = tmp_path
    _write_cache(root, before_year, 18)
    raw_dir = _write_cache(root, year, club_count)
    raw_original = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    output_dir = root / "data/processed/jleague"
    output_dir.mkdir(parents=True)
    before = parse_matches_html(_season_html(before_year, 18), expected_season=before_year)
    before.to_csv(output_dir / f"{before_year}_matches_probe.csv", index=False, date_format="%Y-%m-%d")
    (output_dir / f"{before_year}_matches_probe.summary.json").write_text('{"preserve": true}\n', encoding="utf-8")
    (output_dir / f"{before_year}_matches_probe.review.md").write_text("Preserve this prior review.\n", encoding="utf-8")
    old_outputs = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    run_inspection = inspect_jleague.run_inspection
    monkeypatch.setattr(inspect_jleague, "run_inspection", lambda year: run_inspection(year, root=root))
    monkeypatch.setattr(sys, "argv", ["inspect_jleague", "--year", str(year)])
    inspect_jleague.main()
    expected = parse_matches_html(_season_html(year, club_count), expected_season=year)
    pd.testing.assert_frame_equal(load_matches(output_dir / f"{year}_matches_probe.csv"), expected)
    summary = json.loads((output_dir / f"{year}_matches_probe.summary.json").read_text(encoding="utf-8"))
    assert summary["season"] == year
    assert summary["network_requests"] == 0
    assert summary["csv_roundtrip_validated"] is True
    assert summary["metadata_sha256_verified"] is True
    assert summary[f"baseline_{before_year}_sha256"] == hashlib.sha256(
        raw_original[f"{before_year}_j1_search.html"]
    ).hexdigest()
    assert summary["comparison"][str(before_year)]["matches"] == 306
    assert summary["comparison"][str(year)]["matches"] == len(expected)
    review = (output_dir / f"{year}_matches_probe.review.md").read_text(encoding="utf-8")
    for text in (f"{year}年J1", f"{before_year}年との差分", "full_season",
                 f"1～{(club_count - 1) * 2}節", "random_state=42", "人工会場\\|"):
        assert text in review
    outputs = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    assert set(outputs) == set(old_outputs) | {
        f"{year}_matches_probe.csv", f"{year}_matches_probe.summary.json", f"{year}_matches_probe.review.md",
    }
    for filename, original in old_outputs.items():
        assert outputs[filename] == original
    inspect_jleague.main()
    assert {path.name: path.read_bytes() for path in output_dir.iterdir()} == outputs
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == raw_original


def test_2021_format_change_preserves_2017_output_bytes_from_committed_implementation(tmp_path):
    raw_dir = _write_cache(tmp_path, 2016, 18)
    _write_cache(tmp_path, 2017, 18)
    original = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    inspect_jleague.run_inspection(2017, root=tmp_path)
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    newline_key = "sha256_crlf" if os.linesep == "\r\n" else "sha256_lf"
    output_dir = tmp_path / "data/processed/jleague"
    assert set(path.name for path in output_dir.iterdir()) == set(golden["outputs"])
    for filename, expected in golden["outputs"].items():
        assert hashlib.sha256((output_dir / filename).read_bytes()).hexdigest() == expected[newline_key], filename
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == original
