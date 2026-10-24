"""G2 memory-only request boundary. No HTTP client, worker or transport API.

Actual access/permit gates remain closed. Synthetic gate fixtures qualify only
an in-memory sink, never live authority. Historical L/N records are immutable.
Canonical JSON is an input representation, not HTTP wire bytes or a signature.
"""
from dataclasses import dataclass
import json
import re
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator
from research.nn_v2.phase2_5N import ua_adoption as g1
from research.nn_v2.phase2_5M import impact_review as m

legacy = m.contract
VERSION = 'NNV2_G2_OFFLINE_ADAPTER_V1'
SCOPE = 'NN_V2_G2_OFFLINE_ONLY'
REQUEST_SCHEMA = 'NNV2_G2_CANDIDATE_REQUEST_V1'
E1_SCHEMA = 'NNV2_G2_E1_OFFLINE_V1'
G1_FILE_SHA = 'ce88f2430954647e6f9cf0f3e92703867c23288c2e09ed16085b543848e58b78'
G1_SCHEMA_SHA = 'ace72dce9845f753d616f1c9232d76380d703c1f7c01175e7a67fff64c03839b'
GATE_ORDER = ('G1', 'request_schema', 'method', 'URL_scope', 'robots', 'terms',
              'permit', 'identity', 'redirect_retry', 'final_pre_send')


class OfflineError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise OfflineError(reason)


def same(a, b):
    return g1.canonical(a) == g1.canonical(b)


def ident(value):
    need(type(value) is str and re.fullmatch(r'syn-[A-Za-z0-9_-]{1,80}', value) is not None,
         'SYNTHETIC_ID_REQUIRED')


@dataclass(frozen=True)
class IdentityProvider:
    """Caller supplies bytes; this provider does not read config/env/files."""
    manifest_bytes: bytes
    candidate_bytes: bytes
    schema_bytes: bytes
    matrix_bytes: bytes

    def config(self, now_utc):
        need(g1.sha(self.manifest_bytes) == G1_FILE_SHA, 'G1_MANIFEST_HASH')
        need(g1.sha(self.schema_bytes) == G1_SCHEMA_SHA, 'G1_SCHEMA_HASH')
        need(g1.sha(self.matrix_bytes) == g1.MATRIX_SHA256, 'MATRIX_HASH')
        value = g1.strict_json(self.manifest_bytes)
        schema = g1.strict_json(self.schema_bytes)['schemas']['UA_ADOPTION_MANIFEST.json']
        Draft202012Validator.check_schema(schema)
        need(not list(Draft202012Validator(schema).iter_errors(value)), 'G1_SCHEMA')
        g1.verify_manifest(value, candidate_bytes=self.candidate_bytes, verified_at_utc=now_utc)
        return value

    def row(self, target_id, now_utc):
        self.config(now_utc)
        need(type(target_id) is str and target_id in m.TARGETS, 'FIXED_TARGET_REQUIRED')
        return next(x for x in g1.strict_json(self.matrix_bytes)['rows'] if x['id'] == target_id)


def build_request(provider, *, request_id, run_id, target_id, exact_url, method,
                  source_revision, created_utc, now_utc, scope=SCOPE):
    need(type(provider) is IdentityProvider and scope == SCOPE, 'RESEARCH_ONLY_PROVIDER_SCOPE')
    config = provider.config(now_utc)
    ident(request_id); ident(run_id)
    need(method == 'GET', 'GET_ONLY')
    row = provider.row(target_id, now_utc)
    need(type(exact_url) is str and exact_url == row['URL'] == m.TARGETS[target_id], 'EXACT_URL_SCOPE')
    need(source_revision == g1.BASE_COMMIT, 'FIXED_SOURCE_REVISION')
    need(g1.utc(config['adopted_utc']) <= g1.utc(created_utc) <= g1.utc(now_utc), 'CREATION_CLOCK')
    url = urlsplit(exact_url)
    body = dict(schema_version=REQUEST_SCHEMA, scope=SCOPE, adapter_revision=VERSION,
        request_id=request_id, run_id=run_id, target_id=target_id, method=method, exact_url=exact_url,
        origin='https://' + url.netloc, host=url.hostname, port=443, path=url.path, query=url.query,
        user_agent=config['HTTP_USER_AGENT'], product_token=config['ROBOTS_PRODUCT_TOKEN'],
        source_evidence_revision=source_revision, source_evidence_manifest_SHA256=g1.MATRIX_SHA256,
        robots_reference_SHA256=row['robots']['reference_SHA256'],
        created_utc=created_utc, G1_manifest_SHA256=G1_FILE_SHA,
        G1_canonical_SHA256=g1.sha(g1.canonical(config)), G1_state=config['adoption_state'],
        robots_state=row['robots']['decision'], robots_conditional_only=True,
        terms_state='UNKNOWN', permit_state='UNAPPROVED', permit_id=None,
        redirect=0, retry=0, parallel=0, execution_authorized=False, history_admission=False)
    return dict(request=body, SHA256=g1.sha(g1.canonical(body)))


