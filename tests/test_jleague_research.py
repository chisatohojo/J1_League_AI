"""Offline research checks using artificial HTML and a synthetic season."""

from datetime import date, timedelta
import hashlib
from html import escape
import json

import pandas as pd
import pytest

from scripts.inspect_jleague_2015 import parse_matches_html, summarize_matches
from scripts import inspect_jleague_2016
from scripts.inspect_jleague_2016 import build_review_summary
from src.collect.matches import validate_matches


HEADERS = (
    "シーズン", "大会", "節", "試合日", "K/O時刻", "ホーム", "スコア",
    "アウェイ", "スタジアム", "入場者数", "インターネット中継・TV放送",
)
MATCH_COLUMNS = [
    "match_id", "season", "round", "match_date", "home_team", "away_team",
    "stadium", "home_score", "away_score", "result", "stage", "competition",
    "round_label", "kickoff_time", "source_url",
]


def _html(season=2015, **changes):
    values = {
        "season": str(season), "competition": "Ｊ１ １ｓｔ",
        "round_label": "第１節第１日", "date_label": f"{season % 100:02d}/02/27(土)",
        "kickoff": "14:00", "home": "Ｇ大阪", "score": "2-1", "away": "川崎Ｆ",
        "stadium": "ＢＭＷス", "attendance": "12,345", "broadcast": "テスト放送",
    }
    values.update(changes)
    cells = [f"<td>{escape(value)}</td>" for value in values.values()]
    cells[6] = f'<td><a href="/SFMS02/?match_card_id=00123">{escape(values["score"])}</a></td>'
    header = "".join(f"<th>{escape(item)}</th>" for item in HEADERS)
    # Unrelated tables and current-year navigation must not become match rows.
    return (
        '<a href="/SFMS01/?year=2026">2026</a><table><tr><td>検索条件</td></tr></table>'
        f'<table class="table-base00 search-table"><thead><tr>{header}</tr></thead>'
        f'<tbody><tr>{"".join(cells)}</tr></tbody></table>'
    )


@pytest.fixture
def season_2016():
    """Every pair meets once per stage, with reversed venues in stage two."""
    clubs = [f"クラブ{number:02d}" for number in range(18)]
    rotating = clubs.copy()
    rounds = []
    for _ in range(17):
        rounds.append(list(zip(rotating[:9], reversed(rotating[9:]))))
        rotating = [rotating[0], rotating[-1], *rotating[1:-1]]
    records = []
    for stage_number, stage in enumerate(("1st", "2nd")):
        for round_number, pairs in enumerate(rounds, 1):
            for pair_number, (home, away) in enumerate(pairs):
                if stage_number:
                    home, away = away, home
                match_id = str(len(records) + 1)
                home_score, away_score = ((0, 1), (1, 1), (2, 1))[pair_number % 3]
                records.append({
                    "match_id": match_id, "season": 2016, "round": round_number,
                    "match_date": date(2016, 2, 27) + timedelta(
                        days=stage_number * 126 + (round_number - 1) * 7
                    ),
                    "home_team": home, "away_team": away, "stadium": "人工スタジアム",
                    "home_score": home_score, "away_score": away_score,
                    "result": pair_number % 3, "stage": stage,
                    "competition": "Ｊ１ １ｓｔ" if stage == "1st" else "Ｊ１ ２ｎｄ",
                    "round_label": f"第{round_number}節第１日", "kickoff_time": "14:00",
                    "source_url": f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}",
                })
    return validate_matches(pd.DataFrame.from_records(records))


def test_2015_default_parser_remains_compatible():
    default = parse_matches_html(_html())
    explicit = parse_matches_html(_html(), expected_season=2015)
    pd.testing.assert_frame_equal(default, explicit)
    assert default.columns.tolist() == MATCH_COLUMNS
    assert default.loc[0, "season"] == 2015
    assert default.loc[0, "match_date"] == pd.Timestamp("2015-02-27")


@pytest.mark.parametrize("stage, expected", [("Ｊ１ １ｓｔ", "1st"), ("Ｊ１ ２ｎｄ", "2nd")])
def test_2016_parser_preserves_source_names_and_identifiers(stage, expected):
    source = _html(2016, competition=stage)
    matches = parse_matches_html(source, expected_season=2016)
    assert matches.columns.tolist() == MATCH_COLUMNS
    assert matches.loc[0, "match_id"] == "00123"
    assert matches.loc[0, "match_date"] == pd.Timestamp("2016-02-27")
    assert matches.loc[0, "home_team"] == "Ｇ大阪"
    assert matches.loc[0, "away_team"] == "川崎Ｆ"
    assert matches.loc[0, "stadium"] == "ＢＭＷス"
    assert matches.loc[0, "competition"] == stage
    assert matches.loc[0, "stage"] == expected
    assert matches.loc[0, "round_label"] == "第１節第１日"
    assert matches.loc[0, "source_url"] == "https://data.j-league.or.jp/SFMS02/?match_card_id=00123"


