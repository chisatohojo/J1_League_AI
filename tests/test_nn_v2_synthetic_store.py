"""Synthetic contract only: no models, network or real fixture writes."""
from copy import deepcopy
import json

import pytest

from test_nn_v2_offsets_contracts import plan, prediction, full_schedule
from src.modeling import nn_v2_contracts as c
from src.modeling import nn_v2_synthetic_store as s


def case(tmp_path):
    p = plan(); records = [prediction(p, f) for f in p["fixtures"][:10]]
    witness = {"data_origin": "synthetic", "official_revision": p["official_revision"],
               "observed_at": records[0]["source_observed_at"]}
    for r in records: r["source_witness_sha256"] = s.digest(s.body(witness))
    artifacts = {k: records[0][k] for k in ("baseline_sha256", "residual_sha256", "feature_schema_sha256")}
    root = tmp_path/"store"; s.initialize(root, p, artifacts)
    return root, p, records, witness


def clock():
    return "2026-11-01T07:00:02+09:00"


def test_atomic_pair_readback_and_no_duplicate_key(tmp_path):
    root, p, records, witness = case(tmp_path)
    before = deepcopy(records)
    c.validate_target_selection(p, full_schedule(), now=p["t0"])
    receipt = s.publish(root, "first", records, witness, clock=clock)
    pin = s.digest(s.body(receipt))
    assert s.read_batch(root, "first", expected_receipt_sha=pin) == records == before
    with pytest.raises(FileExistsError): s.publish(root, "again", records, witness, clock=clock)
    assert s.read_batch(root, "first", expected_receipt_sha=pin) == before
    assert len(list((root/"ledger").glob("*.json"))) == 1


@pytest.mark.parametrize("edit", ["missing_id", "missing_kickoff", "partial", "duplicates", "source", "artifact", "mixed_snapshot", "real_origin", "rescheduled"])
def test_rejects_incomplete_identity_pair_or_context(tmp_path, edit):
    root, p, records, witness = case(tmp_path)
    if edit == "missing_id": records[0]["fixture"]["official_id"] = None
    if edit == "missing_kickoff": records[0]["fixture"]["kickoff"] = None
    if edit == "partial": records.pop()
    if edit == "duplicates": records.append(deepcopy(records[0]))
    if edit == "source": witness["observed_at"] = "2026-11-01T06:00:00+09:00"
    if edit == "artifact": records[0]["baseline_sha256"] = "f"*64
    if edit == "mixed_snapshot": records[0]["official_revision"] = "f"*64
    if edit == "real_origin": records[0]["data_origin"] = "real"
    if edit == "rescheduled": records[0]["fixture"]["kickoff"] = "2026-11-02T14:00:00+09:00"
    with pytest.raises((ValueError, TypeError)): s.publish(root, "bad", records, witness, clock=clock)
    assert not list((root/"receipts").glob("*.json"))


@pytest.mark.parametrize("point", ["after_stage", "after_commit_dir", "after_ledger"])
def test_partial_failure_is_not_visible_and_attempt_is_retained(tmp_path, point):
    root, p, records, witness = case(tmp_path)
    def fail(stage):
        if stage == point: raise RuntimeError("SYNTHETIC_FAULT")
    with pytest.raises(RuntimeError): s.publish(root, "failed", records, witness, clock=clock, fault=fail)
    assert (root/"attempts/failed.json").is_file() and (root/"diagnostics/failed.json").is_file()
    assert not (root/"receipts/failed.json").exists()
    with pytest.raises((ValueError, FileExistsError)): s.publish(root, "failed", records, witness, clock=clock)


@pytest.mark.parametrize("at", ["2026-11-01T14:00:00+09:00", "2026-11-01T14:00:00.0000001+09:00"])
def test_earliest_deadline_is_strict(tmp_path, at):
    root, p, records, witness = case(tmp_path)
    with pytest.raises(ValueError): s.publish(root, "late", records, witness, clock=lambda: at)


def test_deadline_during_durable_write_never_gets_success_receipt(tmp_path):
    root, p, records, witness = case(tmp_path)
    times = iter([clock(), clock(), "2026-11-01T14:00:00+09:00"])
    with pytest.raises(ValueError): s.publish(root, "late", records, witness, clock=lambda: next(times))
    assert (root/"ledger/000001.json").exists()
    assert not (root/"receipts/late.json").exists()


@pytest.mark.parametrize("target", ["records", "receipt", "ledger", "header"])
def test_hash_or_receipt_tamper_is_rejected(tmp_path, target):
    root, p, records, witness = case(tmp_path)
    receipt = s.publish(root, "one", records, witness, clock=clock); pin=s.digest(s.body(receipt))
    path = {"records": root/"commits/one/records.json", "receipt": root/"receipts/one.json",
            "ledger": root/"ledger/000001.json", "header": root/"store.json"}[target]
    path.write_bytes(path.read_bytes()+b" ")
    with pytest.raises(ValueError): s.read_batch(root, "one", expected_receipt_sha=pin)


def test_real_store_initialization_prohibited(tmp_path):
    p=plan();p["data_origin"]="real"
    with pytest.raises(ValueError): s.initialize(tmp_path/"real", p, {})


def test_known_daily_predictions_with_future_unknown_kickoff_plan_cannot_be_registered():
    p=plan();p["fixtures"][-1]["kickoff"]=None
    with pytest.raises(ValueError): c.validate_enrollment(p,now=p["t0"])


def test_official_reschedule_keeps_identity_and_requires_independent_source_match():
    p = plan(); original = deepcopy(p["fixtures"][0]); source = full_schedule()
    p["official_revision"] = "f"*64
    p["fixtures"][0]["kickoff"] = "2026-11-03T14:00:00+09:00"
    with pytest.raises(ValueError): c.validate_target_selection(p, source, now=p["t0"])
    source[100]["kickoff"] = p["fixtures"][0]["kickoff"]
    c.validate_target_selection(p, source, now=p["t0"])
    for field in ("fixture_key", "round", "home_team_id", "away_team_id", "official_id"):
        assert p["fixtures"][0][field] == original[field]


def test_clock_regression_is_a_failure(tmp_path):
    root, p, records, witness = case(tmp_path)
    times = iter(["2026-11-01T07:00:03+09:00", clock()])
    with pytest.raises(ValueError): s.publish(root, "clock", records, witness, clock=lambda: next(times))
    assert not (root/"receipts/clock.json").exists()
