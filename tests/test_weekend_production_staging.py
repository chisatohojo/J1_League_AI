"""Windows I/O and candidate adapters, exclusively fake HTTP/model inputs."""
import ast
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import uuid

import numpy as np
import pytest

from test_weekend_source import factory
from test_weekend_integration import e2e, invoke, tree, utc
from test_weekend_batch import no_real_estimator_or_network
from test_dashboard_feed import production_and_network_firewall
from src.modeling import weekend_batch as w
from src.modeling import weekend_production_staging as s
from src.modeling import weekend_staging_publication as pub
from src.modeling.weekend_staging_windows import Arena, StagingHold, identity


@pytest.fixture(autouse=True)
def no_child_DNS_or_network(monkeypatch):
    def no(*args,**kwargs):
        pytest.fail('No child, external communication or model in staging tests')
    for obj,names in [(subprocess,['Popen','run','call','check_call','check_output']),
                      (socket,['getaddrinfo','create_connection']),
                      (socket.socket,['connect','connect_ex','bind','listen'])]:
        for name in names:
            monkeypatch.setattr(obj,name,no)


@pytest.fixture
def arena():
    value=Arena.create(Path(tempfile.gettempdir())/('j1ai-weekend-staging-'+uuid.uuid4().hex))
    try:
        yield value
    finally:
        value.close()  # No arena/failed evidence is deleted.


def candidate(e2e):
    original=e2e.backend
    witness=e2e.witness if hasattr(e2e,'witness') else original.witnesses['estimator']
    adapter=s.MockChampionAdapter(original.artifact,{k:witness[k] for k in ['path','sha256']})
    backend=s.StagingReceiptBackend(e2e.workspace,adapter,original.special,original.witnesses,
                                   e2e.source_workspace,e2e.ref,monotonic=lambda:0.0)
    return backend


def test_actual_NTFS_owner_DACL_fsync_readback_and_directory_rename(arena):
    assert arena.api.filesystem(arena.root)=='NTFS'
    assert arena.acl['owner'].startswith('S-1-') and 'D:P' in arena.acl['sddl']
    src=arena.mkdir('pending')
    written=arena.write_new('pending/data.json',b'{}\n')
    assert written['sha256']==w.sha(src/'data.json') and written['security']['owner']==arena.acl['owner']
    before=identity(src)
    dst=arena.rename_new('pending','committed')
    assert identity(dst)==before and (dst/'data.json').read_bytes()==b'{}\n' and not src.exists()


@pytest.mark.parametrize('relative',['../outside','/absolute','C:/outside','a/../../b','file:stream','NUL','COM1.txt','a//b','a\\b','.','..'])
def test_path_escape_ADS_and_device_names_refused(arena,relative):
    with pytest.raises(StagingHold):arena.write_new(relative,b'no')


def test_exclusive_root_and_closed_capability_refused(arena):
    with pytest.raises(StagingHold):Arena.create(arena.root)
    arena.close()
    with pytest.raises(StagingHold):arena.write_new('after-close',b'no')


def test_root_cannot_be_replaced_while_native_handle_held(arena):
    with pytest.raises(OSError):arena.root.rename(arena.root.with_name(arena.root.name+'-swapped'))
    arena.check()


def test_competing_native_writer_claim_and_completed_attempt_no_reuse(arena):
    errors=[]
    with arena.transaction('a'*64):
        def other():
            try:
                with arena.transaction('b'*64):
                    errors.append('UNEXPECTED_SUCCESS')
            except OSError:
                errors.append('OS_REJECTED')
        thread=threading.Thread(target=other)
        thread.start(); thread.join(timeout=3)
        assert not thread.is_alive() and errors==['OS_REJECTED']
    assert not (arena.root/'publication.lock').exists()
    with pytest.raises(FileExistsError):
        with arena.transaction('a'*64):pass
    assert (arena.root/'publication.lock').exists()


def test_interrupted_transaction_retains_lock_attempt_and_refuses_resume(arena):
    with pytest.raises(RuntimeError):
        with arena.transaction('c'*64):
            arena.write_new('partial.raw',b'partial')
            raise RuntimeError('simulated interruption, not process kill')
    before=tree(arena.root)
    with pytest.raises(OSError):
        with arena.transaction('c'*64):pass
    assert tree(arena.root)==before
    assert pub.Publisher(arena).recovery_report()['state']=='HOLD_MANUAL_REVIEW'


