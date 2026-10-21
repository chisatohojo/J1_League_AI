"""Synthetic exact manager-dismissal witness contract; no individual source evidence in Git."""
from copy import deepcopy
import ast,hashlib,importlib.util,json,os,re,socket,subprocess
from pathlib import Path
import pytest
from test_nn_reviewed_coach_contract import case as coach_case,review as v3,old as v2,oldrule as interpreter,packet,normalize,legacy
from test_nn_reviewed_gk_contract import review as v4

path=os.environ.get('J1AI_MANAGER_REVIEW_IMPLEMENTATION')
if not path:pytest.skip('Set J1AI_MANAGER_REVIEW_IMPLEMENTATION to sealed v5 adapter',allow_module_level=True)
source=Path(path)
assert hashlib.sha256(source.read_bytes()).hexdigest()=='6d8aede159213b3ff9ae1d7d6e41794b6b3c0f66c0793a6fdbc3796fa9d4b354'
spec=importlib.util.spec_from_file_location('manager_review_local',source);review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
coach=json.loads(Path(os.environ['J1AI_COACH_REVIEW_RULE']).read_bytes())
gk=json.loads(Path(os.environ['J1AI_GK_REVIEW_RULE']).read_bytes())

@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No network, operational process or side-effect entry point')
    monkeypatch.setattr(socket,'create_connection',forbidden);monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'getaddrinfo',forbidden);monkeypatch.setattr(subprocess,'Popen',forbidden)

def case(role='\u76e3\u7763',minute='77',code='S6',expression='\u9000\u5834'):
    c=coach_case();c['row'].update(home_score_90=2,away_score_90=2,pk_played=True,complete_expected_header=c['header'],
        source_CSV_sha256='synthetic-csv',source_row_sha256='synthetic-row',listing_raw_sha256='synthetic-listing')
    f={'minute':minute,'event_expression':expression,'event_code':code,'club_verbatim':'SyntheticClub',
       'person_verbatim':'Synthetic\u3000Staff','role_verbatim':'\uff08'+role+'\uff09'}
    text=minute+"' "+f['event_expression']+'('+code+') '+f['club_verbatim']+'  '+f['person_verbatim']+' '+f['role_verbatim']
    paragraph='<p>'+text+'</p>';raw=('<html><!-- A10 End --><!-- A11 Start --><div><h4>\u5099\u8003</h4>'+paragraph+
        '</div><!-- A11 End --><!-- A12 Start --></html>').encode('utf8')
    c['raw'],c['meta'],c['request'],c['pins']=packet(raw,c['row'])
    c['base'].update(remarks=[normalize(text)],remarks_structure='A11_BLOCK')
    c['base']['parsed'].update(home_score_90=2,away_score_90=2,home_pk_score=14,away_pk_score=13,extra_time_played=False)
    b=re.search(rb'<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->',raw,re.S)
    c['rule'].update(version=review.VERSION,decision='ACCEPT_EXACT_MANAGER_DISMISSAL_WITNESS_ONLY',fixture_scope=deepcopy(c['row']),
        packet={**deepcopy(c['pins']),'request_started_at_utc':json.loads(c['meta'])['request_started_at_utc']},
        strict_parsed_result=deepcopy(c['base']['parsed']),normalized_full_remark=c['base']['remarks'][0],
        block_byte_start=b.start(),block_byte_end=b.end(),block_sha256=review.sha(b.group()),block_html_verbatim=b.group().decode(),
        a10_end_byte_start=raw.find(b'<!-- A10 End -->'),a12_relative_byte_start=raw[b.end():].find(b'<!-- A12 Start -->'),
        paragraph_html_verbatim=paragraph,paragraph_text_verbatim=text,disciplinary_fields=f)
    c['rule_sha']=review.sha(review.encoded(c['rule']));return c

def run(c,coach_rule=coach,interpreter_rule=interpreter,gk_rule=gk):
    return review.analyze_packet(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['pins'],c['rule'],c['rule_sha'],
        v4,gk_rule,v3,coach_rule,v2,interpreter_rule,object(),lambda *args:deepcopy(c['base']),legacy.remarks_classification)

def test_positive_exact_original_manager_dismissal_and_pk_separation():
    c=case();result=run(c);assert result['status']=='PASS' and result['rule_applied']=='REVIEWED_EXACT_MANAGER_DISMISSAL'
    assert result['strict_analysis']['parsed']==c['base']['parsed']
    assert result['strict_analysis']['parsed']['home_score_90']==2 and result['strict_analysis']['parsed']['home_pk_score']==14

@pytest.mark.parametrize('field',['identity','data_site_match_id','url','series','source_date','source_reported_kickoff','home_team_id','away_team_id',
    'home_score_90','away_score_90','pk_played','extra_time_played','source_CSV_sha256','source_row_sha256','listing_raw_sha256','complete_expected_header','header'])
