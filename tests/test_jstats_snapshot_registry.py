"""Offline contracts for the read-only J Stats prospective snapshot registry."""

from __future__ import annotations

import csv
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from src.collect import jstats_snapshot_registry as registry
from src.collect.jstats_team_snapshots import (
    BASE_URL,
    CSV_FIELDS,
    FULL_STATS,
    STAT_BY_SLUG,
    STATS,
    SUPPLEMENTAL_STATS,
    expected_club_slugs,
)
from src.collect.teams import load_team_master


ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "data/processed/jleague/2026_27/schedule.csv"
MASTER = load_team_master()
SLUGS = expected_club_slugs(SCHEDULE)
IDENTITIES = sorted(
    (alias.source_club_id, alias.source_name, alias.team_id)
    for alias in MASTER.aliases
    if alias.source == "jleague_official"
    and alias.source_club_id in SLUGS
    and MASTER.resolve_team_id(
        alias.source_name, source="jleague_official", on=date(2026, 9, 21),
    ) == alias.team_id
)
assert len(IDENTITIES) == 20
TEAM_IDS = tuple(sorted(identity[2] for identity in IDENTITIES))


def _make_snapshot(
    root: Path,
    snapshot_id: str,
    stats,
    *,
    status="COMPLETE",
    source_dates=None,
    write_csv=True,
):
    raw_root, processed_root = root / "raw", root / "processed"
    raw_dir = raw_root / snapshot_id
    raw_dir.mkdir(parents=True)
    stats = tuple(stats)
    source_dates = source_dates or ["2026-09-21"] * len(stats)
    pages = []
    for stat, source_date in zip(stats, source_dates):
        body = f"official raw {snapshot_id} {stat.slug}".encode()
        digest = hashlib.sha256(body).hexdigest()
        (raw_dir / f"{stat.slug}.html").write_bytes(body)
        pages.append({
            "stat_name": stat.slug,
            "requested_url": BASE_URL.format(slug=stat.slug),
            "final_url": BASE_URL.format(slug=stat.slug),
            "status": 200,
            "content_type": "text/html; charset=utf-8",
            "bytes": len(body),
            "sha256": digest,
            "html": f"{stat.slug}.html",
            "parsed_clubs": 20,
            "source_updated_date_jst": source_date,
        })
    manifest = {
        "snapshot_id": snapshot_id,
        "retrieved_at": "2026-09-22T12:00:00Z",
        "season": "2026-27",
        "requested_stats": [stat.slug for stat in stats],
        "status": status,
        "pages": pages,
    }
    (raw_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    output = processed_root / f"{snapshot_id}.csv"
    if write_csv:
        processed_root.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for stat, page in zip(stats, pages):
                definition = STAT_BY_SLUG[stat.slug]
                for slug, name, team_id in IDENTITIES:
                    writer.writerow({
                        "snapshot_id": snapshot_id,
                        "retrieved_at": "2026-09-22T12:00:00Z",
                        "source_updated_at": "",
                        "source_updated_date_jst": source_dates[0],
                        "competition": "j1",
                        "season": "2026-27",
                        "team_id": team_id,
                        "official_club_id": slug,
                        "official_club_name": name,
                        "official_club_slug": slug,
                        "games_played": "",
                        "stat_name": stat.slug,
                        "stat_value": "1",
                        "raw_value": "1",
                        "value_type": definition.value_type,
                        "unit": definition.unit,
                        "source_url": page["requested_url"],
                        "raw_sha256": page["sha256"],
                    })
    return raw_dir, processed_root, output


def _physical(snapshot_id: str, profile: str, stats, *, teams=TEAM_IDS):
    return registry.PhysicalSnapshot(
        snapshot_id=snapshot_id,
        status="COMPLETE",
        profile=profile,
        retrieved_at="2026-09-22T12:00:00Z",
        season="2026-27",
        source_state_date="2026-09-21",
        stat_count=len(tuple(stats)),
        page_count=len(tuple(stats)),
        row_count=20 * len(tuple(stats)),
        integrity_status="PASS",
        stat_names=tuple(stat.slug for stat in stats),
        team_ids=tuple(teams),
        raw_dir="raw",
        processed_path="processed.csv",
    )


def _logical(day: str, *, teams=TEAM_IDS):
    return registry.LogicalFullState(
        season="2026-27",
        source_state_date=day,
        profile="FULL_37",
        kind="PHYSICAL",
        snapshot_ids=(f"snapshot-{day}",),
        stat_names=tuple(stat.slug for stat in FULL_STATS),
        team_ids=tuple(teams),
    )


def _data_site_names():
    names = {}
    with SCHEDULE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            match_date = date.fromisoformat(row["match_date"])
            for side in ("home", "away"):
                name = row[f"{side}_team"]
                team_id = MASTER.resolve_team_id(name, source="jleague_data_site", on=match_date)
                names.setdefault(team_id, name)
    assert set(names) == set(TEAM_IDS)
    return names


def _write_matches(path: Path, *, rounds=1):
    names = _data_site_names()
    teams = list(TEAM_IDS)
    rows = []
    for round_index in range(rounds):
        for index in range(0, 20, 2):
            rows.append({
                "match_id": f"m{round_index}-{index // 2}",
                "match_date": f"2026-09-{15 + round_index:02d}",
                "home_team": names[teams[index]],
                "away_team": names[teams[index + 1]],
            })
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("match_id", "match_date", "home_team", "away_team"))
        writer.writeheader()
        writer.writerows(rows)


