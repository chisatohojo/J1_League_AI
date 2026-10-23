"""Two-specification single-use run. Sealed responses require an offline review checkpoint.

Never call an older acquisition launcher. No model, collector or B capability.
The sole task argument is a sealed private permit; there is no arbitrary URL CLI.
"""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from spec_worker import URLS,CAPS,encoded,sha,now,require,validate
from spec_contract import verify_response


def main():
    require(len(sys.argv)==3,'SEALED_PERMIT_ONLY')
    permit_path=Path(sys.argv[1]);permit_sha=sys.argv[2]
    raw_permit=permit_path.read_bytes();require(sha(raw_permit)==permit_sha,'PERMIT_SHA')
    permit=json.loads(raw_permit)
    validate(permit,dict(kind='I_APPROVED_ONE_GET',ordinal=1,URL=URLS[0],id='S1'),now())
    for name,pin in permit['code_files'].items():require(sha(Path(name).read_bytes())==pin,'CODE_SHA')
    sys.path.insert(0,permit['windows_module_directory'])
    from windows_local import DirectoryLease,acl_audit,read_bytes_locked,write_new_locked,secure_mkdir,open_handle,Close,OwnedJob
    root=Path(permit['output_root']);require(root.is_dir(),'PRECREATED_EXCLUSIVE_REVIEWED_ROOT')
    consumed=Path(permit['consumed_marker']);require(not consumed.exists(),'RUN_ALREADY_CONSUMED_NO_RESUME')
    held=[];ledger=[];stopped=None;last=None;start=time.monotonic();start_utc=now()
    def write(p,v):return write_new_locked(p,encoded(v))
    def remaining():return 90-(time.monotonic()-start)
    try:
        with DirectoryLease(root),DirectoryLease(permit_path.parent):
            acl_audit(root);acl_audit(root/'SPEC')
            for name in [*permit['code_files'],str(permit_path)]:held.append(open_handle(name,0x80000000,1,3))
            write(consumed,dict(permit_SHA256=permit_sha,permit_id=permit['permit_id'],UTC=start_utc,parent_PID=os.getpid(),single_use=True))
            for i,url in enumerate(URLS):
                try:
                    require(remaining()>14,'GLOBAL_DEADLINE_REMAINING')
                    require(datetime.now(timezone.utc)<datetime.fromisoformat(permit['expires_UTC']),'PERMIT_EXPIRED')
                    if last is not None:
                        delay=5-(time.monotonic()-last)
                        if delay>0:time.sleep(delay)
                    require(remaining()>14,'GLOBAL_DEADLINE_REMAINING')
                    for name,pin in permit['code_files'].items():require(sha(read_bytes_locked(name))==pin,'CODE_SHA')
                    acl_audit(root);slot=root/'SPEC'/('spec-'+str(i+1).zfill(4));secure_mkdir(slot)
                    with DirectoryLease(slot):
                        task=dict(kind='I_APPROVED_ONE_GET',ordinal=i+1,id='S'+str(i+1),URL=url,
                            request_id=permit['permit_id']+'-S'+str(i+1),permit_path=str(permit_path),permit_SHA256=permit_sha)
                        task_path=slot/'task.json';task_sha=write(task_path,task)['SHA256']
                        intent=dict(id=task['id'],url=url,UTC=now(),attempt_charged=1,task_SHA256=task_sha,
                                    outcome='UNKNOWN_UNTIL_RECEIPT',retry_allowed=False)
                        write(slot/'consumed-intent.json',intent)
                        ledger.append(intent)
                        write(root/('intent-ledger-'+str(i+1).zfill(4)+'.json'),dict(permit_SHA256=permit_sha,attempts=list(ledger)))
                        identity=None;observed=None;cleanup=None;active=None;response=None;error=None
                        with OwnedJob() as job:
                            try:
                                identity=job.start(['-B',permit['worker_path'],'--task',task_path,task_sha],slot)
                                observed=job.wait(min(12,remaining()))
                                settle=time.monotonic()+.2
                                while not observed['timed_out'] and job.active() and time.monotonic()<settle:time.sleep(.005)
                                require(not observed['timed_out'] and observed['exit_code']==0 and job.active()==0,'WORKER_TIMEOUT_EXIT_RESIDUE')
                                raw=read_bytes_locked(slot/'raw.bin',CAPS[i]);md=read_bytes_locked(slot/'metadata.json');req=read_bytes_locked(slot/'request.json')
                                receipt=json.loads(read_bytes_locked(slot/'worker-receipt.json'))
                                require(receipt['PID']==identity['PID'] and receipt['task_SHA256']==task_sha and receipt['permit_SHA256']==permit_sha,'OWNED_WORKER_RECEIPT')
                                headers=read_bytes_locked(slot/'status-headers.bin',32768)
                                require(sha(headers)==receipt['status_headers_SHA256'],'RAW_HEADERS_SHA')
                                response=verify_response(i,raw,md,req,receipt)
                                write(slot/'seal.json',dict(raw_SHA256=sha(raw),metadata_SHA256=sha(md),request_SHA256=sha(req),
                                    status_headers_SHA256=sha(headers),worker_receipt_SHA256=sha(read_bytes_locked(slot/'worker-receipt.json')),
                                    verified_UTC=now(),readback=True,history_admission=False))
                            except BaseException as exc:
                                error=type(exc).__name__+':'+str(exc)
                                if job.process:cleanup=job.cleanup(2)
                            active=job.active()
                            if active:cleanup=job.cleanup(2);active=job.active();error='OWNED_PROCESS_RESIDUE'
                        last=time.monotonic()
                        parent=dict(id=task['id'],url=url,request_id=task['request_id'],permit_SHA256=permit_sha,
                            identity=identity,observed_exit=observed,cleanup=cleanup,final_owned_active_processes=active,
                            response=response,error=error,parent_completed_UTC=now(),task_SHA256=task_sha)
                        write(slot/'parent-receipt.json',parent)
                        ledger[-1]=dict(intent,parent_receipt_SHA256=sha(read_bytes_locked(slot/'parent-receipt.json')),
                            outcome='STOP' if error or response is None or response['status']=='STOP' else 'SEALED_RESPONSE',response=response)
                        write(root/('response-ledger-'+str(i+1).zfill(4)+'.json'),dict(permit_SHA256=permit_sha,attempts=list(ledger)))
                        print('SEALED',task['id'],json.dumps(response),flush=True)
                        require(error is None and response is not None and response['status']=='SEALED_RESPONSE','HTTP_OR_EVIDENCE_GLOBAL_STOP')
                        require(sum(x['response']['bytes'] for x in ledger)<=sum(CAPS),'TOTAL_BODY_CAP')
                        # An analyst must inspect actual sealed bytes, never a guessed robots policy.
                        if i<1:
                            print('WAIT_OFFLINE_REVIEW',str(slot/'review.json'),flush=True)
                            while not (slot/'review.json').exists():
                                require(remaining()>14,'REVIEW_GLOBAL_DEADLINE');time.sleep(.05)
                            review=json.loads(read_bytes_locked(slot/'review.json'))
                            require(review['id']==task['id'] and review['raw_SHA256']==response['SHA256']
                                    and review['parent_receipt_SHA256']==sha(read_bytes_locked(slot/'parent-receipt.json')),'REVIEW_BINDING')
                            require(review['B_authorized'] is False and review['decision']=='NEXT_SPEC_CONDITIONS_ONLY','REVIEW_STOP')
                            write(slot/'review-confirmed.json',dict(SHA256=sha(read_bytes_locked(slot/'review.json')),UTC=now(),next_id='S'+str(i+2)))
                except BaseException as exc:
                    stopped=type(exc).__name__+':'+str(exc);break
            write(root/'final-receipt.json',dict(permit_id=permit['permit_id'],permit_SHA256=permit_sha,started_UTC=start_utc,
                completed_UTC=now(),elapsed_seconds=time.monotonic()-start,attempts=ledger,attempt_count=len(ledger),
                unused_budget_expired=2-len(ledger),stop_reason=stopped,all_future_reuse_forbidden=True,
                B_GET=0,history_admission=False))
            print('RUN_TERMINAL',len(ledger),stopped,flush=True)
    finally:
        for handle in held:Close(handle)
    return 2 if stopped else 0


if __name__=='__main__':raise SystemExit(main())
