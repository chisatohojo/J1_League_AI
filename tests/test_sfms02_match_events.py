import hashlib
import re
import pytest
from src.collect.sfms02_match_events import parse_match_events

def fx(goals=True, red=False, yellow=True, marker='\u25bd'):
    g = '<!-- A2 Start --><div class="left-area"><table><tr><td>Scorer</td><td>45\'+1\'</td></tr></table></div><div class="right-area"><table></table></div><!-- A2 End -->' if goals else ''
    a7 = f'<!-- A7 Start --><table><tr><td class="change">{marker}</td><td class="name">Out</td><td class="time">12\'</td></tr><tr><td class="change">\u25b2</td><td class="name">In</td><td class="time"></td></tr></table><!-- A7 End --><!-- A7 Start --><table><tr><td class="change">{marker}</td><td class="name">Out2</td><td class="time">55\'</td></tr><tr><td class="change">\u25b2</td><td class="name">In2</td><td class="time"></td></tr></table><!-- A7 End -->'
    a8 = '<!-- A8 Start --><table><tr><td class="name">Carded</td><td class="time">90\'+2\'</td></tr></table><!-- A8 End --><!-- A8 Start --><table></table><!-- A8 End -->' if yellow else ''
    a9 = '<!-- A9 Start --><table><tr><td class="name">SentOff</td><td class="time">33\'</td></tr></table><!-- A9 End --><!-- A9 Start --><table></table><!-- A9 End -->' if red else ''
    roster = '<!-- A5 Start --><table></table><!-- A5 End --><!-- A5 Start --><table></table><!-- A5 End --><!-- A6 Start --><table></table><!-- A6 End --><!-- A6 Start --><table></table><!-- A6 End -->'
    return (g + roster + a7 + a8 + a9 + '<!-- A12 Start -->').encode()

def parse(raw):
    return parse_match_events(raw, match_id='1', match_date='2024-01-01', season=2024, team_ids={'home':'h','away':'a'}, team_names={'home':'Home FC','away':'Away FC'}, source_url='offline')

def test_schema_event_types_names_and_determinism():
    raw=fx(); kw=dict(match_id='1',match_date='2024-01-01',season=2024,team_ids={'home':'h','away':'a'},team_names={'home':'Home FC','away':'Away FC'},source_url='x'); a=parse_match_events(raw,**kw,raw_sha256=hashlib.sha256(raw).hexdigest()); b=parse_match_events(raw,**kw,raw_sha256=hashlib.sha256(raw).hexdigest()); assert a==b and {x['team_name'] for x in a}=={'Home FC','Away FC'}
def test_substitution_pair_and_multiple(): assert len([x for x in parse(fx(yellow=False)) if x['event_type']=='SUBSTITUTION'])==2
def test_malformed_substitution_and_exact_identity_fail():
    with pytest.raises(ValueError): parse(fx(marker='BAD'))
    with pytest.raises(ValueError): parse_match_events(fx(),match_id='1',match_date='x',season=2024,team_ids={'home':'','away':'a'},team_names={'home':'H','away':'A'},source_url='x')
def test_multiple_goals_unique_ids():
    raw=fx().replace(b"<tr><td>Scorer</td><td>45'+1'</td></tr>",b"<tr><td>Scorer</td><td>45'+1'</td></tr><tr><td>Scorer2</td><td>46'</td></tr>"); x=[x for x in parse(raw) if x['event_type']=='GOAL']; assert len(x)==2 and len({e['event_id'] for e in x})==2
def test_red_card():
    x=next(x for x in parse(fx(red=True)) if x['event_type']=='RED_CARD'); assert x['source_section']=='A9' and x['player_name_raw']=='SentOff'
def test_46_ambiguity():
    x=next(x for x in parse(fx().replace(b"45'+1'",b"46'")) if x['event_type']=='GOAL'); assert x['minute_normalized']==46 and 'MINUTE_46_BOUNDARY_AMBIGUOUS' in x['normalization_flags']
def test_unpaired_substitution():
    text=fx().decode(); text=re.sub(r'<tr><td class="change">.*?</tr><tr><td class="change">.*?</tr>',lambda _: '<tr><td class="change">▽</td><td class="name">Out</td><td class="time">12\'</td></tr>',text,count=1)
    with pytest.raises(ValueError):
        parse(text.encode())
@pytest.mark.parametrize('bad',['','\ufffdBroken'])
def test_blank_or_replacement_names(bad):
    with pytest.raises(ValueError): parse(fx().replace(b'Carded',bad.encode()))
@pytest.mark.parametrize('bad',['','\ufffdBroken'])
def test_blank_or_replacement_goal_scorer(bad):
    with pytest.raises(ValueError): parse(fx().replace(b'Scorer',bad.encode(),1))
def test_same_minute_substitution_red():
    raw=fx(red=True).replace(b'SentOff',b'Out').replace(b'Out</td><td class="time">12\'',b'Out</td><td class="time">33\'')
    with pytest.raises(ValueError):
        parse(raw)
def test_absent_and_zero_sections():
    raw=fx(goals=False,yellow=False).replace(b'<!-- A9 Start --><!-- A9 End -->',b''); assert not {x['event_type'] for x in parse(raw)} & {'GOAL','YELLOW_CARD','RED_CARD'}
def test_malformed_a8_and_a2_present():
    with pytest.raises(ValueError): parse(fx().replace(b'<!-- A8 End --><!-- A8 Start --><table></table><!-- A8 End -->',b'<!-- A8 End -->'))
    with pytest.raises(ValueError): parse(fx().replace(b'<div class="right-area"><table></table></div>',b''))
def test_missing_a7_and_no_network(monkeypatch):
    import urllib.request; monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')))
    with pytest.raises(Exception): parse(re.sub(rb'<!-- A7 Start -->.*?<!-- A7 End -->',b'',fx(),count=2))
    assert parse(fx())
