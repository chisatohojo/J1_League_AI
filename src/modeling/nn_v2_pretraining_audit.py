"""Read-only input audit for NN v2. No estimator, offset or scaler fitting."""
from collections import defaultdict, deque
from contextlib import ExitStack, contextmanager
import hashlib
import json
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.features import nn_research_timing as timing
from src.modeling import nn_residual_v2 as residual
from src.modeling import nn_v2_offsets as offsets
from src.modeling.nn_research_v1 import COUNTS, FEATURES, validate_features


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def verify_detail_team_ids(master, page, row):
    """Same exact namespaces as jleague_match_stats_season; no fallback."""
    for side in ("home", "away"):
        official = master.resolve_team_id(page[side + "_team"], source="jleague_official", on=row.match_date)
        if official != getattr(row, side + "_team_id"):
            raise ValueError("Official detail / TeamMaster identity mismatch: " + str(row.match_id))


@contextmanager
def no_learning():
    """Tripwire against accidentally reaching a real learning/inference path."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    calls = []

    def forbidden(*args, **kwargs):
        calls.append("FORBIDDEN_LEARNING_OR_INFERENCE")
        raise RuntimeError("Pretraining audit prohibits learning and model inference")

    with ExitStack() as stack:
        for cls in (LogisticRegression, MLPClassifier, Pipeline, StandardScaler, residual.ResidualNN):
            for method in ("fit", "partial_fit", "fit_transform", "predict", "predict_proba",
                           "decision_function"):
                if hasattr(cls, method):
                    stack.enter_context(patch.object(cls, method, forbidden))
        for module, names in ((offsets, ("generate_crossfit_offsets", "fit_final_baseline", "_fit")),
                              (residual, ("initial_parameters",))):
            for name in names:
                stack.enter_context(patch.object(module, name, forbidden))
        yield calls
        if calls:
            raise RuntimeError("A forbidden call was intercepted; audit is not READY")


def split_plan(frame):
    """Freeze IDs and raw Form joins only; never generate offsets/statistics."""
    frame = offsets.validate_state(frame)
    validate_features(frame)
    counts = {int(y): int(n) for y, n in frame.groupby("season").size().items()}
    if counts != COUNTS or len(frame) != 3588:
        raise ValueError("Frozen ordinary-J1 population mismatch")
    form = frame[["match_id", *residual.FORM_FEATURES]].copy()
    residual.feature_array(form[list(residual.FORM_FEATURES)])
    folds, all_targets = [], []
    for year in range(2017, 2026):
        train = frame.loc[frame.season.lt(year)]
        target = frame.loc[frame.season.eq(year)]
        train_ids, target_ids = train.match_id.tolist(), target.match_id.tolist()
        if set(train_ids) & set(target_ids) or set(train.season) != set(range(2015, year)):
            raise ValueError("Cross-fit training boundary/identity mismatch")
        if set(train.result) != {0, 1, 2}:
            raise ValueError("Cross-fit training classes incomplete")
        joined = target[["match_id"]].merge(form, on="match_id", how="left", validate="one_to_one")
        if joined.match_id.tolist() != target_ids or not np.array_equal(
                residual.feature_array(joined[list(residual.FORM_FEATURES)]),
                residual.feature_array(target[list(residual.FORM_FEATURES)])):
            raise ValueError("Raw Form / target ID join mismatch")
        folds.append({"target_year": year, "training_years": list(range(2015, year)),
                      "training_ids": train_ids, "target_ids": target_ids,
                      "training_count": len(train_ids), "target_count": len(target_ids),
                      "training_ids_sha256": canonical_sha(train_ids),
                      "target_ids_sha256": canonical_sha(target_ids),
                      "target_labels_passed_to_baseline_fit": False,
                      "offset_state": "NOT_GENERATED", "scaler_statistics_state": "NOT_GENERATED"})
        all_targets.extend(target_ids)
    residual_ids = frame.loc[frame.season.ge(2017), "match_id"].tolist()
    if len(all_targets) != 2976 or len(set(all_targets)) != 2976 or all_targets != residual_ids:
        raise ValueError("Cross-fit union must equal all 2976 residual rows exactly")
    return {"folds": folds, "residual_scaler_fit_ids": residual_ids,
            "residual_scaler_fit_ids_sha256": canonical_sha(residual_ids),
            "final_baseline_fit_ids": frame.match_id.tolist(),
            "final_baseline_fit_ids_sha256": canonical_sha(frame.match_id.tolist()),
            "seed_ids": frame.loc[frame.season.le(2016), "match_id"].tolist()}


def audit_trace(frame, trace):
    """Verify each read's entire result dependency set, not just its last row."""
    records = {r.match_id: r for r in frame.itertuples(index=False)}
    frozen, applied, dependencies = set(), set(), []
    per_row = []
    forms = defaultdict(lambda: deque(maxlen=5))
    # Independent Elo calculation: no fitted model or target labels at reads.
    ratings = defaultdict(lambda: 1500.0)
    latest = None
    for event in trace:
        mid, at, kind = event["match_id"], event["at"], event["event"]
        if mid not in records or (latest is not None and at < latest):
            raise ValueError("Unknown/reordered event")
        latest = at
        r = records[mid]
        if kind == "result_applied":
            if mid not in frozen or mid in applied or at != r.result_effective_timestamp:
                raise ValueError("Result applied early or more than once")
            if pd.Timestamp(at).date().isoformat() <= r.recorded_source_date:
                raise ValueError("Same-day result update")
            h, a = r.home_team_id, r.away_team_id
            expectation = 1.0 / (1.0 + 10.0 ** ((ratings[a] - ratings[h] - 175.0) / 400.0))
            delta = 30.0 * (int(r.final_label) / 2.0 - expectation)
            ratings[h] += delta
            ratings[a] -= delta
            for club, gf, ga, win in ((h, r.home_score, r.away_score, 2),
                                      (a, r.away_score, r.home_score, 0)):
                forms[club].append((mid, 3 * int(r.final_label == win) + int(r.final_label == 1),
                                    int(gf), int(ga)))
            applied.add(mid)
            dependencies.append(mid)
        elif kind == "features_frozen":
            if mid in frozen or mid in applied or at != r.history_cutoff_timestamp:
                raise ValueError("Duplicate/late feature emission")
            expected_dependencies = {k for k, prior in records.items()
                                     if prior.result_effective_timestamp <= at}
            if applied != expected_dependencies or mid in expected_dependencies:
                raise ValueError("Missing, own, same-day or future result dependency")
            if any(records[k].recorded_source_date >= at[:10] for k in applied):
                raise ValueError("Same-day/future source result used")
            expected = [ratings[r.home_team_id] - ratings[r.away_team_id]]
            for pos in (None, 1, 2, 3):
                for club in (r.home_team_id, r.away_team_id):
                    expected.append(len(forms[club]) if pos is None else sum(g[pos] for g in forms[club]))
            actual = [getattr(r, name) for name in FEATURES]
            if not np.allclose(actual, expected, rtol=0, atol=1e-10):
                raise ValueError("Independent Elo/Form replay mismatch")
            per_row.append({"match_id": mid, "history_count": len(applied),
                            "history_ids_sha256": canonical_sha(dependencies),
                            "max_history_source_date": max((records[k].recorded_source_date for k in applied), default=None),
                            "home_form_ids": [g[0] for g in forms[r.home_team_id]],
                            "away_form_ids": [g[0] for g in forms[r.away_team_id]],
                            "includes_30700": timing.SPECIAL_ID in applied,
                            "independent_9_feature_match": True})
            frozen.add(mid)
        else:
            raise ValueError("Unknown event kind")
    if frozen != set(records) or applied != frozen or len(trace) != 2 * len(records):
        raise ValueError("Incomplete feature/result events")
    return per_row


