"""Pure, synthetic-only UA evidence contract. No client/transport/permit API.

Canonical JSON identifies reviewed inputs; it is not HTTP wire serialization,
a signature, a proof of truthful callers, or a historical transmission record.
E4 never implies E3. E2 start never implies completion. All E2/E3 inputs here
are fixtures; actual transmission and independent observation remain unproven.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import PurePosixPath
import re
from urllib.parse import urlsplit

from research.nn_v2.phase2_5K import product_token_groups as robots

UA = 'J1AI-Research-Timing-Pilot/1.0'
TOKEN = 'Research-Timing-Pilot'
STATE = 'CANDIDATE_FROZEN_NOT_ACTIVATED'
CONFIG_REVISION = 'NNV2_L_UA_CANDIDATE_V1'
SCHEMA_VERSION = 'NNV2_UA_EVIDENCE_V1'
PREPARED_VERSION = 'NNV2_UA_PREPARED_V1'
SCOPE = 'SYNTHETIC_ONLY'
LEVELS = ('E0', 'E1', 'E2', 'E3', 'E4')
HEADER_NAMES = frozenset({'user-agent', 'host', 'accept', 'accept-encoding', 'connection', 'x-j1ai-request-id'})
FIELDS = frozenset({'schema_version', 'scope', 'simulated', 'retroactive', 'run_started_utc',
    'request_id', 'execution_id', 'permit_id', 'source_revision', 'target_url', 'method',
    'intended_user_agent', 'product_token', 'header_configuration_hash', 'prepared_request_hash',
    'transport_adapter_identity', 'evidence_level', 'timestamp_utc', 'timestamp_source',
    'transport_outcome', 'response_status', 'response_hash', 'storage_identity', 'readback_verified',
    'failure_reason', 'evidence_payload', 'record_hash'})
IDENTITY_FIELDS = ('request_id', 'execution_id', 'permit_id', 'source_revision')


class ContractError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise ContractError(reason)


def canonical_bytes(value):
    """JSON sorted keys, compact separators, ASCII escapes, LF; no NaN."""
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode('ascii')


def hash_json(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def candidate():
    return dict(configuration_revision=CONFIG_REVISION, intended_user_agent=UA,
                product_token=TOKEN, state=STATE, activated=False)


def configuration_hash():
    return hash_json(candidate())


def utc(value):
    need(type(value) is str and 'T' in value, 'UTC_REQUIRED')
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ContractError('UTC_REQUIRED') from exc
    need(stamp.utcoffset() == timezone.utc.utcoffset(stamp), 'UTC_REQUIRED')
    return stamp


def identity(value):
    need(type(value) is str and re.fullmatch(r'syn-[A-Za-z0-9_-]{1,80}', value) is not None, 'SYNTHETIC_ID_REQUIRED')


def digest(value):
    need(type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None, 'SHA256_REQUIRED')


def adapter_binding(actual, expected):
    need(type(expected) is dict and set(expected) == {'identity', 'revision', 'code_sha256'}, 'ADAPTER_SCHEMA')
    identity(expected['identity']);identity(expected['revision']);digest(expected['code_sha256'])
    need(actual == expected, 'ADAPTER_BINDING')


def canonical_url(value):
    """Exact synthetic URL, no normalization of escapes/query order/port spelling."""
    need(type(value) is str and value.isascii() and 0 < len(value) <= 2048 and
         not re.search(r'[\x00-\x20\x7f\\#]', value), 'UNSAFE_URL')
    for match in re.finditer('%', value):
        part = value[match.start()+1:match.start()+3]
        need(re.fullmatch('[0-9a-fA-F]{2}', part) is not None, 'URL_PERCENT_ENCODING')
        need(int(part, 16) > 32 and int(part, 16) != 127, 'URL_ENCODED_CONTROL')
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ContractError('UNSAFE_URL') from exc
    need(parsed.scheme == 'https' and parsed.netloc in {'synthetic.invalid', 'synthetic.invalid:443'}
         and port in (None, 443) and not parsed.username and not parsed.password, 'SYNTHETIC_HTTPS_ORIGIN_REQUIRED')
    # Conservative secret-bearing query names are not admitted to an evidence
    # record. This is an allowlist, not a claim of general secret detection.
    if parsed.query:
        need(all(re.fullmatch(r'(a|b|q|lang|year)=[A-Za-z0-9._~%+-]*', x) for x in parsed.query.split('&')),
             'UNREVIEWED_OR_SENSITIVE_QUERY')
    need(not any(x in {'.', '..'} for x in re.sub('%2[eE]', '.', parsed.path).split('/')), 'DOT_SEGMENT')
    return dict(literal=value, scheme='https', host='synthetic.invalid', port=443,
                explicit_port=port, path=parsed.path or '/', query=parsed.query)


def prepare(*, method, target_url, headers, request_id, execution_id, permit_id, source_revision,
            intended_user_agent=UA, product_token=TOKEN):
    """Construct reviewed *input evidence* only, not an HTTP request object."""
    need(method == 'GET', 'EXACT_GET_REQUIRED')
    need(intended_user_agent == UA and product_token == TOKEN, 'FROZEN_UA_TOKEN_MISMATCH')
    need(re.fullmatch('[A-Za-z_-]+', product_token) is not None and product_token in intended_user_agent, 'TOKEN_BINDING')
    ids = dict(request_id=request_id, execution_id=execution_id, permit_id=permit_id, source_revision=source_revision)
    for v in ids.values():
        identity(v)
    url = canonical_url(target_url)
    need(type(headers) in (list, tuple) and 1 <= len(headers) <= 6, 'HEADER_PAIRS_REQUIRED')
    collected = {}
    for pair in headers:
        need(type(pair) in (list, tuple) and len(pair) == 2, 'HEADER_PAIR')
        name, value = pair
        need(type(name) is str and re.fullmatch(r'[A-Za-z0-9-]+', name) is not None, 'HEADER_NAME')
        name = name.lower()
        need(name in HEADER_NAMES, 'SECRET_OR_UNREVIEWED_HEADER_FORBIDDEN')
        need(name not in collected, 'DUPLICATE_HEADER')
        need(type(value) is str and 0 < len(value) <= 1024 and value == value.strip(' ') and
             all(32 <= ord(c) < 127 for c in value), 'HEADER_VALUE_OR_CRLF')
        collected[name] = value
    need(collected.get('user-agent') == UA, 'MISSING_OR_CHANGED_USER_AGENT')
    need(collected.get('host') == urlsplit(target_url).netloc, 'HOST_HEADER_MISMATCH')
    need(collected.get('x-j1ai-request-id') == request_id, 'REQUEST_ID_HEADER_MISMATCH')
    body = dict(schema_version=PREPARED_VERSION, method=method, target_url=target_url, URL=url,
                headers=sorted([list(x) for x in collected.items()]), **ids,
                intended_user_agent=UA, product_token=TOKEN, header_configuration_hash=configuration_hash())
    return dict(canonical=body, sha256=hash_json(body))


def verify_prepared(value):
    need(type(value) is dict and set(value) == {'canonical', 'sha256'} and type(value['canonical']) is dict, 'PREPARED_SCHEMA')
    body = value['canonical']
    need(set(body) == {'schema_version', 'method', 'target_url', 'URL', 'headers', *IDENTITY_FIELDS,
                      'intended_user_agent', 'product_token', 'header_configuration_hash'}, 'PREPARED_FIELDS')
    rebuilt = prepare(**{x: body[x] for x in ['method', 'target_url', 'headers', *IDENTITY_FIELDS,
                                             'intended_user_agent', 'product_token']})
    need(value == rebuilt, 'PREPARED_HASH_OR_REPRESENTATION_MISMATCH')
    return body


def check_plan(prepared, plan, now_utc):
    """Validate synthetic plan input, never issue, consume or accept a real permit."""
    result = dict(decision='UNAPPROVED', reason='NO_PERMIT', execution_authorized=False, permit_issued=False)
    if plan is None:
        return result
    try:
        body = verify_prepared(prepared)
        keys = {'kind', 'scope', 'approved_for_simulation', *IDENTITY_FIELDS, 'target_url', 'method',
                'user_agent', 'product_token', 'header_configuration_hash', 'max_requests', 'attempts_used',
                'issued_utc', 'expires_utc', 'redirect', 'retry', 'parallel', 'body_cap', 'destination'}
        need(type(plan) is dict and set(plan) == keys, 'PLAN_SCHEMA')
        need(plan['kind'] == 'SYNTHETIC_UA_PLAN_V1' and plan['scope'] == SCOPE and
             plan['approved_for_simulation'] is True, 'NO_REAL_PERMIT_SUPPORTED')
        for name in [*IDENTITY_FIELDS, 'target_url', 'method', 'product_token', 'header_configuration_hash']:
            need(plan[name] == body[name], 'PLAN_'+name.upper())
        need(plan['user_agent'] == body['intended_user_agent'], 'PLAN_USER_AGENT')
        need(type(plan['max_requests']) is int and plan['max_requests'] == 1 and
             type(plan['attempts_used']) is int and plan['attempts_used'] == 0, 'BUDGET_ALREADY_USED_OR_INVALID')
        need(all(type(plan[x]) is int and plan[x] == 0 for x in ['redirect', 'retry', 'parallel']), 'TRANSPORT_LIMITS')
        need(type(plan['body_cap']) is int and 0 < plan['body_cap'] <= 65536, 'BODY_CAP')
        need(utc(plan['issued_utc']) <= utc(now_utc) < utc(plan['expires_utc']), 'PLAN_TIME')
        dest = plan['destination']
        need(type(dest) is str and '\\' not in dest and ':' not in dest and
             re.fullmatch(r'sandbox/[A-Za-z0-9_./-]+', dest) is not None and
             '..' not in PurePosixPath(dest).parts, 'SYNTHETIC_DESTINATION')
        result.update(decision='ALLOW', reason='SYNTHETIC_PLAN_MATCH_ONLY')
    except (ContractError, ValueError, TypeError, KeyError) as exc:
        result.update(decision='DENY', reason=str(exc))
    return result


def verify_record(record, prepared, *, expected_adapter=None, response_bytes=None, readback_bytes=None):
    """Check a synthetic evidence claim, not its real-world provenance."""
    body = verify_prepared(prepared)
    need(type(record) is dict and set(record) == FIELDS, 'RECORD_SCHEMA')
    need(record['schema_version'] == SCHEMA_VERSION and record['scope'] == SCOPE and
         record['simulated'] is True and record['retroactive'] is False, 'NO_REAL_OR_RETROSPECTIVE_EVIDENCE')
    for name in [*IDENTITY_FIELDS, 'target_url', 'method', 'intended_user_agent', 'product_token', 'header_configuration_hash']:
        need(record[name] == body[name], 'RECORD_'+name.upper())
    digest(record['record_hash'])
    need(hash_json({n: v for n, v in record.items() if n != 'record_hash'}) == record['record_hash'], 'RECORD_HASH_MISMATCH')
    need(record['timestamp_source'] == 'SYNTHETIC_CLOCK' and
         utc(record['run_started_utc']) <= utc(record['timestamp_utc']), 'CLOCK_SOURCE_OR_ROLLBACK')
    level = record['evidence_level']
    need(level in LEVELS, 'EVIDENCE_LEVEL')
    if record['prepared_request_hash'] is not None:
        digest(record['prepared_request_hash'])
    need(record['response_status'] is None or type(record['response_status']) is int, 'RESPONSE_STATUS_TYPE')
    need(record['readback_verified'] is None or type(record['readback_verified']) is bool, 'READBACK_TYPE')
    nullable = ['prepared_request_hash', 'transport_adapter_identity', 'transport_outcome', 'response_status',
                'response_hash', 'storage_identity', 'readback_verified', 'failure_reason']
    payload = record['evidence_payload']
    need(type(payload) is dict, 'PAYLOAD_SCHEMA')
    result = dict(level=level, status='CONSISTENT_SYNTHETIC_CLAIM', stop_required=False,
                  actual_transmission_proven=False, actual_independent_observation_proven=False,
                  actual_User_Agent='UNKNOWN', actual_evidence_level='UNKNOWN', simulated=True)
    allowed = set()
    if level == 'E0':
        need(payload == {'configuration_revision': CONFIG_REVISION, 'state': STATE}, 'E0_CONFIGURATION')
    elif level == 'E1':
        allowed = {'prepared_request_hash'}
        need(set(payload) == {'prepared_request'} and payload['prepared_request'] == prepared, 'E1_INPUT_BINDING')
        need(record['prepared_request_hash'] == prepared['sha256'], 'E1_PREPARED_HASH')
    elif level == 'E2':
        allowed = {'prepared_request_hash', 'transport_adapter_identity', 'transport_outcome', 'failure_reason'}
        need(set(payload) == {'events', 'final_request'}, 'E2_PAYLOAD')
        adapter_binding(record['transport_adapter_identity'], expected_adapter)
        verify_prepared(payload['final_request'])
        need(payload['final_request'] == prepared and record['prepared_request_hash'] == prepared['sha256'], 'CLIENT_MUTATED_FINAL_HEADERS')
        events = payload['events']
        need(type(events) is list and 1 <= len(events) <= 2 and
             all(type(x) is dict and set(x) == {'event', 'timestamp_utc'} for x in events), 'TRANSPORT_EVENTS_REQUIRED')
        need(events[0]['event'] == 'SEND_STARTED', 'SEND_START_REQUIRED')
        stamps = [utc(x['timestamp_utc']) for x in events]
        need(utc(record['run_started_utc']) <= stamps[0] and stamps == sorted(stamps) and
             stamps[-1] == utc(record['timestamp_utc']), 'TRANSPORT_EVENT_ORDER')
        outcome = record['transport_outcome']
        need(outcome in {'STARTED', 'COMPLETED', 'FAILED', 'UNKNOWN'}, 'TRANSPORT_OUTCOME')
        if outcome in {'STARTED', 'UNKNOWN'}:
            need(len(events) == 1 and record['failure_reason'] is None, 'START_ONLY_NOT_COMPLETE')
            result['status'] = 'INCOMPLETE'
        else:
            need(len(events) == 2 and events[1]['event'] == ('SEND_COMPLETED' if outcome == 'COMPLETED' else 'SEND_FAILED'), 'TRANSPORT_COMPLETION_REQUIRED')
            if outcome == 'FAILED':
                need(record['failure_reason'] in {'TRANSPORT_TIMEOUT', 'TRANSPORT_ERROR', 'CANCELLED'}, 'FAILURE_REASON')
                result.update(status='CONSISTENT_FAILURE', stop_required=True)
            else:
                need(record['failure_reason'] is None, 'COMPLETED_WITH_ERROR')
    elif level == 'E3':
        allowed = {'prepared_request_hash', 'transport_adapter_identity'}
        need(set(payload) == {'observation_method', 'observer_identity', 'observed_request', 'observed_utc', 'observation_hash'}, 'E3_PAYLOAD')
        need(payload['observation_method'] == 'SYNTHETIC_INDEPENDENT_OBSERVER', 'NO_VALIDATED_REAL_OBSERVATION_METHOD')
        identity(payload['observer_identity'])
        adapter_binding(record['transport_adapter_identity'], expected_adapter)
        need(payload['observer_identity'] != expected_adapter['identity'], 'INDEPENDENT_OBSERVER_BINDING')
        need(payload['observed_request'] == prepared and record['prepared_request_hash'] == prepared['sha256'], 'OBSERVED_REQUEST_BINDING')
        need(utc(record['run_started_utc']) <= utc(payload['observed_utc']) <= utc(record['timestamp_utc']), 'OBSERVATION_TIME')
        need(payload['observation_hash'] == hash_json({n: v for n, v in payload.items() if n != 'observation_hash'}), 'OBSERVATION_HASH')
    elif level == 'E4':
        allowed = {'response_status', 'response_hash', 'storage_identity', 'readback_verified', 'failure_reason'}
        need(set(payload) == {'response_metadata', 'readback_hash', 'response_received_utc', 'storage_verified_utc'}, 'E4_PAYLOAD')
        received = utc(payload['response_received_utc'])
        need(utc(record['run_started_utc']) <= received <= utc(record['timestamp_utc']), 'RESPONSE_TIME')
        meta = payload['response_metadata']
        need(type(meta) is dict and set(meta) == {'request_id', 'status', 'content_type', 'bytes'}, 'RESPONSE_METADATA')
        need(meta['request_id'] == body['request_id'] and type(meta['status']) is int and
             100 <= meta['status'] <= 599 and meta['status'] == record['response_status'], 'RESPONSE_BINDING')
        need(meta['content_type'] in {'text/plain', 'text/html', 'application/octet-stream'}, 'CONTENT_TYPE')
        need(type(response_bytes) is bytes and len(response_bytes) <= 65536 and
             type(meta['bytes']) is int and len(response_bytes) == meta['bytes'], 'RESPONSE_BYTES_REQUIRED')
        need(record['response_hash'] == hashlib.sha256(response_bytes).hexdigest(), 'RESPONSE_HASH')
        storage = record['storage_identity']
        need(type(storage) is dict and set(storage) == {'namespace', 'object_id'} and
             storage['namespace'] == 'SYNTHETIC_MEMORY', 'STORAGE_IDENTITY')
        identity(storage['object_id'])
        need(type(record['readback_verified']) is bool, 'READBACK_STATE')
        if record['readback_verified']:
            need(type(readback_bytes) is bytes and response_bytes == readback_bytes and
                 payload['readback_hash'] == hashlib.sha256(readback_bytes).hexdigest(), 'READBACK_MISMATCH')
            need(received <= utc(payload['storage_verified_utc']) <= utc(record['timestamp_utc']), 'STORAGE_TIME')
        else:
            need(payload['readback_hash'] is None and payload['storage_verified_utc'] is None and
                 record['failure_reason'] == 'STORAGE_READBACK_FAILED', 'INCOMPLETE_STORAGE_EVIDENCE')
            result.update(status='INCOMPLETE', stop_required=True)
        if record['response_status'] != 200:
            need(record['failure_reason'] == 'HTTP_FAILURE', 'HTTP_FAILURE_REASON')
            result.update(status='CONSISTENT_FAILURE', stop_required=True)
        elif record['readback_verified']:
            need(record['failure_reason'] is None, 'SAVED_WITH_ERROR')
    need(all(record[n] is None for n in nullable if n not in allowed), 'CROSS_LEVEL_PROMOTION_OR_UNKNOWN_NOT_NULL')
    return result


def evaluate_chain(records, prepared, **evidence_inputs):
    """No monotone E0->E4 inference. Missing facets remain explicit UNKNOWN."""
    result = dict(decision='UNKNOWN', present_levels=[], missing_levels=list(LEVELS),
                  statuses=[], actual_User_Agent='UNKNOWN', execution_authorized=False, history_admission=False)
    try:
        need(type(records) is list and len(records) <= 5, 'CHAIN_SCHEMA')
        seen = set(); by_level = {}; last = None; start = None
        for record in records:
            verified = verify_record(record, prepared, **evidence_inputs)
            level = verified['level'];need(level not in seen, 'DUPLICATE_EVIDENCE_LEVEL')
            stamp = utc(record['timestamp_utc'])
            need(last is None or stamp >= last, 'CHAIN_CLOCK_ROLLBACK')
            need(start is None or start == record['run_started_utc'], 'EXECUTION_START_MISMATCH')
            seen.add(level);by_level[level]=record;last=stamp;start=record['run_started_utc']
            result['statuses'].append(verified)
        # Facets are independent, but a complete chain must have a plausible
        # request -> send -> response/storage chronology. Record order alone
        # cannot detect a response that predates its request.
        if 'E2' in by_level:
            sent = by_level['E2'];events=sent['evidence_payload']['events']
            send_start=utc(events[0]['timestamp_utc'])
            if 'E1' in by_level:
                need(utc(by_level['E1']['timestamp_utc']) <= send_start, 'PREPARATION_AFTER_SEND_START')
            if 'E3' in by_level:
                need(send_start <= utc(by_level['E3']['evidence_payload']['observed_utc']), 'OBSERVATION_BEFORE_SEND_START')
            if 'E4' in by_level:
                saved=by_level['E4']['evidence_payload']
                need(send_start <= utc(saved['response_received_utc']), 'RESPONSE_BEFORE_SEND_START')
                if sent['transport_outcome']=='COMPLETED' and saved['storage_verified_utc'] is not None:
                    need(utc(events[-1]['timestamp_utc']) <= utc(saved['storage_verified_utc']), 'STORAGE_BEFORE_SEND_COMPLETION')
        if 'E3' in by_level and 'E4' in by_level:
            need(utc(by_level['E3']['evidence_payload']['observed_utc']) <=
                 utc(by_level['E4']['evidence_payload']['response_received_utc']), 'REQUEST_OBSERVATION_AFTER_RESPONSE')
        result.update(present_levels=[x for x in LEVELS if x in seen], missing_levels=[x for x in LEVELS if x not in seen])
        if any(x['stop_required'] for x in result['statuses']):
            result.update(decision='DENY', reason='STOP_EVIDENCE')
        elif not result['missing_levels'] and all(x['status'] == 'CONSISTENT_SYNTHETIC_CLAIM' for x in result['statuses']):
            result.update(decision='ALLOW', reason='ALL_SYNTHETIC_FACETS_CONSISTENT_NOT_REAL_PROOF')
        else:
            result['reason'] = 'MISSING_OR_INCOMPLETE_EVIDENCE'
    except (ContractError, TypeError, ValueError, KeyError) as exc:
        result.update(decision='DENY', reason=str(exc))
    return result


def evaluate_layers(raw, prepared, records, plan, *, now_utc, expected_raw_hash,
                    specification_hashes, **evidence_inputs):
    """Recompute all three layers against the same synthetic request binding.

    No bare caller-supplied ALLOW summary or old real permit is accepted.
    The logical ALLOW branch exists only for complete *synthetic* evidence.
    Future real transport qualification and approval are separate gates.
    """
    try:
        body = verify_prepared(prepared)
        normative = robots.evaluate(raw, source_host='synthetic.invalid', target_url=body['target_url'],
            header=body['intended_user_agent'], declared_tokens=[body['product_token']],
            expected_raw_SHA256=expected_raw_hash, specification_SHA256=specification_hashes,
            profile=robots.subset.SYNTHETIC_PROFILE)['layer1']
        evidence = evaluate_chain(records, prepared, **evidence_inputs)
        permit = check_plan(prepared, plan, now_utc)
    except (ContractError, TypeError, ValueError, KeyError) as exc:
        normative = dict(decision='UNKNOWN', safety_stop=True, reason='INVALID_REQUEST_BINDING')
        evidence = dict(decision='DENY', reason=str(exc))
        permit = dict(decision='DENY', reason='INVALID_REQUEST_BINDING')
    allowed = all(x['decision'] == 'ALLOW' for x in [normative, evidence, permit]) and normative['safety_stop'] is False
    return dict(layer1=normative, layer2=evidence, layer3=permit,
                decision='ALLOW' if allowed else 'UNKNOWN', communication_candidate=allowed,
                scope=SCOPE, execution_authorized=False, B_authorized=False, history_admission=False,
                real_transmission_proven=False, permit_issued=False)
