"""Offline saved-byte replay only. No HTTP worker, permits or prediction integration."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

VERSION = "two_stage_saved_byte_replay_v1"
FINAL = "PARSE_VERIFIED_FINAL_RECORD_ONLY"
TIMING_ONLY_REASONS = frozenset({
    "ValueError:new_or_ambiguous_timing_note_REQUIRES_REVIEW",
    "ValueError:unreviewed_timing_note",
})


class Stop(RuntimeError):
    """Acquisition/evidence integrity or persistence failure; never a remark HOLD."""


def require(ok, reason):
    if not ok:
        raise Stop(reason)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def utc(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timezone.utc.utcoffset(None), "UTC_REQUIRED")
    return parsed


@dataclass(frozen=True)
class SavedPacket:
    raw: bytes
    metadata: bytes
    request: bytes
    row: dict
    source_revision: dict
    original_refs: dict
    source_mode: str = "SAVED_OFFICIAL_WITNESS"
    synthetic_observation: dict | None = None


@dataclass(frozen=True)
class Expected:
    row: dict
    header: str
    pins: dict
    source_revision: dict
    normalized_header: str


class SyntheticBudget:
    """Virtual observations only; never starts, waits for, or retries a request."""
    def __init__(self, count=12, deadline=180, interval=5):
        require(type(count) is int and count > 0 and math.isfinite(deadline) and math.isfinite(interval)
                and deadline > 0 and interval >= 5, "SYNTHETIC_LIMITS")
        self.cap, self.deadline, self.interval = count, deadline, interval
        self.used, self.last_end, self.total_bytes = set(), None, 0

    def observe(self, url, observation):
        require(url not in self.used and len(self.used) < self.cap, "SYNTHETIC_COUNT_OR_DUPLICATE_STOP")
        start, end, size = observation["start"], observation["end"], observation["bytes"]
        require(type(start) in (int, float) and type(end) in (int, float)
                and math.isfinite(start) and math.isfinite(end), "SYNTHETIC_CLOCK_FINITE")
        require(observation["outcome"] == "COMPLETE_200_VERIFIED_TLS_NO_REDIRECT", "SYNTHETIC_TRANSPORT_STOP")
        require(0 <= start <= end <= self.deadline and end - start <= 10, "SYNTHETIC_DEADLINE_STOP")
        require(self.last_end is None or start - self.last_end >= self.interval, "SYNTHETIC_RATE_STOP")
        require(type(size) is int and 0 < size <= 2*1024*1024
                and self.total_bytes + size <= self.cap * 2*1024*1024, "SYNTHETIC_BODY_STOP")
        self.used.add(url); self.last_end = end; self.total_bytes += size


def check_path(path):
    path = Path(os.path.abspath(path))
    for parent in [*reversed(path.parents), path]:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 1024,
                "REPARSE_OR_SYMLINK")
    return path


class ImmutableStore:
    """Exclusive-create files, file fsync, SHA readback; never updates a packet."""
    def __init__(self, new_root):
        self.root = check_path(new_root)
        self.root.mkdir(exist_ok=False)

    def path(self, relative):
        rel = Path(relative)
        require(not rel.is_absolute() and all(re.fullmatch(r"[A-Za-z0-9_.-]+", p)
                    and p not in {".", ".."} for p in rel.parts), "UNSAFE_RELATIVE_PATH")
        p = check_path(self.root / rel)
        require(p.resolve().is_relative_to(self.root.resolve()), "OUTSIDE_NEW_STORE")
        return p

    def write(self, relative, data):
        require(type(data) is bytes, "BYTES_REQUIRED")
        p = self.path(relative)
        p.parent.mkdir(parents=True, exist_ok=True)
        self.path(relative)
        with p.open("xb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        require(self.read(relative) == data, "WRITE_READBACK_MISMATCH")
        return sha(data)

    def read(self, relative):
        p = self.path(relative)
        require(p.is_file(), "MISSING_SEALED_FILE")
        return p.read_bytes()

    def seal(self, folder, files):
        pins = {}
        for name, data in files.items():
            require(Path(name).name == name, "NESTED_BUNDLE_MEMBER")
            pins[name] = self.write(folder + "/" + name, data)
        manifest = {"version": VERSION, "files": pins, "self_excluded": True}
        h = self.write(folder + "/seal.json", encoded(manifest))
        self.verify(folder, h)
        return h

    def verify(self, folder, manifest_sha):
        body = self.read(folder + "/seal.json")
        require(sha(body) == manifest_sha, "SEAL_SHA_MISMATCH")
        manifest = json.loads(body)
        require(manifest["version"] == VERSION and manifest["self_excluded"] is True, "SEAL_SCHEMA")
        require(set(p.name for p in self.path(folder).iterdir()) == set(manifest["files"]) | {"seal.json"},
                "BUNDLE_FILE_SET_MISMATCH")
        result = {}
        for name, h in manifest["files"].items():
            data = self.read(folder + "/" + name)
            require(sha(data) == h, "SEALED_PAYLOAD_SHA_MISMATCH")
            result[name] = data
        return result


def stage_a(packet, expected, strict_analyze):
    """Validate original evidence and fixture facts; preserve unresolved remarks."""
    require(packet.source_mode in {"SAVED_OFFICIAL_WITNESS", "SYNTHETIC"}, "OFFLINE_SOURCES_ONLY")
    require(encoded(packet.row) == encoded(expected.row), "FIXTURE_ROW_MISMATCH")
    require(encoded(packet.source_revision) == encoded(expected.source_revision), "OFFICIAL_REVISION_MISMATCH")
    row = expected.row
    # Earliest pilot rows carry their sealed full header separately in Expected.
    if "complete_expected_header" in row:
        require(expected.header == row["complete_expected_header"], "EXPECTED_HEADER_MISMATCH")
    url = re.fullmatch(r"https://data\.j-league\.or\.jp/SFMS02/\?match_card_id=([1-9][0-9]*)", row["url"])
    require(url is not None and url[1] == row["data_site_match_id"], "OFFICIAL_URL_ID")
    for part, key in ((packet.raw, "raw_sha256"), (packet.metadata, "metadata_sha256"),
                      (packet.request, "request_sha256")):
        require(sha(part) == expected.pins[key], "ORIGINAL_PACKET_SHA_MISMATCH")
    meta = json.loads(packet.metadata)
    request = json.loads(packet.request)
    require(meta["status"] == 200 and meta["success"] is True and meta["complete_body"] is True,
            "HTTP_OR_COMPLETION_STOP")
    require(meta["requested_url"] == meta["final_url"] == request["url"] == row["url"] == expected.pins["url"],
            "REQUEST_RESPONSE_URL_MISMATCH")
    require(request["identity"] == row["identity"] and request["method"] == "GET", "REQUEST_IDENTITY_METHOD")
    require(meta["sha256"] == sha(packet.raw) and type(meta["bytes"]) is int and meta["bytes"] == len(packet.raw)
            and meta["request_sha256"] == sha(packet.request), "INTERNAL_SHA_OR_BYTES_MISMATCH")
    require(0 < len(packet.raw) <= 2 * 1024 * 1024, "BODY_LIMIT")
    attempts = meta.get("GET_attempts", meta.get("request_attempts"))
    require(type(attempts) is int and attempts == 1, "SINGLE_ORIGINAL_GET_REQUIRED")
    require(meta["automatic_retries"] == request["automatic_retries"] == 0, "RETRY_FORBIDDEN")
    require(request.get("TLS_verification", request.get("tls_verification")) is True, "TLS_RECORD_REQUIRED")
    require(request["timeout_seconds"] == 10, "TIMEOUT_POLICY_MISMATCH")
    if "redirects_followed" in request:
        require(request["redirects_followed"] == meta["redirects_followed"] == 0, "REDIRECT_FORBIDDEN")
    else:
        require(request.get("redirect_following") is False, "REDIRECT_POLICY_UNKNOWN")
    content_type = meta.get("content_type", meta.get("headers", {}).get("content-type", ""))
    require(re.fullmatch(r"text/html\s*;\s*charset\s*=\s*UTF-8", content_type, re.I) is not None,
            "UNKNOWN_CONTENT_TYPE")
    start = utc(request["request_started_at_utc"])
    end = utc(meta["response_completed_at_utc"])
    require(request["request_started_at_utc"] == meta["request_started_at_utc"] and start <= end
            and (end - start).total_seconds() <= 10
            and meta["response_completed_at_utc"] == expected.pins["response_completed_at_utc"], "ORIGINAL_UTC_BINDING")
    base = strict_analyze(packet.raw, row, expected.header)
    require(base["status"] == FINAL or (base["status"] == "HOLD" and base.get("hold_reason") in TIMING_ONLY_REASONS),
            "STRICT_IDENTITY_RESULT_OR_UNKNOWN_HTML_STOP")
    require(base["identity"] == row["identity"] and base["source_raw_sha256"] == sha(packet.raw)
            and base["competition_header"] == expected.normalized_header
            and base["official_date"] == row["source_date"]
            and base["official_kickoff"] == row["source_reported_kickoff"][11:16]
            and base["date_kickoff_match_saved_source"] is True
            and base["completion_state"] == "OFFICIAL_RECORD_FINAL_PERIODS_MATCH_COMPLETED_SOURCE", "STRICT_FACTS_STOP")
    parsed = base["parsed"]
    require(all(type(parsed[s+"_score_90"]) is int and parsed[s+"_score_90"] == row[s+"_score_90"]
                for s in ("home", "away")), "REGULATION_RESULT_STOP")
    require(parsed["extra_time_played"] == row["extra_time_played"]
            and (parsed["home_pk_score"] is not None) == row["pk_played"], "PK_ET_SEPARATION_STOP")
    return {"status": "SOURCE_INTEGRITY_VERIFIED", "strict_analysis": base,
            "original_request_started_UTC": request["request_started_at_utc"],
            "original_response_completed_UTC": meta["response_completed_at_utc"],
            "source_mode": packet.source_mode, "replayed_at_UTC": now()}


class ReplayRun:
    """Single-use offline replay. Callbacks are parsers of saved bytes, never workers."""
    def __init__(self, store, *, blocked_urls=(), synthetic_budget=None):
        self.store = store
        self.blocked_urls = frozenset(blocked_urls)
        self.records = []
        self.sources = []
        self.claimed = False
        self.synthetic_budget = synthetic_budget

    def run(self, items, strict_analyze, review_saved):
        require(not self.claimed, "RUN_REEXECUTION_FORBIDDEN")
        self.claimed = True
        # This survives interruption; a new ReplayRun on the same store also fails.
        try:
            self.store.write("run-claim.json", encoded({"version": VERSION, "at_UTC": now(), "offline_only": True}))
        except Exception as exc:
            raise Stop("RUN_CLAIM_OR_REEXECUTION_STOP") from exc
        used_urls, used_ids = set(), set()
        stop = None
        for ordinal, (packet, expected) in enumerate(items, 1):
            try:
                row = expected.row
                require(row["url"] not in self.blocked_urls and row["url"] not in used_urls
                        and row["identity"] not in used_ids, "DUPLICATE_OR_PREVIOUSLY_CONSUMED_SOURCE")
                used_urls.add(row["url"]); used_ids.add(row["identity"])
                if packet.source_mode == "SYNTHETIC":
                    require(self.synthetic_budget is not None and packet.synthetic_observation is not None,
                            "SYNTHETIC_OBSERVATION_REQUIRED")
                    require(packet.synthetic_observation["bytes"] == len(packet.raw), "SYNTHETIC_BODY_ACCOUNTING")
                    self.synthetic_budget.observe(row["url"], packet.synthetic_observation)
                else:
                    require(packet.synthetic_observation is None, "NO_SYNTHETIC_CLOCK_ON_REAL_WITNESS")
                a = stage_a(packet, expected, strict_analyze)
                folder = "source-%04d" % ordinal
                original_seal = self.store.seal(folder, {"raw.html": packet.raw, "metadata.json": packet.metadata,
                    "request.json": packet.request, "stage-A.json": encoded(a), "expected.json": encoded({
                        "row": row, "header": expected.header, "pins": expected.pins,
                        "revision": expected.source_revision, "original_refs": packet.original_refs})})
                self.sources.append({"folder": folder, "SHA256": original_seal})
                # Stage B consumes only a re-read and reverified sealed packet.
                sealed = self.store.verify(folder, original_seal)
                b = review_saved(sealed["raw.html"], sealed["metadata.json"], sealed["request.json"], expected)
                require(b["strict_analysis"] == a["strict_analysis"], "STAGE_B_IDENTITY_RESULT_DRIFT")
                require(b["status"] in {"PASS", "HOLD"}, "UNKNOWN_STAGE_B_STATE")
                require(not re.search(r"SHA|PACKET_(?:URL|INTERNAL|UTC)|IDENTITY|DATETIME|STRICT_RESULT|REVISION",
                                      b.get("reason") or ""), "STAGE_B_EVIDENCE_INTEGRITY_STOP")
                require(a["strict_analysis"]["status"] == FINAL or b["status"] == "HOLD",
                        "TIMING_HOLD_CANNOT_PASS")
                if b["status"] == "HOLD":
                    require(b.get("legacy_category") == "UNKNOWN_FORMAT" or bool(a["strict_analysis"].get("timing_notes"))
                            or a["strict_analysis"].get("hold_reason") in TIMING_ONLY_REASONS, "NON_REMARK_HOLD_IS_STOP")
                hold = b["status"] == "HOLD"
                packet_doc = {"identity": row["identity"], "url": row["url"], "official_id": row["data_site_match_id"],
                    "namespace": row["identity"].split(":")[0], "source_revision": expected.source_revision,
                    "original_pins": expected.pins, "original_request_started_UTC": a["original_request_started_UTC"],
                    "original_response_completed_UTC": a["original_response_completed_UTC"], "source_mode": packet.source_mode,
                    "source_acquired": True, "source_integrity_verified": True,
                    "detail_analysis_status": b["status"], "quarantine_status": hold,
                    "timing_evidence_status": "HOLD_B_C_D", "history_admission_status": False,
                    "unconfirmed_remarks_category": b.get("legacy_category", b.get("category")),
                    "stage_B_reason": b.get("reason"), "source_folder": folder, "source_seal_SHA256": original_seal,
                    "stage_A_reference": folder + "/stage-A.json", "stage_B_analysis_reference": "analysis.json",
                    "receipt_reference": "../receipt-%04d.json" % ordinal, "review_completed_UTC": now()}
                review_folder = ("quarantine-" if hold else "review-") + "%04d" % ordinal
                review_seal = self.store.seal(review_folder, {"packet.json": encoded(packet_doc), "analysis.json": encoded(b)})
                # Packet SHA is detached to avoid a self-referential hash.
                receipt = {"ordinal": ordinal, "review_folder": review_folder, "review_seal_SHA256": review_seal,
                           "packet_SHA256": sha(encoded(packet_doc)), "source_seal_SHA256": original_seal,
                           "file_fsync_and_readback_complete": True, "at_UTC": now()}
                receipt_name = "receipt-%04d.json" % ordinal
                receipt_sha = self.store.write(receipt_name, encoded(receipt))
                self.verify_receipt(receipt_name, receipt_sha)
                self.records.append({"receipt": receipt_name, "SHA256": receipt_sha})
            except Exception as exc:
                stop = {"ordinal": ordinal, "reason": type(exc).__name__ + ":" + str(exc)}
                # Preserve untrusted failure bytes without treating them as validated detail.
                try:
                    self.store.seal("failure-%04d" % ordinal, {"raw.html": packet.raw, "metadata.json": packet.metadata,
                        "request.json": packet.request, "failure.json": encoded(stop)})
                except Exception:
                    stop["failure_evidence_persistence_unconfirmed"] = True
                break
        try:
            result = self.aggregate()
        except Exception as exc:
            # An orphan/partial quarantine is a STOP, never an omitted HOLD.
            stop = stop or {"reason": type(exc).__name__ + ":" + str(exc)}
            result = {"version": VERSION, "counts_complete_and_verified": False,
                      "committed_receipts": len(self.records), "detail_PASS": None,
                      "detail_HOLD": None, "history_admitted": 0, "network_GET": 0,
                      "communication_permits_created": 0}
        result.update(status="OFFLINE_REPLAY_STOPPED" if stop else "OFFLINE_REPLAY_COMPLETED", stop=stop)
        self.store.write("terminal-receipt.json", encoded(result))
        return result

    def verify_receipt(self, name, h):
        raw = self.store.read(name)
        require(sha(raw) == h, "RECEIPT_SHA_MISMATCH")
        receipt = json.loads(raw)
        files = self.store.verify(receipt["review_folder"], receipt["review_seal_SHA256"])
        require(sha(files["packet.json"]) == receipt["packet_SHA256"], "QUARANTINE_PACKET_SHA_MISMATCH")
        packet = json.loads(files["packet.json"])
        self.store.verify(packet["source_folder"], packet["source_seal_SHA256"])
        analysis = json.loads(files["analysis.json"])
        require(analysis["status"] == packet["detail_analysis_status"], "ANALYSIS_PACKET_STATUS_MISMATCH")
        require(packet["quarantine_status"] is (analysis["status"] == "HOLD")
                and packet["history_admission_status"] is False and packet["timing_evidence_status"] == "HOLD_B_C_D",
                "HOLD_OR_ADMISSION_STATE_MISMATCH")
        return packet

    def aggregate(self):
        packets = [self.verify_receipt(r["receipt"], r["SHA256"]) for r in self.records]
        for item in self.sources:
            self.store.verify(item["folder"], item["SHA256"])
        source_folders = {p.name for p in self.store.root.iterdir() if p.name.startswith("source-")}
        require(source_folders == {r["folder"] for r in self.sources}, "UNACCOUNTED_OR_UNCOMMITTED_SOURCE")
        # Do not accept caller-supplied counters or skip quarantine packets.
        receipt_files = {p.name for p in self.store.root.glob("receipt-*.json")}
        require(receipt_files == {r["receipt"] for r in self.records}, "UNACCOUNTED_RECEIPT")
        review_folders = {p.name for p in self.store.root.iterdir() if p.name.startswith(("review-", "quarantine-"))}
        expected_folders = {json.loads(self.store.read(r["receipt"]))["review_folder"] for r in self.records}
        require(review_folders == expected_folders, "UNACCOUNTED_OR_UNCOMMITTED_QUARANTINE")
        return {"version": VERSION, "source_acquired": len(self.sources), "source_integrity_verified": len(self.sources),
                "detail_PASS": sum(p["detail_analysis_status"] == "PASS" for p in packets),
                "detail_HOLD": sum(p["detail_analysis_status"] == "HOLD" for p in packets),
                "quarantined": sum(p["quarantine_status"] for p in packets), "history_admitted": 0,
                "timing_evidence_status": "HOLD_B_C_D", "receipt_count": len(packets),
                "network_GET": 0, "communication_permits_created": 0}


def require_history_admission(packet):
    """No offline replay output is admissible to a feature generator."""
    raise Stop("HISTORY_ADMISSION_NOT_AUTHORIZED")
