"""Frozen Candidate P independent-Poisson model component."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted


MAX_GOALS = 15
CLASS_ORDER = (0, 1, 2)  # Away, Draw, Home.
MATCH_COLUMNS = (
    "match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "home_score",
    "away_score",
    "elo_diff",
)
FIXTURE_COLUMNS = (
    "match_id",
    "match_date",
    "home_team_id",
    "away_team_id",
    "elo_diff",
)
FEATURE_COLUMNS = (
    "attacking_team_id",
    "defending_team_id",
    "is_home",
    "attacker_elo_diff",
)
OBSERVATION_COLUMNS = (
    "match_id",
    "match_date",
    "side",
    *FEATURE_COLUMNS,
    "target_goals",
)
PROBABILITY_COLUMNS = (
    "match_id",
    "lambda_home",
    "lambda_away",
    "p_away",
    "p_draw",
    "p_home",
    "predicted_class",
)


@dataclass(frozen=True)
class FittedPoissonModel:
    """A fitted instance of the frozen Candidate P pipeline."""

    pipeline: Pipeline


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


def _validate_fixture_frame(frame: pd.DataFrame) -> None:
    _validate_columns(frame, FIXTURE_COLUMNS)
    if _is_blank(frame["match_id"]).any():
        raise ValueError("match_id must be nonmissing and nonblank.")
    if frame["match_id"].duplicated().any():
        raise ValueError("match_id must be unique.")
    for column in ("home_team_id", "away_team_id"):
        if _is_blank(frame[column]).any():
            raise ValueError(f"{column} must be nonmissing and nonblank.")
    if frame["home_team_id"].eq(frame["away_team_id"]).any():
        raise ValueError("home_team_id and away_team_id must differ.")
    parsed_dates = pd.to_datetime(frame["match_date"], errors="coerce", format="mixed")
    if parsed_dates.isna().any():
        raise ValueError("match_date must contain valid, nonmissing dates.")
    try:
        elo = pd.to_numeric(frame["elo_diff"], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("elo_diff must be numeric and finite.") from exc
    if not np.isfinite(elo).all():
        raise ValueError("elo_diff must be numeric and finite.")


def _validated_scores(frame: pd.DataFrame, column: str) -> np.ndarray:
    try:
        values = pd.to_numeric(frame[column], errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{column} must contain nonnegative integers.") from exc
    if not np.isfinite(values).all() or (values < 0).any() or not np.equal(values, np.floor(values)).all():
        raise ValueError(f"{column} must contain nonnegative integers.")
    return values.astype(np.int64)


def _fixture_observations(matches: pd.DataFrame) -> pd.DataFrame:
    """Build alternating home/away feature rows without reading scores."""
    _validate_fixture_frame(matches)
    row_count = len(matches)
    observations = pd.DataFrame(index=np.arange(row_count * 2), columns=FEATURE_COLUMNS)
    observations["attacking_team_id"] = np.column_stack(
        [matches["home_team_id"].to_numpy(), matches["away_team_id"].to_numpy()]
    ).reshape(-1)
    observations["defending_team_id"] = np.column_stack(
        [matches["away_team_id"].to_numpy(), matches["home_team_id"].to_numpy()]
    ).reshape(-1)
    observations["is_home"] = np.tile(np.array([1, 0], dtype=np.int8), row_count)
    elo = pd.to_numeric(matches["elo_diff"], errors="raise").to_numpy(dtype=float)
    observations["attacker_elo_diff"] = np.column_stack([elo, -elo]).reshape(-1)
    return observations.loc[:, list(FEATURE_COLUMNS)]


def build_goal_observations(matches: pd.DataFrame) -> pd.DataFrame:
    """Convert each scored match to home then away goal observations."""
    _validate_columns(matches, MATCH_COLUMNS)
    features = _fixture_observations(matches)
    home_scores = _validated_scores(matches, "home_score")
    away_scores = _validated_scores(matches, "away_score")
    row_count = len(matches)
    result = pd.DataFrame(index=np.arange(row_count * 2))
    result["match_id"] = np.repeat(matches["match_id"].to_numpy(), 2)
    result["match_date"] = np.repeat(matches["match_date"].to_numpy(), 2)
    result["side"] = np.tile(np.array(["home", "away"], dtype=object), row_count)
    for column in FEATURE_COLUMNS:
        result[column] = features[column].to_numpy()
    result["target_goals"] = np.column_stack([home_scores, away_scores]).reshape(-1)
    return result.loc[:, list(OBSERVATION_COLUMNS)]


def build_poisson_pipeline() -> Pipeline:
    """Return a fresh pipeline implementing the frozen Candidate P contract."""
    preprocessor = ColumnTransformer(
        transformers=(
            (
                "teams",
                OneHotEncoder(
                    categories="auto",
                    drop=None,
                    sparse_output=True,
                    dtype=np.float64,
                    handle_unknown="ignore",
                ),
                ("attacking_team_id", "defending_team_id"),
            ),
            ("elo", StandardScaler(), ("attacker_elo_diff",)),
            ("home", "passthrough", ("is_home",)),
        ),
        remainder="drop",
        sparse_threshold=1.0,
    )
    estimator = PoissonRegressor(
        alpha=1.0,
        fit_intercept=True,
        solver="lbfgs",
        max_iter=1000,
        tol=1e-4,
        warm_start=False,
        verbose=0,
    )
    return Pipeline((("features", preprocessor), ("poisson", estimator)))


def _validate_fitted_pipeline(pipeline: Pipeline) -> PoissonRegressor:
    if not isinstance(pipeline, Pipeline) or tuple(pipeline.named_steps) != ("features", "poisson"):
        raise ValueError("Model does not contain the frozen Candidate P pipeline.")
    estimator = pipeline.named_steps["poisson"]
    if not isinstance(estimator, PoissonRegressor):
        raise ValueError("Candidate P must contain exactly one PoissonRegressor.")
    expected = {
        "alpha": 1.0,
        "fit_intercept": True,
        "solver": "lbfgs",
        "max_iter": 1000,
        "tol": 1e-4,
        "warm_start": False,
        "verbose": 0,
    }
    actual = estimator.get_params(deep=False)
    if any(actual[name] != value for name, value in expected.items()):
        raise ValueError("PoissonRegressor parameters differ from the frozen contract.")
    check_is_fitted(estimator)
    if not np.isfinite(estimator.coef_).all() or not np.isfinite(estimator.intercept_):
        raise ValueError("Fitted Poisson coefficients and intercept must be finite.")
    return estimator


def fit_poisson_model(training_matches: pd.DataFrame) -> FittedPoissonModel:
    """Fit one shared Poisson model on two observations per input match."""
    observations = build_goal_observations(training_matches)
    if len(observations) != len(training_matches) * 2:
        raise ValueError("Each training match must produce exactly two goal observations.")
    targets = observations["target_goals"].to_numpy(dtype=float)
    if not np.isfinite(targets).all() or (targets < 0).any() or not np.equal(targets, np.floor(targets)).all():
        raise ValueError("target_goals must contain finite nonnegative integers.")
    pipeline = build_poisson_pipeline()
    pipeline.fit(observations.loc[:, list(FEATURE_COLUMNS)], targets)
    _validate_fitted_pipeline(pipeline)
    return FittedPoissonModel(pipeline=pipeline)


def predict_lambdas(model: FittedPoissonModel, matches: pd.DataFrame) -> pd.DataFrame:
    """Predict home and away scoring rates using the training row semantics."""
    if not isinstance(model, FittedPoissonModel):
        raise TypeError("model must be a FittedPoissonModel.")
    _validate_fitted_pipeline(model.pipeline)
    observations = _fixture_observations(matches)
    predicted = np.asarray(model.pipeline.predict(observations), dtype=float)
    if predicted.shape != (len(matches) * 2,):
        raise ValueError("Poisson model returned an unexpected lambda shape.")
    lambdas = predicted.reshape(-1, 2)
    if not np.isfinite(lambdas).all() or (lambdas <= 0).any():
        raise ValueError("Poisson lambdas must be finite and strictly positive.")
    return pd.DataFrame(
        {
            "match_id": matches["match_id"].to_numpy(copy=True),
            "lambda_home": lambdas[:, 0],
            "lambda_away": lambdas[:, 1],
        }
    )


def _poisson_pmf(rate: float) -> np.ndarray:
    probabilities = np.empty(MAX_GOALS + 1, dtype=float)
    probabilities[0] = np.exp(-rate)
    for goals in range(1, MAX_GOALS + 1):
        probabilities[goals] = probabilities[goals - 1] * rate / goals
    return probabilities


def score_grid_probabilities(lambda_home: float, lambda_away: float) -> np.ndarray:
    """Convert two Poisson rates to normalized [Away, Draw, Home] probabilities."""
    rates = np.asarray([lambda_home, lambda_away], dtype=float)
    if not np.isfinite(rates).all() or (rates <= 0).any():
        raise ValueError("Poisson lambdas must be finite and strictly positive.")
    score_grid = np.outer(_poisson_pmf(rates[0]), _poisson_pmf(rates[1]))
    retained_mass = float(score_grid.sum())
    if not np.isfinite(retained_mass) or retained_mass <= 0:
        raise ValueError("Retained score-grid mass must be finite and positive.")
    probabilities = np.array(
        [
            np.triu(score_grid, k=1).sum(),
            np.trace(score_grid),
            np.tril(score_grid, k=-1).sum(),
        ],
        dtype=float,
    ) / retained_mass
    if (
        not np.isfinite(probabilities).all()
        or (probabilities < 0).any()
        or (probabilities > 1).any()
        or not np.isclose(probabilities.sum(), 1.0, rtol=0.0, atol=1e-12)
    ):
        raise ValueError("Invalid Away/Draw/Home probability vector.")
    return probabilities


def predict_proba(model: FittedPoissonModel, fixtures: pd.DataFrame) -> pd.DataFrame:
    """Predict ordered W/D/L probabilities and plain-argmax classes."""
    lambdas = predict_lambdas(model, fixtures)
    probabilities = np.vstack(
        [
            score_grid_probabilities(home_rate, away_rate)
            for home_rate, away_rate in lambdas.loc[:, ["lambda_home", "lambda_away"]].itertuples(
                index=False, name=None
            )
        ]
    ) if len(lambdas) else np.empty((0, 3), dtype=float)
    result = lambdas.copy(deep=True)
    result[["p_away", "p_draw", "p_home"]] = probabilities
    result["predicted_class"] = np.asarray(CLASS_ORDER, dtype=np.int8)[probabilities.argmax(axis=1)]
    return result.loc[:, list(PROBABILITY_COLUMNS)]