def test_ACL_change_is_detected_before_write(arena):
    import ctypes
    from ctypes import wintypes as T
    sd=T.LPVOID()
    sid=arena.acl['owner']
    arena.api.ok(arena.api.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        f'D:P(A;OICI;FA;;;{sid})',1,ctypes.byref(sd),None))
    try:arena.api.ok(arena.api.a.SetFileSecurityW(str(arena.root),0x80000004,sd))
    finally:arena.api.k.LocalFree(sd)
    with pytest.raises(StagingHold,match='DACL_changed'):arena.write_new('denied-by-contract',b'x')


def test_actual_DACL_write_denial_on_new_test_subdirectory(arena):
    import ctypes
    from ctypes import wintypes as T
    path=arena.mkdir('denied')
    sd=T.LPVOID(); sid=arena.acl['owner']
    arena.api.ok(arena.api.a.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        f'D:P(D;OICI;FW;;;{sid})(A;OICI;FA;;;{sid})',1,ctypes.byref(sd),None))
    try:arena.api.ok(arena.api.a.SetFileSecurityW(str(path),0x80000004,sd))
    finally:arena.api.k.LocalFree(sd)
    with pytest.raises(PermissionError):
        with (path/'no.txt').open('xb') as stream:stream.write(b'no')
    with pytest.raises(StagingHold):arena.write_new('denied/no.txt',b'no')
    assert not (path/'no.txt').exists()


def test_Reparse_point_target_in_new_sandbox_is_rejected(arena):
    # A mount-point reparse buffer on two NEW sibling directories, no cmd/mklink.
    import ctypes
    from ctypes import wintypes as T
    import struct
    source=arena.mkdir('junction'); target=arena.mkdir('target')
    handle=arena.api.k.CreateFileW(str(source),0x40000000,3,None,3,0x02200000,None)
    assert handle!=ctypes.c_void_p(-1).value
    substitute=('\\??\\'+str(target)).encode('utf-16le')
    printed=str(target).encode('utf-16le')
    paths=substitute+b'\0\0'+printed+b'\0\0'
    data=struct.pack('<IHHHHHH',0xA0000003,8+len(paths),0,0,len(substitute),len(substitute)+2,len(printed))+paths
    kernel=arena.api.k
    kernel.DeviceIoControl.argtypes=[T.HANDLE,T.DWORD,T.LPVOID,T.DWORD,T.LPVOID,T.DWORD,ctypes.POINTER(T.DWORD),T.LPVOID]
    count=T.DWORD()
    try:
        arena.api.ok(kernel.DeviceIoControl(handle,0x000900A4,ctypes.create_string_buffer(data),len(data),None,0,ctypes.byref(count),None))
    finally:kernel.CloseHandle(handle)
    with pytest.raises(StagingHold,match='reparse'):arena.write_new('junction/no.txt',b'no')
    assert not (target/'no.txt').exists()


def test_night_publication_selection_no_fallback(e2e):
    selected=s.SourceWorkerCandidate(e2e.source_workspace,e2e.ref,e2e.friday)
    current,receipt=selected.select_previous_night()
    assert current.revision_id==e2e.ref.revision_id and receipt['facts']['history_completed_count']==1
    with pytest.raises(StagingHold):selected.independent_0645_real_acquisition()
    with pytest.raises(StagingHold):s.production_entrypoint(enabled=True)


@pytest.mark.parametrize('field,value',[('timeout_seconds',11),('retry_limit',1),('interval_seconds',4),('max_requests',13),('max_body_bytes',2*1024*1024+1),('deadline_seconds',601),('max_requests',True)])
def test_communication_limits_fail_closed(field,value):
    with pytest.raises(StagingHold):replace(s.CommunicationLimits(),**{field:value}).check()


def transport_response(url,**changes):
    value=dict(status=200,final_url=url,body=b'<html>synthetic</html>',tls_verified=True)
    value.update(changes);return value


