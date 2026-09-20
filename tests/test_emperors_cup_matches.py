import json, hashlib
import pandas as pd
import pytest
from src.collect.emperors_cup_matches import parse_jfa_schedule_json, _get

PAYLOAD={'matchScheduleList':{'competitionName':'天皇杯','matchSchedule':[{'matchTypeName':'1回戦','matchNumber':'1','matchDate':'2015/08/29','homeTeamName':'J1 FC','awayTeamName':'大学FC'}]}}
def test_official_schedule_row_parse():
 r=parse_jfa_schedule_json(PAYLOAD,season=2015).iloc[0]
 assert r.match_date==pd.Timestamp('2015-08-29') and r.home_team=='J1 FC' and r.away_team=='大学FC'
 assert r.round_raw=='1回戦' and r.competition=='emperors_cup' and r.source_match_id=='2015-m01'
 assert r.source_url.endswith('/match_page/m1.html')
def test_duplicate_identity_rejected():
 p={'matchScheduleList':dict(PAYLOAD['matchScheduleList'],matchSchedule=PAYLOAD['matchScheduleList']['matchSchedule']*2)}
 with pytest.raises(ValueError): parse_jfa_schedule_json(p,season=2015)
def test_cache_reuse(tmp_path):
 u='https://example.test/schedule.json'; b=b'{}'; k=hashlib.sha256(u.encode()).hexdigest(); (tmp_path/(k+'.json')).write_bytes(b); (tmp_path/(k+'.metadata.json')).write_text(json.dumps({'requested_url':u,'final_url':u,'status':200,'bytes':2,'sha256':hashlib.sha256(b).hexdigest()})); assert _get(u,tmp_path,0)[1]
