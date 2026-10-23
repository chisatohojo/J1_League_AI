"""Phase J pure contracts and source-backed synthetic differential cases.

Actual sealed S1/S2/A1 readback is a separate private read-only audit. Nothing
here calls HTTP, issues a permit, starts a worker, loads a model or writes data.
"""
import ast
from copy import deepcopy
import hashlib
import json
from itertools import product
from pathlib import Path

import pytest

from research.nn_v2.phase2_5I import robots_normative as prior
from research.nn_v2.phase2_5J import robots_layers as current
from research.nn_v2.phase2_5J.differential_cases import cases,compare


def ev(raw=b'User-agent: *\nDisallow: /private',path='/public',**changes):
    if isinstance(raw,str):raw=raw.encode('utf8')
    args=dict(source_host='synthetic.invalid',target_url='https://synthetic.invalid'+path,
        user_agent='ExampleBot/1.0',product_token='ExampleBot',profile=prior.SYNTHETIC_PROFILE,
        expected_raw_SHA256=hashlib.sha256(raw).hexdigest(),specification_SHA256=prior.SPEC_SHAS)
    args.update(changes)
    result=current.evaluate(raw,**args)
    assert not result['execution_authorized'] and not result['B_authorized'] and not result['history_admission']
    assert result['parser_version']==current.VERSION
    return result


def plan():
    return dict(kind='SYNTHETIC_TRANSPORT_PLAN_V1',scope='SYNTHETIC_ONLY',approved_for_synthetic_test=True,
        URL='https://synthetic.invalid/robots.txt',host='synthetic.invalid',port=443,method='GET',
        max_GET=1,remaining_GET=1,issued_UTC='2026-01-01T00:00:00+00:00',expires_UTC='2026-01-01T01:00:00+00:00',
        redirect=0,retry=0,parallel=0,destination='sandbox/snapshot.bin',body_cap=65536)


def request():
    p=plan();r={k:p[k] for k in ['URL','host','port','method','scope','destination']};r['body_bytes']=646;return r


@pytest.mark.parametrize('case',cases(),ids=lambda c:c['id'])
def test_differential_H_I_J_source_backed(case):
    r=compare(case)
    assert r['expected_decisions']==case['expected']
    assert r['J_layers']['layer1']['decision']!='ALLOW' or not r['J_layers']['execution_authorized']
    if r['I_synthetic']['decision']=='UNKNOWN' and r['J_layers']['layer1']['decision']!='UNKNOWN':
        assert r['J_layers']['j1ai_evidence_policy']['decision']=='UNKNOWN'
        assert case['id'] in {'unknown_record','unknown_record_allow','empty','comment_only','query_ascii_pair'}


@pytest.mark.parametrize('body',[b'',b'\n',b'\r\n',b' ',b'\t',b'# comment',b'\xef\xbb\xbf# BOM comment',b'\r#comment\r'])
def test_empty_body_normative_ALLOW_is_not_J1AI_evidence_permission(body):
    r=ev(body)
    assert r['layer1']['decision']=='ALLOW'
    assert r['j1ai_evidence_policy']['decision']=='UNKNOWN'
    assert r['legacy_I_result']['decision']=='UNKNOWN'


@pytest.mark.parametrize('field',['X-review: retained','Crawl-delay: 10','Host: other.invalid','Request-rate: 1/9','Sitemaps: https://unfetched.invalid/map'])
@pytest.mark.parametrize('path,decision',[('/private','DENY'),('/public','ALLOW')])
def test_other_records_do_not_change_defined_rules_but_policy_stays_unknown(field,path,decision):
    r=ev('User-agent: *\n'+field+'\nDisallow: /private',path)
    assert r['layer1']['decision']==decision and r['j1ai_evidence_policy']['decision']=='UNKNOWN'
    assert r['layer1']['ignored_other_records'][0]['reason']=='UNKNOWN_DIRECTIVE'


def test_other_record_does_not_break_multi_agent_group():
    r=ev(b'User-agent: ExampleBot\nX-review: keep\nUser-agent: OtherBot\nDisallow: /')
    assert r['layer1']['decision']=='DENY'
    assert r['layer1']['applied_groups']==[dict(group=1,agents=['ExampleBot','OtherBot'])]


