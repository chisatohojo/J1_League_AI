"""Saved-byte workflow and synthetic faults; sockets, models and collectors unused."""
from copy import deepcopy
from dataclasses import replace
import ast
import importlib.util
import json
from pathlib import Path
import socket
import sys
import pytest

source = Path(__file__).parents[1] / 'research/nn_v2/phase2_5B_12/offline_two_stage.py'
spec = importlib.util.spec_from_file_location('two_stage_offline_test', source)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


@pytest.fixture(autouse=True)
def no_external_effects(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError('Offline tests cannot use network or model deserialization')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    import pickle
    monkeypatch.setattr(pickle, 'load', forbidden)
    monkeypatch.setattr(pickle, 'loads', forbidden)


def example(i=0, kind='KNOWN'):
    mid = str(10000+i)
    row = {'identity':'jleague_data_site_sfms02:'+mid, 'data_site_match_id':mid,
           'url':'https://data.j-league.or.jp/SFMS02/?match_card_id='+mid,
           'complete_expected_header':'Synthetic competition season round', 'source_date':'2026-02-01',
           'source_reported_kickoff':'2026-02-01T13:03:00+09:00', 'home_score_90':1, 'away_score_90':0,
           'home_team_id':'synthetic_home', 'away_team_id':'synthetic_away',
           'pk_played':False, 'extra_time_played':False}
    raw = m.encoded({'kind':kind, 'fixture':mid})
    req = m.encoded({'url':row['url'], 'identity':row['identity'], 'method':'GET',
                     'request_started_at_utc':'2026-10-20T01:00:00+00:00', 'TLS_verification':True,
                     'timeout_seconds':10, 'automatic_retries':0, 'redirects_followed':0})
    meta = m.encoded({'status':200, 'success':True, 'complete_body':True, 'requested_url':row['url'],
                      'final_url':row['url'], 'sha256':m.sha(raw), 'bytes':len(raw), 'request_sha256':m.sha(req),
                      'request_started_at_utc':'2026-10-20T01:00:00+00:00',
                      'response_completed_at_utc':'2026-10-20T01:00:00.1+00:00',
                      'GET_attempts':1, 'automatic_retries':0, 'redirects_followed':0,
                      'content_type':'text/html;charset=UTF-8'})
    pins = {'url':row['url'], 'raw_sha256':m.sha(raw), 'metadata_sha256':m.sha(meta),
            'request_sha256':m.sha(req), 'response_completed_at_utc':'2026-10-20T01:00:00.1+00:00'}
    revision = {'source_CSV_sha256':'synthetic_frozen_revision'}
    p = m.SavedPacket(raw, meta, req, deepcopy(row), deepcopy(revision), {}, 'SYNTHETIC',
                      {'start':i*6, 'end':i*6+0.1, 'bytes':len(raw),
                       'outcome':'COMPLETE_200_VERIFIED_TLS_NO_REDIRECT'})
    return p, m.Expected(row, row['complete_expected_header'], pins, revision, row['complete_expected_header'])


def strict(raw, row, header):
    kind = json.loads(raw)['kind']
    r = {'identity':row['identity'], 'status':m.FINAL, 'source_raw_sha256':m.sha(raw),
         'competition_header':header, 'official_date':row['source_date'], 'official_kickoff':'13:03',
         'date_kickoff_match_saved_source':True,
         'completion_state':'OFFICIAL_RECORD_FINAL_PERIODS_MATCH_COMPLETED_SOURCE',
         'parsed':{'home_score_90':1, 'away_score_90':0, 'extra_time_played':False, 'home_pk_score':None},
         'timing_notes':[], 'remarks':[] if kind=='KNOWN' else [kind]}
    if kind=='TIMING':
        r.update(status='HOLD', timing_notes=['unclassified timing note'],
                 hold_reason='ValueError:new_or_ambiguous_timing_note_REQUIRES_REVIEW')
    if kind=='UNKNOWN_HTML':
        return {'status':'HOLD', 'hold_reason':'unknown identity/result structure'}
    return r


def review(raw, metadata, request, expected):
    base = strict(raw, expected.row, expected.header)
    hold = json.loads(raw)['kind'] != 'KNOWN'
    return {'status':'HOLD' if hold else 'PASS', 'strict_analysis':base,
            'legacy_category':'UNKNOWN_FORMAT' if hold else 'EMPTY_REMARKS',
            'reason':'UNKNOWN_REMARK_REQUIRES_REVIEW' if hold else None}


def run(tmp_path, items, **kwargs):
    store = m.ImmutableStore(tmp_path/'new')
    runner = m.ReplayRun(store, synthetic_budget=m.SyntheticBudget(count=30, deadline=300), **kwargs)
    return runner.run(items, strict, review), runner


def repin(p, e, *, meta=None, req=None, raw=None):
    raw = p.raw if raw is None else raw
    req = p.request if req is None else m.encoded(req)
    meta = json.loads(p.metadata) if meta is None else meta
    meta.update(sha256=m.sha(raw), bytes=len(raw), request_sha256=m.sha(req))
    data = m.encoded(meta)
    pins = {**e.pins, 'raw_sha256':m.sha(raw), 'metadata_sha256':m.sha(data), 'request_sha256':m.sha(req)}
    obs = {**p.synthetic_observation, 'bytes':len(raw)}
    return replace(p, raw=raw, metadata=data, request=req, synthetic_observation=obs), replace(e, pins=pins)


def test_one_unknown_then_eleven_clean_committed_before_successor(tmp_path):
    items = [example(0,'UNKNOWN')] + [example(i) for i in range(1,12)]
    result, runner = run(tmp_path, items)
    assert result['status']=='OFFLINE_REPLAY_COMPLETED'
    assert (result['source_acquired'], result['detail_PASS'], result['detail_HOLD'], result['quarantined'])==(12,11,1,1)
    q = runner.verify_receipt(runner.records[0]['receipt'], runner.records[0]['SHA256'])
    assert q['source_acquired'] is q['source_integrity_verified'] is q['quarantine_status'] is True
    assert q['history_admission_status'] is False and q['timing_evidence_status']=='HOLD_B_C_D'


def test_successor_is_not_even_yielded_before_quarantine_receipt_verified(tmp_path):
    store = m.ImmutableStore(tmp_path/'new')
    runner = m.ReplayRun(store, synthetic_budget=m.SyntheticBudget())
    def inputs():
        yield example(0,'UNKNOWN')
        assert len(runner.records)==1
        packet = runner.verify_receipt(runner.records[0]['receipt'],runner.records[0]['SHA256'])
        assert packet['quarantine_status'] is True
        yield example(1)
    assert runner.run(inputs(),strict,review)['detail_PASS']==1


def test_multiple_unknowns_and_unclassified_timing_remain_separate_holds(tmp_path):
    result, _ = run(tmp_path, [example(0,'UNKNOWN_STAFF'),example(1,'TIMING'),example(2,'DISMISSAL'),example(3)])
    assert (result['source_acquired'],result['detail_PASS'],result['detail_HOLD'])==(4,1,3)
    assert result['history_admitted']==0


@pytest.mark.parametrize('status',[403,429,302,500,None])
def test_unknown_then_HTTP_anomaly_stops_before_third_page(tmp_path,status):
    p,e=example(1);meta=json.loads(p.metadata);meta['status']=status;p,e=repin(p,e,meta=meta)
    result,_=run(tmp_path,[example(0,'UNKNOWN'),(p,e),example(2)])
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and result['source_acquired']==1 and result['detail_HOLD']==1


@pytest.mark.parametrize('field',['identity','data_site_match_id','url','source_date','source_reported_kickoff',
                                  'home_team_id','away_team_id','home_score_90','away_score_90','complete_expected_header'])
def test_changed_fixture_after_unknown_is_fatal(tmp_path,field):
    p,e=example(1);row=deepcopy(p.row);v=row[field];row[field]=v+1 if isinstance(v,int) else v+'changed'
    result,_=run(tmp_path,[example(0,'UNKNOWN'),(replace(p,row=row),e),example(2)])
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and result['source_acquired']==1


@pytest.mark.parametrize('field',['raw','metadata','request'])
def test_original_SHA_mismatch_is_STOP_not_quarantine(tmp_path,field):
    p,e=example();p=replace(p,**{field:getattr(p,field)+b' '})
    result,_=run(tmp_path,[(p,e),example(1)])
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and result['source_acquired']==0


@pytest.mark.parametrize('change',['revision','complete','identity_request','raw_internal','TLS','retry','redirect','twoget',
                                   'startUTC','responseUTC','timeoutpolicy','contenttype','unknownHTML'])
def test_rehashed_but_invalid_source_integrity_is_fatal(tmp_path,change):
    p,e=example();meta=json.loads(p.metadata);req=json.loads(p.request)
    if change=='revision':p=replace(p,source_revision={'source_CSV_sha256':'unapproved'})
    if change=='complete':meta['complete_body']=False
    if change=='identity_request':req['identity']='other'
    if change=='TLS':req['TLS_verification']=False
    if change=='retry':meta['automatic_retries']=1
    if change=='redirect':meta['redirects_followed']=1
    if change=='twoget':meta['GET_attempts']=2
    if change=='startUTC':req['request_started_at_utc']='2026-10-20T01:00:00+09:00'
    if change=='responseUTC':meta['response_completed_at_utc']='2026-10-20T01:00:11+00:00'
    if change=='timeoutpolicy':req['timeout_seconds']=None
    if change=='contenttype':meta['content_type']='application/octet-stream'
    if change=='unknownHTML':p,e=repin(p,e,raw=m.encoded({'kind':'UNKNOWN_HTML'}))
    if change not in {'unknownHTML'}:p,e=repin(p,e,meta=meta,req=req)
    if change=='raw_internal':
        meta=json.loads(p.metadata);meta['sha256']='0'*64;p=replace(p,metadata=m.encoded(meta));e=replace(e,pins={**e.pins,'metadata_sha256':m.sha(p.metadata)})
    result,_=run(tmp_path,[(p,e),example(1)])
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and result['detail_HOLD']==0


@pytest.mark.parametrize('field',['identity','parsed','official_kickoff'])
def test_stage_B_semantic_drift_is_STOP(tmp_path,field):
    store=m.ImmutableStore(tmp_path/'new');runner=m.ReplayRun(store,synthetic_budget=m.SyntheticBudget())
    def changed(*args):
        r=review(*args);r['strict_analysis'][field]='changed';return r
    result=runner.run([example(),example(1)],strict,changed)
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and result['source_acquired']==1 and result['detail_PASS']==0


@pytest.mark.parametrize('reason',['PACKET_SHA_MISMATCH','IDENTITY_MISMATCH','GK_RULE_SHA','REVISION_CHANGED'])
def test_stage_B_integrity_failure_cannot_be_disguised_as_unknown_remark(tmp_path,reason):
    store=m.ImmutableStore(tmp_path/'new');runner=m.ReplayRun(store,synthetic_budget=m.SyntheticBudget())
    def changed(*args):r=review(*args);r.update(status='HOLD',legacy_category='UNKNOWN_FORMAT',reason=reason);return r
    result=runner.run([example(),example(1)],strict,changed)
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and result['source_acquired']==1 and result['detail_HOLD']==0


def test_stage_B_cannot_pass_a_timing_HOLD(tmp_path):
    store=m.ImmutableStore(tmp_path/'new');runner=m.ReplayRun(store,synthetic_budget=m.SyntheticBudget())
    def unsafe(*args):r=review(*args);r.update(status='PASS');return r
    result=runner.run([example(0,'TIMING'),example(1)],strict,unsafe)
    assert result['status']=='OFFLINE_REPLAY_STOPPED'


@pytest.mark.parametrize('at',['quarantine-0001/packet.json','quarantine-0001/seal.json','receipt-0001.json'])
def test_quarantine_write_failure_prevents_successor_and_false_all_PASS(tmp_path,monkeypatch,at):
    store=m.ImmutableStore(tmp_path/'new');original=store.write
    def fail(name,data):
        if name==at:raise OSError('simulated storage interruption')
        return original(name,data)
    monkeypatch.setattr(store,'write',fail)
    runner=m.ReplayRun(store,synthetic_budget=m.SyntheticBudget())
    r=runner.run([example(0,'UNKNOWN'),example(1)],strict,review)
    assert r['status']=='OFFLINE_REPLAY_STOPPED' and not runner.records
    assert not (store.root/'source-0002').exists()
    if at!='quarantine-0001/packet.json':
        with pytest.raises(m.Stop):runner.aggregate()


def test_abrupt_exit_before_receipt_prevents_unapproved_resume(tmp_path,monkeypatch):
    class Crash(BaseException):pass
    store=m.ImmutableStore(tmp_path/'new');original=store.write
    def crash(name,data):
        if name=='receipt-0001.json':raise Crash()
        return original(name,data)
    monkeypatch.setattr(store,'write',crash)
    runner=m.ReplayRun(store,synthetic_budget=m.SyntheticBudget())
    with pytest.raises(Crash):runner.run([example(0,'UNKNOWN'),example(1)],strict,review)
    assert (store.root/'run-claim.json').exists() and not (store.root/'source-0002').exists()
    monkeypatch.setattr(store,'write',original)
    with pytest.raises(m.Stop):m.ReplayRun(store).run([],strict,review)
    with pytest.raises(m.Stop):runner.aggregate()


def test_file_fsync_failure_stops_without_running_stage_B(tmp_path,monkeypatch):
    store=m.ImmutableStore(tmp_path/'new');runner=m.ReplayRun(store)
    def fail(*args):raise OSError('fsync interrupted')
    monkeypatch.setattr(m.os,'fsync',fail)
    with pytest.raises(m.Stop):runner.run([],strict,review)
    assert not (store.root/'terminal-receipt.json').exists()


def test_SHA_readback_failure_stops(tmp_path,monkeypatch):
    store=m.ImmutableStore(tmp_path/'new');original=store.read
    monkeypatch.setattr(store,'read',lambda name:b'corrupted' if name=='run-claim.json' else original(name))
    with pytest.raises(m.Stop):m.ReplayRun(store).run([],strict,review)


def test_duplicate_and_previously_consumed_URLs_stop(tmp_path):
    r,_=run(tmp_path,[example(),example()]);assert r['status']=='OFFLINE_REPLAY_STOPPED' and r['source_acquired']==1


def test_explicitly_blocked_URL_cannot_be_reused(tmp_path):
    p,e=example();r,_=run(tmp_path,[(p,e)],blocked_urls=[e.row['url']])
    assert r['status']=='OFFLINE_REPLAY_STOPPED' and r['source_acquired']==0


def test_same_object_and_new_object_cannot_reexecute_a_stopped_run(tmp_path):
    p,e=example();r,runner=run(tmp_path,[(replace(p,raw=b'bad'),e)])
    assert r['status']=='OFFLINE_REPLAY_STOPPED'
    with pytest.raises(m.Stop):runner.run([],strict,review)
    with pytest.raises(m.Stop):m.ReplayRun(runner.store).run([],strict,review)


@pytest.mark.parametrize('outcome',['HTTP403','HTTP429','TIMEOUT','TLS_ERROR','ACCESS_LIMIT','REDIRECT','UNKNOWN_COMPLETION'])
def test_virtual_transport_fault_after_quarantine_is_global_STOP(tmp_path,outcome):
    p,e=example(1);p=replace(p,synthetic_observation={**p.synthetic_observation,'outcome':outcome})
    r,_=run(tmp_path,[example(0,'UNKNOWN'),(p,e),example(2)])
    assert r['status']=='OFFLINE_REPLAY_STOPPED' and r['source_acquired']==1


@pytest.mark.parametrize('change',['rate','duration','deadline','body','count','infinite','nan'])
def test_virtual_budget_failures_stop_after_prior_commit(tmp_path,change):
    p,e=example(1);obs=deepcopy(p.synthetic_observation)
    if change=='rate':obs.update(start=1,end=1.1)
    if change=='duration':obs.update(end=20)
    if change=='deadline':obs.update(start=301,end=301.1)
    if change=='body':obs['bytes']=2*1024*1024+1
    if change=='infinite':obs.update(start=float('inf'),end=float('inf'))
    if change=='nan':obs['start']=float('nan')
    store=m.ImmutableStore(tmp_path/'new');runner=m.ReplayRun(store,synthetic_budget=m.SyntheticBudget(count=1 if change=='count' else 12,deadline=300))
    r=runner.run([example(0,'UNKNOWN'),(replace(p,synthetic_observation=obs),e),example(2)],strict,review)
    assert r['status']=='OFFLINE_REPLAY_STOPPED' and r['source_acquired']==1


def test_no_synthetic_clock_can_be_attached_to_saved_official_witness(tmp_path):
    p,e=example();r,_=run(tmp_path,[(replace(p,source_mode='SAVED_OFFICIAL_WITNESS'),e)])
    assert r['status']=='OFFLINE_REPLAY_STOPPED'


def test_quarantine_cannot_be_omitted_from_aggregate(tmp_path):
    r,runner=run(tmp_path,[example(0,'UNKNOWN'),example(1)])
    assert r['detail_PASS']==1 and r['detail_HOLD']==1
    runner.records=runner.records[1:]
    with pytest.raises(m.Stop):runner.aggregate()


def test_quarantine_mutation_or_unreadable_packet_cannot_be_counted_as_PASS(tmp_path):
    _,runner=run(tmp_path,[example(0,'UNKNOWN')]);packet=runner.store.root/'quarantine-0001/packet.json'
    packet.write_bytes(b'changed')
    with pytest.raises(m.Stop):runner.aggregate()


def test_admission_is_denied_even_for_clean_detail(tmp_path):
    _,runner=run(tmp_path,[example()]);p=runner.verify_receipt(**{'name':runner.records[0]['receipt'],'h':runner.records[0]['SHA256']})
    with pytest.raises(m.Stop):m.require_history_admission(p)


@pytest.mark.parametrize('name',['../escape','/absolute','..','folder/../../escape'])
def test_storage_rejects_escape_and_existing_files(tmp_path,name):
    store=m.ImmutableStore(tmp_path/'new')
    with pytest.raises(m.Stop):store.write(name,b'no')
    store.write('one',b'one')
    with pytest.raises(FileExistsError):store.write('one',b'overwrite')


def test_existing_output_root_is_rejected(tmp_path):
    m.ImmutableStore(tmp_path/'new')
    with pytest.raises(FileExistsError):m.ImmutableStore(tmp_path/'new')


def test_earliest_pilot_schema_uses_sealed_separate_header_without_modifying_row(tmp_path):
    p,e=example();row={k:v for k,v in e.row.items() if k!='complete_expected_header'}
    req=json.loads(p.request);req['tls_verification']=req.pop('TLS_verification')
    req.pop('redirects_followed');req['redirect_following']=False
    meta=json.loads(p.metadata);meta['request_attempts']=meta.pop('GET_attempts');meta.pop('redirects_followed')
    p,e=repin(p,e,meta=meta,req=req);p=replace(p,row=deepcopy(row));e=replace(e,row=row)
    r,_=run(tmp_path,[(p,e)]);assert r['detail_PASS']==1


def test_boolean_is_not_a_valid_GET_count(tmp_path):
    p,e=example();meta=json.loads(p.metadata);meta['GET_attempts']=True;p,e=repin(p,e,meta=meta)
    r,_=run(tmp_path,[(p,e)]);assert r['status']=='OFFLINE_REPLAY_STOPPED' and r['source_acquired']==0


def test_reparse_attribute_is_rejected_before_storage_creation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import stat
    root=tmp_path/'new';original=Path.lstat
    monkeypatch.setattr(Path,'lstat',lambda p:SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=1024) if p==root else original(p))
    with pytest.raises(m.Stop):m.ImmutableStore(root)


