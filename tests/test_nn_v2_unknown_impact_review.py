"""Scope priorities and approval ordering; only synthetic bytes and scenarios."""
from copy import deepcopy
import hashlib
import itertools
import pytest

from research.nn_v2.phase2_5M import impact_review as m

RAW = b'User-agent: *\nDisallow: /closed\nUser-agent: spider\nDisallow: /\n'


def assess(raw=RAW, target='B1', **changes):
    args = dict(scope='SYNTHETIC_ONLY', expected_reference_SHA256=hashlib.sha256(raw).hexdigest(),
                specification_SHA256=m.robots.subset.SPEC_SHAS)
    args.update(changes)
    return m.assess(raw, target, **args)


def scenario(phase='BEFORE', target='B1'):
    return dict(kind='OFFLINE_GATE_SCENARIO_V1', scope='SYNTHETIC_ONLY', target_id=target,
        target_url=m.TARGETS[target], phase=phase, approvals={x: True for x in ['G1','G2','G3','G4_start']},
        checks={x: True for x in m.SCENARIO_CHECKS}, permit_source='NEW_SYNTHETIC_ONLY',
        attempts_used=0 if phase=='BEFORE' else 1, E3_requirement='REQUIRED',
        E2_outcome=None if phase=='BEFORE' else 'COMPLETED',
        E3_outcome=None if phase=='BEFORE' else 'VERIFIED', E4_outcome=None if phase=='BEFORE' else 'SEALED_READBACK')


@pytest.mark.parametrize('target', ['A1','A3','A4','B1'])
def test_bounded_scope_separates_seven_quality_axes_without_promoting_normative_UNKNOWN(target):
    row=assess(target=target)
    assert row['normative']=='ALLOW'
    assert row['matched_rule_count']==0 and [g['agents'] for g in row['group_selection']]==[['*']]
    assert {a for a,p in row['priorities'].items() if p=='P0'}==m.DIRECT
    assert sum(x=='P2' for x in row['priorities'].values())==7
    assert row['certificate']['facts']['work_units'] is not None
    assert not row['execution_authorized'] and not row['permit_issued']


@pytest.mark.parametrize('target', ['A2','B2'])
def test_aboutj_missing_source_does_not_inherit_www_quality_exclusions(target):
    result=m.assess(None,target,scope='SEALED_A1_OFFLINE_REVIEW',expected_reference_SHA256=None)
    assert result['normative']=='UNKNOWN'
    assert sum(x=='P0' for x in result['priorities'].values())==2
    assert sum(x=='P1' for x in result['priorities'].values())==7
    assert not any(result['scope_exclusions'].values())


@pytest.mark.parametrize('target', ['A2','B2'])
def test_negative_www_body_cannot_be_assigned_to_aboutj(target):
    with pytest.raises(m.ReviewError):assess(target=target)


@pytest.mark.parametrize('direct,excluded,unused,expected', [
    (True,False,False,'P0'),(True,True,False,'P0'),(False,False,False,'P1'),
    (False,False,True,'P1'),(False,True,False,'P2'),(False,True,True,'P3')])
def test_priority_requires_proven_exclusion_even_for_unused_future_features(direct,excluded,unused,expected):
    assert m.priority(direct_stop=direct,scope_exclusion_proven=excluded,unused_in_scope=unused)==expected


@pytest.mark.parametrize('value', [None,0,1,'ALLOW','UNKNOWN',{},[]])
def test_negative_untyped_priority_facts_do_not_create_P2_P3(value):
    with pytest.raises(m.ReviewError):m.priority(direct_stop=False,scope_exclusion_proven=value)


@pytest.mark.parametrize('mutation', ['raw-SHA','spec-SHA','old-version','real-profile-on-synthetic-body'])
def test_negative_scope_exclusion_never_survives_integrity_or_version_failure(mutation):
    args={}
    if mutation=='raw-SHA':args['expected_reference_SHA256']='0'*64
    elif mutation=='spec-SHA':args['specification_SHA256']={}
    elif mutation=='old-version':args['parser_version']='nn_v2_robots_offline_layers_v3'
    else:args['scope']='SEALED_A1_OFFLINE_REVIEW'
    result=assess(**args)
    assert result['safety_stop'] and set(result['priorities'].values())=={'P0'}
    assert not any(result['scope_exclusions'].values())


@pytest.mark.parametrize('target', ['A1','A3','A4','B1'])
@pytest.mark.parametrize('change', ['query','percent','host','port','scheme','case','suffix'])
def test_negative_exact_URL_scope_does_not_expand(target,change):
    url=m.TARGETS[target]
    if change=='query':url+='?q=x'
    elif change=='percent':url=url.replace('/', '/%2F',1)
    elif change=='host':url=url.replace('www.jleague.jp','other.invalid')
    elif change=='port':url=url.replace('www.jleague.jp','www.jleague.jp:443')
    elif change=='scheme':url=url.replace('https:','http:')
    elif change=='case':url=url.replace('www.jleague.jp','WWW.JLEAGUE.JP')
    else:url+='extra'
    with pytest.raises(m.ReviewError):assess(target=target,target_url=url)


