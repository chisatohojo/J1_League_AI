"""Local-only subprocess crash harness; outputs exclusively in a new test root."""
import importlib.util
import json
import os
from pathlib import Path
import sys
from windows_local import OwnedJob,secure_mkdir,write_new_locked
from local_integration import LocalManager,leased_store_class,replay_with_workers,sha,encoded


def main():
    if len(sys.argv)!=3:raise ValueError('LOCAL_SCENARIO_AND_NEW_ROOT_REQUIRED')
    scenario,root=sys.argv[1],Path(sys.argv[2]).absolute();secure_mkdir(root)
    def boundary(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.bind','http.client.connect','urllib.Request','pickle.find_class'}:
            raise RuntimeError('LOCAL_HARNESS_NO_NETWORK_OR_MODEL')
    sys.addaudithook(boundary)
    if scenario=='parent-job-crash':
        out=root/'worker-output';secure_mkdir(out)
        sources={k:{'path':str(root/(k+'.unused')),'SHA256':'unused'} for k in ['raw','metadata','request']}
        task=encoded({'kind':'LOCAL_BYTES_ONLY','sources':sources,'output':str(out),'fault':'sleep'})
        # Worker requires its task directory to own worker-output.
        write_new_locked(root/'task.json',task)
        job=OwnedJob();identity=job.start(['-B',Path(__file__).with_name('local_worker.py'),'--task',root/'task.json',sha(task)],root)
        write_new_locked(root/'owner-start.json',encoded({'identity':identity,'controller_PID':os.getpid(),'scenario':scenario}))
        os._exit(41)
    repo=Path(__file__).resolve().parents[3]
    sys.path.insert(0,str(repo/'tests'))
    import test_nn_two_stage_offline as helpers
    offline=helpers.m;Store=leased_store_class(offline)
    class CrashStore(Store):
        def write(self,name,data):
            if scenario=='seal-before' and name=='source-0001/seal.json':os._exit(51)
            if scenario=='receipt-before' and name=='receipt-0001.json':os._exit(52)
            result=super().write(name,data)
            if scenario=='receipt-after' and name=='receipt-0001.json':os._exit(53)
            return result
    manager=LocalManager(root/'transport',allowed_base=root,worker_path=Path(__file__).with_name('local_worker.py'),
        worker_sha=sha(Path(__file__).with_name('local_worker.py').read_bytes()),windows_sha=sha(Path(__file__).with_name('windows_local.py').read_bytes()))
    store=CrashStore(root/'stage',allowed_base=root)
    try:
        replay_with_workers(offline,manager,store,[helpers.example(0,'UNKNOWN'),helpers.example(1)],helpers.strict,helpers.review,
                            local_synthetic_budget=offline.SyntheticBudget())
    finally:store.close();manager.close()
    raise RuntimeError('CRASH_SCENARIO_DID_NOT_FIRE')


if __name__=='__main__':main()
