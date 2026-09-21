"""Offline contracts for prospective J.LEAGUE suspension snapshots."""

import csv
from datetime import date, datetime, timezone
import json

import pytest

from src.collect.jleague_suspensions import (
    CSV_FIELDS, SuspensionSnapshotError, collect_snapshot, link_rows, parse_notice,
)
from src.collect.teams import TeamAlias, TeamMaster


URL = "https://www.jleague.jp/news/article/99999/"


def master():
    return TeamMaster([
        TeamAlias("team_0001", "ジェフユナイテッド千葉", "千葉", "jleague_data_site", None, None, "chiba"),
        TeamAlias("team_0014", "ＦＣ町田ゼルビア", "町田", "jleague_data_site", None, None, "machida"),
        TeamAlias("team_0021", "ファジアーノ岡山", "岡山", "jleague_data_site", None, None, "okayama"),
        TeamAlias("team_0025", "清水エスパルス", "清水", "jleague_data_site", None, None, "shimizu"),
    ])


def schedule(path, *, blank_id=False):
    fields = ["match_id", "match_date", "round_label", "home_team", "away_team", "competition_key"]
    rows = [
        ["" if blank_id else "m1", "2026-09-19", "第８節第１日", "清水", "千葉", "j1_2026_2027"],
        ["m2", "2026-09-20", "第８節第２日", "町田", "岡山", "j1_2026_2027"],
        ["m3", "2026-09-26", "第９節第１日", "千葉", "町田", "j1_2026_2027"],
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def fixture_html(*, duplicate=False, malformed=False, fuzzy_club=False, second_explicit=True):
    rows = [
        ("明本 考浩", "町田X" if fuzzy_club else "町田", "", "J1(a)",
         "２０２６／２７明治安田Ｊ１リーグ第８節第２日(09/20)"),
        ("橋本 健人", "千葉", "", "J1(b)",
         "２０２６／２７明治安田Ｊ１リーグ第８節第１日(09/19)"),
    ]
    if second_explicit:
        rows.append(("", "", "", "", "２０２６／２７明治安田Ｊ１リーグ第９節第１日(09/26)"))
    rows.append(("他大会 選手", "清水", "", "C(a)", "２０２６／２７Ｊリーグ ルヴァンカップ(09/29)"))
    if duplicate:
        rows.append(rows[0])
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    if malformed:
        body = "<tr><td>壊れた行</td></tr>"
    article = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": "出場停止選手のお知らせ（2026/09/14）",
        "datePublished": "2026-09-14T10:00:00.000Z",
        "dateModified": "2026-09-15T00:31:55.754Z",
    }
    return (
        "<html><head><script type=\"application/ld+json\">"
        + json.dumps(article, ensure_ascii=False)
        + "</script></head><body><table><tr>"
        + "".join(f"<th>{value}</th>" for value in ("選手", "チーム", "前回の停止", "今回の停止", "出場停止試合"))
        + f"</tr>{body}</table></body></html>"
    ).encode()


def test_official_notice_publication_and_explicit_multi_match_parse():
    rows, diagnostics = parse_notice(fixture_html(), source_url=URL)
    assert diagnostics == {
        "notice_id": "99999",
        "published_at": "2026-09-14T10:00:00Z",
        "updated_at": "2026-09-15T00:31:55.754000Z",
        "explicit_target_rows": 4,
        "j1_target_rows": 3,
        "ignored_non_j1_target_rows": 1,
    }
    assert [row["player_name_raw"] for row in rows] == ["明本 考浩", "橋本 健人", "橋本 健人"]
    assert [row["suspension_match_index"] for row in rows] == [1, 1, 2]
    assert [row["suspension_match_count"] for row in rows] == [1, 2, 2]
    assert {row["competition"] for row in rows} == {"j1"}


def test_code_never_infers_an_unlisted_second_match():
    rows, _ = parse_notice(fixture_html(second_explicit=False), source_url=URL)
    bridge = [row for row in rows if row["player_name_raw"] == "橋本 健人"]
    assert len(bridge) == 1
    assert bridge[0]["suspension_match_count"] == 1


