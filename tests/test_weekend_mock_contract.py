"""Pure packet/state tests only. No worker, filesystem publication or model."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
import socket
import subprocess

import pytest

from src.modeling import weekend_mock_contract as c

REV = "a" * 64
NOW = "2026-10-29T22:00:00+00:00"  # Friday 07:00 JST


@pytest.fixture(autouse=True)
def no_connections_or_child_processes(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("No network, DNS, child process or OS command allowed in pure tests")
    for owner, names in [(socket, ["getaddrinfo", "create_connection"]),
                         (socket.socket, ["connect", "connect_ex", "bind", "listen"]),
                         (subprocess, ["Popen", "run", "call", "check_call", "check_output"]),
                         (os, ["system", "startfile", "spawnl", "spawnv"])]:
        for name in names:
            monkeypatch.setattr(owner, name, forbidden, raising=False)


def packet(friday="2026-10-30"):
    start = date.fromisoformat(friday)
    frozen = datetime.fromisoformat(friday + "T07:00:00+09:00").astimezone(timezone.utc)
    ratings, targets, features = {}, [], []
    for i, offset in enumerate([0] + [1] * 4 + [2] * 4 + [3]):
        home, away = f"mock-team-{2*i+1:03}", f"mock-team-{2*i+2:03}"
        ratings.update({home: 1500.0 + i, away: 1500.0 - i})
        key = f"mock-fixture-{i+1:03}"
        targets.append(dict(fixture_key=key, match_id=f"mock-match-{i+1:03}", match_date=str(start+timedelta(days=offset)),
            kickoff_time="19:00", home_team_id=home, away_team_id=away, match_id_namespace="synthetic_mock"))
        features.append(dict(fixture_key=key, elo_diff=ratings[home]-ratings[away]))
    value = dict(format_version=c.REQUEST, scope=c.SCOPE, request_id="1"*64, source_revision=REV,
        source_receipt_sha256="b"*64, reservation_sha256="c"*64,
        source_ready_at_utc=(frozen-timedelta(hours=9)).isoformat(), frozen_at_utc=frozen.isoformat(),
        created_at_utc=frozen.isoformat(), deadline_at_utc=(frozen+timedelta(seconds=30)).isoformat(),
        weekend_start=friday, ratings=ratings, ratings_sha256=c.digest(ratings), targets=targets, features=features)
    return reseal(value)


def reseal(value):
    value["ratings_sha256"] = c.digest(value["ratings"])
    value["snapshot_sha256"] = c.snapshot_id(value)
    value["batch_id"] = c.batch_id(value)
    return value


def response(request):
    # Literal synthetic response, not the output of any estimator or worker.
    p = c.decode(request)
    return dict(format_version=c.RESPONSE, scope=c.SCOPE, mock_identity=c.MOCK,
        request_id=p["request_id"], request_sha256=hashlib.sha256(request).hexdigest(), batch_id=p["batch_id"],
        source_revision=p["source_revision"], snapshot_sha256=p["snapshot_sha256"], status="OK",
        completed_at_utc=p["created_at_utc"],
        results=[dict(fixture_key=t["fixture_key"], probabilities=[0.2, 0.3, 0.5]) for t in p["targets"]])


def validate(raw, now=NOW):
    return c.validate_request(raw, now_utc=now, expected_source_revision=REV)


def validate_reply(raw, reply, **kwargs):
    return c.validate_response(raw, reply, now_utc=NOW, expected_source_revision=REV, **kwargs)


def test_ten_targets_common_ratings_exact_snapshot_and_detached_results():
    p = packet(); raw = c.encode(p); saved = deepcopy(p)
    got = validate(raw)
    assert len(got["targets"]) == 10 and p == saved
    assert [f["elo_diff"] for f in got["features"]] == [float(i*2) for i in range(10)]
    reply = c.encode(response(raw))
    assert len(validate_reply(raw, reply)["results"]) == 10
    got["ratings"]["mock-team-001"] = 0
    assert validate(raw)["ratings"]["mock-team-001"] == 1500


@pytest.mark.parametrize("friday", ["2026-10-30", "2027-01-01", "2027-12-31"])
def test_pure_calendar_boundaries(friday):
    p = packet(friday)
    assert len(validate(c.encode(p), p["created_at_utc"])["targets"]) == 10
    assert p["targets"][-1]["match_date"] == str(date.fromisoformat(friday)+timedelta(days=3))


@pytest.mark.parametrize("field,value", [
    ("scope", "PRODUCTION"), ("format_version", "champion-weekend-v2"), ("request_id", "bad"),
    ("source_revision", "d"*64), ("source_revision", "bad"), ("source_receipt_sha256", ""),
    ("reservation_sha256", "c"*63), ("batch_id", "d"*64), ("snapshot_sha256", "e"*64),
    ("ratings_sha256", "0"*64), ("source_ready_at_utc", "2026-10-29T22:00:00.000001+00:00"),
    ("source_ready_at_utc", "2026-10-28T21:59:59+00:00"), ("frozen_at_utc", "2026-10-29T21:59:59+00:00"),
    ("created_at_utc", "2026-10-29T22:00:00"), ("created_at_utc", "2026-10-30T07:00:00+09:00"),
    ("deadline_at_utc", "2026-10-29T22:00:31+00:00"), ("deadline_at_utc", NOW),
    ("weekend_start", "2026-10-31"), ("targets", []), ("features", []), ("ratings", []),
])
def test_request_rejects_bad_contract(field, value):
    p = packet(); p[field] = value
    with pytest.raises(c.ContractError): validate(c.encode(p))


@pytest.mark.parametrize("mutation", ["unknown", "duplicate", "team", "real_id", "namespace", "score", "outside", "kickoff", "feature", "extra_rating"])
def test_rehashed_request_still_checks_synthetic_identity_and_common_map(mutation):
    p = packet()
    if mutation == "unknown": p["unknown"] = True
    elif mutation == "duplicate": p["targets"][1] = deepcopy(p["targets"][0])
    elif mutation == "team": p["targets"][0]["home_team_id"] = p["targets"][0]["away_team_id"]
    elif mutation == "real_id": p["targets"][0]["match_id"] = "101101"
    elif mutation == "namespace": p["targets"][0]["match_id_namespace"] = "jleague_match_page"
    elif mutation == "score": p["targets"][0]["result"] = "2"
    elif mutation == "outside": p["targets"][0]["match_date"] = "2026-11-03"
    elif mutation == "kickoff": p["targets"][0]["kickoff_time"] = "07:00"
    elif mutation == "feature": p["features"][0]["elo_diff"] += 175
    else: p["ratings"]["mock-team-999"] = 1500
    reseal(p)
    with pytest.raises(c.ContractError): validate(c.encode(p))


@pytest.mark.parametrize("number", [True, "1500", float("nan"), float("inf"), -float("inf")])
def test_nonfinite_bool_or_text_ratings_never_enter_contract(number):
    p = packet(); p["ratings"]["mock-team-001"] = number
    with pytest.raises(c.ContractError): validate(c.encode(p))


@pytest.mark.parametrize("raw", [b"", b"{}"*40000, b"[]\n", b"{", b'{}', b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'\xef\xbb\xbf{}\n', b'\xff'],
    ids=["empty", "oversize", "array", "truncated", "noncanonical", "duplicate-key", "NaN", "BOM", "invalid-utf8"])
def test_incomplete_duplicate_noncanonical_or_oversize_json_rejected(raw):
    with pytest.raises(c.ContractError): c.decode(raw)


@pytest.mark.parametrize("now", ["2026-10-29T21:59:59+00:00", "2026-10-29T22:00:30.000001+00:00"])
def test_request_time_limits(now):
    with pytest.raises(c.ContractError): validate(c.encode(packet()), now)


@pytest.mark.parametrize("field,value", [("request_id", "2"*64), ("batch_id", "f"*64), ("source_revision", "d"*64),
    ("snapshot_sha256", "f"*64), ("request_sha256", "f"*64), ("mock_identity", "real-worker"),
    ("scope", "PRODUCTION"), ("format_version", "other"), ("status", "FAILED"),
    ("completed_at_utc", "2026-10-29T22:00:01+00:00")])
def test_response_requires_parent_request_and_exact_mock_binding(field, value):
    raw = c.encode(packet()); r = response(raw); r[field] = value
    with pytest.raises(c.ContractError): validate_reply(raw, c.encode(r))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "reordered", "extra", "shape", "negative", "sum", "bool", "unknown"])
def test_response_has_all_ten_results_once_in_request_order(mutation):
    raw = c.encode(packet()); r = response(raw)
    if mutation == "missing": r["results"].pop()
    elif mutation == "duplicate": r["results"][1] = deepcopy(r["results"][0])
    elif mutation == "reordered": r["results"].reverse()
    elif mutation == "extra": r["results"].append(deepcopy(r["results"][0]))
    elif mutation == "shape": r["results"][0]["probabilities"] = [0.2, 0.8]
    elif mutation == "negative": r["results"][0]["probabilities"] = [-0.2, 0.3, 0.9]
    elif mutation == "sum": r["results"][0]["probabilities"] = [0.2, 0.3, 0.6]
    elif mutation == "bool": r["results"][0]["probabilities"] = [False, 0, 1]
    else: r["results"][0]["source"] = "official"
    with pytest.raises(c.ContractError): validate_reply(raw, c.encode(r))


def test_response_consumption_and_missing_receipt_are_not_success():
    raw = c.encode(packet()); reply = c.encode(response(raw))
    with pytest.raises(c.ContractError): validate_reply(raw, reply, seen_request_ids=frozenset({"1"*64}))
    with pytest.raises(c.ContractError):
        c.validate_simulated_receipt(b"", raw, reply, now_utc=NOW, expected_source_revision=REV)


def test_immutable_ledger_and_terminal_states_refuse_retry_and_duplicate_commit():
    raw = c.encode(packet()); state = c.claim_request((), raw, now_utc=NOW, expected_source_revision=REV)
    assert state[0].status == "CLAIMED"
    with pytest.raises(c.ContractError): c.advance(state, "1"*64, "COMMITTED")
    verified = c.advance(state, "1"*64, "RESPONSE_VERIFIED")
    committed = c.advance(verified, "1"*64, "COMMITTED")
    failed = c.advance(state, "1"*64, "FAILED")
    assert state[0].status == "CLAIMED" and committed[0].status == "COMMITTED"
    for terminal in (committed, failed):
        with pytest.raises(c.ContractError): c.advance(terminal, "1"*64, "COMMITTED")
        with pytest.raises(c.ContractError): c.claim_request(terminal, raw, now_utc=NOW, expected_source_revision=REV)
        p = packet(); p["request_id"] = "2"*64
        with pytest.raises(c.ContractError): c.claim_request(terminal, c.encode(p), now_utc=NOW, expected_source_revision=REV)


@pytest.mark.parametrize("state", [[], ("bad",), (c.Claim("bad", "a"*64, "b"*64),), (c.Claim("1"*64, "a"*64, "b"*64, "BAD"),)])
def test_invalid_ledger_rejected(state):
    with pytest.raises(c.ContractError): c.claim_request(state, c.encode(packet()), now_utc=NOW, expected_source_revision=REV)


@pytest.mark.parametrize("phase", ["CLAIMED", "RESPONSE_VERIFIED"])
@pytest.mark.parametrize("reason", ["STOP", "CANCEL", "TIMEOUT", "CRASH"])
def test_stop_logic_is_terminal_without_process_or_receipt_effects(phase, reason):
    raw = c.encode(packet())
    original = c.claim_request((), raw, now_utc=NOW, expected_source_revision=REV)
    active = original if phase == "CLAIMED" else c.advance(original, "1"*64, phase)
    stopped = c.stop_request(active, "1"*64, reason=reason)
    assert active[0].status == phase and original[0].status == "CLAIMED"
    assert stopped[0].status == "FAILED" and stopped[0].failure_reason == reason
    for next_state in ("RESPONSE_VERIFIED", "COMMITTED", "CLAIMED", "FAILED"):
        with pytest.raises(c.ContractError): c.advance(stopped, "1"*64, next_state)
    with pytest.raises(c.ContractError): c.stop_request(stopped, "1"*64, reason=reason)
    with pytest.raises(c.ContractError): c.claim_request(stopped, raw, now_utc=NOW, expected_source_revision=REV)


@pytest.mark.parametrize("reason", ["STOP", "CANCEL", "TIMEOUT", "CRASH", "unknown", "CONTRACT_FAILURE", None, []])
def test_stop_after_commit_or_invalid_reason_is_refused(reason):
    raw = c.encode(packet())
    state = c.claim_request((), raw, now_utc=NOW, expected_source_revision=REV)
    committed = c.advance(c.advance(state, "1"*64, "RESPONSE_VERIFIED"), "1"*64, "COMMITTED")
    with pytest.raises(c.ContractError): c.stop_request(committed, "1"*64, reason=reason)
    if reason not in ("STOP", "CANCEL", "TIMEOUT", "CRASH"):
        with pytest.raises(c.ContractError): c.stop_request(state, "1"*64, reason=reason)


def test_stop_unknown_request_does_not_change_another_claim():
    raw = c.encode(packet())
    state = c.claim_request((), raw, now_utc=NOW, expected_source_revision=REV)
    with pytest.raises(c.ContractError): c.stop_request(state, "2"*64, reason="STOP")
    assert state[0].status == "CLAIMED" and state[0].failure_reason is None


@pytest.mark.parametrize("status,reason", [("FAILED", None), ("FAILED", "unknown"), ("CLAIMED", "STOP"), ("COMMITTED", "STOP")])
def test_forged_failure_state_or_reason_is_refused(status, reason):
    ledger = (c.Claim("1"*64, "a"*64, "b"*64, status, reason),)
    with pytest.raises(c.ContractError): c.check_ledger(ledger)


def test_simulated_receipt_explicitly_denies_os_evidence_and_history_admission():
    raw = c.encode(packet()); reply = c.encode(response(raw))
    receipt = c.simulated_receipt(raw, reply, now_utc=NOW, expected_source_revision=REV)
    p = c.validate_simulated_receipt(receipt, raw, reply, now_utc=NOW, expected_source_revision=REV)
    assert p["evidence_kind"] == "PURE_FUNCTION_SIMULATION" and p["result_count"] == 10
    for flag in ["worker_started", "batch_published", "os_isolation_verified", "durability_verified", "history_admission"]:
        assert p[flag] is False
        changed = deepcopy(p); changed[flag] = True
        with pytest.raises(c.ContractError):
            c.validate_simulated_receipt(c.encode(changed), raw, reply, now_utc=NOW, expected_source_revision=REV)


def test_request_raw_change_does_not_match_old_response():
    raw = c.encode(packet()); reply = c.encode(response(raw)); p = packet(); p["request_id"] = "2"*64
    with pytest.raises(c.ContractError): validate_reply(c.encode(p), reply)


@pytest.mark.parametrize("replacement", [b"Enable", b"Default", b"enable", b"", b" Disable "])
def test_sandbox_inert_template_rejects_weaker_policy(replacement):
    assert c.validate_sandbox_template(c.sandbox_template())
    with pytest.raises(c.ContractError): c.validate_sandbox_template(c.sandbox_template().replace(b"Disable", replacement, 1))


@pytest.mark.parametrize("tag", ["MappedFolders", "LogonCommand", "HostFolder", "Unknown"])
def test_sandbox_template_never_admits_host_mapping_or_commands(tag):
    changed = c.sandbox_template().replace(b"</Configuration>", f"<{tag}/></Configuration>".encode())
    with pytest.raises(c.ContractError): c.validate_sandbox_template(changed)
