"""Offline cache, virtual-clock and synthetic path qualification models.

No live permission, network, process or Windows policy interfaces. Conditional
cache usability never proves current content; path policy never proves OS ACLs.
"""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from pathlib import PureWindowsPath
import math
import re

STATES = ('PROVEN_OFFLINE', 'PROVEN_STATIC_ONLY', 'UNKNOWN', 'BLOCKED', 'REQUIRES_DYNAMIC_APPROVAL')
HOLDS = dict(B='HOLD', C='HOLD', D='HOLD', HISTORY='HOLD', PREDICTION='HOLD',
             Phase_A='BLOCKED', Phase_B='NOT_AUTHORIZED', G3='HOLD', G4='NOT_AUTHORIZED')
PROPOSED_TIMING = dict(kind='DRAFT_DEDICATED_CONDITIONS_WORKER_NOT_APPROVED',
    tcp_connect_seconds=5, TLS_handshake_seconds=5, read_idle_seconds=15,
    worker_wall_seconds=60, storage_total_seconds=10, cleanup_seconds=5,
    parent_wall_seconds=70, redirect=0, retry=0)


class QualificationError(ValueError):
    pass


def need(value, message):
    if not value:
        raise QualificationError(message)


def utc(value):
    need(type(value) is str and 'T' in value, 'UTC_REQUIRED')
    t = datetime.fromisoformat(value)
    need(t.tzinfo is not None and t.utcoffset() == timedelta(0), 'UTC_REQUIRED')
    return t.astimezone(timezone.utc)


def cache_review(raw, *, expected_SHA256, acquired_utc, reviewed_utc,
                 cache_control, unreachable_observed=None, project_policy=None):
    need(type(raw) is bytes and sha256(raw).hexdigest() == expected_SHA256, 'ORIGINAL_HASH_MISMATCH')
    age = (utc(reviewed_utc)-utc(acquired_utc)).total_seconds()
    need(age >= 0, 'CLOCK_ROLLBACK')
    need(unreachable_observed is None or type(unreachable_observed) is bool, 'UNREACHABLE_EVIDENCE_TYPE')
    need(cache_control is None or type(cache_control) is str, 'CACHE_CONTROL_TYPE')
    # RFC9309 SHOULD NOT >24h is a recommendation with an unreachable exception;
    # a separate approved rationale could exist, but none is silently invented.
    normative = 'CONDITIONAL_WITHIN_24H' if age <= 86400 else (
        'CONDITIONAL_UNREACHABLE_EXCEPTION' if unreachable_observed is True else 'UNKNOWN')
    project = 'UNKNOWN'
    if project_policy is not None:
        need(type(project_policy) is dict and set(project_policy) == {'kind', 'TTL_seconds'}, 'PROJECT_POLICY_SCHEMA')
        need(project_policy['kind'] == 'SYNTHETIC_POLICY_ONLY', 'NO_POLICY_ADOPTION_HERE')
        ttl = project_policy['TTL_seconds']
        need(type(ttl) is int and ttl > 0, 'TTL_MUST_BE_EXPLICIT')
        project = 'SYNTHETIC_WITHIN_TTL' if age <= ttl else 'SYNTHETIC_REVIEW_REQUIRED'
    return dict(NORMATIVE_CACHE_ELIGIBILITY=normative,
                PROJECT_FRESHNESS_POLICY=project, SOURCE_CURRENTNESS_EVIDENCE='UNKNOWN',
                FETCH_ELIGIBILITY='HOLD_OFFLINE_ONLY', age_seconds=age,
                cache_control_evidence='PRESENT_UNINTERPRETED' if cache_control is not None else 'UNKNOWN',
                normative_recommendation_is_project_TTL=False, age_alone_invalidates_original=False,
                cached_bytes_are_current_live_bytes=False, permit_ready=False, execution_authorized=False)


def require_no_authority(claim):
    need(type(claim) is dict and claim.get('scope') == 'OFFLINE_ONLY', 'OFFLINE_SCOPE')
    need(set(claim) == {'scope', 'terms', 'robots', 'E2', 'E3', 'holds', 'overall_access',
                       'permit_ready', 'G3_authorized', 'G4_authorized', 'live_send_authorized'}, 'AUTHORITY_SCHEMA')
    need(claim['overall_access'] == 'HOLD', 'TERMS_UNKNOWN_IS_NOT_OVERALL_ALLOW')
    need(claim.get('terms') == 'UNKNOWN' and claim.get('robots') in {'CONDITIONAL_FIXED_ALLOW', 'UNKNOWN', 'DENY'}, 'HISTORICAL_ACCESS_STATE')
    need(claim.get('E2') == claim.get('E3') == 'UNKNOWN', 'E1_IS_NOT_E2_E3')
    need(claim.get('holds') == HOLDS, 'HOLD_IMMUTABLE')
    need(all(claim.get(k) is False for k in ('permit_ready', 'G3_authorized', 'G4_authorized', 'live_send_authorized')), 'NO_OFFLINE_AUTHORITY')
    return True


