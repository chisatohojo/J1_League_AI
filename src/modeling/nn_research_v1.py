"""Independent fixed-spec ordinary-J1 NN research; no operational write paths."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from src.collect.matches import load_matches
from src.collect.teams import load_team_master
from src.features.elo_history import _prepare_ordinary_matches
from src.features.form import add_form_features
from src.modeling.player_workload_evaluation import _add_elo
from src.features.nn_research_timing import (
    POLICY, TIMING_COLUMNS, build_event_features, validate_timed_state, review_cache,
    REVIEW_PATH,
)

ROOT = Path(__file__).resolve().parents[2]
FEATURES = (
    "elo_diff", "home_last5_matches_available", "away_last5_matches_available",
    "home_last5_points", "away_last5_points", "home_last5_goals_for",
    "away_last5_goals_for", "home_last5_goals_against", "away_last5_goals_against",
)
CLASSES = (0, 1, 2)
YEARS = (2020, 2021, 2022, 2023, 2024)
COUNTS = {y: 380 if y in (2021, 2024, 2025) else 306 for y in range(2015, 2026)}
NAMES = ("elo_logistic", "form_logistic", "mlp")
LOGISTIC_PARAMS = dict(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)
MLP_PARAMS = dict(
    hidden_layer_sizes=(32, 16), activation="relu", solver="adam", alpha=0.01,
    learning_rate_init=0.001, random_state=42, max_iter=500, early_stopping=False,
    batch_size="auto", learning_rate="constant", power_t=0.5, shuffle=True,
    tol=0.0001, verbose=False, warm_start=False, momentum=0.9,
    nesterovs_momentum=True, validation_fraction=0.1, beta_1=0.9, beta_2=0.999,
    epsilon=1e-8, n_iter_no_change=10, max_fun=15000,
)
REFERENCE = {
    2020: (1.023119734659012, 0.611757221871064, 0.506535947712418),
    2021: (1.025343721048779, 0.614982913867462, 0.507894736842105),
    2022: (1.094018638537145, 0.661022433916161, 0.401960784313726),
    2023: (1.060428556859565, 0.638530529273072, 0.460784313725490),
    2024: (1.079241181120235, 0.653169594366402, 0.450000000000000),
    "pooled": (1.056065401323764, 0.635732341929272, 0.466626936829559),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def jsonable(value):
    return json.loads(json.dumps(value, allow_nan=False))


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")


def specification():
    return jsonable({
        "name": "nn_research_v1_phase1", "features": FEATURES, "classes": CLASSES,
        "mlp": MLP_PARAMS, "logistic": LOGISTIC_PARAMS,
        "scaler": {"with_mean": True, "with_std": True},
        "elo": {"initial": 1500, "K": 30, "home_advantage": 175},
        "validation_seasons": YEARS, "expected_season_counts": COUNTS,
        "final_training_rows": 3588, "primary_metric": "multiclass_log_loss",
        "brier_definition": "mean(sum((p-one_hot)**2, axis=1))",
        "cpu_threads": 1, "tuning": False, "early_stopping": False,
        "chronology": POLICY,
        "resumption_exception": {"match_id": "30700", "recorded_date": "2024-11-22",
                                 "original_kickoff": "2024-08-24T19:03:00+09:00",
                                 "history_cutoff": "2024-08-24T00:00:00+09:00",
                                 "result_effective": "2024-11-23T00:00:00+09:00",
                                 "label": "final_90_min_draw", "source_date_unchanged": True},
        "evidence_manifest_sha256": sha(ROOT / "research/nn_v1/timing-v1_1/evidence-manifest.json"),
        "timing_registry_sha256": sha(REVIEW_PATH),
        "all_three_models_share_event_features": True,
        "legacy_historical_reference_is_required_gate": False,
        "unknown_timing_case": "STOP before any fit",
        "historical_publication_asof_proven": False,
        "spent_validation": True, "evaluate_2025": False, "use_2026": False,
        "convergence_warning_policy": "record; no retry; finite fixed-budget fit is not a technical exception",
        "production_connection": False,
    })


def verify_spec(path):
    if json.loads(Path(path).read_bytes()) != specification():
        raise ValueError("Frozen specification mismatch")


def load_source(source_root, pins_path):
    source_root = Path(source_root).resolve()
    pins = json.loads(Path(pins_path).read_bytes())
    expected = {f"data/processed/jleague/{y}_matches_probe.csv" for y in COUNTS}
    expected.add("data/master/teams.csv")
    if set(pins) != expected:
        raise ValueError("Only the 11 ordinary-J1 tables and TeamMaster are allowed")
    for name, digest in pins.items():
        if sha(source_root / name) != digest:
            raise ValueError(f"Source SHA mismatch: {name}")
    master = load_team_master(source_root / "data/master/teams.csv")
    frames = []
    for year, count in COUNTS.items():
        f = load_matches(source_root / f"data/processed/jleague/{year}_matches_probe.csv")
        if len(f) != count or not f.season.eq(year).all():
            raise ValueError(f"Season population mismatch: {year}")
        frames.append(f)
    source = _prepare_ordinary_matches(pd.concat(frames, ignore_index=True), master)
    if len(source) != 3588 or not source.match_id.is_unique:
        raise ValueError("Expected 3588 unique ordinary-J1 matches")
    return source, pins


def validate_features(frame):
    if frame.columns.has_duplicates or set(FEATURES) - set(frame.columns):
        raise ValueError("Feature schema mismatch")
    x = frame.loc[:, list(FEATURES)]
    if any(not pd.api.types.is_numeric_dtype(x[c]) or pd.api.types.is_bool_dtype(x[c]) for c in FEATURES):
        raise ValueError("Features must be numeric")
    values = x.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError("Nonfinite or missing feature")
    for side in ("home", "away"):
        count = x[f"{side}_last5_matches_available"].to_numpy()
        if not ((count >= 0) & (count <= 5) & (count == np.floor(count))).all():
            raise ValueError("Invalid prior-match count")
        for kind in ("points", "goals_for", "goals_against"):
            v = x[f"{side}_last5_{kind}"].to_numpy()
            if ((v < 0) | (v != np.floor(v)) | ((count == 0) & (v != 0))).any():
                raise ValueError("Invalid prior form total")
            if kind == "points" and (v > 3 * count).any():
                raise ValueError("Points exceed prior-match count")
    return x


def legacy_features(matches):
    """Reuse reviewed day-batched Elo and form; reject duplicate day/club."""
    ordered = matches.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    # _add_elo checks unique appearances/day before any result update. Thus
    # add_form_features' per-row independent-club reads equal day-batched reads.
    frame = add_form_features(_add_elo(ordered))
    for side in ("home", "away"):
        frame[f"{side}_last5_matches_available"] = sum(
            frame[f"{side}_last5_{c}"] for c in ("wins", "draws", "losses")
        )
    validate_features(frame)
    return frame


def build_features(matches):
    frame = build_event_features(matches)
    validate_features(frame)
    return frame


def require_original_kickoff_timing(matches):
    """The registered event needs validated original-start/result metadata."""
    if "match_id" not in matches or matches.match_id.isna().any():
        raise ValueError("Missing temporal identity")
    validate_timed_state(matches)


def probabilities(p, count):
    p = np.asarray(p, dtype=float)
    if (p.shape != (count, 3) or not np.isfinite(p).all()
            or ((p < 0) | (p > 1)).any()
            or not np.allclose(p.sum(axis=1), 1.0, atol=1e-12, rtol=0)):
        raise ValueError("Invalid class probabilities")
    return p


def metrics(y, p):
    y = np.asarray(y)
    if y.ndim != 1 or not np.isin(y, CLASSES).all() or not len(y):
        raise ValueError("Invalid target classes")
    p = probabilities(p, len(y))
    return dict(n=len(y), log_loss=float(log_loss(y, p, labels=list(CLASSES))),
                brier=float(np.mean(np.sum((p - (y[:, None] == CLASSES)) ** 2, axis=1))),
                accuracy=float(accuracy_score(y, np.asarray(CLASSES)[p.argmax(axis=1)])))


def estimator(name):
    if name not in NAMES:
        raise ValueError("Unknown fixed model")
    clf = MLPClassifier(**MLP_PARAMS) if name == "mlp" else LogisticRegression(**LOGISTIC_PARAMS)
    return Pipeline([("scaler", StandardScaler()), ("classifier", clf)])


def fit(name, train):
    require_original_kickoff_timing(train)
    if "season" not in train or not train.season.isin(range(2015, 2026)).all():
        raise ValueError("Fit permits only 2015--2025 ordinary-J1 seasons")
    x = validate_features(train)
    columns = ["elo_diff"] if name == "elo_logistic" else list(FEATURES)
    if set(train.result.unique()) != set(CLASSES):
        raise ValueError("All three training classes are required")
    model = estimator(name)
    started = time.perf_counter()
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(x[columns], train.result)
    elapsed = time.perf_counter() - started
    clf = model.named_steps["classifier"]
    if tuple(clf.classes_) != CLASSES:
        raise ValueError("Class order mismatch")
    for w in caught:
        if not issubclass(w.category, ConvergenceWarning):
            raise RuntimeError(f"Unexpected fit warning: {w.category.__name__}")
    for values in (model.named_steps["scaler"].mean_, model.named_steps["scaler"].scale_):
        if not np.isfinite(values).all():
            raise ValueError("Invalid scaler state")
    curve = [float(v) for v in getattr(clf, "loss_curve_", [])]
    if curve and not np.isfinite(curve).all():
        raise ValueError("Nonfinite MLP loss")
    weights = [*clf.coefs_, *clf.intercepts_] if name == "mlp" else [clf.coef_, clf.intercept_]
    if not all(np.isfinite(w).all() for w in weights):
        raise ValueError("Nonfinite fitted weights")
    report = {"seconds": elapsed, "iterations": int(np.max(clf.n_iter_)),
              "converged": not caught, "warnings": [w.category.__name__ for w in caught],
              "loss_curve": curve, "scaler_training_rows": int(model.named_steps["scaler"].n_samples_seen_)}
    return model, report


def score_model(name, model, validation):
    require_original_kickoff_timing(validation)
    if "season" not in validation or not validation.season.isin(range(2015, 2025)).all():
        raise ValueError("No 2025 spent-test or 2026 evaluation")
    x = validate_features(validation)
    columns = ["elo_diff"] if name == "elo_logistic" else list(FEATURES)
    with threadpool_limits(limits=1):
        return probabilities(model.predict_proba(x[columns]), len(validation))


def legacy_reference_delta(measured, scope):
    """Different chronology: diagnostic comparison, never an acceptance gate."""
    return {k: float(measured[k] - ref) for k, ref in
            zip(("log_loss", "brier", "accuracy"), REFERENCE[scope])}


def evaluate(frame, output):
    """No 2025 metric access; no fitting or scoring of production artifacts."""
    require_original_kickoff_timing(frame)
    frame = frame.loc[frame.season.between(2015, 2024)].copy()
    if frame.season.value_counts().to_dict() != {y: n for y, n in COUNTS.items() if y < 2025}:
        raise ValueError("Historical population mismatch")
    folds, rows, curves = [], [], {}
    for year in YEARS:
        train = frame.loc[frame.season.lt(year)]
        valid = frame.loc[frame.season.eq(year)]
        if train.match_date.max() >= valid.match_date.min():
            raise ValueError("Fold chronology overlap")
        for name in NAMES:
            print(f"Fitting {name}: validation={year}, train={len(train)}, validation={len(valid)}", flush=True)
            model, training = fit(name, train)
            p = score_model(name, model, valid)
            measured = metrics(valid.result, p)
            folds.append({"model": name, "fold": year, "train": len(train), **measured,
                          **{k: v for k, v in training.items() if k != "loss_curve"}})
            if name == "elo_logistic":
                folds[-1]["legacy_reference_delta"] = legacy_reference_delta(measured, year)
            if name == "mlp":
                curves[str(year)] = training["loss_curve"]
            result = valid[["match_id", "season", "match_date", "home_team_id", "away_team_id", "result"]].copy()
            result["model"] = name
            result[["p_away", "p_draw", "p_home"]] = p
            result["predicted_class"] = np.asarray(CLASSES)[p.argmax(axis=1)]
            rows.append(result)
        write_json(output / f"fold-{year}.json", folds[-3:])
    oof = pd.concat(rows, ignore_index=True)
    pooled = []
    for name in NAMES:
        selected = oof.loc[oof.model.eq(name)]
        if len(selected) != 1678 or not selected.match_id.is_unique:
            raise ValueError("Pooled OOF membership mismatch")
        m = metrics(selected.result, selected[["p_away", "p_draw", "p_home"]])
        pooled.append({"model": name, **m})
        if name == "elo_logistic":
            pooled[-1]["legacy_reference_delta"] = legacy_reference_delta(m, "pooled")
    pd.DataFrame(folds).to_csv(output / "fold-metrics.csv", index=False)
    pd.DataFrame(pooled).to_csv(output / "pooled-metrics.csv", index=False)
    oof.to_csv(output / "oof-predictions.csv", index=False)
    return folds, pooled, curves


def audit(source_root, source, state, pins, output, timing_review=None):
    summary = {
        "rows": len(state), "historical_rows": int(state.season.lt(2025).sum()),
        "season_counts": {str(k): int(v) for k, v in state.season.value_counts().sort_index().items()},
        "ordinary_J1_only": True, "input_sha256": pins,
        "unknown_original_publication_times": True,
        "historical_PIT_claim": "original-start prior-day features; final-result publication/correction availability not proven as-of",
        "exceptions": [{"match_id": "30700", "recorded_date": "2024-11-22",
                        "original_kickoff_date": "2024-08-24", "original_kickoff_feature_time_resolved": True,
                        "result_effective": "2024-11-23T00:00:00+09:00",
                        "disposition": "REGISTERED_FEATURE_RESULT_EVENT_SPLIT"}],
        "historical_training_readiness": "READY_CHRONOLOGY_ONLY_NO_FIT",
        "source_dates_changed": False, "same_day_team_collisions": 0,
        "missing_value_policy": "fail; cold-start history totals=0 with available count=0",
        "existing_features_used_as_training_input": False,
        "excluded_input_families": ["current-match score/result/stats", "xg", "snapshots", "suspensions", "2026 results", "retrospective predictions"],
    }
    write_json(output / "dataset-audit.json", summary)
    entries = []
    for c in FEATURES:
        for end in (2024, 2025):
            values = state.loc[state.season.le(end), c]
            entries.append(dict(source="rebuilt ordinary-J1 history", feature=c, scope=f"2015-{end}",
                rows=len(values), nonmissing=int(values.notna().sum()), missing=int(values.isna().sum()),
                coverage=float(values.notna().mean()), selected=True,
                minimum=float(values.min()), maximum=float(values.max()),
                admitted_to_historical_training=False,
                original_kickoff_timing="resolved feature/result split; publication as-of not proven",
                timing="only results effective by the original feature-day midnight",
                provenance="pinned yearly CSVs + exact TeamMaster + reviewed Elo/form helpers"))
    inventory = []
    allowed_ids = set(source.match_id)
    directory = Path(source_root) / "data/processed/features"
    for path in sorted(directory.glob("*.csv")):
        frame = pd.read_csv(path, dtype={"match_id": str})
        inventory.append({"path": str(path.relative_to(source_root)).replace("\\", "/"),
                          "rows": len(frame), "sha256": sha(path), "used_for_training": False})
        # Audit values only; no join of these historical/2026 artifacts into state.
        historical = frame.loc[frame.match_id.isin(allowed_ids)] if "match_id" in frame else frame.iloc[:0]
        for c in frame.columns:
            if c in {"match_id", "match_date", "season", "competition", "home_team_id", "away_team_id"}:
                continue
            values = historical[c]
            entries.append(dict(source=str(path.relative_to(source_root)).replace("\\", "/"), feature=c,
                scope="matched ordinary-J1 IDs (audit only)", rows=len(values),
                nonmissing=int(values.notna().sum()), missing=int(values.isna().sum()),
                coverage=float(values.notna().mean()) if len(values) else 0, selected=False,
                minimum=None, maximum=None,
                admitted_to_historical_training=False,
                original_kickoff_timing="NOT_ESTABLISHED",
                timing="not admitted: closed/deferred experiment or unproven historical PIT/coverage",
                provenance="existing derived artifact; SHA recorded; no eligibility inferred from nonmissing values"))
    write_json(output / "existing-feature-assets.json", inventory)
    pd.DataFrame(entries).to_csv(output / "feature-audit.csv", index=False)
    lines = ["# Training-data audit", "", f"Ordinary J1: {len(state)} rows; historical evaluation: 3208.",
        "Nine selected features are finite and have 100% computational coverage. Empty-history totals are genuine zeros, not future-value imputation.",
        "", "## Timing boundary", "",
        "All inputs derive from results effective at the original feature-day midnight. Publication/correction timestamps are not proven; this is historical reconstruction, not a strict contemporaneous publication as-of claim.",
        "Match 30700 freezes features before 2024-08-24, retains its Draw label and original CSV date 2024-11-22, and becomes completed history only from 2024-11-23. No halftime score is a completed-history event. All three research models share this chronology; the old frozen metric values are informational, not an equality gate.",
        "", "## Other assets", "",
        "`feature-audit.csv` lists every saved feature column's observed ordinary-J1 coverage and missingness. `existing-feature-assets.json` records its source SHA. These are audit-only; none is joined into training.",
        "Current-match scores/results/stats are labels or post-match evidence, never feature inputs. xG lacks 2015--2024 coverage. Snapshots/suspensions lack the necessary historical PIT proof. Existing closed/deferred features remain excluded.",
        "", "## Scope", "", "2020--2024 were previously explored. 2025 is a spent test used only in final training. No 2026 performance is accessed. No benchmark decision is rewritten."]
    (output / "DATA_AUDIT.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    if timing_review is not None:
        write_json(output / "source-timing-review.json", timing_review)
    old = legacy_features(source).set_index("match_id")
    new = state.set_index("match_id")
    delta = []
    for mid in new.index:
        for c in FEATURES:
            if new.loc[mid, c] != old.loc[mid, c]:
                delta.append({"match_id": mid, "feature": c, "legacy": float(old.loc[mid, c]),
                              "event_policy": float(new.loc[mid, c])})
    pd.DataFrame(delta, columns=["match_id", "feature", "legacy", "event_policy"]).to_csv(output / "legacy-feature-delta.csv", index=False)
    state[["match_id", "season", "home_team_id", "away_team_id", *TIMING_COLUMNS]].to_csv(output / "timing-events.csv", index=False)
    write_json(output / "chronology-comparison.json", {
        "old_policy": "recorded source date for feature and result", "new_policy": POLICY,
        "changed_fixture_ids": sorted({d["match_id"] for d in delta}), "changed_feature_cells": len(delta),
        "source_row_count": len(source), "source_dates_changed": False,
        "legacy_reference_gate": False, "historical_fit_evaluate_final_fit": [0, 0, 0],
        "all_three_models_share_feature_builder": True})


def plots(folds, pooled, curves, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.family": "DejaVu Sans"}):
        fig, ax = plt.subplots(figsize=(8, 5))
        for label, curve in curves.items():
            ax.plot(range(1, len(curve) + 1), curve, label=label)
        ax.set(xlabel="Epoch", ylabel="Training optimization loss", title="Fixed MLP: training loss (no validation tuning)")
        ax.legend(); fig.tight_layout(); fig.savefig(output / "training-curves.png", dpi=160); plt.close(fig)
        fig, axes = plt.subplots(1, 3, figsize=(13, 4))
        for ax, metric in zip(axes, ("log_loss", "brier", "accuracy")):
            ax.bar([p["model"] for p in pooled], [p[metric] for p in pooled])
            ax.set_title("Pooled OOF " + metric); ax.tick_params(axis="x", rotation=20)
        fig.tight_layout(); fig.savefig(output / "pooled-comparison.png", dpi=160); plt.close(fig)
        fig, ax = plt.subplots(figsize=(8, 5))
        for name in NAMES:
            selected = [f for f in folds if f["model"] == name]
            ax.plot([f["fold"] for f in selected], [f["log_loss"] for f in selected], marker="o", label=name)
        ax.set(xlabel="Validation year", ylabel="Multiclass Log Loss", xticks=YEARS)
        ax.legend(); fig.tight_layout(); fig.savefig(output / "fold-log-loss.png", dpi=160); plt.close(fig)


def seal(output):
    files = [{"path": p.relative_to(output).as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
             for p in sorted(output.rglob("*")) if p.is_file()]
    write_json(output / "SHA256-MANIFEST.json", {"algorithm": "SHA-256", "files": files})
    for item in files:
        if sha(output / item["path"]) != item["sha256"]:
            raise ValueError("Output readback mismatch")


def run(source_root, output, *, audit_only=False):
    output = Path(output).resolve()
    source_root = Path(source_root).resolve()
    if source_root == output or source_root in output.parents:
        raise ValueError("Outputs must be outside the read-only source repository")
    verify_spec(ROOT / "research/nn_v1/frozen-spec.json")
    source, pins = load_source(source_root, ROOT / "research/nn_v1/input-pins.json")
    timing_review = review_cache(source_root, source)
    state = build_features(source)
    if not audit_only:
        require_original_kickoff_timing(state)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "attempt.json", {"started_at": now(), "spec_sha256": sha(ROOT / "research/nn_v1/frozen-spec.json"),
                                        "original_kickoff_required": True, "audit_only": audit_only})
    try:
        audit(source_root, source, state, pins, output, timing_review)
        if audit_only:
            seal(output)
            return {"status": "AUDIT_COMPLETE_NO_FIT", "rows": len(state)}
        folds, pooled, curves = evaluate(state, output)
        # All historical fits and evaluations passed. The spent 2025 targets
        # enter only this single final fit, never a test/selection metric.
        print("Fitting final research-only MLP once: 2015--2025, 3588 rows", flush=True)
        final, training = fit("mlp", state)
        curves["final_2015_2025"] = training["loss_curve"]
        artifact = output / "artifact"
        artifact.mkdir()
        joblib.dump(final.named_steps["classifier"], artifact / "model.joblib")
        joblib.dump(final.named_steps["scaler"], artifact / "scaler.joblib")
        state[["match_id", "season", "match_date", "home_team_id", "away_team_id", *TIMING_COLUMNS]].to_csv(artifact / "training-manifest.csv", index=False)
        write_json(artifact / "metadata.json", {"role": "research_only_not_champion", "trained_at": now(),
            "training_rows": len(state), "training_period": ["2015", "2025"], "feature_order": FEATURES,
            "target_mapping": {"0": "Away", "1": "Draw", "2": "Home"}, "specification": specification(),
            "source_sha256": pins, "model_sha256": sha(artifact / "model.joblib"),
            "scaler_sha256": sha(artifact / "scaler.joblib"), "training_manifest_sha256": sha(artifact / "training-manifest.csv"),
            "versions": {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__, "joblib": joblib.__version__},
            "training": {k: v for k, v in training.items() if k != "loss_curve"},
            "feature_result_chronology": POLICY, "historical_publication_asof_proven": False,
            "prediction_use": "not connected to production"})
        # Deserialize only our just-created objects and compare actual arrays;
        # no extra final-training or 2025 evaluation calls are performed.
        restored_mlp, restored_scaler = joblib.load(artifact / "model.joblib"), joblib.load(artifact / "scaler.joblib")
        if tuple(restored_mlp.classes_) != CLASSES or not np.array_equal(restored_scaler.mean_, final.named_steps["scaler"].mean_):
            raise ValueError("Serialized artifact mismatch")
        for a, b in zip(restored_mlp.coefs_, final.named_steps["classifier"].coefs_, strict=True):
            if not np.array_equal(a, b):
                raise ValueError("Serialized weight mismatch")
        write_json(output / "training-curves.json", curves)
        plots(folds, pooled, curves, output)
        result = {"status": "RESEARCH_COMPLETE", "historical_reference": "COMPARISON_ONLY_DIFFERENT_CHRONOLOGY",
                  "oof_rows_per_model": 1678, "pooled": pooled, "final_training": training,
                  "historical_model_fits": 15, "final_mlp_fits": 1, "tuning": False,
                  "completed_at": now(), "phase_A": "BLOCKED", "phase_B": "NOT_AUTHORIZED"}
        write_json(output / "result.json", result)
        for path, digest in pins.items():
            if sha(source_root / path) != digest:
                raise ValueError("Source changed during research")
        seal(output)
        return {k: v for k, v in result.items() if k != "final_training"}
    except BaseException as exc:
        write_json(output / "failure.json", {"type": type(exc).__name__, "message": str(exc),
                                              "at": now(), "automatic_retry": False})
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--audit-only", action="store_true")
    args = p.parse_args()
    if sys.version_info[:3] != (3, 12, 14):
        p.error("The frozen research runtime requires Python 3.12.14")
    print(json.dumps(run(args.source_root, args.output, audit_only=args.audit_only)), flush=True)


if __name__ == "__main__":
    main()