@pytest.mark.parametrize('field,value', [('header','Override/1.0'),('token',None),('token','Timing-Pilot'),('token',m.contract.UA)])
def test_negative_identity_change_invalidates_quality_certificate(field,value):
    result=assess(**{field:value})
    assert sum(x=='P2' for x in result['priorities'].values())==0
    assert result['priorities']['agent_grammar']=='P0'


def test_scope_certificate_recomputed_against_entire_context():
    row=assess()
    args=dict(scope='SYNTHETIC_ONLY',expected_reference_SHA256=hashlib.sha256(RAW).hexdigest(),specification_SHA256=m.robots.subset.SPEC_SHAS)
    assert m.verify_certificate(row['certificate_hash'],RAW,'B1',**args)
    with pytest.raises(m.ReviewError):m.verify_certificate(row['certificate_hash'],RAW,'A3',**args)
    with pytest.raises(m.ReviewError):m.verify_certificate('0'*64,RAW,'B1',**args)


@pytest.mark.parametrize('raw,axis', [
    (b'User-agent: *\nDisallow: *.gif\n','rule_grammar'),
    (b'\xff','encoding_errors'),
    (b'User-agent: *\nAllow: /j1/news\nDisallow: /j**********\n','longest_rule'),
    (b'User-agent: *\nDisallow: /closed\n#'+b'x'*65536,'parse_limits')],
    ids=['malformed-rule','invalid-UTF8','ranking-conflict','oversize'])
def test_negative_triggered_UNKNOWN_becomes_direct_STOP_not_quality_exclusion(raw,axis):
    result=assess(raw)
    assert result['normative']=='UNKNOWN'
    assert result['priorities'][axis]=='P0'
    assert not result['scope_exclusions'][axis]


@pytest.mark.parametrize('pattern,axis', [('/unused?q=x','query'),('/unused-%2A','reserved_octets')])
def test_untriggered_but_unproved_scope_returns_P1(pattern,axis):
    result=assess(('User-agent: *\nDisallow: '+pattern+'\n').encode())
    assert result['normative']=='ALLOW'
    assert result['priorities'][axis]=='P1' and not result['scope_exclusions'][axis]


@pytest.mark.parametrize('path,raw,expected', [
    ('/search?q=foo',b'User-agent: *\nDisallow: /search?q=foo\n','DENY'),
    ('/search?q=https://x',b'User-agent: *\nDisallow: /closed\n','UNKNOWN'),
    ('/foo%2Fbar',b'User-agent: *\nDisallow: /foo/bar\n','UNKNOWN'),
    ('/%7Euser',b'User-agent: *\nDisallow: /~user\n','DENY'),
    ('/x/public',b'User-agent: *\nDisallow: /x\nAllow: /x/public\n','ALLOW'),
    ('/page.htm',b'User-agent: *\nAllow: /page\nDisallow: /*.htm\n','UNKNOWN')])
def test_unchanged_parser_path_query_encoding_longest_differences(path,raw,expected):
    result=m.robots.evaluate(raw,source_host='synthetic.invalid',target_url='https://synthetic.invalid'+path,
        header=m.contract.UA,declared_tokens=[m.contract.TOKEN],expected_raw_SHA256=hashlib.sha256(raw).hexdigest(),
        specification_SHA256=m.robots.subset.SPEC_SHAS,profile=m.robots.subset.SYNTHETIC_PROFILE)
    assert result['layer1']['decision']==expected
    assert not result['execution_authorized']


@pytest.mark.parametrize('phase', ['BEFORE','AFTER'])
@pytest.mark.parametrize('target', list(m.TARGETS))
def test_gate_order_is_synthetic_only_with_current_send_proof_post_send(phase,target):
    value=scenario(phase,target);before=deepcopy(value)
    result=m.review_gate_scenario(value)
    assert result['decision']==('SIMULATED_PRE_SEND_READY' if phase=='BEFORE' else 'SIMULATED_POST_SEND_REVIEW_COMPLETE')
    assert value==before and not result['execution_authorized'] and not result['permit_issued']
    assert not result['actual_E2_verified'] and not result['actual_E3_verified']


@pytest.mark.parametrize('gate', ['G1','G2','G3','G4_start'])
def test_negative_one_approval_cannot_substitute_for_another(gate):
    value=scenario();value['approvals'][gate]=False
    result=m.review_gate_scenario(value)
    assert result['decision']=='SIMULATED_STOP' and gate in result['missing']


@pytest.mark.parametrize('condition',sorted(m.SCENARIO_CHECKS))
def test_negative_missing_pre_send_mechanism_evidence_or_scope_stops(condition):
    value=scenario();value['checks'][condition]=False
    assert m.review_gate_scenario(value)['decision']=='SIMULATED_STOP'


@pytest.mark.parametrize('field,value', [
    ('scope','PRODUCTION'),('kind','PERMIT'),('permit_source','OLD_G_UNUSED_A_BUDGET'),
    ('permit_source','OLD_I_SPEC_BUDGET'),('permit_source','APPROVED_REAL_PERMIT'),('attempts_used',1),
    ('attempts_used',2),('attempts_used',True),('E2_outcome','COMPLETED'),('E3_outcome','VERIFIED'),
    ('E4_outcome','SEALED_READBACK'),('E3_requirement','IGNORE_UNKNOWN')])
