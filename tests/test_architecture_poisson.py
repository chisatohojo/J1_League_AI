import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.modeling.architecture_poisson import (
    FEATURE_COLUMNS,
    MAX_GOALS,
    OBSERVATION_COLUMNS,
    PROBABILITY_COLUMNS,
    build_goal_observations,
    build_poisson_pipeline,
    fit_poisson_model,
    predict_lambdas,
    predict_proba,
    score_grid_probabilities,
)


def _training_matches() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "match_id": ["m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8"],
            "match_date": pd.to_datetime(
                ["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04",
                 "2020-01-05", "2020-01-06", "2020-01-07", "2020-01-08"]
            ),
            "home_team_id": ["A", "B", "C", "A", "B", "C", "A", "C"],
            "away_team_id": ["B", "C", "A", "C", "A", "B", "B", "A"],
            "home_score": [2, 0, 1, 3, 1, 2, 0, 1],
            "away_score": [1, 1, 0, 2, 2, 0, 0, 3],
            "elo_diff": [40.0, -15.0, 5.0, 80.0, -30.0, 20.0, 0.0, -55.0],
        }
    )


def _fixtures() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "match_id": ["f1", "f2"],
            "match_date": ["2021-02-01", "2021-02-02"],
            "home_team_id": ["A", "NEW"],
            "away_team_id": ["C", "B"],
            "elo_diff": [25.0, -10.0],
        }
    )


def test_build_goal_observations_exact_rows_semantics_order_and_no_mutation():
    matches = _training_matches().iloc[[0]].copy(deep=True)
    original = matches.copy(deep=True)

    result = build_goal_observations(matches)

    assert tuple(result.columns) == OBSERVATION_COLUMNS
    assert len(result) == 2
    assert result.iloc[0].to_dict() == {
        "match_id": "m1",
        "match_date": pd.Timestamp("2020-01-01"),
        "side": "home",
        "attacking_team_id": "A",
        "defending_team_id": "B",
        "is_home": 1,
        "attacker_elo_diff": 40.0,
        "target_goals": 2,
    }
    assert result.iloc[1].to_dict() == {
        "match_id": "m1",
        "match_date": pd.Timestamp("2020-01-01"),
        "side": "away",
        "attacking_team_id": "B",
        "defending_team_id": "A",
        "is_home": 0,
        "attacker_elo_diff": -40.0,
        "target_goals": 1,
    }
    assert_frame_equal(matches, original)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.drop(columns="elo_diff"), "Missing required columns"),
        (lambda frame: pd.concat([frame, frame], axis=1), "Duplicate columns"),
        (lambda frame: frame.assign(match_id="m1"), "match_id must be unique"),
        (lambda frame: frame.assign(home_team_id="  "), "nonmissing and nonblank"),
        (lambda frame: frame.assign(home_team_id=frame["away_team_id"]), "must differ"),
        (lambda frame: frame.assign(match_date="not-a-date"), "valid, nonmissing dates"),
        (lambda frame: frame.assign(home_score=-1), "nonnegative integers"),
        (lambda frame: frame.assign(away_score=1.5), "nonnegative integers"),
        (lambda frame: frame.assign(elo_diff=np.inf), "numeric and finite"),
    ],
)
def test_build_goal_observations_rejects_invalid_input(mutation, message):
    matches = _training_matches().iloc[:2].copy(deep=True)
    with pytest.raises(ValueError, match=message):
        build_goal_observations(mutation(matches))


