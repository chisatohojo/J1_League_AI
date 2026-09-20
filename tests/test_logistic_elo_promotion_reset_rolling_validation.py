import pandas as pd
from src.modeling.logistic_elo_promotion_reset_rolling_validation import (
    VALIDATION_SEASONS, EXPECTED_VALIDATION_COUNTS, _replay,
)

def test_fixed_folds_and_counts():
    assert VALIDATION_SEASONS==(2020,2021,2022,2023,2024)
    assert list(EXPECTED_VALIDATION_COUNTS.values())==[306,380,306,306,380]

def test_reset_only_returning_entry_and_continuous_club_not_reset():
    f=pd.DataFrame({"match_id":["a","b","c"],"season":[2015,2016,2017],"match_date":pd.to_datetime(["2015-01-01","2016-01-01","2017-01-01"]),"home_team_id":["team_0001","team_0001","team_0002"],"away_team_id":["team_0002","team_0003","team_0003"],"result":[2,2,2]})
    memberships={2015:{"team_0001","team_0002"},2016:{"team_0001","team_0003"},2017:{"team_0002","team_0003"}}
    current,_=_replay(f,memberships,False); reset,_=_replay(f,memberships,True)
    assert reset.loc[reset.match_id=="c","elo_diff"].iloc[0] != current.loc[current.match_id=="c","elo_diff"].iloc[0]
