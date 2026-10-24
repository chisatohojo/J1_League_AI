"""Synthetic append-only revisions and atomic-head staging experiments.

Only a directory named syn-* may be used. No production ledger, process or
transport API. File fsync/readback and os.replace are exercised; directory
power-loss durability and real process CAS remain unqualified.
"""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timedelta
import errno
import json
import os
import re


class LedgerError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise LedgerError(reason)


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)+'\n').encode()


def digest(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'DIGEST')


def timestamp(value):
    need(type(value) is str and 'T' in value, 'UTC_REQUIRED')
    dt = datetime.fromisoformat(value)
    need(dt.tzinfo is not None and dt.utcoffset() == timedelta(0), 'UTC_REQUIRED')
    return dt


def strict_pairs(pairs):
    result = {}
    for k, v in pairs:
        need(k not in result, 'DUPLICATE_JSON_KEY')
        result[k] = v
    return result


class StagingLedger:
    def __init__(self, root):
        self.root = Path(root).absolute()
        need(self.root.name.startswith('syn-'), 'SYNTHETIC_STAGING_ONLY')
        self._paths()
        if not self.root.exists():
            self.root.mkdir()
        if not (self.root/'head.json').exists():
            need(not list(self.root.iterdir()), 'ORPHANED_STORE_MANUAL_REVIEW')
            state = dict(kind='SYNTHETIC_S_LEDGER', revision=0, previous_state_SHA256=None, events=[])
            self._put('state-000000.json', state)
            self._put('head.json', dict(revision=0, state_SHA256=sha256(encoded(state)).hexdigest()))
        self.read()

    def _paths(self):
        for p in [self.root, *self.root.parents]:
            if p.exists():
                need(not p.is_symlink() and not getattr(p.lstat(), 'st_file_attributes', 0) & 1024, 'REPARSE_OR_LINK')

    def _put(self, name, value, fault=None):
        self._paths()
        raw = encoded(value)
        with (self.root/name).open('xb') as f:
            if fault == 'ENOSPC':
                raise OSError(errno.ENOSPC, 'synthetic storage full')
            if fault == 'EACCES':
                raise PermissionError(errno.EACCES, 'synthetic denied write')
            f.write(raw[:max(1, len(raw)//2)] if fault == 'partial' else raw)
            f.flush()
            os.fsync(f.fileno())
        if fault == 'partial':
            raise LedgerError('SYNTHETIC_INTERRUPTION_INCOMPLETE_WRITE')
        need((self.root/name).read_bytes() == raw, 'READBACK_HASH_MISMATCH')

    def _get(self, name):
        self._paths()
        try:
            raw = (self.root/name).read_bytes()
            value = json.loads(raw, object_pairs_hook=strict_pairs)
            need(raw == encoded(value), 'NON_CANONICAL_OR_BYTE_TAMPER')
            return value
        except (ValueError, TypeError, KeyError) as exc:
            raise LedgerError('CORRUPT_JSON') from exc

    @staticmethod
    def replay(events):
        identities, states, seen_request_hashes, targets = {}, {}, set(), set()
        last = None
        for sequence, e in enumerate(events, 1):
            need(set(e) == {'sequence', 'attempt_id', 'request_SHA256', 'target', 'state', 'UTC'}, 'EVENT_SCHEMA')
            need(type(e['sequence']) is int and e['sequence'] == sequence, 'SEQUENCE')
            need(type(e['attempt_id']) is str and re.fullmatch(r'syn-[A-Za-z0-9_-]+', e['attempt_id']), 'SYNTHETIC_ID')
            digest(e['request_SHA256']); need(e['target'] in {'A3', 'A4'}, 'TARGET_SCOPE')
            at = timestamp(e['UTC']); need(last is None or at >= last, 'CLOCK_ROLLBACK'); last = at
            aid = e['attempt_id']; identity = (e['request_SHA256'], e['target']); old = states.get(aid)
            need(aid not in identities or identities[aid] == identity, 'IMMUTABLE_ATTEMPT_IDENTITY')
            if old is None:
                need(e['state'] == 'RESERVED' and e['request_SHA256'] not in seen_request_hashes and e['target'] not in targets, 'ONCE_ONLY_RESERVATION')
                need(not any(s in {'UNKNOWN_OUTCOME', 'ABORTED'} for s in states.values()), 'GLOBAL_STOP')
                need(e['target'] != 'A4' or any(identities[k][1] == 'A3' and s == 'COMPLETED' for k, s in states.items()), 'A3_BEFORE_A4')
                seen_request_hashes.add(e['request_SHA256']); targets.add(e['target'])
            else:
                transitions = dict(RESERVED={'STARTED', 'ABORTED', 'UNKNOWN_OUTCOME'}, STARTED={'SENT', 'UNKNOWN_OUTCOME'}, SENT={'COMPLETED', 'UNKNOWN_OUTCOME'})
                need(e['state'] in transitions.get(old, set()), 'TERMINAL_OR_ILLEGAL_TRANSITION')
            identities[aid] = identity; states[aid] = e['state']
        return states, identities

    def read(self, *, expected_head_SHA256=None):
        head_bytes = (self.root/'head.json').read_bytes()
        head_SHA = sha256(head_bytes).hexdigest()
        need(expected_head_SHA256 is None or head_SHA == expected_head_SHA256, 'TRUSTED_HEAD_MISMATCH')
        head = self._get('head.json')
        need(set(head) == {'revision', 'state_SHA256'} and type(head['revision']) is int and head['revision'] >= 0, 'HEAD_SCHEMA')
        n = head['revision']; digest(head['state_SHA256'])
        allowed = {'head.json'} | {f'state-{i:06d}.json' for i in range(n+1)} | {f'claim-{i:06d}.json' for i in range(1, n+1)}
        need({p.name for p in self.root.iterdir()} == allowed, 'ORPHANED_OR_INCOMPLETE_COMMIT_HOLD')
        previous_SHA, previous_events = None, []
        for i in range(n+1):
            state = self._get(f'state-{i:06d}.json')
            need(set(state) == {'kind', 'revision', 'previous_state_SHA256', 'events'} and state['kind'] == 'SYNTHETIC_S_LEDGER' and type(state['revision']) is int and state['revision'] == i and state['previous_state_SHA256'] == previous_SHA, 'REVISION_CHAIN')
            need(type(state['events']) is list and len(state['events']) == i and (i == 0 or state['events'][:-1] == previous_events), 'APPEND_ONLY_HISTORY')
            if i:
                claim = self._get(f'claim-{i:06d}.json')
                need(claim == dict(expected_revision=i-1, expected_state_SHA256=previous_SHA, event=state['events'][-1]), 'CLAIM_BINDING')
            self.replay(state['events'])
            previous_SHA = sha256(encoded(state)).hexdigest(); previous_events = state['events']
        need(previous_SHA == head['state_SHA256'], 'STATE_HASH_MISMATCH')
        return dict(revision=n, head_SHA256=head_SHA, state_SHA256=previous_SHA, events=state['events'])

    def commit(self, event, *, expected_revision, expected_head_SHA256, fault=None):
        snapshot = self.read(expected_head_SHA256=expected_head_SHA256)
        need(type(expected_revision) is int and snapshot['revision'] == expected_revision, 'CAS_CONFLICT')
        n = expected_revision+1
        need(type(event) is dict and event['sequence'] == n, 'EVENT_REVISION')
        events = snapshot['events']+[event]
        self.replay(events)
        claim = dict(expected_revision=expected_revision, expected_state_SHA256=snapshot['state_SHA256'], event=event)
        self._put(f'claim-{n:06d}.json', claim, fault if fault in {'ENOSPC', 'EACCES', 'partial'} else None)
        if fault == 'after_claim':
            raise LedgerError('SYNTHETIC_INTERRUPTION_AFTER_CLAIM')
        state = dict(kind='SYNTHETIC_S_LEDGER', revision=n, previous_state_SHA256=snapshot['state_SHA256'], events=events)
        self._put(f'state-{n:06d}.json', state)
        if fault == 'after_state':
            raise LedgerError('SYNTHETIC_INTERRUPTION_AFTER_STATE')
        new_head = dict(revision=n, state_SHA256=sha256(encoded(state)).hexdigest())
        self._put('head.pending.json', new_head)
        if fault == 'replace_denied':
            raise PermissionError(errno.EACCES, 'synthetic atomic replace denied')
        self._paths()
        os.replace(self.root/'head.pending.json', self.root/'head.json')
        need((self.root/'head.json').read_bytes() == encoded(new_head), 'ATOMIC_HEAD_READBACK')
        if fault == 'after_replace':
            raise LedgerError('SYNTHETIC_INTERRUPTION_AFTER_REPLACE')
        return self.read()

    def event(self, aid, request_SHA256, target, state, at_utc):
        snapshot = self.read()
        return dict(sequence=snapshot['revision']+1, attempt_id=aid, request_SHA256=request_SHA256,
                    target=target, state=state, UTC=at_utc)
