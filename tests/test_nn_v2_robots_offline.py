"""Local draft experiments and fail-closed evidence gates; not RFC examples."""
import ast
import hashlib
import importlib.util
from pathlib import Path

import pytest

FILE=Path(__file__).parents[1]/'research/nn_v2/phase2_5H/robots_offline.py'
spec=importlib.util.spec_from_file_location('offline_robots_draft_test',FILE)
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)


def run(raw,path='/',agent='SyntheticBot/1.0',**changes):
    v=dict(source_host='synthetic.invalid',target_url='https://synthetic.invalid'+path,
        user_agent=agent,parser_version=p.VERSION,profile=p.SYNTHETIC_PROFILE,
        expected_raw_SHA256=hashlib.sha256(raw).hexdigest())
    v.update(changes);return p.evaluate(raw,**v)


@pytest.mark.parametrize('raw,path,decision',[
    (b'User-agent: *\nDisallow: /private','/private/a','DENY'),
    (b'User-agent: *\nDisallow: /Private','/private/a','ALLOW'),
    (b'User-agent: *\nDisallow: /private\nAllow: /private/public','/private/public/a','ALLOW'),
    (b'User-agent: *\nDisallow: /same\nAllow: /same','/same','ALLOW'),
    (b'User-agent: *\nAllow: /same\nDisallow: /same','/same','ALLOW'),
    (b'User-agent: *\nDisallow: /a*b','/ab','DENY'),
    (b'User-agent: *\nDisallow: /a*b','/a/one/two/b','DENY'),
    (b'User-agent: *\nDisallow: /a*b$','/a/one/b/more','ALLOW'),
    (b'User-agent: *\nDisallow: /a*b$','/ab','DENY'),
    (b'User-agent: *\nDisallow: /a$','/abc','ALLOW'),
    (b'User-agent: *\nDisallow: /a','/abc','DENY'),
    (b'User-agent: *\nDisallow: /*?secret=','/a?secret=1','DENY'),
    (b'User-agent: *\nDisallow: /a$','/a?x=1','ALLOW'),
    (b'User-agent: *\nDisallow: /%7Ehome','/~home','DENY'),
    (b'User-agent: *\nDisallow: /~home','/%7ehome','DENY'),
    (b'User-agent: *\nDisallow: /a%2Fb','/a/b','ALLOW'),
    (b'User-agent: *\nDisallow: /a%2Fb','/a%2fb','DENY'),
    (b'User-agent: *\nDisallow: /%2A$','/%2A','DENY'),
    (b'User-agent: *\nDisallow: /%2A$','/*','ALLOW'),
    ('User-agent: *\nDisallow: /日本'.encode(),'/日本/a','DENY'),
    ('User-agent: *\nDisallow: /日本'.encode(),'/%E6%97%A5%E6%9C%AC/a','DENY'),
    (b'User-agent: *\nDisallow: /%E6%97%A5%E6%9C%AC','/日本','DENY'),
    ('User-agent: *\nDisallow: /é$'.encode(),'/e\u0301','ALLOW'),
    (b'\xef\xbb\xbf#comment\r\nUsEr-AgEnT: *\r\nDiSaLlOw: /deny # note\r\n\r\n','/deny','DENY'),
    (b'User-agent: *\rDisallow: /deny\r','/deny','DENY'),
    (b'User-agent: *\nDisallow:\nAllow:\n','/','ALLOW'),
])
def test_synthetic_pattern_semantics_candidate_only(raw,path,decision):
    result=run(raw,path)
    assert result['decision']==decision and not result['execution_authorized'] and not result['B_authorized']
    assert not result['specification_snapshots_verified']


@pytest.mark.parametrize('agent,path,decision',[
    ('SpecificBot/1.0','/wildcard','ALLOW'),('OtherBot/1.0','/wildcard','DENY'),
    ('SPECIFICBOT/1.0','/one','DENY'),('SpecificBot/1.0','/two','DENY'),
    ('SpecificBot/1.0','/same','ALLOW'),('LongSpecificBot/1.0','/one','ALLOW'),
    ('LongSpecificBot/1.0','/specific','DENY')])
