"""Synthetic read-only contracts for the suspension PIT registry."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

import src.collect.jleague_suspension_registry as registry
from src.collect.jleague_suspensions import CSV_FIELDS


URL = "https://www.jleague.jp/news/article/99999/"
NOTICE_ID = "99999"
SCHEDULE_SHA = "a" * 64
PUBLISHED = "2026-10-08T08:00:00Z"
UPDATED = "2026-10-08T08:10:00Z"
RETRIEVED = "2026-10-08T09:00:00Z"
KICKOFF = "2026-10-09T19:00:00+09:00"


def _row(snapshot_id, generation, **changes):
    values = {
        "snapshot_id": snapshot_id,
        "retrieved_at": RETRIEVED,
        "published_at": PUBLISHED,
        "updated_at": UPDATED,
        "notice_id": NOTICE_ID,
        "competition": "j1",
        "season": "2026/27",
        "team_id": "team_0001",
        "team_link_status": "EXACT",
        "official_club_name": "千葉",
        "player_name_raw": "選手 一郎",
        "official_player_id": "",
        "target_match_id": "m1",
        "target_match_date": "2026-10-09",
        "target_round": "第１１節第１日",
        "opponent_name": "町田",
        "suspension_code": "J1(a)",
        "suspension_reason": "",
        "suspension_match_index": "1",
        "suspension_match_count": "1",
        "match_link_status": "EXACT",
        "player_link_status": "UNRESOLVED",
        "source_url": URL,
    }
    if generation == registry.KICKOFF_V2:
        values.update({
            "target_kickoff_time": "19:00",
            "target_kickoff_at": KICKOFF,
            "schedule_sha256": SCHEDULE_SHA,
            "kickoff_link_status": "EXACT",
        })
    values.update(changes)
    return values


def _write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _make_snapshot(
    tmp_path,
    snapshot_id,
    *,
    generation=registry.LEGACY_V1,
    status="COMPLETE",
    retrieved_at=RETRIEVED,
    rows=None,
    write_csv=None,
):
    raw_root = tmp_path / "raw"
    processed_root = tmp_path / "processed"
    raw_dir = raw_root / snapshot_id
    raw_dir.mkdir(parents=True)
    body = f"immutable-{snapshot_id}".encode()
    html_name = f"notice_{NOTICE_ID}.html"
    (raw_dir / html_name).write_bytes(body)
    rows = list(rows) if rows is not None else [_row(snapshot_id, generation)]
    for row in rows:
        row["retrieved_at"] = retrieved_at
    manifest = {
        "snapshot_id": snapshot_id,
        "retrieved_at": retrieved_at,
        "season": "2026/27",
        "status": status,
        "source_urls": [URL],
        "pages": [{
            "notice_id": NOTICE_ID,
            "requested_url": URL,
            "final_url": URL,
            "http_status": 200,
            "content_type": "text/html",
            "response_size": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "html": html_name,
            "parse_result": "OK",
        }],
        "notice_count": 1 if status == "COMPLETE" else 0,
        "processed_target_rows": len(rows) if status == "COMPLETE" else 0,
    }
    if status == "COMPLETE":
        manifest.update({
            "exact_team_linkage_count": sum(row["team_link_status"] == "EXACT" for row in rows),
            "exact_match_linkage_count": sum(row["match_link_status"] == "EXACT" for row in rows),
            "unresolved_match_count": sum(row["match_link_status"] != "EXACT" for row in rows),
            "exact_player_linkage_count": sum(row["player_link_status"] == "EXACT" for row in rows),
        })
    if generation == registry.KICKOFF_V2:
        manifest.update({
            "schedule_path": "data/processed/jleague/2026_27/schedule.csv",
            "schedule_sha256": SCHEDULE_SHA,
            "exact_kickoff_linkage_count": (
                sum(row["kickoff_link_status"] == "EXACT" for row in rows)
                if status == "COMPLETE" else 0
            ),
            "unresolved_kickoff_count": (
                sum(row["kickoff_link_status"] != "EXACT" for row in rows)
                if status == "COMPLETE" else 0
            ),
        })
    (raw_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output = processed_root / f"{snapshot_id}.csv"
    if write_csv is None:
        write_csv = status == "COMPLETE"
    if write_csv:
        fields = registry.LEGACY_CSV_FIELDS if generation == registry.LEGACY_V1 else CSV_FIELDS
        _write_csv(output, fields, rows)
    return raw_root, processed_root, raw_dir, output


def _manifest(raw_dir):
    return json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))


def _save_manifest(raw_dir, value):
    (raw_dir / "manifest.json").write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _csv_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return tuple(reader.fieldnames), list(reader)


def test_valid_complete_legacy_snapshot_is_explicitly_not_assessable(tmp_path):
    _, processed, raw_dir, _ = _make_snapshot(tmp_path, "legacy")
    physical, rows = registry.audit_snapshot(raw_dir, processed_root=processed)
    assert physical.schema_generation == registry.LEGACY_V1
    assert physical.integrity_status == "VALID_COMPLETE"
    assert physical.exact_kickoff_linkage_count is None
    assert rows[0].target_kickoff_at == ""
    assert rows[0].kickoff_link_status == ""
    assert rows[0].schedule_sha256 == ""
    assert rows[0].evidence_status == "NOT_ASSESSABLE_LEGACY"


def test_valid_complete_v2_snapshot_uses_only_frozen_provenance(tmp_path):
    _, processed, raw_dir, _ = _make_snapshot(
        tmp_path, "v2", generation=registry.KICKOFF_V2
    )
    physical, rows = registry.audit_snapshot(raw_dir, processed_root=processed)
    assert physical.schema_generation == registry.KICKOFF_V2
    assert physical.schedule_sha256 == SCHEDULE_SHA
    assert physical.exact_kickoff_linkage_count == 1
    assert rows[0].target_kickoff_at == KICKOFF
    assert rows[0].evidence_status == "PRE_KICKOFF_CONFIRMED"


@pytest.mark.parametrize("generation", [registry.LEGACY_V1, registry.KICKOFF_V2])
def test_valid_incomplete_snapshot_has_no_evidence_rows(tmp_path, generation):
    _, processed, raw_dir, _ = _make_snapshot(
        tmp_path, f"incomplete-{generation}", generation=generation, status="INCOMPLETE"
    )
    physical, rows = registry.audit_snapshot(raw_dir, processed_root=processed)
    assert physical.status == "INCOMPLETE"
    assert physical.schema_generation == generation
    assert physical.integrity_status == "VALID_INCOMPLETE"
    assert physical.processed_path is None
    assert rows == ()


def test_manifest_snapshot_id_mismatch_is_rejected(tmp_path):
    _, processed, raw_dir, _ = _make_snapshot(tmp_path, "snapshot-id")
    manifest = _manifest(raw_dir)
    manifest["snapshot_id"] = "different"
    _save_manifest(raw_dir, manifest)
    with pytest.raises(registry.SuspensionRegistryError, match="snapshot_id mismatch"):
        registry.audit_snapshot(raw_dir, processed_root=processed)


def test_invalid_manifest_json_is_rejected(tmp_path):
    _, processed, raw_dir, _ = _make_snapshot(tmp_path, "bad-json")
    (raw_dir / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(registry.SuspensionRegistryError, match="Cannot read manifest"):
        registry.audit_snapshot(raw_dir, processed_root=processed)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw, manifest: (raw / manifest["pages"][0]["html"]).unlink(), "missing raw page"),
        (lambda raw, manifest: (raw / manifest["pages"][0]["html"]).write_bytes(b"changed"), "SHA-256 mismatch"),
        (lambda _raw, manifest: manifest["pages"][0].update(response_size=999), "response size mismatch"),
        (lambda _raw, manifest: manifest["pages"].append(dict(manifest["pages"][0])), "duplicate manifest notice/page"),
    ],
)
def test_raw_page_integrity_failures_are_rejected(tmp_path, mutation, message):
    _, processed, raw_dir, _ = _make_snapshot(tmp_path, "raw-integrity")
    manifest = _manifest(raw_dir)
    mutation(raw_dir, manifest)
    _save_manifest(raw_dir, manifest)
    with pytest.raises(registry.SuspensionRegistryError, match=message):
        registry.audit_snapshot(raw_dir, processed_root=processed)


def test_complete_missing_processed_csv_is_rejected(tmp_path):
    _, processed, raw_dir, _ = _make_snapshot(
        tmp_path, "missing-csv", write_csv=False
    )
    with pytest.raises(registry.SuspensionRegistryError, match="lacks processed CSV"):
        registry.audit_snapshot(raw_dir, processed_root=processed)


def test_incomplete_with_processed_csv_is_rejected(tmp_path):
    _, processed, raw_dir, _ = _make_snapshot(
        tmp_path, "incomplete-csv", status="INCOMPLETE", write_csv=True
    )
    with pytest.raises(registry.SuspensionRegistryError, match="INCOMPLETE snapshot has"):
        registry.audit_snapshot(raw_dir, processed_root=processed)


def test_unknown_processed_header_is_rejected(tmp_path):
    _, processed, raw_dir, output = _make_snapshot(tmp_path, "unknown-header")
    fields, rows = _csv_rows(output)
    _write_csv(output, (*fields[:-1], "invented"), rows)
    with pytest.raises(registry.SuspensionRegistryError, match="unknown processed schema"):
        registry.audit_snapshot(raw_dir, processed_root=processed)


@pytest.mark.parametrize(
    ("generation", "remove_v2", "message"),
    [
        (registry.LEGACY_V1, False, "legacy CSV/new manifest hybrid"),
        (registry.KICKOFF_V2, True, "new CSV/legacy manifest hybrid"),
    ],
)
def test_hybrid_schema_is_rejected(tmp_path, generation, remove_v2, message):
    _, processed, raw_dir, _ = _make_snapshot(
        tmp_path, f"hybrid-{generation}", generation=generation
    )
    manifest = _manifest(raw_dir)
    if remove_v2:
        for key in registry.V2_MANIFEST_FIELDS:
            manifest.pop(key)
    else:
        manifest.update({
            "schedule_path": "schedule.csv",
            "schedule_sha256": SCHEDULE_SHA,
            "exact_kickoff_linkage_count": 0,
            "unresolved_kickoff_count": 1,
        })
    _save_manifest(raw_dir, manifest)
    with pytest.raises(registry.SuspensionRegistryError, match=message):
        registry.audit_snapshot(raw_dir, processed_root=processed)


@pytest.mark.parametrize(
    ("row_change", "manifest_change", "message"),
    [
        ({"snapshot_id": "other"}, {}, "processed snapshot_id mismatch"),
        ({"retrieved_at": "2026-10-08T09:01:00Z"}, {}, "processed retrieved_at mismatch"),
        ({"notice_id": "12345"}, {}, "notice ID not in manifest"),
        ({"source_url": "https://www.jleague.jp/news/article/12345/"}, {}, "source URL mismatch"),
        ({}, {"processed_target_rows": 2}, "manifest row count mismatch"),
        ({}, {"exact_match_linkage_count": 0}, "exact_match_linkage_count mismatch"),
        ({}, {"exact_player_linkage_count": 1}, "exact_player_linkage_count mismatch"),
    ],
)
def test_manifest_csv_consistency_failures(
    tmp_path, row_change, manifest_change, message
):
    _, processed, raw_dir, output = _make_snapshot(tmp_path, "consistency")
    fields, rows = _csv_rows(output)
    rows[0].update(row_change)
    _write_csv(output, fields, rows)
    manifest = _manifest(raw_dir)
    manifest.update(manifest_change)
    _save_manifest(raw_dir, manifest)
    with pytest.raises(registry.SuspensionRegistryError, match=message):
        registry.audit_snapshot(raw_dir, processed_root=processed)


@pytest.mark.parametrize(
    ("row_change", "manifest_change", "message"),
    [
        ({}, {"exact_kickoff_linkage_count": 0, "unresolved_kickoff_count": 1}, "kickoff count mismatch"),
        ({"schedule_sha256": "b" * 64}, {}, "schedule SHA mismatch"),
        ({"target_kickoff_at": ""}, {}, r"must be a \+09:00 timestamp"),
    ],
)
def test_v2_provenance_consistency_failures(
    tmp_path, row_change, manifest_change, message
):
    _, processed, raw_dir, output = _make_snapshot(
        tmp_path, "v2-consistency", generation=registry.KICKOFF_V2
    )
    fields, rows = _csv_rows(output)
    rows[0].update(row_change)
    _write_csv(output, fields, rows)
    manifest = _manifest(raw_dir)
    manifest.update(manifest_change)
    _save_manifest(raw_dir, manifest)
    with pytest.raises(registry.SuspensionRegistryError, match=message):
        registry.audit_snapshot(raw_dir, processed_root=processed)


@pytest.mark.parametrize(
    ("generation", "changes", "expected"),
    [
        (registry.KICKOFF_V2, {}, "PRE_KICKOFF_CONFIRMED"),
        (registry.KICKOFF_V2, {"retrieved_at": "2026-10-09T10:00:00Z"}, "POST_KICKOFF_RETRIEVAL"),
        (
            registry.KICKOFF_V2,
            {"published_at": "2026-10-09T10:00:00Z", "retrieved_at": "2026-10-09T10:01:00Z", "updated_at": ""},
            "POST_KICKOFF_PUBLICATION",
        ),
        (registry.LEGACY_V1, {}, "NOT_ASSESSABLE_LEGACY"),
        (registry.KICKOFF_V2, {"match_link_status": "UNRESOLVED"}, "NOT_ASSESSABLE_MATCH"),
        (registry.KICKOFF_V2, {"kickoff_link_status": "UNRESOLVED_MISSING"}, "NOT_ASSESSABLE_KICKOFF"),
        (
            registry.KICKOFF_V2,
            {"published_at": "2026-10-08T10:00:00Z", "retrieved_at": "2026-10-08T09:00:00Z"},
            "INVALID_TIME_PROVENANCE",
        ),
        (
            registry.KICKOFF_V2,
            {"updated_at": "2026-10-08T07:59:00Z"},
            "INVALID_TIME_PROVENANCE",
        ),
        (
            registry.KICKOFF_V2,
            {"updated_at": "2026-10-08T09:01:00Z"},
            "INVALID_TIME_PROVENANCE",
        ),
    ],
)
def test_evidence_timing_precedence(generation, changes, expected):
    row = _row("timing", registry.KICKOFF_V2)
    row.update(changes)
    assert registry.classify_evidence(row, generation) == expected


def test_notice_versions_retain_all_observations_in_retrieval_order(tmp_path):
    raw_root, processed, _, _ = _make_snapshot(
        tmp_path, "z-earlier", retrieved_at="2026-10-08T09:00:00Z"
    )
    _make_snapshot(
        tmp_path, "a-later", retrieved_at="2026-10-08T10:00:00Z"
    )
    report = registry.audit_registry(raw_root=raw_root, processed_root=processed)
    assert [item.snapshot_id for item in report.physical_snapshots] == ["z-earlier", "a-later"]
    assert len(report.evidence_rows) == 2
    assert len(report.notice_versions) == 1
    version = report.notice_versions[0]
    assert version.snapshot_ids == ("z-earlier", "a-later")
    assert version.retrieved_at == (
        "2026-10-08T09:00:00Z", "2026-10-08T10:00:00Z"
    )


def test_registry_order_is_deterministic_and_files_are_never_modified(tmp_path):
    raw_root, processed, _, _ = _make_snapshot(
        tmp_path, "third", retrieved_at="2026-10-08T11:00:00Z"
    )
    _make_snapshot(tmp_path, "first", retrieved_at="2026-10-08T09:00:00Z")
    _make_snapshot(tmp_path, "second", retrieved_at="2026-10-08T10:00:00Z")
    paths = sorted(
        [path for path in raw_root.rglob("*") if path.is_file()]
        + [path for path in processed.rglob("*") if path.is_file()]
    )
    before = {
        str(path): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in paths
    }
    first = registry.audit_registry(raw_root=raw_root, processed_root=processed)
    second = registry.audit_registry(raw_root=raw_root, processed_root=processed)
    after = {
        str(path): (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        for path in paths
    }
    assert [item.snapshot_id for item in first.physical_snapshots] == ["first", "second", "third"]
    assert first == second
    assert before == after
    assert set(paths) == {
        path for path in raw_root.rglob("*") if path.is_file()
    } | {
        path for path in processed.rglob("*") if path.is_file()
    }


def test_summary_counts_are_archive_observations_not_coverage(tmp_path):
    raw_root, processed, _, _ = _make_snapshot(tmp_path, "legacy-summary")
    report = registry.audit_registry(raw_root=raw_root, processed_root=processed)
    summary = registry.summary_counts(report)
    assert summary == {
        "physical_snapshots": 1,
        "complete_snapshots": 1,
        "incomplete_snapshots": 0,
        "legacy_v1_snapshots": 1,
        "kickoff_v2_snapshots": 0,
        "evidence_rows": 1,
        "exact_match_rows": 1,
        "exact_kickoff_rows": 0,
        "pre_kickoff_confirmed_rows": 0,
        "not_assessable_legacy_rows": 1,
        "unresolved_match_rows": 0,
        "unresolved_kickoff_rows": 0,
        "unresolved_player_rows": 1,
        "distinct_notice_ids": 1,
        "distinct_exact_target_match_ids": 1,
    }
    assert "coverage" not in json.dumps(summary).lower()


def test_registry_source_has_no_schedule_model_network_or_write_path():
    source = Path(registry.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "schedule.csv",
        "src.modeling",
        "urlopen",
        "requests",
        "write_text",
        "write_bytes",
        ".open(\"w",
        "eligible",
        "feature_ready",
    ):
        assert forbidden not in source
    assert set(registry.EVIDENCE_STATUSES) == {
        "PRE_KICKOFF_CONFIRMED",
        "NOT_ASSESSABLE_LEGACY",
        "NOT_ASSESSABLE_MATCH",
        "NOT_ASSESSABLE_KICKOFF",
        "POST_KICKOFF_RETRIEVAL",
        "POST_KICKOFF_PUBLICATION",
        "INVALID_TIME_PROVENANCE",
    }
