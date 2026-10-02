import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMClassifier
from pandas.testing import assert_frame_equal
from sklearn.pipeline import Pipeline

from src.features.form import add_form_features
from src.modeling.architecture_lightgbm import (
    CLASS_ORDER,
    FEATURE_COLUMNS,
    MODEL_VERSION,
    PROBABILITY_COLUMNS,
    STATE_COLUMNS,
    build_lightgbm_classifier,
    build_lightgbm_state_features,
    fit_lightgbm_model,
    predict_proba,
    validate_lightgbm_features,
)


FROZEN_PARAMETERS = {
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


def _matches() -> pd.DataFrame:
    home = ["A", "C", "A", "E", "A", "G", "A"]
    away = ["B", "A", "D", "A", "F", "A", "H"]
    home_score = [2, 0, 1, 2, 0, 1, 3]
    away_score = [0, 1, 1, 0, 2, 1, 0]
    return pd.DataFrame(
        {
            "match_id": [f"m{i}" for i in range(7)],
            "match_date": pd.to_datetime(
                ["2019-12-20", "2020-01-10", "2020-01-20", "2020-02-01",
                 "2020-02-10", "2020-02-20", "2020-03-01"]
            ),
            "home_team_id": home,
            "away_team_id": away,
            "home_score": home_score,
            "away_score": away_score,
            "result": [
                2 if h > a else 0 if h < a else 1
                for h, a in zip(home_score, away_score)
            ],
            "elo_diff": [10.0, -15.0, 3.0, 22.0, -8.0, 0.0, 31.0],
        }
    )


def _synthetic_training(rows: int = 180) -> pd.DataFrame:
    index = np.arange(rows)
    available_home = index % 6
    available_away = (index * 5 + 2) % 6
    return pd.DataFrame(
        {
            "match_id": [f"s{i:03d}" for i in index],
            "elo_diff": ((index * 37) % 401 - 200).astype(float),
            "home_last5_matches_available": available_home,
            "away_last5_matches_available": available_away,
            "home_last5_points": (index * 7) % 16,
            "away_last5_points": (index * 11 + 1) % 16,
            "home_last5_goals_for": (index * 3) % 18,
            "away_last5_goals_for": (index * 5 + 2) % 18,
            "home_last5_goals_against": (index * 7 + 1) % 18,
            "away_last5_goals_against": (index * 11 + 3) % 18,
            "result": index % 3,
        }
    )


def test_frozen_identity_and_exact_ordered_vector():
    assert MODEL_VERSION == "architecture_lightgbm_form_v1"
    assert CLASS_ORDER == (0, 1, 2)
    assert FEATURE_COLUMNS == (
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


def test_state_builder_reuses_form_semantics_availability_and_preserves_input():
    matches = _matches()
    original = matches.copy(deep=True)
    state = build_lightgbm_state_features(matches)
    form = add_form_features(matches)

    assert tuple(state.columns) == STATE_COLUMNS
    assert tuple(state.loc[:, list(FEATURE_COLUMNS)].columns) == FEATURE_COLUMNS
    assert not any(column.endswith(("_wins", "_draws", "_losses")) for column in FEATURE_COLUMNS)
    assert state["home_last5_matches_available"].tolist() == [0, 0, 2, 0, 4, 0, 5]
    assert state["away_last5_matches_available"].tolist() == [0, 1, 0, 3, 0, 5, 0]
    for side in ("home", "away"):
        expected = sum(form[f"{side}_last5_{outcome}"] for outcome in ("wins", "draws", "losses"))
        np.testing.assert_array_equal(state[f"{side}_last5_matches_available"], expected)
        assert state[f"{side}_last5_matches_available"].between(0, 5).all()
    assert state.loc[0, [column for column in FEATURE_COLUMNS if column != "elo_diff"]].eq(0).all()
    assert state.loc[1, "away_last5_matches_available"] == 1
    assert state.loc[1, "away_last5_points"] == 3
    assert state.loc[1, "away_last5_goals_for"] == 2
    assert state.loc[1, "away_last5_goals_against"] == 0
    assert state.loc[1, "away_last5_matches_available"] == 1  # Cross-year, no reset.
    assert state.loc[6, "home_last5_matches_available"] == 5
    assert state.loc[6, "home_last5_points"] == 5
    assert state.loc[6, "home_last5_goals_for"] == 3
    assert state.loc[6, "home_last5_goals_against"] == 6
    assert_frame_equal(matches, original)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda frame: frame.iloc[[1, 0]].reset_index(drop=True), "chronological order"),
        (lambda frame: frame.assign(match_id="same"), "match_id must be unique"),
        (lambda frame: pd.concat([frame, frame[["elo_diff"]]], axis=1), "Duplicate columns"),
        (lambda frame: frame.assign(home_team_id=" "), "nonmissing and nonblank"),
        (lambda frame: frame.assign(home_team_id=frame["away_team_id"]), "must differ"),
        (lambda frame: frame.assign(home_score=-1), "nonnegative integers"),
        (lambda frame: frame.assign(away_score=1.5), "nonnegative integers"),
        (lambda frame: frame.assign(result=2), "must agree"),
        (lambda frame: frame.assign(elo_diff=np.inf), "numeric and finite"),
    ],
)
def test_state_builder_rejects_invalid_schema_and_values(mutation, message):
    with pytest.raises(ValueError, match=message):
        build_lightgbm_state_features(mutation(_matches().iloc[:2].copy(deep=True)))


