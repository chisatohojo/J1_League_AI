"""Synthetic shadow grammar safety. Candidate labels never admit history."""
import ast,hashlib,importlib.util,os,socket,subprocess,unicodedata
from pathlib import Path
import pytest

path=os.environ.get('J1AI_STAFF_WARNING_SHADOW')
if not path:pytest.skip('Set J1AI_STAFF_WARNING_SHADOW to isolated design candidate',allow_module_level=True)
source=Path(path)
assert hashlib.sha256(source.read_bytes()).hexdigest()=='1c6ef11fe9e94cb1715c7444104f8e98924dccf25b0fcb9c0cd1952e31daaec8'
spec=importlib.util.spec_from_file_location('staff_shadow_local',source);shadow=importlib.util.module_from_spec(spec);spec.loader.exec_module(shadow)

@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Shadow cannot connect, fit, infer or invoke operations')
    monkeypatch.setattr(socket,'create_connection',forbidden);monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'getaddrinfo',forbidden);monkeypatch.setattr(subprocess,'Popen',forbidden)

def paragraph(role='\u76e3\u7763',person='Synthetic\u3000Staff',club='SyntheticClub',minute="86'",code='C3'):
    return minute+' \u8b66\u544a('+code+') '+club+'  '+person+' \uff08'+role+'\uff09'

def raw(text=None):
    if text is None:text=paragraph()
    return ('<html><!-- A11\u3000\u5099\u8003\u30a8\u30ea\u30a2\u3000Start -->\r\n'
        '<div class="two-column-table-b"><div class="two-column-table-box" >'
        '<h4 class="two-column-table-st-base">\u5099\u8003</h4><div class="two-column-table-base"><p>'+text+
        '</p></div></div></div><!-- A11\u3000\u5099\u8003\u30a8\u30ea\u30a2\u3000End --></html>').encode('utf8')

def run(value,clubs=('SyntheticClub','OtherClub')):
    result=shadow.classify(value,clubs)
    assert result['history_admission'] is result['source_witness_verified'] is result['timing_evidence_verified'] is result['acquisition_path_connected'] is False
    return result

@pytest.mark.parametrize('role',['\u76e3\u7763','\u901a\u8a33','\u30b3\u30fc\u30c1','\uff27\uff2b\u30b3\u30fc\u30c1'])
def test_known_four_literal_roles_are_distinct_structural_candidates_only(role):
    result=run(raw(paragraph(role=role)))
    assert result['status']=='STRUCTURAL_CANDIDATE_ONLY' and result['role_verbatim']==role
    assert result['person_identity_verified'] is False and result['warning_code_semantics_inferred'] is False

@pytest.mark.parametrize('role',['\u901a\u8a33\u88dc\u4f50','\u533b\u5e2b','\u30d5\u30a3\u30b8\u30ab\u30eb\u30b3\u30fc\u30c1','GK\u30b3\u30fc\u30c1','\uff27\uff2b\u30b3\u30fc\u30c1\u88dc\u4f50',''])
def test_unregistered_role_or_representation_requires_review(role):
    assert run(raw(paragraph(role=role)))['status']=='HOLD_UNCLASSIFIED'

@pytest.mark.parametrize('note',['\u4e2d\u65ad','\u518d\u958b','\u5ef6\u671f','\u4e2d\u6b62','\u958b\u59cb\u6642\u523b\u5909\u66f4','\u53d6\u6d88','\u8a02\u6b63',
    '15:00','2026-03-21','unknown additional sentence'])
def test_warning_with_time_correction_or_unknown_annotation_never_partially_accepted(note):
    assert run(raw(paragraph()+' '+note))['status']=='HOLD_UNCLASSIFIED'
    assert run(raw(paragraph()).replace(b'</p>',('</p><p>'+note+'</p>').encode()))['status']=='HOLD_UNCLASSIFIED'

@pytest.mark.parametrize('change',['extra_paragraph','extra_block','nested_span','paragraph_attribute','class_change','extra_attribute','heading_change','marker_change','unclosed_marker','entity'])
def test_unreviewed_html_and_multiple_nodes_hold(change):
    value=raw()
    if change=='extra_paragraph':value=value.replace(b'</p>',b'</p><p>another</p>')
    if change=='extra_block':value+=raw()
    if change=='nested_span':value=value.replace(b'SyntheticClub',b'<span>SyntheticClub</span>')
    if change=='paragraph_attribute':value=value.replace(b'<p>',b'<p class="note">')
    if change=='class_change':value=value.replace(b'two-column-table-box',b'changed-class')
    if change=='extra_attribute':value=value.replace(b'<p>',b'<p hidden>')
    if change=='heading_change':value=value.replace('\u5099\u8003</h4>'.encode(),'\u5099\u8003\u8a73\u7d30</h4>'.encode())
    if change=='marker_change':value=value.replace('\u5099\u8003\u30a8\u30ea\u30a2'.encode(),b'changed-area')
    if change=='unclosed_marker':value=value.replace(b'End -->',b'End broken')
    if change=='entity':value=value.replace(b'SyntheticClub',b'&#83;yntheticClub')
    assert run(value)['status']=='HOLD_UNCLASSIFIED'

