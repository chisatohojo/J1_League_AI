"""Synthetic-only weekend reservation, frozen Elo, and atomic versioned batches.

No HTTP, model deserializer, production entry point, or activation switch.
The normal updater rejects an enabled policy without an explicit temporary
workspace and marked synthetic estimator. Production integration is a later task.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import uuid
from zoneinfo import ZoneInfo

import pandas as pd

from scripts import build_dashboard_feed as feed
from src.collect.teams import load_team_master
from src.modeling.champion_prediction import TARGET_COLUMNS, replay_ratings, probability_rows
from src.modeling.prediction_identity import BINDING_COLUMNS

POLICY = "weekend_snapshot_v1"
FORMAT = "champion-weekend-v2"
PREFIX = "weekend-v2-"
SCOPE = "SYNTHETIC_ONLY"
JST = ZoneInfo("Asia/Tokyo")


def need(condition, reason):
    feed.require(condition, "weekend_" + reason)


def body(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(body(value)).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stamp(value):
    return feed.timestamp(value.isoformat() if isinstance(value, datetime) else value)


def utc(value):
    return stamp(value).astimezone(timezone.utc).isoformat()


def safe(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        need(not item.is_symlink() and not item.is_junction(), "linked_path")
    return path


def write_new(path, data):
    path = safe(path)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    need(path.read_bytes() == data, "write_readback")


@contextmanager
def publication_lock(runtime):
    """Shared by legacy and weekend publishers; abandoned locks are not reclaimed."""
    path = safe(Path(runtime) / "prediction-publication.lock")
    token = body(dict(pid=os.getpid(), nonce=uuid.uuid4().hex))
    write_new(path, token)
    try:
        yield
    finally:
        need(path.read_bytes() == token, "publication_lock_changed")
        path.unlink()


def read_json(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            need(key not in out, "duplicate_json_key")
            out[key] = value
        return out
    return json.loads(safe(path).read_bytes(), object_pairs_hook=unique)


def period(friday):
    start = date.fromisoformat(feed.calendar_date(friday))
    need(start.weekday() == 4, "friday_required")
    return dict(start=str(start), end=str(start + timedelta(days=3)),
                history_cutoff=f"{start}T00:00:00+09:00", information_cutoff=f"{start}T07:00:00+09:00")


def policy(config):
    value = config.get("weekend_policy", {"enabled": False})
    need(isinstance(value, dict) and type(value.get("enabled")) is bool, "policy_schema")
    if not value["enabled"]:
        need(set(value) == {"enabled"}, "disabled_policy_schema")
        return None
    need(set(value) == {"enabled", "friday", "deadline_seconds"}, "policy_schema")
    need(type(value["deadline_seconds"]) is int and 1 <= value["deadline_seconds"] <= 900, "deadline")
    period(value["friday"])
    return dict(value)


def target_identity(current, window):
    need(current.manifest["format_version"] == "ongoing-v2", "typed_publication_required")
    rows = current.schedule.loc[current.schedule.match_date.between(window["start"], window["end"])].copy()
    need(not rows.empty and len(rows) <= 40, "target_count")
    need(rows.status.eq("scheduled").all(), "target_not_scheduled")
    need(rows[["home_score", "away_score", "result"]].eq("").all().all(), "unexpected_target_result")
    need(rows.fixture_key.is_unique and rows.match_id.is_unique, "duplicate_target")
    need(rows.match_id.astype(str).ne("").all() and rows.match_id_namespace.isin(
        [feed.MATCH_PAGE_NAMESPACE, feed.DATA_SITE_NAMESPACE]).all(), "typed_identity")
    teams = pd.concat([rows.home_team_id, rows.away_team_id])
    need(teams.is_unique, "multiple_appearances_require_review")
    return rows.sort_values("fixture_key").loc[:, list(TARGET_COLUMNS)].to_dict("records")


def verify_publication(current, runtime):
    need(feed.HEX64.fullmatch(current.revision_id) and feed.HEX64.fullmatch(current.manifest_sha), "revision_identity")
    pointer = safe(runtime / "official/latest.json")
    expected = {"revision_id": current.revision_id, "manifest_sha256": current.manifest_sha}
    need(read_json(pointer) == expected, "revision_changed")
    directory = runtime / "official/revisions" / current.revision_id
    need(sha(safe(directory / "manifest.json")) == current.manifest_sha, "manifest_changed")
    need(read_json(directory / "manifest.json") == current.manifest, "manifest_changed")
    pins = {str(pointer): sha(pointer), str(directory / "manifest.json"): current.manifest_sha}
    for name, h in current.manifest["files"].items():
        need(feed.SAFE_FILE.fullmatch(name) and ".." not in name, "source_filename")
        p = safe(directory / name)
        need(sha(p) == h, "source_sha")
        pins[str(p)] = h
    raw = feed.csv_frame((directory / "schedule.csv").read_bytes())
    completed = feed.csv_frame((directory / "completed_matches.csv").read_bytes())
    def ordered(frame):
        return frame.sort_values("fixture_key").reset_index(drop=True)
    need(ordered(current.schedule.loc[:, list(raw.columns)]).equals(ordered(raw)), "schedule_projection")
    need(ordered(current.completed).equals(ordered(completed)), "result_projection")
    return pins


def check_pins(pins):
    need(all(safe(p).is_file() and sha(p) == h for p, h in pins.items()), "input_sha_changed")


@dataclass(frozen=True)
class SyntheticWorkspace:
    root: Path

    @classmethod
    def create(cls, root):
        root = safe(root)
        need(root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()), "temporary_workspace_required")
        root.mkdir()  # exclusive; never adopt an existing output or production runtime
        write_new(root / "scope.json", body({"scope": SCOPE, "format": FORMAT}))
        return cls(root)

    def check(self, source, runtime):
        need(safe(self.root).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()), "temporary_workspace_required")
        need(read_json(self.root / "scope.json") == {"scope": SCOPE, "format": FORMAT}, "scope_marker")
        need(safe(runtime).resolve().is_relative_to(self.root.resolve()), "runtime_outside_sandbox")
        # Synthetic fixture repositories may be siblings of the temporary output.
        need(safe(source).resolve().parent == self.root.resolve().parent, "source_outside_sandbox")


@dataclass
class Prepared:
    targets: pd.DataFrame
    values: object
    context: dict
    pins: dict


class OfflineWeekendBackend:
    """Explicit test capability, never constructed by the operational CLI."""

    batch_format = FORMAT
    batch_prefix = PREFIX

    def verify_source(self, current):
        return verify_publication(current, self.runtime)

    def before_inference(self, current, snapshot, pins, clock):
        pass

    def before_commit(self, prepared, records, bindings, clock):
        return {}

    def manifest_extension(self, prepared):
        return {}

    def before_visibility(self, prepared, clock):
        pass

    def __init__(self, workspace, artifact, special, witnesses):
        need(isinstance(workspace, SyntheticWorkspace), "workspace_required")
        need(getattr(artifact.model, "synthetic_only", False) is True
             and getattr(artifact.scaler, "synthetic_only", False) is True, "synthetic_estimator_required")
        self.workspace, self.artifact = workspace, artifact
        self.special = special.copy(deep=True)
        self.witnesses = witnesses

    def bind(self, source, runtime, config):
        self.workspace.check(source, runtime)
        self.source, self.runtime, self.config = Path(source), Path(runtime), policy(config)
        need(self.config is not None, "enabled_policy_required")
        self.window = period(self.config["friday"])

    def reserve(self, current, saved, now):
        identity = target_identity(current, self.window)
        ids = {r["fixture_key"] for r in identity}
        existing = ids & {r["fixture_key"] for r in saved}
        directory = safe(self.runtime / "weekend-reservations")
        directory.mkdir(exist_ok=True)
        path = directory / (self.window["start"] + ".json")
        if path.exists():
            reservation = read_json(path)
            need(set(reservation) == {"policy", "scope", "period", "targets", "created_at", "source_revision", "source_manifest_sha256"}, "reservation_schema")
            need(reservation["scope"] == SCOPE and reservation["policy"] == POLICY and reservation["period"] == self.window
                 and reservation["targets"] == identity, "HOLD_REVIEW_ON_SCHEDULE_CHANGE")
            need(stamp(reservation["created_at"]) <= now, "reservation_clock")
            need(stamp(reservation["created_at"]) < stamp(self.window["information_cutoff"]) - timedelta(days=2), "late_reservation")
            return reservation, sha(path)
        need(not existing, "partial_or_legacy_saved")
        need(stamp(current.observed_at) <= now, "future_reservation_source")
        need(now < stamp(self.window["information_cutoff"]) - timedelta(days=2), "late_reservation")
        reservation = dict(policy=POLICY, scope=SCOPE, period=self.window, targets=identity,
                           created_at=utc(now), source_revision=current.revision_id,
                           source_manifest_sha256=current.manifest_sha)
        write_new(path, body(reservation))
        return reservation, sha(path)

    def review(self, current, saved):
        """Read-only applicability audit; safe for evening without inference."""
        self.verify_source(current)
        # Natural completion/typed-namespace transition never causes a second
        # forecast. Validate applicability separately from frozen source time.
        published = []
        for directory in (self.runtime / "batches").glob(PREFIX + "*"):
            item = read_batch(directory)
            if item[2]["period"] == self.window:
                published.append(item)
        if published:
            need(len(published) == 1, "duplicate_published_group")
            records, _, _, context = published[0]
            reservation_path = self.runtime / "weekend-reservations" / (self.window["start"] + ".json")
            need(sha(safe(reservation_path)) == context["reservation_sha256"], "reservation_changed")
            reservation = read_json(reservation_path)
            expected = context["snapshot"]["targets"]
            need(reservation["targets"] == expected, "reservation_changed")
            scope = current.schedule.loc[current.schedule.match_date.between(self.window["start"], self.window["end"])]
            keys = {r["fixture_key"] for r in expected}
            need(set(scope.fixture_key) == keys and scope.status.isin(["scheduled", "completed"]).all(), "HOLD_REVIEW_ON_SCHEDULE_CHANGE")
            bykey = scope.set_index("fixture_key")
            for target in expected:
                row = bykey.loc[target["fixture_key"]]
                need(all(row[k] == target[k] for k in ("match_date", "kickoff_time", "home_team_id", "away_team_id")), "HOLD_REVIEW_ON_SCHEDULE_CHANGE")
                original_field = "match_page_id" if target["match_id_namespace"] == feed.MATCH_PAGE_NAMESPACE else "data_site_match_id"
                need(row[original_field] == target["match_id"], "saved_typed_identity_conflict")
            need([r for r in saved if r["fixture_key"] in keys] == records, "saved_values_changed")
            return True
        reservation_path = self.runtime / "weekend-reservations" / (self.window["start"] + ".json")
        if reservation_path.exists():
            r = read_json(reservation_path)
            need(r["period"] == self.window and r["policy"] == POLICY and r["scope"] == SCOPE
                 and r["targets"] == target_identity(current, self.window), "HOLD_REVIEW_ON_SCHEDULE_CHANGE")
            need(not {r["fixture_key"] for r in r["targets"]} & {row["fixture_key"] for row in saved}, "partial_or_legacy_saved")
        return False

    def prepare(self, current, saved, now, clock):
        if self.review(current, saved):
            return None
        reservation, reservation_sha = self.reserve(current, saved, now)
        targets = pd.DataFrame(reservation["targets"], columns=TARGET_COLUMNS)
        keys = set(targets.fixture_key)
        present = keys & {r["fixture_key"] for r in saved}
        need(not present, "partial_or_legacy_saved")
        if now.astimezone(JST).date().isoformat() < self.window["start"]:
            return None  # reservation excludes these dates from daily selection
        cutoff = stamp(self.window["information_cutoff"])
        need(now.astimezone(JST).date().isoformat() == self.window["start"] and now >= cutoff, "friday_execution_required")
        need((now - cutoff).total_seconds() <= self.config["deadline_seconds"], "missed_execution_deadline")
        need(all(now < stamp(feed.kickoff_at(r.match_date, r.kickoff_time)) for r in targets.itertuples()), "kickoff_elapsed")
        need(stamp(current.observed_at) <= cutoff and cutoff - stamp(current.observed_at) <= timedelta(hours=24), "source_not_available_at_0700")
        past = current.schedule.loc[current.schedule.match_date.lt(self.window["start"])]
        need(past.status.eq("completed").all(), "history_incomplete")
        # Never consume any target-period result, even from a later publication.
        need(current.completed.match_date.lt(self.window["start"]).all(), "future_result_in_snapshot")
        for row in current.completed.itertuples():
            need(row.evidence_sha256 and stamp(row.evidence_fetched_at_utc) <= cutoff, "history_evidence_unavailable")
        pins = self.verify_source(current)
        reservation_path = self.runtime / "weekend-reservations" / (self.window["start"] + ".json")
        pins[str(reservation_path)] = reservation_sha
        need(set(self.witnesses) == {"training", "special", "teams", "estimator"}, "input_evidence_missing")
        for witness in self.witnesses.values():
            need(set(witness) == {"path", "sha256", "fetched_at_utc"}, "input_evidence_schema")
            need(safe(witness["path"]).resolve().is_relative_to(self.workspace.root.parent.resolve()), "input_outside_sandbox")
            need(stamp(witness["fetched_at_utc"]) <= cutoff, "input_evidence_unavailable")
            pins[str(witness["path"])] = witness["sha256"]
        check_pins(pins)
        need(self.artifact.training.to_csv(index=False, lineterminator="\n").encode() == Path(self.witnesses["training"]["path"]).read_bytes(), "training_projection")
        need(self.special.to_csv(index=False, lineterminator="\n").encode() == Path(self.witnesses["special"]["path"]).read_bytes(), "special_projection")
        need(Path(self.witnesses["teams"]["path"]).resolve() == (self.source / feed.TEAM_MASTER_PATH).resolve(), "team_master_witness")
        master = load_team_master(self.source / feed.TEAM_MASTER_PATH)
        from src.features.elo_history import _prepare_ongoing_matches
        ongoing = _prepare_ongoing_matches(current.completed, master, current.observed_at)
        ordered = []
        for segment, frame in (("training", self.artifact.training), ("special", self.special), ("ongoing", ongoing)):
            normalized = frame.copy()
            normalized["match_date"] = pd.to_datetime(normalized.match_date).dt.strftime("%Y-%m-%d")
            for row in normalized.sort_values(["match_date", "match_id"], kind="stable").astype(str).to_dict("records"):
                ordered.append({"segment": segment, "row": row})
        # Uses the frozen operational replay, explicitly K30/HA175, exactly once.
        ratings = replay_ratings(self.artifact.training, self.special, ongoing, master, self.window["start"])
        need(all(math.isfinite(v) for v in ratings.values()), "nonfinite_ratings")
        snapshot = dict(policy=POLICY, scope=SCOPE, period=self.window, frozen_at=utc(now),
                        official_revision=current.revision_id, official_manifest_sha256=current.manifest_sha,
                        source_observed_at=current.observed_at, targets=reservation["targets"],
                        history_events_sha256=digest(ordered), history_count=len(ordered),
                        ratings=ratings, ratings_sha256=digest(ratings),
                        elo_parameters=dict(initial=1500, K=30, home_advantage=175, season_reset=False),
                        features={r.fixture_key: ratings[r.home_team_id] - ratings[r.away_team_id] for r in targets.itertuples()},
                        input_sha256={name: w["sha256"] for name, w in self.witnesses.items()},
                        input_acquired_utc={name: utc(w["fetched_at_utc"]) for name, w in self.witnesses.items()},
                        code_sha256={"weekend_batch": sha(Path(__file__)), "champion_prediction": sha(Path(__file__).with_name("champion_prediction.py"))},
                        model_identity=dict(version=feed.CHAMPION_VERSION, artifact_hash=feed.CHAMPION_HASH, estimator_scope=SCOPE))
        for file in (Path(__file__), Path(__file__).with_name("champion_prediction.py")):
            pins[str(file)] = sha(file)
        attempts = safe(self.runtime / "weekend-attempts")
        attempts.mkdir(exist_ok=True)
        snapshot_id = digest(snapshot)
        write_new(attempts / (self.window["start"] + ".json"), body(dict(snapshot_id=snapshot_id, started_at=utc(now))))
        self.before_inference(current, snapshot, pins, clock)
        need(digest(snapshot) == snapshot_id, "snapshot_changed_during_preflight")
        check_pins(pins)
        ready = stamp(clock())
        need(ready >= now, "clock_moved_backwards")
        need((ready - cutoff).total_seconds() <= self.config["deadline_seconds"], "inference_deadline")
        need(all(ready < stamp(feed.kickoff_at(r.match_date, r.kickoff_time)) for r in targets.itertuples()), "kickoff_elapsed")
        values = probability_rows(self.artifact, targets, ratings)
        generated = stamp(clock())
        need(generated >= ready, "clock_moved_backwards")
        context = dict(scope=SCOPE, snapshot=snapshot, snapshot_id=digest(snapshot),
                       reservation_sha256=reservation_sha, generated_at=utc(generated))
        return Prepared(targets, values, context, pins)

    def commit(self, prepared, records, bindings, clock, fault=lambda point: None):
        need(records and len(records) == len(prepared.targets) == len(bindings), "batch_count")
        need({r["fixture_key"] for r in records} == set(prepared.targets.fixture_key), "batch_fixture_set")
        expected = {r.fixture_key: values for r, values in zip(prepared.targets.itertuples(), prepared.values)}
        need(all(set(r) == set(feed.CHAMPION_COLUMNS) and all(float(r["a_p_" + side]) == float(expected[r["fixture_key"]][index])
                 for index, side in enumerate(("away", "draw", "home"))) for r in records), "output_prediction_changed")
        check_pins(prepared.pins)
        need(all(r["prediction_generated_at"] == prepared.context["generated_at"] for r in records), "generated_time")
        extra_files = self.before_commit(prepared, records, bindings, clock)
        need(all(all(float(r["a_p_" + side]) == float(expected[r["fixture_key"]][index])
                     for index, side in enumerate(("away", "draw", "home"))) for r in records), "output_prediction_changed")
        directory = safe(self.runtime / (".pending-" + PREFIX + uuid.uuid4().hex))
        directory.mkdir()
        # A failed stage is retained for inspection, never silently resumed/deleted.
        csvs = {"predictions.csv": pd.DataFrame(records, columns=feed.CHAMPION_COLUMNS).to_csv(index=False, lineterminator="\n").encode(),
                "bindings.csv": pd.DataFrame(bindings, columns=BINDING_COLUMNS).to_csv(index=False, lineterminator="\n").encode(),
                "snapshot.json": body(prepared.context), **extra_files}
        for name, data in csvs.items():
            fault("before_" + name)
            write_new(directory / name, data)
            fault("after_" + name)
        committed = stamp(clock())
        need(committed >= stamp(prepared.context["generated_at"]), "clock_moved_backwards")
        need((committed - stamp(self.window["information_cutoff"])).total_seconds() <= self.config["deadline_seconds"], "commit_deadline")
        need(all(committed < stamp(feed.kickoff_at(r["match_date"], r["kickoff"])) for r in records), "kickoff_elapsed_before_commit")
        manifest = dict(format_version=self.batch_format, scope=SCOPE, policy=POLICY, period=self.window,
                        official_revision=prepared.context["snapshot"]["official_revision"],
                        official_manifest_sha256=prepared.context["snapshot"]["official_manifest_sha256"],
                        fixture_set_sha256=digest(sorted(r["fixture_key"] for r in records)),
                        snapshot_id=prepared.context["snapshot_id"], model_identity=prepared.context["snapshot"]["model_identity"],
                        input_sha256=prepared.context["snapshot"]["input_sha256"],
                        generated_at=prepared.context["generated_at"], committed_at=utc(committed),
                        count=len(records), completeness="PASS", commit_state="COMMITTED",
                        files={n: hashlib.sha256(data).hexdigest() for n, data in csvs.items()})
        manifest.update(self.manifest_extension(prepared))
        fault("before_manifest")
        write_new(directory / "manifest.json", body(manifest))
        read_batch(directory, staging=True)
        fault("before_publish")
        with publication_lock(self.runtime):
            from scripts.update_champion_dashboard import saved_batches
            existing, _ = saved_batches(self.runtime)
            batches = safe(self.runtime / "batches")
            batches.mkdir(exist_ok=True)
            need(not any(read_batch(p)[2]["period"] == self.window for p in batches.glob(PREFIX + "*")), "already_published")
            need(not {r["fixture_key"] for r in existing} & {r["fixture_key"] for r in records}, "concurrent_saved_overlap")
            check_pins(prepared.pins)
            self.before_visibility(prepared, clock)
            read_batch(directory, staging=True)
            publication_check = stamp(clock())
            need(publication_check >= committed and (publication_check - stamp(self.window["information_cutoff"])).total_seconds() <= self.config["deadline_seconds"]
                 and all(publication_check < stamp(feed.kickoff_at(r["match_date"], r["kickoff"])) for r in records), "publication_clock")
            destination = batches / (self.batch_prefix + hashlib.sha256(body(manifest)).hexdigest())
            directory.rename(destination)  # single same-filesystem visibility boundary
        return destination


def read_batch(directory, *, staging=False):
    directory = safe(directory)
    manifest_body = safe(directory / "manifest.json").read_bytes()
    m = read_json(directory / "manifest.json")
    if m.get("format_version") == "champion-weekend-v2-source-v1":
        from src.modeling.weekend_integration import read_bound_batch
        return read_bound_batch(directory, staging=staging)
    need(set(m) == {"format_version", "scope", "policy", "period", "official_revision", "official_manifest_sha256", "fixture_set_sha256", "snapshot_id", "model_identity", "input_sha256", "generated_at", "committed_at", "count", "completeness", "commit_state", "files"}, "manifest_schema")
    need(staging or directory.name == PREFIX + hashlib.sha256(manifest_body).hexdigest(), "manifest_address")
    need(m["format_version"] == FORMAT and m["scope"] == SCOPE and m["policy"] == POLICY
         and m["commit_state"] == "COMMITTED" and m["completeness"] == "PASS", "manifest_state")
    need(m["period"] == period(m["period"]["start"]), "manifest_period")
    need(set(m["files"]) == {"predictions.csv", "bindings.csv", "snapshot.json"}, "manifest_files")
    need({p.name for p in directory.iterdir()} == set(m["files"]) | {"manifest.json"}, "batch_files")
    for name, h in m["files"].items():
        need(sha(safe(directory / name)) == h, "batch_sha")
    c = read_json(directory / "snapshot.json")
    return validate_core(m, c, (directory / "predictions.csv").read_bytes(),
                         (directory / "bindings.csv").read_bytes())


def validate_core(m, c, predictions_body, bindings_body):
    """Shared v2 semantics; version-specific envelopes are validated by readers."""
    need(set(c) == {"scope", "snapshot", "snapshot_id", "reservation_sha256", "generated_at"}, "context_schema")
    s = c["snapshot"]
    need(set(s) == {"policy", "scope", "period", "frozen_at", "official_revision", "official_manifest_sha256", "source_observed_at", "targets", "history_events_sha256", "history_count", "ratings", "ratings_sha256", "elo_parameters", "features", "input_sha256", "input_acquired_utc", "code_sha256", "model_identity"}, "snapshot_schema")
    need(s["policy"] == POLICY and s["scope"] == SCOPE and s["elo_parameters"] == dict(initial=1500,K=30,home_advantage=175,season_reset=False), "snapshot_contract")
    need(s["model_identity"] == dict(version=feed.CHAMPION_VERSION,artifact_hash=feed.CHAMPION_HASH,estimator_scope=SCOPE), "model_identity")
    need(set(s["input_sha256"]) == set(s["input_acquired_utc"]) == {"training","special","teams","estimator"}, "snapshot_inputs")
    need(stamp(s["source_observed_at"]) <= stamp(s["period"]["information_cutoff"])
         and all(stamp(t) <= stamp(s["period"]["information_cutoff"]) for t in s["input_acquired_utc"].values()), "read_availability")
    cutoff = stamp(s["period"]["information_cutoff"])
    need(cutoff - stamp(s["source_observed_at"]) <= timedelta(hours=24), "read_source_stale")
    # Every permitted writer deadline is at most 900 seconds. A rehashed
    # manifest must not turn a later run into a valid Friday 07:00 batch.
    need(stamp(m["committed_at"]) <= cutoff + timedelta(seconds=900), "read_commit_deadline")
    need(c["scope"] == SCOPE and digest(s) == c["snapshot_id"] == m["snapshot_id"], "snapshot_sha")
    need(s["period"] == m["period"] and s["model_identity"] == m["model_identity"]
         and s["official_revision"] == m["official_revision"] and s["official_manifest_sha256"] == m["official_manifest_sha256"]
         and s["input_sha256"] == m["input_sha256"] and c["generated_at"] == m["generated_at"], "context_manifest_conflict")
    need(digest(s["ratings"]) == s["ratings_sha256"], "rating_map_sha")
    records = feed.csv_frame(predictions_body, exact=feed.CHAMPION_COLUMNS).to_dict("records")
    bindings = feed.csv_frame(bindings_body, exact=BINDING_COLUMNS).to_dict("records")
    frame = feed.read_champion_only_predictions(predictions_body)
    feed.validate_binding_coverage(frame, pd.DataFrame(bindings, columns=BINDING_COLUMNS), champion_only=True)
    need(type(m["count"]) is int and 1 <= m["count"] <= 40 and len(records) == len(bindings) == len(s["targets"]) == m["count"], "read_count")
    need(digest(sorted(r["fixture_key"] for r in records)) == m["fixture_set_sha256"], "read_fixture_set")
    targets = {r["fixture_key"]: r for r in s["targets"]}
    need(len(targets) == len(s["targets"]) and set(s["features"]) == set(targets), "feature_coverage")
    for key, t in targets.items():
        need(s["features"][key] == s["ratings"][t["home_team_id"]] - s["ratings"][t["away_team_id"]], "frozen_feature_value")
    for r in records:
        need(r["fixture_key"] in targets, "read_target")
        t = targets[r["fixture_key"]]
        need(all(r[k] == t[k] for k in ("fixture_key", "match_id", "match_date", "home_team_id", "away_team_id")) and r["kickoff"] == t["kickoff_time"], "read_identity")
        need(r["source_revision"] == m["official_revision"] and r["prediction_generated_at"] == m["generated_at"], "read_source")
        need(m["period"]["start"] <= r["match_date"] <= m["period"]["end"], "read_period_coverage")
        need(stamp(s["period"]["information_cutoff"]) <= stamp(s["frozen_at"]) <= stamp(m["generated_at"]) <= stamp(m["committed_at"]) < stamp(feed.kickoff_at(r["match_date"], r["kickoff"])), "read_chronology")
    for binding in bindings:
        need(binding["identity_witness_revision_id"] == m["official_revision"]
             and binding["identity_witness_manifest_sha256"] == m["official_manifest_sha256"]
             and binding["prediction_id_namespace"] == targets[binding["fixture_key"]]["match_id_namespace"], "binding_snapshot_conflict")
    return records, bindings, m, c
