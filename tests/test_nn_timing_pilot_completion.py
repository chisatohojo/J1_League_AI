"""Offline tests for the independent five-GET Phase 2.5B-3 permit."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import socket

import pytest

from test_nn_timing_evidence_pilot import p as core

path = os.environ.get("J1AI_TIMING_COMPLETION_GUARD")
if not path:
    pytest.skip("Set J1AI_TIMING_COMPLETION_GUARD to the sealed offline guard", allow_module_level=True)
source = Path(path)
if hashlib.sha256(source.read_bytes()).hexdigest() != "f61e38544e4653a09d52c2dd8a63d835abd08f2806bfd392622e61b2fdc5fb32":
    raise ValueError("Completion guard SHA mismatch")
spec = importlib.util.spec_from_file_location("timing_completion_guard_local", source)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline permit tests cannot access the network")
    monkeypatch.setattr(socket, "create_connection", forbidden)


def population():
    original = [{"identity": "fixture:"+str(i), "data_site_match_id": str(i), "series": "ongoing",
                 "url": "https://data.j-league.or.jp/SFMS02/?match_card_id="+str(i)} for i in range(1,13)]
    acquired = [{"url": r["url"]} for r in original[:7]]
    pending = [{**r, "complete_expected_header": core.header_expectation({"source_season_label": "2026/27",
                "competition": "Ｊ１", "round_label": "第１節第１日"}, "ongoing")} for r in original[7:]]
    return original, acquired, pending


def witness(raw=b"not found", status=404, fetched="2026-10-20T00:00:00+00:00"):
    return raw, {"requested_url": guard.ROBOTS, "final_url": guard.ROBOTS, "status": status,
                 "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "fetched_at_utc": fetched}


NOW = datetime(2026,10,20,9,0,tzinfo=timezone.utc)


def test_exact_difference_and_full_year_headers_are_prepared_offline():
    original, acquired, pending = population()
    assert guard.verify_remainder(original, acquired, pending) == {"original":12,"acquired":7,"remaining":5,"new_targets":0}
    assert all("2026/27" in r["complete_expected_header"] for r in pending)


@pytest.mark.parametrize("change", ["six", "repeat", "changed_identity", "missing_year", "unknown_host"])
def test_no_extra_URLs_retries_identity_changes_or_incomplete_headers(change):
    original, acquired, pending = population()
    if change == "six": pending.append(dict(pending[0]))
    if change == "repeat": pending[0] = dict(pending[1])
    if change == "changed_identity": pending[0]["identity"] = "another"
    if change == "missing_year": pending[0]["complete_expected_header"] = "明治安田Ｊ１リーグ第１節第１日"
    if change == "unknown_host":
        original[7]["url"] = pending[0]["url"] = "https://evil.test/SFMS02/?match_card_id=8"
    with pytest.raises(ValueError):
        guard.verify_remainder(original, acquired, pending)


def test_stale_404_is_not_current_permission_and_does_not_spend_the_five_GET_budget():
    original, acquired, pending = population()
    raw, meta = witness(fetched="2026-09-11T08:31:15.689077+00:00")
    permit = guard.preflight(original, acquired, pending, raw, meta, NOW)
    assert permit["status"] == "PERMIT_HELD" and not permit["network_enabled"]
    assert permit["max_total_GET"] == 5 and permit["robots_or_notices_requests_authorized"] == 0
    assert not permit["remaining_276_authorized"]
    assert set(permit["already_acquired_URLs_forbidden"]).isdisjoint(permit["allowed_URLs"])


@pytest.mark.parametrize("status", [403,429,500])
def test_unknown_or_restricted_access_response_holds(status):
    raw, meta = witness(status=status)
    assert not guard.access_gate(raw,meta,[population()[2][0]["url"]],NOW)["network_enabled"]


@pytest.mark.parametrize("raw", [b"User-agent: *\nDisallow: /SFMS02/\n", b"User-agent: *\nCrawl-delay: 6\n"])
def test_disallow_or_longer_crawl_delay_does_not_enable_network(raw):
    raw, meta = witness(raw,status=200)
    assert not guard.access_gate(raw,meta,[population()[2][0]["url"]],NOW)["network_enabled"]


def test_fresh_nonrestrictive_witness_can_only_prepare_original_five():
    original, acquired, pending = population()
    raw, meta = witness()
    permit = guard.preflight(original,acquired,pending,raw,meta,NOW)
    assert permit["network_enabled"] and len(permit["allowed_URLs"]) == 5
    assert permit["max_total_body_bytes"] == 10*1024*1024
    assert permit["redirects_followed"] == permit["automatic_retries"] == permit["parallel_downloads"] == 0


def test_access_witness_SHA_change_rejected_and_future_clock_is_not_freshness():
    raw, meta = witness()
    with pytest.raises(ValueError,match="SHA_or_URL"):
        guard.access_gate(raw+b"change",meta,[],NOW)
    raw, meta = witness(fetched="2026-10-21T00:00:00+00:00")
    assert not guard.access_gate(raw,meta,[],NOW)["network_enabled"]
