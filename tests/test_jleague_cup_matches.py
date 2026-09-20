import hashlib,json
import pytest
from src.collect.jleague_cup_matches import parse_sfms01_html,_get
HTML='''<table class="table-base00 search-table"><tr><td>2015</td><td>ＹＮＣ 予選</td><td>第１節</td><td>15/03/18(水)</td><td>19:00</td><td>鳥栖</td><td><a href="/SFMS02/?match_card_id=123">1-0</a></td><td>松本</td><td>x</td><td>x</td><td>x</td></tr></table>'''
def test_parse_row():
 r=parse_sfms01_html(HTML,expected_season=2015).iloc[0]; assert r.source_match_id=='123'; assert r.competition=='jleague_cup'; assert r.home_team=='鳥栖'; assert r.match_date.year==2015
def test_season_reject():
 with pytest.raises(ValueError): parse_sfms01_html(HTML,expected_season=2024)
def test_selector_and_unrelated_table_are_ignored():
 html='<select><option>琉球</option></select><table><tr><td>2015</td><td>x</td></tr></table>'+HTML
 r=parse_sfms01_html(html,expected_season=2015); assert len(r)==1 and '琉球' not in set(r.home_team)|set(r.away_team)
def test_duplicate_match_id_rejected():
 with pytest.raises(ValueError): parse_sfms01_html(HTML+HTML,expected_season=2015)
def test_cache_reuse(tmp_path):
 u='https://example.test'; b=b'x'; k=hashlib.sha256(u.encode()).hexdigest(); (tmp_path/(k+'.html')).write_bytes(b); (tmp_path/(k+'.metadata.json')).write_text(json.dumps({'requested_url':u,'final_url':u,'status':200,'bytes':1,'sha256':hashlib.sha256(b).hexdigest()})); assert _get(u,tmp_path,0)[0]==b
