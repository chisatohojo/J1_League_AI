"""Offline pilot boundaries. No test may open an actual network connection."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl

import pytest

from test_jleague_hyakunen_source import detail

# The user restricts GitHub additions to aggregates/specifications/SHA/tests.
# Restore the local implementation from the verified backup to run this suite.
implementation = os.environ.get("J1AI_TIMING_PILOT_IMPLEMENTATION")
if not implementation:
    pytest.skip("Set J1AI_TIMING_PILOT_IMPLEMENTATION to the sealed local implementation", allow_module_level=True)
implementation_path = Path(implementation)
if hashlib.sha256(implementation_path.read_bytes()).hexdigest() != "009236881c349d5600054bca94ab57d9f7c79001ce25af7432a2f4cabbfafcad":
    raise ValueError("Local pilot implementation SHA mismatch")
module_spec = importlib.util.spec_from_file_location("nn_timing_evidence_pilot_local", implementation_path)
p = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(p)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic tests forbid real network IO")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    class SyntheticClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 20, tzinfo=timezone.utc)
    monkeypatch.setattr(p, "datetime", SyntheticClock)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    folder = tmp_path / "J1AI/NNResearch-phase2_5B_2-20261020-000000"
    folder.mkdir(parents=True)
    return folder


def row(mid="1"):
    return {"identity": "jleague_data_site_sfms02:" + mid, "data_site_match_id": mid,
            "url": "https://data.j-league.or.jp/SFMS02/?match_card_id=" + mid,
            "series": "hyakunen", "source_date": "2026-02-06",
            "source_reported_kickoff": "2026-02-06T19:03:00+09:00",
            "selection_record_sha256": "a"*64,
            "home_score_90": 1, "away_score_90": 1, "pk_played": True,
            "extra_time_played": False, "home_team_id": "team_0001", "away_team_id": "team_0002"}


@pytest.mark.parametrize("url", [
    "http://data.j-league.or.jp/SFMS02/?match_card_id=1",
    "https://data.j-league.or.jp.evil.test/SFMS02/?match_card_id=1",
    "https://user@data.j-league.or.jp/SFMS02/?match_card_id=1",
    "https://data.j-league.or.jp:443/SFMS02/?match_card_id=1",
    "https://data.j-league.or.jp/SFMS02/?match_card_id=2",
    "https://data.j-league.or.jp/SFMS02/?match_card_id=%31",
    "https://data.j-league.or.jp/SFMS02/?match_card_id=1&x=2",
    "https://data.j-league.or.jp/SFMS02/?match_card_id=1#fragment",
])
def test_url_id_and_host_strictness(url):
    with pytest.raises(ValueError, match="URL_ID_or_host"):
        p.checked_url(url, "1")


def test_page_cap_and_no_duplicate_url():
    p.validate_selection([row(str(i+1)) for i in range(12)])
    for rows in ([], [row(str(i+1)) for i in range(13)], [row(), row()]):
        with pytest.raises(ValueError):
            p.validate_selection(rows)


def test_deterministic_stratified_selection_is_subset_of_exact_saved_links():
    matrix, missing = [], []
    for series, count in (("hyakunen", 189), ("ongoing", 99)):
        for i in range(count):
            r = row(str((1000 if series == "hyakunen" else 2000)+i))
            r.update(series=series, source_date=(date(2026, 1, 1)+timedelta(days=i)).isoformat(),
                     pk_played=i % 2 == 0, date_or_kickoff_changes_in_saved_revisions=i>=79,
                     binding_sha256="b"*64 if 79 <= i <= 82 else None)
            r["sfms02_candidate_url_from_saved_listing"] = r["url"]
            matrix.append(r)
            missing.append({"identity": r["identity"], "url": r["url"], "data_site_match_id": r["data_site_match_id"]})
    selected = p.select_candidates(missing, matrix)
    assert selected == p.select_candidates(list(reversed(missing)), list(reversed(matrix)))
    assert len(selected) == 12 and sum(r["series"] == "hyakunen" for r in selected) == 6
    assert {r["url"] for r in selected} <= {r["url"] for r in missing}


def test_rate_limit_is_at_least_five_seconds_after_response_completion():
    current, sleeps = [12.0], []
    def sleep(delay):
        sleeps.append(delay); current[0] += delay
    p.wait_gap(10.0, now=lambda: current[0], sleep=sleep)
    assert sleeps == [3.0] and current[0] == 15.0
    p.wait_gap(10.0, now=lambda: current[0], sleep=sleep)
    assert sleeps == [3.0]


class FakeResponse:
    def __init__(self, body=b"<html>ok</html>", status=200, headers=None):
        self.body, self.status, self.pos = body, status, 0
        self.headers = headers or [("Content-Type", "text/html;charset=UTF-8")]
    def getheaders(self):
        return self.headers
    def read(self, size):
        chunk = self.body[self.pos:self.pos+size]; self.pos += len(chunk)
        return chunk


def fetch(root, response=None, failure=None):
    folder = root / "snapshot/request_01"; folder.mkdir(parents=True)
    calls = []
    class Connection:
        def __init__(self, host, **kwargs):
            assert host == p.HOST and kwargs["port"] == 443 and kwargs["timeout"] == 10
            context = kwargs["context"]
            assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
        def request(self, *args, **kwargs):
            calls.append(args)
            if failure:
                raise failure
        def getresponse(self):
            return response or FakeResponse()
        def close(self):
            pass
    meta = p.fetch_one(row(), folder, "b"*64, connection_factory=Connection)
    assert len(calls) == 1
    assert meta["sha256"] == p.digest((folder/"raw.html").read_bytes())
    assert meta["request_sha256"] == p.digest((folder/"request.json").read_bytes())
    assert json.loads((folder/"metadata.json").read_bytes()) == meta
    return meta, folder


def test_tls_timeout_sha_and_repeated_request_rejection(root):
    meta, folder = fetch(root)
    assert meta["success"] and meta["request_attempts"] == 1
    with pytest.raises(ValueError, match="worker_output_not_empty"):
        p.fetch_one(row(), folder, "b"*64)


def test_actual_acquisition_cannot_be_silently_backdated_to_another_month(root, monkeypatch):
    class OtherMonth(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(p, "datetime", OtherMonth)
    folder = root/"snapshot/request_01"; folder.mkdir(parents=True)
    with pytest.raises(ValueError, match="actual_acquisition_month_mismatch"):
        p.fetch_one(row(), folder, "b"*64)
    assert not list(folder.iterdir())


@pytest.mark.parametrize("code", [403, 429, 500])
def test_denied_status_saved_once_and_never_retried(root, code):
    meta, _ = fetch(root, FakeResponse(status=code))
    assert not meta["success"] and meta["status"] == code and meta["automatic_retries"] == 0


@pytest.mark.parametrize("destination", ["https://evil.test/", "https://www.jleague.jp/", "/SFMS02/other"])
def test_redirect_is_saved_without_following_or_requesting_destination(root, destination):
    meta, _ = fetch(root, FakeResponse(status=302, headers=[("Location", destination)]))
    assert not meta["success"] and "redirect" in meta["error"]


def test_timeout_causes_one_failed_attempt_without_retry(root):
    meta, _ = fetch(root, failure=TimeoutError("synthetic timeout"))
    assert not meta["success"] and "TimeoutError" in meta["error"]


def test_body_cap_is_enforced_and_truncation_is_not_a_success(root):
    meta, _ = fetch(root, FakeResponse(body=b"a"*(p.MAX_BODY+1)))
    assert not meta["success"] and meta["bytes"] == p.MAX_BODY and not meta["complete_body"]


def test_original_source_paths_and_filename_escape_are_rejected(tmp_path, root):
    with pytest.raises(ValueError, match="output_outside_new_research_root"):
        p.new_file(tmp_path, "original.html", b"do not write")
    assert not (tmp_path/"original.html").exists()
    with pytest.raises(ValueError, match="unsafe_filename"):
        p.new_file(root, "../original.html", b"do not write")
    p.new_file(root, "once.json", b"{}")
    with pytest.raises(FileExistsError):
        p.new_file(root, "once.json", b"replace")


def test_reparse_point_is_refused(tmp_path, monkeypatch):
    real = Path.lstat
    class Reparse:
        st_mode = 0
        st_file_attributes = 1024
    monkeypatch.setattr(Path, "lstat", lambda self: Reparse() if self == tmp_path else real(self))
    with pytest.raises(ValueError, match="reparse_point_rejected"):
        p.no_reparse(tmp_path/"new")


HEADER = "明治安田Ｊ１百年構想リーグ EASTグループ 第１節第１日"


class Master:
    def resolve_team_id(self, name, **kwargs):
        return {"Home ＦＣ": "team_0001", "Away ＦＣ": "team_0002"}[name]


def page(remarks="", **changes):
    top = "".join(f'<h2>公式記録</h2><p class="t-txt">{HEADER}</p>' for _ in range(2))
    info = '<!-- A12 Start --><table><tbody><tr>' + "".join(
        '<td>'+v+'</td>' for v in ["2026/02/06", "19:03", "Stadium", "100", "Fine", "20", "40%"]
    ) + '</tr></tbody></table><!-- A12 End -->'
    return (top + detail(pk=(4,3), **changes) + '<!-- A10 End -->▲：IN▽：OUT' + remarks + info).encode('utf8')


def test_strict_parser_recognizes_empty_remarks_without_claiming_original_schedule():
    report = p.analyze(page(), row(), Master(), HEADER)
    assert report["status"] == "PARSE_VERIFIED_FINAL_RECORD_ONLY"
    assert report["remarks_structure"] == "VERIFIED_EMPTY_A10_A12_TEMPLATE"
    assert not report["historical_publication_as_of_proven"] and not report["original_announcement_proven"]


def test_telemetry_error_dictionary_is_not_an_actual_http_denial():
    raw = page() + b'<script>const TOO_MANY={message:"429: Too Many Requests"};</script>'
    assert p.analyze(raw, row(), Master(), HEADER)["status"] == "PARSE_VERIFIED_FINAL_RECORD_ONLY"
    denied = page() + b'<p>Too Many Requests</p>'
    assert p.analyze(denied, row(), Master(), HEADER)["status"] == "HOLD"


def test_full_ongoing_season_header_is_prepared_before_network():
    record = {"source_season_label": "2026/27", "competition": "Ｊ１", "round_label": "第１節第１日"}
    expected = p.header_expectation(record, "ongoing")
    assert p.normal(expected) == "2026/27明治安田J1リーグ第1節第1日"
    r = row(); r.update(series="ongoing")
    raw = page().decode("utf8").replace(HEADER, expected).encode("utf8")
    assert p.analyze(raw, r, Master(), expected)["status"] == "PARSE_VERIFIED_FINAL_RECORD_ONLY"
    assert p.analyze(raw, r, Master(), expected.replace("2026/27", ""))["status"] == "HOLD"


@pytest.mark.parametrize("changes", [{"source_season_label": "2027/28"}, {"competition": "Ｊ２"}])
def test_header_preparation_does_not_accept_another_competition(changes):
    record = {"source_season_label": "2026/27", "competition": "Ｊ１", "round_label": "第１節第１日", **changes}
    with pytest.raises(ValueError, match="unapproved_ordinary_header_source"):
        p.header_expectation(record, "ongoing")


@pytest.mark.parametrize("raw", [
    page(match_id="2"), page().replace(b"2026/02/06", b"2026/02/07"),
    page().replace(b"19:03", b"19:04"), page().replace(b"A12", b"UNKNOWN"),
    page(remarks='<!-- A11 Start --><p>雷雨で中断、翌日に再開</p><!-- A11 End -->'),
    page(remarks='<p>リーグ中断期間が終了し再開</p>'),
])
def test_ambiguous_notes_unknown_structure_and_identity_conflict_hold(raw):
    report = p.analyze(raw, row(), Master(), HEADER)
    assert report["status"] == "HOLD" and not report["actual_interruption_proven"]


def test_cached_robots_disallow_stops_before_any_request():
    raw = b"User-agent: *\nDisallow: /SFMS02/\n"
    meta = {"requested_url": "https://data.j-league.or.jp/robots.txt", "final_url": "https://data.j-league.or.jp/robots.txt",
            "status": 200, "sha256": p.digest(raw), "bytes": len(raw), "fetched_at_utc": "2026-10-20T00:00:00Z"}
    with pytest.raises(ValueError, match="robots_disallow"):
        p.cached_robots(raw, meta, [row()["url"]])


def test_parent_deadline_stops_entire_pilot_and_cannot_resume(root, monkeypatch):
    import subprocess
    import src.collect.teams
    rows = [row("1"), row("2")]
    selection_sha = p.new_file(root, "selection.json", p.encoded(rows))
    permit = {"selection_sha256": selection_sha, "allowed_host": p.HOST, "max_pages": 12,
              "timeout_seconds": 10, "interval_seconds": 5.0, "max_body_bytes": p.MAX_BODY,
              "automatic_retries": 0, "all_prechecks_passed": True, "required_input_sha256": {},
              "snapshot_directory": str(root/"snapshot"), "team_master_path": "unused",
              "expected_headers": {r["identity"]: HEADER for r in rows}}
    permit_sha = p.new_file(root, "preflight.json", p.encoded(permit))
    monkeypatch.setattr(src.collect.teams, "load_team_master", lambda path: Master())
    calls = []
    def timeout(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 10
        raise subprocess.TimeoutExpired(command, 10)
    monkeypatch.setattr(p.subprocess, "run", timeout)
    report = p.acquire(root/"preflight.json", permit_sha)
    assert len(calls) == 1 and report["status"] == "HOLD_EVIDENCE_ACQUISITION"
    assert report["not_attempted"] == [rows[1]["identity"]]
    with pytest.raises(ValueError, match="unsafe_snapshot_output"):
        p.acquire(root/"preflight.json", permit_sha)
    assert len(calls) == 1


def test_continuation_cannot_use_unknown_review_or_change_original_targets(root):
    original = [row("1"), row("2")]
    original_sha = p.new_file(root, "original.json", p.encoded(original))
    review_sha = p.new_file(root, "review.json", p.encoded({"status": "HOLD", "stop_cause": "UNKNOWN"}))
    permit = {"original_selection_path": str(root/"original.json"), "original_selection_sha256": original_sha,
              "offline_review_path": str(root/"review.json"), "offline_review_sha256": review_sha,
              "continuation_reason": "OFFLINE_PROVEN_TELEMETRY_FALSE_POSITIVE", "prior_snapshot_seals": []}
    with pytest.raises(ValueError, match="outside_original_selection"):
        p.continuation_budget(permit, [row("3")])
    with pytest.raises(ValueError, match="offline_proof"):
        p.continuation_budget(permit, [row("2")])


@pytest.mark.parametrize("http_status", [200, 403, 429])
def test_continuation_budget_never_retries_used_url_or_bypasses_real_denial(root, http_status):
    original_sha = p.new_file(root, "original.json", p.encoded([row("1"), row("2")]))
    prior = root/"prior"; prior.mkdir(); request = prior/"request_01"; request.mkdir()
    raw = b"saved official record"
    p.new_file(request, "raw.html", raw)
    record = {"results": [{"ordinal": 1, "http_status": http_status, "acquisition_success": True,
                           "hold_reason": "ValueError:access_restriction_body", "identity": row()["identity"],
                           "timed_out": False}]}
    p.new_file(prior, "pilot-report.json", p.encoded(record))
    seal = {"files": {"pilot-report.json": p.digest((prior/"pilot-report.json").read_bytes()),
                      "request_01/raw.html": p.digest(raw)}}
    seal_sha = p.new_file(prior, "snapshot-seal.json", p.encoded(seal))
    review = {"status": "PARSE_VERIFIED_FINAL_RECORD_ONLY", "stop_cause": "TELEMETRY_STRING_ONLY",
              "identity": row()["identity"], "source_raw_sha256": p.digest(raw)}
    review_sha = p.new_file(root, "review.json", p.encoded(review))
    permit = {"original_selection_path": str(root/"original.json"), "original_selection_sha256": original_sha,
              "offline_review_path": str(root/"review.json"), "offline_review_sha256": review_sha,
              "continuation_reason": "OFFLINE_PROVEN_TELEMETRY_FALSE_POSITIVE",
              "prior_snapshot_seals": [{"directory": str(prior), "sha256": seal_sha}]}
    if http_status == 200:
        assert p.continuation_budget(permit, [row("2")]) == 1
        with pytest.raises(ValueError, match="retry_forbidden"):
            p.continuation_budget(permit, [row("1")])
    else:
        with pytest.raises(ValueError, match="genuine_failure_cannot_continue"):
            p.continuation_budget(permit, [row("2")])
