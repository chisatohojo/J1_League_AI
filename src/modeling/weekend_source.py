"""Offline-only pre-cutoff publication receipts and explicitly pinned sources.

No collector, HTTP worker, estimator, updater activation or production entry point.
All writes require an exclusively created, marked system-temporary workspace.
Clock callbacks and fault injection belong to this synthetic capability only.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
import hashlib
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

from scripts import build_dashboard_feed as feed
from src.collect import jleague_ongoing as ongoing
from src.collect.teams import load_team_master
from src.modeling import weekend_batch as w

FORMAT = "weekend-source-publication-receipt-v1"
SCOPE = "SYNTHETIC_ONLY"
MAX_PAGES = 512                 # archived responses, not permission for HTTP
MAX_BODY = 2 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_REQUEST_SECONDS = 30
DEADLINE = 600


def need(value, reason):
    feed.require(value, "source_" + reason)


def utc(value):
    result = w.stamp(value)
    need(result.utcoffset().total_seconds() == 0, "UTC_required")
    return result


def name(value):
    need(isinstance(value, str) and feed.SAFE_FILE.fullmatch(value) and ".." not in value,
         "unsafe_filename")
    return value


def hash_value(value):
    need(isinstance(value, str) and feed.HEX64.fullmatch(value), "invalid_sha256")
    return value


def evidence_errors(function):
    """Missing/malformed evidence is a HOLD; never substitute timestamps/files."""
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, AttributeError, IndexError, FileNotFoundError) as error:
            raise feed.DashboardFeedError("source_evidence_missing_or_invalid") from error
    return checked


@dataclass(frozen=True)
class Workspace:
    root: Path

    @classmethod
    def create(cls, root):
        root = w.safe(root)
        need(root.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()), "temporary_only")
        root.mkdir()
        w.write_new(root / "scope.json", w.body(dict(format=FORMAT, scope=SCOPE)))
        return cls(root)

    def check(self):
        need(w.safe(self.root).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()), "temporary_only")
        need(w.read_json(self.root / "scope.json") == dict(format=FORMAT, scope=SCOPE), "workspace_marker")

    def input(self, root):
        self.check()
        root = w.safe(root)
        need(root.resolve().is_relative_to(self.root.parent.resolve()) and not root.resolve().is_relative_to(self.root.resolve()),
             "candidate_outside_synthetic_inputs")
        return root


class Clock:
    """Bounded wall/monotonic observations; no assertion of absolute clock truth."""
    def __init__(self, wall, monotonic=time.monotonic):
        self.wall, self.monotonic, self.samples = wall, monotonic, []

    def sample(self, event):
        wall, mono = utc(self.wall()), self.monotonic()
        need(isinstance(mono, (float, int)) and not isinstance(mono, bool) and math.isfinite(mono), "monotonic_invalid")
        if self.samples:
            last = self.samples[-1]
            dw = (wall - utc(last["utc"])).total_seconds()
            dm = mono - last["monotonic_seconds"]
            need(dw >= 0 and dm >= 0 and abs(dw - dm) <= 2, "clock_changed")
            elapsed = mono - self.samples[0]["monotonic_seconds"]
            need(abs((wall - utc(self.samples[0]["utc"])).total_seconds() - elapsed) <= 2, "clock_changed")
            need(elapsed <= DEADLINE, "deadline")
        self.samples.append(dict(event=event, utc=w.utc(wall), monotonic_seconds=mono))
        return wall


@contextmanager
def owner(workspace):
    workspace.check()
    path = workspace.root / "source-publication.lock"
    token = w.body(dict(pid=os.getpid(), nonce=uuid.uuid4().hex, scope=SCOPE))
    w.write_new(path, token)
    try:
        yield
    finally:
        need(path.read_bytes() == token, "lock_owner_changed")
        path.unlink()         # never adopt or reclaim another owner's lock


@evidence_errors
def inspect(root, revision, manifest_sha, friday):
    """Read one explicit revision and its raw provenance; never read latest."""
    root = w.safe(root)
    hash_value(revision); hash_value(manifest_sha)
    window = w.period(friday)
    cutoff = w.stamp(window["information_cutoff"])
    directory = root / "official/revisions" / revision
    files = {}

    def pin(path):
        path = w.safe(path)
        need(path.resolve().is_relative_to(root.resolve()), "input_escape")
        files[path.relative_to(root).as_posix()] = w.sha(path)
        return files[path.relative_to(root).as_posix()]

    need(pin(directory / "manifest.json") == manifest_sha, "manifest_sha")
    manifest = w.read_json(directory / "manifest.json")
    need(manifest["format_version"] == "ongoing-v2", "typed_publication_required")
    for filename, digest in manifest["files"].items():
        need(pin(directory / name(filename)) == hash_value(digest), "publication_payload_sha")
    pin(root / "teams.csv")
    master = load_team_master(root / "teams.csv")
    current = feed.read_official_revision(directory, master, expected_sha=manifest_sha)
    observed = utc(current.observed_at)
    need(observed <= cutoff and cutoff - observed <= timedelta(hours=24), "source_stale_or_after_cutoff")
    past = current.schedule.loc[current.schedule.match_date.lt(window["start"])]
    need(past.status.eq("completed").all(), "history_incomplete")
    need(current.completed.match_date.lt(window["start"]).all(), "future_result")
    targets = w.target_identity(current, window)
    snapshot_ids = {name(manifest["snapshot_id"])} | {name(v) for v in current.completed.completion_origin_snapshot}
    requests, parsed, snapshots = [], {}, {}
    total = 0
    for identity in sorted(snapshot_ids):
        folder = root / "snapshots" / identity
        snapshots[identity] = pin(folder / "manifest.json")
        # Strict duplicate JSON key checks precede the unchanged source parser.
        sm = w.read_json(folder / "manifest.json")
        for entry in sm["sources"]:
            raw, metadata = folder / name(entry["html"]), folder / name(entry["metadata"])
            pin(raw); pin(metadata)
            md = w.read_json(metadata)
            need({"request_started_at_utc", "fetched_at_utc"} <= md.keys(), "request_UTC_missing")
            started, finished = utc(md["request_started_at_utc"]), utc(md["fetched_at_utc"])
            need(started <= finished <= utc(sm["created_at_utc"]) <= cutoff, "source_chronology")
            need((finished - started).total_seconds() <= MAX_REQUEST_SECONDS, "request_timeout")
            need(raw.stat().st_size <= MAX_BODY and metadata.stat().st_size <= 65536, "body_cap")
            total += raw.stat().st_size
            need(total <= MAX_TOTAL and len(requests) < MAX_PAGES, "archive_limit")
            requests.append(dict(snapshot=identity, raw=raw.relative_to(root).as_posix(),
                metadata=metadata.relative_to(root).as_posix(), raw_sha256=entry["sha256"],
                metadata_sha256=entry["metadata_sha256"], request_started_at_utc=w.utc(started),
                fetched_at_utc=w.utc(finished), url=md["requested_url"], bytes=md["bytes"]))
        events = sorted([r for r in requests if r["snapshot"] == identity], key=lambda r: r["request_started_at_utc"])
        need(all(utc(a["fetched_at_utc"]) <= utc(b["request_started_at_utc"]) for a, b in zip(events, events[1:])), "parallel_requests")
        checked = ongoing._read_snapshot(folder, require_v2=True)
        parsed[identity] = ongoing._parse_snapshot(folder, checked)
        if identity == manifest["snapshot_id"]:
            need(manifest["run"]["snapshot_sha256"] == snapshots[identity]
                 and manifest["run"]["snapshot_id"] == identity
                 and manifest["summary"]["sources"] == sm["sources"], "snapshot_manifest_link")
            need(utc(sm["observed_at_utc"]) == observed, "observation_link")
    need(hashlib.sha256(ongoing._json(manifest["run"])).hexdigest() == revision, "revision_run_hash")
    raw_current = {r["fixture_key"]: r for r in parsed[manifest["snapshot_id"]]}
    need(set(raw_current) == set(current.schedule.fixture_key), "raw_fixture_coverage")
    facts = ("fixture_key", "home_club", "away_club", "round", "match_date", "kickoff_time")

    def same(a, b, keys):
        return all(str(a[k]) == str(b[k]) for k in keys)

    all_parsed = [r for records in parsed.values() for r in records]
    for row in current.schedule.to_dict("records"):
        raw = raw_current[row["fixture_key"]]
        need(same(row, raw, facts), "raw_fixture_conflict")
        for field in ("home_score", "away_score", "result"):
            need(raw.get(field) in (None, "") or str(raw[field]) == row[field], "raw_result_conflict")
        field = "match_page_id" if row["match_id_namespace"] == feed.MATCH_PAGE_NAMESPACE else "data_site_match_id"
        need(any(same(row, p, facts) and str(p.get(field) or "") == row["match_id"] for p in all_parsed), "raw_typed_identity_witness")
        if row["status"] == "completed":
            proofs = parsed[row["completion_origin_snapshot"]]
            need(any(p["status"] == "completed" and same(row, p, (*facts, "home_score", "away_score", "result", "evidence_sha256", "evidence_fetched_at_utc")) for p in proofs), "raw_completion_witness")
    # Catch changes during read/parse, not just at the next checkpoint.
    need(all(w.sha(w.safe(root / p)) == h for p, h in files.items()), "input_changed_during_read")
    return current, dict(period=window, revision_id=revision, publication_manifest_sha256=manifest_sha,
        snapshot_sha256=snapshots, files=files, requests=requests, source_acquired_at_utc=w.utc(observed),
        snapshot_created_at_utc=w.utc(max(utc(w.read_json(root / "snapshots" / i / "manifest.json")["created_at_utc"]) for i in snapshot_ids)),
        targets=targets, fixture_count=len(current.schedule), history_completed_count=len(past),
        fixture_result_completeness="PASS", raw_bytes=total)


@dataclass(frozen=True)
class Reference:
    revision_id: str
    receipt_sha256: str       # SHA of the complete receipt file
    seal_sha256: str
    ready_at_utc: str         # measured after seal fsync/readback, not a file mtime


def publish(workspace, candidate, revision, manifest_sha, friday, *, clock, monotonic=time.monotonic, fault=lambda event: None):
    """Publish synthetic prepared bytes; never fetch, replay a collector or backfill receipts."""
    need(isinstance(workspace, Workspace), "workspace_required")
    candidate = workspace.input(candidate)
    timer = Clock(clock, monotonic)
    cutoff = w.stamp(w.period(friday)["information_cutoff"])
    with owner(workspace):
        started = timer.sample("publication_started")
        need(started <= cutoff, "publication_after_cutoff")
        _, facts = inspect(candidate, revision, manifest_sha, friday)
        need(utc(facts["snapshot_created_at_utc"]) <= started, "snapshot_created_after_publication_start")
        for subdir in ("publications", "receipts", "attempts"):
            w.safe(workspace.root / subdir).mkdir(exist_ok=True)
        w.write_new(workspace.root / "attempts" / (revision + ".json"),
                    w.body(dict(revision_id=revision, started_at_utc=w.utc(started), scope=SCOPE)))
        destination = workspace.root / "publications" / revision
        need(not destination.exists(), "already_published")
        stage = workspace.root / (".pending-source-" + uuid.uuid4().hex)
        stage.mkdir()
        for relative, digest in facts["files"].items():
            path = w.safe(stage / relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            fault("before_payload")
            data = (candidate / relative).read_bytes()
            need(hashlib.sha256(data).hexdigest() == digest, "candidate_changed")
            w.write_new(path, data)
        _, copied = inspect(stage, revision, manifest_sha, friday)
        need(copied == facts, "copy_changed")
        timer.sample("payload_fsync_readback")
        fault("before_publish")
        need(timer.sample("publish_check") <= cutoff, "publication_after_cutoff")
        stage.rename(destination)
        fault("after_publish")
        _, reread = inspect(destination, revision, manifest_sha, friday)
        need(reread == facts, "published_readback_conflict")
        completed = timer.sample("publication_completed_after_readback")
        need(completed <= cutoff, "publication_after_cutoff")
        fault("before_receipt")
        created = timer.sample("receipt_created")
        need(created <= cutoff, "receipt_after_cutoff")
        receipt = dict(format_version=FORMAT, scope=SCOPE, facts=facts,
            publication_started_at_utc=w.utc(started), publication_completed_at_utc=w.utc(completed),
            receipt_created_at_utc=w.utc(created), clock_samples=list(timer.samples),
            verification=dict(payload_fsync=True, published_readback=True,
                              directory_power_loss_durability="NOT_PROVEN"))
        # Self checksum excludes this one field; Reference also pins the entire file.
        receipt["receipt_sha256"] = w.digest(receipt)
        folder = workspace.root / "receipts" / revision
        folder.mkdir()
        w.write_new(folder / "receipt.json", w.body(receipt))
        fault("after_receipt")
        verified = timer.sample("receipt_fsync_readback")
        need(verified <= cutoff, "receipt_after_cutoff")
        seal = dict(format_version=FORMAT, scope=SCOPE, revision_id=revision,
                    receipt_file_sha256=w.sha(folder / "receipt.json"), verified_at_utc=w.utc(verified),
                    receipt_fsync=True, receipt_readback=True)
        fault("before_seal")
        w.write_new(folder / "seal.json", w.body(seal))
        ready = timer.sample("seal_fsync_readback")
        need(ready <= cutoff, "receipt_after_cutoff")
        reference = Reference(revision, w.sha(folder / "receipt.json"), w.sha(folder / "seal.json"), w.utc(ready))
        # Persist the post-seal observation; it is an anchor to existing evidence,
        # not a new acquisition/publication timestamp or a replacement receipt.
        w.write_new(folder / "reference.json", w.body(reference.__dict__))
        timer.sample("reference_fsync_readback")
        return reference


@evidence_errors
def verify(workspace, reference, friday):
    """No discovery/fallback. A caller supplies the explicit reference and expected SHAs."""
    need(isinstance(workspace, Workspace) and isinstance(reference, Reference), "explicit_reference_required")
    workspace.check()
    revision = hash_value(reference.revision_id)
    folder = workspace.root / "receipts" / revision
    need(w.safe(folder / "reference.json").is_file(), "receipt_missing_or_partial")
    need((folder / "reference.json").read_bytes() == w.body(reference.__dict__), "receipt_or_seal_sha")
    receipt_path, seal_path = w.safe(folder / "receipt.json"), w.safe(folder / "seal.json")
    need(receipt_path.is_file() and seal_path.is_file(), "receipt_missing_or_partial")
    need(w.sha(receipt_path) == hash_value(reference.receipt_sha256)
         and w.sha(seal_path) == hash_value(reference.seal_sha256), "receipt_or_seal_sha")
    receipt, seal = w.read_json(receipt_path), w.read_json(seal_path)
    need(set(receipt) == {"format_version", "scope", "facts", "publication_started_at_utc", "publication_completed_at_utc", "receipt_created_at_utc", "clock_samples", "verification", "receipt_sha256"}, "receipt_schema")
    payload = dict(receipt); self_sha = payload.pop("receipt_sha256")
    need(w.digest(payload) == self_sha and receipt["format_version"] == FORMAT and receipt["scope"] == SCOPE, "receipt_contract")
    need(receipt["verification"] == dict(payload_fsync=True, published_readback=True, directory_power_loss_durability="NOT_PROVEN"), "verification_missing")
    need(set(seal) == {"format_version", "scope", "revision_id", "receipt_file_sha256", "verified_at_utc", "receipt_fsync", "receipt_readback"}
         and seal == dict(format_version=FORMAT, scope=SCOPE, revision_id=revision, receipt_file_sha256=reference.receipt_sha256,
                          verified_at_utc=seal.get("verified_at_utc"), receipt_fsync=True, receipt_readback=True), "seal_contract")
    current, facts = inspect(workspace.root / "publications" / revision, revision,
                             receipt["facts"]["publication_manifest_sha256"], friday)
    need(facts == receipt["facts"] and facts["revision_id"] == revision, "receipt_facts_changed")
    cutoff = w.stamp(facts["period"]["information_cutoff"])
    times = [facts["snapshot_created_at_utc"], receipt["publication_started_at_utc"],
             receipt["publication_completed_at_utc"], receipt["receipt_created_at_utc"],
             seal["verified_at_utc"], reference.ready_at_utc]
    need(all(utc(a) <= utc(b) for a, b in zip(times, times[1:])) and utc(times[-1]) <= cutoff, "receipt_chronology")
    samples = receipt["clock_samples"]
    need([s["event"] for s in samples] == ["publication_started", "payload_fsync_readback", "publish_check", "publication_completed_after_readback", "receipt_created"], "clock_samples")
    need(samples[0]["utc"] == receipt["publication_started_at_utc"] and samples[-2]["utc"] == receipt["publication_completed_at_utc"]
         and samples[-1]["utc"] == receipt["receipt_created_at_utc"], "clock_sample_link")
    for a, b in zip(samples, samples[1:]):
        dw = (utc(b["utc"]) - utc(a["utc"])).total_seconds()
        dm = b["monotonic_seconds"] - a["monotonic_seconds"]
        need(math.isfinite(dm) and dw >= 0 and dm >= 0 and abs(dw - dm) <= 2, "clock_changed")
        total_wall = (utc(b["utc"]) - utc(samples[0]["utc"])).total_seconds()
        need(abs(total_wall - (b["monotonic_seconds"] - samples[0]["monotonic_seconds"])) <= 2, "clock_changed")
    need(samples[-1]["monotonic_seconds"] - samples[0]["monotonic_seconds"] <= DEADLINE
         and (utc(reference.ready_at_utc) - utc(times[1])).total_seconds() <= DEADLINE + 2, "deadline")
    return current, receipt


class Provider:
    """Explicit fixed-revision handoff for a future backend, not an updater hook."""
    def __init__(self, workspace, reference, friday, reservation, *, clock, monotonic=time.monotonic):
        self.workspace, self.reference, self.friday = workspace, reference, friday
        workspace.check()
        self.reservation = w.safe(reservation)
        need(self.reservation.resolve().is_relative_to(workspace.root.parent.resolve()), "reservation_outside_sandbox")
        self.reservation_sha256 = w.sha(self.reservation)
        self.timer = Clock(clock, monotonic)
        self.failed = False
        self.timer.sample("selection_started")
        current, receipt = verify(workspace, reference, friday)
        self.frozen_at = self.timer.sample("freeze_verified")
        self.receipt = receipt
        self.state = "FROZEN"
        self.prediction_checked_at = None
        self.target_sha256 = w.digest(receipt["facts"]["targets"])
        self.identity = w.digest(dict(scope=SCOPE, policy=w.POLICY, reference=reference.__dict__,
            frozen_at_utc=w.utc(self.frozen_at), target_sha256=self.target_sha256, reservation_sha256=self.reservation_sha256))
        window = receipt["facts"]["period"]
        need(w.stamp(window["information_cutoff"]) <= self.frozen_at, "freeze_before_cutoff")
        self._check(current, self.frozen_at)

    def _check(self, current, now):
        facts = self.receipt["facts"]
        cutoff = w.stamp(facts["period"]["information_cutoff"])
        need(cutoff <= now <= cutoff + timedelta(seconds=900), "execution_deadline")
        need(now >= utc(self.reference.ready_at_utc), "freeze_before_ready")
        need(w.sha(self.reservation) == self.reservation_sha256, "reservation_changed")
        r = w.read_json(self.reservation)
        need(set(r) == {"scope", "policy", "period", "targets", "created_at", "source_revision", "source_manifest_sha256"}, "reservation_schema")
        hash_value(r["source_revision"]); hash_value(r["source_manifest_sha256"])
        need(r["scope"] == SCOPE and r["policy"] == w.POLICY and r["period"] == facts["period"]
             and r["targets"] == facts["targets"], "reservation_target_conflict")
        need(utc(r["created_at"]) < cutoff - timedelta(days=2), "late_reservation")
        need(w.target_identity(current, facts["period"]) == facts["targets"], "schedule_changed")
        need(all(now < w.stamp(feed.kickoff_at(t["match_date"], t["kickoff_time"])) for t in facts["targets"]), "kickoff_elapsed")

    def checkpoint(self, phase, *, applicability=None, generated_at_utc=None):
        need(not self.failed, "failed_session_no_resume")
        try:
            return self._checkpoint(phase, applicability=applicability, generated_at_utc=generated_at_utc)
        except BaseException:
            self.failed = True
            raise

    def _checkpoint(self, phase, *, applicability=None, generated_at_utc=None):
        need(phase in {"before_prediction", "before_save"}, "checkpoint_phase")
        need((self.state, phase) in {("FROZEN", "before_prediction"), ("PREDICTION_CHECKED", "before_save")}, "checkpoint_order_or_reuse")
        self.timer.sample(phase + "_started")
        current, receipt = verify(self.workspace, self.reference, self.friday)
        need(receipt == self.receipt, "selected_source_changed")
        now = self.timer.sample(phase + "_verified")
        self._check(current, now)
        if applicability is not None:
            # Later observations may invalidate applicability, never replace input facts.
            need(w.target_identity(applicability, receipt["facts"]["period"]) == receipt["facts"]["targets"], "schedule_changed")
        if phase == "before_prediction":
            need(generated_at_utc is None, "unexpected_generation_timestamp")
            self.prediction_checked_at = now
            self.state = "PREDICTION_CHECKED"
        else:
            need(generated_at_utc is not None, "generation_timestamp_required")
            generated = utc(generated_at_utc)
            need(self.prediction_checked_at <= generated <= now, "generation_chronology")
            need(all(generated < w.stamp(feed.kickoff_at(t["match_date"], t["kickoff_time"])) for t in receipt["facts"]["targets"]), "generated_after_kickoff")
            self.state = "SAVE_CHECKED"
        return dict(source=current, snapshot_id=self.identity, receipt_sha256=self.reference.receipt_sha256,
                    frozen_at_utc=w.utc(self.frozen_at), checkpoint_at_utc=w.utc(now),
                    source_acquired_at_utc=receipt["facts"]["source_acquired_at_utc"])
