"""Synthetic evidence only. No model, historical prediction or network API."""
from copy import deepcopy
import ast
import importlib.util
import json
from pathlib import Path

import pytest

FILE=Path(__file__).resolve().parents[1]/'research/nn_v2/phase2_5C/evidence_contract.py'
spec=importlib.util.spec_from_file_location('bcd_contract',FILE)
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


def body(v): return json.dumps(v,sort_keys=True).encode()


def packet():
    # Synthetic identity literal, never an acquisition candidate or GET request.
    url='https://data.j-league.or.jp/SFMS02/?match_card_id=1'
    raw=b'<html>synthetic</html>'
    row=dict(identity='synthetic:fixture',url=url,data_site_match_id='1')
    q=dict(identity=row['identity'],url=url,method='GET',request_started_at_utc='2026-10-22T00:00:00+00:00')
    req=body(q)
    md=dict(requested_url=url,final_url=url,identity=row['identity'],sha256=c.sha(raw),request_sha256=c.sha(req),
        bytes=len(raw),status=200,success=True,complete_body=True,
        request_started_at_utc=q['request_started_at_utc'],response_completed_at_utc='2026-10-22T00:00:01+00:00')
    return raw,md,q,dict(row=row,pins={})


def seal(raw,md,q,expected):
    meta,req=body(md),body(q)
    expected['pins']=dict(raw_sha256=c.sha(raw),metadata_sha256=c.sha(meta),request_sha256=c.sha(req),
        url=expected['row']['url'],response_completed_at_utc=md['response_completed_at_utc'])
    return raw,meta,req,expected


def facts():
    return dict(A_verified=True,identity='synthetic:target',actual_start='UNKNOWN',interruption_chain='UNKNOWN',
        completion_chronology='UNKNOWN',original_announcement='UNKNOWN',change_notice_chain='UNKNOWN',
        notice_acquisition='UNKNOWN',prediction_cutoff=None,history_trace=None,history_complete_verified=False,
        feature_cutoff='2026-10-22T00:00:00+09:00',kickoff='2026-10-22T19:00:00+09:00')


def known_trace():
    f=facts();f.update(prediction_cutoff='2026-10-22T07:00:00+09:00',history_complete_verified=True,
        history_trace=[dict(identity='synthetic:prior',source_revision='sealed-source',verified_packet=True,
            raw_sha256='a'*64,metadata_sha256='b'*64,request_sha256='c'*64,
            actual_acquisition_UTC='2026-10-21T12:00:00+00:00',
            result_effective_policy_at='2026-10-21T00:00:00+09:00')])
    return f


def test_acquisition_is_an_upper_bound_never_first_publication_or_event_end():
    raw,md,q,x=packet();result=c.verify_acquisition(*seal(raw,md,q,x))
    assert result['result_observed_available_by_UTC']==md['response_completed_at_utc']
    assert result['first_result_publication_UTC'] is None and not result['historical_publication_asof_proven']


@pytest.mark.parametrize('which',[0,1,2])
def test_any_packet_byte_tampering_STOP(which):
    raw,md,q,x=packet();args=list(seal(raw,md,q,x));args[which]+=b' '
    with pytest.raises(c.EvidenceStop,match='PACKET_SHA'):c.verify_acquisition(*args)


@pytest.mark.parametrize('kind',['url','identity','raw_hash','request_hash','size','HTTP','incomplete','request_clock','end_clock','snapshot','fetched'])
def test_internally_contradictory_even_resealed_metadata_STOP(kind):
    raw,md,q,x=packet()
    if kind=='url':md['final_url']+='&other=1'
    if kind=='identity':q['identity']='synthetic:other'
    if kind=='raw_hash':md['sha256']='f'*64
    if kind=='request_hash':md['request_sha256']='f'*64
    if kind=='size':md['bytes']+=1
    if kind=='HTTP':md['status']=429
    if kind=='incomplete':md['complete_body']=False
    if kind=='request_clock':md['request_started_at_utc']='2026-10-23T00:00:00+00:00'
    if kind=='end_clock':md['response_completed_at_utc']='2026-10-21T00:00:00+00:00'
    if kind=='snapshot':md['snapshot_saved_at_utc']='2026-10-20T00:00:00+00:00'
    if kind=='fetched':md['fetched_at_utc']='2026-10-20T00:00:00+00:00'
    with pytest.raises(c.EvidenceStop):c.verify_acquisition(*seal(raw,md,q,x))


