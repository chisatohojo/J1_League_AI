"""Pure scope/priority analysis and synthetic gate scenarios; no live authority.

No parser/collector/permit change. UNKNOWN is never promoted to normative PASS.
The real-source profile only examines the exact sealed A1 and six fixed URLs;
the synthetic profile is diagnostic test input, not an execution capability.
"""
import hashlib
from urllib.parse import urlsplit

from research.nn_v2.phase2_5L import ua_evidence_contract as contract

robots = contract.robots
IDS = ('agent_grammar', 'rule_grammar', 'longest_rule', 'reserved_octets', 'query',
       'encoding_errors', 'parse_limits', 'standard_examples', 'sealed_A1_replay')
DIRECT = frozenset({'agent_grammar', 'sealed_A1_replay'})
TARGETS = {
    'A1': 'https://www.jleague.jp/robots.txt',
    'A3': 'https://www.jleague.jp/general/kiyaku/',
    'A4': 'https://www.jleague.jp/general/copyright/',
    'B1': 'https://www.jleague.jp/j1/news/',
    'A2': 'https://aboutj.jleague.jp/robots.txt',
    'B2': 'https://aboutj.jleague.jp/corporate/pressrelease/',
}
PROFILES = frozenset({'SEALED_A1_OFFLINE_REVIEW', 'SYNTHETIC_ONLY'})


class ReviewError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise ReviewError(reason)


def check_target(target_id, url):
    need(type(target_id) is str and target_id in TARGETS and url == TARGETS[target_id], 'EXACT_FIXED_TARGET_REQUIRED')
    return urlsplit(url)


def priority(*, direct_stop, scope_exclusion_proven, unused_in_scope=False):
    """A classification only. Unproved P2/P3 always returns to P1."""
    need(all(type(x) is bool for x in [direct_stop, scope_exclusion_proven, unused_in_scope]), 'PRIORITY_FACT_TYPES')
    if direct_stop:
        return 'P0'
    if not scope_exclusion_proven:
        return 'P1'
    return 'P3' if unused_in_scope else 'P2'


