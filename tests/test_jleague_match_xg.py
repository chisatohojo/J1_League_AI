from datetime import date
from pathlib import Path

import pytest

from src.collect.jleague_match_xg import (
    build_processed_rows,
    commentary_url,
    fetch_cached,
    parse_commentary_page,
    parse_full_time_summary,
    parse_schedule_detail_hrefs,
)
from src.collect.teams import TeamAlias, TeamMaster


SEASON = 2025
PATH_ID = "021401"
URL = commentary_url(SEASON, PATH_ID)
SUMMARY = (
    "この試合のシュート：Ｇ大阪：１６本、Ｃ大阪：１２本／"
    "枠内シュート：Ｇ大阪：５本、Ｃ大阪：７本／"
    "ゴール期待値：Ｇ大阪：１．４３、Ｃ大阪：１．３３"
)


def _page(*, date_value="2025-02-14", home_short="Ｇ大阪", summary=SUMMARY):
    payload = (
        r'\"awayTeam\":{\"name\":\"セレッソ大阪\",\"nameS\":\"Ｃ大阪\",'
        r'\"score\":5,\"playerScoreList\":[]},'
        rf'\"date\":\"$D{date_value}T10:03:00.000Z\",'
        rf'\"homeTeam\":{{\"name\":\"ガンバ大阪\",\"nameS\":\"{home_short}\",'
        r'\"score\":2,\"playerScoreList\":[]}'
    )
    return (
        f'<html><head><link rel="canonical" href="{URL}"/></head>'
        f'<body><script>{payload}</script><p>{summary}</p></body></html>'
    )


def _master():
    aliases = []
    for team_id, canonical, short, source_id in (
        ("team_0005", "ガンバ大阪", "Ｇ大阪", "gosaka"),
        ("team_0002", "セレッソ大阪", "Ｃ大阪", "cosaka"),
    ):
        aliases.extend((
            TeamAlias(team_id, canonical, canonical, "jleague_official", None, None, source_id),
            TeamAlias(team_id, canonical, short, "jleague_data_site", None, None, source_id),
        ))
    return TeamMaster(aliases)


def _match(source=None):
    return parse_commentary_page(
        source or _page(), season=SEASON, source_match_path_id=PATH_ID,
        source_url=URL, retrieved_at="2026-09-21T00:00:00+00:00",
    )


def _reference():
    return [{
        "match_id": "31361", "season": "2025", "match_date": "2025-02-14",
        "home_team": "Ｇ大阪", "away_team": "Ｃ大阪",
        "home_score": "2", "away_score": "5", "result": "0",
    }]


def test_full_time_summary_parses_xg_shots_and_sot():
    result = parse_full_time_summary(f'<p>{SUMMARY}</p>')
    assert result.status == "complete"
    assert (str(result.home_xg), str(result.away_xg)) == ("1.43", "1.33")
    assert (result.home_shots, result.away_shots) == (16, 12)
    assert (result.home_shots_on_target, result.away_shots_on_target) == (5, 7)


def test_ui_translation_label_alone_is_missing():
    result = parse_full_time_summary('"expected_goals":"ゴール期待値"')
    assert result.status == "missing"
    assert result.home_xg is None and result.away_xg is None


def test_partial_and_missing_xg_are_explicit():
    partial = SUMMARY.rsplit("、", 1)[0]
    assert parse_full_time_summary(partial).status == "partial"
    without_xg = SUMMARY.split("／ゴール期待値", 1)[0]
    assert parse_full_time_summary(without_xg).status == "missing"


def test_negative_xg_is_rejected():
    invalid = SUMMARY.replace("１．４３", "－０．１０")
    with pytest.raises(ValueError, match="nonnegative"):
        parse_full_time_summary(invalid)


def test_schedule_uses_only_observed_detail_hrefs():
    source = (
        r'\"detailHref\":\"/match/j1/2025/021401\" '
        r'\"detailHref\":\"/match/j1/2025/021502\" '
        r'\"detailHref\":\"/match/j2/2025/021401\"'
    )
    assert parse_schedule_detail_hrefs(source, season=2025) == ("021401", "021502")


def test_page_identity_and_team_master_exact_resolution():
    match = _match()
    rows = build_processed_rows(_reference(), [match], _master())
    assert len(rows) == 1
    assert rows[0]["match_id"] == "31361"
    assert rows[0]["home_team_id"] == "team_0005"
    assert rows[0]["away_team_id"] == "team_0002"


def test_page_identity_mismatch_is_rejected():
    with pytest.raises(ValueError, match="summary teams"):
        _match(_page(summary=SUMMARY.replace("Ｇ大阪", "柏")))
    with pytest.raises(ValueError, match="identity mismatch"):
        build_processed_rows(_reference(), [_match(_page(date_value="2025-02-15"))], _master())


def test_unknown_near_name_is_not_fuzzy_matched():
    match = _match(_page(home_short="G大阪", summary=SUMMARY.replace("Ｇ大阪", "G大阪")))
    with pytest.raises(ValueError, match="Unresolved home team"):
        build_processed_rows(_reference(), [match], _master())


def test_duplicate_commentary_match_is_rejected():
    match = _match()
    with pytest.raises(ValueError, match="Duplicate official commentary"):
        build_processed_rows(_reference(), [match, match], _master())


def test_raw_cache_is_reused_without_network(tmp_path):
    calls = []

    def fetcher(url):
        calls.append(url)
        return b"official", url, 200

    path = tmp_path / "021401.html"
    first = fetch_cached(URL, path, fetcher=fetcher, interval=0, sleep=lambda _: None)
    second = fetch_cached(
        URL, path,
        fetcher=lambda _: pytest.fail("valid cache must not call network"),
        interval=0, sleep=lambda _: None,
    )
    assert first[2] is False and second[2] is True
    assert second[0] == b"official"
    assert calls == [URL]


def test_collector_has_no_model_dependency():
    source = Path("src/collect/jleague_match_xg.py").read_text(encoding="utf-8")
    assert "src.modeling" not in source
    assert "sklearn" not in source
