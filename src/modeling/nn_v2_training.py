"""Single-attempt NN v2 research driver. No performance metrics or live hooks."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import warnings
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from src.features import nn_research_timing as timing
from src.modeling import nn_research_v1 as loader
from src.modeling import nn_residual_v2 as nn
from src.modeling import nn_v2_offsets as offsets
from src.modeling import nn_v2_pretraining_audit as auditor
from src.modeling.nn_v2_contracts import validate_artifact_manifest

ROOT = Path(__file__).resolve().parents[2]
STUDY = "nn_v2_residual_20261020_01"
MANIFEST_SHA = "75d51da6e8c984666fe5630330a3b962e37ff32d0fb3d294aaf3989f0ebf44cb"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+"\n").encode()
    with Path(path).open("xb") as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())
    if Path(path).read_bytes() != raw:
        raise ValueError("JSON readback mismatch")


def save_joblib(path, value):
    with Path(path).open("xb") as f:
        joblib.dump(value, f, compress=3); f.flush(); os.fsync(f.fileno())
    return sha(path)


def save_npz(path, **arrays):
    with Path(path).open("xb") as f:
        np.savez(f, **arrays); f.flush(); os.fsync(f.fileno())


def csv(path, frame):
    with Path(path).open("x", encoding="utf-8", newline="") as f:
        frame.to_csv(f, index=False); f.flush(); os.fsync(f.fileno())


def assert_probabilities(p):
    p = nn.finite(p)
    if p.ndim != 2 or p.shape[1] != 3 or (p < 0).any() or (p > 1).any() or not np.allclose(p.sum(axis=1), 1, rtol=0, atol=1e-12):
        raise ValueError("Invalid technical probability check")


def preflight(manifest_path, source_root, evidence_root):
    """Real input verification only, behind a guard against learning/inference."""
    manifest_path, source_root = Path(manifest_path), Path(source_root)
    if sha(manifest_path) != MANIFEST_SHA:
        raise ValueError("Study manifest SHA mismatch")
    m = json.loads(manifest_path.read_bytes())
    if m["study_id"] != STUDY or m["status"] != "READY_FOR_SEPARATE_TRAINING_APPROVAL":
        raise ValueError("Study identity/state mismatch")
    for name, digest in m["source_sha256"].items():
        if sha(ROOT/name) != digest:
            raise ValueError("Frozen source changed: "+name)
    for name, digest in m["audit_payload_sha256"].items():
        if sha(manifest_path.parent/name) != digest:
            raise ValueError("Frozen audit payload changed: "+name)
    old_spec = json.loads((ROOT/"research/nn_v2/phase2_1/implementation-spec.json").read_bytes())
    if m["numeric_specification"] != nn.specification() or nn.versions() != old_spec["tested_versions"]:
        raise ValueError("Frozen numeric/environment mismatch")
    with auditor.no_learning():
        source, pins = loader.load_source(source_root, ROOT/"research/nn_v1/input-pins.json")
        if pins != m["raw_data_sha256"]:
            raise ValueError("Input pins differ from study")
        review = timing.review_cache(source_root, source)
        if review != json.loads((manifest_path.parent/"official-cache-sha256.json").read_bytes()):
            raise ValueError("Official raw/metadata/registry changed")
        evidence = json.loads((ROOT/"research/nn_v1/timing-v1_1/evidence-manifest.json").read_bytes())
        for e in evidence["sources"]:
            if sha(Path(evidence_root)/e["local_raw_name"]) != e["sha256"]:
                raise ValueError("Official timing evidence changed")
        frame = offsets.prepare_history(source)
        if auditor.split_plan(frame) != m["crossfit"]:
            raise ValueError("Training/target ID sets differ from study")
        frozen = pd.read_csv(manifest_path.parent/"all-input-audit.csv", dtype={"match_id": str}, float_precision="round_trip")
        if frozen.match_id.tolist() != frame.match_id.tolist():
            raise ValueError("Frozen row order changed")
        for col in timing.TIMING_COLUMNS:
            if frame[col].astype(str).tolist() != frozen[col].astype(str).tolist():
                raise ValueError("Frozen timing changed")
        np.testing.assert_allclose(frame[list(loader.FEATURES)], frozen[list(loader.FEATURES)], rtol=0, atol=1e-12)
    return m, frame


def plain_parent(path):
    """Reject redirected output parents; never traverse an existing reparse."""
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.exists() and (parent.is_symlink() or getattr(parent.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Reparse/symlink in research output ancestry")


def fit_once(frame, plan, root):
    """Instrument existing fixed algorithms; callers reserve the attempt first."""
    frame = offsets.validate_state(frame)
    if frame.match_id.tolist() != plan["final_baseline_fit_ids"]:
        raise ValueError("Final baseline ID order mismatch")
    root = Path(root)
    for name in ("fit-events", "crossfit", "final-baseline"):
        (root/name).mkdir(exist_ok=False)
    counts = {"crossfit_baseline": 0, "final_baseline": 0, "residual_nn": 0,
              "logistic_fit_calls": 0, "scaler_fit_calls": 0, "adam_updates": 0}
    original_fit, lr_fit, scaler_fit, adam = offsets._fit, LogisticRegression.fit, StandardScaler.fit, nn.adam_step
    retained, current, durations = [], {}, []

    def counted_scaler(obj, x, *args, **kwargs):
        counts["scaler_fit_calls"] += 1
        if counts["scaler_fit_calls"] > 11:
            raise ValueError("Unexpected scaler refit")
        return scaler_fit(obj, x, *args, **kwargs)

    def counted_logistic(obj, x, y, *args, **kwargs):
        counts["logistic_fit_calls"] += 1
        if counts["logistic_fit_calls"] > 10 or len(y) != len(current["train"]):
            raise ValueError("Unexpected Logistic fit")
        np.testing.assert_array_equal(y, current["train"].result.to_numpy())
        return lr_fit(obj, x, y, *args, **kwargs)

    def counted_adam(*args, **kwargs):
        counts["adam_updates"] += 1
        if args[-1] != counts["adam_updates"] or counts["adam_updates"] > 200:
            raise ValueError("Unexpected Adam update")
        return adam(*args, **kwargs)

    def baseline_fit(train):
        n = counts["crossfit_baseline"] + counts["final_baseline"]
        if n >= 10:
            raise ValueError("Unexpected baseline refit")
        fold = plan["folds"][n] if n < 9 else None
        expected = fold["training_ids"] if fold else plan["final_baseline_fit_ids"]
        if train.match_id.tolist() != expected or (fold and not train.season.lt(fold["target_year"]).all()):
            raise ValueError("Baseline training-year/ID mismatch")
        role = "crossfit_baseline" if fold else "final_baseline"
        counts[role] += 1
        event = {"role": role, "fit_number": n+1, "started_at": now(),
                 "training_ids": expected, "training_years": sorted(map(int, train.season.unique())),
                 "target_year": fold["target_year"] if fold else None}
        write_json(root/"fit-events"/f"{n+1:02d}-started.json", event)
        current["train"] = train
        model = original_fit(train)
        if any(model is old or model[0] is old[0] or model[-1] is old[-1] for old in retained):
            raise ValueError("Estimator/scaler instance reused")
        retained.append(model)
        raw = train[["elo_diff"]].to_numpy(dtype=float)
        np.testing.assert_allclose(model[0].mean_, raw.mean(axis=0), rtol=0, atol=1e-10)
        np.testing.assert_allclose(model[0].var_, raw.var(axis=0), rtol=1e-12, atol=1e-10)
        event.update(finished_at=now(), scaler_rows=int(model[0].n_samples_seen_),
                     scaler_mean=model[0].mean_.tolist(), scaler_var=model[0].var_.tolist(),
                     scaler_scale=model[0].scale_.tolist(), class_order=model.classes_.tolist(),
                     iterations=model[-1].n_iter_.tolist())
        destination = root/"crossfit"/f"{fold['target_year']}.joblib" if fold else root/"final-baseline/model.joblib"
        event["model_sha256"] = save_joblib(destination, model)
        write_json(root/"fit-events"/f"{n+1:02d}-succeeded.json", event)
        durations.append(event)
        return model

    with ExitStack() as stack, warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        stack.enter_context(patch.object(offsets, "_fit", baseline_fit))
        stack.enter_context(patch.object(LogisticRegression, "fit", counted_logistic))
        stack.enter_context(patch.object(StandardScaler, "fit", counted_scaler))
        stack.enter_context(patch.object(nn, "adam_step", counted_adam))
        cross = offsets.generate_crossfit_offsets(frame)
        ids = plan["residual_scaler_fit_ids"]
        if cross.rows.match_id.tolist() != ids:
            raise ValueError("Offset order/union mismatch")
        for actual, expected in zip(cross.audit, plan["folds"], strict=True):
            if actual["training_ids"] != expected["training_ids"] or actual["target_ids"] != expected["target_ids"]:
                raise ValueError("Actual cross-fit IDs differ from seal")
        csv(root/"crossfit-offsets.csv", cross.rows)
        base_cols = ["base_logit_away", "base_logit_draw", "base_logit_home"]
        base = nn.finite(cross.rows[base_cols].to_numpy(), (len(ids), 3))
        save_npz(root/"crossfit-offsets.npz", logits=base, match_ids=np.asarray(ids), classes=np.array([0, 1, 2]))
        write_json(root/"crossfit-audit.json", list(cross.audit))
        final = offsets.fit_final_baseline(frame)
        save_joblib(root/"final-baseline/scaler.joblib", final.pipeline[0])
        write_json(root/"final-baseline/metadata.json", final.audit)
        training = frame.loc[frame.match_id.isin(ids)].copy()
        if training.match_id.tolist() != ids:
            raise ValueError("Residual Form join mismatch")
        form = training[list(nn.FORM_FEATURES)]
        nn.feature_array(form)
        write_json(root/"fit-events/11-started.json", {"role": "residual_nn", "started_at": now(), "training_ids": ids})
        counts["residual_nn"] += 1
        model = nn.ResidualNN().fit(form, base, training.result.to_numpy())
        if caught:
            raise ValueError("Fit warning: "+",".join(type(w.message).__name__ for w in caught))
    expected_counts = dict(crossfit_baseline=9, final_baseline=1, residual_nn=1,
                           logistic_fit_calls=10, scaler_fit_calls=11, adam_updates=200)
    if counts != expected_counts or model.n_iter_ != 200 or len(model.theta_) != 90:
        raise ValueError("Fit/update budget mismatch")
    x = nn.feature_array(form)
    if model.scaler_.n_samples_seen_ != len(ids):
        raise ValueError("Residual scaler population mismatch")
    np.testing.assert_allclose(model.scaler_.mean_, x.mean(axis=0), rtol=0, atol=1e-12)
    np.testing.assert_allclose(model.scaler_.var_, x.var(axis=0), rtol=0, atol=1e-12)
    nn.finite(model.loss_curve_, (200,))
    probabilities = model.predict_proba(form, base)
    delta = model.residual_logits(form, base)
    assert_probabilities(probabilities)
    if (np.abs(delta) > 0.25).any():
        raise ValueError("Residual bound mismatch")
    adjusted = base.copy(); adjusted[:, 0] += delta[:, 0]; adjusted[:, 2] += delta[:, 1]
    np.testing.assert_allclose(probabilities, np.exp(nn.log_softmax(adjusted)), rtol=0, atol=1e-14)
    model.save(root/"residual")
    save_npz(root/"residual-scaler.npz", mean=model.scaler_.mean_, var=model.scaler_.var_,
             scale=model.scaler_.scale_, training_rows=np.array(len(ids)))
    csv(root/"training-loss.csv", pd.DataFrame({"update": range(1, 201), "training_objective": model.loss_curve_}))
    csv(root/"training-inputs.csv", frame[["match_id", "season", *timing.TIMING_COLUMNS, *loader.FEATURES]])
    write_json(root/"fit-events/11-succeeded.json", {"role": "residual_nn", "finished_at": now(),
               "training_rows": len(ids), "parameters": 90, "updates": 200})
    # Synthetic inputs only for the independent saved-model reproduction probe.
    probe = pd.DataFrame([[0]*8, [1,1,3,0,1,0,0,1], [5,5,8,7,9,7,6,8],
                          [5,4,0,12,0,12,10,0], [5,5,15,15,20,20,0,0]], columns=nn.FORM_FEATURES)
    elo = pd.DataFrame({"elo_diff": [-10000., -400., 0., 400., 10000.]})
    logits = final.decision_function(elo)
    pp = model.predict_proba(probe, logits); assert_probabilities(pp)
    write_json(root/"technical-probe.json", {"data_origin": "synthetic", "role": "serialization_test_only_not_forecast",
               "elo": elo.elo_diff.tolist(), "form": probe.values.tolist(),
               "baseline_logits": logits.tolist(), "residual_probabilities": pp.tolist()})
    write_json(root/"fit-counts.json", counts)
    return counts


def verify_models(root):
    """Independent readback: no fitting, labels or performance calculation."""
    root = Path(root)
    base = joblib.load(root/"final-baseline/model.joblib")
    scaler = joblib.load(root/"final-baseline/scaler.joblib")
    np.testing.assert_array_equal(base.classes_, [0, 1, 2])
    for key in ("mean_", "var_", "scale_"):
        np.testing.assert_array_equal(getattr(base[0], key), getattr(scaler, key))
    residual = nn.ResidualNN.load(root/"residual", expected_sha256=sha(root/"residual/artifact.json"))
    with np.load(root/"residual-scaler.npz", allow_pickle=False) as stored:
        for key in ("mean", "var", "scale"):
            np.testing.assert_array_equal(stored[key], getattr(residual.scaler_, key+"_"))
        if int(stored["training_rows"]) != residual.scaler_.n_samples_seen_:
            raise ValueError("Residual scaler readback mismatch")
    probe = json.loads((root/"technical-probe.json").read_bytes())
    if probe["data_origin"] != "synthetic":
        raise ValueError("Readback probe must be synthetic")
    values = offsets._logits(base, pd.DataFrame({"elo_diff": probe["elo"]}))
    np.testing.assert_array_equal(values, probe["baseline_logits"])
    pp = residual.predict_proba(pd.DataFrame(probe["form"], columns=nn.FORM_FEATURES), values)
    np.testing.assert_array_equal(pp, probe["residual_probabilities"]); assert_probabilities(pp)
    rows = pd.read_csv(root/"crossfit-offsets.csv", dtype={"match_id": str}, float_precision="round_trip")
    with np.load(root/"crossfit-offsets.npz", allow_pickle=False) as stored:
        if rows.match_id.tolist() != stored["match_ids"].tolist():
            raise ValueError("Offset readback IDs differ")
        np.testing.assert_array_equal(rows.iloc[:, 2:].to_numpy(), stored["logits"])
    inputs = pd.read_csv(root/"training-inputs.csv", dtype={"match_id": str}, float_precision="round_trip").set_index("match_id")
    audits = json.loads((root/"crossfit-audit.json").read_bytes())
    for fold in audits:
        pipeline = joblib.load(root/"crossfit"/f"{fold['target_year']}.joblib")
        target = inputs.loc[fold["target_ids"], ["elo_diff"]]
        logits = offsets._logits(pipeline, target)
        actual = rows.loc[rows.season.eq(fold["target_year"])].iloc[:, 2:].to_numpy()
        np.testing.assert_array_equal(logits, actual)
        for key in ("mean", "var"):
            np.testing.assert_array_equal(getattr(pipeline[0], key+"_"), fold["scaler_"+key])
        if pipeline[0].n_samples_seen_ != fold["scaler_rows"]:
            raise ValueError("Cross-fit scaler readback mismatch")
    return {"status": "PASS", "synthetic_probe_rows": len(pp), "model_probability_max_abs_difference": 0.0,
            "offset_rows": len(rows), "crossfit_models_read_back": 9, "performance_evaluations": 0, "fits": 0}


def training_plot(root):
    # Keep matplotlib's cache inside this new research output, not a user profile.
    os.environ["MPLCONFIGDIR"] = str(root/"matplotlib-cache")
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    curve = pd.read_csv(root/"training-loss.csv")
    figure = Figure(figsize=(8, 4), layout="constrained")
    axes = figure.subplots()
    axes.plot(curve["update"], curve.training_objective)
    axes.set(xlabel="Adam update", ylabel="Training objective (CE + L2)",
             title="NN v2 fixed 200 updates - training only, no performance evaluation")
    axes.grid(alpha=0.25)
    figure.savefig(root/"training-loss.png", dpi=160)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=("preflight", "train", "verify"))
    p.add_argument("--manifest", type=Path)
    p.add_argument("--source-root", type=Path)
    p.add_argument("--evidence-root", type=Path)
    p.add_argument("--execution-seal", type=Path)
    p.add_argument("--seal-sha")
    p.add_argument("--artifact-root", type=Path)
    args = p.parse_args()
    if args.mode == "verify":
        seal = args.artifact_root/"artifact-seal.json"
        if sha(seal) != args.seal_sha:
            raise ValueError("Externally pinned artifact seal mismatch")
        data = json.loads(seal.read_bytes())
        for name, digest in data["files"].items():
            if sha(args.artifact_root/name) != digest:
                raise ValueError("Sealed payload mismatch")
        print(json.dumps(verify_models(args.artifact_root)))
        return
    m, frame = preflight(args.manifest, args.source_root, args.evidence_root)
    root = Path(m["output_contract"]["training_output"])
    marker = root.parent/"NNResearch-study-attempts"/(STUDY+".json")
    if root.exists() or marker.exists():
        raise ValueError("Existing output/attempt; same-study retry forbidden")
    if args.mode == "preflight":
        print(json.dumps({"status": "PREFLIGHT_PASS_NO_FIT", "rows": len(frame), "residual_rows": 2976,
                          "manifest_sha256": MANIFEST_SHA, "versions": nn.versions(), "fits": 0}))
        return
    execution_sha = args.seal_sha or os.environ.get("J1AI_NN_EXECUTION_SEAL_SHA256")
    if sha(args.execution_seal) != execution_sha:
        raise ValueError("Execution seal SHA mismatch")
    execution = json.loads(args.execution_seal.read_bytes())
    if execution["study_id"] != STUDY or execution["manifest_sha256"] != MANIFEST_SHA or execution["output"] != str(root):
        raise ValueError("Execution seal scope mismatch")
    for name, digest in execution["implementation_sha256"].items():
        if sha(ROOT/name) != digest:
            raise ValueError("Execution driver/dependency changed")
    plain_parent(root.parent)
    plain_parent(marker.parent)
    marker.parent.mkdir(exist_ok=True)
    write_json(marker, {"study_id": STUDY, "state": "STARTED", "at": now(), "manifest_sha256": MANIFEST_SHA,
                        "execution_seal_sha256": execution_sha, "pid": os.getpid(), "retry": False})
    root.mkdir(exist_ok=False)
    try:
        write_json(root/"attempt-receipt.json", json.loads(marker.read_bytes()))
        for name, path in (("study-manifest.json", args.manifest), ("execution-seal.json", args.execution_seal)):
            with (root/name).open("xb") as f:
                f.write(path.read_bytes()); f.flush(); os.fsync(f.fileno())
        write_json(root/"environment.json", nn.versions())
        write_json(root/"input-pins.json", m["raw_data_sha256"])
        counts = fit_once(frame, m["crossfit"], root)
        write_json(root/"technical-readback.json", verify_models(root))
        training_plot(root)
        artifact = {"schema": "nn_v2_study_artifact_manifest_v1", "role": "research_only_not_champion",
            "data_origin": "real", "study_id": STUDY, "residual_sha256": sha(root/"residual/artifact.json"),
            "baseline_sha256": sha(root/"final-baseline/model.joblib"), "implementation_sha256": sha(__file__),
            "spec_sha256": auditor.canonical_sha(m["numeric_specification"]), "training_manifest_sha256": MANIFEST_SHA,
            "input_sha256": m["raw_data_sha256"], "feature_order": list(nn.FORM_FEATURES), "class_order": [0,1,2],
            "timing_policy": timing.POLICY, "source_rows": 3588, "residual_rows": 2976, "sealed_at": now()}
        validate_artifact_manifest(artifact)
        write_json(root/"artifact-manifest.json", artifact)
        seal = {"schema": "nn_v2_final_artifact_seal_v1", "status": "TRAINED_AND_SEALED_RESEARCH_ONLY",
            "study_id": STUDY, "manifest_sha256": MANIFEST_SHA, "execution_seal_sha256": execution_sha,
            "sealed_at": now(), "fit_counts": counts, "performance_evaluations": 0,
            "future_predictions_saved": 0, "T0": None,
            "files": {q.relative_to(root).as_posix(): sha(q) for q in sorted(root.rglob("*")) if q.is_file()}}
        write_json(root/"artifact-seal.json", seal)
        write_json(root/"SUCCEEDED.json", {"status": seal["status"], "finished_at": now(),
            "artifact_seal_sha256": sha(root/"artifact-seal.json"), "fit_counts": counts})
        print(json.dumps({"status": seal["status"], "artifact_seal_sha256": sha(root/"artifact-seal.json"), "fit_counts": counts}))
    except Exception as exc:
        write_json(root/"FAILED.json", {"state": "FAILED", "at": now(), "exception_type": type(exc).__name__,
                                       "diagnostic": str(exc), "retry": False})
        raise


if __name__ == "__main__":
    main()