def test_profile_classification_uses_exact_set_equality():
    assert registry.classify_profile(stat.slug for stat in STATS) == "BASE_10"
    assert registry.classify_profile(stat.slug for stat in SUPPLEMENTAL_STATS) == "SUPPLEMENTAL_27"
    assert registry.classify_profile(stat.slug for stat in FULL_STATS) == "FULL_37"
    assert registry.classify_profile([stat.slug for stat in STATS[:-1]] + ["invented"]) == "UNKNOWN"


def test_latest_logical_source_date_is_distinct_and_not_retrieval_time():
    old = _logical("2026-09-14")
    duplicate = replace(old, kind="RECONSTRUCTED", snapshot_ids=("base", "supplemental"))
    latest = _logical("2026-09-21")
    report = registry.RegistryReport((), (latest, duplicate, old), ())
    assert registry.distinct_logical_source_dates(report) == ("2026-09-14", "2026-09-21")
    assert registry.latest_logical_source_date(report) == "2026-09-21"


def test_manifest_raw_sha_mismatch_is_hard_failure(tmp_path):
    raw_dir, processed_root, _ = _make_snapshot(tmp_path, "sha-mismatch", STATS)
    (raw_dir / "shoot.html").write_bytes(b"mutated")
    with pytest.raises(registry.SnapshotRegistryError, match="raw SHA-256 mismatch"):
        registry.audit_snapshot(raw_dir, processed_root=processed_root, schedule_path=SCHEDULE, master=MASTER)


def test_complete_without_processed_csv_is_rejected(tmp_path):
    raw_dir, processed_root, _ = _make_snapshot(
        tmp_path, "complete-no-csv", STATS, write_csv=False,
    )
    with pytest.raises(registry.SnapshotRegistryError, match="lacks processed CSV"):
        registry.audit_snapshot(raw_dir, processed_root=processed_root, schedule_path=SCHEDULE, master=MASTER)


def test_incomplete_with_processed_csv_is_rejected(tmp_path):
    raw_dir, processed_root, _ = _make_snapshot(
        tmp_path, "incomplete-with-csv", STATS, status="INCOMPLETE", write_csv=True,
    )
    with pytest.raises(registry.SnapshotRegistryError, match="INCOMPLETE snapshot has"):
        registry.audit_snapshot(raw_dir, processed_root=processed_root, schedule_path=SCHEDULE, master=MASTER)


def test_processed_stat_set_mismatch_is_rejected(tmp_path):
    raw_dir, processed_root, output = _make_snapshot(tmp_path, "stat-mismatch", STATS)
    fields, rows = None, None
    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    rows[-1]["stat_name"] = "invented"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(registry.SnapshotRegistryError, match="processed stat set mismatch"):
        registry.audit_snapshot(raw_dir, processed_root=processed_root, schedule_path=SCHEDULE, master=MASTER)


