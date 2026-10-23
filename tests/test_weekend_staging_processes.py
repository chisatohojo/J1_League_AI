"""Authorized real Windows test processes; only new, marked staging arenas."""
from pathlib import Path
import ctypes
from ctypes import wintypes as T
import json
import tempfile
import uuid

import pytest

from test_weekend_source import factory
from test_weekend_integration import e2e, invoke, tree
from test_weekend_batch import no_real_estimator_or_network
from test_dashboard_feed import production_and_network_firewall
from weekend_staging_process_helper import OwnedJob
from src.modeling.weekend_staging_windows import Arena, StagingHold
from src.modeling.weekend_staging_publication import Publisher
from src.modeling import weekend_integration as integration
from src.modeling import weekend_batch as w
from src.modeling import champion_prediction as champion


@pytest.fixture
def arena():
    value = Arena.create(Path(tempfile.gettempdir())/('j1ai-weekend-staging-'+uuid.uuid4().hex))
    try: yield value
    finally: value.close()  # Never delete test/failed evidence.


@pytest.fixture
def job(arena):
    value = OwnedJob(arena)
    try: yield value
    finally: value.close()


@pytest.fixture
def saved_input(e2e, arena):
    assert invoke(e2e)['added']==10 and len(e2e.model.inputs)==1
    original = next((e2e.runtime/'batches').glob(integration.PREFIX+'*'))
    records,_,_,_ = integration.read_bound_batch(original)
    arena.mkdir('input'); arena.mkdir('input/'+original.name)
    for p in original.iterdir(): arena.write_new('input/'+original.name+'/'+p.name,p.read_bytes())
    return dict(directory='input/'+original.name,files={p.name:w.sha(p) for p in original.iterdir()},
                witness=e2e.backend.witnesses['estimator']['sha256'],
                fixture_keys=[r['fixture_key'] for r in records],model_pins=dict(champion.FILE_PINS))


def wait_pass(job, child):
    assert job.wait(child)==0
    result = job.result(child)
    assert result['status']=='PASS' and result['pid']==child['pid'] and result['nonce']==child['nonce']
    assert child['kernel_command_line_verified'] and child['job_verified_before_resume']
    return result


def test_two_real_processes_lock_then_owned_normal_exit_and_later_claim(job,arena):
    a=job.spawn('claim',request_id='a'*64,pauses=['lock-held'])
    job.state(a,'lock-held')
    membership=job.membership_report()
    assert {r['pid'] for r in membership['members']}=={a['pid']}
    arena.write_new('control/active-membership.json',w.body(membership))
    b=job.spawn('claim',request_id='b'*64)
    assert a['pid']!=b['pid'] and job.wait(b)==3 and job.result(b)['status']=='HOLD'
    assert (arena.root/'publication.lock').is_file()
    job.release(a,'lock-held'); wait_pass(job,a)
    assert not (arena.root/'publication.lock').exists()
    c=job.spawn('claim',request_id='c'*64)
    wait_pass(job,c)
    assert not job.job_pids() and not (arena.root/'publication.lock').exists()
    assert a['identity']['creation_filetime']>0 and 'python.exe' in a['identity']['executable'].lower()


def test_other_process_rename_replace_delete_refused_then_allowed_after_handle_release(job,arena):
    held=[]
    for name in ['held-rename','held-delete','held-replace']:
        held.append(arena.api.open_directory(arena.mkdir(name)))
    arena.mkdir('replacement')
    arena.write_new('held-file-replace',b'old'); arena.write_new('replacement-file',b'new')
    held.append(arena.api.open_directory(arena.root/'held-file-replace'))
    try:
        denied=job.spawn('mutate'); results=wait_pass(job,denied)['results']
        assert set(results)=={'rename','delete','replace','file_replace'} and all(not r['allowed'] for r in results.values())
        assert results['rename']['winerror']==results['delete']['winerror']==32
        assert results['file_replace']['winerror'] in {5,32}
    finally:
        for handle in held: arena.api.ok(arena.api.k.CloseHandle(handle))
    allowed=job.spawn('mutate'); results=wait_pass(job,allowed)['results']
    assert all(results[n]['allowed'] for n in ['rename','delete','file_replace'])
    # Windows does not support replacing an existing directory with Path.replace,
    # even without the held handle. Record that baseline, never call it a lock proof.
    assert results['replace']==dict(allowed=False,winerror=5)
    assert (arena.root/'held-file-replace').read_bytes()==b'new'
    assert (arena.root/'renamed').is_dir() and not (arena.root/'held-delete').exists()