def test_another_fixture_competition_source_datetime_team_or_score_cannot_use_rule(field):
    c=case()
    if field=='header':c['header']='different competition season round'
    else:
        value=c['row'][field];c['row'][field]=not value if isinstance(value,bool) else value+1 if isinstance(value,int) else value+'changed'
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('role',['\u9078\u624b','\u901a\u8a33','\u30b3\u30fc\u30c1','GK\u30b3\u30fc\u30c1','\u76e3\u7763\u88dc\u4f50'])
def test_positive_role_literal_is_not_normalized_or_generalized(role):
    c=case(role=role)
    with pytest.raises(ValueError,match='MANAGER_POSITIVE_ROLE_AND_DISMISSAL_FORM'):
        review.reviewed_manager_match(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['base'],c['rule'],c['rule_sha'])
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('part',['raw','meta','request','rule'])
def test_raw_metadata_request_or_rule_sha_mismatch(part):
    c=case()
    if part=='rule':c['rule']['decision']='generic GK coach permission'
    else:c[part]+=b' '
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('change',['spacing','role_width','html','person','paragraph','block','timing_text'])
def test_rehashed_observation_does_not_replace_reviewed_full_original(change):
    c=case()
    if change=='spacing':c['raw']=c['raw'].replace(b"77' ",b"77'  ")
    if change=='role_width':c['raw']=c['raw'].replace('\uff08\u76e3\u7763\uff09'.encode(),' (\u76e3\u7763)'.encode())
    if change=='html':c['raw']=c['raw'].replace(b'<p>',b'<p class="changed">')
    if change=='person':c['raw']=c['raw'].replace(b'Synthetic',b'Changed')
    if change=='paragraph':c['raw']=c['raw'].replace(b'</p>',b'</p><p>unknown</p>')
    if change=='block':c['raw']+=b'<!-- A11 Start --><p>unknown</p><!-- A11 End -->'
    if change=='timing_text':c['raw']=c['raw'].replace(b'</p>',' \u4e2d\u65ad</p>'.encode())
    c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row']);assert run(c)['status']=='HOLD'

def test_same_nfkc_text_is_insufficient():
    c=case();text=c['rule']['paragraph_text_verbatim'];assert normalize(text)==normalize(text.replace('\uff08\u76e3\u7763\uff09','(\u76e3\u7763)'))
    c['raw']=c['raw'].replace('\uff08\u76e3\u7763\uff09'.encode(),' (\u76e3\u7763)'.encode());c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row'])
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('note',['\u4e2d\u65ad','\u518d\u958b','\u5ef6\u671f','\u6253\u5207\u308a','unknown non-time annotation'])
def test_mixed_note_never_partially_accepted(note):
    c=case();c['base']['remarks'].append(note);assert run(c)['status']=='HOLD'
    c['base']['timing_notes']=[note];assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('field',['identity','competition_header','official_date','official_kickoff','parsed','remarks_structure','status'])
def test_strict_identity_time_result_or_hold_cannot_be_overridden(field):
    c=case()
    if field=='parsed':c['base']['parsed']['away_pk_score']=0
    else:c['base'][field]='changed'
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('field',['block_byte_start','block_byte_end','block_sha256','block_html_verbatim','paragraph_html_verbatim','paragraph_text_verbatim',
    'a10_end_byte_start','a12_relative_byte_start'])
def test_full_reviewed_structure_is_required(field):
    c=case();v=c['rule'][field];c['rule'][field]=v+1 if isinstance(v,int) else v+'changed';c['rule_sha']=review.sha(review.encoded(c['rule']))
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('which',['coach','interpreter'])
def test_existing_review_rules_must_remain_sealed(which):
    c=case();r=deepcopy(coach if which=='coach' else interpreter);r['fixture_scope']['identity']='other'
    assert run(c,coach_rule=r if which=='coach' else coach,interpreter_rule=r if which=='interpreter' else interpreter)['status']=='HOLD'

def test_boolean_type_cannot_be_substituted_by_equal_integer():
    c=case();c['row']['pk_played']=1;assert run(c)['status']=='HOLD'

def test_original_acquisition_utc_not_backdated():
    c=case();c['rule']['packet']['request_started_at_utc']='2026-01-01T00:00:00+00:00';c['rule_sha']=review.sha(review.encoded(c['rule']))
    assert run(c)['status']=='HOLD'

def test_previously_accepted_manager_warning_retains_all_semantic_fields():
    c=case(expression='\u8b66\u544a',code='C3');result=run(c)
    prior=v4.analyze_packet(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['pins'],gk,review.GK_RULE_SHA,v3,coach,v2,interpreter,
        object(),lambda *args:deepcopy(c['base']),legacy.remarks_classification)
    assert result['status']=='PASS' and result['rule_applied'] is None
    assert {k:v for k,v in result.items() if k!='version'}=={k:v for k,v in prior.items() if k!='version'}

def test_no_general_classifier_transport_model_or_write_entry_point():
    text=source.read_text(encoding='utf8');tree=ast.parse(text)
    assert {a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}=={'hashlib','html','json','re'}
    assert 'staff-warning-shadow' not in text and 'classify_structure' not in text
    forbidden={'fit','fit_transform','predict','predict_proba','open','write','connect','request','execute','worker'}
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and (isinstance(n.func,ast.Attribute) and n.func.attr in forbidden or isinstance(n.func,ast.Name) and n.func.id in forbidden)]


def test_old_gk_rule_cannot_be_changed():
    c=case();r=deepcopy(gk);r['fixture_scope']['identity']='another'
    assert run(c,gk_rule=r)['status']=='HOLD'


def test_manager_warning_is_not_accepted_by_new_dismissal_review():
    c=case(expression='\u8b66\u544a',code='C3')
    with pytest.raises(ValueError,match='MANAGER_POSITIVE_ROLE_AND_DISMISSAL_FORM'):
        review.reviewed_manager_match(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['base'],c['rule'],c['rule_sha'])


@pytest.mark.parametrize('field,value',[('minute','78'),('event_code','S1'),('event_expression','unknown')])
def test_other_minute_code_or_dismissal_form_cannot_be_generalized(field,value):
    c=case();c['rule']['disciplinary_fields'][field]=value;c['rule_sha']=review.sha(review.encoded(c['rule']))
    assert run(c)['status']=='HOLD'
