"""R pre-send refusal checks and synthetic durable-attempt tests.

No HTTP, DNS, socket, process, ACL or Job API. This module cannot authorize
or invoke a live transport. File writes are for explicitly synthetic stores.
Exclusive file creation and fsync/readback are local tests, not evidence of
OS isolation, directory power-loss durability or live-client qualification.
"""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import Path
import json
import os

TARGETS = dict(A3='https://www.jleague.jp/general/kiyaku/',
               A4='https://www.jleague.jp/general/copyright/')
UA = 'J1AI-Research-Timing-Pilot/1.0'
TOKEN = 'Research-Timing-Pilot'
LIMITS = dict(max_attempts_per_URL=1, max_total_attempts=2, body_cap=1048576,
              connect_timeout_seconds=5, read_timeout_seconds=15,
              redirect=0, retry=0, external_resources=0)
CHECKS = ('source_binding', 'robots_applicability', 'robots_freshness_basis',
          'no_major_robots_uncertainty', 'bounded_conditions_inspection_basis',
          'known_conditions_review', 'TLS_client_qualification', 'proxy_policy',
          'operational_write_boundary', 'private_storage_identity',
          'exact_client_limits', 'durable_attempt_qualification')


class ReviewError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise ReviewError(reason)


def canonical(x):
    return (json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                       allow_nan=False)+'\n').encode()


def same(a, b):
    return type(a) is type(b) and (set(a) == set(b) and all(same(a[k], b[k]) for k in a)
        if type(a) is dict else len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
        if type(a) is list else a == b)


def utc(value):
    need(type(value) is str and 'T' in value, 'UTC_REQUIRED')
    x = datetime.fromisoformat(value)
    need(x.tzinfo is not None and x.utcoffset() == timedelta(0), 'UTC_REQUIRED')
    return x


def request(target):
    need(target in TARGETS, 'A3_A4_ONLY')
    return dict(target=target, URL=TARGETS[target], method='GET', user_agent=UA,
                product_token=TOKEN, purpose='CONDITIONS_INSPECTION_ONLY',
                limits=dict(LIMITS), cookie=None, authentication=False,
                certificate_verification=True, hostname_verification=True,
                G3_permit=False, G4_authority=False)


def validate_request(value):
    need(type(value) is dict and value.get('target') in TARGETS, 'A3_A4_ONLY')
    need(same(value, request(value['target'])), 'EXACT_REQUEST_IDENTITY_SCOPE_AND_LIMITS')
    return True


def synthetic_precheck(value, checks):
    out = dict(status='REJECTED', reasons=[], live_send_authorized=False,
               G3_permit=False, G4_authorized=False)
    try:
        validate_request(value)
        need(type(checks) is dict and set(checks) == set(CHECKS), 'PRECHECK_FIELDS')
        need(all(type(v) is str and v in {'PASS', 'DENY', 'UNKNOWN'} for v in checks.values()), 'PRECHECK_STATES')
        out['reasons'] = [k+':'+checks[k] for k in CHECKS if checks[k] != 'PASS']
        if not out['reasons']:
            out['status'] = 'SYNTHETIC_PRECHECK_COMPLETE_ONLY'
    except (ValueError, TypeError, KeyError) as exc:
        out['reasons'] = [str(exc)]
    return out


def require_live_preconditions(checks):
    """Used to demonstrate that the actual UNKNOWN evidence refuses a send.

    Even hypothetical all-PASS input cannot unlock a live client here.
    """
    out = synthetic_precheck(request('A3'), checks)
    need(out['status'] == 'SYNTHETIC_PRECHECK_COMPLETE_ONLY', 'PRE_SEND_HOLD:'+','.join(out['reasons']))
    raise ReviewError('NO_QUALIFIED_LIVE_CLIENT_IN_THIS_MODULE')


def validate_synthetic_response(value):
    need(type(value) is dict and value['kind'] == 'SYNTHETIC_R_RESPONSE', 'SYNTHETIC_ONLY')
    need(value['status'] == 200 and type(value['status']) is int, 'HTTP_STATUS_STOP')
    need(value['redirect_followed'] is False and value['retry_count'] == 0 and
         type(value['retry_count']) is int and value['resource_requests'] == 0 and
         type(value['resource_requests']) is int, 'NO_REDIRECT_RETRY_OR_RESOURCE')
    need(value['TLS_verified'] is True and value['hostname_verified'] is True, 'TLS_REQUIRED')
    body = value['body']
    need(type(body) is bytes and 0 < len(body) <= LIMITS['body_cap'], 'BODY_CAP')
    need(value['content_type'].lower().split(';')[0].strip() == 'text/html', 'EXPECTED_HTML')
    length = value['content_length']
    need(length is None or type(length) is int and length == len(body), 'CONTENT_LENGTH')
    need(type(value['expected_SHA256']) is str and sha256(body).hexdigest() == value['expected_SHA256'], 'READBACK_SHA256')
    need(value['E2'] == value['E3'] == value['E4'] == 'NOT_ACTUAL_SYNTHETIC_ONLY', 'SYNTHETIC_IS_NOT_EVIDENCE')
    return dict(status='SYNTHETIC_BYTES_VERIFIED', actual_E2=False, actual_E3=False,
                actual_E4=False, terms='UNKNOWN', server_observation_proven=False)


def no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 'DUPLICATE_JSON_KEY')
        out[key] = value
    return out