def test_local_legacy_agent_oracle_longest_and_combined_draft_groups(agent,path,decision):
    raw=(b'User-agent: *\nDisallow: /wildcard\n\n'
         b'User-agent: SpecificBot\nUser-agent: AlternateBot\nDisallow: /one\nDisallow: /same\n\n'
         b'User-agent: SpecificBot\nDisallow: /two\nAllow: /same\n\n'
         b'User-agent: LongSpecificBot\nDisallow: /specific\n')
    assert run(raw,path,agent)['decision']==decision


def test_unmatched_agent_no_default_is_only_a_synthetic_candidate():
    r=run(b'User-agent: OtherBot\nDisallow: /\n','/','SyntheticBot/1.0')
    assert r['decision']=='ALLOW' and r['applied_groups']==[]


@pytest.mark.parametrize('raw',[
    b'',b'\xff',b'User-agent: *\nDisallow: /a\x00',b'No colon',
    b'Disallow: /\n',b'User-agent: \nDisallow: /',b'User-agent: *\nCrawl-delay: 10\n',
    b'User-agent: *\nX-Unreviewed: yes\n',b'User-agent: *\nDisallow: /bad%2\n',
    b'User-agent: *\nDisallow: /bad%GG\n',b'User-agent: *\nDisallow: /bad$middle\n',
    b'User-agent: *\nDisallow: /bad$$\n',b'User-agent: *\nDisallow: relative\n',
    b'User-agent: *\nDisallow: /bad path\n',b'<html>not robots</html>',pytest.param(b'x'*65537,id='oversize-65537'),
    b'User-agent: *\nDisallow: /'+b'*'*33,b'# comments only\n'])
def test_malformed_unknown_empty_oversize_and_encoding_fail_closed(raw):
    result=run(raw)
    assert result['decision']=='UNKNOWN' and result['candidate_decision'] is None
    assert not result['execution_authorized']


@pytest.mark.parametrize('changes',[
    dict(user_agent=''),dict(user_agent=None),dict(user_agent='TwoBot/1 OtherBot/2'),
    dict(parser_version='unreviewed'),dict(profile='RFC9309_PROVEN'),dict(expected_raw_SHA256='0'*64),
    dict(target_url='http://synthetic.invalid/'),dict(target_url='https://synthetic.invalid:443/'),
    dict(target_url='https://synthetic.invalid/?x=1#fragment'),dict(target_url='https://synthetic.invalid/#'),
    dict(target_url='https://user@synthetic.invalid/'),dict(target_url='https://different.invalid/'),
    dict(target_url='https://synthetic.invalid/space here'),dict(target_url='https://synthetic.invalid/../a'),
    dict(target_url='https://synthetic.invalid/%GG'),dict(source_host='www.jleague.jp'),
    dict(source_host='unexpected.invalid')])
def test_invalid_contract_cannot_become_ALLOW(changes):
    r=run(b'User-agent: *\nDisallow:\n',**changes)
    assert r['decision']=='UNKNOWN' and not r['execution_authorized']


@pytest.mark.parametrize('url',[
    'https://www.jleague.jp/robots.txt','https://www.jleague.jp/general/kiyaku/',
    'https://www.jleague.jp/general/copyright/','https://www.jleague.jp/j1/news/'])
def test_unverified_official_spec_never_exposes_real_source_candidate_ALLOW(url):
    raw=b'User-agent: *\nDisallow: /match/*/201*\n'
    r=p.evaluate(raw,source_host='www.jleague.jp',target_url=url,user_agent=p.FIXED_AGENT,
        parser_version=p.VERSION,profile=p.EVIDENCE_PROFILE,expected_raw_SHA256=p.hashlib.sha256(raw).hexdigest())
    assert r['decision']=='UNKNOWN' and r['candidate_decision']=='ALLOW'
    assert r['reason']=='AUTHORITATIVE_SPECIFICATION_SNAPSHOTS_UNAVAILABLE'


