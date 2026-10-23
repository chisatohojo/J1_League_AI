"""Pure provisional robots evaluator. Not an RFC-conformance assertion.

Authoritative RFC/Google specification snapshots have not been found locally.
Real-source decisions remain UNKNOWN. Synthetic experiments expose candidate
semantics for review; no result grants network, permit or history authority.
Neither this evaluator nor its draft profile is imported by the HTTP executor.
"""
import hashlib
import re
from urllib.parse import urlsplit
from urllib.robotparser import Entry as LocalLegacyAgentMatcher

VERSION='nn_v2_robots_offline_draft_v1'
EVIDENCE_PROFILE='J1AI_EVIDENCE_FAIL_CLOSED_DRAFT_V1'
SYNTHETIC_PROFILE='J1AI_SYNTHETIC_PATTERN_EXPERIMENT_V1'
FIXED_AGENT='J1AI-Research-Timing-Pilot/1.0'
A1_SHA='3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c'
HOSTS=frozenset({'www.jleague.jp','aboutj.jleague.jp'})
SPECIFICATION_SNAPSHOTS_VERIFIED=False
UNRESERVED=frozenset(b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~')


class Uncertain(ValueError):
    pass


def need(condition,reason):
    if not condition:raise Uncertain(reason)


def octets(value,*,pattern=False):
    """Draft canonical octets; encoded reserved octets stay distinct from raw.

    No Unicode normalization, URL rewriting, unquote-all or regex fallback.
    '*' is a wildcard only as a literal pattern character. Encoded %2A is data.
    """
    need(type(value) is str and len(value)<=8192,'COMPONENT_LENGTH_OR_TYPE')
    anchored=False
    if pattern:
        need(value.startswith('/'),'PATTERN_MUST_START_SLASH')
        need(value.count('$')<=1 and ('$' not in value or value.endswith('$')),'AMBIGUOUS_ANCHOR')
        if value.endswith('$'):anchored=True;value=value[:-1]
        need(value.count('*')<=32,'WILDCARD_COMPLEXITY_CAP')
    result=[];i=0
    while i<len(value):
        ch=value[i]
        need(not ch.isspace() and ord(ch)>=32 and ord(ch)!=127 and ch!='\\','UNESCAPED_WHITESPACE_OR_CONTROL')
        if ch=='%':
            need(i+2<len(value) and re.fullmatch('[0-9A-Fa-f]{2}',value[i+1:i+3]) is not None,'INVALID_PERCENT_ENCODING')
            b=int(value[i+1:i+3],16)
            result.append(b if b in UNRESERVED else ('encoded',b));i+=3
        elif pattern and ch=='*':result.append('wildcard');i+=1
        else:
            for b in ch.encode('utf8'):result.append(b if b<128 else ('encoded',b))
            i+=1
    return tuple(result),anchored


def match_pattern(pattern,path_tokens,*,work_limit=1000000):
    tokens,anchor=octets(pattern,pattern=True)
    need(len(tokens)<=2048 and len(path_tokens)<=8192,'MATCH_SIZE_CAP')
    positions={0};work=0
    for token in tokens:
        work+=len(positions)
        need(work<=work_limit,'MATCH_WORK_CAP')
        if not positions:break
        if token=='wildcard':positions=set(range(min(positions),len(path_tokens)+1))
        else:positions={p+1 for p in positions if p<len(path_tokens) and path_tokens[p]==token}
    return (len(path_tokens) in positions if anchor else bool(positions)),sum(t!='wildcard' for t in tokens),work


def parse_saved(raw):
    need(type(raw) is bytes and 0<len(raw)<=65536,'EMPTY_OR_OVERSIZE_ROBOTS')
    text=raw.decode('utf-8-sig')
    need(not any(ord(c)<32 and c not in '\t\r\n' or ord(c)==127 for c in text),'CONTROL_CHARACTER')
    need('<html' not in text.lower() and '<!doctype' not in text.lower(),'HTML_NOT_ROBOTS')
    lines=text.replace('\r\n','\n').replace('\r','\n').split('\n')
    need(len(lines)<=4096,'LINE_CAP')
    groups=[];agents=[];rules=[];annotations=[];uncertain=[];has_rule=False
    def finish():
        if agents:groups.append(dict(group=len(groups)+1,agents=list(agents),rules=list(rules)))
    for number,line in enumerate(lines,1):
        line=line.split('#',1)[0].strip(' \t')
        if not line:continue
        if ':' not in line:uncertain.append(dict(line=number,reason='MALFORMED_DIRECTIVE'));continue
        key,value=line.split(':',1);key=key.strip(' \t').lower();value=value.strip(' \t')
        if key=='user-agent':
            if has_rule:finish();agents=[];rules=[];has_rule=False
            if not re.fullmatch(r'\*|[A-Za-z0-9_-]+',value):uncertain.append(dict(line=number,reason='UNKNOWN_AGENT_GRAMMAR'))
            else:agents.append(value)
        elif key in {'allow','disallow'}:
            if not agents:uncertain.append(dict(line=number,reason='RULE_WITHOUT_AGENT'));continue
            has_rule=True
            if not value:continue
            try:octets(value,pattern=True)
            except Uncertain as exc:uncertain.append(dict(line=number,reason=str(exc)));continue
            rules.append(dict(directive=key,pattern=value,line=number))
        elif key=='sitemap':
            annotations.append(dict(directive=key,value=value,line=number,resource_fetched=False))
        else:uncertain.append(dict(line=number,reason='UNKNOWN_DIRECTIVE',directive=key))
    finish()
    need(bool(groups),'NO_AGENT_GROUP')
    need(sum(len(g['rules']) for g in groups)<=1000,'RULE_CAP')
    return groups,annotations,uncertain


def local_agent_selection(groups,user_agent):
    """Reuse inspected CPython legacy applicability, not a new substring rule.

    Longest token selection/merging below is an explicitly synthetic draft.
    CPython is not represented as RFC 9309 or Google conformance evidence.
    """
    need(type(user_agent) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)?',user_agent) is not None,'MISSING_OR_UNSUPPORTED_USER_AGENT')
    scored=[]
    for group in groups:
        scores=[]
        for agent in group['agents']:
            if agent=='*':continue
            entry=LocalLegacyAgentMatcher();entry.useragents=[agent]
            if entry.applies_to(user_agent):scores.append(len(agent.encode('ascii')))
        if scores:scored.append((max(scores),group))
    if scored:
        longest=max(s for s,g in scored)
        return [g for s,g in scored if s==longest],'LOCAL_LEGACY_APPLICABILITY_LONGEST_DRAFT'
    return [g for g in groups if '*' in g['agents']],'WILDCARD_GROUP_DRAFT'


def evaluate(raw,*,source_host,target_url,user_agent,parser_version,profile,expected_raw_SHA256):
    """Fail-closed evidence API; only synthetic.invalid can expose draft ALLOW.

    This deliberately cannot be switched into an evidence-authorizing profile
    by a caller assertion or root/host change. A new reviewed version is needed.
    """
    digest=hashlib.sha256(raw).hexdigest() if type(raw) is bytes else None
    result=dict(decision='UNKNOWN',candidate_decision=None,reason=None,parser_version=VERSION,
        requested_parser_version=parser_version,profile=profile,raw_SHA256=digest,
        specification_snapshots_verified=False,applied_groups=[],matched_rules=[],
        source_host=source_host,target_URL=target_url,user_agent=user_agent,
        execution_authorized=False,B_authorized=False,history_admission=False,safety_stop=False)
    try:
        need(parser_version==VERSION,'PARSER_VERSION_MISMATCH')
        need(profile in {EVIDENCE_PROFILE,SYNTHETIC_PROFILE},'UNKNOWN_PROFILE')
        need(type(expected_raw_SHA256) is str and re.fullmatch('[a-f0-9]{64}',expected_raw_SHA256) is not None and digest==expected_raw_SHA256,'RAW_SHA_MISMATCH')
        allowed={'synthetic.invalid'} if profile==SYNTHETIC_PROFILE else HOSTS
        need(source_host in allowed,'UNEXPECTED_HOST_OR_SYNTHETIC_PROFILE_ON_REAL_SOURCE')
        need(digest!=A1_SHA or source_host=='www.jleague.jp','SEALED_A1_HOST_MISMATCH')
        need(type(target_url) is str and '#' not in target_url and not re.search(r'[\x00-\x20\\]',target_url),'UNSAFE_URL')
        url=urlsplit(target_url)
        need(url.scheme=='https' and url.netloc==source_host and not url.username and not url.password
             and not url.fragment and not url.port,'EXACT_HTTPS_ORIGIN_REQUIRED')
        need(profile!=EVIDENCE_PROFILE or user_agent==FIXED_AGENT,'FIXED_EVIDENCE_AGENT_REQUIRED')
        uri=url.path or '/'
        need(not any(s in {'.','..'} for s in url.path.split('/')),'DOT_SEGMENTS_REQUIRE_REVIEW')
        if '?' in target_url:uri+='?'+url.query
        tokens,_=octets(uri)
        groups,annotations,uncertain=parse_saved(raw)
        result['annotations']=annotations;result['unresolved_syntax']=uncertain
        need(not uncertain,'UNRESOLVED_DIRECTIVES_OR_PATTERNS')
        selected,selection=local_agent_selection(groups,user_agent)
        result['applied_groups']=[dict(group=g['group'],agents=g['agents']) for g in selected]
        result['agent_selection_basis']=selection
        work=0;matches=[]
        for group in selected:
            for rule in group['rules']:
                matched,length,cost=match_pattern(rule['pattern'],tokens,work_limit=1000000-work)
                work+=cost
                if matched:matches.append(dict(rule,group=group['group'],specificity_octets=length))
        result['matched_rules']=matches
        if matches:
            length=max(r['specificity_octets'] for r in matches)
            winners=[r for r in matches if r['specificity_octets']==length]
            candidate='ALLOW' if any(r['directive']=='allow' for r in winners) else 'DENY'
            basis='LONGEST_CANONICAL_OCTETS_ALLOW_TIE_DRAFT'
        else:candidate='ALLOW';basis='NO_MATCHED_RULE_DRAFT'
        result.update(candidate_decision=candidate,candidate_basis=basis,work_units=work)
        if profile==SYNTHETIC_PROFILE:
            result.update(decision=candidate,reason='SYNTHETIC_DRAFT_SEMANTICS_ONLY')
        else:
            result.update(decision='UNKNOWN',reason='AUTHORITATIVE_SPECIFICATION_SNAPSHOTS_UNAVAILABLE')
    except (Uncertain,UnicodeError,ValueError,TypeError) as exc:
        result['reason']=str(exc) or type(exc).__name__
        if result['reason'] in {'RAW_SHA_MISMATCH','SEALED_A1_HOST_MISMATCH'}:result['safety_stop']=True
    return result