@pytest.mark.parametrize('person',['',' ','\u3000','Synthetic Staff','Synthetic\u00a0Staff','Synthetic\u200bStaff','Synthetic\u3000\u3000Staff','\u4e2d\u65ad','name123'])
def test_staff_subject_missing_ambiguous_or_unreviewed_hold(person):
    assert run(raw(paragraph(person=person)))['status']=='HOLD_UNCLASSIFIED'

def test_mononym_and_name_with_known_ideographic_separator_remain_unverified():
    for person in ('Synthetic','Synthetic\u3000Staff'):
        assert run(raw(paragraph(person=person)))['status']=='STRUCTURAL_CANDIDATE_ONLY'

@pytest.mark.parametrize('club',['','UnknownClub','Synthetic Club'])
def test_club_missing_or_outside_supplied_exact_context_hold(club):
    assert run(raw(paragraph(club=club)))['status']=='HOLD_UNCLASSIFIED'

def test_no_supplied_club_context_does_not_invent_one():
    assert run(raw(),())['status']=='HOLD_UNCLASSIFIED'

@pytest.mark.parametrize('text',["86' \u8b66\u544a(C3) SyntheticClub  Synthetic\u3000Staff",'\u8b66\u544a \u30b3\u30fc\u30c1',
    '\u30ea\u30fc\u30b0\u4e2d\u65ad\u5f8c\u306e\u518d\u958b\u8a18\u4e8b','arbitrary note without timing words'])
def test_role_missing_or_keyword_only_or_article_does_not_classify(text):
    assert run(raw(text))['status']=='HOLD_UNCLASSIFIED'

@pytest.mark.parametrize('minute',["0'","91'","120'","86'+2","90'+0","90\u2019+2","14:35",'2026-03-21'])
def test_unreviewed_minute_or_calendar_clock_forms_hold(minute):
    assert run(raw(paragraph(minute=minute)))['status']=='HOLD_UNCLASSIFIED'

@pytest.mark.parametrize('minute',["1'","45'+2","90'+6"])
def test_known_minute_grammar_is_not_calendar_or_acquisition_time(minute):
    result=run(raw(paragraph(minute=minute)));assert result['status']=='STRUCTURAL_CANDIDATE_ONLY'
    assert 'acquired_at' not in result and 'result_effective_at' not in result

@pytest.mark.parametrize('code',['C1','C2','C4','C6','C7','c3','C\uff13',''])
def test_unobserved_code_spellings_are_not_interpreted(code):
    assert run(raw(paragraph(code=code)))['status']=='HOLD_UNCLASSIFIED'

@pytest.mark.parametrize('change',['nbsp','role_width','parenthesis_width','smart_quote','newline'])
def test_unicode_and_spacing_changes_do_not_get_normalization_fallback(change):
    text=paragraph(role='\uff27\uff2b\u30b3\u30fc\u30c1');changed=text
    if change=='nbsp':changed=text.replace("86' ","86'\u00a0")
    if change=='role_width':changed=text.replace('\uff27\uff2b','GK')
    if change=='parenthesis_width':changed=text.replace('\uff08','(').replace('\uff09',')')
    if change=='smart_quote':changed=text.replace("'",'\u2019')
    if change=='newline':changed=text.replace('  ','\n')
    if change in {'nbsp','role_width','parenthesis_width'}:assert unicodedata.normalize('NFKC',text)==unicodedata.normalize('NFKC',changed)
    assert run(raw(changed))['status']=='HOLD_UNCLASSIFIED'

def test_absent_a11_is_unclassified_and_cannot_admit_empty_history():
    assert run(b'<html>No remarks block</html>')['status']=='NOT_CLASSIFIED'

def test_undecodable_original_holds():
    assert run(raw().replace(b'SyntheticClub',b'\xff'))['status']=='HOLD_UNCLASSIFIED'

def test_no_acquisition_witness_bypass_or_model_entry_point():
    tree=ast.parse(source.read_text(encoding='utf8'))
    assert {a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}=={'re','unicodedata'}
    forbidden={'fit','predict','analyze_packet','open','write','request','execute','worker','connect'}
    assert not [n for n in ast.walk(tree) if isinstance(n,ast.Call) and (isinstance(n.func,ast.Attribute) and n.func.attr in forbidden or isinstance(n.func,ast.Name) and n.func.id in forbidden)]
