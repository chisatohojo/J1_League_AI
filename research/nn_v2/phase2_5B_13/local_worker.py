"""Research local byte worker. No HTTP/socket client or live network mode."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def digest(data):return hashlib.sha256(data).hexdigest()


def encoded(value):return (json.dumps(value,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode('utf8')


def main():
    # The descendant fault mode only sleeps, within its inherited owned job.
    if len(sys.argv)==2 and sys.argv[1]=='--sleep-only':
        time.sleep(60);return
    if len(sys.argv)!=4 or sys.argv[1]!='--task':raise ValueError('LOCAL_TASK_ONLY')
    task_path=Path(sys.argv[2]);task_bytes=task_path.read_bytes()
    if digest(task_bytes)!=sys.argv[3]:raise ValueError('TASK_SHA')
    task=json.loads(task_bytes);out=Path(task['output']);sources=task['sources']
    if out!=task_path.parent/'worker-output' or not out.is_dir() or any(out.iterdir()):raise ValueError('NEW_LOCAL_OUTPUT_REQUIRED')
    if task['kind']!='LOCAL_BYTES_ONLY' or set(sources)!={'raw','metadata','request'}:raise ValueError('NO_TRANSPORT_MODE')
    reads={str(Path(v['path']).resolve()) for v in sources.values()}
    root=task_path.parent.resolve()
    def guard(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.bind','http.client.connect','urllib.Request','pickle.find_class'}:
            raise RuntimeError('LOCAL_WORKER_NETWORK_OR_MODEL_FORBIDDEN')
        if event=='open':
            p,mode,flags=args
            if isinstance(p,int):return
            target=Path(os.fsdecode(p)).resolve()
            writing=(mode and any(c in mode for c in 'wax+')) or flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)
            if writing:
                if not target.is_relative_to(root):raise RuntimeError('WORKER_WRITE_OUTSIDE_LOCAL_ROOT')
            elif str(target) not in reads and not target.is_relative_to(root):raise RuntimeError('WORKER_UNAPPROVED_READ')
        if event=='subprocess.Popen':
            allowed=[sys.executable,'-B',str(Path(__file__).resolve()),'--sleep-only']
            if task['fault']!='spawn-child-exit' or args[1] not in (allowed,subprocess.list2cmdline(allowed)):raise RuntimeError('ONLY_OWNED_SLEEP_DESCENDANT_FAULT_ALLOWED')
    sys.addaudithook(guard)
    fault=task['fault']
    if fault=='audit-network-probe':sys.audit('socket.connect',None,('synthetic-no-connection',0))
    if fault=='audit-outside-write-probe':
        with (root.parent/'outside-worker-probe').open('xb') as f:f.write(b'forbidden')
    if fault=='sleep':time.sleep(60);return
    if fault=='exit-nonzero':os._exit(17)
    if fault=='spawn-child-exit':
        child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--sleep-only'],creationflags=0x08000000)
        # Child inherits membership; this file is local test evidence, never a receipt.
        with (out/'descendant.json').open('xb') as f:f.write(encoded({'PID':child.pid}));f.flush();os.fsync(f.fileno())
        return
    blobs={}
    for name,spec in sources.items():
        data=Path(spec['path']).read_bytes()
        if digest(data)!=spec['SHA256']:raise ValueError('SOURCE_BYTE_SHA')
        if name=='raw' and len(data)>2097152:raise ValueError('LOCAL_RAW_CAP')
        if name!='raw' and len(data)>262144:raise ValueError('LOCAL_METADATA_CAP')
        blobs[name]=data
    if fault in {'partial-raw','partial-metadata'}:
        name='raw' if fault=='partial-raw' else 'metadata'
        with (out/(name+'.partial')).open('xb') as f:f.write(blobs[name][:len(blobs[name])//2]);f.flush();os.fsync(f.fileno())
        os._exit(23)
    if fault!='copy':raise ValueError('UNREVIEWED_LOCAL_FAULT')
    result=encoded({'kind':'LOCAL_BYTE_RESULT','task_SHA256':digest(task_bytes),'PID':os.getpid(),
        'blobs':{k:base64.b64encode(v).decode('ascii') for k,v in blobs.items()},'network_GET':0})
    with (out/'result.json').open('xb') as f:f.write(result);f.flush();os.fsync(f.fileno())
    if (out/'result.json').read_bytes()!=result:raise ValueError('LOCAL_RESULT_READBACK')
    receipt=encoded({'result_SHA256':digest(result),'task_SHA256':digest(task_bytes),'PID':os.getpid(),
        'completed_epoch_ns':time.time_ns(),'result_file_fsync_readback':True,'network_GET':0})
    with (out/'worker-receipt.json').open('xb') as f:f.write(receipt);f.flush();os.fsync(f.fileno())
    if (out/'worker-receipt.json').read_bytes()!=receipt:raise ValueError('LOCAL_RECEIPT_READBACK')


if __name__=='__main__':main()