def test_build_poisson_pipeline_has_exact_preprocessor_and_estimator_contract():
    pipeline = build_poisson_pipeline()

    assert isinstance(pipeline, Pipeline)
    assert tuple(pipeline.named_steps) == ("features", "poisson")
    preprocessor = pipeline.named_steps["features"]
    assert isinstance(preprocessor, ColumnTransformer)
    assert preprocessor.remainder == "drop"
    assert preprocessor.sparse_threshold == 1.0
    teams_name, encoder, team_columns = preprocessor.transformers[0]
    assert teams_name == "teams"
    assert isinstance(encoder, OneHotEncoder)
    assert encoder.handle_unknown == "ignore"
    assert encoder.categories == "auto"
    assert encoder.drop is None
    assert encoder.sparse_output is True
    assert encoder.dtype == np.float64
    assert tuple(team_columns) == ("attacking_team_id", "defending_team_id")
    elo_name, scaler, elo_columns = preprocessor.transformers[1]
    assert elo_name == "elo"
    assert isinstance(scaler, StandardScaler)
    assert tuple(elo_columns) == ("attacker_elo_diff",)
    assert preprocessor.transformers[2] == ("home", "passthrough", ("is_home",))
    assert sum(isinstance(value, StandardScaler) for _, value, _ in preprocessor.transformers) == 1

    estimator = pipeline.named_steps["poisson"]
    assert isinstance(estimator, PoissonRegressor)
    assert estimator.get_params(deep=False) == {
        "alpha": 1.0,
        "fit_intercept": True,
        "max_iter": 1000,
        "solver": "lbfgs",
        "tol": 1e-4,
        "verbose": 0,
        "warm_start": False,
    }
    assert sum(isinstance(step, PoissonRegressor) for step in pipeline.named_steps.values()) == 1


def test_build_poisson_pipeline_returns_fresh_instances():
    first = build_poisson_pipeline()
    second = build_poisson_pipeline()
    assert first is not second
    assert first.named_steps["features"] is not second.named_steps["features"]
    assert first.named_steps["poisson"] is not second.named_steps["poisson"]


def test_fit_completes_is_finite_deterministic_and_does_not_mutate_input():
    matches = _training_matches()
    original = matches.copy(deep=True)

    first = fit_poisson_model(matches)
    second = fit_poisson_model(matches)

    first_estimator = first.pipeline.named_steps["poisson"]
    second_estimator = second.pipeline.named_steps["poisson"]
    assert np.isfinite(first_estimator.coef_).all()
    assert np.isfinite(first_estimator.intercept_)
    np.testing.assert_array_equal(first_estimator.coef_, second_estimator.coef_)
    assert first_estimator.intercept_ == second_estimator.intercept_
    assert_frame_equal(matches, original)


