"""Launch argument contract only; no Desktop, real server or model execution."""
from pathlib import Path
from unittest.mock import Mock
import pytest
from scripts import launch_dashboard as launcher


def test_weekend_forwarding_and_legacy_command_unchanged(tmp_path):
    python=tmp_path/'python.exe';data=tmp_path/'base.json';weekend=tmp_path/'weekend.json'
    original=launcher.server_command(python,data)
    assert launcher.server_command(python,data,weekend_data=weekend)==original+['--weekend-data',str(weekend.resolve())]
    assert '--weekend-data' not in launcher.server_command(python,None)


def test_unpaired_command_refused(tmp_path):
    with pytest.raises(ValueError): launcher.server_command(Path('python.exe'),None,weekend_data=tmp_path/'weekend.json')


@pytest.mark.parametrize('args',[['--weekend-data','x'],['--stop','--weekend-data','x']])
def test_unpaired_cli_refused_before_any_IPC(monkeypatch,args):
    controls=Mock();monkeypatch.setattr(launcher,'WindowsInstance',controls)
    with pytest.raises(SystemExit) as e: launcher.main(args)
    assert e.value.code==2;controls.assert_not_called()


def test_cli_forwards_both_paths_and_default_browser(monkeypatch,tmp_path):
    run=Mock(return_value=0);monkeypatch.setattr(launcher,'run_launcher',run)
    data=tmp_path/'base.json';weekend=tmp_path/'weekend.json'
    assert launcher.main(['--data',str(data),'--weekend-data',str(weekend),'--browser-mode','default'])==0
    assert run.call_args.kwargs['data']==data and run.call_args.kwargs['weekend_data']==weekend
    assert run.call_args.kwargs['browser_mode']=='default'


def test_unpaired_function_refused_before_IPC(monkeypatch,tmp_path):
    monkeypatch.setattr(launcher,'require_windows',lambda:None)
    controls=Mock();monkeypatch.setattr(launcher,'WindowsInstance',controls)
    with pytest.raises(ValueError): launcher.run_launcher(tmp_path,weekend_data=tmp_path/'weekend.json')
    controls.assert_not_called()