@pytest.mark.parametrize('pattern,path,decision',[
    ('/foo/bar?baz=quz','/foo/bar?baz=quz','DENY'),
    ('/foo/bar?baz=','/foo/bar?baz=','DENY'),
    ('/foo/bar?baz=quz','/foo/bar?baz=other','ALLOW'),
    ('/foo/bar?baz=quz','/foo/bar','ALLOW'),
    ('/foo/bar?baz=quz','/foo/bar?baz=https://foo.bar','UNKNOWN'),
    ('/foo/bar?baz=quz','/foo/bar?baz=%3A','UNKNOWN'),
    ('/foo/bar?baz=quz','/foo/bar?baz=x&other=y','UNKNOWN')])
def test_RFC_figure4_ASCII_query_pair_without_reserved_data_generalization(pattern,path,decision):
    r=ev('User-agent: *\nDisallow: '+pattern,path)
    assert r['layer1']['decision']==decision


def test_ASCII_query_cannot_bypass_missing_token_or_defined_rule_error():
    assert ev(path='/x?q=x',product_token=None)['layer1']['decision']=='UNKNOWN'
    assert ev(b'User-agent: *\nDisallow: *.gif$',path='/x?q=x')['layer1']['decision']=='UNKNOWN'


@pytest.mark.parametrize('extra',[
    b'Disallow: *.gif$',b'Allow: /bad%GG',b'Disallow /bad',b'Disallow: /bad$anchor',b'User-agent: Bot1'])
def test_unknown_field_cannot_hide_malformed_defined_rule(extra):
    r=ev(b'User-agent: *\nX-review: keep\n'+extra)
    assert r['layer1']['decision']=='UNKNOWN'


def test_implicit_robots_URI_does_not_infer_or_change_HTTP_product_token():
    r=ev(path='/robots.txt',user_agent=prior.FIXED_AGENT,product_token=None)
    assert r['layer1']['decision']=='ALLOW' and r['legacy_I_result']['decision']=='UNKNOWN'
    assert r['layer1']['user_agent']==prior.FIXED_AGENT
    assert r['layer1']['applied_groups']==[] and r['j1ai_evidence_policy']['decision']=='UNKNOWN'
    assert r['layer1']['source_references']==['S1#section-2.2.2']


@pytest.mark.parametrize('path',['/general/kiyaku/','/general/copyright/','/j1/news/','/robots.txt?x'])
def test_non_implicit_targets_keep_missing_token_unknown(path):
    assert ev(path=path,user_agent=prior.FIXED_AGENT,product_token=None)['layer1']['decision']=='UNKNOWN'


@pytest.mark.parametrize('path',['/robots.txt','/public'])
@pytest.mark.parametrize('raw',[b'',b'# comment',b'User-agent: *\nAllow: /'])
@pytest.mark.parametrize('bad',[
    {'expected_raw_SHA256':'0'*64},{'specification_SHA256':{}},{'parser_version':'old'},
    {'target_url':'http://synthetic.invalid/robots.txt'},{'target_url':'https://synthetic.invalid.evil/robots.txt'},
    {'source_host':'www.jleague.jp'},{'profile':'LIVE'}])
def test_no_override_past_integrity_origin_version_or_scope_failure(path,raw,bad):
    r=ev(raw,path=path,product_token=None,**bad)
    assert r['layer1']['decision']=='UNKNOWN'


@pytest.mark.parametrize('status',[301,403,404,429,500,503,None,True])
@pytest.mark.parametrize('raw',[b'',b'User-agent: *\nAllow: /'])
def test_retrieval_failure_never_uses_empty_or_implicit_ALLOW(status,raw):
    r=ev(raw,path='/robots.txt',response_status=status)
    assert r['layer1']['decision']=='UNKNOWN' and r['layer1']['safety_stop']
    assert r['j1ai_evidence_policy']['decision']=='DENY' and r['legacy_I_result'] is None


