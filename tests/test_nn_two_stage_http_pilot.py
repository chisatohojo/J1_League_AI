"""No live requests: injected HTTP responses and native Windows ownership/persistence."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import time
import pytest
from test_nn_two_stage_offline import example,strict,review,m

REPO=Path(__file__).parents[1]
OLD=REPO/'research/nn_v2/phase2_5B_13';CODE=REPO/'research/nn_v2/phase2_5B_14'
sys.path.insert(0,str(OLD));sys.path.insert(0,str(CODE))
import http_worker as worker
import http_integration as layer
import windows_local as win


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*a,**kw):raise AssertionError('Tests never access external sockets')
    monkeypatch.setattr(socket,'getaddrinfo',denied);monkeypatch.setattr(socket.socket,'connect',denied)


def approval(tmp_path,kind='DETAIL'):
    rows=[example(i)[1].row for i in range(3)] if kind=='DETAIL' else [{'url':'https://data.j-league.or.jp/robots.txt','identity':'ROBOTS_EXACT_URL'}]
    pins={str(p):worker.sha(p.read_bytes()) for p in [CODE/'http_worker.py',CODE/'http_integration.py',OLD/'windows_local.py',OLD/'local_integration.py']}
    return {'version':'real_http_small_pilot_v1','kind':kind,'host':worker.HOST,'rows':rows,'max_GET':len(rows),
        'socket_timeout_seconds':10,'parent_deadline_seconds':12,'interval_seconds':5,'body_cap':2097152 if kind=='DETAIL' else 65536,
        'total_body_cap':6291456 if kind=='DETAIL' else 65536,'retry':0,'redirect':0,'parallel':0,
        'global_deadline_seconds':180,'output_root':str(tmp_path/'transport'),'code_files':pins,'windows_module_directory':str(OLD)}


def task(p):return {'kind':'APPROVED_SINGLE_GET','ordinal':1,'row':deepcopy(p['rows'][0])}


@pytest.mark.parametrize('kind',['DETAIL','ROBOTS'])
def test_exact_independent_approval_caps(tmp_path,kind):
    p=approval(tmp_path,kind);row,cap=worker.validate(p,task(p));assert row==p['rows'][0] and cap==p['body_cap']


@pytest.mark.parametrize('field,value',[('host','other.invalid'),('socket_timeout_seconds',11),('parent_deadline_seconds',0),
    ('interval_seconds',4),('retry',1),('redirect',1),('parallel',1),('body_cap',2097153),('total_body_cap',6291457),('max_GET',4)])
def test_constraint_changes_rejected(tmp_path,field,value):
    p=approval(tmp_path);p[field]=value
    with pytest.raises(ValueError):worker.validate(p,task(p))


@pytest.mark.parametrize('url',['http://data.j-league.or.jp/SFMS02/?match_card_id=10000',
 'https://other.invalid/SFMS02/?match_card_id=10000','https://data.j-league.or.jp/SFMS02/?match_card_id=10001',
 'https://data.j-league.or.jp/robots.txt','https://data.j-league.or.jp/SFMS02/?match_card_id=10000&extra=1'])
def test_target_url_identity_must_be_exact(tmp_path,url):
    p=approval(tmp_path);p['rows'][0]['url']=url
    with pytest.raises(ValueError):worker.validate(p,task(p))


def test_no_duplicate_or_fourth_URL(tmp_path):
    p=approval(tmp_path);p['rows'][1]=deepcopy(p['rows'][0])
    with pytest.raises(ValueError):worker.validate(p,task(p))
    p=approval(tmp_path);t=task(p);t['ordinal']=4
    with pytest.raises(ValueError):worker.validate(p,t)


class Wire:
    def version(self):return 'TLSv1.3'
    def cipher(self):return ('SYNTHETIC', 'TLSv1.3',256)
    def getpeercert(self,binary_form):return b'synthetic-certificate'
    def settimeout(self,n):assert 0<n<=10


class FakeConnection:
    calls=[];body=b'synthetic';status=200;headers=[('Content-Type','text/html;charset=UTF-8')];error=None
    def __init__(self,*a,**kw):self.sock=Wire();self.pos=0;self.closed=False;self.__class__.calls.append(self)
    def request(self,*a,**kw):
        self.request_args=(a,kw)
        if self.error:raise self.error
    def getresponse(self):return self
    def getheaders(self):return self.headers
    def read(self,n):v=self.body[self.pos:self.pos+n];self.pos+=len(v);return v
    def close(self):self.closed=True


@pytest.mark.parametrize('status',[200,301,302,403,429])
def test_single_GET_no_retry_or_redirect_response_following(tmp_path,status):
    cls=type('Response',(FakeConnection,),{'calls':[],'status':status})
    raw,s,headers,tls=worker.fetch_once(approval(tmp_path)['rows'][0],2097152,ssl.create_default_context(),connection_factory=cls)
    assert s==status and raw==b'synthetic' and len(cls.calls)==1 and cls.calls[0].closed
    assert cls.calls[0].request_args[0][0]=='GET' and tls['check_hostname'] and tls['verify_mode']==ssl.CERT_REQUIRED


@pytest.mark.parametrize('error',[TimeoutError('synthetic'),ssl.SSLError('synthetic'),ConnectionError('synthetic')])
def test_network_failure_never_retries(tmp_path,error):
    cls=type('Failure',(FakeConnection,),{'calls':[],'error':error})
    with pytest.raises(type(error)):worker.fetch_once(approval(tmp_path)['rows'][0],2097152,ssl.create_default_context(),connection_factory=cls)
    assert len(cls.calls)==1 and cls.calls[0].closed


@pytest.mark.parametrize('headers,body',[([('Content-Length','2097153')],b''),([],b'x'*2097153),
 ([('Content-Length','20')],b'short'),([('Content-Encoding','gzip')],b'gzip')],ids=['declared-cap','stream-cap','truncated','compression'])
def test_body_length_and_encoding_fail_closed(tmp_path,headers,body):
    cls=type('Body',(FakeConnection,),{'calls':[],'headers':headers,'body':body})
    with pytest.raises(ValueError):worker.fetch_once(approval(tmp_path)['rows'][0],2097152,ssl.create_default_context(),connection_factory=cls)


def test_unverified_TLS_context_is_rejected_before_request(tmp_path):
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);ctx.check_hostname=False;ctx.verify_mode=ssl.CERT_NONE
    with pytest.raises(ValueError,match='TLS_VERIFY'):worker.fetch_once(approval(tmp_path)['rows'][0],2097152,ctx,connection_factory=FakeConnection)


def saved(i,kind='KNOWN'):
    p,e=example(i,kind);return replace(p,source_mode='SAVED_OFFICIAL_WITNESS',synthetic_observation=None),e


def replay(tmp_path,items,reviewer=review,store_type=None):
    manager=layer.LocalManager(tmp_path/'workers',allowed_base=tmp_path,worker_path=OLD/'local_worker.py',
        worker_sha=worker.sha((OLD/'local_worker.py').read_bytes()),windows_sha=worker.sha((OLD/'windows_local.py').read_bytes()))
    cls=store_type or layer.leased_store_class(m);store=cls(tmp_path/'stage',allowed_base=tmp_path)
    try:return layer.run_stage(m,manager,store,items,strict,reviewer),manager,store
    finally:store.close();manager.close()


@pytest.mark.parametrize('kind',['UNKNOWN','TIMING'])
def test_quarantine_commit_gates_next_native_owned_worker(tmp_path,kind):
    (result,runner),manager,store=replay(tmp_path,[saved(0,kind),saved(1),saved(2)])
    r=result['sealed_byte_engine'];assert r['detail_PASS']==2 and r['detail_HOLD']==r['quarantined']==1 and r['history_admitted']==0
    receipt=store.path(runner.records[0]['receipt']);assert receipt.stat().st_mtime_ns<=manager.receipts[1]['launched_epoch_ns']
    assert all(x['final_owned_active_processes']==0 and x['identity']['job_membership_verified'] for x in manager.receipts)


def test_quarantine_storage_failure_global_STOP_prevents_next_worker(tmp_path):
    base=layer.leased_store_class(m)
    class Broken(base):
        def write(self,name,data):
            if name=='receipt-0001.json':raise OSError('synthetic receipt failure')
            return super().write(name,data)
    (result,_),manager,_=replay(tmp_path,[saved(0,'UNKNOWN'),saved(1)],store_type=Broken)
    assert result['sealed_byte_engine']['status']=='OFFLINE_REPLAY_STOPPED' and manager.sequence==1


def test_stage_B_drift_is_global_STOP(tmp_path):
    def drift(*args):r=review(*args);r['strict_analysis']['parsed']['home_score_90']=99;return r
    (result,_),manager,_=replay(tmp_path,[saved(0),saved(1)],reviewer=drift)
    assert result['sealed_byte_engine']['status']=='OFFLINE_REPLAY_STOPPED' and manager.sequence==1


def test_actual_HTTP_worker_rejects_before_DNS_and_owned_cleanup_is_finite(tmp_path):
    p=approval(tmp_path);p['code_files'][str(CODE/'http_worker.py')]='0'*64
    permit_path=tmp_path/'permit.json';permit_path.write_bytes(worker.encoded(p))
    folder=tmp_path/'native';win.secure_mkdir(folder);win.secure_mkdir(folder/'worker-output')
    t={**task(p),'permit_path':str(permit_path),'permit_SHA256':worker.sha(permit_path.read_bytes())}
    task_path=folder/'task.json';task_path.write_bytes(worker.encoded(t))
    with win.OwnedJob() as job:
        identity=job.start(['-B',CODE/'http_worker.py','--task',task_path,worker.sha(task_path.read_bytes())],folder)
        result=job.wait(5);assert not result['timed_out'] and result['exit_code']!=0 and identity['job_membership_verified']
        assert job.cleanup(2)['cleanup_complete'] and job.active()==0
    assert not (folder/'worker-output/connection-started.json').exists()


def test_permit_double_execution_and_previously_acquired_rejected(tmp_path):
    p=approval(tmp_path);path=tmp_path/'permit.json';path.write_bytes(worker.encoded(p));h=worker.sha(path.read_bytes())
    with pytest.raises(ValueError,match='PREVIOUSLY'):layer.HttpManager(tmp_path/'transport',allowed_base=tmp_path,permit_path=path,permit_sha=h,
        worker_path=CODE/'http_worker.py',blocked_urls=[p['rows'][0]['url']])
    # Separate exclusive roots still share the durable permit claim.
    p['output_root']=str(tmp_path/'second');path2=tmp_path/'second-permit.json';path2.write_bytes(worker.encoded(p));h2=worker.sha(path2.read_bytes())
    t=layer.HttpManager(tmp_path/'second',allowed_base=tmp_path,permit_path=path2,permit_sha=h2,worker_path=CODE/'http_worker.py');t.close()
    with pytest.raises((FileExistsError,OSError)):layer.HttpManager(tmp_path/'second',allowed_base=tmp_path,permit_path=path2,permit_sha=h2,worker_path=CODE/'http_worker.py')
    assert path2.with_suffix('.consumed.json').exists()


def test_explicit_admission_rejected():
    with pytest.raises(m.Stop,match='NOT_AUTHORIZED'):m.require_history_admission({})


@pytest.mark.parametrize('body,status,ok',[(b'User-agent: *\nDisallow: /',200,False),
 (b'User-agent: *\nDisallow:\n',200,True),(b'User-agent: *\nCrawl-delay: 10',200,False),
 (b'User-agent: *\nRequest-rate: 1/10',200,False),(b'<html>challenge</html>',200,False),
 (b'unknown',403,False),(b'unknown',429,False),(b'known404',404,True),(b'other404',404,False)])
def test_access_conditions_and_limited_404_meaning(body,status,ok):
    meta={'requested_url':'https://data.j-league.or.jp/robots.txt','final_url':'https://data.j-league.or.jp/robots.txt',
        'status':status,'sha256':worker.sha(body),'bytes':len(body),'response_completed_at_utc':'2026-10-21T00:00:00+00:00','content_type':'text/plain'}
    fn=lambda:layer.access_policy(body,meta,['https://data.j-league.or.jp/SFMS02/?match_card_id=10000'],'2026-10-21T00:00:01+00:00',known_404_sha=worker.sha(b'known404'))
    if ok:assert fn()['site_wide_permission_proven'] is False
    else:
        with pytest.raises(ValueError):fn()


def synthetic_http_job(monkeypatch,stage_root,*,status=200,tamper=None,timeout=False):
    """Parent HTTP branch, with no socket and no real HTTP child process."""
    class Job:
        starts=[]
        process=True
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def start(self,args,cwd):
            task_path=Path(args[-2]);t=json.loads(task_path.read_bytes());ordinal=t['ordinal'];self.starts.append(t)
            if ordinal>1:
                assert (stage_root/('receipt-%04d.json'%(ordinal-1))).is_file(),'next worker before receipt'
            p,e=saved(ordinal-1,'UNKNOWN' if ordinal==1 else 'KNOWN')
            out=Path(cwd)/'worker-output';req=json.loads(p.request);req.update(PID=123,task_SHA256=args[-1],permit_SHA256=t['permit_SHA256'])
            request=worker.encoded(req);meta=json.loads(p.metadata);meta.update(request_sha256=worker.sha(request),status=status,
                TLS={'verified':True,'hostname_verified':True,'server_hostname':worker.HOST})
            metadata=worker.encoded(meta)
            receipt={'PID':123,'task_SHA256':args[-1],'permit_SHA256':t['permit_SHA256'],'raw_SHA256':worker.sha(p.raw),
                'metadata_SHA256':worker.sha(metadata),'request_SHA256':worker.sha(request),'GET_attempts':1}
            if tamper:receipt[tamper]='changed'
            for name,data in [('raw.html',p.raw),('metadata.json',metadata),('request.json',request),('worker-receipt.json',worker.encoded(receipt))]:
                (out/name).write_bytes(data)
            return {'PID':123,'kernel_PID':123,'parent_PID':os.getpid(),'kernel_parent_PID':os.getpid(),'job_membership_verified':True}
        def wait(self,seconds):return {'timed_out':timeout,'exit_code':0,'active_job_processes':0}
        def active(self):return 0
        def cleanup(self,seconds):return {'cleanup_complete':True,'active':0}
    monkeypatch.setattr(layer,'OwnedJob',Job)
    elapsed=[0.]
    monkeypatch.setattr(layer.time,'monotonic',lambda:elapsed[0])
    monkeypatch.setattr(layer.time,'sleep',lambda duration:elapsed.__setitem__(0,elapsed[0]+duration))
    return Job,elapsed


@pytest.mark.parametrize('status,tamper,timeout,success',[(200,None,False,True),(403,None,False,False),
 (429,None,False,False),(302,None,False,False),(200,'raw_SHA256',False,False),
 (200,'metadata_SHA256',False,False),(200,'request_SHA256',False,False),(200,None,True,False)])
def test_live_parent_branch_with_synthetic_worker_bindings_rate_and_STOP(tmp_path,monkeypatch,status,tamper,timeout,success):
    stage=tmp_path/'stage';Job,elapsed=synthetic_http_job(monkeypatch,stage,status=status,tamper=tamper,timeout=timeout)
    p=approval(tmp_path);path=tmp_path/'permit.json';path.write_bytes(worker.encoded(p));h=worker.sha(path.read_bytes())
    manager=layer.HttpManager(tmp_path/'transport',allowed_base=tmp_path,permit_path=path,permit_sha=h,worker_path=CODE/'http_worker.py')
    store=layer.leased_store_class(m)(stage,allowed_base=tmp_path)
    try:
        result,run=layer.run_stage(m,manager,store,[saved(i) for i in range(3)],strict,review,live=True)
        if success:
            r=result['sealed_byte_engine'];assert r['detail_PASS']==2 and r['detail_HOLD']==r['quarantined']==1
            assert len(Job.starts)==3 and elapsed[0]>=10 and manager.total>0
            assert all(run.verify_receipt(r['receipt'],r['SHA256'])['history_admission_status'] is False for r in run.records)
        else:
            assert result['sealed_byte_engine']['status']=='GLOBAL_STOP' and len(Job.starts)==1
            assert manager.sequence==1 and not (manager.root/'worker-0002').exists()
        with pytest.raises(ValueError,match='TERMINAL'):manager.one(p['rows'][0])
    finally:store.close();manager.close()


def test_prior_robots_completion_gates_first_detail_and_finite_global_deadline(tmp_path,monkeypatch):
    _,elapsed=synthetic_http_job(monkeypatch,tmp_path/'unused')
    p=approval(tmp_path);p['global_deadline_seconds']=1;path=tmp_path/'permit.json';path.write_bytes(worker.encoded(p))
    manager=layer.HttpManager(tmp_path/'transport',allowed_base=tmp_path,permit_path=path,
        permit_sha=worker.sha(path.read_bytes()),worker_path=CODE/'http_worker.py',previous_completion=0)
    try:
        with pytest.raises(ValueError,match='GLOBAL_DEADLINE'):manager.one(p['rows'][0])
        assert elapsed[0]==5 and manager.sequence==0
    finally:manager.close()
