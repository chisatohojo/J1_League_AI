"""Offline refactor regressions against outputs captured from the old scripts.

The HTML is artificial. Golden hashes were generated with the pre-refactor
2015/2016 implementations, never with the common implementation under test.
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

from src.collect.matches import load_matches


GOLDEN_PATH = Path(__file__).parent / "fixtures/jleague_refactor/legacy_output_hashes.json"
HEADERS = (
    "シーズン", "大会", "節", "試合日", "K/O時刻", "ホーム", "スコア",
    "アウェイ", "スタジアム", "入場者数", "インターネット中継・TV放送",
)
MATCH_COLUMNS = [
    "match_id", "season", "round", "match_date", "home_team", "away_team",
    "stadium", "home_score", "away_score", "result", "stage", "competition",
    "round_label", "kickoff_time", "source_url",
]


def synthetic_html(year: int) -> str:
    """Two round robins with reversed venues, leading-zero IDs and raw labels."""
    clubs = [f"人工クラブ{number:02d}" for number in range(18)]
    clubs[1:3] = ["人工Ｇ01", "人工Ｆ02"]
    if year == 2016:
        clubs[-3:] = [f"追加クラブ{number}" for number in range(3)]
    rotating = clubs.copy()
    rounds = []
    for _ in range(17):
        rounds.append(list(zip(rotating[:9], reversed(rotating[9:]))))
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    rows = []
    for stage_index in range(2):
        for round_number, pairs in enumerate(rounds, 1):
            for pair_number, (home, away) in enumerate(pairs):
                if stage_index:
                    home, away = away, home
                match_id = f"0{year}{len(rows) + 1:04d}"
                match_date = date(year, 2, 27) + timedelta(
                    days=stage_index * 126 + (round_number - 1) * 7
                )
                scores = ((0, 1), (1, 1), (2, 1))[pair_number % 3]
                venue = "人工ＢＭＷス" if home == clubs[0] else f"人工会場{clubs.index(home):02d}"
                if year == 2016 and home == clubs[1]:
                    venue = "新人工会場|東"
                values = [
                    str(year), ("Ｊ１ １ｓｔ", "Ｊ１ ２ｎｄ")[stage_index],
                    f"第{round_number}節第１日", match_date.strftime("%y/%m/%d") + "(土・祝)",
                    "14:03", home, f"{scores[0]}-{scores[1]}", away, venue,
                    "12,345", "人工放送",
                ]
                cells = [f"<td>{escape(value)}</td>" for value in values]
                cells[6] = (
                    f'<td><a href="/SFMS02/?match_card_id={match_id}">'
                    f'{values[6]}</a></td>'
                )
                rows.append("<tr>" + "".join(cells) + "</tr>")
    # Deliberately preserve an unusual source order instead of sorting by date.
    rows = rows[-3:] + rows[:-3]
    header = "".join(f"<th>{escape(value)}</th>" for value in HEADERS)
    return (
        '<table><tr><td>取得対象外の案内</td></tr></table>'
        f'<table class="table-base00 search-table"><thead><tr>{header}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def write_synthetic_cache(root: Path) -> Path:
    """Materialize deterministic fixtures without depending on real raw data."""
    raw_dir = root / "data/raw/jleague"
    raw_dir.mkdir(parents=True)
    for year in (2015, 2016):
        raw = synthetic_html(year).encode("utf-8")
        raw_path = raw_dir / f"{year}_j1_search.html"
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
        raw_path.with_suffix(".metadata.json").write_bytes(
            (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
    return raw_dir


@pytest.fixture
def offline_cache(tmp_path, monkeypatch):
    def forbidden_network(*args, **kwargs):
        pytest.fail("Offline inspection attempted network access.")

    monkeypatch.setattr(socket.socket, "connect", forbidden_network)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_network)
    raw_dir = write_synthetic_cache(tmp_path)
    originals = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    return tmp_path, raw_dir, originals


def assert_legacy_outputs(output_dir: Path):
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    newline_key = "sha256_crlf" if os.linesep == "\r\n" else "sha256_lf"
    assert set(path.name for path in output_dir.iterdir()) == set(golden["outputs"])
    for filename, expected in golden["outputs"].items():
        actual = (output_dir / filename).read_bytes()
        assert hashlib.sha256(actual).hexdigest() == expected[newline_key], filename


def test_common_inspection_exactly_preserves_all_five_legacy_outputs(offline_cache):
    from scripts.inspect_jleague import run_inspection

    root, raw_dir, originals = offline_cache
    run_inspection(2015, root=root)
    run_inspection(2016, root=root)
    assert_legacy_outputs(root / "data/processed/jleague")
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == originals


def test_legacy_cli_entry_points_preserve_all_five_outputs(offline_cache, monkeypatch):
    from scripts import inspect_jleague_2015, inspect_jleague_2016

    root, raw_dir, originals = offline_cache
    for year, module in ((2015, inspect_jleague_2015), (2016, inspect_jleague_2016)):
        monkeypatch.setattr(module, "ROOT", root)
        monkeypatch.setattr(module, "OUTPUT_DIR", root / "data/processed/jleague")
        monkeypatch.setattr(sys, "argv", [f"inspect_jleague_{year}"])
        module.main()
    assert_legacy_outputs(root / "data/processed/jleague")
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == originals


def test_common_cli_year_argument_preserves_both_legacy_results(offline_cache, monkeypatch):
    from scripts import inspect_jleague

    root, raw_dir, originals = offline_cache
    run_inspection = inspect_jleague.run_inspection
    monkeypatch.setattr(
        inspect_jleague, "run_inspection", lambda year: run_inspection(year, root=root)
    )
    for year in (2015, 2016):
        monkeypatch.setattr(sys, "argv", ["inspect_jleague", "--year", str(year)])
        inspect_jleague.main()
    assert_legacy_outputs(root / "data/processed/jleague")
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == originals


@pytest.mark.parametrize("args", [[], ["--year", "2022"], ["--year", "invalid"]])
def test_common_cli_rejects_missing_or_unsupported_year_before_inspection(monkeypatch, args):
    from scripts import inspect_jleague

    def unexpected_inspection(year):
        pytest.fail("Invalid CLI arguments reached cache inspection.")

    monkeypatch.setattr(inspect_jleague, "run_inspection", unexpected_inspection)
    monkeypatch.setattr(sys, "argv", ["inspect_jleague", *args])
    with pytest.raises(SystemExit) as error:
        inspect_jleague.main()
    assert error.value.code == 2


@pytest.mark.parametrize("year", [2015, 2016])
def test_common_parser_preserves_types_names_labels_ids_and_row_order(offline_cache, year):
    from src.collect.jleague import parse_matches_html, read_cached_matches

    _, raw_dir, _ = offline_cache
    matches, metadata = read_cached_matches(year, raw_dir=raw_dir)
    pd.testing.assert_frame_equal(
        matches, parse_matches_html(synthetic_html(year), expected_season=year)
    )
    assert matches.columns.tolist() == MATCH_COLUMNS
    assert len(matches) == 306
    assert matches.match_id.tolist() == (
        [f"0{year}{number:04d}" for number in range(304, 307)]
        + [f"0{year}{number:04d}" for number in range(1, 304)]
    )
    assert matches.loc[0, "stage"] == "2nd"
    assert matches.loc[0, "round"] == 17
    assert matches.loc[0, "competition"] == "Ｊ１ ２ｎｄ"
    assert matches.loc[0, "round_label"] == "第17節第１日"
    assert matches.loc[3, "match_date"] == pd.Timestamp(f"{year}-02-27")
    assert "人工Ｇ01" in set(matches.home_team)
    assert "人工Ｆ02" in set(matches.away_team)
    assert "人工ＢＭＷス" in set(matches.stadium)
    assert matches.match_id.dtype == pd.StringDtype()
    assert str(matches.match_date.dtype) == "datetime64[ns]"
    for column in ("season", "round", "home_score", "away_score", "result"):
        assert str(matches[column].dtype) == "int64"
    assert metadata["bytes"] == len(synthetic_html(year).encode("utf-8"))


@pytest.mark.parametrize("year", [2015, 2016])
@pytest.mark.parametrize("failure", ["missing_html", "missing_metadata", "invalid_json", "bad_sha256"])
def test_common_inspection_stops_on_invalid_cache_without_network_or_output(offline_cache, year, failure):
    from scripts.inspect_jleague import run_inspection

    root, raw_dir, _ = offline_cache
    raw_path = raw_dir / f"{year}_j1_search.html"
    metadata_path = raw_path.with_suffix(".metadata.json")
    if failure == "missing_html":
        raw_path.unlink()
    elif failure == "missing_metadata":
        metadata_path.unlink()
    elif failure == "invalid_json":
        metadata_path.write_bytes(b"{bad json")
    else:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["sha256"] = "0" * 64
        metadata_path.write_bytes(json.dumps(metadata).encode("utf-8"))
    before = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    with pytest.raises((FileNotFoundError, ValueError)):
        run_inspection(year, root=root)
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == before
    assert not (root / "data/processed/jleague").exists()


@pytest.mark.parametrize("field, invalid_value", [
    ("requested_url", "https://example.com/2015"),
    ("final_url", "https://example.com/2015"),
    ("status", 404), ("bytes", 0), ("fetched_at_utc", ""),
])
def test_2015_uses_complete_metadata_checks_shared_with_2016(offline_cache, field, invalid_value):
    from src.collect.jleague import read_cached_matches

    _, raw_dir, _ = offline_cache
    metadata_path = raw_dir / "2015_j1_search.metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = invalid_value
    metadata_path.write_bytes(json.dumps(metadata).encode("utf-8"))
    before = {path.name: path.read_bytes() for path in raw_dir.iterdir()}
    with pytest.raises(ValueError):
        read_cached_matches(2015, raw_dir=raw_dir)
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == before


@pytest.mark.parametrize("year", [2014, 2022, 2026])
def test_common_entry_points_reject_unverified_years_without_io(tmp_path, year):
    from scripts.inspect_jleague import run_inspection
    from src.collect.jleague import parse_matches_html, read_cached_matches, summarize_matches

    with pytest.raises(ValueError):
        run_inspection(year, root=tmp_path)
    with pytest.raises(ValueError):
        read_cached_matches(year, raw_dir=tmp_path)
    with pytest.raises(ValueError):
        parse_matches_html("", expected_season=year)
    with pytest.raises(ValueError):
        summarize_matches(pd.DataFrame(), expected_season=year)
    assert not list(tmp_path.iterdir())


def test_common_inspection_supports_explicit_output_directory(offline_cache):
    from scripts.inspect_jleague import run_inspection

    root, raw_dir, originals = offline_cache
    output_dir = root / "custom-results"
    run_inspection(2015, root=root, output_dir=output_dir)
    run_inspection(2016, root=root, output_dir=output_dir)
    for year in (2015, 2016):
        assert len(load_matches(output_dir / f"{year}_matches_probe.csv")) == 306
    summary = json.loads((output_dir / "2015_matches_probe.summary.json").read_text(encoding="utf-8"))
    assert summary["csv_path"] == "custom-results/2015_matches_probe.csv"
    assert not (root / "data/processed/jleague").exists()
    assert {path.name: path.read_bytes() for path in raw_dir.iterdir()} == originals
