"""Pure offline evidence/policy checks, never a network or permit API."""
from datetime import datetime
import hashlib
import json
import re
from urllib.parse import urlsplit

URLS=('https://www.rfc-editor.org/rfc/rfc9309.html',
      'https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec?hl=ja')
CAPS=(2097152,2097152)
AGENT='J1AI-Research-Timing-Pilot/1.0'


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(b):return hashlib.sha256(b).hexdigest()


def verify_response(i,raw,md_bytes,req_bytes,receipt):
    md=json.loads(md_bytes);req=json.loads(req_bytes)
    require(type(i) is int and 0<=i<2,'A_ONLY')
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

