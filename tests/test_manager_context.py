import pandas as pd
import pytest
from src.features.manager_context import FEATURE_COLUMNS, add_manager_context_features

def frames():
    m=pd.DataFrame({'match_id':['1','2','3','4'],'match_date':pd.to_datetime(['2020-01-01','2020-01-08','2020-01-15','2020-01-22']),'home_team_id':['a','b','a','b'],'away_team_id':['b','a','b','a'],'result':[2,0,1,2]})
    h=m.copy(); h['home_manager_staff_id']=['x','x',pd.NA,'y']; h['away_manager_staff_id']=['y','x','y',pd.NA]; return m,h
def test_context_features_and_unknown_gap():
    m,h=frames(); o=add_manager_context_features(m,h)
    assert o.loc[0,'home_manager_known']==1 and o.loc[0,'home_manager_change_known']==0
    assert o.loc[1,'home_manager_changed']==1 and o.loc[1,'home_manager_prior_matches_in_charge']==0
    assert o.loc[2,'home_manager_known']==0 and o.loc[2,'home_manager_prior_matches_in_charge']==0
    assert o.loc[3,'away_manager_change_known']==0 and o.loc[3,'away_manager_prior_matches_in_charge']==0
    assert all(str(o[c].dtype)=='int64' for c in FEATURE_COLUMNS)
def test_alignment_and_input_immutability():
    m,h=frames(); before=m.copy(deep=True); add_manager_context_features(m,h); pd.testing.assert_frame_equal(m,before)
    bad=h.copy(); bad.loc[0,'home_team_id']='z'
    with pytest.raises(ValueError): add_manager_context_features(m,bad)
