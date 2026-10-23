"""No live connection: fake responses, sealed bytes and exclusive temp files."""
import ast
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import ssl

import pytest

BASE=Path(__file__).parents[1]/'research/nn_v2/phase2_5G'
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
w=load('access_fetch_worker_test',BASE/'access_worker.py')
c=load('access_fetch_contract_test',BASE/'access_contract.py')
NOW='2026-01-02T00:00:00+00:00'


def permit():
    return dict(kind='NNV2_G_A_ONLY_SINGLE_RUN_V1',scope='ACCESS_CONDITIONS_ONLY',max_GET=4,B_GET=0,
        URLs=list(w.URLS),body_caps=list(w.CAPS),total_body_cap=sum(w.CAPS),header_cap=32768,
        retry=0,redirect=0,parallel=0,socket_deadline=10,parent_deadline=12,global_deadline=120,
        interval=5,cleanup_deadline=2,issued_UTC=NOW,expires_UTC='2026-01-02T00:01:00+00:00')


def task():return dict(kind='G_APPROVED_ONE_GET',ordinal=1,URL=w.URLS[0],id='A1')


class FakeSock:
    def version(self):return 'SYNTHETIC_TLS'
    def cipher(self):return ('SYNTHETIC',None,0)
    def getpeercert(self,**kw):return b'synthetic certificate'
    def settimeout(self,v):assert 0<v<=10


class FakeResponse:
    def __init__(self,body=b'User-agent: *\nDisallow:\n',headers=None,status=200):
        self.body=body;self.offset=0;self.headers=headers if headers is not None else [('Content-Length',str(len(body)))];self.status=status
    def getheaders(self):return self.headers
    def isclosed(self):return self.offset==len(self.body)
    def read1(self,size):
        v=self.body[self.offset:self.offset+size];self.offset+=len(v);return v


class Factory:
    def __init__(self,response):self.response=response;self.requests=[];self.connects=0;self.closed=False
    def __call__(self,*a,**kw):self.sock=FakeSock();return self
    def connect(self):self.connects+=1
    def request(self,*args,**kw):self.requests.append((args,kw))
    def getresponse(self):return self.response
    def close(self):self.closed=True


@pytest.mark.parametrize('i',range(4))
def test_exact_one_synthetic_request_no_redirect_retry_or_proxy(i):
    factory=Factory(FakeResponse());e={}
    w.fetch_once(i,ssl.create_default_context(),e,factory=factory,clock=lambda:0)
    assert factory.connects==len(factory.requests)==1 and factory.closed and e['complete_body']
    assert factory.requests[0][0]==('GET',w.PATHS[i])
    assert factory.requests[0][1]['headers']['Host']==w.HOSTS[i]


@pytest.mark.parametrize('key,value',[
    ('kind','OLD_COLLECTION_PERMIT'),('scope','B_DISCOVERY'),('max_GET',5),('B_GET',1),
    ('retry',1),('redirect',1),('parallel',1),('header_cap',32769),('total_body_cap',2228225),
    ('socket_deadline',11),('parent_deadline',13),('global_deadline',121),('interval',4),('cleanup_deadline',3)])
def test_permit_cannot_widen_authority(key,value):
    p=permit();p[key]=value
    with pytest.raises(ValueError):w.validate(p,task(),NOW)


@pytest.mark.parametrize('value',[
    'https://www.jleague.jp/j1/news/','https://aboutj.jleague.jp/corporate/pressrelease/',
    'https://www.jleague.jp:443/robots.txt','http://www.jleague.jp/robots.txt',
    'https://www.jleague.jp/robots.txt?q=1','https://data.j-league.or.jp/robots.txt'])
def test_exact_URL_no_B_old_permit_alias_or_query(value):
    t=task();t['URL']=value
    with pytest.raises(ValueError):w.validate(permit(),t,NOW)


def test_reorder_or_duplicate_or_expired_task_rejected():
    for changes in [dict(ordinal=2),dict(id='A2'),dict(kind='RESUME'),dict(ordinal=0),dict(ordinal=True)]:
        t=task();t.update(changes)
        with pytest.raises(ValueError):w.validate(permit(),t,NOW)
    p=permit();p['URLs'][1]=p['URLs'][0]
    with pytest.raises(ValueError):w.validate(p,task(),NOW)
    with pytest.raises(ValueError):w.validate(permit(),task(),'2026-01-02T00:01:00+00:00')


@pytest.mark.parametrize('status',[301,302,307,308,403,404,429,500])
def test_error_or_redirect_response_is_returned_once_never_followed(status):
    factory=Factory(FakeResponse(status=status,headers=[('Location','https://unapproved.invalid/')]))
    evidence={};w.fetch_once(0,ssl.create_default_context(),evidence,factory=factory,clock=lambda:0)
    assert len(factory.requests)==factory.connects==1 and evidence['HTTP_status']==status


@pytest.mark.parametrize('headers',[
    [('Content-Length','65537')],[('Content-Encoding','gzip')],[('Content-Length','1'),('Content-Length','1')],
    [('Content-Length','bad')],[('Content-Length','-1')],[('X-Synthetic','x'*32769)]])
def test_bad_encoding_length_headers_stop_without_retry(headers):
    f=Factory(FakeResponse(headers=headers))
    with pytest.raises(ValueError):w.fetch_once(0,ssl.create_default_context(),{},factory=f,clock=lambda:0)
    assert f.connects==len(f.requests)==1 and f.closed


