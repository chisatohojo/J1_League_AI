"""Offline refusal tests and real local synthetic-ledger I/O; no live probes."""
from pathlib import Path
from copy import deepcopy
import ast
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator
from research.nn_v2.phase2_5R import offline_review as r

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'research/nn_v2/phase2_5R'
NOW = '2026-10-24T14:35:00+00:00'


def fixture():
    body = b'<html><body>synthetic terms fixture only</body></html>'
    return dict(kind='SYNTHETIC_R_RESPONSE', status=200, body=body,
        content_type='text/html; charset=utf-8', content_length=len(body),
        expected_SHA256=hashlib.sha256(body).hexdigest(), redirect_followed=False,
        retry_count=0, resource_requests=0, TLS_verified=True, hostname_verified=True,
        E2='NOT_ACTUAL_SYNTHETIC_ONLY', E3='NOT_ACTUAL_SYNTHETIC_ONLY', E4='NOT_ACTUAL_SYNTHETIC_ONLY')


def store(tmp_path):
    return r.SyntheticAttemptStore(tmp_path/'syn-store')


@pytest.mark.parametrize('target', list(r.TARGETS))
def test_hypothetical_complete_precheck_never_grants_live_or_G3_G4(target):
    out = r.synthetic_precheck(r.request(target), dict.fromkeys(r.CHECKS, 'PASS'))
    assert out['status'] == 'SYNTHETIC_PRECHECK_COMPLETE_ONLY'
    assert not out['live_send_authorized'] and not out['G3_permit'] and not out['G4_authorized']
    with pytest.raises(r.ReviewError, match='NO_QUALIFIED_LIVE_CLIENT'):
        r.require_live_preconditions(dict.fromkeys(r.CHECKS, 'PASS'))


@pytest.mark.parametrize('field', r.CHECKS)
@pytest.mark.parametrize('state', ['DENY', 'UNKNOWN'])
def test_negative_each_precondition_denies_without_transport(field, state):
    checks = dict.fromkeys(r.CHECKS, 'PASS'); checks[field] = state
    out = r.synthetic_precheck(r.request('A3'), checks)
    assert out['status'] == 'REJECTED' and out['reasons'] == [field+':'+state]
    with pytest.raises(r.ReviewError, match='PRE_SEND_HOLD'):
        r.require_live_preconditions(checks)


REQUEST_MUTATIONS = [
    ('target', 'A1'), ('target', 'A2'), ('target', 'B1'), ('target', 'B2'),
    ('URL', 'https://www.jleague.jp/general/kiyaku/?page=2'),
    ('URL', 'https://aboutj.jleague.jp/general/kiyaku/'),
    ('URL', 'https://www.jleague.jp:443/general/kiyaku/'),
    ('method', 'HEAD'), ('method', 'POST'), ('user_agent', r.UA+' '),
    ('user_agent', 'Other/1.0'), ('product_token', 'spider'), ('purpose', 'RESEARCH_DATA'),
    ('cookie', 'session=anything'), ('authentication', True),
    ('certificate_verification', False), ('hostname_verification', False),
    ('G3_permit', True), ('G4_authority', True)]


@pytest.mark.parametrize('field,value', REQUEST_MUTATIONS)
def test_negative_URL_method_UA_scope_cookie_TLS_and_authority(field, value):
    x = r.request('A3'); x[field] = value
    assert r.synthetic_precheck(x, dict.fromkeys(r.CHECKS, 'PASS'))['status'] == 'REJECTED'


@pytest.mark.parametrize('field,value', [('max_attempts_per_URL', 2), ('max_total_attempts', 3),
    ('body_cap', 1048577), ('connect_timeout_seconds', 10), ('read_timeout_seconds', 10),
    ('retry', 1), ('redirect', 1), ('external_resources', 1), ('retry', False),
    ('max_attempts_per_URL', True)])