@pytest.mark.parametrize("score, result", [("0-1", 0), ("2-2", 1), ("3-0", 2)])
def test_parser_derives_result_from_scores(score, result):
    matches = parse_matches_html(_html(2016, score=score), expected_season=2016)
    assert matches.loc[0, "result"] == result


@pytest.mark.parametrize("year", [2014, 2024, 2026])
def test_parser_rejects_uninvestigated_years(year):
    with pytest.raises(ValueError):
        parse_matches_html(_html(year), expected_season=year)


@pytest.mark.parametrize("source_year, expected_year", [(2015, 2016), (2016, 2015)])
def test_parser_rejects_source_season_mismatch(source_year, expected_year):
    with pytest.raises(ValueError):
        parse_matches_html(_html(source_year), expected_season=expected_year)


@pytest.mark.parametrize("date_label", ["15/02/27(土)", "16/02/30(火)", "2016-02-27", "16/02/27()"])
def test_parser_rejects_wrong_or_invalid_date(date_label):
    with pytest.raises(ValueError):
        parse_matches_html(_html(2016, date_label=date_label), expected_season=2016)


def test_parser_accepts_holiday_date_label():
    matches = parse_matches_html(_html(2016, date_label="16/11/03(木・祝)"), expected_season=2016)
    assert matches.loc[0, "match_date"] == pd.Timestamp("2016-11-03")


@pytest.mark.parametrize("changes", [
    {"competition": "Ｊ１"}, {"competition": "Ｊ１ ３ｒｄ"},
    {"competition": "Ｊ１ チャンピオンシップ"}, {"competition": "Ｊ２"},
    {"round_label": "第１８節第１日"}, {"round_label": "第１節第０日"},
    {"kickoff": "25:00"}, {"score": "-1-0"}, {"score": "試合中止"},
    {"score": "1(4PK3)1"}, {"home": "川崎Ｆ"}, {"stadium": " "},
])
def test_parser_rejects_unsupported_or_invalid_source_values(changes):
    with pytest.raises(ValueError):
        parse_matches_html(_html(2016, **changes), expected_season=2016)


@pytest.mark.parametrize("old, new", [
    ("search-table", "other-table"),
    ("<th>シーズン</th>", "<th>年度</th>"),
    ("<td>12,345</td>", ""),
    ("match_card_id=00123", "match_card_id=unknown"),
    ("/SFMS02/?match_card_id=00123", "/SFMS03/?match_card_id=00123"),
    ('<a href="/SFMS02/?match_card_id=00123">2-1</a>', "2-1"),
])
def test_parser_rejects_changed_table_or_match_link(old, new):
    with pytest.raises(ValueError):
        parse_matches_html(_html(2016).replace(old, new), expected_season=2016)


def test_parser_rejects_multiple_search_tables():
    with pytest.raises(ValueError):
        parse_matches_html(_html(2016) * 2, expected_season=2016)


def test_parser_rejects_duplicate_matches():
    html = _html(2016)
    match_row = html.split("<tbody>")[1].split("</tbody>")[0]
    with pytest.raises(ValueError):
        parse_matches_html(html.replace(match_row, match_row * 2), expected_season=2016)


def test_summary_accepts_2016_and_keeps_2015_default(season_2016):
    summary = summarize_matches(season_2016, expected_season=2016)
    assert summary["matches"] == 306
    assert summary["season"] == 2016
    previous = season_2016.copy(deep=True)
    previous["season"] = 2015
    previous["match_date"] -= pd.Timedelta(days=365)
    assert summarize_matches(previous)["season"] == 2015
    with pytest.raises(ValueError):
        summarize_matches(season_2016)


def test_review_summary_covers_clubs_rounds_and_quality(season_2016):
    original = season_2016.copy(deep=True)
    summary = build_review_summary(season_2016)
    assert summary["columns"] == MATCH_COLUMNS
    assert summary["matches"] == 306
    assert summary["match_id_count"] == 306
    assert summary["club_count"] == 18
    assert summary["clubs"] == sorted(season_2016["home_team"].unique())
    assert set(summary["club_match_counts"]) == set(summary["clubs"])
    assert all(value == {"total": 34, "home": 17, "away": 17}
               for value in summary["club_match_counts"].values())
    assert summary["round_counts"] == dict.fromkeys(range(1, 18), 18)
    assert summary["result_counts"] == {0: 102, 1: 102, 2: 102}
    assert summary["missing_counts"] == dict.fromkeys(MATCH_COLUMNS, 0)
    assert all(count == 0 for count in summary["blank_counts"].values())
    assert summary["duplicate_rows"] == 0
    assert summary["duplicate_match_ids"] == 0
    assert summary["duplicate_matches"] == 0
    assert summary["same_team_rows"] == 0
    assert summary["score_result_mismatches"] == 0
    assert summary["negative_score_rows"] == 0
    assert summary["date_min"] == "2016-02-27"
    assert summary["date_max"] == "2016-10-22"
    assert summary["stadiums"] == ["人工スタジアム"]
    for stage in ("1st", "2nd"):
        assert summary["stages"][stage]["matches"] == 153
        assert summary["stages"][stage]["round_counts"] == dict.fromkeys(range(1, 18), 9)
    pd.testing.assert_frame_equal(season_2016, original)


