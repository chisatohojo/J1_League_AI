"""Frozen season-transition screen. Real execution needs separate authorization.

Import/help are stdlib-only and do not read evidence or execute any model lane.
Implementation tests use synthetic inputs; default production preflight/formal
must not be invoked in the implementation task. ST0 is saved evidence ONLY.
"""

from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from numbers import Integral
import os
from pathlib import Path
import platform
import subprocess
import sys
from types import MappingProxyType
import warnings


ROOT = Path(__file__).parents[2]
MODULE_PATH = "src/modeling/champion_a_season_transition_evaluation.py"
SPEC_PATH = "docs/CHAMPION_A_SEASON_TRANSITION_RESEARCH_SPEC.md"
SPEC_COMMIT = "88b6d28ac12ae2232f29d5084e8d9ebf395292a9"
SPEC_SHA = "efbf7995d2a8f5611d4002f5f9fe2299201d1d24c6e100dbf8662081e163cdd2"
CSV_PATH = "data/processed/model_diagnostics/champion_a_oof_2020_2024.csv"
MANIFEST_PATH = "data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json"
CSV_SHA = "cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59"
MANIFEST_SHA = "b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10"
TEAM_MASTER_PATH = "data/master/teams.csv"
TEAM_MASTER_SHA = "ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f"
MARKER_PATH = "data/processed/model_season_transition/formal_season_transition_attempt.json"
RESULT_PATH = "docs/CHAMPION_A_SEASON_TRANSITION_EVALUATION_RESULT.md"
AUTHORIZATION_ENV = "CHAMPION_A_SEASON_TRANSITION_AUTHORIZATION"
GENERATOR_COMMIT = "6481780f208ffe95294bdb426a3e572a82a34a98"
GENERATOR_SHA = "40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78"
GENERATION_TASK = "champion-a-oof-one-time-generation-approved-2026-10-05"
CALIBRATION_TASK = "champion-a-calibration-formal-evaluation-approved-2026-10-05"
SOURCE_HASHES = {
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
SEMANTIC_HASHES = {
    "src/features/elo.py": "f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4",
    "src/modeling/player_workload_evaluation.py": "7517880be643e7891eb7d0eb426d1dd57744ef5f7b730ce7713457e953457d76",
    "src/modeling/champion_a_oof_diagnostic.py": GENERATOR_SHA,
    "src/collect/matches.py": "0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c",
    "src/collect/teams.py": "b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c",
}
REQUIREMENTS_HASHES = {
    "requirements.txt": "887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda",
    "requirements-lock.txt": "3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04",
}
VERSIONS = {"numpy": "2.5.3", "pandas": "3.0.5", "scipy": "1.18.1", "scikit-learn": "1.9.1"}
YEARS = tuple(range(2015, 2025))
FOLDS = (2020, 2021, 2022, 2023, 2024)
SEASON_COUNTS = {y: 380 if y in (2021, 2024) else 306 for y in YEARS}
FOLD_COUNTS = {2020: (1530, 306), 2021: (1836, 380), 2022: (2216, 306), 2023: (2522, 306), 2024: (2828, 380)}
TRAIN_ID_HASHES = {
    2020: "65b199341adc5ff9c7fc9c09dcfd73b1c4087e5d4f73cd71571fd4a69cddb158",
    2021: "a5a1265db672da0747a01fe0a69ab548ae684871be4f45efc4d1d1563e4ea266",
    2022: "dcd657ec4693b73a32fc27a6ee3dfc6b4c7c6efcde0c90328cdaeed9ce4b6cab",
    2023: "405d0a8913098d6509381825a2299f494649b804af4528585d200e85c8c7013d",
    2024: "54a43cb0b98414d0768f1ad55f4e2adf474cf154080b0af1043792bed8f2304a",
}
VALID_ID_HASHES = {
    2020: "66e2faeb3a51f0ea8e49bd76d1c484d191054997d8753c5acbc8663d3bbf1d35",
    2021: "9cd6cfa337ffb0477108775595a56bedb1edca7d05c4f099888bad54f41ded1e",
    2022: "970c316240ee1597bf823d90711995bce334ba3e767f24d6c2d971088fc11803",
    2023: "7a7e5f5dbf26a0ba046dbf8a59a441a05df535bd9b3730299e2e2b2bc9f46cc9",
    2024: "40ccf48bbadc5398d54f11e79f9f2c5f1e914a4ecede086caa3eef77dd72d915",
}
POOLED_ID_SHA = "0546d0e440f159b8507579933e0cca8deba635f1179b233bcd5e64c889547fe6"
SOURCE_ROWS, OOF_ROWS = 3208, 1678
INITIAL_RATING, HOME_ADVANTAGE, BASE_K, EARLY_K = 1500.0, 175.0, 30.0, 45.0
CLASS_ORDER = (0, 1, 2)
FEATURES = ("elo_diff",)
MODEL_PARAMS = MappingProxyType({"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0})
ATOL, RTOL = 1e-12, 0.0
REFERENCES = {
    "2020": {"n": 306, "accuracy": 0.5065359477124183, "log_loss": 1.023119734659012, "brier": 0.6117572218710644},
    "2021": {"n": 380, "accuracy": 0.5078947368421053, "log_loss": 1.0253437210487792, "brier": 0.6149829138674616},
    "2022": {"n": 306, "accuracy": 0.4019607843137255, "log_loss": 1.0940186385371449, "brier": 0.6610224339161608},
    "2023": {"n": 306, "accuracy": 0.46078431372549017, "log_loss": 1.0604285568595655, "brier": 0.638530529273072},
    "2024": {"n": 380, "accuracy": 0.45, "log_loss": 1.079241181120235, "brier": 0.6531695943664019},
    "pooled": {"n": 1678, "accuracy": 0.466626936829559, "log_loss": 1.056065401323764, "brier": 0.6357323419292724},
}
P_COLUMNS = ("p_away", "p_draw", "p_home")
OOF_COLUMNS = (
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
DTYPES = {c: "float64" if c in FLOAT_COLUMNS else "string" if c in STRING_COLUMNS else "int64" for c in OOF_COLUMNS}
MANIFEST_KEYS = (
    "schema_version", "purpose", "reviewed_source_commit", "freeze_spec", "generation_authorization",
    "generator", "runtime", "inputs", "team_master", "champion_a_contract", "folds", "class_order",
    "columns", "column_dtypes", "row_count", "csv", "references", "observed_metrics",
    "diagnostic_contract", "gates", "generated_at",
)
A_CONTRACT = {
    "initial_elo": 1500.0, "k": 30.0, "home_advantage": 175.0, "reset": False,
    "feature": ["elo_diff"], "batching": "all date reads before result updates", "home_advantage_in_feature": False,
    "scaler": {"class": "StandardScaler", "copy": True, "with_mean": True, "with_std": True, "fit_scope": "training_only"},
    "logistic": {**MODEL_PARAMS, "unspecified_parameters": "locked_defaults"},
    "metrics": {"accuracy": "argmax", "log_loss": "sklearn log_loss labels=[0,1,2]",
                "brier": "sum over classes, no division", "nll_clipping": "float64 epsilon for loss only"},
    "rtol": RTOL, "atol": ATOL,
}
# Canonical JSON digest of original pure metadata, reviewed without artifact IO.
DIAGNOSTIC_CONTRACT_SHA = "707fd3fb4b9ecebf4dc46e7fa268c368c7025ee18882201d850e18d091fcaf4b"
ARTIFACT_FAILURE = "BLOCKED_SEASON_TRANSITION_ARTIFACT_INTEGRITY"
REFERENCE_FAILURE = "BLOCKED_SEASON_TRANSITION_REFERENCE_MISMATCH"
MODEL_FAILURE = "BLOCKED_SEASON_TRANSITION_MODEL_FAILURE"
CLOSE_GATE = "CLOSE_SEASON_TRANSITION_RESEARCH_LANE"
PROCEED_GATE = "PROCEED_TO_SEASON_TRANSITION_PROSPECTIVE_FREEZE"


@dataclass(frozen=True)
class Candidate:
    name: str
    carry: float
    early_k: bool
    mechanisms: int


CANDIDATES = MappingProxyType({
    "ST0": Candidate("accepted A0 baseline", 1.0, False, 0),
    "ST1": Candidate("SEASON_REGRESSION_ONLY", 0.75, False, 1),
    "ST2": Candidate("EARLY_K_ONLY", 1.0, True, 1),
    "ST3": Candidate("SEASON_REGRESSION_PLUS_EARLY_K", 0.75, True, 2),
})
CHALLENGERS = ("ST1", "ST2", "ST3")


class TransitionError(ValueError):
    """Technical STOP: never a research decision or retry permission."""

    def __init__(self, message, status=ARTIFACT_FAILURE):
        self.status = status
        super().__init__(message)


def require(condition, message, status=ARTIFACT_FAILURE):
    if not condition:
        raise TransitionError(message, status)


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


def challenger(name):
    require(name in CHALLENGERS, "ST0/unknown state cannot enter challenger replay/fit API")
    return CANDIDATES[name]


def team_ids(values):
    values = tuple(values)
    require(bool(values) and len(set(values)) == len(values), "Nonempty unique registered roster")
    require(all(isinstance(v, str) and bool(v) and v == v.strip() and v.isprintable() for v in values), "Exact string team IDs")
    return values


def season_regression(ratings):
    """Pure exact 25% regression over EVERY supplied registered ID."""
    team_ids(ratings)
    require(all(not isinstance(r, bool) and isinstance(r, (int, float)) and math.isfinite(r)
                for r in ratings.values()), "Finite rating state")
    result = {key: 1500.0 + 0.75 * (float(value) - 1500.0) for key, value in ratings.items()}
    require(all(math.isfinite(v) for v in result.values()), "Nonfinite boundary state")
    return result


def match_k(name, home_ordinal, away_ordinal):
    definition = challenger(name)
    require(all(isinstance(v, Integral) and not isinstance(v, bool) and v >= 1
                for v in (home_ordinal, away_ordinal)), "Positive integer appearance ordinals")
    return EARLY_K if definition.early_k and (home_ordinal <= 5 or away_ordinal <= 5) else BASE_K


def validate_schedule(source):
    """Pure identity/schedule validation; no Elo, fit, source IO or metrics."""
    np, pd = libs()
    required = ("match_id", "season", "match_date", "home_team_id", "away_team_id", "round", "result")
    require(source.columns.is_unique and all(c in source for c in required) and len(source) > 0, "Schedule schema/empty")
    require(not source.loc[:, list(required)].isna().any().any(), "Missing schedule value")
    for c in ("match_id", "home_team_id", "away_team_id"):
        require(source[c].map(lambda s: isinstance(s, str) and bool(s) and s == s.strip() and s.isprintable()).all(), "Exact string identities")
    for c in ("season", "round", "result"):
        require(source[c].dtype.kind in "iu" and np.isfinite(source[c]).all(), "Integer schedule field")
    require(set(source.season).issubset(YEARS), "Forbidden season: no filtering/discovery")
    require(source.match_id.is_unique and source["round"].ge(1).all(), "Unique IDs/positive round")
    require(source.result.isin(CLASS_ORDER).all() and not source.home_team_id.eq(source.away_team_id).any(), "Class/self-match")
    dates = pd.to_datetime(source.match_date, errors="raise")
    require(dates.dt.tz is None and dates.eq(dates.dt.normalize()).all()
            and dates.dt.year.eq(source.season).all(), "Calendar date/season coherence")
    ordered = source.assign(_date=dates).sort_values(["_date", "match_id"], kind="stable")
    require(ordered.match_id.tolist() == source.match_id.tolist(), "Noncanonical date/ID order")
    sides = pd.concat([pd.DataFrame({"date": dates, "team": source[f"{s}_team_id"]}) for s in ("home", "away")])
    require(not sides.duplicated(["date", "team"]).any(), "Same-date team duplicate")
    return source.reset_index(drop=True).copy(deep=True).assign(match_date=dates.reset_index(drop=True))


def schedule_metadata(source):
    """Ordinals/status/phase from identity ONLY, without reading result values."""
    _, pd = libs()
    counts, rows, membership = {}, [], {}
    for y, frame in source.groupby("season", sort=True):
        membership[int(y)] = set(frame.home_team_id) | set(frame.away_team_id)
    for r in source.itertuples():
        year = int(r.season)
        prior = set().union(*(ids for y, ids in membership.items() if y < year))
        values = {"season_phase": "opening" if r.round <= 5 else "middle" if r.round <= 29 else "closing"}
        for side in ("home", "away"):
            team = getattr(r, f"{side}_team_id")
            key = (year, team)
            ordinal = counts.get(key, 0) + 1
            counts[key] = ordinal
            values[f"{side}_season_appearance"] = ordinal
            values[f"{side}_first5"] = int(ordinal <= 5)
            values[f"{side}_status"] = "ESTABLISHED" if team in membership.get(year-1, set()) else "RETURNING" if team in prior else "FIRST_TIME_IN_SCOPE"
        values["any_team_first5"] = int(values["home_first5"] or values["away_first5"])
        values["both_team_first5"] = int(values["home_first5"] and values["away_first5"])
        statuses = (values["home_status"], values["away_status"])
        values.update(promoted_involved=int(any(s != "ESTABLISHED" for s in statuses)),
                      returning_involved=int("RETURNING" in statuses), established_only=int(all(s == "ESTABLISHED" for s in statuses)))
        rows.append(values)
    return pd.DataFrame(rows)


def replay_candidate(source, name, registered_ids):
    """One fresh full-stream replay. No ST0/borrowed state; caller owns outputs."""
    definition = challenger(name)
    _, pd = libs()
    from src.features.elo import expected_score
    ordered = validate_schedule(source)
    require(not set(("home_rating", "away_rating", "elo_diff", "home_expected", "match_k",
                     "home_season_appearance", "away_season_appearance")) & set(ordered.columns),
            "Input must not contain generated replay columns")
    require(int(ordered.season.iloc[0]) == 2015, "Replay must begin at 2015")
    roster = team_ids(registered_ids)
    require((set(ordered.home_team_id) | set(ordered.away_team_id)).issubset(roster), "Unknown registered ID; no insertion")
    ratings = {key: 1500.0 for key in roster}
    counts, captures, boundaries, current_season = {}, [], [], 2015
    for _, day in ordered.groupby("match_date", sort=False):
        year = int(day.season.iloc[0])
        require(day.season.eq(year).all() and year >= current_season, "Interleaved seasons")
        if year != current_season:
            for boundary in range(current_season + 1, year + 1):
                if definition.carry == 0.75:
                    ratings = season_regression(ratings)
                    boundaries.append(boundary)
            counts = {}
            current_season = year
        daily = []
        for r in day.itertuples():
            home, away = ratings[r.home_team_id], ratings[r.away_team_id]
            home_n, away_n = counts.get(r.home_team_id, 0)+1, counts.get(r.away_team_id, 0)+1
            expectation = expected_score(home + 175.0, away)
            k = match_k(name, home_n, away_n)
            value = {"home_rating": home, "away_rating": away, "elo_diff": home-away,
                     "home_season_appearance": home_n, "away_season_appearance": away_n,
                     "home_expected": expectation, "match_k": k}
            require(all(math.isfinite(v) for v in value.values()), "Nonfinite pre-match state")
            daily.append((r, value))
            captures.append(value)
        # Results are first consumed here, AFTER every date feature capture.
        for r, value in daily:
            delta = value["match_k"] * (int(r.result) / 2.0 - value["home_expected"])
            ratings[r.home_team_id] = value["home_rating"] + delta
            ratings[r.away_team_id] = value["away_rating"] - delta
            require(math.isfinite(ratings[r.home_team_id]) and math.isfinite(ratings[r.away_team_id]), "Nonfinite Elo update")
        for r, value in daily:
            counts[r.home_team_id] = value["home_season_appearance"]
            counts[r.away_team_id] = value["away_season_appearance"]
    outputs = pd.concat([ordered, pd.DataFrame(captures)], axis=1)
    require(outputs.columns.is_unique, "Input must not contain generated replay columns")
    return {"candidate": name, "features": outputs, "final_ratings": ratings.copy(), "boundary_seasons": boundaries}


def validate_source(source, master):
    from src.collect.matches import validate_matches
    normalized = validate_matches(source)
    normalized = validate_schedule(normalized)
    require(len(normalized) == SOURCE_ROWS and normalized.season.value_counts().sort_index().to_dict() == SEASON_COUNTS, "Exact source population")
    require(source.match_id.tolist() == normalized.match_id.tolist(), "IDs must not be normalized")
    registered = {alias.team_id for alias in master.aliases}
    require((set(normalized.home_team_id) | set(normalized.away_team_id)).issubset(registered), "Exact TeamMaster registration")
    for r in normalized.itertuples():
        for side in ("home", "away"):
            require(master.resolve_team_id(getattr(r, f"{side}_team"), on=r.match_date) == getattr(r, f"{side}_team_id"), "Exact TeamMaster alias/date/ID")
    return normalized


def probabilities(p, n=None):
    np, _ = libs()
    p = np.asarray(p, dtype=np.float64)
    require(p.ndim == 2 and p.shape[1] == 3 and len(p) > 0 and (n is None or len(p) == n), "N x 3 probability shape/count")
    require(np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all(), "Probability finite/range")
    require(np.allclose(p.sum(axis=1), 1.0, rtol=RTOL, atol=ATOL), "Probability sum; no repair")
    return p


def labels(y, n, *, all_classes=False):
    np, _ = libs()
    y = np.asarray(y)
    require(CLASS_ORDER == (0, 1, 2) and y.shape == (n,) and y.dtype.kind in "iu"
            and np.isin(y, CLASS_ORDER).all(), "Exact integer class order/labels")
    if all_classes:
        require(np.array_equal(np.unique(y), CLASS_ORDER), "Missing training class")
    return y.astype(np.int64, copy=True)


def validate_oof(rows):
    np, pd = libs()
    require(tuple(rows.columns) == OOF_COLUMNS and len(rows) == OOF_ROWS and not rows.isna().any().any(), "Exact OOF schema/count/missing")
    require(all(str(rows[c].dtype) == DTYPES[c] for c in OOF_COLUMNS), "Exact OOF dtypes")
    require(rows.validation_year.value_counts().sort_index().to_dict() == {y: FOLD_COUNTS[y][1] for y in FOLDS}, "Exact OOF years")
    for c in STRING_COLUMNS:
        require(rows[c].map(lambda s: isinstance(s, str) and bool(s.strip())).all(), "OOF string field")
    for c in FLOAT_COLUMNS:
        require(np.isfinite(rows[c]).all(), "OOF finite field")
    dates = pd.to_datetime(rows.match_date, format="%Y-%m-%d", errors="raise")
    require(dates.dt.strftime("%Y-%m-%d").tolist() == rows.match_date.tolist()
            and dates.dt.year.eq(rows.validation_year).all(), "OOF date/year")
    require(rows.match_id.is_unique and rows.match_id.tolist() == rows.sort_values(["validation_year", "match_date", "match_id"], kind="stable").match_id.tolist(), "OOF ordered unique IDs")
    require(id_hash(rows.match_id) == POOLED_ID_SHA, "Pooled ordered-ID hash")
    p = probabilities(rows[list(P_COLUMNS)], len(rows))
    y = labels(rows.result, len(rows))
    require(np.array_equal(rows.predicted_class, p.argmax(axis=1)), "Saved argmax")
    for c, values in {"max_p": p.max(axis=1), "p_true": p[np.arange(len(y)), y], "abs_elo_diff": abs(rows.elo_diff)}.items():
        require(np.allclose(rows[c], values, rtol=RTOL, atol=ATOL), "Saved derived field")
    require(rows.nll.ge(0).all() and rows.brier.ge(0).all(), "Saved loss domain")
    for y in FOLDS:
        require(id_hash(rows.loc[rows.validation_year.eq(y), "match_id"]) == VALID_ID_HASHES[y], "OOF validation IDs")


def validate_identity(source, rows):
    """Schedule/source-to-OOF identity ONLY; no ST0/candidate replay or metrics."""
    validate_oof(rows)
    target = source.loc[source.season.isin(FOLDS)].reset_index(drop=True)
    require(len(target) == len(rows), "Source-to-OOF row count")
    for output, origin in (("validation_year", "season"), ("match_id", "match_id"), ("result", "result"),
                           ("round", "round"), ("home_team_id", "home_team_id"), ("away_team_id", "away_team_id"),
                           ("home_team", "home_team"), ("away_team", "away_team")):
        require(rows[output].tolist() == target[origin].tolist(), f"Source-to-OOF identity: {output}")
    require(rows.match_date.tolist() == target.match_date.dt.strftime("%Y-%m-%d").tolist(), "Source-to-OOF date")
    meta = schedule_metadata(source).loc[source.season.isin(FOLDS)].reset_index(drop=True)
    for c in meta:
        require(meta[c].tolist() == rows[c].tolist(), f"Source-to-OOF schedule metadata: {c}")
    require(rows.home_favorite.eq((rows.p_home > rows.p_away).astype(int)).all()
            and rows.away_favorite.eq((rows.p_away > rows.p_home).astype(int)).all()
            and rows.near_even.eq((abs(rows.p_home-rows.p_away) < .05).astype(int)).all(), "Saved favorite flags")


def extract_folds(source):
    folds = []
    for year in FOLDS:
        train = source.loc[source.season.between(2015, year-1)].copy(deep=True)
        valid = source.loc[source.season.eq(year)].copy(deep=True)
        require((len(train), len(valid)) == FOLD_COUNTS[year], "Exact expanding-fold counts")
        require(set(train.match_id).isdisjoint(valid.match_id) and train.match_date.max() < valid.match_date.min(), "Prior fold dates/disjoint IDs")
        require(id_hash(train.match_id) == TRAIN_ID_HASHES[year] and id_hash(valid.match_id) == VALID_ID_HASHES[year], "Frozen ordered-fold IDs")
        labels(train.result, len(train), all_classes=True)
        folds.append((year, train, valid))
    require(id_hash([i for _, _, v in folds for i in v.match_id]) == POOLED_ID_SHA, "Pooled fold order")
    return folds


def assert_reference(actual, expected):
    np, _ = libs()
    require(set(actual) == set(expected) == {"n", "accuracy", "log_loss", "brier"}
            and actual["n"] == expected["n"], "Reference schema/n", REFERENCE_FAILURE)
    require(all(np.isfinite(actual[k]) and np.isclose(actual[k], expected[k], rtol=RTOL, atol=ATOL)
                for k in ("accuracy", "log_loss", "brier")), "Saved ST0 reference mismatch", REFERENCE_FAILURE)


def validate_manifest(manifest, csv_bytes, rows):
    require(set(manifest) == set(MANIFEST_KEYS), "Exact manifest keys")
    require(manifest["schema_version"] == "champion_a_oof_diagnostic_v1" and
            manifest["purpose"] == "diagnostic_only_not_formal_evaluation_not_model_input", "Manifest schema/purpose")
    require(manifest["reviewed_source_commit"] == "376973e1f2238bbd29799386ec100dd400648ce4", "Reviewed original source")
    require(manifest["freeze_spec"] == {"path": "docs/CHAMPION_A_OOF_DIAGNOSTIC_FREEZE_SPEC.md",
            "commit": "159ca0c7d71dfd10b9d3888971fb05c9f681855e", "sha256": "3167daf9ddff78ef4c3dceec64ed36782c6c36424baed239d83ce1191c023663"}, "Original freeze")
    require(manifest["generator"] == {"path": "src/modeling/champion_a_oof_diagnostic.py", "commit": GENERATOR_COMMIT,
            "sha256": GENERATOR_SHA, "git_dirty": False, "fits": 5, "prediction_batches": 5, "automatic_retries": 0}, "Generator provenance")
    require(manifest["generation_authorization"] == {"reviewed_implementation_commit": GENERATOR_COMMIT,
            "task_reference": GENERATION_TASK}, "Generation authorization")
    require(manifest["inputs"] == [{"path": path, "season": y, "rows": SEASON_COUNTS[y], "sha256": h}
            for y, (path, h) in zip(YEARS, SOURCE_HASHES.items())], "Recorded source identities")
    require(manifest["team_master"] == {"path": TEAM_MASTER_PATH, "sha256": TEAM_MASTER_SHA}
            and manifest["champion_a_contract"] == A_CONTRACT, "Recorded master/A contract")
    require(metadata_hash(manifest["diagnostic_contract"]) == DIAGNOSTIC_CONTRACT_SHA, "Original diagnostic metadata")
    require(manifest["columns"] == list(OOF_COLUMNS) and manifest["column_dtypes"] == DTYPES
            and manifest["class_order"] == list(CLASS_ORDER) and manifest["row_count"] == OOF_ROWS, "Recorded OOF schema")
    require(manifest["csv"] == {"path": CSV_PATH, "sha256": sha256(csv_bytes), "encoding": "utf-8", "line_ending": "LF",
            "float_format": "%.17g", "ordered_ids_sha256": id_hash(rows.match_id)}, "Recorded CSV identity")
    require(manifest["folds"] == [{"validation_year": y, "training_seasons": list(range(2015, y)),
            "training_rows": FOLD_COUNTS[y][0], "validation_rows": FOLD_COUNTS[y][1],
            "train_ids_sha256": TRAIN_ID_HASHES[y], "validation_ids_sha256": VALID_ID_HASHES[y]} for y in FOLDS], "Recorded folds")
    require(manifest["references"] == {"values": REFERENCES, "sources": ["docs/H2H_EVALUATION.md", "docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md"],
            "rtol": RTOL, "atol": ATOL}, "Recorded references")
    require(set(manifest["observed_metrics"]) == set(REFERENCES), "Recorded reference years")
    for year, value in REFERENCES.items():
        assert_reference(manifest["observed_metrics"][year], value)  # constants, no score computation
    require(manifest["gates"] == {k: "PASS" for k in ("input", "source", "chronology", "folds", "identity", "classes", "probabilities", "references", "serialization")}, "Recorded gates")
    runtime = manifest["runtime"]
    require(set(runtime) == {"python", "platform", *VERSIONS, "requirements_sha256", "lock_sha256"}
            and runtime["python"] == "3.12.14" and runtime["platform"].startswith("Windows")
            and all(runtime[k] == v for k, v in VERSIONS.items())
            and runtime["requirements_sha256"] == REQUIREMENTS_HASHES["requirements.txt"]
            and runtime["lock_sha256"] == REQUIREMENTS_HASHES["requirements-lock.txt"], "Recorded runtime")
    require(manifest["generated_at"].endswith("Z"), "UTC provenance")
    datetime.fromisoformat(manifest["generated_at"].replace("Z", "+00:00"))


def input_hashes():
    require(tuple(SOURCE_HASHES) == tuple(f"data/processed/jleague/{year}_matches_probe.csv" for year in YEARS)
            and YEARS == tuple(range(2015, 2025)), "Explicit 2015-2024 paths only; no discovery/forbidden-year lookup")
    return {**SOURCE_HASHES, TEAM_MASTER_PATH: TEAM_MASTER_SHA, CSV_PATH: CSV_SHA, MANIFEST_PATH: MANIFEST_SHA}


def validate_source_file_semantics(source, year):
    """Pure per-file checks; physical CSV order is NOT a semantic gate.

    Completed-match validation covers schema/unique IDs/fixtures, finite integer
    scores/results and valid dates/teams. Exact TeamMaster IDs are added next by
    the loader; canonical-stream validation follows concat and stable sort.
    """
    from src.collect.matches import validate_matches
    require(isinstance(year, Integral) and not isinstance(year, bool) and year in YEARS,
            "Forbidden per-file season")
    normalized = validate_matches(source)
    require(len(normalized) == SEASON_COUNTS[year] and normalized.season.eq(year).all(),
            "Explicit per-file season/count")
    require(normalized.match_date.dt.year.eq(normalized.season).all(),
            "Per-file calendar date/season coherence")
    require(source.match_id.tolist() == normalized.match_id.tolist(), "IDs must not be normalized")
    return normalized


def canonicalize_source(frames):
    """Pure loader-boundary canonicalization, not evidence repair or replay.

    Caller must have verified ALL frozen bytes and per-file semantics first.
    Exact ten-file season concat; no outcome keys, filtering or deduplication.
    Canonical validation/hashes/OOF identity remain mandatory after this helper.
    """
    _, pd = libs()
    require(len(frames) == len(YEARS), "Exactly ten source files")
    require(all(frame.season.eq(year).all() and len(frame) == SEASON_COUNTS[year]
                for year, frame in zip(YEARS, frames)), "Exact season concat sequence/counts")
    source = pd.concat(frames, ignore_index=True)
    return source.sort_values(["match_date", "match_id"], ascending=True, kind="stable").reset_index(drop=True)


def load_inputs(root):
    """Only explicit frozen paths; all byte gates precede parse. Future tasks ONLY."""
    _, pd = libs()
    from src.collect.teams import load_team_master
    snapshots = {path: (root / path).read_bytes() for path in input_hashes()}
    require(all(sha256(snapshots[p]) == h for p, h in input_hashes().items()), "Frozen input SHA mismatch")
    master = load_team_master(root / TEAM_MASTER_PATH)
    require(sha256((root / TEAM_MASTER_PATH).read_bytes()) == TEAM_MASTER_SHA, "Master changed during load")
    frames = []
    for year, path in zip(YEARS, SOURCE_HASHES):
        values = list(csv.reader(io.StringIO(snapshots[path].decode("utf-8-sig")), strict=True))
        require(bool(values) and all(len(v) == len(values[0]) for v in values), "CSV field count")
        frame = validate_source_file_semantics(pd.DataFrame(values[1:], columns=values[0]), year)
        frame = master.add_team_ids(frame)  # Exact alias/date/registered-ID resolution.
        frames.append(frame)
    source = canonicalize_source(frames)
    source = validate_source(source, master)
    data = snapshots[CSV_PATH]
    require(not data.startswith(b"\xef\xbb\xbf") and b"\r\n" not in data
            and data.splitlines()[0].decode("utf-8") == ",".join(OOF_COLUMNS), "OOF UTF8/LF/header")
    rows = pd.read_csv(io.BytesIO(data), dtype={c: v for c, v in DTYPES.items() if v != "float64"},
                       float_precision="round_trip", keep_default_na=False).astype(DTYPES)
    validate_oof(rows)
    manifest = json.loads(snapshots[MANIFEST_PATH])
    validate_manifest(manifest, data, rows)
    validate_identity(source, rows)
    extract_folds(source)
    roster = sorted(set(source.home_team_id) | set(source.away_team_id))
    return source, rows, manifest, roster


def build_pipeline(name):
    challenger(name)
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    return Pipeline([("scaler", StandardScaler(copy=True, with_mean=True, with_std=True)),
                     ("logistic", LogisticRegression(**MODEL_PARAMS))])


def feature_array(x):
    np, _ = libs()
    x = np.asarray(x, dtype=np.float64)
    require(x.ndim == 2 and x.shape[1] == 1 and len(x) > 0 and np.isfinite(x).all(), "Exactly one finite raw elo_diff feature")
    return x.copy()


def fit_classifier(name, train_x, train_y, target_x, *, progress=None):
    """Prior-only fit; target API has features, NEVER target labels/metadata."""
    challenger(name)
    np, _ = libs()
    from sklearn.exceptions import ConvergenceWarning
    train_x, target_x = feature_array(train_x), feature_array(target_x)
    train_y = labels(train_y, len(train_x), all_classes=True)
    model = build_pipeline(name)
    scaler_count_before = progress["scaler_fits_completed"] if progress is not None else 0
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            model.fit(train_x, train_y)
            if progress is not None:
                progress["fits_completed"] += 1
                progress["scaler_fits_completed"] += 1
            scaler, classifier = model.named_steps["scaler"], model.named_steps["logistic"]
            require(np.array_equal(classifier.classes_, CLASS_ORDER), "Classifier class order", MODEL_FAILURE)
            require(all(np.isfinite(v).all() for v in (scaler.mean_, scaler.var_, scaler.scale_, classifier.coef_, classifier.intercept_)), "Nonfinite fitted state", MODEL_FAILURE)
            require(np.asarray(scaler.n_samples_seen_).ndim == 0 and int(scaler.n_samples_seen_) == len(train_x), "Training-only scaler sample count", MODEL_FAILURE)
            if progress is not None:
                progress["prediction_attempts"] += 1
                progress["stage"] = f"{progress['fold']}:{name}:prediction"
            p = probabilities(model.predict_proba(target_x), len(target_x))
            if progress is not None:
                progress["predictions_completed"] += 1
            record = {"training_n": len(train_x), "scaler_mean": scaler.mean_.tolist(),
                      "scaler_var": scaler.var_.tolist(), "scaler_scale": scaler.scale_.tolist(),
                      "scaler_n_samples_seen": int(scaler.n_samples_seen_), "classes": classifier.classes_.tolist(),
                      "coef": classifier.coef_.tolist(), "intercept": classifier.intercept_.tolist(),
                      "n_iter": classifier.n_iter_.tolist(), "convergence_warning": False,
                      "classifier_params": dict(MODEL_PARAMS)}
    except Exception as exc:
        if (progress is not None and progress["scaler_fits_completed"] == scaler_count_before
                and hasattr(model.named_steps["scaler"], "n_samples_seen_")):
            progress["scaler_fits_completed"] += 1
        raise TransitionError(f"Classifier/prediction technical STOP; no retry: {exc}", MODEL_FAILURE) from exc
    return p, record


def calculate_metrics(y, p):
    np, _ = libs()
    from sklearn.metrics import log_loss
    p = probabilities(p)
    y = labels(y, len(p))
    return {"n": len(y), "accuracy": float(np.mean(p.argmax(axis=1) == y)),
            "log_loss": float(log_loss(y, p, labels=list(CLASS_ORDER))),
            "brier": float(np.mean(np.sum((p - (y[:, None] == np.asarray(CLASS_ORDER)))**2, axis=1)))}


def metric_delta(value, baseline):
    require(value["n"] == baseline["n"], "Matched metric population")
    return {key: value[key] - baseline[key] for key in ("accuracy", "log_loss", "brier")}


def context_masks(frame):
    np, _ = libs()
    for c in ("round", "home_season_appearance", "away_season_appearance"):
        v = frame[c].to_numpy()
        require(v.dtype.kind in "iu" and (v >= 1).all(), "Positive schedule-only context ordinal/round")
    return {"opening": np.asarray(frame["round"] <= 5),
            "any_team_first5": np.asarray((frame.home_season_appearance <= 5) | (frame.away_season_appearance <= 5))}


def context_metrics(y, p, masks):
    require(tuple(masks) == ("opening", "any_team_first5"), "Exactly two context views")
    p = probabilities(p)
    y = labels(y, len(p))
    results = {}
    for name, mask in masks.items():
        require(mask.shape == (len(p),) and mask.dtype.kind == "b", "Context mask identity")
        value = calculate_metrics(y[mask], p[mask]) if mask.any() else {"n": 0, "log_loss": None, "brier": None}
        results[name] = {k: value[k] for k in ("n", "log_loss", "brier")}
    return results


def baseline_gate(rows, manifest):
    """Formal-only saved ST0 reference verification. No baseline replay or fit."""
    np, _ = libs()
    metrics = {}
    for year in (*FOLDS, "pooled"):
        frame = rows if year == "pooled" else rows.loc[rows.validation_year.eq(year)]
        p, y = frame[list(P_COLUMNS)].to_numpy(), frame.result.to_numpy()
        actual = calculate_metrics(y, p)
        assert_reference(actual, REFERENCES[str(year)])
        assert_reference(actual, manifest["observed_metrics"][str(year)])
        eps = np.finfo(np.float64).eps
        require(np.allclose(frame.nll, -np.log(np.clip(p[np.arange(len(y)), y], eps, 1-eps)), rtol=RTOL, atol=ATOL), "Saved row NLL", REFERENCE_FAILURE)
        require(np.allclose(frame.brier, np.sum((p-(y[:, None] == np.asarray(CLASS_ORDER)))**2, axis=1), rtol=RTOL, atol=ATOL), "Saved row Brier", REFERENCE_FAILURE)
        metrics[str(year)] = actual
    return metrics


def candidate_pass(folds, pooled, baseline_folds, baseline_pooled):
    np, _ = libs()
    require(set(folds) == set(baseline_folds) == set(FOLDS), "Fixed fivefold denominator")
    require(pooled["n"] == baseline_pooled["n"] == OOF_ROWS, "Pooled gate count")
    for year in FOLDS:
        require(folds[year]["n"] == baseline_folds[year]["n"] == FOLD_COUNTS[year][1], "Fold gate count")
    require(all(np.isfinite(v[k]) for v in [pooled, baseline_pooled, *folds.values(), *baseline_folds.values()]
                for k in ("log_loss", "brier", "accuracy")), "Nonfinite primary metric")
    improved = sum(folds[y]["log_loss"] < baseline_folds[y]["log_loss"] for y in FOLDS)
    components = {"pooled_ll_improved": pooled["log_loss"] < baseline_pooled["log_loss"],
                  "fold_ll_improved_3_of_5": improved >= 3,
                  "pooled_brier_nonworse": pooled["brier"] <= baseline_pooled["brier"]}
    return {"improved_ll_folds": improved, "components": components, "passes": all(components.values())}


def select_candidate(results):
    require(tuple(results) == tuple(CANDIDATES), "Exact result registry")
    passing = [name for name in CHALLENGERS if results[name]["gate"]["passes"]]
    if not passing:
        return {"decision": CLOSE_GATE, "selected_candidate": None, "tied_candidates": []}
    minimum = min(results[name]["pooled"]["log_loss"] for name in passing)
    tied = [name for name in passing if abs(results[name]["pooled"]["log_loss"] - minimum) <= ATOL]
    selected = min(tied, key=lambda name: (CANDIDATES[name].mechanisms, CHALLENGERS.index(name)))
    return {"decision": PROCEED_GATE, "selected_candidate": selected, "tied_candidates": tied}


def new_progress():
    return {"stage": "marker consumption", "replay_attempts": 0, "replays_completed": 0,
            "fit_attempts": 0, "fits_completed": 0, "scaler_fits_completed": 0,
            "prediction_attempts": 0, "predictions_completed": 0}


def evaluate(source, rows, roster, *, progress=None):
    """Real use formal-only; tests use toy source/OOF, never production evidence."""
    np, _ = libs()
    validate_identity(source, rows)
    extract_folds(source)
    progress = new_progress() if progress is None else progress
    replays, candidate_folds = {}, {}
    for name in CHALLENGERS:
        progress.update(stage=f"{name}:replay", replay_attempts=progress["replay_attempts"]+1)
        replays[name] = replay_candidate(source, name, roster)
        progress["replays_completed"] += 1
        require(replays[name]["features"].match_id.tolist() == source.match_id.tolist(), "Replay source identity")
        candidate_folds[name] = extract_folds(replays[name]["features"])
    results = {name: {"folds": {}, "deltas": {}, "context": {}, "models": {}} for name in CANDIDATES}
    arrays = {name: [] for name in CANDIDATES}
    pooled_y, pooled_masks, identities = [], {"opening": [], "any_team_first5": []}, []
    for index, year in enumerate(FOLDS):
        target = rows.loc[rows.validation_year.eq(year)]
        outputs = {"ST0": target[list(P_COLUMNS)].to_numpy(copy=True)}
        for name in CHALLENGERS:
            _, train, valid = candidate_folds[name][index]
            require(valid.match_id.tolist() == target.match_id.tolist(), "Candidate target order")
            progress.update(stage=f"{year}:{name}:fit", fold=year, fit_attempts=progress["fit_attempts"]+1)
            outputs[name], record = fit_classifier(name, train[list(FEATURES)].to_numpy(copy=True),
                                                  train.result.to_numpy(copy=True), valid[list(FEATURES)].to_numpy(copy=True), progress=progress)
            results[name]["models"][year] = record
        y = target.result.to_numpy(copy=True)  # Scoring labels are joined AFTER prediction.
        progress["stage"] = f"{year}:metrics and context"
        masks = context_masks(target)
        pooled_y.append(y)
        for view in pooled_masks:
            pooled_masks[view].append(masks[view])
        identities.append({"year": year, "training_n": FOLD_COUNTS[year][0], "validation_n": len(target),
                           "training_ids_sha256": TRAIN_ID_HASHES[year], "validation_ids_sha256": id_hash(target.match_id)})
        for name in CANDIDATES:
            results[name]["folds"][year] = calculate_metrics(y, outputs[name])
            results[name]["deltas"][year] = metric_delta(results[name]["folds"][year], results["ST0"]["folds"][year])
            results[name]["context"][year] = context_metrics(y, outputs[name], masks)
            arrays[name].append(outputs[name])
    require((progress["replays_completed"], progress["fits_completed"], progress["scaler_fits_completed"], progress["predictions_completed"]) == (3, 15, 15, 15), "Exactly3 replays/15 fits/scalers/predictions")
    y = np.concatenate(pooled_y)
    progress["stage"] = "pooled metrics and pass gates"
    masks = {view: np.concatenate(v) for view, v in pooled_masks.items()}
    for name in CANDIDATES:
        p = np.concatenate(arrays[name], axis=0)
        require(len(p) == OOF_ROWS, "Matched pooled rows")
        results[name]["pooled"] = calculate_metrics(y, p)
        results[name]["deltas"]["pooled"] = metric_delta(results[name]["pooled"], results["ST0"]["pooled"])
        results[name]["context"]["pooled"] = context_metrics(y, p, masks)
        if name in CHALLENGERS:
            results[name]["gate"] = candidate_pass(results[name]["folds"], results[name]["pooled"], results["ST0"]["folds"], results["ST0"]["pooled"])
    progress["stage"] = "frozen selection"
    decision = select_candidate(results)
    return {"results": results, "identities": identities, "counts": dict(progress),
            "boundaries": {name: replays[name]["boundary_seasons"] for name in CHALLENGERS}, **decision}


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


def execution_head(root):
    require(not git(root, "status", "--porcelain").strip(), "Clean reviewed tree required")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    require(len(head) == 40 and all(c in "0123456789abcdef" for c in head), "Exact execution HEAD")
    return head


def verify_code(root, head):
    require(sha256(git(root, "show", f"{SPEC_COMMIT}:{SPEC_PATH}")) == SPEC_SHA
            and sha256((root / SPEC_PATH).read_bytes()) == SPEC_SHA, "Committed/live spec SHA")
    git(root, "merge-base", "--is-ancestor", SPEC_COMMIT, head)
    data = (root / MODULE_PATH).read_bytes()
    require(data == git(root, "show", f"{head}:{MODULE_PATH}"), "Committed evaluator bytes")
    require(all(sha256((root / p).read_bytes()) == h for p, h in SEMANTIC_HASHES.items()), "Reviewed semantic code SHA")
    allowed = {"__future__", "argparse", "ast", "contextlib", "csv", "ctypes", "dataclasses", "datetime", "hashlib", "importlib",
               "io", "json", "math", "numbers", "os", "pathlib", "platform", "subprocess", "sys", "types", "warnings", "numpy", "pandas", "sklearn"}
    scoped = {"src.features.elo": {"expected_score"}, "src.collect.matches": {"validate_matches"}, "src.collect.teams": {"load_team_master"}}
    for node in ast.walk(ast.parse(data.decode("utf-8"))):
        if isinstance(node, ast.ImportFrom):
            if node.module in scoped:
                require({a.name for a in node.names}.issubset(scoped[node.module]), "Unscoped repository utility")
            else:
                require(node.module and node.module.split(".")[0] in allowed, "Forbidden lane/import")
                if node.module.startswith("sklearn"):
                    require(node.module in {"sklearn.linear_model", "sklearn.pipeline", "sklearn.preprocessing", "sklearn.metrics", "sklearn.exceptions"}, "Forbidden sklearn dependency")
        elif isinstance(node, ast.Import):
            require(all(a.name.split(".")[0] in allowed for a in node.names), "Forbidden import")
    return sha256(data)


def validate_registry():
    require(tuple(CANDIDATES) == ("ST0", "ST1", "ST2", "ST3") and CHALLENGERS == ("ST1", "ST2", "ST3"), "Exact candidate registry")
    require(tuple(CANDIDATES.values()) == (
        Candidate("accepted A0 baseline", 1.0, False, 0), Candidate("SEASON_REGRESSION_ONLY", .75, False, 1),
        Candidate("EARLY_K_ONLY", 1.0, True, 1), Candidate("SEASON_REGRESSION_PLUS_EARLY_K", .75, True, 2)), "Frozen state definitions")
    require((INITIAL_RATING, HOME_ADVANTAGE, BASE_K, EARLY_K, CLASS_ORDER, FEATURES) == (1500.0, 175.0, 30.0, 45.0, (0, 1, 2), ("elo_diff",)), "Frozen numeric/feature constants")
    require(dict(MODEL_PARAMS) == {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 0}, "Frozen model params")


def runtime_provenance(root):
    from importlib.metadata import version
    observed = {key: version(key) for key in VERSIONS}
    require(os.name == "nt" and platform.python_version() == "3.12.14" and observed == VERSIONS, "Frozen Windows runtime")
    require(all(sha256((root / p).read_bytes()) == h for p, h in REQUIREMENTS_HASHES.items()), "Frozen dependency locks")
    return {"python": platform.python_version(), "platform": platform.platform(), **observed,
            "requirements_sha256": REQUIREMENTS_HASHES["requirements.txt"], "lock_sha256": REQUIREMENTS_HASHES["requirements-lock.txt"]}


def path_present(path):
    return path.exists() or path.is_symlink()


def refuse_existing(root):
    require(not path_present(root / MARKER_PATH), "Existing/partial consumed marker: REFUSE")
    require(not path_present(root / RESULT_PATH), "Existing/partial result: REFUSE")


def preflight():
    head = execution_head(ROOT)
    code_sha = verify_code(ROOT, head)
    validate_registry()
    runtime = runtime_provenance(ROOT)
    refuse_existing(ROOT)
    source, rows, _, roster = load_inputs(ROOT)
    folds = extract_folds(source)
    return {"status": "READY_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_FORMAL_EVALUATION", "head": head, "spec_commit": SPEC_COMMIT, "spec_sha": SPEC_SHA,
            "evaluator_sha": code_sha, "input_hashes": input_hashes(), "runtime": runtime,
            "source_n": len(source), "pooled_n": len(rows), "registered_teams": len(roster),
            "folds": [{"year": y, "training_n": len(t), "validation_n": len(v)} for y, t, v in folds],
            "candidate_replay": "NOT RUN", "candidate_fit": "NOT RUN", "candidate_prediction": "NOT RUN",
            "candidate_metrics": "NOT RUN", "marker_created": False, "result_created": False}


def formal_authorization(root):
    try:
        auth = json.loads(os.environ.get(AUTHORIZATION_ENV, "{}"))
    except ValueError as exc:
        raise TransitionError("Malformed formal authorization") from exc
    require(isinstance(auth, dict) and set(auth) == {"approved_execution_head", "task_reference"}, "Separate formal authorization required")
    require(isinstance(auth["task_reference"], str) and bool(auth["task_reference"].strip())
            and auth["task_reference"].strip() not in {GENERATION_TASK, CALIBRATION_TASK}, "Distinct season-transition formal task required")
    head = execution_head(root)
    require(auth["approved_execution_head"] == head, "Approved exact execution HEAD")
    return head, auth


@contextmanager
def process_lock(root):
    """Dedicated nonpersistent Windows named mutex; no wait, file or repair."""
    require(os.name == "nt", "Windows process lock required")
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    name = "Global\\J1ChampionASeasonTransition_" + sha256(str((root / MARKER_PATH).resolve()).casefold().encode())
    ctypes.set_last_error(0)
    handle = kernel.CreateMutexW(None, True, name)
    require(bool(handle), "Process lock unavailable")
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        raise TransitionError("Concurrent second formal execution: REFUSE")
    try:
        yield
    finally:
        kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def marker_payload(root, head, auth):
    from importlib.metadata import PackageNotFoundError, version
    def observed_hash(path):
        try:
            return sha256((root / path).read_bytes())
        except OSError:
            return None
    def observed_version(key):
        try:
            return version(key)
        except PackageNotFoundError:
            return None
    return {"schema_version": "champion_a_season_transition_attempt_v1", "state": "ATTEMPT_CONSUMED",
            "authorization": auth, "execution_head": head,
            "spec": {"path": SPEC_PATH, "commit": SPEC_COMMIT, "expected_sha256": SPEC_SHA, "observed_sha256": observed_hash(SPEC_PATH)},
            "evaluator": {"path": MODULE_PATH, "commit": head, "sha256": observed_hash(MODULE_PATH)},
            "expected_inputs": input_hashes(), "runtime": {"python": platform.python_version(), "platform": platform.platform(), **{k: observed_version(k) for k in VERSIONS}},
            "dependency_lock": {p: {"expected_sha256": h, "observed_sha256": observed_hash(p)} for p, h in REQUIREMENTS_HASHES.items()},
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


def exclusive_write(path, data):
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
    """Pure full-precision result rendering; never writes derived artifacts."""
    lines = ["# Champion A Season Transition Evaluation Result", "", "Formal status: COMPLETE", "",
             "Reused historical RESEARCH SCREEN, not unseen confirmation, causality, or a new Champion.", "",
             "## Provenance and pre-fit gates", "", "Source/master/OOF/schema/identity/chronology/runtime/ST0 reference gates: PASS.", "",
             "~~~json", json.dumps(provenance, ensure_ascii=False, indent=2, allow_nan=False), "~~~", "",
             "## Frozen state and replay rules", "",
             "Initial1500 / HA175 / scale400 / raw elo_diff without HA / 90-minute result / date-batched reads before updates.",
             "ST0=saved accepted p, ZERO replay/fit/prediction; ST1=carry0.75,K30; ST2=carry1,K45 iff either ordinal<=5 else30; ST3=both.",
             "All population IDs shrink once at every2016-2024 boundary for ST1/ST3, including absent teams. Ordinals reset each season.", "",
             "~~~json", json.dumps({"fold_identities": outcome["identities"], "boundary_seasons": outcome["boundaries"], "counts": outcome["counts"],
             "automatic_retries": 0, "st0_replays": 0, "st0_fits": 0, "st0_predictions": 0, "winner_refits": 0}, indent=2), "~~~", "",
             "## Training-only scaler/classifier and convergence evidence", ""]
    for name in CHALLENGERS:
        lines += [f"### {name}", "", "~~~json", json.dumps(outcome["results"][name]["models"], indent=2, allow_nan=False), "~~~", ""]
    lines += ["## Metrics and matched deltas", "", "| Candidate | Year | n | Accuracy | Log Loss | Brier | Delta Accuracy | Delta LL | Delta Brier |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for name, result in outcome["results"].items():
        for year in (*FOLDS, "pooled"):
            m = result["pooled"] if year == "pooled" else result["folds"][year]
            d = result["deltas"][year]
            lines.append(f'| {name} | {year} | {m["n"]} | {m["accuracy"]!r} | {m["log_loss"]!r} | {m["brier"]!r} | {d["accuracy"]!r} | {d["log_loss"]!r} | {d["brier"]!r} |')
    lines += ["", "## Exactly two transition views (context ONLY)", "", "| Candidate | Year | View | n | Log Loss | Brier |", "| --- | --- | --- | --- | --- | --- |"]
    for name, result in outcome["results"].items():
        for year in (*FOLDS, "pooled"):
            for view, value in result["context"][year].items():
                lines.append(f'| {name} | {year} | {view} | {value["n"]} | {value["log_loss"]!r} | {value["brier"]!r} |')
    lines += ["", "## Candidate gate and selection", "", "| Candidate | Improved LL folds /5 | Pooled LL improved | >=3 folds | Pooled Brier nonworse | Pass |", "| --- | --- | --- | --- | --- | --- |"]
    for name in CHALLENGERS:
        g = outcome["results"][name]["gate"]
        c = g["components"]
        lines.append(f'| {name} | {g["improved_ll_folds"]}/5 | {c["pooled_ll_improved"]} | {c["fold_ll_improved_3_of_5"]} | {c["pooled_brier_nonworse"]} | {g["passes"]} |')
    lines += ["", f'Selected candidate: {outcome["selected_candidate"]}', f'Minimum-anchored tied set: {outcome["tied_candidates"]}',
              "Tie: absolute1e-12/rtol0 from minimum passing pooled LL; mechanisms ST1=1/ST2=1/ST3=2; then ST1/ST2/ST3.", "",
              "## Interpretation and actions not performed", "", "Accuracy/context excluded from gates and selection; no causality/unseen-improvement claim.",
              "Closed calibration lane remains unchanged. No calibration/architecture/P/G/workload/xG/player/suspension evaluation.",
              "ST0 refit/replay/prediction / OOF regeneration / diagnose(): NOT RUN.",
              "2025 / 2026+ / lockbox inspection / HTTP / production prediction / activation: NOT USED.",
              "Feature-contract changes=NO; parameter-contract changes=NO; tuning=NOT RUN; adaptive follow-up=NOT RUN.",
              "Saved Champion A/persisted/opened predictions: UNCHANGED. Derived datasets/models/plots: NOT CREATED. Push NOT PERFORMED.",
              "A pass permits ONLY a separate prospective freeze at a NEW unseen boundary, not promotion.", "",
              "## Final research decision", "", outcome["decision"], ""]
    return "\n".join(lines)


def publish_result(root, document, marker_sha):
    require(not path_present(root / RESULT_PATH), "Existing/partial result: REFUSE")
    require(sha256((root / MARKER_PATH).read_bytes()) == marker_sha, "Immutable marker changed")
    require(all(sha256((root / p).read_bytes()) == h for p, h in input_hashes().items()), "Input changed before publication")
    exclusive_write(root / RESULT_PATH, document.encode("utf-8"))


def formal():
    root = ROOT
    head, auth = formal_authorization(root)
    require(not path_present(root / RESULT_PATH), "Existing/partial result: REFUSE")
    with process_lock(root):
        refuse_existing(root)
        progress = new_progress()
        try:
            marker_sha = consume_marker(root, marker_payload(root, head, auth))
            progress["stage"] = "pre-fit integrity"
            require(execution_head(root) == head, "Execution HEAD/tree changed")
            code_sha = verify_code(root, head)
            validate_registry()
            runtime = runtime_provenance(root)
            source, rows, manifest, roster = load_inputs(root)
            progress["stage"] = "ST0 saved reference gate"
            reference = baseline_gate(rows, manifest)
            outcome = evaluate(source, rows, roster, progress=progress)
            progress["stage"] = "result publication"
            provenance = {"execution_head": head, "authorization": auth, "spec_commit": SPEC_COMMIT, "spec_sha": SPEC_SHA,
                          "evaluator_sha": code_sha, "input_hashes": input_hashes(), "runtime": runtime,
                          "st0_reference": reference, "marker_path": MARKER_PATH, "marker_sha": marker_sha, "marker_state": "ATTEMPT_CONSUMED"}
            publish_result(root, build_result(outcome, provenance), marker_sha)
        except Exception as exc:
            status = exc.status if isinstance(exc, TransitionError) else ARTIFACT_FAILURE
            evidence = "consumed attempt retained" if path_present(root / MARKER_PATH) else "attempt not consumed"
            raise TransitionError(f"{exc}; {evidence}; progress={progress}", status) from exc
    return {"status": "COMPLETE", "decision": outcome["decision"], "selected_candidate": outcome["selected_candidate"],
            "counts": outcome["counts"], "automatic_retries": 0, "marker_sha": marker_sha}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Frozen season-transition screen: default read-only preflight; formal requires separate reviewed authorization.")
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--confirm-one-shot", action="store_true")
    args = parser.parse_args(argv)
    if args.formal != args.confirm_one_shot:
        parser.error("Formal requires BOTH --formal and --confirm-one-shot")
    try:
        result = formal() if args.formal else preflight()
    except Exception as exc:
        status = exc.status if isinstance(exc, TransitionError) else ARTIFACT_FAILURE
        print(f"{status}: {exc}; technical STOP; no retry and no research decision", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
