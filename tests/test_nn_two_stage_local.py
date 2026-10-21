"""Real Windows local processes, ACLs, reparse points and bounded crash tests."""
import ast
from dataclasses import replace
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import pytest
from test_nn_two_stage_offline import example,strict,review,m as offline,repin

CODE=Path(__file__).parents[1]/'research/nn_v2/phase2_5B_13'
sys.path.insert(0,str(CODE))
import windows_local as win
import local_integration as local


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('Local-only OS tests forbid sockets')
    monkeypatch.setattr(socket.socket,'connect',forbidden);monkeypatch.setattr(socket,'getaddrinfo',forbidden)


def manager(tmp_path,name='transport'):
    return local.LocalManager(tmp_path/name,allowed_base=tmp_path,worker_path=CODE/'local_worker.py',
        worker_sha=local.sha((CODE/'local_worker.py').read_bytes()),windows_sha=local.sha((CODE/'windows_local.py').read_bytes()))


def store(tmp_path,name='stage'):
    return local.leased_store_class(offline)(tmp_path/name,allowed_base=tmp_path)


def integrated(tmp_path,items,reviewer=review,store_class=None):
    transport=manager(tmp_path);storage=store(tmp_path) if store_class is None else store_class(tmp_path/'stage',allowed_base=tmp_path)
    try:
        result,run=local.replay_with_workers(offline,transport,storage,items,strict,reviewer,local_synthetic_budget=offline.SyntheticBudget(count=30,deadline=300))
        return result,run,transport,storage
    finally:storage.close();transport.close()


def test_real_worker_PID_executable_kernel_parent_and_exit_receipt_order(tmp_path):
    t=manager(tmp_path)
    try:
        p,e=example();returned=t.one(p);assert returned==p
        r=t.receipts[0];i=r['identity']
        assert i['kernel_PID']==i['PID'] and i['kernel_parent_PID']==os.getpid() and i['job_membership_verified']
        assert Path(i['executable']).resolve()==Path(sys._base_executable).resolve()
        assert r['observed_exit']['exit_code']==0 and not r['observed_exit']['timed_out']
        worker=json.loads((t.root/'worker-0001/worker-output/worker-receipt.json').read_bytes())
        assert worker['completed_epoch_ns']<r['parent_committed_epoch_ns'] and r['worker_exit_precedes_result_acceptance']
    finally:t.close()


def test_actual_CreateProcess_start_failure_leaves_no_worker(tmp_path):
    with win.OwnedJob() as job:
        with pytest.raises(OSError):job.start(['-B',CODE/'local_worker.py'],tmp_path/'absent-cwd')
        assert job.process is None and job.active()==0


@pytest.mark.parametrize('fault,expected',[('exit-nonzero','WORKER_NONZERO_EXIT'),('partial-raw','WORKER_NONZERO_EXIT'),
 ('partial-metadata','WORKER_NONZERO_EXIT'),('sleep','WORKER_TIMEOUT'),('spawn-child-exit','OWNED_DESCENDANT_REMAINS')])
def test_worker_failure_timeout_or_owned_descendant_stops_without_retry(tmp_path,fault,expected):
    t=manager(tmp_path)
    try:
        with pytest.raises(RuntimeError):t.one(example()[0],fault=fault,deadline=.15 if fault=='sleep' else 3)
        r=t.receipts[0];assert r['stop']==expected and r['cleanup']['cleanup_complete'] and r['cleanup']['active']==0
        with pytest.raises(RuntimeError,match='TERMINAL'):t.one(example(1)[0])
        assert t.sequence==1 and not (t.root/'worker-0002').exists()
        if fault=='spawn-child-exit':assert (t.root/'worker-0001/worker-output/descendant.json').is_file()
        if fault.startswith('partial'):assert list((t.root/'worker-0001/worker-output').glob('*.partial'))
    finally:t.close()


