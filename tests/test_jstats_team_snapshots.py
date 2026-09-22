"""Offline contract tests for official J Stats point-in-time collection."""

import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.collect.jstats_team_snapshots import (
    BASE_URL, RELATED_BASE_SNAPSHOT_ID, STATS, SUPPLEMENTAL_SOURCE_STATE_DATE,
    SUPPLEMENTAL_STATS, Stat, SnapshotError, collect_snapshot,
    collect_supplemental_snapshot, expected_club_slugs, parse_page,
)
from src.collect.teams import load_team_master


ROOT = Path(__file__).resolve().parents[1]
MASTER = load_team_master()
SLUGS = expected_club_slugs()
IDENTITIES = sorted(
    [(a.source_club_id, a.source_name, a.team_id) for a in MASTER.aliases
     if a.source == "jleague_official" and a.source_club_id in SLUGS
     and a.valid_from is None and a.valid_to is None]
)
assert len(IDENTITIES) == 20


def fixture_html(stat=STATS[0], *, count=20, duplicate=False, broken_value=False,
                 bad_name=False, update=True, value="1.20"):
    records = []
    for index, (slug, name, _) in enumerate(IDENTITIES[:count]):
        if duplicate and index == count - 1:
            slug, name, _ = IDENTITIES[0]
        if bad_name and index == 0:
            name += " "
        records.append({"href": f"/club/{slug}", "club": {"code": slug, "name": name},
                        "name": name, "score": "?" if broken_value and index == 0 else value})
    ranking = {"id": f"ranking-{stat.slug}", "category": "j1", "year": "2026",
               "stats": {"value": stat.slug, "label": stat.label}, "data": records}
    payload = "8:" + json.dumps({"rankingList": [ranking]}, ensure_ascii=False)
    script = json.dumps([1, payload], ensure_ascii=False)
    visible = "".join(
        f'<a class="m-ranking-club-list-item__link" href="/club/{r["club"]["code"]}/">'
        f'<div class="m-ranking-club-list-item" name="{r["name"]}" score="{r["score"]}"></div></a>'
        for r in records[:10]
    )
    date = "2026/9/14 更新" if update else ""
    return (f"<html><head><title>2026/27 J1</title></head><body>{date}{visible}"
            f"<script>self.__next_f.push({script})</script></body></html>").encode("utf-8")


def parse(raw, stat=STATS[0]):
    return parse_page(raw, stat=stat, expected_slugs=SLUGS, master=MASTER,
                      observed_date="2026-09-21")


def test_rsc_20_not_only_visible_10_exact_identity_and_precision():
    raw = fixture_html()
    rows, source_date = parse(raw)
    assert len(rows) == 20
    assert len({row["team_id"] for row in rows}) == 20
    assert {row["official_club_slug"] for row in rows} == SLUGS
    assert all(row["stat_value"] == "1.20" for row in rows)
    assert source_date == "2026-09-14"
    assert parse(raw) == (rows, source_date)


@pytest.mark.parametrize("changes", [
    {"count": 10}, {"count": 19}, {"duplicate": True}, {"broken_value": True},
    {"bad_name": True},
])
def test_incomplete_duplicate_invalid_or_unresolved_page_rejected(changes):
    with pytest.raises(SnapshotError):
        parse(fixture_html(**changes))


def test_unknown_stat_slug_and_wrong_season_rejected():
    with pytest.raises(SnapshotError):
        parse(fixture_html(), Stat("invented", "invented", "total", ""))
    with pytest.raises(SnapshotError):
        parse(fixture_html().replace(b"2026/27", b"2025"))


def test_visible_and_rsc_must_agree():
    raw = fixture_html().replace(b'score="1.20"', b'score="2.20"', 1)
    with pytest.raises(SnapshotError, match="disagree"):
        parse(raw)


