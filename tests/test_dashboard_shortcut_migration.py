"""Real Windows COM in temporary folders only; never the actual Desktop."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
from scripts import launch_dashboard as launch
from scripts import serve_dashboard as server
from scripts import unify_dashboard_shortcut as m

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows COM migration tests')


@pytest.fixture
def prepared(tmp_path):
    desktop=tmp_path/'desktop';desktop.mkdir()
    legacy=tmp_path/'legacy';(legacy/'scripts').mkdir(parents=True)
    (legacy/'scripts/launch_dashboard.py').write_text('# synthetic launcher')
    python=tmp_path/'python.exe';python.write_bytes(b'synthetic python')
    python.with_name('pythonw.exe').write_bytes(b'synthetic pythonw')
    data=tmp_path/'champion.json';data.write_text(json.dumps(server.empty_dashboard()))
    fields={'TargetPath':str(python.with_name('pythonw.exe')),'Arguments':m.subprocess.list2cmdline(['-B',str(legacy/'scripts/launch_dashboard.py'),'--runtime',str(tmp_path/'runtime'),'--view','rounds','--python',str(python)]),
            'WorkingDirectory':str(legacy),'IconLocation':str(m.ROOT/'web/assets/j1ai.ico')+',0',
            'Description':'J1AI Champion A launcher v1 | '+str(legacy)+' | '+str(tmp_path/'runtime')}
    old=desktop/'J1AI legacy.lnk';m.link(old,fields)
    p=m.plan(python,data,folders=[desktop],registered=[legacy])
    return desktop,old,p,tmp_path/'backup'


def test_real_COM_create_plan_apply_and_exact_rollback(prepared):
    desktop,old,p,backup=prepared
    original=old.read_bytes()
    assert p['mode']=='DRY_RUN_ONLY' and old.read_bytes()==original and not (desktop/'J1AI.lnk').exists()
    m.apply(p,backup)
    assert not old.exists() and m.link(desktop/'J1AI.lnk')==p['new_fields']
    with pytest.raises(ValueError):m.apply(p,backup.parent/'second-backup')
    m.rollback(backup)
    assert old.read_bytes()==original and not (desktop/'J1AI.lnk').exists()


@pytest.mark.parametrize('field',['TargetPath','WorkingDirectory','Arguments','Description'])
def test_owner_or_target_changes_STOP_before_desktop_mutation(prepared,field):
    desktop,old,p,backup=prepared
    fake=deepcopy(p);fake['old'][0]['fields'][field]='unrelated'
    before=old.read_bytes()
    with pytest.raises((ValueError,KeyError)):m.apply(fake,backup)
    assert old.read_bytes()==before and not (desktop/'J1AI.lnk').exists() and not backup.exists()


def test_other_repository_or_unknown_shortcut_not_adopted(prepared):
    desktop,old,p,backup=prepared
    fields=m.link(old);fields['Description']='Unrelated'
    other=desktop/'J1AI unrelated.lnk';m.link(other,fields);before=other.read_bytes()
    with pytest.raises(ValueError,match='No verified owned'):
        m.plan(Path(p['new_fields']['TargetPath']).with_name('python.exe'),Path(m.argv(p['new_fields']['Arguments'])[3]),folders=[desktop],registered=[])
    assert other.read_bytes()==before


def test_foreign_destination_and_modified_rollback_STOP(prepared):
    desktop,old,p,backup=prepared
    m.apply(p,backup)
    (desktop/'J1AI.lnk').write_bytes(b'changed by another owner')
    with pytest.raises(ValueError,match='changed'):m.rollback(backup)
    assert not old.exists()


def test_partial_migration_failure_keeps_backups_and_rolls_back(prepared,monkeypatch):
    desktop,old,p,backup=prepared
    second=desktop/'J1AI second.lnk';m.link(second,m.link(old))
    original={q:q.read_bytes() for q in [old,second]}
    args=m.argv(p['new_fields']['Arguments'])
    p=m.plan(Path(args[5]),Path(args[3]),folders=[desktop],registered=[Path(p['old'][0]['fields']['WorkingDirectory'])])
    unlink=Path.unlink
    def fail(path,*a,**k):
        if path==second:raise OSError('synthetic failure after first legacy removal')
        return unlink(path,*a,**k)
    with monkeypatch.context() as scoped:
        scoped.setattr(Path,'unlink',fail)
        with pytest.raises(OSError):m.apply(p,backup)
    assert (desktop/'J1AI.lnk').exists() and not old.exists() and second.exists()
    assert (backup/'manifest.json').exists() and not (backup/'applied.json').exists()
    m.rollback(backup)
    assert not (desktop/'J1AI.lnk').exists()
    for q,data in original.items():assert q.read_bytes()==data


def test_source_input_changed_after_plan_STOP(prepared):
    desktop,old,p,backup=prepared
    source=Path(next(k for k in p['pins'] if k.endswith('champion.json')));source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='input changed'):m.apply(p,backup)
    assert old.exists() and not backup.exists()


def test_reparse_and_traversal_refused(tmp_path):
    with pytest.raises(ValueError,match='traversal'):m.safe(tmp_path/'..'/'escape')
    target=tmp_path/'target';target.mkdir();junction=tmp_path/'junction'
    result=m.subprocess.run(['cmd','/c','mklink','/J',str(junction),str(target)],capture_output=True)
    assert result.returncode==0
    try:
        with pytest.raises(ValueError,match='Reparse'):m.safe(junction/'file')
    finally:junction.rmdir()  # removes only this known junction, never recursive deletion


def test_help_and_import_no_desktop_side_effect(monkeypatch,capsys):
    monkeypatch.setattr(m,'desktop_paths',lambda:pytest.fail('Desktop accessed'))
    monkeypatch.setattr(m,'link',lambda *a:pytest.fail('COM accessed'))
    with pytest.raises(SystemExit) as result:m.main(['--help'])
    assert result.value.code==0 and 'rollback' in capsys.readouterr().out


def test_icon_sizes_and_windows_shell_extraction(tmp_path):
    from PIL import Image
    ico=m.ROOT/'web/assets/j1ai.ico'
    with Image.open(ico) as image:
        assert image.ico.sizes()=={(n,n) for n in [16,24,32,48,64,128,256]}
        for size in image.ico.sizes(): assert image.ico.getimage(size).convert('RGBA').getbbox()
    # Shell icon extraction uses the same native icon resource mechanism as Explorer.
    import ctypes
    shell=ctypes.WinDLL('shell32');user=ctypes.WinDLL('user32')
    shell.ExtractIconExW.argtypes=(ctypes.c_wchar_p,ctypes.c_int,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint)
    icon=ctypes.c_void_p();small=ctypes.c_void_p()
    assert shell.ExtractIconExW(str(ico),0,ctypes.byref(icon),ctypes.byref(small),1)==1
    user.DestroyIcon.argtypes=(ctypes.c_void_p,)
    for handle in [icon,small]:
        if handle.value:assert user.DestroyIcon(handle)


def test_default_browser_launcher_only_opens_validated_url(monkeypatch):
    seen=[];monkeypatch.setattr(launch.os,'startfile',seen.append)
    launch.start_default_browser('http://127.0.0.1:4321/')
    assert seen==['http://127.0.0.1:4321/']
    for url in ['https://example.com/','http://127.0.0.1:4321/?demo=1','http://localhost:4321/']:
        with pytest.raises(launch.LauncherError):launch.start_default_browser(url)
    def fail(url):raise OSError('synthetic association failure')
    monkeypatch.setattr(launch.os,'startfile',fail)
    with pytest.raises(launch.LauncherError) as error:launch.start_default_browser('http://127.0.0.1:4321/')
    assert error.value.code=='default_browser_failed'


def test_real_windows_mutex_and_owned_server_duplicate_stop_restart(tmp_path,monkeypatch):
    import threading,time
    events=[];urls=[];processes=[];errors=[]
    real_start=launch.start_server
    def start(python,root,data):
        child=real_start(python,m.ROOT,data);processes.append(child);return child
    monkeypatch.setattr(launch,'start_server',start)
    monkeypatch.setattr(launch,'record_event',lambda root,code:events.append(code))
    monkeypatch.setattr(launch,'show_message',lambda *a,**k:None)
    monkeypatch.setattr(launch,'start_default_browser',urls.append)
    data=tmp_path/'synthetic.json';data.write_text(json.dumps(server.empty_dashboard()))
    def run():
        try:launch.run_launcher(tmp_path,data=data,python=Path(sys.executable),browser_mode='default',timeout=8)
        except Exception as exc:errors.append(exc)
    for cycle in range(2):
        worker=threading.Thread(target=run,daemon=True);worker.start()
        try:
            deadline=time.monotonic()+10
            while len(urls)<=cycle and not errors and time.monotonic()<deadline:time.sleep(.03)
            assert not errors and len(urls)==cycle+1
            launch.run_launcher(tmp_path,data=data,python=Path(sys.executable),browser_mode='default')
            assert len(processes)==cycle+1 and events.count('already_running')==cycle+1
            assert processes[-1].poll() is None
        finally:
            controls=launch.WindowsInstance(tmp_path)
            controls.signal_stop();controls.close();worker.join(timeout=8)
        assert not worker.is_alive() and processes[-1].poll() is not None and not errors
    assert len(processes)==2 and events.count('stopped')==2
