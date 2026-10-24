"""G1 decision validation only; no client, worker, permit or operational data."""
import ast
from copy import deepcopy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from research.nn_v2.phase2_5N import ua_adoption as n

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/nn_v2/phase2_5N'
CANDIDATE = (ROOT / 'research/nn_v2/phase2_5L/USER_AGENT_CANDIDATE.json').read_bytes()
MATRIX = (ROOT / 'research/nn_v2/phase2_5M/URL_STOP_MATRIX.json').read_bytes()
STAMP = '2026-10-24T08:35:00+00:00'  # synthetic validation time, not a send timestamp
AFTER = '2026-10-24T08:36:00+00:00'


def manifest():
    return n.make_manifest(STAMP)


def verify(value, now=AFTER):
    return n.verify_manifest(value, candidate_bytes=CANDIDATE, verified_at_utc=now)


def evidence():
    return n.make_evidence(manifest(), candidate_bytes=CANDIDATE, matrix_bytes=MATRIX,
                           verified_at_utc=AFTER)


def verify_evidence(value):
    return n.verify_evidence(value, manifest(), candidate_bytes=CANDIDATE,
                             matrix_bytes=MATRIX, verified_at_utc=AFTER)


def test_exact_adoption_distinct_roles_and_no_authority():
    value = manifest()
    assert value['HTTP_USER_AGENT'] == 'J1AI-Research-Timing-Pilot/1.0'
    assert value['ROBOTS_PRODUCT_TOKEN'] == 'Research-Timing-Pilot'
    assert value['HTTP_USER_AGENT'] != value['ROBOTS_PRODUCT_TOKEN']
    assert verify(value) == dict(adoption_verified=True, execution_authorized=False,
                                  adapter_configuration_loaded=False)


@pytest.mark.parametrize('field,value', [
    ('HTTP_USER_AGENT', 'j1ai-Research-Timing-Pilot/1.0'),
    ('HTTP_USER_AGENT', 'J1AI-Research-Timing-Pilot/1.0 '),
    ('HTTP_USER_AGENT', 'J1AI-Research-Timing-Pilot/1.0\r\nX: y'),
    ('HTTP_USER_AGENT', 'Other/1.0'),
    ('ROBOTS_PRODUCT_TOKEN', 'research-timing-pilot'),
    ('ROBOTS_PRODUCT_TOKEN', 'J1AI-Research-Timing-Pilot/1.0'),
    ('ROBOTS_PRODUCT_TOKEN', None),
    ('ROBOTS_PRODUCT_TOKEN', ''),
    ('adoption_state', 'CANDIDATE_FROZEN_NOT_ACTIVATED'),
    ('adoption_state', 'ACTIVATED'), ('scope', 'PRODUCTION'),
    ('scope', 'Champion_A'), ('scope', 'scheduled_workers'),
    ('history_admission', True), ('unresolved_normative_ids', []),
    ('normative_counts', dict(PASS=24, FAIL=0, UNKNOWN=0)),
    ('decision_source', dict(kind='CODE_INFERENCE', SHA256=n.DECISION_SHA256)),
    ('legacy_request_schema', 'NNV2_UA_EVIDENCE_V2')])
def test_negative_exact_identity_scope_history_and_normative_contract(field, value):
    x = manifest(); x[field] = value
    with pytest.raises(n.AdoptionError):
        verify(x)


def test_negative_missing_token_or_swapped_roles():
    x = manifest(); del x['ROBOTS_PRODUCT_TOKEN']
    with pytest.raises(n.AdoptionError):
        verify(x)
    x = manifest()
    x['HTTP_USER_AGENT'], x['ROBOTS_PRODUCT_TOKEN'] = x['ROBOTS_PRODUCT_TOKEN'], x['HTTP_USER_AGENT']
    with pytest.raises(n.AdoptionError):
        verify(x)


