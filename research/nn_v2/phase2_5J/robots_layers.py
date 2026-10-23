"""Pure offline v3 review; no HTTP, permit issuer, filesystem or model API.

Reuse the immutable Phase I subset. Only source-supported distinctions are new:
RFC9309 2.2.2 implicit robots URI; 2.2.1/2.2.2 empty rules; 2.2.4 other records.
Normative results, J1AI evidence restrictions and synthetic permit plans remain
separate. A communication *candidate* never grants real execution authority.
"""
from datetime import datetime
from pathlib import PurePosixPath
from urllib.parse import urlsplit
import re

from research.nn_v2.phase2_5I import robots_normative as previous

VERSION='nn_v2_robots_offline_layers_v3'
SCHEMA='NNV2_ROBOTS_OFFLINE_LAYERS_V3'


def _unknown(reason,*,stop=False):
    return dict(decision='UNKNOWN',reason=reason,applied_groups=[],matched_rules=[],
        parser_version=VERSION,execution_authorized=False,B_authorized=False,
        history_admission=False,safety_stop=stop)


def _checked_rule_groups(groups,annotations,uncertain,agent,token,uri):
    """Ignore other fields for Layer1 only, without rewriting any raw bytes.

    Any malformed defined record remains UNKNOWN. Access/rate instructions in
    other fields are NOT discarded by the independent J1AI policy layer.
    """
    previous.need(all(x['reason']=='UNKNOWN_DIRECTIVE' for x in uncertain),
                  'NOT_SOLELY_OTHER_RECORDS')
    selected,basis=previous.declared_agent_selection(groups,agent,token)
    tokens,_=previous.octets(uri)
    matches=[];work=0
    for group in selected:
        for rule in group['rules']:
            matched,literal_length,google_length,cost=previous.match_pattern(rule['pattern'],tokens,work_limit=1000000-work)
            work+=cost
            if matched:matches.append(dict(rule,group=group['group'],specificity_octets=literal_length,google_pattern_length=google_length))
    candidate='ALLOW'
    if matches:
        length=max(x['specificity_octets'] for x in matches)
        winners=[x for x in matches if x['specificity_octets']==length]
        candidate='ALLOW' if any(x['directive']=='allow' for x in winners) else 'DENY'
        gl=max(x['google_pattern_length'] for x in matches)
        google='ALLOW' if any(x['directive']=='allow' and x['google_pattern_length']==gl for x in matches) else 'DENY'
        previous.need(candidate==google,'RFC_GOOGLE_MARKER_RANKING_REQUIRES_REVIEW')
        previous.need(not(len(matches)>1 and any('%' in x['pattern'] for x in matches)),'ENCODED_RULE_RANKING_REQUIRES_REVIEW')
    return dict(decision=candidate,reason='RFC_2_2_4_OTHER_RECORDS_DO_NOT_CHANGE_RULES' if uncertain else 'RFC_2_2_2_FIGURE4_ASCII_QUERY_PAIR',
        applied_groups=[dict(group=g['group'],agents=g['agents']) for g in selected],matched_rules=matches,
        ignored_other_records=uncertain,annotations=annotations,agent_selection_basis=basis,
        source_references=['S1#section-2.2.4','S2#syntax','S2#grouping-of-lines-and-rules'] if uncertain else ['S1#section-2.2.2','S2#url-matching-based-on-path-values'])


