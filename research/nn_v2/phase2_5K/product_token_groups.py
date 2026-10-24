"""Pure offline v4: explicit crawler declaration, groups, paths, evidence.

S1 RFC9309 2.2/2.2.1: ASCII token; case-insensitive exact group matching;
matching groups merge; wildcard is fallback. Header substring binding is a
separate, stricter J1AI requirement based on the RFC SHOULD, never a group
substring algorithm. Google crawler-name normalization is not generalized.

No automatic extraction, HTTP, filesystem, permit issuance or live integration.
The I parser/matcher and J synthetic permit checker remain immutable imports.
This bounded subset is not full RFC or Google conformance.
"""
import hashlib
import re
from urllib.parse import urlsplit

from research.nn_v2.phase2_5I import robots_normative as subset
from research.nn_v2.phase2_5J import robots_layers as legacy

VERSION = 'nn_v2_robots_offline_groups_v4'
SCHEMA = 'NNV2_ROBOTS_OFFLINE_GROUPS_V4'
STRUCTURAL_ERRORS = frozenset({'UNKNOWN_AGENT_GRAMMAR', 'MALFORMED_DIRECTIVE', 'RULE_WITHOUT_AGENT'})


def declared_identity(header, tokens):
    """Validate one *declared* token; never extract a name from HTTP syntax.

    Header syntax here is bounded visible ASCII, not a complete HTTP UA parser.
    Complex visible headers may supply a token (RFC Figure1); a declaration is
    not proof of the header actually sent. Multiple declarations stay UNKNOWN,
    including duplicates or candidates leading to the same wildcard group.
    """
    result = dict(status='UNKNOWN', product_token=None, reason=None,
                  auto_extracted=False, actual_transmission_proven=False)
    try:
        subset.need(type(header) is str and 0 < len(header) <= 1024 and
                    all(32 <= ord(c) < 127 for c in header), 'HTTP_HEADER_REQUIRED_VISIBLE_ASCII')
        subset.need(type(tokens) in (list, tuple) and len(tokens) == 1, 'ONE_EXPLICIT_DECLARATION_REQUIRED')
        token = tokens[0]
        subset.need(type(token) is str and re.fullmatch(r'[A-Za-z_-]+', token) is not None,
                    'INVALID_RFC_PRODUCT_TOKEN')
        subset.need(token.casefold() in header.casefold(), 'J1AI_TOKEN_HEADER_BINDING_REQUIRED')
        result.update(status='BOUND_CANDIDATE', product_token=token,
                      reason='EXPLICIT_DECLARATION_NOT_RUNTIME_ACTIVATION')
    except (subset.Uncertain, TypeError, ValueError) as exc:
        result['reason'] = str(exc)
    return result


def select_groups(raw, *, header, declared_tokens):
    """Return grouping separately even when defined path syntax is unresolved."""
    identity = declared_identity(header, declared_tokens)
    result = dict(status='UNKNOWN', reason=identity['reason'], identity=identity,
                  groups=[], selection_basis=None, annotations=[], unresolved=[], body_structure_verified=False)
    try:
        subset.need(type(raw) is bytes and len(raw) <= 65536, 'BODY_TYPE_OR_CAP')
        # Preserve the J no-groups result, without treating failed HTTP as empty.
        text = raw.decode('utf-8-sig')
        if all(not line.split('#', 1)[0].strip(' \t') for line in text.replace('\r', '\n').split('\n')):
            groups, annotations, uncertain = [], [], []
        else:
            groups, annotations, uncertain = subset.parse_saved(raw)
        result.update(annotations=annotations, unresolved=uncertain)
        subset.need(not any(x['reason'] in STRUCTURAL_ERRORS for x in uncertain), 'GROUP_BOUNDARY_OR_AGENT_GRAMMAR_UNKNOWN')
        result['body_structure_verified'] = True
        subset.need(identity['status'] == 'BOUND_CANDIDATE', identity['reason'])
        token = identity['product_token'].casefold()
        named = [g for g in groups if token in [a.casefold() for a in g['agents']]]
        selected = named or [g for g in groups if '*' in g['agents']]
        basis = 'EXACT_CASE_INSENSITIVE_MERGED' if named else 'WILDCARD_FALLBACK' if selected else 'NO_APPLICABLE_GROUP'
        result.update(status='SELECTED', reason='S1_2_2_1_EXPLICIT_TOKEN', groups=selected, selection_basis=basis)
    except (subset.Uncertain, UnicodeError, ValueError, TypeError) as exc:
        result['reason'] = str(exc)
    return result


