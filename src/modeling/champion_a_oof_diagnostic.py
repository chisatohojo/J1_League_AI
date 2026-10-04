"""Frozen, dedicated A-only OOF reconstruction; real execution needs separate review.

Import/help use only the standard library and do not read inputs or fit models.
The authorization environment value is provenance, never a model/path override:
CHAMPION_A_OOF_DIAGNOSTIC_AUTHORIZATION must be a JSON object containing the
reviewed implementation commit and the separately approved generation task reference.
No formal evaluator, operational bundle, or prospective predictor is used.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import threading
import warnings


ROOT = Path(__file__).parents[2]
REVIEWED_SOURCE_COMMIT = "376973e1f2238bbd29799386ec100dd400648ce4"
FREEZE_COMMIT = "159ca0c7d71dfd10b9d3888971fb05c9f681855e"
SPEC_PATH = "docs/CHAMPION_A_OOF_DIAGNOSTIC_FREEZE_SPEC.md"
SPEC_SHA = "3167daf9ddff78ef4c3dceec64ed36782c6c36424baed239d83ce1191c023663"
MODULE_PATH = "src/modeling/champion_a_oof_diagnostic.py"
CSV_PATH = "data/processed/model_diagnostics/champion_a_oof_2020_2024.csv"
MANIFEST_PATH = "data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json"
AUTHORIZATION_ENV = "CHAMPION_A_OOF_DIAGNOSTIC_AUTHORIZATION"
SCHEMA_VERSION = "champion_a_oof_diagnostic_v1"
PURPOSE = "diagnostic_only_not_formal_evaluation_not_model_input"
CLASS_ORDER = (0, 1, 2)
FEATURES = ("elo_diff",)
INITIAL_ELO, K, HOME_ADVANTAGE = 1500.0, 30.0, 175.0
RTOL, ATOL = 0.0, 1e-12
FOLDS = (2020, 2021, 2022, 2023, 2024)
FOLD_COUNTS = {2020: (1530, 306), 2021: (1836, 380), 2022: (2216, 306),
               2023: (2522, 306), 2024: (2828, 380)}
SEASON_COUNTS = {y: 380 if y in (2021, 2024) else 306 for y in range(2015, 2025)}
SOURCE_ROWS, OOF_ROWS = 3208, 1678
INPUT_HASHES = {
    "data/processed/jleague/2015_matches_probe.csv": "ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353",
    "data/processed/jleague/2016_matches_probe.csv": "4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f",
    "data/processed/jleague/2017_matches_probe.csv": "d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b",
    "data/processed/jleague/2018_matches_probe.csv": "f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681",
    "data/processed/jleague/2019_matches_probe.csv": "3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f",
    "data/processed/jleague/2020_matches_probe.csv": "fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17",
    "data/processed/jleague/2021_matches_probe.csv": "298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6",
    "data/processed/jleague/2022_matches_probe.csv": "d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2",
    "data/processed/jleague/2023_matches_probe.csv": "6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9",
    "data/processed/jleague/2024_matches_probe.csv": "4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1",
}
TEAM_MASTER_PATH = "data/master/teams.csv"
TEAM_MASTER_SHA = "ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f"
CODE_HASHES = {
    "src/features/elo.py": "f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4",
    "src/modeling/player_workload_evaluation.py": "7517880be643e7891eb7d0eb426d1dd57744ef5f7b730ce7713457e953457d76",
    "src/modeling/model_architecture_evaluation.py": "b610cb52e3fc136bb6ab1fa303102d2413b4357ea5cc7bd899d24aad9d3105c5",
    "src/collect/matches.py": "0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c",
    "src/collect/teams.py": "b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c",
    "requirements.txt": "887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda",
    "requirements-lock.txt": "3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04",
}
REFERENCES = {
    2020: {"n": 306, "accuracy": 0.5065359477124183, "log_loss": 1.023119734659012, "brier": 0.6117572218710644},
    2021: {"n": 380, "accuracy": 0.5078947368421053, "log_loss": 1.0253437210487792, "brier": 0.6149829138674616},
    2022: {"n": 306, "accuracy": 0.4019607843137255, "log_loss": 1.0940186385371449, "brier": 0.6610224339161608},
    2023: {"n": 306, "accuracy": 0.46078431372549017, "log_loss": 1.0604285568595655, "brier": 0.638530529273072},
    2024: {"n": 380, "accuracy": 0.45, "log_loss": 1.079241181120235, "brier": 0.6531695943664019},
    "pooled": {"n": 1678, "accuracy": 0.466626936829559, "log_loss": 1.056065401323764, "brier": 0.6357323419292724},
}
COLUMNS = (
    "validation_year", "match_id", "match_date", "home_team_id", "away_team_id", "result",
    "elo_diff", "p_away", "p_draw", "p_home", "predicted_class", "max_p", "p_true", "nll",
    "brier", "abs_elo_diff", "round", "home_team", "away_team", "season_phase",
    "home_season_appearance", "away_season_appearance", "home_first5", "away_first5",
    "any_team_first5", "both_team_first5", "home_status", "away_status", "promoted_involved",
    "returning_involved", "established_only", "home_favorite", "away_favorite", "near_even",
)
FLOAT_COLUMNS = ("elo_diff", "p_away", "p_draw", "p_home", "max_p", "p_true", "nll", "brier", "abs_elo_diff")
STRING_COLUMNS = ("match_id", "match_date", "home_team_id", "away_team_id", "home_team", "away_team",
                  "season_phase", "home_status", "away_status")
INT_COLUMNS = tuple(c for c in COLUMNS if c not in FLOAT_COLUMNS + STRING_COLUMNS)
DTYPES = {c: "float64" if c in FLOAT_COLUMNS else "string" if c in STRING_COLUMNS else "int64" for c in COLUMNS}
PROBABILITY_EDGES = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
MAX_P_EDGES = (0.0, 0.4, 0.5, 0.6, 0.7, 1.0)
ABS_ELO_EDGES = (0.0, 50.0, 100.0, 200.0, 300.0, float("inf"))
SIGNED_ELO_EDGES = (-float("inf"), -200.0, -50.0, 50.0, 200.0, float("inf"))
CALIBRATION_GATE = "PROCEED_TO_CALIBRATION_RESEARCH_SPEC"
TRANSITION_GATE = "PROCEED_TO_SEASON_TRANSITION_DIAGNOSTIC_SPEC"
INCONCLUSIVE_GATE = "NO_LANE_OPENED_DIAGNOSTIC_INCONCLUSIVE"
MANIFEST_KEYS = (
    "schema_version", "purpose", "reviewed_source_commit", "freeze_spec", "generation_authorization",
    "generator", "runtime", "inputs", "team_master", "champion_a_contract", "folds", "class_order",
    "columns", "column_dtypes", "row_count", "csv", "references", "observed_metrics",
    "diagnostic_contract", "gates", "generated_at",
)
GATE_NAMES = ("input", "source", "chronology", "folds", "identity", "classes", "probabilities", "references", "serialization")
_ATTEMPTS: set[str] = set()
_ATTEMPTS_LOCK = threading.Lock()


class DiagnosticError(ValueError):
    """Technical failure: never a diagnostic decision or a retry trigger."""


def _libs():
    import numpy as np
    import pandas as pd
    return np, pd


def _require(condition, message):
    if not condition:
        raise DiagnosticError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def id_hash(ids) -> str:
    return sha256(json.dumps(list(ids), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def verify_hashes(root: Path) -> None:
    """Only explicit frozen paths; no discovery, evaluator execution, or marker IO."""
    for name, expected in {**INPUT_HASHES, TEAM_MASTER_PATH: TEAM_MASTER_SHA,
                           **CODE_HASHES, SPEC_PATH: SPEC_SHA}.items():
        _require(sha256((root / name).read_bytes()) == expected, f"Hash mismatch: {name}")


def validate_source(source, master=None, *, exact_population=True):
    np, pd = _libs()
    from src.collect.matches import validate_matches
    normalized = validate_matches(source)
    _require(not normalized.empty, "Empty source")
    _require(source.match_id.map(lambda v: isinstance(v, str)).all(), "IDs must remain strings")
    seasons = set(normalized.season)
    _require(seasons.issubset(SEASON_COUNTS), "Forbidden source season")
    if exact_population:
        _require(len(source) == SOURCE_ROWS, "Source count mismatch")
        _require(normalized.season.value_counts().sort_index().to_dict() == SEASON_COUNTS, "Season counts")
    for side in ("home", "away"):
        c = f"{side}_team_id"
        _require(c in source and source[c].map(lambda v: isinstance(v, str) and bool(v.strip())).all(), "Missing team IDs")
        if master is not None:
            _require(set(source[c]).issubset({a.team_id for a in master.aliases}), "Unknown TeamMaster ID")
    _require(not source.home_team_id.eq(source.away_team_id).any(), "Self match")
    ordered = normalized.sort_values(["match_date", "match_id"], kind="stable")
    _require(source.match_id.tolist() == ordered.match_id.tolist(), "Noncanonical source order")
    appearances = pd.concat([normalized[["match_date", f"{s}_team_id"]].rename(
        columns={f"{s}_team_id": "team_id"}) for s in ("home", "away")])
    _require(not appearances.duplicated(["match_date", "team_id"]).any(), "Same-date team duplicate")
    return normalized.reset_index(drop=True)


def load_source(root: Path):
    _, pd = _libs()
    from src.collect.matches import load_matches
    from src.collect.teams import load_team_master
    master = load_team_master(root / TEAM_MASTER_PATH)
    frames = [master.add_team_ids(load_matches(root / name)) for name in INPUT_HASHES]
    ordered = pd.concat(frames, ignore_index=True).sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    return validate_source(ordered, master)


def replay_elo(source):
    """Reuse the reviewed numeric/date-batch implementation, not a rewritten formula."""
    from src.modeling.player_workload_evaluation import _add_elo
    return _add_elo(source)


def build_pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([("scaler", StandardScaler()), ("logistic", LogisticRegression(
        C=1.0, solver="lbfgs", max_iter=1000, random_state=0))])


def validate_probabilities(probabilities, expected_rows=None):
    np, _ = _libs()
    p = np.asarray(probabilities, dtype=np.float64)
    _require(p.ndim == 2 and p.shape[1] == 3, "Expected N x 3 probabilities")
    _require(expected_rows is None or len(p) == expected_rows, "Probability row count")
    _require(np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all(), "Probability range/finite")
    _require(np.allclose(p.sum(axis=1), 1, rtol=RTOL, atol=ATOL), "Probability sum")
    return p


def fit_fold(train, validation):
    np, _ = _libs()
    from sklearn.exceptions import ConvergenceWarning
    model = build_pipeline()
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        try:
            model.fit(train.loc[:, list(FEATURES)], train.result)
            _require(np.array_equal(model.named_steps["logistic"].classes_, CLASS_ORDER), "Class order mismatch")
            p = model.predict_proba(validation.loc[:, list(FEATURES)])
        except DiagnosticError:
            raise
        except Exception as exc:
            raise DiagnosticError("A fit/prediction failed; no retry") from exc
    return validate_probabilities(p, len(validation))


def derived_values(labels, probabilities):
    np, _ = _libs()
    y = np.asarray(labels)
    _require(y.ndim == 1 and np.isin(y, CLASS_ORDER).all(), "Invalid result labels")
    y = y.astype(np.int64)
    p = validate_probabilities(probabilities, len(y))
    p_true = p[np.arange(len(y)), y]
    eps = np.finfo(np.float64).eps
    return {"predicted_class": np.asarray(CLASS_ORDER)[p.argmax(axis=1)], "max_p": p.max(axis=1),
            "p_true": p_true, "nll": -np.log(np.clip(p_true, eps, 1-eps)),
            "brier": np.sum((p - (y[:, None] == np.asarray(CLASS_ORDER))) ** 2, axis=1)}


def calculate_metrics(labels, probabilities):
    np, _ = _libs()
    from sklearn.metrics import log_loss
    d = derived_values(labels, probabilities)
    y = np.asarray(labels, dtype=int)
    _require(len(y) > 0, "Cannot gate empty metrics")
    return {"n": len(y), "accuracy": float(np.mean(d["predicted_class"] == y)),
            "log_loss": float(log_loss(y, probabilities, labels=list(CLASS_ORDER))),
            "brier": float(d["brier"].mean())}


def assert_reference(actual, expected):
    np, _ = _libs()
    _require(set(actual) == set(expected) == {"n", "accuracy", "log_loss", "brier"}, "Metric schema")
    _require(actual["n"] == expected["n"], "Metric count mismatch")
    for key in ("accuracy", "log_loss", "brier"):
        _require(np.isfinite(actual[key]) and np.isclose(actual[key], expected[key], rtol=RTOL, atol=ATOL), f"Reference mismatch: {key}")


def season_phase(round_number):
    _require(round_number > 0 and int(round_number) == round_number, "Invalid round")
    return "opening" if round_number <= 5 else "middle" if round_number <= 29 else "closing"


def add_metadata(source):
    """Pure full-stream metadata; never derive a prematch input from outcomes."""
    _, pd = _libs()
    ordered = source.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True).copy(deep=True)
    membership = {int(y): set(f.home_team_id) | set(f.away_team_id) for y, f in ordered.groupby("season")}
    appearances = {}
    rows = []
    for r in ordered.itertuples():
        year = int(r.season)
        previous = membership.get(year - 1, set())
        past = set().union(*(ids for y, ids in membership.items() if y < year))
        values = {"season_phase": season_phase(r.round)}
        for side in ("home", "away"):
            team = getattr(r, f"{side}_team_id")
            key = (year, team)
            ordinal = appearances.get(key, 0) + 1
            appearances[key] = ordinal
            values[f"{side}_season_appearance"] = ordinal
            values[f"{side}_first5"] = int(ordinal <= 5)
            values[f"{side}_status"] = "ESTABLISHED" if team in previous else "RETURNING" if team in past else "FIRST_TIME_IN_SCOPE"
        values["any_team_first5"] = int(values["home_first5"] or values["away_first5"])
        values["both_team_first5"] = int(values["home_first5"] and values["away_first5"])
        statuses = (values["home_status"], values["away_status"])
        values["promoted_involved"] = int(any(s != "ESTABLISHED" for s in statuses))
        values["returning_involved"] = int("RETURNING" in statuses)
        values["established_only"] = int(all(s == "ESTABLISHED" for s in statuses))
        rows.append(values)
    return pd.concat([ordered, pd.DataFrame(rows)], axis=1)


def favorite_flags(p):
    p = validate_probabilities(p)
    return {"home_favorite": (p[:, 2] > p[:, 0]).astype(int),
            "away_favorite": (p[:, 0] > p[:, 2]).astype(int),
            "near_even": (abs(p[:, 2] - p[:, 0]) < 0.05).astype(int)}


def make_rows(metadata, probabilities):
    np, _ = _libs()
    p = validate_probabilities(probabilities, len(metadata))
    rows = metadata.copy(deep=True).reset_index(drop=True)
    rows["validation_year"] = rows.season
    rows["match_date"] = rows.match_date.map(lambda d: str(d)[:10])
    for i, c in enumerate(("p_away", "p_draw", "p_home")):
        rows[c] = p[:, i]
    for c, values in {**derived_values(rows.result, p), **favorite_flags(p)}.items():
        rows[c] = values
    rows["abs_elo_diff"] = np.abs(rows.elo_diff)
    result = rows.loc[:, list(COLUMNS)].astype(DTYPES)
    validate_rows(result)
    return result


def validate_rows(rows, expected=None):
    np, pd = _libs()
    _require(tuple(rows.columns) == COLUMNS and not rows.isna().any().any(), "Row schema/missing")
    _require(rows.match_id.is_unique, "Duplicate OOF IDs")
    _require(set(rows.validation_year).issubset(FOLDS), "Forbidden OOF year")
    for c in STRING_COLUMNS:
        _require(rows[c].map(lambda v: isinstance(v, str) and bool(v.strip())).all(), f"String field: {c}")
    dates = pd.to_datetime(rows.match_date, format="%Y-%m-%d", errors="raise")
    _require(dates.dt.strftime("%Y-%m-%d").tolist() == rows.match_date.tolist(), "Calendar date format")
    _require(not rows.home_team_id.eq(rows.away_team_id).any(), "OOF self match")
    for c in INT_COLUMNS:
        v = rows[c].to_numpy(dtype=float)
        _require(np.isfinite(v).all() and np.equal(v, np.floor(v)).all(), f"Integer field: {c}")
    for c in FLOAT_COLUMNS:
        _require(np.isfinite(rows[c].to_numpy(dtype=float)).all(), f"Finite field: {c}")
    order = rows.sort_values(["validation_year", "match_date", "match_id"], kind="stable").match_id.tolist()
    _require(rows.match_id.tolist() == order, "OOF identity/order")
    p = validate_probabilities(rows[["p_away", "p_draw", "p_home"]], len(rows))
    expected_derived = {**derived_values(rows.result, p), **favorite_flags(p), "abs_elo_diff": np.abs(rows.elo_diff)}
    for c, values in expected_derived.items():
        if c in INT_COLUMNS:
            _require(np.array_equal(rows[c], values), f"Derived field: {c}")
        else:
            _require(np.allclose(rows[c], values, rtol=RTOL, atol=ATOL), f"Derived field: {c}")
    for r in rows.itertuples():
        _require(r.season_phase == season_phase(r.round), "Phase mismatch")
        _require(r.home_season_appearance >= 1 and r.away_season_appearance >= 1, "Appearance ordinal")
        _require(r.home_first5 == int(r.home_season_appearance <= 5) and r.away_first5 == int(r.away_season_appearance <= 5), "First five")
        _require(r.any_team_first5 == int(r.home_first5 or r.away_first5) and r.both_team_first5 == int(r.home_first5 and r.away_first5), "First-five flags")
        statuses = (r.home_status, r.away_status)
        _require(set(statuses).issubset({"ESTABLISHED", "RETURNING", "FIRST_TIME_IN_SCOPE"}), "Club status")
        _require(r.promoted_involved == int(any(s != "ESTABLISHED" for s in statuses)) and
                 r.returning_involved == int("RETURNING" in statuses) and
                 r.established_only == int(all(s == "ESTABLISHED" for s in statuses)), "Status flags")
    if expected is not None:
        _require(len(rows) == len(expected), "OOF identity count")
        for c in COLUMNS:
            if c in FLOAT_COLUMNS:
                _require(np.array_equal(rows[c].to_numpy(), expected[c].to_numpy()), f"Round-trip float: {c}")
            else:
                _require(rows[c].tolist() == expected[c].tolist(), f"OOF identity/metadata: {c}")


def gate_rows(rows):
    validate_rows(rows)
    metrics = {}
    for y in FOLDS:
        f = rows.loc[rows.validation_year.eq(y)]
        metrics[str(y)] = calculate_metrics(f.result, f[["p_away", "p_draw", "p_home"]].to_numpy())
        assert_reference(metrics[str(y)], REFERENCES[y])
        np, _ = _libs()
        _require(np.isclose(f.nll.mean(), metrics[str(y)]["log_loss"], rtol=RTOL, atol=ATOL), "Row NLL inconsistency")
    metrics["pooled"] = calculate_metrics(rows.result, rows[["p_away", "p_draw", "p_home"]].to_numpy())
    assert_reference(metrics["pooled"], REFERENCES["pooled"])
    return metrics


def assert_target_identity(rows, source):
    """Check source metadata, not just an aggregate metric or an ID set."""
    _, pd = _libs()
    targets = pd.concat([source.loc[source.season.eq(y)] for y in FOLDS], ignore_index=True)
    _require(len(rows) == len(targets), "Target identity count")
    for output, origin in (("validation_year", "season"), ("match_id", "match_id"),
                           ("home_team_id", "home_team_id"), ("away_team_id", "away_team_id"),
                           ("result", "result"), ("round", "round"),
                           ("home_team", "home_team"), ("away_team", "away_team")):
        _require(rows[output].tolist() == targets[origin].tolist(), f"Target identity: {output}")
    _require(rows.match_date.tolist() == targets.match_date.map(lambda d: str(d)[:10]).tolist(), "Target date identity")


def reconstruct(source):
    """Real use is deferred; tests may substitute synthetic frames/models."""
    _, pd = _libs()
    state = add_metadata(replay_elo(source))
    outputs, fold_manifests = [], []
    for year in FOLDS:
        train = state.loc[state.season.lt(year)].copy(deep=True)
        valid = state.loc[state.season.eq(year)].copy(deep=True)
        _require((len(train), len(valid)) == FOLD_COUNTS[year], f"Fold count: {year}")
        p = fit_fold(train, valid)
        assert_reference(calculate_metrics(valid.result, p), REFERENCES[year])
        outputs.append(make_rows(valid, p))
        fold_manifests.append({"validation_year": year, "training_seasons": list(range(2015, year)),
                               "training_rows": len(train), "validation_rows": len(valid),
                               "train_ids_sha256": id_hash(train.match_id), "validation_ids_sha256": id_hash(valid.match_id)})
    rows = pd.concat(outputs, ignore_index=True)
    _require(len(rows) == OOF_ROWS, "Pooled count")
    assert_target_identity(rows, source)
    return rows, gate_rows(rows), fold_manifests


def bin_index(value, edges):
    """Literal fixed left-closed boundaries; final finite right edge is inclusive."""
    _require(value == value and edges[0] <= value <= edges[-1], "Bin value outside domain")
    for i in range(len(edges)-1):
        if edges[i] <= value < edges[i+1] or (i == len(edges)-2 and value == edges[-1]):
            return i
    raise DiagnosticError("Invalid bin value")


def sparse_status(n):
    _require(n >= 0 and int(n) == n, "Invalid count")
    return "EMPTY" if n == 0 else "SPARSE" if n < 30 else "NONSPARSE"


def sign(value):
    return 0 if value is None else 1 if value > ATOL else -1 if value < -ATOL else 0


def summary(frame):
    """Actual outcome loss, not -log(p_c) for every member of class-c bins."""
    np, _ = _libs()
    n = len(frame)
    return {"n": n, "status": sparse_status(n), "class_counts": [int(frame.result.eq(c).sum()) for c in CLASS_ORDER],
            "mean_p": [float(frame[p].mean()) if n else None for p in ("p_away", "p_draw", "p_home")],
            "accuracy": float(frame.predicted_class.eq(frame.result).mean()) if n else None,
            "log_loss": float(frame.nll.mean()) if n else None, "brier": float(frame.brier.mean()) if n else None,
            "total_nll": float(frame.nll.sum()), "total_brier": float(frame.brier.sum()),
            "class_conditional": [{"n": int(frame.result.eq(c).sum()),
                                   "status": sparse_status(int(frame.result.eq(c).sum())),
                                   "mean_nll": float(frame.loc[frame.result.eq(c), "nll"].mean()) if frame.result.eq(c).any() else None}
                                  for c in CLASS_ORDER]}


def reliability_cell(frame, class_id):
    n = len(frame)
    column = ("p_away", "p_draw", "p_home")[class_id]
    predicted = float(frame[column].mean()) if n else None
    empirical = float(frame.result.eq(class_id).mean()) if n else None
    return {"n": n, "status": sparse_status(n), "mean_predicted_probability": predicted,
            "empirical_class_frequency": empirical, "bias": empirical-predicted if n else None,
            "total_nll": float(frame.nll.sum()), "mean_nll": float(frame.nll.mean()) if n else None}


def localization_mass(frame, class_id, direction):
    np, _ = _libs()
    _require(direction in (-1, 1), "Localization direction")
    p = frame[("p_away", "p_draw", "p_home")[class_id]].to_numpy()
    mass = np.maximum(direction * (frame.result.eq(class_id).to_numpy(dtype=float) - p), 0)
    narrow = frame.promoted_involved.eq(1) | frame.any_team_first5.eq(1)
    ratio = float(mass[narrow].sum()/mass.sum()) if mass.sum() else None
    return {"share": ratio, "status": "UNDEFINED" if ratio is None else "TRANSITION_CONCENTRATED" if ratio >= 0.80 else "NOT_CONCENTRATED"}


def calibration_diagnostics(rows):
    result = {}
    for year in (*FOLDS, "pooled"):
        frame = rows if year == "pooled" else rows.loc[rows.validation_year.eq(year)]
        classes = {}
        for c, column in enumerate(("p_away", "p_draw", "p_home")):
            bins = frame[column].map(lambda v: bin_index(v, PROBABILITY_EDGES))
            cells = [reliability_cell(frame.loc[bins.eq(i)], c) for i in range(10)]
            nonsparse_bins = [i for i, cell in enumerate(cells) if cell["n"] >= 30]
            core = frame.loc[frame.established_only.eq(1) & frame.any_team_first5.eq(0)]
            classes[str(c)] = {"overall": reliability_cell(frame, c), "bins": cells,
                               "nonsparse": reliability_cell(frame.loc[bins.isin(nonsparse_bins)], c),
                               "core": reliability_cell(core, c),
                               "localization": {str(d): localization_mass(frame, c, d) for d in (-1, 1)}}
        result[str(year)] = classes
    return result


def transition_masks(frame):
    masks = {f"phase:{p}": frame.season_phase.eq(p) for p in ("opening", "middle", "closing")}
    masks.update({"any_first5": frame.any_team_first5.eq(1), "neither_first5": frame.any_team_first5.eq(0),
                  "both_first5": frame.both_team_first5.eq(1)})
    for s in ("home", "away"):
        masks[f"{s}_first5"] = frame[f"{s}_first5"].eq(1)
        masks[f"{s}_6plus"] = frame[f"{s}_first5"].eq(0)
    for group in ("promoted_involved", "returning_involved", "established_only"):
        member = frame[group].eq(1)
        masks[group] = member
        if group != "established_only":
            masks[f"not:{group}"] = ~member
        for p in ("opening", "middle", "closing"):
            masks[f"{group}:phase:{p}"] = member & frame.season_phase.eq(p)
        for first in (0, 1):
            masks[f"{group}:first5:{first}"] = member & frame.any_team_first5.eq(first)
    masks["core"] = frame.established_only.eq(1) & frame.any_team_first5.eq(0)
    # Fixed side-level status/appearance cross-tabs; not extra selected buckets.
    for s in ("home", "away"):
        for status in ("ESTABLISHED", "RETURNING", "FIRST_TIME_IN_SCOPE"):
            for first in (0, 1):
                masks[f"{s}:{status}:first5:{first}"] = frame[f"{s}_status"].eq(status) & frame[f"{s}_first5"].eq(first)
    return masks


def transition_diagnostics(rows):
    return {str(y): {name: summary(frame.loc[mask]) for name, mask in transition_masks(frame).items()}
            for y in (*FOLDS, "pooled")
            for frame in [rows if y == "pooled" else rows.loc[rows.validation_year.eq(y)]]}


def favorite_diagnostics(rows):
    return {str(y): {f"{flag}:{c}": summary(f.loc[f[flag].eq(1) & f.result.eq(c)])
                    for flag in ("home_favorite", "away_favorite", "near_even") for c in CLASS_ORDER}
            for y in (*FOLDS, "pooled")
            for f in [rows if y == "pooled" else rows.loc[rows.validation_year.eq(y)]]}


def confidence_diagnostics(rows):
    output = {}
    for y in (*FOLDS, "pooled"):
        f = rows if y == "pooled" else rows.loc[rows.validation_year.eq(y)]
        bins = f.max_p.map(lambda v: bin_index(v, MAX_P_EDGES))
        cells = {}
        for predicted in (None, *CLASS_ORDER):
            for i in range(len(MAX_P_EDGES)-1):
                part = f.loc[bins.eq(i) & (True if predicted is None else f.predicted_class.eq(predicted))]
                cell = summary(part)
                cell["mean_confidence"] = float(part.max_p.mean()) if len(part) else None
                cell["empirical_argmax_accuracy"] = cell["accuracy"]
                cell["empirical_minus_predicted"] = cell["accuracy"]-cell["mean_confidence"] if len(part) else None
                cells[f"{predicted}:{i}"] = cell
        output[str(y)] = cells
    return output


def elo_diagnostics(rows):
    output = {}
    for y in (*FOLDS, "pooled"):
        f = rows if y == "pooled" else rows.loc[rows.validation_year.eq(y)]
        output[str(y)] = {}
        for column, edges in (("abs_elo_diff", ABS_ELO_EDGES), ("elo_diff", SIGNED_ELO_EDGES)):
            bins = f[column].map(lambda v: bin_index(v, edges))
            cells = []
            for i in range(len(edges)-1):
                part = f.loc[bins.eq(i)]
                cell = summary(part)
                cell["class_frequencies"] = [count/len(part) if len(part) else None for count in cell["class_counts"]]
                cell["bias"] = [a-p if a is not None else None for a, p in zip(cell["class_frequencies"], cell["mean_p"])]
                cells.append(cell)
            output[str(y)][column] = cells
    return output


def club_diagnostics(rows):
    _, pd = _libs()
    sides = pd.concat([rows.assign(team_id=rows[f"{s}_team_id"]) for s in ("home", "away")], ignore_index=True)
    total = float(sides.nll.sum())
    year_totals = sides.groupby("validation_year").nll.sum()
    cells = []
    for (year, team), part in sides.groupby(["validation_year", "team_id"], sort=True):
        cell = summary(part)
        cell.update({"validation_year": int(year), "team_id": str(team),
                     "pooled_attributed_nll_share": cell["total_nll"]/total if total else None,
                     "year_attributed_nll_share": cell["total_nll"]/float(year_totals.loc[year]) if year_totals.loc[year] else None})
        cells.append(cell)
    def concentration(selected):
        ranked = sorted(selected, key=lambda c: (-c["total_nll"], c["validation_year"], c["team_id"]))
        means = pd.Series([c["log_loss"] for c in selected], dtype=float)
        mass = sum(c["total_nll"] for c in selected)
        q = means.quantile([0.25, 0.5, 0.75], interpolation="linear")
        return {"top5_share": sum(c["total_nll"] for c in ranked[:5])/mass if mass else None,
                "median": float(q.loc[0.5]) if len(means) else None,
                "q1": float(q.loc[0.25]) if len(means) else None,
                "q3": float(q.loc[0.75]) if len(means) else None,
                "iqr": float(q.loc[0.75]-q.loc[0.25]) if len(means) else None}
    return {"cells": cells, "attributed_n": len(sides), "attributed_nll": total,
            "concentration": {str(y): concentration(cells if y == "pooled" else [c for c in cells if c["validation_year"] == y])
                              for y in (*FOLDS, "pooled")}}


def decide(calibration, transition):
    """Pure frozen hierarchy. Missing/sparse evidence never reduces the 5-year denominator."""
    for c in map(str, CLASS_ORDER):
        for direction in (-1, 1):
            evidence = [calibration[str(y)][c] for y in FOLDS]
            if sum(sign(e["overall"]["bias"]) == direction for e in evidence) < 4:
                continue
            conditional = any(sum(e["bins"][i]["n"] >= 30 and sign(e["bins"][i]["bias"]) == direction for e in evidence) >= 3 for i in range(10))
            broad = sum(e["nonsparse"]["n"] >= 30 and sign(e["nonsparse"]["bias"]) == direction for e in evidence) >= 4
            core = sum(e["core"]["n"] >= 30 and sign(e["core"]["bias"]) == direction and
                       e["localization"][str(direction)]["share"] is not None and
                       e["localization"][str(direction)]["share"] < 0.80 for e in evidence) >= 3
            if conditional and broad and core:
                return CALIBRATION_GATE
    def positive_comparison(e, a, b, *, check_brier=False):
        left, right = e[a], e[b]
        return (min(left["n"], right["n"]) >= 30 and sign(left["log_loss"]-right["log_loss"]) == 1 and
                (not check_brier or left["brier"]-right["brier"] >= -ATOL))
    all_opening, all_first5, established = 0, 0, 0
    for y in FOLDS:
        e = transition[str(y)]
        all_opening += positive_comparison(e, "phase:opening", "phase:middle")
        all_first5 += positive_comparison(e, "any_first5", "neither_first5")
        established += (positive_comparison(e, "established_only:phase:opening", "established_only:phase:middle", check_brier=True) and
                        positive_comparison(e, "established_only:first5:1", "established_only:first5:0", check_brier=True))
    return TRANSITION_GATE if min(all_opening, all_first5, established) >= 3 else INCONCLUSIVE_GATE


def diagnose(rows):
    """Accepted row artifact only; reference gate precedes every diagnostic helper."""
    gate_rows(rows)
    calibration = calibration_diagnostics(rows)
    transition = transition_diagnostics(rows)
    return {"calibration": calibration, "transition": transition, "favorite": favorite_diagnostics(rows),
            "confidence": confidence_diagnostics(rows), "elo": elo_diagnostics(rows), "clubs": club_diagnostics(rows),
            "decision": decide(calibration, transition)}


def parse_rows(csv_bytes):
    """Strict accepted-artifact parsing; never reads a path or executes a fit."""
    _, pd = _libs()
    _require(not csv_bytes.startswith(b"\xef\xbb\xbf") and b"\r\n" not in csv_bytes, "CSV UTF-8/LF contract")
    _require(csv_bytes.splitlines()[0].decode("utf-8") == ",".join(COLUMNS), "CSV header/order")
    parsed = pd.read_csv(io.BytesIO(csv_bytes), dtype={c: DTYPES[c] for c in COLUMNS if c not in FLOAT_COLUMNS},
                         float_precision="round_trip", keep_default_na=False)
    parsed = parsed.astype(DTYPES)
    validate_rows(parsed)
    return parsed


def serialize_rows(rows):
    gate_rows(rows)
    buffer = rows.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode("utf-8")
    parsed = parse_rows(buffer)
    validate_rows(parsed, rows)
    gate_rows(parsed)
    return buffer


def diagnostic_contract():
    transition_views = [f"phase:{p}" for p in ("opening", "middle", "closing")]
    transition_views += ["any_first5", "neither_first5", "both_first5", "home_first5", "home_6plus", "away_first5", "away_6plus"]
    for group in ("promoted_involved", "returning_involved", "established_only"):
        transition_views.append(group)
        if group != "established_only":
            transition_views.append(f"not:{group}")
        transition_views += [f"{group}:phase:{p}" for p in ("opening", "middle", "closing")]
        transition_views += [f"{group}:first5:{v}" for v in (0, 1)]
    transition_views += ["core"]
    transition_views += [f"{s}:{status}:first5:{v}" for s in ("home", "away")
                         for status in ("ESTABLISHED", "RETURNING", "FIRST_TIME_IN_SCOPE") for v in (0, 1)]
    return {"probability_edges": list(PROBABILITY_EDGES), "max_p_edges": list(MAX_P_EDGES),
            "abs_elo_edges": [0, 50, 100, 200, 300, "+infinity"],
            "signed_elo_edges": ["-infinity", -200, -50, 50, 200, "+infinity"],
            "closure": "left_closed_right_open_final_finite_right_inclusive", "phase_rounds": [5, 29],
            "first5": {"n": 5, "home": "ordinal<=5", "away": "ordinal<=5", "any": "OR", "both": "AND"},
            "status": {"entrant": "M_y-M_previous", "returning": "entrant in prior scoped union", "established": "in M_previous"},
            "favorites": {"home": "p_home>p_away", "away": "p_away>p_home", "near_even": "abs(p_home-p_away)<0.05", "independent": True},
            "sparse": {"empty": 0, "non_sparse_min": 30, "merge": False, "intervals": False},
            "localization": {"narrow": "promoted_involved OR any_team_first5", "core": "established_only AND NOT any_team_first5",
                             "mass": "max(direction*(1[result=c]-p_c),0)", "concentrated_at": 0.80},
            "decision": {"priority": [CALIBRATION_GATE, TRANSITION_GATE, INCONCLUSIVE_GATE],
                         "sign_zero_atol": ATOL, "denominator_years": list(FOLDS),
                         "A": {"overall": 4, "same_class_sign_bin": True, "same_bin": 3, "nonsparse": 4, "core_not_localized": 3},
                         "B": {"opening": 3, "first5": 3, "established_joint_with_brier": 3,
                               "pairs": [["phase:opening", "phase:middle"], ["any_first5", "neither_first5"],
                                         ["established_only:phase:opening", "established_only:phase:middle"],
                                         ["established_only:first5:1", "established_only:first5:0"]],
                               "established_brier_min_delta": -ATOL}},
            "club": {"attribution": "both participants", "share_denominator": "2*match_total", "top": 5, "tie": "year,team_id", "quantile": "linear"},
            "report_views": {"years": [*FOLDS, "pooled"], "transition": transition_views,
                             "reliability": {"classes": list(CLASS_ORDER), "bin_indices": list(range(10)), "max_p_predicted_classes": [None, *CLASS_ORDER]},
                             "favorite": {"flags": ["home_favorite", "away_favorite", "near_even"], "true_classes": list(CLASS_ORDER)},
                             "elo": ["elo_diff", "abs_elo_diff"], "ece": False, "p_values": False, "calibrator": False}}


def a_contract():
    return {"initial_elo": INITIAL_ELO, "k": K, "home_advantage": HOME_ADVANTAGE, "reset": False,
            "feature": list(FEATURES), "batching": "all date reads before result updates", "home_advantage_in_feature": False,
            "scaler": {"class": "StandardScaler", "copy": True, "with_mean": True, "with_std": True, "fit_scope": "training_only"},
            "logistic": {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0, "unspecified_parameters": "locked_defaults"},
            "metrics": {"accuracy": "argmax", "log_loss": "sklearn log_loss labels=[0,1,2]", "brier": "sum over classes, no division", "nll_clipping": "float64 epsilon for loss only"},
            "rtol": RTOL, "atol": ATOL}


def build_manifest(rows, csv_bytes, observed_metrics, folds, *, authorization, commit, runtime, generator_sha, generated_at):
    """Pure provenance construction; does not infer or grant execution authority."""
    _require(set(authorization) == {"reviewed_implementation_commit", "task_reference"} and
             authorization["reviewed_implementation_commit"] == commit and
             isinstance(authorization["task_reference"], str) and authorization["task_reference"].strip(), "Separate generation authorization required")
    manifest = {
        "schema_version": SCHEMA_VERSION, "purpose": PURPOSE, "reviewed_source_commit": REVIEWED_SOURCE_COMMIT,
        "freeze_spec": {"path": SPEC_PATH, "sha256": SPEC_SHA, "commit": FREEZE_COMMIT},
        "generation_authorization": dict(authorization),
        "generator": {"path": MODULE_PATH, "commit": commit, "sha256": generator_sha, "git_dirty": False, "fits": 5, "prediction_batches": 5, "automatic_retries": 0},
        "runtime": dict(runtime),
        "inputs": [{"path": p, "season": y, "rows": SEASON_COUNTS[y], "sha256": h} for y, (p, h) in zip(range(2015, 2025), INPUT_HASHES.items())],
        "team_master": {"path": TEAM_MASTER_PATH, "sha256": TEAM_MASTER_SHA},
        "champion_a_contract": a_contract(), "folds": folds, "class_order": list(CLASS_ORDER),
        "columns": list(COLUMNS), "column_dtypes": dict(DTYPES), "row_count": len(rows),
        "csv": {"path": CSV_PATH, "sha256": sha256(csv_bytes), "encoding": "utf-8", "line_ending": "LF", "float_format": "%.17g", "ordered_ids_sha256": id_hash(rows.match_id)},
        "references": {"values": {str(k): v for k, v in REFERENCES.items()}, "sources": ["docs/H2H_EVALUATION.md", "docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md"], "rtol": RTOL, "atol": ATOL},
        "observed_metrics": observed_metrics, "diagnostic_contract": diagnostic_contract(),
        "gates": {g: "PASS" for g in GATE_NAMES}, "generated_at": generated_at,
    }
    validate_manifest(manifest, csv_bytes, rows)
    return manifest


def validate_manifest(manifest, csv_bytes, rows):
    validate_rows(parse_rows(csv_bytes), rows)
    _require(set(manifest) == set(MANIFEST_KEYS), "Manifest exact schema")
    _require(manifest["schema_version"] == SCHEMA_VERSION and manifest["purpose"] == PURPOSE, "Manifest purpose/version")
    _require(manifest["reviewed_source_commit"] == REVIEWED_SOURCE_COMMIT and manifest["freeze_spec"] == {"path": SPEC_PATH, "sha256": SPEC_SHA, "commit": FREEZE_COMMIT}, "Manifest freeze provenance")
    _require(manifest["class_order"] == list(CLASS_ORDER) and manifest["columns"] == list(COLUMNS) and manifest["column_dtypes"] == DTYPES, "Manifest row schema")
    _require(manifest["row_count"] == len(rows) == OOF_ROWS, "Manifest count")
    _require(manifest["csv"] == {"path": CSV_PATH, "sha256": sha256(csv_bytes), "encoding": "utf-8", "line_ending": "LF", "float_format": "%.17g", "ordered_ids_sha256": id_hash(rows.match_id)}, "Manifest CSV")
    expected_inputs = [{"path": p, "season": y, "rows": SEASON_COUNTS[y], "sha256": h} for y, (p, h) in zip(range(2015, 2025), INPUT_HASHES.items())]
    _require(manifest["inputs"] == expected_inputs and manifest["team_master"] == {"path": TEAM_MASTER_PATH, "sha256": TEAM_MASTER_SHA}, "Manifest input hashes")
    _require(manifest["champion_a_contract"] == a_contract() and manifest["diagnostic_contract"] == diagnostic_contract(), "Manifest frozen contract")
    _require(manifest["gates"] == {g: "PASS" for g in GATE_NAMES}, "Manifest gate coverage")
    _require(manifest["references"] == {"values": {str(k): v for k, v in REFERENCES.items()}, "sources": ["docs/H2H_EVALUATION.md", "docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md"], "rtol": RTOL, "atol": ATOL}, "Manifest references")
    _require(manifest["generator"]["path"] == MODULE_PATH and manifest["generator"]["git_dirty"] is False and
             manifest["generator"]["fits"] == 5 and manifest["generator"]["prediction_batches"] == 5 and manifest["generator"]["automatic_retries"] == 0, "Manifest generator")
    _require(set(manifest["generator"]) == {"path", "commit", "sha256", "git_dirty", "fits", "prediction_batches", "automatic_retries"}, "Generator schema")
    def hex_string(value, length):
        return isinstance(value, str) and len(value) == length and all(c in "0123456789abcdef" for c in value)
    _require(hex_string(manifest["generator"]["commit"], 40) and hex_string(manifest["generator"]["sha256"], 64), "Generator commit/hash")
    runtime = manifest["runtime"]
    _require(set(runtime) == {"python", "platform", "numpy", "pandas", "scikit-learn", "scipy", "requirements_sha256", "lock_sha256"}, "Runtime schema")
    _require(runtime["python"] == "3.12.14" and runtime["platform"].startswith("Windows") and
             {k: runtime[k] for k in ("numpy", "pandas", "scikit-learn", "scipy")} ==
             {"numpy": "2.5.3", "pandas": "3.0.5", "scikit-learn": "1.9.1", "scipy": "1.18.1"} and
             runtime["requirements_sha256"] == CODE_HASHES["requirements.txt"] and
             runtime["lock_sha256"] == CODE_HASHES["requirements-lock.txt"], "Runtime provenance")
    auth = manifest["generation_authorization"]
    _require(set(auth) == {"reviewed_implementation_commit", "task_reference"} and
             auth["reviewed_implementation_commit"] == manifest["generator"]["commit"] and bool(auth["task_reference"].strip()), "Manifest authorization")
    _require(manifest["generated_at"].endswith("Z"), "Manifest UTC timestamp")
    datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))
    metrics = gate_rows(rows)
    _require(manifest["observed_metrics"] == metrics, "Manifest actual metrics")
    _require(len(manifest["folds"]) == 5, "Manifest fold count")
    for year, f in zip(FOLDS, manifest["folds"]):
        _require(set(f) == {"validation_year", "training_seasons", "training_rows", "validation_rows", "train_ids_sha256", "validation_ids_sha256"}, "Fold manifest schema")
        _require(f["validation_year"] == year and f["training_seasons"] == list(range(2015, year)) and
                 (f["training_rows"], f["validation_rows"]) == FOLD_COUNTS[year] and
                 f["validation_ids_sha256"] == id_hash(rows.loc[rows.validation_year.eq(year), "match_id"]), "Manifest fold identity")
        _require(hex_string(f["train_ids_sha256"], 64), "Manifest training ID hash")


def refuse_existing(root):
    _require(not (root / CSV_PATH).exists() and not (root / MANIFEST_PATH).exists(), "Existing/partial pair: REFUSE")


@contextmanager
def production_lock(root):
    """Windows process-level named mutex; no persistent filesystem marker."""
    _require(os.name == "nt", "Frozen production runtime requires Windows")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    name = "Global\\J1ChampionAOOF_" + sha256(str((root / CSV_PATH).resolve()).casefold().encode())
    ctypes.set_last_error(0)
    handle = kernel.CreateMutexW(None, True, name)
    error = ctypes.get_last_error()
    _require(bool(handle), "Cannot create exclusive mutex")
    if error == 183:  # ERROR_ALREADY_EXISTS: refuse even a reentrant same-thread acquisition.
        kernel.CloseHandle(handle)
        raise DiagnosticError("Concurrent reconstruction: REFUSE")
    try:
        yield
    finally:
        kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def publish_pair(root, rows, csv_bytes, manifest):
    """Never repair/clean up partial evidence. Validate all buffers before creation."""
    refuse_existing(root)
    _require(serialize_rows(rows) == csv_bytes, "Publication serialization mismatch")
    validate_manifest(manifest, csv_bytes, rows)
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    verify_hashes(root)
    (root / CSV_PATH).parent.mkdir(parents=True, exist_ok=True)
    for path, buffer in ((CSV_PATH, csv_bytes), (MANIFEST_PATH, manifest_bytes)):
        with (root / path).open("xb") as target:
            target.write(buffer)
            target.flush()
            os.fsync(target.fileno())


def runtime_provenance():
    from importlib.metadata import version
    versions = {k: version(k) for k in ("numpy", "pandas", "scikit-learn", "scipy")}
    _require(platform.python_version() == "3.12.14" and os.name == "nt" and versions == {
        "numpy": "2.5.3", "pandas": "3.0.5", "scikit-learn": "1.9.1", "scipy": "1.18.1"}, "Runtime lock mismatch")
    return {"python": platform.python_version(), "platform": platform.platform(), **versions,
            "requirements_sha256": CODE_HASHES["requirements.txt"], "lock_sha256": CODE_HASHES["requirements-lock.txt"]}


def execution_provenance(root):
    def git(*args):
        return subprocess.run(["git", *args], cwd=root, check=True, text=True, capture_output=True).stdout.strip()
    _require(not git("status", "--porcelain"), "Generation requires clean committed tree")
    commit = git("rev-parse", "HEAD")
    _require(sha256(subprocess.run(["git", "show", f"{FREEZE_COMMIT}:{SPEC_PATH}"], cwd=root,
                                   check=True, capture_output=True).stdout) == SPEC_SHA, "Committed freeze mismatch")
    auth = json.loads(os.environ.get(AUTHORIZATION_ENV, "{}"))
    _require(set(auth) == {"reviewed_implementation_commit", "task_reference"} and
             auth["reviewed_implementation_commit"] == commit and isinstance(auth["task_reference"], str) and
             bool(auth["task_reference"].strip()), "Explicit separate generation authorization provenance required")
    return commit, auth


def run_generation():
    """No real invocation in implementation tests/tasks. Exceptions propagate, once."""
    root = ROOT
    with production_lock(root):
        refuse_existing(root)
        commit, auth = execution_provenance(root)
        key = str((root / CSV_PATH).resolve())
        with _ATTEMPTS_LOCK:
            _require(key not in _ATTEMPTS, "Attempt already made in this process: REFUSE")
            _ATTEMPTS.add(key)
        runtime = runtime_provenance()
        verify_hashes(root)
        source = load_source(root)
        original = source.copy(deep=True)
        rows, metrics, folds = reconstruct(source)
        _, pd = _libs()
        pd.testing.assert_frame_equal(source, original)
        csv_bytes = serialize_rows(rows)
        manifest = build_manifest(rows, csv_bytes, metrics, folds, authorization=auth, commit=commit,
                                  runtime=runtime, generator_sha=sha256((root / MODULE_PATH).read_bytes()),
                                  generated_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        publish_pair(root, rows, csv_bytes, manifest)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Frozen A-only OOF generator. Real reconstruction needs a separately reviewed task; no overrides.")
    parser.parse_args(argv)
    try:
        run_generation()
    except Exception as exc:
        print(f"STOP: {exc}; no automatic retry", file=sys.stderr)
        return 1
    print("Champion A diagnostic-only artifact pair published; no diagnostics or challenger evaluation run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
