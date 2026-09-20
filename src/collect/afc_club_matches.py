"""AFC club-match identity adapters and J1-retention helpers.

This module deliberately keeps legacy numeric IDs and modern derived fixture
keys as different identity types. It does not infer IDs from row positions.
"""
from hashlib import sha256
import json
import re
from html.parser import HTMLParser
import pandas as pd

OUTPUT_COLUMNS=("calendar_year","match_date","home_team","away_team","home_team_id","away_team_id","home_is_j1","away_is_j1","competition","competition_raw","round_raw","identity_type","source_match_id","match_key","source_url")

def make_derived_fixture_key(competition, match_date, home_team, away_team, stage):
    fields=[str(competition),pd.Timestamp(match_date).strftime('%Y-%m-%d'),str(home_team),str(away_team),str(stage)]
    if any(not x or x.strip()=='' for x in fields): raise ValueError('derived key fields must be non-empty')
    # Names are official source values; no fuzzy or transliteration step is applied.
    return 'afc:derived:' + ':'.join(x.strip().lower().replace(' ','-') for x in fields)

def make_official_match_key(source_match_id):
    if source_match_id is None or str(source_match_id).strip()=='': raise ValueError('official match ID is required')
    return 'afc:official:' + str(source_match_id).strip()

class _LegacyText(HTMLParser):
    def __init__(self): super().__init__(convert_charrefs=True); self.parts=[]
    def handle_data(self,data): self.parts.append(data)
    def text(self): return ' '.join(' '.join(self.parts).split())

def parse_legacy_match_report_html(html, *, source_match_id, source_url):
    """Parse the old official stats.the-afc.com match-report layout.

    The numeric ID is supplied from the official URL/link; it is never guessed
    from HTML order or a scoreline.
    """
    if not isinstance(html,str) or not html.strip(): raise ValueError('empty legacy HTML')
    p=_LegacyText(); p.feed(html); text=p.text()
    comp=re.search(r'((?:AFC\s+)?[A-Z][A-Z\s]+?\s+20\d{2})',text)
    date=re.search(r'\b(20\d{2})[-/]([01]\d)[-/]([0-3]\d)\b',text)
    teams=re.findall(r'([A-Z][A-Z0-9 .&\-]+\s+\([A-Z]{3}\))',text)
    if not date or len(teams)<2: raise ValueError('legacy match fields not found')
    # The first two official scoreboard team labels precede line-up labels.
    home,away=teams[0].strip(),teams[1].strip()
    year=int(date.group(1)); match_date=pd.Timestamp(year,int(date.group(2)),int(date.group(3)))
    raw=comp.group(1).strip() if comp else 'AFC club competition'
    return {'calendar_year':year,'match_date':match_date,'home_team':home,'away_team':away,
            'competition':'afc_club_competition','competition_raw':raw,'round_raw':None,
            'identity_type':'official_match_id','source_match_id':str(source_match_id),
            'match_key':make_official_match_key(source_match_id),'source_url':source_url}

def parse_modern_fixture_records(records, *, calendar_year):
    """Normalize official AFC fixture/PDF-extracted records.

    Records must already be extracted from an official structured fixture
    source. No OCR or row-number identity is accepted here.
    """
    out=[]
    for r in records:
        date=r.get('match_date'); home=r.get('home_team'); away=r.get('away_team'); stage=r.get('stage') or r.get('matchday')
        if not date or not home or not away or home==away or not stage: raise ValueError(f'invalid modern fixture record: {r!r}')
        d=pd.to_datetime(date,errors='coerce')
        if pd.isna(d): raise ValueError(f'invalid fixture date: {date!r}')
        out.append({'calendar_year':int(calendar_year),'match_date':d,'home_team':str(home),'away_team':str(away),
                    'competition':'afc_club_competition','competition_raw':r.get('competition_raw'),'round_raw':str(stage),
                    'identity_type':'derived_fixture_key','source_match_id':None,
                    'match_key':make_derived_fixture_key(r.get('competition_canonical','afc_club_competition'),d,home,away,stage),
                    'source_url':r.get('source_url')})
    out=pd.DataFrame(out)
    if not out.empty and out.match_key.duplicated().any(): raise ValueError('duplicate derived fixture key')
    return out

def validate_identity_frame(frame):
    if list(frame.columns)!=list(OUTPUT_COLUMNS): raise ValueError('unexpected AFC output schema')
    if frame.match_key.isna().any() or frame.match_key.duplicated().any(): raise ValueError('invalid match_key')
    official=frame.identity_type.eq('official_match_id')
    derived=frame.identity_type.eq('derived_fixture_key')
    if (~(official|derived)).any(): raise ValueError('unknown identity_type')
    if frame.loc[official,'source_match_id'].isna().any() or frame.loc[derived,'source_match_id'].notna().any(): raise ValueError('identity/source ID mismatch')
    if frame.match_date.isna().any() or frame.home_team.isna().any() or frame.away_team.isna().any(): raise ValueError('missing fixture field')
    if (frame.home_team==frame.away_team).any(): raise ValueError('home equals away')
    return frame

def retain_j1_matches(frame):
    if not frame.home_is_j1.dtype==bool or not frame.away_is_j1.dtype==bool: raise ValueError('J1 flags must be boolean')
    out=frame[frame.home_is_j1|frame.away_is_j1].copy()
    if not out.empty and not (out.home_is_j1|out.away_is_j1).all(): raise ValueError('non-J1 match retained')
    return out