def verify_request(prepared, provider, now_utc):
    need(type(prepared) is dict and set(prepared) == {'request', 'SHA256'} and
         type(prepared['request']) is dict, 'REQUEST_SCHEMA')
    body = prepared['request']
    keys = ('request_id', 'run_id', 'target_id', 'exact_url', 'method', 'created_utc', 'scope')
    need(all(k in body for k in keys) and 'source_evidence_revision' in body, 'REQUEST_FIELDS')
    rebuilt = build_request(provider, **{k: body[k] for k in keys},
        source_revision=body['source_evidence_revision'], now_utc=now_utc)
    need(same(prepared, rebuilt), 'REQUEST_IDENTITY_POLICY_OR_HASH')
    return body


def client_input(prepared, provider, now_utc):
    """Match legacy conn.request(method, path, headers=...) DATA only, never call it."""
    r = verify_request(prepared, provider, now_utc)
    return dict(method=r['method'], request_target=r['path'], headers={
        'Host': r['host'], 'User-Agent': r['user_agent'],
        'Accept-Encoding': 'identity', 'Connection': 'close'})


def actual_gates(prepared, provider, now_utc):
    r = verify_request(prepared, provider, now_utc)
    states = dict.fromkeys(GATE_ORDER, 'PASS')
    states['robots'] = {'ALLOW': 'PASS', 'DENY': 'DENY', 'UNKNOWN': 'UNKNOWN'}[r['robots_state']]
    states['terms'] = states['permit'] = states['final_pre_send'] = 'UNKNOWN'
    return [dict(gate=k, status=states[k]) for k in GATE_ORDER]


def e1_record(prepared, provider, *, final_client_input, now_utc):
    r = verify_request(prepared, provider, now_utc)
    need(same(final_client_input, client_input(prepared, provider, now_utc)), 'FINAL_CLIENT_INPUT_CHANGED')
    value = dict(schema_version=E1_SCHEMA, scope=SCOPE, evidence_level='E1', offline_only=True,
        adapter_revision=VERSION, request_id=r['request_id'], run_id=r['run_id'],
        created_utc=r['created_utc'], evidence_utc=now_utc,
        G1_manifest_SHA256=G1_FILE_SHA, G1_configuration_loaded_offline=True,
        source_evidence_revision=r['source_evidence_revision'], prepared_request=prepared,
        final_client_input=final_client_input, actual_gates=actual_gates(prepared, provider, now_utc),
        legacy_facet_reference='NNV2_UA_EVIDENCE_V1; separate G2 representation, not a legacy live record',
        E2='UNKNOWN', E3='UNKNOWN', E4_new_acquisition=False,
        transport_outcome=None, response_status=None, response_hash=None,
        real_permit_issued=False, execution_authorized=False, history_admission=False,
        B='HOLD', C='HOLD', D='HOLD', HISTORY='HOLD', PREDICTION='HOLD',
        Phase_A='BLOCKED', Phase_B='NOT_AUTHORIZED')
    return dict(value, record_SHA256=g1.sha(g1.canonical(value)))


def verify_e1(record, prepared, provider, now_utc):
    need(type(record) is dict and type(record.get('evidence_utc')) is str, 'E1_SCHEMA')
    need(g1.utc(record['evidence_utc']) <= g1.utc(now_utc), 'E1_FUTURE')
    expected = e1_record(prepared, provider, final_client_input=client_input(prepared, provider, now_utc),
                         now_utc=record['evidence_utc'])
    need(same(record, expected), 'E1_BINDING_OR_PROHIBITED_PROMOTION')
    return dict(status='PASS_OFFLINE_E1_ONLY', execution_authorized=False)


def simulation_input(prepared, provider, now_utc):
    """Explicit synthetic.invalid subview for unchanged L plan checker only."""
    r = verify_request(prepared, provider, now_utc)
    return legacy.prepare(method='GET', target_url='https://synthetic.invalid' + r['path'],
        headers=[['Host', 'synthetic.invalid'], ['User-Agent', r['user_agent']],
                 ['X-J1AI-Request-ID', r['request_id']]],
        request_id=r['request_id'], execution_id=r['run_id'], permit_id='syn-g2-plan',
        source_revision='syn-frozen-M', intended_user_agent=r['user_agent'], product_token=r['product_token'])


