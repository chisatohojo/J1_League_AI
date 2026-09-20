import pandas as pd
import pytest
from src.collect.afc_club_matches import *

LEGACY='''<html><body><h1>AFC CHAMPIONS LEAGUE 2019</h1><div>2019-06-18</div><div>KASHIMA ANTLERS (JPN)</div><div>1</div><div>SANFRECCE HIROSHIMA (JPN)</div></body></html>'''
def test_legacy_official_id_parse():
 r=parse_legacy_match_report_html(LEGACY,source_match_id='16143',source_url='https://stats.the-afc.com/match_report/16143')
 assert r['identity_type']=='official_match_id' and r['match_key']=='afc:official:16143'
 assert r['match_date']==pd.Timestamp('2019-06-18')
def test_modern_derived_key_is_deterministic_and_order_sensitive():
 a=parse_modern_fixture_records([{'match_date':'2024-10-01','home_team':'Kawasaki Frontale','away_team':'Gwangju FC','stage':'MD2','competition_canonical':'afc-champions-league-elite','competition_raw':'AFC Champions League Elite','source_url':'https://example.test'}],calendar_year=2024).iloc[0]
 b=make_derived_fixture_key('afc-champions-league-elite','2024-10-01','Kawasaki Frontale','Gwangju FC','MD2')
 assert a.match_key==b and a.source_match_id is None
 assert a.match_key!=make_derived_fixture_key('afc-champions-league-elite','2024-10-01','Gwangju FC','Kawasaki Frontale','MD2')
def test_modern_duplicate_rejected():
 r={'match_date':'2024-10-01','home_team':'A','away_team':'B','stage':'MD2','competition_canonical':'x','source_url':'u'}
 with pytest.raises(ValueError): parse_modern_fixture_records([r,r],calendar_year=2024)
def test_retention_keeps_j1_involved_only():
 f=pd.DataFrame({'home_is_j1':pd.Series([True,False],dtype=bool),'away_is_j1':pd.Series([False,False],dtype=bool)})
 assert len(retain_j1_matches(f))==1
def test_identity_schema_distinguishes_official_and_derived():
 cols=list(OUTPUT_COLUMNS)
 f=pd.DataFrame([{c:None for c in cols}]); f.loc[0,'identity_type']='derived_fixture_key'; f.loc[0,'match_key']='afc:derived:x'; f.loc[0,'match_date']=pd.Timestamp('2024-01-01'); f.loc[0,'home_team']='A'; f.loc[0,'away_team']='B'; f.loc[0,'home_is_j1']=True; f.loc[0,'away_is_j1']=False
 validate_identity_frame(f)