def test_review_samples_preserve_all_columns_and_seed(season_2016):
    # Sample from deliberately non-chronological source order.
    shuffled = season_2016.iloc[::-1].reset_index(drop=True)
    summary = build_review_summary(shuffled)
    records = shuffled.copy(deep=True)
    records["match_date"] = records["match_date"].dt.strftime("%Y-%m-%d")
    assert summary["random_state"] == 42
    assert summary["first_five"] == records.head(5).to_dict(orient="records")
    assert summary["last_five"] == records.tail(5).to_dict(orient="records")
    assert summary["random_ten"] == records.sample(n=10, random_state=42).to_dict(orient="records")
    assert all(list(row) == MATCH_COLUMNS for row in summary["random_ten"])


@pytest.mark.parametrize("year", [2014, 2024])
def test_summary_rejects_uninvestigated_years(season_2016, year):
    season_2016["season"] = year
    with pytest.raises(ValueError):
        summarize_matches(season_2016, expected_season=year)


@pytest.mark.parametrize("column, value", [
    ("stage", None), ("source_url", " "), ("stadium", None),
    ("home_score", -1), ("result", 2), ("match_id", "2"),
])
def test_review_rejects_missing_or_invalid_values(season_2016, column, value):
    if value is None:
        season_2016[column] = season_2016[column].astype(object)
    season_2016.loc[0, column] = value
    with pytest.raises(ValueError):
        build_review_summary(season_2016)


@pytest.mark.parametrize("column", ["stage", "competition", "round_label", "kickoff_time", "source_url"])
def test_review_rejects_missing_extra_column(season_2016, column):
    with pytest.raises(ValueError):
        build_review_summary(season_2016.drop(columns=column))


def test_review_rejects_incomplete_season(season_2016):
    with pytest.raises(ValueError):
        build_review_summary(season_2016.iloc[:-1])


def test_review_rejects_unbalanced_home_away(season_2016):
    home, away = season_2016.loc[0, ["home_team", "away_team"]]
    season_2016.loc[0, ["home_team", "away_team"]] = [away, home]
    # Match count, round counts and club appearances are still correct.
    with pytest.raises(ValueError):
        build_review_summary(season_2016)


def test_review_rejects_repeated_pairs_even_with_balanced_appearances(season_2016):
    # Swap two away clubs within the first round in both stages. Each club
    # still appears 34 times with 17 home/away games, but some pairs repeat.
    for offset in (0, 153):
        column = "away_team" if offset == 0 else "home_team"
        values = season_2016.loc[[offset, offset + 1], column].tolist()
        season_2016.loc[[offset, offset + 1], column] = values[::-1]
    with pytest.raises(ValueError):
        build_review_summary(season_2016)


@pytest.fixture
def cached_html(tmp_path, monkeypatch):
    """A tiny local cache, independent of the downloaded originals."""
    monkeypatch.setattr(inspect_jleague_2016, "ROOT", tmp_path)
    raw_path = tmp_path / "data/raw/jleague/2016_j1_search.html"
    raw_path.parent.mkdir(parents=True)
    raw = _html(2016).encode("utf-8")
    raw_path.write_bytes(raw)
    url = (
        "https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1"
        "&competition_years=2016&tv_relay_station_name="
    )
    metadata = {
        "requested_url": url, "final_url": url, "status": 200,
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "fetched_at_utc": "2026-09-12T00:00:00+00:00",
    }
    metadata_path = raw_path.with_suffix(".metadata.json")
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return raw_path, metadata_path, metadata


def test_cached_html_is_reused_without_modifying_original(cached_html):
    raw_path, metadata_path, metadata = cached_html
    originals = (raw_path.read_bytes(), metadata_path.read_bytes())
    matches, actual_metadata = inspect_jleague_2016.read_cached_matches(2016)
    assert matches.loc[0, "match_id"] == "00123"
    assert actual_metadata == metadata
    assert (raw_path.read_bytes(), metadata_path.read_bytes()) == originals


@pytest.mark.parametrize("field, invalid_value", [
    ("sha256", "0" * 64), ("bytes", 0), ("status", 404),
    ("requested_url", "https://example.com/2016"),
    ("final_url", "https://example.com/2016"), ("fetched_at_utc", ""),
])
def test_cached_html_rejects_inconsistent_acquisition_metadata(cached_html, field, invalid_value):
    raw_path, metadata_path, metadata = cached_html
    original = raw_path.read_bytes()
    metadata[field] = invalid_value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        inspect_jleague_2016.read_cached_matches(2016)
    assert raw_path.read_bytes() == original
