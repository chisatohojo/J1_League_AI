"""Synthetic 98-result publication, result update and ten new saved predictions. No model/network."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import threading
import socket
from urllib.request import build_opener, ProxyHandler
from unittest.mock import Mock
from pathlib import Path
import sys

import pytest
from scripts import retrospective_generations as generations
from scripts import build_retrospective_preview as builder
from scripts import update_champion_dashboard as update
from scripts.dashboard_retrospective import build_overlay
from scripts.retrospective_display import CHAMPION_HASH, encoded, sha, validate_overlay
from scripts.serve_dashboard import CHAMPION_MODEL, create_server
from test_champion_dashboard_update import operational, repository, snapshot, NOW


@pytest.fixture(autouse=True)
def loopback_only(monkeypatch):
    connect=socket.socket.connect
    def guarded(instance,address):
        assert address[0]=="127.0.0.1","External network forbidden"
        return connect(instance,address)
    monkeypatch.setattr(socket.socket,"connect",guarded)


def synthetic_pair(stage=0):
    rounds=[];entries=[];identities={}
    for number in range(1,12 if stage>=2 else 11):
        matches=[]
        for i in range(10):
            key=f"j1_2026_2027:club{number}_{i}:away{number}_{i}"
            completed=number<=9 or number==10 and (i<8 or stage>=1)
            saved=number==9 and i<2 or number==10 and i>=8 or number==11
            day=(datetime(2026,8,7)+timedelta(days=(number-1)*7)).date().isoformat()
            if number==9: day="2026-10-09"
            if number==10: day="2026-10-17" if i<8 else "2026-10-18"
            if number==11: day="2026-10-21"
            prediction=dict(source="saved_pre_match",generatedAt="2026-08-01T00:00:00Z",
                probabilities=dict(home=55,draw=25,away=20)) if saved else None
            match=dict(id=key,round=number,status="completed" if completed else "scheduled",
                homeTeam=dict(id=f"team_{2*i+1:04d}",name=f"Home {i}"),
                awayTeam=dict(id=f"team_{2*i+2:04d}",name=f"Away {i}"),
                kickoffAt=day+"T19:00:00+09:00",prediction=prediction,
                result=dict(homeScore=2,awayScore=1) if completed else None)
            identities[key]=dict(id=str(100000+number*10+i),namespace="jleague_match_page")
            # The reconstruction is fixed at 98. Later results never acquire fabricated probabilities.
            if (number<=9 or number==10 and i<8) and not saved:
                entries.append(dict(fixtureKey=key,round=number,matchDate=day,
                    homeTeamId=match["homeTeam"]["id"],awayTeamId=match["awayTeam"]["id"],
                    officialId=identities[key]["id"],officialNamespace="jleague_match_page",result=deepcopy(match["result"]),
                    reconstruction=dict(type="retrospective_reconstruction",calculatedAt="2026-10-18T05:00:00Z",
                        probabilities=dict(home=55,draw=25,away=20),predictedOutcome="home",hit=True,
                        modelHash="6"*64,artifactHash=CHAMPION_HASH)))
            matches.append(match)
        rounds.append(dict(number=number,label=f"Round {number}",kind="previous",matches=matches))
    observed=["2026-10-18T00:00:00Z","2026-10-18T13:00:00Z","2026-10-18T22:00:00Z"][stage]
    previous=deepcopy(rounds[8 if stage<2 else 9]);following=deepcopy(rounds[9 if stage<2 else 10]);following["kind"]="current" if stage<2 else "next"
    data=dict(schemaVersion=2,mode="operational",model=dict(CHAMPION_MODEL),updatedAt=observed,
        previousRound=previous,nextRound=following)
    overlay=dict(schemaVersion=1,type="retrospective_overlay",model=dict(CHAMPION_MODEL),runId="1"*64,
        reconstructionRevision="2"*64,officialRevision=str(stage+3)*64,officialObservedAt=observed,
        note="当時の試合前保存予測ではありません",dashboardSha256=sha(encoded(data)),entries=entries,
        historyRounds=rounds,officialIdentities=identities,diagnostics=[])
    return data,validate_overlay(overlay,data)


def get(url):
    with build_opener(ProxyHandler({})).open(url,timeout=5) as response: return json.load(response)


@pytest.fixture
def store(tmp_path):
    root=tmp_path/"display-store"
    first=generations.publish_pair(root,*synthetic_pair(),"7"*64)
    return root,first["store_sha256"]


def test_98_results_then_results_and_ten_predictions_atomic_reload(store):
    root,anchor=store
    before=generations.read_current(root,anchor)
    sealed={p:p.read_bytes() for p in (root/"generations").rglob("*") if p.is_file()}
    server=create_server(port=0,generation_store=root,store_sha=anchor)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f"http://127.0.0.1:{server.server_address[1]}/api/presentation"
    try:
        initial=get(url)
        assert initial["sequence"]==1 and initial["status"]["pollSeconds"]==60
        assert sum(m["status"]=="completed" for r in initial["overlay"]["historyRounds"] for m in r["matches"])==98
        assert len(initial["overlay"]["entries"])==96
        for stage in (1,2):
            data,overlay=synthetic_pair(stage)
            result=generations.publish_pair(root,data,overlay,"7"*64,expected_store_sha=anchor)
            seen=get(url)
            assert seen["sequence"]==stage+1 and seen["generationId"]==result["generation"]
            assert seen["dashboard"]==data and seen["overlay"]==overlay
            assert sum(m["prediction"] is not None for r in overlay["historyRounds"] for m in r["matches"])==(4 if stage==1 else 14)
            assert len(overlay["entries"])==96
        latest=get(url)
        # Missing one half cannot expose the new v2 paired with the old overlay.
        current=generations.read_current(root,anchor)
        path=root/"generations"/current["pointer"]["generation"]/"retrospective-overlay.json"
        original=path.read_bytes();path.write_bytes(b"{}")
        retained=get(url)
        assert retained["dashboard"]==latest["dashboard"] and retained["overlay"]==latest["overlay"]
        assert retained["status"]["state"]=="error"
        path.write_bytes(original)
        # Updating state holds the old pair, even when another valid pair is committed.
        generations.atomic(root/"status.json",dict(state="updating",startedAt=None,finishedAt=None,lastSuccessAt=None,errorCode=None))
        assert get(url)["generationId"]==latest["generationId"]
        generations.atomic(root/"current.json",before["pointer"])
        generations.atomic(root/"status.json",dict(state="ready",startedAt=None,finishedAt=None,lastSuccessAt=None,errorCode=None))
        assert get(url)["generationId"]==latest["generationId"]  # rollback rejected
        assert all(p.read_bytes()==body for p,body in sealed.items())
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)


def test_idempotence_anchor_lock_and_failed_publication_preserve_pointer(store,monkeypatch):
    root,anchor=store
    before=(root/"current.json").read_bytes()
    assert generations.publish_pair(root,*synthetic_pair(),"7"*64,expected_store_sha=anchor)["sequence"]==1
    assert (root/"current.json").read_bytes()==before
    with pytest.raises(ValueError): generations.read_current(root,"0"*64)
    (root/".publish.lock").write_text("another owner")
    with pytest.raises(FileExistsError): generations.publish_pair(root,*synthetic_pair(1),"7"*64,expected_store_sha=anchor)
    assert (root/".publish.lock").read_text()=="another owner";(root/".publish.lock").unlink()
    original=generations.atomic
    def fail_status(path,value):
        if path.name=="status.json" and value["state"]=="ready": raise OSError("synthetic commit failure")
        return original(path,value)
    monkeypatch.setattr(generations,"atomic",fail_status)
    with pytest.raises(OSError): generations.publish_pair(root,*synthetic_pair(1),"7"*64,expected_store_sha=anchor)
    assert (root/"current.json").read_bytes()==before
    assert generations.read_status(root)["state"]=="error"
    monkeypatch.setattr(generations,"atomic",original)
    assert generations.publish_pair(root,*synthetic_pair(1),"7"*64,expected_store_sha=anchor)["sequence"]==2


def test_optional_refresh_failure_cannot_fail_core_update(operational,monkeypatch,tmp_path):
    repo,runtime=operational
    original=snapshot(repo["root"])
    config=dict(lookahead_days=2,max_source_age_hours=24,retrospective_display=dict(store_root=str(tmp_path/"store"),
        store_sha256="1"*64,reconstruction_root=str(tmp_path/"replay"),ledger_sha256="2"*64))
    def display(*args,**kwargs):
        assert not(runtime/"update.lock").exists()
        assert json.loads((runtime/"view/update-status.json").read_bytes())["state"]=="ready"
        raise OSError("synthetic display failure")
    refresh=Mock(side_effect=display);monkeypatch.setattr(builder,"refresh_store",refresh)
    result=update.run_update(repo["root"],runtime,"evening",config,collector=lambda *args:None,clock=lambda:NOW)
    assert result==dict(added=0,total=4,state="ready",retrospectiveState="error")
    assert snapshot(repo["root"])==original
    assert json.loads((runtime/"view/update-status.json").read_bytes())["state"]=="ready"
    refresh.assert_called_once()


def test_update_connection_refreshes_external_store_after_core_success(operational,monkeypatch,tmp_path):
    repo,runtime=operational; root=tmp_path/"display-store"
    first=generations.publish_pair(root,*synthetic_pair(),"7"*64)
    options=dict(store_root=str(root),store_sha256=first["store_sha256"],
        reconstruction_root=str(tmp_path/"fixed-replay"),ledger_sha256="7"*64)
    config=dict(lookahead_days=2,max_source_age_hours=24,retrospective_display=options)
    def prepared(source,live,replay,ledger,destination,**kwargs):
        assert not(runtime/"update.lock").exists()
        assert json.loads((runtime/"view/update-status.json").read_bytes())["state"]=="ready"
        destination.mkdir()
        data,overlay=synthetic_pair(2)
        (destination/"champion_rounds.json").write_bytes(encoded(data))
        (destination/"retrospective-overlay.json").write_bytes(encoded(overlay))
    monkeypatch.setattr(builder,"build_preview",prepared)
    result=update.run_update(repo["root"],runtime,"evening",config,collector=lambda *args:None,clock=lambda:NOW)
    assert result["state"]==result["retrospectiveState"]=="ready"
    current=generations.read_current(root,first["store_sha256"])
    assert len(current["overlay"]["entries"])==96
    assert sum(m["prediction"] is not None for r in current["overlay"]["historyRounds"] for m in r["matches"])==14


def test_refresh_bad_source_retains_pair_and_marks_only_display_error(store,tmp_path):
    root,anchor=store;before=(root/"current.json").read_bytes()
    with pytest.raises(OSError): builder.refresh_store(tmp_path/"source",tmp_path/"runtime",tmp_path/"replay","7"*64,
        root,expected_store_sha=anchor)
    assert (root/"current.json").read_bytes()==before
    assert generations.read_current(root,anchor)["pointer"]["sequence"]==1
    assert generations.read_status(root)["state"]=="error"


@pytest.mark.skipif(sys.platform!="win32",reason="Windows interpreter ownership")
def test_generation_server_runs_on_the_retained_base_interpreter_handle(store):
    from scripts import launch_dashboard as launcher
    root,anchor=store
    process=launcher.start_server(Path(sys.executable),Path(launcher.__file__).parents[1],None,
        presentation_root=root,store_sha=anchor)
    try:
        url=launcher.wait_for_ready(process,10,require_data=True,expected_version=2)
        assert get(url+"api/presentation")["sequence"]==1
        assert process.poll() is None
    finally:
        launcher.stop_owned_server(process)
    assert process.poll() is not None
