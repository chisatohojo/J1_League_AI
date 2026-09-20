"""Offline/cache-aware J.League Cup SFMS01 collector."""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json, re, time
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd
from src.collect.teams import load_team_master, TeamMasterError

OUTPUT_COLUMNS=("season","match_date","home_team","away_team","home_team_id","away_team_id","competition","competition_raw","source_match_id","source_url")
class _Parser(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.rows=[]; self.row=None; self.cell=None; self.link=None; self.table_depth=0; self.active=False; self.cell_index=0
    def handle_starttag(self,t,a):
        a=dict(a)
        if t=='table' and 'search-table' in (a.get('class') or '').split(): self.active=True; self.table_depth=1
        elif t=='table' and self.active: self.table_depth+=1
        if not self.active: return
        if t=='tr': self.row=[]
        if t=='td' and self.row is not None: self.cell=[]; self.cell_index=len(self.row)
        if t=='a' and self.cell is not None and self.cell_index==6 and 'SFMS02/?match_card_id=' in (a.get('href') or ''): self.link=a['href']
    def handle_data(self,d):
        if self.cell is not None: self.cell.append(d)
    def handle_endtag(self,t):
        if not self.active: return
        if t=='td' and self.cell is not None: self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        if t=='tr' and self.row is not None:
            if len(self.row)==11 and self.link: self.rows.append((self.row[0],self.row[1],self.row[3],self.row[5],self.row[7],self.link))
            self.row=None; self.link=None
        if t=='table':
            self.table_depth-=1
            if self.table_depth==0: self.active=False
def parse_sfms01_html(html,*,expected_season):
    p=_Parser(); p.feed(html); p.close(); out=[]
    for season,raw,date,home,away,href in p.rows:
        if int(season)!=int(expected_season): raise ValueError('season mismatch')
        m=re.match(r'(\d{2})/(\d{2})/(\d{2})',date)
        if not m: raise ValueError('invalid match date')
        year=int(season); out.append({'season':year,'match_date':pd.Timestamp(year,int(m.group(2)),int(m.group(3))), 'home_team':home,'away_team':away,'competition':'jleague_cup','competition_raw':raw,'source_match_id':re.search(r'match_card_id=(\d+)',href).group(1),'source_url':'https://data.j-league.or.jp'+href})
    result=pd.DataFrame(out)
    if not result.empty and result.source_match_id.duplicated().any(): raise ValueError('duplicate match_card_id')
    return result
def _get(url,root,interval=.25):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); key=sha256(url.encode()).hexdigest(); rp=root/(key+'.html'); mp=root/(key+'.metadata.json')
    if rp.exists() and mp.exists():
        b=rp.read_bytes(); m=json.loads(mp.read_text(encoding='utf8'))
        if m.get('requested_url')==url and m.get('final_url')==url and m.get('status')==200 and m.get('bytes')==len(b) and m.get('sha256')==sha256(b).hexdigest(): return b,True
    req=Request(url,headers={'User-Agent':'J1-League-AI research prototype'})
    with urlopen(req,timeout=30) as r: b=r.read(); final=r.geturl(); status=r.status
    rp.write_bytes(b); mp.write_text(json.dumps({'requested_url':url,'final_url':final,'status':status,'fetched_at_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(b),'sha256':sha256(b).hexdigest()},indent=2)+'\n')
    time.sleep(interval); return b,False
def collect_jleague_cup_history(*,years=range(2015,2025),raw_dir='data/raw/jleague_cup',output_path='data/processed/jleague_cup/2015_2024_jleague_cup_matches.csv',interval=.25):
    master=load_team_master(); frames=[]; unresolved=[]
    for year in years:
        url=f'https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=11&competition_years={year}'
        b,_=_get(url,raw_dir,interval); f=parse_sfms01_html(b.decode('utf8',errors='replace'),expected_season=year)
        for side in ('home','away'):
            ids=[]
            for row in f.itertuples():
                try: ids.append(master.resolve_team_id(getattr(row,side+'_team'),source='jleague_data_site',on=row.match_date))
                except TeamMasterError as e: unresolved.append((year,row.source_match_id,side,getattr(row,side+'_team'),str(e))); ids.append(pd.NA)
            f[side+'_team_id']=ids
        frames.append(f)
    if unresolved:
        details='\n'.join(f'{y} match_id={mid} {side} {name!r}: {reason}' for y,mid,side,name,reason in unresolved)
        raise ValueError('Unresolved J.League Cup team aliases; no output written:\n'+details)
    out=pd.concat(frames,ignore_index=True).loc[:,list(OUTPUT_COLUMNS)].sort_values(['match_date','source_match_id']).reset_index(drop=True)
    if out.source_match_id.duplicated().any(): raise ValueError('duplicate source_match_id')
    if out[['match_date','home_team','away_team']].isna().any().any() or (out.home_team==out.away_team).any(): raise ValueError('invalid match row')
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True); out.to_csv(p,index=False,encoding='utf8'); return out