def test_mock_HTTP_request_receipts_and_single_use(e2e,arena):
    urls=('https://data.j-league.or.jp/SFMS02/?match_card_id=mock-one',)
    http=s.MockHTTP({urls[0]:transport_response(urls[0])})
    times=iter([e2e.now-timedelta(minutes=15),e2e.now-timedelta(minutes=15),e2e.now-timedelta(minutes=15)+timedelta(seconds=1)])
    worker=s.SourceWorkerCandidate(e2e.source_workspace,e2e.ref,e2e.friday)
    receipts=worker.collect_mock(arena,urls,http,clock=lambda:next(times))
    assert len(receipts)==len(http.called)==1 and receipts[0]['evidence_kind']=='MOCK_HTTP_NOT_REAL_ACQUISITION'
    with pytest.raises(FileExistsError):worker.collect_mock(arena,urls,http,clock=lambda:e2e.now)
    assert len(http.called)==1


@pytest.mark.parametrize('changes',[{'status':403},{'status':429},{'status':500},{'tls_verified':False},{'final_url':'https://elsewhere.invalid/'},{'body':b'x'*(2*1024*1024+1)}],ids=['403','429','500','TLS','redirect','body-cap'])
def test_mock_HTTP_global_stop_and_no_retry(e2e,arena,changes):
    urls=('https://data.j-league.or.jp/SFMS02/?mock=one','https://data.j-league.or.jp/SFMS02/?mock=two')
    http=s.MockHTTP({u:transport_response(u) for u in urls})
    http.responses[urls[0]].update(changes)
    worker=s.SourceWorkerCandidate(e2e.source_workspace,e2e.ref,e2e.friday)
    with pytest.raises(StagingHold):worker.collect_mock(arena,urls,http,clock=lambda:e2e.now)
    assert http.called==[urls[0]]


@pytest.mark.parametrize('seconds,error',[(11,'timeout'),(-1,'timeout')])
def test_mock_HTTP_clock_and_timeout_stop(e2e,arena,seconds,error):
    url='https://data.j-league.or.jp/SFMS02/?mock=timeout'
    http=s.MockHTTP({url:transport_response(url)})
    times=iter([e2e.now,e2e.now,e2e.now+timedelta(seconds=seconds)])
    worker=s.SourceWorkerCandidate(e2e.source_workspace,e2e.ref,e2e.friday)
    with pytest.raises(StagingHold,match=error):worker.collect_mock(arena,(url,),http,clock=lambda:next(times))
    assert len(http.called)==1


def test_mock_Champion_candidate_existing_Phase4_NTFS_envelope_and_no_reinference(e2e,arena):
    backend=candidate(e2e); publisher=pub.Publisher(arena)
    source_before=tree(e2e.repo)
    request_id,group=publisher.run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    assert len(group[0])==10 and len(e2e.model.inputs)==1
    assert group[2]['format_version']=='champion-weekend-v2-source-v1' and group[2]['scope']=='SYNTHETIC_ONLY'
    before=tree(arena.root)
    again=publisher.run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now,slot='evening')
    assert again[0]==request_id and tree(arena.root)==before and len(e2e.model.inputs)==1
    assert tree(e2e.repo)==source_before
    view=w.read_json(e2e.runtime/'view/champion_home.json')
    assert len(view['nextRound']['matches'])==10


@pytest.mark.parametrize('point',['after_predictions.csv','before_rename','after_rename','before_receipt','before_seal','after_seal'])
def test_interrupted_staging_preserves_original_and_blocks_reexecution(e2e,arena,point):
    backend=candidate(e2e); publisher=pub.Publisher(arena)
    def fault(event):
        if event==point:raise OSError('simulated interruption')
    with pytest.raises(OSError):publisher.run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now,fault=fault)
    assert len(e2e.model.inputs)==1
    original=tree(e2e.runtime/'batches')
    with pytest.raises((OSError,StagingHold)):
        publisher.run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    assert len(e2e.model.inputs)==1 and tree(e2e.runtime/'batches')==original
    assert publisher.recovery_report()['state']=='HOLD_MANUAL_REVIEW'


def test_publication_mutation_and_receipt_missing_are_HOLD(e2e,arena):
    backend=candidate(e2e); publisher=pub.Publisher(arena)
    request_id,_=publisher.run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    receipt=arena.path('batch-'+request_id+'/receipt.json')
    receipt.write_bytes(b'{}\n') # only this freshly made test receipt
    with pytest.raises(StagingHold):publisher.read(request_id)


