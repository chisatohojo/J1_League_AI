"""Pure synthetic packet checks. No worker, launcher, persistence or model API.

These functions certify data and logical transitions only. They cannot authorize
execution, establish OS isolation, or certify a durable receipt/publication.
"""
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re

SCOPE = "SYNTHETIC_ONLY"
REQUEST = "weekend-mock-request-v1"
RESPONSE = "weekend-mock-response-v1"
RECEIPT = "weekend-mock-contract-receipt-v1"
MOCK = "j1ai-weekend-contract-mock-v1"
MAX_BYTES = 65536
TARGET_KEYS = {"fixture_key", "match_id", "match_date", "kickoff_time", "home_team_id", "away_team_id", "match_id_namespace"}
REQUEST_KEYS = {"format_version", "scope", "request_id", "batch_id", "source_revision", "source_receipt_sha256",
    "reservation_sha256", "source_ready_at_utc", "frozen_at_utc", "created_at_utc", "deadline_at_utc", "weekend_start",
    "ratings", "ratings_sha256", "targets", "features", "snapshot_sha256"}
RESPONSE_KEYS = {"format_version", "scope", "mock_identity", "request_id", "request_sha256", "batch_id",
    "source_revision", "snapshot_sha256", "status", "completed_at_utc", "results"}


class ContractError(ValueError):
    pass


def need(ok, reason):
    if not ok:
        raise ContractError(reason)


def encode(value):
    try:
        return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf8")
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        raise ContractError("encoding") from exc


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def decode(raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "body_size_or_type")
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate_key")
            result[key] = value
        return result
    def constant(value):
        raise ContractError("nonfinite_json")
    try:
        result = json.loads(raw.decode("utf8"), object_pairs_hook=pairs, parse_constant=constant)
        need(type(result) is dict and encode(result) == raw, "canonical_object_required")
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ContractError("invalid_packet") from exc


def hash_value(value):
    need(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "sha256")
    return value


def utc(value):
    try:
        need(type(value) is str, "UTC_string")
        result = datetime.fromisoformat(value)
        need(result.tzinfo is not None and result.utcoffset() == timedelta(0), "UTC_required")
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError) as exc:
        raise ContractError("invalid_UTC") from exc


def finite(value):
    try:
        need(type(value) in (int, float) and math.isfinite(value), "finite_number")
    except OverflowError as exc:
        raise ContractError("finite_number") from exc
    return value


def snapshot_id(p):
    return digest({k: p[k] for k in ("source_revision", "source_receipt_sha256", "reservation_sha256",
        "source_ready_at_utc", "frozen_at_utc", "weekend_start", "ratings", "ratings_sha256", "targets", "features")})


def batch_id(p):
    return digest(dict(scope=SCOPE, snapshot_sha256=p["snapshot_sha256"], targets=p["targets"]))


