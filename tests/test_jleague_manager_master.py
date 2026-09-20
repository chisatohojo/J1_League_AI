import hashlib, json
import pandas as pd
import pytest
from src.collect.jleague_manager_master import parse_sfix06_html, normalize_name, _cached_get, _validate_master

HTML='''<table><tr><td><input name="staff_ids" value="1357"/><a href="/SFIX07/?staff_id=1357">山田　太郎</a></td><td>YAMADA Taro</td><td>1970/01/01</td><td>日本</td></tr></table>'''
def test_parse_directory_row():
    r=parse_sfix06_html(HTML,source_url='https://data.j-league.or.jp/SFIX06/x'); assert r.iloc[0].staff_id=='1357'; assert r.iloc[0].official_name=='山田 太郎'
def test_whitespace_only_and_no_fuzzy():
    assert normalize_name('  A　 B\n')=='A B'; assert normalize_name('山田・太郎')!=normalize_name('山田太郎')
def test_cache_sha_validation(tmp_path):
    u='https://example.test/x'; b=b'x'; k=hashlib.sha256(u.encode()).hexdigest(); (tmp_path/(k+'.html')).write_bytes(b); (tmp_path/(k+'.metadata.json')).write_text(json.dumps({'requested_url':u,'final_url':u,'status':200,'bytes':1,'sha256':hashlib.sha256(b).hexdigest()}))
    assert _cached_get(u,tmp_path,sleep_seconds=0)[0]==b
def test_duplicate_staff_id_rejected():
    with pytest.raises(ValueError):
        _validate_master(pd.DataFrame({'staff_id':['1357','1357'],'official_name':['A','B']}))