def test_streaming_never_reads_body_past_cap_and_incomplete_is_not_success():
    r=FakeResponse(body=b'x'*65537,headers=[]);f=Factory(r);e={}
    with pytest.raises(ValueError,match='BODY_CAP_COMPLETION_UNKNOWN'):w.fetch_once(0,ssl.create_default_context(),e,factory=f,clock=lambda:0)
    assert len(e['body'])==r.offset==65536 and not e['complete_body']
    r=FakeResponse(body=b'x',headers=[('Content-Length','2')]);f=Factory(r);e={}
    with pytest.raises(ValueError,match='INCOMPLETE_BODY'):w.fetch_once(0,ssl.create_default_context(),e,factory=f,clock=lambda:0)
    assert not e['complete_body']


def test_header_reader_budget_before_parse():
    reader=w.HeaderReader(io.BytesIO(b'HTTP/1.1 200 OK\r\nX: '+b'a'*32768+b'\r\n\r\n'))
    assert reader.readline().startswith(b'HTTP/')
    with pytest.raises(ValueError):reader.readline()
    assert reader.count<=32768


def test_no_TLS_weakening_and_deadline_no_second_attempt():
    context=ssl._create_unverified_context()
    with pytest.raises(ValueError,match='TLS_REQUIRED'):w.fetch_once(0,context,{},factory=Factory(FakeResponse()))
    values=iter([0,11]);f=Factory(FakeResponse())
    with pytest.raises(ValueError,match='DEADLINE'):w.fetch_once(0,ssl.create_default_context(),{},factory=f,clock=lambda:next(values))
    assert f.connects==len(f.requests)==1


def sealed(**changes):
    raw=b'User-agent: *\nDisallow:\n'
    req=dict(url=w.URLS[0],request_id='synthetic',PID=1,method='GET',request_started_UTC=NOW)
    reqb=w.encoded(req)
    md=dict(requested_url=w.URLS[0],actual_response_url=w.URLS[0],request_id='synthetic',PID=1,
        raw_SHA256=w.sha(raw),bytes=len(raw),request_SHA256=w.sha(reqb),redirect_follow=0,retry=0,redirect_history=[],proxy_used=False,
        response_completed_UTC='2026-01-02T00:00:01+00:00',snapshot_saved_UTC='2026-01-02T00:00:02+00:00',
        HTTP_status=200,complete_body=True,error=None,TLS=dict(verified=True,hostname_verified=True,server_hostname='www.jleague.jp'))
    md.update(changes);mdb=w.encoded(md)
    receipt=dict(raw_SHA256=w.sha(raw),metadata_SHA256=w.sha(mdb),request_SHA256=w.sha(reqb),
        request_id='synthetic',PID=1,receipt_completed_UTC='2026-01-02T00:00:03+00:00')
    return raw,mdb,reqb,receipt


@pytest.mark.parametrize('status',[301,302,403,404,429,500])
def test_all_non200_including_robots404_stop_G(status):
    assert c.verify_response(0,*sealed(HTTP_status=status))['status']=='STOP'


@pytest.mark.parametrize('key,value',[
    ('raw_SHA256','0'*64),('request_SHA256','0'*64),('requested_url',w.URLS[1]),('PID',2),
    ('bytes',-1),('retry',1),('redirect_follow',1),('proxy_used',True),
    ('TLS',dict(verified=False,hostname_verified=True,server_hostname='www.jleague.jp')),
    ('response_completed_UTC','2026-01-02T00:00:11+00:00')])
def test_independent_evidence_tamper_rejected(key,value):
    with pytest.raises(ValueError):c.verify_response(0,*sealed(**{key:value}))


@pytest.mark.parametrize('raw',[
    b'User-agent: *\nDisallow: /\n',b'User-agent: *\nDisallow: /j1/news/\n',
    b'User-agent: *\nDisallow: /*.json$\n',b'User-agent: *\nCrawl-delay: 10\n',
    b'User-agent: *\nX-Unknown: yes\n',b'<html>challenge</html>',b'\xff',
    b'User-agent: *\nCrawl-delay: unknown\n'])
def test_robot_denial_unknown_pattern_encoding_or_rate_HOLD(raw):
    assert c.review_robots(raw,host='www.jleague.jp')['status']=='HOLD'


def test_robots_path_review_does_not_grant_terms_B_or_history():
    r=c.review_robots(b'User-agent: *\nDisallow:\n',host='www.jleague.jp')
    assert r['status']=='ROBOTS_PATH_REVIEW_ONLY' and r['content_permission']==r['terms_permission']=='UNKNOWN' and not r['B_authorized']


def test_exclusive_flush_readback_and_double_claim_rejection(tmp_path):
    win=load('access_test_windows_primitives',BASE.parent/'phase2_5B_13/windows_local.py')
    root=tmp_path/'synthetic-access-store';audit=win.secure_mkdir(root)
    assert audit['scope_verified']
    with win.DirectoryLease(root):
        receipt=win.write_new_locked(root/'synthetic-consumed.json',b'synthetic-single-use')
        assert receipt['FlushFileBuffers'] and win.read_bytes_locked(root/'synthetic-consumed.json')==b'synthetic-single-use'
        with pytest.raises(OSError):win.write_new_locked(root/'synthetic-consumed.json',b'duplicate')


def test_worker_no_urllib_requests_proxy_collector_model_task_or_B_import():
    tree=ast.parse((BASE/'access_worker.py').read_text('utf8'))
    imports=[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert set(imports)=={'hashlib','http.client','json','os','socket','ssl','sys','time'}
    text=(BASE/'access_parent.py').read_text('utf8')
    assert "consumed.exists()" in text and "RUN_ALREADY_CONSUMED_NO_RESUME" in text
    assert "with OwnedJob() as job" in text and "'--task'" in text
    assert "review['B_authorized'] is False" in text and "'NEXT_A_CONDITIONS_ONLY'" in text