def test_snapshot_is_atomic_and_provenance_is_shared(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        stat = next(s for s in STATS if BASE_URL.format(slug=s.slug) == url)
        return fixture_html(stat), 200, url, "text/html; charset=utf-8"

    now = datetime(2026, 9, 21, 1, 2, 3, tzinfo=timezone.utc)
    kwargs = {"raw_root": tmp_path / "raw", "processed_root": tmp_path / "processed",
              "now": now, "fetch": fetch, "pause": lambda _: None,
              "previous_source_state_date": "2026-09-14",
              "previous_snapshot_ids": ["old-base", "old-supplemental"]}
    result = collect_snapshot(**kwargs)
    assert result["request_count"] == len(STATS) == len(set(calls))
    assert result["row_count"] == 20 * len(STATS)
    assert set(result["parsed_clubs_per_stat"].values()) == {20}
    with result["processed_path"].open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 200
    assert {r["snapshot_id"] for r in rows} == {result["snapshot_id"]}
    assert {r["retrieved_at"] for r in rows} == {"2026-09-21T01:02:03Z"}
    assert {r["source_updated_at"] for r in rows} == {""}
    assert {r["games_played"] for r in rows} == {""}
    assert {r["source_updated_date_jst"] for r in rows} == {"2026-09-14"}
    assert {r["stat_value"] for r in rows} == {"1.20"}
    assert {r["source_url"] for r in rows} == set(calls)
    assert not any("delta" in r or "match_id" in r for r in rows)
    manifest = json.loads((result["raw_dir"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE"
    assert len(manifest["pages"]) == len(STATS)
    assert manifest["previous_source_state_date"] == "2026-09-14"
    assert manifest["previous_snapshot_ids"] == ["old-base", "old-supplemental"]
    with pytest.raises(SnapshotError, match="already exists"):
        collect_snapshot(**kwargs)
    assert len(calls) == len(STATS)  # no duplicate request or overwrite


def test_partial_failure_keeps_raw_but_no_processed_snapshot(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        stat = next(s for s in STATS if BASE_URL.format(slug=s.slug) == url)
        return fixture_html(stat, count=19 if len(calls) == 2 else 20), 200, url, "text/html"

    with pytest.raises(SnapshotError):
        collect_snapshot(raw_root=tmp_path / "raw", processed_root=tmp_path / "processed",
                         now=datetime(2026, 9, 21, tzinfo=timezone.utc),
                         fetch=fetch, pause=lambda _: None)
    assert len(calls) == 2
    assert not list((tmp_path / "processed").glob("*.csv")) if (tmp_path / "processed").exists() else True
    manifest = next((tmp_path / "raw").glob("*/manifest.json"))
    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "INCOMPLETE"
    assert (manifest.parent / "shoot.html").exists()


def test_source_update_unknown_is_not_retrieval_time():
    rows, date = parse(fixture_html(update=False))
    assert len(rows) == 20 and date is None


def test_supplemental_snapshot_is_complete_related_and_same_source_state(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        stat = next(s for s in SUPPLEMENTAL_STATS if BASE_URL.format(slug=s.slug) == url)
        return fixture_html(stat), 200, url, "text/html; charset=utf-8"

    result = collect_supplemental_snapshot(
        raw_root=tmp_path / "raw", processed_root=tmp_path / "processed",
        now=datetime(2026, 9, 21, 2, 3, 4, tzinfo=timezone.utc),
        fetch=fetch, pause=lambda _: None,
    )
    assert result["request_count"] == len(SUPPLEMENTAL_STATS) == len(set(calls))
    assert result["row_count"] == 20 * len(SUPPLEMENTAL_STATS)
    assert set(result["parsed_clubs_per_stat"].values()) == {20}
    manifest = json.loads((result["raw_dir"] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "COMPLETE"
    assert manifest["related_snapshot_id"] == RELATED_BASE_SNAPSHOT_ID
    assert manifest["source_state_date"] == SUPPLEMENTAL_SOURCE_STATE_DATE
    assert {page["source_updated_date_jst"] for page in manifest["pages"]} == {
        SUPPLEMENTAL_SOURCE_STATE_DATE
    }


def test_supplemental_snapshot_rejects_mixed_update_state(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        stat = next(s for s in SUPPLEMENTAL_STATS if BASE_URL.format(slug=s.slug) == url)
        raw = fixture_html(stat)
        if len(calls) == 2:
            raw = raw.replace(b"2026/9/14", b"2026/9/21")
        return raw, 200, url, "text/html; charset=utf-8"

    with pytest.raises(SnapshotError, match="does not match required state"):
        collect_supplemental_snapshot(
            raw_root=tmp_path / "raw", processed_root=tmp_path / "processed",
            now=datetime(2026, 9, 21, 2, 3, 4, tzinfo=timezone.utc),
            fetch=fetch, pause=lambda _: None,
        )
    assert len(calls) == 2
    assert not list((tmp_path / "processed").glob("*.csv")) \
        if (tmp_path / "processed").exists() else True


def test_allowlist_is_fixed_and_contains_no_model_or_2025_routes():
    assert {s.slug for s in STATS} == {
        "shoot", "shoot_on_target", "suffer_shoot_on_target", "ball_rate",
        "pass_count", "pass_count_per_game", "expected_goals", "expected_goals_against",
        "distance_per_game", "sprint_per_game",
    }
    assert all("/2026-27/" in BASE_URL.format(slug=s.slug) for s in STATS)
    assert len(SUPPLEMENTAL_STATS) == 27
    assert not ({s.slug for s in STATS} & {s.slug for s in SUPPLEMENTAL_STATS})
    assert len({s.slug for s in SUPPLEMENTAL_STATS}) == len(SUPPLEMENTAL_STATS)
    assert all("/2026-27/" in BASE_URL.format(slug=s.slug) for s in SUPPLEMENTAL_STATS)