@pytest.mark.parametrize('field', ['G2_connected', 'G3_permit_issued', 'G4_execution_authorized', 'current_requests'])
def test_negative_G1_never_grants_downstream_gate(field):
    x = manifest(); x['authorities'][field] = True
    with pytest.raises(n.AdoptionError):
        verify(x)


@pytest.mark.parametrize('field', ['Champion_A', 'Weekend_Batch', 'GUI', 'scheduled_workers'])
def test_negative_no_configuration_deployment_or_scope_extension(field):
    x = manifest(); x['excluded_scopes'].remove(field)
    with pytest.raises(n.AdoptionError):
        verify(x)


@pytest.mark.parametrize('field', ['HTTP_USER_AGENT', 'ROBOTS_PRODUCT_TOKEN', 'adopted_utc', 'decision_source'])
def test_negative_missing_adoption_field(field):
    x = manifest(); del x[field]
    with pytest.raises(n.AdoptionError):
        verify(x)


@pytest.mark.parametrize('now', ['2026-10-23T23:59:59+00:00', '2026-10-24T08:34:59.999999+00:00'])
def test_negative_pre_adoption_evidence_cannot_be_adopted(now):
    with pytest.raises(n.AdoptionError):
        verify(manifest(), now)


@pytest.mark.parametrize('stamp', ['2026-10-23T00:00:00+00:00', '2026-10-25T00:00:00+00:00',
                                  '2026-10-24', '2026-10-24T17:35:00+09:00'])
def test_negative_wrong_adoption_date_or_unqualified_clock(stamp):
    with pytest.raises(n.AdoptionError):
        n.make_manifest(stamp)


@pytest.mark.parametrize('level', ['E2', 'E3'])
def test_negative_adoption_cannot_promote_transmission_or_independent_observation(level):
    x = evidence(); x['facets'][level] = dict(status='PASS', performed=True)
    with pytest.raises(n.AdoptionError):
        verify_evidence(x)


@pytest.mark.parametrize('mutation', ['adapter-E0', 'new-E1', 'retroactive-E4', 'old-raw-UA',
                                     'permit', 'all-URLs', 'clear-UNKNOWN', 'admission', 'fake-hash'])
def test_negative_no_evidence_promotion_even_with_consistent_manifest_hash(mutation):
    x = evidence()
    if mutation == 'adapter-E0': x['facets']['E0']['actual_adapter_configuration_read'] = 'PASS'
    elif mutation == 'new-E1': x['facets']['E1']['new_request_prepared'] = True
    elif mutation == 'retroactive-E4': x['facets']['E4']['retroactive_attribution'] = True
    elif mutation == 'old-raw-UA': x['facets']['E4']['historical_outbound_UA'] = n.HTTP_USER_AGENT
    elif mutation == 'permit': x['permit_issued'] = True
    elif mutation == 'all-URLs':
        for row in x['URLs']: row['final_communication'] = True
    elif mutation == 'clear-UNKNOWN': x['fully_resolved_by_G1'] = list(n.UNKNOWN_IDS)
    elif mutation == 'admission': x['history_admission'] = True
    else: x['manifest_SHA256'] = '0' * 64
    with pytest.raises(n.AdoptionError):
        verify_evidence(x)


@pytest.mark.parametrize('target', ['A1', 'A3', 'A4', 'B1', 'A2', 'B2'])
def test_six_URLs_keep_host_specific_robots_evidence_and_stop(target):
    value = evidence()
    old = next(x for x in json.loads(MATRIX)['rows'] if x['id'] == target)
    row = next(x for x in value['URLs'] if x['id'] == target)
    assert row['historical_M_robots'] == old['robots']
    assert row['URL'] == old['URL'] and row['G1_identity_adopted']
    assert row['actual_outbound_UA'] == 'UNKNOWN' and row['site_access']['status'] == 'UNKNOWN'
    assert row['current_request_authority'] == 0 and not row['final_communication']
    assert row['remaining_STOP_reasons']
    assert 'FORMAL_UA_TOKEN_ADOPTION_NOT_APPROVED' not in row['remaining_STOP_reasons']
    assert row['historical_M_robots']['decision'] == ('UNKNOWN' if target in {'A2', 'B2'} else 'ALLOW')


