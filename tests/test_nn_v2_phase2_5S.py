"""Offline models and syn-* staging only. Never start a process, socket or Job."""
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
import ast
import json

import pytest
from jsonschema import Draft202012Validator
from research.nn_v2.phase2_5S import qualification as q
from research.nn_v2.phase2_5S import attempt_staging as a

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'research/nn_v2/phase2_5S'
NOW = '2026-10-25T00:00:00+00:00'
BODY = b'Synthetic robots, not a fetched response.'
PIN = sha256(BODY).hexdigest()
REQUEST = '1'*64


def cache(**kw):
    args = dict(expected_SHA256=PIN, acquired_utc='2026-10-23T00:00:00+00:00', reviewed_utc=NOW,
                cache_control=None, unreachable_observed=None, project_policy=None)
    args.update(kw)
    return q.cache_review(BODY, **args)


def authority():
    return dict(scope='OFFLINE_ONLY', terms='UNKNOWN', robots='CONDITIONAL_FIXED_ALLOW', E2='UNKNOWN', E3='UNKNOWN',overall_access='HOLD',
                holds=dict(q.HOLDS), permit_ready=False, G3_authorized=False, G4_authorized=False, live_send_authorized=False)


def store(tmp_path):
    return a.StagingLedger(tmp_path/'syn-store')


def step(s, state='RESERVED', *, aid='syn-S-A3', req=REQUEST, target='A3', at=NOW, fault=None):
    x = s.read()
    e = s.event(aid, req, target, state, at)
    return s.commit(e, expected_revision=x['revision'], expected_head_SHA256=x['head_SHA256'], fault=fault)


@pytest.mark.parametrize('elapsed_days,unreachable,expected', [(0, None, 'CONDITIONAL_WITHIN_24H'),
    (1, False, 'CONDITIONAL_WITHIN_24H'), (2, None, 'UNKNOWN'), (2, False, 'UNKNOWN'),
    (2, True, 'CONDITIONAL_UNREACHABLE_EXCEPTION')])
def test_cache_recommendation_exception_and_currentness_are_separate(elapsed_days, unreachable, expected):
    reviewed = ['2026-10-23T00:00:00+00:00','2026-10-24T00:00:00+00:00','2026-10-25T00:00:00+00:00'][elapsed_days]
    x = cache(reviewed_utc=reviewed, unreachable_observed=unreachable)
    assert x['NORMATIVE_CACHE_ELIGIBILITY'] == expected
    assert x['SOURCE_CURRENTNESS_EVIDENCE'] == 'UNKNOWN' and x['FETCH_ELIGIBILITY'] == 'HOLD_OFFLINE_ONLY'
    assert not x['age_alone_invalidates_original'] and not x['permit_ready']


def test_negative_01_old_robots_does_not_establish_fetch_eligibility():
    assert cache()['NORMATIVE_CACHE_ELIGIBILITY'] == 'UNKNOWN'
    assert cache()['FETCH_ELIGIBILITY'] == 'HOLD_OFFLINE_ONLY'


def test_negative_02_unknown_Cache_Control_is_not_invented_TTL():
    x = cache(reviewed_utc='2026-10-23T01:00:00+00:00')
    assert x['cache_control_evidence'] == x['PROJECT_FRESHNESS_POLICY'] == 'UNKNOWN'


def test_negative_03_original_hash_mismatch():
    with pytest.raises(q.QualificationError, match='HASH'): cache(expected_SHA256='0'*64)


def test_negative_04_normative_rule_is_not_project_policy_adoption():
    assert not cache()['normative_recommendation_is_project_TTL']
    with pytest.raises(q.QualificationError, match='NO_POLICY_ADOPTION'):
        cache(project_policy=dict(kind='ADOPTED_FROM_RFC_WITHOUT_APPROVAL', TTL_seconds=86400))


def test_negative_05_eligible_cache_does_not_prove_currentness():
    x = cache(unreachable_observed=True)
    assert x['NORMATIVE_CACHE_ELIGIBILITY'].startswith('CONDITIONAL')
    assert x['SOURCE_CURRENTNESS_EVIDENCE'] == 'UNKNOWN' and not x['cached_bytes_are_current_live_bytes']