def test_cleanup_deadline_exhaustion_is_STOP_then_bounded_owned_rescue(tmp_path):
    t=manager(tmp_path)
    try:
        with pytest.raises(RuntimeError):t.one(example()[0],fault='sleep',deadline=.1,cleanup_deadline=0)
        r=t.receipts[0];assert r['stop']=='CLEANUP_DEADLINE_UNCONFIRMED'
        assert not r['cleanup']['cleanup_complete'] and r['cleanup']['rescue']['cleanup_complete']
    finally:t.close()


def test_owned_job_cleanup_does_not_terminate_peer_outside_job(tmp_path):
    peer=subprocess.Popen([sys._base_executable,'-B',str(CODE/'local_worker.py'),'--sleep-only'],creationflags=0x08000000)
    try:
        with win.OwnedJob() as j:
            j.start(['-B',CODE/'local_worker.py','--sleep-only'],tmp_path)
            assert j.wait(.05)['timed_out'];assert j.cleanup(2)['cleanup_complete']
            assert peer.poll() is None
    finally:peer.kill();peer.wait(timeout=3)


def harness(tmp_path,scenario):
    env=os.environ.copy();repo=CODE.parents[2]
    site=Path(sys.executable).parents[1]/'Lib/site-packages'
    env['PYTHONPATH']=str(site)+os.pathsep+str(repo/'tests')+os.pathsep+str(repo)
    out=tmp_path/'harness'
    p=subprocess.Popen([sys._base_executable,'-B',str(CODE/'fault_harness.py'),scenario,str(out)],env=env,creationflags=0x08000000)
    try:code=p.wait(timeout=10)
    except BaseException:p.kill();p.wait(timeout=3);raise
    return out,code


def process_original_is_gone(pid,creation):
    open_process=win.api(win.K,'OpenProcess',[win.W.DWORD,win.W.BOOL,win.W.DWORD],win.W.HANDLE)
    h=open_process(0x100000|0x1000,False,pid)
    if not h:
        assert ctypes.get_last_error()==87
        return True
    try:
        if win.process_identity(h)['creation_FILETIME']!=creation:return True
        return win.Wait(h,0)==0
    finally:win.Close(h)


def test_actual_parent_exit_closes_job_and_kills_owned_worker(tmp_path):
    root,exit_code=harness(tmp_path,'parent-job-crash');assert exit_code==41
    identity=json.loads((root/'owner-start.json').read_bytes())['identity']
    end=time.monotonic()+3
    while time.monotonic()<end:
        if process_original_is_gone(identity['PID'],identity['creation_FILETIME']):break
        time.sleep(.02)
    assert process_original_is_gone(identity['PID'],identity['creation_FILETIME'])


@pytest.mark.parametrize('scenario,code',[('seal-before',51),('receipt-before',52),('receipt-after',53)])
def test_actual_parent_crash_at_storage_boundary_has_no_successor_or_resume(tmp_path,scenario,code):
    root,exit_code=harness(tmp_path,scenario);assert exit_code==code
    assert (root/'stage/run-claim.json').is_file()
    assert not (root/'transport/worker-0002').exists()
    if scenario=='seal-before':assert not (root/'stage/source-0001/seal.json').exists()
    elif scenario=='receipt-before':assert not (root/'stage/receipt-0001.json').exists()
    else:
        receipt=json.loads((root/'stage/receipt-0001.json').read_bytes())
        packet=json.loads((root/'stage'/receipt['review_folder']/'packet.json').read_bytes())
        assert packet['quarantine_status'] and packet['history_admission_status'] is False
    with pytest.raises(OSError):manager(root)
    with pytest.raises(OSError):store(root)


def test_restrictive_owner_ACL_and_exclusive_reuse(tmp_path):
    s=store(tmp_path)
    try:
        report=win.acl_audit(s.root);assert report['scope_verified'] and report['owner_sid']==win.current_sid()
        s.write('test.bin',b'original')
        with pytest.raises(OSError):s.write('test.bin',b'overwrite')
        with pytest.raises(OSError):store(tmp_path)
        assert s.read('test.bin')==b'original'
    finally:s.close()


