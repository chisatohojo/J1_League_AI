"""Synthetic discovery contracts. No real evidence, workers, model or GET."""
from copy import deepcopy
import ast
import importlib.util
from pathlib import Path

import pytest

FILE=Path(__file__).parents[1]/'research/nn_v2/phase2_5D/discovery_contract.py'
spec=importlib.util.spec_from_file_location('pure_discovery',FILE)
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)


def claim(role='acquisition', **changes):
    kind={'planned_kickoff':'SCHEDULE_OBSERVATION','actual_kickoff':'OFFICIAL_EXPLICIT_EVENT',
        'change_announcement':'OFFICIAL_EXPLICIT_NOTICE','information_publication':'OFFICIAL_EXPLICIT_PUBLICATION',
        'acquisition':'REQUEST_RESPONSE_COMPLETION','prediction_cutoff':'ACTUAL_REGISTERED_CUTOFF',
        'result_available':'OFFICIAL_COMPLETED_RESULT_WITNESS'}[role]
    item=dict(role=role,value='2026-01-01T12:00:00+00:00',precision='SECOND_WITH_OFFSET',proof_kind=kind,
        source_verified=True,raw_sha256='a'*64,observed_version_acquired_at='2026-01-01T12:00:00+00:00')
    item.update(changes);return item


def trace():
    target=dict(identity='synthetic:target',revision='fixed-source',cutoff='2026-01-03T00:00:00+00:00',
        kickoff='2026-01-03T12:00:00+00:00')
    rows=[dict(identity='synthetic:prior',revision='fixed-source',raw_sha256='a'*64,metadata_sha256='b'*64,
        request_sha256='c'*64,actual_kickoff=claim('actual_kickoff',value='2026-01-01T09:00:00+00:00'),
        end_time='2026-01-01T11:00:00+00:00',result_available=claim('result_available',value='2026-01-01T11:30:00+00:00'),
        acquisition=claim(),verified_complete_regulation_result=True)]
    return target,rows


def test_axes_are_the_existing_four_not_a_new_evidence_taxonomy():
    assert d.axes(['D','A','B','C'])==('A','B','C','D')


@pytest.mark.parametrize('values',[[],['b'],[' B'],['TIME'],['B','B'],['B',1],'BCD',None])
def test_ambiguous_or_unknown_axis_not_normalized_to_PASS(values):
    with pytest.raises(d.DiscoveryStop):d.axes(values)


@pytest.mark.parametrize('role',sorted(d.ROLES))
def test_well_formed_time_claim_alone_never_PASSes_B_C_D(role):
    report=d.inspect_time(claim(role))
    assert report['status']=='CLAIM_SHAPE_VERIFIED_ONLY'
    assert not report['evidence_axis_PASS'] and not report['history_admission']


@pytest.mark.parametrize('value',['2026-01-01','2026-01-01T12:00','2026-01-01T12:00:00',None,'unknown'])
def test_date_only_unknown_or_naive_is_not_promoted_to_exact_UTC(value):
    assert d.inspect_time(claim(value=value))['status']=='HOLD'


@pytest.mark.parametrize('precision',['DATE','MINUTE','UNKNOWN',None])
def test_precision_cannot_be_invented_from_midnight_or_zero_seconds(precision):
    assert d.inspect_time(claim(precision=precision))['status']=='HOLD'


@pytest.mark.parametrize('role,kind',[('actual_kickoff','SCHEDULE_OBSERVATION'),
    ('acquisition','FILE_MTIME'),('information_publication','REQUEST_RESPONSE_COMPLETION'),
    ('change_announcement','CURRENT_SCHEDULE'),('prediction_cutoff','HYPOTHETICAL_MIDNIGHT'),
    ('result_available','NINETY_MINUTES_AFTER_KICKOFF')])
def test_semantically_different_clocks_are_not_substitutes(role,kind):
    assert d.inspect_time(claim(role,proof_kind=kind))['status']=='HOLD'


@pytest.mark.parametrize('changes',[dict(source_verified=False),dict(raw_sha256='not-a-hash')])
def test_unverified_original_cannot_prove_time(changes):
    assert d.inspect_time(claim(**changes))['status']=='HOLD'


