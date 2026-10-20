"""Synthetic offline v3 review cases; no saved individual histories in Git."""
from copy import deepcopy
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess

import pytest
from test_nn_reviewed_remark_contract import case as interpreter_case, packet, normalize, review as old
from test_nn_timing_bounded_batches import batch as legacy

path=os.environ.get('J1AI_COACH_REVIEW_IMPLEMENTATION')
if not path:
    pytest.skip('Set J1AI_COACH_REVIEW_IMPLEMENTATION to the sealed offline v3 adapter',allow_module_level=True)
source=Path(path)
assert hashlib.sha256(source.read_bytes()).hexdigest()=='0cc5cb1a382090a49e905418ba918e9063ad723eade091e7ddc459e82c28a425'
spec=importlib.util.spec_from_file_location('coach_review_local',source)
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
oldrule=json.loads(Path(os.environ['J1AI_REMARK_REVIEW_RULE']).read_bytes())

@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('No network, process, or runtime write in offline review')
    monkeypatch.setattr(socket,'create_connection',forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'getaddrinfo',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    monkeypatch.setattr(Path,'write_text',forbidden)
    monkeypatch.setattr(Path,'write_bytes',forbidden)

def case(role='\u30b3\u30fc\u30c1',minute="90'+6",code='C3'):
    c=interpreter_case();f={'minute':minute,'warning_expression':'\u8b66\u544a','warning_code':code,
        'club_verbatim':'SyntheticClub','person_verbatim':'Synthetic\u3000Staff','role_verbatim':'\uff08'+role+'\uff09'}
    text=minute+' '+f['warning_expression']+'('+code+') '+f['club_verbatim']+'  '+f['person_verbatim']+' '+f['role_verbatim']
    paragraph='<p>'+text+'</p>'
    c['raw']=('<html><!-- A10 End --><!-- A11 Start --><div><h4>\u5099\u8003</h4>'+paragraph+
              '</div><!-- A11 End --><!-- A12 Start --></html>').encode('utf8')
    c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row'])
    b=re.search(rb'<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->',c['raw'],re.S)
    c['base'].update(remarks=[normalize(text)],remarks_structure='A11_BLOCK')
    c['rule'].update(version=review.VERSION,decision='ACCEPT_EXACT_COACH_WITNESS_ONLY',packet=deepcopy(c['pins']),
        normalized_full_remark=c['base']['remarks'][0],block_byte_start=b.start(),block_byte_end=b.end(),
        block_sha256=review.sha(b.group()),block_html_verbatim=b.group().decode(),a10_end_byte_start=c['raw'].find(b'<!-- A10 End -->'),
        a12_relative_byte_start=c['raw'][b.end():].find(b'<!-- A12 Start -->'),paragraph_html_verbatim=paragraph,
        paragraph_text_verbatim=text,disciplinary_fields=f)
    c['rule_sha']=review.sha(review.encoded(c['rule']));return c

def run(c,previous_rule=None):
    return review.analyze_packet(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['pins'],c['rule'],c['rule_sha'],
        old,oldrule if previous_rule is None else previous_rule,object(),lambda *args:deepcopy(c['base']),legacy.remarks_classification)

def test_exact_coach_witness_positive_syntax():
    c=case();assert legacy.remarks_classification(c['base'])=='UNKNOWN_FORMAT'
    result=run(c);assert result['status']=='PASS' and result['rule_applied']=='REVIEWED_EXACT_COACH_WARNING'
    assert result['strict_analysis']==c['base']

@pytest.mark.parametrize('field',['identity','data_site_match_id','url','series','source_date','source_reported_kickoff',
    'home_team_id','away_team_id','home_score_90','away_score_90','pk_played','extra_time_played','header'])
def test_same_warning_elsewhere_never_inherits_permission(field):
    c=case()
    if field=='header':c['header']='other season and round'
    else:
        value=c['row'][field];c['row'][field]=not value if isinstance(value,bool) else value+1 if isinstance(value,int) else value+'changed'
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('role',['\u76e3\u7763','\u901a\u8a33','\u533b\u5e2b','\u30b3\u30fc\u30c1\u88dc\u4f50'])
def test_coach_positive_rule_does_not_conflate_roles(role):
    c=case(role=role)
    with pytest.raises(ValueError,match='COACH_POSITIVE_ROLE_AND_FORM'):
        review.coach_match(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['base'],c['rule'],c['rule_sha'])
    if role!='\u76e3\u7763':assert run(c)['status']=='HOLD'

def test_legacy_head_coach_permission_remains_v2_only():
    c=case(role='\u76e3\u7763');result=run(c)
    prior=old.analyze_packet(c['raw'],c['meta'],c['request'],c['row'],c['header'],c['pins'],oldrule,review.OLD_RULE_SHA,
        object(),lambda *args:deepcopy(c['base']),legacy.remarks_classification)
    assert result['status']=='PASS' and result['rule_applied'] is None
    assert {k:v for k,v in result.items() if k!='version'}=={k:v for k,v in prior.items() if k!='version'}

@pytest.mark.parametrize('part',['raw','meta','request','rule'])
def test_witness_or_rule_sha_mismatch(part):
    c=case()
    if part=='rule':c['rule']['decision']='general coach permission'
    else:c[part]+=b' '
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('change',['spacing','width','text','html','extra_paragraph','extra_block','unknown_note','timing_note'])
def test_rehashed_observation_cannot_replace_reviewed_original(change):
    c=case()
    if change=='spacing':c['raw']=c['raw'].replace(b"90'+6 ",b"90'+6  ")
    if change=='width':c['raw']=c['raw'].replace('\u3000'.encode(),b' ')
    if change=='text':c['raw']=c['raw'].replace(b'SyntheticClub',b'OtherClub')
    if change=='html':c['raw']=c['raw'].replace(b'<p>',b'<p class="changed">')
    if change=='extra_paragraph':c['raw']=c['raw'].replace(b'</p>',b'</p><p>unknown</p>')
    if change=='extra_block':c['raw']+=b'<!-- A11 Start --><p>unknown</p><!-- A11 End -->'
    if change in {'unknown_note','timing_note'}:c['raw']=c['raw'].replace(b'</p>',b' unknown annotation</p>')
    c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row'])
    assert run(c)['status']=='HOLD'

def test_same_normalized_string_still_requires_original_bytes():
    c=case();text=c['rule']['paragraph_text_verbatim'];assert normalize(text)==normalize(text.replace('\u3000',' '))
    c['raw']=c['raw'].replace('\u3000'.encode(),b' ')
    c['raw'],c['meta'],c['request'],c['pins']=packet(c['raw'],c['row'])
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('note',['\u4e2d\u65ad','\u518d\u958b','\u5ef6\u671f','unknown non-time paragraph'])
def test_mixed_notes_never_partially_accepted(note):
    c=case();c['base']['remarks'].append(note)
    assert run(c)['status']=='HOLD'
    c['base']['timing_notes']=[note];assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('field',['competition_header','official_date','official_kickoff','identity','parsed','remarks_structure'])
def test_strict_output_cannot_drift(field):
    c=case()
    if field=='parsed':c['base']['parsed']['home_score_90']=9
    else:c['base'][field]='changed'
    assert run(c)['status']=='HOLD'

def test_no_fallback_after_strict_hold():
    c=case();c['base']['status']='HOLD';assert run(c)['status']=='HOLD'

def test_no_fallback_from_generic_warning_text():
    c=case();c['base']['remarks']=['warning without timing keywords'];assert run(c)['status']=='HOLD'

def test_original_interpreter_rule_cannot_be_replaced():
    c=case();changed=deepcopy(oldrule);changed['fixture_scope']['identity']=c['row']['identity']
    assert run(c,changed)['status']=='HOLD'
    assert review.OLD_RULE_SHA==old.sha(old.encoded(oldrule))

@pytest.mark.parametrize('field',['block_byte_start','block_byte_end','block_sha256','block_html_verbatim','paragraph_html_verbatim','paragraph_text_verbatim','a10_end_byte_start','a12_relative_byte_start'])
def test_review_structure_required_even_for_internally_sealed_rule(field):
    c=case();value=c['rule'][field];c['rule'][field]=value+1 if isinstance(value,int) else value+'changed'
    c['rule_sha']=review.sha(review.encoded(c['rule']))
    assert run(c)['status']=='HOLD'

@pytest.mark.parametrize('minute,code',[("90'+5",'C3'),("90'+6",'C2')])
def test_different_explicit_warning_form_requires_new_review(minute,code):
    assert run(case(minute=minute,code=code))['status']=='HOLD'

def plan():
    rows=[{'identity':'synthetic_ordinary:'+str(i),'data_site_match_id':str(900000+i),
           'url':'https://data.j-league.or.jp/SFMS02/?match_card_id='+str(900000+i),
           'complete_expected_header':'synthetic full season and round','listing_raw_sha256':'synthetic'} for i in range(245)]
    return {'network_enabled':False,'permit_created':False,'execution_authorized':False,'rows':rows,
            'previous_43_URLs':['synthetic-prior:'+str(i) for i in range(43)],
            'batches':[{'rows':rows[i:i+12]} for i in range(0,245,12)]}

def test_plan_preserves_distinct_source_namespace_and_20x12_plus5():
    assert review.validate_plan(plan())['remaining']==245

@pytest.mark.parametrize('change',['network','permit','authorization','duplicate','reaccess','count','batch','url_id','order'])
def test_plan_never_authorizes_execution_or_changes_fixed_set(change):
    p=plan()
    if change=='network':p['network_enabled']=True
    if change=='permit':p['permit_created']=True
    if change=='authorization':p['execution_authorized']=True
    if change=='duplicate':p['rows'][1]=p['rows'][0]
    if change=='reaccess':p['previous_43_URLs'][0]=p['rows'][0]['url']
    if change=='count':p['rows'].pop()
    if change=='batch':p['batches'].pop()
    if change=='url_id':p['rows'][0]['data_site_match_id']='different'
    if change=='order':p['batches'][0]['rows'].reverse()
    with pytest.raises(ValueError):review.validate_plan(p)

def test_adapter_has_no_transport_model_or_write_entry_points():
    tree=ast.parse(source.read_text(encoding='utf8'))
    imports={a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
    assert imports=={'hashlib','html','json','re'}
    forbidden={'fit','fit_transform','predict','predict_proba','load','loads_model','execute','worker','open','write','write_bytes','write_text','connect','urlopen'}
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and
                (isinstance(n.func,ast.Attribute) and n.func.attr in forbidden or isinstance(n.func,ast.Name) and n.func.id in forbidden)]