def validate_request(raw, *, now_utc, expected_source_revision):
    p = decode(raw)
    try:
        need(set(p) == REQUEST_KEYS and p["format_version"] == REQUEST and p["scope"] == SCOPE, "request_schema_scope")
        for key in ("request_id", "batch_id", "source_revision", "source_receipt_sha256", "reservation_sha256", "ratings_sha256", "snapshot_sha256"):
            hash_value(p[key])
        need(p["source_revision"] == hash_value(expected_source_revision), "unpinned_source_revision")
        start = date.fromisoformat(p["weekend_start"])
        need(start.isoformat() == p["weekend_start"] and start.weekday() == 4, "Friday_required")
        cutoff = datetime.fromisoformat(str(start) + "T07:00:00+09:00").astimezone(timezone.utc)
        ready, frozen, created, deadline = [utc(p[k]) for k in ("source_ready_at_utc", "frozen_at_utc", "created_at_utc", "deadline_at_utc")]
        need(ready <= cutoff <= frozen <= created < deadline <= cutoff + timedelta(minutes=15), "chronology")
        need(cutoff - ready <= timedelta(hours=24) and deadline - created <= timedelta(seconds=30), "freshness_or_deadline")
        need(created <= utc(now_utc) <= deadline, "expired_or_future_request")
        targets, ratings, features = p["targets"], p["ratings"], p["features"]
        need(type(targets) is list and 1 <= len(targets) <= 40 and type(ratings) is dict and type(features) is list, "request_shape")
        need(len(features) == len(targets), "feature_count")
        for key, value in ratings.items():
            need(re.fullmatch(r"mock-team-[0-9]{3}", key) is not None, "synthetic_team")
            finite(value)
        keys, match_ids, teams = set(), set(), set()
        for target, feature in zip(targets, features):
            need(type(target) is dict and set(target) == TARGET_KEYS, "target_schema")
            need(type(feature) is dict and set(feature) == {"fixture_key", "elo_diff"}, "feature_schema")
            need(type(target["fixture_key"]) is str and re.fullmatch(r"mock-fixture-[0-9]{3}", target["fixture_key"]) is not None, "synthetic_fixture")
            need(type(target["match_id"]) is str and re.fullmatch(r"mock-match-[0-9]{3}", target["match_id"]) is not None
                 and target["match_id_namespace"] == "synthetic_mock", "synthetic_identity")
            need(target["fixture_key"] not in keys and target["match_id"] not in match_ids, "duplicate_fixture")
            keys.add(target["fixture_key"]); match_ids.add(target["match_id"])
            home, away = target["home_team_id"], target["away_team_id"]
            need(type(home) is str and type(away) is str and home in ratings and away in ratings and home != away, "team_identity")
            need(home not in teams and away not in teams, "repeated_weekend_team")
            teams.update((home, away))
            day = date.fromisoformat(target["match_date"])
            need(day.isoformat() == target["match_date"] and start <= day <= start + timedelta(days=3), "outside_weekend")
            need(type(target["kickoff_time"]) is str and re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", target["kickoff_time"]) is not None, "kickoff_format")
            kickoff = datetime.fromisoformat(target["match_date"] + "T" + target["kickoff_time"] + ":00+09:00")
            need(deadline < kickoff, "kickoff_elapsed")
            finite(feature["elo_diff"])
            need(feature["fixture_key"] == target["fixture_key"] and feature["elo_diff"] == ratings[home] - ratings[away], "common_rating_feature")
        need(set(ratings) == teams and digest(ratings) == p["ratings_sha256"], "rating_map")
        need(snapshot_id(p) == p["snapshot_sha256"] and batch_id(p) == p["batch_id"], "snapshot_or_batch_sha")
        return p
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise ContractError("invalid_request") from exc


def validate_response(request, response, *, now_utc, expected_source_revision, seen_request_ids=frozenset()):
    p = validate_request(request, now_utc=now_utc, expected_source_revision=expected_source_revision)
    r = decode(response)
    try:
        need(set(r) == RESPONSE_KEYS and r["format_version"] == RESPONSE and r["scope"] == SCOPE, "response_schema_scope")
        need(r["mock_identity"] == MOCK and r["status"] == "OK", "mock_only_success")
        need(p["request_id"] not in seen_request_ids, "duplicate_response")
        need(all(r[k] == p[k] for k in ("request_id", "batch_id", "source_revision", "snapshot_sha256")), "response_binding")
        need(r["request_sha256"] == hashlib.sha256(request).hexdigest(), "request_bytes_sha")
        need(utc(p["created_at_utc"]) <= utc(r["completed_at_utc"]) <= utc(now_utc) <= utc(p["deadline_at_utc"]), "response_chronology")
        need(type(r["results"]) is list and len(r["results"]) == len(p["targets"]), "result_count")
        for item, target in zip(r["results"], p["targets"]):
            need(type(item) is dict and set(item) == {"fixture_key", "probabilities"} and item["fixture_key"] == target["fixture_key"], "result_identity_order")
            values = item["probabilities"]
            need(type(values) is list and len(values) == 3, "probability_shape")
            for v in values:
                finite(v); need(0 <= v <= 1, "probability_range")
            need(math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-12), "probability_sum")
        return r
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise ContractError("invalid_response") from exc