@pytest.mark.parametrize('suffix',['&x=2','#fragment','&match_card_id=2','%20','/'])
def test_URL_notation_fallback_is_forbidden(suffix):
    raw,md,q,x=packet();url=x['row']['url']+suffix
    x['row']['url']=q['url']=md['requested_url']=md['final_url']=url
    md['request_sha256']=c.sha(body(q))
    with pytest.raises(c.EvidenceStop,match='URL_NAMESPACE_ID'):c.verify_acquisition(*seal(raw,md,q,x))


@pytest.mark.parametrize('value',['2026-10-22T00:00:00','not-a-date',None])
def test_naive_or_unknown_clock_is_not_repaired(value):
    with pytest.raises(c.EvidenceStop):c.stamp(value)


def test_A_PASS_never_implies_B_C_D_or_admission():
    result=c.classify(facts())
    assert result['A']=='PASS' and all(result[k]['status']=='HOLD' for k in ['B','C','D'])
    assert not result['history_admission'] and not result['prediction_authorized']


@pytest.mark.parametrize('field',['actual_start','interruption_chain','completion_chronology'])
def test_one_missing_event_component_keeps_B_HOLD(field):
    f=facts();f.update(actual_start='ESTABLISHED',interruption_chain='ESTABLISHED',completion_chronology='ESTABLISHED')
    f[field]='UNKNOWN';assert c.classify(f)['B']['status']=='HOLD'


@pytest.mark.parametrize('field',['original_announcement','change_notice_chain','notice_acquisition'])
def test_current_schedule_or_notation_difference_cannot_fill_original_or_notice(field):
    f=facts();f.update(original_announcement='ESTABLISHED',change_notice_chain='ESTABLISHED',notice_acquisition='ESTABLISHED')
    f[field]='UNKNOWN';assert c.classify(f)['C']['status']=='HOLD'


def test_all_positive_synthetic_audit_facts_still_cannot_admit_history():
    f=known_trace()
    for key in ['actual_start','interruption_chain','completion_chronology','original_announcement','change_notice_chain','notice_acquisition']:
        f[key]='ESTABLISHED'
    report=c.classify(f)
    assert all(report[k]['status']=='PASS' for k in ['B','C','D']) and not report['history_admission']
    with pytest.raises(c.EvidenceStop,match='ADMISSION_NOT_AUTHORIZED'):c.require_history_admission(report)


def test_later_target_result_is_not_a_prior_feature_dependency():
    f=known_trace();f['history_trace'][0]['identity']=f['identity']
    with pytest.raises(c.EvidenceStop,match='TARGET_OR_DUPLICATE'):c.classify(f)


def test_duplicate_history_result_STOP():
    f=known_trace();f['history_trace']*=2
    with pytest.raises(c.EvidenceStop,match='TARGET_OR_DUPLICATE'):c.classify(f)


@pytest.mark.parametrize('field,value',[('actual_acquisition_UTC','2026-10-22T00:00:00+00:00'),
    ('result_effective_policy_at','2026-10-23T00:00:00+09:00')])
def test_late_acquisition_or_same_day_result_fails_D_without_time_backdating(field,value):
    f=known_trace();f['history_trace'][0][field]=value
    assert c.classify(f)['D']['status']=='HOLD'


def test_previous_day_result_at_exact_midnight_and_actual_morning_acquisition_are_distinct():
    f=known_trace();f['prediction_cutoff']='2026-10-22T09:00:00+09:00'
    f['history_trace'][0].update(result_effective_policy_at='2026-10-22T00:00:00+09:00',
        actual_acquisition_UTC='2026-10-21T23:00:00+00:00')  # 08:00 JST, not 00:00.
    assert c.classify(f)['D']['status']=='PASS'
    assert f['history_trace'][0]['actual_acquisition_UTC']=='2026-10-21T23:00:00+00:00'


@pytest.mark.parametrize('field,value',[('verified_packet',False),('source_revision',''),('raw_sha256','bad')])
def test_unverified_trace_is_STOP_not_an_ordinary_missing_time(field,value):
    f=known_trace();f['history_trace'][0][field]=value
    with pytest.raises(c.EvidenceStop):c.classify(f)