def test_cutoff_boundary_exact_allowed_later_microsecond_rejected():
    cutoff='2026-01-01T12:00:00+00:00'
    assert d.inspect_time(claim(),cutoff=cutoff)['status']=='CLAIM_SHAPE_VERIFIED_ONLY'
    assert 'AFTER_CUTOFF' in d.inspect_time(claim(value='2026-01-01T12:00:00.000001+00:00'),cutoff=cutoff)['reasons']


@pytest.mark.parametrize('value',[None,'2026-01-01','2026-01-02T00:00:00+00:00'])
def test_old_claim_on_a_later_acquired_page_does_not_establish_past_PIT(value):
    item=claim('information_publication',observed_version_acquired_at=value)
    assert d.inspect_time(item,cutoff='2026-01-01T13:00:00+00:00')['status']=='HOLD'


def test_only_literal_saved_link_resolution_without_ID_generation():
    raw=b'<a href="/news/article/900001/?a=1&amp;b=2">Synthetic notice</a>'
    result=d.extract_saved_links(raw,expected_sha256=d.sha(raw),source_url='https://www.jleague.jp/j1/news/')[0]
    assert result['url']=='https://www.jleague.jp/news/article/900001/?a=1&b=2'
    assert '&amp;' in result['start_tag'] and result['origin']=='LITERAL_SAVED_HTML_ATTRIBUTE'
    assert not result['execution_authorized'] and result['current_existence']=='UNKNOWN'
    assert result['historical_publication']=='UNKNOWN'


@pytest.mark.parametrize('href',['http://www.jleague.jp/news/','https://evil.invalid/news/',
    'https://www.jleague.jp.evil.invalid/','https://u:p@www.jleague.jp/','https://www.jleague.jp:443/',
    'javascript:alert(1)','file:///tmp/evidence','https://aboutj.jleague.jp/corporate/pressrelease/'])
def test_unknown_host_scheme_or_credentials_never_become_authorized_URL(href):
    result=d.resolve_saved_link('https://www.jleague.jp/j1/news/',href)
    assert result['status']=='UNAPPROVED_HOST_OR_SCHEME' and not result['execution_authorized']


@pytest.mark.parametrize('href',['',' /news/','/news/\n','\\\\host\\path'])
def test_unsafe_literal_is_rejected_without_fallback(href):
    assert d.resolve_saved_link('https://www.jleague.jp/j1/news/',href)['status']=='REJECTED_UNSAFE_LITERAL'


def test_tampered_original_refuses_link_discovery():
    with pytest.raises(d.DiscoveryStop,match='ORIGINAL_SHA_MISMATCH'):
        d.extract_saved_links(b'<a href="/news/">synthetic</a>',expected_sha256='a'*64,source_url='https://www.jleague.jp/')


def test_changed_HTML_base_does_not_retarget_relative_links():
    raw=b'<base href="https://evil.invalid/"><a href="news/">synthetic</a>'
    with pytest.raises(d.DiscoveryStop,match='HTML_BASE'):
        d.extract_saved_links(raw,expected_sha256=d.sha(raw),source_url='https://www.jleague.jp/')


def test_fragment_resolution_preserves_provenance_without_a_second_resource():
    result=d.resolve_saved_link('https://www.jleague.jp/j1/news/','#saved-fragment')
    assert result['literal_resolved_url'].endswith('#saved-fragment')
    assert result['url']=='https://www.jleague.jp/j1/news/' and not result['execution_authorized']


def witness(**changes):
    item=dict(identity='synthetic:prior',url='https://www.jleague.jp/synthetic/',raw_sha256='a'*64,role='acquisition',revision='fixed')
    item.update(changes);return item


def test_duplicate_witness_is_not_two_independent_confirmations():
    with pytest.raises(d.DiscoveryStop,match='DUPLICATE_WITNESS'):d.witness_set([witness(),witness()],expected_revision='fixed')


def test_revision_change_is_STOP_not_an_evidence_gap():
    with pytest.raises(d.DiscoveryStop,match='REVISION'):d.witness_set([witness(revision='latest')],expected_revision='fixed')


def test_one_raw_may_support_distinct_claim_roles_without_double_counting():
    assert d.witness_set([witness(),witness(role='planned_kickoff')],expected_revision='fixed')==2


