"""Synthetic permit review / memory ledger only; no socket or child probes."""
from copy import deepcopy
from pathlib import Path
import ast
import json

import pytest
from jsonschema import Draft202012Validator
from research.nn_v2.phase2_5P import pre_review as p

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-10-24T11:30:00+00:00'
PD, RD = '1'*64, '2'*64


def case(target='A3'):
    return dict(kind=p.VERSION, scope='SYNTHETIC_ONLY', fixture_id='syn-P-review', approver='syn-reviewer',
        approval_utc='2026-10-24T11:20:00+00:00', start_utc='2026-10-24T11:25:00+00:00', end_utc='2026-10-24T11:35:00+00:00',
        target_id=target, exact_url=p.g2.m.TARGETS[target], family='A_ACCESS_CONDITIONS_ONLY' if target.startswith('A') else 'B_ENTRY_ONLY',
        method='GET', user_agent=p.g2.g1.HTTP_USER_AGENT, product_token=p.g2.g1.ROBOTS_PRODUCT_TOKEN,
        G1_manifest_SHA256=p.g2.G1_FILE_SHA, source_revision=p.g2.g1.BASE_COMMIT, limits=p.limits(target),
        storage='SYNTHETIC_MEMORY_ONLY', audit_ledger='SYNTHETIC_HASH_CHAIN_ONLY',
        checks=dict.fromkeys(p.CHECKS,'PASS'), P2=dict(p.P2), issued=False, allow_resume=False)


def step(raw, state, *, aid='syn-attempt-1', pd=PD, expected_revision=None, stamp=NOW):
    return p.model_transition(raw,expected_SHA256=p.g2.g1.sha(raw),
        expected_revision=json.loads(raw)['revision'] if expected_revision is None else expected_revision,
        attempt_id=aid,permit_digest=pd,request_digest=RD,to_state=state,at_utc=stamp)


def sequence(*states):
    raw=p.empty_model()
    for state in states: raw=step(raw,state)
    return raw


@pytest.mark.parametrize('target',list(p.CAPS))
def test_synthetic_candidate_has_no_real_permit_G4_or_POST_send_proof(target):
    x=p.assess_synthetic_case(case(target),NOW)
    assert x['decision']=='SYNTHETIC_REVIEW_CANDIDATE_ONLY'
    assert not any(x[k] for k in ['real_permit_issued','execution_authorized','G4_authorized','history_admission','real_prerequisites_verified'])


@pytest.mark.parametrize('key',p.CHECKS)
@pytest.mark.parametrize('status',['DENY','UNKNOWN'])
def test_negative_each_unproven_prerequisite_blocks_synthetic_review(key,status):
    x=case();x['checks'][key]=status
    out=p.assess_synthetic_case(x,NOW)
    assert out['decision']=='SYNTHETIC_REVIEW_REJECTED' and out['reasons']==[key+':'+status]
    assert not out['real_permit_issued']


@pytest.mark.parametrize('key,value',[('scope','LIVE'),('kind','REAL_PERMIT'),('fixture_id','real-id'),
    ('approver','user'),('approval_utc','2026-10-24T11:26:00+00:00'),('start_utc','2026-10-24T11:31:00+00:00'),
    ('end_utc',NOW),('end_utc','2026-10-24T11:29:59+00:00'),('target_id','B3'),
    ('exact_url','https://other.invalid/general/kiyaku/'),('exact_url','https://www.jleague.jp/general/kiyaku/?x=1'),
    ('method','HEAD'),('user_agent','Other/1.0'),('product_token','Other'),('G1_manifest_SHA256','0'*64),
    ('source_revision','latest'),('storage','C:/production'),('audit_ledger','REAL_LEDGER'),
    ('issued',True),('allow_resume',True),('family','B_ENTRY_ONLY')])
def test_negative_case_scope_identity_time_storage_and_no_issuance(key,value):
    x=case();x[key]=value
    assert p.assess_synthetic_case(x,NOW)['decision']=='SYNTHETIC_REVIEW_REJECTED'


