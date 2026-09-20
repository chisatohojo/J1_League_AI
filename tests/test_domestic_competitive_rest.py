import pandas as pd
import pytest
from src.features.domestic_competitive_rest import (
    add_domestic_competitive_rest_features, audit_domestic_competitive_rest,
)
from src.features.schedule_gap import add_schedule_gap_features

def league(dates):
 return pd.DataFrame({'match_id':[f'm{i}' for i in range(len(dates))],'match_date':dates,'home_team_id':['A']*len(dates),'away_team_id':['B']*len(dates),'home_days_since_last_match':[0]*len(dates),'away_days_since_last_match':[0]*len(dates)})
def cup(date, comp='cup', home='A', away='X', hi=True, ai=False):
 return pd.DataFrame({'match_date':[date],'home_team_id':[home if hi else pd.NA],'away_team_id':[away if ai else pd.NA],'home_is_j1':[hi],'away_is_j1':[ai],'source_match_id':[comp]})
def test_league_only_matches_when_no_cup():
 x=add_domestic_competitive_rest_features(league(['2015-01-01','2015-01-08']),cup('2015-01-03',home='lower'),cup('2015-01-04',home='lower'))
 assert x.iloc[1].home_domestic_days_since_last_competitive_match==7
def test_cup_is_used_and_home_away_history_continues():
 x=add_domestic_competitive_rest_features(league(['2015-01-01','2015-01-10']),cup('2015-01-05'),cup('2015-01-06',home='lower'))
 assert x.iloc[1].home_domestic_days_since_last_competitive_match==5
def test_current_and_same_day_event_not_used():
 x=add_domestic_competitive_rest_features(league(['2015-01-01','2015-01-05']),cup('2015-01-05'),cup('2015-01-05'))
 assert x.iloc[1].home_domestic_days_since_last_competitive_match==4
def test_nullable_non_j1_opponent_allowed_and_input_unchanged():
 l=league(['2015-01-01','2015-01-10']); before=l.copy(deep=True)
 x=add_domestic_competitive_rest_features(l,cup('2015-01-05',home='A',away='lower'),cup('2015-01-06',home='lower'))
 assert x.iloc[1].home_domestic_days_since_last_competitive_match==5
 pd.testing.assert_frame_equal(l,before)
def test_outside_year_rejected():
 with pytest.raises(ValueError): add_domestic_competitive_rest_features(league(['2025-01-01']),cup('2025-01-02'),cup('2025-01-03'))
 with pytest.raises(ValueError): add_domestic_competitive_rest_features(league(['2024-12-01']),cup('2025-01-02'),cup('2024-12-03'))

def test_previous_j1_gaps_equal_and_all_appearances_classified():
 l=league(['2015-01-01','2015-01-08'])
 audit=audit_domestic_competitive_rest(l,cup('2015-01-03',home='lower'),cup('2015-01-04',home='lower'))
 assert len(audit)==2*len(l)
 assert audit.category.value_counts().to_dict()=={'no_previous_domestic':2,'equal':2}
 later=audit[audit.current_match_id.eq('m1')]
 assert later.domestic_previous_competition.eq('J1').all()
 assert later.domestic_days.eq(later.league_only_days).all()
 assert later.league_previous_match_id.eq('m0').all()
 assert later.domestic_previous_key.eq('j1:m0').all()

def test_only_nonleague_events_shorten_and_gap_cannot_increase():
 l=league(['2015-01-01','2015-01-10'])
 audit=audit_domestic_competitive_rest(l,cup('2015-01-05'),cup('2015-01-06'))
 shorter=audit[audit.category.eq('shorter')]
 assert len(shorter)==1
 assert shorter.iloc[0].domestic_previous_competition=="Emperor's Cup"
 assert shorter.iloc[0].league_only_days==9 and shorter.iloc[0].domestic_days==4
 assert (audit.loc[audit.league_previous_match_id.notna(),'domestic_days']
         <= audit.loc[audit.league_previous_match_id.notna(),'league_only_days']).all()

def test_duplicate_j1_team_date_is_rejected():
 l=league(['2015-01-01','2015-01-01'])
 with pytest.raises(ValueError,match='Duplicate J1 team/date'):
  audit_domestic_competitive_rest(l,cup('2015-01-02'),cup('2015-01-03'))

def test_existing_gap_alignment_uses_match_id_not_row_position():
 l=league(['2015-01-01','2015-01-08'])
 existing=add_schedule_gap_features(l.drop(columns=['home_days_since_last_match','away_days_since_last_match']))
 audit=audit_domestic_competitive_rest(l,cup('2015-01-03',home='lower'),cup('2015-01-04',home='lower'),existing_league_features=existing.iloc[::-1])
 assert len(audit)==4
 wrong=existing.copy(); wrong.loc[0,'match_id']='unknown'
 with pytest.raises(ValueError,match='align'):
  audit_domestic_competitive_rest(l,cup('2015-01-03',home='lower'),cup('2015-01-04',home='lower'),existing_league_features=wrong)
 wrong=existing.copy(); wrong.loc[1,'home_days_since_last_match']=99
 with pytest.raises(ValueError,match='differs'):
  audit_domestic_competitive_rest(l,cup('2015-01-03',home='lower'),cup('2015-01-04',home='lower'),existing_league_features=wrong)

def test_current_and_future_matches_never_become_previous():
 l=league(['2015-01-01','2015-01-10'])
 base=audit_domestic_competitive_rest(l,cup('2015-01-05'),cup('2015-01-11',home='lower'))
 future=audit_domestic_competitive_rest(l,cup('2015-01-05'),cup('2015-01-11'))
 pd.testing.assert_frame_equal(base,future)
 assert not (future.domestic_previous_key=='j1:'+future.current_match_id).any()

def test_home_away_roles_share_one_history():
 l=league(['2015-01-01','2015-01-10'])
 l.loc[1,['home_team_id','away_team_id']]=['B','A']
 a=audit_domestic_competitive_rest(l,cup('2015-01-05'),cup('2015-01-06',home='lower'))
 away=a[(a.current_match_id=='m1')&(a.side=='away')].iloc[0]
 assert away.team_id=='A' and away.league_previous_match_id=='m0'
 assert away.domestic_previous_competition=='J.League Cup' and away.domestic_days==5

def test_cup_before_first_j1_is_exclusive_category():
 l=league(['2015-01-10'])
 a=audit_domestic_competitive_rest(l,cup('2015-01-05'),cup('2015-01-06',home='lower'))
 assert a.category.value_counts().to_dict()=={'no_previous_league':1,'no_previous_domestic':1}
 assert len(a)==2
