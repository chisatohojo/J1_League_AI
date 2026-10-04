"""Immutable observations and reviewed result revisions for the ongoing J1 season.

The authoritative publication is ``latest.json`` plus its immutable revision.
Root CSV files are convenient projections; readers needing a consistent set must
use :func:`read_latest`. Nothing here modifies historical season outputs.
"""

from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Sequence
import uuid

import pandas as pd

from src.collect.jleague_ongoing_source import (
    COMPETITION_KEY, COMPLETION_POLICY_VERSION, DATA_SITE_NAMESPACE,
    MATCH_PAGE_NAMESPACE, SOURCE_URL, apply_completion_evidence,
    apply_operational_identity, parse_completion_evidence, parse_listing,
    validate_fixture_coverage,
)
from src.collect.matches import REQUIRED_COLUMNS, validate_matches


FORMAT_VERSION = "ongoing-v2"
LEGACY_FORMAT_VERSION = "ongoing-v1"
COMPLETION_POLICY = COMPLETION_POLICY_VERSION
IDENTITY_BRIDGE_POLICY_VERSION = "official-id-namespace-bridge-v1"
V1_TO_V2_MIGRATION_POLICY_VERSION = "ongoing-v1-to-v2-id-namespace-v1"
FROZEN_V1_REVISION_ID = "71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538"
FROZEN_V1_MANIFEST_SHA256 = "c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34"
FROZEN_V1_OBSERVATIONS_SHA256 = "5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc"
FROZEN_V1_SCHEDULE_SHA256 = "599ad3dad9b30bf440d5e50b9867fd55d796b0a5a7bcc5a9d13a5b44526f1bd0"
PROJECTIONS = (
    "schedule.csv", "completed_matches.csv", "change_log.csv",
    "update_summary.json", "fixture_identity.csv", "identity_bridges.csv", "review.md",
)
EVENT_COLUMNS = (
    "event_id", "comparison", "event_type", "fixture_key", "match_id",
    "previous_snapshot_id", "snapshot_id", "detected_at_utc",
    "changed_fields", "before", "after",
)
_SCORE_FIELDS = ("home_score", "away_score", "result")
_SCHEDULE_FIELDS = ("match_date", "kickoff_time", "stadium", "round")
IDENTITY_BOUND_FIELDS = (
    "fixture_key", "competition_key", "home_club", "away_club", "match_date", "round",
)
OBSERVATION_COLUMNS = (
    "match_id", "season", "round", "match_date", "home_team", "away_team",
    "stadium", "home_score", "away_score", "result", "fixture_key", "status",
    "competition_key", "source_season_label", "source_year_id", "source_frame_id",
    "competition", "stage", "round_label", "round_day", "match_date_label",
    "kickoff_time", "home_club", "away_club", "home_team_source_url",
    "away_team_source_url", "raw_score_text", "attendance_raw", "broadcast_raw",
    "source_url", "listing_source_url", "evidence_url", "evidence_type",
    "evidence_sha256", "completion_origin_snapshot", "evidence_fetched_at_utc",
    "completion_origin_revision", "identity_origin_revision", "match_page_id",
    "data_site_match_id", "match_id_namespace", "match_page_origin_snapshot",
    "match_page_origin_revision", "data_site_origin_snapshot",
    "data_site_origin_revision",
)
BRIDGE_COLUMNS = (
    "bridge_id", "fixture_key", "competition_key", "match_page_id",
    "data_site_match_id", "match_page_evidence_url", "match_page_evidence_type",
    "match_page_evidence_sha256", "match_page_evidence_fetched_at_utc",
    "match_page_origin_snapshot", "match_page_origin_revision",
    "data_site_source_url", "data_site_listing_sha256",
    "data_site_listing_fetched_at_utc", "data_site_origin_snapshot",
    "data_site_origin_revision", "established_snapshot", "established_revision",
    "bridge_policy_version",
)
_SCHEDULED_IDENTITY_URL = re.compile(
    r"https://www\.jleague\.jp/match/j1/(2026|2027)/([0-9]{6})/"
)
_IGNORE_FIELDS = {
    "evidence_url", "evidence_type", "evidence_sha256", "evidence_fetched_at_utc",
    "completion_origin_revision", "completion_origin_snapshot", "identity_origin_revision",
    "match_page_origin_snapshot", "match_page_origin_revision",
    "data_site_origin_snapshot", "data_site_origin_revision",
}
_BRIDGE_EVENT_PROVENANCE_FIELDS = (
    "evidence_url", "evidence_type", "evidence_sha256", "evidence_fetched_at_utc",
    "match_page_origin_snapshot", "match_page_origin_revision",
    "data_site_origin_snapshot", "data_site_origin_revision",
)


def _json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Source timestamps must have an explicit UTC offset.")
    return parsed


def _safe_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value) or ".." in value:
        raise ValueError("Invalid snapshot or revision name.")
    return value


@contextmanager
def _lock(directory: Path, name: str):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    try:
        handle = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise RuntimeError(f"Writer lock already exists: {path}. Inspect it before recovery.") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        path.unlink()


def _write_new(path: Path, body: bytes):
    with path.open("xb") as target:
        target.write(body)
        target.flush()
        os.fsync(target.fileno())


def _source(html: Path, *, listing: bool) -> tuple[bytes, bytes, dict]:
    content = html.read_bytes()
    metadata_bytes = html.with_suffix(".metadata.json").read_bytes()
    metadata = json.loads(metadata_bytes)
    required = {"requested_url", "final_url", "status", "fetched_at_utc", "content_type", "bytes", "sha256"}
    if not required <= metadata.keys():
        raise ValueError(f"Incomplete metadata: {html}")
    _utc(metadata["fetched_at_utc"])
    if type(metadata["status"]) is not int or metadata["status"] != 200:
        raise ValueError("Only successful HTTP 200 observations are accepted.")
    if type(metadata["bytes"]) is not int or metadata["bytes"] != len(content) or metadata["sha256"] != _sha(content):
        raise ValueError(f"Source bytes/SHA-256 mismatch: {html}")
    if "text/html" not in metadata["content_type"].lower():
        raise ValueError("Expected HTML content type.")
    url = metadata["requested_url"]
    if metadata["final_url"] != url:
        raise ValueError("Unexpected source redirect; inspect before accepting.")
    if listing:
        if url != SOURCE_URL:
            raise ValueError("Listing URL does not identify regular 2026/27 J1.")
    elif not re.fullmatch(r"https://www\.jleague\.jp/match/j1/(2026|2027)/[0-9]{6}/", url):
        raise ValueError("Expected an official J1 match summary URL.")
    content.decode("utf-8-sig")
    return content, metadata_bytes, metadata