def test_negative_absent_permit_or_unknown_approval_not_issued():
    assert p.assess_synthetic_case(None,NOW)['decision']=='SYNTHETIC_REVIEW_REJECTED'
    x=case();x['checks']['explicit_user_approval']='UNKNOWN'
    assert not p.assess_synthetic_case(x,NOW)['real_permit_issued']


@pytest.mark.parametrize('key,value',[('max_requests',2),('per_URL',2),('body_cap',2097153),
    ('retry',1),('redirect',1),('parallel',1),('interval_seconds',0),('parent_seconds',0),('global_seconds',True)])
def test_negative_extra_requests_redirect_retry_and_deadline_change(key,value):
    x=case();x['limits'][key]=value
    assert p.assess_synthetic_case(x,NOW)['decision']=='SYNTHETIC_REVIEW_REJECTED'


@pytest.mark.parametrize('field',list(p.P2))
def test_negative_E1_or_pre_review_cannot_create_P2_or_G4(field):
    x=case();x['P2'][field]='PASS'
    result=p.assess_synthetic_case(x,NOW)
    assert result['decision']=='SYNTHETIC_REVIEW_REJECTED' and not result['G4_authorized']


def test_positive_logical_ledger_and_terminal_state_never_grants_execution():
    raw=sequence('CREATED','RESERVED','STARTED','SENT','COMPLETED')
    value,states,used=p.inspect_model(raw,p.g2.g1.sha(raw))
    assert value['revision']==5 and states=={'syn-attempt-1':'COMPLETED'} and used=={PD}
    assert p.model_recovery(raw,p.g2.g1.sha(raw))['storage_durability_proven'] is False


def test_negative_logical_competing_reservation_has_CAS_conflict_not_OS_proof():
    before=sequence('CREATED');old_revision=json.loads(before)['revision']
    winner=step(before,'RESERVED',expected_revision=old_revision)
    with pytest.raises(ValueError,match='CAS_CONFLICT'):step(winner,'RESERVED',expected_revision=old_revision)
    assert json.loads(winner)['revision']==2


def test_negative_new_permit_does_not_reauthorize_same_reserved_request_hash():
    raw=sequence('CREATED','RESERVED','UNKNOWN_OUTCOME')
    raw=step(raw,'CREATED',aid='syn-attempt-2',pd='3'*64)
    with pytest.raises(ValueError,match='REQUEST_ALREADY_RESERVED'):
        step(raw,'RESERVED',aid='syn-attempt-2',pd='3'*64)


@pytest.mark.parametrize('terminal',['ABORTED','UNKNOWN_OUTCOME','COMPLETED'])
def test_negative_consumption_never_refunded_on_failure_or_completion(terminal):
    states=['CREATED','RESERVED']
    if terminal=='COMPLETED':states+=['STARTED','SENT']
    raw=sequence(*states,terminal)
    raw=step(raw,'CREATED',aid='syn-attempt-2')
    with pytest.raises(ValueError,match='PERMIT_ALREADY_CONSUMED'):step(raw,'RESERVED',aid='syn-attempt-2')


@pytest.mark.parametrize('last',['RESERVED','STARTED','SENT'])
def test_negative_crash_model_requires_manual_review_and_no_automatic_retry(last):
    states=['CREATED','RESERVED','STARTED','SENT'];raw=sequence(*states[:states.index(last)+1])
    out=p.model_recovery(raw,p.g2.g1.sha(raw))
    assert out['status']=='HOLD_MANUAL_OWNERSHIP_REVIEW' and out['pending_attempts']==['syn-attempt-1']
    assert not out['automatic_resume'] and not out['retry_allowed'] and not out['real_execution_authorized']
    terminal=step(raw,'UNKNOWN_OUTCOME')
    with pytest.raises(ValueError):step(terminal,'STARTED')