@pytest.mark.parametrize('token',[None,'','Bot1','ExampleBot/1.0','*','OtherBot'])
def test_declared_agent_not_silently_inferred_for_unknown_fields(token):
    assert ev(b'User-agent: *\nCrawl-delay: 2\nAllow: /',product_token=token)['layer1']['decision']=='UNKNOWN'


def test_valid_synthetic_plan_is_pure_and_does_not_consume_or_issue_permit():
    p=plan();r=request();before=deepcopy((p,r))
    for _ in range(2):
        out=current.permit_check(r,p,'2026-01-01T00:30:00+00:00')
        assert out['decision']=='ALLOW' and not out['real_permit_issued'] and not out['execution_authorized']
    assert (p,r)==before


def test_unapproved_plan_is_rejected_even_with_robots_ALLOW():
    p=current.permit_check(request(),None,'2026-01-01T00:30:00+00:00')
    out=current.communication_check(dict(decision='ALLOW',safety_stop=False),p,dict(decision='ALLOW'),site_access_conditions_verified=True)
    assert p['decision']=='UNAPPROVED' and not out['communication_candidate'] and not out['execution_authorized']


@pytest.mark.parametrize('key,value',[
    ('kind','REAL_PERMIT'),('scope','B'),('approved_for_synthetic_test',False),('remaining_GET',0),('remaining_GET',2),
    ('remaining_GET',True),('max_GET',2),('method','HEAD'),('host','www.jleague.jp'),('port',80),('port',True),
    ('redirect',1),('retry',1),('parallel',1),('body_cap',645),('body_cap',65537),
    ('destination','../snapshot.bin'),('destination','C:/runtime/out'),('destination','sandbox/../out'),
    ('destination','sandbox\\out'),('destination','/sandbox/out'),('expires_UTC','2025-12-31T23:00:00+00:00')])
def test_plan_negative_control_limits_scope_method_host_destination(key,value):
    p=plan();p[key]=value
    assert current.permit_check(request(),p,'2026-01-01T00:30:00+00:00')['decision']=='DENY'


@pytest.mark.parametrize('now',['2025-12-31T23:59:59+00:00','2026-01-01T01:00:00+00:00','2026-01-01T00:30:00','not-a-time','2026-01-01T00:30:00+09:00'])
def test_plan_time_expiry_and_timezone(now):
    assert current.permit_check(request(),plan(),now)['decision']=='DENY'


@pytest.mark.parametrize('url',[
    'https://www.jleague.jp/robots.txt','https://aboutj.jleague.jp/robots.txt',
    'https://synthetic.invalid.evil/robots.txt','https://user@synthetic.invalid/robots.txt',
    'https://synthetic.invalid:443/robots.txt','https://synthetic.invalid/a\nb',
    'https://synthetic.invalid/robots.txt#fragment'])
def test_real_and_malformed_URLs_cannot_be_authorized_by_a_synthetic_plan(url):
    p=plan();r=request();p['URL']=r['URL']=url
    assert current.permit_check(r,p,'2026-01-01T00:30:00+00:00')['decision']=='DENY'


@pytest.mark.parametrize('robots,permit,evidence,site',list(product(['ALLOW','DENY','UNKNOWN'],['ALLOW','DENY','UNAPPROVED'],['ALLOW','DENY','UNKNOWN'],[False,True])))
def test_three_layers_truth_table_no_authority_escalation(robots,permit,evidence,site):
    p=dict(decision=permit,real_permit_issued=False,execution_authorized=False)
    out=current.communication_check(dict(decision=robots,safety_stop=False),p,dict(decision=evidence),site_access_conditions_verified=site)
    assert out['communication_candidate']==(robots==permit==evidence=='ALLOW' and site)
    assert not out['execution_authorized'] and not out['B_authorized'] and not out['history_admission']


@pytest.mark.parametrize('stop',[True,None,'',0])
def test_unknown_safety_state_never_becomes_candidate(stop):
    p=current.permit_check(request(),plan(),'2026-01-01T00:30:00+00:00')
    assert not current.communication_check(dict(decision='ALLOW',safety_stop=stop),p,dict(decision='ALLOW'),site_access_conditions_verified=True)['communication_candidate']


