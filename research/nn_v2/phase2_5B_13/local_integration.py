"""Local worker/Stage A/B integration. No HTTP worker, permits or runtime imports."""
import base64
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import time
from windows_local import DirectoryLease,OwnedJob,Close,open_handle,acl_audit,secure_mkdir,read_bytes_locked,write_new_locked


def encoded(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf8')
def sha(v):return hashlib.sha256(v).hexdigest()


def leased_store_class(offline):
    class LeasedStore(offline.ImmutableStore):
        def __init__(self,new_root,*,allowed_base):
            root=Path(os.path.abspath(new_root));base=Path(allowed_base).resolve()
            if not root.is_relative_to(base) or root==base:raise ValueError('OUTSIDE_APPROVED_LOCAL_TEST_AREA')
            self.base_lease=DirectoryLease(root.parent)
            try:
                self.acl=secure_mkdir(root);self.root=root;self.root_lease=DirectoryLease(root)
            except BaseException:self.base_lease.close();raise

        def _parent(self,relative):
            rel=Path(relative)
            if len(rel.parts)>2:raise ValueError('ONLY_FLAT_SEALED_BUNDLES')
            target=self.path(relative)
            if len(rel.parts)==2:
                try:target.parent.mkdir(exist_ok=False)
                except FileExistsError:pass
            return target

        def write(self,relative,data):
            if type(data) is not bytes:raise ValueError('BYTES_REQUIRED')
            acl_audit(self.root)
            p=self._parent(relative)
            with DirectoryLease(p.parent):result=write_new_locked(p,data)['SHA256']
            acl_audit(self.root)
            return result

        def read(self,relative):
            acl_audit(self.root)
            data=read_bytes_locked(self.path(relative))
            acl_audit(self.root)
            return data

        def close(self):
            self.root_lease.close();self.base_lease.close()
    return LeasedStore


class LocalManager:
    def __init__(self,new_root,*,allowed_base,worker_path,worker_sha,windows_sha):
        self.root=Path(os.path.abspath(new_root));base=Path(allowed_base).resolve()
        if not self.root.is_relative_to(base) or self.root==base:raise ValueError('OUTSIDE_LOCAL_TEST_ROOT')
        self.base_lease=DirectoryLease(self.root.parent)
        self.code_handles=[]
        try:
            self.acl=secure_mkdir(self.root);self.lease=DirectoryLease(self.root)
            self.worker=Path(worker_path).resolve()
            for p in [self.worker,self.worker.with_name('windows_local.py'),Path(__file__).resolve()]:
                self.code_handles.append(open_handle(p,0x80000000,1,3))
            if sha(self.worker.read_bytes())!=worker_sha:raise ValueError('WORKER_CODE_SHA')
            if sha(self.worker.with_name('windows_local.py').read_bytes())!=windows_sha:raise ValueError('WINDOWS_CODE_SHA')
            self.worker_sha=worker_sha;self.windows_sha=windows_sha;self.sequence=0;self.receipts=[];self.stopped=False;self.consumed=set()
            write_new_locked(self.root/'run-claim.json',encoded({'kind':'LOCAL_ONLY_SINGLE_USE','PID':os.getpid(),'at_epoch_ns':time.time_ns()}))
        except BaseException:
            if hasattr(self,'lease'):self.lease.close()
            for handle in self.code_handles:Close(handle)
            self.base_lease.close();raise

    def one(self,packet,*,fault='copy',deadline=10,cleanup_deadline=2):
        if self.stopped:raise RuntimeError('LOCAL_RUN_TERMINAL_NO_RESTART')
        try:return self._one(packet,fault=fault,deadline=deadline,cleanup_deadline=cleanup_deadline)
        except BaseException:self.stopped=True;raise

    def _one(self,packet,*,fault,deadline,cleanup_deadline):
        if not 0<deadline<=10:raise ValueError('LOCAL_WORKER_FINITE_MAX10_DEADLINE')
        acl_audit(self.root)
        if packet.row['url'] in self.consumed:raise RuntimeError('LOCAL_SOURCE_ALREADY_CONSUMED_NO_RETRY')
        self.consumed.add(packet.row['url'])
        self.sequence+=1
        folder=self.root/('worker-%04d'%self.sequence);secure_mkdir(folder)
        with DirectoryLease(folder),ExitStack() as held:
            output=folder/'worker-output';secure_mkdir(output)
            held.enter_context(DirectoryLease(output))
            sources={}
            for name,data in [('raw',packet.raw),('metadata',packet.metadata),('request',packet.request)]:
                path=folder/(name+'.input');pin=write_new_locked(path,data)['SHA256'];sources[name]={'path':str(path),'SHA256':pin}
            task={'kind':'LOCAL_BYTES_ONLY','sources':sources,'output':str(output),'fault':fault}
            task_path=folder/'task.json';task_sha=write_new_locked(task_path,encoded(task))['SHA256']
            launched_ns=time.time_ns();result=None;stop=None;identity=None;observed=None;cleanup=None;active=None;final_active=None
            with OwnedJob() as job:
                try:
                    identity=job.start(['-B',self.worker,'--task',task_path,task_sha],folder)
                    observed=job.wait(deadline)
                    # Account for the short kernel accounting lag after the process handle signals.
                    settle=time.monotonic()+.2
                    while job.active() and not observed['timed_out'] and time.monotonic()<settle:time.sleep(.005)
                    active=job.active()
                    if observed['timed_out'] or observed['exit_code']!=0 or active:
                        stop='WORKER_TIMEOUT' if observed['timed_out'] else 'WORKER_NONZERO_EXIT' if observed['exit_code']!=0 else 'OWNED_DESCENDANT_REMAINS'
                        cleanup=job.cleanup(cleanup_deadline)
                        if not cleanup['cleanup_complete']:
                            # Finite rescue remains confined to the same held Job Object.
                            cleanup['rescue']=job.cleanup(2);stop='CLEANUP_DEADLINE_UNCONFIRMED'
                    else:
                        for protected in [self.root,folder,output]:acl_audit(protected)
                        data=read_bytes_locked(output/'result.json',4*1024*1024)
                        rec=json.loads(read_bytes_locked(output/'worker-receipt.json'))
                        result=json.loads(data)
                        if rec['PID']!=identity['PID'] or result['PID']!=identity['PID'] or rec['task_SHA256']!=task_sha or result['task_SHA256']!=task_sha or rec['result_SHA256']!=sha(data):raise ValueError('LOCAL_RESULT_BINDING')
                        if result['kind']!='LOCAL_BYTE_RESULT' or result['network_GET']!=0 or rec['network_GET']!=0:raise ValueError('LOCAL_BOUNDARY')
                        blobs={k:base64.b64decode(v,validate=True) for k,v in result['blobs'].items()}
                        if set(blobs)!=set(sources) or any(sha(v)!=sources[k]['SHA256'] for k,v in blobs.items()):raise ValueError('RETURNED_BYTES_SHA')
                        result=replace(packet,raw=blobs['raw'],metadata=blobs['metadata'],request=blobs['request'])
                except Exception as exc:
                    stop=type(exc).__name__+':'+str(exc)
                    if job.process:cleanup=job.cleanup(2)
                final_active=job.active()
            receipt={'ordinal':self.sequence,'status':'STOP' if stop else 'LOCAL_BYTES_COMPLETE','stop':stop,
                'identity':identity,'observed_exit':observed,'cleanup':cleanup,'task_SHA256':task_sha,
                'post_settle_active_job_processes':active,'final_owned_active_processes':final_active,
                'worker_SHA256':self.worker_sha,'windows_SHA256':self.windows_sha,
                'launched_epoch_ns':launched_ns,'parent_committed_epoch_ns':time.time_ns(),
                'worker_exit_precedes_result_acceptance':True,'network_GET':0}
            write_new_locked(folder/'parent-receipt.json',encoded(receipt));self.receipts.append(receipt)
            if stop:raise RuntimeError('LOCAL_GLOBAL_STOP:'+stop)
            return result

    def close(self):
        self.lease.close();self.base_lease.close()
        for handle in self.code_handles:Close(handle)
        self.code_handles=[]


def replay_with_workers(offline,manager,stage_store,items,strict,review,*,local_synthetic_budget=None):
    runner=offline.ReplayRun(stage_store,synthetic_budget=local_synthetic_budget)
    def delivered():
        for packet,expected in items:yield manager.one(packet),expected
    def checked_review(*args):
        result=review(*args)
        if result.get('status')=='HOLD' and str(result.get('reason','')).startswith(('TypeError:','KeyError:','IndexError:','UnicodeError:')):
            raise RuntimeError('LOCAL_ANALYSIS_CONTRACT_ERROR_IS_GLOBAL_STOP')
        return result
    try:
        result=runner.run(delivered(),strict,checked_review)
    except Exception as exc:
        result={'status':'LOCAL_GLOBAL_STOP','reason':type(exc).__name__+':'+str(exc),'history_admitted':0,
                'committed_stage_B_receipts':len(runner.records),'worker_attempts':manager.sequence,'network_GET':0}
    manager.stopped=True
    write_new_locked(manager.root/'integration-terminal.json',encoded(result))
    return result,runner
