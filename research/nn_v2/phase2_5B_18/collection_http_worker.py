"""Single approved GET for the 109-page collection run in an owned Windows job. No retry, redirect or replay mode."""
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import ssl
import sys
import time


HOST = 'data.j-league.or.jp'
AGENT = 'J1AI-Research-Timing-Pilot/1.0'
def encoded(v): return (json.dumps(v, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf8')
def sha(v): return hashlib.sha256(v).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()
def require(ok, reason):
    if not ok: raise ValueError(reason)


def validate(permit, task):
    require(permit['version']=='real_http_collection109_v1' and permit['host']==HOST, 'PERMIT_KIND_HOST')
    kind=permit['kind']; rows=permit['rows']
    require(kind in {'DETAIL','ROBOTS'}, 'PERMIT_KIND')
    require(len(rows)==(109 if kind=='DETAIL' else 1) and permit['max_GET']==len(rows), 'PERMIT_CAP')
    urls=[r['url'] for r in rows]
    require(len(set(urls))==len(urls) and len({r['identity'] for r in rows})==len(rows), 'DUPLICATE')
    for r in rows:
        if kind=='ROBOTS': require(r['url']=='https://'+HOST+'/robots.txt' and r['identity']=='ROBOTS_EXACT_URL', 'ROBOTS_URL')
        else:
            hit=re.fullmatch(r'https://data\.j-league\.or\.jp/SFMS02/\?match_card_id=([1-9][0-9]*)',r['url'])
            require(hit is not None and hit[1]==r['data_site_match_id'], 'URL_ID')
    require(task['kind']=='APPROVED_SINGLE_GET' and type(task['ordinal']) is int and 1<=task['ordinal']<=len(rows), 'TASK_ORDINAL')
    require(task['row']==rows[task['ordinal']-1], 'TASK_ROW')
    require(permit['socket_timeout_seconds']==10 and permit['parent_deadline_seconds']==12 and permit['interval_seconds']>=5,
            'DEADLINE_RATE')
    require(permit['body_cap']==(2097152 if kind=='DETAIL' else 65536) and permit['total_body_cap']==permit['body_cap']*len(rows), 'BODY_CAP')
    require(permit['retry']==permit['redirect']==permit['parallel']==0, 'NO_RETRY_REDIRECT_PARALLEL')
    return task['row'], permit['body_cap']


def fetch_once(row, cap, context, *, connection_factory=None, clock=time.monotonic):
    """One request; dependency injection is used only by in-process synthetic tests."""
    require(context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED, 'TLS_VERIFY_REQUIRED')
    started=clock()
    class SingleAddressTLS(http.client.HTTPSConnection):
        def connect(self):
            addresses=socket.getaddrinfo(HOST,443,type=socket.SOCK_STREAM)
            require(bool(addresses),'NO_DNS_ADDRESS')
            family,kind,proto,_,address=addresses[0]
            remaining=10-(clock()-started); require(remaining>0,'WORKER_WALL_DEADLINE')
            wire=socket.socket(family,kind,proto); wire.settimeout(remaining)
            try:
                wire.connect(address)
                remaining=10-(clock()-started); require(remaining>0,'WORKER_WALL_DEADLINE')
                wire.settimeout(remaining)
                self.sock=context.wrap_socket(wire,server_hostname=HOST)
            except BaseException:
                wire.close(); raise
    conn=(connection_factory or SingleAddressTLS)(HOST,443,timeout=10,context=context)
    try:
        path=row['url'].removeprefix('https://'+HOST)
        conn.request('GET',path,headers={'User-Agent':AGENT,'Accept-Encoding':'identity','Connection':'close'})
        # Certificate and negotiated protocol are recorded before a close-delimited read.
        require(conn.sock is not None,'TLS_SOCKET_MISSING')
        tls={'verified':True,'hostname_verified':True,'server_hostname':HOST,'version':conn.sock.version(),
             'cipher':conn.sock.cipher(),'peer_certificate_SHA256':sha(conn.sock.getpeercert(binary_form=True)),
             'verify_mode':int(context.verify_mode),'check_hostname':context.check_hostname}
        response=conn.getresponse()
        headers={k.lower():v for k,v in response.getheaders() if k.lower() in {'content-type','content-length','content-encoding','location','retry-after'}}
        require(headers.get('content-encoding','identity').lower() in {'','identity'},'UNEXPECTED_CONTENT_ENCODING')
        if 'content-length' in headers: require(0<=int(headers['content-length'])<=cap,'BODY_CONTENT_LENGTH_CAP')
        body=bytearray()
        while True:
            remaining=10-(clock()-started); require(remaining>0,'WORKER_WALL_DEADLINE')
            if conn.sock is not None: conn.sock.settimeout(remaining)
            chunk=response.read(min(65536,cap+1-len(body)))
            if not chunk: break
            body.extend(chunk); require(len(body)<=cap,'BODY_CAP')
        require(clock()-started<=10,'WORKER_WALL_DEADLINE')
        if 'content-length' in headers: require(len(body)==int(headers['content-length']),'INCOMPLETE_BODY')
        return bytes(body), response.status, headers, tls
    finally: conn.close()


def main():
    require(len(sys.argv)==4 and sys.argv[1]=='--task','TASK_ONLY')
    task_path=Path(sys.argv[2]); task_bytes=task_path.read_bytes(); require(sha(task_bytes)==sys.argv[3],'TASK_SHA')
    task=json.loads(task_bytes); permit_path=Path(task['permit_path']); permit_bytes=permit_path.read_bytes()
    require(sha(permit_bytes)==task['permit_SHA256'],'PERMIT_SHA')
    permit=json.loads(permit_bytes); row,cap=validate(permit,task)
    root=task_path.parent.resolve(); out=root/'worker-output'
    require(out.is_dir() and not any(out.iterdir()),'EXCLUSIVE_OUTPUT')
    # Code and approval bytes are pinned before loading the Windows persistence layer.
    for name,pin in permit['code_files'].items(): require(sha(Path(name).read_bytes())==pin,'CODE_SHA')
    sys.path.insert(0,permit['windows_module_directory'])
    from windows_local import write_new_locked, DirectoryLease, acl_audit
    context=ssl.create_default_context(); require(context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED,'TLS_POLICY')
    def guard(event,args):
        if event in {'subprocess.Popen','os.system','pickle.find_class','socket.bind','urllib.Request'}: raise RuntimeError('WORKER_BOUNDARY')
        if event=='socket.getaddrinfo': require(args[0]==HOST and args[1]==443,'DNS_HOST')
        if event=='http.client.connect': require(args[1]==HOST and args[2]==443,'HTTP_HOST')
        if event=='open':
            p,mode,flags=args
            if isinstance(p,int): return
            writing=(mode and any(c in mode for c in 'wax+')) or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
            if writing: require(Path(os.fsdecode(p)).resolve().is_relative_to(root),'WRITE_BOUNDARY')
    sys.addaudithook(guard)
    with DirectoryLease(root),DirectoryLease(out):
        acl_audit(root); acl_audit(out)
        request={'url':row['url'],'identity':row['identity'],'method':'GET','request_started_at_utc':now(),
            'TLS_verification':True,'timeout_seconds':10,'automatic_retries':0,'redirects_followed':0,
            'permit_SHA256':sha(permit_bytes),'task_SHA256':sha(task_bytes),'PID':os.getpid()}
        request_bytes=encoded(request); write_new_locked(out/'request.json',request_bytes)
        # A durable consumed marker exists before DNS/connection. Never retried after uncertainty.
        write_new_locked(out/'connection-started.json',encoded({'UTC':now(),'url':row['url'],'max_GET':1}))
        try:
            raw,status,headers,tls=fetch_once(row,cap,context)
            completed=now(); write_new_locked(out/'raw.html',raw)
            meta={'requested_url':row['url'],'final_url':row['url'],'status':status,'success':status==200,
                'complete_body':True,'sha256':sha(raw),'bytes':len(raw),'request_sha256':sha(request_bytes),
                'request_started_at_utc':request['request_started_at_utc'],'response_completed_at_utc':completed,
                'snapshot_saved_at_utc':now(),'GET_attempts':1,'automatic_retries':0,'redirects_followed':0,
                'content_type':headers.get('content-type',''),'headers':headers,'TLS':tls}
            meta_bytes=encoded(meta); write_new_locked(out/'metadata.json',meta_bytes)
            write_new_locked(out/'worker-receipt.json',encoded({'PID':os.getpid(),'task_SHA256':sha(task_bytes),
                'permit_SHA256':sha(permit_bytes),'raw_SHA256':sha(raw),'metadata_SHA256':sha(meta_bytes),
                'request_SHA256':sha(request_bytes),'GET_attempts':1,'response_completed_at_utc':completed,
                'file_fsync_readback':True,'receipt_completed_at_utc':now()}))
        except BaseException as exc:
            write_new_locked(out/'failure.json',encoded({'reason':type(exc).__name__+':'+str(exc),
                'UTC':now(),'connection_started':True,'retry_permitted':False,'GET_upper_bound':1}))
            raise


if __name__=='__main__': main()