@pytest.mark.parametrize('path',['../escape','/absolute','folder/../../escape','a/b/c'])
def test_traversal_and_depth_escape_are_rejected(tmp_path,path):
    s=store(tmp_path)
    try:
        with pytest.raises((ValueError,offline.Stop,OSError)):s.write(path,b'forbidden')
    finally:s.close()


def junction(link,target,base):
    assert Path(link).absolute().is_relative_to(base.resolve()) and target.resolve().is_relative_to(base.resolve())
    p=subprocess.run(['cmd','/d','/c','mklink','/J',str(link),str(target)],capture_output=True,timeout=3,creationflags=0x08000000)
    assert p.returncode==0


@pytest.mark.parametrize('kind',['junction','symlink'])
def test_actual_reparse_destination_cannot_write_outside_store(tmp_path,kind):
    s=store(tmp_path);outside=tmp_path/'outside';outside.mkdir();link=s.root/'trap'
    try:
        if kind=='junction':junction(link,outside,tmp_path)
        else:os.symlink(outside,link,target_is_directory=True)
        with pytest.raises((ValueError,offline.Stop,OSError)):s.write('trap/escape',b'forbidden')
        assert list(outside.iterdir())==[]
    finally:s.close()


def safe_rename(source,target,base):
    assert source.absolute().is_relative_to(base.resolve()) and target.absolute().is_relative_to(base.resolve())
    os.rename(source,target)


def test_actual_directory_rename_race_is_blocked_while_handle_lease_is_held(tmp_path):
    root=tmp_path/'race';root.mkdir();moved=tmp_path/'moved';errors=[]
    with win.DirectoryLease(root):
        def actor():
            for _ in range(20):
                try:safe_rename(root,moved,tmp_path)
                except OSError as e:errors.append(e.winerror)
        t=threading.Thread(target=actor);t.start();t.join(timeout=3);assert not t.is_alive()
        assert len(errors)==20 and set(errors)<={5,32}
        win.write_new_locked(root/'safe',b'safe')
    safe_rename(root,moved,tmp_path);assert (moved/'safe').read_bytes()==b'safe'


def test_actual_parent_swap_between_path_check_and_open_is_detected(tmp_path,monkeypatch):
    s=store(tmp_path);slot=s.root/'slot';slot.mkdir();outside=tmp_path/'outside';outside.mkdir()
    checked=threading.Event();swapped=threading.Event();errors=[];original=s._parent
    def parent(name):
        p=original(name);checked.set();assert swapped.wait(3);return p
    monkeypatch.setattr(s,'_parent',parent)
    def actor():
        try:
            assert checked.wait(3);safe_rename(slot,s.root/'old-slot',tmp_path);junction(slot,outside,tmp_path)
        except BaseException as e:errors.append(e)
        finally:swapped.set()
    t=threading.Thread(target=actor);t.start()
    try:
        with pytest.raises((ValueError,OSError)):s.write('slot/escape',b'forbidden')
        t.join(timeout=3);assert not t.is_alive() and not errors and not list(outside.iterdir())
    finally:s.close()


def test_actual_swap_after_parent_handle_acquisition_is_prevented(tmp_path,monkeypatch):
    s=store(tmp_path);slot=s.root/'slot';slot.mkdir();entered=threading.Event();attempted=threading.Event();errors=[]
    original=local.write_new_locked
    def paused(path,data):entered.set();assert attempted.wait(3);return original(path,data)
    monkeypatch.setattr(local,'write_new_locked',paused)
    def actor():
        assert entered.wait(3)
        try:safe_rename(slot,s.root/'moved',tmp_path)
        except OSError as e:errors.append(e.winerror)
        finally:attempted.set()
    t=threading.Thread(target=actor);t.start()
    try:
        s.write('slot/safe',b'safe');t.join(timeout=3)
        assert not t.is_alive() and errors and s.read('slot/safe')==b'safe'
    finally:s.close()


