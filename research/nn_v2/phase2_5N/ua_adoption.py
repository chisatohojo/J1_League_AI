"""G1 research identity adoption only: pure values, no I/O or capabilities.

This separate decision record is NOT an NNV2_UA_EVIDENCE_V1 request record.
Hashes bind reviewed bytes; they are neither signatures nor transmission proof.
No adapter, client, permit issuer, operational configuration or clock is loaded.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json

HTTP_USER_AGENT = 'J1AI-Research-Timing-Pilot/1.0'
ROBOTS_PRODUCT_TOKEN = 'Research-Timing-Pilot'
STATE = 'G1_ADOPTED_OFFLINE_ONLY'
SCHEMA_VERSION = 'NNV2_G1_UA_ADOPTION_V1'
EVIDENCE_VERSION = 'NNV2_G1_UA_ADOPTION_EVIDENCE_V1'
SCOPE = 'NN_V2_RESEARCH_IDENTITY_ONLY'
DECISION_SHA256 = '3423d2106f2d34c229d37d35d3ec4ff026ad46054044aaf5e14d55fa37afa171'
BASE_COMMIT = 'ce39d7e3f868b33a14d657f433feeeafc96a5c87'
CANDIDATE_SHA256 = 'abab599fdf54b2fc0e88e5bb62b3e261ecf1bb8fc326afca9c26417991a3f0af'
MATRIX_SHA256 = '70a6d7a97fa84f865a5a634909cfe3e5f8d35c8dc2f19dbc4e95fa994fba8c87'
PRIOR_PINS = (
    ('research/nn_v2/phase2_5L/USER_AGENT_CANDIDATE.json', CANDIDATE_SHA256),
    ('research/nn_v2/phase2_5L/REQUEST_EVIDENCE_SCHEMA.json',
     'c643688edd9bca0da25d35dc5808cf81145fba87f0e5dbada231e4f8e898c6c5'),
    ('research/nn_v2/phase2_5M/URL_STOP_MATRIX.json', MATRIX_SHA256),
    ('research/nn_v2/phase2_5M/UNKNOWN_IMPACT_MATRIX.json',
     'd1b95cb8c2ea693838070bb33f19cb8f319e624f323c332d57fdfaaced34a2a0'),
    ('research/nn_v2/phase2_5M/APPROVAL_GATES.json',
     '879475141495d59c46149a588b0aa966696100dd6e785ba15caa05e581602d92'),
)
UNKNOWN_IDS = ('agent_grammar', 'rule_grammar', 'longest_rule', 'reserved_octets',
               'query', 'encoding_errors', 'parse_limits', 'standard_examples', 'sealed_A1_replay')
EXCLUDED = ('Champion_A', 'Weekend_Batch', 'GUI', 'scheduled_workers',
            'operational_configuration', 'live_transport', 'permit_issuance')


class AdoptionError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise AdoptionError(reason)


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('ascii')


def sha(body):
    need(type(body) is bytes, 'EXACT_BYTES_REQUIRED')
    return hashlib.sha256(body).hexdigest()


def utc(value):
    need(type(value) is str and value.endswith('+00:00') and 'T' in value, 'UTC_REQUIRED')
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AdoptionError('UTC_REQUIRED') from exc
    need(stamp.utcoffset() == timedelta(0), 'UTC_REQUIRED')
    return stamp


def strict_json(body):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def nonfinite(_):
        raise AdoptionError('NONFINITE_JSON')
    need(type(body) is bytes, 'EXACT_BYTES_REQUIRED')
    try:
        return json.loads(body, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, UnicodeError) as exc:
        raise AdoptionError('INVALID_JSON') from exc


def make_manifest(adopted_utc):
    """Build an offline decision value; caller must supply and verify actual UTC."""
    stamp = utc(adopted_utc)
    need(stamp.astimezone(timezone(timedelta(hours=9))).date().isoformat() == '2026-10-24',
         'ADOPTION_DECISION_DATE')
    return dict(
        schema_version=SCHEMA_VERSION, adoption_state=STATE, scope=SCOPE,
        HTTP_USER_AGENT=HTTP_USER_AGENT, ROBOTS_PRODUCT_TOKEN=ROBOTS_PRODUCT_TOKEN,
        adopted_utc=adopted_utc, adoption_date_JST='2026-10-24',
        decision_source=dict(kind='EXPLICIT_USER_G1_INSTRUCTION', SHA256=DECISION_SHA256),
        base_commit=BASE_COMMIT, prior_evidence_SHA256=dict(PRIOR_PINS),
        previous_state='CANDIDATE_FROZEN_NOT_ACTIVATED',
        legacy_request_schema='NNV2_UA_EVIDENCE_V1',
        applicable_phases='Future separately approved NN v2 limited research acquisition planning',
        excluded_scopes=list(EXCLUDED),
        comparison_policy='Exact ASCII bytes; no trim, case fold, extraction or normalization',
        robots_group_matching='Existing K parser case-insensitive group comparison unchanged',
        roles=dict(HTTP_USER_AGENT='Intended HTTP User-Agent header value only',
                   ROBOTS_PRODUCT_TOKEN='Explicit robots group-selection identifier only'),
        change_policy='Any value, role, scope or state change requires separate review and approval',
        unresolved_normative_ids=list(UNKNOWN_IDS), normative_counts=dict(PASS=15, FAIL=0, UNKNOWN=9),
        authorities=dict(G1_adopted=True, G2_connected=False, G3_permit_issued=False,
                         G4_execution_authorized=False, current_requests=0),
        history_admission=False, B='HOLD', C='HOLD', D='HOLD', HISTORY='HOLD', PREDICTION='HOLD',
        Phase_A='BLOCKED', Phase_B='NOT_AUTHORIZED',
        G2_prerequisites=['Separate explicit offline adapter qualification approval',
            'Pinned code/config and final-header E0/E1 capture; no implicit collector',
            'Attempt charging, finite limits, ownership, storage and STOP tests with mocks',
            'Host-specific access conditions, freshness and bounded bootstrap review',
            'E2/E4 capture qualification; explicit E3 requirement/method/privacy review',
            'No live transport or new permit until separately approved G3/G4'])


def verify_manifest(value, *, candidate_bytes, verified_at_utc):
    need(sha(candidate_bytes) == CANDIDATE_SHA256, 'FROZEN_CANDIDATE_CHANGED')
    candidate = strict_json(candidate_bytes)['candidate']
    need(candidate['intended_user_agent'] == HTTP_USER_AGENT and
         candidate['product_token'] == ROBOTS_PRODUCT_TOKEN and
         candidate['state'] == 'CANDIDATE_FROZEN_NOT_ACTIVATED' and
         candidate['activated'] is False, 'CANDIDATE_IDENTITY_OR_STATE')
    need(type(value) is dict and type(value.get('adopted_utc')) is str, 'MANIFEST_SCHEMA')
    expected = make_manifest(value['adopted_utc'])
    need(canonical(value) == canonical(expected), 'EXACT_G1_CONTRACT_REQUIRED')
    need(utc(verified_at_utc) >= utc(value['adopted_utc']), 'PRE_ADOPTION_OR_CLOCK_ROLLBACK')
    return dict(adoption_verified=True, execution_authorized=False, adapter_configuration_loaded=False)


def make_evidence(manifest, *, candidate_bytes, matrix_bytes, verified_at_utc):
    verify_manifest(manifest, candidate_bytes=candidate_bytes, verified_at_utc=verified_at_utc)
    need(sha(matrix_bytes) == MATRIX_SHA256, 'M_URL_FIXTURE_CHANGED')
    previous = strict_json(matrix_bytes)
    rows = []
    for row in previous['rows']:
        rows.append(dict(id=row['id'], URL=row['URL'], scheme=row['scheme'], host=row['host'],
            port=row['port'], historical_M_robots=row['robots'],
            related_UNKNOWN_IDs=row['related_UNKNOWN_IDs'],
            G1_identity_adopted=True, actual_outbound_UA='UNKNOWN',
            site_access=row['site_access'], permit_status='UNAPPROVED', current_request_authority=0,
            final_communication=False,
            remaining_STOP_reasons=[x for x in row['direct_STOP_reasons']
                                    if x != 'FORMAL_UA_TOKEN_ADOPTION_NOT_APPROVED']))
    return dict(schema_version=EVIDENCE_VERSION, scope=SCOPE,
        manifest_SHA256=sha(canonical(manifest)), evidence_utc=verified_at_utc,
        facets=dict(
            E0=dict(adopted_constant_proof='VERIFIED_OFFLINE_DECISION_ONLY',
                    actual_adapter_configuration_read='NOT_PERFORMED'),
            E1=dict(status='EXISTING_OFFLINE_DESIGN_ONLY', new_request_prepared=False),
            E2=dict(status='UNKNOWN', performed=False), E3=dict(status='UNKNOWN', performed=False),
            E4=dict(new_acquisition=False, historical_outbound_UA='UNKNOWN', retroactive_attribution=False)),
        URLs=rows, normative_counts=dict(PASS=15, FAIL=0, UNKNOWN=9),
        unresolved_normative_ids=list(UNKNOWN_IDS), fully_resolved_by_G1=[],
        partially_addressed_by_G1=['agent_grammar', 'sealed_A1_replay'],
        actual_adapter_connection=False, permit_issued=False, requests=0, history_admission=False)


def verify_evidence(value, manifest, *, candidate_bytes, matrix_bytes, verified_at_utc):
    need(type(value) is dict and type(value.get('evidence_utc')) is str, 'EVIDENCE_SCHEMA')
    need(utc(verified_at_utc) >= utc(value['evidence_utc']), 'EVIDENCE_FUTURE_OR_CLOCK_ROLLBACK')
    expected = make_evidence(manifest, candidate_bytes=candidate_bytes, matrix_bytes=matrix_bytes,
                             verified_at_utc=value['evidence_utc'])
    need(canonical(value) == canonical(expected), 'NO_PROMOTION_OR_RETROACTIVE_ATTRIBUTION')
    return dict(adoption_verified=True, execution_authorized=False, history_admission=False)