def evaluate(raw,*,parser_version=VERSION,response_status=200,**inputs):
    """Layer1 + J1AI evidence policy, with the unchanged I result beside them.

    The caller must first verify saved metadata/request/seal. This pure function
    checks supplied bytes/SHA/specification pins; it does not authenticate a
    caller assertion or mint authority. Real A1 replay is audited separately.
    """
    out=dict(schema=SCHEMA,parser_version=VERSION,layer1=_unknown('NOT_EVALUATED'),
        j1ai_evidence_policy=dict(decision='UNKNOWN',reason='NOT_EVALUATED'),
        legacy_I_result=None,execution_authorized=False,B_authorized=False,history_admission=False)
    if parser_version!=VERSION:
        out['layer1']=_unknown('J_PARSER_VERSION_MISMATCH');return out
    if type(response_status) is not int or response_status!=200:
        out['layer1']=_unknown('HTTP_FAILURE_NOT_A_VERIFIED_SUCCESS_BODY',stop=True)
        out['j1ai_evidence_policy']=dict(decision='DENY',reason='HTTP_STOP_CONTRACT_UNCHANGED');return out
    legacy=previous.evaluate(raw,parser_version=previous.VERSION,**inputs)
    out['legacy_I_result']=legacy
    layer=dict(legacy,parser_version=VERSION,source_references=['S1#section-2.2.1','S1#section-2.2.2'])
    out['j1ai_evidence_policy']=dict(decision='ALLOW' if legacy['decision'] in {'ALLOW','DENY'} else 'UNKNOWN',
        reason='UNCHANGED_STRICT_I_EVIDENCE_GATES' if legacy['decision'] in {'ALLOW','DENY'} else legacy['reason'])
    # Narrow overrides only after the immutable I validator reached the stated
    # parsing/identity point. An earlier raw/spec/origin/version error cannot
    # become ALLOW, including for an empty body or /robots.txt.
    try:
        if legacy['decision']=='UNKNOWN' and not legacy['safety_stop']:
            url=urlsplit(inputs['target_url'])
            if url.path=='/robots.txt' and '?' not in inputs['target_url'] and legacy['reason']=='EXPLICIT_RFC_PRODUCT_TOKEN_REQUIRED':
                layer.update(decision='ALLOW',candidate_decision='ALLOW',reason='RFC_2_2_2_IMPLICIT_ROBOTS_URI_INDEPENDENT_OF_TOKEN',
                    source_references=['S1#section-2.2.2'],applied_groups=[],matched_rules=[])
            elif legacy['reason'] in {'EMPTY_OR_OVERSIZE_ROBOTS','NO_AGENT_GROUP'} and type(raw) is bytes and len(raw)<=65536:
                text=raw.decode('utf-8-sig')
                if all(not line.split('#',1)[0].strip(' \t') for line in text.replace('\r\n','\n').replace('\r','\n').split('\n')):
                    layer.update(decision='ALLOW',candidate_decision='ALLOW',reason='RFC_2_2_1_NO_GROUPS_NO_RULES',
                        source_references=['S1#section-2.2.1','S1#section-2.2.2'],applied_groups=[],matched_rules=[])
            elif legacy['reason']=='UNRESOLVED_DIRECTIVES_OR_PATTERNS':
                groups,annotations,uncertain=previous.parse_saved(raw)
                uri=url.path or '/'
                if '?' in inputs['target_url']:uri+='?'+url.query
                derived=_checked_rule_groups(groups,annotations,uncertain,inputs['user_agent'],inputs.get('product_token'),uri)
                layer.update(derived)
            elif legacy['reason']=='COMPLEX_RESERVED_QUERY_REQUIRES_REVIEW' and re.fullmatch(r'[A-Za-z0-9._~-]+=[A-Za-z0-9._~-]*',url.query):
                # RFC Figure4 directly shows an ASCII ?key=value comparison.
                # No reserved query data, decoding or multi-pair generalization.
                groups,annotations,uncertain=previous.parse_saved(raw)
                uri=(url.path or '/')+'?'+url.query
                derived=_checked_rule_groups(groups,annotations,uncertain,inputs['user_agent'],inputs.get('product_token'),uri)
                layer.update(derived)
    except (previous.Uncertain,UnicodeError,ValueError,TypeError,KeyError) as exc:
        layer.update(decision='UNKNOWN',candidate_decision=None,reason=str(exc))
    # The legacy candidate is not the normative decision after an override.
    # Historical values stay solely in the explicit legacy_I_result field.
    if layer['decision']=='UNKNOWN':layer['candidate_decision']=None
    out['layer1']=layer
    return out