def create_snapshot(
    raw_root: Path, *, listing_html: Path, evidence_html: Sequence[Path] = (),
    snapshot_id: str | None = None,
) -> Path:
    """Import verified cache files without replacing an earlier observation.

    ``raw_root`` is the season's snapshots directory. Explicit network captures
    use the same function after storing their responses and metadata separately.
    """
    raw_root = Path(raw_root)
    sources = [("listing", Path(listing_html))]
    sources.extend(("evidence", Path(path)) for path in evidence_html)
    inputs, payload, seen_urls = [], {}, set()
    for index, (kind, path) in enumerate(sources):
        content, metadata_bytes, metadata = _source(path, listing=kind == "listing")
        if metadata["requested_url"] in seen_urls:
            raise ValueError("Duplicate evidence URL in snapshot.")
        seen_urls.add(metadata["requested_url"])
        stem = "listing" if kind == "listing" else f"evidence_{index:03d}"
        payload[f"{stem}.html"] = content
        payload[f"{stem}.metadata.json"] = metadata_bytes
        inputs.append({
            "kind": kind, "html": f"{stem}.html", "metadata": f"{stem}.metadata.json",
            "sha256": _sha(content), "metadata_sha256": _sha(metadata_bytes),
            "source_url": metadata["requested_url"], "fetched_at_utc": metadata["fetched_at_utc"],
        })
    fingerprint = _sha(_json(inputs))
    snapshot_id = _safe_name(snapshot_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + uuid.uuid4().hex[:8])
    with _lock(raw_root, ".snapshot.lock"):
        destination = raw_root / snapshot_id
        if destination.exists():
            manifest = _read_snapshot(destination)
            if manifest["input_fingerprint"] != fingerprint:
                raise ValueError("An existing snapshot cannot be overwritten with different inputs.")
            return destination
        previous = []
        for path in raw_root.glob("*/manifest.json"):
            if not path.parent.name.startswith("."):
                previous.append(_read_snapshot(path.parent))
        previous.sort(key=lambda item: item["sequence"])
        last = previous[-1] if previous else None
        manifest = {
            "format_version": FORMAT_VERSION, "competition_key": COMPETITION_KEY,
            "snapshot_id": snapshot_id, "sequence": last["sequence"] + 1 if last else 1,
            "previous_snapshot_id": last["snapshot_id"] if last else None,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "listing_fetched_at_utc": inputs[0]["fetched_at_utc"],
            "observed_at_utc": max((item["fetched_at_utc"] for item in inputs), key=_utc),
            "input_fingerprint": fingerprint, "sources": inputs,
        }
        # A crash leaves a clearly uncommitted directory, never a valid snapshot.
        staging = raw_root / f".pending-{snapshot_id}-{uuid.uuid4().hex}"
        staging.mkdir()
        for name, content in payload.items():
            _write_new(staging / name, content)
        _write_new(staging / "manifest.json", _json(manifest))
        staging.rename(destination)
        return destination


def _read_snapshot(path: Path, *, require_v2: bool = False) -> dict:
    manifest = json.loads((path / "manifest.json").read_bytes())
    version = manifest.get("format_version")
    if (
        manifest["snapshot_id"] != path.name
        or manifest["competition_key"] != COMPETITION_KEY
        or version not in {LEGACY_FORMAT_VERSION, FORMAT_VERSION}
        or (require_v2 and version != FORMAT_VERSION)
    ):
        raise ValueError("Snapshot identity or format mismatch.")
    if _sha(_json(manifest["sources"])) != manifest["input_fingerprint"]:
        raise ValueError("Snapshot input fingerprint mismatch.")
    if not manifest["sources"] or manifest["sources"][0]["kind"] != "listing":
        raise ValueError("Snapshot has no listing.")
    for index, entry in enumerate(manifest["sources"]):
        if entry["kind"] != ("listing" if index == 0 else "evidence"):
            raise ValueError("Unexpected snapshot source order.")
        html = path / _safe_name(entry["html"])
        if entry["metadata"] != html.with_suffix(".metadata.json").name:
            raise ValueError("Snapshot metadata filename mismatch.")
        content, metadata_bytes, metadata = _source(html, listing=index == 0)
        if _sha(content) != entry["sha256"] or _sha(metadata_bytes) != entry["metadata_sha256"]:
            raise ValueError("Snapshot source digest mismatch.")
        if entry["source_url"] != metadata["requested_url"] or entry["fetched_at_utc"] != metadata["fetched_at_utc"]:
            raise ValueError("Snapshot source metadata mismatch.")
    if manifest["listing_fetched_at_utc"] != manifest["sources"][0]["fetched_at_utc"]:
        raise ValueError("Snapshot listing timestamp mismatch.")
    if manifest["observed_at_utc"] != max((entry["fetched_at_utc"] for entry in manifest["sources"]), key=_utc):
        raise ValueError("Snapshot observation timestamp mismatch.")
    return manifest


def _parse_snapshot(path: Path, manifest: dict) -> list[dict]:
    if manifest.get("format_version") != FORMAT_VERSION:
        raise ValueError("An unprocessed ongoing-v1 snapshot cannot create a new revision.")
    listing = manifest["sources"][0]
    records = parse_listing(
        (path / listing["html"]).read_text(encoding="utf-8-sig"),
        enforce_unique_ids=False,
    )
    evidence = []
    for source in manifest["sources"][1:]:
        item = parse_completion_evidence(
            (path / source["html"]).read_text(encoding="utf-8-sig"), source_url=source["source_url"],
        )
        item["evidence_sha256"] = source["sha256"]
        item["evidence_fetched_at_utc"] = source["fetched_at_utc"]
        evidence.append(item)
    result = apply_completion_evidence(records, evidence, enforce_unique_ids=False)
    by_key = {item["fixture_key"]: item for item in evidence}
    for record in result:
        record["data_site_origin_snapshot"] = (
            manifest["snapshot_id"] if record.get("data_site_match_id") else None
        )
        if record["status"] == "completed":
            proof = by_key[record["fixture_key"]]
            record["evidence_sha256"] = proof["evidence_sha256"]
            record["evidence_fetched_at_utc"] = proof["evidence_fetched_at_utc"]
            record["completion_origin_snapshot"] = manifest["snapshot_id"]
        proof = by_key.get(record["fixture_key"])
        if proof:
            record["evidence_sha256"] = proof["evidence_sha256"]
            record["evidence_fetched_at_utc"] = proof["evidence_fetched_at_utc"]
            record["match_page_origin_snapshot"] = manifest["snapshot_id"]
    return result


