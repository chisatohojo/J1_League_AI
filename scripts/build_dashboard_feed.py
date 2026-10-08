"""Project saved Champion A predictions into a validated, display-only feed.

No models, inference, metrics, network, source updates, or research-result joins.
Import/help are side-effect free. Real execution requires a separate reviewed task.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from zoneinfo import ZoneInfo

import pandas as pd

from scripts.serve_dashboard import CHAMPION_MODEL, validate_dashboard_data
from src.collect.jleague_ongoing import COMPLETION_POLICY, read_latest
from src.collect.jleague_ongoing_source import (
    COMPETITION_KEY, DATA_SITE_NAMESPACE, MATCH_PAGE_NAMESPACE,
    apply_operational_identity, validate_fixture_coverage,
)
from src.collect.matches import REQUIRED_COLUMNS, validate_matches
from src.collect.teams import load_team_master
from src.modeling.prediction_identity import BINDING_COLUMNS, validate_prediction_bindings


ROOT = Path(__file__).resolve().parents[1]
PREDICTION_ARTIFACT = "data/processed/predictions/season_transition_st2_prospective.csv"
BINDING_PATH = "data/processed/predictions/2026_27_prediction_fixture_bindings.csv"
ONGOING_PATH = "data/processed/jleague/2026_27"
TEAM_MASTER_PATH = "data/master/teams.csv"
OUTPUT_PATH = "data/processed/dashboard/champion_home.json"
COMPARISON_VERSION = "season_transition_st2_vs_a_20261006_v1"
CHAMPION_VERSION = "operational_champion_20260922_v1"
CHAMPION_HASH = "2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1"

# Only these values can survive CSV parsing. comparison_version is checked then discarded.
PROJECTION_COLUMNS = (
    "fixture_key", "match_id", "match_date", "kickoff", "home_team_id",
    "away_team_id", "home_team_name", "away_team_name", "prediction_generated_at",
    "source_revision", "champion_a_model_version", "champion_a_artifact_hash",
    "a_p_away", "a_p_draw", "a_p_home",
)
# Frozen input header only: research cells remain opaque and are never put in a frame.
MIXED_COLUMNS = (
    "fixture_key", "match_id", "match_date", "kickoff", "home_team_id",
    "away_team_id", "home_team_name", "away_team_name", "prediction_generated_at",
    "prospective_boundary", "comparison_version", "model_version", "source_revision",
    "source_observed_at", "champion_a_model_version", "champion_a_artifact_hash",
    "st2_model_version", "st2_artifact_hash", "a_elo_diff", "st2_elo_diff",
    "a_p_away", "a_p_draw", "a_p_home", "st2_p_away", "st2_p_draw", "st2_p_home",
    "a_predicted_class", "st2_predicted_class",
)
IDENTITY_COLUMNS = ("fixture_key", "match_id", "home_club", "away_club")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PAGE_URL = re.compile(r"https://www\.jleague\.jp/match/j1/(2026|2027)/([0-9]{6})/\Z")
SAFE_FILE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


class DashboardFeedError(ValueError):
    """Technical stop: do not repair, impute, recover journals, or generate predictions."""


def require(condition, message):
    if not condition:
        raise DashboardFeedError(message)


def sha(body):
    return hashlib.sha256(body).hexdigest()


def rooted(root, relative):
    root = Path(root).resolve()
    path = root / relative
    require(path.resolve().is_relative_to(root), "Input path escapes repository")
    return path


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value),
        "Timezone-qualified ISO timestamp required")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise DashboardFeedError("Invalid timestamp") from None
    require(parsed.utcoffset() is not None, "Timezone required")
    return parsed


def calendar_date(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "Exact date required")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise DashboardFeedError("Invalid calendar date") from None
    return value


def kickoff_at(day, kickoff):
    calendar_date(day)
    require(isinstance(kickoff, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", kickoff),
            "Unambiguous kickoff HH:mm required")
    return f"{day}T{kickoff}:00+09:00"


def csv_frame(body, *, exact=None):
    try:
        reader = csv.reader(io.StringIO(body.decode("utf-8-sig")), strict=True)
        columns = next(reader, [])
        require(bool(columns) and len(set(columns)) == len(columns), "CSV header invalid")
        require(exact is None or tuple(columns) == tuple(exact), "CSV schema mismatch")
        rows = []
        for values in reader:
            require(len(values) == len(columns), "CSV row width mismatch")
            rows.append(values)
        return pd.DataFrame(rows, columns=columns, dtype=str)
    except (csv.Error, UnicodeError):
        raise DashboardFeedError("Malformed CSV") from None


def read_champion_predictions(path=None, *, body=None):
    """Parse by allowlisted indices, before any official result can be joined."""
    if body is None:
        body = Path(path).read_bytes()
    try:
        reader = csv.reader(io.StringIO(body.decode("utf-8-sig")), strict=True)
        header = next(reader, [])
        require(tuple(header) == MIXED_COLUMNS, "Frozen prediction CSV header mismatch")
        indices = [header.index(column) for column in PROJECTION_COLUMNS]
        version_index = header.index("comparison_version")
        projected = []
        for values in reader:
            require(len(values) == len(header), "Prediction CSV row width mismatch")
            require(values[version_index] == COMPARISON_VERSION, "Wrong comparison version")
            projected.append([values[index] for index in indices])
        # Forbidden cells are never converted, validated, logged or materialized as named fields.
        frame = pd.DataFrame(projected, columns=PROJECTION_COLUMNS, dtype=str)
    except (csv.Error, UnicodeError):
        raise DashboardFeedError("Malformed prediction CSV") from None
    require(not frame.fixture_key.duplicated().any() and not frame.match_id.duplicated().any(),
            "Duplicate saved prediction identity")
    for row in frame.itertuples(index=False):
        require(all(isinstance(value, str) and value and value == value.strip()
                    for value in row), "Blank or padded Champion projection field")
        require(row.champion_a_model_version == CHAMPION_VERSION, "Wrong Champion version")
        require(row.champion_a_artifact_hash == CHAMPION_HASH, "Wrong Champion artifact hash")
        require(HEX64.fullmatch(row.source_revision), "Invalid prediction source revision")
        require(re.fullmatch(r"j1_2026_2027:[a-z0-9_-]+:[a-z0-9_-]+", row.fixture_key),
                "Invalid saved fixture key")
        require(timestamp(row.prediction_generated_at) < timestamp(kickoff_at(row.match_date, row.kickoff)),
                "Saved prediction must precede kickoff")
        try:
            values = [float(getattr(row, f"a_p_{side}")) for side in ("home", "draw", "away")]
        except (ValueError, OverflowError):
            raise DashboardFeedError("Invalid Champion probabilities") from None
        require(all(math.isfinite(value) and 0 <= value <= 1 for value in values)
                and math.isclose(sum(values), 1, rel_tol=0, abs_tol=1e-12), "Invalid Champion probabilities")
    return frame


@dataclass(frozen=True)
class OfficialSource:
    revision_id: str
    manifest_sha: str
    manifest: dict
    schedule: pd.DataFrame
    completed: pd.DataFrame

    @property
    def observed_at(self):
        return self.manifest["summary"]["observed_at_utc"]


def read_official_revision(directory, master, *, expected_sha=None):
    """Read an accepted immutable revision and validate its official semantics."""
    directory = Path(directory).resolve()
    require(HEX64.fullmatch(directory.name), "Invalid revision identity")
    manifest_body = rooted(directory, "manifest.json").read_bytes()
    require(expected_sha is None or sha(manifest_body) == expected_sha, "Witness manifest SHA mismatch")
    manifest = json.loads(manifest_body)
    require(isinstance(manifest, dict) and isinstance(manifest.get("summary"), dict),
            "Official manifest schema invalid")
    require(manifest.get("format_version") in {"ongoing-v1", "ongoing-v2"}
            and manifest.get("completion_policy") == COMPLETION_POLICY
            and manifest.get("summary", {}).get("publication_status") == "published",
            "Unaccepted official revision")
    summary = manifest["summary"]
    observed = timestamp(summary["observed_at_utc"])
    require(observed.utcoffset().total_seconds() == 0, "Official observed_at_utc must use UTC")
    require(not summary.get("publication_blocks"), "Official publication has unresolved blocks")
    files = manifest.get("files")
    require(isinstance(files, dict) and {"schedule.csv", "completed_matches.csv", "fixture_identity.csv"} <= files.keys(),
            "Official revision file coverage missing")
    bodies = {}
    for name, digest in files.items():
        require(isinstance(name, str) and SAFE_FILE.fullmatch(name) and ".." not in name
                and isinstance(digest, str) and HEX64.fullmatch(digest), "Invalid manifest file entry")
        path = rooted(directory, name)
        bodies[name] = path.read_bytes()
        require(sha(bodies[name]) == digest, "Official manifest file hash mismatch")
    if "update_summary.json" in bodies:
        require(json.loads(bodies["update_summary.json"]) == summary, "Official summary projection mismatch")
    schedule = csv_frame(bodies["schedule.csv"])
    completed = csv_frame(bodies["completed_matches.csv"], exact=schedule.columns)
    identity = csv_frame(bodies["fixture_identity.csv"], exact=IDENTITY_COLUMNS)
    required = set(REQUIRED_COLUMNS) | {
        "fixture_key", "kickoff_time", "status", "competition_key", "competition", "stage",
        "home_club", "away_club", "evidence_type", "evidence_url", "evidence_sha256",
        "evidence_fetched_at_utc", "completion_origin_snapshot",
    }
    require(required <= set(schedule), "Official schedule schema incomplete")
    if manifest["format_version"] == "ongoing-v2":
        require({"match_page_id", "data_site_match_id", "match_id_namespace"} <= set(schedule),
                "Official v2 typed identity schema incomplete")
    require(schedule.fixture_key.is_unique and identity.fixture_key.is_unique, "Official fixture cardinality invalid")
    require(schedule[list(IDENTITY_COLUMNS)].sort_values("fixture_key").reset_index(drop=True).equals(
        identity.sort_values("fixture_key").reset_index(drop=True)), "Official fixture identity mismatch")
    require(schedule.status.isin(["scheduled", "candidate", "completed"]).all(), "Invalid official status")
    require(schedule.season.eq("2026").all() and schedule.competition_key.eq(COMPETITION_KEY).all()
            and schedule.competition.eq("Ｊ１").all() and schedule.stage.eq("full_season").all(),
            "Source is not ordinary 2026/27 J1")
    normalized = []
    for row in schedule.to_dict("records"):
        calendar_date(row["match_date"])
        require("2026-08-01" <= row["match_date"] <= "2027-06-30", "Official date outside season")
        require(row["home_club"] != row["away_club"]
                and re.fullmatch(r"[a-z0-9_-]+", row["home_club"])
                and re.fullmatch(r"[a-z0-9_-]+", row["away_club"])
                and row["fixture_key"] == f"{COMPETITION_KEY}:{row['home_club']}:{row['away_club']}",
                "Directional official fixture key mismatch")
        try:
            row["round"] = int(row["round"])
        except ValueError:
            raise DashboardFeedError("Invalid official round") from None
        for field in ("match_id", "match_page_id", "data_site_match_id", "match_id_namespace"):
            row[field] = row.get(field) or None
        if manifest["format_version"] == "ongoing-v2":
            scalar = (row["match_id"], row["match_id_namespace"])
            apply_operational_identity(row)
            require((row["match_id"], row["match_id_namespace"]) == scalar, "Official typed identity conflict")
        normalized.append(row)
    validate_fixture_coverage(normalized)
    expected = schedule.loc[schedule.status.eq("completed")].reset_index(drop=True)
    require(expected.equals(completed.reset_index(drop=True)), "Completed subset differs from schedule")
    if "total_fixtures" in summary:
        require(summary["total_fixtures"] == len(schedule), "Official population mismatch")
    if "counts" in summary:
        require(summary["counts"] == {status: int(schedule.status.eq(status).sum())
                for status in ("scheduled", "candidate", "completed")}, "Official status counts mismatch")
    if "result_validation" in summary:
        require(summary["result_validation"] == ("passed" if len(completed) else "no_completed_matches"),
                "Official result validation status mismatch")
    if not completed.empty:
        validate_matches(completed)
        for row in completed.itertuples(index=False):
            require(row.evidence_type == "official_game_over_section" and PAGE_URL.fullmatch(row.evidence_url),
                    "Explicit official game-over proof required")
            require(HEX64.fullmatch(row.evidence_sha256) and bool(row.completion_origin_snapshot),
                    "Completed provenance incomplete")
            require(timestamp(kickoff_at(row.match_date, row.kickoff_time))
                    <= timestamp(row.evidence_fetched_at_utc) <= observed
                    and row.match_date <= observed.astimezone(ZoneInfo("Asia/Tokyo")).date().isoformat()
                    and timestamp(kickoff_at(row.match_date, row.kickoff_time)) <= observed,
                    "Completed result unavailable at source observation")
            page = PAGE_URL.fullmatch(row.evidence_url)
            if getattr(row, "match_page_id", ""):
                require(page[2] == row.match_page_id, "Completion page identity conflict")
    # Resolve exact registered aliases on all official rows, not a convenient ID subset.
    for side in ("home", "away"):
        schedule[f"{side}_team_id"] = [master.resolve_team_id(name, on=day)
            for name, day in zip(schedule[f"{side}_team"], schedule.match_date)]
    require(not schedule.home_team_id.eq(schedule.away_team_id).any(), "Official team identity conflict")
    return OfficialSource(directory.name, sha(manifest_body), manifest, schedule, completed)


def validate_binding_coverage(predictions, bindings):
    validate_prediction_bindings(bindings)
    selected = bindings.loc[bindings.prediction_artifact.eq(PREDICTION_ARTIFACT)]
    require(selected.model_version.eq(COMPARISON_VERSION).all(), "Wrong sidecar comparison version")
    require(len(selected) == len(predictions), "Missing or orphan prediction binding")
    require(selected.prediction_match_id.is_unique, "Duplicate sidecar prediction ID")
    by_id = selected.set_index("prediction_match_id")
    require(set(by_id.index) == set(predictions.match_id), "Binding coverage mismatch")
    for row in predictions.itertuples(index=False):
        binding = by_id.loc[row.match_id]
        require(all(binding[column] == getattr(row, column) for column in (
            "fixture_key", "match_date", "home_team_id", "away_team_id", "prediction_generated_at")),
            "Prediction sidecar identity conflict")
        require(HEX64.fullmatch(binding.identity_witness_revision_id)
                and HEX64.fullmatch(binding.identity_witness_manifest_sha256), "Invalid witness identity")
    return by_id


def build_dashboard_feed(repository_root=ROOT):
    """Construct the entire feed before writing anything; inputs remain read-only."""
    root = Path(repository_root).resolve()
    prediction_path, binding_path, master_path = [rooted(root, path) for path in (
        PREDICTION_ARTIFACT, BINDING_PATH, TEAM_MASTER_PATH)]
    journal = binding_path.with_name(f".{binding_path.name}.journal.json")
    lock = binding_path.with_name(f".{binding_path.name}.lock")
    require(not journal.exists() and not lock.exists(), "Prediction append pending; read-only adapter cannot recover")
    snapshots = {path: path.read_bytes() for path in (prediction_path, binding_path, master_path)}
    predictions = read_champion_predictions(body=snapshots[prediction_path])
    bindings = csv_frame(snapshots[binding_path], exact=BINDING_COLUMNS)
    by_id = validate_binding_coverage(predictions, bindings)
    master = load_team_master(master_path)
    names = {alias.team_id: alias.canonical_name for alias in master.aliases}
    ongoing = rooted(root, ONGOING_PATH)
    pointer_path = rooted(ongoing, "latest.json")
    pointer_body = pointer_path.read_bytes()
    pointer = json.loads(pointer_body)
    require(HEX64.fullmatch(pointer["revision_id"]) and HEX64.fullmatch(pointer["manifest_sha256"]),
            "Invalid latest pointer")
    # Scope every manifested path before the generic reader performs its own hash reads.
    current = read_official_revision(rooted(ongoing, f"revisions/{pointer['revision_id']}"), master,
                                     expected_sha=pointer["manifest_sha256"])
    latest = read_latest(ongoing)  # Existing generic read-only publication/hash validation.
    require(latest is not None and latest[0].name == pointer["revision_id"], "Latest pointer changed")
    cache = {current.revision_id: current}

    def revision(identity, digest=None):
        require(isinstance(identity, str) and HEX64.fullmatch(identity), "Invalid source revision identity")
        if identity not in cache:
            cache[identity] = read_official_revision(rooted(ongoing, f"revisions/{identity}"), master,
                                                    expected_sha=digest)
        item = cache[identity]
        require(digest is None or item.manifest_sha == digest, "Witness manifest SHA mismatch")
        require(timestamp(item.observed_at) <= timestamp(current.observed_at), "Source newer than current publication")
        return item

    joined = []  # Only Champion projection + safe official identity/score fields.
    official_by_key = current.schedule.set_index("fixture_key")
    completed_by_key = current.completed.set_index("fixture_key")
    for row in predictions.itertuples(index=False):
        binding = by_id.loc[row.match_id]
        source = revision(row.source_revision)
        witness = revision(binding.identity_witness_revision_id, binding.identity_witness_manifest_sha256)
        require(timestamp(witness.observed_at) <= timestamp(source.observed_at)
                and timestamp(source.observed_at) <= timestamp(row.prediction_generated_at),
                "Saved prediction precedes its identity/source evidence")
        for evidence in (source, witness):
            rows = evidence.schedule.loc[evidence.schedule.fixture_key.eq(row.fixture_key)]
            require(len(rows) == 1, "Saved fixture missing from source/witness")
            observed_row = rows.iloc[0]
            require(all(observed_row[column] == getattr(row, column) for column in (
                "match_date", "home_team_id", "away_team_id")), "Source/witness fixture conflict")
            require(observed_row.kickoff_time == row.kickoff, "Source/witness kickoff conflict")
        witness_row = witness.schedule.loc[witness.schedule.fixture_key.eq(row.fixture_key)].iloc[0]
        require(witness_row.match_id == row.match_id, "Witness prediction ID conflict")
        namespace = binding.prediction_id_namespace
        if witness.manifest["format_version"] == "ongoing-v2":
            require(witness_row.match_id_namespace == namespace, "Witness namespace conflict")
        else:
            page = PAGE_URL.fullmatch(witness_row.evidence_url)
            require(namespace == MATCH_PAGE_NAMESPACE and page is not None and page[2] == row.match_id
                    and witness_row.evidence_type in {"official_scheduled_identity", "official_completion_unconfirmed", "official_game_over_section"},
                    "Witness v1 explicit page namespace proof missing")
        if namespace == MATCH_PAGE_NAMESPACE or witness_row.evidence_fetched_at_utc:
            require(HEX64.fullmatch(witness_row.evidence_sha256)
                    and timestamp(witness_row.evidence_fetched_at_utc) <= timestamp(witness.observed_at),
                    "Witness evidence provenance invalid")
        for side in ("home", "away"):
            identity, display_name = getattr(row, f"{side}_team_id"), getattr(row, f"{side}_team_name")
            require(identity in names, "Prediction TeamMaster ID missing")
            if display_name != names[identity]:
                require(master.resolve_team_id(display_name, on=row.match_date) == identity,
                        "Prediction display name does not resolve to its TeamMaster ID")
        require(row.fixture_key in official_by_key.index, "Saved fixture missing from current schedule")
        official = official_by_key.loc[row.fixture_key]  # Never join by an external match ID.
        require(all(official[f"{side}_team_id"] == getattr(row, f"{side}_team_id") for side in ("home", "away")),
                "Current official home/away identity conflict")
        require(bool(official.match_id), "Saved fixture has no current official ID; no ID-available subset")
        match = {
            "id": row.fixture_key,
            "homeTeam": {"id": row.home_team_id, "name": names[row.home_team_id]},
            "awayTeam": {"id": row.away_team_id, "name": names[row.away_team_id]},
            "kickoffAt": kickoff_at(official.match_date, official.kickoff_time),
            "prediction": {"source": "saved_pre_match", "generatedAt": row.prediction_generated_at,
                "probabilities": {side: float(getattr(row, f"a_p_{side}")) * 100
                                  for side in ("home", "draw", "away")}},
        }
        require(timestamp(row.prediction_generated_at) < timestamp(match["kickoffAt"]),
                "Saved prediction must precede current official kickoff")
        if official.status == "completed":
            result = completed_by_key.loc[row.fixture_key]
            match["result"] = {"homeScore": int(result.home_score), "awayScore": int(result.away_score)}
        joined.append((official.match_date, official.status == "completed", match))

    # No missing saved rows may be backfilled or silently dropped from a frozen date batch.
    for day, batch in predictions.groupby("match_date", sort=False):
        require(batch.source_revision.nunique() == 1 and batch.prediction_generated_at.nunique() == 1,
                "Split saved prediction date batch")
        source = revision(batch.source_revision.iloc[0])
        expected = source.schedule.loc[source.schedule.match_date.eq(day) & ~source.schedule.status.eq("completed")]
        require(set(batch.fixture_key) == set(expected.fixture_key), "Partial saved prediction date batch")

    payload = {"schemaVersion": 1, "mode": "operational", "model": dict(CHAMPION_MODEL),
               "updatedAt": current.observed_at}
    for previous, key, label in ((True, "previousRound", "前節"), (False, "nextRound", "次節")):
        candidates = [item for item in joined if item[1] == previous]
        selected_day = (max if previous else min)(item[0] for item in candidates) if candidates else None
        selected = sorted((item[2] for item in candidates if item[0] == selected_day), key=lambda match: match["id"])
        payload[key] = {"label": f"{label} · {selected_day}" if selected_day else label, "matches": selected}
    validate_dashboard_data(payload)  # Exact recursive output schema is also the research leak firewall.
    require(all(path.read_bytes() == body for path, body in snapshots.items())
            and pointer_path.read_bytes() == pointer_body and not journal.exists() and not lock.exists(),
            "Input publication changed during adapter read")
    return payload


def write_dashboard_feed(payload, output):
    """Validate first, then flush/fsync a same-directory temporary file and replace."""
    validate_dashboard_data(payload)
    body = (json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
    output = Path(output)
    require(output.suffix.lower() == ".json", "Dashboard output must be JSON")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{output.name}-", suffix=".tmp", dir=output.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as target:
            target.write(body)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None, *, repository_root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help=f"Validated JSON destination (default: {OUTPUT_PATH})")
    args = parser.parse_args(argv)
    try:
        root = Path(repository_root).resolve()
        output = args.output if args.output is not None else rooted(root, OUTPUT_PATH)
        protected = ("models", "data/raw", "data/master", "data/processed/predictions", ONGOING_PATH)
        require(not any(output.resolve().is_relative_to(root / path) for path in protected), "Output overlaps protected inputs")
        payload = build_dashboard_feed(root)
        write_dashboard_feed(payload, output)
    except Exception:
        # Never echo source cells or exception excerpts from the mixed research CSV.
        print("Dashboard feed TECHNICAL STOP; inputs or output validation failed.", file=sys.stderr)
        return 1
    print("Champion-only dashboard feed written; no predictions or metrics generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
