"""Synthetic dictionaries/bytes only. No HTTP, worker, model or real storage."""
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from research.nn_v2.phase2_5L import ua_evidence_contract as c

T = '2026-10-24T01:00:'
ADAPTER = dict(identity='syn-adapter', revision='syn-adapter-v1', code_sha256='a'*64)
BODY = b'synthetic response'
RAW = b'User-agent: *\nDisallow: /closed\n'


def headers():
    return [['Host', 'synthetic.invalid'], ['User-Agent', c.UA], ['X-J1AI-Request-ID', 'syn-request'],
            ['Accept-Encoding', 'identity'], ['Connection', 'close']]


def prepared(**updates):
    args = dict(method='GET', target_url='https://synthetic.invalid/public', headers=headers(),
                request_id='syn-request', execution_id='syn-execution', permit_id='syn-plan', source_revision='syn-source')
    args.update(updates)
    return c.prepare(**args)


def plan(p=None):
    body = (p or prepared())['canonical']
    return dict(kind='SYNTHETIC_UA_PLAN_V1', scope=c.SCOPE, approved_for_simulation=True,
                **{x: body[x] for x in [*c.IDENTITY_FIELDS, 'target_url', 'method', 'product_token', 'header_configuration_hash']},
                user_agent=c.UA, max_requests=1, attempts_used=0, issued_utc=T+'00+00:00', expires_utc=T+'30+00:00',
                redirect=0, retry=0, parallel=0, body_cap=65536, destination='sandbox/receipts')


def seal(record):
    record['record_hash'] = c.hash_json({n: v for n, v in record.items() if n != 'record_hash'})
    return record


def record(level, p=None):
    p = p or prepared();b = p['canonical']
    r = dict(schema_version=c.SCHEMA_VERSION, scope=c.SCOPE, simulated=True, retroactive=False,
             run_started_utc=T+'00+00:00', **{x: b[x] for x in [*c.IDENTITY_FIELDS, 'target_url', 'method',
                'intended_user_agent', 'product_token', 'header_configuration_hash']},
             prepared_request_hash=None, transport_adapter_identity=None, evidence_level=level,
             timestamp_utc=T+dict(E0='00', E1='01', E2='03', E3='04', E4='05')[level]+'+00:00',
             timestamp_source='SYNTHETIC_CLOCK', transport_outcome=None, response_status=None, response_hash=None,
             storage_identity=None, readback_verified=None, failure_reason=None, evidence_payload={})
    if level == 'E0':
        r['evidence_payload'] = dict(configuration_revision=c.CONFIG_REVISION, state=c.STATE)
    if level == 'E1':
        r.update(prepared_request_hash=p['sha256'], evidence_payload=dict(prepared_request=p))
    if level == 'E2':
        r.update(prepared_request_hash=p['sha256'], transport_adapter_identity=deepcopy(ADAPTER), transport_outcome='COMPLETED',
                 evidence_payload=dict(final_request=p, events=[dict(event='SEND_STARTED', timestamp_utc=T+'02+00:00'),
                                                               dict(event='SEND_COMPLETED', timestamp_utc=T+'03+00:00')]))
    if level == 'E3':
        payload = dict(observation_method='SYNTHETIC_INDEPENDENT_OBSERVER', observer_identity='syn-observer', observed_request=p, observed_utc=T+'04+00:00')
        payload['observation_hash'] = c.hash_json(payload)
        r.update(prepared_request_hash=p['sha256'], transport_adapter_identity=deepcopy(ADAPTER), evidence_payload=payload)
    if level == 'E4':
        r.update(response_status=200, response_hash=hashlib.sha256(BODY).hexdigest(),
                 storage_identity=dict(namespace='SYNTHETIC_MEMORY', object_id='syn-storage'), readback_verified=True,
                 evidence_payload=dict(response_metadata=dict(request_id='syn-request', status=200, content_type='text/plain', bytes=len(BODY)),
                                       readback_hash=hashlib.sha256(BODY).hexdigest(),
                                       response_received_utc=T+'04.500000+00:00', storage_verified_utc=T+'05+00:00'))
    return seal(r)


def evidence_inputs():
    return dict(expected_adapter=ADAPTER, response_bytes=BODY, readback_bytes=BODY)


def chain():
    return [record(x) for x in c.LEVELS]


