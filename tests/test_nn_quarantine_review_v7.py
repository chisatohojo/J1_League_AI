"""Offline synthetic v7 safety cases; no real fixture, person or filesystem evidence."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
import socket
import unicodedata
import pytest

PATH = Path(__file__).parents[1] / 'research/nn_v2/phase2_5B_19/exact_detail_review_v7.py'
spec = importlib.util.spec_from_file_location('review_v7', PATH)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs): raise AssertionError('No network in v7 tests')
    monkeypatch.setattr(socket, 'getaddrinfo', deny)
    monkeypatch.setattr(socket.socket, 'connect', deny)


def case(i, mutate=None, fields_mutation=None):
    kind = ['POSTMATCH_PLAYER_CAUTION_REFERENCE', 'POSTMATCH_COACH_CAUTION', 'MINUTE_GK_CAUTION',
            'SUBSTITUTION_WITH_RESPONSE_CONTINUATION', 'TWO_STAFF_CAUTION_PARAGRAPHS', 'MINUTE_GK_CAUTION'][i]
    if i == 0:
        fields = [{'marker': '***', 'club': 'Club A', 'number': '25', 'person': 'Player A'}]
    elif i == 3:
        fields = [{'display': "60'", 'club': 'Club A', 'out_number': '9', 'out_person': 'Player A', 'in_number': '38', 'in_person': 'Player B'},
                  {'display': "88'", 'club': 'Club B', 'out_number': '8', 'out_person': 'Player C', 'in_number': '35', 'in_person': 'Player D'}]
    else:
        fields = [{'display': '試合終了後' if i == 1 else "57'" if i == 2 else "45'+3" if i == 5 else "28'", 'club': 'Club A',
                   'person': 'Staff A', 'role': '（コーチ）' if i == 1 else '（監督）' if i == 4 else '（ＧＫコーチ）', 'expression': '警告', 'code': 'C3'}]
        if i == 4:
            fields.append({'display': "90'+9", 'club': 'Club A', 'person': 'Staff B', 'role': '（コーチ）', 'expression': '警告', 'code': 'C1'})
    continuation = {'classification': 'REVIEWED_LITERAL_RESPONSE_ALLOWANCE', 'paragraph_index': 2,
                    'verbatim': 'Synthetic reviewed response allowance continuation',
                    'text_SHA256': c.sha(b'Synthetic reviewed response allowance continuation')}
    texts = c.positive_paragraphs({'kind': kind, 'positive_fields': fields, 'reviewed_continuation': continuation})
    if mutate: texts = mutate(texts)
    if fields_mutation: fields_mutation(fields)
    prefix = '<!-- A8 Start --><table><tr><td>25</td><td>Player A</td><td>***</td></tr></table><!-- A8 End -->'
    prefix += '<!-- A7 Start --><table><tr><td>Player A</td><td>Player B</td></tr></table><!-- A7 End -->'
    prefix += '<!-- A5 Start --><table><tr><td>25</td><td>Player A</td></tr></table><!-- A5 End -->'
    prefix += '<!-- A10 Start --><table><tr><td>Staff A</td></tr></table><!-- A10 End -->'
    block = '<!-- A11 Start --><div><h4>備考</h4>' + ''.join('<p>' + p + '</p>' for p in texts) + '</div><!-- A11 End -->'
    raw = (prefix + block + '<!-- A12 Start -->').encode('utf8')
    identity = 'jleague_data_site_sfms02:' + str(900001+i) if i < 2 else 'j1_2026_2027:synthetic_home_' + str(i) + ':synthetic_away_' + str(i)
    url = 'https://data.j-league.or.jp/SFMS02/?match_card_id=' + str(900001+i)
    req = c.encoded({'identity': identity, 'url': url, 'request_started_at_utc': '2026-10-22T00:00:00+00:00'})
    meta = c.encoded({'requested_url': url, 'final_url': url, 'request_started_at_utc': '2026-10-22T00:00:00+00:00',
                      'response_completed_at_utc': '2026-10-22T00:00:01+00:00', 'snapshot_saved_at_utc': '2026-10-22T00:00:02+00:00',
                      'request_sha256': c.sha(req), 'sha256': c.sha(raw)})
    expected = {'row': {'identity': identity, 'url': url, 'data_site_match_id': str(900001+i), 'home_team_id': 'synthetic_home',
                       'away_team_id': 'synthetic_away', 'source_date': '2026-01-01', 'source_reported_kickoff': '2026-01-01T14:00:00+09:00',
                       'home_score_90': 1, 'away_score_90': 0, 'pk_played': False, 'extra_time_played': False}, 'header': 'Synthetic season/competition/round',
                'revision': {'source_CSV_SHA256': 'fixed-source', 'source_row_SHA256': 'fixed-row'},
                'pins': {'url': url, 'raw_sha256': c.sha(raw), 'metadata_sha256': c.sha(meta), 'request_sha256': c.sha(req)}}
    before = {'version': 'unchanged_baseline', 'identity': identity, 'status': 'HOLD', 'legacy_category': 'UNKNOWN_FORMAT', 'rule_applied': None,
              'reason': 'original HOLD', 'strict_analysis': {'status': c.BASE_PASS, 'timing_notes': [], 'remarks_structure': 'A11_BLOCK', 'remarks': texts}}
    b = next(re.finditer(rb'<!-- A11[^>]*Start -->(.*?)<!-- A11[^>]*End -->', raw, re.S))
    a10 = list(re.finditer(rb'<!-- A10[^>]*End -->', raw[:b.start()]))[-1]
    spans = []
    for label, pattern in [('A11', rb'<!-- A11[^>]*Start -->.*?<!-- A11[^>]*End -->'), ('A8', rb'<!-- A8[^>]*Start -->.*?<!-- A8[^>]*End -->'),
                           ('A7', rb'<!-- A7[^>]*Start -->.*?<!-- A7[^>]*End -->'), ('ROSTER', rb'<!-- A5[^>]*Start -->.*?<!-- A5[^>]*End -->'),
                           ('A10', rb'<!-- A10[^>]*Start -->.*?<!-- A10[^>]*End -->')]:
        m = next(re.finditer(pattern, raw, re.S))
        spans.append({'field': label, 'byte_range': [m.start(), m.end()], 'HTML': m.group().decode('utf8'), 'SHA256': c.sha(m.group())})
    rule = {'identity': identity, 'fixture_namespace': identity.split(':')[0], 'official_detail_namespace': 'jleague_data_site_sfms02',
            'kind': kind, 'positive_fields': fields, 'reviewed_continuation': continuation,
            'positive_basis': ['Synthetic affirmative reviewed structure'], 'expected': deepcopy(expected),
            'original_baseline_HOLD': deepcopy(before), 'request_started_UTC': '2026-10-22T00:00:00+00:00', 'response_completed_UTC': '2026-10-22T00:00:01+00:00',
            'snapshot_saved_UTC': '2026-10-22T00:00:02+00:00', 'A11_byte_range': [b.start(), b.end()], 'A11_SHA256': c.sha(b.group()),
            'A11_HTML': b.group().decode('utf8'), 'A10_end_byte_start': a10.start(), 'A12_relative_byte_start': 0,
            'paragraph_HTML': ['<p>'+p+'</p>' for p in texts], 'paragraph_verbatim': texts, 'normalized_remarks': texts,
            'corroborating_spans': spans, 'decision': 'EXACT_REVIEWED_WITNESS_ONLY', 'classification': 'A_AFFIRMATIVE_NON_TIMING',
            'history_admission': False, 'timing_B_C_D': 'HOLD'}
    return [raw, meta, req, expected, before, rule]


def scenario(i=0, **kwargs):
    cases = [case(j, **kwargs) if j == i else case(j) for j in range(6)]
    return cases[i], {'version': c.VERSION, 'rules': [v[5] for v in cases]}


def verify(raw, meta, request, pins):
    for data, key in [(raw, 'raw_sha256'), (meta, 'metadata_sha256'), (request, 'request_sha256')]:
        if c.sha(data) != pins[key]: raise ValueError('SHA mismatch')


def run(f, registry, pin=None):
    return c.analyze(*f[:4], lambda *_: deepcopy(f[4]), verify, registry, pin or c.sha(c.encoded(registry)))


@pytest.mark.parametrize('i', range(6))
def test_each_of_six_exact_synthetic_witnesses_and_no_admission(i):
    f, r = scenario(i)
    before = deepcopy((f, r))
    assert run(f, r)['status'] == 'PASS'
    assert (f, r) == before
    with pytest.raises(ValueError, match='HISTORY_ADMISSION'): c.require_history_admission(run(f, r))


@pytest.mark.parametrize('field', ['url', 'data_site_match_id', 'home_team_id', 'away_team_id', 'source_date', 'source_reported_kickoff',
                                 'home_score_90', 'away_score_90', 'pk_played', 'extra_time_played'])
def test_fixture_drift_is_evidence_STOP(field):
    f, r = scenario()
    f[3]['row'][field] = 'modified'
    with pytest.raises(c.EvidenceStop): run(f, r)


@pytest.mark.parametrize('field', ['header', 'revision', 'pins'])
def test_header_source_revision_and_pin_drift_STOP(field):
    f, r = scenario()
    if field == 'header': f[3][field] += ' next season'
    else: f[3][field]['unexpected'] = 'changed'
    with pytest.raises(c.EvidenceStop): run(f, r)


@pytest.mark.parametrize('i', [0, 1, 2])
def test_raw_metadata_request_drift_STOP_not_remark_HOLD(i):
    f, r = scenario()
    f[i] += b' '
    with pytest.raises(c.EvidenceStop): run(f, r)


@pytest.mark.parametrize('field', ['A11_byte_range', 'A11_SHA256', 'A11_HTML', 'fixture_namespace', 'official_detail_namespace',
                                 'request_started_UTC', 'response_completed_UTC', 'snapshot_saved_UTC', 'A10_end_byte_start', 'A12_relative_byte_start'])
def test_repinned_synthetic_rule_cannot_hide_evidence_drift(field):
    f, r = scenario()
    if field == 'A11_byte_range': f[5][field][0] += 1
    elif type(f[5][field]) is int: f[5][field] += 1
    else: f[5][field] += ' changed'
    with pytest.raises(c.EvidenceStop): run(f, r)


@pytest.mark.parametrize('kind', ['bad_sha', 'duplicate', 'extra'])
def test_registry_trust_failure_STOP(kind):
    f, r = scenario()
    pin = c.sha(c.encoded(r))
    if kind == 'bad_sha': r['version'] += ' altered'
    if kind == 'duplicate': r['rules'][1]['identity'] = r['rules'][0]['identity']; pin = c.sha(c.encoded(r))
    if kind == 'extra': r['rules'].append(deepcopy(r['rules'][0])); pin = c.sha(c.encoded(r))
    with pytest.raises(c.EvidenceStop): run(f, r, pin)


@pytest.mark.parametrize('suffix', [' 中断', ' 再開', ' 延期', ' 訂正', ' 打切り', ' 18:00', ' unknown'])
def test_mixed_timing_or_unknown_sentence_remains_HOLD(suffix):
    f, r = scenario(1, mutate=lambda p: [p[0] + suffix])
    assert run(f, r)['status'] == 'HOLD'


@pytest.mark.parametrize('change', ['append', 'omit', 'duplicate', 'reverse', 'whitespace', 'markup', 'unicode'])
def test_complete_paragraph_order_and_verbatim_structure(change):
    def mutate(p):
        if change == 'append': return p + ['unknown paragraph']
        if change == 'omit': return p[:-1]
        if change == 'duplicate': return p + p
        if change == 'reverse': return list(reversed(p))
        if change == 'whitespace': return [s.replace(' ', '  ') for s in p]
        if change == 'markup': return ['<b>'+p[0]+'</b>'] + p[1:]
        return [unicodedata.normalize('NFKC', s) for s in p]
    i = 2 if change == 'unicode' else 3
    f, r = scenario(i, mutate=mutate)
    assert run(f, r)['status'] == 'HOLD'


@pytest.mark.parametrize('field,value', [('role', '（通訳）'), ('role', '（監督）'), ('role', '(GKコーチ)'), ('code', 'C1'), ('expression', '退場')])
def test_distinct_staff_roles_codes_and_expressions(field, value):
    f, r = scenario(2, fields_mutation=lambda fields: fields[0].update({field: value}))
    assert run(f, r)['status'] == 'HOLD'


def test_two_warning_roles_or_paragraphs_cannot_be_swapped():
    f, r = scenario(4, mutate=lambda p: list(reversed(p)))
    assert run(f, r)['status'] == 'HOLD'


def test_wrong_fixture_no_fallback_and_baseline_PASS_full_result_unchanged():
    f, r = scenario()
    f[3]['row']['identity'] = 'j1_2026_2027:other:fixture'
    f[4]['identity'] = f[3]['row']['identity']
    assert run(f, r) == f[4]
    f[4].update(status='PASS', rule_applied='old_v6_exact_witness', nested={'semantic': [1, None, False]})
    assert run(f, r) == f[4]


def test_confirmed_timing_flag_never_accepted_and_corroboration_required():
    f, r = scenario()
    f[4]['strict_analysis']['timing_notes'] = ['unresolved time note']
    f[5]['original_baseline_HOLD'] = deepcopy(f[4])
    assert run(f, r)['status'] == 'HOLD'
    f, r = scenario()
    f[5]['corroborating_spans'] = []
    assert run(f, r)['status'] == 'HOLD'


def test_corroboration_SHA_drift_STOP():
    f, r = scenario()
    f[5]['corroborating_spans'][0]['SHA256'] = 'changed'
    with pytest.raises(c.EvidenceStop): run(f, r)


@pytest.mark.parametrize('field', ['classification', 'paragraph_index', 'text_SHA256'])
def test_continuation_requires_reviewed_private_literal_and_position(field):
    f, r = scenario(3)
    f[5]['reviewed_continuation'][field] = 'unreviewed'
    assert run(f, r)['status'] == 'HOLD'


def test_pure_adapter_has_no_network_permit_model_or_operational_write_path(monkeypatch):
    tree = ast.parse(PATH.read_text('utf8'))
    assert {n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)} == {'copy', 'hashlib', 'html', 'json', 're'}
    assert not any(isinstance(n, ast.ImportFrom) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in {'open', 'eval', 'exec', '__import__'} for n in ast.walk(tree))
    f, r = scenario()
    def deny(*args, **kwargs): raise AssertionError('No I/O, model or permit access')
    with monkeypatch.context() as scoped:
        scoped.setattr('builtins.open', deny)
        assert run(f, r)['status'] == 'PASS'
