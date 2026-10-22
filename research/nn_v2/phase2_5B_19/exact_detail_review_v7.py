"""Offline exact-witness v7. No I/O, acquisition, permits, models or admission."""
import copy
import hashlib
import html
import json
import re

VERSION = 'reviewed_detail_exact_witness_v7'
BASE_PASS = 'PARSE_VERIFIED_FINAL_RECORD_ONLY'
KINDS = {'POSTMATCH_PLAYER_CAUTION_REFERENCE', 'POSTMATCH_COACH_CAUTION', 'MINUTE_GK_CAUTION',
         'SUBSTITUTION_WITH_RESPONSE_CONTINUATION', 'TWO_STAFF_CAUTION_PARAGRAPHS'}


class EvidenceStop(RuntimeError):
    """Evidence/identity/trust inconsistency; never downgraded to remark HOLD."""


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def trust(condition, reason):
    if not condition:
        raise EvidenceStop(reason)


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def positive_paragraphs(rule):
    """Affirmative literal syntax, evaluated only for a sealed exact witness."""
    kind, fields = rule['kind'], rule['positive_fields']
    require(kind in KINDS, 'UNREVIEWED_KIND')
    if kind == 'POSTMATCH_PLAYER_CAUTION_REFERENCE':
        require(len(fields) == 1, 'ONE_PLAYER_REFERENCE')
        f = fields[0]
        require(f['marker'] == '***' and f['number'].isdigit() and f['club'] and f['person'], 'PLAYER_REFERENCE_FIELDS')
        return [f['marker'] + ' ' + f['club'] + ' ' + f['number'] + ' ' + f['person'] + 'の警告は試合終了後の警告']
    if kind == 'SUBSTITUTION_WITH_RESPONSE_CONTINUATION':
        require(len(fields) == 2, 'EXACT_TWO_SUBSTITUTION_PAIRS')
        stems = []
        for f in fields:
            require(all(type(f[k]) is str and f[k] for k in ('display', 'club', 'out_number', 'out_person', 'in_number', 'in_person')), 'SUBSTITUTION_FIELDS')
            require(f['out_number'].isdigit() and f['in_number'].isdigit(), 'JERSEY_FIELDS')
            stems.append(f['display'] + ' ' + f['club'] + ' ' + f['out_number'] + ' ' + f['out_person'] + '→' + f['in_number'] + ' ' + f['in_person'])
        continuation = rule['reviewed_continuation']
        require(continuation['classification'] == 'REVIEWED_LITERAL_RESPONSE_ALLOWANCE'
                and continuation['paragraph_index'] == 2
                and sha(continuation['verbatim'].encode('utf8')) == continuation['text_SHA256'],
                'EXACT_PRIVATELY_REVIEWED_CONTINUATION')
        # Its full text is private witness data, never a generic sentence classifier.
        return [stems[0] + ' は脳振盪交代　相手チーム交代枠+1', stems[1] + ' ', continuation['verbatim']]
    count = 2 if kind == 'TWO_STAFF_CAUTION_PARAGRAPHS' else 1
    require(len(fields) == count, 'EXACT_STAFF_PARAGRAPH_COUNT')
    roles = ['（監督）', '（コーチ）'] if count == 2 else ['（コーチ）' if kind == 'POSTMATCH_COACH_CAUTION' else '（ＧＫコーチ）']
    codes = ['C3', 'C1'] if count == 2 else ['C3']
    result = []
    for f, role, code in zip(fields, roles, codes):
        require(f['role'] == role and f['expression'] == '警告' and f['code'] == code, 'EXACT_ROLE_WARNING_CODE_LITERALS')
        require(f['club'] and f['person'], 'EXPLICIT_CLUB_AND_PERSON')
        if kind == 'POSTMATCH_COACH_CAUTION':
            require(f['display'] == '試合終了後', 'RELATIVE_POSTMATCH_LITERAL')
        else:
            require(re.fullmatch(r"[0-9]+'(?:\+[0-9]+)?", f['display']) is not None, 'MINUTE_DISPLAY_LITERAL')
        result.append(f['display'] + ' ' + f['expression'] + '(' + f['code'] + ') ' + f['club'] + '  ' + f['person'] + ' ' + f['role'])
    return result


