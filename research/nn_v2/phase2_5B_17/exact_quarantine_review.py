"""Offline v6 exact-witness review. No I/O, HTTP, permit or history admission."""
import copy
import hashlib
import html
import json
import re

VERSION = 'reviewed_quarantine_exact_witness_v6'
BASE_PASS = 'PARSE_VERIFIED_FINAL_RECORD_ONLY'
KINDS = {'EXACT_SUBSTITUTION_PAIR', 'EXACT_POSTMATCH_COACH_WARNING', 'EXACT_MINUTE_GK_WARNING'}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def positive_paragraphs(rule):
    """Validate affirmative reviewed syntax, after the exact witness checks."""
    fields = rule['positive_fields']
    if rule['kind'] == 'EXACT_SUBSTITUTION_PAIR':
        require(len(fields) == 2, 'REVIEWED_PAIR_ONLY')
        result = []
        for f in fields:
            require(all(type(f[k]) is str and f[k] for k in (
                'display', 'club', 'out_number', 'out_person', 'in_number', 'in_person')), 'SUBSTITUTION_FIELDS')
            require(f['out_number'].isdigit() and f['in_number'].isdigit(), 'JERSEY_NUMBERS')
            # Display markers remain literal. Their medical/rule/time meaning is not inferred.
            result.append(f['display'] + ' ' + f['club'] + ' ' + f['out_number'] + ' ' + f['out_person']
                          + '→' + f['in_number'] + ' ' + f['in_person'] + ' は脳振盪交代　相手チーム交代枠+1')
        return result
    require(len(fields) == 1, 'SINGLE_STAFF_PARAGRAPH_ONLY')
    f = fields[0]
    require(all(type(f[k]) is str and f[k] for k in ('display', 'club', 'person', 'role', 'expression', 'code')), 'STAFF_FIELDS')
    require(f['expression'] == '警告' and f['code'] == 'C3', 'EXACT_WARNING_LITERAL')
    if rule['kind'] == 'EXACT_POSTMATCH_COACH_WARNING':
        require(f['display'] == '試合終了後' and f['role'] == '（コーチ）', 'EXACT_POSTMATCH_COACH_FORM')
    else:
        require(rule['kind'] == 'EXACT_MINUTE_GK_WARNING' and f['role'] == '（ＧＫコーチ）', 'EXACT_GK_ROLE')
        require(re.fullmatch(r"[0-9]+'(?:\+[0-9]+)?", f['display']) is not None, 'MINUTE_LITERAL_FORM')
    return [f['display'] + ' ' + f['expression'] + '(' + f['code'] + ') ' + f['club'] + '  ' + f['person'] + ' ' + f['role']]


