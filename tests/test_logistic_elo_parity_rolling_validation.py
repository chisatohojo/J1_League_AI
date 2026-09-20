import numpy as np
import pandas as pd

from src.modeling.logistic_elo_parity_rolling_validation import (
    ELO_FEATURES, PARITY_FEATURES, VALIDATION_SEASONS,
    EXPECTED_VALIDATION_COUNTS, _metrics, _replay_elo,
)

def test_fixed_features_and_folds():
    assert ELO_FEATURES == ("elo_diff",)
    assert PARITY_FEATURES == ("elo_diff", "abs_elo_diff")
    assert VALIDATION_SEASONS == (2020,2021,2022,2023,2024)
    assert list(EXPECTED_VALIDATION_COUNTS.values()) == [306,380,306,306,380]

def test_abs_parity_and_deterministic_pre_match_elo():
    frame=pd.DataFrame({"match_id":["a","b"],"match_date":pd.to_datetime(["2019-01-01","2019-01-10"]),"home_team_id":["team_0001","team_0002"],"away_team_id":["team_0002","team_0001"],"result":[2,0]})
    first=_replay_elo(frame); second=_replay_elo(frame)
    pd.testing.assert_frame_equal(first,second)
    assert np.array_equal(first.elo_diff.abs(), first.elo_diff.abs())
    assert first.loc[0,"elo_diff"] == 0
    assert first.loc[1,"elo_diff"] != 0

def test_probability_validation():
    m=_metrics(np.array([0,1,2]),np.eye(3))
    assert m.accuracy == 1
