from datetime import date
from pathlib import Path

import pytest

from src.collect.jleague_match_xg import (
    AUTO_SUMMARY,
    COMPETITIONS,
    LEGACY_FULL_TIME_SUMMARY,
    TWO_WIDGET_SUMMARY,
    build_processed_rows,
    commentary_url,
    fetch_cached,
    parse_commentary_page,
    parse_full_time_summary,
    parse_match_summary,
    parse_schedule_detail_hrefs,
    parse_two_widget_summary,
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


def _page(
    *, date_value="2025-02-14", home_short="Ｇ大阪", summary=SUMMARY,
    home_score=2, away_score=5,
):
    payload = (
        r'\"awayTeam\":{\"name\":\"セレッソ大阪\",\"nameS\":\"Ｃ大阪\",'
        rf'\"score\":{away_score},\"playerScoreList\":[]}},'
        rf'\"date\":\"$D{date_value}T10:03:00.000Z\",'
        rf'\"homeTeam\":{{\"name\":\"ガンバ大阪\",\"nameS\":\"{home_short}\",'
        rf'\"score\":{home_score},\"playerScoreList\":[]}}'
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
    assert result.source_format == LEGACY_FULL_TIME_SUMMARY


def _two_widget_source(home=SUMMARY, away=SUMMARY.replace("１６", "９").replace("１２", "８")):
    home = "この試合のシュート：１６本、枠内シュート：５本、ゴール期待値：１．４３" if home == SUMMARY else home
    away = "この試合のシュート：９本、枠内シュート：３本、ゴール期待値：０．８０" if "Ｇ大阪" in away else away
    return (
        r'\"visual\":\"$x:awayTeam:teamLogo\",\"children\":\"' + away + r'\" '
        r'\"visual\":\"$x:homeTeam:teamLogo\",\"children\":\"' + home + r'\"'
    )


def test_two_widget_summary_binds_explicit_home_and_away_markers():
    result = parse_two_widget_summary(_two_widget_source())
    assert result.status == "complete"
    assert result.source_format == TWO_WIDGET_SUMMARY
    assert (str(result.home_xg), str(result.away_xg)) == ("1.43", "0.80")
    assert (result.home_shots, result.away_shots) == (16, 9)
    assert (result.home_shots_on_target, result.away_shots_on_target) == (5, 3)


def test_summary_format_detection_is_explicit_and_deterministic():
    assert parse_match_summary(SUMMARY, source_format=AUTO_SUMMARY).source_format == LEGACY_FULL_TIME_SUMMARY
    assert parse_match_summary(_two_widget_source(), source_format=AUTO_SUMMARY).source_format == TWO_WIDGET_SUMMARY


def test_malformed_two_widget_summary_is_rejected():
    malformed = _two_widget_source(home="この試合のシュート：１６本、ゴール期待値：１．４３")
    with pytest.raises(ValueError, match="shots and SOT"):
        parse_two_widget_summary(malformed)


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


def test_schedule_filters_exact_competition_and_excludes_future():
    source = (
        r'\"leagueDisplayName\":\"明治安田Ｊ１百年構想リーグ\",'
        r'\"state\":\"game-over\",\"detailHref\":\"/match/j1/2026/020601\" '
        r'\"leagueDisplayName\":\"明治安田Ｊ１リーグ\",'
        r'\"state\":\"game-over\",\"detailHref\":\"/match/j1/2026/080701\" '
        r'\"state\":\"before-game\",\"detailHref\":\"/match/j1/2026/092701\"'
    )
    assert parse_schedule_detail_hrefs(
        source, season=2026, competition_name="明治安田Ｊ１百年構想リーグ",
        completed_only=True,
    ) == ("020601",)
    assert parse_schedule_detail_hrefs(
        source, season=2026, competition_name="明治安田Ｊ１リーグ",
        completed_only=True,
    ) == ("080701",)


def test_page_identity_and_team_master_exact_resolution():
    match = _match()
    rows = build_processed_rows(_reference(), [match], _master())
    assert len(rows) == 1
    assert rows[0]["match_id"] == "31361"
    assert rows[0]["home_team_id"] == "team_0005"
    assert rows[0]["away_team_id"] == "team_0002"


def test_extra_time_source_score_preserves_regulation_and_flags_xg_scope():
    match = _match(_page(home_score=2, away_score=1))
    reference = [{
        **_reference()[0], "home_score": "0", "away_score": "0", "result": "1",
        "extra_time_played": "True", "home_extra_time_score": "2",
        "away_extra_time_score": "1",
    }]
    rows = build_processed_rows(
        reference, [match], _master(), allow_extra_time_source_score=True,
    )
    assert (rows[0]["home_score"], rows[0]["away_score"]) == (0, 0)
    assert (rows[0]["source_home_score"], rows[0]["source_away_score"]) == (2, 1)
    assert rows[0]["score_scope_status"] == "EXTRA_TIME_SOURCE_SCORE"
    assert rows[0]["xg_time_scope"] == "OFFICIAL_FINAL_SCOPE_UNRESOLVED"


def test_unexplained_source_score_mismatch_is_rejected():
    with pytest.raises(ValueError, match="score differs"):
        build_processed_rows(_reference(), [_match(_page(home_score=3))], _master())


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


def test_competition_cache_namespaces_are_separate():
    legacy = COMPETITIONS["2025_j1"]
    hyakunen = COMPETITIONS["2026_hyakunen"]
    ordinary = COMPETITIONS["2026_27_j1"]
    assert len({legacy.raw_dir, hyakunen.raw_dir, ordinary.raw_dir}) == 3
    assert hyakunen.source_format == LEGACY_FULL_TIME_SUMMARY
    assert ordinary.source_format == TWO_WIDGET_SUMMARY


def test_collector_has_no_model_dependency():
    source = Path("src/collect/jleague_match_xg.py").read_text(encoding="utf-8")
    assert "src.modeling" not in source
    assert "sklearn" not in source
