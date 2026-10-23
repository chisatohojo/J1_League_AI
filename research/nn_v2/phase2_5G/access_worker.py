"""One approved conditions GET, in a parent-owned Job. No retries or redirects."""
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import time

URLS=('https://www.jleague.jp/robots.txt','https://aboutj.jleague.jp/robots.txt',
      'https://www.jleague.jp/general/kiyaku/','https://www.jleague.jp/general/copyright/')
CAPS=(65536,65536,1048576,1048576)
HOSTS=('www.jleague.jp','aboutj.jleague.jp','www.jleague.jp','www.jleague.jp')
PATHS=('/robots.txt','/robots.txt','/general/kiyaku/','/general/copyright/')
AGENT='J1AI-Research-Timing-Pilot/1.0'


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def encoded(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')


def validate(permit,task,at):
    require(permit['kind']=='NNV2_G_A_ONLY_SINGLE_RUN_V1','A_ONLY_PERMIT')
    require(permit['scope']=='ACCESS_CONDITIONS_ONLY' and permit['max_GET']==4 and permit['B_GET']==0,'SCOPE_CAP')
    require(permit['URLs']==list(URLS) and permit['body_caps']==list(CAPS),'EXACT_URL_CAPS')
    require(permit['total_body_cap']==sum(CAPS) and permit['header_cap']==32768,'TOTAL_CAP')
    require(permit['retry']==permit['redirect']==permit['parallel']==0,'NO_RETRY_REDIRECT_PARALLEL')
    require(permit['socket_deadline']==10 and permit['parent_deadline']==12 and permit['global_deadline']==120
            and permit['interval']==5 and permit['cleanup_deadline']==2,'FIXED_DEADLINES')
    require(datetime.fromisoformat(permit['issued_UTC'])<=datetime.fromisoformat(at)<datetime.fromisoformat(permit['expires_UTC']),'PERMIT_TIME')
    require(task['kind']=='G_APPROVED_ONE_GET' and type(task['ordinal']) is int and 1<=task['ordinal']<=4,'TASK_KIND_ORDER')
    i=task['ordinal']-1
    require(task['URL']==URLS[i] and task['id']=='A'+str(i+1),'EXACT_TASK_URL')
    return i


class HeaderReader:
    """Cap received status/header lines before http.client parses them."""
    def __init__(self,fp):self.fp=fp;self.count=0;self.raw=bytearray()
    def readline(self,limit=-1):
        remain=32768-self.count
        require(remain>0,'HEADER_CAP')
        line=self.fp.readline(min(remain,limit) if limit>=0 else remain)
        self.count+=len(line);self.raw.extend(line)
        require(not line or line.endswith(b'\n'),'HEADER_LINE_TRUNCATED_AT_CAP')
        return line


class BoundedResponse(http.client.HTTPResponse):
    def begin(self):
        original=self.fp;reader=HeaderReader(original);self.header_reader=reader
        self.fp=reader
        try:super().begin()
        finally:self.fp=original


def fetch_once(i,context,evidence,*,factory=None,clock=time.monotonic):
    """Injection exists only for synthetic in-process tests, never the CLI."""
    require(type(i) is int and 0<=i<4,'EXACT_TARGET_INDEX')
    require(context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED,'TLS_REQUIRED')
    host=HOSTS[i];cap=CAPS[i];started=clock()
    evidence.update(body=bytearray(),headers=[],complete_body=False,TLS=None,HTTP_status=None,
                    DNS_resolution_calls=0,TCP_connect_calls=0,request_calls=0)
    class SingleConnection(http.client.HTTPSConnection):
        response_class=BoundedResponse
        def connect(self):
            require(evidence['TCP_connect_calls']==0,'CONNECT_RETRY_FORBIDDEN')
            evidence['DNS_resolution_calls']+=1
            addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            require(bool(addresses),'DNS_NO_ADDRESS')
            family,kind,proto,_,address=addresses[0]
            evidence['TCP_connect_calls']+=1
            remaining=10-(clock()-started);require(remaining>0,'WORKER_WALL_DEADLINE')
            wire=socket.socket(family,kind,proto);wire.settimeout(remaining)
            try:
                wire.connect(address)
                remaining=10-(clock()-started);require(remaining>0,'WORKER_WALL_DEADLINE')
                wire.settimeout(remaining);self.sock=context.wrap_socket(wire,server_hostname=host)
            except BaseException:wire.close();raise
    conn=(factory or SingleConnection)(host,443,timeout=10,context=context)
    conn.auto_open=0
    try:
        conn.connect()
        require(conn.sock is not None,'TLS_SOCKET_MISSING')
        evidence['TLS']=dict(verified=True,hostname_verified=True,server_hostname=host,
            version=conn.sock.version(),cipher=conn.sock.cipher(),peer_certificate_SHA256=sha(conn.sock.getpeercert(binary_form=True)),
            check_hostname=context.check_hostname,verify_mode=int(context.verify_mode))
        evidence['request_calls']+=1
        conn.request('GET',PATHS[i],headers={'Host':host,'User-Agent':AGENT,'Accept-Encoding':'identity','Connection':'close'})
        response=conn.getresponse()
        evidence['HTTP_status']=response.status
        evidence['headers']=response.getheaders()
        if hasattr(response,'header_reader'):evidence['raw_status_headers']=bytes(response.header_reader.raw)
        # Preserve all response headers privately; they are never replayed.
        normalized={}
        for key,value in evidence['headers']:
            low=key.lower()
            if low in {'content-length','content-encoding','location'}:require(low not in normalized,'DUPLICATE_CRITICAL_HEADER')
            normalized[low]=value
        require(sum(len(k.encode('latin1'))+len(v.encode('latin1'))+4 for k,v in evidence['headers'])<=32768,'HEADER_CAP')
        require(normalized.get('content-encoding','identity').lower() in {'identity',''},'UNKNOWN_ENCODING')
        length=normalized.get('content-length')
        if length is not None:
            require(length.isascii() and length.isdigit() and int(length)<=cap,'BODY_CONTENT_LENGTH_CAP')
        while True:
            remaining=10-(clock()-started);require(remaining>0,'WORKER_WALL_DEADLINE')
            if conn.sock is not None:conn.sock.settimeout(remaining)
            available=cap-len(evidence['body'])
            if available==0:
                require(response.isclosed() or (length is not None and len(evidence['body'])==int(length)), 'BODY_CAP_COMPLETION_UNKNOWN')
                break
            chunk=response.read1(min(16384,available))
            require(len(chunk)<=available,'BODY_CAP')
            evidence['body'].extend(chunk)
            if not chunk:break
        require(clock()-started<=10,'WORKER_WALL_DEADLINE')
        if length is not None:require(len(evidence['body'])==int(length),'INCOMPLETE_BODY')
        evidence['complete_body']=True
    finally:conn.close()


def main():
    require(len(sys.argv)==4 and sys.argv[1]=='--task','TASK_ONLY_NO_GENERAL_URL_CLI')
    task_path=Path(sys.argv[2]);task_bytes=task_path.read_bytes();require(sha(task_bytes)==sys.argv[3],'TASK_SHA')
    task=json.loads(task_bytes);permit_path=Path(task['permit_path']);permit_bytes=permit_path.read_bytes()
    require(sha(permit_bytes)==task['permit_SHA256'],'PERMIT_SHA')
    permit=json.loads(permit_bytes);i=validate(permit,task,now())
    for name,pin in permit['code_files'].items():require(sha(Path(name).read_bytes())==pin,'CODE_SHA')
    # No old executor/collector is imported. Windows storage/Job primitives only.
    sys.path.insert(0,permit['windows_module_directory'])
    from windows_local import DirectoryLease,acl_audit,write_new_locked
    root=task_path.parent;out=root
    require(root.absolute()==Path(permit['output_root']).absolute()/'A'/('access-'+str(i+1).zfill(4)),'OUTPUT_BINDING')
    require({p.name for p in out.iterdir()}=={'task.json','consumed-intent.json'},'EXCLUSIVE_OUTPUT_NO_REPLAY')
    consumed=json.loads(Path(permit['consumed_marker']).read_bytes())
    require(consumed['permit_SHA256']==sha(permit_bytes),'CONSUMED_PERMIT_BINDING')
    context=ssl.create_default_context()
    expected_host=HOSTS[i]
    def guard(event,args):
        if event in {'subprocess.Popen','os.system','pickle.find_class','socket.bind','socket.sendto','urllib.Request'}:raise RuntimeError('WORKER_BOUNDARY')
        if event=='socket.getaddrinfo':require(args[0]==expected_host and args[1]==443,'DNS_ONLY_INSIDE_APPROVED_CONNECTION')
        if event=='http.client.connect':require(args[1]==expected_host and args[2]==443,'HTTP_HOST')
        if event=='open' and not isinstance(args[0],int):
            path,mode,flags=args
            if (mode and any(c in mode for c in 'wax+')) or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
                require(Path(os.fsdecode(path)).absolute().is_relative_to(root.absolute()),'WRITE_BOUNDARY')
    sys.addaudithook(guard)
    with DirectoryLease(root),DirectoryLease(out):
        acl_audit(root);acl_audit(out)
        req=dict(request_id=task['request_id'],permit_id=permit['permit_id'],id=task['id'],url=URLS[i],method='GET',
                 request_started_UTC=now(),PID=os.getpid(),permit_SHA256=sha(permit_bytes),task_SHA256=sha(task_bytes),
                 proxy_used=False,redirect=0,retry=0,TLS_verification=True)
        req_bytes=encoded(req);write_new_locked(out/'request.json',req_bytes)
        write_new_locked(out/'connection-started.json',encoded(dict(UTC=now(),url=URLS[i],GET_attempt_charged=1)))
        evidence={};error=None
        try:fetch_once(i,context,evidence)
        except BaseException as exc:error=type(exc).__name__+':'+str(exc)
        completed=now();body=bytes(evidence.pop('body',b''));raw_headers=evidence.pop('raw_status_headers',b'')
        write_new_locked(out/'raw.bin',body)
        write_new_locked(out/'status-headers.bin',raw_headers)
        metadata=dict(requested_url=URLS[i],actual_response_url=URLS[i] if evidence.get('HTTP_status') is not None else None,
            request_id=task['request_id'],permit_id=permit['permit_id'],id=task['id'],PID=os.getpid(),
            request_started_UTC=req['request_started_UTC'],response_completed_UTC=completed,
            snapshot_saved_UTC=now(),raw_SHA256=sha(body),bytes=len(body),request_SHA256=sha(req_bytes),
            redirect_history=[],redirect_follow=0,retry=0,proxy_used=False,error=error,**evidence)
        md=encoded(metadata);write_new_locked(out/'metadata.json',md)
        write_new_locked(out/'worker-receipt.json',encoded(dict(PID=os.getpid(),request_id=task['request_id'],
            permit_SHA256=sha(permit_bytes),task_SHA256=sha(task_bytes),raw_SHA256=sha(body),metadata_SHA256=sha(md),
            request_SHA256=sha(req_bytes),status_headers_SHA256=sha(raw_headers),GET_attempt_charged=1,
            receipt_completed_UTC=now(),fsync_readback=True,error=error)))
        if error:raise RuntimeError('SINGLE_ATTEMPT_FAILED_NO_RETRY')


if __name__=='__main__':main()