@pytest.mark.parametrize('header', ['s-maxage=31536000', 'max-age=86400', 'no-cache', 'private', ''])
def test_negative_headers_do_not_automatically_create_freshness_permission(header):
    x = cache(cache_control=header)
    assert x['PROJECT_FRESHNESS_POLICY'] == x['SOURCE_CURRENTNESS_EVIDENCE'] == 'UNKNOWN'


@pytest.mark.parametrize('ttl,expected', [(86400,'SYNTHETIC_REVIEW_REQUIRED'),(259200,'SYNTHETIC_WITHIN_TTL')])
def test_synthetic_TTL_policy_still_never_authorizes_fetch(ttl, expected):
    x = cache(project_policy=dict(kind='SYNTHETIC_POLICY_ONLY', TTL_seconds=ttl))
    assert x['PROJECT_FRESHNESS_POLICY'] == expected and not x['execution_authorized']


def test_negative_06_repeated_slow_reads_have_finite_total_deadline():
    m = q.VirtualDeadline()
    assert all(m.step('read', 14) for _ in range(4))
    assert not m.step('read', 14) and m.now == 60 and m.state == 'UNKNOWN_OUTCOME_STOP'
    with pytest.raises(q.QualificationError, match='TERMINAL_NO_RETRY'): m.step('read', 1)


def test_negative_07_fake_Job_expiry_is_stop_not_real_Job_proof():
    m = q.VirtualDeadline();m.step('dns', 50)
    x = m.stop_for_job_expiry(60)
    assert x['logical_stop'] and x['consumed'] and not x['retry'] and not x['actual_Job_proven']


def test_negative_08_storage_hash_fsync_readback_share_a_finite_budget():
    m = q.VirtualDeadline();assert m.step('hash', 6)
    assert not m.step('fsync', 6) and m.now == 10
    with pytest.raises(q.QualificationError): m.step('readback', 1)


@pytest.mark.parametrize('phase,delay', [('dns',61),('tcp',6),('tls',6),('read',16)])
def test_negative_phase_timeouts_are_distinct_from_whole_process_deadline(phase, delay):
    assert not q.VirtualDeadline().step(phase, delay)


def test_virtual_good_path_is_only_a_model():
    m = q.VirtualDeadline()
    assert all(m.step(p, d) for p,d in [('dns',2),('tcp',3),('tls',3),('read',10),('hash',2),('fsync',2),('readback',2)])
    assert m.now == 24 and not m.transport_proven


def test_negative_09_unknown_outcome_is_consumed_and_never_retried(tmp_path):
    s = store(tmp_path);step(s);step(s,'UNKNOWN_OUTCOME')
    s = a.StagingLedger(s.root)
    with pytest.raises(a.LedgerError): step(s,'STARTED')
    with pytest.raises(a.LedgerError): step(s,aid='syn-new')
    with pytest.raises(a.LedgerError): step(s,aid='syn-A4',target='A4',req='2'*64)


def test_negative_10_same_user_path_policy_is_not_OS_write_deny():
    x = q.path_policy('R:/syn-session/raw/original.bin',same_user_can_write_production=True)
    assert x['application_write_allowed'] and x['same_user_production_access_risk']
    assert x['OS_WRITE_DENIAL'] == 'UNKNOWN' and not x['actual_ACL_proven']
    assert not q.path_policy('C:/production/predictions/result.csv')['application_write_allowed']


@pytest.mark.parametrize('path', ['R:/syn-session/raw/file.bin','R:/syn-session/ledger/intent.json'])
def test_negative_11_reparse_junction_or_volume_escape(path):
    assert not q.path_policy(path,reparse=True)['application_write_allowed']
    assert not q.path_policy(path,same_volume=False)['application_write_allowed']


