"""Synthetic bytes exercise the validators; sealed originals are verified separately."""
from pathlib import Path
from copy import deepcopy
import ast
import hashlib
import json

import pytest
from jsonschema import Draft202012Validator
from research.nn_v2.phase2_5Q import access_evidence as q

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'research/nn_v2/phase2_5Q'


def read(name):
    return json.loads((OUT / name).read_bytes())


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def sample():
    x = read('ACCESS_EVIDENCE_INVENTORY.json')
    g = read('TERMS_GAP_MATRIX.json')
    raw = b'Synthetic robots bytes. Not a website response.'
    h = hashlib.sha256(raw).hexdigest()
    req = encoded(dict(url=q.TARGETS['A1'], note='synthetic request, no send'))
    orig = x['rows'][0]['original']
    md = encoded(dict(requested_url=q.TARGETS['A1'], actual_response_url=q.TARGETS['A1'],
        response_completed_UTC=orig['acquired_utc'], snapshot_saved_UTC=orig['saved_utc'],
        raw_SHA256=h, request_SHA256=hashlib.sha256(req).hexdigest()))
    seal = encoded(dict(raw_SHA256=h, request_SHA256=hashlib.sha256(req).hexdigest(),
        metadata_SHA256=hashlib.sha256(md).hexdigest(), readback=True))
    blobs = {'synthetic:raw': raw, 'synthetic:metadata': md, 'synthetic:request': req, 'synthetic:seal': seal}
    pins = {k: hashlib.sha256(v).hexdigest() for k, v in blobs.items()}
    orig.update(location='synthetic:raw', raw_SHA256=h, bytes=len(raw),
        supporting_records=[dict(role=role, location='synthetic:'+role, SHA256=pins['synthetic:'+role])
                            for role in ('metadata', 'request', 'seal')])
    for r in x['rows']:
        if r['robots']['source_SHA256']:
            r['robots']['source_SHA256'] = h
    return x, g, blobs, pins


def assess(x, g, blobs, pins, **kwargs):
    return q.evaluate_readiness(x, g, blobs, pins, schema_validated=True,
        provenance_links_verified=True, protection_passed=True, **kwargs)


def mutate(value, pointer, replacement):
    keys = pointer.strip('/').split('/')
    for k in keys[:-1]:
        value = value[int(k)] if type(value) is list else value[k]
    key = int(keys[-1]) if type(value) is list else keys[-1]
    value[key] = deepcopy(replacement)


def test_documented_unknowns_can_be_review_ready_without_access_authority():
    out = assess(*sample())
    assert out['gate'] == 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY'
    assert not any(out[k] for k in ('access_authorized', 'permit_issued', 'G3_review_authorized', 'G4_authorized'))
    assert out['historical_unknowns_resolved'] == 0


