"""Offline/cache-aware J.League Cup SFMS01 collector."""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json, re, time
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd
from src.collect.teams import load_team_master, TeamMasterError

OUTPUT_COLUMNS=("season","match_date","home_team","away_team","home_team_id","away_team_id","home_is_j1","away_is_j1","competition","competition_raw","source_match_id","source_url")
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
def _season_j1_team_ids(year, master, league_dir='data/processed/jleague'):
    path=Path(league_dir)/f'{year}_matches_probe.csv'
    if not path.exists(): raise FileNotFoundError(f'missing J1 league data: {path}')
    league=pd.read_csv(path, dtype={'home_team':str,'away_team':str})
    ids=set(); names=set()
    for row in league.itertuples():
        for side in ('home','away'):
            name=getattr(row, side+'_team')
            if pd.isna(name) or not str(name).strip():
                raise ValueError(f'missing J1 team name: season={year}, match_id={row.match_id}, side={side}')
            try:
                ids.add(master.resolve_team_id(str(name), source='jleague_data_site', on=pd.Timestamp(row.match_date)))
            except TeamMasterError as e:
                raise ValueError(f'unresolved J1 team: season={year}, match_id={row.match_id}, side={side}, name={name!r}: {e}') from e
            names.add(str(name))
    if not ids: raise ValueError(f'empty J1 team set: season={year}')
    return ids, names

def _retain_j1_matches(frame, j1_ids):
    """Return only Cup rows involving at least one season J1 club."""
    return frame[frame.home_is_j1 | frame.away_is_j1].copy()

def collect_jleague_cup_history(*,years=range(2015,2025),raw_dir='data/raw/jleague_cup',output_path='data/processed/jleague_cup/2015_2024_jleague_cup_matches.csv',interval=.25,league_dir='data/processed/jleague'):
    master=load_team_master(); frames=[]; diagnostics=[]
    for year in years:
        j1_ids,j1_names=_season_j1_team_ids(year, master, league_dir)
        url=f'https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=11&competition_years={year}'
        b,_=_get(url,raw_dir,interval); f=parse_sfms01_html(b.decode('utf8',errors='replace'),expected_season=year)
        for side in ('home','away'):
            ids=[]
            for row in f.itertuples():
                try: ids.append(master.resolve_team_id(getattr(row,side+'_team'),source='jleague_data_site',on=row.match_date))
                except TeamMasterError:
                    if getattr(row, side+'_team') in j1_names:
                        raise ValueError(f'unresolved J1 Cup team: season={year}, match_id={row.source_match_id}, side={side}, name={getattr(row, side+"_team")!r}')
                    ids.append(pd.NA)
            f[side+'_team_id']=ids
            f[side+'_is_j1']=f[side+'_team_id'].isin(j1_ids)
        retained=_retain_j1_matches(f, j1_ids)
        for row in f.itertuples():
            for side in ('home','away'):
                if pd.isna(getattr(row,side+'_team_id')) and not getattr(row,side+'_is_j1'):
                    diagnostics.append({'season':year,'match_id':row.source_match_id,'date':row.match_date,'side':side,'team_name':getattr(row,side+'_team')})
        frames.append(retained)
        if retained.empty and not f.empty: raise ValueError(f'no retained J1 Cup matches: season={year}')
    out=pd.concat(frames,ignore_index=True).loc[:,list(OUTPUT_COLUMNS)].sort_values(['match_date','source_match_id']).reset_index(drop=True)
    if out.source_match_id.duplicated().any(): raise ValueError('duplicate source_match_id')
    if out[['match_date','home_team','away_team']].isna().any().any() or (out.home_team==out.away_team).any(): raise ValueError('invalid match row')
    if not out.home_is_j1.astype(bool).any() and not out.away_is_j1.astype(bool).any(): raise ValueError('retained output has no J1 match')
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True); out.to_csv(p,index=False,encoding='utf8')
    out.attrs['diagnostics']=pd.DataFrame(diagnostics)
    return out