def layers(records=None, chosen_plan=None, raw=RAW):
    return c.evaluate_layers(raw, prepared(), chain() if records is None else records,
        plan() if chosen_plan is None else chosen_plan, now_utc=T+'10+00:00', expected_raw_hash=hashlib.sha256(raw).hexdigest(),
        specification_hashes=c.robots.subset.SPEC_SHAS, **evidence_inputs())


def test_frozen_candidate_matches_K_without_activation():
    assert c.robots.declared_identity(c.UA, [c.TOKEN])['status'] == 'BOUND_CANDIDATE'
    assert c.candidate()['state'] == 'CANDIDATE_FROZEN_NOT_ACTIVATED'
    assert c.candidate()['activated'] is False
    assert c.configuration_hash() == c.hash_json(c.candidate())


@pytest.mark.parametrize('level', c.LEVELS)
def test_each_facet_is_consistent_synthetic_evidence_not_real_sending(level):
    result = c.verify_record(record(level), prepared(), **evidence_inputs())
    assert result['level'] == level and result['status'] == 'CONSISTENT_SYNTHETIC_CLAIM'
    assert not result['actual_transmission_proven'] and not result['actual_independent_observation_proven']
    assert result['actual_User_Agent'] == result['actual_evidence_level'] == 'UNKNOWN'


@pytest.mark.parametrize('variant', ['header-case', 'header-order', 'json-key-order'])
def test_canonical_hash_reproducibility(variant):
    p = prepared()
    if variant == 'header-case':
        assert prepared(headers=[[n.lower(), v] for n, v in headers()]) == p
    elif variant == 'header-order':
        assert prepared(headers=list(reversed(headers()))) == p
    else:
        assert c.hash_json(dict(reversed(list(p['canonical'].items())))) == p['sha256']
    assert c.canonical_bytes(p['canonical']).endswith(b'\n')
    assert c.canonical_bytes(p['canonical']).isascii()


@pytest.mark.parametrize('left,right', [('/a%2Fb', '/a%2fb'), ('/a%41', '/aA'),
    ('/a?a=1&b=2', '/a?b=2&a=1'), ('/a?q=one+two', '/a?q=one%20two')])
def test_exact_escape_and_query_order_are_not_normalized(left, right):
    # Encoded whitespace is outside this conservative contract, not normalized.
    p = prepared(target_url='https://synthetic.invalid'+left)
    if '%20' in right:
        with pytest.raises(c.ContractError):prepared(target_url='https://synthetic.invalid'+right)
    else:
        assert p['sha256'] != prepared(target_url='https://synthetic.invalid'+right)['sha256']


def test_explicit_port_spelling_and_internal_header_spaces_preserved():
    h = headers();h[0][1] = 'synthetic.invalid:443'
    assert prepared(target_url='https://synthetic.invalid:443/public', headers=h)['sha256'] != prepared()['sha256']
    one = headers()+[['Accept', 'text/plain; q=1']]
    two = headers()+[['Accept', 'text/plain;  q=1']]
    assert prepared(headers=one)['sha256'] != prepared(headers=two)['sha256']


@pytest.mark.parametrize('bad', ['http://synthetic.invalid/x', 'https://www.jleague.jp/robots.txt',
    'https://aboutj.jleague.jp/robots.txt', 'https://synthetic.invalid.evil/x', 'https://u:p@synthetic.invalid/x',
    'https://synthetic.invalid:444/x', 'https://synthetic.invalid/x#fragment', 'https://synthetic.invalid/\r\nx',
    'https://synthetic.invalid/white space', 'https://synthetic.invalid/é', 'https://synthetic.invalid/%',
    'https://synthetic.invalid/%zz', 'https://synthetic.invalid/%0d', 'https://synthetic.invalid/%0A',
    'https://synthetic.invalid/%00', 'https://synthetic.invalid/%7f', 'https://synthetic.invalid/../x',
    'https://synthetic.invalid/%2e/x', 'https://synthetic.invalid/x?token=secret', 'https://synthetic.invalid/x?Authorization=secret'])
def test_negative_URL_origin_encoding_secret_or_injection(bad):
    with pytest.raises(c.ContractError):prepared(target_url=bad)


@pytest.mark.parametrize('name,value', [('User-Agent', ''), ('User-Agent', 'Changed/1'), ('User-Agent', c.UA+' '),
    ('User-Agent', ' '+c.UA), ('User-Agent', c.UA+'\r\nX: y'), ('User-Agent', c.UA+'\t'),
    ('User-Agent', c.UA+'é'), ('Host', 'other.invalid'), ('X-J1AI-Request-ID', 'syn-other'),
    ('Cookie', 'secret'), ('Authorization', 'secret'), ('Proxy-Authorization', 'secret'),
    ('X-API-Key', 'secret'), ('Set-Cookie', 'secret'), ('X-Unknown', 'secret'), ('Bad\r\nName', 'x')])
