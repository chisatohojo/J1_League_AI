"""Frozen Candidate G LightGBM state-classifier component."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from sklearn.utils.validation import check_is_fitted

from src.features.form import add_form_features


MODEL_VERSION = "architecture_lightgbm_form_v1"
CLASS_ORDER = (0, 1, 2)  # Away, Draw, Home.
FEATURE_COLUMNS = (
    "elo_diff",
    "home_last5_matches_available",
    "away_last5_matches_available",
    "home_last5_points",
    "away_last5_points",
    "home_last5_goals_for",
    "away_last5_goals_for",
    "home_last5_goals_against",
    "away_last5_goals_against",
)
MATCH_COLUMNS = (
    "match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "home_score",
    "away_score",
    "result",
    "elo_diff",
)
STATE_COLUMNS = (
    "match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "result",
    *FEATURE_COLUMNS,
)
PROBABILITY_COLUMNS = (
    "match_id",
    "p_away",
    "p_draw",
    "p_home",
    "predicted_class",
)
_FORM_SOURCE_COLUMNS = tuple(
    f"{side}_last5_{metric}"
    for metric in ("points", "wins", "draws", "losses", "goals_for", "goals_against")
    for side in ("home", "away")
)
_FROZEN_PARAMETERS = {
    "boosting_type": "gbdt",
    "objective": "multiclass",
    "num_class": 3,
    "n_estimators": 100,
    "learning_rate": 0.05,
    "num_leaves": 4,
    "max_depth": 2,
    "min_child_samples": 40,
    "min_child_weight": 0.001,
    "min_split_gain": 0.0,
    "subsample": 1.0,
    "subsample_freq": 0,
    "colsample_bytree": 1.0,
    "reg_alpha": 0.0,
    "reg_lambda": 1.0,
    "class_weight": None,
    "random_state": 0,
    "n_jobs": 1,
    "verbosity": -1,
    "deterministic": True,
    "force_col_wise": True,
}


@dataclass(frozen=True)
class FittedLightGBMModel:
    """A fitted instance of the frozen Candidate G classifier."""

    classifier: LGBMClassifier


def _validate_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> None:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Input must be a pandas DataFrame.")
    duplicate_columns = frame.columns[frame.columns.duplicated()].tolist()
    if duplicate_columns:
        raise ValueError(f"Duplicate columns are not allowed: {duplicate_columns}")
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | series.map(lambda value: isinstance(value, str) and not value.strip())


def _numeric_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    series = frame[column]
    if not is_numeric_dtype(series.dtype) or is_bool_dtype(series.dtype):
        raise ValueError(f"{column} must be numeric and finite.")
    values = series.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise ValueError(f"{column} must be numeric and finite.")
    return values


def _nonnegative_integer_values(frame: pd.DataFrame, column: str) -> np.ndarray:
    values = _numeric_values(frame, column)
    if (values < 0).any() or not np.equal(values, np.floor(values)).all():
        raise ValueError(f"{column} must contain nonnegative integers.")
    return values.astype(np.int64)


def _validate_matches(matches: pd.DataFrame) -> None:
    _validate_columns(matches, MATCH_COLUMNS)
    if _is_blank(matches["match_id"]).any():
        raise ValueError("match_id must be nonmissing and nonblank.")
    if matches["match_id"].duplicated().any():
        raise ValueError("match_id must be unique.")
    for column in ("home_team_id", "away_team_id"):
        if _is_blank(matches[column]).any():
            raise ValueError(f"{column} must be nonmissing and nonblank.")
    if matches["home_team_id"].eq(matches["away_team_id"]).any():
        raise ValueError("home_team_id and away_team_id must differ.")
    try:
        dates = pd.to_datetime(matches["match_date"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("match_date must contain valid, nonmissing dates.") from exc
    if dates.isna().any():
        raise ValueError("match_date must contain valid, nonmissing dates.")
    if not dates.is_monotonic_increasing:
        raise ValueError("Matches must be supplied in chronological order.")

    home_scores = _nonnegative_integer_values(matches, "home_score")
    away_scores = _nonnegative_integer_values(matches, "away_score")
    results = _nonnegative_integer_values(matches, "result")
    if not np.isin(results, CLASS_ORDER).all():
        raise ValueError("result must contain only 0, 1, or 2.")
    expected = np.where(home_scores > away_scores, 2, np.where(home_scores < away_scores, 0, 1))
    if not np.array_equal(results, expected):
        raise ValueError("result must agree with home_score and away_score.")
    _numeric_values(matches, "elo_diff")


def validate_lightgbm_features(frame: pd.DataFrame) -> None:
    """Hard-check the exact nine Candidate G feature fields without transforming them."""
    _validate_columns(frame, FEATURE_COLUMNS)
    values = {column: _numeric_values(frame, column) for column in FEATURE_COLUMNS}
    for column in ("home_last5_matches_available", "away_last5_matches_available"):
        available = values[column]
        if (
            not np.equal(available, np.floor(available)).all()
            or (available < 0).any()
            or (available > 5).any()
        ):
            raise ValueError(f"{column} must contain integers from 0 through 5.")
    for column in FEATURE_COLUMNS[3:]:
        if (values[column] < 0).any():
            raise ValueError(f"{column} must be nonnegative.")


def build_lightgbm_state_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Build strictly-prior form state from caller-ordered completed matches."""
    _validate_matches(matches)
    source = matches.loc[:, list(MATCH_COLUMNS)].copy(deep=True)
    with_form = add_form_features(source)
    for side in ("home", "away"):
        with_form[f"{side}_last5_matches_available"] = (
            with_form[f"{side}_last5_wins"]
            + with_form[f"{side}_last5_draws"]
            + with_form[f"{side}_last5_losses"]
        )

    for column in _FORM_SOURCE_COLUMNS:
        values = _nonnegative_integer_values(with_form, column)
        if not np.array_equal(values, with_form[column].to_numpy()):
            raise ValueError(f"Generated form field {column} is invalid.")
    validate_lightgbm_features(with_form)
    return with_form.loc[:, list(STATE_COLUMNS)].copy(deep=True)