def test_no_HTTP_worker_permit_issuer_model_or_filesystem_import_or_call():
    path=Path(__file__).parents[1]/'research/nn_v2/phase2_5J/robots_layers.py'
    tree=ast.parse(path.read_text('utf8'))
    imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(a.name for a in node.names)
        if isinstance(node,ast.ImportFrom):imports.append(node.module)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):assert node.func.id not in {'open','exec','eval','__import__'}
    assert set(imports)=={'datetime','pathlib','urllib.parse','re','research.nn_v2.phase2_5I'}


def test_exact_original_eleven_axes_and_problems_are_preserved():
    base=Path(__file__).parents[1]/'research/nn_v2'
    old=json.loads((base/'phase2_5I/NORMATIVE_CONFORMANCE.json').read_bytes())
    new=json.loads((base/'phase2_5J/NORMATIVE_REVIEW.json').read_bytes())
    unknown=[x for x in old['items'] if x['status']=='UNKNOWN']
    assert [x['id'] for x in new['items']]==[x['id'] for x in unknown]
    assert len(new['items'])==11 and new['counts']==dict(PASS=2,FAIL=0,UNKNOWN=9)
    functions={x.name for x in ast.parse(Path(__file__).read_text('utf8')).body if isinstance(x,ast.FunctionDef)}
    for row,original in zip(new['items'],unknown):
        assert row['inherited_item']==original and row['inherited_problem_unchanged']==original['unresolved']
        assert row['additional_tests'] and set(row['additional_tests'])<=functions
        assert all(row[k] for k in ['normative_text_requirement','relationship_to_examples','current_I_behavior','J_interpretation','evidence_strength'])
        assert row['status']!='UNKNOWN' or row['unresolved']
    assert not new['full_RFC_conformance'] and not new['full_Google_conformance']


def test_published_differential_is_reproducible_and_has_no_new_inconsistency():
    path=Path(__file__).parents[1]/'research/nn_v2/phase2_5J/PARSER_DIFF.json'
    stored=json.loads(path.read_bytes())
    assert stored['cases']==[compare(c) for c in cases()]
    assert len(stored['cases'])==28 and stored['new_inconsistency_count']==0
    assert stored['observed_new_false_ALLOW_count']==0 and not stored['universal_false_ALLOW_absence_proven']


def test_published_A1_layer_change_does_not_change_old_record_or_authorize_GET():
    base=Path(__file__).parents[1]/'research/nn_v2'
    old=base/'phase2_5I/ROBOTS_REEVALUATION.json'
    report=json.loads((base/'phase2_5J/ROBOTS_REEVALUATION.json').read_bytes())
    assert report['old_I_result_SHA256']==hashlib.sha256(old.read_bytes()).hexdigest()
    assert all(x['decision']=='UNKNOWN' for x in json.loads(old.read_bytes())['results'])
    assert [x['layer1']['decision'] for x in report['results']]==['ALLOW','UNKNOWN','UNKNOWN','UNKNOWN']
    assert all(x['layer2']['decision']=='UNAPPROVED' and not x['layer3']['communication_candidate'] and not x['layer3']['execution_authorized'] for x in report['results'])
    assert report['aboutj']['layer1']=='UNKNOWN' and report['new_permit']==report['A2_A4_GET']==report['B_GET']==0


def test_source_provenance_has_exact_pins_without_new_acquisition():
    path=Path(__file__).parents[1]/'research/nn_v2/phase2_5J/INPUT_EVIDENCE.json'
    report=json.loads(path.read_bytes())
    assert [s['raw_SHA256'] for s in report['sources']]==[prior.SPEC_SHAS['S1'],prior.SPEC_SHAS['S2']]
    assert [s['bytes'] for s in report['sources']]==[82367,107151]
    assert all(s['original_readback_SHA_verified'] for s in report['sources'])
    assert report['A1']['raw_SHA256']==prior.A1_SHA and report['A1']['readback_SHA_verified']
    assert report['new_GET']==report['HEAD']==report['DNS_probe']==report['permit_issued']==report['old_run_reexecuted']==0
