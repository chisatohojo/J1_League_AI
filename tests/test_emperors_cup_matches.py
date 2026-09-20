import json, hashlib
import pandas as pd
import pytest
from src.collect.emperors_cup_matches import parse_jfa_schedule_json, parse_jfa_2026_match_page, _get

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

def test_2026_match_page_completed_status_comes_from_score_cells():
    html = '''<div id="header-schedule-result"><div class="text-schedule">[56] 2026年08月26日 19:00 KickOff</div></div>
    <div id="score-board-header"><div class="flag"><p>Home</p></div><div class="total-score">1</div>
    <div class="total-score">0</div><div class="flag"><p>Away</p></div></div>'''
    row = parse_jfa_2026_match_page(html, match_number=56)
    assert row["completed"] is True and row["match_date"] == pd.Timestamp("2026-08-26")

def test_2026_match_page_future_has_empty_score():
    html = '''<div id="header-schedule-result"><div class="text-schedule">[57] 2026年09月23日 17:00 KickOff</div></div>
    <div id="score-board-header"><div class="flag"><p>Home</p></div><div class="total-score"></div>
    <div class="total-score"></div><div class="flag"><p>Away</p></div></div>'''
    assert parse_jfa_2026_match_page(html, match_number=57)["completed"] is False