@pytest.mark.parametrize('path', ['R:/syn-session/raw/../../production/file','R:/syn-session/raw/../raw/file',
    'R:/syn-session/rawish/file','R:relative','//server/share/raw/file','\\\\?\\R:\\syn-session\\raw\\file',
    'R:/syn-session/raw/file:stream','C:/syn-session/raw/file','R:/syn-session/raw/./file'])
def test_negative_12_path_traversal_UNC_ADS_or_wrong_root(path):
    assert not q.path_policy(path)['application_write_allowed']


@pytest.mark.parametrize('fault', ['ENOSPC','EACCES','partial','after_claim','after_state','replace_denied'])
def test_negative_13_18_staging_failures_and_incomplete_write_hold_without_repair(tmp_path,fault):
    s = store(tmp_path)
    with pytest.raises((a.LedgerError,OSError)): step(s,fault=fault)
    names = {p.name for p in s.root.iterdir()}
    with pytest.raises(a.LedgerError, match='ORPHANED'): a.StagingLedger(s.root)
    assert {p.name for p in s.root.iterdir()} == names


def test_negative_14_duplicate_reservation_and_20_ID_reuse(tmp_path):
    s = store(tmp_path);step(s)
    with pytest.raises(a.LedgerError): step(s)
    with pytest.raises(a.LedgerError): step(s,aid='syn-other')
    with pytest.raises(a.LedgerError): step(s,'STARTED',req='2'*64)


def test_negative_15_two_simulated_contenders_use_CAS_without_process_claim(tmp_path):
    s1 = store(tmp_path);s2 = a.StagingLedger(s1.root)
    old = s1.read();e = s1.event('syn-S-A3',REQUEST,'A3','RESERVED',NOW)
    winner = s1.commit(e,expected_revision=old['revision'],expected_head_SHA256=old['head_SHA256'])
    with pytest.raises(a.LedgerError,match='TRUSTED_HEAD'): s2.commit(e,expected_revision=old['revision'],expected_head_SHA256=old['head_SHA256'])
    with pytest.raises(a.LedgerError,match='CAS_CONFLICT'): s2.commit(e,expected_revision=0,expected_head_SHA256=winner['head_SHA256'])


def test_negative_16_corrupt_JSON_is_not_repaired(tmp_path):
    s = store(tmp_path);step(s)
    (s.root/'state-000001.json').write_bytes(b'{corrupt')
    with pytest.raises(a.LedgerError,match='CORRUPT'): a.StagingLedger(s.root)
    assert (s.root/'state-000001.json').read_bytes() == b'{corrupt'


def test_negative_17_hash_tamper_and_untrusted_new_head(tmp_path):
    s = store(tmp_path);x = step(s)
    head = json.loads((s.root/'head.json').read_bytes());head['state_SHA256']='0'*64
    (s.root/'head.json').write_bytes(a.encoded(head))
    with pytest.raises(a.LedgerError,match='TRUSTED_HEAD'): s.read(expected_head_SHA256=x['head_SHA256'])
    with pytest.raises(a.LedgerError,match='STATE_HASH'): s.read()


def test_negative_17_whitespace_byte_tamper_is_not_silently_recanonicalized(tmp_path):
    s=store(tmp_path);step(s)
    p=s.root/'state-000001.json';p.write_bytes(b' '+p.read_bytes())
    with pytest.raises(a.LedgerError,match='CORRUPT'):s.read()


def test_negative_19_wall_clock_rollback_and_bad_virtual_clock(tmp_path):
    s = store(tmp_path);step(s)
    with pytest.raises(a.LedgerError,match='CLOCK_ROLLBACK'): step(s,'STARTED',at='2026-10-24T23:59:59+00:00')
    m = q.VirtualDeadline();m.step('read',4)
    with pytest.raises(q.QualificationError,match='MONOTONIC'):m.stop_for_job_expiry(3)
    failed=q.VirtualDeadline();assert not failed.step('dns',61)
    with pytest.raises(q.QualificationError,match='MONOTONIC'):failed.stop_for_job_expiry(59)