def test_mock_artifact_changed_before_save_refused(e2e,arena,monkeypatch):
    backend=candidate(e2e)
    original=backend.before_commit
    def changed(*args):
        Path(backend.adapter.witness['path']).write_bytes(b'changed mock bytes')
        return original(*args)
    monkeypatch.setattr(backend,'before_commit',changed)
    with pytest.raises(StagingHold):pub.Publisher(arena).run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    assert len(e2e.model.inputs)==1 and not list((e2e.runtime/'batches').glob('weekend-v2-*'))


def test_candidate_modules_have_no_real_loader_transport_or_CLI():
    folder=Path(__file__).resolve().parents[1]/'src/modeling'
    for name in ['weekend_production_staging.py','weekend_staging_publication.py','weekend_staging_windows.py']:
        code=(folder/name).read_text(encoding='utf8')
        tree_ast=ast.parse(code)
        assert not any(isinstance(n,ast.If) and '__name__' in ast.unparse(n.test) for n in tree_ast.body)
        calls=[ast.unparse(n.func) for n in ast.walk(tree_ast) if isinstance(n,ast.Call)]
        assert not any(c.startswith(('socket.','requests.','urllib.request.','subprocess.','joblib.','pickle.')) or c.endswith(('.fit','.fit_transform','.load_champion')) for c in calls)
    assert s.PRODUCTION_ENABLED is False and s.PRODUCTION_CONTRACT['production_enabled'] is False


def test_root_delete_and_replace_refused_and_handles_released(arena):
    import ctypes
    from ctypes import wintypes as T
    arena.api.k.GetCurrentProcess.restype=T.HANDLE
    arena.api.k.GetProcessHandleCount.argtypes=[T.HANDLE,ctypes.POINTER(T.DWORD)]
    def handles():
        count=T.DWORD()
        arena.api.ok(arena.api.k.GetProcessHandleCount(arena.api.k.GetCurrentProcess(),ctypes.byref(count)))
        return count.value
    with pytest.raises(OSError):arena.root.rmdir()
    replacement=arena.root.with_name(arena.root.name+'-replacement')
    replacement.mkdir()  # New dedicated test directory, retained.
    with pytest.raises(OSError):replacement.replace(arena.root)
    empty=arena.mkdir('empty-held')
    held=arena.api.open_directory(empty)
    try:
        with pytest.raises(OSError):empty.rmdir()
        with pytest.raises(OSError):empty.rename(arena.root/'empty-moved')
        another=arena.mkdir('empty-replacement')
        with pytest.raises(OSError):another.replace(empty)
    finally:
        arena.api.ok(arena.api.k.CloseHandle(held))
    before=handles()
    for _ in range(3):
        h=arena.api.open_directory(arena.root)
        arena.api.ok(arena.api.k.CloseHandle(h))
    assert handles()==before


def test_plain_directory_swap_and_scope_change_rejected(arena):
    original=arena.mkdir('original')
    original.rename(arena.root/'old-original')
    original.mkdir()  # Entirely inside a newly created test arena.
    with pytest.raises(StagingHold,match='identity'):arena.write_new('original/no',b'x')
    (arena.root/'scope.json').write_bytes(b'{"scope":"PRODUCTION"}\n')
    with pytest.raises(StagingHold,match='scope_changed'):arena.write_new('no',b'x')


def test_parent_swap_during_write_is_OS_rejected(arena,monkeypatch):
    parent=arena.mkdir('parent')
    original=Path.open
    def checked(path,*args,**kwargs):
        if path==parent/'ok' and args and args[0]=='x+b':
            with pytest.raises(OSError):parent.rename(arena.root/'swapped')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',checked)
    arena.write_new('parent/ok',b'complete')
    assert (parent/'ok').read_bytes()==b'complete'


def test_saved_parent_ACL_and_lock_token_corruption_HOLD(arena,monkeypatch):
    original=arena.api.delete_owned_lock_on_close
    def wrong_token(handle,path,token,file_id):
        return original(handle,path,token+b'wrong',file_id)
    monkeypatch.setattr(arena.api,'delete_owned_lock_on_close',wrong_token)
    with pytest.raises(StagingHold,match='lock_owner_changed'):
        with arena.transaction('e'*64):pass
    assert (arena.root/'publication.lock').is_file()