class SyntheticAttemptStore:
    """Append-only synthetic intent/result files; never a production ledger.

    A crash/partial intent consumes the filename and refuses reopening. No
    cleanup, repair, lock takeover, budget refund, live callback or retry.
    """
    def __init__(self, root, *, session='syn-R-session'):
        need(type(session) is str and session.startswith('syn-'), 'SYNTHETIC_SESSION_REQUIRED')
        self.root = Path(root).absolute()
        need(self.root.name.startswith('syn-'), 'SYNTHETIC_DIRECTORY_REQUIRED')
        self.session = session
        self.identity = dict(kind='SYNTHETIC_R_STORE_V1', session=session, targets=TARGETS,
                             scope='SYNTHETIC_ONLY_NOT_APPROVAL', live_transport=False)
        self._path_check()
        if not self.root.exists():
            self.root.mkdir()
        marker = self.root/'session.json'
        if marker.exists():
            need(self._read('session.json') == self.identity, 'SESSION_BINDING')
        else:
            need(not list(self.root.iterdir()), 'EMPTY_EXCLUSIVE_SYNTHETIC_STORE_REQUIRED')
            self._write('session.json', self.identity)
        self.inspect()

    def _path_check(self):
        for p in [self.root, *self.root.parents]:
            if p.exists():
                need(not p.is_symlink() and not getattr(p.lstat(), 'st_file_attributes', 0) & 1024, 'NO_REPARSE')

    def _write(self, name, payload):
        self._path_check()
        data = canonical(dict(payload=payload, SHA256=sha256(canonical(payload)).hexdigest()))
        with (self.root/name).open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        need((self.root/name).read_bytes() == data, 'FSYNC_READBACK')

    def _read(self, name):
        self._path_check()
        try:
            value = json.loads((self.root/name).read_bytes(), object_pairs_hook=no_duplicate_keys)
            need(set(value) == {'payload', 'SHA256'} and
                 sha256(canonical(value['payload'])).hexdigest() == value['SHA256'], 'LEDGER_HASH')
            return value['payload']
        except (ValueError, KeyError, TypeError) as exc:
            raise ReviewError('LEDGER_CORRUPTION') from exc

    def inspect(self):
        allowed = {'session.json', 'A3.intent.json', 'A3.result.json', 'A4.intent.json', 'A4.result.json'}
        need({p.name for p in self.root.iterdir()} <= allowed, 'UNKNOWN_LEDGER_FILE')
        intents, results = {}, {}
        for target in TARGETS:
            if (self.root/(target+'.intent.json')).exists():
                entry = self._read(target+'.intent.json')
                need(entry['session'] == self.session and entry['attempt_id'] == 'syn-R-'+target and
                     entry['kind'] == 'SYNTHETIC_CONSUMED_INTENT' and entry['consumed'] is True and
                     entry['transport_called'] is False, 'INTENT_BINDING')
                validate_request(entry['request'])
                need(entry['request']['target'] == target and
                     sha256(canonical(entry['request'])).hexdigest() == entry['request_SHA256'], 'REQUEST_HASH_BINDING')
                utc(entry['UTC'])
                intents[target] = entry
            if (self.root/(target+'.result.json')).exists():
                result = self._read(target+'.result.json')
                need(target in intents and result['attempt_id'] == intents[target]['attempt_id'] and
                     result['intent_SHA256'] == sha256(canonical(intents[target])).hexdigest(), 'RESULT_BINDING')
                need(result['outcome'] in {'SYNTHETIC_SUCCESS', 'TIMEOUT', 'CRASH_UNKNOWN_OUTCOME', 'SAVE_FAILED'}, 'OUTCOME')
                results[target] = result
        if 'A4' in intents:
            need(results.get('A3', {}).get('outcome') == 'SYNTHETIC_SUCCESS', 'A3_BEFORE_A4')
        return intents, results

    def consume(self, value, at_utc):
        validate_request(value)
        stamp = utc(at_utc)
        intents, results = self.inspect()
        target = value['target']
        need(target not in intents, 'ATTEMPT_ALREADY_CONSUMED_NO_RETRY')
        need(not any(r['outcome'] != 'SYNTHETIC_SUCCESS' for r in results.values()), 'GLOBAL_STOP')
        if target == 'A4':
            need(results.get('A3', {}).get('outcome') == 'SYNTHETIC_SUCCESS', 'A3_BEFORE_A4')
        payload = dict(kind='SYNTHETIC_CONSUMED_INTENT', session=self.session,
                       attempt_id='syn-R-'+target, request=value, request_SHA256=sha256(canonical(value)).hexdigest(),
                       approval_scope='SYNTHETIC_ONLY_NOT_APPROVAL', UTC=at_utc,
                       JST=stamp.astimezone(timezone(timedelta(hours=9))).isoformat(),
                       consumed=True, transport_called=False, retry_authorized=False)
        self._write(target+'.intent.json', payload)
        return payload

    def finish(self, target, outcome):
        need(target in TARGETS, 'A3_A4_ONLY')
        intents, _ = self.inspect()
        need(target in intents, 'INTENT_BEFORE_RESULT')
        need(outcome in {'SYNTHETIC_SUCCESS', 'TIMEOUT', 'CRASH_UNKNOWN_OUTCOME', 'SAVE_FAILED'}, 'OUTCOME')
        self._write(target+'.result.json', dict(attempt_id=intents[target]['attempt_id'], outcome=outcome,
                    intent_SHA256=sha256(canonical(intents[target])).hexdigest(), retry_authorized=False,
                    real_E2=False, real_E3=False, real_E4=False))
