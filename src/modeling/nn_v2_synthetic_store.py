"""Synthetic-only reference transaction for the unchanged paired-v1 contract.

No real-data switch, model loader, clock override for a live predictor, or CLI.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from src.modeling import nn_v2_contracts as c


def body(obj):
    return (json.dumps(obj, sort_keys=True, allow_nan=False, separators=(",", ":"))+"\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, raw):
    with Path(path).open("xb") as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    if Path(path).read_bytes() != raw:
        raise ValueError("SYNTHETIC_READBACK_MISMATCH")


def no_reparse(path):
    for p in (Path(path), *Path(path).parents):
        if p.exists() and (p.is_symlink() or getattr(p.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("SYNTHETIC_REPARSE_REJECTED")


def initialize(root, plan, artifacts):
    if (plan.get("data_origin") != "synthetic" or not plan.get("study_id", "").startswith("synthetic-")
            or any(not f["fixture_key"].startswith("synthetic-") for f in plan.get("fixtures", []))):
        raise ValueError("REAL_DATA_STORAGE_NOT_IMPLEMENTED_OR_AUTHORIZED")
    c.validate_enrollment(plan, now=plan["t0"])
    if set(artifacts) != {"baseline_sha256", "residual_sha256", "feature_schema_sha256"}:
        raise ValueError("ARTIFACT_REFERENCE_FIELDS")
    for h in artifacts.values(): c.digest(h)
    root = Path(root); no_reparse(root.parent); root.mkdir(exist_ok=False)
    for name in ("attempts", "keys", "staging", "commits", "ledger", "receipts", "diagnostics"):
        (root/name).mkdir()
    write(root/"store.json", body({"role": "SYNTHETIC_CONTRACT_ONLY", "data_origin": "synthetic",
          "plan": plan, "plan_sha256": digest(body(plan)), "artifacts": artifacts}))


def key(record):
    f = record["fixture"]
    return digest(body([record["model_version"], f["namespace"], f["official_id"]]))


def publish(root, batch_id, records, witness, *, clock, fault=lambda stage: None):
    root = Path(root); no_reparse(root)
    if not isinstance(batch_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", batch_id):
        raise ValueError("INVALID_BATCH_ID")
    header = json.loads((root/"store.json").read_bytes()); plan = header["plan"]
    if header["role"] != "SYNTHETIC_CONTRACT_ONLY" or header["data_origin"] != "synthetic":
        raise ValueError("REAL_DATA_STORAGE_NOT_AUTHORIZED")
    if witness.get("data_origin") != "synthetic" or any(r.get("data_origin") != "synthetic" for r in records):
        raise ValueError("REAL_DATA_STORAGE_NOT_AUTHORIZED")
    c.validate_prediction_batch(records, plan)
    common = ("study_id", "model_version", "official_revision", "source_witness_sha256", "history_cutoff",
              "source_observed_at", "baseline_sha256", "residual_sha256", "feature_schema_sha256", "run_id")
    for field in common:
        if len({r[field] for r in records}) != 1:
            raise ValueError("PAIRED_BATCH_CONTEXT_MISMATCH")
    if (digest(body(witness)) != records[0]["source_witness_sha256"]
            or witness["official_revision"] != records[0]["official_revision"]
            or witness["observed_at"] != records[0]["source_observed_at"]):
        raise ValueError("SOURCE_WITNESS_MISMATCH")
    if any(r[f] != h for r in records for f, h in header["artifacts"].items()):
        raise ValueError("ARTIFACT_REFERENCE_MISMATCH")
    deadline = min(c.stamp(r["fixture"]["kickoff"]) for r in records)
    started_at = clock()
    if c.stamp(started_at) >= deadline:
        raise ValueError("EARLIEST_KICKOFF_EXPIRED")
    lock = root/"writer.lock"; owner = body({"owner": uuid.uuid4().hex})
    write(lock, owner)
    started = False
    try:
        # An orphaned ledger entry blocks new publication; no automatic recovery.
        entries = sorted((root/"ledger").glob("*.json")); previous = "0"*64
        for n, path in enumerate(entries, 1):
            e = json.loads(path.read_bytes())
            if (path.name != f"{n:06d}.json" or e["previous_sha256"] != previous
                    or not (root/"receipts"/(e["batch_id"]+".json")).is_file()):
                raise ValueError("PRIOR_TRANSACTION_INCOMPLETE")
            previous = digest(path.read_bytes())
        write(root/"attempts"/(batch_id+".json"), body({"batch_id": batch_id, "state": "STARTED", "retry": False}))
        started = True
        for r in records:
            write(root/"keys"/(key(r)+".json"), body({"batch_id": batch_id, "key": key(r)}))
        stage = root/"staging"/batch_id; stage.mkdir(exist_ok=False)
        write(stage/"records.json", body(records))
        write(stage/"source-witness.json", body(witness))
        manifest = {p.name: digest(p.read_bytes()) for p in stage.iterdir()}
        write(stage/"manifest.json", body(manifest))
        payload_readback = clock()
        if (not c.stamp(started_at) <= c.stamp(payload_readback) < deadline
                or any(c.stamp(r["readback_at"]) > c.stamp(payload_readback) for r in records)):
            raise ValueError("PAYLOAD_READBACK_DEADLINE")
        fault("after_stage")
        stage.rename(root/"commits"/batch_id)
        fault("after_commit_dir")
        entry = {"batch_id": batch_id, "previous_sha256": previous, "keys": [key(r) for r in records],
                 "manifest_sha256": digest(body(manifest)), "payload_readback_at": payload_readback}
        lp = root/"ledger"/f"{len(entries)+1:06d}.json"
        write(lp, body(entry)); fault("after_ledger")
        ledger_readback = clock()
        if not c.stamp(payload_readback) <= c.stamp(ledger_readback) < deadline:
            raise ValueError("LEDGER_READBACK_DEADLINE")
        receipt = {"batch_id": batch_id, "status": "SYNTHETIC_COMMITTED", "ledger_file": lp.name,
                   "ledger_sha256": digest(lp.read_bytes()), "store_sha256": digest((root/"store.json").read_bytes()),
                   "payload_and_ledger_readback_at": ledger_readback}
        # Payload and ledger already passed durable readback before kickoff.
        # The receipt is the sole visibility point; incomplete staging is ignored.
        temp = root/"receipts"/(batch_id+".pending")
        write(temp, body(receipt)); temp.rename(root/"receipts"/(batch_id+".json"))
        return receipt
    except Exception as exc:
        if started:
            write(root/"diagnostics"/(batch_id+".json"), body({"batch_id": batch_id, "state": "FAILED",
                  "exception_type": type(exc).__name__, "retry": False, "success_visible": False}))
        raise
    finally:
        if lock.read_bytes() != owner:
            raise ValueError("LOCK_OWNERSHIP_CHANGED")
        lock.unlink()


def read_batch(root, batch_id, *, expected_receipt_sha):
    root = Path(root); no_reparse(root)
    if not isinstance(batch_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", batch_id):
        raise ValueError("INVALID_BATCH_ID")
    raw_receipt = (root/"receipts"/(batch_id+".json")).read_bytes()
    if digest(raw_receipt) != expected_receipt_sha:
        raise ValueError("EXTERNAL_RECEIPT_PIN_MISMATCH")
    receipt = json.loads(raw_receipt)
    if digest((root/"store.json").read_bytes()) != receipt["store_sha256"]:
        raise ValueError("STORE_HEADER_CHANGED")
    if not re.fullmatch(r"[0-9]{6}\.json", receipt["ledger_file"]):
        raise ValueError("INVALID_LEDGER_REFERENCE")
    ledger = root/"ledger"/receipt["ledger_file"]
    if digest(ledger.read_bytes()) != receipt["ledger_sha256"]:
        raise ValueError("LEDGER_SHA_MISMATCH")
    entry = json.loads(ledger.read_bytes()); commit = root/"commits"/batch_id
    previous = "0"*64
    for n in range(1, int(ledger.stem)+1):
        raw = (root/"ledger"/f"{n:06d}.json").read_bytes()
        if json.loads(raw)["previous_sha256"] != previous:
            raise ValueError("LEDGER_CHAIN_CHANGED")
        previous = digest(raw)
    if entry["batch_id"] != batch_id or digest((commit/"manifest.json").read_bytes()) != entry["manifest_sha256"]:
        raise ValueError("COMMIT_IDENTITY_OR_MANIFEST_MISMATCH")
    for name, h in json.loads((commit/"manifest.json").read_bytes()).items():
        if Path(name).name != name or digest((commit/name).read_bytes()) != h:
            raise ValueError("COMMIT_PAYLOAD_SHA_MISMATCH")
    records = json.loads((commit/"records.json").read_bytes())
    header = json.loads((root/"store.json").read_bytes())
    c.validate_prediction_batch(records, header["plan"])
    if entry["keys"] != [key(r) for r in records]:
        raise ValueError("COMMIT_KEYS_CHANGED")
    witness = json.loads((commit/"source-witness.json").read_bytes())
    if any(r["source_witness_sha256"] != digest(body(witness)) for r in records):
        raise ValueError("SOURCE_WITNESS_CHANGED")
    if any(r[f] != h for r in records for f, h in header["artifacts"].items()):
        raise ValueError("ARTIFACT_REFERENCES_CHANGED")
    if c.stamp(receipt["payload_and_ledger_readback_at"]) >= min(c.stamp(r["fixture"]["kickoff"]) for r in records):
        raise ValueError("DURABLE_READBACK_AFTER_DEADLINE")
    return records
