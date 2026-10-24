"""Offline evidence consistency checks. No I/O, transport or permit API.

Callers provide bytes and separately pinned digests. A consistent inventory
can be review-ready while every access decision remains HOLD.
"""
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
import re
import json

BASE_COMMIT = 'd57e182521dbf354b41b536a67e27b17440d2950'
USER_AGENT = 'J1AI-Research-Timing-Pilot/1.0'
PRODUCT_TOKEN = 'Research-Timing-Pilot'
TARGETS = {
    'A1': 'https://www.jleague.jp/robots.txt',
    'A2': 'https://aboutj.jleague.jp/robots.txt',
    'A3': 'https://www.jleague.jp/general/kiyaku/',
    'A4': 'https://www.jleague.jp/general/copyright/',
    'B1': 'https://www.jleague.jp/j1/news/',
    'B2': 'https://aboutj.jleague.jp/corporate/pressrelease/',
}
UNKNOWN_IDS = ('agent_grammar', 'rule_grammar', 'longest_rule', 'reserved_octets',
               'query', 'encoding_errors', 'parse_limits', 'standard_examples', 'sealed_A1_replay')
GAP_CLASSES = ('MISSING_ORIGINAL', 'MISSING_PROVENANCE', 'STALE_EVIDENCE',
               'ROBOTS_NORMATIVE_UNKNOWN', 'UA_WIRE_UNKNOWN', 'TERMS_UNKNOWN',
               'SCOPE_UNRESOLVED', 'STORAGE_AUDIT_UNPROVEN', 'INDEPENDENT_OBSERVATION_UNKNOWN')
HOLDS = dict(B='HOLD', C='HOLD', D='HOLD', HISTORY='HOLD', PREDICTION='HOLD',
             Phase_A='BLOCKED', Phase_B='NOT_AUTHORIZED', G3='HOLD', G4='NOT_AUTHORIZED')
OPERATIONS = dict(HTTP=0, DNS=0, socket=0, new_acquisitions=0, transport_connections=0,
                  permits_issued_updated=0, model_operations=0, GUI_changes=0,
                  task_changes=0, policy_changes=0)
RIGHTS = ('applicability', 'research_use', 'automated_access', 'storage', 'processing',
          'redistribution', 'publication', 'commercial_use', 'version', 'robots_relationship')


class EvidenceError(ValueError):
    pass


def need(condition, reason):
    if not condition:
        raise EvidenceError(reason)


def stamp(value):
    need(type(value) is str and ('T' in value), 'UTC_TIMESTAMP_REQUIRED')
    dt = datetime.fromisoformat(value)
    need(dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0, 'UTC_TIMESTAMP_REQUIRED')
    return dt.astimezone(timezone.utc)


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'SHA256_REQUIRED')


def same(a, b):
    # bool is not an integer evidence count.
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def validate_scope(target, url, host):
    need(type(target) is str and target in TARGETS and url == TARGETS[target], 'EXACT_URL_SCOPE')
    parsed = urlsplit(url)
    need(host == parsed.hostname and parsed.scheme == 'https' and parsed.port is None
         and not parsed.query and not parsed.fragment and not parsed.username, 'EXACT_HOST_SCOPE')
    return parsed


def verify_provenance(original, blobs, trusted_pins, now_utc):
    """No filesystem access; blobs and trust anchors must be supplied independently."""
    need(type(original) is dict, 'ORIGINAL_SCHEMA')
    if original['status'] == 'NO_VERIFIED_ORIGINAL':
        need(all(original[k] is None for k in ('location', 'raw_SHA256', 'bytes',
             'acquired_utc', 'saved_utc', 'source_url')), 'ABSENT_ORIGINAL_HAS_NO_CLAIMS')
        need(original['supporting_records'] == [], 'ABSENT_ORIGINAL_HAS_NO_RECORDS')
        return False
    need(original['status'] == 'VERIFIED_SAVED_ORIGINAL', 'ORIGINAL_STATUS')
    need(original['source_url'] in TARGETS.values(), 'ORIGINAL_SOURCE_SCOPE')
    acquired = stamp(original['acquired_utc'])
    need(acquired <= stamp(original['saved_utc']) <= stamp(now_utc), 'ORIGINAL_TIME_ORDER')
    loc = original['location']
    digest(original['raw_SHA256'])
    need(type(original['bytes']) is int and original['bytes'] > 0, 'ORIGINAL_BYTES')
    need(type(loc) is str and loc in trusted_pins and loc in blobs, 'PINNED_ORIGINAL_REQUIRED')
    need(type(blobs[loc]) is bytes and len(blobs[loc]) == original['bytes'] and
         sha256(blobs[loc]).hexdigest() == original['raw_SHA256'] == trusted_pins[loc], 'ORIGINAL_HASH_MISMATCH')
    need(type(original['supporting_records']) is list and
         {x['role'] for x in original['supporting_records']} >= {'metadata', 'request', 'seal'}, 'PROVENANCE_RECORDS_REQUIRED')
    for record in original['supporting_records']:
        path = record['location']; digest(record['SHA256'])
        need(path in blobs and path in trusted_pins and type(blobs[path]) is bytes and
             sha256(blobs[path]).hexdigest() == record['SHA256'] == trusted_pins[path], 'PROVENANCE_HASH_MISMATCH')
    records = {r['role']: r for r in original['supporting_records']}
    need(len(records) == len(original['supporting_records']), 'UNIQUE_PROVENANCE_ROLES')
    metadata = json.loads(blobs[records['metadata']['location']])
    request = json.loads(blobs[records['request']['location']])
    seal = json.loads(blobs[records['seal']['location']])
    need(metadata['requested_url'] == metadata['actual_response_url'] == request['url'] == original['source_url'], 'PROVENANCE_URL_BINDING')
    need(metadata['response_completed_UTC'] == original['acquired_utc'] and
         metadata['snapshot_saved_UTC'] == original['saved_utc'], 'PROVENANCE_TIME_BINDING')
    need(metadata['raw_SHA256'] == seal['raw_SHA256'] == original['raw_SHA256'] and
         metadata['request_SHA256'] == seal['request_SHA256'] == records['request']['SHA256'] and
         seal['metadata_SHA256'] == records['metadata']['SHA256'] and seal['readback'] is True, 'PROVENANCE_SEAL_BINDING')
    return True