def test_elo_scaler_statistics_come_only_from_training_observations():
    matches = _training_matches()
    observations = build_goal_observations(matches)
    expected = observations["attacker_elo_diff"].to_numpy(dtype=float)
    model = fit_poisson_model(matches)
    scaler = model.pipeline.named_steps["features"].named_transformers_["elo"]

    np.testing.assert_allclose(scaler.mean_, [expected.mean()], rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(scaler.var_, [expected.var()], rtol=0.0, atol=1e-12)
    frozen_mean = scaler.mean_.copy()
    frozen_var = scaler.var_.copy()
    predict_lambdas(model, _fixtures().assign(elo_diff=[10000.0, -10000.0]))
    np.testing.assert_array_equal(scaler.mean_, frozen_mean)
    np.testing.assert_array_equal(scaler.var_, frozen_var)


def test_predict_lambdas_accepts_unknown_team_without_substitution_or_mutation():
    model = fit_poisson_model(_training_matches())
    fixtures = _fixtures()
    original = fixtures.copy(deep=True)

    result = predict_lambdas(model, fixtures)

    assert result["match_id"].tolist() == ["f1", "f2"]
    assert np.isfinite(result[["lambda_home", "lambda_away"]].to_numpy()).all()
    assert (result[["lambda_home", "lambda_away"]].to_numpy() > 0).all()
    encoder = model.pipeline.named_steps["features"].named_transformers_["teams"]
    assert "NEW" not in set(encoder.categories_[0])
    assert "NEW" not in set(encoder.categories_[1])
    unknown_team_block = encoder.transform(
        pd.DataFrame({"attacking_team_id": ["NEW"], "defending_team_id": ["OTHER"]})
    )
    assert unknown_team_block.nnz == 0
    assert_frame_equal(fixtures, original)


@pytest.mark.parametrize(
    ("home_rate", "away_rate"),
    [(1.2, 0.8), (1.5, 1.5), (1e-12, 2e-12), (20.0, 18.0)],
)
def test_score_grid_probabilities_are_valid_and_deterministic(home_rate, away_rate):
    first = score_grid_probabilities(home_rate, away_rate)
    second = score_grid_probabilities(home_rate, away_rate)
    assert first.shape == (3,)
    assert np.isfinite(first).all()
    assert ((0 <= first) & (first <= 1)).all()
    assert np.isclose(first.sum(), 1.0, rtol=0.0, atol=1e-12)
    np.testing.assert_array_equal(first, second)


def test_score_grid_uses_frozen_axis_and_away_draw_home_order():
    assert MAX_GOALS == 15
    home_favored = score_grid_probabilities(2.0, 0.5)
    assert home_favored[2] > home_favored[0]
    away_favored = score_grid_probabilities(0.5, 2.0)
    assert away_favored[0] > away_favored[2]


def test_score_grid_is_symmetric_for_equal_lambdas():
    probabilities = score_grid_probabilities(1.35, 1.35)
    assert probabilities[0] == pytest.approx(probabilities[2], rel=0.0, abs=1e-15)


@pytest.mark.parametrize("invalid", [0.0, -1.0, np.nan, np.inf, -np.inf])
def test_score_grid_rejects_invalid_lambda(invalid):
    with pytest.raises(ValueError, match="finite and strictly positive"):
        score_grid_probabilities(invalid, 1.0)


@pytest.mark.parametrize("invalid", [0.0, -0.1])
def test_predict_lambdas_rejects_nonpositive_model_output(monkeypatch, invalid):
    model = fit_poisson_model(_training_matches())
    monkeypatch.setattr(model.pipeline, "predict", lambda _features: np.array([invalid, 1.0]))
    with pytest.raises(ValueError, match="finite and strictly positive"):
        predict_lambdas(model, _fixtures().iloc[:1])


def test_predict_proba_end_to_end_preserves_rows_and_uses_plain_argmax():
    model = fit_poisson_model(_training_matches())
    fixtures = _fixtures()

    result = predict_proba(model, fixtures)

    assert tuple(result.columns) == PROBABILITY_COLUMNS
    assert len(result) == len(fixtures)
    assert result["match_id"].tolist() == fixtures["match_id"].tolist()
    probabilities = result[["p_away", "p_draw", "p_home"]].to_numpy()
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)
    np.testing.assert_array_equal(result["predicted_class"], probabilities.argmax(axis=1))
    assert "home_score" not in fixtures and "away_score" not in fixtures and "result" not in fixtures


def test_predict_proba_is_deterministic_on_synthetic_data():
    fixtures = _fixtures()
    first = predict_proba(fit_poisson_model(_training_matches()), fixtures)
    second = predict_proba(fit_poisson_model(_training_matches()), fixtures)
    assert_frame_equal(first, second)


def test_plain_argmax_tie_uses_first_index(monkeypatch):
    model = fit_poisson_model(_training_matches())
    monkeypatch.setattr(
        "src.modeling.architecture_poisson.score_grid_probabilities",
        lambda _home, _away: np.array([0.4, 0.4, 0.2]),
    )
    result = predict_proba(model, _fixtures().iloc[:1])
    assert result.loc[0, "predicted_class"] == 0


def test_fixture_validation_rejects_duplicate_match_id_and_invalid_identity():
    model = fit_poisson_model(_training_matches())
    duplicate = pd.concat([_fixtures().iloc[[0]], _fixtures().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="match_id must be unique"):
        predict_lambdas(model, duplicate)
    with pytest.raises(ValueError, match="nonmissing and nonblank"):
        predict_lambdas(model, _fixtures().assign(away_team_id=""))


def test_feature_contract_contains_no_additional_model_inputs():
    assert FEATURE_COLUMNS == (
        "attacking_team_id",
        "defending_team_id",
        "is_home",
        "attacker_elo_diff",
    )
