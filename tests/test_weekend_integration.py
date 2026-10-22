"""End-to-end fake HTML -> receipt -> Elo/mock -> atomic batch -> saved feed."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import test_weekend_source as source_tests
from test_weekend_source import factory, tree
from test_weekend_batch import MockModel, MockScaler, no_real_estimator_or_network
from test_dashboard_feed import csv_bytes, production_and_network_firewall
from scripts import update_champion_dashboard as update
from scripts import build_dashboard_feed as feed
from src.modeling import champion_prediction as champion
from src.modeling import weekend_batch as w
from src.modeling import weekend_source as source
from src.modeling import weekend_integration as integration
from src.collect import jleague_ongoing as ongoing
from test_jleague_ongoing_update import listing_html, write_source, write_completion


def utc(day, hour):
    return datetime.fromisoformat(day + 'T' + hour + '+09:00').astimezone(timezone.utc)


def install(candidate, destination):
    """Synthetic night publisher registry: retain old revisions, change latest once."""
    for path in (candidate.root / 'official/revisions').rglob('*'):
        if path.is_file():
            target = destination / 'revisions' / path.relative_to(candidate.root / 'official/revisions')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists(): assert target.read_bytes() == path.read_bytes()
            else: w.write_new(target, path.read_bytes())
    update.atomic_json(destination / 'latest.json', w.read_json(candidate.root / 'official/latest.json'))


@pytest.fixture
def e2e(factory, tmp_path, monkeypatch, request):
    friday = getattr(request, 'param', '2026-08-14')
    monkeypatch.setattr(source_tests, 'FRIDAY', friday)
    original = source_tests.synthetic_fixtures
    def fixtures():
        rows = original()
        for row in rows:
            if row['round'] >= 3:
                row['date'] = date.fromisoformat(friday)+timedelta(days=7+4*(row['round']-3))
        return rows
    monkeypatch.setattr(source_tests, 'synthetic_fixtures', fixtures)
    day = date.fromisoformat(friday)
    monday = (day-timedelta(days=4)).isoformat()
    tuesday = (day-timedelta(days=3)).isoformat()
    thursday = (day-timedelta(days=1)).isoformat()
    first = factory(fetched=utc(monday, '22:00:00'))
    repo = tmp_path / 'repo'
    teams = repo / feed.TEAM_MASTER_PATH; teams.parent.mkdir(parents=True)
    teams.write_bytes((first.root / 'teams.csv').read_bytes())
    prediction = repo / feed.PREDICTION_ARTIFACT; prediction.parent.mkdir(parents=True)
    prediction.write_bytes(csv_bytes([], feed.MIXED_COLUMNS))
    binding = repo / feed.BINDING_PATH
    binding.write_bytes(csv_bytes([], update.BINDING_COLUMNS))
    install(first, repo / feed.ONGOING_PATH)
    workspace = w.SyntheticWorkspace.create(tmp_path / 'prediction-workspace')
    runtime = workspace.root / 'runtime'
    update.initialize(repo, runtime)
    training = pd.DataFrame([dict(match_id='train-1', match_date='2015-08-01', season='2015',
        home_team_id='team_0001',away_team_id='team_0002',target_class='2',elo_diff='0.0')])
    special = pd.DataFrame([dict(match_id='special-1',match_date='2026-06-01',home_team_id='team_0003',away_team_id='team_0004',result='0')])
    model = MockModel(); artifact = champion.ChampionArtifact(MockScaler(),model,training)
    witnesses = {}
    for name, data in {'training':training.to_csv(index=False,lineterminator='\n').encode(),
                       'special':special.to_csv(index=False,lineterminator='\n').encode(),'estimator':b'SYNTHETIC_ONLY'}.items():
        path = workspace.root / (name+'.txt');path.write_bytes(data)
        witnesses[name]=dict(path=str(path),sha256=w.sha(path),fetched_at_utc=utc(monday,'21:00:00').isoformat())
    witnesses['teams']=dict(path=str(teams),sha256=w.sha(teams),fetched_at_utc=utc(monday,'21:00:00').isoformat())
    config=dict(lookahead_days=7,max_source_age_hours=24,max_evidence_pages=20,
                weekend_policy=dict(enabled=True,friday=friday,deadline_seconds=900))
    reserve_backend=w.OfflineWeekendBackend(workspace,artifact,special,witnesses)
    reserve_backend.bind(repo,runtime,config)
    reservation, reservation_sha=reserve_backend.reserve(update.official(repo,runtime/'official'),[],utc(tuesday,'06:59:00'))
    night=factory(fetched=utc(thursday,'22:00:00'))
    source_workspace=source.Workspace.create(tmp_path/'source-workspace')
    ref=source.publish(source_workspace,night.root,night.revision,night.manifest_sha,friday,
                       clock=lambda:utc(thursday,'22:00:30'),monotonic=lambda:0.0)
    install(night,runtime/'official')
    backend=integration.ReceiptBoundBackend(workspace,artifact,special,witnesses,source_workspace,ref,monotonic=lambda:0.0)
    return SimpleNamespace(repo=repo,runtime=runtime,workspace=workspace,source_workspace=source_workspace,
        night=night,ref=ref,backend=backend,config=config,model=model,friday=friday,
        now=utc(friday,'07:00:00'),reservation=reservation,reservation_sha=reservation_sha,
        original_repo=tree(repo))


def forbidden(*args):
    pytest.fail('Pinned weekend must never invoke collector or daily predictor')


def invoke(c, *, slot='morning', now=None):
    return update.run_update(c.repo,c.runtime,slot,c.config,collector=forbidden,predictor=forbidden,
                             clock=lambda: now or c.now,weekend_backend=c.backend)


def batch(c):
    paths=list((c.runtime/'batches').glob(integration.PREFIX+'*'))
    assert len(paths)==1
    return paths[0]


def test_full_reservation_receipt_common_elo_atomic_batch_and_saved_feed(e2e,monkeypatch):
    calls=[]; replay=w.replay_ratings
    monkeypatch.setattr(w,'replay_ratings',lambda *a:(calls.append(True),replay(*a))[1])
    assert invoke(e2e)==dict(added=10,total=10,state='ready')
    assert len(calls)==len(e2e.model.inputs)==1
    path=batch(e2e);r,b,m,c=w.read_batch(path)
    assert len(r)==len(b)==m['count']==10 and m['format_version']==integration.FORMAT
    proof=w.read_json(path/'source-proof.json')
    assert proof['reference']==e2e.ref.__dict__ and proof['reservation_sha256']==e2e.reservation_sha
    assert c['snapshot']['frozen_at']==e2e.now.isoformat()
    assert np.array_equal(e2e.model.inputs[0].ravel(),[c['snapshot']['features'][row['fixture_key']] for row in r])
    view=w.read_json(e2e.runtime/'view/champion_home.json')
    assert view['schemaVersion']==1 and len(view['nextRound']['matches'])==10
    assert not any(word in json.dumps(view) for word in ['receipt_sha256','ratings','SYNTHETIC_ONLY','source_binding'])
    before=tree(e2e.runtime/'batches')
    assert invoke(e2e)['added']==0
    assert len(e2e.model.inputs)==len(calls)==1 and tree(e2e.runtime/'batches')==before
    assert tree(e2e.repo)==e2e.original_repo


@pytest.mark.parametrize('e2e',['2026-10-30','2027-01-01'],indirect=True)
def test_month_and_year_boundary_e2e(e2e):
    assert invoke(e2e)['added']==10
    _,_,m,c=w.read_batch(batch(e2e))
    assert m['period']==w.period(e2e.friday)
    proof=w.read_json(batch(e2e)/'source-proof.json')
    assert proof['receipt']['publication_completed_at_utc'] < c['snapshot']['frozen_at']


@pytest.mark.parametrize('point',['before_predictions.csv','after_bindings.csv','before_manifest','before_publish'])
def test_prepublication_fault_has_zero_visible_predictions_and_retains_attempt(e2e,monkeypatch,point):
    commit=e2e.backend.commit
    def interrupted(prepared,records,bindings,clock):
        def fault(event):
            if event==point:raise OSError('synthetic crash')
        return commit(prepared,records,bindings,clock,fault=fault)
    monkeypatch.setattr(e2e.backend,'commit',interrupted)
    with pytest.raises(OSError):invoke(e2e)
    assert not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))
    assert list((e2e.runtime/'weekend-attempts').glob('*.json'))
    assert len(e2e.model.inputs)==1
    with pytest.raises(ValueError,match='incomplete_attempt_no_resume'):invoke(e2e)
    assert len(e2e.model.inputs)==1


def test_feed_failure_after_commit_reprojects_without_inference(e2e,monkeypatch):
    old=(e2e.runtime/'view/champion_home.json').read_bytes()
    builder=update.build_display_feeds
    monkeypatch.setattr(update,'build_display_feeds',lambda *a:(_ for _ in ()).throw(OSError('synthetic feed error')))
    with pytest.raises(OSError):invoke(e2e)
    before=tree(e2e.runtime/'batches');assert batch(e2e).is_dir()
    assert (e2e.runtime/'view/champion_home.json').read_bytes()==old and len(e2e.model.inputs)==1
    monkeypatch.setattr(update,'build_display_feeds',builder)
    assert invoke(e2e)['added']==0 and len(e2e.model.inputs)==1
    assert tree(e2e.runtime/'batches')==before


@pytest.mark.parametrize('filename',['receipt.json','seal.json','reference.json'])
def test_receipt_mismatch_before_prediction_holds(e2e,filename):
    path=e2e.source_workspace.root/'receipts'/e2e.ref.revision_id/filename
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):invoke(e2e)
    assert not e2e.model.inputs and not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))


def test_evening_and_daily_reserved_selection_never_infer_weekend(e2e):
    assert invoke(e2e,slot='evening')['added']==0 and not e2e.model.inputs
    current=update.official(e2e.repo,e2e.runtime/'official')
    targets=update.select_targets(current,[],e2e.now,3,reserved_periods=[e2e.reservation['period']])
    assert targets.empty
    rows=pd.DataFrame(e2e.reservation['targets'],columns=champion.TARGET_COLUMNS)
    records,bindings=update.new_records(rows[:1],np.array([[.2,.3,.5]]),current,
                                       feed.load_team_master(e2e.repo/feed.TEAM_MASTER_PATH),e2e.now)
    with pytest.raises(ValueError,match='daily_reserved_fixture'):update.publish_batch(e2e.runtime,records,bindings)


def test_partial_legacy_saved_weekend_holds(e2e):
    current=update.official(e2e.repo,e2e.runtime/'official')
    rows=pd.DataFrame(e2e.reservation['targets'],columns=champion.TARGET_COLUMNS)
    r,b=update.new_records(rows[:1],np.array([[.2,.3,.5]]),current,
                           feed.load_team_master(e2e.repo/feed.TEAM_MASTER_PATH),e2e.now)
    update._publish_daily_batch(e2e.runtime,r,b)  # explicit corrupt/legacy synthetic state
    before=tree(e2e.runtime/'batches')
    with pytest.raises(ValueError,match='partial_or_legacy_saved'):invoke(e2e)
    assert not e2e.model.inputs and tree(e2e.runtime/'batches')==before


def later_publication(c, monkeypatch, *, saturday_result=False, reschedule=False):
    rows=deepcopy(c.night.fixtures)
    day=(date.fromisoformat(c.friday)+timedelta(days=1)).isoformat() if saturday_result else c.friday
    observed=utc(day,'22:00:00' if saturday_result else '07:00:30')
    if saturday_result:rows[11]['score']=(0,0)
    if reschedule=='outside_scope':rows[10]['date']+=timedelta(days=7)
    elif reschedule:rows[10]['kickoff']='20:00'
    root=c.workspace.root.parent/'later-publication'
    listing=write_source(root/'input/listing.html',listing_html(rows),timestamp=observed.isoformat())
    evidence=[]
    for number,row in enumerate([rows[0]]+([rows[11]] if saturday_result else []),1):
        p=write_completion(root/'input',row,number)
        md=w.read_json(p.with_suffix('.metadata.json'))
        write_source(p,p.read_text(encoding='utf8'),timestamp=(observed+timedelta(seconds=number)).isoformat(),url=md['requested_url'])
        evidence.append(p)
    for p in [listing,*evidence]:
        md=w.read_json(p.with_suffix('.metadata.json'))
        md['request_started_at_utc']=(datetime.fromisoformat(md['fetched_at_utc'])-timedelta(milliseconds=500)).isoformat()
        p.with_suffix('.metadata.json').write_bytes(w.body(md))
    class LaterDatetime(datetime):
        @classmethod
        def now(cls,tz=None):return (observed+timedelta(seconds=5)).astimezone(tz)
    monkeypatch.setattr(ongoing,'datetime',LaterDatetime)
    snap=ongoing.create_snapshot(root/'snapshots',listing_html=listing,evidence_html=evidence,snapshot_id='later-official')
    assert ongoing.process_snapshot(snap,root/'official')['publication_status']=='published'
    pointer=w.read_json(root/'official/latest.json')
    candidate=SimpleNamespace(root=root,revision=pointer['revision_id'],manifest_sha=pointer['manifest_sha256'])
    install(candidate,c.runtime/'official')
    return candidate,observed+timedelta(seconds=10)


def test_newer_latest_before_execution_is_not_an_input_revision(e2e,monkeypatch):
    later,_=later_publication(e2e,monkeypatch)
    assert later.revision!=e2e.ref.revision_id
    assert invoke(e2e,now=e2e.now+timedelta(minutes=1))['added']==10
    r,_,_,context=w.read_batch(batch(e2e))
    assert {p['source_revision'] for p in r}=={e2e.ref.revision_id}
    assert context['snapshot']['history_count']==3  # toy training/special + one frozen result
    assert context['snapshot']['source_observed_at']==utc((date.fromisoformat(e2e.friday)-timedelta(days=1)).isoformat(),'22:00:00').isoformat()


def test_saturday_result_does_not_change_saved_sunday_or_snapshot(e2e,monkeypatch):
    invoke(e2e)
    before=tree(e2e.runtime/'batches')
    original=w.read_batch(batch(e2e))
    later,now=later_publication(e2e,monkeypatch,saturday_result=True)
    assert len(update.official(e2e.repo,e2e.runtime/'official').completed)==2
    assert invoke(e2e,slot='evening',now=now)['added']==0
    assert len(e2e.model.inputs)==1 and tree(e2e.runtime/'batches')==before
    assert w.read_batch(batch(e2e))==original
    assert later.revision!=original[2]['official_revision']


@pytest.mark.parametrize('committed',[False,True])
@pytest.mark.parametrize('kind',['kickoff','outside_scope'])
def test_known_schedule_change_holds_before_new_inference_or_reprojection(e2e,monkeypatch,committed,kind):
    if committed:invoke(e2e)
    before=tree(e2e.runtime/'batches')
    later,now=later_publication(e2e,monkeypatch,reschedule=kind)
    with pytest.raises(ValueError,match='HOLD_REVIEW_ON_SCHEDULE_CHANGE'):invoke(e2e,now=now)
    assert len(e2e.model.inputs)==int(committed) and tree(e2e.runtime/'batches')==before


def test_source_change_after_model_is_rejected_before_visibility(e2e,monkeypatch):
    model=e2e.model.predict_proba
    def predict(matrix):
        result=model(matrix)
        path=e2e.source_workspace.root/'receipts'/e2e.ref.revision_id/'seal.json'
        path.write_bytes(path.read_bytes()+b' ')
        return result
    monkeypatch.setattr(e2e.model,'predict_proba',predict)
    with pytest.raises(ValueError):invoke(e2e)
    assert len(e2e.model.inputs)==1 and not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))
    assert list((e2e.runtime/'weekend-attempts').glob('*.json'))


def test_source_and_staged_output_rechecked_inside_publication_boundary(e2e,monkeypatch):
    commit=e2e.backend.commit
    def interrupted(prepared,records,bindings,clock):
        def fault(event):
            if event=='before_publish':
                pending=next(e2e.runtime.glob('.pending-weekend-v2-*'))
                p=pending/'predictions.csv';p.write_bytes(p.read_bytes()+b' ')
        return commit(prepared,records,bindings,clock,fault=fault)
    monkeypatch.setattr(e2e.backend,'commit',interrupted)
    with pytest.raises(ValueError,match='batch_sha'):invoke(e2e)
    assert not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))


def test_competing_publication_lock_is_not_reclaimed(e2e):
    p=e2e.runtime/'prediction-publication.lock';p.write_bytes(b'other owner')
    with pytest.raises(FileExistsError):invoke(e2e)
    assert p.read_bytes()==b'other owner' and not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))
    assert len(e2e.model.inputs)==1
    with pytest.raises(ValueError,match='incomplete_attempt_no_resume'):invoke(e2e)
    assert len(e2e.model.inputs)==1


def test_late_execution_and_backward_generation_clock_hold(e2e,monkeypatch):
    with pytest.raises(ValueError,match='execution_deadline'):invoke(e2e,now=e2e.now+timedelta(seconds=901))
    assert not e2e.model.inputs
    model=e2e.model.predict_proba
    def predict(matrix):
        result=model(matrix);e2e.now-=timedelta(microseconds=1);return result
    monkeypatch.setattr(e2e.model,'predict_proba',predict)
    with pytest.raises(ValueError,match='clock_moved_backwards'):invoke(e2e)
    assert not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))


def test_late_source_acquisition_cannot_produce_capability_or_fallback(e2e,factory):
    fetched=e2e.now+timedelta(microseconds=1)
    candidate=factory(fetched=fetched)
    lane=source.Workspace.create(e2e.workspace.root.parent/'late-source')
    with pytest.raises(ValueError):
        source.publish(lane,candidate.root,candidate.revision,candidate.manifest_sha,e2e.friday,
                       clock=lambda:fetched+timedelta(seconds=2),monotonic=lambda:0.0)
    with pytest.raises(ValueError,match='source_capability_required'):
        integration.ReceiptBoundBackend(e2e.workspace,e2e.backend.artifact,e2e.backend.special,
                                        e2e.backend.witnesses,lane,None)
    assert not e2e.model.inputs


@pytest.mark.parametrize('artifact',['source-proof.json','snapshot.json','manifest.json'])
def test_bound_reader_rejects_missing_or_corrupt_proof(e2e,artifact):
    invoke(e2e);p=batch(e2e)/artifact
    p.write_bytes(p.read_bytes()+b' ')
    # Address/SHA checks apply even when JSON still parses to the same value.
    with pytest.raises(ValueError):update.saved_batches(e2e.runtime)


def test_bound_batch_cannot_be_downgraded_to_previous_v2(e2e):
    invoke(e2e);p=batch(e2e);m=w.read_json(p/'manifest.json')
    m['format_version']=w.FORMAT;m.pop('source_binding_sha256')
    (p/'manifest.json').write_bytes(w.body(m))
    p.rename(p.with_name(w.PREFIX+w.sha(p/'manifest.json')))
    with pytest.raises(ValueError):update.saved_batches(e2e.runtime)


def test_real_cli_defaults_and_missing_capability_are_refused_before_any_io(e2e):
    before=tree(e2e.runtime)
    with pytest.raises(ValueError,match='synthetic_callbacks_required'):
        update.run_update(e2e.repo,e2e.runtime,'morning',e2e.config,weekend_backend=e2e.backend)
    with pytest.raises(ValueError,match='weekend_offline_only'):
        update.run_update(e2e.repo,e2e.runtime,'morning',e2e.config)
    assert tree(e2e.runtime)==before and not e2e.model.inputs


def test_future_applicability_observation_is_not_available(e2e,monkeypatch):
    later_publication(e2e,monkeypatch)
    with pytest.raises(ValueError,match='future_applicability'):invoke(e2e)
    assert not e2e.model.inputs


@pytest.mark.parametrize('mutation',['clock','features'])
def test_actual_preinference_time_and_snapshot_are_rechecked(e2e,monkeypatch,mutation):
    original=e2e.backend.before_inference
    def intervene(current,snapshot,pins,clock):
        original(current,snapshot,pins,clock)
        if mutation=='clock':e2e.now+=timedelta(seconds=901)
        else:snapshot['features'][next(iter(snapshot['features']))]+=1
    monkeypatch.setattr(e2e.backend,'before_inference',intervene)
    with pytest.raises(ValueError,match='inference_deadline|snapshot_changed_during_preflight'):invoke(e2e)
    assert not e2e.model.inputs and not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))


def test_output_mutation_after_save_checkpoint_is_rejected(e2e,monkeypatch):
    original=e2e.backend.before_commit
    def intervene(prepared,records,bindings,clock):
        files=original(prepared,records,bindings,clock)
        records[0]['a_p_away']=0.1
        return files
    monkeypatch.setattr(e2e.backend,'before_commit',intervene)
    with pytest.raises(ValueError,match='output_prediction_changed'):invoke(e2e)
    assert not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))


def test_live_source_is_rechecked_after_staging(e2e,monkeypatch):
    original=e2e.backend.commit
    def intervene(prepared,records,bindings,clock):
        def fault(event):
            if event=='before_publish':
                p=e2e.source_workspace.root/'receipts'/e2e.ref.revision_id/'receipt.json'
                p.write_bytes(p.read_bytes()+b' ')
        return original(prepared,records,bindings,clock,fault=fault)
    monkeypatch.setattr(e2e.backend,'commit',intervene)
    with pytest.raises(ValueError):invoke(e2e)
    assert not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))


def test_rehashed_proof_still_requires_checkpoint_chronology(e2e):
    invoke(e2e);p=batch(e2e)
    proof=w.read_json(p/'source-proof.json')
    proof['before_save']['checkpoint_at_utc']=(e2e.now-timedelta(microseconds=1)).isoformat()
    (p/'source-proof.json').write_bytes(w.body(proof))
    context=w.read_json(p/'snapshot.json');context['source_binding']['sha256']=w.digest(proof)
    (p/'snapshot.json').write_bytes(w.body(context))
    manifest=w.read_json(p/'manifest.json');manifest['source_binding_sha256']=w.digest(proof)
    manifest['files'].update({name:w.sha(p/name) for name in ['source-proof.json','snapshot.json']})
    (p/'manifest.json').write_bytes(w.body(manifest))
    p=p.rename(p.with_name(integration.PREFIX+w.sha(p/'manifest.json')))
    with pytest.raises(ValueError,match='checkpoint_chronology'):w.read_batch(p)


def test_clock_reversal_between_preinference_and_generation_is_rejected(e2e,monkeypatch):
    check=e2e.backend.before_inference;predict=e2e.model.predict_proba
    def before(*args):
        check(*args);e2e.now+=timedelta(seconds=1)
    def model(matrix):
        result=predict(matrix);e2e.now-=timedelta(seconds=1);return result
    monkeypatch.setattr(e2e.backend,'before_inference',before)
    monkeypatch.setattr(e2e.model,'predict_proba',model)
    with pytest.raises(ValueError,match='clock_moved_backwards'):invoke(e2e)
    assert len(e2e.model.inputs)==1 and not list((e2e.runtime/'batches').glob(integration.PREFIX+'*'))


def test_previous_night_evening_slot_does_not_freeze_or_infer(e2e):
    now=utc((date.fromisoformat(e2e.friday)-timedelta(days=1)).isoformat(),'22:00:31')
    assert invoke(e2e,slot='evening',now=now)['added']==0
    assert e2e.backend.provider is None and not e2e.model.inputs
    assert not list((e2e.runtime/'weekend-attempts').glob('*.json'))
    assert invoke(e2e)['added']==10 and len(e2e.model.inputs)==1
