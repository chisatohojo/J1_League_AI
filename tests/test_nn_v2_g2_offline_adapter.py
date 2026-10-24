"""Memory-only integration; fixed research URLs are identity strings, not destinations."""
from dataclasses import replace
from copy import deepcopy
import ast
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from research.nn_v2.phase2_5O import offline_adapter as a

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-10-24T10:10:00+00:00'
CREATED = '2026-10-24T10:09:59+00:00'


def provider():
    return a.IdentityProvider(
        (ROOT/'research/nn_v2/phase2_5N/UA_ADOPTION_MANIFEST.json').read_bytes(),
        (ROOT/'research/nn_v2/phase2_5L/USER_AGENT_CANDIDATE.json').read_bytes(),
        (ROOT/'research/nn_v2/phase2_5N/ADOPTION_SCHEMAS.json').read_bytes(),
        (ROOT/'research/nn_v2/phase2_5M/URL_STOP_MATRIX.json').read_bytes())


def inputs(target='B1', request_id='syn-g2-01'):
    return dict(request_id=request_id, target_id=target, exact_url=a.m.TARGETS[target],
        method='GET', source_revision=a.g1.BASE_COMMIT, created_utc=CREATED, now_utc=NOW)


def request(target='B1'):
    return a.build_request(provider(), run_id='syn-g2-run', **inputs(target))


def fixture(p, *, robot='PASS', terms='PASS', with_plan=True):
    raw = {'PASS': b'User-agent: *\nDisallow: /closed\n',
           'DENY': b'User-agent: *\nDisallow: /\n',
           'UNKNOWN': b'User-agent: *\nDisallow: no-slash\n'}[robot]
    prepared = a.simulation_input(p, provider(), NOW)
    c = prepared['canonical']
    plan = dict(kind='SYNTHETIC_UA_PLAN_V1', scope='SYNTHETIC_ONLY', approved_for_simulation=True,
        **{k:c[k] for k in a.legacy.IDENTITY_FIELDS}, target_url=c['target_url'], method='GET',
        user_agent=c['intended_user_agent'], product_token=c['product_token'],
        header_configuration_hash=c['header_configuration_hash'], max_requests=1, attempts_used=0,
        issued_utc='2026-10-24T10:00:00+00:00', expires_utc='2026-10-24T10:20:00+00:00',
        redirect=0, retry=0, parallel=0, body_cap=65536, destination='sandbox/g2')
    return dict(kind='G2_SYNTHETIC_GATE_FIXTURE_V1', scope='SYNTHETIC_ONLY',
        prepared_SHA256=p['SHA256'], request_id=p['request']['request_id'],
        robots_raw=raw, robots_SHA256=a.g1.sha(raw), terms=terms, plan=plan if with_plan else None)


def record(p=None):
    p = request() if p is None else p
    return a.e1_record(p, provider(), final_client_input=a.client_input(p,provider(),NOW), now_utc=NOW)


def rehash(p):
    p['SHA256'] = a.g1.sha(a.g1.canonical(p['request']))


@pytest.mark.parametrize('target', list(a.m.TARGETS))
def test_provider_request_final_input_E1_sink_and_readback(target):
    source = provider(); config = source.config(NOW)
    assert config['HTTP_USER_AGENT'] == 'J1AI-Research-Timing-Pilot/1.0'
    assert config['ROBOTS_PRODUCT_TOKEN'] == 'Research-Timing-Pilot'
    session = a.OfflineSession(source,'syn-g2-run'); p = session.prepare(**inputs(target))
    sink = a.MemorySink()
    result = session.deliver(p,sink,fixture=fixture(p),final_client_input=a.client_input(p,source,NOW),now_utc=NOW)
    assert result['E1'] == record(p)
    assert not result['real_execution_authorized'] and not session.stopped
    assert list(a.g1.strict_json(sink.readback(p['request']['request_id']))['final_client_input']['headers'])
    assert session.attempts[-1]['status']=='COMPLETED_OFFLINE_ONLY'
    assert result['E1']['E2']==result['E1']['E3']=='UNKNOWN'
    assert not result['E1']['E4_new_acquisition'] and result['E1']['response_status'] is None


