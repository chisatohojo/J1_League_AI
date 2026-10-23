"""Offline source-backed cases; no HTTP and no crawler activation.

S1=sealed RFC9309; S2=sealed Google Japanese robots specification.
NORMATIVE_CONFORMANCE.json binds each test name to source anchors and SHA.
Deliberately stricter UNKNOWN cases are not standard-compliance PASS claims.
"""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

BASE=Path(__file__).parents[1]/'research/nn_v2'
s=importlib.util.spec_from_file_location('robots_normative_test',BASE/'phase2_5I/robots_normative.py')
n=importlib.util.module_from_spec(s);s.loader.exec_module(n)
h=importlib.util.spec_from_file_location('robots_old_for_comparison',BASE/'phase2_5H/robots_offline.py')
old=importlib.util.module_from_spec(h);h.loader.exec_module(old)


def ev(raw=b'User-agent: *\nDisallow: /private',path='/public',**changes):
    if isinstance(raw,str):raw=raw.encode('utf8')
    args=dict(source_host='synthetic.invalid',target_url='https://synthetic.invalid'+path,
        user_agent='ExampleBot/1.0',product_token='ExampleBot',parser_version=n.VERSION,
        profile=n.SYNTHETIC_PROFILE,expected_raw_SHA256=hashlib.sha256(raw).hexdigest(),
        specification_SHA256=n.SPEC_SHAS)
    args.update(changes)
    out=n.evaluate(raw,**args)
    assert not out['execution_authorized'] and not out['B_authorized'] and not out['history_admission']
    assert not out['full_RFC_conformance']
    return out


@pytest.mark.parametrize('token',['ExampleBot','EXAMPLEBOT','Example_Bot','Example-Bot'])
def test_agent_grammar_valid_explicit_product_token(token):
    assert ev(user_agent=token+'/1.0',product_token=token)['decision']=='ALLOW'


@pytest.mark.parametrize('token',[None,'','Bot1','J1AI-Research-Timing-Pilot','ExampleBot/1.0','*','Example.Bot','Ägent','OtherBot'])
def test_agent_grammar_no_implicit_or_unsupported_identity(token):
    assert ev(product_token=token)['decision']=='UNKNOWN'


def test_agent_matching_exact_not_legacy_substring():
    raw=b'User-agent: Bot\nDisallow: /\nUser-agent: ExampleBot\nAllow: /'
    assert ev(raw)['decision']=='ALLOW'
    assert ev(raw.replace(b'ExampleBot',b'examplebot'))['decision']=='ALLOW'


def test_agent_precedence_named_not_wildcard_and_no_group():
    raw=b'User-agent: *\nDisallow: /\nUser-agent: ExampleBot\nAllow: /public'
    assert ev(raw)['decision']=='ALLOW'
    assert ev(b'User-agent: OtherBot\nDisallow: /')['decision']=='ALLOW'
    assert ev(b'User-agent: *\nDisallow: /')['decision']=='DENY'


def test_group_merge_s1_figures_2_3_and_sitemap_boundary():
    raw=b'User-agent: ExampleBot\nDisallow: /a\nUser-agent: eXAMPLEbOT\nDisallow: /b\nUser-agent: *\nDisallow: /c'
    assert ev(raw,'/a')['decision']==ev(raw,'/b')['decision']=='DENY'
    assert len(ev(raw)['applied_groups'])==2 and ev(raw,'/c')['decision']=='ALLOW'
    grouped=b'User-agent: ExampleBot\nSitemap: https://unfetched.invalid/map\nUser-agent: OtherBot\nDisallow: /'
    r=ev(grouped);assert r['decision']=='DENY' and not r['annotations'][0]['resource_fetched']


@pytest.mark.parametrize('newline',['\n','\r','\r\n'])
@pytest.mark.parametrize('bom',['','\ufeff'])
def test_rule_grammar_bom_comments_line_endings_empty_values(newline,bom):
    raw=bom+newline.join(['# comment','uSeR-aGeNt : ExampleBot','Disallow:','Allow:','Disallow:/private # private'])
    assert ev(raw)['decision']=='ALLOW' and ev(raw,'/private')['decision']=='DENY'


@pytest.mark.parametrize('raw',[
    b'User-agent: Bot1\nAllow: /',b'User-agent: ExampleBot/1.0\nAllow: /',
    b'Disallow: /\nUser-agent: *\nAllow: /',b'User-agent: *\nDisallow: *.gif$',
    b'User-agent: *\nDisallow /private',b'<html>User-agent: *\nAllow: /</html>',
    b'User-agent: *\nAllow: /\x00',b'\xff',b'',b'# comment only'])
def test_malformed_encoding_empty_and_ambiguous_s1_example_stay_unknown(raw):
    assert ev(raw)['decision']=='UNKNOWN'


def test_longest_rule_literal_octets_and_allow_tie():
    raw=b'User-agent: *\nDisallow: /private\nAllow: /private/public'
    assert ev(raw,'/private/public/file')['decision']=='ALLOW'
    assert ev(raw,'/private/file')['decision']=='DENY'
    assert ev(b'User-agent: *\nAllow: /x\nDisallow: /x','/x')['decision']=='ALLOW'