def permit_check(request,plan,now_UTC):
    """Validate a SYNTHETIC plan only. No real permit can be issued/accepted.

    The plan is just immutable test input; this function performs no I/O, budget
    consumption, signing, reservation, persistence or executor integration.
    """
    out=dict(decision='UNAPPROVED',reason='NO_PERMIT_ISSUED',real_permit_issued=False,execution_authorized=False)
    if plan is None:return out
    try:
        previous.need(type(request) is dict and type(plan) is dict,'PLAN_SCHEMA')
        expected={'kind','scope','approved_for_synthetic_test','URL','host','port','method','max_GET','remaining_GET',
                  'issued_UTC','expires_UTC','redirect','retry','parallel','destination','body_cap'}
        previous.need(set(plan)==expected,'PLAN_SCHEMA')
        previous.need(plan['kind']=='SYNTHETIC_TRANSPORT_PLAN_V1' and plan['scope']=='SYNTHETIC_ONLY' and plan['approved_for_synthetic_test'] is True,'SYNTHETIC_ONLY_NOT_REAL_APPROVAL')
        previous.need(set(request)=={'URL','host','port','method','scope','destination','body_bytes'},'REQUEST_SCHEMA')
        previous.need(type(request['URL']) is str and not re.search(r'[\x00-\x20\\]',request['URL']),'UNSAFE_URL')
        u=urlsplit(request['URL'])
        previous.need(u.scheme=='https' and u.netloc=='synthetic.invalid' and not u.fragment and '#' not in request['URL'],'NO_REAL_HOST_PERMIT_SUPPORTED')
        for key in ['URL','host','port','method','scope','destination']:previous.need(request[key]==plan[key],'EXACT_'+key.upper())
        previous.need(request['host']==u.hostname and type(request['port']) is int and request['port']==443 and request['method']=='GET','HOST_PORT_METHOD')
        previous.need(type(plan['max_GET']) is int and type(plan['remaining_GET']) is int and 0<plan['remaining_GET']<=plan['max_GET']==1,'GET_BUDGET')
        previous.need(all(type(plan[k]) is int and plan[k]==0 for k in ['redirect','retry','parallel']),'NO_REDIRECT_RETRY_PARALLEL')
        times=[datetime.fromisoformat(x) for x in [plan['issued_UTC'],now_UTC,plan['expires_UTC']]]
        previous.need(all(x.utcoffset() is not None and x.utcoffset().total_seconds()==0 for x in times) and times[0]<=times[1]<times[2],'UTC_EXPIRY')
        destination=PurePosixPath(plan['destination'])
        previous.need(type(plan['destination']) is str and not destination.is_absolute() and '..' not in destination.parts and
                      destination.parts and destination.parts[0]=='sandbox' and '\\' not in plan['destination'] and ':' not in plan['destination'],'SYNTHETIC_DESTINATION')
        previous.need(type(request['body_bytes']) is int and type(plan['body_cap']) is int and 0<=request['body_bytes']<=plan['body_cap']<=65536,'BODY_CAP')
        out.update(decision='ALLOW',reason='SYNTHETIC_PLAN_ONLY_NO_EXECUTION_AUTHORITY')
    except (previous.Uncertain,ValueError,TypeError,KeyError,AttributeError) as exc:
        out.update(decision='DENY',reason=str(exc))
    return out


def communication_check(layer1,permit,evidence_policy,*,site_access_conditions_verified=False):
    """Layer3 is a pure logical candidate, never a live execution grant."""
    robots=layer1.get('decision') if type(layer1) is dict else None
    permitted=permit.get('decision') if type(permit) is dict else None
    evidence=evidence_policy.get('decision') if type(evidence_policy) is dict else None
    candidate=(robots=='ALLOW' and permitted=='ALLOW' and evidence=='ALLOW' and
               site_access_conditions_verified is True and layer1.get('safety_stop') is False and
               permit.get('real_permit_issued') is False and permit.get('execution_authorized') is False)
    return dict(robots_decision=robots,permit_decision=permitted,evidence_policy_decision=evidence,
        site_access_conditions_verified=site_access_conditions_verified is True,
        communication_candidate=candidate,execution_authorized=False,B_authorized=False,history_admission=False)
