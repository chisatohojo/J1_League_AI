"""Read-only integrity registry for prospective J Stats team snapshots.

This module audits immutable raw/processed observations and describes logical
37-stat source states.  It never writes snapshots, reconstructs match-level
statistics, fits a model, or evaluates predictions.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from src.collect.jstats_team_snapshots import (
    BASE_URL,
    CSV_FIELDS,
    FULL_STATS,
    PROCESSED_ROOT,
    RAW_ROOT,
    SEASON,
    STATS,
    SUPPLEMENTAL_STATS,
    expected_club_slugs,
)
from src.collect.teams import TeamMaster, load_team_master


ROOT = Path(__file__).resolve().parents[2]
COMPLETED_MATCHES = ROOT / "data/processed/jleague/2026_27/completed_matches.csv"
BASE_SLUGS = frozenset(stat.slug for stat in STATS)
SUPPLEMENTAL_SLUGS = frozenset(stat.slug for stat in SUPPLEMENTAL_STATS)
FULL_SLUGS = frozenset(stat.slug for stat in FULL_STATS)
PROFILE_SETS = {
    "BASE_10": BASE_SLUGS,
    "SUPPLEMENTAL_27": SUPPLEMENTAL_SLUGS,
    "FULL_37": FULL_SLUGS,
}
SOURCE_MIXED = "MIXED_SOURCE_STATE"
SOURCE_UNKNOWN = "UNKNOWN_SOURCE_STATE"


class SnapshotRegistryError(ValueError):
    """A saved snapshot or logical-state invariant failed."""


@dataclass(frozen=True)
class PhysicalSnapshot:
    snapshot_id: str
    status: str
    profile: str
    retrieved_at: str
    season: str
    source_state_date: str
    stat_count: int
    page_count: int
    row_count: int
    integrity_status: str
    stat_names: tuple[str, ...]
    team_ids: tuple[str, ...]
    raw_dir: str
    processed_path: str | None


@dataclass(frozen=True)
class LogicalFullState:
    season: str
    source_state_date: str
    profile: str
    kind: str
    snapshot_ids: tuple[str, ...]
    stat_names: tuple[str, ...]
    team_ids: tuple[str, ...]


@dataclass(frozen=True)
class TransitionAudit:
    previous_source_state_date: str
    source_state_date: str
    status: str
    match_ids: tuple[str, ...]
    match_count: int
    team_appearance_increments: dict[str, int]


@dataclass(frozen=True)
class RegistryReport:
    physical_snapshots: tuple[PhysicalSnapshot, ...]
    logical_full_states: tuple[LogicalFullState, ...]
    transitions: tuple[TransitionAudit, ...]


def classify_profile(stat_names) -> str:
    """Classify by exact slug-set equality, never by count alone."""
    observed = frozenset(stat_names)
    for profile, expected in PROFILE_SETS.items():
        if observed == expected:
            return profile
    return "UNKNOWN"


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SnapshotRegistryError(f"Cannot read manifest: {path}") from exc
    if not isinstance(value, dict):
        raise SnapshotRegistryError(f"Manifest must be an object: {path}")
    return value


def _utc_timestamp(value, label: str) -> datetime:
    if not isinstance(value, str):
        raise SnapshotRegistryError(f"{label} must be an ISO UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotRegistryError(f"{label} must be an ISO UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise SnapshotRegistryError(f"{label} must be UTC")
    return parsed


def _source_state_date(pages: list[dict]) -> str:
    values = [page.get("source_updated_date_jst") for page in pages]
    known = {value for value in values if isinstance(value, str) and value}
    if len(known) > 1:
        return SOURCE_MIXED
    if not pages or len(known) != 1 or any(not isinstance(value, str) or not value for value in values):
        return SOURCE_UNKNOWN
    value = next(iter(known))
    try:
        if datetime.fromisoformat(value).strftime("%Y-%m-%d") != value:
            raise ValueError
    except ValueError as exc:
        raise SnapshotRegistryError(f"Invalid source update date: {value!r}") from exc
    return value


def _audit_raw_pages(raw_dir: Path, manifest: dict, requested: tuple[str, ...]) -> tuple[list[dict], str]:
    pages = manifest.get("pages")
    if not isinstance(pages, list):
        raise SnapshotRegistryError(f"{raw_dir.name}: manifest pages must be a list")
    page_stats = []
    for page in pages:
        if not isinstance(page, dict):
            raise SnapshotRegistryError(f"{raw_dir.name}: invalid page record")
        required = {"stat_name", "requested_url", "final_url", "status", "sha256", "html"}
        if not required <= set(page):
            raise SnapshotRegistryError(f"{raw_dir.name}: incomplete page provenance")
        stat_name = page["stat_name"]
        if not isinstance(stat_name, str) or not stat_name or stat_name in page_stats:
            raise SnapshotRegistryError(f"{raw_dir.name}: duplicate/invalid page stat")
        if stat_name not in requested:
            raise SnapshotRegistryError(f"{raw_dir.name}: page outside requested stat set")
        expected_url = BASE_URL.format(slug=stat_name)
        if page["requested_url"] != expected_url:
            raise SnapshotRegistryError(f"{raw_dir.name}: requested URL mismatch for {stat_name}")
        if not isinstance(page["final_url"], str) or not page["final_url"]:
            raise SnapshotRegistryError(f"{raw_dir.name}: missing final URL for {stat_name}")
        if isinstance(page["status"], bool) or not isinstance(page["status"], int):
            raise SnapshotRegistryError(f"{raw_dir.name}: invalid HTTP status for {stat_name}")
        html_name = page["html"]
        if not isinstance(html_name, str) or Path(html_name).name != html_name:
            raise SnapshotRegistryError(f"{raw_dir.name}: unsafe raw HTML path")
        html_path = raw_dir / html_name
        if not html_path.is_file():
            raise SnapshotRegistryError(f"{raw_dir.name}: missing raw HTML for {stat_name}")
        body = html_path.read_bytes()
        actual = hashlib.sha256(body).hexdigest()
        expected = page["sha256"]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or actual != expected:
            raise SnapshotRegistryError(f"{raw_dir.name}: raw SHA-256 mismatch for {stat_name}")
        if "bytes" in page and page["bytes"] != len(body):
            raise SnapshotRegistryError(f"{raw_dir.name}: raw byte count mismatch for {stat_name}")
        page_stats.append(stat_name)
    if not set(page_stats) <= set(requested):
        raise SnapshotRegistryError(f"{raw_dir.name}: raw page membership mismatch")
    return pages, _source_state_date(pages)


def _read_processed(path: Path) -> tuple[tuple[str, ...], list[dict]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            fields = tuple(reader.fieldnames or ())
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise SnapshotRegistryError(f"Cannot read processed snapshot: {path}") from exc
    return fields, rows


def _audit_processed(
    path: Path,
    *,
    manifest: dict,
    requested: tuple[str, ...],
    pages: list[dict],
    source_state_date: str,
    master: TeamMaster,
    schedule_path: Path,
) -> tuple[int, tuple[str, ...]]:
    fields, rows = _read_processed(path)
    if fields != CSV_FIELDS:
        raise SnapshotRegistryError(f"{path.name}: processed schema mismatch")
    expected_rows = 20 * len(requested)
    if len(rows) != expected_rows:
        raise SnapshotRegistryError(f"{path.name}: expected {expected_rows} rows, got {len(rows)}")
    snapshot_id = manifest["snapshot_id"]
    if {row["snapshot_id"] for row in rows} != {snapshot_id}:
        raise SnapshotRegistryError(f"{path.name}: snapshot_id mismatch")
    if {row["season"] for row in rows} != {manifest["season"]} or {row["competition"] for row in rows} != {"j1"}:
        raise SnapshotRegistryError(f"{path.name}: season/competition mismatch")
    if any(not row["team_id"] or not row["official_club_name"] or not row["official_club_slug"] for row in rows):
        raise SnapshotRegistryError(f"{path.name}: null team identity")
    pairs = [(row["team_id"], row["stat_name"]) for row in rows]
    if len(pairs) != len(set(pairs)):
        raise SnapshotRegistryError(f"{path.name}: duplicate (team_id, stat_name)")
    if set(row["stat_name"] for row in rows) != set(requested):
        raise SnapshotRegistryError(f"{path.name}: processed stat set mismatch")

    expected_slugs = expected_club_slugs(schedule_path)
    page_by_stat = {page["stat_name"]: page for page in pages}
    retrieved_date = _utc_timestamp(manifest["retrieved_at"], "retrieved_at").astimezone(ZoneInfo("Asia/Tokyo")).date()
    aliases = {
        (alias.source_club_id, alias.source_name, alias.team_id)
        for alias in master.aliases if alias.source == "jleague_official"
    }
    team_sets = []
    for stat_name in requested:
        stat_rows = [row for row in rows if row["stat_name"] == stat_name]
        if len(stat_rows) != 20 or len({row["team_id"] for row in stat_rows}) != 20:
            raise SnapshotRegistryError(f"{path.name}: {stat_name} does not contain 20 unique teams")
        if {row["official_club_slug"] for row in stat_rows} != expected_slugs:
            raise SnapshotRegistryError(f"{path.name}: {stat_name} club slugs differ from schedule")
        page = page_by_stat[stat_name]
        for row in stat_rows:
            identity = (row["official_club_slug"], row["official_club_name"], row["team_id"])
            if identity not in aliases:
                raise SnapshotRegistryError(f"{path.name}: exact TeamMaster identity mismatch")
            resolved = master.resolve_team_id(
                row["official_club_name"], source="jleague_official", on=retrieved_date,
            )
            if resolved != row["team_id"] or row["official_club_id"] != row["official_club_slug"]:
                raise SnapshotRegistryError(f"{path.name}: TeamMaster identity conflict")
            if row["source_url"] != page["requested_url"] or row["raw_sha256"] != page["sha256"]:
                raise SnapshotRegistryError(f"{path.name}: processed/raw provenance mismatch")
            expected_date = source_state_date if source_state_date not in (SOURCE_MIXED, SOURCE_UNKNOWN) else ""
            if row["source_updated_date_jst"] != expected_date:
                raise SnapshotRegistryError(f"{path.name}: processed source-state mismatch")
        team_sets.append({row["team_id"] for row in stat_rows})
    if any(team_set != team_sets[0] for team_set in team_sets[1:]):
        raise SnapshotRegistryError(f"{path.name}: team identity differs across stats")
    return len(rows), tuple(sorted(team_sets[0]))


def audit_snapshot(
    raw_dir: str | Path,
    *,
    processed_root: str | Path = PROCESSED_ROOT,
    schedule_path: str | Path = Path(__file__).resolve().parents[2] / "data/processed/jleague/2026_27/schedule.csv",
    master: TeamMaster | None = None,
) -> PhysicalSnapshot:
    raw_dir = Path(raw_dir)
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotRegistryError(f"{raw_dir.name}: manifest is missing")
    manifest = _read_json(manifest_path)
    snapshot_id = manifest.get("snapshot_id")
    if snapshot_id != raw_dir.name or not isinstance(snapshot_id, str):
        raise SnapshotRegistryError(f"{raw_dir.name}: manifest snapshot_id mismatch")
    status = manifest.get("status")
    if status not in ("COMPLETE", "INCOMPLETE"):
        raise SnapshotRegistryError(f"{snapshot_id}: invalid manifest status")
    retrieved_at = manifest.get("retrieved_at")
    _utc_timestamp(retrieved_at, "retrieved_at")
    season = manifest.get("season")
    if not isinstance(season, str) or not season:
        raise SnapshotRegistryError(f"{snapshot_id}: invalid season")
    requested_value = manifest.get("requested_stats")
    if (not isinstance(requested_value, list) or not requested_value
            or any(not isinstance(value, str) or not value for value in requested_value)):
        raise SnapshotRegistryError(f"{snapshot_id}: invalid requested stat set")
    requested = tuple(requested_value)
    if len(requested) != len(set(requested)):
        raise SnapshotRegistryError(f"{snapshot_id}: duplicate requested stat slug")
    pages, source_state_date = _audit_raw_pages(raw_dir, manifest, requested)
    profile = classify_profile(requested)
    output = Path(processed_root) / f"{snapshot_id}.csv"
    master = master or load_team_master()

    if status == "COMPLETE":
        if len(pages) != len(requested) or {page["stat_name"] for page in pages} != set(requested):
            raise SnapshotRegistryError(f"{snapshot_id}: COMPLETE raw page set mismatch")
        for page in pages:
            if page["status"] != 200 or page["final_url"] != page["requested_url"] or page.get("parsed_clubs") != 20:
                raise SnapshotRegistryError(f"{snapshot_id}: COMPLETE page validation mismatch")
        if source_state_date in (SOURCE_MIXED, SOURCE_UNKNOWN):
            raise SnapshotRegistryError(f"{snapshot_id}: COMPLETE source state is not one known date")
        declared = manifest.get("source_state_date")
        if declared is not None and declared != source_state_date:
            raise SnapshotRegistryError(f"{snapshot_id}: manifest source_state_date mismatch")
        if not output.is_file():
            raise SnapshotRegistryError(f"{snapshot_id}: COMPLETE snapshot lacks processed CSV")
        row_count, team_ids = _audit_processed(
            output,
            manifest=manifest,
            requested=requested,
            pages=pages,
            source_state_date=source_state_date,
            master=master,
            schedule_path=Path(schedule_path),
        )
        processed_path = str(output)
    else:
        if output.exists():
            raise SnapshotRegistryError(f"{snapshot_id}: INCOMPLETE snapshot has processed CSV")
        row_count, team_ids, processed_path = 0, (), None

    return PhysicalSnapshot(
        snapshot_id=snapshot_id,
        status=status,
        profile=profile,
        retrieved_at=retrieved_at,
        season=season,
        source_state_date=source_state_date,
        stat_count=len(requested),
        page_count=len(pages),
        row_count=row_count,
        integrity_status="PASS",
        stat_names=tuple(requested),
        team_ids=team_ids,
        raw_dir=str(raw_dir),
        processed_path=processed_path,
    )


def reconstruct_full_state(first: PhysicalSnapshot, second: PhysicalSnapshot) -> LogicalFullState:
    """Represent a valid BASE_10 + SUPPLEMENTAL_27 pair without writing a merge."""
    profiles = {first.profile, second.profile}
    if profiles != {"BASE_10", "SUPPLEMENTAL_27"}:
        raise SnapshotRegistryError("Reconstruction requires exact BASE_10 and SUPPLEMENTAL_27 profiles")
    if first.status != "COMPLETE" or second.status != "COMPLETE" or first.integrity_status != "PASS" or second.integrity_status != "PASS":
        raise SnapshotRegistryError("Reconstruction requires two provenance-valid COMPLETE snapshots")
    if first.season != second.season or first.source_state_date != second.source_state_date:
        raise SnapshotRegistryError("Reconstruction season/source-state mismatch")
    if first.source_state_date in (SOURCE_MIXED, SOURCE_UNKNOWN):
        raise SnapshotRegistryError("Reconstruction requires one known source-state date")
    first_stats, second_stats = set(first.stat_names), set(second.stat_names)
    if first_stats & second_stats:
        raise SnapshotRegistryError("Reconstruction stat sets overlap")
    if first_stats | second_stats != set(FULL_SLUGS):
        raise SnapshotRegistryError("Reconstruction stat union is not exact FULL_37")
    if len(first.team_ids) != 20 or first.team_ids != second.team_ids:
        raise SnapshotRegistryError("Reconstruction team identities differ")
    return LogicalFullState(
        season=first.season,
        source_state_date=first.source_state_date,
        profile="FULL_37",
        kind="RECONSTRUCTED",
        snapshot_ids=tuple(sorted((first.snapshot_id, second.snapshot_id))),
        stat_names=tuple(stat.slug for stat in FULL_STATS),
        team_ids=first.team_ids,
    )


def build_logical_full_states(physical: tuple[PhysicalSnapshot, ...]) -> tuple[LogicalFullState, ...]:
    states = []
    for snapshot in physical:
        if (snapshot.status == "COMPLETE" and snapshot.integrity_status == "PASS"
                and snapshot.profile == "FULL_37"
                and snapshot.source_state_date not in (SOURCE_MIXED, SOURCE_UNKNOWN)):
            states.append(LogicalFullState(
                season=snapshot.season,
                source_state_date=snapshot.source_state_date,
                profile="FULL_37",
                kind="PHYSICAL",
                snapshot_ids=(snapshot.snapshot_id,),
                stat_names=snapshot.stat_names,
                team_ids=snapshot.team_ids,
            ))
    bases = [snapshot for snapshot in physical if snapshot.profile == "BASE_10"]
    supplemental = [snapshot for snapshot in physical if snapshot.profile == "SUPPLEMENTAL_27"]
    for first, second in itertools.product(bases, supplemental):
        if first.season != second.season or first.source_state_date != second.source_state_date:
            continue
        try:
            states.append(reconstruct_full_state(first, second))
        except SnapshotRegistryError:
            # A shared date is necessary but never sufficient for reconstruction.
            continue
    return tuple(sorted(states, key=lambda state: (state.source_state_date, state.kind, state.snapshot_ids)))


def audit_transition(
    previous: LogicalFullState,
    current: LogicalFullState,
    *,
    completed_path: str | Path = COMPLETED_MATCHES,
    master: TeamMaster | None = None,
) -> TransitionAudit:
    if current.source_state_date <= previous.source_state_date:
        raise SnapshotRegistryError("Logical source-state dates must be strictly ascending")
    if (set(previous.stat_names) != set(FULL_SLUGS) or set(current.stat_names) != set(FULL_SLUGS)
            or previous.team_ids != current.team_ids or previous.season != current.season):
        return TransitionAudit(
            previous.source_state_date, current.source_state_date, "IDENTITY_MISMATCH", (), 0, {},
        )
    try:
        with Path(completed_path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            required = {"match_id", "match_date", "home_team", "away_team"}
            if not required <= set(reader.fieldnames or ()):
                raise SnapshotRegistryError("Completed-match input schema mismatch")
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise SnapshotRegistryError("Cannot read completed-match transition input") from exc
    master = master or load_team_master()
    interval = []
    for row in rows:
        try:
            match_date = datetime.fromisoformat(row["match_date"]).date()
        except (TypeError, ValueError) as exc:
            raise SnapshotRegistryError("Invalid completed match date") from exc
        if datetime.fromisoformat(previous.source_state_date).date() < match_date <= datetime.fromisoformat(current.source_state_date).date():
            interval.append((match_date, row))
    interval.sort(key=lambda item: (item[0], str(item[1]["match_id"])))
    match_ids = tuple(str(row["match_id"]) for _, row in interval)
    if len(match_ids) != len(set(match_ids)):
        raise SnapshotRegistryError("Duplicate completed match ID in transition interval")
    counts = {team_id: 0 for team_id in previous.team_ids}
    for match_date, row in interval:
        for side in ("home", "away"):
            team_id = master.resolve_team_id(
                row[f"{side}_team"], source="jleague_data_site", on=match_date,
            )
            if team_id not in counts:
                return TransitionAudit(
                    previous.source_state_date, current.source_state_date,
                    "IDENTITY_MISMATCH", match_ids, len(match_ids), counts,
                )
            counts[team_id] += 1
    if not interval:
        status = "NO_MATCH_INTERVAL"
    elif len(interval) == 10 and set(counts.values()) == {1}:
        status = "CLEAN_ONE_MATCH_PER_TEAM"
    else:
        status = "MULTI_MATCH_INTERVAL"
    return TransitionAudit(
        previous.source_state_date,
        current.source_state_date,
        status,
        match_ids,
        len(match_ids),
        counts,
    )


def audit_registry(
    *,
    raw_root: str | Path = RAW_ROOT,
    processed_root: str | Path = PROCESSED_ROOT,
    schedule_path: str | Path = Path(__file__).resolve().parents[2] / "data/processed/jleague/2026_27/schedule.csv",
    completed_path: str | Path = COMPLETED_MATCHES,
) -> RegistryReport:
    raw_root = Path(raw_root)
    if not raw_root.is_dir():
        raise SnapshotRegistryError(f"Snapshot raw root does not exist: {raw_root}")
    master = load_team_master()
    physical = tuple(
        audit_snapshot(
            directory,
            processed_root=processed_root,
            schedule_path=schedule_path,
            master=master,
        )
        for directory in sorted((path for path in raw_root.iterdir() if path.is_dir()), key=lambda path: path.name)
    )
    logical = build_logical_full_states(physical)
    transitions = tuple(
        audit_transition(previous, current, completed_path=completed_path, master=master)
        for previous, current in zip(logical, logical[1:])
        if previous.source_state_date < current.source_state_date
    )
    return RegistryReport(physical, logical, transitions)


def _json_report(report: RegistryReport) -> str:
    return json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True)


def render_summary(report: RegistryReport) -> str:
    lines = [f"physical snapshots: {len(report.physical_snapshots)}"]
    for snapshot in report.physical_snapshots:
        lines.append(
            f"{snapshot.snapshot_id} {snapshot.status} {snapshot.profile} "
            f"retrieved_at={snapshot.retrieved_at} source_state_date={snapshot.source_state_date} "
            f"stats={snapshot.stat_count} pages={snapshot.page_count} rows={snapshot.row_count} "
            f"integrity={snapshot.integrity_status}"
        )
    lines.append(f"logical FULL_37 states: {len(report.logical_full_states)}")
    for state in report.logical_full_states:
        if state.kind == "RECONSTRUCTED":
            detail = f"reconstructed from {len(state.snapshot_ids)} snapshots"
        else:
            detail = f"physical snapshot {state.snapshot_ids[0]}"
        lines.append(f"{state.source_state_date} FULL_37 {detail}")
    lines.append(f"transitions: {len(report.transitions)}")
    for transition in report.transitions:
        lines.append(
            f"{transition.previous_source_state_date} -> {transition.source_state_date} "
            f"{transition.status} matches={transition.match_count}"
        )
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the audited registry as JSON")
    args = parser.parse_args(argv)
    report = audit_registry()
    print(_json_report(report) if args.json else render_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