def test_worker_stage_A_B_quarantine_receipt_gates_next_worker(tmp_path):
    result,run,t,s=integrated(tmp_path,[example(0,'UNKNOWN'),example(1)])
    assert result['source_acquired']==2 and result['detail_PASS']==result['detail_HOLD']==result['quarantined']==1
    first=json.loads((s.root/'receipt-0001.json').read_bytes())
    packet=json.loads((s.root/first['review_folder']/'packet.json').read_bytes())
    first_receipt_ns=(s.root/'receipt-0001.json').stat().st_mtime_ns
    assert first_receipt_ns<=t.receipts[1]['launched_epoch_ns'] and not packet['history_admission_status']
    assert t.stopped


@pytest.mark.parametrize('failure',['quarantine-0001/packet.json','quarantine-0001/seal.json','receipt-0001.json'])
def test_quarantine_save_failure_globally_stops_before_next_local_worker(tmp_path,failure):
    Store=local.leased_store_class(offline)
    class Fail(Store):
        def write(self,name,data):
            if name==failure:raise OSError('injected local persistence failure')
            return super().write(name,data)
    result,_,t,_=integrated(tmp_path,[example(0,'UNKNOWN'),example(1)],store_class=Fail)
    assert result['status'] in {'LOCAL_GLOBAL_STOP','OFFLINE_REPLAY_STOPPED'} and t.sequence==1 and t.stopped


def test_local_worker_unknown_then_stage_B_identity_drift_STOP(tmp_path):
    def changed(*args):
        r=review(*args)
        if args[-1].row['data_site_match_id']=='10001':r['strict_analysis']['identity']='contradiction'
        return r
    result,_,t,_=integrated(tmp_path,[example(0,'UNKNOWN'),example(1),example(2)],reviewer=changed)
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and t.sequence==2


@pytest.mark.parametrize('status',[403,429,302])
def test_local_synthetic_HTTP_or_redirect_anomaly_is_global_STOP(tmp_path,status):
    p,e=example(1);meta=json.loads(p.metadata);meta['status']=status;p,e=repin(p,e,meta=meta)
    result,_,t,_=integrated(tmp_path,[example(0,'UNKNOWN'),(p,e),example(2)])
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and t.sequence==2 and result['detail_HOLD']==1


def test_duplicate_is_rejected_before_second_worker_start(tmp_path):
    result,_,t,_=integrated(tmp_path,[example(),example()])
    assert result['status']=='LOCAL_GLOBAL_STOP' and t.sequence==1 and t.stopped


@pytest.mark.parametrize('fault',['audit-network-probe','audit-outside-write-probe'])
def test_real_worker_audit_boundary_rejects_probes_without_effects(tmp_path,fault):
    t=manager(tmp_path)
    try:
        with pytest.raises(RuntimeError):t.one(example()[0],fault=fault)
        assert t.receipts[0]['stop']=='WORKER_NONZERO_EXIT'
        assert not (t.root/'outside-worker-probe').exists()
    finally:t.close()


@pytest.mark.parametrize('failure',['TLS','GET','body','rate','SHA','URL_ID','result'])
def test_local_worker_and_stage_integrity_failures_are_not_remark_HOLD(tmp_path,failure):
    p,e=example(1)
    if failure in {'TLS','GET'}:
        meta=json.loads(p.metadata);req=json.loads(p.request)
        if failure=='TLS':req['TLS_verification']=False
        else:meta['GET_attempts']=2
        p,e=repin(p,e,meta=meta,req=req)
    if failure=='body':p=replace(p,raw=b'x'*(2*1024*1024+1))
    if failure=='rate':p=replace(p,synthetic_observation={**p.synthetic_observation,'start':1,'end':1.1})
    if failure=='SHA':p=replace(p,metadata=p.metadata+b' ')
    if failure=='URL_ID':p=replace(p,row={**p.row,'data_site_match_id':'other'})
    if failure=='result':p=replace(p,row={**p.row,'away_score_90':3})
    result,_,t,_=integrated(tmp_path,[example(0,'UNKNOWN'),(p,e),example(2)])
    assert result['status'] in {'LOCAL_GLOBAL_STOP','OFFLINE_REPLAY_STOPPED'} and t.sequence==2 and t.stopped


