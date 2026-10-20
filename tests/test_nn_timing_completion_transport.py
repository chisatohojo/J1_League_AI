"""Synthetic transport tests; all connections are injected and offline."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
from types import SimpleNamespace

import pytest

path = os.environ.get("J1AI_TIMING_COMPLETION_FETCHER")
if not path:
    pytest.skip("Set J1AI_TIMING_COMPLETION_FETCHER to the sealed local fetcher", allow_module_level=True)
source = Path(path)
if hashlib.sha256(source.read_bytes()).hexdigest() != "b3895883d10a41e3f286061c6bf6f166f1e67ab2a1c575c02a2e041f49a8c3f1":
    raise ValueError("Completion fetcher SHA mismatch")
spec = importlib.util.spec_from_file_location("timing_completion_fetcher_local", source)
fetcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetcher)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Synthetic transport must never open a socket")
    monkeypatch.setattr(socket, "create_connection", forbidden)


def permit(kind="robots"):
    rows = [{"identity": "fixture:"+str(i), "data_site_match_id": str(i), "complete_expected_header":"2026/27 synthetic full header",
             "url": "https://data.j-league.or.jp/SFMS02/?match_card_id="+str(i)} for i in range(8,13)]
    result = {"kind":kind,"approved":True,"network_enabled":True,"allowed_host":fetcher.HOST,
              "timeout_seconds":10,"interval_seconds":5,"retries":0,"redirect_following":False,
              "rows":rows,"max_total_GET":5,"max_body_bytes":2097152,
              "previous_seven_URLs":[],"remaining_five_URLs":[r["url"] for r in rows]}
    if kind == "robots":
        result.update(rows=[{"identity":"robots","url":"https://data.j-league.or.jp/robots.txt"}],
                      max_total_GET=1,max_body_bytes=65536)
    return result


@pytest.mark.parametrize("change", ["extra", "host", "retry", "redirect", "previous", "ID", "held"])
def test_permits_reject_expansion_and_policy_changes(change):
    p = permit("fixtures")
    if change == "extra": p["rows"].append(dict(p["rows"][0]))
    if change == "host": p["allowed_host"] = "evil.test"
    if change == "retry": p["retries"] = 1
    if change == "redirect": p["redirect_following"] = True
    if change == "previous": p["previous_seven_URLs"] = [p["rows"][0]["url"]]
    if change == "ID": p["rows"][0]["data_site_match_id"] = "1"
    if change == "held": p["approved"] = False
    with pytest.raises(ValueError): fetcher.validate(p)


@pytest.mark.parametrize("status", [200,404,403,429,302,500])
def test_one_GET_no_redirect_or_retry_and_SHA_receipts(status,tmp_path,monkeypatch):
    p = permit(); calls = []; body = b"User-agent: *\nDisallow:\n"
    class Response:
        def __init__(self): self.status = status; self.body = body
        def getheaders(self): return [("Content-Type","text/plain"),("Location","https://evil.test/")]
        def read(self,n): result,self.body = self.body[:n],self.body[n:]; return result
    class Connection:
        def __init__(self,host,port,timeout,context):
            assert host == fetcher.HOST and port == 443 and timeout == 10
            assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
        def request(self,method,path,headers): calls.append((method,path))
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(fetcher,"safe",lambda path: Path(path))
    meta = fetcher.worker(p,"a"*64,1,tmp_path,Connection)
    assert calls == [("GET","/robots.txt")]
    assert meta["success"] == (status in (200,404))
    assert meta["GET_attempts"] == 1 and meta["redirects_followed"] == 0
    raw = (tmp_path/"raw.html").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == meta["sha256"] and len(raw) == meta["bytes"]
    assert hashlib.sha256((tmp_path/"request.json").read_bytes()).hexdigest() == meta["request_sha256"]
    assert json.loads((tmp_path/"metadata.json").read_bytes()) == meta
    with pytest.raises(ValueError,match="attempt_already_exists"):
        fetcher.worker(p,"a"*64,1,tmp_path,Connection)
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["timeout", "body_limit", "template"])
def test_failures_stop_without_retry_and_preserve_bounded_evidence(failure,tmp_path,monkeypatch):
    p = permit(); calls=[]
    class Response:
        status=200
        def getheaders(self): return [("Content-Type","text/html" if failure=="template" else "text/plain")]
        def read(self,n): return b"x"*n if failure=="body_limit" else b""
    class Connection:
        def __init__(self,*args,**kwargs): pass
        def request(self,*args,**kwargs):
            calls.append(1)
            if failure=="timeout": raise TimeoutError("synthetic")
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(fetcher,"safe",lambda path:Path(path))
    meta=fetcher.worker(p,"b"*64,1,tmp_path,Connection)
    assert not meta["success"] and len(calls)==1
    assert meta["bytes"] <= p["max_body_bytes"] and "error" in meta


def test_real_write_guard_rejects_existing_source(tmp_path):
    with pytest.raises(ValueError,match="outside_new_research_root"):
        fetcher.write(tmp_path,"raw.html",b"forbidden")
    assert not (tmp_path/"raw.html").exists()


@pytest.mark.parametrize("outcome", ["PASS", "HTTP_429", "hard_timeout"])
def test_parent_serial_rate_limit_and_stop_without_retry(outcome,tmp_path,monkeypatch):
    p=permit("fixtures")
    p.update(input_SHA256={},core_path="sealed-core",guard_path="sealed-guard",
             access_raw_path=str(tmp_path/"access-raw"),access_metadata_path=str(tmp_path/"access-meta"),
             team_master_path="unused",not_before_utc="2026-01-01T00:00:00+00:00",
             snapshot_directory=str(tmp_path/"snapshot"))
    (tmp_path/"access-raw").write_bytes(b"404")
    (tmp_path/"access-meta").write_bytes(b"{}")
    body=fetcher.encoded(p);path=tmp_path/"permit.json";path.write_bytes(body)
    monkeypatch.setattr(fetcher,"safe",lambda path:Path(path))
    core=SimpleNamespace(analyze=lambda *args:{"status":"PARSE_VERIFIED_FINAL_RECORD_ONLY"})
    guard=SimpleNamespace(access_gate=lambda *args:{"network_enabled":True})
    monkeypatch.setattr(fetcher,"load_module",lambda path,*args:core if path=="sealed-core" else guard)
    import src.collect.teams
    monkeypatch.setattr(src.collect.teams,"load_team_master",lambda path:object())
    clock=[0.0];starts=[];calls=[]
    monkeypatch.setattr(fetcher.time,"monotonic",lambda:clock[0])
    monkeypatch.setattr(fetcher.time,"sleep",lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    def run(command,timeout,capture_output):
        assert timeout==10 and capture_output and "worker" in command
        ordinal=int(command[-1]);starts.append(clock[0]);calls.append(ordinal);clock[0]+=0.25
        if outcome=="hard_timeout": raise subprocess.TimeoutExpired(command,timeout)
        folder=tmp_path/"snapshot"/f"request_{ordinal:02d}"
        request=b"{}";raw=b"synthetic"
        meta={"success":outcome=="PASS","status":200 if outcome=="PASS" else 429,
              "sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),
              "request_sha256":hashlib.sha256(request).hexdigest()}
        (folder/"request.json").write_bytes(request);(folder/"raw.html").write_bytes(raw)
        (folder/"metadata.json").write_bytes(fetcher.encoded(meta))
        return SimpleNamespace(returncode=0,stderr=b"")
    monkeypatch.setattr(fetcher.subprocess,"run",run)
    report=fetcher.execute(path,hashlib.sha256(body).hexdigest())
    expected=5 if outcome=="PASS" else 1
    assert calls==list(range(1,expected+1)) and report["attempted"]==expected
    assert report["all_PASS"]==(outcome=="PASS")
    assert all(b-a>=5.25 for a,b in zip(starts,starts[1:]))
    assert (tmp_path/"snapshot/seal.json").exists()
