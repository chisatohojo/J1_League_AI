"""Synthetic source trees and estimator doubles; no network or production artifact loading."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from test_dashboard_feed import repository, publish, set_completed, production_and_network_firewall
from scripts import update_champion_dashboard as update
from src.features.elo_history import _prepare_ongoing_matches
from src.modeling import champion_retrospective as retrospective

NOW = datetime(2026, 10, 18, 5, tzinfo=timezone.utc)


@pytest.fixture
def reconstruction(repository, tmp_path, monkeypatch):
    repo = repository
    rows = deepcopy(repo["rows"])
    for index, row in enumerate(rows):
        row["match_id_namespace"] = retrospective.feed.MATCH_PAGE_NAMESPACE
        row["match_date"] = (datetime(2026, 11, 1)+timedelta(days=int(row["round"]))).date().isoformat()
        if index < 20:
            row["match_date"] = "2026-08-07" if index < 2 else "2026-08-08" if index < 8 else "2026-08-09" if index < 10 else "2026-10-09"
            set_completed(row)
    sha = publish(repo["current_dir"], rows, observed="2026-10-18T00:00:00+00:00", version="ongoing-v2")
    proof = repo["root"] / "synthetic-history-pin.csv"
    proof.write_bytes(b"fixed synthetic history")
    monkeypatch.setattr(retrospective, "source_pins", lambda source: {proof.name: retrospective.digest(proof.read_bytes())})
    seen = []
    class Scaler:
        def transform(self, value):
            assert value.shape[1] == 1
            seen.append(value.copy())
            return value
        def fit(self, *args):
            pytest.fail("No training")
    class Model:
        classes_ = np.array([0, 1, 2])
        def predict_proba(self, value):
            delta = np.clip(value[:, 0]/2000, -.15, .15)
            return np.column_stack((.25-delta, np.full(len(value), .25), .5+delta))
        def fit(self, *args):
            pytest.fail("No training")
    training = pd.DataFrame([dict(match_id="old",match_date="2015-08-01",season="2015",
        home_team_id="team_0001",away_team_id="team_0020",target_class="2",elo_diff="0")])
    special = pd.DataFrame([dict(match_id="special",match_date="2026-06-01",
        home_team_id="team_0002",away_team_id="team_0019",result="1")])
    artifact = SimpleNamespace(training=training, scaler=Scaler(), model=Model())
    def state(source, official, master):
        completed = _prepare_ongoing_matches(official.completed, master, official.observed_at)
        completed["match_date"] = completed.match_date.dt.strftime("%Y-%m-%d")
        return artifact, special, completed
    monkeypatch.setattr(retrospective, "load_state", state)
    options = dict(source=repo["root"], official_directory=repo["current_dir"], expected_sha=sha,
        output=tmp_path/"retrospective", clock=lambda: NOW, progress=lambda line: None)
    return SimpleNamespace(repo=repo, rows=rows, proof=proof, options=options, seen=seen,
                           artifact=artifact, special=special)


def snapshot(root):
    return {str(path.relative_to(root)): retrospective.digest(path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def test_trial_then_complete_seals_predictions_before_scoring_and_preserves_sources(reconstruction, monkeypatch):
    data = reconstruction
    before = snapshot(data.repo["root"])
    root = data.options["output"]
    score = retrospective.score_predictions
    def guarded(predictions, *args):
        stage = "trial" if len(predictions) == 10 else "complete"
        assert (root/"prediction-seals"/f"{stage}.json").is_file()
        assert not any({"result", "home_score", "away_score", "correct"} & set(row) for row in predictions)
        return score(predictions, *args)
    monkeypatch.setattr(retrospective, "score_predictions", guarded)
    trial = retrospective.run_reconstruction(**data.options)
    assert trial["predicted_count"] == trial["target_count"] == 10
    assert trial["pending_count"] == 0 and trial["coverage"] == 1
    sealed_before = snapshot(root/"days")
    full = retrospective.run_reconstruction(**data.options, stage="complete", resume=True)
    assert full["predicted_count"] == full["target_count"] == 20
    assert full["coverage"] == 1 and full["pending_count"] == 0
    assert len(data.seen) == 4  # Three trial days reused, not predicted twice.
    assert all((root/"days"/name).read_bytes() and snapshot(root/"days")[name] == sha for name, sha in sealed_before.items())
    assert snapshot(data.repo["root"]) == before
    results = json.loads((root/"complete/results.json").read_bytes())
    assert {r["prediction_type"] for r in results} == {"retrospective_reconstruction"}
    assert {r["calculated_at_utc"] for r in results} == {NOW.isoformat()}
    assert all(r["evidence_sha256"] and r["model_hash"] and r["home_team"].startswith("Canonical") for r in results)
    assert not (root/".run.lock").exists()
    before = snapshot(root)
    assert retrospective.run_reconstruction(**data.options, stage="complete", resume=True) == full
    assert snapshot(root) == before and len(data.seen) == 4


def test_same_day_and_future_outcomes_cannot_change_features_or_probabilities(reconstruction):
    data = reconstruction
    _, _, official, master, _ = retrospective.prepare_run(data.options["source"],data.options["official_directory"],
        data.options["expected_sha"],data.options["output"])
    _, special, completed = retrospective.load_state(data.options["source"],official,master)
    day = "2026-10-09"
    targets = official.schedule.loc[official.schedule.match_date.eq(day),list(retrospective.champion.TARGET_COLUMNS)]
    before, lineage = retrospective.reconstruct_day(data.artifact,special,completed,master,targets,day,clock=lambda: NOW)
    changed = completed.copy()
    future = completed.iloc[[-1]].copy()
    future["match_date"] = "2026-10-10"
    future["match_id"] = "future-not-available"
    changed = pd.concat([changed, future], ignore_index=True)
    changed.loc[changed.match_date.ge(day),"result"] = 0
    changed.loc[changed.match_date.ge(day),"home_score"] = 99
    after, _ = retrospective.reconstruct_day(data.artifact,special,changed,master,targets,day,clock=lambda: NOW)
    assert before == after and lineage["history_count"] == 10
    assert lineage["history_max_date"] == "2026-08-09"
    changed = completed.copy()
    changed.loc[changed.match_date.lt(day),"result"] = 0
    prior_changed, _ = retrospective.reconstruct_day(data.artifact,special,changed,master,targets,day,clock=lambda: NOW)
    assert before != prior_changed
    with pytest.raises(ValueError,match="target_contract"):
        retrospective.reconstruct_day(data.artifact,special,completed,master,targets.assign(result="2"),day)


def test_interrupted_run_resumes_only_missing_dates(reconstruction, monkeypatch):
    data = reconstruction
    original = retrospective.champion.probability_rows
    calls = 0
    def interrupt(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic interruption")
        return original(*args)
    monkeypatch.setattr(retrospective.champion,"probability_rows",interrupt)
    with pytest.raises(RuntimeError,match="interruption"):
        retrospective.run_reconstruction(**data.options)
    first = (data.options["output"]/"days/2026-08-07/predictions.json").read_bytes()
    assert not (data.options["output"]/".run.lock").exists()
    monkeypatch.setattr(retrospective.champion,"probability_rows",original)
    assert retrospective.run_reconstruction(**data.options,resume=True)["predicted_count"] == 10
    assert (data.options["output"]/"days/2026-08-07/predictions.json").read_bytes() == first
    assert len(data.seen) == 3


@pytest.mark.parametrize("problem",["hash","source","lock","missing_day","run_id"])
def test_resume_rejects_changed_or_incomplete_artifacts(reconstruction, problem):
    data = reconstruction
    retrospective.run_reconstruction(**data.options)
    root = data.options["output"]
    if problem == "hash": (root/"days/2026-08-07/predictions.json").write_bytes(b"tampered")
    elif problem == "source": data.proof.write_bytes(b"changed fixed input")
    elif problem == "lock": (root/".run.lock").write_text("another owner")
    elif problem == "missing_day": (root/"days/2026-08-07/lineage.json").unlink()
    else:
        contract=json.loads((root/"run.json").read_bytes());contract["run_id"]="0"*64
        (root/"run.json").write_bytes(retrospective.encoded(contract))
    with pytest.raises((ValueError,OSError)):
        retrospective.run_reconstruction(**data.options,stage="complete",resume=True)
    assert len(data.seen) == 3
    if problem == "lock": assert (root/".run.lock").read_text() == "another owner"


def test_full_run_requires_successful_trial_and_output_cannot_overlap_inputs(reconstruction):
    options = reconstruction.options
    with pytest.raises(ValueError,match="trial_required"):
        retrospective.run_reconstruction(**options,stage="complete")
    overlapping=dict(options,output=options["source"]/"output")
    with pytest.raises(ValueError,match="overlaps_inputs"):
        retrospective.run_reconstruction(**overlapping)


def test_incomplete_past_history_stops_before_next_day_inference(reconstruction):
    data=reconstruction
    data.rows[3].update(status="candidate",evidence_type="official_completion_unconfirmed",completion_origin_snapshot="")
    sha=publish(data.repo["current_dir"],data.rows,observed="2026-10-18T00:00:00+00:00",version="ongoing-v2")
    data.options["expected_sha"]=sha
    with pytest.raises(ValueError,match="history_incomplete"):
        retrospective.run_reconstruction(**data.options)
    assert len(data.seen)==2 and not (data.options["output"]/"trial").exists()


def test_metric_conventions_and_empty_groups():
    rows=[dict(p_away=1/3,p_draw=1/3,p_home=1/3,actual_class=actual,correct=actual==0) for actual in (0,1,2)]
    value=retrospective.metrics(rows)
    assert value["accuracy"]==pytest.approx(1/3)
    assert value["log_loss"]==pytest.approx(np.log(3))
    assert value["brier_score"]==pytest.approx(2/3)
    assert retrospective.metrics([])["accuracy"] is None
    perfect=[dict(p_away=1.,p_draw=0.,p_home=0.,actual_class=0,correct=True)]
    assert retrospective.metrics(perfect)==dict(n=1,hits=1,accuracy=1,log_loss=0,brier_score=0)


def test_live_comparison_is_separate_and_does_not_force_saved_probabilities(reconstruction,monkeypatch):
    data=reconstruction
    retrospective.run_reconstruction(**data.options)
    retrospective.run_reconstruction(**data.options,stage="complete",resume=True)
    results=json.loads((data.options["output"]/"complete/results.json").read_bytes())
    chosen=[r for r in results if r["match_date"]=="2026-10-09"][:2]
    saved=[dict(fixture_key=r["fixture_key"],match_date=r["match_date"],prediction_generated_at="2026-10-08T00:00:00+00:00",
        source_revision=data.repo["current_id"],**{f"a_p_{s}":repr(r[f"p_{s}"]) for s in ("home","draw","away")}) for r in chosen]
    monkeypatch.setattr(update,"saved_batches",lambda runtime:(deepcopy(saved),[]))
    runtime=data.options["output"].parent/"runtime";runtime.mkdir()
    report=retrospective.compare_saved_predictions(data.options["output"],runtime)
    assert len(report["comparisons"])==2 and all(r["exact_probability_match"] for r in report["comparisons"])
    assert report["live_predictions_and_metrics_combined"] is False
    assert retrospective.compare_saved_predictions(data.options["output"],runtime)==report
    assert len(data.seen)==4  # Comparison/resume never regenerated the sealed main predictions.
