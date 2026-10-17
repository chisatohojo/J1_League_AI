"""Temporary synthetic repositories only; never load the real estimator or fetch official sources."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from test_dashboard_feed import repository, publish, csv_bytes, production_and_network_firewall
from scripts import update_champion_dashboard as update
from scripts import build_dashboard_feed as feed
from src.modeling.champion_prediction import probability_rows, replay_ratings, TARGET_COLUMNS
from src.collect.teams import load_team_master

NOW = datetime.fromisoformat("2026-08-20T16:00:00+00:00")
CONFIG = dict(lookahead_days=7, max_source_age_hours=24, max_evidence_pages=20)


@pytest.fixture
def operational(repository, tmp_path):
    repo = repository
    repo["predictions"] = repo["predictions"][:4]
    repo["bindings"] = repo["bindings"][:4]
    repo["prediction_path"].write_bytes(csv_bytes(repo["predictions"], feed.MIXED_COLUMNS))
    repo["binding_path"].write_bytes(csv_bytes(repo["bindings"], update.BINDING_COLUMNS))
    digest = publish(repo["current_dir"], repo["current_rows"],
                     observed="2026-08-20T15:00:00+00:00", version="ongoing-v2")
    (repo["root"] / feed.ONGOING_PATH / "latest.json").write_text(json.dumps({
        "revision_id": repo["current_id"], "manifest_sha256": digest}), encoding="utf-8")
    runtime = tmp_path / "runtime"
    update.initialize(repo["root"], runtime)
    return repo, runtime


def no_collection(*args):
    pass


def synthetic_probabilities(targets, *args):
    assert tuple(targets.columns) == TARGET_COLUMNS
    return np.tile([0.2, 0.3, 0.5], (len(targets), 1))


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def invoke(operational, slot="morning", **kwargs):
    repo, runtime = operational
    return update.run_update(repo["root"], runtime, slot, CONFIG,
                             collector=kwargs.pop("collector", no_collection),
                             predictor=kwargs.pop("predictor", synthetic_probabilities),
                             clock=kwargs.pop("clock", lambda: NOW), **kwargs)


def test_update_success_idempotence_and_original_data_unchanged(operational):
    repo, runtime = operational
    before = snapshot(repo["root"])
    first = invoke(operational)
    assert first == dict(added=2, total=6, state="ready")
    archive = snapshot(runtime / "batches")
    def no_second_inference(*args):
        pytest.fail("Saved fixtures must not be predicted again")
    assert invoke(operational, predictor=no_second_inference)["added"] == 0
    assert snapshot(runtime / "batches") == archive
    assert snapshot(repo["root"]) == before
    payload = json.loads((runtime / "view/champion_home.json").read_bytes())
    feed.validate_dashboard_data(payload)
    assert len(payload["previousRound"]["matches"]) == len(payload["nextRound"]["matches"]) == 2
    assert payload["nextRound"]["matches"][0]["prediction"]["probabilities"] == dict(home=50, draw=30, away=20)
    assert "st2_" not in (runtime / "view/champion_home.json").read_text()
    assert len(list((runtime / "batches").iterdir())) == 2


@pytest.mark.parametrize("failure", ["network", "inference", "probabilities", "missing_id", "candidate", "stale"])
def test_failure_keeps_last_normal_feed_and_predictions(operational, failure):
    repo, runtime = operational
    feed_before = (runtime / "view/champion_home.json").read_bytes()
    archive = snapshot(runtime / "batches")
    def fail(*args):
        raise TimeoutError("synthetic_private_path_must_not_leak")
    collector, predictor = no_collection, synthetic_probabilities
    clock = lambda: NOW
    if failure == "network":
        collector = fail
    elif failure == "inference":
        predictor = fail
    elif failure == "probabilities":
        predictor = lambda targets, *args: np.tile([0.8, 0.8, -0.6], (len(targets), 1))
    elif failure == "stale":
        clock = lambda: datetime.fromisoformat("2026-08-22T08:00:00+00:00")
    else:
        def collector(source, runtime, config, stage):
            rows = deepcopy(repo["current_rows"])
            if failure == "candidate":
                rows[4]["status"] = "candidate"
            else:
                for key in ("match_id", "match_page_id", "data_site_match_id", "match_id_namespace"):
                    rows[4][key] = ""
            identity = "3" * 64
            digest = publish(runtime / "official/revisions" / identity, rows,
                             observed="2026-08-20T15:00:00+00:00", version="ongoing-v2")
            update.atomic_json(runtime / "official/latest.json", dict(revision_id=identity, manifest_sha256=digest))
    with pytest.raises(Exception):
        invoke(operational, collector=collector, predictor=predictor, clock=clock)
    assert (runtime / "view/champion_home.json").read_bytes() == feed_before
    assert snapshot(runtime / "batches") == archive
    status = json.loads((runtime / "view/update-status.json").read_bytes())
    assert status["state"] == "error" and status["errorCode"] == "update_failed"
    assert "private" not in json.dumps(status)
    assert not (runtime / "update.lock").exists()


def test_evening_never_predicts_and_records_success(operational):
    def forbidden(*args):
        pytest.fail("Evening must not generate forecasts")
    assert invoke(operational, slot="evening", predictor=forbidden)["added"] == 0
    repo, runtime = operational
    assert json.loads((runtime / "view/update-status.json").read_bytes())["lastSuccessAt"] == NOW.isoformat()


def test_exclusion_lock_and_abandoned_lock_not_recovered(operational):
    repo, runtime = operational
    lock = runtime / "update.lock"
    lock.write_text("synthetic-owner", encoding="utf-8")
    before = snapshot(runtime)
    with pytest.raises(FileExistsError):
        invoke(operational)
    assert snapshot(runtime) == before
    assert lock.read_text() == "synthetic-owner"


def test_modified_saved_prediction_is_detected(operational):
    repo, runtime = operational
    path = next((runtime / "batches").glob("*/predictions.csv"))
    path.write_bytes(path.read_bytes() + b"\n")
    before = (runtime / "view/champion_home.json").read_bytes()
    with pytest.raises(ValueError, match="saved_prediction_modified"):
        invoke(operational)
    assert (runtime / "view/champion_home.json").read_bytes() == before


def test_kickoff_crossed_during_inference_cannot_commit(operational):
    repo, runtime = operational
    times = [datetime.fromisoformat("2026-08-22T09:30:00+00:00")]
    def collector(source, runtime, config, stage):
        identity = "3" * 64
        digest = publish(runtime / "official/revisions" / identity, repo["current_rows"],
                         observed="2026-08-22T08:00:00+00:00", version="ongoing-v2")
        update.atomic_json(runtime / "official/latest.json", dict(revision_id=identity, manifest_sha256=digest))
    def predictor(targets, *args):
        times[0] = datetime.fromisoformat("2026-08-22T10:01:00+00:00")
        return synthetic_probabilities(targets)
    archive = snapshot(runtime / "batches")
    with pytest.raises(ValueError, match="kickoff_elapsed"):
        invoke(operational, collector=collector, predictor=predictor, clock=lambda: times[0])
    assert snapshot(runtime / "batches") == archive


def test_prediction_api_uses_only_transform_predict_no_fit():
    class Scaler:
        def transform(self, matrix):
            return matrix
        def fit(self, *args):
            pytest.fail("fit forbidden")
    class Model:
        classes_ = np.array([0, 1, 2])
        def predict_proba(self, matrix):
            return np.tile([.2, .3, .5], (len(matrix), 1))
        def fit(self, *args):
            pytest.fail("fit forbidden")
    targets = pd.DataFrame([dict(zip(TARGET_COLUMNS, [
        "j1_2026_2027:a:b", "100001", "2026-08-22", "19:00",
        "team_0001", "team_0002", feed.MATCH_PAGE_NAMESPACE]))])
    artifact = SimpleNamespace(scaler=Scaler(), model=Model())
    result = probability_rows(artifact, targets, {"team_0001": 1500, "team_0002": 1480})
    assert result.tolist() == [[.2, .3, .5]]
    with pytest.raises(ValueError, match="prediction_target_allowlist"):
        probability_rows(artifact, targets.assign(home_score=2), {})


def test_disabled_cli_has_no_update_side_effects(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    runtime = tmp_path / "runtime"
    config = dict(CONFIG, enabled=False, source_root=str(source), runtime_root=str(runtime),
                  morning="07:00", evening="22:00", timezone="Asia/Tokyo", network_timeout_seconds=30)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert update.main(["--config", str(path), "--slot", "morning"]) == 1
    assert not runtime.exists()



def test_elo_replay_excludes_same_day_and_future_results(repository):
    master = load_team_master(repository["root"] / feed.TEAM_MASTER_PATH)
    training = pd.DataFrame([dict(match_id="historic", match_date="2015-08-01", season="2015",
        home_team_id="team_0001", away_team_id="team_0002", target_class="2", elo_diff="0")])
    empty = pd.DataFrame(columns=["match_id", "match_date", "home_team_id", "away_team_id", "result"])
    future = pd.DataFrame([dict(match_id="not-known-yet", match_date="2026-08-22",
        home_team_id="team_0001", away_team_id="team_0002", result="0")])
    baseline = replay_ratings(training, empty, empty, master, "2026-08-22")
    assert replay_ratings(training, empty, future, master, "2026-08-22") == baseline
    future["result"] = "2"
    assert replay_ratings(training, empty, future, master, "2026-08-22") == baseline
    future["match_date"] = "2026-08-21"
    assert replay_ratings(training, empty, future, master, "2026-08-22") != baseline


def test_champion_bad_artifact_hash_stops_before_deserialization(tmp_path):
    from src.modeling.champion_prediction import load_champion, ARTIFACT_PATH, FILE_PINS
    directory = tmp_path / ARTIFACT_PATH
    directory.mkdir(parents=True)
    for name in FILE_PINS:
        (directory / name).write_bytes(b"synthetic-tampered-artifact")
    with pytest.raises(ValueError, match="champion_bundle_hash"):
        load_champion(tmp_path)


def test_source_pins_cover_data_without_reading_evolving_research_documents(tmp_path):
    from src.modeling.champion_prediction import HISTORY_PATHS, validate_source_data
    entries = []
    for path in sorted(HISTORY_PATHS):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"synthetic-pinned-input")
        entries.append(dict(path=path, sha256=feed.sha(destination.read_bytes())))
    entries.append(dict(path="docs/PROJECT_STATUS.md", sha256="f" * 64))
    metadata = dict(source_datasets=entries)
    validate_source_data(tmp_path, metadata)  # Document is deliberately absent.
    (tmp_path / "data/master/teams.csv").write_bytes(b"changed")
    with pytest.raises(ValueError, match="champion_source_changed"):
        validate_source_data(tmp_path, metadata)
    with pytest.raises(ValueError, match="champion_source_contract"):
        validate_source_data(tmp_path, dict(source_datasets=entries[1:]))


def test_champion_entrypoint_with_synthetic_frozen_inputs(repository, monkeypatch):
    from src.modeling import champion_prediction as champion
    from src.features import elo_history
    from src.collect import jleague_hyakunen
    source = repository["root"]
    path = source / champion.HYAKUNEN_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic-approved-special-history")
    monkeypatch.setattr(champion, "HYAKUNEN_SHA", hashlib.sha256(path.read_bytes()).hexdigest())
    artifact = SimpleNamespace(training=pd.DataFrame(), scaler=None, model=None)
    monkeypatch.setattr(champion, "load_champion", lambda root: artifact)
    monkeypatch.setattr(elo_history, "_read_hyakunen_matches", lambda path: pd.DataFrame())
    monkeypatch.setattr(elo_history, "_order_matches", lambda frame, master: frame)
    monkeypatch.setattr(elo_history, "_prepare_ongoing_matches", lambda *args: pd.DataFrame())
    monkeypatch.setattr(jleague_hyakunen, "validate_competition", lambda frame: None)
    monkeypatch.setattr(champion, "replay_ratings", lambda *args: {"synthetic": 1500})
    seen = []
    def probabilities(bundle, targets, ratings):
        assert bundle is artifact and ratings == {"synthetic": 1500}
        seen.append(tuple(targets.columns))
        return synthetic_probabilities(targets)
    monkeypatch.setattr(champion, "probability_rows", probabilities)
    targets = pd.DataFrame([dict(zip(TARGET_COLUMNS, [
        "j1_2026_2027:a:b", "100001", "2026-08-22", "19:00",
        "team_0001", "team_0002", feed.MATCH_PAGE_NAMESPACE]))])
    current = SimpleNamespace(completed=pd.DataFrame(), observed_at=NOW.isoformat())
    assert champion.predict_champion(targets, current, source, NOW).tolist() == [[.2, .3, .5]]
    assert seen == [TARGET_COLUMNS]
    with pytest.raises(ValueError, match="kickoff_elapsed"):
        champion.predict_champion(targets, current, source,
                                  datetime.fromisoformat("2026-08-22T10:00:00+00:00"))
    assert len(seen) == 1


@pytest.mark.parametrize("pending", ["official", "prediction"])
def test_pending_source_transaction_preserves_display(operational, pending):
    repo, runtime = operational
    before = (runtime / "view/champion_home.json").read_bytes()
    path = (repo["root"] / feed.ONGOING_PATH / ".update.lock" if pending == "official" else
            repo["binding_path"].with_name(f".{repo['binding_path'].name}.journal.json"))
    path.write_text("unfinished-synthetic-owner", encoding="utf-8")
    with pytest.raises(ValueError, match="update_pending"):
        invoke(operational)
    assert path.read_text() == "unfinished-synthetic-owner"
    assert (runtime / "view/champion_home.json").read_bytes() == before
    assert json.loads((runtime / "view/update-status.json").read_bytes())["state"] == "error"


@pytest.mark.parametrize("mode", ["success", "identity", "limit", "held"])
def test_bounded_collector_reuses_official_gate_without_guessing_ids(operational, monkeypatch, mode):
    from scripts import update_jleague_ongoing as acquisition
    from src.collect import jleague_ongoing as publisher
    from src.collect import jleague_ongoing_source as parser
    import time
    repo, runtime = operational
    prior = update.official(repo["root"], runtime / "official")
    pending = prior.schedule.loc[~prior.schedule.fixture_key.isin(prior.completed.fixture_key)].iloc[0]
    assert pending.match_page_id
    monkeypatch.setattr(update, "official", lambda *args: prior)
    monkeypatch.setattr(update, "seed_snapshot_history", lambda *args: None)
    rows = [dict(fixture_key=pending.fixture_key, match_date="2026-08-20",
                 match_page_id="999999" if mode == "identity" else None),
            dict(fixture_key="j1_2026_2027:unmapped:a", match_date="2026-08-20",
                 match_page_id=None, data_site_match_id="7654321")]
    monkeypatch.setattr(parser, "parse_listing", lambda text: rows)
    monkeypatch.setattr(update, "utc_now", lambda: NOW)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    fetched, snapshots, publications = [], [], []
    def fetch(url, destination):
        assert destination.is_relative_to(runtime)
        fetched.append(url)
        destination.write_text("synthetic-html", encoding="utf-8")
    def capture(directory, **kwargs):
        assert directory == runtime / "snapshots"
        assert len(kwargs["evidence_html"]) == 1
        snapshots.append(kwargs)
        return directory / "synthetic-snapshot"
    def publish_snapshot(snapshot_path, output, **kwargs):
        assert output == runtime / "official"
        assert kwargs == dict(prediction_binding_path=runtime / "synthetic-stage" / update.SIDECAR,
                              prediction_repository_root=runtime / "synthetic-stage",
                              prediction_artifacts=(update.NATIVE,))
        publications.append(kwargs)
        return dict(publication_status="held" if mode == "held" else "published")
    monkeypatch.setattr(acquisition, "_fetch", fetch)
    monkeypatch.setattr(publisher, "create_snapshot", capture)
    monkeypatch.setattr(publisher, "process_snapshot", publish_snapshot)
    config = dict(CONFIG, max_evidence_pages=0 if mode == "limit" else 20)
    before = snapshot(repo["root"])
    if mode == "success":
        update.collect_official(repo["root"], runtime, config, runtime / "synthetic-stage")
    else:
        code = dict(identity="official_page_identity_changed", limit="evidence_page_limit",
                    held="official_publication_held")[mode]
        with pytest.raises(ValueError, match=code):
            update.collect_official(repo["root"], runtime, config, runtime / "synthetic-stage")
    assert len(fetched) == (1 if mode in {"identity", "limit"} else 2)
    if len(fetched) == 2:
        assert fetched[1] == f"https://www.jleague.jp/match/j1/2026/{pending.match_page_id}/"
        assert "7654321" not in fetched[1]
        assert len(snapshots) == len(publications) == 1
    assert snapshot(repo["root"]) == before


def test_seed_preserves_accepted_observation_sequence_and_run(tmp_path):
    from src.collect.jleague_ongoing import create_snapshot, _read_snapshot, _json, FORMAT_VERSION
    from test_jleague_ongoing_update import write_source
    source, runtime = tmp_path / "source", tmp_path / "runtime"
    raw = source / "data/raw/jleague/2026_27/snapshots"
    html = write_source(tmp_path / "input/listing.html", "<html>Synthetic archived observation</html>",
                        timestamp="2026-08-20T15:00:00+00:00")
    original = create_snapshot(raw, listing_html=html, snapshot_id="accepted-synthetic")
    manifest = _read_snapshot(original)
    run = dict(snapshot_id=original.name, snapshot_sha256=feed.sha((original / "manifest.json").read_bytes()),
               format_version=FORMAT_VERSION, previous_accepted_revision_id=None)
    prior = SimpleNamespace(manifest=dict(snapshot_id=original.name, format_version=FORMAT_VERSION,
        sequence=manifest["sequence"], summary=dict(sources=manifest["sources"]), run=run),
        revision_id=feed.sha(_json(run)))
    (runtime / "official").mkdir(parents=True)
    before = snapshot(source)
    update.seed_snapshot_history(source, runtime, prior)
    assert _read_snapshot(runtime / "snapshots" / original.name) == manifest
    assert json.loads((runtime / "official/runs" / f"{original.name}-{FORMAT_VERSION}.json").read_bytes()) == run
    next_snapshot = create_snapshot(runtime / "snapshots", listing_html=html, snapshot_id="next-synthetic")
    following = _read_snapshot(next_snapshot)
    assert following["previous_snapshot_id"] == original.name
    assert following["sequence"] == manifest["sequence"] + 1
    assert snapshot(source) == before
