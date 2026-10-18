"""Synthetic retrospective evidence; no official fetch, estimator or operational writes."""
from copy import deepcopy
from datetime import datetime
import json
from types import SimpleNamespace
import pytest

from test_champion_retrospective import reconstruction, repository, production_and_network_firewall, snapshot
from scripts import dashboard_retrospective as overlay
from scripts import build_dashboard_feed as feed
from scripts.serve_dashboard import create_server, validate_dashboard_data
from src.collect.teams import load_team_master
from src.modeling import champion_retrospective as retrospective


@pytest.fixture
def evidence(reconstruction,monkeypatch):
    data=reconstruction
    pins=retrospective.source_pins
    monkeypatch.setattr(retrospective,"source_pins",lambda root:dict(pins(root),**{
        f"models/model_a/{feed.CHAMPION_VERSION}/model.joblib":retrospective.champion.FILE_PINS["model.joblib"],
        f"models/model_a/{feed.CHAMPION_VERSION}/checksums.sha256":feed.CHAMPION_HASH}))
    retrospective.run_reconstruction(**data.options)
    retrospective.run_reconstruction(**data.options,stage="complete",resume=True)
    root=data.options["output"]
    run=json.loads((root/"run.json").read_bytes())
    ledger=dict(run_id=run["run_id"],files=[dict(path=p.relative_to(root).as_posix(),sha256=overlay.sha(p.read_bytes()))
        for p in sorted(root.rglob('*')) if p.is_file()])
    (root/"SHA256-MANIFEST.json").write_bytes(overlay.encoded(ledger))
    digest=overlay.sha((root/"SHA256-MANIFEST.json").read_bytes())
    master=load_team_master(data.repo["root"]/feed.TEAM_MASTER_PATH)
    official=feed.read_official_revision(data.repo["current_dir"],master,expected_sha=data.options["expected_sha"])
    run,rows=overlay.read_reconstruction(root,digest,master)
    names={a.team_id:a.canonical_name for a in master.aliases}
    saved={r["fixture_key"]:dict(prediction=dict(source="saved_pre_match",generatedAt="2026-08-01T00:00:00+00:00",
        probabilities=dict(home=31,draw=25,away=44))) for r in rows[:2]+rows[-2:]}
    dashboard=feed.round_dashboard(official,names,saved,now=datetime.fromisoformat('2026-10-09T00:00:00+09:00'))
    payload=overlay.build_overlay(dashboard,official,names,saved,run,rows)
    return SimpleNamespace(root=root,sha=digest,run=run,rows=rows,master=master,official=official,names=names,
        saved=saved,dashboard=dashboard,payload=payload)


def test_readonly_overlay_has_saved_priority_and_independent_source(evidence):
    e=evidence; before=snapshot(e.root); original=deepcopy(e.dashboard)
    assert len(e.payload["entries"])==16
    assert len(e.payload["historyRounds"])==2
    assert len(e.saved)==4
    assert not set(e.saved)&{r['fixtureKey'] for r in e.payload['entries']}
    assert overlay.validate_overlay(e.payload,e.dashboard) is e.payload
    assert validate_dashboard_data(e.dashboard) is e.dashboard and e.dashboard==original
    assert all(r['reconstruction']['type']=='retrospective_reconstruction' for r in e.payload['entries'])
    assert overlay.read_reconstruction(e.root,e.sha,e.master)[0]==e.run
    assert snapshot(e.root)==before