def validate_terms(row):
    terms = row['terms']
    need(terms['status'] == 'UNKNOWN' and terms['originals'] == [], 'NO_VERIFIED_TERMS_ORIGINAL')
    need(same(terms['conditions'], dict.fromkeys(RIGHTS, 'UNKNOWN')), 'UNPROVEN_TERMS_RIGHTS')
    need(type(terms['missing_reasons']) is list and len(terms['missing_reasons']) >= 3
         and 'MISSING_ORIGINAL' in terms['missing_reasons'], 'TERMS_GAP_REASONS_REQUIRED')
    need(row['copyright']['status'] == 'UNKNOWN' and
         row['copyright']['redistribution_authorized'] is False, 'NO_COPYRIGHT_PERMISSION')
    return 'UNKNOWN'


def validate_gaps(matrix):
    need(matrix['kind'] == 'NNV2_ACCESS_GAPS_V1' and matrix['scope'] == 'OFFLINE_REVIEW_ONLY', 'GAP_SCHEMA')
    need(same(matrix['normative_counts'], dict(PASS=15, FAIL=0, UNKNOWN=9)), 'HISTORICAL_COUNTS_IMMUTABLE')
    need(same(matrix['fully_resolved_historical_unknowns'], 0), 'NO_HISTORICAL_UNKNOWN_PROMOTION')
    rows = matrix['rows']
    need(type(rows) is list and len({r['id'] for r in rows}) == len(rows), 'UNIQUE_GAPS_REQUIRED')
    need([r['historical_id'] for r in rows if r['historical_id'] is not None] == list(UNKNOWN_IDS), 'EXACT_NINE_UNKNOWN_IDS')
    need({c for r in rows for c in r['classes']} == set(GAP_CLASSES), 'ALL_GAP_CLASSES_REQUIRED')
    for r in rows:
        need(r['status'] == 'UNKNOWN' and r['classes'] and set(r['classes']) <= set(GAP_CLASSES), 'GAP_CLASS_OR_STATE')
        need(r['targets'] and set(r['targets']) <= set(TARGETS), 'GAP_TARGET_SCOPE')
        need(r['priority'] in {'P0', 'P1', 'P2'} and r['bucket'] in {'P0-A', 'P0-B', 'P1', 'P2'}, 'GAP_PRIORITY')
        need((r['priority'] == r['bucket'][:2]), 'GAP_PRIORITY_BUCKET')
        flags = ('offline_fully_resolvable', 'external_acquisition_required', 'dynamic_isolation_required',
                 'only_after_real_communication', 'additional_approval_required')
        need(all(type(r[k]) is bool for k in flags), 'GAP_FLAGS_BOOLEAN')
        need(not r['offline_fully_resolvable'] or not any(r[k] for k in flags[1:4]), 'CONTRADICTORY_OFFLINE_RESOLUTION')
        need(not any(r[k] for k in flags[1:4]) or r['additional_approval_required'], 'ADDITIONAL_APPROVAL_REQUIRED')
        need(r['affected_gates'] and r['minimum_steps'] and r['residual_constraints'] and r['shared_evidence'], 'GAP_RESOLUTION_REQUIRED')
        if r['historical_id'] is not None:
            need(r['original_definition'] and r['source_record_SHA256'], 'HISTORICAL_SOURCE_REQUIRED')
            digest(r['source_record_SHA256'])
    return True