def validate_qualification_item(item):
    need(type(item) is dict and item['status'] in STATES, 'QUALIFICATION_STATUS')
    need(item['method'] in {'OFFLINE', 'STATIC', 'UNPROVEN'}, 'QUALIFICATION_METHOD')
    need(item['actual_OS_or_transport_proven'] is False, 'NO_DYNAMIC_PASS_IN_S')
    need(item['status'] != 'PROVEN_OFFLINE' or item['method'] == 'OFFLINE', 'OFFLINE_PROOF_METHOD')
    need(item['status'] != 'PROVEN_STATIC_ONLY' or item['method'] == 'STATIC', 'STATIC_PROOF_METHOD')
    need(item['evidence'] and item['unproven'] and item['next_action'] and item['approval'] and
         item['stop_conditions'] and item['G3_impact'], 'HANDOFF_FIELDS_REQUIRED')
    if item['subject'] in {'real_Job', 'OS_write_deny', 'real_process_CAS', 'power_loss_durability'}:
        need(item['status'] in {'UNKNOWN', 'BLOCKED', 'REQUIRES_DYNAMIC_APPROVAL'} and item['method'] == 'UNPROVEN', 'STATIC_OR_FAKE_IS_NOT_DYNAMIC')
    return True


class VirtualDeadline:
    """Mock time only. A STOP result does not terminate an actual process."""
    CAPS = dict(dns=60, tcp=5, tls=5, read=15, hash=10, fsync=10, readback=10)
    def __init__(self):
        self.now = 0.0
        self.last = 0.0
        self.storage_started = None
        self.state = 'RESERVED_SYNTHETIC_CONSUMED'
        self.events = []
        self.transport_proven = False

    def step(self, phase, duration):
        need(self.state == 'RESERVED_SYNTHETIC_CONSUMED', 'TERMINAL_NO_RETRY')
        need(phase in self.CAPS and type(duration) in (int, float) and
             math.isfinite(duration) and duration >= 0, 'PHASE_DURATION')
        budget = min(self.CAPS[phase], 60-self.now)
        if phase in {'hash', 'fsync', 'readback'}:
            if self.storage_started is None:
                self.storage_started = self.now
            budget = min(budget, 10-(self.now-self.storage_started))
        if duration > budget or budget <= 0:
            self.now += max(0, budget)
            self.state = 'UNKNOWN_OUTCOME_STOP'
            self.events.append(dict(phase=phase, outcome='STOP', at=self.now))
            return False
        self.now += duration
        self.last = self.now
        self.events.append(dict(phase=phase, outcome='MODEL_COMPLETED', at=self.now))
        return True

    def stop_for_job_expiry(self, observed_at):
        need(type(observed_at) in (int, float) and math.isfinite(observed_at) and observed_at >= self.now, 'MONOTONIC_CLOCK')
        self.now = observed_at
        self.state = 'UNKNOWN_OUTCOME_STOP'
        return dict(logical_stop=True, consumed=True, retry=False, actual_Job_proven=False,
                    actual_child_cleanup_proven=False, cleanup_budget=5, parent_budget=70)


def path_policy(path, *, same_volume=True, reparse=False, same_user_can_write_production=True):
    """Pure Windows-path policy, not an effective-access check or race defense."""
    need(all(type(x) is bool for x in (same_volume, reparse, same_user_can_write_production)), 'PATH_FACT_TYPES')
    allowed = False
    if type(path) is str and '\x00' not in path:
        parts = re.split(r'[\\/]+', path)
        p = PureWindowsPath(path)
        roots = [PureWindowsPath('R:/syn-session/'+n) for n in ('staging', 'raw', 'ledger')]
        syntax_ok = p.is_absolute() and not path.startswith(('\\\\', '//')) and not any(x in {'.', '..'} for x in parts)
        syntax_ok = syntax_ok and not any(':' in x for x in p.parts[1:])
        allowed = syntax_ok and same_volume and not reparse and any(p == root or root in p.parents for root in roots)
    return dict(application_write_allowed=allowed, OS_WRITE_DENIAL='UNKNOWN',
                same_user_production_access_risk=same_user_can_write_production,
                actual_ACL_proven=False, TOCTOU_race_prevention_proven=False)