def test_negative_header_contract_and_secret_exclusion(name, value):
    h = [x for x in headers() if x[0].lower() != name.lower()]+[[name, value]]
    with pytest.raises(c.ContractError) as error:prepared(headers=h)
    assert 'secret' not in str(error.value) and value not in str(error.value) if value == 'secret' else True


@pytest.mark.parametrize('name', ['User-Agent', 'Host', 'X-J1AI-Request-ID'])
def test_negative_missing_required_header(name):
    with pytest.raises(c.ContractError):prepared(headers=[x for x in headers() if x[0] != name])


@pytest.mark.parametrize('name', ['User-Agent', 'USER-AGENT', 'Host', 'host', 'Connection'])
def test_negative_duplicate_header_case_insensitive(name):
    value = next(v for n, v in headers() if n.lower() == name.lower())
    with pytest.raises(c.ContractError):prepared(headers=headers()+[[name, value]])


@pytest.mark.parametrize('field,value', [('method', 'POST'), ('method', 'get'), ('product_token', 'Timing-Pilot'),
    ('product_token', c.UA), ('intended_user_agent', 'Override/1.0'), ('request_id', 'A1'),
    ('execution_id', 'historical-run'), ('permit_id', 'old-G-permit'), ('source_revision', '')])
def test_negative_request_configuration_or_historical_rebinding(field, value):
    with pytest.raises(c.ContractError):prepared(**{field: value})


@pytest.mark.parametrize('field,value', [('kind', 'REAL_PERMIT'), ('scope', 'PRODUCTION'),
    ('approved_for_simulation', False), ('request_id', 'syn-other'), ('execution_id', 'syn-other'),
    ('permit_id', 'syn-other'), ('source_revision', 'syn-changed'), ('target_url', 'https://synthetic.invalid/other'),
    ('method', 'HEAD'), ('user_agent', 'Override/1.0'), ('product_token', 'Other'),
    ('header_configuration_hash', '0'*64), ('max_requests', 2), ('max_requests', True), ('attempts_used', 1),
    ('attempts_used', True), ('redirect', 1), ('retry', 1), ('parallel', 1), ('body_cap', 65537),
    ('expires_utc', T+'09+00:00'), ('expires_utc', T+'10+00:00'), ('issued_utc', T+'11+00:00'),
    ('destination', '../outside'), ('destination', 'sandbox/../outside'), ('destination', 'C:/production')])
def test_negative_plan_exact_binding_budget_expiry_and_no_old_permit(field, value):
    p = plan();p[field] = value
    assert c.check_plan(prepared(), p, T+'10+00:00')['decision'] == 'DENY'


def test_plan_only_simulation_no_issuance_budget_consumption_or_execution():
    p = plan();copy = deepcopy(p)
    result = c.check_plan(prepared(), p, T+'10+00:00')
    assert result['decision'] == 'ALLOW' and not result['permit_issued'] and not result['execution_authorized']
    assert p == copy
    assert c.check_plan(prepared(), None, T+'10+00:00')['decision'] == 'UNAPPROVED'
    assert c.check_plan(prepared(), {'max_GET': 4}, T+'10+00:00')['decision'] == 'DENY'


@pytest.mark.parametrize('level', c.LEVELS)
@pytest.mark.parametrize('field,value', [('request_id', 'syn-wrong'), ('permit_id', 'syn-wrong'),
    ('execution_id', 'syn-wrong'), ('method', 'POST'), ('response_status', 'UNKNOWN'),
    ('source_revision', 'syn-wrong'), ('target_url', 'https://synthetic.invalid/other'),
    ('intended_user_agent', 'Override/1.0'), ('product_token', 'Other'), ('header_configuration_hash', '0'*64),
    ('scope', 'PRODUCTION'), ('simulated', False), ('retroactive', True), ('timestamp_source', 'ACTUAL_UTC'),
    ('timestamp_utc', '2026-10-24'), ('run_started_utc', T+'59+00:00')])
def test_negative_record_binding_even_with_recomputed_hash(level, field, value):
    r = record(level);r[field] = value;seal(r)
    with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())


