"""Synthetic checks for the train-only, three-feature form candidate."""

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import logistic_form
from src.modeling.time_split import split_training_dataset


@pytest.fixture(scope="module")
def dataset():
    rows = []
    seasons = list(range(2015, 2024)) + [2024, 2024, 2024, 2025, 2026]
    for i, season in enumerate(seasons):
        row = dict.fromkeys(DATASET_COLUMNS, np.nan)
        row.update(
            match_id=f"synthetic-{i}",
            match_date=f"{season}-07-{i + 1:02d}",
            season=season,
            competition="J1",
            home_team="Home",
            away_team="Away",
            home_team_id="home",
            away_team_id="away",
            elo_diff=float((i % 3 - 1) * 90 + i),
            home_last5_points=float(i % 6 + 2),
            away_last5_points=float((i + 3) % 5),
            home_last5_goals_for=float(i % 4 + 3),
            home_last5_goals_against=float(i % 3),
            away_last5_goals_for=float((i + 1) % 5),
            away_last5_goals_against=float((i + 2) % 4),
            result=i % 3,
        )
        if season == 2024:
            row["elo_diff"] += 1000
        if season > 2024:
            # Future feature/target values cannot be used for fitting/evaluation.
            row["elo_diff"] = np.nan
            row["home_last5_points"] = np.nan
            row["home_last5_goals_for"] = np.nan
            row["result"] = 99
        rows.append(row)
    return pd.DataFrame(rows, columns=DATASET_COLUMNS, index=range(100, 128, 2))


@pytest.fixture(scope="module")
def result(dataset):
    return logistic_form.run_logistic_form(dataset)


@pytest.fixture(scope="module")
def validation_probabilities(dataset, result):
    validation = dataset.loc[dataset["season"].eq(2024)]
    return result.model.predict_proba(logistic_form.build_feature_frame(validation))


@pytest.fixture
def asymmetric_matches():
    return pd.DataFrame(
        {
            "elo_diff": [40.0, -12.0],
            "home_last5_points": [13, 2],
            "away_last5_points": [4, 9],
            "home_last5_goals_for": [12, 2],
            "home_last5_goals_against": [3, 8],
            "away_last5_goals_for": [5, 9],
            "away_last5_goals_against": [7, 1],
        },
        index=[8, 3],
    )


def test_uses_only_the_three_requested_features(dataset, result):
    expected = ("elo_diff", "last5_points_diff", "last5_goal_diff")
    assert logistic_form.FEATURE_COLUMNS == expected
    features = logistic_form.build_feature_frame(dataset)
    assert tuple(features.columns) == expected
    assert tuple(result.model.feature_names_in_) == expected
    pd.testing.assert_series_equal(features["elo_diff"], dataset["elo_diff"])


def test_last5_points_difference(asymmetric_matches):
    features = logistic_form.build_feature_frame(asymmetric_matches)
    assert features["last5_points_diff"].tolist() == [9, -7]
    pd.testing.assert_index_equal(features.index, asymmetric_matches.index)


def test_last5_goal_difference(asymmetric_matches):
    features = logistic_form.build_feature_frame(asymmetric_matches)
    assert features["last5_goal_diff"].tolist() == [11, -14]


def test_pipeline_and_fixed_settings(result):
    model = result.model
    assert isinstance(model, Pipeline)
    assert [name for name, _ in model.steps] == ["scaler", "logistic"]
    assert isinstance(model.named_steps["scaler"], StandardScaler)
    logistic = model.named_steps["logistic"]
    assert isinstance(logistic, LogisticRegression)
    assert (logistic.solver, logistic.max_iter, logistic.random_state) == ("lbfgs", 1000, 0)


