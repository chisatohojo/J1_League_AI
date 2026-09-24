import hashlib
import re

import pytest

from src.collect.sfms02_match_events import parse_match_events


def _fixture(*, goals=True, bad_sub=False):
    goal = '''<!-- A2 goal Start --><div class="left-area"><table><tr><td>Scorer</td><td>45'+1'</td></tr></table></div><div class="right-area"><table></table></div><!-- A2 goal End -->''' if goals else '<!-- A2 goal Start --><div class="left-area"><table></table></div><div class="right-area"><table></table></div><!-- A2 goal End -->'
    marker = '笆ｽ' if not bad_sub else 'BAD'
    sub = f'''<!-- A7 sub Start --><table><tr><td class="change">{marker}</td><td class="name">Out</td><td class="time">12'</td></tr><tr><td class="change">笆ｲ</td><td class="name">In</td><td class="time"></td></tr></table><!-- A7 sub End --><!-- A7 sub Start --><table><tr><td class="change">{marker}</td><td class="name">Out2</td><td class="time">55'</td></tr><tr><td class="change">笆ｲ</td><td class="name">In2</td><td class="time"></td></tr></table><!-- A7 sub End -->'''
    yellow = '''<!-- A8 card Start --><table><tr><td class="name">Carded</td><td class="time">90'+2'</td></tr></table><!-- A8 card End -->'''
    roster = '<!-- A5 Start --><table></table><!-- A5 End --><!-- A5 Start --><table></table><!-- A5 End --><!-- A6 Start --><table></table><!-- A6 End --><!-- A6 Start --><table></table><!-- A6 End -->'
    return (goal + roster + sub + yellow + '<!-- A9 red Start --><!-- A9 red End --><!-- A9 Start --><!-- A9 End --><!-- A12 Start -->').encode()


def test_schema_and_event_types_are_deterministic():
    raw = _fixture()
    kwargs = dict(match_id='1', match_date='2024-01-01', season=2024,
                  team_ids={'home': 'team_0001', 'away': 'team_0002'}, source_url='https://example')
    first = parse_match_events(raw, **kwargs, raw_sha256=hashlib.sha256(raw).hexdigest())
    second = parse_match_events(raw, **kwargs, raw_sha256=hashlib.sha256(raw).hexdigest())
    assert first == second
    assert {row['event_type'] for row in first} == {'GOAL', 'SUBSTITUTION', 'YELLOW_CARD'}
    assert all(row['team_id'] in {'team_0001', 'team_0002'} for row in first)
    assert all('player_id' not in row for row in first)


def test_substitution_is_one_event_from_two_raw_rows():
    rows = parse_match_events(_fixture(goals=False), match_id='1', match_date='2024-01-01', season=2024,
                              team_ids={'home': 'h', 'away': 'a'}, source_url='x')
    subs = [row for row in rows if row['event_type'] == 'SUBSTITUTION']
    assert len(subs) == 2
    assert subs[0]['player_name_raw'] == 'Out'
    assert subs[0]['related_player_name_raw'] == 'In'


def test_malformed_substitution_fails():
    with pytest.raises(ValueError):
        parse_match_events(_fixture(bad_sub=True), match_id='1', match_date='2024-01-01', season=2024,
                           team_ids={'home': 'h', 'away': 'a'}, source_url='x')


def test_missing_exact_team_identity_fails():
    with pytest.raises(ValueError):
        parse_match_events(_fixture(), match_id='1', match_date='2024-01-01', season=2024,
                           team_ids={'home': '', 'away': 'a'}, source_url='x')


def _parse(raw):
    return parse_match_events(raw.encode(), match_id='1', match_date='2024-01-01', season=2024,
                              team_ids={'home': 'h', 'away': 'a'}, source_url='offline')


def test_multiple_goals_have_unique_deterministic_ids():
    raw = _fixture().decode()
    raw = raw.replace('<tr><td>Scorer</td><td>45\'+1\'</td></tr>',
                      '<tr><td>Scorer</td><td>45\'+1\'</td></tr><tr><td>Scorer2</td><td>46\'</td></tr>')
    first = [row for row in _parse(raw) if row['event_type'] == 'GOAL']
    second = [row for row in _parse(raw) if row['event_type'] == 'GOAL']
    assert len(first) == 2
    assert len({row['event_id'] for row in first}) == 2
    assert first == second


def test_red_card_is_preserved_as_event():
    raw = _fixture().decode().replace('<!-- A9 red Start --><!-- A9 red End -->',
        '<!-- A9 red Start --><table><tr><td class="name">SentOff</td><td class="time">33\'</td></tr></table><!-- A9 red End -->')
    row = next(item for item in _parse(raw) if item['event_type'] == 'RED_CARD')
    assert row['player_name_raw'] == 'SentOff'
    assert row['minute_raw'] == "33'"
    assert row['source_section'] == 'A9'


def test_46_minute_ambiguity_flag_is_retained():
    raw = _fixture().decode().replace("45'+1'", "46'")
    row = next(item for item in _parse(raw) if item['event_type'] == 'GOAL')
    assert row['minute_normalized'] == 46
    assert 'MINUTE_46_BOUNDARY_AMBIGUOUS' in row['normalization_flags']


def test_unpaired_substitution_is_hard_failure():
    raw = _fixture().decode()
    raw = re.sub(r'<tr><td class="change">.*?</tr><tr><td class="change">.*?</tr>',
                 '<tr><td class="change">隨・ｽｽ</td><td class="name">Out</td><td class="time">12\'</td></tr>', raw, count=1)
    with pytest.raises(ValueError):
        _parse(raw)


@pytest.mark.parametrize('name', ['', '\ufffdBroken'])
def test_blank_or_replacement_player_name_is_hard_failure(name):
    raw = _fixture().decode().replace('Carded', name)
    with pytest.raises(ValueError):
        _parse(raw)


def test_same_minute_substitution_red_is_hard_failure():
    raw = _fixture().decode().replace('Out</td><td class="time">12\'', 'Out</td><td class="time">33\'')
    raw = raw.replace('<!-- A9 red Start --><!-- A9 red End -->',
        '<!-- A9 red Start --><table><tr><td class="name">Out</td><td class="time">33\'</td></tr></table><!-- A9 red End -->')
    with pytest.raises(ValueError):
        _parse(raw)


def test_section_absence_and_zero_event_semantics():
    raw = _fixture(goals=False).decode()
    raw = raw.replace('<!-- A8 card Start --><table><tr><td class="name">Carded</td><td class="time">90\'+2\'</td></tr></table><!-- A8 card End -->',
                      '<!-- A8 card Start --><!-- A8 card End -->')
    raw = raw.replace('<!-- A9 red Start --><!-- A9 red End -->', '')
    raw = raw.replace('<!-- A9 Start --><!-- A9 End -->', '')
    raw = re.sub(r'<!-- A2 goal Start -->.*?<!-- A2 goal End -->', '', raw, count=1, flags=re.S)
    rows = _parse(raw)
    assert not any(row['event_type'] in {'GOAL', 'YELLOW_CARD', 'RED_CARD'} for row in rows)


def test_missing_a7_boundary_is_hard_failure():
    raw = re.sub(r'<!-- A7 sub Start -->.*?<!-- A7 sub End -->', '', _fixture().decode(), count=2, flags=re.S)
    with pytest.raises(Exception):
        _parse(raw)


def test_parser_has_no_network_dependency(monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('network')))
    assert _parse(_fixture().decode())