def match_review(raw, metadata_raw, request_raw, expected, prior, rule):
    require(rule['decision'] == 'KNOWN_NON_TIMING_EXACT_WITNESS_ONLY' and rule['kind'] in KINDS, 'REVIEW_DECISION')
    require(rule['namespace'] == 'jleague_data_site_sfms02', 'NAMESPACE')
    require(encoded(expected) == encoded(rule['expected']), 'FULL_EXPECTED_IDENTITY_SOURCE_REVISION_PINS')
    require(expected['row']['identity'] == prior['identity'] == rule['identity'], 'IDENTITY')
    require(encoded(prior) == encoded(rule['original_v5_HOLD']), 'ORIGINAL_V5_ANALYSIS')
    base = prior['strict_analysis']
    require(prior['status'] == 'HOLD' and prior['legacy_category'] == 'UNKNOWN_FORMAT'
            and base['status'] == BASE_PASS and not base['timing_notes'], 'STRICT_UNKNOWN_ONLY')
    for value, key in [(raw, 'raw_sha256'), (metadata_raw, 'metadata_sha256'), (request_raw, 'request_sha256')]:
        require(sha(value) == rule['expected']['pins'][key], 'EXACT_PACKET_SHA')
    meta, request = json.loads(metadata_raw), json.loads(request_raw)
    require(meta['requested_url'] == meta['final_url'] == request['url'] == expected['row']['url'], 'PACKET_URL')
    require(meta['request_started_at_utc'] == request['request_started_at_utc'] == rule['request_started_UTC']
            and meta['response_completed_at_utc'] == rule['response_completed_UTC']
            and meta['snapshot_saved_at_utc'] == rule['snapshot_saved_UTC'], 'ACTUAL_ACQUISITION_UTC')
    blocks = list(re.finditer(rb'<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->', raw, re.S))
    require(len(blocks) == 1, 'A11_COUNT')
    block = blocks[0]
    require([block.start(), block.end()] == rule['A11_byte_range'], 'A11_BYTE_RANGE')
    require(sha(block.group()) == rule['A11_SHA256'] and block.group().decode('utf8') == rule['A11_HTML'], 'A11_FULL_HTML')
    a10 = list(re.finditer(rb'<!-- A10[^>]*End -->', raw[:block.start()]))
    a12 = re.search(rb'<!-- A12[^>]*Start -->', raw[block.end():])
    require(bool(a10) and a12 is not None and a10[-1].start() == rule['A10_end_byte_start']
            and a12.start() == rule['A12_relative_byte_start'], 'NEIGHBOR_STRUCTURE')
    body = block.group(1).decode('utf8')
    require(re.findall(r'<h4\b[^>]*>(.*?)</h4>', body, re.S) == ['備考'], 'REMARK_HEADING')
    paragraphs = re.findall(r'<p\b[^>]*>.*?</p>', body, re.S)
    require(paragraphs == rule['paragraph_HTML'], 'ALL_PARAGRAPHS_EXACT')
    texts = [html.unescape(re.sub(r'<[^>]*>', '', p)) for p in paragraphs]
    require(texts == rule['paragraph_verbatim'] == positive_paragraphs(rule), 'POSITIVE_FULL_SYNTAX')
    require(base['remarks_structure'] == 'A11_BLOCK' and base['remarks'] == rule['normalized_remarks'], 'ALL_REMARKS')
    require(rule['classification'] == 'AFFIRMATIVELY_REVIEWED_NON_TIMING_ANNOTATION'
            and rule['history_admission'] is False and rule['timing_B_C_D'] == 'HOLD', 'REVIEW_BOUNDARY')


def analyze(raw, metadata_raw, request_raw, expected, prior_analyze, verify_packet, registry, registry_sha):
    """Retain v5 PASS verbatim; only pinned UNKNOWN_FORMAT witnesses can change."""
    report = {'version': VERSION, 'identity': expected.get('row', {}).get('identity'), 'status': 'HOLD', 'rule_applied': None}
    try:
        require(sha(encoded(registry)) == registry_sha and registry['version'] == VERSION, 'REGISTRY_SHA_VERSION')
        rules = registry['rules']
        require(len(rules) == 3 and len({r['identity'] for r in rules}) == 3, 'THREE_REVIEWED_WITNESSES_ONLY')
        verify_packet(raw, metadata_raw, request_raw, expected['pins'])
        prior = prior_analyze(raw, metadata_raw, request_raw, expected)
        if prior['status'] == 'PASS':
            return copy.deepcopy(prior)
        report = copy.deepcopy(prior)
        rule = next((r for r in rules if r['identity'] == expected['row']['identity']), None)
        if rule is None:
            return report
        match_review(raw, metadata_raw, request_raw, expected, prior, rule)
        report.pop('reason', None)
        report.update(version=VERSION, status='PASS', category='KNOWN_NON_TIMING_NOTE', rule_applied=rule['kind'])
    except (ValueError, KeyError, TypeError, UnicodeError, IndexError) as exc:
        report.update(status='HOLD', reason=type(exc).__name__ + ':' + str(exc))
    return report


def require_history_admission(_analysis):
    raise ValueError('HISTORY_ADMISSION_NOT_AUTHORIZED')