def test_mock_HTTP_rate_and_0700_boundary(e2e,arena):
    urls=('https://data.j-league.or.jp/SFMS02/?rate=one','https://data.j-league.or.jp/SFMS02/?rate=two')
    http=s.MockHTTP({u:transport_response(u) for u in urls})
    base=e2e.now-timedelta(minutes=10)
    times=iter([base,base,base+timedelta(seconds=1),base+timedelta(seconds=5)])
    worker=s.SourceWorkerCandidate(e2e.source_workspace,e2e.ref,e2e.friday)
    with pytest.raises(StagingHold,match='rate_limit'):worker.collect_mock(arena,urls,http,clock=lambda:next(times))
    assert http.called==[urls[0]]


def test_mock_HTTP_after_cutoff_retains_failure_receipt(e2e,arena):
    url='https://data.j-league.or.jp/SFMS02/?late=one'
    http=s.MockHTTP({url:transport_response(url)})
    times=iter([e2e.now,e2e.now,e2e.now+timedelta(microseconds=1)])
    worker=s.SourceWorkerCandidate(e2e.source_workspace,e2e.ref,e2e.friday)
    with pytest.raises(StagingHold,match='after_0700'):worker.collect_mock(arena,(url,),http,clock=lambda:next(times))
    holds=list(arena.root.glob('*.HOLD.json'))
    assert len(holds)==1 and w.read_json(holds[0])['production_admission'] is False and len(http.called)==1


@pytest.mark.parametrize('kind',['classes','marker','features'])
def test_mock_Champion_input_contract_refuses_changes(e2e,kind):
    backend=candidate(e2e)
    if kind=='classes':
        e2e.model.classes_=np.array([2,1,0])
        with pytest.raises(StagingHold):backend.adapter.verify()
    elif kind=='marker':
        e2e.model.synthetic_only=False
        with pytest.raises(StagingHold):backend.adapter.verify()
    else:
        backend.adapter.expected=np.asarray([[1.]])
        with pytest.raises(StagingHold):backend.adapter.artifact.scaler.transform(np.asarray([[2.]]))
    assert not e2e.model.inputs


def test_bad_mock_probabilities_do_not_publish(e2e,arena,monkeypatch):
    backend=candidate(e2e)
    monkeypatch.setattr(e2e.model,'predict_proba',lambda matrix:np.tile([.2,.3,.9],(len(matrix),1)))
    with pytest.raises(ValueError,match='probability_contract'):
        pub.Publisher(arena).run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    assert not list((e2e.runtime/'batches').glob('weekend-v2-*')) and not list(arena.root.glob('batch-*'))


def test_new_staging_envelope_is_rejected_by_operational_saved_reader(e2e,arena):
    backend=candidate(e2e)
    request_id,_=pub.Publisher(arena).run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    fake_runtime=arena.mkdir('reader-only-runtime')
    arena.mkdir('reader-only-runtime/batches')
    (fake_runtime/'batches'/('batch-'+request_id)).mkdir()
    # Reader sees a staging-format descriptor, never an operational batch.
    descriptor=(arena.root/('batch-'+request_id)/'staging-manifest.json').read_bytes()
    (fake_runtime/'batches'/('batch-'+request_id)/'manifest.json').write_bytes(descriptor)
    with pytest.raises(ValueError):pub.updater.saved_batches(fake_runtime)


def test_saved_feed_error_retains_batch_and_requires_manual_review(e2e,arena,monkeypatch):
    backend=candidate(e2e); publisher=pub.Publisher(arena)
    old=(e2e.runtime/'view/champion_home.json').read_bytes()
    monkeypatch.setattr(pub.updater,'build_display_feeds',lambda *a:(_ for _ in ()).throw(OSError('mock feed failure')))
    with pytest.raises(OSError):publisher.run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    assert len(e2e.model.inputs)==1 and list((e2e.runtime/'batches').glob('weekend-v2-source-*'))
    assert (e2e.runtime/'view/champion_home.json').read_bytes()==old
    saved=tree(e2e.runtime/'batches')
    with pytest.raises(OSError):publisher.run_mock(backend,e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now)
    assert tree(e2e.runtime/'batches')==saved and len(e2e.model.inputs)==1


def test_evening_cannot_generate_new_batch(e2e,arena):
    with pytest.raises(StagingHold,match='evening_prediction_generation_forbidden'):
        pub.Publisher(arena).run_mock(candidate(e2e),e2e.repo,e2e.runtime,e2e.config,clock=lambda:e2e.now,slot='evening')
    assert not e2e.model.inputs