def test_complete_synthetic_trace_still_cannot_admit_history_or_PASS_D():
    target,rows=trace();before=deepcopy(rows)
    result=d.trace_requirements(target,rows,expected_prior_identities=['synthetic:prior'])
    assert result['status']=='TRACE_FIELDS_COMPLETE_NOT_ADMISSION'
    assert not result['D_PASS'] and not result['history_admission'] and rows==before


@pytest.mark.parametrize('key',['raw_sha256','metadata_sha256','request_sha256','actual_kickoff',
    'result_available','acquisition','end_time'])
def test_missing_trace_component_keeps_HOLD(key):
    target,rows=trace();rows[0].pop(key)
    assert d.trace_requirements(target,rows,expected_prior_identities=['synthetic:prior'])['status']=='HOLD'


def test_history_universe_unknown_is_not_legitimate_cold_start():
    target,_=trace()
    assert d.trace_requirements(target,[],expected_prior_identities=None)['status']=='HOLD'
    assert d.trace_requirements(target,[],expected_prior_identities=[])['status']=='TRACE_FIELDS_COMPLETE_NOT_ADMISSION'


def test_missing_cutoff_and_trace_are_reported_as_unknown():
    target,_=trace();target['cutoff']=None
    r=d.trace_requirements(target,None,expected_prior_identities=None)
    assert {'UNKNOWN_COMPLETE_HISTORY_UNIVERSE','NO_ACTUAL_PREDICTION_CUTOFF','NO_PRIOR_RESULT_TRACE'}<=set(r['missing'])


@pytest.mark.parametrize('mode',['target','duplicate','revision','clock'])
def test_history_identity_revision_and_clock_contradictions_STOP(mode):
    target,rows=trace()
    if mode=='target':rows[0]['identity']=target['identity']
    if mode=='duplicate':rows*=2
    if mode=='revision':rows[0]['revision']='changed'
    if mode=='clock':rows[0]['end_time']='2026-01-01T08:00:00+00:00'
    with pytest.raises(d.DiscoveryStop):d.trace_requirements(target,rows,expected_prior_identities=['synthetic:prior'])


def test_missing_or_extra_history_members_not_silently_dropped():
    target,rows=trace()
    assert 'INCOMPLETE_OR_EXTRA_HISTORY' in d.trace_requirements(target,rows,expected_prior_identities=[])['missing']


def test_claim_role_mismatch_in_trace_is_not_reinterpreted():
    target,rows=trace();rows[0]['result_available']=claim('planned_kickoff')
    assert d.trace_requirements(target,rows,expected_prior_identities=['synthetic:prior'])['status']=='HOLD'


def fixtures():
    return [dict(identity='synthetic:'+str(i),ordinal=i,notation_difference=i<8,
        match_page_ID_known=i<14,PK=i%2==0) for i in range(30)]


def test_sample_quota_is_stable_bounded_and_excludes_old_quarantines():
    source=fixtures();blocked={'synthetic:0','synthetic:1'}
    picked=d.select_samples(source,blocked_identities=blocked)
    assert len(picked)==10 and len({r['identity'] for r in picked})==10
    assert not set(r['identity'] for r in picked)&blocked
    assert picked==d.select_samples(list(reversed(source)),blocked_identities=blocked)
    assert all(r['investigation_only'] and not r['evaluation_registration'] and not r['actual_schedule_unchanged_proven'] for r in picked)


@pytest.mark.parametrize('maximum',[11,-1,'10',True])
def test_sample_limit_cannot_be_extended(maximum):
    with pytest.raises(d.DiscoveryStop):d.select_samples(fixtures(),blocked_identities=set(),maximum=maximum)


def test_duplicate_fixture_universe_rejected():
    source=fixtures()
    with pytest.raises(d.DiscoveryStop,match='DUPLICATE_FIXTURE'):d.select_samples(source+source[:1],blocked_identities=set())


def test_discovery_code_has_no_file_network_model_permit_or_worker_entrypoint():
    tree=ast.parse(FILE.read_text('utf8'))
    imported=[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    imported += [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert set(imported)<={'datetime','hashlib','html.parser','re','urllib.parse'}
    calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
    assert not any(n in {'open','exec','eval'} or n.endswith(('.fit','.predict','.predict_proba','.write_bytes','.write_text')) or n.startswith(('socket','subprocess','requests')) for n in calls)