def _csv(records: list[dict], columns: Sequence[str]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({key: json.dumps(record.get(key), ensure_ascii=False, sort_keys=True) if isinstance(record.get(key), (dict, list)) else record.get(key) for key in columns})
    return stream.getvalue().encode("utf-8")


def _semantic(record: dict | None) -> dict | None:
    return {key: value for key, value in record.items() if key not in _IGNORE_FIELDS} if record is not None else None


def _event_semantic(record: dict | None, event_type: str) -> dict | None:
    value = _semantic(record)
    if value is not None and event_type in {
        "identity_bridge_established", "identity_namespace_transition",
    }:
        value.update({field: record.get(field) for field in _BRIDGE_EVENT_PROVENANCE_FIELDS})
    return value


def _carry_forward_scheduled_identity(
    previous: list[dict], current: list[dict], *, explicit_keys: set[str],
    previous_revision_id: str | None,
) -> None:
    """Retain only a previously verified, unchanged scheduled identity.

    This never derives an ID from fixture data. It reuses an immutable accepted
    official-page provenance only when every field bound by that evidence is
    unchanged and no current source has assigned the ID to another fixture.
    """
    before = {row["fixture_key"]: row for row in previous}
    current_ids = {
        row["match_id"]: row["fixture_key"] for row in current if row.get("match_id")
    }
    for row in current:
        old = before.get(row["fixture_key"])
        if (
            old is None
            or row["fixture_key"] in explicit_keys
            or row.get("status") not in {"scheduled", "candidate"}
            or row.get("match_page_id") not in (None, "")
            or old.get("status") != "scheduled"
            or not isinstance(old.get("match_page_id"), str)
            or not old["match_page_id"]
            or old.get("evidence_type") != "official_completion_unconfirmed"
        ):
            continue
        match = _SCHEDULED_IDENTITY_URL.fullmatch(old.get("evidence_url") or "")
        if (
            match is None
            or match[2] != old["match_page_id"]
            or any(old.get(field) != row.get(field) for field in IDENTITY_BOUND_FIELDS)
            or (
                old["match_page_id"] in current_ids
                and current_ids[old["match_page_id"]] != row["fixture_key"]
            )
        ):
            continue
        row["match_page_id"] = old["match_page_id"]
        row["evidence_url"] = old["evidence_url"]
        row["evidence_type"] = old["evidence_type"]
        origin = old.get("identity_origin_revision") or previous_revision_id
        if origin:
            row["identity_origin_revision"] = origin
        row["match_page_origin_snapshot"] = old.get("match_page_origin_snapshot") or old.get("completion_origin_snapshot")
        row["match_page_origin_revision"] = old.get("match_page_origin_revision") or origin
        row["evidence_sha256"] = old.get("evidence_sha256")
        row["evidence_fetched_at_utc"] = old.get("evidence_fetched_at_utc")
        apply_operational_identity(row)
        current_ids[row["match_page_id"]] = row["fixture_key"]


def _bridge_id(row: dict) -> str:
    return _sha(_json({key: row[key] for key in (
        "competition_key", "fixture_key", "match_page_id", "data_site_match_id",
        "match_page_origin_revision", "data_site_origin_revision", "bridge_policy_version",
    )}))


def _bridge_from_record(record: dict, *, snapshot_id: str, revision_id: str, listing: dict) -> dict:
    if not record.get("match_page_id") or not record.get("data_site_match_id"):
        raise ValueError("A bridge requires both typed identifiers.")
    row = {
        "fixture_key": record["fixture_key"], "competition_key": record["competition_key"],
        "match_page_id": record["match_page_id"], "data_site_match_id": record["data_site_match_id"],
        "match_page_evidence_url": record.get("evidence_url"),
        "match_page_evidence_type": record.get("evidence_type"),
        "match_page_evidence_sha256": record.get("evidence_sha256"),
        "match_page_evidence_fetched_at_utc": record.get("evidence_fetched_at_utc"),
        "match_page_origin_snapshot": record.get("match_page_origin_snapshot"),
        "match_page_origin_revision": record.get("match_page_origin_revision"),
        "data_site_source_url": record.get("source_url"),
        "data_site_listing_sha256": listing.get("sha256"),
        "data_site_listing_fetched_at_utc": listing.get("fetched_at_utc"),
        "data_site_origin_snapshot": record.get("data_site_origin_snapshot"),
        "data_site_origin_revision": record.get("data_site_origin_revision"),
        "established_snapshot": snapshot_id, "established_revision": revision_id,
        "bridge_policy_version": IDENTITY_BRIDGE_POLICY_VERSION,
    }
    if any(row.get(column) in (None, "") for column in BRIDGE_COLUMNS if column != "bridge_id"):
        raise ValueError("Identity bridge provenance is incomplete.")
    row["bridge_id"] = _bridge_id(row)
    return {column: row[column] for column in BRIDGE_COLUMNS}


def _validate_typed_identities(records: list[dict]) -> None:
    page, data, operational = {}, {}, {}
    for row in records:
        apply_operational_identity(row)
        for field, values in (("match_page_id", page), ("data_site_match_id", data)):
            value = row.get(field)
            if value:
                if value in values and values[value] != row["fixture_key"]:
                    raise ValueError(f"Duplicate {field} across fixtures.")
                values[value] = row["fixture_key"]
        value = row.get("match_id")
        if value:
            if value in operational and operational[value] != row["fixture_key"]:
                raise ValueError("Duplicate operational match_id across fixtures.")
            operational[value] = row["fixture_key"]


def _hydrate_accepted_bridges(
    records: list[dict], bridges: list[dict], previous_records: list[dict],
) -> list[str]:
    """Hydrate immutable bridge state; return fixture keys with conflicts."""
    by_key = {row["fixture_key"]: row for row in records}
    previous_by_key = {row["fixture_key"]: row for row in previous_records}
    conflicts = []
    for bridge in bridges:
        row = by_key.get(bridge["fixture_key"])
        old = previous_by_key.get(bridge["fixture_key"])
        if row is None or old is None or any(
            row.get(field) != old.get(field) for field in IDENTITY_BOUND_FIELDS
        ):
            conflicts.append(bridge["fixture_key"])
            continue
        current_page, current_data = row.get("match_page_id"), row.get("data_site_match_id")
        if current_page not in (None, bridge["match_page_id"]) or current_data not in (None, bridge["data_site_match_id"]):
            conflicts.append(bridge["fixture_key"])
            continue
        row["match_page_id"] = bridge["match_page_id"]
        row["data_site_match_id"] = bridge["data_site_match_id"]
        row["evidence_url"] = bridge["match_page_evidence_url"]
        row["evidence_type"] = bridge["match_page_evidence_type"]
        row["evidence_sha256"] = bridge["match_page_evidence_sha256"]
        row["evidence_fetched_at_utc"] = bridge["match_page_evidence_fetched_at_utc"]
        row["match_page_origin_snapshot"] = bridge["match_page_origin_snapshot"]
        row["match_page_origin_revision"] = bridge["match_page_origin_revision"]
        row["data_site_origin_snapshot"] = bridge["data_site_origin_snapshot"]
        row["data_site_origin_revision"] = bridge["data_site_origin_revision"]
        apply_operational_identity(row)
    return conflicts


def _accepted_v1_history(output_dir: Path, baseline_sequence: int) -> list[tuple[Path, dict, list[dict]]]:
    history = []
    for manifest_path in (output_dir / "revisions").glob("*/manifest.json"):
        manifest = _read_revision(manifest_path.parent)
        if (
            manifest.get("format_version") == LEGACY_FORMAT_VERSION
            and manifest.get("sequence", 0) <= baseline_sequence
            and manifest.get("summary", {}).get("publication_status") == "published"
        ):
            history.append((manifest_path.parent, manifest, json.loads((manifest_path.parent / "observations.json").read_bytes())))
    return sorted(history, key=lambda item: (item[1]["sequence"], item[0].name))


def migrate_v1_to_v2(
    previous_revision: Path,
    output_dir: Path,
    *,
    established_snapshot: str,
    established_revision: str,
    enforce_frozen_baseline: bool = True,
) -> tuple[list[dict], list[dict], dict]:
    """Pure offline typed-ID migration over accepted immutable v1 history."""
    previous_revision, output_dir = Path(previous_revision), Path(output_dir)
    manifest_bytes = (previous_revision / "manifest.json").read_bytes()
    manifest = _read_revision(previous_revision)
    observations_bytes = (previous_revision / "observations.json").read_bytes()
    schedule_bytes = (previous_revision / "schedule.csv").read_bytes()
    if manifest.get("format_version") != LEGACY_FORMAT_VERSION:
        raise ValueError("Migration source is not ongoing-v1.")
    if enforce_frozen_baseline and (
        previous_revision.name != FROZEN_V1_REVISION_ID
        or _sha(manifest_bytes) != FROZEN_V1_MANIFEST_SHA256
        or _sha(observations_bytes) != FROZEN_V1_OBSERVATIONS_SHA256
        or _sha(schedule_bytes) != FROZEN_V1_SCHEDULE_SHA256
        or manifest.get("sequence") != 8
    ):
        raise ValueError("Latest accepted v1 state is not the frozen migration baseline.")
    legacy = json.loads(observations_bytes)
    history = _accepted_v1_history(output_dir, manifest["sequence"])
    explicit_page, explicit_data = {}, {}
    for revision_path, revision_manifest, rows in history:
        sources = revision_manifest.get("summary", {}).get("sources", revision_manifest.get("sources", []))
        source_by_url = {item.get("source_url"): item for item in sources}
        for row in rows:
            key = row["fixture_key"]
            page_url = row.get("evidence_url") or ""
            page_match = _SCHEDULED_IDENTITY_URL.fullmatch(page_url)
            page_source = source_by_url.get(page_url)
            if page_match and page_source and (
                row.get("status") != "scheduled" or row.get("match_id") == page_match[2]
            ):
                explicit_page.setdefault((key, page_match[2]), (
                    row, page_source, revision_manifest["snapshot_id"], revision_path.name,
                ))
            data_match = re.fullmatch(
                r"https://data\.j-league\.or\.jp/SFMS02/\?match_card_id=([1-9][0-9]*)",
                row.get("source_url") or "",
            )
            listing = next((item for item in sources if item.get("kind") == "listing"), None)
            if data_match and listing and row.get("match_id") == data_match[1]:
                explicit_data.setdefault((key, data_match[1]), (
                    row, listing, revision_manifest["snapshot_id"], revision_path.name,
                ))
    migrated = []
    for old in legacy:
        row = {column: old.get(column) for column in OBSERVATION_COLUMNS}
        row.update({key: value for key, value in old.items() if key in OBSERVATION_COLUMNS})
        row.update({
            "match_page_id": None, "data_site_match_id": None,
            "match_id_namespace": None, "match_page_origin_snapshot": None,
            "match_page_origin_revision": None, "data_site_origin_snapshot": None,
            "data_site_origin_revision": None,
        })
        data_match = re.fullmatch(
            r"https://data\.j-league\.or\.jp/SFMS02/\?match_card_id=([1-9][0-9]*)",
            old.get("source_url") or "",
        )
        page_match = _SCHEDULED_IDENTITY_URL.fullmatch(old.get("evidence_url") or "")
        if data_match and old.get("match_id") == data_match[1]:
            origin = explicit_data.get((old["fixture_key"], data_match[1]))
            if origin is None:
                raise ValueError("Data Site identity origin is not recoverable from accepted v1 history.")
            row["data_site_match_id"] = data_match[1]
            row["data_site_origin_snapshot"], row["data_site_origin_revision"] = origin[2], origin[3]
        if page_match:
            if old.get("status") == "scheduled" and old.get("match_id") != page_match[2]:
                raise ValueError("Scheduled v1 page identity conflicts with its evidence URL.")
            origin = explicit_page.get((old["fixture_key"], page_match[2]))
            if origin is None:
                raise ValueError("Match-page identity origin is not recoverable from accepted v1 history.")
            source_row, source, origin_snapshot, origin_revision = origin
            if any(source_row.get(field) != old.get(field) for field in IDENTITY_BOUND_FIELDS):
                raise ValueError("Match-page identity-bound fields are ambiguous in v1 history.")
            row["match_page_id"] = page_match[2]
            row["match_page_origin_snapshot"] = origin_snapshot
            row["match_page_origin_revision"] = origin_revision
            row["evidence_sha256"] = source["sha256"]
            row["evidence_fetched_at_utc"] = source["fetched_at_utc"]
        apply_operational_identity(row)
        migrated.append(row)
    _validate_typed_identities(migrated)
    completed_both = [row for row in migrated if row["status"] == "completed" and row.get("match_page_id") and row.get("data_site_match_id")]
    scheduled_page = [row for row in migrated if row["status"] == "scheduled" and row.get("match_page_id") and not row.get("data_site_match_id")]
    scheduled_blank = [row for row in migrated if row["status"] == "scheduled" and not row.get("match_page_id") and not row.get("data_site_match_id")]
    expected = (80, 7, 293) if enforce_frozen_baseline else (len(completed_both), len(scheduled_page), len(scheduled_blank))
    if (len(completed_both), len(scheduled_page), len(scheduled_blank)) != expected:
        raise ValueError("Migrated v1 identity classification mismatch.")
    if any(row["match_page_id"] == row["data_site_match_id"] for row in completed_both):
        raise ValueError("Frozen completed namespace IDs must all differ.")
    bridges = [
        _bridge_from_record(
            row, snapshot_id=established_snapshot, revision_id=established_revision,
            listing=explicit_data[(row["fixture_key"], row["data_site_match_id"])][1],
        )
        for row in completed_both
    ]
    migration = {
        "policy_version": V1_TO_V2_MIGRATION_POLICY_VERSION,
        "source_revision_id": previous_revision.name,
        "source_manifest_sha256": _sha(manifest_bytes),
        "source_observations_sha256": _sha(observations_bytes),
        "source_row_count": len(migrated), "migrated_bridge_count": len(bridges),
        "migrated_match_page_only_count": len(scheduled_page),
    }
    return migrated, sorted(bridges, key=lambda row: row["fixture_key"]), migration


def _changes(
    previous: list[dict], current: list[dict], *, comparison: str,
    previous_snapshot_id: str | None, manifest: dict,
    newly_bridged: set[str] | None = None,
    bridged_fixtures: set[str] | None = None,
) -> list[dict]:
    newly_bridged = newly_bridged or set()
    bridged_fixtures = bridged_fixtures or set()
    before, after = ({row["fixture_key"]: row for row in rows} for rows in (previous, current))
    events = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        types = []
        if old is None:
            types.append("new_fixture")
            if key in newly_bridged:
                types.append("identity_bridge_established")
            if new["home_score"] is not None:
                types.append("result_candidate")
            if new["status"] == "completed":
                types.append("completed")
        elif new is None:
            types.append("missing_from_snapshot")
        else:
            if any(old.get(field) != new.get(field) for field in _SCHEDULE_FIELDS):
                types.append("schedule_changed")
            if key in newly_bridged:
                types.append("identity_bridge_established")
            namespace_transition = (
                key in bridged_fixtures
                and
                old.get("match_id_namespace") == MATCH_PAGE_NAMESPACE
                and new.get("match_id_namespace") == DATA_SITE_NAMESPACE
            )
            if namespace_transition:
                types.append("identity_namespace_transition")
            if old.get("match_id") != new.get("match_id") and not namespace_transition:
                types.append("identity_linked" if old.get("match_id") is None and new.get("match_id") else "identity_conflict")
            if any(old.get(field) != new.get(field) for field in _SCORE_FIELDS):
                types.append("result_corrected" if old["status"] == "completed" else "result_candidate")
            if old["status"] != "completed" and new["status"] == "completed":
                types.append("completed")
            if old["status"] == "completed" and new["status"] != "completed":
                types.append("completion_unconfirmed")
            if not types and _semantic(old) != _semantic(new):
                types.append("metadata_changed")
        for event_type in types:
            old_value, new_value = _event_semantic(old, event_type), _event_semantic(new, event_type)
            changed = sorted(
                field for field in (old_value or {}).keys() | (new_value or {}).keys()
                if (old_value or {}).get(field) != (new_value or {}).get(field)
            )
            event = {
                "comparison": comparison, "event_type": event_type, "fixture_key": key,
                "match_id": (new or old).get("match_id"),
                "previous_snapshot_id": previous_snapshot_id, "snapshot_id": manifest["snapshot_id"],
                "detected_at_utc": manifest["observed_at_utc"], "changed_fields": changed,
                "before": old_value, "after": new_value,
            }
            event["event_id"] = _sha(_json(event))
            events.append(event)
    return events


def _read_revision(path: Path) -> dict:
    manifest = json.loads((path / "manifest.json").read_bytes())
    if manifest.get("format_version") not in {LEGACY_FORMAT_VERSION, FORMAT_VERSION}:
        raise ValueError("Unsupported revision format version.")
    for name, digest in manifest["files"].items():
        if _sha((path / _safe_name(name)).read_bytes()) != digest:
            raise ValueError(f"Revision artifact was modified: {path / name}")
    return manifest


def read_latest(output_dir: Path) -> tuple[Path, dict] | None:
    """Resolve and verify one complete immutable revision, ignoring CSV projections."""
    output_dir = Path(output_dir)
    pointer_path = output_dir / "latest.json"
    if not pointer_path.exists():
        return None
    pointer = json.loads(pointer_path.read_bytes())
    revision = output_dir / "revisions" / _safe_name(pointer["revision_id"])
    if _sha((revision / "manifest.json").read_bytes()) != pointer["manifest_sha256"]:
        raise ValueError("Published manifest digest mismatch.")
    manifest = _read_revision(revision)
    if manifest["summary"]["publication_status"] != "published":
        raise ValueError("Latest pointer references an unaccepted revision.")
    return revision, manifest


def _replace_latest(path: Path, content: bytes):
    temporary = path.with_name(f".{path.name}-{uuid.uuid4().hex}.tmp")
    _write_new(temporary, content)
    os.replace(temporary, path)


def _publish(output_dir: Path, revision_dir: Path, pointer: dict):
    # The pointer commits the entire revision atomically. Projections are for
    # humans and may be repaired by replay after an interrupted process.
    backups = {name: (output_dir / name).read_bytes() if (output_dir / name).exists() else None for name in PROJECTIONS}
    try:
        for name in PROJECTIONS:
            _replace_latest(output_dir / name, (revision_dir / name).read_bytes())
        _replace_latest(output_dir / "latest.json", _json(pointer))
    except BaseException:
        for name, content in backups.items():
            path = output_dir / name
            if content is None:
                path.unlink(missing_ok=True)
            else:
                # Do not use the fault-injection boundary while restoring.
                temporary = output_dir / f".restore-{uuid.uuid4().hex}"
                _write_new(temporary, content)
                os.replace(temporary, path)
        raise


def _review(summary: dict, records: list[dict]) -> bytes:
    lines = [
        "# 2026/27 J1 更新レビュー", "",
        f"- Snapshot: `{summary['snapshot_id']}`",
        f"- Listing observed (UTC): {summary['listing_fetched_at_utc']}",
        f"- Evidence observed through (UTC): {summary['observed_at_utc']}",
        f"- Publication: {summary['publication_status']}",
        f"- Scheduled / candidate / completed: {summary['counts']['scheduled']} / {summary['counts']['candidate']} / {summary['counts']['completed']}",
        f"- Result validation: {summary['result_validation']}",
        "- Completed requires the official match page's explicit game-over section, with fixture/date/round/scores checked.",
        "- Candidate scores are observations, not final results. Scheduled dates/KO may be provisional.",
        "- Read latest.json and its immutable revision for a consistent publication.", "",
        "## Publication blocks", "", *[f"- {value}" for value in summary['publication_blocks']], "",
        "## Verified completed matches", "",
        "| match_id | date | home | score | away | evidence |", "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in records:
        if row["status"] == "completed":
            lines.append(f"| {row['match_id']} | {row['match_date']} | {row['home_team']} | {row['home_score']}-{row['away_score']} | {row['away_team']} | {row.get('evidence_url', '')} |")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _validate_frozen_v1_boundary(revision: Path, manifest: dict) -> None:
    if (
        revision.name != FROZEN_V1_REVISION_ID
        or _sha((revision / "manifest.json").read_bytes()) != FROZEN_V1_MANIFEST_SHA256
        or _sha((revision / "observations.json").read_bytes()) != FROZEN_V1_OBSERVATIONS_SHA256
        or _sha((revision / "schedule.csv").read_bytes()) != FROZEN_V1_SCHEDULE_SHA256
        or manifest.get("sequence") != 8
        or manifest.get("summary", {}).get("total_fixtures") != 380
    ):
        raise ValueError("Latest accepted v1 state is not the frozen migration baseline.")


def _prediction_binding_gate(
    affected: set[str], *, binding_path: Path | None,
    repository_root: Path | None = None,
    prediction_artifacts: Sequence[str] | None = None,
) -> tuple[str, str | None]:
    predicted = {
        "j1_2026_2027:kashima:gosaka", "j1_2026_2027:kashiwa:kobe",
    }
    if binding_path is not None and binding_path.is_file():
        try:
            from src.modeling.prediction_identity import read_prediction_bindings
            predicted.update(read_prediction_bindings(binding_path)["fixture_key"])
        except Exception:
            try:
                raw = pd.read_csv(binding_path, dtype=str, keep_default_na=False)
                predicted.update(raw.get("fixture_key", pd.Series(dtype=str)))
            except Exception:
                pass
    if not affected & predicted:
        return "NOT_REQUIRED", None
    if binding_path is None or not binding_path.is_file():
        return "MISSING", "Prediction fixture binding sidecar is required for this identity transition."
    try:
        from src.modeling.prediction_identity import (
            FROZEN_PREDICTIONS, validate_complete_sidecar,
        )
        bindings = validate_complete_sidecar(
            repository_root=repository_root or Path(__file__).resolve().parents[2],
            binding_path=binding_path,
            prediction_artifacts=(
                tuple(prediction_artifacts) if prediction_artifacts is not None
                else tuple(FROZEN_PREDICTIONS)
            ),
        )
        if not predicted <= set(bindings["fixture_key"]):
            raise ValueError("Frozen predicted fixtures are not fully bound.")
    except Exception as exc:
        return "INVALID", f"Prediction fixture binding sidecar is invalid: {exc}"
    return "VALID", None


def process_snapshot(
    snapshot_dir: Path, output_dir: Path, *,
    prediction_binding_path: Path | None = None,
    prediction_repository_root: Path | None = None,
    prediction_artifacts: Sequence[str] | None = None,
) -> dict:
    """Validate and publish a snapshot, or keep a held revision with diagnostics.

    Parse/integrity failures raise and leave latest unchanged. Missing fixtures,
    identity conflicts and unverified corrections produce a held revision whose
    before/after events remain available for review and later recovery.
    """
    snapshot_dir, output_dir = Path(snapshot_dir), Path(output_dir)
    with _lock(output_dir, ".update.lock"):
        manifest = _read_snapshot(snapshot_dir)
        if manifest["format_version"] == LEGACY_FORMAT_VERSION:
            legacy_run_path = output_dir / "runs" / f"{manifest['snapshot_id']}-{LEGACY_FORMAT_VERSION}.json"
            if not legacy_run_path.is_file():
                raise ValueError("An unprocessed ongoing-v1 snapshot cannot create a new revision.")
            legacy_run = json.loads(legacy_run_path.read_bytes())
            if legacy_run.get("snapshot_sha256") != _sha((snapshot_dir / "manifest.json").read_bytes()):
                raise ValueError("Legacy snapshot changed after its processing run.")
            legacy_revision = output_dir / "revisions" / _sha(_json(legacy_run))
            if not legacy_revision.is_dir():
                raise ValueError("An unprocessed ongoing-v1 snapshot cannot create a new revision.")
            return _read_revision(legacy_revision)["summary"]
        latest = read_latest(output_dir)
        latest_id = latest[0].name if latest else None
        if latest and latest[1]["format_version"] == LEGACY_FORMAT_VERSION:
            _validate_frozen_v1_boundary(latest[0], latest[1])
        runs = output_dir / "runs"
        runs.mkdir(exist_ok=True)
        run_path = runs / f"{manifest['snapshot_id']}-{FORMAT_VERSION}.json"
        if run_path.exists():
            run = json.loads(run_path.read_bytes())
            if run["snapshot_sha256"] != _sha((snapshot_dir / "manifest.json").read_bytes()):
                raise ValueError("Snapshot changed after its first processing attempt.")
        else:
            run = {
                "snapshot_id": manifest["snapshot_id"],
                "snapshot_sha256": _sha((snapshot_dir / "manifest.json").read_bytes()),
                "format_version": FORMAT_VERSION, "completion_policy": COMPLETION_POLICY,
                "identity_bridge_policy": IDENTITY_BRIDGE_POLICY_VERSION,
                "previous_accepted_revision_id": latest_id,
            }
            _write_new(run_path, _json(run))
        revision_id = _sha(_json(run))
        revision = output_dir / "revisions" / revision_id
        pointer = {"revision_id": revision_id}
        if revision.exists():
            existing = _read_revision(revision)
            pointer["manifest_sha256"] = _sha((revision / "manifest.json").read_bytes())
            # Same-input replay repairs projections but never rolls back latest.
            if existing["summary"]["publication_status"] == "published" and latest_id in {revision_id, run["previous_accepted_revision_id"]}:
                _publish(output_dir, revision, pointer)
            return existing["summary"]
        previous_revision = None
        previous_records = []
        previous_bridges = []
        migration = None
        if run["previous_accepted_revision_id"]:
            previous_revision = output_dir / "revisions" / _safe_name(run["previous_accepted_revision_id"])
            previous_manifest = _read_revision(previous_revision)
            if previous_manifest.get("completion_policy") != COMPLETION_POLICY:
                raise ValueError("Parser/policy changes need a separate migration, not a source correction.")
            if previous_manifest["format_version"] == LEGACY_FORMAT_VERSION:
                previous_records, previous_bridges, migration = migrate_v1_to_v2(
                    previous_revision, output_dir,
                    established_snapshot=manifest["snapshot_id"],
                    established_revision=revision_id,
                )
            elif previous_manifest["format_version"] == FORMAT_VERSION:
                previous_records = json.loads((previous_revision / "observations.json").read_bytes())
                previous_bridges = list(csv.DictReader(
                    io.StringIO((previous_revision / "identity_bridges.csv").read_text(encoding="utf-8"))
                ))
            else:
                raise ValueError("A v2 revision cannot roll back to an unsupported predecessor.")
        try:
            current = _parse_snapshot(snapshot_dir, manifest)
            raw_data_by_key = {row["fixture_key"]: row.get("data_site_match_id") for row in current}
            old_by_key = {row["fixture_key"]: row for row in previous_records}
            explicit_keys = set()
            for source in manifest["sources"][1:]:
                proof = parse_completion_evidence((snapshot_dir / source["html"]).read_text(encoding="utf-8-sig"), source_url=source["source_url"])
                explicit_keys.add(proof["fixture_key"])
            for row in current:
                if row.get("data_site_match_id"):
                    row["data_site_origin_revision"] = revision_id
                if row["fixture_key"] in explicit_keys:
                    row["match_page_origin_revision"] = revision_id
                    row["identity_origin_revision"] = revision_id
            bridge_conflicts = []
            for field in ("match_page_id", "data_site_match_id"):
                owners = {}
                for row in current:
                    if row.get(field):
                        owners.setdefault(row[field], []).append(row["fixture_key"])
                bridge_conflicts.extend(
                    key for keys in owners.values() if len(keys) > 1 for key in keys
                )
            bridge_conflicts.extend(
                _hydrate_accepted_bridges(current, previous_bridges, previous_records)
            )
            _carry_forward_scheduled_identity(
                previous_records, current, explicit_keys=explicit_keys,
                previous_revision_id=previous_revision.name if previous_revision else None,
            )
            for field in ("match_page_id", "data_site_match_id"):
                owners = {}
                for row in current:
                    if row.get(field):
                        owners.setdefault(row[field], []).append(row["fixture_key"])
                bridge_conflicts.extend(
                    key for keys in owners.values() if len(keys) > 1 for key in keys
                )
            existing_bridge_by_key = {row["fixture_key"]: row for row in previous_bridges}
            established = []
            bridge_identity_owners = {
                (namespace, bridge[field]): bridge["fixture_key"]
                for bridge in previous_bridges
                for namespace, field in (
                    (MATCH_PAGE_NAMESPACE, "match_page_id"),
                    (DATA_SITE_NAMESPACE, "data_site_match_id"),
                )
            }
            for row in current:
                if row["fixture_key"] in bridge_conflicts:
                    continue
                if row["fixture_key"] in existing_bridge_by_key:
                    continue
                if not (row.get("match_page_id") and row.get("data_site_match_id")):
                    continue
                old = old_by_key.get(row["fixture_key"])
                page_is_valid = row["fixture_key"] in explicit_keys or (
                    old is not None
                    and old.get("status") == "scheduled"
                    and old.get("match_page_id") == row.get("match_page_id")
                    and all(old.get(field) == row.get(field) for field in IDENTITY_BOUND_FIELDS)
                )
                reused = any(
                    bridge_identity_owners.get((namespace, row[field])) not in (None, row["fixture_key"])
                    for namespace, field in (
                        (MATCH_PAGE_NAMESPACE, "match_page_id"),
                        (DATA_SITE_NAMESPACE, "data_site_match_id"),
                    )
                )
                old_page_conflict = old and old.get("match_page_id") not in (None, row["match_page_id"])
                if (
                    not page_is_valid or raw_data_by_key[row["fixture_key"]] != row["data_site_match_id"]
                    or reused or old_page_conflict
                ):
                    bridge_conflicts.append(row["fixture_key"])
                    continue
                try:
                    established.append(_bridge_from_record(
                        row, snapshot_id=manifest["snapshot_id"], revision_id=revision_id,
                        listing=manifest["sources"][0],
                    ))
                except ValueError:
                    bridge_conflicts.append(row["fixture_key"])
                    continue
                bridge_identity_owners[(MATCH_PAGE_NAMESPACE, row["match_page_id"])] = row["fixture_key"]
                bridge_identity_owners[(DATA_SITE_NAMESPACE, row["data_site_match_id"])] = row["fixture_key"]
            bridges = sorted([*previous_bridges, *established], key=lambda row: row["fixture_key"])
            newly_bridged = {row["fixture_key"] for row in established}
            bridged_fixtures = {
                row["fixture_key"] for row in bridges
                if row["fixture_key"] not in set(bridge_conflicts)
            }
            # A verified finish may be retained only for identical results and
            # identity. A changed score/date requires fresh matching proof.
            for row in current:
                old = old_by_key.get(row["fixture_key"])
                if old and old["status"] == "completed" and row["status"] == "candidate" and row["fixture_key"] not in explicit_keys:
                    if all(old.get(field) == row.get(field) for field in (*_SCORE_FIELDS, "data_site_match_id", "match_date", "round")):
                        row["status"] = "completed"
                        for field in _IGNORE_FIELDS:
                            if field in old:
                                row[field] = old[field]
                        row["completion_origin_revision"] = previous_revision.name
                apply_operational_identity(row)
            current = [{column: row.get(column) for column in OBSERVATION_COLUMNS} for row in current]
            blocks, comparison_notes = [], []
            if bridge_conflicts:
                blocks.append("identity_conflict")
            if latest_id != run["previous_accepted_revision_id"]:
                blocks.append("Accepted baseline changed since the first attempt; this revision cannot replace it.")
            if latest and _utc(manifest["listing_fetched_at_utc"]) < _utc(latest[1]["summary"]["listing_fetched_at_utc"]):
                blocks.append("The listing observation is older than the currently published listing.")
            accepted_snapshot = previous_manifest["snapshot_id"] if previous_revision else None
            events = _changes(
                previous_records, current, comparison="previous_accepted",
                previous_snapshot_id=accepted_snapshot, manifest=manifest,
                newly_bridged=newly_bridged,
                bridged_fixtures=bridged_fixtures,
            )
            for key in sorted(set(bridge_conflicts)):
                old, new = old_by_key.get(key), next((row for row in current if row["fixture_key"] == key), None)
                event = {
                    "comparison": "previous_accepted", "event_type": "identity_conflict",
                    "fixture_key": key, "match_id": (new or old or {}).get("match_id"),
                    "previous_snapshot_id": accepted_snapshot, "snapshot_id": manifest["snapshot_id"],
                    "detected_at_utc": manifest["observed_at_utc"],
                    "changed_fields": sorted(
                        field for field in set((old or {}).keys()) | set((new or {}).keys())
                        if (old or {}).get(field) != (new or {}).get(field)
                    ),
                    "before": _semantic(old), "after": _semantic(new),
                }
                event["event_id"] = _sha(_json(event))
                events.append(event)
            observed_id = manifest["previous_snapshot_id"]
            if observed_id:
                try:
                    observed_path = snapshot_dir.parent / _safe_name(observed_id)
                    observed_manifest = _read_snapshot(observed_path)
                    observed_records = (
                        previous_records if observed_manifest["format_version"] == LEGACY_FORMAT_VERSION and migration
                        else _parse_snapshot(observed_path, observed_manifest)
                    )
                    # Preserve completion inherited by an already processed
                    # predecessor; otherwise unchanged scores would repeatedly
                    # appear to become completed on each new observation.
                    observed_run = runs / f"{observed_id}-{FORMAT_VERSION}.json"
                    if observed_run.exists():
                        prior_run = json.loads(observed_run.read_bytes())
                        if prior_run["snapshot_sha256"] != _sha((observed_path / "manifest.json").read_bytes()):
                            raise ValueError("Previous snapshot was modified after processing.")
                        prior_revision = output_dir / "revisions" / _sha(_json(prior_run))
                        if prior_revision.exists():
                            _read_revision(prior_revision)
                            observed_records = json.loads((prior_revision / "observations.json").read_bytes())
                    events += _changes(
                        observed_records, current, comparison="previous_snapshot",
                        previous_snapshot_id=observed_id, manifest=manifest,
                        newly_bridged=newly_bridged,
                        bridged_fixtures=bridged_fixtures,
                    )
                except (ValueError, OSError, KeyError) as exc:
                    comparison_notes.append(f"Previous snapshot comparison unavailable: {exc}")
                    blocks.append("Previous snapshot could not be compared; review required.")
            else:
                events += _changes(
                    [], current, comparison="previous_snapshot", previous_snapshot_id=None,
                    manifest=manifest, newly_bridged=newly_bridged,
                    bridged_fixtures=bridged_fixtures,
                )
            forbidden = {"missing_from_snapshot", "identity_conflict", "completion_unconfirmed"}
            for event_type in sorted({event["event_type"] for event in events} & forbidden):
                blocks.append(event_type)
            # Reusing an official ID for a different fixture is never a rename.
            old_ids = {row["match_id"]: row["fixture_key"] for row in previous_records if row["match_id"]}
            if any(row["match_id"] in old_ids and old_ids[row["match_id"]] != row["fixture_key"] for row in current if row["match_id"]):
                blocks.append("identity_conflict")
                blocks.append("Official match_id was assigned to a different fixture.")
            try:
                _validate_typed_identities(current)
            except ValueError as exc:
                blocks.append("identity_conflict")
                blocks.append(f"Typed identity validation failed: {exc}")
            affected = newly_bridged | {
                event["fixture_key"] for event in events
                if event["event_type"] == "identity_namespace_transition"
            }
            binding = (
                Path(prediction_binding_path) if prediction_binding_path is not None
                else Path(__file__).resolve().parents[2] / "data/processed/predictions/2026_27_prediction_fixture_bindings.csv"
            )
            binding_status, binding_block = _prediction_binding_gate(
                affected, binding_path=binding,
                repository_root=prediction_repository_root,
                prediction_artifacts=prediction_artifacts,
            )
            if binding_block:
                blocks.append(binding_block)
            try:
                coverage = validate_fixture_coverage(current)
            except ValueError as exc:
                coverage = {"valid": False, "error": str(exc)}
                blocks.append(f"Fixture coverage failed: {exc}")
            completed = [row for row in current if row["status"] == "completed"]
            if completed:
                validate_matches(pd.DataFrame(completed))
                result_validation = "passed"
            else:
                result_validation = "no_completed_matches"
            counts = {status: sum(row["status"] == status for row in current) for status in ("scheduled", "candidate", "completed")}
            summary = {
                "competition_key": COMPETITION_KEY, "snapshot_id": manifest["snapshot_id"],
                "sequence": manifest["sequence"], "revision_id": revision_id,
                "previous_snapshot_id": observed_id, "previous_accepted_revision_id": run["previous_accepted_revision_id"],
                "listing_fetched_at_utc": manifest["listing_fetched_at_utc"], "observed_at_utc": manifest["observed_at_utc"],
                "counts": counts, "total_fixtures": len(current), "coverage": coverage,
                "match_id_count": len({row['match_id'] for row in current if row['match_id']}),
                "match_page_id_count": len({row['match_page_id'] for row in current if row.get('match_page_id')}),
                "data_site_match_id_count": len({row['data_site_match_id'] for row in current if row.get('data_site_match_id')}),
                "identity_bridge_count": len(bridges),
                "identity_bridge_policy": IDENTITY_BRIDGE_POLICY_VERSION,
                "migration": migration,
                "prediction_binding_status": binding_status,
                "result_validation": result_validation, "completion_policy": COMPLETION_POLICY,
                "publication_status": "held" if blocks else "published", "publication_blocks": blocks,
                "comparison_notes": comparison_notes,
                "change_counts": {kind: sum(event["event_type"] == kind for event in events) for kind in sorted({event["event_type"] for event in events})},
                "change_counts_by_comparison": {
                    comparison: {kind: sum(event["comparison"] == comparison and event["event_type"] == kind for event in events) for kind in sorted({event["event_type"] for event in events if event["comparison"] == comparison})}
                    for comparison in ("previous_snapshot", "previous_accepted")
                },
                "source_requests_during_processing": 0, "sources": manifest["sources"],
            }
            if migration is None:
                summary.pop("migration")
            # Return the same JSON scalar/key types on first execution and replay.
            summary = json.loads(_json(summary))
            history = {}
            for existing_path in sorted((output_dir / "revisions").glob("*/manifest.json")):
                existing = _read_revision(existing_path.parent)
                if existing["sequence"] < manifest["sequence"]:
                    for event in json.loads((existing_path.parent / "changes.json").read_bytes()):
                        history[event["event_id"]] = event
            history.update({event["event_id"]: event for event in events})
            history_rows = sorted(history.values(), key=lambda event: (event["detected_at_utc"], event["snapshot_id"], event["event_id"]))
            columns = list(OBSERVATION_COLUMNS)
            payload = {
                "schedule.csv": _csv(current, columns),
                "completed_matches.csv": _csv(completed, columns),
                "fixture_identity.csv": _csv(current, ("fixture_key", "match_id", "home_club", "away_club")),
                "identity_bridges.csv": _csv(bridges, BRIDGE_COLUMNS),
                "change_log.csv": _csv(history_rows, EVENT_COLUMNS),
                "update_summary.json": _json(summary), "review.md": _review(summary, current),
                "observations.json": _json(current), "changes.json": _json(events),
            }
            for name in ("schedule.csv", "completed_matches.csv"):
                parsed = list(csv.DictReader(io.StringIO(payload[name].decode("utf-8"))))
                expected = current if name == "schedule.csv" else completed
                if len(parsed) != len(expected) or any(row["fixture_key"] != original["fixture_key"] for row, original in zip(parsed, expected)):
                    raise ValueError("CSV round-trip verification failed.")
            revision_manifest = {
                "format_version": FORMAT_VERSION, "completion_policy": COMPLETION_POLICY,
                "identity_bridge_policy": IDENTITY_BRIDGE_POLICY_VERSION,
                "snapshot_id": manifest["snapshot_id"], "sequence": manifest["sequence"],
                "run": run, "files": {name: _sha(content) for name, content in payload.items()}, "summary": summary,
            }
            if migration is not None:
                revision_manifest["migration"] = migration
            revision.parent.mkdir(exist_ok=True)
            staging = revision.parent / f".pending-{revision_id}-{uuid.uuid4().hex}"
            staging.mkdir()
            for name, content in payload.items():
                _write_new(staging / name, content)
            _write_new(staging / "manifest.json", _json(revision_manifest))
            staging.rename(revision)
            _read_revision(revision)
            if not blocks:
                pointer["manifest_sha256"] = _sha((revision / "manifest.json").read_bytes())
                _publish(output_dir, revision, pointer)
            return summary
        except Exception as exc:
            failures = output_dir / "failures"
            failures.mkdir(exist_ok=True)
            _write_new(failures / f"{manifest['snapshot_id']}-{uuid.uuid4().hex}.json", _json({"run": run, "error_type": type(exc).__name__, "error": str(exc)}))
            raise