def test_two_publishers_and_real_reader_never_return_partial_batch(job,arena,saved_input,e2e):
    a=job.spawn('publish',request_id='a'*64,source=saved_input,
                pauses=['ready','before_rename','after_rename','after_seal'])
    b=job.spawn('publish',request_id='b'*64,source=saved_input,pauses=['ready'])
    job.state(a,'ready'); job.state(b,'ready')
    observer=job.spawn('observe',request_id='a'*64,source=saved_input)
    job.state(observer,'observing'); job.state(observer,'first-hold')
    job.release(a,'ready'); job.state(a,'before_rename')
    job.release(b,'ready')
    assert job.wait(b)==3 and job.result(b)['status']=='HOLD'
    assert not list(arena.root.glob('batch-*'))
    job.release(a,'before_rename'); job.state(a,'after_rename')
    with pytest.raises((OSError,ValueError)): Publisher(arena).read('a'*64)
    job.release(a,'after_rename'); job.state(a,'after_seal')
    job.state(observer,'first-complete')
    job.release(a,'after_seal'); wait_pass(job,a)
    job.release(observer,'observe'); observed=wait_pass(job,observer)
    assert observed['holds']>0 and observed['counts'] and set(observed['counts'])=={10}
    assert len(list(arena.root.glob('batch-*')))==1 and len(Publisher(arena).read('a'*64)[0])==10
    before=tree(arena.root/('batch-'+'a'*64))
    Publisher(arena).read('a'*64)
    assert tree(arena.root/('batch-'+'a'*64))==before and len(e2e.model.inputs)==1


def test_distinct_request_duplicate_fixture_rejected_and_published_bytes_unchanged(job,arena,saved_input,e2e):
    a=job.spawn('publish',request_id='a'*64,source=saved_input); wait_pass(job,a)
    before=tree(arena.root/('batch-'+'a'*64))
    duplicate=job.spawn('publish',request_id='b'*64,source=saved_input)
    assert job.wait(duplicate)==3 and 'duplicate_saved_fixture' in job.result(duplicate)['reason']
    assert len(list(arena.root.glob('batch-*')))==1 and tree(arena.root/('batch-'+'a'*64))==before
    assert Publisher(arena).recovery_report()['state']=='HOLD_MANUAL_REVIEW' and len(e2e.model.inputs)==1


@pytest.mark.parametrize('point',['after_predictions.csv','before_rename','after_rename','before_receipt','after_seal'])
def test_Job_forced_exit_preserves_evidence_no_partial_acceptance_or_auto_reinference(job,arena,saved_input,e2e,point):
    child=job.spawn('publish',request_id='a'*64,source=saved_input,pauses=[point])
    state=job.state(child,point)
    before={p.relative_to(arena.root).as_posix():w.sha(p) for p in arena.root.rglob('*') if p.is_file() and 'control' not in p.parts and p.name!='publication.lock'}
    job.stop()
    assert child['exit_code']==0xE3 and not job.job_pids() and job.result(child) is None
    after={p.relative_to(arena.root).as_posix():w.sha(p) for p in arena.root.rglob('*') if p.is_file() and 'control' not in p.parts and p.name!='publication.lock'}
    assert after==before and (arena.root/'publication.lock').is_file() and list(arena.root.glob('attempt-*'))
    assert w.sha(arena.root/'publication.lock')==state['owned_lock_sha256']
    if point=='after_seal':
        assert len(Publisher(arena).read('a'*64)[0])==10
    else:
        with pytest.raises((OSError,ValueError)): Publisher(arena).read('a'*64)
    with pytest.raises(RuntimeError,match='owner confirmation'): job.review_recovery(child,'unconfirmed')
    review=job.review_recovery(child,child['nonce'])
    assert review['owner_exit_verified'] and not review['auto_resume'] and not review['auto_delete']
    arena.write_new('control/'+child['nonce']+'.manual-review.json',w.body(review))
    later=job.spawn('claim',request_id='a'*64)
    assert job.wait(later)==3 and job.result(later)['status']=='HOLD'
    assert len(e2e.model.inputs)==1 and Publisher(arena).recovery_report()['state']=='HOLD_MANUAL_REVIEW'


def test_assignment_refusal_injection_never_resumes_owned_suspended_child(job,arena):
    child=job.spawn('claim',refuse_assignment=True)
    assert job.wait(child)==0xE1 and child['assignment_refused_before_resume'] and not child['resumed']
    assert not job.job_pids() and not (arena.root/'publication.lock').exists()
    assert not list((arena.root/'control').glob('*.state.*'))


def test_unrecognized_entrypoint_fails_before_process_creation(job):
    with pytest.raises(RuntimeError,match='entrypoint allowlist'): job.spawn('real_worker')
    assert not job.children and not job.job_pids()


def test_owned_job_and_process_handles_return_to_baseline(arena):
    kernel=arena.api.k
    kernel.GetCurrentProcess.restype=T.HANDLE
    kernel.GetProcessHandleCount.argtypes=[T.HANDLE,ctypes.POINTER(T.DWORD)]
    def count():
        result=T.DWORD(); arena.api.ok(kernel.GetProcessHandleCount(kernel.GetCurrentProcess(),ctypes.byref(result)))
        return result.value
    before=count()
    for index in range(2):
        job=OwnedJob(arena)
        try: wait_pass(job,job.spawn('claim',request_id=str(index+1)*64))
        finally: job.close()
        assert job.closed
    assert count()==before


def test_publish_requires_live_owned_transaction(arena,saved_input):
    source=arena.root/saved_input['directory']
    with pytest.raises(StagingHold,match='owned_transaction_required'):
        Publisher(arena).stage_saved(source,'a'*64,saved_input['witness'],recheck=lambda:None)
    assert not list(arena.root.glob('batch-*'))