@dataclass(frozen=True)
class Claim:
    request_id: str
    batch_id: str
    request_sha256: str
    status: str = "CLAIMED"
    failure_reason: str | None = None


TRANSITIONS = {"CLAIMED": {"RESPONSE_VERIFIED", "FAILED"}, "RESPONSE_VERIFIED": {"COMMITTED", "FAILED"}, "COMMITTED": set(), "FAILED": set()}
FAILURE_REASONS = frozenset({"CONTRACT_FAILURE", "STOP", "CANCEL", "TIMEOUT", "CRASH"})


def check_ledger(ledger):
    need(type(ledger) is tuple and all(type(c) is Claim for c in ledger), "ledger_type")
    for c in ledger:
        for value in (c.request_id, c.batch_id, c.request_sha256):
            hash_value(value)
        need(type(c.status) is str and c.status in TRANSITIONS, "ledger_state")
        need((c.status == "FAILED" and type(c.failure_reason) is str and c.failure_reason in FAILURE_REASONS)
             or (c.status != "FAILED" and c.failure_reason is None), "failure_reason")
    need(len({c.request_id for c in ledger}) == len({c.batch_id for c in ledger}) == len(ledger), "ledger_duplicates")


def claim_request(ledger, request, *, now_utc, expected_source_revision):
    check_ledger(ledger)
    p = validate_request(request, now_utc=now_utc, expected_source_revision=expected_source_revision)
    need(not any(c.request_id == p["request_id"] or c.batch_id == p["batch_id"] for c in ledger), "request_or_batch_already_consumed")
    return ledger + (Claim(p["request_id"], p["batch_id"], hashlib.sha256(request).hexdigest()),)


def advance(ledger, request_id, status):
    """Logical simulation only; no receipt, process or filesystem is committed."""
    check_ledger(ledger)
    need(any(c.request_id == request_id for c in ledger), "unknown_request")
    current = next(c for c in ledger if c.request_id == request_id)
    need(type(status) is str and status in TRANSITIONS[current.status], "transition_or_resume_denied")
    return tuple(replace(c, status=status, failure_reason="CONTRACT_FAILURE" if status == "FAILED" else None)
                 if c == current else c for c in ledger)


def stop_request(ledger, request_id, *, reason):
    """Model a terminal failure only. Does not stop any process or persist state."""
    need(type(reason) is str and reason in FAILURE_REASONS - {"CONTRACT_FAILURE"}, "stop_reason")
    failed = advance(ledger, request_id, "FAILED")
    return tuple(replace(c, failure_reason=reason) if c.request_id == request_id else c for c in failed)


def simulated_receipt(request, response, *, now_utc, expected_source_revision):
    r = validate_response(request, response, now_utc=now_utc, expected_source_revision=expected_source_revision)
    result = dict(format_version=RECEIPT, scope=SCOPE, evidence_kind="PURE_FUNCTION_SIMULATION",
        request_id=r["request_id"], batch_id=r["batch_id"], source_revision=r["source_revision"],
        request_sha256=hashlib.sha256(request).hexdigest(), response_sha256=hashlib.sha256(response).hexdigest(),
        result_count=len(r["results"]), worker_started=False, batch_published=False,
        os_isolation_verified=False, durability_verified=False, history_admission=False)
    return encode(dict(result, receipt_sha256=digest(result)))


def validate_simulated_receipt(raw, request, response, *, now_utc, expected_source_revision):
    need(decode(raw) == decode(simulated_receipt(request, response, now_utc=now_utc, expected_source_revision=expected_source_revision)), "receipt_mismatch")
    return decode(raw)


def sandbox_template():
    """Inert closed template: no mapping, logon command, network or clipboard."""
    return ("<Configuration>\n  <Networking>Disable</Networking>\n"
        "  <ClipboardRedirection>Disable</ClipboardRedirection>\n  <VGpu>Disable</VGpu>\n</Configuration>\n").encode("utf8")


def validate_sandbox_template(raw):
    need(type(raw) is bytes and raw == sandbox_template(), "not_the_closed_sandbox_template")
    return True