def simulation_gates(prepared, provider, fixture, now_utc):
    """Caller fixture is explicitly untrusted simulation, not site/permit evidence."""
    verify_request(prepared, provider, now_utc)
    if fixture is None:
        return dict(offline_sink_allowed=False, execution_authorized=False,
                    robots='UNKNOWN', terms='UNKNOWN', permit='UNKNOWN', reason='NO_SYNTHETIC_FIXTURE')
    fields = {'kind', 'scope', 'prepared_SHA256', 'request_id', 'robots_raw', 'robots_SHA256', 'terms', 'plan'}
    need(type(fixture) is dict and set(fixture) == fields and
         fixture['kind'] == 'G2_SYNTHETIC_GATE_FIXTURE_V1' and fixture['scope'] == 'SYNTHETIC_ONLY',
         'NO_REAL_PERMIT_OR_SITE_ASSERTION')
    need(fixture['prepared_SHA256'] == prepared['SHA256'] and
         fixture['request_id'] == prepared['request']['request_id'], 'FIXTURE_REQUEST_BINDING')
    need(fixture['terms'] in {'PASS', 'DENY', 'UNKNOWN'}, 'TERMS_FIXTURE_STATE')
    p = simulation_input(prepared, provider, now_utc)
    robots = m.robots.evaluate(fixture['robots_raw'], source_host='synthetic.invalid',
        target_url=p['canonical']['target_url'], header=prepared['request']['user_agent'],
        declared_tokens=[prepared['request']['product_token']], expected_raw_SHA256=fixture['robots_SHA256'],
        specification_SHA256=m.robots.subset.SPEC_SHAS, profile=m.robots.subset.SYNTHETIC_PROFILE)['layer1']
    plan = legacy.check_plan(p, fixture['plan'], now_utc)
    status = {'ALLOW': 'PASS', 'DENY': 'DENY', 'UNKNOWN': 'UNKNOWN', 'UNAPPROVED': 'UNKNOWN'}
    result = dict(robots=status[robots['decision']], terms=fixture['terms'], permit=status[plan['decision']])
    return dict(result, offline_sink_allowed=all(v == 'PASS' for v in result.values()),
                execution_authorized=False, reason='SYNTHETIC_SUBVIEW_ONLY_NOT_HOST_ACCESS_OR_G3')


class MemorySink:
    """Fixed implementation, no injectable transport/callback or response generator."""
    def __init__(self, fault=None):
        need(fault in {None, 'BEFORE_ACCEPT', 'AFTER_ACCEPT', 'READBACK'}, 'SYNTHETIC_FAULT')
        self.fault = fault
        self.records = {}

    def accept(self, body):
        record = g1.strict_json(body)
        key = record['request_id']
        need(key not in self.records, 'DUPLICATE_SINK_REQUEST')
        need(self.fault != 'BEFORE_ACCEPT', 'SYNTHETIC_SINK_FAILURE_BEFORE')
        self.records[key] = body
        need(self.fault != 'AFTER_ACCEPT', 'SYNTHETIC_SINK_FAILURE_AFTER')

    def readback(self, key):
        return self.records[key] + (b' ' if self.fault == 'READBACK' else b'')


class OfflineSession:
    """One-use in-memory run; failure is terminal, uncertain delivery never retries."""
    def __init__(self, provider, run_id):
        need(type(provider) is IdentityProvider, 'RESEARCH_PROVIDER_REQUIRED')
        ident(run_id)
        self.provider, self.run_id = provider, run_id
        self.requests, self.targets, self.attempts = {}, set(), []
        self.stopped = False

    def prepare(self, **inputs):
        need(not self.stopped, 'RUN_STOPPED_NO_RESUME')
        try:
            value = build_request(self.provider, run_id=self.run_id, **inputs)
            r = value['request']
            need(r['request_id'] not in self.requests and r['exact_url'] not in self.targets, 'DUPLICATE_REQUEST_OR_URL')
            self.requests[r['request_id']] = g1.canonical(value)
            self.targets.add(r['exact_url'])
            return value
        except Exception:
            self.stopped = True
            raise

    def deliver(self, prepared, sink, *, fixture, final_client_input, now_utc):
        need(not self.stopped, 'RUN_STOPPED_NO_RESUME')
        attempt = dict(status='STARTED_OFFLINE_ONLY', request_id=None, real_requests=0)
        self.attempts.append(attempt)
        try:
            r = verify_request(prepared, self.provider, now_utc)
            attempt['request_id'] = r['request_id']
            need(r['run_id'] == self.run_id and self.requests.get(r['request_id']) == g1.canonical(prepared), 'SESSION_REQUEST_BINDING')
            need(not any(x['request_id'] == r['request_id'] for x in self.attempts[:-1]), 'DUPLICATE_DELIVERY')
            need(type(sink) is MemorySink, 'ONLY_FIXED_MEMORY_SINK')
            record = e1_record(prepared, self.provider, final_client_input=final_client_input, now_utc=now_utc)
            gates = simulation_gates(prepared, self.provider, fixture, now_utc)
            need(gates['offline_sink_allowed'], 'OFFLINE_GUARD_STOP:' + gates['reason'])
            body = g1.canonical(record)
            attempt['E1_SHA256'] = g1.sha(body)
            MemorySink.accept(sink, body)
            attempt['status'] = 'ACCEPTED_AWAITING_READBACK'
            readback = MemorySink.readback(sink, r['request_id'])
            need(body == readback, 'SINK_READBACK_SHA')
            verify_e1(g1.strict_json(readback), prepared, self.provider, now_utc)
            attempt.update(status='COMPLETED_OFFLINE_ONLY', readback_SHA256=g1.sha(readback))
            return dict(E1=record, simulation=gates, real_execution_authorized=False)
        except Exception as exc:
            attempt.update(status='STOPPED_OFFLINE_ONLY', failure=type(exc).__name__)
            self.stopped = True
            raise