@pytest.mark.parametrize('problem', ['id','namespace','date','home','away','round','score','candidate','missing'])
def test_latest_official_mismatch_withholds_and_diagnoses(evidence,problem):
    e=evidence; current=deepcopy(e.official); key=e.rows[2]['fixture_key']
    index=current.schedule.index[current.schedule.fixture_key.eq(key)][0]
    col,value={'id':('match_id','555555'),'namespace':('match_id_namespace','jleague_match_page'),
        'date':('match_date','2026-08-10'),'home':('home_team_id','team_9998'),
        'away':('away_team_id','team_9999'),'round':('round','2'),'score':('home_score','9'),
        'candidate':('status','candidate'),'missing':('fixture_key','different') }[problem]
    current.schedule.loc[index,col]=value
    # Test the join boundary directly; malformed full-round official inputs are already rejected by the reader.
    row=current.schedule.loc[index]
    reason='fixture_missing' if problem=='missing' else overlay.identity_conflict(e.rows[2],row)
    assert reason is not None
    if problem in {'id','namespace','score','candidate'}:
        # These remain valid round structures, so exercise the complete withholding path too.
        if problem=='score':
            ci=current.completed.index[current.completed.fixture_key.eq(key)][0]
            current.completed.loc[ci,'home_score']='9'
        if problem=='candidate':
            current.completed.drop(current.completed.index[current.completed.fixture_key.eq(key)],inplace=True)
        dashboard=feed.round_dashboard(current,e.names,e.saved,now=datetime.fromisoformat('2026-10-09T00:00:00+09:00'))
        result=overlay.build_overlay(dashboard,current,e.names,e.saved,e.run,e.rows)
        assert key not in {r['fixtureKey'] for r in result['entries']}
        assert dict(fixtureKey=key,code=reason) in result['diagnostics']


@pytest.mark.parametrize('problem',['saved','id','namespace','swap','date','round','result','candidate','duplicate','hash','hit','time','extra','type'])
def test_python_display_contract_rejects_unsafe_overlay(evidence,problem):
    e=evidence; payload=deepcopy(e.payload); row=payload['entries'][0]
    match=next(m for section in payload['historyRounds'] for m in section['matches'] if m['id']==row['fixtureKey'])
    if problem=='saved': match['prediction']=deepcopy(next(iter(e.saved.values()))['prediction'])
    elif problem=='id': row['officialId']='888888'
    elif problem=='namespace': row['officialNamespace']='jleague_match_page' if row['officialNamespace']=='jleague_data_site' else 'jleague_data_site'
    elif problem=='swap': row['homeTeamId'],row['awayTeamId']=row['awayTeamId'],row['homeTeamId']
    elif problem=='date': row['matchDate']='2026-08-10'
    elif problem=='round': row['round']=33
    elif problem=='result': row['result']['homeScore']=9
    elif problem=='candidate': match.update(status='candidate',result=None)
    elif problem=='duplicate': payload['entries'].append(deepcopy(row))
    elif problem=='hash': row['reconstruction']['artifactHash']='0'*64
    elif problem=='hit': row['reconstruction']['hit']=not row['reconstruction']['hit']
    elif problem=='time': row['reconstruction']['calculatedAt']='2026-01-01T00:00:00Z'
    elif problem=='extra': row['reconstruction']['source']='saved_pre_match'
    else: row['reconstruction']['type']='saved_pre_match'
    with pytest.raises(ValueError): overlay.validate_overlay(payload,e.dashboard)


@pytest.mark.parametrize('filename',['run.json','prediction-seals/complete.json','complete/manifest.json',
    'complete/results.json','complete/summary.json','days/2026-08-07/predictions.json'])
def test_tamper_rejected_against_external_ledger_anchor(evidence,filename):
    e=evidence;(e.root/filename).write_bytes(b'{}')
    with pytest.raises(ValueError): overlay.read_reconstruction(e.root,e.sha,e.master)


def test_server_explicit_overlay_is_anchored_and_v2_cannot_masquerade(evidence,tmp_path):
    e=evidence; path=tmp_path/'overlay.json'; path.write_bytes(overlay.encoded(e.payload))
    before=path.read_bytes()
    server=create_server(e.dashboard,port=0,retrospective_path=path,retrospective_sha=overlay.sha(before))
    server.server_close()
    assert path.read_bytes()==before
    with pytest.raises(ValueError): create_server(e.dashboard,port=0,retrospective_path=path,retrospective_sha='0'*64)
    forged=deepcopy(e.dashboard)
    forged['previousRound']['matches'][0]['prediction']['source']='retrospective_reconstruction'
    with pytest.raises(ValueError): validate_dashboard_data(forged)