@pytest.mark.parametrize('level', c.LEVELS)
def test_negative_record_hash_and_incomplete_receipt(level):
    r = record(level);r['record_hash'] = '0'*64
    with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())
    r = record(level);del r['failure_reason'];seal(r)
    with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())


@pytest.mark.parametrize('level', ['E0', 'E1', 'E4'])
def test_negative_cross_level_promotion_and_UNKNOWN_empty_substitution(level):
    for field, value in [('prepared_request_hash', ''), ('transport_outcome', 'COMPLETED'), ('transport_adapter_identity', {})]:
        r = record(level);r[field] = value;seal(r)
        with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())


@pytest.mark.parametrize('outcome', ['STARTED', 'UNKNOWN'])
def test_send_start_only_is_not_send_completion(outcome):
    r = record('E2');r['transport_outcome'] = outcome;r['evidence_payload']['events'] = r['evidence_payload']['events'][:1]
    r['timestamp_utc'] = T+'02+00:00';seal(r)
    assert c.verify_record(r, prepared(), **evidence_inputs())['status'] == 'INCOMPLETE'
    records = chain();records[2] = r
    assert c.evaluate_chain(records, prepared(), **evidence_inputs())['decision'] == 'UNKNOWN'


@pytest.mark.parametrize('mutation', ['no-events', 'missing-start', 'missing-completion', 'reversed-clock', 'wrong-adapter', 'header-added', 'header-changed'])
def test_negative_E2_missing_transport_or_client_header_mutation(mutation):
    r = record('E2');payload = r['evidence_payload']
    if mutation == 'no-events':payload['events'] = []
    elif mutation == 'missing-start':payload['events'][0]['event'] = 'SEND_COMPLETED'
    elif mutation == 'missing-completion':payload['events'] = payload['events'][:1]
    elif mutation == 'reversed-clock':payload['events'][0]['timestamp_utc'] = T+'04+00:00'
    elif mutation == 'wrong-adapter':r['transport_adapter_identity']['revision'] = 'syn-other'
    elif mutation == 'header-added':payload['final_request'] = prepared(headers=headers()+[['Accept', 'text/plain']])
    else:
        h = headers();h[-1][1] = 'keep-alive';payload['final_request'] = prepared(headers=h)
    seal(r)
    with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())


@pytest.mark.parametrize('reason', ['TRANSPORT_TIMEOUT', 'TRANSPORT_ERROR', 'CANCELLED'])
def test_failed_transport_is_preserved_as_STOP_no_automatic_retry(reason):
    r = record('E2');r['transport_outcome'] = 'FAILED';r['failure_reason'] = reason
    r['evidence_payload']['events'][-1]['event'] = 'SEND_FAILED';seal(r)
    records = chain();records[2] = r
    assert c.evaluate_chain(records, prepared(), **evidence_inputs())['decision'] == 'DENY'


@pytest.mark.parametrize('mutation', ['E1-promotion', 'encrypted-pcap', 'same-observer', 'bad-observation-hash', 'wrong-observed-request', 'future-observation'])
def test_negative_E3_independence_and_visibility_not_inferred(mutation):
    r = record('E3');p = r['evidence_payload']
    if mutation == 'E1-promotion':r['evidence_payload'] = record('E1')['evidence_payload']
    elif mutation == 'encrypted-pcap':p['observation_method'] = 'ENCRYPTED_PCAP_ONLY'
    elif mutation == 'same-observer':p['observer_identity'] = ADAPTER['identity']
    elif mutation == 'bad-observation-hash':p['observation_hash'] = '0'*64
    elif mutation == 'wrong-observed-request':p['observed_request'] = prepared(target_url='https://synthetic.invalid/other')
    else:p['observed_utc'] = T+'59+00:00'
    seal(r)
    with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())


def test_E4_response_alone_never_proves_outbound_header_or_E3():
    result = c.evaluate_chain([record('E4')], prepared(), **evidence_inputs())
    assert result['decision'] == 'UNKNOWN' and result['missing_levels'] == ['E0', 'E1', 'E2', 'E3']
    assert result['actual_User_Agent'] == 'UNKNOWN'