def build_lightgbm_classifier() -> LGBMClassifier:
    """Return a fresh unfitted estimator with the frozen Candidate G parameters."""
    return LGBMClassifier(**_FROZEN_PARAMETERS)


def _validate_fitted_classifier(classifier: LGBMClassifier) -> None:
    if not isinstance(classifier, LGBMClassifier):
        raise ValueError("Candidate G must contain exactly one LGBMClassifier.")
    actual = classifier.get_params(deep=False)
    if any(actual.get(name) != value for name, value in _FROZEN_PARAMETERS.items()):
        raise ValueError("LGBMClassifier parameters differ from the frozen contract.")
    check_is_fitted(classifier)
    if not np.array_equal(classifier.classes_, np.asarray(CLASS_ORDER)):
        raise ValueError("Expected classes_ in [0, 1, 2] (Away, Draw, Home) order.")
    if classifier.n_features_in_ != len(FEATURE_COLUMNS):
        raise ValueError("Candidate G fitted feature width must be exactly nine.")
    booster = classifier.booster_
    bounds = np.asarray([booster.lower_bound(), booster.upper_bound()], dtype=float)
    if booster.num_feature() != len(FEATURE_COLUMNS) or not np.isfinite(bounds).all():
        raise ValueError("Candidate G fitted state is invalid.")


def _feature_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    validate_lightgbm_features(frame)
    return frame.loc[:, list(FEATURE_COLUMNS)].copy(deep=True)


def fit_lightgbm_model(training_features: pd.DataFrame) -> FittedLightGBMModel:
    """Fit Candidate G on the exact ordered feature vector and result target."""
    _validate_columns(training_features, (*FEATURE_COLUMNS, "result"))
    features = _feature_matrix(training_features)
    target = _nonnegative_integer_values(training_features, "result")
    if not np.array_equal(np.unique(target), np.asarray(CLASS_ORDER)):
        raise ValueError("Training result must contain all and only classes [0, 1, 2].")
    classifier = build_lightgbm_classifier()
    classifier.fit(features, target)
    _validate_fitted_classifier(classifier)
    return FittedLightGBMModel(classifier=classifier)


def predict_proba(model: FittedLightGBMModel, fixtures: pd.DataFrame) -> pd.DataFrame:
    """Return validated [Away, Draw, Home] probabilities and plain-argmax classes."""
    if not isinstance(model, FittedLightGBMModel):
        raise TypeError("model must be a FittedLightGBMModel.")
    _validate_fitted_classifier(model.classifier)
    _validate_columns(fixtures, ("match_id", *FEATURE_COLUMNS))
    if _is_blank(fixtures["match_id"]).any():
        raise ValueError("match_id must be nonmissing and nonblank.")
    if fixtures["match_id"].duplicated().any():
        raise ValueError("match_id must be unique.")
    features = _feature_matrix(fixtures)
    probabilities = np.asarray(model.classifier.predict_proba(features), dtype=float)
    expected_shape = (len(fixtures), len(CLASS_ORDER))
    if probabilities.shape != expected_shape:
        raise ValueError(f"Candidate G returned probability shape {probabilities.shape}, not {expected_shape}.")
    if (
        not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or (probabilities > 1).any()
        or not np.allclose(probabilities.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)
    ):
        raise ValueError("Candidate G returned invalid probabilities.")
    predicted = np.asarray(CLASS_ORDER, dtype=np.int8)[probabilities.argmax(axis=1)]
    return pd.DataFrame(
        {
            "match_id": fixtures["match_id"].to_numpy(copy=True),
            "p_away": probabilities[:, 0],
            "p_draw": probabilities[:, 1],
            "p_home": probabilities[:, 2],
            "predicted_class": predicted,
        }
    ).loc[:, list(PROBABILITY_COLUMNS)]