def test_mixed_source_dates_are_explicit_and_not_inferred(tmp_path):
    dates = ["2026-09-14"] * len(STATS)
    dates[-1] = "2026-09-21"
    raw_dir, processed_root, _ = _make_snapshot(
        tmp_path, "mixed", STATS, status="INCOMPLETE", source_dates=dates, write_csv=False,
    )
    audited = registry.audit_snapshot(
        raw_dir, processed_root=processed_root, schedule_path=SCHEDULE, master=MASTER,
    )
    assert audited.source_state_date == registry.SOURCE_MIXED


def test_base_and_supplemental_reconstruct_exact_logical_full_37():
    base = _physical("base", "BASE_10", STATS)
    supplemental = _physical("supplemental", "SUPPLEMENTAL_27", SUPPLEMENTAL_STATS)
    state = registry.reconstruct_full_state(base, supplemental)
    assert state.profile == "FULL_37"
    assert state.kind == "RECONSTRUCTED"
    assert set(state.stat_names) == set(registry.FULL_SLUGS)
    assert state.snapshot_ids == ("base", "supplemental")


def test_overlapping_stat_reconstruction_is_rejected():
    base = _physical("base", "BASE_10", STATS)
    supplemental = _physical("supplemental", "SUPPLEMENTAL_27", SUPPLEMENTAL_STATS)
    overlap = replace(
        supplemental,
        stat_names=(STATS[0].slug, *supplemental.stat_names[1:]),
    )
    with pytest.raises(registry.SnapshotRegistryError, match="overlap"):
        registry.reconstruct_full_state(base, overlap)


def test_mismatched_team_identity_reconstruction_is_rejected():
    base = _physical("base", "BASE_10", STATS)
    supplemental = _physical(
        "supplemental", "SUPPLEMENTAL_27", SUPPLEMENTAL_STATS,
        teams=(*TEAM_IDS[:-1], "team_9999"),
    )
    with pytest.raises(registry.SnapshotRegistryError, match="team identities differ"):
        registry.reconstruct_full_state(base, supplemental)


def test_same_date_alone_does_not_merge_invalid_pair():
    base = _physical("base", "BASE_10", STATS)
    supplemental = _physical(
        "supplemental", "SUPPLEMENTAL_27", SUPPLEMENTAL_STATS,
        teams=(*TEAM_IDS[:-1], "team_9999"),
    )
    assert registry.build_logical_full_states((base, supplemental)) == ()


def test_transition_clean_one_match_per_team(tmp_path):
    matches = tmp_path / "completed.csv"
    _write_matches(matches, rounds=1)
    result = registry.audit_transition(
        _logical("2026-09-14"), _logical("2026-09-21"),
        completed_path=matches, master=MASTER,
    )
    assert result.status == "CLEAN_ONE_MATCH_PER_TEAM"
    assert result.match_count == 10
    assert set(result.team_appearance_increments.values()) == {1}


def test_transition_multi_match_interval(tmp_path):
    matches = tmp_path / "completed.csv"
    _write_matches(matches, rounds=2)
    result = registry.audit_transition(
        _logical("2026-09-14"), _logical("2026-09-21"),
        completed_path=matches, master=MASTER,
    )
    assert result.status == "MULTI_MATCH_INTERVAL"
    assert result.match_count == 20
    assert set(result.team_appearance_increments.values()) == {2}


def test_transition_no_match_interval(tmp_path):
    matches = tmp_path / "completed.csv"
    _write_matches(matches, rounds=0)
    result = registry.audit_transition(
        _logical("2026-09-14"), _logical("2026-09-21"),
        completed_path=matches, master=MASTER,
    )
    assert result.status == "NO_MATCH_INTERVAL"
    assert result.match_count == 0


def test_registry_has_no_model_or_evaluation_dependency():
    source = Path(registry.__file__).read_text(encoding="utf-8")
    assert "src.modeling" not in source
    assert "sklearn" not in source
    assert "metric" not in source.lower()