def test_missing_quarantine_packet_is_not_read_as_all_PASS(tmp_path):
    _,run,t,s=integrated(tmp_path,[example(0,'UNKNOWN'),example(1)])
    # Test-owned new output only; the source snapshots are never changed.
    target=s.root/'quarantine-0001/packet.json';assert target.resolve().is_relative_to(s.root.resolve());target.unlink()
    reader=object.__new__(offline.ImmutableStore);reader.root=s.root;run.store=reader
    with pytest.raises(offline.Stop):run.aggregate()


def test_unexpected_analysis_contract_TypeError_is_STOP_not_remark_quarantine(tmp_path):
    def wrong(*args):r=review(*args);r.update(status='HOLD',legacy_category='UNKNOWN_FORMAT',reason='TypeError: invalid rule binding');return r
    result,_,t,_=integrated(tmp_path,[example(),example(1)],reviewer=wrong)
    assert result['status']=='OFFLINE_REPLAY_STOPPED' and result['detail_HOLD']==0 and t.sequence==1


def set_test_acl(path,policy,base):
    assert path.absolute().is_relative_to(base.resolve())
    sd=win.P();length=win.W.DWORD()
    win.checked(win.SDDL(policy,1,ctypes.byref(sd),ctypes.byref(length)),'Test SDDL')
    fn=win.api(win.A,'SetFileSecurityW',[win.W.LPCWSTR,win.W.DWORD,win.P])
    try:win.checked(fn(str(path),4|0x80000000,sd),'Test ACL mutation')
    finally:win.LocalFree(sd)


def test_actual_concurrent_ACL_change_is_detected_before_commit(tmp_path,monkeypatch):
    s=store(tmp_path);sid=win.current_sid()
    safe=f'O:{sid}D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'
    loose=safe+'(A;OICI;FA;;;WD)'
    entered=threading.Event();changed=threading.Event();errors=[];original=local.write_new_locked
    def paused(path,data):entered.set();assert changed.wait(3);return original(path,data)
    monkeypatch.setattr(local,'write_new_locked',paused)
    def actor():
        try:assert entered.wait(3);set_test_acl(s.root,loose,tmp_path)
        except BaseException as e:errors.append(e)
        finally:changed.set()
    t=threading.Thread(target=actor);t.start()
    try:
        with pytest.raises(ValueError,match='OWNER_OR_DACL'):s.write('uncommitted.bin',b'local test bytes')
        t.join(timeout=3);assert not t.is_alive() and not errors
        with pytest.raises(ValueError):win.acl_audit(s.root)
    finally:set_test_acl(s.root,safe,tmp_path);s.close()


def test_quarantine_cannot_be_ignored_and_admission_always_denied(tmp_path):
    result,run,t,s=integrated(tmp_path,[example(0,'UNKNOWN'),example(1)])
    # Read-only inspection after handles close; no failed run is resumed.
    reader=object.__new__(offline.ImmutableStore);reader.root=s.root;run.store=reader
    packet=run.verify_receipt(run.records[0]['receipt'],run.records[0]['SHA256'])
    with pytest.raises(offline.Stop):offline.require_history_admission(packet)
    run.records=run.records[1:]
    with pytest.raises(offline.Stop):run.aggregate()


def test_research_sources_have_no_HTTP_or_model_integration():
    for name in ['windows_local.py','local_worker.py','local_integration.py','fault_harness.py']:
        tree=ast.parse((CODE/name).read_text(encoding='utf8'))
        imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}|{a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
        assert not any(x and any(s in x for s in ['socket','http','urllib','requests','torch','sklearn','champion','staff_warning_shadow']) for x in imports)
