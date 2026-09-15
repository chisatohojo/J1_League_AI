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
    COMPETITION_KEY, COMPLETION_POLICY_VERSION, SOURCE_URL, apply_completion_evidence,
    parse_completion_evidence, parse_listing, validate_fixture_coverage,
)
from src.collect.matches import REQUIRED_COLUMNS, validate_matches


FORMAT_VERSION = "ongoing-v1"
COMPLETION_POLICY = COMPLETION_POLICY_VERSION
PROJECTIONS = (
    "schedule.csv", "completed_matches.csv", "change_log.csv",
    "update_summary.json", "fixture_identity.csv", "review.md",
)
EVENT_COLUMNS = (
    "event_id", "comparison", "event_type", "fixture_key", "match_id",
    "previous_snapshot_id", "snapshot_id", "detected_at_utc",
    "changed_fields", "before", "after",
)
_SCORE_FIELDS = ("home_score", "away_score", "result")
_SCHEDULE_FIELDS = ("match_date", "kickoff_time", "stadium", "round")
_IGNORE_FIELDS = {
    "evidence_url", "evidence_type", "evidence_sha256", "evidence_fetched_at_utc",
    "completion_origin_revision", "completion_origin_snapshot",
}


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


def _read_snapshot(path: Path) -> dict:
    manifest = json.loads((path / "manifest.json").read_bytes())
    if manifest["snapshot_id"] != path.name or manifest["competition_key"] != COMPETITION_KEY or manifest["format_version"] != FORMAT_VERSION:
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
    listing = manifest["sources"][0]
    records = parse_listing((path / listing["html"]).read_text(encoding="utf-8-sig"))
    evidence = []
    for source in manifest["sources"][1:]:
        item = parse_completion_evidence(
            (path / source["html"]).read_text(encoding="utf-8-sig"), source_url=source["source_url"],
        )
        item["evidence_sha256"] = source["sha256"]
        item["evidence_fetched_at_utc"] = source["fetched_at_utc"]
        evidence.append(item)
    result = apply_completion_evidence(records, evidence)
    by_key = {item["fixture_key"]: item for item in evidence}
    for record in result:
        if record["status"] == "completed":
            proof = by_key[record["fixture_key"]]
            record["evidence_sha256"] = proof["evidence_sha256"]
            record["evidence_fetched_at_utc"] = proof["evidence_fetched_at_utc"]
            record["completion_origin_snapshot"] = manifest["snapshot_id"]
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


def _changes(previous: list[dict], current: list[dict], *, comparison: str, previous_snapshot_id: str | None, manifest: dict) -> list[dict]:
    before, after = ({row["fixture_key"]: row for row in rows} for rows in (previous, current))
    events = []
    for key in sorted(before.keys() | after.keys()):
        old, new = before.get(key), after.get(key)
        types = []
        if old is None:
            types.append("new_fixture")
            if new["home_score"] is not None:
                types.append("result_candidate")
            if new["status"] == "completed":
                types.append("completed")
        elif new is None:
            types.append("missing_from_snapshot")
        else:
            if any(old.get(field) != new.get(field) for field in _SCHEDULE_FIELDS):
                types.append("schedule_changed")
            if old.get("match_id") != new.get("match_id"):
                types.append("identity_linked" if old.get("match_id") is None and new.get("match_id") else "identity_conflict")
            if any(old.get(field) != new.get(field) for field in _SCORE_FIELDS):
                types.append("result_corrected" if old["status"] == "completed" else "result_candidate")
            if old["status"] != "completed" and new["status"] == "completed":
                types.append("completed")
            if old["status"] == "completed" and new["status"] != "completed":
                types.append("completion_unconfirmed")
            if not types and _semantic(old) != _semantic(new):
                types.append("metadata_changed")
        old_value, new_value = _semantic(old), _semantic(new)
        changed = sorted(field for field in (old_value or {}).keys() | (new_value or {}).keys() if (old_value or {}).get(field) != (new_value or {}).get(field))
        for event_type in types:
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


