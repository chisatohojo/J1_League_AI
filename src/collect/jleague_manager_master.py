"""Official J.League manager directory cache and identity resolution."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

MASTER_COLUMNS = ("staff_id", "official_name", "official_english_name", "birth_date", "nationality", "source_url")
BASE = "https://data.j-league.or.jp"


def normalize_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("manager name must be a string")
    return re.sub(r"[\s\u3000]+", " ", value).strip()


class _IndexParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.rows=[]; self.row=None; self.cell=[]; self.in_cell=False; self.link=None
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=="tr": self.row=[]; self.staff_id=None
        if tag=="input" and a.get("name")=="staff_ids": self.staff_id=a.get("value")
        if tag=="td" and self.row is not None: self.in_cell=True; self.cell=[]
        if tag=="a" and self.row is not None and "/SFIX07/?staff_id=" in (a.get("href") or ""):
            self.link=(a.get("href"), []); self.cell=[]
    def handle_data(self, data):
        if self.in_cell: self.cell.append(data)
        if self.link: self.link[1].append(data)
    def handle_endtag(self, tag):
        if tag=="a" and self.link:
            self.cell=["".join(self.link[1])]; self.link=None
        if tag=="td" and self.in_cell:
            self.row.append("".join(self.cell).strip()); self.in_cell=False
        if tag=="tr" and self.row is not None:
            if self.staff_id and len(self.row)>=4: self.rows.append([self.staff_id, *self.row[:4]])
            self.row=None


def parse_sfix06_html(html: str, *, source_url: str) -> pd.DataFrame:
    p=_IndexParser(); p.feed(html); p.close()
    rows=[]
    for row in p.rows:
        staff_id, name, english, birth, nationality = row[0], row[1], row[2], row[3], row[4]
        if not name: raise ValueError("official name empty")
        rows.append((str(staff_id), normalize_name(name), normalize_name(english), birth.strip(), nationality.strip(), BASE+f"/SFIX07/?staff_id={staff_id}"))
    return pd.DataFrame(rows, columns=MASTER_COLUMNS)


def _cached_get(url: str, cache_dir: str | Path, *, sleep_seconds: float=0.25) -> tuple[bytes,bool]:
    root=Path(cache_dir); root.mkdir(parents=True,exist_ok=True); key=sha256(url.encode()).hexdigest(); raw_path=root/(key+'.html'); meta_path=root/(key+'.metadata.json')
    if raw_path.exists() and meta_path.exists():
        raw=raw_path.read_bytes(); m=json.loads(meta_path.read_text(encoding='utf8'))
        if m.get('requested_url')==url and m.get('final_url')==url and m.get('status')==200 and m.get('bytes')==len(raw) and m.get('sha256')==sha256(raw).hexdigest(): return raw,True
    req=Request(url,headers={'User-Agent':'J1-League-AI research prototype'})
    with urlopen(req,timeout=30) as response: raw=response.read(); final=response.geturl(); status=response.status
    raw_path.write_bytes(raw); meta_path.write_text(json.dumps({'requested_url':url,'final_url':final,'status':status,'fetched_at_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(raw),'sha256':sha256(raw).hexdigest()},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    if sleep_seconds: time.sleep(sleep_seconds)
    return raw,False


def build_manager_master(*, cache_dir='data/raw/jleague_manager_master', output_path='data/processed/jleague_manager_master/managers.csv', sleep_seconds=0.25) -> pd.DataFrame:
    raw, _ = _cached_get(BASE+'/SFIX06/', cache_dir, sleep_seconds=sleep_seconds)
    p=_IndexParser(); p.feed(raw.decode('utf8',errors='replace')); p.close()
    urls=sorted({BASE+f'/SFIX06/searchStaffListInfoByFirstAlphabet?staffNameFirstAlphabet={quote(ch)}' for ch in 'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわ'})
    frames=[]
    for url in urls:
        raw,_=_cached_get(url,cache_dir,sleep_seconds=sleep_seconds); frames.append(parse_sfix06_html(raw.decode('utf8',errors='replace'),source_url=url))
    result=_validate_master(pd.concat(frames,ignore_index=True).drop_duplicates())
    result=result.loc[:,MASTER_COLUMNS].sort_values('staff_id').reset_index(drop=True)
    out=Path(output_path); out.parent.mkdir(parents=True,exist_ok=True); result.to_csv(out,index=False,encoding='utf8'); return result


def _validate_master(result: pd.DataFrame) -> pd.DataFrame:
    if result.staff_id.duplicated().any():
        raise ValueError('duplicate staff_id')
    if result.official_name.isna().any() or result.official_name.eq('').any():
        raise ValueError('official name empty')
    return result


def resolve_manager_history(history: pd.DataFrame, master: pd.DataFrame, *, output_path='data/processed/jleague_match_managers/2015_2024_match_managers_resolved.csv') -> pd.DataFrame:
    out=history.copy(deep=True); lookup={}
    for row in master.itertuples(index=False): lookup.setdefault(normalize_name(row.official_name),[]).append(row.staff_id)
    unresolved=0
    for side in ('home','away'):
        result=[]
        for name in out[side+'_manager_name']:
            ids=lookup.get(normalize_name(name),[]); result.append(ids[0] if len(ids)==1 else pd.NA); unresolved += len(ids)!=1
        out[side+'_manager_staff_id']=result
    out=out.sort_values(['match_date','match_id'],kind='mergesort').reset_index(drop=True)
    Path(output_path).parent.mkdir(parents=True,exist_ok=True); out.to_csv(output_path,index=False,encoding='utf8'); return out
