"""Frozen calibration screen; import/help are stdlib-only and perform no IO.

Real preflight/formal execution needs a later reviewed task. No base model,
source loader, OOF generator, diagnostic runner, or prediction system is imported.
Tests use isolated synthetic arrays/files, never the accepted production pair.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from types import MappingProxyType
import warnings


ROOT = Path(__file__).parents[2]
MODULE_PATH = "src/modeling/champion_a_calibration_evaluation.py"
SPEC_PATH = "docs/CHAMPION_A_CALIBRATION_RESEARCH_SPEC.md"
SPEC_COMMIT = "b5354705f1a7a32e64e2a0d484e22cd55f59d483"
SPEC_SHA = "821e2a35e99bb7c785cd5405aa241ba898ef452123428199ac671a6c50df2e07"
CSV_PATH = "data/processed/model_diagnostics/champion_a_oof_2020_2024.csv"
MANIFEST_PATH = "data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json"
CSV_SHA = "cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59"
MANIFEST_SHA = "b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10"
MARKER_PATH = "data/processed/model_calibration/formal_calibration_attempt.json"
RESULT_PATH = "docs/CHAMPION_A_CALIBRATION_EVALUATION_RESULT.md"
AUTHORIZATION_ENV = "CHAMPION_A_CALIBRATION_AUTHORIZATION"
GENERATOR_COMMIT = "6481780f208ffe95294bdb426a3e572a82a34a98"
GENERATOR_SHA = "40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78"
GENERATION_TASK = "champion-a-oof-one-time-generation-approved-2026-10-05"
REQUIREMENTS_HASHES = {
    "requirements.txt": "887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda",
    "requirements-lock.txt": "3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04",
}
VERSIONS = {"numpy": "2.5.3", "pandas": "3.0.5", "scipy": "1.18.1", "scikit-learn": "1.9.1"}
CLASS_ORDER = (0, 1, 2)
CLASS_NAMES = ("Away", "Draw", "Home")
YEARS = (2020, 2021, 2022, 2023, 2024)
EVALUATION_YEARS = (2021, 2022, 2023, 2024)
YEAR_COUNTS = {2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}
TRAIN_COUNTS = {2021: 306, 2022: 686, 2023: 992, 2024: 1298}
OOF_ROWS, POOLED_ROWS = 1678, 1372
ATOL, RTOL = 1e-12, 0.0
TRAIN_ID_HASHES = {
    2021: "66e2faeb3a51f0ea8e49bd76d1c484d191054997d8753c5acbc8663d3bbf1d35",
    2022: "7b46320d22f92ade52007b02cb495adcc012455d857e7cda4b98d89fe6547e81",
    2023: "4545189f99cc234f3754c4ae96712d207a0d4ad86d64cc40e14c632980c3daf8",
    2024: "0bbb249147c37452c098f85fe48b1f8658db91905888131f0a690bc27a83c391",
}
VALID_ID_HASHES = {
    2020: TRAIN_ID_HASHES[2021],
    2021: "9cd6cfa337ffb0477108775595a56bedb1edca7d05c4f099888bad54f41ded1e",
    2022: "970c316240ee1597bf823d90711995bce334ba3e767f24d6c2d971088fc11803",
    2023: "7a7e5f5dbf26a0ba046dbf8a59a441a05df535bd9b3730299e2e2b2bc9f46cc9",
    2024: "40ccf48bbadc5398d54f11e79f9f2c5f1e914a4ecede086caa3eef77dd72d915",
}
POOLED_ID_SHA = "ae3c676eb346a2e1a77271c1a2b1ed8d5008adadce796d05d555394a61b3708e"
REFERENCES = {
    "2020": {"n": 306, "accuracy": 0.5065359477124183, "log_loss": 1.023119734659012, "brier": 0.6117572218710644},
    "2021": {"n": 380, "accuracy": 0.5078947368421053, "log_loss": 1.0253437210487792, "brier": 0.6149829138674616},
    "2022": {"n": 306, "accuracy": 0.4019607843137255, "log_loss": 1.0940186385371449, "brier": 0.6610224339161608},
    "2023": {"n": 306, "accuracy": 0.46078431372549017, "log_loss": 1.0604285568595655, "brier": 0.638530529273072},
    "2024": {"n": 380, "accuracy": 0.45, "log_loss": 1.079241181120235, "brier": 0.6531695943664019},
    "pooled": {"n": 1678, "accuracy": 0.466626936829559, "log_loss": 1.056065401323764, "brier": 0.6357323419292724},
}
P_COLUMNS = ("p_away", "p_draw", "p_home")
COLUMNS = (
    "validation_year", "match_id", "match_date", "home_team_id", "away_team_id", "result",
    "elo_diff", "p_away", "p_draw", "p_home", "predicted_class", "max_p", "p_true", "nll",
    "brier", "abs_elo_diff", "round", "home_team", "away_team", "season_phase",
    "home_season_appearance", "away_season_appearance", "home_first5", "away_first5",
    "any_team_first5", "both_team_first5", "home_status", "away_status", "promoted_involved",
    "returning_involved", "established_only", "home_favorite", "away_favorite", "near_even",
)
FLOAT_COLUMNS = ("elo_diff", *P_COLUMNS, "max_p", "p_true", "nll", "brier", "abs_elo_diff")
STRING_COLUMNS = ("match_id", "match_date", "home_team_id", "away_team_id", "home_team", "away_team",
                  "season_phase", "home_status", "away_status")
INT_COLUMNS = tuple(c for c in COLUMNS if c not in FLOAT_COLUMNS + STRING_COLUMNS)
DTYPES = {c: "float64" if c in FLOAT_COLUMNS else "string" if c in STRING_COLUMNS else "int64" for c in COLUMNS}
MANIFEST_KEYS = (
    "schema_version", "purpose", "reviewed_source_commit", "freeze_spec", "generation_authorization",
    "generator", "runtime", "inputs", "team_master", "champion_a_contract", "folds", "class_order",
    "columns", "column_dtypes", "row_count", "csv", "references", "observed_metrics",
    "diagnostic_contract", "gates", "generated_at",
)
GATE_NAMES = ("input", "source", "chronology", "folds", "identity", "classes", "probabilities", "references", "serialization")
# Canonical JSON digests of pure metadata from the reviewed generator source,
# calculated without reading the accepted pair or any historical data.
METADATA_HASHES = {
    "inputs": "bb41ec4918ba16cb58d8d6b4d5391af885f52bb85c6b643d74531e35ef7c76de",
    "team_master": "fd6aeb4a14c78ea8cfa07a1f81ffdb4857285c3feb208e0f6e286331b61ab932",
    "champion_a_contract": "a360d71746ba3df8d37df0b47f9cd0f89a2b9baebaff821b3531a2e591032036",
    "diagnostic_contract": "707fd3fb4b9ecebf4dc46e7fa268c368c7025ee18882201d850e18d091fcaf4b",
}
ARTIFACT_FAILURE = "BLOCKED_CALIBRATION_ARTIFACT_INTEGRITY"
OPTIMIZER_FAILURE = "BLOCKED_CALIBRATION_OPTIMIZER_FAILURE"
REFERENCE_FAILURE = "BLOCKED_CALIBRATION_REFERENCE_MISMATCH"
CLOSE_GATE = "CLOSE_CALIBRATION_RESEARCH_LANE"
PROCEED_GATE = "PROCEED_TO_CALIBRATION_PROSPECTIVE_FREEZE"


@dataclass(frozen=True)
class Candidate:
    coordinates: tuple[str, ...]
    initial: tuple[float, ...]
    bounds: tuple[tuple[float | None, float | None], ...]


CANDIDATES = MappingProxyType({
    "A0": Candidate((), (), ()),
    "C1": Candidate(("tau",), (1.0,), ((0.0, None),)),
    "C2": Candidate(("b_draw", "b_home"), (0.0, 0.0), ((None, None), (None, None))),
    "C3": Candidate(("tau", "b_draw", "b_home"), (1.0, 0.0, 0.0), ((0.0, None), (None, None), (None, None))),
})
OPTIMIZER_OPTIONS = MappingProxyType({
    "maxcor": 10, "maxiter": 15000, "maxfun": 15000,
    "ftol": 2.220446049250313e-09, "gtol": 1e-05, "maxls": 20,
})


class CalibrationError(ValueError):
    """Technical STOP, never a research decision and never a retry."""

    def __init__(self, message, status=ARTIFACT_FAILURE):
        self.status = status
        super().__init__(message)


def require(condition, message, status=ARTIFACT_FAILURE):
    if not condition:
        raise CalibrationError(message, status)


def libs():
    import numpy as np
    import pandas as pd
    return np, pd


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def id_hash(ids):
    return sha256(json.dumps(list(ids), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def metadata_hash(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def probabilities(p):
    np, _ = libs()
    p = np.asarray(p, dtype=np.float64)
    require(p.ndim == 2 and p.shape[1] == 3 and len(p) > 0, "Expected nonempty N x 3 probabilities")
    require(np.isfinite(p).all() and ((p > 0) & (p <= 1)).all(), "Probabilities must be finite, strictly positive, <=1")
    require(np.allclose(p.sum(axis=1), 1, rtol=RTOL, atol=ATOL), "Probability sum; no repair")
    return p


def labels(y, n, *, all_classes=False):
    np, _ = libs()
    y = np.asarray(y)
    require(y.shape == (n,) and np.isin(y, CLASS_ORDER).all(), "Exact integer labels [0,1,2]")
    require(CLASS_ORDER == (0, 1, 2), "Class-order mismatch")
    y = y.astype(np.int64)
    if all_classes:
        require(np.array_equal(np.unique(y), CLASS_ORDER), "Prior training must contain all three classes")
    return y


def candidate(name):
    require(name in CANDIDATES, "Unknown calibration family")
    return CANDIDATES[name]


def parameters(name, theta):
    np, _ = libs()
    definition = candidate(name)
    theta = np.asarray(theta, dtype=np.float64)
    require(theta.shape == (len(definition.coordinates),) and np.isfinite(theta).all(), "Parameter shape/finite")
    if name in ("C1", "C3"):
        require(theta[0] >= 0, "Negative tau; no projection")
    tau = float(theta[0]) if name in ("C1", "C3") else 1.0
    biases = np.zeros(3, dtype=np.float64)
    if name == "C2":
        biases[1:] = theta
    elif name == "C3":
        biases[1:] = theta[1:]
    return tau, biases


def transform_components(p, name, theta):
    """Pure transform. No metadata or labels can enter this API."""
    np, _ = libs()
    from scipy.special import logsumexp
    p = probabilities(p)
    require(name != "A0", "A0 must retain exact saved values")
    tau, b = parameters(name, theta)
    with np.errstate(over="raise", divide="raise", invalid="raise", under="ignore"):
        log_p = np.log(p)
        z = tau * log_p + b
        require(np.isfinite(z).all(), "Nonfinite logits")
        normalizer = logsumexp(z, axis=1, keepdims=True)
        log_q = z - normalizer
        q = np.exp(log_q)
    require(all(np.isfinite(a).all() for a in (log_p, normalizer, log_q)), "Nonfinite transform")
    probabilities(q)  # Underflow to zero is a hard failure, never clipped.
    return log_p, log_q, q


def apply_calibration(p, fitted):
    """Only target probabilities and a fitted parameter vector; no y/year/club."""
    p = probabilities(p)
    name = fitted["candidate"]
    parameters(name, fitted["parameters"])
    return p.copy() if name == "A0" else transform_components(p, name, fitted["parameters"])[2]


def objective_and_gradient(theta, p, y, name):
    np, _ = libs()
    log_p, log_q, q = transform_components(p, name, theta)
    y = labels(y, len(q))
    index = np.arange(len(y))
    loss = np.float64(-log_q[index, y].mean())
    residual = q.copy()
    residual[index, y] -= 1
    tau_gradient = np.mean(np.sum(q * log_p, axis=1) - log_p[index, y])
    bias_gradient = residual[:, 1:].mean(axis=0)
    gradient = (np.array([tau_gradient], dtype=np.float64) if name == "C1" else
                bias_gradient if name == "C2" else
                np.array([tau_gradient, *bias_gradient], dtype=np.float64))
    require(np.isfinite(loss) and np.isfinite(gradient).all(), "Nonfinite objective/gradient")
    return loss, gradient


def fit_calibrator(p, y, name):
    """One optimizer call on prior-only copies; starts at identity every time."""
    np, _ = libs()
    from scipy.optimize import minimize
    definition = candidate(name)
    require(name != "A0", "A0 has no fit")
    p = probabilities(p).copy()
    y = labels(y, len(p), all_classes=True).copy()
    p.flags.writeable = y.flags.writeable = False
    def objective(theta):
        return objective_and_gradient(theta, p, y, name)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            result = minimize(
                fun=objective, x0=np.array(definition.initial, dtype=np.float64),
                args=(), method="L-BFGS-B", jac=True, bounds=definition.bounds,
                tol=None, callback=None, options=dict(OPTIMIZER_OPTIONS),
            )
        require(result.success is True or isinstance(result.success, np.bool_) and bool(result.success),
                "Optimizer unsuccessful", OPTIMIZER_FAILURE)
        require(result.status == 0, "Optimizer status", OPTIMIZER_FAILURE)
        parameters(name, result.x)
        jac = np.asarray(result.jac, dtype=np.float64)
        require(jac.shape == (len(definition.coordinates),) and np.isfinite(jac).all()
                and np.ndim(result.fun) == 0 and np.isfinite(result.fun), "Optimizer result finite/shape", OPTIMIZER_FAILURE)
        projected = jac.copy()
        if name in ("C1", "C3") and result.x[0] == 0 and projected[0] > 0:
            projected[0] = 0
        record = {
            "success": bool(result.success), "status": int(result.status), "message": str(result.message),
            "nit": int(result.nit), "nfev": int(result.nfev), "njev": int(result.njev),
            "fun": float(result.fun), "jac": jac.tolist(),
            "projected_gradient_inf": float(np.max(np.abs(projected))),
        }
    except Exception as exc:
        raise CalibrationError(f"Optimizer/numerical failure; no retry: {exc}", OPTIMIZER_FAILURE) from exc
    return {"candidate": name, "parameters": tuple(map(float, result.x)), "optimizer": record}


def calculate_metrics(y, p):
    np, _ = libs()
    from sklearn.metrics import log_loss
    p = probabilities(p)
    y = labels(y, len(p))
    return {"n": len(y), "accuracy": float(np.mean(p.argmax(axis=1) == y)),
            "log_loss": float(log_loss(y, p, labels=list(CLASS_ORDER))),
            "brier": float(np.mean(np.sum((p - (y[:, None] == np.asarray(CLASS_ORDER)))**2, axis=1)))}


def calibration_context(y, p):
    np, _ = libs()
    p = probabilities(p)
    y = labels(y, len(p))
    predicted = p.mean(axis=0)
    empirical = np.array([np.mean(y == c) for c in CLASS_ORDER])
    return {"mean_probability": predicted.tolist(), "empirical_frequency": empirical.tolist(),
            "bias": (empirical - predicted).tolist()}


def metric_delta(value, baseline):
    require(value["n"] == baseline["n"], "Unmatched metric population")
    return {key: value[key] - baseline[key] for key in ("accuracy", "log_loss", "brier")}


def assert_reference(actual, expected):
    np, _ = libs()
    require(set(actual) == set(expected) == {"n", "accuracy", "log_loss", "brier"}
            and actual["n"] == expected["n"], "Reference schema/count mismatch", REFERENCE_FAILURE)
    for key in ("accuracy", "log_loss", "brier"):
        require(np.isfinite(actual[key]) and np.isclose(actual[key], expected[key], rtol=RTOL, atol=ATOL),
                f"Reference mismatch: {key}", REFERENCE_FAILURE)


def baseline_gate(rows, manifest):
    """Formal-only baseline reference recomputation, never called by preflight."""
    np, _ = libs()
    values = {}
    for year in (*YEARS, "pooled"):
        frame = rows if year == "pooled" else rows.loc[rows.validation_year.eq(year)]
        key = str(year)
        actual = calculate_metrics(frame.result, frame.loc[:, list(P_COLUMNS)].to_numpy())
        assert_reference(actual, REFERENCES[key])
        assert_reference(actual, manifest["observed_metrics"][key])
        p = frame.loc[:, list(P_COLUMNS)].to_numpy()
        y = frame.result.to_numpy()
        eps = np.finfo(np.float64).eps
        require(np.allclose(frame.nll, -np.log(np.clip(p[np.arange(len(y)), y], eps, 1-eps)), rtol=RTOL, atol=ATOL),
                "Stored row NLL mismatch", REFERENCE_FAILURE)
        values[key] = actual
    return values


def validate_rows(rows):
    """Structural/derived-column validation only; no screen metric reduction."""
    np, pd = libs()
    require(tuple(rows.columns) == COLUMNS and len(rows) == OOF_ROWS, "Exact row schema/count")
    require(not rows.isna().any().any(), "Missing OOF values")
    require(all(str(rows[c].dtype) == DTYPES[c] for c in COLUMNS), "Exact row dtypes")
    require(rows.validation_year.value_counts().sort_index().to_dict() == YEAR_COUNTS, "Exact OOF years/counts")
    require(rows.match_id.is_unique, "Duplicate target ID")
    for c in STRING_COLUMNS:
        require(rows[c].map(lambda s: isinstance(s, str) and bool(s.strip())).all(), f"String field: {c}")
    for c in FLOAT_COLUMNS:
        require(np.isfinite(rows[c]).all(), f"Nonfinite field: {c}")
    dates = pd.to_datetime(rows.match_date, format="%Y-%m-%d", errors="raise")
    require(dates.dt.strftime("%Y-%m-%d").tolist() == rows.match_date.tolist()
            and dates.dt.year.eq(rows.validation_year).all(), "Exact dates/year")
    require(not rows.home_team_id.eq(rows.away_team_id).any(), "Self match")
    require(rows.match_id.tolist() == rows.sort_values(["validation_year", "match_date", "match_id"], kind="stable").match_id.tolist(),
            "Canonical OOF order")
    p = probabilities(rows.loc[:, list(P_COLUMNS)])
    y = labels(rows.result, len(rows))
    for year in YEARS:
        require(id_hash(rows.loc[rows.validation_year.eq(year), "match_id"]) == VALID_ID_HASHES[year], "Validation ordered-ID hash")
    require(np.array_equal(rows.predicted_class, p.argmax(axis=1)), "Stored predicted-class mismatch")
    derived = {"max_p": p.max(axis=1), "p_true": p[np.arange(len(y)), y],
               "abs_elo_diff": np.abs(rows.elo_diff),
               "brier": np.sum((p - (y[:, None] == np.asarray(CLASS_ORDER)))**2, axis=1)}
    for c, expected in derived.items():
        require(np.allclose(rows[c], expected, rtol=RTOL, atol=ATOL), f"Stored derived mismatch: {c}")
    require(rows.nll.ge(0).all(), "Negative stored NLL")
    for r in rows.itertuples():
        require(r.round >= 1 and r.home_season_appearance >= 1 and r.away_season_appearance >= 1, "Round/ordinal")
        phase = "opening" if r.round <= 5 else "middle" if r.round <= 29 else "closing"
        require(r.season_phase == phase, "Phase mismatch")
        home, away = int(r.home_season_appearance <= 5), int(r.away_season_appearance <= 5)
        statuses = (r.home_status, r.away_status)
        require(set(statuses).issubset({"ESTABLISHED", "RETURNING", "FIRST_TIME_IN_SCOPE"}), "Unknown club status")
        expected = {
            "home_first5": home, "away_first5": away, "any_team_first5": int(home or away), "both_team_first5": int(home and away),
            "promoted_involved": int(any(s != "ESTABLISHED" for s in statuses)),
            "returning_involved": int("RETURNING" in statuses), "established_only": int(all(s == "ESTABLISHED" for s in statuses)),
            "home_favorite": int(r.p_home > r.p_away), "away_favorite": int(r.p_away > r.p_home),
            "near_even": int(abs(r.p_home-r.p_away) < 0.05),
        }
        require(all(getattr(r, c) == value for c, value in expected.items()), "Stored diagnostic flags mismatch")


def parse_rows(data):
    _, pd = libs()
    require(bool(data), "Empty CSV")
    require(not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data, "CSV UTF-8 without BOM/LF")
    require(data.splitlines()[0].decode("utf-8") == ",".join(COLUMNS), "CSV exact header")
    rows = pd.read_csv(io.BytesIO(data), dtype={c: DTYPES[c] for c in COLUMNS if c not in FLOAT_COLUMNS},
                       float_precision="round_trip", keep_default_na=False).astype(DTYPES)
    validate_rows(rows)
    return rows


def rolling_folds(rows):
    """Fixed counts/order/hashes/date separation; no fits or transformations."""
    validate_rows(rows)
    folds = []
    for year in EVALUATION_YEARS:
        train = rows.loc[rows.validation_year.ge(2020) & rows.validation_year.lt(year)].copy(deep=True)
        valid = rows.loc[rows.validation_year.eq(year)].copy(deep=True)
        require((len(train), len(valid)) == (TRAIN_COUNTS[year], YEAR_COUNTS[year]), "Calibration fold counts")
        require(set(train.match_id).isdisjoint(valid.match_id), "Train/evaluation identity overlap")
        require(train.match_date.max() < valid.match_date.min(), "Non-prior calibration dates")
        require(id_hash(train.match_id) == TRAIN_ID_HASHES[year] and id_hash(valid.match_id) == VALID_ID_HASHES[year], "Calibration fold ID hash")
        labels(train.result, len(train), all_classes=True)
        folds.append((year, train, valid))
    pooled = rows.loc[rows.validation_year.isin(EVALUATION_YEARS)]
    require(len(pooled) == POOLED_ROWS and id_hash(pooled.match_id) == POOLED_ID_SHA, "Pooled target identity")
    return folds


def validate_manifest(manifest, data, rows):
    """Hashes bind complete original contents; no source or generator import."""
    require(set(manifest) == set(MANIFEST_KEYS), "Exact manifest schema")
    require(manifest["schema_version"] == "champion_a_oof_diagnostic_v1"
            and manifest["purpose"] == "diagnostic_only_not_formal_evaluation_not_model_input", "Manifest version/purpose")
    require(manifest["reviewed_source_commit"] == "376973e1f2238bbd29799386ec100dd400648ce4", "Manifest reviewed source")
    require(manifest["freeze_spec"] == {"path": "docs/CHAMPION_A_OOF_DIAGNOSTIC_FREEZE_SPEC.md",
            "sha256": "3167daf9ddff78ef4c3dceec64ed36782c6c36424baed239d83ce1191c023663",
            "commit": "159ca0c7d71dfd10b9d3888971fb05c9f681855e"}, "Original freeze provenance")
    require(manifest["columns"] == list(COLUMNS) and manifest["column_dtypes"] == DTYPES
            and manifest["class_order"] == list(CLASS_ORDER) and manifest["row_count"] == OOF_ROWS, "Manifest row contract")
    require(manifest["csv"] == {"path": CSV_PATH, "sha256": sha256(data), "encoding": "utf-8", "line_ending": "LF",
            "float_format": "%.17g", "ordered_ids_sha256": id_hash(rows.match_id)}, "Manifest CSV provenance")
    require(manifest["generator"] == {
        "path": "src/modeling/champion_a_oof_diagnostic.py", "commit": GENERATOR_COMMIT, "sha256": GENERATOR_SHA,
        "git_dirty": False, "fits": 5, "prediction_batches": 5, "automatic_retries": 0}, "Generator provenance")
    require(manifest["generation_authorization"] == {"reviewed_implementation_commit": GENERATOR_COMMIT,
            "task_reference": GENERATION_TASK}, "Generation task provenance")
    require(manifest["gates"] == {g: "PASS" for g in GATE_NAMES}, "Recorded gates")
    require(all(metadata_hash(manifest[key]) == expected for key, expected in METADATA_HASHES.items()),
            "Frozen original metadata contract")
    references = manifest["references"]
    require(references == {"values": REFERENCES, "sources": ["docs/H2H_EVALUATION.md", "docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md"],
            "rtol": RTOL, "atol": ATOL}, "Recorded reference contract")
    require(set(manifest["observed_metrics"]) == set(REFERENCES), "Recorded metric years")
    for year, reference in REFERENCES.items():
        assert_reference(manifest["observed_metrics"][year], reference)  # recorded constants only
    runtime = manifest["runtime"]
    require(set(runtime) == {"python", "platform", *VERSIONS, "requirements_sha256", "lock_sha256"}, "Recorded runtime schema")
    require(runtime["python"] == "3.12.14" and runtime["platform"].startswith("Windows")
            and all(runtime[k] == v for k, v in VERSIONS.items())
            and runtime["requirements_sha256"] == REQUIREMENTS_HASHES["requirements.txt"]
            and runtime["lock_sha256"] == REQUIREMENTS_HASHES["requirements-lock.txt"], "Recorded runtime")
    require(len(manifest["folds"]) == len(YEARS), "Recorded base fold count")
    for year, fold in zip(YEARS, manifest["folds"]):
        require(set(fold) == {"validation_year", "validation_rows", "training_seasons", "training_rows",
                             "train_ids_sha256", "validation_ids_sha256"}, "Recorded base fold schema")
        require(fold["validation_year"] == year and fold["validation_rows"] == YEAR_COUNTS[year]
                and fold["training_seasons"] == list(range(2015, year))
                and fold["training_rows"] == {2020: 1530, 2021: 1836, 2022: 2216, 2023: 2522, 2024: 2828}[year]
                and fold["validation_ids_sha256"] == VALID_ID_HASHES[year], "Recorded base fold provenance")
        require(isinstance(fold["train_ids_sha256"], str) and len(fold["train_ids_sha256"]) == 64
                and all(c in "0123456789abcdef" for c in fold["train_ids_sha256"]), "Recorded base training ID hash")
    require(manifest["generated_at"].endswith("Z"), "Manifest UTC timestamp")
    datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))


def load_accepted(root):
    """Exactly two explicit data reads. SHA validation precedes parsing."""
    data = (root / CSV_PATH).read_bytes()
    manifest_data = (root / MANIFEST_PATH).read_bytes()
    require(sha256(data) == CSV_SHA and sha256(manifest_data) == MANIFEST_SHA, "Accepted-pair SHA mismatch")
    rows = parse_rows(data)
    manifest = json.loads(manifest_data)
    validate_manifest(manifest, data, rows)
    return rows, manifest


def candidate_pass(fold_values, pooled, baseline_folds, baseline_pooled):
    require(set(fold_values) == set(baseline_folds) == set(EVALUATION_YEARS), "Exactly four decision folds")
    np, _ = libs()
    for value in [pooled, baseline_pooled, *fold_values.values(), *baseline_folds.values()]:
        require(all(np.isfinite(value[k]) for k in ("accuracy", "log_loss", "brier")), "Nonfinite decision metrics")
    require(pooled["n"] == baseline_pooled["n"] == POOLED_ROWS, "Decision pooled count")
    for year in EVALUATION_YEARS:
        require(fold_values[year]["n"] == baseline_folds[year]["n"] == YEAR_COUNTS[year], "Decision fold count")
    improved = sum(fold_values[y]["log_loss"] < baseline_folds[y]["log_loss"] for y in EVALUATION_YEARS)
    components = {"pooled_ll_improved": pooled["log_loss"] < baseline_pooled["log_loss"],
                  "fold_ll_improved_3_of_4": improved >= 3, "pooled_brier_nonworse": pooled["brier"] <= baseline_pooled["brier"]}
    return {"improved_ll_folds": improved, "components": components, "passes": all(components.values())}


def select_candidate(results):
    require(tuple(results) == tuple(CANDIDATES), "Exact candidate result registry")
    passing = [name for name in ("C1", "C2", "C3") if results[name]["gate"]["passes"]]
    if not passing:
        return {"decision": CLOSE_GATE, "selected_candidate": None, "tied_candidates": []}
    minimum = min(results[name]["pooled"]["log_loss"] for name in passing)
    tied = [name for name in passing if abs(results[name]["pooled"]["log_loss"] - minimum) <= ATOL]
    selected = min(tied, key=lambda name: (len(candidate(name).coordinates), tuple(CANDIDATES).index(name)))
    return {"decision": PROCEED_GATE, "selected_candidate": selected, "tied_candidates": tied}


def evaluate(rows, *, progress=None):
    """Real use reserved for formal; implementation tests pass synthetic rows."""
    np, _ = libs()
    folds = rolling_folds(rows)
    results = {name: {"folds": {}, "parameters": {}, "optimizers": {}, "context": {}, "deltas": {}} for name in CANDIDATES}
    arrays = {name: [] for name in CANDIDATES}
    pooled_labels, pooled_ids, identities = [], [], []
    fits = applications = 0
    if progress is None:
        progress = {}
    progress.update(fit_attempts=0, fits_completed=0, application_attempts=0, applications_completed=0)
    for year, train, valid in folds:
        train_p = train.loc[:, list(P_COLUMNS)].to_numpy(copy=True)
        train_y = train.result.to_numpy(copy=True)
        target_p = valid.loc[:, list(P_COLUMNS)].to_numpy(copy=True)
        outputs = {"A0": target_p.copy()}
        identities.append({"year": year, "training_n": len(train), "evaluation_n": len(valid),
                           "training_ids_sha256": id_hash(train.match_id), "evaluation_ids_sha256": id_hash(valid.match_id)})
        # No target y or metadata is passed to fit/apply (including their closures).
        for name in ("C1", "C2", "C3"):
            progress.update(stage=f"{year}:{name}:fit", fit_attempts=progress["fit_attempts"] + 1)
            fitted = fit_calibrator(train_p, train_y, name)
            fits += 1
            progress.update(fits_completed=fits, stage=f"{year}:{name}:apply",
                            application_attempts=progress["application_attempts"] + 1)
            outputs[name] = apply_calibration(target_p, fitted)
            applications += 1
            progress["applications_completed"] = applications
            results[name]["parameters"][year] = list(fitted["parameters"])
            results[name]["optimizers"][year] = fitted["optimizer"]
        target_y = valid.result.to_numpy(copy=True)  # scoring only AFTER application
        pooled_labels.append(target_y)
        pooled_ids.extend(valid.match_id)
        for name in CANDIDATES:
            probabilities(outputs[name])
            require(outputs[name].shape == target_p.shape, "Target application shape")
            results[name]["folds"][year] = calculate_metrics(target_y, outputs[name])
            results[name]["context"][year] = calibration_context(target_y, outputs[name])
            arrays[name].append(outputs[name])
            results[name]["deltas"][year] = metric_delta(results[name]["folds"][year], results["A0"]["folds"][year])
    require(fits == applications == 12, "Exactly 12 fits/applications")
    require(len(pooled_ids) == POOLED_ROWS and id_hash(pooled_ids) == POOLED_ID_SHA, "Final pooled target identity")
    y = np.concatenate(pooled_labels)
    for name in CANDIDATES:
        p = np.concatenate(arrays[name], axis=0)
        results[name]["pooled"] = calculate_metrics(y, p)
        results[name]["context"]["pooled"] = calibration_context(y, p)
        results[name]["deltas"]["pooled"] = metric_delta(results[name]["pooled"], results["A0"]["pooled"])
        if name != "A0":
            results[name]["gate"] = candidate_pass(results[name]["folds"], results[name]["pooled"],
                                                 results["A0"]["folds"], results["A0"]["pooled"])
    return {"results": results, "identities": identities, "fits": fits, "applications": applications,
            **select_candidate(results)}


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


def execution_head(root):
    require(not git(root, "status", "--porcelain").strip(), "Clean tree required")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    require(len(head) == 40 and all(c in "0123456789abcdef" for c in head), "Execution HEAD")
    return head


def verify_code(root, head):
    require(sha256(git(root, "show", f"{SPEC_COMMIT}:{SPEC_PATH}")) == SPEC_SHA
            and sha256((root / SPEC_PATH).read_bytes()) == SPEC_SHA, "Committed/live freeze SHA")
    git(root, "merge-base", "--is-ancestor", SPEC_COMMIT, head)
    module_bytes = (root / MODULE_PATH).read_bytes()
    require(module_bytes == git(root, "show", f"{head}:{MODULE_PATH}"), "Committed evaluator mismatch")
    tree = ast.parse(module_bytes.decode("utf-8"))
    allowed = {"__future__", "argparse", "ast", "contextlib", "ctypes", "dataclasses", "datetime", "hashlib", "importlib", "io", "json", "os",
               "pathlib", "platform", "subprocess", "sys", "types", "warnings", "numpy", "pandas", "scipy", "sklearn"}
    for node in ast.walk(tree):
        imports = [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names] if isinstance(node, ast.Import) else []
        require(all(name and name.split(".")[0] in allowed for name in imports), "Forbidden evaluator import")
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("sklearn"):
            require(node.module == "sklearn.metrics", "Base-model dependency forbidden")
    return sha256(module_bytes)


def validate_registry():
    require(tuple(CANDIDATES) == ("A0", "C1", "C2", "C3") and
            [(c.coordinates, c.initial, c.bounds) for c in CANDIDATES.values()] == [
                ((), (), ()), (("tau",), (1.0,), ((0.0, None),)),
                (("b_draw", "b_home"), (0.0, 0.0), ((None, None), (None, None))),
                (("tau", "b_draw", "b_home"), (1.0, 0.0, 0.0), ((0.0, None), (None, None), (None, None)))],
            "Frozen candidate registry")
    require(dict(OPTIMIZER_OPTIONS) == {"maxcor": 10, "maxiter": 15000, "maxfun": 15000,
            "ftol": 2.220446049250313e-09, "gtol": 1e-05, "maxls": 20}, "Frozen optimizer options")


def runtime_provenance(root):
    from importlib.metadata import version
    from scipy.optimize import minimize
    require(callable(minimize), "Optimizer implementation absent")
    observed = {key: version(key) for key in VERSIONS}
    require(platform.python_version() == "3.12.14" and os.name == "nt" and observed == VERSIONS, "Frozen runtime mismatch")
    for path, expected in REQUIREMENTS_HASHES.items():
        require(sha256((root / path).read_bytes()) == expected, "Dependency lock mismatch")
    return {"python": platform.python_version(), "platform": platform.platform(), **observed,
            "requirements_sha256": REQUIREMENTS_HASHES["requirements.txt"],
            "lock_sha256": REQUIREMENTS_HASHES["requirements-lock.txt"]}


def refuse_existing(root):
    require(not path_present(root / MARKER_PATH), "Existing/partial consumed marker: REFUSE")
    require(not path_present(root / RESULT_PATH), "Existing/partial result: REFUSE")


def path_present(path):
    """A dangling symlink is still an existing entry, not an empty target."""
    return path.exists() or path.is_symlink()


def preflight():
    root = ROOT
    head = execution_head(root)
    module_sha = verify_code(root, head)
    validate_registry()
    runtime = runtime_provenance(root)
    refuse_existing(root)
    rows, _ = load_accepted(root)
    folds = rolling_folds(rows)
    return {"status": "PREFLIGHT_PASS", "head": head, "spec_commit": SPEC_COMMIT, "spec_sha": SPEC_SHA,
            "evaluator_sha": module_sha, "csv_sha": CSV_SHA, "manifest_sha": MANIFEST_SHA, "runtime": runtime,
            "folds": [{"year": y, "training_n": len(t), "evaluation_n": len(v)} for y, t, v in folds],
            "pooled_n": POOLED_ROWS, "candidate_fit": "NOT RUN", "candidate_transform": "NOT RUN",
            "candidate_metrics": "NOT RUN", "marker_created": False, "result_created": False}


def formal_authorization(root):
    try:
        auth = json.loads(os.environ.get(AUTHORIZATION_ENV, "{}"))
    except ValueError as exc:
        raise CalibrationError("Malformed formal authorization") from exc
    require(isinstance(auth, dict) and set(auth) == {"approved_execution_head", "task_reference"}, "Separate formal authorization required")
    require(isinstance(auth["task_reference"], str) and bool(auth["task_reference"].strip())
            and auth["task_reference"].strip() != GENERATION_TASK, "Distinct formal task reference required")
    head = execution_head(root)
    require(auth["approved_execution_head"] == head, "Authorization must match exact approved execution HEAD")
    return head, auth


@contextmanager
def process_lock(root):
    """Windows named mutex; no persistent lock file, no repair or waits."""
    require(os.name == "nt", "Windows production lock required")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    name = "Global\\J1ChampionACalibration_" + sha256(str((root / MARKER_PATH).resolve()).casefold().encode())
    ctypes.set_last_error(0)
    handle = kernel.CreateMutexW(None, True, name)
    error = ctypes.get_last_error()
    require(bool(handle), "Exclusive process lock unavailable")
    if error == 183:
        kernel.CloseHandle(handle)
        raise CalibrationError("Concurrent formal execution: REFUSE")
    try:
        yield
    finally:
        kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def marker_payload(root, head, auth):
    """Observed versions/hashes only; validation follows durable consumption."""
    from importlib.metadata import PackageNotFoundError, version
    def observed_hash(path):
        try:
            return sha256((root / path).read_bytes())
        except FileNotFoundError:
            return None
    def observed_version(key):
        try:
            return version(key)
        except PackageNotFoundError:
            return None
    return {
        "schema_version": "champion_a_calibration_attempt_v1", "state": "ATTEMPT_CONSUMED",
        "authorization": auth, "execution_head": head,
        "spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT, "expected_sha256": SPEC_SHA,
                 "observed_sha256": observed_hash(SPEC_PATH)},
        "evaluator": {"path": MODULE_PATH, "sha256": observed_hash(MODULE_PATH)},
        "expected_inputs": {CSV_PATH: CSV_SHA, MANIFEST_PATH: MANIFEST_SHA},
        "runtime": {"python": platform.python_version(), "platform": platform.platform(),
                    **{key: observed_version(key) for key in VERSIONS}},
        "dependency_lock": {path: {"expected_sha256": h, "observed_sha256": observed_hash(path)}
                            for path, h in REQUIREMENTS_HASHES.items()},
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def exclusive_write(path, data):
    """No overwrite, rollback, deletion, or partial-file cleanup."""
    with path.open("xb") as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())


def consume_marker(root, payload):
    refuse_existing(root)
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    (root / MARKER_PATH).parent.mkdir(parents=True, exist_ok=True)
    exclusive_write(root / MARKER_PATH, data)
    return sha256(data)


def build_result(outcome, provenance):
    """Pure full-precision Markdown rendering; no IO or derived data file."""
    lines = ["# Champion A Calibration Evaluation Result", "", "Formal status: COMPLETE", "",
             "This is a reused historical RESEARCH SCREEN, not unseen confirmation or a new Champion.", "",
             "## Provenance and pre-fit gates", "", "Artifact/schema/identity/chronology/runtime/A-only reference gates: PASS.", "",
             "~~~json", json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False), "~~~", "",
             "## Rolling fold identities", "",
             "| Year | Train n | Evaluation n | Training IDs SHA | Evaluation IDs SHA |",
             "| --- | --- | --- | --- | --- |"]
    for e in outcome["identities"]:
        lines.append(f'| {e["year"]} | {e["training_n"]} | {e["evaluation_n"]} | {e["training_ids_sha256"]} | {e["evaluation_ids_sha256"]} |')
    lines += ["", "## Parameters and optimizer convergence", ""]
    for name, result in outcome["results"].items():
        lines += [f"### {name}", ""]
        if name == "A0":
            lines += ["No fitted parameters; q=p; zero optimizer calls.", ""]
        else:
            lines += ["~~~json", json.dumps({"coordinates": candidate(name).coordinates,
                       "identity": candidate(name).initial, "bounds": candidate(name).bounds,
                       "options": dict(OPTIMIZER_OPTIONS), "method": "L-BFGS-B", "jac": True, "tol": None,
                       "callback": None, "b_away": 0.0, "fixed_tau": 1.0 if name == "C2" else None,
                       "fixed_biases": [0.0, 0.0, 0.0] if name == "C1" else None,
                       "parameters": result["parameters"], "optimizers": result["optimizers"]},
                       ensure_ascii=False, indent=2, allow_nan=False), "~~~", ""]
    lines += ["## Metrics and matched deltas", "",
              "| Candidate | Year | n | Accuracy | Log Loss | Brier | Delta Accuracy | Delta LL | Delta Brier |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, result in outcome["results"].items():
        for year in (*EVALUATION_YEARS, "pooled"):
            value = result["pooled"] if year == "pooled" else result["folds"][year]
            delta = result["deltas"][year]
            lines.append(f'| {name} | {year} | {value["n"]} | {value["accuracy"]!r} | {value["log_loss"]!r} | {value["brier"]!r} | {delta["accuracy"]!r} | {delta["log_loss"]!r} | {delta["brier"]!r} |')
    lines += ["", "## Calibration context (NOT a gate)", "",
              "| Candidate | Year | Class | Mean probability | Empirical frequency | Bias |",
              "| --- | --- | --- | --- | --- | --- |"]
    for name, result in outcome["results"].items():
        for year in (*EVALUATION_YEARS, "pooled"):
            context = result["context"][year]
            for c, label in enumerate(CLASS_NAMES):
                lines.append(f'| {name} | {year} | {label} | {context["mean_probability"][c]!r} | {context["empirical_frequency"][c]!r} | {context["bias"][c]!r} |')
    lines += ["", "## Candidate decision and selection", "",
              "| Candidate | Improved LL folds / 4 | Pooled LL improved | >=3 folds | Pooled Brier nonworse | Pass |",
              "| --- | --- | --- | --- | --- | --- |"]
    for name in ("C1", "C2", "C3"):
        gate = outcome["results"][name]["gate"]
        component = gate["components"]
        lines.append(f'| {name} | {gate["improved_ll_folds"]}/4 | {component["pooled_ll_improved"]} | {component["fold_ll_improved_3_of_4"]} | {component["pooled_brier_nonworse"]} | {gate["passes"]} |')
    lines += ["", f'Selected candidate: {outcome["selected_candidate"]}', f'Minimum-anchored tied set: {outcome["tied_candidates"]}',
              "Tie rule: absolute difference from minimum pooled LL <=1e-12; fewer parameters, then C1/C2/C3.", "",
              f'Fits={outcome["fits"]}; target applications={outcome["applications"]}; retries=0; pooled n={POOLED_ROWS}.', "",
              "## Interpretation and actions not performed", "",
              "A pass authorizes ONLY a separate prospective freeze at a NEW unseen boundary. No operational promotion.",
              "Champion A refit / predict_proba / Elo replay / OOF regeneration / diagnose(): NOT RUN.",
              "2025 / 2026+ / historical sources / HTTP / production prediction / activation: NOT USED.",
              "Feature changes=NO; parameter-contract changes=NO; tuning=NOT RUN; adaptive follow-up=NOT RUN.",
              "Saved Champion A / opened lockbox / rolling-xG / P/G probabilities: UNCHANGED.",
              "Derived datasets / calibrator bundles / production artifacts: NOT CREATED; push NOT PERFORMED.", "",
              "## Final research decision", "", outcome["decision"], ""]
    return "\n".join(lines)


def publish_result(root, document, marker_sha):
    require(not path_present(root / RESULT_PATH), "Existing/partial result: REFUSE")
    require(sha256((root / MARKER_PATH).read_bytes()) == marker_sha, "Consumed marker changed")
    require(sha256((root / CSV_PATH).read_bytes()) == CSV_SHA
            and sha256((root / MANIFEST_PATH).read_bytes()) == MANIFEST_SHA, "Accepted pair changed before publication")
    exclusive_write(root / RESULT_PATH, document.encode("utf-8"))


def formal():
    """Separately authorized one-shot ONLY; tests replace all IO with tmp fixtures."""
    root = ROOT
    head, auth = formal_authorization(root)
    require(not path_present(root / RESULT_PATH), "Existing/partial result: REFUSE")
    with process_lock(root):
        refuse_existing(root)
        progress = {"stage": "marker consumption", "fit_attempts": 0, "fits_completed": 0,
                    "application_attempts": 0, "applications_completed": 0}
        try:
            marker_sha = consume_marker(root, marker_payload(root, head, auth))
            progress["stage"] = "pre-fit integrity"
            # Durable consumed marker precedes ALL validation and ALL challenger fits.
            require(execution_head(root) == head, "Execution HEAD/tree changed")
            module_sha = verify_code(root, head)
            validate_registry()
            runtime = runtime_provenance(root)
            rows, manifest = load_accepted(root)
            rolling_folds(rows)
            progress["stage"] = "A-only reference gate"
            reference = baseline_gate(rows, manifest)
            outcome = evaluate(rows, progress=progress)
            provenance = {"execution_head": head, "authorization": auth, "spec_commit": SPEC_COMMIT,
                          "spec_sha": SPEC_SHA, "evaluator_sha": module_sha, "csv_sha": CSV_SHA,
                          "manifest_sha": MANIFEST_SHA, "runtime": runtime, "baseline_reference": reference,
                          "marker_path": MARKER_PATH, "marker_sha": marker_sha, "marker_state": "ATTEMPT_CONSUMED"}
            progress["stage"] = "result publication"
            document = build_result(outcome, provenance)
            publish_result(root, document, marker_sha)
        except Exception as exc:
            status = exc.status if isinstance(exc, CalibrationError) else ARTIFACT_FAILURE
            evidence = "consumed attempt retained" if path_present(root / MARKER_PATH) else "attempt not consumed"
            raise CalibrationError(f"{exc}; {evidence}; progress={progress}", status) from exc
    return {"status": "COMPLETE", "decision": outcome["decision"], "selected_candidate": outcome["selected_candidate"],
            "fits": outcome["fits"], "applications": outcome["applications"], "marker_sha": marker_sha}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Frozen calibration research: default read-only preflight; formal needs separate reviewed authorization.")
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--confirm-one-shot", action="store_true")
    args = parser.parse_args(argv)
    if args.formal != args.confirm_one_shot:
        parser.error("Formal requires BOTH --formal and --confirm-one-shot")
    try:
        result = formal() if args.formal else preflight()
    except Exception as exc:
        status = exc.status if isinstance(exc, CalibrationError) else ARTIFACT_FAILURE
        print(f"{status}: {exc}; technical STOP; no retry and no research decision", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
