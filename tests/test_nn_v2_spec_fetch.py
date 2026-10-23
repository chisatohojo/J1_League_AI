"""Mock response tests only; the approved two GETs are never invoked here."""
import importlib.util
from pathlib import Path
import ssl

import pytest
from test_nn_v2_access_fetch import Factory,FakeResponse

BASE=Path(__file__).parents[1]/'research/nn_v2/phase2_5I'
s=importlib.util.spec_from_file_location('spec_worker_test',BASE/'spec_worker.py')
w=importlib.util.module_from_spec(s);s.loader.exec_module(w)


def permit():
    return dict(kind='NNV2_I_SPEC_ONLY_SINGLE_RUN_V1',scope='OFFICIAL_SPECIFICATION_ONLY',max_GET=2,B_GET=0,
        URLs=list(w.URLS),body_caps=list(w.CAPS),total_body_cap=4194304,header_cap=32768,retry=0,redirect=0,parallel=0,
        socket_deadline=10,parent_deadline=12,global_deadline=90,interval=5,cleanup_deadline=2,
        issued_UTC='2026-01-01T00:00:00+00:00',expires_UTC='2026-01-02T00:00:00+00:00')


def task(i=0):return dict(kind='I_APPROVED_ONE_GET',ordinal=i+1,URL=w.URLS[i],id='S'+str(i+1))


@pytest.mark.parametrize('i',[0,1])
def test_two_exact_spec_scopes_and_one_GET_with_exact_query(i):
    assert w.validate(permit(),task(i),'2026-01-01T01:00:00+00:00')==i
    f=Factory(FakeResponse(body=b'<html>synthetic official specification</html>'));e={}
    w.fetch_once(i,ssl.create_default_context(),e,factory=f,clock=lambda:0)
    assert f.requests[0][0]==('GET',w.PATHS[i]) and len(f.requests)==1 and f.connects==1 and e['complete_body']
    if i==1:assert w.PATHS[i].endswith('?hl=ja')


@pytest.mark.parametrize('key,value',[
    ('kind','NNV2_G_A_ONLY_SINGLE_RUN_V1'),('scope','ACCESS_CONDITIONS_ONLY'),('max_GET',3),('B_GET',1),
    ('retry',1),('redirect',1),('parallel',1),('total_body_cap',4194305),('global_deadline',91)])
def test_old_permit_or_broader_authority_rejected(key,value):
    p=permit();p[key]=value
    with pytest.raises(ValueError):w.validate(p,task(),'2026-01-01T01:00:00+00:00')


@pytest.mark.parametrize('url',[
    'https://www.jleague.jp/robots.txt','https://www.jleague.jp/j1/news/',
    'https://aboutj.jleague.jp/corporate/pressrelease/',
    'https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec',
    'https://www.rfc-editor.org/rfc/rfc9309.txt'])
def test_no_Jleague_or_query_change_or_text_fallback(url):
    t=task();t['URL']=url
    with pytest.raises(ValueError):w.validate(permit(),t,'2026-01-01T01:00:00+00:00')


@pytest.mark.parametrize('status',[301,302,307,308,403,429,404])
def test_response_error_never_follows_or_retries(status):
    f=Factory(FakeResponse(status=status,headers=[('Location','https://unapproved.invalid/')]))
    e={};w.fetch_once(0,ssl.create_default_context(),e,factory=f,clock=lambda:0)
    assert f.connects==len(f.requests)==1 and e['HTTP_status']==status


def test_scope_ordinal_duplicate_expired_and_oversize_fail_closed():
    t=task();t['ordinal']=3
    with pytest.raises(ValueError):w.validate(permit(),t,'2026-01-01T01:00:00+00:00')
    p=permit();p['URLs'][1]=p['URLs'][0]
    with pytest.raises(ValueError):w.validate(p,task(),'2026-01-01T01:00:00+00:00')
    with pytest.raises(ValueError):w.validate(permit(),task(),'2026-01-02T00:00:00+00:00')
    f=Factory(FakeResponse(headers=[('Content-Length','2097153')]))
    with pytest.raises(ValueError,match='CAP'):w.fetch_once(0,ssl.create_default_context(),{},factory=f,clock=lambda:0)
    assert f.connects==len(f.requests)==1


def test_new_parent_single_use_scope_and_finite_deadlines():
    text=(BASE/'spec_parent.py').read_text('utf8')
    assert "'RUN_ALREADY_CONSUMED_NO_RESUME'" in text and 'return 90-' in text
    assert "root/'SPEC'" in text and 'unused_budget_expired=2-len(ledger)' in text
    assert "with OwnedJob() as job" in text and "'NEXT_SPEC_CONDITIONS_ONLY'" in text
