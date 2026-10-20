"""Synthetic exact-witness remark review; no individual source data or GET."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import unicodedata

import pytest
from test_nn_timing_bounded_batches import batch as legacy

path=os.environ.get('J1AI_REMARK_REVIEW_IMPLEMENTATION')
if not path:
    pytest.skip('Set J1AI_REMARK_REVIEW_IMPLEMENTATION to the sealed offline adapter',allow_module_level=True)
source=Path(path)
if hashlib.sha256(source.read_bytes()).hexdigest()!='7879e2825f06533a63aa9bd59de0b3aebb4cf092b8aae5baab1ee5e1a74f2b49':
    raise ValueError('Offline remark adapter SHA mismatch')
spec=importlib.util.spec_from_file_location('reviewed_remark_local',source)
review=importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Offline contract test cannot connect')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)


def normalize(text):return re.sub(r'\s+','',unicodedata.normalize('NFKC',text))


def packet(raw,row):
    request=review.encoded({'url':row['url'],'request_started_at_utc':'2026-10-20T10:00:00+00:00'})
    meta=review.encoded({'requested_url':row['url'],'final_url':row['url'],'status':200,'success':True,'complete_body':True,
                        'sha256':review.sha(raw),'bytes':len(raw),'request_sha256':review.sha(request),
                        'request_started_at_utc':'2026-10-20T10:00:00+00:00','response_completed_at_utc':'2026-10-20T10:00:01+00:00'})
    pins={'url':row['url'],'raw_sha256':review.sha(raw),'metadata_sha256':review.sha(meta),
          'request_sha256':review.sha(request),'response_completed_at_utc':'2026-10-20T10:00:01+00:00'}
    return raw,meta,request,pins


def case():
    row={'identity':'jleague_data_site_sfms02:9001','data_site_match_id':'9001',
         'url':'https://data.j-league.or.jp/SFMS02/?match_card_id=9001','series':'hyakunen',
         'source_date':'2026-02-22','source_reported_kickoff':'2026-02-22T14:03:00+09:00',
         'home_team_id':'team_1001','away_team_id':'team_1002','home_score_90':1,'away_score_90':2,
         'pk_played':False,'extra_time_played':False}
    fields={'minute':'38','warning_expression':'\u8b66\u544a','warning_code':'C3','club_verbatim':'SyntheticClub',
            'person_verbatim':'Synthetic\u3000Staff','role_verbatim':'\uff08\u901a\u8a33\uff09'}
    text="38' \u8b66\u544a(C3) SyntheticClub  Synthetic\u3000Staff \uff08\u901a\u8a33\uff09"
    paragraph='<p>'+text+'</p>'
    raw=('<html><!-- A10 End --><!-- A11 Start --><div><h4>\u5099\u8003</h4>'+paragraph+
         '</div><!-- A11 End --><!-- A12 Start --></html>').encode('utf8')
    raw,meta,request,pins=packet(raw,row)
    block=re.search(rb'<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->',raw,re.S)
    header='2026 synthetic full competition and round'
    base={'status':review.BASE_PASS,'identity':row['identity'],'competition_header':header,'official_date':row['source_date'],
          'official_kickoff':'14:03','parsed':{'home_score_90':1,'away_score_90':2,'extra_time_played':False},
          'remarks':[normalize(text)],'timing_notes':[]}
    rule={'version':review.VERSION,'decision':'ACCEPT_EXACT_NON_TIMING_STAFF_WARNING','namespace':'jleague_data_site_sfms02',
          'fixture_scope':deepcopy(row),'expected_header':header,'normalized_header':header,'packet':deepcopy(pins),
          'strict_parsed_result':deepcopy(base['parsed']),'normalized_full_remark':base['remarks'][0],
          'block_byte_start':block.start(),'block_byte_end':block.end(),'block_sha256':review.sha(block.group()),
          'remarks_heading':'\u5099\u8003','paragraph_html_verbatim':paragraph,'paragraph_text_verbatim':text,
          'disciplinary_fields':fields}
    return {'raw':raw,'meta':meta,'request':request,'pins':pins,'row':row,'header':header,'base':base,
            'rule':rule,'rule_sha':review.sha(review.encoded(rule))}


def run(c):
    return review.analyze_packet(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['pins'],c['rule'],c['rule_sha'],
                                 object(),lambda *args:deepcopy(c['base']),legacy.remarks_classification)


def test_interpreter_requires_complete_positive_structure_and_reviewed_packet():
    c=case();assert legacy.remarks_classification(c['base'])=='UNKNOWN_FORMAT'
    result=run(c)
    assert result['status']=='PASS' and result['rule_applied']=='REVIEWED_EXACT_INTERPRETER_WARNING'
    assert result['strict_analysis']==c['base']


def test_coach_uses_unchanged_legacy_contract_and_is_not_an_interpreter_rule():
    c=case();c['raw']=c['raw'].replace('\u901a\u8a33'.encode(),'\u76e3\u7763'.encode())
    c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row'])
    c['base']['remarks']=[x.replace('\u901a\u8a33','\u76e3\u7763') for x in c['base']['remarks']]
    result=run(c);assert result['status']=='PASS' and result['rule_applied'] is None


@pytest.mark.parametrize('role',['\u901a\u8a33\u88dc\u4f50','\u30b3\u30fc\u30c1','\u533b\u5e2b'])
def test_unreviewed_roles_do_not_inherit_interpreter_permission(role):
    c=case();c['raw']=c['raw'].replace('\u901a\u8a33'.encode(),role.encode())
    c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row'])
    c['base']['remarks']=[x.replace('\u901a\u8a33',role) for x in c['base']['remarks']]
    assert run(c)['status']=='HOLD'


@pytest.mark.parametrize('change',['identity','data_site_match_id','url','series','source_date','source_reported_kickoff',
                                  'home_team_id','away_team_id','home_score_90','away_score_90','pk_played','extra_time_played','header'])
def test_no_cross_fixture_competition_datetime_team_or_score_application(change):
    c=case()
    if change=='header':c['header']='different season or round'
    else:
        value=c['row'][change]
        c['row'][change]=not value if isinstance(value,bool) else value+1 if isinstance(value,int) else value+'changed'
    assert run(c)['status']=='HOLD'


@pytest.mark.parametrize('signal',['\u4e2d\u65ad','\u518d\u958b','\u5ef6\u671f','unknown temporal note'])
def test_known_warning_mixed_with_unknown_time_note_holds(signal):
    c=case();c['base']['remarks'].append(signal);c['base']['timing_notes']=[signal]
    assert run(c)['status']=='HOLD'


def test_partial_known_non_temporal_mixture_also_holds():
    c=case();c['base']['remarks'].append('unrecognized non-temporal sentence')
    assert run(c)['status']=='HOLD'


@pytest.mark.parametrize('part',['raw','meta','request','rule'])
def test_packet_or_review_tampering_detected(part):
    c=case()
    if part=='rule':c['rule']['decision']='arbitrary broad approval'
    else:c[part]+=b' '
    assert run(c)['status']=='HOLD'


@pytest.mark.parametrize('change',['prefix','suffix','spacing','warning_code','extra_paragraph','heading'])
def test_rehashed_packet_cannot_bypass_exact_approved_witness(change):
    c=case()
    if change=='prefix':c['raw']=c['raw'].replace(b'<p>',b'<p>prefix ')
    if change=='suffix':c['raw']=c['raw'].replace(b'</p>',b' suffix</p>')
    if change=='spacing':c['raw']=c['raw'].replace(b"38' ",b"38'  ")
    if change=='warning_code':c['raw']=c['raw'].replace(b'C3',b'C2')
    if change=='extra_paragraph':c['raw']=c['raw'].replace(b'</p>',b'</p><p>unknown</p>')
    if change=='heading':c['raw']=c['raw'].replace('\u5099\u8003'.encode(),b'unknown heading')
    c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row'])
    assert run(c)['status']=='HOLD'


def test_review_never_overrides_a_strict_parser_hold():
    c=case();c['base']['status']='HOLD';c['base']['hold_reason']='identity mismatch'
    assert run(c)['status']=='HOLD'


def test_strict_parsed_fields_must_stay_identical_even_with_matching_packet():
    c=case();c['base']['parsed']['home_score_90']=9
    assert run(c)['status']=='HOLD'


def test_no_warning_sentence_fallback_on_absence_of_time_words():
    c=case();c['base']['remarks']=['arbitrary warning sentence without timing keywords']
    assert run(c)['status']=='HOLD'


def plan():
    rows=[{'identity':'fixture:'+str(i),'data_site_match_id':str(i),
           'url':'https://data.j-league.or.jp/SFMS02/?match_card_id='+str(i),
           'complete_expected_header':'2026 synthetic','listing_raw_sha256':'a'*64} for i in range(1000,1249)]
    return {'network_enabled':False,'permit_created':False,'execution_authorized':False,'rows':rows,
            'previous_39_URLs':['saved:'+str(i) for i in range(39)],
            'batches':[{'rows':rows[i*12:(i+1)*12]} for i in range(21)]}


def test_next_plan_is_exact249_in_20_full_batches_plus9_without_permission():
    assert review.validate_plan(plan())=={'status':'PLAN_ONLY_NOT_AUTHORIZED','remaining':249,'batches':21,'previous_forbidden':39,'new_GET':0}


@pytest.mark.parametrize('change',['permission','permit','network','duplicate','previous','host','batch'])
def test_plan_cannot_enable_network_or_revisit_saved_pages(change):
    p=plan()
    if change=='permission':p['execution_authorized']=True
    if change=='permit':p['permit_created']=True
    if change=='network':p['network_enabled']=True
    if change=='duplicate':p['rows'][0]=p['rows'][1]
    if change=='previous':p['previous_39_URLs'][0]=p['rows'][0]['url']
    if change=='host':p['rows'][0]['url']='https://evil.test/'
    if change=='batch':p['batches'][-1]['rows']=p['batches'][-1]['rows'][:-1]
    with pytest.raises(ValueError):review.validate_plan(p)