def test_negative_no_old_budget_activation_or_preexisting_current_send_proof(field,value):
    case=scenario();case[field]=value
    assert m.review_gate_scenario(case)['decision']=='SIMULATED_STOP'


@pytest.mark.parametrize('outcome', ['STARTED','UNKNOWN','FAILED',None])
def test_negative_post_send_failure_never_retries_or_uses_E4_as_E2(outcome):
    case=scenario('AFTER');case['E2_outcome']=outcome
    result=m.review_gate_scenario(case)
    assert result['decision']=='SIMULATED_STOP' and not result['automatic_retry']


@pytest.mark.parametrize('field,value', [('E3_outcome','NOT_OBSERVED'),('E3_outcome','UNKNOWN'),('E4_outcome',None),
    ('E4_outcome','PARTIAL'),('attempts_used',0),('attempts_used',2)])
def test_negative_post_send_missing_required_evidence_stops(field,value):
    case=scenario('AFTER');case[field]=value
    assert m.review_gate_scenario(case)['decision']=='SIMULATED_STOP'


def test_explicit_E3_scope_records_unobserved_without_claiming_independent_header_proof():
    for phase in ['BEFORE','AFTER']:
        case=scenario(phase);case['E3_requirement']='NOT_REQUIRED_EXPLICITLY_APPROVED'
        case['checks']['E3_method_qualified']=False
        if phase=='AFTER':case['E3_outcome']='NOT_OBSERVED'
        result=m.review_gate_scenario(case)
        assert result['decision']!='SIMULATED_STOP' and not result['actual_E3_verified']
    case['E3_outcome']='VERIFIED'
    assert m.review_gate_scenario(case)['decision']=='SIMULATED_STOP'


@pytest.mark.parametrize('target,url', [('B3','https://www.jleague.jp/extra/'),('B1','https://www.jleague.jp/j1/news/?page=2'),
    ('B2','https://www.jleague.jp/corporate/pressrelease/'),('A2','https://www.jleague.jp/robots.txt')])
def test_negative_unapproved_URL_in_scenario_rejected(target,url):
    case=scenario();case['target_id']=target;case['target_url']=url
    assert m.review_gate_scenario(case)['decision']=='SIMULATED_STOP'


@pytest.mark.parametrize('filename', ['UNKNOWN_IMPACT_MATRIX.json','URL_STOP_MATRIX.json','APPROVAL_GATES.json'])
def test_public_document_schema_and_exact_identity_references(filename):
    from pathlib import Path
    import json
    from jsonschema import Draft202012Validator
    p=Path(m.__file__).parent
    schema=json.loads((p/'REVIEW_SCHEMAS.json').read_bytes())['schemas'][filename]
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(json.loads((p/filename).read_bytes())))


def test_actual_review_rows_preserve_formal_definitions_and_history():
    from pathlib import Path
    import json
    p=Path(m.__file__).parent
    original=json.loads((p.parent/'phase2_5J/NORMATIVE_REVIEW.json').read_bytes())
    old=[x for x in original['items'] if x['status']=='UNKNOWN']
    new=json.loads((p/'UNKNOWN_IMPACT_MATRIX.json').read_bytes())
    assert [x['id'] for x in old]==[x['id'] for x in new['rows']]==list(m.IDS)
    assert all(a['inherited_item']==b['original_I_record'] and b['definition']==a['inherited_item']['normative_expected_behavior'] and
               b['normative_status']=='UNKNOWN' for a,b in zip(old,new['rows']))
    assert new['counts']['overall_six_targets']==dict(P0=2,P1=7,P2=0,P3=0)
    assert new['counts']['www_fixed_A1']==dict(P0=2,P1=0,P2=7,P3=0)
    assert new['counts']['aboutj_missing_source']==dict(P0=2,P1=7,P2=0,P3=0)


def test_scope_certificates_in_published_review_have_no_aboutj_exclusion():
    from pathlib import Path
    import json
    rows=json.loads((Path(m.__file__).parent/'URL_STOP_MATRIX.json').read_bytes())['rows']
    assert len(rows)==6 and {x['id'] for x in rows}==set(m.TARGETS)
    for row in rows:
        assert row['URL']==m.TARGETS[row['id']] and not row['final_communication']
        assert row['evidence']['status']=='UNKNOWN' and row['permit']['current_request_authority']==0
        if row['id'] in {'A2','B2'}:
            assert row['robots']['reference_SHA256'] is None and row['robots']['decision']=='UNKNOWN'
        else:
            assert row['robots']['reference_SHA256']==m.robots.subset.A1_SHA
            assert row['robots']['decision']=='ALLOW' and row['robots']['conditional_candidate_only']


def test_no_live_policy_or_transport_import_added():
    import ast
    from pathlib import Path
    tree=ast.parse(Path(m.__file__).read_text(encoding='utf8'))
    assert {x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names}=={'hashlib'}
    assert {n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}=={'urllib.parse','research.nn_v2.phase2_5L'}