def path_decision(selection, uri):
    """Unchanged bounded I octet matcher and ranking cross-check; no fallback."""
    result = dict(decision='UNKNOWN', reason=None, matched_rules=[])
    try:
        subset.need(selection['status'] == 'SELECTED', 'GROUP_SELECTION_UNKNOWN')
        subset.need(all(x['reason'] == 'UNKNOWN_DIRECTIVE' for x in selection['unresolved']),
                    'DEFINED_RULE_OR_PATH_UNKNOWN')
        path_tokens, _ = subset.octets(uri)
        work = 0
        matches = []
        for group in selection['groups']:
            for rule in group['rules']:
                matched, size, google_size, cost = subset.match_pattern(rule['pattern'], path_tokens, work_limit=1000000-work)
                work += cost
                if matched:
                    matches.append(dict(rule, group=group['group'], specificity_octets=size, google_pattern_length=google_size))
        result['matched_rules'] = matches
        decision = 'ALLOW'
        if matches:
            size = max(x['specificity_octets'] for x in matches)
            decision = 'ALLOW' if any(x['directive'] == 'allow' and x['specificity_octets'] == size for x in matches) else 'DENY'
            google_size = max(x['google_pattern_length'] for x in matches)
            comparison = 'ALLOW' if any(x['directive'] == 'allow' and x['google_pattern_length'] == google_size for x in matches) else 'DENY'
            subset.need(decision == comparison, 'RFC_GOOGLE_MARKER_RANKING_REQUIRES_REVIEW')
            subset.need(not (len(matches) > 1 and any('%' in x['pattern'] for x in matches)), 'ENCODED_RULE_RANKING_REQUIRES_REVIEW')
        result.update(decision=decision, reason='SUPPORTED_OFFLINE_PATH_SUBSET', work_units=work)
    except (subset.Uncertain, UnicodeError, ValueError, TypeError, KeyError) as exc:
        result['reason'] = str(exc)
    return result


