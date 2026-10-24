"""G3 design qualification model, not a permit issuer or storage/transport API.

Only explicitly synthetic cases and caller-supplied memory snapshots. CAS,
hash-chain and crash rules are logical models, NOT real atomic/durable I/O.
All outputs deny real issuance, execution and history admission.
"""
import re
from research.nn_v2.phase2_5O import offline_adapter as g2

VERSION = 'NNV2_G3_SYNTHETIC_REVIEW_V1'
CHECKS = ('G1', 'G2_E1', 'robots', 'terms', 'TLS_policy', 'OS_isolation', 'Job', 'ACL',
          'attempt_durability', 'limits', 'storage', 'source_binding', 'clock',
          'production_separation', 'explicit_user_approval')
P2 = dict(E2='UNKNOWN', E3='UNKNOWN', E4='NOT_ACQUIRED', TLS_handshake='NOT_OBSERVED')
CAPS = dict(A1=65536, A2=65536, A3=1048576, A4=1048576, B1=2097152, B2=2097152)
STATES = {None: ('CREATED',), 'CREATED': ('RESERVED', 'REJECTED', 'ABORTED'),
          'RESERVED': ('STARTED', 'ABORTED', 'UNKNOWN_OUTCOME'),
          'STARTED': ('SENT', 'UNKNOWN_OUTCOME'), 'SENT': ('COMPLETED', 'UNKNOWN_OUTCOME'),
          'COMPLETED': (), 'REJECTED': (), 'ABORTED': (), 'UNKNOWN_OUTCOME': ()}


class ReviewError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise ReviewError(message)


def digest(value):
    need(type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None, 'SHA256_REQUIRED')


def limits(target):
    return dict(max_requests=1, per_URL=1, body_cap=CAPS[target], total_body_cap=CAPS[target],
                header_cap=32768, socket_seconds=10, parent_seconds=12, cleanup_seconds=2,
                global_seconds=120, interval_seconds=5, redirect=0, retry=0, parallel=0)


def assess_synthetic_case(case, now_utc):
    """Even all-PASS fixtures are just candidates; real issuance stays false."""
    out = dict(decision='SYNTHETIC_REVIEW_REJECTED', reasons=[], real_permit_issued=False,
               execution_authorized=False, G4_authorized=False, history_admission=False,
               real_prerequisites_verified=False)
    try:
        fields = {'kind', 'scope', 'fixture_id', 'approver', 'approval_utc', 'start_utc', 'end_utc',
                  'target_id', 'exact_url', 'family', 'method', 'user_agent', 'product_token',
                  'G1_manifest_SHA256', 'source_revision', 'limits', 'storage', 'audit_ledger',
                  'checks', 'P2', 'issued', 'allow_resume'}
        need(type(case) is dict and set(case) == fields, 'CASE_SCHEMA')
        need(case['kind'] == VERSION and case['scope'] == 'SYNTHETIC_ONLY', 'NO_REAL_PERMIT_INPUT')
        for key in ['fixture_id', 'approver']:
            g2.ident(case[key])
        target = case['target_id']
        need(type(target) is str and target in CAPS and case['exact_url'] == g2.m.TARGETS[target], 'EXACT_URL_SCOPE')
        need(case['family'] == ('A_ACCESS_CONDITIONS_ONLY' if target.startswith('A') else 'B_ENTRY_ONLY'), 'A_B_BUDGET_SEPARATION')
        need(case['method'] == 'GET', 'GET_ONLY')
        need(case['user_agent'] == g2.g1.HTTP_USER_AGENT and case['product_token'] == g2.g1.ROBOTS_PRODUCT_TOKEN, 'ADOPTED_IDENTITY')
        need(case['G1_manifest_SHA256'] == g2.G1_FILE_SHA and case['source_revision'] == g2.g1.BASE_COMMIT, 'EVIDENCE_REVISION')
        need(g2.same(case['limits'], limits(target)), 'FIXED_LIMITS')
        need(case['storage'] == 'SYNTHETIC_MEMORY_ONLY' and case['audit_ledger'] == 'SYNTHETIC_HASH_CHAIN_ONLY', 'NO_REAL_STORAGE')
        need(case['issued'] is False and case['allow_resume'] is False, 'NO_ISSUANCE_OR_RESUME')
        need(g2.same(case['P2'], P2), 'POST_SEND_PROOF_NOT_AVAILABLE_PRE_SEND')
        need(g2.g1.utc(case['approval_utc']) <= g2.g1.utc(case['start_utc']) <=
             g2.g1.utc(now_utc) < g2.g1.utc(case['end_utc']), 'WINDOW_OR_CLOCK')
        statuses = case['checks']
        need(type(statuses) is dict and set(statuses) == set(CHECKS) and
             all(type(x) is str and x in {'PASS', 'DENY', 'UNKNOWN'} for x in statuses.values()), 'CHECK_STATES')
        out['reasons'] = [k + ':' + statuses[k] for k in CHECKS if statuses[k] != 'PASS']
        if not out['reasons']:
            out['decision'] = 'SYNTHETIC_REVIEW_CANDIDATE_ONLY'
    except (ValueError, TypeError, KeyError) as exc:
        out['reasons'] = [str(exc)]
    return out


