"""Pure offline evidence/policy checks, never a network or permit API."""
from datetime import datetime
import hashlib
import json
import re
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

URLS=('https://www.jleague.jp/robots.txt','https://aboutj.jleague.jp/robots.txt',
      'https://www.jleague.jp/general/kiyaku/','https://www.jleague.jp/general/copyright/')
CAPS=(65536,65536,1048576,1048576)
AGENT='J1AI-Research-Timing-Pilot/1.0'


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(b):return hashlib.sha256(b).hexdigest()


def verify_response(i,raw,md_bytes,req_bytes,receipt):
    md=json.loads(md_bytes);req=json.loads(req_bytes)
    require(type(i) is int and 0<=i<4,'A_ONLY')
    require(receipt['raw_SHA256']==md['raw_SHA256']==sha(raw),'RAW_SHA')
    require(receipt['metadata_SHA256']==sha(md_bytes) and receipt['request_SHA256']==md['request_SHA256']==sha(req_bytes),'MD_REQUEST_SHA')
    require(req['url']==md['requested_url']==URLS[i] and md['actual_response_url'] in {None,URLS[i]},'EXACT_RESPONSE_URL')
    require(req['request_id']==md['request_id']==receipt['request_id'] and req['PID']==md['PID']==receipt['PID'],'REQUEST_PROCESS_BINDING')
    require(req['method']=='GET' and md['bytes']==len(raw)<=CAPS[i],'METHOD_BODY_CAP')
    require(md['redirect_follow']==md['retry']==0 and md['redirect_history']==[] and not md['proxy_used'],'NO_REDIRECT_RETRY_PROXY')
    times=[datetime.fromisoformat(v) for v in [req['request_started_UTC'],md['response_completed_UTC'],md['snapshot_saved_UTC'],receipt['receipt_completed_UTC']]]
    require(all(x.utcoffset().total_seconds()==0 for x in times) and times==sorted(times),'UTC_ORDER')
    require((times[1]-times[0]).total_seconds()<=10,'SOCKET_DEADLINE')
    stop=None
    if md.get('error'):stop='COMMUNICATION_FAILURE'
    elif md['HTTP_status']!=200:stop='HTTP_ERROR_OR_REDIRECT'
    elif not md['complete_body']:stop='INCOMPLETE_BODY'
    else:
        tls=md['TLS'];host=urlsplit(URLS[i]).hostname
        require(tls['verified'] and tls['hostname_verified'] and tls['server_hostname']==host,'TLS_BINDING')
    return dict(status='STOP' if stop else 'SEALED_RESPONSE',reason=stop,HTTP_status=md['HTTP_status'],
                bytes=len(raw),SHA256=sha(raw),history_admission=False,B_authorized=False)


def review_robots(raw,*,host):
    require(host in {'www.jleague.jp','aboutj.jleague.jp'},'HOST')
    try:text=raw.decode('utf-8-sig')
    except UnicodeError:return dict(status='HOLD',reason='UNKNOWN_ENCODING',content_permission='UNKNOWN')
    if '<html' in text.lower() or '<!doctype' in text.lower():return dict(status='HOLD',reason='HTML_NOT_ROBOTS',content_permission='UNKNOWN')
    directives=[];unknown=[]
    for line in text.splitlines():
        line=line.split('#',1)[0].strip()
        if not line:continue
        if ':' not in line:unknown.append(line);continue
        k,v=line.split(':',1);key=k.strip().lower();value=v.strip()
        if key not in {'user-agent','allow','disallow','sitemap','crawl-delay','request-rate'}:unknown.append(line)
        if key in {'allow','disallow'} and ('*' in value or '$' in value):unknown.append('UNVERIFIED_PATTERN:'+line)
        directives.append(dict(name=key,value=value))
    if unknown:return dict(status='HOLD',reason='UNKNOWN_OR_UNSUPPORTED_ROBOTS_DIRECTIVE',directives=directives,unknown=unknown,content_permission='UNKNOWN')
    parser=RobotFileParser();parser.parse(text.splitlines())
    affected=[URLS[2],URLS[3],'https://www.jleague.jp/j1/news/'] if host=='www.jleague.jp' else ['https://aboutj.jleague.jp/corporate/pressrelease/']
    findings={u:parser.can_fetch(AGENT,u) for u in affected}
    delay=parser.crawl_delay(AGENT);rate=parser.request_rate(AGENT)
    # Unknown scheduling directives cannot silently relax a five-second plan.
    schedule_unknown=any(d['name'] in {'crawl-delay','request-rate'} for d in directives) and delay is None and rate is None
    strict=delay is not None and delay>5 or rate is not None and rate.seconds/rate.requests>5
    return dict(status='HOLD' if not all(findings.values()) or strict or schedule_unknown else 'ROBOTS_PATH_REVIEW_ONLY',
        reason='DENIAL_OR_STRICT_OR_UNKNOWN_RATE' if not all(findings.values()) or strict or schedule_unknown else None,
        directives=directives,applied_agent=AGENT,path_findings=findings,crawl_delay=delay,
        request_rate=None if rate is None else dict(requests=rate.requests,seconds=rate.seconds),
        applicable_host=host,content_permission='UNKNOWN',terms_permission='UNKNOWN',B_authorized=False)