@pytest.mark.parametrize('field', ['manifest_bytes','candidate_bytes','schema_bytes','matrix_bytes'])
def test_negative_missing_or_changed_provider_source(field):
    p = provider()
    for value in [b'',getattr(p,field)+b' ']:
        with pytest.raises(ValueError): replace(p,**{field:value}).config(NOW)


@pytest.mark.parametrize('field,value', [('HTTP_USER_AGENT','Override/1.0'),
    ('ROBOTS_PRODUCT_TOKEN','Other'), ('adoption_state','CANDIDATE_FROZEN_NOT_ACTIVATED'),
    ('scope','Champion_A')])
def test_negative_manifest_semantic_change_before_hash_or_schema_cannot_load(field,value):
    p = provider(); m = a.g1.strict_json(p.manifest_bytes); m[field] = value
    with pytest.raises(ValueError): replace(p,manifest_bytes=a.g1.canonical(m)).config(NOW)


@pytest.mark.parametrize('key,value', [('method','HEAD'),('method','POST'),
    ('target_id','B3'),('exact_url','https://other.invalid/j1/news/'),
    ('exact_url','https://www.jleague.jp/other/'),('exact_url','https://www.jleague.jp/j1/news/?page=2'),
    ('exact_url','https://www.jleague.jp:443/j1/news/'),('exact_url','https://WWW.jleague.jp/j1/news/'),
    ('exact_url','https://www.jleague.jp/j1/../j1/news/'),('exact_url','https://www.jleague.jp/j1/%6eews/'),
    ('exact_url','https://www.jleague.jp/j1/news/?'),('exact_url','http://www.jleague.jp/j1/news/'),
    ('source_revision','latest'),('created_utc','2026-10-23T00:00:00+00:00'),
    ('created_utc','2026-10-24T10:10:00.000001+00:00'),('scope','Champion_A'),
    ('scope','scheduled_workers'),('request_id','real-request')])
def test_negative_candidate_method_URL_clock_source_and_scope(key,value):
    x = inputs(); x[key] = value
    with pytest.raises(ValueError): a.build_request(provider(),run_id='syn-g2-run',**x)


@pytest.mark.parametrize('key,value', [('user_agent','Override/1.0'),('product_token','Other'),
    ('host','aboutj.jleague.jp'),('path','/other'),('query','q=outside'),('port',80),
    ('origin','http://www.jleague.jp'),('G1_state','ACTIVATED'),('G1_manifest_SHA256','0'*64),
    ('source_evidence_revision','later'),('permit_state','PASS'),('permit_id','old-G'),
    ('terms_state','PASS'),('robots_state','DENY'),('redirect',1),('retry',1),('parallel',1),
    ('execution_authorized',True),('history_admission',True),('request_id','syn-other')])
def test_negative_request_tampering_recomputed_hash_still_rejected(key,value):
    p = request(); p['request'][key] = value; rehash(p)
    if key=='request_id':
        # A new ID is a valid different request in isolation, but not registered in the original session.
        s = a.OfflineSession(provider(),'syn-g2-run'); s.prepare(**inputs())
        with pytest.raises(ValueError): s.deliver(p,a.MemorySink(),fixture=fixture(p),final_client_input=a.client_input(p,provider(),NOW),now_utc=NOW)
    else:
        with pytest.raises(ValueError): a.verify_request(p,provider(),NOW)


@pytest.mark.parametrize('field,value', [('User-Agent','Other/1.0'),('Host','other.invalid'),
    ('Accept-Encoding','gzip'),('Connection','keep-alive'),('Authorization','secret')])
def test_negative_final_client_header_mutation(field,value):
    p = request(); final = a.client_input(p,provider(),NOW); final['headers'][field] = value
    with pytest.raises(ValueError): a.e1_record(p,provider(),final_client_input=final,now_utc=NOW)


@pytest.mark.parametrize('field,value', [('request_target','https://outside.invalid/'),('method','HEAD')])
def test_negative_final_client_redirect_or_method_mutation(field,value):
    p = request(); final = a.client_input(p,provider(),NOW); final[field] = value
    with pytest.raises(ValueError): a.e1_record(p,provider(),final_client_input=final,now_utc=NOW)


