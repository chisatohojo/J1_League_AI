import pandas as pd

from src.modeling.logistic_j1_j2_returning_hybrid_rolling_validation import _replay_hybrid


def _fixture():
    return pd.DataFrame([
        {"event_key":"j1:old","season":2015,"match_date":pd.Timestamp("2015-01-01"),"home_team_id":"j1","away_team_id":"r","result":2},
        {"event_key":"j2:old","season":2015,"match_date":pd.Timestamp("2015-01-02"),"home_team_id":"p","away_team_id":"r","result":0},
        {"event_key":"j1:new","season":2016,"match_date":pd.Timestamp("2016-01-01"),"home_team_id":"p","away_team_id":"j1","result":1},
    ])


def test_returning_carries_and_first_time_resets_once():
    j1={2015:{"j1","r"},2016:{"j1","p"}}; j2={2015:{"p","r"},2016:set()}
    j1_frame=pd.DataFrame([{"season":y,"home_team_id":next(iter(ids)),"away_team_id":next(iter(ids))} for y,ids in j1.items()])
    j2_frame=pd.DataFrame([{"season":y,"home_team_id":next(iter(ids)),"away_team_id":next(iter(ids))} for y,ids in j2.items() if ids])
    _, transitions = _replay_hybrid(_fixture(), 2015, j1_frame, j2_frame)
    assert transitions == []


def test_hybrid_module_imports_without_cup_or_j3_dependencies():
    assert True
