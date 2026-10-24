"""Offline candidate identity tests, never an adopted HTTP sender setting."""
import hashlib
import pytest

from research.nn_v2.phase2_5K import product_token_groups as k
from research.nn_v2.phase2_5J import robots_layers as j


def evaluate(raw=b'User-agent: *\nDisallow: /private\n', path='/public', **changes):
    args = dict(source_host='synthetic.invalid', target_url='https://synthetic.invalid'+path,
                header='ExampleBot/1.0', declared_tokens=['ExampleBot'],
                expected_raw_SHA256=hashlib.sha256(raw).hexdigest(),
                specification_SHA256=k.subset.SPEC_SHAS, profile=k.subset.SYNTHETIC_PROFILE)
    args.update(changes)
    return k.evaluate(raw, **args)


@pytest.mark.parametrize('token', ['ExampleBot', 'examplebot', 'EXAMPLEBOT', 'Example', 'Bot', 'Research-Timing-Pilot', 'Timing-Pilot', '_Agent_', 'A-B', '-'])
def test_explicit_binding_is_not_group_substring(token):
    header = 'Mozilla/5.0 (compatible; '+token+'/1.0; research)'
    value = k.declared_identity(header, [token])
    assert value['status'] == 'BOUND_CANDIDATE'
    assert value['product_token'] == token
    assert value['auto_extracted'] is value['actual_transmission_proven'] is False


@pytest.mark.parametrize('token', ['', '*', 'J1AI', 'Bot1', 'Bot/1.0', 'Bot.abc', 'Bot abc', 'Bot\t', 'Bot\r', 'Bot\n', 'Böt', 'Ｂot', 'Bot*', 1, None])
def test_negative_invalid_RFC_token(token):
    assert k.declared_identity('J1AI ExampleBot1/1.0 Böt Ｂot', [token])['status'] == 'UNKNOWN'


@pytest.mark.parametrize('tokens', [None, [], ['ExampleBot', 'Bot'], ['ExampleBot', 'ExampleBot'], 'ExampleBot', {'ExampleBot'}, [1], ['Missing']])
def test_negative_no_automatic_extraction_or_ambiguous_declaration(tokens):
    assert k.declared_identity('ExampleBot/1.0', tokens)['status'] == 'UNKNOWN'


@pytest.mark.parametrize('header', ['', None, 12, 'ExampleBot\n', 'ExampleBot\r\nAllow: /', 'ExampleBot\t', 'ExampleBot\x7f', 'ExampleBoté', 'x'*1025])
def test_negative_header_boundary(header):
    assert k.declared_identity(header, ['ExampleBot'])['status'] == 'UNKNOWN'


GROUP_CASES = [
    (b'User-agent: ExampleBot\nDisallow: /\n', [1], 'DENY'),
    (b'User-agent: eXAMPLEbOT\nDisallow: /\n', [1], 'DENY'),
    (b'User-agent: Other\nUser-agent: ExampleBot\nDisallow: /\n', [1], 'DENY'),
    (b'User-agent: *\nDisallow: /\nUser-agent: ExampleBot\nAllow: /\n', [2], 'ALLOW'),
    (b'User-agent: ExampleBot\nAllow: /\nUser-agent: *\nDisallow: /\n', [1], 'ALLOW'),
    (b'User-agent: ExampleBot\nAllow: /\nUser-agent: examplebot\nDisallow: /public\n', [1, 2], 'DENY'),
    (b'User-agent: ExampleBot\nDisallow: /public\nUser-agent: EXAMPLEBOT\nAllow: /public\n', [1, 2], 'ALLOW'),
    (b'User-agent: Other\nDisallow: /\nUser-agent: *\nAllow: /\n', [2], 'ALLOW'),
    (b'User-agent: Other\nDisallow: /\n', [], 'ALLOW'),
    (b'User-agent: ExampleBot\n', [1], 'ALLOW'),
    (b'User-agent: ExampleBot\nDisallow:\nUser-agent: Other\nDisallow: /\n', [1], 'ALLOW'),
    (b'User-agent: ExampleBot\n\n#comment\nUser-agent: Other\nDisallow: /\n', [1], 'DENY'),
    (b'User-agent: ExampleBot\nOther-field: x\nUser-agent: Other\nDisallow: /\n', [1], 'DENY'),
    (b'User-agent: Bot\nDisallow: /\nUser-agent: *\nAllow: /\n', [2], 'ALLOW'),
    (b'User-agent: ExampleBotExtra\nDisallow: /\nUser-agent: *\nAllow: /\n', [2], 'ALLOW'),
    (b'User-agent: Example\nDisallow: /\nUser-agent: *\nAllow: /\n', [2], 'ALLOW'),
    (b'User-agent: *\nDisallow: /\nUser-agent: *\nAllow: /public\n', [1, 2], 'ALLOW'),
    (b'\xef\xbb\xbfUser-agent: ExampleBot\r\nDisallow: /\r\n', [1], 'DENY'),
    (b'', [], 'ALLOW'),
    (b'# verified empty document\n\t\n', [], 'ALLOW'),
]


