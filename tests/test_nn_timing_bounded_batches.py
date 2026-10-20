"""Offline global-budget, batch-stop and source-chronology tests."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
from types import SimpleNamespace

import pytest

path=os.environ.get('J1AI_TIMING_BATCH_IMPLEMENTATION')
if not path:
    pytest.skip('Set J1AI_TIMING_BATCH_IMPLEMENTATION to the sealed research implementation',allow_module_level=True)
source=Path(path)
if hashlib.sha256(source.read_bytes()).hexdigest()!='b7028ec56c9370e2592adb330903e540083800494634511039b89bc3157b7fed':
    raise ValueError('Batch implementation SHA mismatch')
spec=importlib.util.spec_from_file_location('bounded_batches_local',source)
batch=importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args,**kwargs): raise AssertionError('Synthetic tests cannot connect')
    monkeypatch.setattr(socket,'create_connection',forbidden)


def permit():
    rows=[{'identity':'fixture:'+str(i),'data_site_match_id':str(i),'series':'ongoing',
           'url':'https://data.j-league.or.jp/SFMS02/?match_card_id='+str(i),
           'complete_expected_header':'2026/27 synthetic full header'} for i in range(1000,1276)]
    return {'kind':'fixtures','approved':True,'network_enabled':True,'rows':rows,'max_total_GET':276,
            'batch_size':12,'max_batches':23,'allowed_host':batch.HOST,'timeout_seconds':10,
            'worker_deadline_seconds':10,'global_timeout_seconds':4500,'interval_seconds':5,
            'retries':0,'redirect_following':False,'parallel_downloads':0,'max_body_bytes':2097152,
            'max_total_body_bytes':578813952,'previous_twelve_URLs':[],
            'fixed_remaining_URLs':[r['url'] for r in rows]}


@pytest.mark.parametrize('change',['277','duplicate_URL','duplicate_ID','identity','host','retry','redirect','parallel',
                                  'old_twelve','wrong_ID','no_header','wrong_body_cap','no_deadline'])
def test_global_permit_rejects_scope_or_policy_expansion(change):
    p=permit()
    if change=='277':p['rows'].append(dict(p['rows'][0]))
    if change=='duplicate_URL':p['rows'][1]['url']=p['rows'][0]['url']
    if change=='duplicate_ID':p['rows'][1]['data_site_match_id']=p['rows'][0]['data_site_match_id']
    if change=='identity':p['rows'][1]['identity']=p['rows'][0]['identity']
    if change=='host':p['allowed_host']='evil.test'
    if change=='retry':p['retries']=1
    if change=='redirect':p['redirect_following']=True
    if change=='parallel':p['parallel_downloads']=1
    if change=='old_twelve':p['previous_twelve_URLs']=[p['rows'][0]['url']]
    if change=='wrong_ID':p['rows'][0]['url']='https://data.j-league.or.jp/SFMS02/?match_card_id=999'
    if change=='no_header':p['rows'][0]['complete_expected_header']=''
    if change=='wrong_body_cap':p['max_total_body_bytes']+=1
    if change=='no_deadline':p['global_timeout_seconds']=None
    with pytest.raises(ValueError):batch.validate(p)


@pytest.mark.parametrize('status',[200,403,429,302])
def test_single_transport_GET_TLS_no_redirect_or_retry(status,tmp_path,monkeypatch):
    p=permit();calls=[]
    class Response:
        def __init__(self):self.status=status;self.body=b'synthetic'
        def getheaders(self):return [('Content-Type','text/html;charset=UTF-8')]
        def read(self,n):result,self.body=self.body[:n],self.body[n:];return result
    class Connection:
        def __init__(self,host,port,timeout,context):
            assert host==batch.HOST and port==443 and timeout==10
            assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
        def request(self,method,path,headers):calls.append((method,path))
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(batch,'safe',lambda path:Path(path))
    meta=batch.worker(p,'a'*64,1,tmp_path,Connection)
    assert calls==[('GET','/SFMS02/?match_card_id=1000')]
    assert meta['success']==(status==200) and meta['GET_attempts']==1 and meta['automatic_retries']==0
    assert hashlib.sha256((tmp_path/'raw.html').read_bytes()).hexdigest()==meta['sha256']
    assert hashlib.sha256((tmp_path/'request.json').read_bytes()).hexdigest()==meta['request_sha256']
    with pytest.raises(ValueError,match='attempt_already_exists'):batch.worker(p,'a'*64,1,tmp_path,Connection)


def test_remarks_categories_and_no_implicit_unknown_adoption():
    assert batch.remarks_classification({'status':'PASS','remarks':[]})=='EMPTY'
    assert batch.remarks_classification({'status':'PASS','remarks':['84\u0027\u8b66\u544a(C3)ClubCoach(\u76e3\u7763)']})=='KNOWN_NON_TIMING_NOTE'
    assert batch.remarks_classification({'status':'PASS','remarks':['unknown text']})=='UNKNOWN_FORMAT'
    assert batch.remarks_classification({'status':'HOLD','timing_notes':['\u4e2d\u65ad']})=='REQUIRES_TIMING_AUDIT'


@pytest.mark.parametrize('outcome',['all_PASS','HTTP_429','hard_timeout','unknown_note','timing_note','batch_2_failure'])
def test_23_batches_global_stop_budget_rate_and_no_restart(outcome,tmp_path,monkeypatch):
    p=permit();plan=[{'batch':i+1,'rows':p['rows'][i*12:(i+1)*12]} for i in range(23)]
    planpath=tmp_path/'plan.json';planpath.write_bytes(batch.encoded(plan))
    access=tmp_path/'access';access.write_bytes(b'{}')
    p.update(input_SHA256={},core_path='core',guard_path='guard',team_master_path='unused',
             access_raw_path=str(access),access_metadata_path=str(access),batch_plan_path=str(planpath),selection_sha256='f'*64)
    path=tmp_path/'permit.json';body=batch.encoded(p);path.write_bytes(body)
    monkeypatch.setattr(batch,'safe',lambda path:Path(path))
    def analyze(*args):
        if outcome=='timing_note':return {'status':'HOLD','timing_notes':['interruption'],'hold_reason':'new_timing_note'}
        return {'status':'PASS','remarks':['unknown'] if outcome=='unknown_note' else []}
    core=SimpleNamespace(analyze=analyze);guard=SimpleNamespace(access_gate=lambda *args:{'network_enabled':True})
    monkeypatch.setattr(batch,'load_module',lambda path,*args:core if path=='core' else guard)
    import src.collect.teams
    monkeypatch.setattr(src.collect.teams,'load_team_master',lambda path:object())
    clock=[0.0];starts=[];calls=[]
    monkeypatch.setattr(batch.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(batch.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    def run(command,timeout,capture_output):
        assert timeout==10 and capture_output
        ordinal=int(command[-1]);calls.append(ordinal);starts.append(clock[0]);clock[0]+=.25
        if outcome=='hard_timeout':raise subprocess.TimeoutExpired(command,timeout)
        folder=tmp_path/f'batch-{(ordinal-1)//12+1:02d}'/f'request_{(ordinal-1)%12+1:02d}'
        assert list(folder.iterdir())==[]
        request=b'{}';raw=b'synthetic'
        ok=outcome!='HTTP_429' and not (outcome=='batch_2_failure' and ordinal==13)
        meta={'success':ok,'status':200 if ok else 429,'bytes':len(raw),'sha256':batch.sha(raw),'request_sha256':batch.sha(request),
              'request_started_at_utc':'2026-10-20T10:00:00+00:00','response_completed_at_utc':'2026-10-20T10:00:01+00:00'}
        (folder/'request.json').write_bytes(request);(folder/'raw.html').write_bytes(raw)
        (folder/'metadata.json').write_bytes(batch.encoded(meta))
        (folder/'snapshot-save-receipt.json').write_bytes(batch.encoded({'snapshot_saved_at_utc':'2026-10-20T10:00:01+00:00'}))
        return SimpleNamespace(returncode=0,stderr=b'')
    monkeypatch.setattr(batch.subprocess,'run',run)
    report=batch.execute(path,batch.sha(body))
    count=276 if outcome=='all_PASS' else 13 if outcome=='batch_2_failure' else 1
    assert calls==list(range(1,count+1)) and report['attempted']==count
    assert report['not_attempted']==276-count and len(report['batch_records'])==23
    assert all(b-a>=5.25 for a,b in zip(starts,starts[1:]))
    assert report['status']==('DETAIL_EVIDENCE_ACQUIRED_RESEARCH_ONLY' if outcome=='all_PASS' else 'HOLD_BOUNDED_EVIDENCE_ACQUISITION')
    assert report['HISTORY']==report['PREDICTION']=='HOLD'
    assert all(x['C'].startswith('HOLD') and x['D'].startswith('HOLD') for x in report['attempts'])
    before=len(calls)
    with pytest.raises(FileExistsError):batch.execute(path,batch.sha(body))
    assert len(calls)==before


def test_writes_to_existing_source_rejected(tmp_path):
    with pytest.raises(ValueError,match='outside_new_research_root'):batch.write(tmp_path,'raw.html',b'forbidden')