def test_fit_uses_only_train_and_predicts_only_validation(dataset, monkeypatch):
    fits, predictions = [], []
    original_fit = Pipeline.fit
    original_predict_proba = Pipeline.predict_proba

    def fit(model, features, target, **kwargs):
        fits.append((features.copy(deep=True), target.copy(deep=True)))
        return original_fit(model, features, target, **kwargs)

    def predict_proba(model, features, **kwargs):
        predictions.append(features.copy(deep=True))
        return original_predict_proba(model, features, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", fit)
    monkeypatch.setattr(Pipeline, "predict_proba", predict_proba)
    result = logistic_form.run_logistic_form(dataset)
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    validation = dataset.loc[dataset["season"].eq(2024)]
    train_features = logistic_form.build_feature_frame(train)
    assert len(fits) == len(predictions) == 1
    pd.testing.assert_frame_equal(fits[0][0], train_features)
    pd.testing.assert_series_equal(fits[0][1], train["result"])
    pd.testing.assert_frame_equal(
        predictions[0], logistic_form.build_feature_frame(validation)
    )
    np.testing.assert_allclose(result.model.named_steps["scaler"].mean_, train_features.mean())


def test_validation_targets_do_not_affect_fit(dataset, result):
    changed = dataset.copy(deep=True)
    validation = changed["season"].eq(2024)
    changed.loc[validation, "result"] = (changed.loc[validation, "result"] + 1) % 3
    other = logistic_form.run_logistic_form(changed)
    np.testing.assert_array_equal(
        result.model.named_steps["logistic"].coef_, other.model.named_steps["logistic"].coef_
    )
    np.testing.assert_array_equal(
        result.model.named_steps["logistic"].intercept_,
        other.model.named_steps["logistic"].intercept_,
    )


@pytest.mark.parametrize("forbidden", ["test", "reserved"])
def test_future_split_is_never_accessed(dataset, monkeypatch, forbidden):
    split = split_training_dataset(dataset)

    class GuardedSplit:
        train = split.train
        validation = split.validation

        def __getattr__(self, name):
            if name == forbidden:
                pytest.fail(f"Accessed forbidden {name} partition")
            return getattr(split, name)

    calls = []

    def guarded_split(actual_dataset):
        assert actual_dataset is dataset
        calls.append(actual_dataset)
        return GuardedSplit()

    monkeypatch.setattr(logistic_form, "split_training_dataset", guarded_split)
    logistic_form.run_logistic_form(dataset)
    assert len(calls) == 1


def test_class_order_is_away_draw_home(result):
    np.testing.assert_array_equal(result.model.classes_, [0, 1, 2])


def test_predict_proba_has_three_columns(validation_probabilities):
    assert validation_probabilities.shape == (3, 3)


def test_predict_proba_rows_sum_to_one(validation_probabilities):
    assert np.isfinite(validation_probabilities).all()
    assert ((validation_probabilities >= 0) & (validation_probabilities <= 1)).all()
    np.testing.assert_allclose(validation_probabilities.sum(axis=1), 1)


def test_validation_accuracy(dataset, result, validation_probabilities):
    accuracy = result.validation_metrics.accuracy
    assert 0 <= accuracy <= 1
    targets = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    assert accuracy == pytest.approx(np.mean(validation_probabilities.argmax(axis=1) == targets))


def test_validation_log_loss(dataset, result, validation_probabilities):
    loss = result.validation_metrics.log_loss
    assert np.isfinite(loss) and loss >= 0
    targets = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    expected = -np.log(validation_probabilities[np.arange(len(targets)), targets]).mean()
    assert loss == pytest.approx(expected)


def test_validation_brier_score_uses_sum_over_classes(dataset, result, validation_probabilities):
    score = result.validation_metrics.brier_score
    assert np.isfinite(score) and score >= 0
    targets = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    one_hot = np.eye(3)[targets]
    expected = np.square(validation_probabilities - one_hot).sum(axis=1).mean()
    assert score == pytest.approx(expected)


def test_input_dataframe_is_unchanged(dataset):
    original = dataset.copy(deep=True)
    features = logistic_form.build_feature_frame(dataset)
    features.iloc[0, 0] = -9999
    logistic_form.run_logistic_form(dataset)
    pd.testing.assert_frame_equal(dataset, original)


def test_same_input_produces_same_result(dataset, result, validation_probabilities):
    repeated = logistic_form.run_logistic_form(dataset)
    assert repeated.validation_metrics == result.validation_metrics
    validation = dataset.loc[dataset["season"].eq(2024)]
    np.testing.assert_array_equal(
        repeated.model.predict_proba(logistic_form.build_feature_frame(validation)),
        validation_probabilities,
    )
