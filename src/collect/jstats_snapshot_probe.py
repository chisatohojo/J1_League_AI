"""Probe one official J Stats page and gate a prospective FULL_37 capture."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from src.collect import jstats_snapshot_registry as registry
from src.collect.jstats_team_snapshots import (
    BASE_URL,
    ROOT,
    SCHEDULE,
    STATS,
    SnapshotError,
    _fetch,
    collect_full_snapshot,
    expected_club_slugs,
    parse_page,
)
from src.collect.teams import load_team_master


PROBE_STAT = next(stat for stat in STATS if stat.slug == "shoot")
PROBE_URL = BASE_URL.format(slug=PROBE_STAT.slug)
RAW_ROOT = ROOT / "data/raw/jstats_snapshot_probes"
ADVANCED = "SOURCE_STATE_ADVANCED"
UNCHANGED = "SOURCE_STATE_UNCHANGED"
REGRESSED = "SOURCE_STATE_REGRESSED"
UNKNOWN = "SOURCE_STATE_UNKNOWN"


@dataclass(frozen=True)
class ProbeResult:
    status: str
    url: str
    retrieved_at: str
    source_state_date: str | None
    latest_saved_source_state_date: str | None
    raw_sha256: str | None
    request_count: int
    parsed_clubs: int
    raw_dir: str | None
    error: str | None = None


def classify_source_state(source_date: str | None, latest_date: str | None) -> str:
    """Classify a probe date against the registry's latest logical state."""
    if source_date is None or latest_date is None:
        return UNKNOWN
    try:
        observed = datetime.fromisoformat(source_date).date()
        latest = datetime.fromisoformat(latest_date).date()
    except (TypeError, ValueError):
        return UNKNOWN
    if observed > latest:
        return ADVANCED
    if observed == latest:
        return UNCHANGED
    return REGRESSED


def probe_source_state(
    *,
    raw_root: str | Path = RAW_ROOT,
    schedule_path: str | Path = SCHEDULE,
    now: datetime | None = None,
    fetch: Callable = _fetch,
    registry_report: registry.RegistryReport | None = None,
    registry_kwargs: dict | None = None,
    master=None,
) -> ProbeResult:
    """Fetch and validate exactly one allowlisted page, retaining probe provenance."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise SnapshotError("Probe retrieval time must be UTC-aware.")
    retrieved_at = now.isoformat().replace("+00:00", "Z")
    probe_id = now.strftime("%Y%m%dT%H%M%S%fZ")
    raw_dir = Path(raw_root) / probe_id
    if raw_dir.exists():
        raise SnapshotError(f"Probe already exists: {probe_id}.")
    raw_dir.mkdir(parents=True)

    digest = None
    source_date = None
    latest_date = None
    parsed_clubs = 0
    error = None
    body = None
    try:
        body, status, final_url, content_type = fetch(PROBE_URL)
        if not isinstance(body, bytes):
            raise SnapshotError("Probe returned a non-byte HTTP response.")
        digest = hashlib.sha256(body).hexdigest()
        (raw_dir / "shoot.html").write_bytes(body)
        if status != 200 or final_url != PROBE_URL or not content_type.lower().startswith("text/html"):
            raise SnapshotError("Probe returned unexpected HTTP status, redirect, URL, or content type.")
        expected = expected_club_slugs(Path(schedule_path))
        master = master or load_team_master()
        rows, source_date = parse_page(
            body,
            stat=PROBE_STAT,
            expected_slugs=expected,
            master=master,
            observed_date=now.astimezone(ZoneInfo("Asia/Tokyo")).date(),
        )
        parsed_clubs = len(rows)
        latest_date = registry.latest_logical_source_date(
            registry_report,
            **(registry_kwargs or {}),
        )
    except Exception as exc:  # UNKNOWN is a safe closed gate, with the error retained.
        error = str(exc)

    status = classify_source_state(source_date, latest_date) if error is None else UNKNOWN
    manifest = {
        "probe_id": probe_id,
        "retrieved_at": retrieved_at,
        "requested_url": PROBE_URL,
        "source_state_date": source_date,
        "latest_saved_source_state_date": latest_date,
        "status": status,
        "request_count": 1,
        "parsed_clubs": parsed_clubs,
        "bytes": len(body) if isinstance(body, bytes) else None,
        "raw_sha256": digest,
        "html": "shoot.html" if isinstance(body, bytes) else None,
    }
    if error is not None:
        manifest["error"] = error
    (raw_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return ProbeResult(
        status=status,
        url=PROBE_URL,
        retrieved_at=retrieved_at,
        source_state_date=source_date,
        latest_saved_source_state_date=latest_date,
        raw_sha256=digest,
        request_count=1,
        parsed_clubs=parsed_clubs,
        raw_dir=str(raw_dir),
        error=error,
    )


def run_capture_gate(*, full_collector: Callable = collect_full_snapshot, **probe_kwargs):
    """Run FULL_37 once only when the one-page probe observes an advance."""
    probe = probe_source_state(**probe_kwargs)
    capture = None
    if probe.status == ADVANCED:
        capture = full_collector(required_source_date=probe.source_state_date)
    return probe, capture


def render_result(result: ProbeResult) -> str:
    first = "PROBE_OK" if result.status != UNKNOWN else "PROBE_UNKNOWN"
    lines = [first]
    for key, value in asdict(result).items():
        lines.append(f"{key}={'' if value is None else value}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture-if-advanced",
        action="store_true",
        help="run the existing FULL_37 collector once if the source state advanced",
    )
    args = parser.parse_args(argv)
    if args.capture_if_advanced:
        result, capture = run_capture_gate()
    else:
        result, capture = probe_source_state(), None
    print(render_result(result))
    print(f"full_capture_executed={'YES' if capture is not None else 'NO'}")
    if capture is not None:
        print(json.dumps(capture, ensure_ascii=False, default=str, indent=2))
    return 0 if result.status in (ADVANCED, UNCHANGED) else 2


if __name__ == "__main__":
    raise SystemExit(main())
