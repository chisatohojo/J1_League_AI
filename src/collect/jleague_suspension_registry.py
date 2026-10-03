"""Read-only integrity registry for immutable J.LEAGUE suspension snapshots.

The registry audits saved raw and processed evidence.  It does not read the
current schedule, discover notices, repair or migrate snapshots, create model
features, fit models, evaluate predictions, or write any file.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from src.collect.jleague_suspensions import (
    CSV_FIELDS,
    KICKOFF_LINK_STATUSES,
    KICKOFF_TIME_RE,
    NOTICE_URL_RE,
    PROCESSED_ROOT,
    RAW_ROOT,
    SEASON,
)


LEGACY_CSV_FIELDS = (
    "snapshot_id", "retrieved_at", "published_at", "updated_at", "notice_id",
    "competition", "season", "team_id", "team_link_status",
    "official_club_name", "player_name_raw", "official_player_id",
    "target_match_id", "target_match_date", "target_round", "opponent_name",
    "suspension_code", "suspension_reason", "suspension_match_index",
    "suspension_match_count", "match_link_status", "player_link_status",
    "source_url",
)
LEGACY_V1 = "LEGACY_V1"
KICKOFF_V2 = "KICKOFF_V2"
V2_MANIFEST_FIELDS = frozenset({
    "schedule_path",
    "schedule_sha256",
    "exact_kickoff_linkage_count",
    "unresolved_kickoff_count",
})
EVIDENCE_STATUSES = (
    "PRE_KICKOFF_CONFIRMED",
    "NOT_ASSESSABLE_LEGACY",
    "NOT_ASSESSABLE_MATCH",
    "NOT_ASSESSABLE_KICKOFF",
    "POST_KICKOFF_RETRIEVAL",
    "POST_KICKOFF_PUBLICATION",
    "INVALID_TIME_PROVENANCE",
)
JST = ZoneInfo("Asia/Tokyo")


class SuspensionRegistryError(ValueError):
    """An immutable suspension snapshot violates the registry contract."""


@dataclass(frozen=True)
class PhysicalSuspensionSnapshot:
    snapshot_id: str
    status: str
    schema_generation: str
    retrieved_at: str
    notice_count: int
    row_count: int
    exact_team_linkage_count: int
    exact_match_linkage_count: int
    exact_kickoff_linkage_count: int | None
    exact_player_linkage_count: int
    schedule_sha256: str | None
    integrity_status: str
    notice_ids: tuple[str, ...]
    source_urls: tuple[str, ...]
    raw_dir: str
    processed_path: str | None


@dataclass(frozen=True)
class SuspensionEvidenceRow:
    snapshot_id: str
    schema_generation: str
    notice_id: str
    source_url: str
    competition: str
    season: str
    team_id: str
    player_name_raw: str
    official_player_id: str
    target_match_id: str
    target_match_date: str
    target_kickoff_time: str
    target_kickoff_at: str
    schedule_sha256: str
    match_link_status: str
    kickoff_link_status: str
    player_link_status: str
    published_at: str
    updated_at: str
    retrieved_at: str
    evidence_status: str


@dataclass(frozen=True)
class NoticeVersion:
    notice_id: str
    snapshot_ids: tuple[str, ...]
    retrieved_at: tuple[str, ...]
    source_urls: tuple[str, ...]


@dataclass(frozen=True)
class SuspensionRegistryReport:
    physical_snapshots: tuple[PhysicalSuspensionSnapshot, ...]
    evidence_rows: tuple[SuspensionEvidenceRow, ...]
    notice_versions: tuple[NoticeVersion, ...]


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SuspensionRegistryError(f"Cannot read manifest: {path}") from exc
    if not isinstance(value, dict):
        raise SuspensionRegistryError(f"Manifest must be a JSON object: {path}")
    return value


def _utc_timestamp(value, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise SuspensionRegistryError(f"{label} must be a nonblank UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SuspensionRegistryError(f"{label} must be a valid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise SuspensionRegistryError(f"{label} must be UTC")
    return parsed


def _kickoff_timestamp(value, label: str = "target_kickoff_at") -> datetime:
    if not isinstance(value, str) or not value or not value.endswith("+09:00"):
        raise SuspensionRegistryError(f"{label} must be a +09:00 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SuspensionRegistryError(f"{label} must be a valid +09:00 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(hours=9):
        raise SuspensionRegistryError(f"{label} must be a +09:00 timestamp")
    return parsed


def _iso_date(value, label: str) -> date:
    if not isinstance(value, str):
        raise SuspensionRegistryError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise SuspensionRegistryError(f"{label} must be an ISO date") from exc
    if parsed.isoformat() != value:
        raise SuspensionRegistryError(f"{label} must be a canonical ISO date")
    return parsed


def _canonical_notice_id(url) -> str:
    if not isinstance(url, str) or urlsplit(url).query or urlsplit(url).fragment:
        raise SuspensionRegistryError(f"Invalid canonical notice URL: {url!r}")
    match = NOTICE_URL_RE.fullmatch(url)
    if match is None:
        raise SuspensionRegistryError(f"Invalid canonical notice URL: {url!r}")
    return match.group(1)


def _manifest_count(manifest: dict, key: str) -> int:
    value = manifest.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SuspensionRegistryError(f"Manifest {key} must be a nonnegative integer")
    return value


def _audit_raw_pages(
    raw_dir: Path, manifest: dict, source_urls: tuple[str, ...], *, complete: bool
) -> tuple[tuple[str, ...], dict[str, str]]:
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise SuspensionRegistryError(f"{raw_dir.name}: manifest pages must be a list")
    notice_ids = []
    requested_urls = []
    html_names = []
    notice_urls = {}
    for page in pages:
        if not isinstance(page, dict):
            raise SuspensionRegistryError(f"{raw_dir.name}: invalid page record")
        required = {"notice_id", "requested_url", "sha256", "html"}
        if not required <= set(page):
            raise SuspensionRegistryError(f"{raw_dir.name}: incomplete raw page provenance")
        notice_id = page["notice_id"]
        requested_url = page["requested_url"]
        if not isinstance(notice_id, str) or not notice_id:
            raise SuspensionRegistryError(f"{raw_dir.name}: invalid page notice ID")
        if _canonical_notice_id(requested_url) != notice_id:
            raise SuspensionRegistryError(f"{raw_dir.name}: notice ID/URL mismatch")
        if requested_url not in source_urls:
            raise SuspensionRegistryError(f"{raw_dir.name}: page URL outside source_urls")
        if notice_id in notice_ids or requested_url in requested_urls:
            raise SuspensionRegistryError(f"{raw_dir.name}: duplicate manifest notice/page")
        html_name = page["html"]
        if (
            not isinstance(html_name, str)
            or not html_name
            or Path(html_name).name != html_name
            or html_name in html_names
        ):
            raise SuspensionRegistryError(f"{raw_dir.name}: unsafe or duplicate raw HTML name")
        html_path = raw_dir / html_name
        if not html_path.is_file():
            raise SuspensionRegistryError(f"{raw_dir.name}: missing raw page {html_name}")
        body = html_path.read_bytes()
        expected_sha = page["sha256"]
        actual_sha = hashlib.sha256(body).hexdigest()
        if (
            not isinstance(expected_sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha) is None
            or expected_sha != actual_sha
        ):
            raise SuspensionRegistryError(f"{raw_dir.name}: raw SHA-256 mismatch")
        if "response_size" in page:
            size = page["response_size"]
            if isinstance(size, bool) or not isinstance(size, int) or size != len(body):
                raise SuspensionRegistryError(f"{raw_dir.name}: response size mismatch")
        notice_ids.append(notice_id)
        requested_urls.append(requested_url)
        html_names.append(html_name)
        notice_urls[notice_id] = requested_url
    actual_html = {
        path.name for path in raw_dir.glob("notice_*.html") if path.is_file()
    }
    if actual_html != set(html_names):
        raise SuspensionRegistryError(f"{raw_dir.name}: raw page membership mismatch")
    if complete and set(requested_urls) != set(source_urls):
        raise SuspensionRegistryError(f"{raw_dir.name}: COMPLETE source/page mismatch")
    return tuple(notice_ids), notice_urls


def _read_processed(path: Path) -> tuple[tuple[str, ...], list[dict]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            fields = tuple(reader.fieldnames or ())
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise SuspensionRegistryError(f"Cannot read processed snapshot: {path}") from exc
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise SuspensionRegistryError(f"{path.name}: processed row width mismatch")
    return fields, rows


def _schema_generation(
    fields: tuple[str, ...] | None, manifest: dict, *, snapshot_id: str
) -> str:
    present = V2_MANIFEST_FIELDS & set(manifest)
    if present and present != V2_MANIFEST_FIELDS:
        raise SuspensionRegistryError(f"{snapshot_id}: hybrid manifest schema")
    manifest_v2 = present == V2_MANIFEST_FIELDS
    if fields is None:
        return KICKOFF_V2 if manifest_v2 else LEGACY_V1
    if fields == LEGACY_CSV_FIELDS:
        if manifest_v2:
            raise SuspensionRegistryError(f"{snapshot_id}: legacy CSV/new manifest hybrid")
        return LEGACY_V1
    if fields == CSV_FIELDS:
        if not manifest_v2:
            raise SuspensionRegistryError(f"{snapshot_id}: new CSV/legacy manifest hybrid")
        return KICKOFF_V2
    raise SuspensionRegistryError(f"{snapshot_id}: unknown processed schema")


def classify_evidence(row: dict, schema_generation: str) -> str:
    """Classify archived timing evidence, never model or feature eligibility."""
    if schema_generation == LEGACY_V1:
        return "NOT_ASSESSABLE_LEGACY"
    if row.get("match_link_status") != "EXACT":
        return "NOT_ASSESSABLE_MATCH"
    if row.get("kickoff_link_status") != "EXACT":
        return "NOT_ASSESSABLE_KICKOFF"
    try:
        published = _utc_timestamp(row.get("published_at"), "published_at")
        retrieved = _utc_timestamp(row.get("retrieved_at"), "retrieved_at")
        kickoff = _kickoff_timestamp(row.get("target_kickoff_at"))
        updated_raw = row.get("updated_at", "")
        updated = _utc_timestamp(updated_raw, "updated_at") if updated_raw else None
    except SuspensionRegistryError:
        return "INVALID_TIME_PROVENANCE"
    if published > retrieved:
        return "INVALID_TIME_PROVENANCE"
    if updated is not None and (updated < published or updated > retrieved):
        return "INVALID_TIME_PROVENANCE"
    if published >= kickoff:
        return "POST_KICKOFF_PUBLICATION"
    if retrieved >= kickoff:
        return "POST_KICKOFF_RETRIEVAL"
    if updated is not None and updated >= kickoff:
        # With updated <= retrieved this is normally caught by retrieval timing,
        # but retain a conservative guard if the ordering code changes later.
        return "POST_KICKOFF_RETRIEVAL"
    return "PRE_KICKOFF_CONFIRMED"


def _validate_v2(
    rows: list[dict], manifest: dict, *, snapshot_id: str, complete: bool
) -> None:
    schedule_path = manifest.get("schedule_path")
    schedule_sha = manifest.get("schedule_sha256")
    if not isinstance(schedule_path, str) or not schedule_path:
        raise SuspensionRegistryError(f"{snapshot_id}: invalid schedule_path")
    if complete or schedule_sha:
        if not isinstance(schedule_sha, str) or re.fullmatch(r"[0-9a-f]{64}", schedule_sha) is None:
            raise SuspensionRegistryError(f"{snapshot_id}: invalid schedule SHA-256")
    elif schedule_sha != "":
        raise SuspensionRegistryError(f"{snapshot_id}: invalid incomplete schedule SHA-256")
    expected_exact = _manifest_count(manifest, "exact_kickoff_linkage_count")
    expected_unresolved = _manifest_count(manifest, "unresolved_kickoff_count")
    if not complete and (expected_exact or expected_unresolved):
        raise SuspensionRegistryError(f"{snapshot_id}: INCOMPLETE kickoff counts must be zero")
    for row in rows:
        if row["schedule_sha256"] != schedule_sha:
            raise SuspensionRegistryError(f"{snapshot_id}: row/manifest schedule SHA mismatch")
        status = row["kickoff_link_status"]
        if status not in KICKOFF_LINK_STATUSES:
            raise SuspensionRegistryError(f"{snapshot_id}: invalid kickoff linkage status")
        kickoff_at = row["target_kickoff_at"]
        raw_time = row["target_kickoff_time"]
        if status == "EXACT":
            if row["match_link_status"] != "EXACT":
                raise SuspensionRegistryError(f"{snapshot_id}: exact kickoff without exact match")
            if KICKOFF_TIME_RE.fullmatch(raw_time) is None:
                raise SuspensionRegistryError(f"{snapshot_id}: invalid exact kickoff clock")
            parsed_kickoff = _kickoff_timestamp(kickoff_at)
            target_date = _iso_date(row["target_match_date"], "target_match_date")
            hour, minute = (int(part) for part in raw_time.split(":"))
            expected = datetime.combine(
                target_date, datetime_time(hour=hour, minute=minute), tzinfo=JST
            )
            if parsed_kickoff != expected:
                raise SuspensionRegistryError(f"{snapshot_id}: kickoff clock/timestamp mismatch")
        elif kickoff_at:
            raise SuspensionRegistryError(f"{snapshot_id}: unresolved kickoff has timestamp")
        if status == "UNRESOLVED_MISSING" and raw_time != "":
            raise SuspensionRegistryError(f"{snapshot_id}: missing kickoff status has raw time")
        if status == "UNRESOLVED_INVALID" and (
            not raw_time or KICKOFF_TIME_RE.fullmatch(raw_time) is not None
        ):
            raise SuspensionRegistryError(f"{snapshot_id}: invalid kickoff status is inconsistent")
    actual_exact = sum(row["kickoff_link_status"] == "EXACT" for row in rows)
    if actual_exact != expected_exact or len(rows) - actual_exact != expected_unresolved:
        raise SuspensionRegistryError(f"{snapshot_id}: V2 kickoff count mismatch")


def _audit_processed(
    path: Path,
    *,
    manifest: dict,
    notice_urls: dict[str, str],
    fields: tuple[str, ...],
    rows: list[dict],
    schema_generation: str,
) -> tuple[SuspensionEvidenceRow, ...]:
    snapshot_id = manifest["snapshot_id"]
    if len(rows) != _manifest_count(manifest, "processed_target_rows"):
        raise SuspensionRegistryError(f"{snapshot_id}: manifest row count mismatch")
    if {row["snapshot_id"] for row in rows} - {snapshot_id}:
        raise SuspensionRegistryError(f"{snapshot_id}: processed snapshot_id mismatch")
    if {row["retrieved_at"] for row in rows} - {manifest["retrieved_at"]}:
        raise SuspensionRegistryError(f"{snapshot_id}: processed retrieved_at mismatch")
    if any(not row["competition"] for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: blank competition")
    if any(row["season"] != manifest["season"] for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: processed season mismatch")
    if any(row["notice_id"] not in notice_urls for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: processed notice ID not in manifest")
    if any(row["source_url"] != notice_urls[row["notice_id"]] for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: processed source URL mismatch")
    for row in rows:
        _iso_date(row["target_match_date"], "target_match_date")
    identities = [
        (
            row["source_url"],
            row["player_name_raw"],
            row["official_club_name"],
            row["target_match_date"],
            row["target_round"],
        )
        for row in rows
    ]
    if len(identities) != len(set(identities)):
        raise SuspensionRegistryError(f"{snapshot_id}: duplicate source/target row")
    if any(row["team_link_status"] not in {"EXACT", "UNRESOLVED"} for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: invalid team linkage status")
    if any(row["player_link_status"] not in {"EXACT", "UNRESOLVED"} for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: invalid player linkage status")
    if any(row["team_link_status"] == "EXACT" and not row["team_id"] for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: exact team linkage lacks team ID")
    if any(row["match_link_status"] == "EXACT" and not row["target_match_id"] for row in rows):
        raise SuspensionRegistryError(f"{snapshot_id}: exact match linkage lacks match ID")

    expected_counts = {
        "exact_team_linkage_count": sum(row["team_link_status"] == "EXACT" for row in rows),
        "exact_match_linkage_count": sum(row["match_link_status"] == "EXACT" for row in rows),
        "unresolved_match_count": sum(row["match_link_status"] != "EXACT" for row in rows),
        "exact_player_linkage_count": sum(row["player_link_status"] == "EXACT" for row in rows),
    }
    for key, actual in expected_counts.items():
        if _manifest_count(manifest, key) != actual:
            raise SuspensionRegistryError(f"{snapshot_id}: manifest {key} mismatch")
    if schema_generation == KICKOFF_V2:
        _validate_v2(rows, manifest, snapshot_id=snapshot_id, complete=True)

    evidence = []
    for row in rows:
        if schema_generation == LEGACY_V1:
            kickoff_time = kickoff_at = kickoff_status = schedule_sha = ""
        else:
            kickoff_time = row["target_kickoff_time"]
            kickoff_at = row["target_kickoff_at"]
            kickoff_status = row["kickoff_link_status"]
            schedule_sha = row["schedule_sha256"]
        normalized = {
            **row,
            "target_kickoff_time": kickoff_time,
            "target_kickoff_at": kickoff_at,
            "kickoff_link_status": kickoff_status,
            "schedule_sha256": schedule_sha,
        }
        evidence.append(SuspensionEvidenceRow(
            snapshot_id=snapshot_id,
            schema_generation=schema_generation,
            notice_id=row["notice_id"],
            source_url=row["source_url"],
            competition=row["competition"],
            season=row["season"],
            team_id=row["team_id"],
            player_name_raw=row["player_name_raw"],
            official_player_id=row["official_player_id"],
            target_match_id=row["target_match_id"],
            target_match_date=row["target_match_date"],
            target_kickoff_time=kickoff_time,
            target_kickoff_at=kickoff_at,
            schedule_sha256=schedule_sha,
            match_link_status=row["match_link_status"],
            kickoff_link_status=kickoff_status,
            player_link_status=row["player_link_status"],
            published_at=row["published_at"],
            updated_at=row["updated_at"],
            retrieved_at=row["retrieved_at"],
            evidence_status=classify_evidence(normalized, schema_generation),
        ))
    return tuple(evidence)


def audit_snapshot(
    raw_dir: str | Path, *, processed_root: str | Path = PROCESSED_ROOT
) -> tuple[PhysicalSuspensionSnapshot, tuple[SuspensionEvidenceRow, ...]]:
    raw_dir = Path(raw_dir)
    if not raw_dir.is_dir():
        raise SuspensionRegistryError(f"Snapshot directory does not exist: {raw_dir}")
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SuspensionRegistryError(f"{raw_dir.name}: manifest is missing")
    manifest = _read_json(manifest_path)
    snapshot_id = manifest.get("snapshot_id")
    if not isinstance(snapshot_id, str) or snapshot_id != raw_dir.name:
        raise SuspensionRegistryError(f"{raw_dir.name}: manifest snapshot_id mismatch")
    status = manifest.get("status")
    if status not in {"COMPLETE", "INCOMPLETE"}:
        raise SuspensionRegistryError(f"{snapshot_id}: invalid manifest status")
    retrieved_at = manifest.get("retrieved_at")
    _utc_timestamp(retrieved_at, "retrieved_at")
    if manifest.get("season") != SEASON:
        raise SuspensionRegistryError(f"{snapshot_id}: invalid manifest season")
    source_urls_value = manifest.get("source_urls")
    if (
        not isinstance(source_urls_value, list)
        or not source_urls_value
        or any(not isinstance(url, str) for url in source_urls_value)
    ):
        raise SuspensionRegistryError(f"{snapshot_id}: invalid source_urls")
    source_urls = tuple(source_urls_value)
    if len(source_urls) != len(set(source_urls)):
        raise SuspensionRegistryError(f"{snapshot_id}: duplicate source URL")
    for url in source_urls:
        _canonical_notice_id(url)
    notice_ids, notice_urls = _audit_raw_pages(
        raw_dir, manifest, source_urls, complete=status == "COMPLETE"
    )
    if status == "COMPLETE":
        if _manifest_count(manifest, "notice_count") != len(source_urls):
            raise SuspensionRegistryError(f"{snapshot_id}: manifest notice count mismatch")
    output = Path(processed_root) / f"{snapshot_id}.csv"

    if status == "COMPLETE":
        if not output.is_file():
            raise SuspensionRegistryError(f"{snapshot_id}: COMPLETE snapshot lacks processed CSV")
        fields, rows = _read_processed(output)
        generation = _schema_generation(fields, manifest, snapshot_id=snapshot_id)
        evidence = _audit_processed(
            output,
            manifest=manifest,
            notice_urls=notice_urls,
            fields=fields,
            rows=rows,
            schema_generation=generation,
        )
        processed_path = str(output)
        row_count = len(rows)
    else:
        if output.exists():
            raise SuspensionRegistryError(f"{snapshot_id}: INCOMPLETE snapshot has processed CSV")
        generation = _schema_generation(None, manifest, snapshot_id=snapshot_id)
        if generation == KICKOFF_V2:
            _validate_v2([], manifest, snapshot_id=snapshot_id, complete=False)
        evidence = ()
        processed_path = None
        row_count = 0

    exact_team = _manifest_count(manifest, "exact_team_linkage_count") if status == "COMPLETE" else 0
    exact_match = _manifest_count(manifest, "exact_match_linkage_count") if status == "COMPLETE" else 0
    exact_player = _manifest_count(manifest, "exact_player_linkage_count") if status == "COMPLETE" else 0
    exact_kickoff = (
        _manifest_count(manifest, "exact_kickoff_linkage_count")
        if generation == KICKOFF_V2 else None
    )
    schedule_sha = manifest.get("schedule_sha256") if generation == KICKOFF_V2 else None
    physical = PhysicalSuspensionSnapshot(
        snapshot_id=snapshot_id,
        status=status,
        schema_generation=generation,
        retrieved_at=retrieved_at,
        notice_count=len(notice_ids),
        row_count=row_count,
        exact_team_linkage_count=exact_team,
        exact_match_linkage_count=exact_match,
        exact_kickoff_linkage_count=exact_kickoff,
        exact_player_linkage_count=exact_player,
        schedule_sha256=schedule_sha,
        integrity_status="VALID_COMPLETE" if status == "COMPLETE" else "VALID_INCOMPLETE",
        notice_ids=tuple(notice_ids),
        source_urls=tuple(notice_urls[notice_id] for notice_id in notice_ids),
        raw_dir=str(raw_dir),
        processed_path=processed_path,
    )
    return physical, evidence


def _notice_versions(
    physical: tuple[PhysicalSuspensionSnapshot, ...]
) -> tuple[NoticeVersion, ...]:
    observations: dict[str, list[tuple[str, str, str]]] = {}
    for snapshot in physical:
        for notice_id, source_url in zip(snapshot.notice_ids, snapshot.source_urls):
            observations.setdefault(notice_id, []).append(
                (snapshot.retrieved_at, snapshot.snapshot_id, source_url)
            )
    versions = []
    for notice_id, items in observations.items():
        ordered = sorted(items, key=lambda item: (_utc_timestamp(item[0], "retrieved_at"), item[1]))
        versions.append(NoticeVersion(
            notice_id=notice_id,
            snapshot_ids=tuple(item[1] for item in ordered),
            retrieved_at=tuple(item[0] for item in ordered),
            source_urls=tuple(item[2] for item in ordered),
        ))
    return tuple(sorted(versions, key=lambda item: item.notice_id))


def audit_registry(
    *, raw_root: str | Path = RAW_ROOT, processed_root: str | Path = PROCESSED_ROOT
) -> SuspensionRegistryReport:
    """Audit the immutable local archive without reading or writing other data."""
    raw_root = Path(raw_root)
    processed_root = Path(processed_root)
    if not raw_root.is_dir():
        raise SuspensionRegistryError(f"Snapshot raw root does not exist: {raw_root}")
    raw_dirs = tuple(path for path in raw_root.iterdir() if path.is_dir())
    raw_ids = {path.name for path in raw_dirs}
    if processed_root.exists() and not processed_root.is_dir():
        raise SuspensionRegistryError(f"Processed root is not a directory: {processed_root}")
    if processed_root.is_dir():
        orphaned = sorted(
            path.name for path in processed_root.glob("*.csv") if path.stem not in raw_ids
        )
        if orphaned:
            raise SuspensionRegistryError(f"Processed snapshots lack raw directories: {orphaned}")

    audited = [
        audit_snapshot(path, processed_root=processed_root)
        for path in raw_dirs
    ]
    physical = tuple(sorted(
        (item[0] for item in audited),
        key=lambda snapshot: (
            _utc_timestamp(snapshot.retrieved_at, "retrieved_at"), snapshot.snapshot_id
        ),
    ))
    evidence = tuple(sorted(
        (row for _, rows in audited for row in rows),
        key=lambda row: (
            row.target_match_date,
            row.target_match_id,
            row.team_id,
            row.player_name_raw,
            row.notice_id,
            row.snapshot_id,
        ),
    ))
    return SuspensionRegistryReport(
        physical_snapshots=physical,
        evidence_rows=evidence,
        notice_versions=_notice_versions(physical),
    )


def summary_counts(report: SuspensionRegistryReport) -> dict[str, int]:
    physical = report.physical_snapshots
    evidence = report.evidence_rows
    exact_target_ids = {
        row.target_match_id
        for row in evidence
        if row.match_link_status == "EXACT" and row.target_match_id
    }
    return {
        "physical_snapshots": len(physical),
        "complete_snapshots": sum(row.status == "COMPLETE" for row in physical),
        "incomplete_snapshots": sum(row.status == "INCOMPLETE" for row in physical),
        "legacy_v1_snapshots": sum(row.schema_generation == LEGACY_V1 for row in physical),
        "kickoff_v2_snapshots": sum(row.schema_generation == KICKOFF_V2 for row in physical),
        "evidence_rows": len(evidence),
        "exact_match_rows": sum(row.match_link_status == "EXACT" for row in evidence),
        "exact_kickoff_rows": sum(row.kickoff_link_status == "EXACT" for row in evidence),
        "pre_kickoff_confirmed_rows": sum(
            row.evidence_status == "PRE_KICKOFF_CONFIRMED" for row in evidence
        ),
        "not_assessable_legacy_rows": sum(
            row.evidence_status == "NOT_ASSESSABLE_LEGACY" for row in evidence
        ),
        "unresolved_match_rows": sum(row.match_link_status != "EXACT" for row in evidence),
        "unresolved_kickoff_rows": sum(
            row.schema_generation == KICKOFF_V2 and row.kickoff_link_status != "EXACT"
            for row in evidence
        ),
        "unresolved_player_rows": sum(row.player_link_status != "EXACT" for row in evidence),
        "distinct_notice_ids": len(report.notice_versions),
        "distinct_exact_target_match_ids": len(exact_target_ids),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    print(json.dumps(summary_counts(audit_registry()), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