def empty_model():
    return g2.g1.canonical(dict(kind='SYNTHETIC_ATTEMPT_MODEL_V1', scope='SYNTHETIC_MEMORY_ONLY', revision=0, events=[]))


def inspect_model(raw, expected_SHA256):
    need(g2.g1.sha(raw) == expected_SHA256, 'MODEL_READBACK_SHA')
    value = g2.g1.strict_json(raw)
    need(type(value) is dict and set(value) == {'kind', 'scope', 'revision', 'events'} and
         value['kind'] == 'SYNTHETIC_ATTEMPT_MODEL_V1' and value['scope'] == 'SYNTHETIC_MEMORY_ONLY', 'MODEL_SCHEMA')
    need(type(value['revision']) is int and type(value['events']) is list and
         value['revision'] == len(value['events']), 'MODEL_REVISION')
    states, bindings, consumed, reserved_requests = {}, {}, set(), set()
    prior, last = None, None
    fields = {'sequence', 'attempt_id', 'permit_digest', 'request_digest', 'from_state', 'to_state',
              'UTC', 'previous_event_SHA256', 'event_SHA256'}
    for index, event in enumerate(value['events']):
        need(type(event) is dict and set(event) == fields and type(event['sequence']) is int and event['sequence'] == index+1, 'EVENT_SCHEMA')
        g2.ident(event['attempt_id']); digest(event['permit_digest']); digest(event['request_digest'])
        body = {k:v for k,v in event.items() if k != 'event_SHA256'}
        need(g2.g1.sha(g2.g1.canonical(body)) == event['event_SHA256'] and event['previous_event_SHA256'] == prior, 'EVENT_CHAIN')
        stamp = g2.g1.utc(event['UTC'])
        need(last is None or last <= stamp, 'CLOCK_ROLLBACK')
        aid = event['attempt_id']; old = states.get(aid); new = event['to_state']
        need(event['from_state'] == old and new in STATES.get(old, ()), 'ILLEGAL_OR_TERMINAL_TRANSITION')
        pair = (event['permit_digest'], event['request_digest'])
        need(aid not in bindings or bindings[aid] == pair, 'ATTEMPT_BINDING')
        if new == 'RESERVED':
            need(event['permit_digest'] not in consumed, 'PERMIT_ALREADY_CONSUMED')
            need(event['request_digest'] not in reserved_requests, 'REQUEST_ALREADY_RESERVED')
            consumed.add(event['permit_digest'])
            reserved_requests.add(event['request_digest'])
        states[aid] = new; bindings[aid] = pair; prior = event['event_SHA256']; last = stamp
    return value, states, consumed


def model_transition(raw, *, expected_SHA256, expected_revision, attempt_id, permit_digest,
                     request_digest, to_state, at_utc):
    """Pure compare-and-swap MODEL. Caller must not treat it as OS atomicity."""
    value, states, _ = inspect_model(raw, expected_SHA256)
    need(type(expected_revision) is int and value['revision'] == expected_revision, 'CAS_CONFLICT')
    event = dict(sequence=expected_revision+1, attempt_id=attempt_id, permit_digest=permit_digest,
        request_digest=request_digest, from_state=states.get(attempt_id), to_state=to_state,
        UTC=at_utc, previous_event_SHA256=value['events'][-1]['event_SHA256'] if value['events'] else None)
    event['event_SHA256'] = g2.g1.sha(g2.g1.canonical(event))
    value['events'].append(event); value['revision'] += 1
    updated = g2.g1.canonical(value)
    inspect_model(updated, g2.g1.sha(updated))
    return updated


def model_recovery(raw, expected_SHA256):
    _, states, consumed = inspect_model(raw, expected_SHA256)
    pending = [k for k,v in states.items() if v in {'RESERVED','STARTED','SENT'}]
    return dict(status='HOLD_MANUAL_OWNERSHIP_REVIEW' if pending else 'MODEL_TERMINAL_OR_UNRESERVED',
                pending_attempts=pending, consumed_permits=len(consumed), retry_allowed=False,
                automatic_resume=False, storage_durability_proven=False, real_execution_authorized=False)


def verify_synthetic_response(raw, expected_SHA256):
    need(type(raw) is bytes and g2.g1.sha(raw) == expected_SHA256, 'SYNTHETIC_RESPONSE_SHA')
    return dict(status='CONSISTENT_SYNTHETIC_BYTES_ONLY', actual_E2=False, actual_E3=False,
                actual_E4=False, execution_authorized=False)