@pytest.mark.parametrize('mutation',['raw','chain','revision','binding','time','duplicate','illegal-skip'])
def test_negative_ledger_readback_tamper_and_state_contradiction(mutation):
    raw=sequence('CREATED','RESERVED','STARTED');trusted=p.g2.g1.sha(raw)
    x=json.loads(raw)
    if mutation=='raw':
        with pytest.raises(ValueError,match='MODEL_READBACK_SHA'):p.inspect_model(raw+b' ',trusted)
        return
    if mutation=='chain':x['events'][1]['previous_event_SHA256']='0'*64
    elif mutation=='revision':x['revision']=99
    elif mutation=='binding':x['events'][2]['permit_digest']='3'*64
    elif mutation=='time':x['events'][2]['UTC']='2026-10-24T11:29:59+00:00'
    elif mutation=='duplicate':x['events'][2]['to_state']='CREATED'
    else:x['events'][0]['to_state']='COMPLETED'
    # Rehash every event: logical checks, not just stale event digests, must reject.
    previous=None
    for event in x['events']:
        event['previous_event_SHA256']=previous if mutation!='chain' else event['previous_event_SHA256']
        event['event_SHA256']=p.g2.g1.sha(p.g2.g1.canonical({k:v for k,v in event.items() if k!='event_SHA256'}))
        previous=event['event_SHA256']
    changed=p.g2.g1.canonical(x)
    with pytest.raises(ValueError):p.inspect_model(changed,p.g2.g1.sha(changed))


def test_negative_response_hash_failure_and_synthetic_success_not_real_E4():
    raw=b'synthetic response only'
    with pytest.raises(ValueError):p.verify_synthetic_response(raw,'0'*64)
    result=p.verify_synthetic_response(raw,p.g2.g1.sha(raw))
    assert not any(result[k] for k in ['actual_E2','actual_E3','actual_E4','execution_authorized'])


@pytest.mark.parametrize('key',['TLS_policy','Job','ACL','OS_isolation'])
def test_negative_mock_TLS_failure_Job_escape_ACL_denial_or_no_OS_proof(key):
    x=case();x['checks'][key]='UNKNOWN' if key=='OS_isolation' else 'DENY'
    assert p.assess_synthetic_case(x,NOW)['decision']=='SYNTHETIC_REVIEW_REJECTED'


def test_G2_memory_sink_reused_without_real_transport_or_permit():
    from test_nn_v2_g2_offline_adapter import provider,inputs,fixture,NOW as old_now
    a=p.g2;s=a.OfflineSession(provider(),'syn-g2-run');r=s.prepare(**inputs());sink=a.MemorySink()
    result=s.deliver(r,sink,fixture=fixture(r),final_client_input=a.client_input(r,provider(),old_now),now_utc=old_now)
    assert not result['real_execution_authorized'] and result['E1']['E2']==result['E1']['E3']=='UNKNOWN'


def test_local_synthetic_schema_and_required_contract_fields():
    out=ROOT/'research/nn_v2/phase2_5P'
    schema=json.loads((out/'SYNTHETIC_REVIEW_SCHEMA.json').read_bytes())
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(case()))
    bad=case();bad['issued']=True
    assert list(Draft202012Validator(schema).iter_errors(bad))
    contract=json.loads((out/'G3_PERMIT_CONTRACT.json').read_bytes())
    assert contract['kind']=='DESIGN_NOT_PERMIT' and not contract['permit_issued']
    assert set(contract['required_future_permit_fields'])>={'permit_id','approver','approval_utc','exact_URL_allowlist','audit_ledger','usage_state_reference'}


def test_preserved_9_UNKNOWNs_six_scope_rows_and_no_runtime_imports():
    out=ROOT/'research/nn_v2/phase2_5P'
    x=json.loads((out/'G3_UNKNOWN_CLASSIFICATION.json').read_bytes())
    assert [r['id'] for r in x['rows']]==list(p.g2.m.IDS) and all(r['status']=='UNKNOWN' for r in x['rows'])
    rows=json.loads((out/'G3_PRE_REVIEW_MATRIX.json').read_bytes())['rows']
    assert len(rows)==6 and all(not r['permit_issuable_now'] and not r['execution_authorized'] for r in rows)
    tree=ast.parse(Path(p.__file__).read_text(encoding='utf8'))
    assert {x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names}=={'re'}
    assert {x.module for x in ast.walk(tree) if isinstance(x,ast.ImportFrom)}=={'research.nn_v2.phase2_5O'}
    assert not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id in {'open','eval','exec','__import__'} for x in ast.walk(tree))
