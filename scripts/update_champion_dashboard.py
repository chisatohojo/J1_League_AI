"""Scheduled Champion-only updates. CLI stays disabled until explicit approval/configuration."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from zoneinfo import ZoneInfo

import pandas as pd

from scripts import build_dashboard_feed as feed
from src.collect.teams import load_team_master
from src.modeling.prediction_identity import BINDING_COLUMNS
from src.modeling.champion_prediction import TARGET_COLUMNS, predict_champion
from src.modeling import weekend_batch

NATIVE = feed.CHAMPION_PREDICTION_ARTIFACT
SIDECAR = "data/processed/predictions/champion_a_fixture_bindings.csv"
LEGACY_VIEW = "champion_home.json"
ROUND_VIEW = "champion_rounds.json"


def utc_now():
    return datetime.now(timezone.utc)


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(body)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def build_display_feeds(source, runtime, prediction, sidecar, now):
    """Validate both projections of one immutable publication before any display write."""
    pointer = runtime / "official/latest.json"
    before = pointer.read_bytes()
    options = dict(prediction_file=prediction, binding_file=sidecar,
                   official_directory=runtime / "official", champion_only=True)
    legacy = feed.build_dashboard_feed(source, **options)
    rounds = feed.build_dashboard_feed(source, **options, round_view=True, now=now)
    feed.require(pointer.read_bytes() == before, "display_publication_changed")
    validate_display_feeds(legacy, rounds)
    return legacy, rounds


def validate_display_feeds(legacy, rounds):
    for payload, version in ((legacy, 1), (rounds, 2)):
        feed.validate_dashboard_data(payload)
        feed.require(payload["schemaVersion"] == version, "display_schema_version")
    feed.require(all(legacy[key] == rounds[key] for key in ("model", "updatedAt", "mode")),
                 "display_publication_mismatch")


@contextmanager
def publish_display_feeds(runtime, legacy, rounds):
    """Stage/flush both files; roll back handled failures, including status publication.

    Each filename is replaced atomically. This is not a filesystem transaction
    across both names: reload-enabled servers hold their snapshot while status
    is updating/error. A hard crash requires inspection, never automatic replay.
    """
    validate_display_feeds(legacy, rounds)
    view = runtime / "view"
    feed.require(not view.is_symlink() and not view.is_junction(), "display_link_denied")
    view.mkdir(exist_ok=True)
    temporary, backups, staged, replaced = [], {}, {}, []
    rollback_failed = False

    def stage(body):
        fd, name = tempfile.mkstemp(prefix=".display-", suffix=".json", dir=view)
        path = Path(name)
        temporary.append(path)
        with os.fdopen(fd, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        feed.require(path.read_bytes() == body, "display_readback_failed")
        return path

    try:
        # Replace legacy last so a v2 write failure cannot touch the old v1 file.
        for name, payload in ((ROUND_VIEW, rounds), (LEGACY_VIEW, legacy)):
            path = view / name
            feed.require(not path.is_symlink() and not path.is_junction(), "display_link_denied")
            backups[path] = stage(path.read_bytes()) if path.exists() else None
            staged[path] = stage((json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode())
        try:
            for path, prepared in staged.items():
                os.replace(prepared, path)
                replaced.append(path)
            yield
        except BaseException:
            failure = None
            for path in reversed(replaced):
                backup = backups[path]
                try:
                    if backup is None:
                        path.unlink()
                    else:
                        os.replace(backup, path)
                except OSError as error:
                    failure = error
            if failure is not None:
                rollback_failed = True
                raise ValueError("display_rollback_failed") from failure
            raise
    finally:
        # Leave a backup on disk if rollback itself failed; never erase recovery evidence.
        keep = {backup for path, backup in backups.items() if rollback_failed and backup is not None
                and path in replaced and backup.exists()}
        for path in temporary:
            if path not in keep:
                path.unlink(missing_ok=True)


def validate_paths(source, runtime):
    runtime = Path(runtime).absolute()
    for path in [runtime, *runtime.parents]:
        feed.require(not path.is_symlink() and not path.is_junction(), "runtime_link_denied")
    source, runtime = Path(source).resolve(), runtime.resolve()
    feed.require(not runtime.is_relative_to(source) and not source.is_relative_to(runtime),
                 "runtime_must_be_separate")
    feed.require(source.is_dir(), "source_root_missing")
    for path in [runtime, *runtime.parents]:
        feed.require(not path.is_symlink() and not path.is_junction(), "runtime_link_denied")
    return source, runtime


def require_quiet_inputs(source, runtime):
    # Do not recover another publisher's unfinished transaction or read its projections.
    for directory in (source / feed.ONGOING_PATH, runtime / "official"):
        feed.require(not (directory / ".update.lock").exists()
                     and not any((directory / "revisions").glob(".pending-*")),
                     "official_update_pending")
    sidecar = source / feed.BINDING_PATH
    feed.require(not sidecar.with_name(f".{sidecar.name}.lock").exists()
                 and not sidecar.with_name(f".{sidecar.name}.journal.json").exists(),
                 "prediction_update_pending")


@contextmanager
def update_lock(runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / "update.lock"
    # A crashed owner's lock is deliberately not reclaimed automatically.
    handle = lock.open("x", encoding="utf-8")
    try:
        handle.write(str(os.getpid()))
        handle.flush()
        os.fsync(handle.fileno())
        yield
    finally:
        handle.close()
        lock.unlink()


def official(source, directory):
    pointer = json.loads((directory / "latest.json").read_bytes())
    feed.require(feed.HEX64.fullmatch(pointer["revision_id"]), "official_revision_id")
    master = load_team_master(source / feed.TEAM_MASTER_PATH)
    return feed.read_official_revision(
        feed.rooted(directory, "revisions/" + pointer["revision_id"]), master,
        expected_sha=pointer["manifest_sha256"])


def csv_write(path, records, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(records, columns=columns)
    with path.open("x", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False, lineterminator="\n")
        handle.flush()
        os.fsync(handle.fileno())


def stage_inputs(directory, records, bindings):
    prediction, binding = directory / NATIVE, directory / SIDECAR
    csv_write(prediction, records, feed.CHAMPION_COLUMNS)
    csv_write(binding, bindings, BINDING_COLUMNS)
    return prediction, binding


def publish_batch(runtime, records, bindings):
    if not records:
        return
    with weekend_batch.publication_lock(runtime):
        existing, _ = saved_batches(runtime)
        feed.require(not {r["fixture_key"] for r in records} & {r["fixture_key"] for r in existing}, "saved_prediction_overlap")
        _publish_daily_batch(runtime, records, bindings)


def _publish_daily_batch(runtime, records, bindings):
    archive = runtime / "batches"
    archive.mkdir(exist_ok=True)
    identity = hashlib.sha256("\n".join(sorted(r["fixture_key"] for r in records)).encode()).hexdigest()
    destination = archive / identity
    feed.require(not destination.exists(), "prediction_batch_already_exists")
    with tempfile.TemporaryDirectory(prefix=".batch-", dir=runtime) as temporary:
        stage = Path(temporary) / identity
        stage.mkdir()
        csv_write(stage / "predictions.csv", records, feed.CHAMPION_COLUMNS)
        csv_write(stage / "bindings.csv", bindings, BINDING_COLUMNS)
        atomic_json(stage / "manifest.json", {
            name: hashlib.sha256((stage / name).read_bytes()).hexdigest()
            for name in ("predictions.csv", "bindings.csv")})
        # Both CSVs and their manifest become visible as one immutable directory.
        stage.rename(destination)


def saved_batches(runtime):
    records, bindings = [], []
    for directory in sorted((runtime / "batches").glob("*")):
        if directory.name.startswith(weekend_batch.PREFIX):
            batch_records, batch_bindings, _, _ = weekend_batch.read_batch(directory)
            records.extend(batch_records)
            bindings.extend(batch_bindings)
            continue
        feed.require(directory.is_dir() and feed.HEX64.fullmatch(directory.name), "invalid_batch_directory")
        manifest = json.loads((directory / "manifest.json").read_bytes())
        feed.require(set(manifest) == {"predictions.csv", "bindings.csv"}, "batch_manifest")
        for name, digest in manifest.items():
            feed.require(hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest,
                         "saved_prediction_modified")
        rows = feed.csv_frame((directory / "predictions.csv").read_bytes(), exact=feed.CHAMPION_COLUMNS)
        sidecar = feed.csv_frame((directory / "bindings.csv").read_bytes(), exact=BINDING_COLUMNS)
        feed.read_champion_only_predictions((directory / "predictions.csv").read_bytes())
        records.extend(rows.to_dict("records"))
        bindings.extend(sidecar.to_dict("records"))
    keys = [r["fixture_key"] for r in records]
    feed.require(len(keys) == len(set(keys)), "duplicate_saved_fixture")
    return records, bindings


def initialize(source, runtime):
    """Copy accepted publications and seed Champion projections; never alter original evidence."""
    if (runtime / "initialized.json").exists():
        marker = json.loads((runtime / "initialized.json").read_bytes())
        feed.require(marker["source_root"] == str(source), "runtime_source_changed")
        return
    feed.require(not (runtime / "batches").exists() and not (runtime / "official").exists(),
                 "incomplete_runtime_initialization")
    payload = feed.build_dashboard_feed(source)
    predictions = feed.read_champion_predictions(source / feed.PREDICTION_ARTIFACT)
    sidecar = feed.csv_frame((source / feed.BINDING_PATH).read_bytes(), exact=BINDING_COLUMNS)
    selected = sidecar.loc[sidecar.prediction_artifact.eq(feed.PREDICTION_ARTIFACT)].copy()
    selected["prediction_artifact"], selected["model_version"] = NATIVE, feed.CHAMPION_VERSION
    records = predictions.assign(model_version=feed.CHAMPION_VERSION).to_dict("records")
    source_official = source / feed.ONGOING_PATH
    pointer = json.loads((source_official / "latest.json").read_bytes())
    revisions = set(predictions.source_revision) | set(selected.identity_witness_revision_id) | {pointer["revision_id"]}
    for revision in revisions:
        original = feed.rooted(source_official, "revisions/" + revision)
        metadata = json.loads((original / "manifest.json").read_bytes())
        destination = runtime / "official/revisions" / revision
        destination.mkdir(parents=True, exist_ok=False)
        for name in ["manifest.json", *metadata["files"]]:
            feed.require(Path(name).name == name, "official_copy_path")
            body = (original / name).read_bytes()
            if name != "manifest.json":
                feed.require(hashlib.sha256(body).hexdigest() == metadata["files"][name], "official_copy_hash")
            with (destination / name).open("xb") as target:
                target.write(body)
                target.flush()
                os.fsync(target.fileno())
    atomic_json(runtime / "official/latest.json", pointer)
    publish_batch(runtime, records, selected.to_dict("records"))
    feed.write_dashboard_feed(payload, runtime / "view/champion_home.json")
    atomic_json(runtime / "initialized.json", {"source_root": str(source), "schemaVersion": 1})


def evidence_allowlist(config):
    """Exact operator-supplied J1 URLs only; never derive or enumerate page IDs."""
    pages = config.get("evidence_urls", [])
    feed.require(type(pages) is list, "evidence_allowlist_schema")
    feed.require(all(isinstance(url, str) and feed.PAGE_URL.fullmatch(url) for url in pages),
                 "evidence_allowlist_url")
    feed.require(len(pages) == len(set(pages)), "evidence_allowlist_duplicate")
    feed.require(len(pages) <= config["max_evidence_pages"], "evidence_page_limit")
    return set(pages)


def discovery_options(config):
    enabled = config.get("discovery_enabled", True)
    feed.require(type(enabled) is bool, "discovery_enabled_schema")
    options = {}
    for name, default, low, high in (
        ("discovery_window_days", 7, 1, 31),
        ("max_discovery_pages", 6, 1, 12),
        ("max_acquisition_seconds", 600, 120, 840),
    ):
        value = config.get(name, default)
        feed.require(type(value) is int and low <= value <= high, "discovery_config_bounds")
        options[name] = value
    return enabled, options


def discovery_windows(targets, today, options):
    """Do not age out unresolved results; reserve a window for upcoming fixtures."""
    windows = []
    for day in sorted({date.fromisoformat(row["match_date"]) for row in targets}):
        if windows and (day - windows[-1][0]).days < options["discovery_window_days"]:
            windows[-1] = (windows[-1][0], day)
        else:
            windows.append((day, day))
    limit = options["max_discovery_pages"]
    selected = windows[:limit]
    future = next((window for window in windows if window[1] >= today), None)
    if future is not None and future not in selected:
        selected = selected[:limit - 1] + [future]
    return selected


def collect_official(source, runtime, config, publication_root):
    """One bounded acquisition; reuse existing official parser/publisher and binding gates."""
    from scripts.update_jleague_ongoing import _fetch
    from src.collect.jleague_ongoing import create_snapshot, process_snapshot
    from src.collect.jleague_ongoing_source import (
        SOURCE_URL, parse_listing, discovery_search_url, discover_match_urls,
        parse_completion_evidence, apply_completion_evidence,
    )
    import time

    urls = evidence_allowlist(config)
    discovery_enabled, options = discovery_options(config)
    prior = official(source, runtime / "official")
    seed_snapshot_history(source, runtime, prior)
    acquisition = runtime / "acquisitions" / uuid.uuid4().hex
    acquisition.mkdir(parents=True)
    deadline = time.monotonic() + options["max_acquisition_seconds"]
    audit = dict(schemaVersion=1, discoveryEnabled=discovery_enabled, searches=[],
                 discovered=[], evidence=[], unresolved=[], state="acquiring")

    def fetch(url, path):
        # The fetch has a 30s stream deadline and 30s socket timeout. Reserve
        # both, plus politeness, so an in-flight read fits the total budget.
        feed.require(deadline - time.monotonic() >= 61, "acquisition_time_limit")
        if audit["searches"] or path.name != "listing.html":
            time.sleep(1)
        _fetch(url, path)
        feed.require(time.monotonic() <= deadline, "acquisition_time_limit")
        body = path.read_bytes()
        metadata = json.loads(path.with_suffix(".metadata.json").read_bytes())
        feed.require(metadata["requested_url"] == metadata["final_url"] == url
                     and metadata["status"] == 200
                     and metadata["sha256"] == hashlib.sha256(body).hexdigest()
                     and metadata["bytes"] == len(body), "acquisition_provenance")
        return dict(url=url, html=path.name, sha256=metadata["sha256"],
                    metadataSHA256=hashlib.sha256(path.with_suffix(".metadata.json").read_bytes()).hexdigest(),
                    fetchedAtUTC=metadata["fetched_at_utc"])

    try:
        listing = acquisition / "listing.html"
        audit["listing"] = fetch(SOURCE_URL, listing)
        listing_rows = parse_listing(listing.read_text(encoding="utf-8-sig"))
        known = {r.fixture_key: str(r.match_page_id) for r in prior.schedule.itertuples()
                 if getattr(r, "match_page_id", "")}
        known_ids = {page: key for key, page in known.items()}
        feed.require(len(known_ids) == len(known), "official_page_identity_collision")
        today = utc_now().astimezone(ZoneInfo("Asia/Tokyo")).date()
        end = (today + timedelta(days=config["lookahead_days"])).isoformat()
        completed = set(prior.completed.fixture_key)
        targets = []
        for row in listing_rows:
            page, previous_page = row.get("match_page_id"), known.get(row["fixture_key"])
            feed.require(not page or not previous_page or page == previous_page, "official_page_identity_changed")
            page = page or previous_page
            if row["fixture_key"] in completed:
                continue
            if row["match_date"] <= today.isoformat() and page:
                feed.require(re.fullmatch(r"[0-9]{6}", page), "official_page_identity")
                urls.add(f"https://www.jleague.jp/match/j1/{row['match_date'][:4]}/{page}/")
            # Candidate age has no cutoff. Missing upcoming IDs are searched
            # only within the configured forecast horizon, never the full year.
            if (row["status"] == "candidate" or
                    (row["status"] == "scheduled" and not page and row["match_date"] <= end)):
                targets.append(row)
        feed.require(len(urls) <= config["max_evidence_pages"], "evidence_page_limit")
        manual_urls = evidence_allowlist(config)
        origins = {url: [] for url in urls}
        if discovery_enabled:
            windows = discovery_windows(targets, today, options)
            known_completed_urls = {
                f"https://www.jleague.jp/match/j1/{r.match_date[:4]}/{r.match_page_id}/"
                for r in prior.schedule.itertuples()
                if r.fixture_key in completed and getattr(r, "match_page_id", "")}
            found = {}
            for i, (start, finish) in enumerate(windows):
                search_url = discovery_search_url(start, finish)
                path = acquisition / f"search_{i:03d}.html"
                search = fetch(search_url, path)
                search.update(start=start.isoformat(), end=finish.isoformat())
                audit["searches"].append(search)
                for url in discover_match_urls(path.read_text(encoding="utf-8-sig"), start=start, end=finish):
                    audit["discovered"].append(dict(url=url, sourcePage=search_url,
                        sourceSHA256=search["sha256"], fetchedAtUTC=search["fetchedAtUTC"]))
                    if url not in known_completed_urls:
                        found.setdefault(url, []).append(search_url)
            # Bounded, deterministic selection. Deferred fixtures remain in
            # the season schedule and in the unresolved audit, never discarded.
            for url in sorted(found):
                if url in urls or len(urls) < config["max_evidence_pages"]:
                    urls.add(url)
                    origins[url] = found[url]
                else:
                    audit["unresolved"].append(dict(url=url, reason="evidence_page_budget"))
        evidence, parsed = [], []
        for i, url in enumerate(sorted(urls)):
            path = acquisition / f"evidence_{i:03d}.html"
            entry = fetch(url, path)
            entry.update(sourcePages=origins.get(url, []), manualAllowlist=url in manual_urls,
                         validation="pending")
            audit["evidence"].append(entry)
            item = parse_completion_evidence(path.read_text(encoding="utf-8-sig"), source_url=url)
            feed.require(known.get(item["fixture_key"], item["match_page_id"]) == item["match_page_id"],
                         "official_page_identity_changed")
            feed.require(known_ids.get(item["match_page_id"], item["fixture_key"]) == item["fixture_key"],
                         "official_page_identity_collision")
            parsed.append(item)
            # Includes duplicate fixture/page-ID collision and candidate-score
            # checks; the publisher repeats these gates with archived sources.
            apply_completion_evidence(listing_rows, parsed)
            entry.update(validation="matched", fixtureKey=item["fixture_key"],
                         matchPageID=item["match_page_id"], namespace="jleague_match_page",
                         matchDate=item["match_date"], round=item["round"],
                         completionVerified=item["verified"])
            evidence.append(path)
        resolved = {row["fixture_key"]: row for row in apply_completion_evidence(listing_rows, parsed)}
        for target in targets:
            row = resolved[target["fixture_key"]]
            if row["status"] == "candidate" or not row.get("match_page_id"):
                audit["unresolved"].append(dict(fixtureKey=row["fixture_key"], matchDate=row["match_date"],
                    status=row["status"], reason="completion_unconfirmed" if row.get("match_page_id")
                    else "official_link_not_resolved"))
        audit["state"] = "validated"
        atomic_json(acquisition / "discovery.json", audit)
        snapshot = create_snapshot(runtime / "snapshots", listing_html=listing, evidence_html=evidence)
        summary = process_snapshot(
            snapshot, runtime / "official", prediction_binding_path=publication_root / SIDECAR,
            prediction_repository_root=publication_root, prediction_artifacts=(NATIVE,))
        feed.require(summary["publication_status"] == "published", "official_publication_held")
        audit.update(state="published", snapshot=snapshot.name)
        atomic_json(acquisition / "discovery.json", audit)
    except Exception:
        audit["state"] = "failed"
        atomic_json(acquisition / "discovery.json", audit)
        raise


def seed_snapshot_history(source, runtime, prior):
    """Preserve the accepted observation sequence in this separate operational lane."""
    from src.collect.jleague_ongoing import _read_snapshot, _json, _write_new, FORMAT_VERSION
    snapshots = runtime / "snapshots"
    if any(snapshots.glob("*/manifest.json")):
        return
    snapshot_id = prior.manifest["snapshot_id"]
    feed.require(feed.SAFE_FILE.fullmatch(snapshot_id), "snapshot_seed_identity")
    original = feed.rooted(source, "data/raw/jleague/2026_27/snapshots/" + snapshot_id)
    manifest = _read_snapshot(original, require_v2=True)
    feed.require(prior.manifest["format_version"] == FORMAT_VERSION
                 and manifest["sequence"] == prior.manifest["sequence"]
                 and manifest["sources"] == prior.manifest["summary"]["sources"], "snapshot_seed_contract")
    run = prior.manifest["run"]
    feed.require(feed.sha(_json(run)) == prior.revision_id, "snapshot_seed_run")
    snapshots.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".seed-", dir=runtime) as temporary:
        stage = Path(temporary) / snapshot_id
        stage.mkdir()
        names = {"manifest.json"} | {entry[key] for entry in manifest["sources"] for key in ("html", "metadata")}
        for name in names:
            feed.require(Path(name).name == name, "snapshot_seed_path")
            _write_new(stage / name, (original / name).read_bytes())
        feed.require(_read_snapshot(stage, require_v2=True) == manifest, "snapshot_seed_changed")
        stage.rename(snapshots / snapshot_id)
    runs = runtime / "official/runs"
    runs.mkdir(exist_ok=True)
    _write_new(runs / f"{snapshot_id}-{FORMAT_VERSION}.json", _json(run))


def select_targets(current, records, now, lookahead, *, reserved_period=None):
    saved = {r["fixture_key"] for r in records}
    today = now.astimezone(ZoneInfo("Asia/Tokyo")).date()
    end = (today + timedelta(days=lookahead)).isoformat()
    candidates = current.schedule.loc[
        current.schedule.status.eq("scheduled") & current.schedule.match_date.ge(today.isoformat())
        & current.schedule.match_date.le(end)]
    if reserved_period is not None:
        feed.require(reserved_period == weekend_batch.period(reserved_period["start"]), "weekend_reserved_period_schema")
        candidates = candidates.loc[~candidates.match_date.between(reserved_period["start"], reserved_period["end"])]
    missing = candidates.loc[~candidates.fixture_key.isin(saved)]
    if missing.empty:
        return missing.loc[:, list(TARGET_COLUMNS)]
    day = missing.match_date.min()
    batch = current.schedule.loc[current.schedule.match_date.eq(day)]
    feed.require(batch.status.eq("scheduled").all(), "target_not_officially_scheduled")
    feed.require(not batch.fixture_key.isin(saved).any(), "saved_date_batch_changed")
    feed.require(batch.fixture_key.is_unique and batch.match_id.is_unique, "target_identity_duplicate")
    feed.require(current.manifest["format_version"] == "ongoing-v2", "prediction_requires_typed_official_ids")
    for row in batch.itertuples(index=False):
        feed.require(bool(row.match_id) and row.match_id_namespace in
                     {feed.MATCH_PAGE_NAMESPACE, feed.DATA_SITE_NAMESPACE}, "official_id_missing")
        feed.require(timestamp_aware(now) < feed.timestamp(feed.kickoff_at(row.match_date, row.kickoff_time)),
                     "kickoff_elapsed")
    appearances = pd.concat([batch[f"{s}_team_id"] for s in ("home", "away")])
    feed.require(appearances.is_unique, "target_team_date_duplicate")
    return batch.sort_values("fixture_key").loc[:, list(TARGET_COLUMNS)]


def require_complete_history(current, target_date, runtime, checked_at):
    """Never replay Elo with an unfinished fixture silently omitted from history."""
    unresolved = current.schedule.loc[
        current.schedule.match_date.lt(target_date) & ~current.schedule.status.eq("completed"),
        ["match_date", "fixture_key", "status"],
    ].sort_values(["match_date", "fixture_key"])
    if not unresolved.empty:
        atomic_json(runtime / "diagnostics" / f"prediction-history-{uuid.uuid4().hex}.json", dict(
            schemaVersion=1, errorCode="prediction_history_incomplete",
            checkedAt=checked_at.isoformat(), targetDate=target_date,
            officialRevision=current.revision_id, unresolved=unresolved.to_dict("records")))
        raise ValueError("prediction_history_incomplete")


def timestamp_aware(value):
    return feed.timestamp(value.isoformat() if isinstance(value, datetime) else value)


def new_records(targets, values, current, master, generated):
    import numpy as np
    values = np.asarray(values, dtype=float)
    feed.require(values.shape == (len(targets), 3) and np.isfinite(values).all()
                 and ((0 <= values) & (values <= 1)).all()
                 and np.allclose(values.sum(axis=1), 1, rtol=0, atol=1e-12), "prediction_probabilities")
    names = {a.team_id: a.canonical_name for a in master.aliases}
    records, bindings = [], []
    for row, probabilities in zip(targets.itertuples(index=False), values):
        feed.require(generated < feed.timestamp(feed.kickoff_at(row.match_date, row.kickoff_time)), "kickoff_elapsed")
        record = {key: getattr(row, key) for key in ("fixture_key", "match_id", "match_date", "home_team_id", "away_team_id")}
        record.update(kickoff=row.kickoff_time, home_team_name=names[row.home_team_id],
                      away_team_name=names[row.away_team_id], prediction_generated_at=generated.isoformat(),
                      source_revision=current.revision_id, champion_a_model_version=feed.CHAMPION_VERSION,
                      champion_a_artifact_hash=feed.CHAMPION_HASH, model_version=feed.CHAMPION_VERSION,
                      **{f"a_p_{side}": repr(float(probabilities[i])) for i, side in enumerate(("away", "draw", "home"))})
        records.append(record)
        bindings.append(dict(prediction_artifact=NATIVE, prediction_match_id=row.match_id,
            model_version=feed.CHAMPION_VERSION, fixture_key=row.fixture_key,
            prediction_id_namespace=row.match_id_namespace, identity_witness_revision_id=current.revision_id,
            identity_witness_manifest_sha256=current.manifest_sha, match_date=row.match_date,
            home_team_id=row.home_team_id, away_team_id=row.away_team_id, prediction_generated_at=generated.isoformat()))
    return records, bindings


def _run_update(source_root, runtime_root, slot, config, *, collector=collect_official,
               predictor=predict_champion, clock=utc_now, weekend_backend=None):
    source, runtime = validate_paths(source_root, runtime_root)
    feed.require(slot in {"morning", "evening"}, "update_slot")
    weekend_policy = weekend_batch.policy(config)
    feed.require(not weekend_policy or isinstance(weekend_backend, weekend_batch.OfflineWeekendBackend), "weekend_offline_only")
    if weekend_policy:
        feed.require(collector is not collect_official and predictor is not predict_champion,
                     "weekend_synthetic_callbacks_required")
        weekend_backend.bind(source, runtime, config)
    with update_lock(runtime):
        status_path = runtime / "view/update-status.json"
        previous = json.loads(status_path.read_bytes()) if status_path.exists() else {}
        started = timestamp_aware(clock())
        state = dict(state="updating", startedAt=started.isoformat(), finishedAt=None,
                     lastSuccessAt=previous.get("lastSuccessAt"), errorCode=None)
        atomic_json(status_path, state)
        try:
            require_quiet_inputs(source, runtime)
            initialize(source, runtime)
            records, bindings = saved_batches(runtime)
            with tempfile.TemporaryDirectory(prefix=".display-", dir=runtime) as temporary:
                stage = Path(temporary)
                prediction, sidecar = stage_inputs(stage, records, bindings)
                collector(source, runtime, config, stage)
                current = official(source, runtime / "official")
                now = timestamp_aware(clock())
                observed = feed.timestamp(current.observed_at)
                feed.require(observed <= now and now - observed <= timedelta(hours=config["max_source_age_hours"]),
                             "official_source_stale_or_future")
                prepared = None
                reserved = None
                if weekend_policy and slot == "morning":
                    prepared = weekend_backend.prepare(current, records, now, clock)
                    reserved = weekend_backend.window
                elif weekend_policy:
                    weekend_backend.review(current, records)  # applicability only; never infer at night
                targets = select_targets(current, records, now, config["lookahead_days"], reserved_period=reserved) if slot == "morning" and prepared is None else None
                added, added_bindings = [], []
                if prepared is not None:
                    master = load_team_master(source / feed.TEAM_MASTER_PATH)
                    added, added_bindings = new_records(prepared.targets, prepared.values, current, master,
                                                       timestamp_aware(prepared.context["generated_at"]))
                elif targets is not None and not targets.empty:
                    require_complete_history(current, targets.match_date.iloc[0], runtime, now)
                    master = load_team_master(source / feed.TEAM_MASTER_PATH)
                    probabilities = predictor(targets, current, source, now)
                    generated = timestamp_aware(clock())
                    feed.require(generated >= now, "clock_moved_backwards")
                    added, added_bindings = new_records(targets, probabilities, current, master, generated)
                # Derived CSVs are temporary; immutable prediction batches are authoritative.
                prediction.unlink()
                sidecar.unlink()
                prediction, sidecar = stage_inputs(stage, records + added, bindings + added_bindings)
                legacy, rounds = build_display_feeds(source, runtime, prediction, sidecar, now)
            for row in added:
                committed = timestamp_aware(clock())
                feed.require(committed >= feed.timestamp(row["prediction_generated_at"]), "clock_moved_backwards")
                feed.require(committed < feed.timestamp(feed.kickoff_at(row["match_date"], row["kickoff"])),
                             "kickoff_elapsed_before_commit")
            if prepared is not None:
                weekend_backend.commit(prepared, added, added_bindings, clock)
            else:
                publish_batch(runtime, added, added_bindings)
            with publish_display_feeds(runtime, legacy, rounds):
                state.update(state="ready", finishedAt=clock().isoformat(), lastSuccessAt=clock().isoformat(), errorCode=None)
                atomic_json(status_path, state)
            return dict(added=len(added), total=len(records) + len(added), state="ready")
        except Exception:
            # Never publish exception strings/source paths or research cells to the UI.
            state.update(state="error", finishedAt=clock().isoformat(),
                         lastSuccessAt=previous.get("lastSuccessAt"), errorCode="update_failed")
            atomic_json(status_path, state)
            raise


def run_update(source_root,runtime_root,slot,config,*,collector=collect_official,predictor=predict_champion,clock=utc_now,weekend_backend=None):
    result=_run_update(source_root,runtime_root,slot,config,collector=collector,predictor=predictor,clock=clock,weekend_backend=weekend_backend)
    # The core update and its lock are complete before the optional, independent display refresh.
    # A display failure must never turn a committed official update/prediction into a core failure.
    if "retrospective_display" in config:
        try:
            options=config["retrospective_display"]
            feed.require(isinstance(options,dict) and set(options)=={
                "store_root","store_sha256","reconstruction_root","ledger_sha256"},"retrospective_display_config")
            from scripts.build_retrospective_preview import refresh_store
            refresh_store(source_root,runtime_root,options["reconstruction_root"],options["ledger_sha256"],
                options["store_root"],expected_store_sha=options["store_sha256"],now=timestamp_aware(clock()))
            result["retrospectiveState"]="ready"
        except Exception:
            result["retrospectiveState"]="error"
    return result


def read_config(path):
    config = json.loads(Path(path).read_bytes())
    weekend_batch.policy(config)
    feed.require(type(config.get("enabled")) is bool, "config_enabled")
    for name in ("morning", "evening"):
        feed.require(isinstance(config.get(name), str) and
                     re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", config[name]), "schedule_time")
    feed.require(config.get("timezone") == "Asia/Tokyo", "schedule_timezone")
    for name, low, high in (("lookahead_days", 1, 14), ("max_source_age_hours", 1, 48),
                            ("max_evidence_pages", 1, 40)):
        feed.require(type(config.get(name)) is int and low <= config[name] <= high, "config_bounds")
    feed.require(config.get("network_timeout_seconds") == 30, "network_timeout_is_fixed_30_seconds")
    evidence_allowlist(config)
    discovery_options(config)
    validate_paths(config["source_root"], config["runtime_root"])
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--slot", required=True, choices=("morning", "evening"))
    args = parser.parse_args(argv)
    try:
        config = read_config(args.config)
        feed.require(config["enabled"] is True, "automatic_updates_disabled")
        print(json.dumps(run_update(config["source_root"], config["runtime_root"], args.slot, config)))
        return 0
    except Exception as error:
        print(json.dumps(dict(state="error", errorCode="automatic_updates_disabled" if
                             str(error) == "automatic_updates_disabled" else "update_failed")), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
