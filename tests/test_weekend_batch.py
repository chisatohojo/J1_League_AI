"""Synthetic publications, toy Elo and marked estimator doubles only."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import ast
import builtins
import hashlib
import io
import json
import socket

import numpy as np
import pandas as pd
import pytest

from test_dashboard_feed import (repository, publish, csv_bytes, save_predictions, save_bindings,
                                 production_and_network_firewall, set_completed)
from scripts import update_champion_dashboard as update
from scripts import build_dashboard_feed as feed
from src.modeling import champion_prediction as champion
from src.modeling import weekend_batch as w
from src.collect.teams import load_team_master

TUESDAY = datetime.fromisoformat("2026-08-18T07:00:00+09:00")
FRIDAY = datetime.fromisoformat("2026-08-21T07:00:30+09:00")
CONFIG = dict(lookahead_days=2, max_source_age_hours=24, max_evidence_pages=20,
              weekend_policy=dict(enabled=True, friday="2026-08-21", deadline_seconds=900))


class MockScaler:
    synthetic_only = True
    def transform(self, matrix):
        assert matrix.ndim == 2 and matrix.shape[1] == 1
        return matrix.copy()
    def fit(self, *args):
        pytest.fail("fit forbidden")


class MockModel:
    synthetic_only = True
    classes_ = np.array([0, 1, 2])
    def __init__(self):
        self.inputs = []
    def predict_proba(self, matrix):
        self.inputs.append(matrix.copy())
        return np.tile([.2, .3, .5], (len(matrix), 1))
    def fit(self, *args):
        pytest.fail("fit forbidden")


@pytest.fixture(autouse=True)
def no_real_estimator_or_network(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("No production model/collector/socket may be invoked")
    monkeypatch.setattr(champion, "load_champion", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    parent=feed.ROOT.parent.resolve()
    private=(Path.home()/'AppData/Local/J1AI').resolve()
    def guarded(original):
        def checked(file,*args,**kwargs):
            if isinstance(file,(str,Path)):
                path=Path(file).resolve()
                assert not path.is_relative_to(private),'Operational/research runtime IO forbidden'
                if path.is_relative_to(parent):
                    relative=path.relative_to(parent).parts
                    assert not (len(relative)>1 and relative[0].startswith('J1_League_AI') and relative[1] in {'data','models'}),'Production source/model IO forbidden'
            return original(file,*args,**kwargs)
        return checked
    monkeypatch.setattr(builtins,'open',guarded(builtins.open))
    monkeypatch.setattr(io,'open',guarded(io.open))


def publish_runtime(case, observed, identity):
    directory = case.runtime / "official/revisions" / identity
    h = publish(directory, case.rows, observed=datetime.fromisoformat(observed).astimezone(timezone.utc).isoformat(), version="ongoing-v2")
    update.atomic_json(case.runtime / "official/latest.json", dict(revision_id=identity, manifest_sha256=h))
    return update.official(case.repo["root"], case.runtime / "official")


@pytest.fixture
def case(repository, tmp_path):
    repo = repository
    repo["predictions"], repo["bindings"] = repo["predictions"][:4], repo["bindings"][:4]
    save_predictions(repo); save_bindings(repo)
    workspace = w.SyntheticWorkspace.create(tmp_path / "offline")
    runtime = workspace.root / "runtime"
    update.initialize(repo["root"], runtime)
    rows = deepcopy(repo["current_rows"])
    for row in rows[4:]:
        row["match_date"] = "2027-06-01"
    days = ["2026-08-21"] + ["2026-08-22"] * 4 + ["2026-08-23"] * 5
    for row, day in zip(rows[10:20], days):
        row["match_date"] = day
    training = pd.DataFrame([dict(match_id="train-1", match_date="2015-08-01", season="2015",
                                  home_team_id="team_0001", away_team_id="team_0002", target_class="2", elo_diff="0.0")])
    special = pd.DataFrame([dict(match_id="special-1", match_date="2026-06-01", home_team_id="team_0003", away_team_id="team_0004", result="0")])
    model = MockModel()
    artifact = champion.ChampionArtifact(MockScaler(), model, training)
    witnesses = {}
    for name, contents in {"training":training.to_csv(index=False, lineterminator="\n").encode(),
                           "special":special.to_csv(index=False, lineterminator="\n").encode(),
                           "estimator":b'{"synthetic_only":true,"kind":"MockScaler+MockModel"}\n'}.items():
        p = workspace.root / (name + ".txt"); p.write_bytes(contents)
        witnesses[name] = dict(path=str(p), sha256=w.sha(p), fetched_at_utc="2026-08-17T22:00:00+00:00")
    p = repo["root"] / feed.TEAM_MASTER_PATH
    witnesses["teams"] = dict(path=str(p), sha256=w.sha(p), fetched_at_utc="2026-08-17T22:00:00+00:00")
    backend = w.OfflineWeekendBackend(workspace, artifact, special, witnesses)
    backend.bind(repo["root"], runtime, CONFIG)
    c = SimpleNamespace(repo=repo, runtime=runtime, rows=rows, backend=backend, model=model)
    c.current = publish_runtime(c, "2026-08-17T22:00:00+00:00", "3" * 64)
    c.original_batches = snapshot(runtime / "batches")
    return c


def snapshot(path):
    return {str(p.relative_to(path)):w.sha(p) for p in path.rglob("*") if p.is_file()}


def reserve(case):
    saved, _ = update.saved_batches(case.runtime)
    return case.backend.reserve(case.current, saved, TUESDAY)


def friday(case):
    reserve(case)
    case.current = publish_runtime(case, "2026-08-20T21:00:00+00:00", "4" * 64)
    return case.current


def prepare(case, now=FRIDAY):
    saved, _ = update.saved_batches(case.runtime)
    return case.backend.prepare(case.current, saved, now, lambda:now)


def outputs(case, prepared):
    return update.new_records(prepared.targets, prepared.values, case.current,
                              load_team_master(case.repo["root"] / feed.TEAM_MASTER_PATH),
                              w.stamp(prepared.context["generated_at"]))


def invoke(case, now, slot="morning", **kwargs):
    return update.run_update(case.repo["root"], case.runtime, slot, CONFIG,
                             collector=lambda *a:None, predictor=kwargs.pop("predictor", lambda *a:pytest.fail("daily predictor unexpected")),
                             clock=lambda:now, weekend_backend=case.backend, **kwargs)


def test_complete_weekend_uses_one_snapshot_atomic_archive_and_schema_v1(case, monkeypatch):
    friday(case)
    calls = []
    original = w.replay_ratings
    monkeypatch.setattr(w, "replay_ratings", lambda *a: (calls.append(True), original(*a))[1])
    assert invoke(case, FRIDAY)["added"] == 10
    assert len(case.model.inputs) == len(calls) == 1
    directories = list((case.runtime / "batches").glob(w.PREFIX + "*")); assert len(directories) == 1
    records, bindings, manifest, context = w.read_batch(directories[0])
    assert manifest["count"] == len(bindings) == len(records) == 10
    assert manifest["format_version"] == w.FORMAT and manifest["commit_state"] == "COMMITTED"
    assert manifest["scope"] == "SYNTHETIC_ONLY"
    assert len({r["source_revision"] for r in records}) == len({r["prediction_generated_at"] for r in records}) == 1
    assert np.array_equal(case.model.inputs[0].ravel(), [context["snapshot"]["features"][r["fixture_key"]] for r in records])
    view = json.loads((case.runtime / "view/champion_home.json").read_bytes())
    assert feed.validate_dashboard_data(view) is view and view["schemaVersion"] == 1
    assert len(view["nextRound"]["matches"]) == 10
    assert view["nextRound"]["label"] == "次の開催週末 · 2026-08-21〜2026-08-24"
    for m in view["nextRound"]["matches"]:
        assert m["prediction"]["probabilities"] == dict(home=50,draw=30,away=20)
        assert "result" not in m
    assert not any(token in json.dumps(view) for token in ["snapshot_id", "input_sha256", "ratings", "SYNTHETIC_ONLY"])
    for name, h in case.original_batches.items():assert w.sha(case.runtime / "batches" / name) == h
    before = snapshot(case.runtime / "batches")
    assert invoke(case, FRIDAY)["added"] == 0
    assert len(case.model.inputs) == 1 and snapshot(case.runtime / "batches") == before


@pytest.mark.parametrize("now", ["2026-08-19T07:00:00+09:00", "2026-08-20T07:00:00+09:00"])
def test_reservation_prevents_wednesday_thursday_partial_saving(case, now):
    reserve(case)
    case.current = publish_runtime(case, datetime.fromisoformat(now).isoformat(), "5" * 64)
    before = snapshot(case.runtime / "batches")
    assert invoke(case, datetime.fromisoformat(now))["added"] == 0
    assert not case.model.inputs and snapshot(case.runtime / "batches") == before


@pytest.mark.parametrize("day", ["2026-08-18", "2026-08-19", "2026-08-20"])
def test_reserved_weekend_does_not_hide_weekday_targets(case, day):
    reserve(case)
    # Completed fixture is not reused; a separate official weekday batch is eligible.
    case.rows[20]["match_date"] = day
    current = publish_runtime(case, day + "T06:00:00+09:00", "5" * 64)
    saved, _ = update.saved_batches(case.runtime)
    selected = update.select_targets(current, saved, datetime.fromisoformat(day+"T07:00:00+09:00"), 7, reserved_period=case.backend.window)
    assert len(selected) == 1 and selected.match_date.iloc[0] == day
    assert invoke(case, datetime.fromisoformat(day+"T07:00:00+09:00"), predictor=lambda targets,*a: np.tile([.2,.3,.5],(len(targets),1)))["added"] == 1
    assert not case.model.inputs


def test_snapshot_has_no_weekend_results_and_order_is_irrelevant(case):
    friday(case)
    case.current.schedule.iloc[:] = case.current.schedule.sample(frac=1,random_state=3).to_numpy()
    p = prepare(case)
    expected = p.context["snapshot"]["ratings"].copy()
    reverse = p.targets.iloc[::-1]
    reversed_values = w.probability_rows(case.backend.artifact, reverse, expected)
    assert np.array_equal(reversed_values[::-1], p.values)
    assert p.context["snapshot"]["ratings"] == expected
    assert p.context["snapshot"]["history_count"] == 6  # toy training1 + special1 + four finished fixtures
    assert p.context["snapshot"]["elo_parameters"]["K"] == 30


@pytest.mark.parametrize("problem", ["history", "candidate", "saturday_result", "late_source", "missing_witness", "late_witness", "changed_input", "kickoff", "date", "club", "id"])
def test_gates_stop_before_estimator(case, problem):
    friday(case)
    observed = "2026-08-20T21:00:00+00:00"
    if problem == "history":case.rows[20]["match_date"] = "2026-08-20"
    if problem == "candidate":case.rows[10]["status"] = "candidate"
    if problem == "saturday_result":set_completed(case.rows[11]); observed = "2026-08-23T00:00:00+00:00"
    if problem == "late_source":observed = "2026-08-20T22:00:01+00:00"
    if problem == "missing_witness":del case.backend.witnesses["special"]
    if problem == "late_witness":case.backend.witnesses["special"]["fetched_at_utc"] = "2026-08-20T22:00:01+00:00"
    if problem == "changed_input":Path(case.backend.witnesses["special"]["path"]).write_bytes(b"tampered")
    if problem == "kickoff":case.rows[10]["kickoff_time"] = "06:00"
    if problem == "date":case.rows[10]["match_date"] = "2026-08-25"
    if problem == "club":case.rows[10]["home_team"] = "Club 2"
    if problem == "id":case.rows[10]["match_id"] = case.rows[10]["match_page_id"] = "123456"
    before = snapshot(case.runtime / "batches")
    with pytest.raises((ValueError,AssertionError)):
        case.current = publish_runtime(case, observed, "5" * 64)
        prepare(case)
    assert not case.model.inputs and snapshot(case.runtime / "batches") == before


@pytest.mark.parametrize("now", ["2026-08-21T06:59:59+09:00", "2026-08-21T19:00:00+09:00", "2026-08-22T07:00:00+09:00"])
def test_actual_execution_time_not_backdated(case, now):
    friday(case)
    with pytest.raises(ValueError):prepare(case, datetime.fromisoformat(now))
    assert not case.model.inputs


def test_partial_legacy_saved_and_late_reservation_hold(case):
    saved, _ = update.saved_batches(case.runtime)
    with pytest.raises(ValueError,match="partial_or_legacy"):
        case.backend.reserve(case.current, saved + [dict(fixture_key=case.rows[10]["fixture_key"])], TUESDAY)
    with pytest.raises(ValueError,match="late_reservation"):
        case.backend.reserve(case.current, saved, FRIDAY)
    assert not case.model.inputs


@pytest.mark.parametrize("point", ["before_predictions.csv", "after_predictions.csv", "after_bindings.csv", "after_snapshot.json", "before_manifest", "before_publish"])
def test_failure_before_single_visibility_boundary_publishes_zero(case, point):
    friday(case);p = prepare(case);records,bindings = outputs(case,p)
    before = snapshot(case.runtime / "batches")
    def fault(where):
        if where == point:raise OSError("synthetic disk/crash failure")
    with pytest.raises(OSError):case.backend.commit(p,records,bindings,lambda:FRIDAY,fault)
    assert snapshot(case.runtime / "batches") == before
    assert list(case.runtime.glob(".pending-*"))
    with pytest.raises(FileExistsError):prepare(case)
    assert len(case.model.inputs) == 1


@pytest.mark.parametrize("change", ["pointer", "input", "deadline", "clock_reverse"])
def test_inputs_and_time_rechecked_at_publication(case, change):
    friday(case);p=prepare(case);records,bindings=outputs(case,p)
    def fault(where):
        if where == "before_publish" and change == "pointer":update.atomic_json(case.runtime/"official/latest.json",{})
        if where == "before_publish" and change == "input":Path(case.backend.witnesses["training"]["path"]).write_bytes(b"changed")
    clock = lambda:datetime.fromisoformat("2026-08-21T07:16:00+09:00") if change == "deadline" else datetime.fromisoformat("2026-08-21T07:00:00+09:00") if change == "clock_reverse" else FRIDAY
    before=snapshot(case.runtime/"batches")
    with pytest.raises(ValueError):case.backend.commit(p,records,bindings,clock,fault)
    assert snapshot(case.runtime/"batches")==before


def test_duplicate_execution_before_commit_does_not_infer_twice(case):
    friday(case);p=prepare(case)
    with pytest.raises(FileExistsError):prepare(case)
    records,bindings=outputs(case,p);case.backend.commit(p,records,bindings,lambda:FRIDAY)
    before=snapshot(case.runtime/"batches")
    with pytest.raises(ValueError,match="already_published"):case.backend.commit(p,records,bindings,lambda:FRIDAY)
    assert len(case.model.inputs)==1 and snapshot(case.runtime/"batches")==before


@pytest.mark.parametrize("file", ["manifest.json", "snapshot.json", "predictions.csv", "bindings.csv"])
def test_reader_rejects_tampering_and_missing_context(case,file):
    friday(case);p=prepare(case);records,bindings=outputs(case,p);directory=case.backend.commit(p,records,bindings,lambda:FRIDAY)
    (directory/file).write_bytes(b"{}")
    with pytest.raises((ValueError,KeyError)):update.saved_batches(case.runtime)


def test_v2_cannot_fall_back_to_legacy_manifest(case):
    friday(case);p=prepare(case);records,bindings=outputs(case,p);directory=case.backend.commit(p,records,bindings,lambda:FRIDAY)
    (directory/"manifest.json").write_bytes(w.body({name:w.sha(directory/name) for name in ["predictions.csv","bindings.csv"]}))
    with pytest.raises(ValueError):update.saved_batches(case.runtime)


def test_evening_never_calls_any_estimator(case):
    friday(case)
    assert invoke(case,FRIDAY,"evening")["added"]==0
    assert not case.model.inputs


def test_enabled_cli_path_requires_explicit_offline_capability_before_io(tmp_path):
    source=tmp_path/"source";source.mkdir();runtime=tmp_path/"runtime"
    with pytest.raises(ValueError,match="weekend_offline_only"):
        update.run_update(source,runtime,"morning",CONFIG)
    assert not runtime.exists()


@pytest.mark.parametrize("anchor,start,end", [("2026-10-30","2026-10-30","2026-11-02"),("2027-12-31","2027-12-31","2028-01-03")])
def test_calendar_month_and_year_crossing(anchor,start,end):
    assert w.period(anchor)["start"]==start and w.period(anchor)["end"]==end
    assert feed.next_saved_period(end)[:2]==(start,end)


def test_workspace_rejects_existing_or_non_temp_output(tmp_path):
    with pytest.raises(FileExistsError):w.SyntheticWorkspace.create(tmp_path)
    with pytest.raises(ValueError):w.SyntheticWorkspace.create(feed.ROOT/"weekend-output")


def test_static_boundary_has_no_deserializer_network_fit_or_live_activation():
    tree=ast.parse(Path(w.__file__).read_text(encoding="utf8"))
    for node in ast.walk(tree):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
            assert node.func.attr not in {"fit","fit_transform","urlopen","load_champion","load_model","connect"}
        if isinstance(node,ast.Import):
            assert all(alias.name.split('.')[0] not in {'joblib','pickle','sklearn','requests','socket','http','urllib'} for alias in node.names)
    assert w.policy({}) is None and w.policy({"weekend_policy":{"enabled":False}}) is None


def test_monday_is_in_same_snapshot(case):
    case.rows[19]["match_date"] = "2026-08-24"
    case.current = publish_runtime(case,"2026-08-17T22:00:00+00:00","6"*64)
    friday(case)
    assert invoke(case,FRIDAY)["added"] == 10
    data=json.loads((case.runtime/"view/champion_home.json").read_bytes())
    assert len(data['nextRound']['matches'])==10
    assert any(m['kickoffAt'].startswith('2026-08-24') for m in data['nextRound']['matches'])


@pytest.mark.parametrize("status",['postponed','cancelled'])
def test_unsupported_schedule_status_never_silently_drops_target(case,status):
    reserve(case);case.rows[10]['status']=status
    with pytest.raises(ValueError):publish_runtime(case,"2026-08-20T21:00:00+00:00","6"*64)
    assert not case.model.inputs


def test_tampered_in_memory_results_do_not_match_source_bytes(case):
    friday(case)
    case.current.completed.loc[0,'home_score']='9'
    with pytest.raises(ValueError,match='result_projection'):prepare(case)
    assert not case.model.inputs


def test_real_estimator_object_cannot_be_used_with_offline_backend(case):
    artifact=champion.ChampionArtifact(object(),object(),pd.DataFrame())
    with pytest.raises(ValueError,match='synthetic_estimator_required'):
        w.OfflineWeekendBackend(case.backend.workspace,artifact,case.backend.special,case.backend.witnesses)


def test_completed_weekend_and_typed_id_transition_remain_noop(case):
    friday(case);invoke(case,FRIDAY)
    before=snapshot(case.runtime/'batches')
    for row in case.rows[10:20]:set_completed(row)
    case.current=publish_runtime(case,'2026-08-24T21:00:00+00:00','6'*64)
    assert invoke(case,datetime.fromisoformat('2026-08-25T07:00:00+09:00'))['added']==0
    assert len(case.model.inputs)==1 and snapshot(case.runtime/'batches')==before


def test_changed_schedule_after_commit_holds_without_modifying_archive(case):
    friday(case);invoke(case,FRIDAY);before=snapshot(case.runtime/'batches')
    case.rows[10]['match_date']='2026-08-25'
    case.current=publish_runtime(case,'2026-08-20T21:00:00+00:00','6'*64)
    with pytest.raises(ValueError,match='HOLD_REVIEW_ON_SCHEDULE_CHANGE'):invoke(case,FRIDAY)
    assert len(case.model.inputs)==1 and snapshot(case.runtime/'batches')==before


def test_concurrent_daily_append_is_rejected_before_weekend_visibility(case):
    friday(case);p=prepare(case);records,bindings=outputs(case,p)
    def fault(where):
        if where=='before_publish':update.publish_batch(case.runtime,records[:1],bindings[:1])
    with pytest.raises(ValueError,match='concurrent_saved_overlap'):
        case.backend.commit(p,records,bindings,lambda:FRIDAY,fault)
    assert not list((case.runtime/'batches').glob(w.PREFIX+'*'))
    assert len(update.saved_batches(case.runtime)[0])==5  # four prior + competing synthetic daily1


def test_shared_publication_lock_refuses_concurrent_or_abandoned_owner(case):
    friday(case);p=prepare(case);records,bindings=outputs(case,p)
    lock=case.runtime/'prediction-publication.lock';lock.write_bytes(b'other owner')
    with pytest.raises(FileExistsError):case.backend.commit(p,records,bindings,lambda:FRIDAY)
    assert lock.read_bytes()==b'other owner' and not list((case.runtime/'batches').glob(w.PREFIX+'*'))


def test_feed_failure_after_batch_commit_keeps_archive_and_never_repredicts(case,monkeypatch):
    friday(case)
    before=(case.runtime/'view/champion_home.json').read_bytes()
    original=update.publish_display_feeds
    def fail(*a):raise OSError('Synthetic display failure after canonical batch commit')
    monkeypatch.setattr(update,'publish_display_feeds',fail)
    with pytest.raises(OSError):invoke(case,FRIDAY)
    archive=snapshot(case.runtime/'batches')
    assert len(list((case.runtime/'batches').glob(w.PREFIX+'*')))==1
    assert (case.runtime/'view/champion_home.json').read_bytes()==before
    assert len(case.model.inputs)==1
    monkeypatch.setattr(update,'publish_display_feeds',original)
    assert invoke(case,FRIDAY)['added']==0
    assert snapshot(case.runtime/'batches')==archive and len(case.model.inputs)==1


def test_forged_workspace_cannot_escape_temporary_storage(tmp_path):
    forged=w.SyntheticWorkspace(feed.ROOT)
    with pytest.raises(ValueError,match='temporary_workspace_required'):
        forged.check(feed.ROOT,feed.ROOT/'runtime')


def test_full_month_crossing_target_snapshot(case):
    days=['2026-10-30']+['2026-10-31']*4+['2026-11-01']*4+['2026-11-02']
    for row,day in zip(case.rows[10:20],days):row['match_date']=day
    config={**CONFIG,'weekend_policy':{**CONFIG['weekend_policy'],'friday':'2026-10-30'}}
    case.backend.bind(case.repo['root'],case.runtime,config)
    current=publish_runtime(case,'2026-10-26T21:00:00+00:00','7'*64)
    saved,_=update.saved_batches(case.runtime)
    case.backend.reserve(current,saved,datetime.fromisoformat('2026-10-27T07:00:00+09:00'))
    case.current=publish_runtime(case,'2026-10-29T21:00:00+00:00','8'*64)
    now=datetime.fromisoformat('2026-10-30T07:00:30+09:00')
    p=prepare(case,now);r,b=outputs(case,p);directory=case.backend.commit(p,r,b,lambda:now)
    assert w.read_batch(directory)[2]['period']['end']=='2026-11-02'


def test_changed_prediction_between_inference_and_commit_is_rejected(case):
    friday(case);p=prepare(case);records,bindings=outputs(case,p)
    records[0]['a_p_home'],records[0]['a_p_away']='0.2','0.5'
    with pytest.raises(ValueError,match='output_prediction_changed'):
        case.backend.commit(p,records,bindings,lambda:FRIDAY)
    assert not list((case.runtime/'batches').glob(w.PREFIX+'*'))


def test_binding_cannot_point_to_a_different_valid_witness(case):
    friday(case);p=prepare(case);records,bindings=outputs(case,p)
    bindings[0]['identity_witness_revision_id']='9'*64
    with pytest.raises(ValueError,match='binding_snapshot_conflict'):
        case.backend.commit(p,records,bindings,lambda:FRIDAY)
    assert not list((case.runtime/'batches').glob(w.PREFIX+'*'))


def test_offline_backend_cannot_implicitly_use_real_collector_or_predictor(case):
    before=snapshot(case.runtime)
    with pytest.raises(ValueError,match='synthetic_callbacks_required'):
        update.run_update(case.repo['root'],case.runtime,'morning',CONFIG,weekend_backend=case.backend)
    assert snapshot(case.runtime)==before and not case.model.inputs


@pytest.mark.parametrize('committed',[False,True])
def test_evening_schedule_review_holds_without_any_new_prediction(case,committed):
    friday(case)
    if committed:invoke(case,FRIDAY)
    archive=snapshot(case.runtime/'batches');calls=len(case.model.inputs)
    case.rows[10]['kickoff_time']='20:00'
    case.current=publish_runtime(case,'2026-08-20T21:00:00+00:00','6'*64)
    with pytest.raises(ValueError,match='HOLD_REVIEW_ON_SCHEDULE_CHANGE'):
        invoke(case,FRIDAY,slot='evening')
    assert len(case.model.inputs)==calls and snapshot(case.runtime/'batches')==archive