def assess(raw, target_id, *, scope, expected_reference_SHA256, target_url=None,
           header=contract.UA, token=contract.TOKEN, parser_version=robots.VERSION,
           specification_SHA256=None):
    """Explain this exact context without changing any normative decision.

    The P2 certificates require exact URL/header/token/version, verified reference
    hash, complete supported syntax, and the axis-specific non-trigger proof.
    Missing aboutj evidence cannot borrow www proof, even for /robots.txt.
    """
    need(scope in PROFILES, 'OFFLINE_PROFILE_REQUIRED')
    url = TARGETS.get(target_id) if target_url is None else target_url
    parsed = check_target(target_id, url)
    result = dict(target_id=target_id, URL=url, scope=scope, priorities={}, normative='UNKNOWN',
                  normative_reason='NO_HOST_SPECIFIC_ORIGINAL', group_selection=[], matched_rule_count=None,
                  scope_exclusions={x: False for x in IDS}, safety_stop=False,
                  execution_authorized=False, permit_issued=False, history_admission=False)
    identity = dict(URL=url, header=header, token=token, parser_version=parser_version,
                    candidate_configuration_hash=contract.configuration_hash(), scope=scope,
                    specification_SHA256=specification_SHA256)
    if parsed.hostname == 'aboutj.jleague.jp':
        need(raw is None and expected_reference_SHA256 is None, 'WWW_PROOF_CANNOT_SUPPLY_ABOUTJ_ORIGINAL')
        result['priorities'] = {x: 'P0' if x in DIRECT else 'P1' for x in IDS}
        result['certificate'] = dict(binding=identity, source_absent=True)
    else:
        actual_sha = hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None
        pin_ok = (type(expected_reference_SHA256) is str and actual_sha == expected_reference_SHA256 and
                  (scope == 'SYNTHETIC_ONLY' or expected_reference_SHA256 == robots.subset.A1_SHA))
        specs = specification_SHA256
        identity.update(raw_SHA256=actual_sha, expected_reference_SHA256=expected_reference_SHA256)
        if not pin_ok or specs != robots.subset.SPEC_SHAS or parser_version != robots.VERSION:
            result.update(safety_stop=True, normative_reason='REFERENCE_SPEC_OR_VERSION_BINDING_FAILURE')
            result['priorities'] = {x: 'P0' for x in IDS}
            result['certificate'] = dict(binding=identity, integrity_verified=False)
        else:
            target = 'https://synthetic.invalid'+parsed.path if scope == 'SYNTHETIC_ONLY' else url
            profile = robots.subset.SYNTHETIC_PROFILE if scope == 'SYNTHETIC_ONLY' else robots.subset.EVIDENCE_PROFILE
            evaluated = robots.evaluate(raw, source_host='synthetic.invalid' if scope == 'SYNTHETIC_ONLY' else parsed.hostname,
                target_url=target, header=header, declared_tokens=[] if token is None else [token],
                expected_raw_SHA256=actual_sha, specification_SHA256=specs, profile=profile)
            layer = evaluated['layer1'];group = layer['group_selection'];path = layer['path_result']
            # K's exact implicit-robots result intentionally omits work units.
            # Reuse its unchanged pure matcher to measure the same selected
            # rules; never replace the normative implicit-URI result.
            path_probe = robots.path_decision(group, parsed.path)
            result.update(normative=layer['decision'], normative_reason=layer['reason'], safety_stop=layer['safety_stop'])
            result['group_selection'] = [dict(group=g['group'], agents=g['agents'], rule_count=len(g['rules'])) for g in group.get('groups', [])]
            result['matched_rule_count'] = len(path.get('matched_rules', []))
            try:
                groups, annotations, unresolved = robots.subset.parse_saved(raw)
                patterns = [r['pattern'] for g in groups for r in g['rules']]
            except (ValueError, UnicodeError):
                groups, annotations, unresolved, patterns = [], [], [{'reason': 'UNPARSEABLE_REFERENCE'}], []
            supported = (layer['decision'] == 'ALLOW' and group.get('status') == 'SELECTED' and
                         group.get('body_structure_verified') is True and not unresolved and
                         header == contract.UA and token == contract.TOKEN and result['matched_rule_count'] == 0)
            facts = dict(reference_integrity_verified=True, bytes=len(raw), line_count=len(raw.splitlines()),
                group_count=len(groups), total_rule_count=sum(len(g['rules']) for g in groups),
                all_defined_rules_supported=bool(groups) and not unresolved,
                unresolved_records=len(unresolved), ASCII_reference=raw.isascii(),
                percent_in_patterns=any('%' in p for p in patterns), percent_in_target='%' in url,
                query_in_patterns=any('?' in p for p in patterns), query_in_target='?' in url,
                no_priority_contest=result['matched_rule_count'] == 0 and path['decision'] == 'ALLOW',
                work_units=path_probe.get('work_units'),
                conflicting_examples_absent=all(p.startswith('/') for p in patterns) and
                    not any(x in raw for x in [b'disallowed.gif', b'disallow.gif']))
            within_caps = (len(raw) <= 65536 and facts['line_count'] < 4096 and facts['total_rule_count'] <= 1000
                           and type(facts['work_units']) is int and facts['work_units'] <= 1000000)
            proofs = dict(rule_grammar=supported and facts['all_defined_rules_supported'],
                longest_rule=supported and facts['no_priority_contest'],
                reserved_octets=supported and facts['ASCII_reference'] and not facts['percent_in_patterns'] and not facts['percent_in_target'],
                query=supported and not facts['query_in_patterns'] and not facts['query_in_target'],
                encoding_errors=supported and facts['ASCII_reference'] and not unresolved,
                parse_limits=supported and within_caps,
                standard_examples=supported and facts['conflicting_examples_absent'])
            result['scope_exclusions'].update(proofs)
            triggered = set()
            reason = layer['reason'] or ''
            if 'RANKING' in reason:triggered.add('longest_rule')
            if 'BODY_TYPE_OR_CAP' in reason or len(raw) > 65536:triggered.add('parse_limits')
            if not groups and len(raw) <= 65536:triggered.update(['rule_grammar', 'encoding_errors'])
            if unresolved and len(raw) <= 65536:triggered.add('rule_grammar')
            result['priorities'] = {x: priority(direct_stop=x in DIRECT or x in triggered or layer['safety_stop'],
                scope_exclusion_proven=bool(result['scope_exclusions'][x])) for x in IDS}
            result['certificate'] = dict(binding=identity, facts=facts, scope_exclusions=result['scope_exclusions'])
    result['certificate_hash'] = contract.hash_json(result['certificate'])
    return result