@pytest.mark.parametrize('cutoff',['2026-10-22T19:00:00+09:00','2026-10-22T20:00:00+09:00','2026-10-21T23:59:59+09:00'])
def test_prediction_cutoff_order_is_strict(cutoff):
    f=known_trace();f['prediction_cutoff']=cutoff
    with pytest.raises(c.EvidenceStop,match='CUTOFF_KICKOFF_ORDER'):c.classify(f)


def test_missing_cutoff_or_dependency_trace_is_unknown_not_implicit_empty_history():
    f=known_trace();f['history_trace']=None
    assert c.classify(f)['D']['components']['complete_prior_result_trace']=='UNKNOWN'
    f['prediction_cutoff']=None
    assert c.classify(f)['D']['components']['actual_prediction_cutoff']=='UNKNOWN'


def test_complete_trace_marker_required_even_for_empty_trace():
    f=known_trace();f.update(history_trace=[],history_complete_verified=False)
    assert c.classify(f)['D']['status']=='HOLD'


@pytest.mark.parametrize('field',['identity','official_date','official_kickoff','status'])
def test_semantic_or_identity_drift_is_STOP(field):
    row=dict(identity='synthetic',source_date='2026-10-21',source_reported_kickoff='2026-10-21T19:00:00+09:00',
        home_score_90=1,away_score_90=0,pk_played=False,extra_time_played=False)
    old=dict(identity='synthetic',official_date='2026-10-21',official_kickoff='19:00',
        status='PARSE_VERIFIED_FINAL_RECORD_ONLY',parsed=dict(home_score_90=1,away_score_90=0,extra_time_played=False,home_pk_score=None))
    new=deepcopy(old);new[field]='changed'
    with pytest.raises(c.EvidenceStop):c.unchanged_semantics(new,old,row)


@pytest.mark.parametrize('field,value',[('home_score_90',3),('away_score_90',2),('pk_played',True),('extra_time_played',True)])
def test_PK_ET_or_score_changes_are_not_mixed_into_90_minute_result(field,value):
    row=dict(identity='synthetic',source_date='2026-10-21',source_reported_kickoff='2026-10-21T19:00:00+09:00',
        home_score_90=1,away_score_90=0,pk_played=False,extra_time_played=False)
    report=dict(identity='synthetic',official_date='2026-10-21',official_kickoff='19:00',
        status='PARSE_VERIFIED_FINAL_RECORD_ONLY',parsed=dict(home_score_90=1,away_score_90=0,extra_time_played=False,home_pk_score=None))
    row[field]=value
    with pytest.raises(c.EvidenceStop):c.unchanged_semantics(report,report,row)


def test_saved_20_rounds_never_register_T0_or_guess_missing_IDs():
    rows=[dict(round=str(r),status='scheduled',match_date='2027-01-01',kickoff_time='',match_page_id='',data_site_match_id='')
          for r in range(1,21) for _ in range(10)]
    result=c.schedule_draft(rows,'2026-12-30T15:30:00+00:00')
    assert result['proposed_20_rounds_exist_in_saved_observation'] and result['missing_kickoffs']==200
    assert result['T0'] is result['R_start'] is None and result['enrolled_fixtures']==0


def test_schedule_day_comparison_uses_JST_and_excludes_incomplete_round():
    row=dict(round='1',status='scheduled',match_date='2026-12-31',kickoff_time='19:00',match_page_id='1',data_site_match_id='')
    assert c.schedule_draft([dict(row) for _ in range(10)],'2026-12-30T15:30:00+00:00')['saved_complete_unstarted_rounds']==0
    row['match_date']='2027-01-01'
    assert c.schedule_draft([dict(row) for _ in range(9)],'2026-12-30T15:30:00+00:00')['saved_complete_unstarted_rounds']==0


def test_contract_has_no_network_filesystem_model_metrics_or_registration_entrypoint():
    tree=ast.parse(FILE.read_text(encoding='utf8'))
    modules=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]+[a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
    assert set(modules)<={'datetime','hashlib','json','re','urllib.parse'}
    calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
    assert not any(n.startswith(('open','Path','subprocess','requests','socket')) or n.endswith(('.fit','.predict','.predict_proba','.write_bytes','.write_text')) for n in calls)