def match_review(raw, metadata_raw, request_raw, expected, prior, rule):
    trust(encoded(expected) == encoded(rule['expected']), 'FIXTURE_SOURCE_REVISION_OR_PINS_DRIFT')
    trust(rule['identity'] == prior['identity'] == expected['row']['identity'], 'IDENTITY_DRIFT')
    trust(rule['fixture_namespace'] == expected['row']['identity'].split(':')[0]
          and rule['official_detail_namespace'] == 'jleague_data_site_sfms02', 'NAMESPACE_DRIFT')
    trust(encoded(prior) == encoded(rule['original_baseline_HOLD']), 'BASELINE_ANALYSIS_DRIFT')
    base = prior['strict_analysis']
    require(prior['status'] == 'HOLD' and prior['legacy_category'] == 'UNKNOWN_FORMAT'
            and base['status'] == BASE_PASS and not base['timing_notes'], 'UNKNOWN_REMARK_ONLY')
    meta, request = json.loads(metadata_raw), json.loads(request_raw)
    trust(meta['requested_url'] == meta['final_url'] == request['url'] == expected['row']['url'], 'URL_DRIFT')
    for data, key in [(raw, 'raw_sha256'), (metadata_raw, 'metadata_sha256'), (request_raw, 'request_sha256')]:
        trust(sha(data) == rule['expected']['pins'][key], 'REVIEWED_PACKET_SHA_DRIFT')
    trust(meta['request_started_at_utc'] == request['request_started_at_utc'] == rule['request_started_UTC']
          and meta['response_completed_at_utc'] == rule['response_completed_UTC']
          and meta['snapshot_saved_at_utc'] == rule['snapshot_saved_UTC'], 'ACQUISITION_UTC_DRIFT')
    blocks = list(re.finditer(rb'<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->', raw, re.S))
    trust(len(blocks) == 1, 'A11_COUNT_DRIFT')
    block = blocks[0]
    trust([block.start(), block.end()] == rule['A11_byte_range'] and sha(block.group()) == rule['A11_SHA256']
          and block.group().decode('utf8') == rule['A11_HTML'], 'A11_POSITION_HTML_SHA_DRIFT')
    a10 = list(re.finditer(rb'<!-- A10[^>]*End -->', raw[:block.start()]))
    a12 = re.search(rb'<!-- A12[^>]*Start -->', raw[block.end():])
    trust(bool(a10) and a12 is not None and a10[-1].start() == rule['A10_end_byte_start']
          and a12.start() == rule['A12_relative_byte_start'], 'NEIGHBOR_POSITION_DRIFT')
    body = block.group(1).decode('utf8')
    require(re.findall(r'<h4\b[^>]*>(.*?)</h4>', body, re.S) == ['備考'], 'EXACT_A11_HEADING')
    paragraphs = re.findall(r'<p\b[^>]*>.*?</p>', body, re.S)
    require(paragraphs == rule['paragraph_HTML'], 'ALL_PARAGRAPH_HTML')
    text = [html.unescape(re.sub(r'<[^>]*>', '', p)) for p in paragraphs]
    require(text == rule['paragraph_verbatim'] == positive_paragraphs(rule), 'ALL_AFFIRMATIVE_PARAGRAPHS')
    require(paragraphs == ['<p>' + t + '</p>' for t in text], 'ONLY_REVIEWED_PLAIN_PARAGRAPH_STRUCTURE')
    require(base['remarks_structure'] == 'A11_BLOCK' and base['remarks'] == rule['normalized_remarks'], 'ALL_REMARKS_REQUIRED')
    spans = rule['corroborating_spans']
    require(bool(spans) and bool(rule['positive_basis']), 'AFFIRMATIVE_EVIDENCE_REQUIRED')
    required = {'A8', 'ROSTER'} if rule['kind'] == 'POSTMATCH_PLAYER_CAUTION_REFERENCE' else {'A7', 'ROSTER'} if rule['kind'] == 'SUBSTITUTION_WITH_RESPONSE_CONTINUATION' else {'A10', 'A11'} if rule['kind'] == 'TWO_STAFF_CAUTION_PARAGRAPHS' else {'A11'}
    require(required <= {span['field'] for span in spans}, 'CORROBORATION_FIELDS_REQUIRED')
    for span in spans:
        start, end = span['byte_range']
        trust(type(start) is int and type(end) is int and 0 <= start < end <= len(raw), 'CORROBORATION_RANGE')
        trust(raw[start:end].decode('utf8') == span['HTML'] and sha(raw[start:end]) == span['SHA256'], 'CORROBORATION_BYTES_SHA')
    require(rule['classification'] == 'A_AFFIRMATIVE_NON_TIMING' and rule['decision'] == 'EXACT_REVIEWED_WITNESS_ONLY'
            and rule['history_admission'] is False and rule['timing_B_C_D'] == 'HOLD', 'REVIEW_BOUNDARY')


def analyze(raw, metadata_raw, request_raw, expected, baseline_analyze, verify_packet, registry, registry_sha):
    trust(sha(encoded(registry)) == registry_sha and registry['version'] == VERSION, 'REGISTRY_SHA_VERSION_DRIFT')
    rules = registry['rules']
    trust(len(rules) == 6 and len({r['identity'] for r in rules}) == 6, 'SIX_EXACT_WITNESSES_ONLY')
    try:
        verify_packet(raw, metadata_raw, request_raw, expected['pins'])
    except (ValueError, KeyError, TypeError, UnicodeError, IndexError) as exc:
        raise EvidenceStop('ORIGINAL_EVIDENCE_VERIFICATION:' + str(exc)) from exc
    prior = baseline_analyze(raw, metadata_raw, request_raw, expected)
    if prior['status'] == 'PASS':
        return copy.deepcopy(prior)
    report = copy.deepcopy(prior)
    rule = next((r for r in rules if r['identity'] == expected['row']['identity']), None)
    if rule is None:
        return report
    try:
        match_review(raw, metadata_raw, request_raw, expected, prior, rule)
        report.pop('reason', None)
        report.update(version=VERSION, status='PASS', category='KNOWN_NON_TIMING_NOTE', rule_applied=rule['kind'])
    except (ValueError, KeyError, TypeError, UnicodeError, IndexError) as exc:
        report.update(status='HOLD', reason=type(exc).__name__ + ':' + str(exc))
    return report


def require_history_admission(_analysis):
    raise ValueError('HISTORY_ADMISSION_NOT_AUTHORIZED')
