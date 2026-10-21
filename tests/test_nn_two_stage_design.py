"""Synthetic-only policy comparison; no real acquisition implementation imported."""
import ast
from pathlib import Path
import importlib.util
import pytest

source = Path(__file__).parents[1] / "research/nn_v2/phase2_5B_11/two_stage_design_model.py"
spec = importlib.util.spec_from_file_location("two_stage_design", source)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


@pytest.mark.parametrize("note", ["UNKNOWN_REMARK", "UNKNOWN_TIMING_NOTE"])
def test_current_contract_stops_on_any_unknown(note):
    r = model.simulate([("a", note), ("b", "DETAIL_CHECKS_PASS")])
    assert r["records"] == [("a", "QUARANTINED_HOLD", False),
                            ("b", "NOT_STARTED_AFTER_GLOBAL_STOP", False)]


@pytest.mark.parametrize("note", ["UNKNOWN_REMARK", "UNKNOWN_TIMING_NOTE"])
def test_proposal_can_continue_but_never_admits_unknown_or_clean_records(note):
    r = model.simulate([("a", note), ("b", "DETAIL_CHECKS_PASS")],
                       mode="PROPOSED_QUARANTINE_ONLY")
    assert r["records"] == [("a", "QUARANTINED_HOLD", False),
                            ("b", "DETAIL_A_ONLY", False)]
    assert r["history_admissions"] == r["requests_dispatched"] == r["permits_created"] == 0


@pytest.mark.parametrize("fatal", sorted(model.FATAL) + ["unrecognized status"])
@pytest.mark.parametrize("mode", ["CURRENT_STOP_ON_ANY_HOLD", "PROPOSED_QUARANTINE_ONLY"])
def test_acquisition_integrity_anomalies_always_stop_everything(fatal, mode):
    r = model.simulate([("a", fatal), ("b", "DETAIL_CHECKS_PASS")], mode=mode)
    assert r["records"][0][1] == "GLOBAL_STOP"
    assert r["records"][1][1] == "NOT_STARTED_AFTER_GLOBAL_STOP"
    assert r["stop"] == fatal


@pytest.mark.parametrize("mode", ["CURRENT_STOP_ON_ANY_HOLD", "PROPOSED_QUARANTINE_ONLY"])
def test_duplicate_and_cap_are_fatal_without_retry(mode):
    r = model.simulate([("a", "DETAIL_CHECKS_PASS"), ("a", "DETAIL_CHECKS_PASS"),
                        ("b", "DETAIL_CHECKS_PASS")], mode=mode)
    assert r["records"][1][1] == "GLOBAL_STOP" and r["records"][2][1].startswith("NOT_STARTED")
    assert model.simulate([("a", "DETAIL_CHECKS_PASS"), ("b", "DETAIL_CHECKS_PASS")],
                           cap=1, mode=mode)["stop"] == "DUPLICATE_OR_LIMIT"


def test_quarantine_does_not_hide_later_transport_failure():
    r = model.simulate([("a", "UNKNOWN_REMARK"), ("b", "HTTP429"),
                        ("c", "DETAIL_CHECKS_PASS")], mode="PROPOSED_QUARANTINE_ONLY")
    assert r["stop"] == "HTTP429" and r["records"][-1][1].startswith("NOT_STARTED")


def test_no_imports_io_transport_or_admission_entry_points():
    tree = ast.parse(source.read_text(encoding="utf8"))
    assert not any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree))
    calls = [n.func for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert not any(isinstance(f, ast.Name) and f.id in {"open", "exec", "eval", "__import__"} for f in calls)
    assert not any(isinstance(f, ast.Attribute) and f.attr in {
        "request", "execute", "connect", "fit", "predict", "write_bytes", "write_text"
    } for f in calls)