def future_capacity(schedule, now):
    """Audit saved schedule capacity only. Does not enroll or invent T0/IDs."""
    if now.tzinfo is None:
        raise ValueError("Aware audit clock required")
    s = schedule.copy(deep=True)
    required = {"fixture_key", "round", "match_date", "kickoff_time", "status",
                "home_club", "away_club", "match_page_id", "match_id", "competition_key"}
    if s.columns.has_duplicates or required - set(s) or len(s) != 380 or not s.fixture_key.is_unique:
        raise ValueError("Full 380-fixture schedule required")
    if not s.competition_key.eq("j1_2026_2027").all():
        raise ValueError("Unexpected competition")
    if not s.status.isin(["scheduled", "candidate", "completed"]).all():
        raise ValueError("Invalid status")
    s["round"] = pd.to_numeric(s["round"], errors="raise")
    if not np.equal(s["round"], np.floor(s["round"])).all() or set(s["round"]) != set(range(1, 39)):
        raise ValueError("Unexpected round set")
    clubs = set(s.home_club) | set(s.away_club)
    if len(clubs) != 20:
        raise ValueError("Twenty-club roster required")
    for _, games in s.groupby("round"):
        both = games.home_club.tolist() + games.away_club.tolist()
        if len(games) != 10 or len(set(both)) != 20 or set(both) != clubs:
            raise ValueError("Incomplete/duplicate round roster")
    blank = s.kickoff_time.eq("")
    if not (blank | s.kickoff_time.str.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")).all():
        raise ValueError("Invalid kickoff")
    if not s.match_date.str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}").all():
        raise ValueError("Unknown date; cannot establish future capacity")
    days = pd.to_datetime(s.match_date, errors="raise").dt.tz_localize("Asia/Tokyo")
    # Midnight is only a mathematical lower bound on an unspecified future
    # day's kickoff. Keep the actual time absent; never invent a kickoff/T0.
    s["kickoff_jst"] = pd.NaT
    known = ~blank
    actual = pd.to_datetime(s.loc[known, "match_date"] + "T" + s.loc[known, "kickoff_time"],
                            errors="raise").dt.tz_localize("Asia/Tokyo")
    s["kickoff_jst"] = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns, Asia/Tokyo]")
    s.loc[known, "kickoff_jst"] = actual
    s["provably_future"] = (blank & days.gt(now)) | (known & s.kickoff_jst.gt(now))
    future = [int(n) for n, games in s.groupby("round")
              if games.status.eq("scheduled").all() and games.provably_future.all()]
    if not future:
        return {"status": "HOLD", "reason": "No wholly unstarted round", "enrolled": False, "T0": None}
    proposed = list(range(min(future), min(future) + 20))
    if not set(proposed) <= set(future):
        return {"status": "HOLD", "reason": "Fewer than 20 consecutive wholly unstarted rounds",
                "available_rounds": future, "enrolled": False, "T0": None}
    targets = s.loc[s["round"].isin(proposed)]
    verified = targets.match_page_id.fillna("").ne("") | targets.match_id.fillna("").ne("")
    ids = targets.loc[verified, "match_page_id"].fillna("")
    nonempty = ids.loc[ids.ne("")]
    if not nonempty.is_unique:
        raise ValueError("Duplicate official match-page ID")
    return {"status": "CAPACITY_AVAILABLE_NOT_ENROLLED", "audit_clock": now.isoformat(),
            "available_rounds": future, "provisional_rounds": proposed, "provisional_fixtures": len(targets),
            "official_identity_present": int(verified.sum()), "mapping_pending": int((~verified).sum()),
            "unknown_kickoff_count": int(targets.kickoff_time.eq("").sum()),
            "first_scheduled_date": targets.match_date.min(), "last_scheduled_date": targets.match_date.max(),
            "first_known_kickoff_jst": None if targets.kickoff_jst.dropna().empty else targets.kickoff_jst.min().isoformat(),
            "last_known_kickoff_jst": None if targets.kickoff_jst.dropna().empty else targets.kickoff_jst.max().isoformat(),
            "unknown_kickoff_rule": "date strictly in future proves unstarted only; no kickoff or prediction eligibility invented",
            "fixture_set_sha256": canonical_sha(sorted(targets.fixture_key)),
            "T0": None, "enrolled": False,
            "registration_requires_fresh_revision_and_real_T0": True,
            "unmapped_fixtures_prediction_state": "HOLD_UNTIL_OFFICIAL_ID_VERIFIED"}
