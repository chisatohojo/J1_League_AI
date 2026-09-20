import pandas as pd
import pytest

from src.modeling.logistic_j1_j2_promotion_calibrated_rolling_validation import _replay_calibrated


def _fixture():
    return pd.DataFrame([
        {"event_key":"j1:old","season":2015,"match_date":pd.Timestamp("2015-01-01"),"home_team_id":"r","away_team_id":"p","result":2},
        {"event_key":"j2:old","season":2015,"match_date":pd.Timestamp("2015-01-02"),"home_team_id":"p","away_team_id":"q","result":0},
        {"event_key":"j1:new","season":2016,"match_date":pd.Timestamp("2016-01-01"),"home_team_id":"p","away_team_id":"r","result":1},
    ])


def test_promoted_intersection_receives_one_boundary_offset():
    j1 = {2015:{"r"}, 2016:{"p","r"}}
    j2 = {2015:{"p","q"}, 2016:{"r"}}
    _, transitions = _replay_calibrated(_fixture(), 2016, j1, j2)
    transition = [x for x in transitions if x["season"] == 2016][0]
    assert transition["promoted_ids"] == ("p",)
    assert transition["relegated_ids"] == ("r",)
    assert transition["offset"] == pytest.approx(transition["mean_relegated_pre"] - transition["mean_promoted_pre"])


def test_2015_has_no_calibration():
    _, transitions = _replay_calibrated(_fixture(), 2015, {2015:{"r"}}, {2015:{"p"}})
    assert transitions == []


def test_empty_group_uses_zero_offset():
    _, transitions = _replay_calibrated(_fixture(), 2016, {2015:{"r"}, 2016:{"p","r"}}, {2015:set(), 2016:set()})
    transition = [x for x in transitions if x["season"] == 2016][0]
    assert transition["offset"] == 0.0