@pytest.mark.parametrize('raw,expected_groups,decision', GROUP_CASES)
def test_group_selection_separate_from_path(raw, expected_groups, decision):
    result = evaluate(raw)
    group = result['layer1']['group_selection']
    assert group['status'] == 'SELECTED'
    assert [g['group'] for g in group['groups']] == expected_groups
    assert result['layer1']['path_result']['decision'] == decision
    assert result['layer1']['decision'] == decision
    assert result['layer2']['decision'] == 'UNKNOWN'
    assert result['layer3']['permit']['decision'] == 'UNAPPROVED'
    assert not result['layer3']['communication']['communication_candidate']


@pytest.mark.parametrize('raw', [b'User-agent: ExampleBot/1.0\nDisallow: /\n',
    b'User-agent: ExampleBot*\nDisallow: /\n', b'User-agent: \nDisallow: /\n',
    b'User-agent: Bot1\nDisallow: /\n', b'User-agent: ExampleBot\nNot a directive\nAllow: /\n',
    b'Disallow: /\nUser-agent: ExampleBot\nAllow: /\n', b'User-agent: ExampleBot\n\xff',
    b'<html>not robots</html>', b'User-agent: ExampleBot\nDisallow: /\x00', b'x'*65537,
    b'User-agent: ExampleBot\nDisallow: /%FF\n'], ids=[f'structure-{n}' for n in range(11)])
def test_negative_structural_or_encoding_unknown(raw):
    result = evaluate(raw)
    assert result['layer1']['group_selection']['status'] == 'UNKNOWN'
    assert result['layer1']['decision'] == 'UNKNOWN'
    assert not result['execution_authorized']


@pytest.mark.parametrize('pattern', ['no-slash', '/%2F', '/x$z', '/a**'*40])
def test_negative_known_group_unknown_path(pattern):
    raw = ('User-agent: ExampleBot\nDisallow: '+pattern+'\n').encode()
    value = evaluate(raw)
    assert value['layer1']['group_selection']['status'] == 'SELECTED'
    assert value['layer1']['decision'] == 'UNKNOWN'


@pytest.mark.parametrize('path', ['/a?x=1&y=2', '/a?x=https://host', '/a?%61=1', '/%2F', '/a/../x', '/%2e/x', '/%FF'])
def test_negative_path_does_not_erase_known_group(path):
    value = evaluate(path=path)
    assert value['layer1']['group_selection']['status'] == 'SELECTED'
    assert value['layer1']['decision'] == 'UNKNOWN'


@pytest.mark.parametrize('field,value', [('expected_raw_SHA256', '0'*64), ('specification_SHA256', {}),
    ('parser_version', j.VERSION), ('response_status', 403), ('response_status', 429), ('response_status', 404),
    ('response_status', None), ('response_status', True), ('source_host', 'www.jleague.jp'),
    ('target_url', 'http://synthetic.invalid/public'), ('target_url', 'https://synthetic.invalid:443/public'),
    ('target_url', 'https://synthetic.invalid.evil/public'), ('target_url', 'https://u@synthetic.invalid/public'),
    ('target_url', 'https://synthetic.invalid/public#x'), ('target_url', 'https://synthetic.invalid/\n'),
    ('profile', 'PRODUCTION')])
def test_negative_no_override_of_integrity_origin_scope(field, value):
    out = evaluate(path='/robots.txt', **{field: value})
    assert out['layer1']['decision'] == 'UNKNOWN'
    assert out['layer3']['permit']['decision'] == 'UNAPPROVED'
    assert not out['layer3']['communication']['communication_candidate']


@pytest.mark.parametrize('path', ['/robots.txt', '/general/kiyaku/', '/general/copyright/', '/j1/news/'])
def test_candidate_and_missing_declaration_not_current_sender_proof(path):
    raw = b'User-agent: *\nDisallow: /closed\nUser-agent: spider\nDisallow: /\n'
    candidate = evaluate(raw, path, header=k.subset.FIXED_AGENT, declared_tokens=['Research-Timing-Pilot'])
    baseline = evaluate(raw, path, header=k.subset.FIXED_AGENT, declared_tokens=[])
    assert candidate['layer1']['decision'] == 'ALLOW'
    assert [g['group'] for g in candidate['layer1']['group_selection']['groups']] == [1]
    assert baseline['layer1']['decision'] == ('ALLOW' if path == '/robots.txt' else 'UNKNOWN')
    assert candidate['layer2']['actual_transmitted_header'] == 'UNKNOWN'
    assert candidate['layer2']['runtime_token_activation'] == 'NOT_APPROVED'
    assert not candidate['history_admission']