@pytest.mark.parametrize('target',list(a.m.TARGETS))
def test_actual_gates_keep_host_robots_terms_and_permit_separate(target):
    p = request(target); x = {r['gate']:r['status'] for r in a.actual_gates(p,provider(),NOW)}
    assert tuple(x)==a.GATE_ORDER
    assert x['robots']==('UNKNOWN' if target in {'A2','B2'} else 'PASS')
    assert x['terms']==x['permit']==x['final_pre_send']=='UNKNOWN'
    assert p['request']['permit_state']=='UNAPPROVED'


@pytest.mark.parametrize('robot,terms,plan', [('DENY','PASS',True),('UNKNOWN','PASS',True),
    ('PASS','DENY',True),('PASS','UNKNOWN',True),('PASS','PASS',False)])
def test_negative_simulation_DENY_UNKNOWN_or_no_plan_blocks_sink(robot,terms,plan):
    s = a.OfflineSession(provider(),'syn-g2-run'); p = s.prepare(**inputs()); sink = a.MemorySink()
    f = fixture(p,robot=robot,terms=terms,with_plan=plan)
    assert not a.simulation_gates(p,provider(),f,NOW)['offline_sink_allowed']
    with pytest.raises(ValueError): s.deliver(p,sink,fixture=f,final_client_input=a.client_input(p,provider(),NOW),now_utc=NOW)
    assert s.stopped and not sink.records and s.attempts[-1]['status']=='STOPPED_OFFLINE_ONLY'


@pytest.mark.parametrize('key,value', [('expires_utc',NOW),('scope','PRODUCTION'),
    ('target_url','https://www.jleague.jp/j1/news/'),('request_id','syn-other'),
    ('user_agent','Other'),('attempts_used',1),('retry',1),('redirect',1),('parallel',1)])
def test_negative_synthetic_plan_expired_mismatched_or_reused(key,value):
    p = request(); f = fixture(p); f['plan'][key] = value
    result = a.simulation_gates(p,provider(),f,NOW)
    assert result['permit']=='DENY' and not result['offline_sink_allowed']
    assert not result['execution_authorized']


@pytest.mark.parametrize('field,value', [('kind','REAL_PERMIT'),('scope','LIVE'),
    ('prepared_SHA256','0'*64),('request_id','syn-other')])
def test_negative_fixture_cannot_masquerade_as_live_approval(field,value):
    p = request(); f = fixture(p); f[field] = value
    with pytest.raises(ValueError): a.simulation_gates(p,provider(),f,NOW)


def test_negative_no_fixture_or_fake_transport_callback():
    for f,sink in [(None,a.MemorySink()),(fixture(request()),lambda *_: None)]:
        s = a.OfflineSession(provider(),'syn-g2-run'); p = s.prepare(**inputs())
        with pytest.raises(ValueError): s.deliver(p,sink,fixture=f,final_client_input=a.client_input(p,provider(),NOW),now_utc=NOW)
        assert s.stopped


@pytest.mark.parametrize('fault',['BEFORE_ACCEPT','AFTER_ACCEPT','READBACK'])
def test_negative_sink_failure_retains_attempt_and_never_retries(fault):
    s = a.OfflineSession(provider(),'syn-g2-run'); p = s.prepare(**inputs()); sink = a.MemorySink(fault)
    with pytest.raises(ValueError): s.deliver(p,sink,fixture=fixture(p),final_client_input=a.client_input(p,provider(),NOW),now_utc=NOW)
    assert s.stopped and len(s.attempts)==1 and s.attempts[0]['real_requests']==0
    assert len(sink.records)==(0 if fault=='BEFORE_ACCEPT' else 1)
    with pytest.raises(ValueError,match='RUN_STOPPED'): s.deliver(p,sink,fixture=fixture(p),final_client_input=a.client_input(p,provider(),NOW),now_utc=NOW)
    assert len(s.attempts)==1