def test_same_normalized_name_does_not_override_raw_SHA():
    raw=b'User-agent: *\nDisallow: /x\n'
    r=run(raw.replace(b'/x',b'/%78'),expected_raw_SHA256=hashlib.sha256(raw).hexdigest())
    assert r['decision']=='UNKNOWN' and r['safety_stop']


def test_known_annotation_never_fetches_its_URL():
    r=run(b'User-agent: *\nDisallow:\nSitemap: https://unapproved.invalid/sitemap.xml\n')
    assert r['decision']=='ALLOW' and r['annotations'][0]['resource_fetched'] is False


def test_work_cap_and_repeated_wildcards_no_regex_backtracking_fallback():
    target,_=p.octets('/'+'a'*5000)
    with pytest.raises(p.Uncertain,match='MATCH_WORK_CAP'):p.match_pattern('/*a*a*a*a*a*b',target,work_limit=10)
    assert p.match_pattern('/a**b',p.octets('/ab')[0])[0]


def test_old_parser_remains_HOLD_and_new_evidence_api_remains_UNKNOWN():
    file=FILE.parent.parent/'phase2_5G/access_contract.py'
    s=importlib.util.spec_from_file_location('old_robots_draft_regression',file)
    old=importlib.util.module_from_spec(s);s.loader.exec_module(old)
    assert old.review_robots(b'User-agent: *\nDisallow: /match/*/201*\n',host='www.jleague.jp')['status']=='HOLD'
    assert old.review_robots(b'User-agent: *\nDisallow:\n',host='www.jleague.jp')['status']=='ROBOTS_PATH_REVIEW_ONLY'


def test_no_network_filesystem_process_model_or_entrypoint_in_new_evaluator():
    tree=ast.parse(FILE.read_text('utf8'))
    imports=[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert imports==['hashlib','re']
    direct=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert direct==['urllib.parse','urllib.robotparser']
    forbidden={'open','exec','eval','__import__','globals','getattr','setattr'}
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in forbidden for n in ast.walk(tree))
    assert not any(isinstance(n,ast.Attribute) and n.attr in {'read','urlopen','request','load','fit','predict','connect','write'} for n in ast.walk(tree))


def test_empty_rule_still_separates_agent_groups():
    raw=b'User-agent: SyntheticBot\nDisallow:\nUser-agent: OtherBot\nDisallow: /blocked\n'
    result=run(raw,'/blocked')
    assert result['decision']=='ALLOW' and result['applied_groups']==[dict(group=1,agents=['SyntheticBot'])]


def test_exact_agent_does_not_independently_reimplement_partial_matching():
    import inspect
    from urllib.robotparser import Entry
    assert p.LocalLegacyAgentMatcher is Entry
    assert 'in useragent' not in inspect.getsource(p.local_agent_selection)


def test_fixture_host_bound_sealed_bytes_cannot_be_relabeled_synthetic(monkeypatch):
    raw=b'User-agent: *\nDisallow:\n'
    monkeypatch.setattr(p,'A1_SHA',hashlib.sha256(raw).hexdigest())
    result=run(raw)
    assert result['decision']=='UNKNOWN' and result['reason']=='SEALED_A1_HOST_MISMATCH' and result['safety_stop']


@pytest.mark.parametrize('target', ['https://aboutj.jleague.jp/robots.txt','https://aboutj.jleague.jp/corporate/pressrelease/'])
def test_www_evidence_host_cannot_apply_to_aboutj(target):
    raw=b'User-agent: *\nDisallow:\n'
    result=p.evaluate(raw,source_host='www.jleague.jp',target_url=target,user_agent=p.FIXED_AGENT,
        parser_version=p.VERSION,profile=p.EVIDENCE_PROFILE,expected_raw_SHA256=hashlib.sha256(raw).hexdigest())
    assert result['decision']=='UNKNOWN' and not result['execution_authorized']


def test_unknown_profile_cannot_self_attest_standard_sources():
    result=run(b'User-agent: *\nDisallow:\n',profile='RFC9309_VERIFIED_BY_CALLER')
    assert result['decision']=='UNKNOWN' and result['reason']=='UNKNOWN_PROFILE'