@pytest.mark.parametrize('subject', ['OS_write_deny','real_Job','real_process_CAS','power_loss_durability'])
def test_negative_21_22_static_or_fake_evidence_cannot_be_dynamic_PASS(subject):
    item=dict(subject=subject,status='PROVEN_OFFLINE',method='OFFLINE',actual_OS_or_transport_proven=False,
              evidence=['synthetic'],unproven=['actual'],next_action='review',approval='required',stop_conditions=['unknown'],G3_impact='HOLD')
    with pytest.raises(q.QualificationError,match='STATIC_OR_FAKE'): q.validate_qualification_item(item)
    item['status']='PROVEN_DYNAMIC'
    with pytest.raises(q.QualificationError): q.validate_qualification_item(item)


@pytest.mark.parametrize('key,value', [('permit_ready',True),('terms','ALLOW'),('E2','PASS'),('E3','PASS'),
    ('G3_authorized',True),('G4_authorized',True),('live_send_authorized',True),('overall_access','ALLOW')])
def test_negative_23_24_25_26_no_robots_only_terms_E1_or_G3_G4_promotion(key,value):
    c=authority();c[key]=value
    with pytest.raises(q.QualificationError):q.require_no_authority(c)


def test_negative_unknown_authority_extension_fails_closed():
    c=authority();c['hidden_live_transport_permission']=True
    with pytest.raises(q.QualificationError,match='AUTHORITY_SCHEMA'):q.require_no_authority(c)


@pytest.mark.parametrize('hold', list(q.HOLDS))
def test_negative_all_historical_HOLDs_are_immutable(hold):
    c=authority();c['holds'][hold]='READY'
    with pytest.raises(q.QualificationError,match='HOLD'):q.require_no_authority(c)


def test_atomic_replace_readback_and_simulated_restart_are_local_only(tmp_path):
    s = store(tmp_path)
    for state in ['RESERVED','STARTED','SENT','COMPLETED']:step(s,state)
    before=s.read();s=a.StagingLedger(s.root)
    assert s.read()==before and before['revision']==4
    assert not (s.root/'head.pending.json').exists()
    assert len(list(s.root.glob('claim-*.json')))==4
    step(s,aid='syn-S-A4',target='A4',req='2'*64)
    assert s.read()['revision']==5


def test_interrupt_after_atomic_replace_has_consumed_state_even_without_ack(tmp_path):
    s=store(tmp_path)
    with pytest.raises(a.LedgerError,match='AFTER_REPLACE'):step(s,fault='after_replace')
    s=a.StagingLedger(s.root)
    assert s.read()['revision']==1
    with pytest.raises(a.LedgerError):step(s)


@pytest.mark.parametrize('bad', [None,True,'latest','0'*63])
def test_negative_invalid_digest_never_reserves(tmp_path,bad):
    s=store(tmp_path)
    with pytest.raises(a.LedgerError):step(s,req=bad)
    assert s.read()['revision']==0


def test_qualification_artifact_and_closed_schema():
    value=json.loads((OUT/'QUALIFICATION_MATRIX.json').read_bytes())
    schema=json.loads((OUT/'QUALIFICATION_SCHEMA.json').read_bytes());Draft202012Validator.check_schema(schema)
    validator=Draft202012Validator(schema);assert not list(validator.iter_errors(value))
    assert [track['track'] for track in value['tracks']]==['A','B','C','D']
    for track in value['tracks']:
        for item in track['items']:assert q.validate_qualification_item(item)
    bad=deepcopy(value);bad['tracks'][0]['items'][0]['actual_OS_or_transport_proven']=True
    assert list(validator.iter_errors(bad))
    q.require_no_authority(value['authority'])


def test_no_network_process_Job_ACL_or_model_entrypoints():
    modules=set()
    for name in ['qualification.py','attempt_staging.py']:
        tree=ast.parse((OUT/name).read_text(encoding='utf8'))
        modules|={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
        modules|={x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names}
        assert not any(isinstance(n,ast.Name) and n.id in {'exec','eval','__import__','socket','subprocess','requests','ctypes'} for n in ast.walk(tree))
    assert modules <= {'datetime','hashlib','pathlib','math','re','json','os','errno'}