def test_longest_rule_google_marker_examples_no_false_allow():
    # S2 explicit /page.htm example: Google DENY, old literal-only score ALLOW.
    raw=b'User-agent: *\nAllow: /page\nDisallow: /*.htm'
    r=ev(raw,'/page.htm')
    assert r['google_comparison_candidate']=='DENY' and r['decision']=='UNKNOWN'
    assert old.evaluate(raw,source_host='synthetic.invalid',target_url='https://synthetic.invalid/page.htm',
        user_agent='ExampleBot/1.0',parser_version=old.VERSION,profile=old.SYNTHETIC_PROFILE,
        expected_raw_SHA256=hashlib.sha256(raw).hexdigest())['candidate_decision']=='ALLOW'
    # In the Google /page.php5 tie example both ranking interpretations ALLOW.
    assert ev(b'User-agent: *\nAllow: /page\nDisallow: /*.ph','/page.php5')['decision']=='ALLOW'


@pytest.mark.parametrize('path,expected',[('/ab','DENY'),('/aXYZb','DENY'),('/ab/c','DENY'),('/xab','ALLOW')])
def test_wildcard_zero_many_and_start_anchoring(path,expected):
    assert ev(b'User-agent: *\nDisallow: /a*b',path)['decision']==expected


@pytest.mark.parametrize('path,expected',[('/x','DENY'),('/xmore','ALLOW'),('/x?q','ALLOW')])
def test_terminal_anchor(path,expected):
    assert ev(b'User-agent: *\nDisallow: /x$',path)['decision']==expected


@pytest.mark.parametrize('special,encoded',[('*','%2A'),('$','%24')])
def test_percent_special_s1_figure6_literal_star_dollar(special,encoded):
    raw=('User-agent: *\nDisallow: /file-'+encoded+'.html').encode()
    assert ev(raw,'/file-'+special+'.html')['decision']=='DENY'
    assert ev(raw,'/file-'+encoded.lower()+'.html')['decision']=='DENY'
    assert ev(raw,'/file-other.html')['decision']=='ALLOW'


@pytest.mark.parametrize('pattern,path',[
    ('/~user','/%7euser'),('/%7Euser','/~user'),('/%62ar','/bar'),
    ('/ツ','/%E3%83%84'),('/%E3%83%84','/ツ')])
def test_percent_encoding_unreserved_and_utf8_s1_figure4(pattern,path):
    assert ev('User-agent: *\nDisallow: '+pattern,path)['decision']=='DENY'


@pytest.mark.parametrize('path',['/%','/%2','/%GG','/%2fprivate','/%00','/%3F'])
def test_reserved_octets_and_malformed_escapes_no_unquote_all(path):
    assert ev(path=path)['decision']=='UNKNOWN'


@pytest.mark.parametrize('path',['/%ff','/%c0%af','/%E3%83','/%ED%A0%80'])
def test_percent_encoded_invalid_utf8_no_allow(path):
    assert ev(path=path)['decision']=='UNKNOWN'


@pytest.mark.parametrize('path',['/a/%2e%2e/b','/%2E/a','/%2e%2e/'])
def test_encoded_dot_segments_not_silently_rewritten(path):
    assert ev(path=path)['decision']=='UNKNOWN'


def test_unicode_no_normalization_fallback():
    assert ev('User-agent: *\nDisallow: /é','/e\u0301')['decision']=='ALLOW'
    assert ev('User-agent: *\nDisallow: /é','/é')['decision']=='DENY'


def test_query_simple_and_empty_but_complex_query_unknown():
    assert ev(b'User-agent: *\nDisallow: /x?q','/x?q')['decision']=='DENY'
    assert ev(b'User-agent: *\nDisallow: /x$','/x?')['decision']=='ALLOW'
    assert ev(path='/x?q=https://else.invalid/a')['decision']=='UNKNOWN'


@pytest.mark.parametrize('directive',['Crawl-delay: 5','Host: elsewhere.invalid','Unknown: allow','Request-rate: 1/5'])
def test_unknown_directives_stricter_than_optional_standard_ignore(directive):
    assert ev('User-agent: *\nAllow: /\n'+directive)['decision']=='UNKNOWN'


@pytest.mark.parametrize('url',[
    'http://synthetic.invalid/','https://synthetic.invalid:443/','https://www.jleague.jp/',
    'https://synthetic.invalid.evil/','https://user@synthetic.invalid/',
    'https://synthetic.invalid/#frag','https://synthetic.invalid/a/../b',
    'https://synthetic.invalid/a b','https://synthetic.invalid/\\evil'])
def test_host_scope_and_invalid_url_fail_closed(url):
    assert ev(target_url=url)['decision']=='UNKNOWN'


def test_parse_limits_not_full_500kib_conformance():
    assert ev(b'User-agent: *\n#'+b'a'*65536)['decision']=='UNKNOWN'
    assert ev(b'User-agent: *\n'+b'\n'*4096)['decision']=='UNKNOWN'
    assert ev(b'User-agent: *\nDisallow: /'+b'*'*33)['decision']=='UNKNOWN'