@pytest.mark.parametrize('which', ['candidate', 'matrix'])
def test_negative_changed_existing_research_fixture_even_same_JSON_meaning(which):
    args = dict(candidate_bytes=CANDIDATE, matrix_bytes=MATRIX, verified_at_utc=AFTER)
    args['candidate_bytes' if which == 'candidate' else 'matrix_bytes'] += b' '
    with pytest.raises(n.AdoptionError):
        n.make_evidence(manifest(), **args)


def test_old_L_candidate_schema_and_M_unknown_records_remain_byte_identical():
    for name, expected in n.PRIOR_PINS:
        assert n.sha((ROOT / name).read_bytes()) == expected
    old = json.loads(CANDIDATE)
    assert old['candidate']['state'] == 'CANDIDATE_FROZEN_NOT_ACTIVATED'
    assert not old['candidate']['activated']
    assert evidence()['unresolved_normative_ids'] == list(n.UNKNOWN_IDS)
    assert not evidence()['fully_resolved_by_G1']


def test_new_state_requires_separate_schema_not_legacy_request_schema():
    old = json.loads((ROOT / n.PRIOR_PINS[1][0]).read_bytes())
    Draft202012Validator.check_schema(old)
    assert list(Draft202012Validator(old).iter_errors(manifest()))
    assert old['properties']['scope']['const'] == 'SYNTHETIC_ONLY'


@pytest.mark.parametrize('filename,kind', [('UA_ADOPTION_MANIFEST.json', 'manifest'),
                                         ('UA_ADOPTION_EVIDENCE.json', 'evidence')])
def test_published_schema_and_semantic_validation(filename, kind):
    x = json.loads((OUT / filename).read_bytes())
    schemas = json.loads((OUT / 'ADOPTION_SCHEMAS.json').read_bytes())
    schema = schemas['schemas'][filename]
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(x))
    m = json.loads((OUT / 'UA_ADOPTION_MANIFEST.json').read_bytes())
    now = x.get('evidence_utc', m['adopted_utc'])
    if kind == 'manifest':
        n.verify_manifest(x, candidate_bytes=CANDIDATE, verified_at_utc=now)
    else:
        n.verify_evidence(x, m, candidate_bytes=CANDIDATE, matrix_bytes=MATRIX, verified_at_utc=now)


@pytest.mark.parametrize('filename', ['UA_ADOPTION_MANIFEST.json', 'UA_ADOPTION_EVIDENCE.json'])
def test_negative_published_schema_rejects_unauthorized_field_or_bool_integer_alias(filename):
    schema = json.loads((OUT / 'ADOPTION_SCHEMAS.json').read_bytes())['schemas'][filename]
    value = json.loads((OUT / filename).read_bytes()); changed = deepcopy(value)
    changed['transport_enabled'] = True
    assert list(Draft202012Validator(schema).iter_errors(changed))
    if 'authorities' in value: value['authorities']['current_requests'] = False
    else: value['requests'] = False
    assert list(Draft202012Validator(schema).iter_errors(value))


@pytest.mark.parametrize('body', [b'{"x":0,"x":1}', b'{"n":NaN}', b'{"n":Infinity}', b'\xff'])
def test_negative_duplicate_keys_nonfinite_or_invalid_UTF8(body):
    with pytest.raises(n.AdoptionError):
        n.strict_json(body)


def test_no_transport_IO_model_permit_or_operational_imports_or_entrypoints():
    tree = ast.parse(Path(n.__file__).read_text(encoding='utf8'))
    assert {x.name for node in ast.walk(tree) if isinstance(node, ast.Import) for x in node.names} == {'hashlib', 'json'}
    assert {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} == {'datetime'}
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id in {'open', 'exec', 'eval', '__import__'} for node in ast.walk(tree))
    assert not any(name.startswith(('send', 'fetch', 'issue', 'activate', 'execute', 'connect')) for name in vars(n))