def test_abrupt_partial_packet_write_leaves_claim_but_no_successor_or_valid_aggregate(tmp_path,monkeypatch):
    class Crash(BaseException):pass
    store=m.ImmutableStore(tmp_path/'new');original=store.write
    def partial(name,data):
        if name=='quarantine-0001/packet.json':
            target=store.path(name);target.parent.mkdir(parents=True)
            with target.open('xb') as f:
                f.write(data[:len(data)//2]);f.flush();m.os.fsync(f.fileno())
            raise Crash()
        return original(name,data)
    monkeypatch.setattr(store,'write',partial)
    runner=m.ReplayRun(store,synthetic_budget=m.SyntheticBudget())
    with pytest.raises(Crash):runner.run([example(0,'UNKNOWN'),example(1)],strict,review)
    assert (store.root/'quarantine-0001/packet.json').is_file()
    assert not (store.root/'receipt-0001.json').exists() and not (store.root/'source-0002').exists()
    with pytest.raises(m.Stop):runner.aggregate()
    monkeypatch.setattr(store,'write',original)
    with pytest.raises(m.Stop):m.ReplayRun(store).run([],strict,review)


def test_source_has_no_real_transport_permit_models_or_operational_imports():
    tree=ast.parse(source.read_text(encoding='utf8'))
    imports={a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
    imports|={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    assert imports <= {'dataclasses','datetime','hashlib','json','math','os','pathlib','re','stat'}
    forbidden={'connect','request','urlopen','execute','worker','fit','fit_transform','predict','predict_proba','load_model'}
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden]
    assert not any(isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and '__name__' in ast.unparse(n.test) for n in ast.walk(tree))
