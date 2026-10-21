"""Synthetic exact-witness faults; no saved personal evidence or live worker."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import socket
import pytest

PATH = Path(__file__).parents[1] / 'research/nn_v2/phase2_5B_17/exact_quarantine_review.py'
spec = importlib.util.spec_from_file_location('review_v6', PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError('Network forbidden')
    monkeypatch.setattr(socket.socket, 'connect', deny)
    monkeypatch.setattr(socket, 'getaddrinfo', deny)


def fixture(kind='EXACT_POSTMATCH_COACH_WARNING', changed_paragraphs=None, changed_fields=None):
    fields = [{'display': '試合終了後', 'club': 'Club A', 'person': 'Person A', 'role': '（コーチ）', 'expression': '警告', 'code': 'C3'}]
    if kind == 'EXACT_MINUTE_GK_WARNING':
        fields[0].update(display="45'+2", role='（ＧＫコーチ）')
    if kind == 'EXACT_SUBSTITUTION_PAIR':
        fields = [{'display': '46*', 'club': 'Club A', 'out_number': '1', 'out_person': 'Person A', 'in_number': '2', 'in_person': 'Person B'},
                  {'display': "85'", 'club': 'Club B', 'out_number': '3', 'out_person': 'Person C', 'in_number': '4', 'in_person': 'Person D'}]
    paragraphs = c.positive_paragraphs({'kind': kind, 'positive_fields': fields})
    if changed_fields:
        fields[0].update(changed_fields)
    if changed_paragraphs:
        paragraphs = changed_paragraphs(paragraphs)
    block = '<!-- A11 Start --><div><h4>備考</h4>' + ''.join('<p>' + p + '</p>' for p in paragraphs) + '</div><!-- A11 End -->'
    raw = ('<!-- A10 End -->' + block + '<!-- A12 Start -->').encode('utf8')
    request = {'url': 'https://data.j-league.or.jp/SFMS02/?match_card_id=900001', 'request_started_at_utc': '2026-10-22T00:00:00+00:00'}
    req = c.encoded(request)
    meta = c.encoded({'requested_url': request['url'], 'final_url': request['url'], 'request_started_at_utc': request['request_started_at_utc'],
                      'response_completed_at_utc': '2026-10-22T00:00:01+00:00', 'snapshot_saved_at_utc': '2026-10-22T00:00:02+00:00',
                      'sha256': c.sha(raw), 'request_sha256': c.sha(req)})
    expected = {'row': {'identity': 'jleague_data_site_sfms02:900001', 'url': request['url'], 'data_site_match_id': '900001',
                       'home_team_id': 'synthetic_home', 'away_team_id': 'synthetic_away', 'source_date': '2026-01-01',
                       'source_reported_kickoff': '2026-01-01T14:00:00+09:00', 'home_score_90': 1, 'away_score_90': 0,
                       'series': 'synthetic', 'pk_played': False, 'extra_time_played': False}, 'header': 'Synthetic season competition round',
                'revision': {'source_CSV_SHA256': 'source-pinned', 'source_row_SHA256': 'row-pinned'},
                'pins': {'raw_sha256': c.sha(raw), 'metadata_sha256': c.sha(meta), 'request_sha256': c.sha(req), 'url': request['url']}}
    before = {'version': 'unchanged_v5', 'identity': expected['row']['identity'], 'status': 'HOLD', 'legacy_category': 'UNKNOWN_FORMAT',
              'strict_analysis': {'status': c.BASE_PASS, 'timing_notes': [], 'remarks_structure': 'A11_BLOCK', 'remarks': paragraphs},
              'reason': 'original unknown', 'rule_applied': None}
    b = list(re.finditer(rb'<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->', raw, re.S))[0]
    rule = {'decision': 'KNOWN_NON_TIMING_EXACT_WITNESS_ONLY', 'kind': kind, 'identity': before['identity'], 'namespace': 'jleague_data_site_sfms02',
            'expected': deepcopy(expected), 'original_v5_HOLD': deepcopy(before), 'request_started_UTC': request['request_started_at_utc'],
            'response_completed_UTC': '2026-10-22T00:00:01+00:00', 'snapshot_saved_UTC': '2026-10-22T00:00:02+00:00',
            'A11_byte_range': [b.start(), b.end()], 'A11_SHA256': c.sha(b.group()), 'A11_HTML': b.group().decode('utf8'),
            'A10_end_byte_start': 0, 'A12_relative_byte_start': 0, 'paragraph_HTML': ['<p>' + p + '</p>' for p in paragraphs],
            'paragraph_verbatim': paragraphs, 'positive_fields': fields, 'normalized_remarks': paragraphs,
            'classification': 'AFFIRMATIVELY_REVIEWED_NON_TIMING_ANNOTATION', 'history_admission': False, 'timing_B_C_D': 'HOLD'}
    rules = [rule]
    for i in [2, 3]:
        other = deepcopy(rule)
        other['identity'] = 'jleague_data_site_sfms02:90000' + str(i)
        rules.append(other)
    registry = {'version': c.VERSION, 'rules': rules}
    return [raw, meta, req, expected, before, registry]


def verify(raw, meta, request, pins):
    for value, key in [(raw, 'raw_sha256'), (meta, 'metadata_sha256'), (request, 'request_sha256')]:
        c.require(c.sha(value) == pins[key], 'SOURCE_SHA')


def run(f, registry_sha=None):
    raw, meta, request, expected, before, registry = f
    return c.analyze(raw, meta, request, expected, lambda *_: deepcopy(before), verify, registry, registry_sha or c.sha(c.encoded(registry)))


@pytest.mark.parametrize('kind', sorted(c.KINDS))
def test_exact_affirmative_witness_pass(kind):
    f = fixture(kind)
    frozen = deepcopy(f)
    assert run(f)['status'] == 'PASS'
    assert f == frozen
    with pytest.raises(ValueError, match='HISTORY_ADMISSION'):
        c.require_history_admission(run(f))


@pytest.mark.parametrize('field', ['identity', 'url', 'data_site_match_id', 'home_team_id', 'away_team_id', 'source_date',
                                 'source_reported_kickoff', 'home_score_90', 'away_score_90', 'series', 'pk_played', 'extra_time_played'])
def test_fixture_scope_modifications_refused(field):
    f = fixture()
    f[3]['row'][field] = 'changed'
    assert run(f)['status'] == 'HOLD'


@pytest.mark.parametrize('field', ['header', 'revision', 'pins'])
def test_header_revision_and_pins_refused(field):
    f = fixture()
    if field == 'header':
        f[3][field] += ' next season'
    else:
        f[3][field]['extra'] = 'changed'
    assert run(f)['status'] == 'HOLD'


@pytest.mark.parametrize('i', [0, 1, 2])
def test_raw_metadata_request_tamper(i):
    f = fixture()
    f[i] += b' '
    assert run(f)['status'] == 'HOLD'


@pytest.mark.parametrize('change', ['byte_range', 'HTML', 'block_SHA', 'paragraph_HTML', 'text', 'role', 'expression', 'code',
                                  'namespace', 'UTC', 'neighbor', 'normalized', 'decision', 'kind', 'admission', 'timing'])
def test_rule_internals_fail_closed_even_with_repinned_test_registry(change):
    f = fixture()
    rule = f[5]['rules'][0]
    if change == 'byte_range': rule['A11_byte_range'][0] += 1
    if change == 'HTML': rule['A11_HTML'] += ' '
    if change == 'block_SHA': rule['A11_SHA256'] = 'bad'
    if change == 'paragraph_HTML': rule['paragraph_HTML'][0] = '<p>changed</p>'
    if change == 'text': rule['paragraph_verbatim'][0] += ' '
    if change == 'role': rule['positive_fields'][0]['role'] = '（監督）'
    if change == 'expression': rule['positive_fields'][0]['expression'] = '退場'
    if change == 'code': rule['positive_fields'][0]['code'] = 'unknown'
    if change == 'namespace': rule['namespace'] = 'wrong'
    if change == 'UTC': rule['response_completed_UTC'] = '2026-01-01T00:00:00+00:00'
    if change == 'neighbor': rule['A12_relative_byte_start'] += 1
    if change == 'normalized': rule['normalized_remarks'].append('unknown')
    if change == 'decision': rule['decision'] = 'ALLOW_ALL'
    if change == 'kind': rule['kind'] = 'UNREVIEWED'
    if change == 'admission': rule['history_admission'] = True
    if change == 'timing': rule['timing_B_C_D'] = 'READY'
    assert run(f)['status'] == 'HOLD'


@pytest.mark.parametrize('suffix', [' 中断', ' 再開', ' 延期', ' 打切り', ' 訂正', ' 18:00', ' unknown'])
def test_unknown_or_timing_text_not_accepted_by_repinned_synthetic_evidence(suffix):
    f = fixture(changed_paragraphs=lambda p: [p[0] + suffix])
    assert run(f)['status'] == 'HOLD'


@pytest.mark.parametrize('change', ['append', 'duplicate', 'HTML', 'same_normalized', 'swap_pair', 'remove_pair'])
def test_all_paragraphs_and_exact_original_form_required(change):
    def mutate(p):
        if change == 'append': return p + ['unknown']
        if change == 'duplicate': return p + p
        if change == 'HTML': return ['<b>' + p[0] + '</b>']
        if change == 'same_normalized': return [p[0].replace(' ', '  ')]
        if change == 'swap_pair': return list(reversed(p))
        return p[:1]
    kind = 'EXACT_SUBSTITUTION_PAIR' if change in {'swap_pair', 'remove_pair'} else 'EXACT_POSTMATCH_COACH_WARNING'
    assert run(fixture(kind, changed_paragraphs=mutate))['status'] == 'HOLD'


def test_unknown_fixture_no_fallback_and_old_v5_pass_unchanged():
    f = fixture()
    f[3]['row']['identity'] = 'jleague_data_site_sfms02:999999'
    assert run(f) == f[4]
    f[4].update(status='PASS', category='KNOWN_NON_TIMING_NOTE', rule_applied='old_exact_rule')
    assert run(f) == f[4]


def test_registry_tamper_duplicate_and_extra_rule_refused():
    f = fixture()
    assert run(f, 'bad')['status'] == 'HOLD'
    f[5]['rules'][1]['identity'] = f[5]['rules'][0]['identity']
    assert run(f)['status'] == 'HOLD'
    f[5]['rules'].append(deepcopy(f[5]['rules'][0]))
    assert run(f)['status'] == 'HOLD'


def test_only_unknown_strict_hold_is_reviewable():
    f = fixture()
    f[4]['strict_analysis']['timing_notes'] = ['unreviewed timing']
    f[5]['rules'][0]['original_v5_HOLD'] = deepcopy(f[4])
    assert run(f)['status'] == 'HOLD'


def test_adapter_has_no_network_model_permit_or_io_entry_point(monkeypatch):
    tree = ast.parse(PATH.read_text('utf8'))
    assert {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} == {'copy', 'hashlib', 'html', 'json', 're'}
    assert not any(isinstance(n, ast.ImportFrom) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {'open', 'exec', 'eval', '__import__'} for n in ast.walk(tree))
    f = fixture()
    def deny(*args, **kwargs): raise AssertionError('I/O, permit and model access forbidden')
    with monkeypatch.context() as scoped:
        scoped.setattr('builtins.open', deny)
        assert run(f)['status'] == 'PASS'
