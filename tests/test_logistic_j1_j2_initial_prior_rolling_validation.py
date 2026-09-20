import pandas as pd
import pytest

from src.modeling.logistic_j1_j2_initial_prior_rolling_validation import (
    J2_INITIAL_RATING,
    VARIANTS,
    _replay,
    _stream,
)


def _stream_fixture():
    return pd.DataFrame([
        {"event_key":"j1:a","season":2015,"match_date":pd.Timestamp("2015-03-01"),"home_team_id":"j1","away_team_id":"j1b","result":2},
        {"event_key":"j2:b","season":2015,"match_date":pd.Timestamp("2015-03-02"),"home_team_id":"j2","away_team_id":"j2b","result":1},
        {"event_key":"j1:c","season":2016,"match_date":pd.Timestamp("2016-03-01"),"home_team_id":"j2","away_team_id":"j1","result":0},
    ])


def test_fixed_variants_and_j2_prior():
    assert VARIANTS == ("current", "equal_j1_j2", "j2_initial_1400")
    replay, initial = _replay(_stream_fixture(), 2015, j2_prior=True)
    assert initial["j1"] == 1500.0
    assert initial["j2"] == J2_INITIAL_RATING


def test_rating_is_carried_without_reset():
    stream = _stream_fixture()
    replay, _ = _replay(stream, 2016, j2_prior=True)
    # The J2 club's 2016 J1 row has a pre-match rating different from 1400,
    # proving the division change did not reset it.
    row = replay.loc[replay.event_key.eq("j1:c")].iloc[0]
    assert row.home_elo != pytest.approx(1400.0)


def test_same_day_duplicate_is_rejected():
    frame = _stream_fixture()
    frame.loc[1, "match_date"] = frame.loc[0, "match_date"]
    frame.loc[1, "home_team_id"] = "j1"
    with pytest.raises(ValueError, match="same team"):
        _stream(frame.iloc[[0]], frame.iloc[[1]])