@pytest.mark.parametrize('change',[
    {'expected_raw_SHA256':'0'*64},{'specification_SHA256':{}},{'parser_version':'old'},
    {'profile':'LIVE'},{'profile':n.SYNTHETIC_PROFILE,'source_host':'www.jleague.jp'}])
def test_safety_priority_sha_version_scope_and_no_execution(change):
    assert ev(**change)['decision']=='UNKNOWN'


def test_google_differences_version_suffix_not_rfc_agent_grammar():
    for agent in ['googlebot/1.2','googlebot*']:
        assert ev('User-agent: '+agent+'\nAllow: /')['decision']=='UNKNOWN'


def test_sealed_A1_replay_fixed_http_agent_not_implicitly_rfc_token():
    # Actual sealed A1 replay is separate private read-only audit, not fake raw here.
    assert ev(user_agent=n.FIXED_AGENT,product_token=None)['reason']=='EXPLICIT_RFC_PRODUCT_TOKEN_REQUIRED'
    assert ev(user_agent=n.FIXED_AGENT,product_token='J1AI-Research-Timing-Pilot')['decision']=='UNKNOWN'


def test_offline_no_network_model_permit_or_executor_import():
    tree=ast.parse((BASE/'phase2_5I/robots_normative.py').read_text('utf8'))
    modules=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):modules.extend(a.name for a in node.names)
        if isinstance(node,ast.ImportFrom):modules.append(node.module)
    assert modules==['hashlib','re','urllib.parse']
    assert not any(isinstance(x,ast.Call) and isinstance(x.func,ast.Name) and x.func.id in {'open','exec','eval','__import__'} for x in ast.walk(tree))


def test_all_24_axes_preserved_and_bound_to_source_and_actual_tests():
    prior=json.loads((BASE/'phase2_5H/NORMATIVE_REVIEW_TEST_PLAN.json').read_bytes())
    current=json.loads((BASE/'phase2_5I/NORMATIVE_CONFORMANCE.json').read_bytes())
    assert [r['id'] for r in current['items']]==[r['id'] for r in prior['items']]
    assert len(current['items'])==24 and current['counts']=={'PASS':13,'FAIL':0,'UNKNOWN':11}
    functions=set()
    for file in [Path(__file__),Path(__file__).with_name('test_nn_v2_spec_fetch.py')]:
        functions.update(x.name for x in ast.parse(file.read_text('utf8')).body if isinstance(x,ast.FunctionDef))
    for row in current['items']:
        assert row['normative_expected_behavior'] and row['old_parser_behavior'] and row['new_parser_difference']
        assert row['tests'] and set(row['tests'])<=functions
        assert row['status']!='UNKNOWN' or row['unresolved']
        assert {r['source'] for r in row['source_references']}=={'S1','S2'}
        for ref in row['source_references']:
            assert ref['raw_SHA256']==n.SPEC_SHAS[ref['source']]
            assert ref['tag_byte_range'][0]<=ref['anchor_attribute_byte_offset']<ref['tag_byte_range'][1]
    assert current['decision']=='NN_V2_ROBOTS_SPEC_CONFORMANCE_PARTIAL'
    assert not current['full_RFC9309_conformance'] and not current['full_Google_conformance']


def test_sealed_a1_public_replay_keeps_four_unknown_no_other_authority():
    r=json.loads((BASE/'phase2_5I/ROBOTS_REEVALUATION.json').read_bytes())
    assert r['raw_SHA256']==n.A1_SHA and r['HTTP_User_Agent']==n.FIXED_AGENT
    assert len(r['results'])==4 and all(x['decision']=='UNKNOWN' for x in r['results'])
    assert all(not x['execution_authorized'] and not x['B_authorized'] and not x['history_admission'] for x in r['results'])
    assert r['aboutj']['decision']=='UNKNOWN' and r['A2_A4_GET']==r['B_GET']==0
    assert r['HISTORY']==r['PREDICTION']==r['B']==r['C']==r['D']=='HOLD'


def test_saved_spec_fetch_ledger_terminal_two_requests_no_reuse():
    ledger=json.loads((BASE/'phase2_5I/SPEC_FETCH_LEDGER.json').read_bytes())
    assert ledger['total_GET']==2 and ledger['total_body_bytes']==189518
    assert [r['id'] for r in ledger['rows']]==['S1','S2']
    assert all(r['HTTP_status']==200 and r['readback_SHA256_match'] for r in ledger['rows'])
    assert ledger['parallel']==ledger['retry']==ledger['redirect']==ledger['A2_A4_GET']==ledger['B_GET']==0
    assert ledger['run_terminal'] and ledger['all_future_reuse_forbidden'] and ledger['unused_budget_expired']==0
    for name,digest in ledger['executed_code_SHA256'].items():
        assert hashlib.sha256((BASE.parents[1]/name).read_bytes()).hexdigest()==digest