def process_snapshot(snapshot_dir: Path, output_dir: Path) -> dict:
    """Validate and publish a snapshot, or keep a held revision with diagnostics.

    Parse/integrity failures raise and leave latest unchanged. Missing fixtures,
    identity conflicts and unverified corrections produce a held revision whose
    before/after events remain available for review and later recovery.
    """
    snapshot_dir, output_dir = Path(snapshot_dir), Path(output_dir)
    with _lock(output_dir, ".update.lock"):
        manifest = _read_snapshot(snapshot_dir)
        latest = read_latest(output_dir)
        latest_id = latest[0].name if latest else None
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
        if run["previous_accepted_revision_id"]:
            previous_revision = output_dir / "revisions" / _safe_name(run["previous_accepted_revision_id"])
            previous_manifest = _read_revision(previous_revision)
            if previous_manifest["format_version"] != FORMAT_VERSION or previous_manifest["completion_policy"] != COMPLETION_POLICY:
                raise ValueError("Parser/policy changes need a separate migration, not a source correction.")
            previous_records = json.loads((previous_revision / "observations.json").read_bytes())
        try:
            current = _parse_snapshot(snapshot_dir, manifest)
            old_by_key = {row["fixture_key"]: row for row in previous_records}
            explicit_keys = set()
            for source in manifest["sources"][1:]:
                proof = parse_completion_evidence((snapshot_dir / source["html"]).read_text(encoding="utf-8-sig"), source_url=source["source_url"])
                explicit_keys.add(proof["fixture_key"])
            # A verified finish may be retained only for identical results and
            # identity. A changed score/date requires fresh matching proof.
            for row in current:
                old = old_by_key.get(row["fixture_key"])
                if old and old["status"] == "completed" and row["status"] == "candidate" and row["fixture_key"] not in explicit_keys:
                    if all(old.get(field) == row.get(field) for field in (*_SCORE_FIELDS, "match_id", "match_date", "round")):
                        row["status"] = "completed"
                        for field in _IGNORE_FIELDS:
                            if field in old:
                                row[field] = old[field]
                        row["completion_origin_revision"] = previous_revision.name
            blocks, comparison_notes = [], []
            if latest_id != run["previous_accepted_revision_id"]:
                blocks.append("Accepted baseline changed since the first attempt; this revision cannot replace it.")
            if latest and _utc(manifest["listing_fetched_at_utc"]) < _utc(latest[1]["summary"]["listing_fetched_at_utc"]):
                blocks.append("The listing observation is older than the currently published listing.")
            accepted_snapshot = previous_manifest["snapshot_id"] if previous_revision else None
            events = _changes(previous_records, current, comparison="previous_accepted", previous_snapshot_id=accepted_snapshot, manifest=manifest)
            observed_id = manifest["previous_snapshot_id"]
            if observed_id:
                try:
                    observed_path = snapshot_dir.parent / _safe_name(observed_id)
                    observed_manifest = _read_snapshot(observed_path)
                    observed_records = _parse_snapshot(observed_path, observed_manifest)
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
                    events += _changes(observed_records, current, comparison="previous_snapshot", previous_snapshot_id=observed_id, manifest=manifest)
                except (ValueError, OSError, KeyError) as exc:
                    comparison_notes.append(f"Previous snapshot comparison unavailable: {exc}")
                    blocks.append("Previous snapshot could not be compared; review required.")
            else:
                events += _changes([], current, comparison="previous_snapshot", previous_snapshot_id=None, manifest=manifest)
            forbidden = {"missing_from_snapshot", "identity_conflict", "completion_unconfirmed"}
            for event_type in sorted({event["event_type"] for event in events} & forbidden):
                blocks.append(event_type)
            # Reusing an official ID for a different fixture is never a rename.
            old_ids = {row["match_id"]: row["fixture_key"] for row in previous_records if row["match_id"]}
            if any(row["match_id"] in old_ids and old_ids[row["match_id"]] != row["fixture_key"] for row in current if row["match_id"]):
                blocks.append("Official match_id was assigned to a different fixture.")
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
            columns = list(dict.fromkeys([*REQUIRED_COLUMNS, "fixture_key", "status", *[key for row in current for key in row]]))
            payload = {
                "schedule.csv": _csv(current, columns),
                "completed_matches.csv": _csv(completed, columns),
                "fixture_identity.csv": _csv(current, ("fixture_key", "match_id", "home_club", "away_club")),
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
                "snapshot_id": manifest["snapshot_id"], "sequence": manifest["sequence"],
                "run": run, "files": {name: _sha(content) for name, content in payload.items()}, "summary": summary,
            }
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