def test_exact_club_and_match_linkage_and_raw_player_name(tmp_path):
    schedule_path = tmp_path / "schedule.csv"
    schedule(schedule_path)
    rows, _ = parse_notice(fixture_html(), source_url=URL)
    linked = link_rows(rows, schedule_path=schedule_path, master=master(),
                       player_identity_keys={("2026/27", "team_0014", "明本 考浩")})
    assert linked[0]["team_id"] == "team_0014"
    assert linked[0]["team_link_status"] == "EXACT"
    assert linked[0]["target_match_id"] == "m2"
    assert linked[0]["opponent_name"] == "岡山"
    assert linked[0]["match_link_status"] == "EXACT"
    assert linked[0]["player_name_raw"] == "明本 考浩"
    assert linked[0]["player_link_status"] == "EXACT"


def test_unresolved_identity_or_missing_match_id_is_never_guessed(tmp_path):
    schedule_path = tmp_path / "schedule.csv"
    schedule(schedule_path, blank_id=True)
    rows, _ = parse_notice(fixture_html(fuzzy_club=True), source_url=URL)
    linked = link_rows(rows, schedule_path=schedule_path, master=master())
    assert linked[0]["team_id"] == ""
    assert linked[0]["team_link_status"] == "UNRESOLVED"
    assert linked[0]["target_match_id"] == ""
    assert linked[0]["match_link_status"] == "UNRESOLVED"
    assert linked[1]["target_match_id"] == ""
    assert linked[1]["match_link_status"] == "UNRESOLVED_NO_MATCH_ID"


def test_snapshot_provenance_common_id_duplicate_reject_and_no_overwrite(tmp_path):
    schedule_path = tmp_path / "schedule.csv"
    schedule(schedule_path)
    calls = []

    def fetch(url):
        calls.append(url)
        return fixture_html(), 200, url, "text/html; charset=utf-8"

    kwargs = {
        "urls": [URL], "raw_root": tmp_path / "raw", "processed_root": tmp_path / "processed",
        "schedule_path": schedule_path, "master": master(),
        "now": datetime(2026, 9, 21, 1, 2, 3, tzinfo=timezone.utc),
        "fetch": fetch, "pause": lambda _: None,
    }
    result = collect_snapshot(**kwargs)
    assert result["request_count"] == result["notice_count"] == 1
    assert result["row_count"] == 3
    with result["processed_path"].open(encoding="utf-8", newline="") as handle:
        output = list(csv.DictReader(handle))
    assert tuple(output[0]) == CSV_FIELDS
    assert {row["snapshot_id"] for row in output} == {result["snapshot_id"]}
    assert {row["retrieved_at"] for row in output} == {"2026-09-21T01:02:03Z"}
    manifest = json.loads((result["raw_dir"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE"
    with pytest.raises(SuspensionSnapshotError, match="already exists"):
        collect_snapshot(**kwargs)
    assert len(calls) == 1

    duplicate_now = datetime(2026, 9, 21, 1, 2, 4, tzinfo=timezone.utc)
    with pytest.raises(SuspensionSnapshotError, match="Duplicate source/target"):
        collect_snapshot(**{**kwargs, "now": duplicate_now,
                             "fetch": lambda url: (fixture_html(duplicate=True), 200, url, "text/html")})


def test_incomplete_snapshot_keeps_raw_but_never_publishes_csv(tmp_path):
    schedule_path = tmp_path / "schedule.csv"
    schedule(schedule_path)
    with pytest.raises(SuspensionSnapshotError):
        collect_snapshot(
            urls=[URL], raw_root=tmp_path / "raw", processed_root=tmp_path / "processed",
            schedule_path=schedule_path, master=master(),
            now=datetime(2026, 9, 21, 2, tzinfo=timezone.utc),
            fetch=lambda url: (fixture_html(malformed=True), 200, url, "text/html"),
        )
    manifest_path = next((tmp_path / "raw").glob("*/manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "INCOMPLETE"
    assert (manifest_path.parent / "notice_99999.html").exists()
    assert not list((tmp_path / "processed").glob("*.csv")) if (tmp_path / "processed").exists() else True


def test_only_observed_current_notice_route_and_no_historical_discovery():
    with pytest.raises(SuspensionSnapshotError):
        parse_notice(fixture_html(), source_url="https://aboutj.jleague.jp/corporate/pressrelease/article/11115")
    with pytest.raises(SuspensionSnapshotError):
        collect_snapshot(urls=[], now=datetime(2026, 9, 21, tzinfo=timezone.utc))


def test_invalid_publication_time_is_rejected():
    raw = fixture_html().replace(b"2026-09-14T10:00:00.000Z", b"2026-09-14")
    with pytest.raises(SuspensionSnapshotError, match="Timezone missing"):
        parse_notice(raw, source_url=URL)
