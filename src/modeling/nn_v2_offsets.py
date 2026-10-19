"""In-memory chronological offset construction; no CSV loader or execution CLI."""
from dataclasses import dataclass, field
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from src.features.nn_research_timing import (
    POLICY, SPECIAL_ID, TIMING_COLUMNS, build_event_features, events,
)
from src.modeling.nn_residual_v2 import CLASSES, FORM_FEATURES, finite, labels

YEARS = tuple(range(2015, 2026))


def prepare_history(matches):
    """Use the retained event policy, without loading or fitting any model."""
    frame = build_event_features(matches)
    validate_state(frame)
    return frame


def validate_state(frame):
    required = {"season", "elo_diff", "match_id", "result", *TIMING_COLUMNS, *FORM_FEATURES}
    if not isinstance(frame, pd.DataFrame) or frame.columns.has_duplicates or required - set(frame.columns):
        raise ValueError("Prepared event features and metadata required")
    seasons = frame.season.to_numpy()
    if seasons.dtype.kind not in "iu" or not np.isin(seasons, YEARS).all():
        raise ValueError("Only ordinary-J1 training years 2015--2025 allowed")
    if set(seasons) != set(YEARS):
        raise ValueError("All seed/target training years must be present")
    expected = events(frame)
    if pd.to_datetime(expected.recorded_source_date).dt.year.tolist() != frame.season.tolist():
        raise ValueError("Source calendar year / training season mismatch")
    for name in TIMING_COLUMNS:
        if frame[name].astype(str).tolist() != expected[name].astype(str).tolist():
            raise ValueError("Unknown/altered chronology: " + name)
    for name in ("timing_exception", "timing_exception_id"):
        if name in frame and frame[name].fillna("").astype(str).str.strip().ne("").any():
            raise ValueError("Unreviewed timing exception field")
    if "original_kickoff" in frame:
        special = frame.match_id.eq(SPECIAL_ID)
        values = frame.loc[special, "original_kickoff"].dropna().astype(str)
        if not values.isin(["", "2024-08-24T19:03:00+09:00"]).all():
            raise ValueError("Known exception original kickoff mismatch")
    finite(frame[["elo_diff", *FORM_FEATURES]].to_numpy(), (len(frame), 9))
    labels(frame.result.to_numpy(), len(frame))
    return frame.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True).copy(deep=True)


def _new_pipeline():
    return Pipeline([("scaler", StandardScaler()), ("classifier", LogisticRegression(
        C=1, solver="lbfgs", max_iter=1000, random_state=0, tol=1e-4))])


def _fit(frame):
    y = labels(frame.result.to_numpy(), len(frame))
    if set(y) != set(CLASSES):
        raise ValueError("Baseline needs all three training classes")
    model = _new_pipeline()
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model.fit(frame[["elo_diff"]], y)
    if caught:
        raise ValueError("Baseline fit warning: " + ",".join(type(w.message).__name__ for w in caught))
    if tuple(model.classes_) != CLASSES:
        raise ValueError("Baseline class order mismatch")
    for value in (model[-1].coef_, model[-1].intercept_, model[0].mean_, model[0].scale_):
        finite(value)
    if model[0].n_samples_seen_ != len(frame):
        raise ValueError("Baseline scaler fit population mismatch")
    return model


def _logits(model, frame):
    if tuple(model.classes_) != CLASSES:
        raise ValueError("Baseline inference class order mismatch")
    if not isinstance(frame, pd.DataFrame) or tuple(frame.columns) != ("elo_diff",):
        raise ValueError("Exact Elo-only input required")
    finite(frame.to_numpy(), (len(frame), 1))
    return finite(model.decision_function(frame), (len(frame), 3))


@dataclass(frozen=True)
class CrossfitOffsets:
    rows: pd.DataFrame
    audit: tuple
    role: str = field(default="crossfit_training_offsets_only", init=False)


@dataclass(frozen=True)
class FinalBaseline:
    pipeline: Pipeline
    audit: dict
    role: str = field(default="final_2015_2025_future_inference_only", init=False)

    def decision_function(self, elo_frame):
        return _logits(self.pipeline, elo_frame)


def _audit(model, train, role):
    return {"role": role, "timing_policy": POLICY,
            "training_years": sorted(int(v) for v in train.season.unique()),
            "training_ids": train.match_id.tolist(), "training_rows": len(train),
            "scaler_rows": int(model[0].n_samples_seen_),
            "scaler_mean": model[0].mean_.tolist(), "scaler_var": model[0].var_.tolist(),
            "coefficient": model[-1].coef_.tolist(), "intercept": model[-1].intercept_.tolist(),
            "class_order": list(CLASSES)}


def generate_crossfit_offsets(prepared):
    frame = validate_state(prepared)
    outputs, audit = [], []
    for year in range(2017, 2026):
        train = frame.loc[frame.season.lt(year)].copy(deep=True)
        target = frame.loc[frame.season.eq(year)].copy(deep=True)
        if train.empty or target.empty or train.season.max() >= year:
            raise ValueError("Incomplete chronological split")
        model = _fit(train)
        # Targets pass only their precomputed pre-match Elo to inference.
        values = _logits(model, target[["elo_diff"]])
        out = target[["match_id", "season"]].copy(deep=True)
        out[["base_logit_away", "base_logit_draw", "base_logit_home"]] = values
        outputs.append(out)
        a = _audit(model, train, "crossfit_training_offsets_only")
        a.update(target_year=year, target_ids=target.match_id.tolist())
        audit.append(a)
    rows = pd.concat(outputs, ignore_index=True)
    if not rows.match_id.is_unique or set(rows.match_id) != set(frame.loc[frame.season.ge(2017), "match_id"]):
        raise ValueError("Offset target set mismatch")
    return CrossfitOffsets(rows, tuple(audit))


def fit_final_baseline(prepared):
    frame = validate_state(prepared)
    model = _fit(frame)
    return FinalBaseline(model, _audit(model, frame, "final_2015_2025_future_inference_only"))
