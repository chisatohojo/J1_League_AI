"""Design-only negative controls. No HTTP, permit issuance or standard claims."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

BASE=Path(__file__).parents[1]/'research/nn_v2/phase2_5H'
s=importlib.util.spec_from_file_location('spec_proposal_test',BASE/'spec_permit_contract.py')
p=importlib.util.module_from_spec(s);s.loader.exec_module(p)


def proposal():return json.loads((BASE/'SPEC_FETCH_PROPOSAL.json').read_bytes())
def checklist():return json.loads((BASE/'NORMATIVE_REVIEW_TEST_PLAN.json').read_bytes())


def test_design_and_checklist_are_consistent_but_cannot_issue_or_enable():
    r=p.validate_proposal(proposal())
    assert r['currently_authorized_GET']==0 and not r['issued'] and not r['execution_authorized'] and not r['B_authorized']
    assert p.validate_review_plan(checklist())['normative_cases_executed']==0


@pytest.mark.parametrize('url',[
    'https://www.rfc-editor.org/rfc/rfc9309.txt','http://www.rfc-editor.org/rfc/rfc9309.html',
    'https://www.rfc-editor.org:443/rfc/rfc9309.html','https://WWW.rfc-editor.org/rfc/rfc9309.html',
    'https://www.rfc-editor.org/rfc/rfc9309.html?x=1','https://www.rfc-editor.org/rfc/rfc9309.html#section-2',
    'https://www.jleague.jp/robots.txt','https://www.jleague.jp/j1/news/',
    'https://aboutj.jleague.jp/corporate/pressrelease/'])
def test_exact_reference_no_replacements_or_old_budgets(url):
    v=proposal();v['documents'][0]['URL']=url
    with pytest.raises(p.ProposalStop):p.validate_proposal(v)


@pytest.mark.parametrize('url',[
    'https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec',
    'https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec?hl=en',
    'https://developers.google.com/search/docs/crawling-indexing/robots/robots_txt?hl=ja',
    'https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec?hl=ja&x=1',
    'https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec?hl=%6Aa'])
def test_Google_language_query_is_exact_not_normalized_or_redirected(url):
    v=proposal();v['documents'][1]['URL']=url
    with pytest.raises(p.ProposalStop):p.validate_proposal(v)


@pytest.mark.parametrize('field,value',[
    ('kind','ACTIVE_PERMIT'),('issued',True),('activated',True),('permit_id','active'),
    ('approval_UTC','2026-01-02T00:00:00Z'),('expires_UTC','2026-01-03T00:00:00Z'),
    ('currently_authorized_GET',2),('currently_authorized_GET',False),('gate','VERIFIED'),
    ('B_GET',1),('A2_A4_GET',1),('extra_robots_GET',1),('reuse_G_unused_budget',True),
    ('automatic_source_substitution',True),('approval_required',False),('host_access_conditions_review_required',False)])
def test_static_proposal_cannot_be_promoted_or_extend_scope(field,value):
    v=proposal();v[field]=value
    with pytest.raises(p.ProposalStop):p.validate_proposal(v)


@pytest.mark.parametrize('field,value',[
    ('host','unexpected.invalid'),('port',80),('explicit_port',443),('path','/'),('query',''),('fragment','x'),
    ('method','HEAD'),('max_attempts',2),('max_attempts',True),('body_cap_bytes',2097153),
    ('HTTP_status',200),('raw_SHA256','0'*64),('response_verified',True),('access_conditions','PERMITTED'),
    ('execution_authorized',True)])
def test_components_and_unobserved_response_cannot_be_forged(field,value):
    v=proposal();v['documents'][1][field]=value
    with pytest.raises(p.ProposalStop):p.validate_proposal(v)


@pytest.mark.parametrize('key',list(proposal()['limits']))
def test_communication_caps_no_retry_redirect_or_deadline_widening(key):
    v=proposal();v['limits'][key]+=1
    with pytest.raises(p.ProposalStop):p.validate_proposal(v)


def test_two_only_fixed_order_no_spare_slots_or_duplicates():
    for change in ['swap','remove','add','duplicate']:
        v=proposal()
        if change=='swap':v['documents'].reverse()
        elif change=='remove':v['documents'].pop()
        elif change=='add':v['documents'].append(v['documents'][0])
        else:v['documents'][1]=v['documents'][0]
        with pytest.raises(p.ProposalStop):p.validate_proposal(v)


@pytest.mark.parametrize('key',[
    'raw_SHA256_required','metadata_request_SHA256_required','flush_fsync_readback_required',
    'seal_receipt_required','no_overwrite','private_originals','exclusive_create_required'])
def test_immutable_storage_and_readback_cannot_be_optional(key):
    v=proposal();v['storage'][key]=False
    with pytest.raises(p.ProposalStop):p.validate_proposal(v)


@pytest.mark.parametrize('key,value',[('created',True),('absolute_root','synthetic-already-active')])
def test_no_root_activation_in_a_design(key,value):
    v=proposal();v['storage'][key]=value
    with pytest.raises(p.ProposalStop):p.validate_proposal(v)


@pytest.mark.parametrize('key,value',[
    ('normative_cases_executed',24),('RFC9309_verified',True),('Google_profile_adopted',True),
    ('source_requirement','memory-only')])
def test_future_normative_tests_are_not_already_executed(key,value):
    v=checklist();v[key]=value
    with pytest.raises(p.ProposalStop):p.validate_review_plan(v)


@pytest.mark.parametrize('field,value',[
    ('status','PASS'),('section_anchor','guessed-section'),('normative_expected_result','ALLOW'),
    ('required_before_offline_verified',False)])
def test_no_unsourced_expected_result_or_waived_specification_gate(field,value):
    v=checklist();v['items'][0][field]=value
    with pytest.raises(p.ProposalStop):p.validate_review_plan(v)


def test_checklist_cannot_drop_or_duplicate_a_required_axis():
    v=checklist();v['items'].pop()
    with pytest.raises(p.ProposalStop):p.validate_review_plan(v)
    v=checklist();v['items'][1]=v['items'][0]
    with pytest.raises(p.ProposalStop):p.validate_review_plan(v)


def test_new_code_is_pure_validation_without_an_http_or_permit_entrypoint():
    tree=ast.parse((BASE/'spec_permit_contract.py').read_text('utf8'))
    assert not any(isinstance(n,ast.Import) for n in ast.walk(tree))
    assert [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]==['urllib.parse']
    forbidden={'open','exec','eval','__import__','getattr','setattr','globals','locals'}
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in forbidden for n in ast.walk(tree))