def test_negative_fixed_attempt_budget_timeouts_and_additional_resource(field, value):
    x = r.request('A3'); x['limits'][field] = value
    assert r.synthetic_precheck(x, dict.fromkeys(r.CHECKS, 'PASS'))['status'] == 'REJECTED'


@pytest.mark.parametrize('field,value', [('status', 301), ('status', 302), ('status', 403),
    ('status', 429), ('status', 500), pytest.param('body', b'x'*1048577, id='body_over_1_MiB'), ('body', b''),
    ('expected_SHA256', '0'*64), ('content_length', 1), ('content_length', True),
    ('content_type', 'application/octet-stream'), ('TLS_verified', False),
    ('hostname_verified', False), ('redirect_followed', True), ('retry_count', 1),
    ('resource_requests', 1), ('E2', 'PASS'), ('E3', 'PASS'), ('E4', 'PASS'),
    ('kind', 'REAL_RESPONSE')])
def test_negative_response_status_size_readback_redirect_retry_resource_and_E_levels(field, value):
    x = fixture(); x[field] = value
    with pytest.raises(r.ReviewError): r.validate_synthetic_response(x)


def test_synthetic_body_is_never_actual_E2_E3_E4_or_terms_permission():
    out = r.validate_synthetic_response(fixture())
    assert not out['actual_E2'] and not out['actual_E3'] and not out['actual_E4']
    assert out['terms'] == 'UNKNOWN' and not out['server_observation_proven']


def test_durable_consumed_intent_is_read_back_before_any_hypothetical_call(tmp_path):
    s = store(tmp_path); value = r.request('A3')
    intent = s.consume(value, NOW)
    assert intent['consumed'] and not intent['transport_called']
    assert intent['UTC'] == NOW and intent['JST'].endswith('+09:00')
    assert intent['request_SHA256'] == hashlib.sha256(r.canonical(value)).hexdigest()
    reopened = r.SyntheticAttemptStore(s.root)
    assert reopened.inspect()[0]['A3'] == intent
    with pytest.raises(r.ReviewError, match='ALREADY_CONSUMED'): reopened.consume(value, NOW)


@pytest.mark.parametrize('outcome', ['TIMEOUT', 'CRASH_UNKNOWN_OUTCOME', 'SAVE_FAILED'])
def test_negative_timeout_crash_or_save_failure_never_refunds_or_allows_A4(tmp_path, outcome):
    s = store(tmp_path); s.consume(r.request('A3'), NOW); s.finish('A3', outcome)
    s = r.SyntheticAttemptStore(s.root)
    with pytest.raises(r.ReviewError, match='ALREADY_CONSUMED'): s.consume(r.request('A3'), NOW)
    with pytest.raises(r.ReviewError, match='GLOBAL_STOP'): s.consume(r.request('A4'), NOW)


def test_negative_partial_intent_after_interruption_blocks_reopen_and_second_target(tmp_path):
    s = store(tmp_path)
    (s.root/'A3.intent.json').write_bytes(b'{"partial":')
    with pytest.raises(r.ReviewError, match='LEDGER_CORRUPTION'): r.SyntheticAttemptStore(s.root)
    with pytest.raises(r.ReviewError, match='LEDGER_CORRUPTION'): s.consume(r.request('A4'), NOW)


@pytest.mark.parametrize('file', ['session.json', 'A3.intent.json', 'A3.result.json'])
def test_negative_corrupt_ledger_fails_closed_without_repair(tmp_path, file):
    s = store(tmp_path); s.consume(r.request('A3'), NOW); s.finish('A3', 'SYNTHETIC_SUCCESS')
    (s.root/file).write_bytes(b'{"SHA256":"forged"}')
    with pytest.raises(r.ReviewError, match='LEDGER_CORRUPTION'): r.SyntheticAttemptStore(s.root)
    assert (s.root/file).read_bytes() == b'{"SHA256":"forged"}'