@pytest.mark.parametrize('mutation', ['response-SHA', 'readback-SHA', 'request-ID', 'bytes', 'storage', 'status-float', 'extra-secret'])
def test_negative_E4_raw_storage_readback_or_metadata_inconsistency(mutation):
    r = record('E4');p = r['evidence_payload']
    if mutation == 'response-SHA':r['response_hash'] = '0'*64
    elif mutation == 'readback-SHA':p['readback_hash'] = '0'*64
    elif mutation == 'request-ID':p['response_metadata']['request_id'] = 'syn-other'
    elif mutation == 'bytes':p['response_metadata']['bytes'] += 1
    elif mutation == 'storage':r['storage_identity']['namespace'] = 'PRODUCTION'
    elif mutation == 'status-float':r['response_status'] = 200.0
    else:p['response_metadata']['Cookie'] = 'secret'
    seal(r)
    with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())


@pytest.mark.parametrize('status', [403, 429, 500])
def test_saved_error_response_is_not_permission_or_success(status):
    r = record('E4');r['response_status'] = status;r['failure_reason'] = 'HTTP_FAILURE'
    r['evidence_payload']['response_metadata']['status'] = status;seal(r)
    assert c.verify_record(r, prepared(), **evidence_inputs())['stop_required']


def test_incomplete_storage_readback_is_not_success():
    r = record('E4');r['readback_verified'] = False;r['failure_reason'] = 'STORAGE_READBACK_FAILED'
    r['evidence_payload']['readback_hash'] = None;r['evidence_payload']['storage_verified_utc'] = None;seal(r)
    assert c.verify_record(r, prepared(), **evidence_inputs())['status'] == 'INCOMPLETE'
    records = chain();records[-1] = r
    assert c.evaluate_chain(records, prepared(), **evidence_inputs())['decision'] == 'DENY'


@pytest.mark.parametrize('mutation', ['duplicate-request', 'clock-reverse', 'mixed-execution', 'missing-facet', 'fake-summary'])
def test_negative_chain_aggregation_and_no_retrospective_repair(mutation):
    records = chain()
    if mutation == 'duplicate-request':records = [records[0], records[0]]
    elif mutation == 'clock-reverse':records = list(reversed(records))
    elif mutation == 'mixed-execution':records[1]['execution_id'] = 'syn-other';seal(records[1])
    elif mutation == 'missing-facet':records = records[:2]
    else:records = [{'decision':'ALLOW', 'evidence_level':'E3'}]
    assert c.evaluate_chain(records, prepared(), **evidence_inputs())['decision'] != 'ALLOW'


@pytest.mark.parametrize('robots_state,evidence_state,permit_state', list(itertools.product(['ALLOW', 'DENY', 'UNKNOWN'], repeat=3)))
def test_three_layers_require_every_independent_synthetic_condition(robots_state, evidence_state, permit_state):
    raw = {'ALLOW': RAW, 'DENY': b'User-agent: *\nDisallow: /\n', 'UNKNOWN': b'User-agent: *\nDisallow: no-slash\n'}[robots_state]
    records = chain() if evidence_state == 'ALLOW' else chain()[:2]
    if evidence_state == 'DENY':records[0]['record_hash'] = '0'*64
    p = plan() if permit_state == 'ALLOW' else None
    if permit_state == 'DENY':p = plan();p['attempts_used'] = 1
    value = c.evaluate_layers(raw, prepared(), records, p, now_utc=T+'10+00:00',
        expected_raw_hash=hashlib.sha256(raw).hexdigest(), specification_hashes=c.robots.subset.SPEC_SHAS, **evidence_inputs())
    assert value['layer1']['decision'] == robots_state
    assert value['layer2']['decision'] == evidence_state
    assert value['layer3']['decision'] == ('UNAPPROVED' if permit_state == 'UNKNOWN' else permit_state)
    assert value['communication_candidate'] == (robots_state == evidence_state == permit_state == 'ALLOW')
    assert not value['execution_authorized'] and not value['real_transmission_proven'] and not value['permit_issued']


@pytest.mark.parametrize('mutation', ['raw-SHA', 'spec-SHA', 'prepared-SHA'])
def test_negative_layer_integrity_cannot_be_overridden_by_good_evidence(mutation):
    args = dict(now_utc=T+'10+00:00', expected_raw_hash=hashlib.sha256(RAW).hexdigest(), specification_hashes=c.robots.subset.SPEC_SHAS)
    p = prepared()
    if mutation == 'raw-SHA':args['expected_raw_hash'] = '0'*64
    elif mutation == 'spec-SHA':args['specification_hashes'] = {}
    else:p['sha256'] = '0'*64
    assert not c.evaluate_layers(RAW, p, chain(), plan(), **args, **evidence_inputs())['communication_candidate']


