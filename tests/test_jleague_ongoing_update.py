"""Offline update scenarios built from artificial season HTML and provenance."""

from datetime import date, timedelta
import hashlib
from html import escape
import json
from pathlib import Path
import socket
import urllib.request

import pandas as pd
import pytest

from src.collect.jleague import HEADERS


LISTING_URL = (
    "https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1"
    "&competition_years=2026&tv_relay_station_name="
)


def synthetic_fixtures():
    """Twenty clubs, all 380 directed pairings, without production raw data."""
    rotation = [f"club{number:02d}" for number in range(20)]
    first_half = []
    for _ in range(19):
        first_half.append(list(zip(rotation[:10], reversed(rotation[10:]))))
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    rounds = first_half + [
        [(away, home) for home, away in pairs] for pairs in first_half
    ]
    return [
        {
            "home": home, "away": away, "round": round_number,
            "date": date(2026, 8, 7) + timedelta(days=7 * (round_number - 1)),
            "kickoff": "19:00", "score": None, "match_id": None,
            "stadium": "人工会場", "attendance": "",
        }
        for round_number, pairs in enumerate(rounds, 1)
        for home, away in pairs
    ]


def listing_html(fixtures):
    rows = []
    for fixture in fixtures:
        score = fixture["score"]
        score_text = "vs" if score is None else f"{score[0]}-{score[1]}"
        values = [
            "2026/27", "Ｊ１", f"第{fixture['round']}節第1日",
            fixture["date"].strftime("%y/%m/%d") + "(土)",
            fixture["kickoff"], fixture["home"], score_text,
            fixture["away"], fixture["stadium"], fixture["attendance"], "人工放送",
        ]
        cells = [f"<td>{escape(value)}</td>" for value in values]
        for column, role in ((5, "home"), (7, "away")):
            club = fixture[role]
            cells[column] = (
                f'<td><a href="http://www.jleague.jp/club/{club}/profile/">'
                f"{escape(club)}</a></td>"
            )
        if fixture["match_id"] is not None:
            cells[6] = (
                f'<td><a href="/SFMS02/?match_card_id={fixture["match_id"]}">'
                f"{score_text}</a></td>"
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    headers = "".join(f"<th>{escape(header)}</th>" for header in HEADERS)
    return (
        '<table class="table-base00 search-table">'
        f"<thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def write_source(path: Path, html: str, *, timestamp: str, url=LISTING_URL):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = html.encode("utf-8")
    path.write_bytes(raw)
    metadata = {
        "requested_url": url, "final_url": url, "status": 200,
        "fetched_at_utc": timestamp, "content_type": "text/html;charset=UTF-8",
        "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
    }
    path.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def write_completion(root: Path, fixture, number: int):
    """An explicit rendered game-over section, not a script or label dictionary."""
    day = fixture["date"]
    url = f"https://www.jleague.jp/match/j1/{day.year}/{day:%m%d}01/"
    home, away = fixture["score"]
    html = (
        f'<link rel="canonical" href="{url}">'
        '<div class="o-page-header--game-details o-page-header--game-details--post-game">'
        '<div class="a-tournament-logo--j1"><img alt="明治安田Ｊ１リーグ"></div>'
        f'<p class="o-page-header__date">{day.year}/{day.month}/{day.day} (土) 19:00 KO</p>'
        f'<p class="o-page-header__section">第{fixture["round"]}節</p>'
        f'<a class="o-page-header__club--home" href="/club/{fixture["home"]}/"></a>'
        f'<a class="o-page-header__club--away" href="/club/{fixture["away"]}/"></a>'
        f'<p class="o-page-header__match-score">{home}</p>'
        f'<p class="o-page-header__match-score">{away}</p></div>'
        '<section id="game-over" class="p-game-details-summary-tab__game-over">'
        '<h3>試合終了</h3>'
        f'<p class="o-team-comparison__score">{home}</p>'
        f'<p class="o-team-comparison__score">{away}</p></section>'
    )
    return write_source(
        root / f"evidence-{number}.html", html,
        timestamp=f"2026-09-{number:02d}T10:00:00+00:00", url=url,
    )


def write_prematch_identity(root: Path, fixture, number: int):
    """An explicit official pre-match page carrying identity, not completion."""
    day = fixture["date"]
    url = f"https://www.jleague.jp/match/j1/{day.year}/{day:%m%d}01/"
    html = (
        f'<link rel="canonical" href="{url}">'
        '<div class="o-page-header--game-details o-page-header--game-details--pre-game">'
        '<div class="a-tournament-logo--j1"><img alt="明治安田Ｊ１リーグ"></div>'
        f'<p class="o-page-header__date">{day.year}/{day.month}/{day.day} (土) 19:00 KO</p>'
        f'<p class="o-page-header__section">第{fixture["round"]}節</p>'
        f'<a class="o-page-header__club--home" href="/club/{fixture["home"]}/"></a>'
        f'<a class="o-page-header__club--away" href="/club/{fixture["away"]}/"></a>'
        '</div>'
    )
    return write_source(
        root / f"identity-evidence-{number}.html", html,
        timestamp=f"2026-09-{number:02d}T10:00:00+00:00", url=url,
    )


def tree_bytes(root: Path):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


def read_csv(root: Path, filename: str):
    return pd.read_csv(root / filename, dtype="string", keep_default_na=False)


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("Snapshot processing must never access the network.")

    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)


@pytest.fixture
def make_snapshot(tmp_path):
    from src.collect.jleague_ongoing import create_snapshot

    def make(fixtures, number, evidence=()):
        timestamp = f"2026-09-{number:02d}T10:00:00+00:00"
        listing = write_source(
            tmp_path / "inputs" / str(number) / "listing.html",
            listing_html(fixtures), timestamp=timestamp,
        )
        return create_snapshot(
            tmp_path / "raw" / "snapshots", listing_html=listing,
            evidence_html=evidence, snapshot_id=f"snapshot-{number:02d}",
        )

    return make


def test_snapshot_is_immutable_and_reusing_identical_input_is_safe(tmp_path):
    from src.collect.jleague_ongoing import create_snapshot

    fixtures = synthetic_fixtures()
    source = write_source(
        tmp_path / "source.html", listing_html(fixtures),
        timestamp="2026-09-01T10:00:00+00:00",
    )
    raw_root = tmp_path / "snapshots"
    snapshot = create_snapshot(raw_root, listing_html=source, snapshot_id="same-id")
    before = tree_bytes(raw_root)
    assert create_snapshot(raw_root, listing_html=source, snapshot_id="same-id") == snapshot
    assert tree_bytes(raw_root) == before

    fixtures[0]["kickoff"] = "19:30"
    write_source(source, listing_html(fixtures), timestamp="2026-09-01T10:00:00+00:00")
    with pytest.raises(ValueError):
        create_snapshot(raw_root, listing_html=source, snapshot_id="same-id")
    assert tree_bytes(raw_root) == before


def test_unprocessed_v1_stops_but_materialized_v1_replay_is_read_only(tmp_path, make_snapshot):
    from src.collect.jleague_ongoing import _json, _sha, process_snapshot

    snapshot = make_snapshot(synthetic_fixtures(), 1)
    manifest_path = snapshot / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["format_version"] = "ongoing-v1"
    manifest_path.write_bytes(_json(manifest))
    output = tmp_path / "processed"
    with pytest.raises(ValueError, match="unprocessed ongoing-v1"):
        process_snapshot(snapshot, output)
    assert not (output / "runs").exists()

    run = {
        "snapshot_id": manifest["snapshot_id"],
        "snapshot_sha256": _sha(manifest_path.read_bytes()),
        "format_version": "ongoing-v1",
    }
    run_path = output / "runs" / f"{manifest['snapshot_id']}-ongoing-v1.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_bytes(_json(run))
    revision = output / "revisions" / _sha(_json(run))
    revision.mkdir(parents=True)
    expected = {"publication_status": "published", "legacy": True}
    (revision / "manifest.json").write_bytes(_json({
        "format_version": "ongoing-v1", "files": {}, "summary": expected,
    }))
    before = tree_bytes(output)
    assert process_snapshot(snapshot, output) == expected
    assert tree_bytes(output) == before


def test_offline_v1_migration_recovers_typed_origins_without_mutating_v1(tmp_path):
    from src.collect.jleague_ongoing import _json, _sha, migrate_v1_to_v2

    output = tmp_path / "processed"
    revision = output / "revisions" / "accepted-v1"
    revision.mkdir(parents=True)
    page_completed = "https://www.jleague.jp/match/j1/2026/100901/"
    page_scheduled = "https://www.jleague.jp/match/j1/2026/101002/"
    listing = {
        "kind": "listing", "source_url": LISTING_URL,
        "sha256": "1" * 64, "fetched_at_utc": "2026-10-01T00:00:00+00:00",
    }
    completed_evidence = {
        "kind": "evidence", "source_url": page_completed,
        "sha256": "2" * 64, "fetched_at_utc": "2026-10-01T00:01:00+00:00",
    }
    scheduled_evidence = {
        "kind": "evidence", "source_url": page_scheduled,
        "sha256": "3" * 64, "fetched_at_utc": "2026-10-01T00:02:00+00:00",
    }
    base = {
        "season": 2026, "competition_key": "j1_2026_2027", "round": 1,
        "match_date": "2026-10-09", "home_club": "a", "away_club": "b",
        "home_team": "A", "away_team": "B", "home_score": None,
        "away_score": None, "result": None, "source_url": LISTING_URL,
        "listing_source_url": LISTING_URL, "evidence_url": "", "evidence_type": "",
    }
    rows = [
        {
            **base, "fixture_key": "j1_2026_2027:a:b", "status": "completed",
            "match_id": "42", "source_url":
            "https://data.j-league.or.jp/SFMS02/?match_card_id=42",
            "evidence_url": page_completed, "evidence_type": "official_game_over_section",
            "home_score": 1, "away_score": 0, "result": 2,
        },
        {
            **base, "fixture_key": "j1_2026_2027:c:d", "home_club": "c",
            "away_club": "d", "status": "scheduled", "match_id": "101002",
            "evidence_url": page_scheduled,
            "evidence_type": "official_completion_unconfirmed",
        },
        {
            **base, "fixture_key": "j1_2026_2027:e:f", "home_club": "e",
            "away_club": "f", "status": "scheduled", "match_id": None,
        },
    ]
    observations = _json(rows)
    schedule = b"legacy-schedule\n"
    (revision / "observations.json").write_bytes(observations)
    (revision / "schedule.csv").write_bytes(schedule)
    manifest = {
        "format_version": "ongoing-v1", "completion_policy": "official-game-over-v1",
        "snapshot_id": "accepted-snapshot", "sequence": 1,
        "files": {"observations.json": _sha(observations), "schedule.csv": _sha(schedule)},
        "summary": {
            "publication_status": "published",
            "sources": [listing, completed_evidence, scheduled_evidence],
        },
    }
    (revision / "manifest.json").write_bytes(_json(manifest))
    before = tree_bytes(revision)

    migrated, bridges, migration = migrate_v1_to_v2(
        revision, output, established_snapshot="boundary-snapshot",
        established_revision="boundary-revision", enforce_frozen_baseline=False,
    )

    assert tree_bytes(revision) == before
    assert [(row["match_page_id"], row["data_site_match_id"]) for row in migrated] == [
        ("100901", "42"), ("101002", None), (None, None),
    ]
    assert len(bridges) == 1
    assert bridges[0]["match_page_origin_revision"] == "accepted-v1"
    assert bridges[0]["data_site_origin_revision"] == "accepted-v1"
    assert migration["migrated_bridge_count"] == 1
    assert migration["migrated_match_page_only_count"] == 1


@pytest.mark.parametrize("field,value", [("sha256", "0" * 64), ("bytes", 1)])
def test_snapshot_rejects_metadata_that_does_not_match_raw(tmp_path, field, value):
    from src.collect.jleague_ongoing import create_snapshot

    source = write_source(
        tmp_path / "source.html", listing_html(synthetic_fixtures()),
        timestamp="2026-09-01T10:00:00+00:00",
    )
    metadata_path = source.with_suffix(".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ValueError):
        create_snapshot(tmp_path / "snapshots", listing_html=source)


def test_bootstrap_with_no_completed_matches_skips_empty_validation_and_replays_exactly(
    tmp_path, make_snapshot, monkeypatch,
):
    from src.collect import jleague_ongoing as ongoing

    def reject_empty_validation(*args, **kwargs):
        pytest.fail("An entirely scheduled season must not reach result validation.")

    monkeypatch.setattr(ongoing, "validate_matches", reject_empty_validation)
    snapshot = make_snapshot(synthetic_fixtures(), 1)
    output = tmp_path / "processed"
    summary = ongoing.process_snapshot(snapshot, output)
    assert summary["counts"] == {"scheduled": 380, "candidate": 0, "completed": 0}
    assert summary["publication_status"] == "published"
    assert len(read_csv(output, "schedule.csv")) == 380
    assert read_csv(output, "completed_matches.csv").empty
    changes = read_csv(output, "change_log.csv")
    assert set(changes.event_type) == {"new_fixture"}
    assert changes.event_id.is_unique
    before = tree_bytes(output)
    assert ongoing.process_snapshot(snapshot, output) == summary
    assert tree_bytes(output) == before


def test_prematch_evidence_publishes_identity_without_changing_status_and_replays(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    snapshot = make_snapshot(fixtures, 1, [evidence])
    output = tmp_path / "processed"

    summary = process_snapshot(snapshot, output)

    assert summary["publication_status"] == "published"
    assert summary["counts"] == {"scheduled": 380, "candidate": 0, "completed": 0}
    assert summary["match_id_count"] == 1
    schedule = read_csv(output, "schedule.csv")
    linked = schedule.loc[schedule.fixture_key.eq("j1_2026_2027:club00:club19")].iloc[0]
    assert linked.match_id == "080701"
    assert linked.status == "scheduled"
    assert linked.evidence_type == "official_completion_unconfirmed"
    assert read_csv(output, "completed_matches.csv").empty
    identity = read_csv(output, "fixture_identity.csv")
    assert identity.loc[identity.fixture_key.eq(linked.fixture_key), "match_id"].item() == "080701"
    before = tree_bytes(output)
    assert process_snapshot(snapshot, output) == summary
    assert tree_bytes(output) == before


def test_verified_scheduled_identity_carries_forward_repeatedly_with_stable_origin(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    output = tmp_path / "processed"
    original = process_snapshot(make_snapshot(fixtures, 1, [evidence]), output)
    fixture_key = "j1_2026_2027:club00:club19"

    # These listing metadata changes were not bound by the identity evidence.
    fixtures[0].update(kickoff="20:00", stadium="変更会場", attendance="12,345")
    second_snapshot = make_snapshot(fixtures, 2)
    second = process_snapshot(second_snapshot, output)
    assert second["publication_status"] == "published"
    assert second["match_id_count"] == 1
    assert second["source_requests_during_processing"] == 0
    assert "identity_conflict" not in second["change_counts"]
    linked = read_csv(output, "schedule.csv").loc[lambda frame: frame.fixture_key.eq(fixture_key)].iloc[0]
    assert linked.match_id == "080701"
    assert linked.status == "scheduled"
    assert linked.home_score == linked.away_score == linked.result == ""
    assert linked.evidence_url == "https://www.jleague.jp/match/j1/2026/080701/"
    assert linked.evidence_type == "official_completion_unconfirmed"
    assert linked.identity_origin_revision == original["revision_id"]
    assert "schedule_changed" in second["change_counts"]

    third_snapshot = make_snapshot(fixtures, 3)
    third = process_snapshot(third_snapshot, output)
    repeated = read_csv(output, "schedule.csv").loc[lambda frame: frame.fixture_key.eq(fixture_key)].iloc[0]
    assert third["publication_status"] == "published"
    assert repeated.match_id == "080701"
    assert repeated.identity_origin_revision == original["revision_id"]

    raw_before = tree_bytes(third_snapshot)
    output_before = tree_bytes(output)
    assert process_snapshot(third_snapshot, output) == third
    assert tree_bytes(third_snapshot) == raw_before
    assert tree_bytes(output) == output_before


@pytest.mark.parametrize("changed_field,new_value", [
    ("date", date(2026, 8, 8)),
    ("round", 2),
])
def test_date_or_round_change_does_not_inherit_scheduled_identity(
    tmp_path, make_snapshot, changed_field, new_value,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1, [evidence]), output)
    previous_pointer = (output / "latest.json").read_bytes()
    fixtures[0][changed_field] = new_value

    summary = process_snapshot(make_snapshot(fixtures, 2), output)

    assert summary["publication_status"] == "held"
    assert "identity_conflict" in summary["publication_blocks"]
    assert (output / "latest.json").read_bytes() == previous_pointer
    held = output / "revisions" / summary["revision_id"]
    row = read_csv(held, "schedule.csv").loc[
        lambda frame: frame.fixture_key.eq("j1_2026_2027:club00:club19")
    ].iloc[0]
    assert row.match_id == ""
    changes = read_csv(held, "change_log.csv")
    current = changes.loc[
        changes.snapshot_id.eq("snapshot-02")
        & changes.fixture_key.eq("j1_2026_2027:club00:club19")
    ]
    assert {"identity_conflict", "schedule_changed"} <= set(current.event_type)


def test_current_explicit_identity_evidence_takes_precedence_over_carry_forward(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    first_evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    process_snapshot(make_snapshot(fixtures, 1, [first_evidence]), output)
    current_evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 2)

    summary = process_snapshot(make_snapshot(fixtures, 2, [current_evidence]), output)

    assert summary["publication_status"] == "published"
    assert "identity_conflict" not in summary["change_counts"]
    linked = read_csv(output, "schedule.csv").loc[
        lambda frame: frame.fixture_key.eq("j1_2026_2027:club00:club19")
    ].iloc[0]
    assert linked.match_id == "080701"
    assert linked.evidence_type == "official_completion_unconfirmed"
    assert linked.identity_origin_revision == summary["revision_id"]
    assert linked.match_page_origin_revision == summary["revision_id"]


def test_current_listing_data_site_identity_bridges_with_previous_page_identity(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    process_snapshot(make_snapshot(fixtures, 1, [evidence]), output)
    fixtures[0]["match_id"] = "999999"

    summary = process_snapshot(make_snapshot(fixtures, 2), output)

    assert summary["publication_status"] == "published"
    assert summary["identity_bridge_count"] == 1
    assert summary["change_counts"]["identity_bridge_established"] == 2
    current = read_csv(output, "schedule.csv").loc[
        lambda frame: frame.fixture_key.eq("j1_2026_2027:club00:club19")
    ].iloc[0]
    assert current.match_id == "080701"
    assert current.match_page_id == "080701"
    assert current.data_site_match_id == "999999"
    assert current.match_id_namespace == "jleague_match_page"


def test_carried_identity_is_not_duplicated_when_current_source_moves_it(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    fixtures[0]["date"] = date(2026, 10, 9)
    output = tmp_path / "processed"
    evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    process_snapshot(make_snapshot(fixtures, 1, [evidence]), output)
    fixtures[1]["match_id"] = "100901"

    summary = process_snapshot(make_snapshot(fixtures, 2), output)

    assert summary["publication_status"] == "held"
    assert "identity_conflict" in summary["publication_blocks"]
    assert any("different fixture" in block for block in summary["publication_blocks"])
    held_schedule = read_csv(output / "revisions" / summary["revision_id"], "schedule.csv")
    assert held_schedule.match_id.tolist().count("100901") == 1
    original = held_schedule.loc[
        held_schedule.fixture_key.eq("j1_2026_2027:club00:club19")
    ].iloc[0]
    assert original.match_id == ""


@pytest.mark.parametrize("with_completion_evidence,expected_status", [
    (False, "candidate"),
    (True, "completed"),
])
def test_candidate_or_completed_data_site_identity_is_never_overwritten_by_carry_forward(
    tmp_path, make_snapshot, with_completion_evidence, expected_status,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    prematch = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    process_snapshot(make_snapshot(fixtures, 1, [prematch]), output)
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    evidence = (
        [write_completion(tmp_path / "evidence", fixtures[0], 2)]
        if with_completion_evidence else []
    )

    summary = process_snapshot(make_snapshot(fixtures, 2, evidence), output)

    assert summary["publication_status"] == "published"
    assert "identity_conflict" not in summary["publication_blocks"]
    current = read_csv(output, "schedule.csv").loc[
        lambda frame: frame.fixture_key.eq("j1_2026_2027:club00:club19")
    ].iloc[0]
    assert current.status == expected_status
    assert current.match_id == "42"
    assert current.match_page_id == "080701"
    assert current.data_site_match_id == "42"
    assert current.match_id_namespace == "jleague_data_site"
    assert summary["change_counts"]["identity_bridge_established"] == 2
    assert summary["change_counts"]["identity_namespace_transition"] == 2


def test_v2_exact_schema_equal_scalar_bridge_and_manifest_artifact(tmp_path, make_snapshot):
    from src.collect.jleague_ongoing import (
        BRIDGE_COLUMNS, FORMAT_VERSION, OBSERVATION_COLUMNS, process_snapshot,
    )

    fixtures = synthetic_fixtures()
    fixtures[0]["date"] = date(2026, 10, 9)
    output = tmp_path / "processed"
    evidence = write_prematch_identity(tmp_path / "evidence", fixtures[0], 1)
    first = process_snapshot(make_snapshot(fixtures, 1, [evidence]), output)
    page_id = "100901"
    fixtures[0].update(score=(1, 0), match_id=page_id, attendance="1,000")
    completion = write_completion(tmp_path / "evidence", fixtures[0], 2)

    summary = process_snapshot(make_snapshot(fixtures, 2, [completion]), output)

    assert summary["publication_status"] == "published"
    assert summary["identity_bridge_count"] == 1
    revision = output / "revisions" / summary["revision_id"]
    manifest = json.loads((revision / "manifest.json").read_bytes())
    assert manifest["format_version"] == FORMAT_VERSION == "ongoing-v2"
    assert "identity_bridges.csv" in manifest["files"]
    assert tuple(read_csv(output, "schedule.csv").columns) == OBSERVATION_COLUMNS
    assert tuple(read_csv(output, "completed_matches.csv").columns) == OBSERVATION_COLUMNS
    bridge = read_csv(output, "identity_bridges.csv")
    assert tuple(bridge.columns) == BRIDGE_COLUMNS
    assert bridge.match_page_id.tolist() == [page_id]
    assert bridge.data_site_match_id.tolist() == [page_id]
    assert bridge.bridge_id.str.fullmatch(r"[0-9a-f]{64}").all()
    row = read_csv(output, "schedule.csv").iloc[0]
    assert row.match_id == page_id
    assert row.match_id_namespace == "jleague_data_site"
    assert first["revision_id"] != summary["revision_id"]


def test_schedule_change_keeps_identity_and_numeric_score_only_becomes_candidate(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1), output)
    original = read_csv(output, "schedule.csv").iloc[0]

    fixtures[0].update(
        date=fixtures[0]["date"] + timedelta(days=2), kickoff="15:00",
        stadium="変更会場", score=(2, 1), match_id="42", attendance="1,000",
    )
    summary = process_snapshot(make_snapshot(fixtures, 2), output)
    assert summary["counts"] == {"scheduled": 379, "candidate": 1, "completed": 0}
    assert summary["publication_status"] == "published"
    current = read_csv(output, "schedule.csv").iloc[0]
    assert current.fixture_key == original.fixture_key
    assert current.match_id == "42"
    mapping = read_csv(output, "fixture_identity.csv")
    assert mapping.loc[mapping.fixture_key == original.fixture_key, "match_id"].item() == "42"
    changes = read_csv(output, "change_log.csv")
    changed = changes.loc[
        (changes.fixture_key == original.fixture_key)
        & (changes.snapshot_id == "snapshot-02")
    ]
    assert {"schedule_changed", "result_candidate"} <= set(changed.event_type)
    assert "new_fixture" not in set(changed.event_type)
    assert read_csv(output, "completed_matches.csv").empty


def test_raw_tampering_is_detected_before_any_published_state_changes(tmp_path, make_snapshot):
    from src.collect.jleague_ongoing import process_snapshot

    output = tmp_path / "processed"
    snapshot = make_snapshot(synthetic_fixtures(), 1)
    process_snapshot(snapshot, output)
    before = (output / "latest.json").read_bytes()
    raw = next(snapshot.rglob("*.html"))
    raw.write_bytes(raw.read_bytes() + b"\n<!-- changed -->")
    with pytest.raises(ValueError):
        process_snapshot(snapshot, output)
    assert (output / "latest.json").read_bytes() == before


def test_missing_fixture_is_reported_without_deleting_previously_published_data(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1), output)
    previous_pointer = (output / "latest.json").read_bytes()
    previous_schedule = (output / "schedule.csv").read_bytes()

    summary = process_snapshot(make_snapshot(fixtures[1:], 2), output)
    assert summary["publication_status"] == "held"
    assert summary["publication_blocks"]
    assert (output / "latest.json").read_bytes() == previous_pointer
    assert (output / "schedule.csv").read_bytes() == previous_schedule
    held = output / "revisions" / summary["revision_id"]
    changes = read_csv(held, "change_log.csv")
    assert "missing_from_snapshot" in set(changes.event_type)
    assert len(read_csv(output, "schedule.csv")) == 380


def test_older_snapshot_replay_cannot_roll_back_latest(tmp_path, make_snapshot):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    old_snapshot = make_snapshot(fixtures, 1)
    old_summary = process_snapshot(old_snapshot, output)
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    newer_summary = process_snapshot(make_snapshot(fixtures, 2), output)
    assert newer_summary["counts"]["candidate"] == 1
    before = tree_bytes(output)
    assert process_snapshot(old_snapshot, output) == old_summary
    assert tree_bytes(output) == before


def test_failed_publication_restores_all_current_outputs_and_allows_retry(
    tmp_path, make_snapshot, monkeypatch,
):
    from src.collect import jleague_ongoing as ongoing

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    ongoing.process_snapshot(make_snapshot(fixtures, 1), output)
    filenames = ("latest.json", "schedule.csv", "completed_matches.csv",
                 "change_log.csv", "update_summary.json")
    before = {name: (output / name).read_bytes() for name in filenames}
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    new_snapshot = make_snapshot(fixtures, 2)
    original_replace = ongoing._replace_latest

    def fail_publication(*args, **kwargs):
        raise OSError("Injected failure before authoritative latest switch")

    monkeypatch.setattr(ongoing, "_replace_latest", fail_publication)
    with pytest.raises(OSError, match="Injected failure"):
        ongoing.process_snapshot(new_snapshot, output)
    assert {name: (output / name).read_bytes() for name in filenames} == before
    monkeypatch.setattr(ongoing, "_replace_latest", original_replace)
    summary = ongoing.process_snapshot(new_snapshot, output)
    assert summary["counts"]["candidate"] == 1
    assert (output / "latest.json").read_bytes() != before["latest.json"]


def test_recovery_compares_previous_observation_and_previous_accepted_separately(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1), output)
    held = process_snapshot(make_snapshot(fixtures[1:], 2), output)
    assert held["publication_status"] == "held"
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    summary = process_snapshot(make_snapshot(fixtures, 3), output)
    assert summary["publication_status"] == "published"
    changes = read_csv(output, "change_log.csv")
    changes = changes.loc[changes.snapshot_id == "snapshot-03"]
    observed = changes.loc[changes.comparison == "previous_snapshot"]
    accepted = changes.loc[changes.comparison == "previous_accepted"]
    assert "new_fixture" in set(observed.event_type)
    assert "new_fixture" not in set(accepted.event_type)
    assert "result_candidate" in set(accepted.event_type)


def test_confirmed_result_reaches_existing_validation_and_a_b_a_corrections_keep_history(
    tmp_path, make_snapshot, monkeypatch,
):
    from src.collect import jleague_ongoing as ongoing

    fixtures = synthetic_fixtures()
    fixtures[0].update(score=(2, 1), match_id="42", attendance="1,000")
    output = tmp_path / "processed"
    original_validate = ongoing.validate_matches
    validated_inputs = []

    def record_validation(frame):
        validated_inputs.append(frame.copy(deep=True))
        return original_validate(frame)

    monkeypatch.setattr(ongoing, "validate_matches", record_validation)
    candidate = ongoing.process_snapshot(make_snapshot(fixtures, 1), output)
    assert candidate["counts"]["candidate"] == 1
    assert validated_inputs == []

    for number, score in ((2, (2, 1)), (3, (0, 2)), (4, (2, 1))):
        fixtures[0]["score"] = score
        evidence = write_completion(tmp_path / "evidence", fixtures[0], number)
        summary = ongoing.process_snapshot(make_snapshot(fixtures, number, [evidence]), output)
        assert summary["publication_status"] == "published"
        assert summary["counts"] == {"scheduled": 379, "candidate": 0, "completed": 1}
        completed = read_csv(output, "completed_matches.csv")
        assert completed.match_id.tolist() == ["42"]
        assert completed.home_score.tolist() == [str(score[0])]
        assert completed.away_score.tolist() == [str(score[1])]
        assert completed.result.tolist() == ["2" if score[0] > score[1] else "0"]

    assert len(validated_inputs) >= 3
    assert all(len(frame) == 1 and frame.match_id.tolist() == ["42"] for frame in validated_inputs)
    changes = read_csv(output, "change_log.csv")
    corrected = changes.loc[
        (changes.event_type == "result_corrected")
        & (changes.comparison == "previous_snapshot")
    ]
    assert corrected.snapshot_id.tolist() == ["snapshot-03", "snapshot-04"]
    assert corrected.event_id.is_unique
    assert [json.loads(value)["home_score"] for value in corrected.before] == [2, 0]
    assert [json.loads(value)["home_score"] for value in corrected.after] == [0, 2]
    assert "completed" in set(changes.event_type)
    before = tree_bytes(output)
    assert ongoing.process_snapshot(make_snapshot(fixtures, 4, [evidence]), output) == summary
    assert tree_bytes(output) == before


def test_changed_confirmed_score_without_fresh_evidence_is_held_as_a_candidate(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    evidence = write_completion(tmp_path / "evidence", fixtures[0], 1)
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1, [evidence]), output)
    previous_pointer = (output / "latest.json").read_bytes()
    previous_completed = (output / "completed_matches.csv").read_bytes()

    fixtures[0]["score"] = (0, 1)
    summary = process_snapshot(make_snapshot(fixtures, 2), output)
    assert summary["publication_status"] == "held"
    assert summary["counts"] == {"scheduled": 379, "candidate": 1, "completed": 0}
    assert (output / "latest.json").read_bytes() == previous_pointer
    assert (output / "completed_matches.csv").read_bytes() == previous_completed
    changes = read_csv(output / "revisions" / summary["revision_id"], "change_log.csv")
    assert "result_corrected" in set(changes.event_type)


def test_unchanged_confirmed_result_retains_provenance_without_requiring_another_fetch(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    evidence = write_completion(tmp_path / "evidence", fixtures[0], 1)
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1, [evidence]), output)
    original_completed = read_csv(output, "completed_matches.csv")
    summary = process_snapshot(make_snapshot(fixtures, 2), output)
    assert summary["publication_status"] == "published"
    assert summary["counts"]["completed"] == 1
    current_completed = read_csv(output, "completed_matches.csv")
    assert current_completed.evidence_url.tolist() == original_completed.evidence_url.tolist()
    changes = read_csv(output, "change_log.csv")
    current_changes = changes.loc[changes.snapshot_id == "snapshot-02"]
    assert "result_corrected" not in set(current_changes.event_type)


def test_an_existing_writer_lock_is_respected(tmp_path, make_snapshot):
    from src.collect.jleague_ongoing import process_snapshot

    snapshot = make_snapshot(synthetic_fixtures(), 1)
    output = tmp_path / "processed"
    output.mkdir()
    lock = output / ".update.lock"
    lock.write_text("another active writer", encoding="utf-8")
    with pytest.raises(RuntimeError):
        process_snapshot(snapshot, output)
    assert lock.read_text(encoding="utf-8") == "another active writer"
    assert not (output / "latest.json").exists()


def test_importing_an_older_listing_under_a_new_snapshot_id_cannot_roll_back_latest(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import create_snapshot, process_snapshot

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    old_source = write_source(
        tmp_path / "old-listing.html", listing_html(fixtures),
        timestamp="2026-09-01T10:00:00+00:00",
    )
    process_snapshot(make_snapshot(fixtures, 1), output)
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    process_snapshot(make_snapshot(fixtures, 2), output)
    before = (output / "latest.json").read_bytes()
    stale_import = create_snapshot(
        tmp_path / "raw" / "snapshots", listing_html=old_source,
        snapshot_id="snapshot-new-id-but-old-observation",
    )
    summary = process_snapshot(stale_import, output)
    assert summary["publication_status"] == "held"
    assert any("older" in block.lower() for block in summary["publication_blocks"])
    assert (output / "latest.json").read_bytes() == before
    assert read_csv(output, "schedule.csv").match_id.tolist().count("42") == 1


def test_an_official_match_id_cannot_silently_move_between_fixture_keys(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot

    fixtures = synthetic_fixtures()
    fixtures[0].update(score=(1, 0), match_id="42", attendance="1,000")
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1), output)
    previous_pointer = (output / "latest.json").read_bytes()
    previous_mapping = (output / "fixture_identity.csv").read_bytes()
    fixtures[0].update(score=None, match_id=None, attendance="")
    fixtures[1].update(score=(1, 0), match_id="42", attendance="1,000")
    summary = process_snapshot(make_snapshot(fixtures, 2), output)
    assert summary["publication_status"] == "held"
    assert any("different fixture" in block for block in summary["publication_blocks"])
    assert (output / "latest.json").read_bytes() == previous_pointer
    assert (output / "fixture_identity.csv").read_bytes() == previous_mapping


def test_existing_result_validation_failure_leaves_snapshot_and_latest_intact(
    tmp_path, make_snapshot,
):
    from src.collect.jleague_ongoing import process_snapshot
    from src.collect.matches import MatchValidationError

    fixtures = synthetic_fixtures()
    output = tmp_path / "processed"
    process_snapshot(make_snapshot(fixtures, 1), output)
    before = (output / "latest.json").read_bytes()
    fixtures[0].update(score=(1, 0), match_id="42", stadium="", attendance="1,000")
    evidence = write_completion(tmp_path / "evidence", fixtures[0], 2)
    invalid_completed_snapshot = make_snapshot(fixtures, 2, [evidence])
    saved_raw = tree_bytes(invalid_completed_snapshot)
    with pytest.raises(MatchValidationError):
        process_snapshot(invalid_completed_snapshot, output)
    assert tree_bytes(invalid_completed_snapshot) == saved_raw
    assert (output / "latest.json").read_bytes() == before
    assert read_csv(output, "completed_matches.csv").empty