def evaluate(raw, *, source_host, target_url, header, declared_tokens,
             expected_raw_SHA256, specification_SHA256, profile,
             parser_version=VERSION, response_status=200):
    """Candidate normative evaluation. Evidence assertions never grant authority.

    Historical transmitted-header proof is deliberately not accepted as a
    caller-provided boolean. A separate offline evidence audit must establish
    that fact; existing A1/S1/S2 request records omit the outbound header.
    """
    group = dict(status='UNKNOWN', reason='NOT_EVALUATED', groups=[])
    layer1 = dict(decision='UNKNOWN', reason='NOT_EVALUATED', safety_stop=False,
                  group_selection=group, path_result=dict(decision='UNKNOWN', reason='NOT_EVALUATED'))
    evidence = dict(decision='UNKNOWN', raw_origin_spec_verified=False,
                    actual_transmitted_header='UNKNOWN', runtime_token_activation='NOT_APPROVED',
                    unresolved_normative_items=True, reason='OFFLINE_CANDIDATE_NOT_HISTORICAL_SENDER_PROOF')
    result = dict(schema=SCHEMA, parser_version=VERSION, layer1=layer1, layer2=evidence,
                  full_RFC_conformance=False, full_Google_conformance=False,
                  execution_authorized=False, B_authorized=False, history_admission=False)
    try:
        subset.need(parser_version == VERSION, 'K_PARSER_VERSION_MISMATCH')
        subset.need(type(response_status) is int and response_status == 200, 'HTTP_FAILURE_STOP')
        subset.need(specification_SHA256 == subset.SPEC_SHAS, 'SPECIFICATION_SHA_BINDING_REQUIRED')
        digest = hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None
        subset.need(type(expected_raw_SHA256) is str and re.fullmatch('[a-f0-9]{64}', expected_raw_SHA256) is not None
                    and digest == expected_raw_SHA256, 'RAW_SHA_MISMATCH')
        subset.need(profile in {subset.EVIDENCE_PROFILE, subset.SYNTHETIC_PROFILE}, 'UNKNOWN_PROFILE')
        hosts = {'synthetic.invalid'} if profile == subset.SYNTHETIC_PROFILE else subset.HOSTS
        subset.need(source_host in hosts, 'UNEXPECTED_HOST_OR_SCOPE')
        subset.need(digest != subset.A1_SHA or source_host == 'www.jleague.jp', 'SEALED_A1_HOST_MISMATCH')
        subset.need(type(target_url) is str and '#' not in target_url and not re.search(r'[\x00-\x20\\]', target_url), 'UNSAFE_URL')
        url = urlsplit(target_url)
        subset.need(url.scheme == 'https' and url.netloc == source_host and not url.port,
                    'EXACT_HTTPS_ORIGIN_REQUIRED')
        subset.need(profile != subset.EVIDENCE_PROFILE or header == subset.FIXED_AGENT, 'FIXED_EVIDENCE_AGENT_REQUIRED')
        # Read/validate grouping even when URI path syntax cannot be matched.
        group = select_groups(raw, header=header, declared_tokens=declared_tokens)
        layer1['group_selection'] = group
        evidence['raw_origin_spec_verified'] = True
        uri = url.path or '/'
        dot_check = re.sub(r'%2[eE]', '.', url.path)
        subset.need(not any(x in {'.', '..'} for x in dot_check.split('/')), 'DOT_SEGMENTS_REQUIRE_REVIEW')
        if '?' in target_url:
            subset.need(re.fullmatch(r'[A-Za-z0-9._~-]+=[A-Za-z0-9._~-]*', url.query) is not None,
                        'QUERY_OUTSIDE_J_VERIFIED_SUBSET')
            uri += '?' + url.query
        path = path_decision(group, uri)
        layer1['path_result'] = path
        layer1.update(decision=path['decision'], reason=path['reason'])
        # Exact implicit URI remains independent of choosing a crawler token,
        # but malformed body/defined rules cannot bypass validation here.
        if (uri == '/robots.txt' and group['body_structure_verified'] and not group['unresolved']
                and (path['decision'] != 'UNKNOWN' or path['reason'] == 'GROUP_SELECTION_UNKNOWN')):
            layer1['path_result'] = dict(decision='ALLOW', reason='RFC_2_2_2_EXACT_IMPLICIT_URI', matched_rules=path['matched_rules'])
            layer1.update(decision='ALLOW', reason='RFC_2_2_2_IMPLICIT_ROBOTS_URI')
    except (subset.Uncertain, UnicodeError, ValueError, TypeError) as exc:
        layer1.update(decision='UNKNOWN', reason=str(exc))
        if str(exc) in {'HTTP_FAILURE_STOP', 'RAW_SHA_MISMATCH', 'SPECIFICATION_SHA_BINDING_REQUIRED', 'SEALED_A1_HOST_MISMATCH'}:
            layer1['safety_stop'] = True
            evidence.update(decision='DENY', reason=str(exc))
    permit = legacy.permit_check(None, None, '2026-10-24T00:00:00+00:00')
    result['layer3'] = dict(permit=permit, communication=legacy.communication_check(layer1, permit, evidence))
    return result