def test_negative_A4_cannot_precede_A3_success(tmp_path):
    s = store(tmp_path)
    with pytest.raises(r.ReviewError, match='A3_BEFORE_A4'): s.consume(r.request('A4'), NOW)
    s.consume(r.request('A3'), NOW)
    with pytest.raises(r.ReviewError, match='A3_BEFORE_A4'): s.consume(r.request('A4'), NOW)


def test_two_successful_synthetic_slots_are_terminal_and_exclusive(tmp_path):
    s = store(tmp_path)
    for target in r.TARGETS:
        s.consume(r.request(target), NOW); s.finish(target, 'SYNTHETIC_SUCCESS')
    assert set(s.inspect()[0]) == set(r.TARGETS)
    for target in r.TARGETS:
        with pytest.raises(r.ReviewError, match='ALREADY_CONSUMED'): s.consume(r.request(target), NOW)
        with pytest.raises(FileExistsError): s.finish(target, 'SYNTHETIC_SUCCESS')


def test_negative_session_substitution_does_not_reuse_consumed_budget(tmp_path):
    s = store(tmp_path); s.consume(r.request('A3'), NOW)
    with pytest.raises(r.ReviewError, match='SESSION_BINDING'):
        r.SyntheticAttemptStore(s.root, session='syn-other')


@pytest.mark.parametrize('timestamp', ['2026-10-24T14:35:00', '2026-10-24T23:35:00+09:00', None])
def test_negative_missing_or_non_UTC_intent_time(tmp_path, timestamp):
    with pytest.raises((r.ReviewError, ValueError)):
        store(tmp_path).consume(r.request('A3'), timestamp)


def test_negative_duplicate_JSON_keys_are_not_silently_accepted():
    with pytest.raises(r.ReviewError, match='DUPLICATE_JSON_KEY'):
        json.loads('{"key":1,"key":2}', object_pairs_hook=r.no_duplicate_keys)


def test_local_request_schema_rejects_scope_and_method_expansion():
    schema = json.loads((OUT/'REQUEST_SCHEMA.json').read_bytes())
    Draft202012Validator.check_schema(schema); validator = Draft202012Validator(schema)
    for target in r.TARGETS: assert not list(validator.iter_errors(r.request(target)))
    x = r.request('A3'); x['method'] = 'HEAD'
    assert list(validator.iter_errors(x))
    x = r.request('A3'); x['unknown_extension'] = True
    assert list(validator.iter_errors(x))


def test_actual_UNKNOWN_precheck_has_no_transport_and_no_consumed_real_attempts():
    pre = json.loads((OUT/'FETCH_PRECHECK.json').read_bytes())
    ledger = json.loads((OUT/'FETCH_ATTEMPT_LEDGER.json').read_bytes())
    assert pre['gate'] == 'NN_V2_2_5R_FETCH_BLOCKED'
    assert pre['checks']['robots_freshness_basis'] == 'UNKNOWN'
    assert pre['checks']['operational_write_boundary'] == 'UNKNOWN'
    with pytest.raises(r.ReviewError, match='PRE_SEND_HOLD'): r.require_live_preconditions(pre['checks'])
    assert ledger['actual_attempts'] == [] and ledger['consumed_attempt_count'] == 0
    for row in ledger['planned_targets']:
        assert row['state'] == 'NOT_ATTEMPTED_BLOCKED' and not row['transport_called']
    evidence = json.loads((OUT/'FETCH_EVIDENCE.json').read_bytes())
    assert all(row['HTTP_status'] is None and row['bytes'] == 0 and row['raw_SHA256'] is None
               for row in evidence['rows'])


def test_no_network_model_process_policy_or_live_execution_imports():
    tree = ast.parse((OUT/'offline_review.py').read_text(encoding='utf8'))
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imports <= {'datetime', 'hashlib', 'pathlib', 'json', 'os'}
    assert not any(isinstance(n, ast.Name) and n.id in {'exec', 'eval', '__import__', 'socket', 'requests', 'subprocess'} for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Attribute) and n.attr in {'connect', 'request', 'urlopen', 'start', 'fit', 'predict'} for n in ast.walk(tree))