CASES = read('NEGATIVE_CONTROLS.json')['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_negative_required_controls_and_additional_evidence_forgery(case):
    x, g, blobs, pins = sample()
    mutate(x, case['path'], case['value'])
    out = assess(x, g, blobs, pins)
    assert out['gate'] != 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY', case['id']
    assert out['reasons'] and not out['access_authorized'] and not out['permit_issued']


@pytest.mark.parametrize('missing', ['schema_validated', 'provenance_links_verified', 'protection_passed'])
def test_negative_missing_validation_or_audit_stays_partial(missing):
    checks = dict(schema_validated=True, provenance_links_verified=True, protection_passed=True)
    checks[missing] = None
    out = q.evaluate_readiness(*sample(), **checks)
    assert out['gate'] == 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_PARTIAL'


def test_negative_protected_difference_requires_blocked_stop():
    out = q.evaluate_readiness(*sample(), schema_validated=True,
        provenance_links_verified=True, protection_passed=False)
    assert out['gate'] == 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_BLOCKED'


@pytest.mark.parametrize('attack', ['bytes', 'trust_anchor', 'request_bytes', 'metadata_bytes', 'seal_bytes', 'missing_pin'])
def test_negative_independent_hash_anchor_and_provenance_chain(attack):
    x, g, blobs, pins = sample()
    if attack == 'bytes': blobs['synthetic:raw'] += b'changed'
    elif attack == 'trust_anchor': pins['synthetic:raw'] = '0' * 64
    elif attack == 'missing_pin': del pins['synthetic:raw']
    else: blobs['synthetic:' + attack.split('_')[0]] += b'changed'
    assert assess(x, g, blobs, pins)['gate'] != 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY'


@pytest.mark.parametrize('field,value', [
    ('status', 'PASS'), ('classes', ['INVENTED']), ('targets', ['B3']), ('priority', 'P3'),
    ('bucket', 'P1'), ('historical_id', 'new_id'), ('source_record_SHA256', None),
    ('minimum_steps', []), ('shared_evidence', []), ('residual_constraints', []),
    ('offline_fully_resolvable', True), ('additional_approval_required', False),
    ('dynamic_isolation_required', 'UNKNOWN'), ('only_after_real_communication', 'UNKNOWN')])
def test_negative_gap_classification_and_resolution_consistency(field, value):
    x, g, blobs, pins = sample()
    g['rows'][0][field] = value
    assert assess(x, g, blobs, pins)['gate'] != 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY'


@pytest.mark.parametrize('name,artifact', [
    ('INVENTORY_SCHEMA.json', 'ACCESS_EVIDENCE_INVENTORY.json'),
    ('GAP_SCHEMA.json', 'TERMS_GAP_MATRIX.json'),
    ('PRIORITY_SCHEMA.json', 'P0_EVIDENCE_PRIORITY.json')])
def test_closed_local_schema_and_actual_artifact(name, artifact):
    schema = read(name)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    value = read(artifact)
    assert not list(validator.iter_errors(value))
    value['unapproved_extension'] = True
    assert list(validator.iter_errors(value))
    assert '$ref' not in json.dumps(schema)


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_negative_inventory_schema_also_rejects_claim_mutation(case):
    value = read('ACCESS_EVIDENCE_INVENTORY.json')
    mutate(value, case['path'], case['value'])
    assert list(Draft202012Validator(read('INVENTORY_SCHEMA.json')).iter_errors(value))


@pytest.mark.parametrize('target,url', [
    ('A1', 'http://www.jleague.jp/robots.txt'), ('A1', 'https://www.jleague.jp:443/robots.txt'),
    ('A1', 'https://www.jleague.jp/robots.txt#x'), ('A1', 'https://www.jleague.jp/ROBOTS.txt'),
    ('A2', q.TARGETS['A1']), ('A3', 'https://user@www.jleague.jp/general/kiyaku/'),
    ('B1', 'https://www.jleague.jp/j1/news/?page=2'), ('B3', 'https://www.jleague.jp/')])
def test_negative_exact_URL_is_not_normalized_or_expanded(target, url):
    with pytest.raises(q.EvidenceError): q.validate_scope(target, url, 'www.jleague.jp')


@pytest.mark.parametrize('target', list(q.TARGETS))
def test_fixed_URL_scope_is_verified_with_no_DNS(target):
    url = q.TARGETS[target]
    host = 'aboutj.jleague.jp' if target in {'A2', 'B2'} else 'www.jleague.jp'
    assert q.validate_scope(target, url, host).hostname == host


def test_historical_sources_and_scope_are_retained_in_handoff():
    inventory = read('ACCESS_EVIDENCE_INVENTORY.json'); gaps = read('TERMS_GAP_MATRIX.json')
    old = json.loads((ROOT / 'research/nn_v2/phase2_5P/G3_UNKNOWN_CLASSIFICATION.json').read_bytes())
    historical = [r for r in gaps['rows'] if r['historical_id']]
    for a, b in zip(old['rows'], historical):
        assert a['id'] == b['historical_id'] and a['original_definition'] == b['original_definition']
        raw = (json.dumps(a['M_original_record'], sort_keys=True, ensure_ascii=True,
                          separators=(',', ':'), allow_nan=False)+'\n').encode()
        assert hashlib.sha256(raw).hexdigest() == b['source_record_SHA256']
    assert inventory['normative_counts'] == gaps['normative_counts'] == dict(PASS=15, FAIL=0, UNKNOWN=9)
    for row in inventory['rows']:
        assert row['terms']['status'] == 'UNKNOWN' and row['acquisition_authorized'] is False
    plan = read('P0_EVIDENCE_PRIORITY.json')['minimal_candidate']
    assert plan['fallback_exact_subset'] == ['A3', 'A4'] and plan['fallback_max_GET'] == 2
    assert plan['aboutj_deferred'] and plan['B1_B2_deferred']


def test_static_pure_imports_and_no_transport_or_storage_entrypoint():
    tree = ast.parse((OUT / 'access_evidence.py').read_text(encoding='utf8'))
    modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    modules |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert modules <= {'datetime', 'hashlib', 'urllib.parse', 're', 'json'}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {'open', 'eval', 'exec', '__import__', 'socket', 'subprocess', 'requests'}
    assert not any(isinstance(n, ast.Attribute) and n.attr in {'read_bytes', 'write_bytes', 'connect', 'urlopen', 'request', 'load', 'dump'} for n in ast.walk(tree))


@pytest.mark.parametrize('bad', [None, {}, [], 'UNKNOWN'])
def test_negative_malformed_inventory_fails_closed(bad):
    _, g, blobs, pins = sample()
    assert assess(bad, g, blobs, pins)['gate'] != 'NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY'
