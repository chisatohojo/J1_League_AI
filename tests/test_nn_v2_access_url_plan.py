"""Static descriptors and synthetic receipts; never perform HTTP or issue permits."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

ROOT=Path(__file__).parents[1]
FILE=ROOT/'research/nn_v2/phase2_5F/access_plan_contract.py'
spec=importlib.util.spec_from_file_location('access_plan',FILE)
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def plan():
    return json.loads((FILE.parent/'A_ACCESS_PLAN.json').read_bytes())


def trace():
    return [dict(scope='SYNTHETIC_ONLY', id=f'A{i+1}', url=url,
        request_started_UTC=f'2026-01-02T00:00:{i*6:02d}+00:00',
        response_completed_UTC=f'2026-01-02T00:00:{i*6+1:02d}+00:00',
        body_bytes=1,header_bytes=1,redirect_follow=0,retry=0,HTTP_status=200,
        TLS_verified=True,access_restriction=False,complete_and_sealed=True,
        reviewed_for_next_conditions_check=True) for i,url in enumerate(p.URLS)]


def test_static_candidate_plan_never_authorizes_acquisition_or_admission():
    result=p.inspect_plan(plan())
    assert result['static_validation']=='PASS' and not result['execution_authorized']
    assert not result['B_authorized'] and not result['history_admission']


@pytest.mark.parametrize('field,value',[
    ('kind','EXECUTABLE_PERMIT'),('permit_id','issued'),('approval_UTC','2026-01-02T00:00:00+00:00'),
    ('issued',True),('activated',True),('currently_authorized_requests',4),('gate','READY'),
    ('B_authorized',True),('B_requests_in_A',1)])
def test_no_real_grant_or_ready_claim(field,value):
    v=plan();v[field]=value
    with pytest.raises(p.PlanStop):p.inspect_plan(v)


@pytest.mark.parametrize('url',[
    'http://www.jleague.jp/robots.txt','https://www.jleague.jp:443/robots.txt',
    'https://WWW.jleague.jp/robots.txt','https://www.jleague.jp/robots.txt?x=1',
    'https://www.jleague.jp/robots.txt#x','https://www.jleague.jp/ROBOTS.txt',
    'https://www.jleague.jp/%72obots.txt','https://www.jleague.jp/robots.txt/',
    'https://www.jleague.jp/j1/news/','https://aboutj.jleague.jp/corporate/pressrelease/',
    'https://auth.jleague.jp/contents/privacypolicy.html','https://data.j-league.or.jp/robots.txt',
    'https://user@www.jleague.jp/robots.txt','https://www.jleague.jp:444/robots.txt'])
def test_exact_urls_no_aliases_redirect_targets_or_B_entrances(url):
    v=plan();v['candidates'][0]['url']=url
    with pytest.raises(p.PlanStop):p.inspect_plan(v)


@pytest.mark.parametrize('field,value',[
    ('scheme','http'),('host','aboutj.jleague.jp'),('port',80),('explicit_port',443),('path','/'),
    ('query','x=1'),('fragment','x'),('bucket','B'),('role','INDEX'),('method','HEAD'),
    ('max_requests',2),('body_cap_bytes',65537),('redirect_follow',1),('HTTP_status',200),
    ('response_verified',True),('content_permission','ALLOWED'),('execution_authorized',True)])
def test_candidate_component_budget_and_evidence_claim_mutations(field,value):
    v=plan();v['candidates'][0][field]=value
    with pytest.raises(p.PlanStop):p.inspect_plan(v)


@pytest.mark.parametrize('key',list(plan()['limits']))
def test_limits_cannot_be_widened_or_silently_changed(key):
    v=plan();v['limits'][key]+=1
    with pytest.raises(p.PlanStop):p.inspect_plan(v)


def test_fixed_order_and_no_spare_or_substituted_slots():
    for change in ['swap','remove','append']:
        v=plan()
        if change=='swap':v['candidates'][0],v['candidates'][1]=v['candidates'][1],v['candidates'][0]
        elif change=='remove':v['candidates'].pop()
        else:v['candidates'].append(deepcopy(v['candidates'][0]))
        with pytest.raises(p.PlanStop):p.inspect_plan(v)


@pytest.mark.parametrize('key,value',[('operator','JLEAGUE_ASSUMED'),('terms_applicability','WWW_ASSUMED')])
def test_aboutj_brand_or_domain_is_not_operator_or_applicability_proof(key,value):
    v=plan();v['host_findings']['aboutj.jleague.jp'][key]=value
    with pytest.raises(p.PlanStop):p.inspect_plan(v)


@pytest.mark.parametrize('key,value',[('created',True),('exclusive_create_required',False),('permit_or_worker_created',True)])
def test_no_destination_activation_or_real_worker(key,value):
    v=plan();v['storage'][key]=value
    with pytest.raises(p.PlanStop):p.inspect_plan(v)


def test_four_synthetic_receipts_preserve_unknown_permission_and_HOLD():
    v=p.inspect_synthetic_prefix(plan(),trace())
    assert v['attempts_consumed']==4 and not v['stopped'] and not v['execution_authorized']
    assert v['B']==v['C']==v['D']=='HOLD' and v['content_permission']=='UNKNOWN'


@pytest.mark.parametrize('status',[301,302,307,308,401,403,429,500])
def test_adverse_HTTP_records_consume_attempt_and_stop(status):
    t=trace();t[0]['HTTP_status']=status
    v=p.inspect_synthetic_prefix(plan(),t[:1]);assert v['stopped'] and v['attempts_consumed']==1
    with pytest.raises(p.PlanStop,match='CONTINUED_AFTER_STOP'):p.inspect_synthetic_prefix(plan(),t[:2])


@pytest.mark.parametrize('field,value',[
    ('TLS_verified',False),('access_restriction',True),('complete_and_sealed',False),
    ('reviewed_for_next_conditions_check',False),('response_completed_UTC',None)])
def test_unknown_conditions_seal_failure_or_unknown_end_prevents_continuation(field,value):
    t=trace();t[0][field]=value
    assert p.inspect_synthetic_prefix(plan(),t[:1])['stopped']
    with pytest.raises(p.PlanStop):p.inspect_synthetic_prefix(plan(),t[:2])


def test_robots_404_is_not_permission_and_requires_review_for_next_conditions_check():
    t=trace();t[0]['HTTP_status']=404
    assert p.inspect_synthetic_prefix(plan(),t)['content_permission']=='UNKNOWN'
    t[0]['reviewed_for_next_conditions_check']=False
    assert p.inspect_synthetic_prefix(plan(),t[:1])['stopped']
    with pytest.raises(p.PlanStop):p.inspect_synthetic_prefix(plan(),t)


@pytest.mark.parametrize('field,value',[
    ('scope','REAL_HTTP'),('id','B1'),('url',p.URLS[1]),('retry',1),('redirect_follow',1),
    ('body_bytes',65537),('header_bytes',32769),('body_bytes',-1),
    ('request_started_UTC','2026-01-02T00:00:00+09:00'),
    ('response_completed_UTC','2026-01-02T00:00:11+00:00')])
def test_receipt_negative_controls(field,value):
    t=trace();t[0][field]=value
    with pytest.raises(p.PlanStop):p.inspect_synthetic_prefix(plan(),t)


def test_rate_limit_cross_host_and_unknown_completion_no_budget_refund():
    t=trace();t[1]['request_started_UTC']='2026-01-02T00:00:05+00:00'
    with pytest.raises(p.PlanStop,match='RATE'):p.inspect_synthetic_prefix(plan(),t)
    t=trace();t[0]['response_completed_UTC']=None
    v=p.inspect_synthetic_prefix(plan(),t[:1]);assert v['attempts_consumed']==1 and v['stopped']
    with pytest.raises(p.PlanStop):p.inspect_synthetic_prefix(plan(),t+[t[0]])


def test_pure_code_has_no_network_storage_model_process_or_permit_entrypoint():
    tree=ast.parse(FILE.read_text(encoding='utf8'))
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert imports==['datetime','urllib.parse']
    assert not any(isinstance(n,ast.Import) for n in ast.walk(tree))
    forbidden={'open','exec','eval','compile','__import__','getattr','setattr','globals','locals'}
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in forbidden for n in ast.walk(tree))