def validate_inventory(data, blobs, trusted_pins):
    need(data['kind'] == 'NNV2_ACCESS_EVIDENCE_V1' and data['scope'] == 'OFFLINE_REVIEW_ONLY'
         and data['base_commit'] == BASE_COMMIT, 'INVENTORY_SCOPE')
    stamp(data['reviewed_utc'])
    need(same(data['identifiers'], dict(user_agent=USER_AGENT, product_token=PRODUCT_TOKEN,
         adoption='G1_ADOPTED_OFFLINE_ONLY')), 'ADOPTED_IDENTIFIERS')
    need(same(data['holds'], HOLDS), 'PROTECTED_HOLDS')
    need(same(data['operations'], OPERATIONS), 'NO_NEW_COMMUNICATION_OR_PERMIT')
    need(same(data['normative_counts'], dict(PASS=15, FAIL=0, UNKNOWN=9)), 'HISTORICAL_COUNTS_IMMUTABLE')
    need(data['historical_unknown_ids'] == list(UNKNOWN_IDS), 'EXACT_NINE_UNKNOWN_IDS')
    need([r['id'] for r in data['rows']] == list(TARGETS), 'EXACT_SIX_URLS')
    for row in data['rows']:
        target = row['id']; validate_scope(target, row['URL'], row['host'])
        need(type(row['purpose']) is str and bool(row['purpose']), 'PURPOSE_REQUIRED')
        saved = verify_provenance(row['original'], blobs, trusted_pins, data['reviewed_utc'])
        need(saved == (target == 'A1'), 'BASELINE_ORIGINAL_SET')
        if saved:
            need(row['original']['source_url'] == row['URL'], 'ORIGINAL_URL_BINDING')
        robots = row['robots']
        conditional = target in {'A1', 'A3', 'A4', 'B1'}
        need(robots['status'] == ('CONDITIONAL_ALLOW_FIXED_ORIGINAL' if conditional else 'UNKNOWN'), 'ROBOTS_BASELINE')
        if conditional:
            source = data['rows'][0]['original']
            need(robots['source_url'] == TARGETS['A1'] and robots['source_host'] == row['host']
                 and robots['source_SHA256'] == source['raw_SHA256'], 'HOST_SPECIFIC_ROBOTS_REQUIRED')
        else:
            need(all(robots[k] is None for k in ('source_url', 'source_host', 'source_SHA256')), 'NO_ABOUTJ_ORIGINAL')
        need(robots['current_site_allow'] is False and robots['normative_complete'] is False
             and robots['currently_valid'] == 'UNKNOWN', 'FIXED_ORIGINAL_IS_NOT_CURRENT_ALLOW')
        need(robots['evaluation_user_agent'] == USER_AGENT and robots['evaluation_product_token'] == PRODUCT_TOKEN, 'ROBOTS_IDENTITY')
        validate_terms(row)
        ua = row['UA_evidence']
        need(ua['E0'] == ua['E1'] == 'OFFLINE_VERIFIED' and ua['E2'] == ua['E3'] == 'UNKNOWN'
             and ua['E4_new'] is False, 'E1_IS_NOT_WIRE_OR_INDEPENDENT_EVIDENCE')
        digest(ua['G2_E1_record_SHA256'])
        freshness = row['freshness']
        need(freshness['status'] == 'UNKNOWN' and freshness['approved_TTL_seconds'] is None
             and freshness['represents_current_site'] is False, 'FRESHNESS_NOT_ESTABLISHED')
        need(row['overall_access'] == 'HOLD' and row['permit_status'] == 'HOLD'
             and row['permit_id'] is None and row['acquisition_authorized'] is False, 'NO_ACCESS_AUTHORITY')
        scope = row['minimum_scope']
        need(scope['candidate_only'] is True and scope['method_if_separately_approved'] == 'GET'
             and same(scope['max_requests_if_approved'], 1) and scope['periodic_refresh'] is False
             and all(same(scope[k], 0) for k in ('redirect', 'retry', 'parallel')), 'MINIMUM_SCOPE_ONLY')
        need(scope['new_URLs'] == [] and scope['external_distribution'] is False, 'NO_SCOPE_EXPANSION')
        need(row['next_evidence'] and row['candidate_methods'] and row['unknown_causes'], 'HANDOFF_REQUIRED')
    return True


def evaluate_readiness(inventory, gaps, blobs, trusted_pins, *, schema_validated=False,
                       provenance_links_verified=False, protection_passed=None):
    """READY means a documented offline handoff, never permission to fetch."""
    result = dict(gate='NN_V2_P0_ACCESS_EVIDENCE_REVIEW_PARTIAL', reasons=[],
                  access_authorized=False, permit_issued=False, G3_review_authorized=False,
                  G4_authorized=False, historical_unknowns_resolved=0)
    try:
        validate_inventory(inventory, blobs, trusted_pins)
        validate_gaps(gaps)
        need(schema_validated is True and provenance_links_verified is True and
             protection_passed is True, 'SCHEMA_PROVENANCE_PROTECTION_REQUIRED')
        result['gate'] = 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY'
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        result['reasons'] = [str(exc)]
        if protection_passed is False:
            result['gate'] = 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_BLOCKED'
            result['reasons'].append('PROTECTED_BOUNDARY_DIFFERENCE_STOP')
        elif str(exc) in {'ORIGINAL_HASH_MISMATCH', 'PROVENANCE_HASH_MISMATCH',
                           'PROVENANCE_URL_BINDING', 'PROVENANCE_TIME_BINDING', 'PROVENANCE_SEAL_BINDING'}:
            result['gate'] = 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_BLOCKED'
    return result