def test_json_schema_is_local_and_all_five_synthetic_records_validate():
    schema = json.loads((Path(c.__file__).parent/'REQUEST_EVIDENCE_SCHEMA.json').read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for level in c.LEVELS:
        assert not list(validator.iter_errors(record(level)))
    assert set(schema['required']) == c.FIELDS and schema['additionalProperties'] is False
    assert all(not isinstance(x, str) or not x.startswith('http') for d in schema['$defs'].values() for x in d.values())


@pytest.mark.parametrize('mutation', ['extra-field', 'missing-field', 'empty-unknown', 'E1-as-E3', 'real-scope'])
def test_negative_published_schema_rejects_unknown_or_promoted_records(mutation):
    r = record('E1')
    if mutation == 'extra-field':r['Authorization'] = 'secret'
    elif mutation == 'missing-field':del r['readback_verified']
    elif mutation == 'empty-unknown':r['response_hash'] = ''
    elif mutation == 'E1-as-E3':r['evidence_level'] = 'E3'
    else:r['scope'] = 'PRODUCTION'
    schema = json.loads((Path(c.__file__).parent/'REQUEST_EVIDENCE_SCHEMA.json').read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(r))


@pytest.mark.parametrize('level', c.LEVELS)
def test_one_facet_never_substitutes_for_missing_other_facets(level):
    result = c.evaluate_chain([record(level)], prepared(), **evidence_inputs())
    assert result['decision'] == 'UNKNOWN'
    assert result['present_levels'] == [level]
    assert len(result['missing_levels']) == 4
    assert result['actual_User_Agent'] == 'UNKNOWN'


@pytest.mark.parametrize('level,field', [('E1', 'prepared_request_hash'), ('E2', 'transport_adapter_identity'),
    ('E2', 'transport_outcome'), ('E3', 'prepared_request_hash'), ('E4', 'response_status'), ('E4', 'storage_identity')])
def test_negative_schema_required_facet_evidence_cannot_be_null(level, field):
    r = record(level);r[field] = None;seal(r)
    schema = json.loads((Path(c.__file__).parent/'REQUEST_EVIDENCE_SCHEMA.json').read_bytes())
    assert list(Draft202012Validator(schema).iter_errors(r))
    with pytest.raises(c.ContractError):c.verify_record(r, prepared(), **evidence_inputs())


def test_no_secret_fields_or_live_transport_imports_in_contract():
    import ast
    tree = ast.parse(Path(c.__file__).read_text(encoding='utf8'))
    assert {x.name for n in ast.walk(tree) if isinstance(n, ast.Import) for x in n.names} == {'hashlib', 'json', 're'}
    assert {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} == {
        'datetime', 'pathlib', 'urllib.parse', 'research.nn_v2.phase2_5K'}
    assert all(x not in c.FIELDS for x in ['Authorization', 'Cookie', 'password', 'raw_body', 'certificate_key'])


@pytest.mark.parametrize('case', ['prepare-after-send', 'observation-before-send', 'response-before-send',
    'storage-before-response', 'observation-after-response', 'storage-after-record', 'storage-before-send-completion'])
def test_negative_cross_facet_times_cannot_be_hidden_by_ordered_receipts(case):
    records = chain()
    if case == 'prepare-after-send':records[1]['timestamp_utc'] = T+'02.500000+00:00'
    elif case == 'observation-before-send':
        p = records[3]['evidence_payload'];p['observed_utc'] = T+'01+00:00'
        p['observation_hash'] = c.hash_json({n:v for n,v in p.items() if n!='observation_hash'})
    elif case == 'response-before-send':records[4]['evidence_payload']['response_received_utc'] = T+'01+00:00'
    elif case == 'storage-before-response':records[4]['evidence_payload']['storage_verified_utc'] = T+'04+00:00'
    elif case == 'observation-after-response':records[4]['evidence_payload']['response_received_utc'] = T+'03.500000+00:00'
    elif case == 'storage-after-record':records[4]['evidence_payload']['storage_verified_utc'] = T+'06+00:00'
    else:
        records[4]['evidence_payload']['response_received_utc'] = T+'02.100000+00:00'
        records[4]['evidence_payload']['storage_verified_utc'] = T+'02.200000+00:00'
        p = records[3]['evidence_payload'];p['observed_utc'] = T+'02+00:00'
        p['observation_hash'] = c.hash_json({n:v for n,v in p.items() if n!='observation_hash'})
    for r in records:seal(r)
    assert c.evaluate_chain(records, prepared(), **evidence_inputs())['decision'] == 'DENY'
