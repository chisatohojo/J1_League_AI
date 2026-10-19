"""NN v2 Phase 2.2 audit/freeze only. This entry point cannot train a model."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

from scripts.build_dashboard_feed import read_official_revision
from src.collect.jleague_match_stats import parse_match_stats_html
from src.collect.teams import load_team_master
from src.features import nn_research_timing as timing
from src.modeling import nn_research_v1 as source_loader
from src.modeling import nn_residual_v2 as residual
from src.modeling import nn_v2_offsets as offsets
from src.modeling import nn_v2_pretraining_audit as audit

ROOT = Path(__file__).resolve().parents[1]
BASE = "a424c1591d4642daca33d5cb9f64ab80c84d063c"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    if Path(path).read_bytes() != data:
        raise ValueError("Output readback failed")


def verified_ledgers():
    for name in ("research/nn_v2/DESIGN-SHA256.json", "research/nn_v2/phase2_1/implementation-sha256.json"):
        ledger = json.loads((ROOT / name).read_bytes())
        for entry in ledger["files"] + ledger.get("existing_reference_files_read_only", []):
            if sha(ROOT / entry["path"]) != entry["sha256"]:
                raise ValueError("Frozen source mismatch: " + entry["path"])


def execute(args, output):
    verified_ledgers()
    spec = json.loads((ROOT / "research/nn_v2/phase2_1/implementation-spec.json").read_bytes())
    if spec["residual"] != residual.specification() or spec["tested_versions"] != residual.versions():
        raise ValueError("Numeric specification/environment mismatch")
    if residual.versions()["python"] != "3.12.14":
        raise ValueError("Python version mismatch")
    source, pins = source_loader.load_source(args.source_root, ROOT / "research/nn_v1/input-pins.json")
    print("Source pins and population verified: 3588", flush=True)
    review = timing.review_cache(args.source_root, source)
    sealed_review = json.loads((ROOT / "research/nn_v1/audit-timing-v1_1/source-timing-review.json").read_bytes())
    if review != sealed_review:
        raise ValueError("Official raw/metadata/timing review differs from sealed Phase 1.1")
    write(output / "official-cache-sha256.json", review)
    evidence = json.loads((ROOT / "research/nn_v1/timing-v1_1/evidence-manifest.json").read_bytes())
    for e in evidence["sources"]:
        if sha(args.evidence_root / e["local_raw_name"]) != e["sha256"]:
            raise ValueError("Timing evidence mismatch")
    master = load_team_master(args.source_root / "data/master/teams.csv")
    raw_root = args.source_root / "data/raw/jleague_match_stats"
    for row in source.itertuples(index=False):
        mid = str(row.match_id)
        page = parse_match_stats_html((raw_root / (mid + ".html")).read_text("utf-8-sig"),
                    expected_match_id=mid, source_url=f"https://data.j-league.or.jp/SFMS02/?match_card_id={mid}").iloc[0]
        audit.verify_detail_team_ids(master, page, row)
    print("3588 HTML/metadata SHA and official home/away IDs verified", flush=True)
    trace = []
    frame = timing.build_event_features(source, trace=trace)
    offsets.validate_state(frame)
    source_loader.validate_features(frame)
    dependencies = audit.audit_trace(frame, trace)
    splits = audit.split_plan(frame)
    special = frame.loc[frame.match_id.eq("30700")].iloc[0]
    if (special.history_cutoff_timestamp != "2024-08-24T00:00:00+09:00"
            or special.feature_timestamp != "2024-08-24T19:03:00+09:00"
            or special.result_effective_timestamp != "2024-11-23T00:00:00+09:00"
            or special.final_label != 1):
        raise ValueError("30700 chronology mismatch")
    dependency_by_id = {d["match_id"]: d for d in dependencies}
    for row in frame.itertuples(index=False):
        if dependency_by_id[row.match_id]["includes_30700"] != (row.history_cutoff_timestamp >= special.result_effective_timestamp):
            raise ValueError("30700 early/late dependency")
    print("7176 events, independent 9-feature replay and 9 ID partitions verified", flush=True)
    official = read_official_revision(args.publication, master, expected_sha=args.publication_sha)
    capacity = audit.future_capacity(official.schedule, datetime.now(timezone.utc))
    capacity.update({"revision_id": official.revision_id, "manifest_sha256": args.publication_sha,
                     "observed_at_utc": official.observed_at, "network_fetches": 0,
                     "scope": "saved accepted publication; recheck at real T0"})
    columns = ["match_id", "season", "round", "home_team_id", "away_team_id", *timing.TIMING_COLUMNS,
               *source_loader.FEATURES]
    for name, rows in (("all-input-audit.csv", frame),
                       ("residual-input-audit.csv", frame.loc[frame.season.ge(2017)])):
        path = output / name
        with path.open("x", encoding="utf-8", newline="") as f:
            rows[columns].to_csv(f, index=False); f.flush(); os.fsync(f.fileno())
        # A separate read verifies the exact row/column count, values and IDs.
        restored = source_loader.pd.read_csv(path, dtype={"match_id": str})
        if restored.match_id.tolist() != rows.match_id.tolist() or list(restored) != columns:
            raise ValueError("CSV readback identity/schema mismatch")
        if not np.allclose(restored[list(source_loader.FEATURES)], rows[list(source_loader.FEATURES)],
                           rtol=0, atol=1e-10):
            raise ValueError("CSV readback feature mismatch")
    write(output / "input-pins.json", pins)
    write(output / "crossfit-id-sets.json", splits)
    write(output / "event-trace.json", trace)
    write(output / "dependency-audit.json", dependencies)
    write(output / "future-capacity.json", capacity)
    code = {}
    for module in list(sys.modules.values()):
        location = getattr(module, "__file__", None)
        if location and Path(location).suffix == ".py" and Path(location).resolve().is_relative_to(ROOT):
            path = Path(location).resolve()
            code[path.relative_to(ROOT).as_posix()] = sha(path)
    code[Path(__file__).relative_to(ROOT).as_posix()] = sha(__file__)
    for path in sorted((ROOT / "research/nn_v2").rglob("*")):
        if path.is_file() and "phase2_2" not in path.parts:
            code[path.relative_to(ROOT).as_posix()] = sha(path)
    for relative in ("research/nn_v1/input-pins.json", "research/nn_v1/timing-v1_1/evidence-manifest.json",
                     "research/nn_v1/timing-v1_1/reviewed-interruptions.json",
                     "research/nn_v1/audit-timing-v1_1/source-timing-review.json"):
        code[relative] = sha(ROOT / relative)
    write(output / "source-sha256.json", dict(sorted(code.items())))
    payload_pins = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    ready = capacity["status"] == "CAPACITY_AVAILABLE_NOT_ENROLLED"
    manifest = {
        "schema": "nn_v2_pretraining_study_v1", "study_id": args.study_id,
        "status": "READY_FOR_SEPARATE_TRAINING_APPROVAL" if ready else "HOLD",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_branch": "feature/nn-research-v1", "research_base_head": BASE,
        "training_authorized_by_this_record": False, "chronology": timing.POLICY,
        "time_exception_registry_sha256": sha(timing.REVIEW_PATH),
        "source_sha256": code, "raw_data_sha256": pins, "audit_payload_sha256": payload_pins,
        "features": list(source_loader.FEATURES), "baseline_features": ["elo_diff"],
        "residual_features": list(residual.FORM_FEATURES), "class_order": [0, 1, 2],
        "numeric_specification": spec["residual"], "offset_specification": spec["offsets"],
        "elo": {"initial": 1500.0, "K": 30.0, "home_advantage": 175.0},
        "crossfit": splits,
        "planned_training_counts": {"crossfit_baseline": 9, "final_baseline": 1, "residual_nn": 1},
        "training_attempts_this_phase": 0, "real_fits": 0, "real_performance_evaluations": 0,
        "future_predictions_saved": 0, "actual_enrollments": 0,
        "not_generated": {"baseline_model_sha256": None, "residual_model_sha256": None,
                          "baseline_scaler_sha256": None, "residual_scaler_sha256": None,
                          "real_offsets_sha256": None, "real_scaler_statistics": None, "T0": None,
                          "state": "NOT_GENERATED_SEAL_SEPARATELY_AFTER_AUTHORIZED_EXECUTION"},
        "output_contract": {"training_output": str(args.training_output.resolve()),
            "output_exists": False, "attempt_marker": "exclusive persistent study-id marker BEFORE first fit",
            "retry_count": 0, "same_study_retraining": False,
            "execution_driver": "NOT_CREATED_NOT_EXECUTED; inspect and SHA-seal before authorized first fit",
            "artifact_readback": "finite arrays, classes, feature order, row sets, versions and SHA; no refit",
            "production_connection": False},
        "future_evaluation": {"plan_sha256": sha(ROOT / "research/nn_v2/FUTURE_EVALUATION_PLAN.md"),
            "capacity_audit": capacity, "T0": None, "registered_fixture_ids": None,
            "policy": "first wholly unstarted round at real T0 plus next 19; 200 exact fixtures; pending IDs never guessed",
            "predictions": "paired frozen research baseline/residual; complete same-date batch before kickoff; immutable witness",
            "evaluation": "only after all 200 completed and sealed forecasts joined; no early selection"},
        "stop_conditions": ["source/spec/version/SHA drift", "counts/identity/chronology mismatch",
            "unknown timing case", "nonfinite input/logit/gradient/loss/probability",
            "missing class or probability sum/order mismatch", "warning or unexpected exception",
            "existing output/attempt marker", "insufficient 20 future complete rounds",
            "missing future official identity/history/witness: no prediction"],
        "historical_publication_asof_proven": False,
        "spent_data": "2020-2024 repeatedly researched; 2025 spent test used only for frozen training; known 2026 not fresh holdout",
        "phase_A": "BLOCKED", "phase_B": "NOT_AUTHORIZED"}
    write(output / "study-manifest.json", manifest)
    report = {"status": manifest["status"], "population": 3588, "seed_rows": 612,
              "residual_rows": 2976, "year_counts": source_loader.COUNTS, "folds": 9,
              "official_cache_rows": 3588, "official_metadata_rows": 3588,
              "known_timing_notes": len(review["reviewed_timing_ids"]), "unknown_timing_cases": [],
              "independent_replay_rows": len(dependencies), "event_count": len(trace),
              "source_inputs_unchanged": all(sha(args.source_root / p) == h for p, h in pins.items()),
              "official_cache_rechecked": timing.review_cache(args.source_root, source) == review,
              "study_manifest_sha256": sha(output / "study-manifest.json"),
              "real_fits": 0, "real_performance_evaluations": 0, "future_predictions_saved": 0,
              "offset_values_generated": False, "scaler_statistics_generated": False,
              "future_capacity": capacity, "versions": residual.versions()}
    if not report["source_inputs_unchanged"] or not report["official_cache_rechecked"]:
        raise ValueError("Input changed during audit")
    write(output / "audit-result.json", report)
    write(output / "SHA256-MANIFEST.json", {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()})
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source-root", "evidence-root", "publication", "output", "training-output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--publication-sha", required=True)
    p.add_argument("--study-id", required=True)
    args = p.parse_args()
    if subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip() != "feature/nn-research-v1":
        raise ValueError("Research branch mismatch")
    # Descendant audit-document commits are allowed for reproducible read-only audits.
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)
    if args.training_output.exists() or args.output.exists():
        raise ValueError("Audit and planned training output must both be unused")
    resolved = args.output.resolve()
    forbidden = (ROOT, args.source_root.resolve(), args.publication.resolve(), args.evidence_root.resolve())
    if any(resolved.is_relative_to(parent) or parent.is_relative_to(resolved) for parent in forbidden):
        raise ValueError("Output overlaps protected inputs")
    resolved.mkdir(parents=False, exist_ok=False)
    try:
        with audit.no_learning() as intercepted:
            report = execute(args, resolved)
        if intercepted:
            raise ValueError("Forbidden learning call attempted")
    except Exception as exc:
        write(resolved / "failure.json", {"status": "HOLD", "exception_type": type(exc).__name__,
              "diagnostic": str(exc), "retry": False})
        raise
    print(json.dumps({"status": report["status"], "study_manifest_sha256": report["study_manifest_sha256"],
                      "real_fits": 0, "offsets_generated": False, "scaler_statistics_generated": False}))
    return 0 if report["status"].startswith("READY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