def verify_certificate(certificate_hash, raw, target_id, **context):
    """Recompute bindings, never trust a bare claimed P2/P3 flag."""
    actual = assess(raw, target_id, **context)
    need(certificate_hash == actual['certificate_hash'] and not actual['safety_stop'], 'SCOPE_CERTIFICATE_MISMATCH')
    return True


SCENARIO_CHECKS = frozenset({'configuration_matches', 'prepared_request_verified', 'scope_certificate_verified',
    'access_conditions_or_bootstrap_reviewed', 'limits_and_storage_verified', 'capture_mechanism_mock_verified',
    'new_run_binding_verified', 'E3_method_qualified'})
SCENARIO_FIELDS = frozenset({'kind', 'scope', 'target_id', 'target_url', 'phase', 'approvals', 'checks',
    'permit_source', 'attempts_used', 'E3_requirement', 'E2_outcome', 'E3_outcome', 'E4_outcome'})


def review_gate_scenario(value):
    """Pure hypothetical sequencing; no live permit acceptance or issuance.

    G1/G2/G3/G4-start approvals are separate fixture facts. E2/E3 for the current
    request are post-send observations, not a prerequisite requiring time travel.
    """
    out = dict(decision='SIMULATED_STOP', missing=[], execution_authorized=False,
               permit_issued=False, actual_E2_verified=False, actual_E3_verified=False, automatic_retry=False)
    try:
        need(type(value) is dict and set(value) == SCENARIO_FIELDS, 'SCENARIO_SCHEMA')
        need(value['kind'] == 'OFFLINE_GATE_SCENARIO_V1' and value['scope'] == 'SYNTHETIC_ONLY', 'NO_REAL_EXECUTION_SCOPE')
        check_target(value['target_id'], value['target_url'])
        approvals=value['approvals'];checks=value['checks']
        need(type(approvals) is dict and set(approvals) == {'G1', 'G2', 'G3', 'G4_start'} and
             all(type(x) is bool for x in approvals.values()), 'SEPARATE_APPROVAL_FACTS')
        need(type(checks) is dict and set(checks) == SCENARIO_CHECKS and all(type(x) is bool for x in checks.values()), 'CHECK_FACTS')
        need(value['permit_source'] == 'NEW_SYNTHETIC_ONLY', 'OLD_OR_REAL_PERMIT_NOT_REUSABLE')
        need(type(value['attempts_used']) is int and value['attempts_used'] in {0, 1}, 'BUDGET_EXCEEDED')
        need(value['E3_requirement'] in {'REQUIRED', 'NOT_REQUIRED_EXPLICITLY_APPROVED'}, 'NO_SILENT_E3_DOWNGRADE')
        out['missing'] = [x for x,b in approvals.items() if not b] + [x for x,b in checks.items() if not b and
            (x != 'E3_method_qualified' or value['E3_requirement'] == 'REQUIRED')]
        if out['missing']:
            out['reason']='PRE_SEND_CONDITIONS_INCOMPLETE';return out
        if value['phase'] == 'BEFORE':
            need(value['attempts_used'] == 0 and all(value[x] is None for x in ['E2_outcome','E3_outcome','E4_outcome']), 'POST_SEND_PROOF_NOT_PREEXISTING')
            out.update(decision='SIMULATED_PRE_SEND_READY', reason='MECHANISM_VERIFIED_NO_CURRENT_SEND_PROOF_REQUIRED')
        else:
            need(value['phase'] == 'AFTER' and value['attempts_used'] == 1, 'PHASE_OR_UNCHARGED_ATTEMPT')
            need(value['E2_outcome'] == 'COMPLETED' and value['E4_outcome'] == 'SEALED_READBACK', 'SEND_OR_SAVE_INCOMPLETE')
            if value['E3_requirement'] == 'REQUIRED':
                need(value['E3_outcome'] == 'VERIFIED', 'REQUIRED_E3_MISSING')
            else:
                need(value['E3_outcome'] in {'NOT_OBSERVED','UNVERIFIED'}, 'UNAPPROVED_E3_PROMOTION')
            out.update(decision='SIMULATED_POST_SEND_REVIEW_COMPLETE', reason='OBSERVED_SCOPE_RECORDED_NO_REAL_WORLD_CLAIM')
    except (ReviewError, TypeError, ValueError, KeyError) as exc:
        out['reason']=str(exc)
    return out