@pytest.mark.parametrize('duplicate',['ID','URL','delivery','new-session'])
def test_negative_duplicate_request_URL_or_delivery(duplicate):
    s = a.OfflineSession(provider(),'syn-g2-run'); p = s.prepare(**inputs()); sink = a.MemorySink()
    if duplicate in {'ID','URL'}:
        x = inputs('A3' if duplicate=='ID' else 'B1',request_id='syn-g2-01' if duplicate=='ID' else 'syn-g2-02')
        with pytest.raises(ValueError): s.prepare(**x)
    else:
        kwargs = dict(fixture=fixture(p),final_client_input=a.client_input(p,provider(),NOW),now_utc=NOW)
        s.deliver(p,sink,**kwargs)
        if duplicate=='new-session':
            s = a.OfflineSession(provider(),'syn-g2-run'); s.prepare(**inputs())
        with pytest.raises(ValueError): s.deliver(p,sink,**kwargs)
        assert len(sink.records)==1
    assert s.stopped


@pytest.mark.parametrize('field,value',[('evidence_level','E2'),('evidence_level','E3'),('E2','PASS'),
    ('E3','PASS'),('E4_new_acquisition',True),('response_status',200),('response_hash','1'*64),
    ('transport_outcome','COMPLETED'),('real_permit_issued',True),('execution_authorized',True),
    ('history_admission',True),('Phase_A','READY'),('Phase_B','AUTHORIZED')])
def test_negative_E1_cannot_become_transport_response_or_admission_evidence(field,value):
    p = request(); e = record(p); e[field] = value
    e['record_SHA256'] = a.g1.sha(a.g1.canonical({k:v for k,v in e.items() if k!='record_SHA256'}))
    with pytest.raises(ValueError): a.verify_e1(e,p,provider(),NOW)


def test_old_evidence_and_workers_unchanged_and_no_runtime_imports():
    for phase in ['K','L','M','N']:
        pins = json.loads((ROOT/f'research/nn_v2/phase2_5{phase}/SHA256-MANIFEST.json').read_bytes())['files']
        assert all(a.g1.sha((ROOT/p).read_bytes())==h for p,h in pins.items())
    tree = ast.parse(Path(a.__file__).read_text(encoding='utf8'))
    imports = [ast.unparse(x) for x in ast.walk(tree) if isinstance(x,(ast.Import,ast.ImportFrom))]
    assert not any(any(b in s for b in ['http.client','urllib.request','requests','httpx','socket','subprocess','os','collect','access_worker','spec_worker','modeling']) for s in imports)
    assert not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id in {'open','exec','eval','__import__'} for x in ast.walk(tree))


def test_legacy_worker_boundary_shape_is_reviewed_by_AST_without_import():
    for phase,worker in [('G','access_worker.py'),('I','spec_worker.py')]:
        tree = ast.parse((ROOT/f'research/nn_v2/phase2_5{phase}'/worker).read_text(encoding='utf8'))
        calls = [x for x in ast.walk(tree) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute) and isinstance(x.func.value,ast.Name) and x.func.value.id=='conn' and x.func.attr=='request']
        assert len(calls)==1 and ast.literal_eval(calls[0].args[0])=='GET'
        headers = next(k.value for k in calls[0].keywords if k.arg=='headers')
        assert {ast.literal_eval(k) for k in headers.keys}=={'Host','User-Agent','Accept-Encoding','Connection'}


def test_published_E1_schema_readback_and_legacy_schema_separation():
    out = ROOT/'research/nn_v2/phase2_5O'
    schema = json.loads((out/'REQUEST_EVIDENCE_SCHEMA.json').read_bytes())
    Draft202012Validator.check_schema(schema)
    for row in json.loads((out/'E1_REQUEST_EVIDENCE.json').read_bytes())['records']:
        assert not list(Draft202012Validator(schema).iter_errors(row))
        now = row['evidence_utc']
        assert a.verify_e1(row,row['prepared_request'],provider(),now)['status']=='PASS_OFFLINE_E1_ONLY'
    old = json.loads((ROOT/'research/nn_v2/phase2_5L/REQUEST_EVIDENCE_SCHEMA.json').read_bytes())
    assert list(Draft202012Validator(old).iter_errors(record()))


def test_negative_published_E1_schema_forbids_promoted_fields():
    schema = json.loads((ROOT/'research/nn_v2/phase2_5O/REQUEST_EVIDENCE_SCHEMA.json').read_bytes())
    for field,value in [('E2','PASS'),('response_status',200),('real_permit_issued',True),('evidence_level','E4'),('extra',True)]:
        e = record(); e[field] = value
        assert list(Draft202012Validator(schema).iter_errors(e))