def test_state_builder_keeps_same_date_duplicate_team_protection():
    matches = _matches().iloc[:2].copy(deep=True)
    matches.loc[1, "match_date"] = matches.loc[0, "match_date"]
    with pytest.raises(ValueError, match="cannot appear twice"):
        build_lightgbm_state_features(matches)


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("elo_diff", np.nan, "numeric and finite"),
        ("elo_diff", np.inf, "numeric and finite"),
        ("elo_diff", "10", "numeric and finite"),
        ("home_last5_matches_available", 2.5, "integers from 0 through 5"),
        ("away_last5_matches_available", 6, "integers from 0 through 5"),
        ("home_last5_points", -1, "nonnegative"),
        ("away_last5_goals_for", -1, "nonnegative"),
        ("home_last5_goals_against", -1, "nonnegative"),
    ],
)
def test_feature_validator_rejects_invalid_state(column, value, message):
    frame = _synthetic_training(6).loc[:, list(FEATURE_COLUMNS)]
    if isinstance(value, str):
        frame[column] = frame[column].astype(object)
    elif isinstance(value, float) and not float(value).is_integer():
        frame[column] = frame[column].astype(float)
    frame.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        validate_lightgbm_features(frame)


def test_feature_validator_rejects_missing_and_duplicate_columns():
    frame = _synthetic_training(6).loc[:, list(FEATURE_COLUMNS)]
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_lightgbm_features(frame.drop(columns="elo_diff"))
    with pytest.raises(ValueError, match="Duplicate columns"):
        validate_lightgbm_features(pd.concat([frame, frame[["elo_diff"]]], axis=1))


def test_classifier_has_exact_frozen_contract_and_is_fresh_direct_estimator():
    first = build_lightgbm_classifier()
    second = build_lightgbm_classifier()

    assert isinstance(first, LGBMClassifier)
    assert not isinstance(first, Pipeline)
    assert first is not second
    actual = first.get_params(deep=False)
    for name, expected in FROZEN_PARAMETERS.items():
        assert actual[name] == expected
    assert "early_stopping_round" not in first.get_params(deep=False)


def test_fit_is_deterministic_has_exact_classes_width_and_preserves_input():
    training = _synthetic_training()
    original = training.copy(deep=True)
    first = fit_lightgbm_model(training)
    second = fit_lightgbm_model(training)
    fixtures = training.iloc[:20].drop(columns="result")

    assert np.array_equal(first.classifier.classes_, np.asarray(CLASS_ORDER))
    assert first.classifier.n_features_in_ == len(FEATURE_COLUMNS)
    assert first.classifier.booster_.num_feature() == len(FEATURE_COLUMNS)
    np.testing.assert_array_equal(
        first.classifier.predict_proba(fixtures.loc[:, list(FEATURE_COLUMNS)]),
        second.classifier.predict_proba(fixtures.loc[:, list(FEATURE_COLUMNS)]),
    )
    assert_frame_equal(training, original)


def test_prediction_schema_order_probabilities_argmax_and_no_target_requirement():
    training = _synthetic_training()
    model = fit_lightgbm_model(training)
    fixtures = training.iloc[[8, 2, 17]].drop(columns="result").reset_index(drop=True)
    original = fixtures.copy(deep=True)

    result = predict_proba(model, fixtures)

    assert tuple(result.columns) == PROBABILITY_COLUMNS
    assert result["match_id"].tolist() == fixtures["match_id"].tolist()
    probabilities = result.loc[:, ["p_away", "p_draw", "p_home"]].to_numpy()
    assert np.isfinite(probabilities).all()
    assert ((probabilities >= 0) & (probabilities <= 1)).all()
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=0.0, atol=1e-12)
    np.testing.assert_array_equal(result["predicted_class"], np.asarray(CLASS_ORDER)[probabilities.argmax(axis=1)])
    assert_frame_equal(fixtures, original)


def test_prediction_rejects_invalid_state_and_duplicate_match_id():
    training = _synthetic_training()
    model = fit_lightgbm_model(training)
    fixtures = training.iloc[:2].drop(columns="result").copy(deep=True)
    fixtures.loc[0, "home_last5_points"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        predict_proba(model, fixtures)

    duplicates = training.iloc[[0, 0]].drop(columns="result").reset_index(drop=True)
    with pytest.raises(ValueError, match="match_id must be unique"):
        predict_proba(model, duplicates)


def test_prediction_rejects_class_order_mismatch(monkeypatch):
    model = fit_lightgbm_model(_synthetic_training())
    monkeypatch.setattr(model.classifier, "_classes", np.array([0, 2, 1]))
    with pytest.raises(ValueError, match="Expected classes_"):
        predict_proba(model, _synthetic_training(3).drop(columns="result"))


@pytest.mark.parametrize(
    ("probabilities", "message"),
    [
        (np.array([[0.2, 0.3, 0.5], [0.1, 0.3, 0.6]]), "probability shape"),
        (np.array([[np.nan, 0.3, 0.7]]), "invalid probabilities"),
        (np.array([[-0.1, 0.4, 0.7]]), "invalid probabilities"),
        (np.array([[0.2, 0.3, 0.4]]), "invalid probabilities"),
    ],
)
def test_prediction_rejects_invalid_model_probabilities(monkeypatch, probabilities, message):
    model = fit_lightgbm_model(_synthetic_training())
    fixtures = _synthetic_training(1).drop(columns="result")
    monkeypatch.setattr(model.classifier, "predict_proba", lambda _features: probabilities)
    with pytest.raises(ValueError, match=message):
        predict_proba(model, fixtures)


def test_plain_argmax_tie_uses_first_class(monkeypatch):
    model = fit_lightgbm_model(_synthetic_training())
    fixtures = _synthetic_training(1).drop(columns="result")
    monkeypatch.setattr(
        model.classifier,
        "predict_proba",
        lambda _features: np.array([[0.4, 0.4, 0.2]]),
    )
    result = predict_proba(model, fixtures)
    assert result.loc[0, "predicted_class"] == 0
