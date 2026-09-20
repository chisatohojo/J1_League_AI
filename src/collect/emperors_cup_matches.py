"""JFA Emperor's Cup schedule collector, retaining matches involving season J1 clubs."""
from datetime import datetime, timezone
from hashlib import sha256
import json, time
from pathlib import Path
from urllib.request import Request, urlopen
import pandas as pd
from bs4 import BeautifulSoup
from src.collect.teams import load_team_master, TeamMasterError

OUTPUT_COLUMNS=("season","match_date","home_team","away_team","home_team_id","away_team_id","home_is_j1","away_is_j1","competition","competition_raw","round_raw","source_match_id","source_url")

def parse_jfa_2026_match_page(html, *, match_number):
    """Parse the 2026 JFA match page; completed status comes from score cells."""
    soup = BeautifulSoup(html, "html.parser")
    schedule = soup.select_one("#header-schedule-score .text-schedule, #header-schedule-result .text-schedule")
    if schedule is None:
        raise ValueError(f"missing JFA schedule block: m{match_number}")
    text = schedule.get_text(" ", strip=True)
    import re
    date = re.search(r"(2026)年(\d{1,2})月(\d{1,2})日", text)
    if not date:
        raise ValueError(f"missing JFA match date: m{match_number}")
    flags = soup.select("#score-board-header .flag p:last-child")
    scores = [x.get_text("", strip=True) for x in soup.select("#score-board-header .total-score")]
    if len(flags) < 2 or len(scores) < 2:
        raise ValueError(f"missing JFA teams/score: m{match_number}")
    completed = all(score != "" for score in scores[:2])
    return {
        "season": 2026, "match_date": pd.Timestamp(int(date.group(1)), int(date.group(2)), int(date.group(3))),
        "home_team": flags[0].get_text("", strip=True), "away_team": flags[1].get_text("", strip=True),
        "completed": completed, "source_match_id": f"2026-m{int(match_number):02d}",
        "source_url": f"https://www.jfa.jp/match/emperorscup_2026/match_page/m{int(match_number)}.html",
        "competition": "emperors_cup", "competition_raw": "Emperor's Cup", "round_raw": text,
    }

def parse_jfa_schedule_json(payload, *, season):
    data=json.loads(payload) if isinstance(payload,(str,bytes,bytearray)) else payload
    root=data.get('matchScheduleList',{})
    raw_comp=root.get('competitionName')
    rows=[]
    for item in root.get('matchSchedule',[]):
        date=item.get('matchDate'); home=item.get('homeTeamName'); away=item.get('awayTeamName'); number=item.get('matchNumber')
        if not date or not home or not away or home==away or not number:
            raise ValueError(f'invalid JFA schedule row: {item!r}')
        match_date=pd.to_datetime(date,format='%Y/%m/%d',errors='coerce')
        if pd.isna(match_date): raise ValueError(f'invalid match date: {date!r}')
        mid=f'{season}-m{int(number):02d}'
        rows.append({'season':int(season),'match_date':match_date,'home_team':home,'away_team':away,
                     'competition':'emperors_cup','competition_raw':raw_comp,'round_raw':item.get('matchTypeName'),
                     'source_match_id':mid,'source_url':f'https://www.jfa.jp/match/emperorscup_{season}/match_page/m{int(number)}.html'})
    out=pd.DataFrame(rows)
    if out.empty: raise ValueError(f'empty JFA schedule: season={season}')
    if out.source_match_id.duplicated().any(): raise ValueError(f'duplicate JFA match identity: season={season}')
    return out

def _get(url, root, interval=.25):
    root=Path(root); root.mkdir(parents=True,exist_ok=True); key=sha256(url.encode()).hexdigest(); rp=root/(key+'.json'); mp=root/(key+'.metadata.json')
    if rp.exists() and mp.exists():
        b=rp.read_bytes(); m=json.loads(mp.read_text(encoding='utf8'))
        if m.get('requested_url')==url and m.get('final_url')==url and m.get('status')==200 and m.get('bytes')==len(b) and m.get('sha256')==sha256(b).hexdigest(): return b,True
    req=Request(url,headers={'User-Agent':'J1-League-AI research prototype'})
    with urlopen(req,timeout=30) as r: b=r.read(); final=r.geturl(); status=r.status
    rp.write_bytes(b); mp.write_text(json.dumps({'requested_url':url,'final_url':final,'status':status,'fetched_at_utc':datetime.now(timezone.utc).isoformat(),'bytes':len(b),'sha256':sha256(b).hexdigest()},indent=2)+'\n')
    time.sleep(interval); return b,False

def _j1_ids(year, master, league_dir):
    path=Path(league_dir)/f'{year}_matches_probe.csv'; league=pd.read_csv(path)
    ids=set(); names=set()
    for row in league.itertuples():
        for side in ('home','away'):
            name=getattr(row,side+'_team'); names.add(str(name))
            try: ids.add(master.resolve_team_id(str(name),source='jleague_data_site',on=pd.Timestamp(row.match_date)))
            except TeamMasterError as e: raise ValueError(f'unresolved J1 team: season={year}, match_id={row.match_id}, side={side}, name={name!r}') from e
    return ids,names

def collect_emperors_cup_history(*,years=range(2015,2025),raw_dir='data/raw/emperors_cup',output_path='data/processed/emperors_cup/2015_2024_emperors_cup_matches.csv',league_dir='data/processed/jleague',interval=.25):
    master=load_team_master(); frames=[]; diagnostics=[]
    for year in years:
        j1_ids,j1_names=_j1_ids(year,master,league_dir)
        url=f'https://www.jfa.jp/match/emperorscup_{year}/match/schedule.json'
        b,hit=_get(url,raw_dir,interval); f=parse_jfa_schedule_json(b,season=year)
        for side in ('home','away'):
            ids=[]
            for row in f.itertuples():
                try: ids.append(master.resolve_team_id(getattr(row,side+'_team'),source='jleague_data_site',on=row.match_date))
                except TeamMasterError:
                    if getattr(row,side+'_team') in j1_names: raise ValueError(f'unresolved J1 Cup team: season={year}, match_id={row.source_match_id}, side={side}, name={getattr(row,side+"_team")!r}')
                    ids.append(pd.NA)
            f[side+'_team_id']=ids; f[side+'_is_j1']=f[side+'_team_id'].isin(j1_ids)
        retained=f[f.home_is_j1|f.away_is_j1].copy()
        for row in f.itertuples():
            for side in ('home','away'):
                if pd.isna(getattr(row,side+'_team_id')) and not getattr(row,side+'_is_j1'):
                    diagnostics.append({'season':year,'match_id':row.source_match_id,'date':row.match_date,'side':side,'team_name':getattr(row,side+'_team')})
        frames.append(retained)
    out=pd.concat(frames,ignore_index=True).loc[:,list(OUTPUT_COLUMNS)].sort_values(['match_date','source_match_id']).reset_index(drop=True)
    if out.source_match_id.duplicated().any(): raise ValueError('duplicate source_match_id')
    if out[['match_date','home_team','away_team']].isna().any().any() or (out.home_team==out.away_team).any(): raise ValueError('invalid retained match')
    if not (out.home_is_j1|out.away_is_j1).all(): raise ValueError('non-J1 match retained')
    p=Path(output_path); p.parent.mkdir(parents=True,exist_ok=True); out.to_csv(p,index=False,encoding='utf8'); out.attrs['diagnostics']=pd.DataFrame(diagnostics); return out