@pytest.mark.parametrize('header,token,groups', [('ExampleBot/1.0', 'ExampleBot', [1]), ('Other/1.0', 'Other', [2]), ('Unknown/1.0', 'Unknown', [3])])
def test_override_requires_explicit_rebinding(header, token, groups):
    raw = b'User-agent: ExampleBot\nDisallow: /\nUser-agent: Other\nDisallow: /other\nUser-agent: *\nDisallow: /unknown\n'
    out = evaluate(raw, header=header, declared_tokens=[token])
    assert [g['group'] for g in out['layer1']['group_selection']['groups']] == groups
    assert evaluate(raw, header='Override/1.0', declared_tokens=[token])['layer1']['decision'] == 'UNKNOWN'


def test_RFC_figure1_visible_HTTP_header_not_automatically_full_product_token():
    raw = b'User-agent: ExampleBot\nDisallow: /\n'
    header = 'Mozilla/5.0 (compatible; ExampleBot/0.1; https://example.invalid/bot)'
    assert evaluate(raw, header=header)['layer1']['decision'] == 'DENY'
    assert evaluate(raw, header=header, declared_tokens=[header])['layer1']['decision'] == 'UNKNOWN'


def test_Google_name_suffix_behavior_not_general_RFC_matching():
    for directive in ['ExampleBot/1.2', 'ExampleBot*']:
        out = evaluate(('User-agent: '+directive+'\nDisallow: /\n').encode())
        assert out['layer1']['decision'] == 'UNKNOWN'


def test_unknown_other_record_only_semantics_never_access_permission():
    value = evaluate(b'User-agent: *\nCrawl-delay: 60\nDisallow: /private\n')
    assert value['layer1']['decision'] == 'ALLOW'
    assert value['layer1']['group_selection']['unresolved'][0]['reason'] == 'UNKNOWN_DIRECTIVE'
    assert value['layer2']['decision'] == 'UNKNOWN'
    assert not value['execution_authorized']


@pytest.mark.parametrize('path', ['/public', '/private', '/robots.txt'])
def test_J_compatible_subset_decisions_unchanged(path):
    raw = b'User-agent: *\nDisallow: /private\n'
    new = evaluate(raw, path)
    old = j.evaluate(raw, source_host='synthetic.invalid', target_url='https://synthetic.invalid'+path,
                     user_agent='ExampleBot/1.0', product_token='ExampleBot', profile=k.subset.SYNTHETIC_PROFILE,
                     expected_raw_SHA256=hashlib.sha256(raw).hexdigest(), specification_SHA256=k.subset.SPEC_SHAS)
    assert new['layer1']['decision'] == old['layer1']['decision']
    assert not old['execution_authorized'] and not new['execution_authorized']


def test_import_boundary_no_live_transport_or_authority():
    # An import-name allowlist is supplemented by the external guarded runner.
    import ast
    from pathlib import Path
    tree = ast.parse(Path(k.__file__).read_text(encoding='utf8'))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert modules == {'urllib.parse', 'research.nn_v2.phase2_5I', 'research.nn_v2.phase2_5J'}
    assert {x.name for n in ast.walk(tree) if isinstance(n, ast.Import) for x in n.names} == {'hashlib', 're'}


@pytest.mark.parametrize('header,token,group,decision', [
    ('ResearchBot/1.0 (spider)', 'ResearchBot', 1, 'ALLOW'),
    ('ResearchBot/1.0 (spider)', 'spider', 2, 'DENY'),
    ('Spider/1.0', 'Spider', 2, 'DENY'),
    ('SPIDER/1.0', 'spider', 2, 'DENY'),
    ('OtherSpider/1.0', 'OtherSpider', 1, 'ALLOW'),
])
def test_named_spider_not_selected_by_undeclared_header_substring(header, token, group, decision):
    raw = b'User-agent: *\nDisallow: /closed\nUser-agent: spider\nDisallow: /\n'
    value = evaluate(raw, header=header, declared_tokens=[token])
    assert [g['group'] for g in value['layer1']['group_selection']['groups']] == [group]
    assert value['layer1']['decision'] == decision
    assert not value['execution_authorized']


def test_negative_implicit_URI_does_not_hide_unknown_pattern_ranking():
    raw = b'User-agent: *\nDisallow: /r**********\nAllow: /robots.txt\n'
    value = evaluate(raw, '/robots.txt')
    assert value['layer1']['group_selection']['status'] == 'SELECTED'
    assert value['layer1']['path_result']['decision'] == 'UNKNOWN'
    assert value['layer1']['decision'] == 'UNKNOWN'


def test_implicit_URI_exception_is_explicit_path_result_without_token_invention():
    value = evaluate(path='/robots.txt', declared_tokens=[])
    assert value['layer1']['group_selection']['status'] == 'UNKNOWN'
    assert value['layer1']['path_result']['decision'] == 'ALLOW'
    assert value['layer1']['path_result']['reason'] == 'RFC_2_2_2_EXACT_IMPLICIT_URI'
    assert value['layer1']['decision'] == 'ALLOW'
