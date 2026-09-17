"""Synthetic checks for the fixed, validation-only Form ablation."""

from dataclasses import fields

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.modeling import logistic_ablation as ablation
from src.modeling.logistic_form import FormLogisticMetrics, build_feature_frame
from src.modeling.time_split import DATASET_COLUMNS, split_training_dataset


EXPECTED_FEATURE_SETS = {
    "elo_only": ("elo_diff",),
    "elo_points": ("elo_diff", "last5_points_diff"),
    "elo_goals": ("elo_diff", "last5_goal_diff"),
    "elo_points_goals": ("elo_diff", "last5_points_diff", "last5_goal_diff"),
}


@pytest.fixture
def dataset():
    records = []
    for season in range(2015, 2027):
        for match in range(6):
            row = dict.fromkeys(DATASET_COLUMNS, 0)
            row.update(
                match_id=f"{season}-{match}",
                match_date=pd.Timestamp(season, 1, match + 1),
                season=season,
                result=match % 3,
                elo_diff=35.0 * (match - 2) + season - 2015,
                home_last5_points=2 * match + 1,
                away_last5_points=8 - match,
                home_last5_goals_for=match + 3,
                home_last5_goals_against=match % 2 + 1,
                away_last5_goals_for=7 - match,
                away_last5_goals_against=match % 3 + 2,
            )
            if season == 2024:
                # Validation moments differ markedly from train moments.
                row["elo_diff"] += 500.0
                row["home_last5_points"] += 10
            elif season >= 2025:
                # These values would break fitting or evaluation if used.
                row["result"] = 99
                for column in (
                    "elo_diff", "home_last5_points", "away_last5_points",
                    "home_last5_goals_for", "home_last5_goals_against",
                    "away_last5_goals_for", "away_last5_goals_against",
                ):
                    row[column] = np.nan
            records.append(row)
    return pd.DataFrame(records, columns=DATASET_COLUMNS, index=range(100, 172))


@pytest.fixture
def observed_run(monkeypatch, dataset):
    fits = []
    predictions = []
    original_fit = Pipeline.fit
    original_predict_proba = Pipeline.predict_proba

    def fit(model, features, target, **kwargs):
        fitted = original_fit(model, features, target, **kwargs)
        fits.append((model, features.copy(deep=True), target.copy(deep=True)))
        return fitted

    def predict_proba(model, features, **kwargs):
        probabilities = original_predict_proba(model, features, **kwargs)
        predictions.append((model, features.copy(deep=True), probabilities.copy()))
        return probabilities

    monkeypatch.setattr(Pipeline, "fit", fit)
    monkeypatch.setattr(Pipeline, "predict_proba", predict_proba)
    metrics = ablation.run_logistic_ablation(dataset)
    return metrics, fits, predictions


def test_exact_feature_sets_and_numeric_results(observed_run):
    metrics, fits, predictions = observed_run
    assert ablation.FEATURE_SETS == EXPECTED_FEATURE_SETS
    assert list(metrics) == list(EXPECTED_FEATURE_SETS)
    assert len(fits) == len(predictions) == 4
    for (name, columns), (_, train, _), (_, validation, _) in zip(
        EXPECTED_FEATURE_SETS.items(), fits, predictions, strict=True
    ):
        assert tuple(train.columns) == tuple(validation.columns) == columns
        assert isinstance(metrics[name], FormLogisticMetrics)
        assert {field.name for field in fields(metrics[name])} == {
            "accuracy", "log_loss", "brier_score",
        }
        assert all(isinstance(getattr(metrics[name], field.name), float)
                   for field in fields(metrics[name]))


def test_identical_pipeline_configuration(observed_run):
    _, fits, _ = observed_run
    assert len({id(model) for model, _, _ in fits}) == 4
    classifier_parameters = []
    scaler_parameters = []
    for model, _, _ in fits:
        assert [name for name, _ in model.steps] == ["scaler", "logistic"]
        scaler = model.named_steps["scaler"]
        classifier = model.named_steps["logistic"]
        assert type(scaler) is StandardScaler
        assert type(classifier) is LogisticRegression
        assert classifier.solver == "lbfgs"
        assert classifier.max_iter == 1000
        assert classifier.random_state == 0
        classifier_parameters.append(classifier.get_params())
        scaler_parameters.append(scaler.get_params())
    assert all(params == classifier_parameters[0] for params in classifier_parameters)
    assert all(params == scaler_parameters[0] for params in scaler_parameters)


def test_fit_and_scaling_use_train_only(dataset, observed_run):
    _, fits, _ = observed_run
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    features = build_feature_frame(train)
    assert len(fits) == 4
    for columns, (model, fitted_features, fitted_target) in zip(
        EXPECTED_FEATURE_SETS.values(), fits, strict=True
    ):
        expected = features.loc[:, list(columns)]
        pd.testing.assert_frame_equal(fitted_features, expected)
        pd.testing.assert_series_equal(fitted_target, train["result"])
        scaler = model.named_steps["scaler"]
        assert scaler.n_samples_seen_ == len(train)
        np.testing.assert_allclose(scaler.mean_, expected.mean().to_numpy())
        np.testing.assert_allclose(scaler.var_, expected.var(ddof=0).to_numpy())


def test_only_validation_is_predicted_and_existing_features_are_reused(
    monkeypatch, dataset, observed_run
):
    _, fits, predictions = observed_run
    validation = dataset.loc[dataset["season"].eq(2024)]
    expected_features = build_feature_frame(validation)
    for columns, (fitted_model, _, _), (model, features, _) in zip(
        EXPECTED_FEATURE_SETS.values(), fits, predictions, strict=True
    ):
        assert model is fitted_model
        pd.testing.assert_frame_equal(features, expected_features.loc[:, list(columns)])

    assert ablation.build_feature_frame is build_feature_frame
    feature_inputs = []

    def observed_feature_builder(matches):
        feature_inputs.append(matches.copy(deep=True))
        return build_feature_frame(matches)

    monkeypatch.setattr(ablation, "build_feature_frame", observed_feature_builder)
    ablation.run_logistic_ablation(dataset)
    assert len(feature_inputs) == 2
    pd.testing.assert_frame_equal(
        feature_inputs[0], dataset.loc[dataset["season"].between(2015, 2023)]
    )
    pd.testing.assert_frame_equal(feature_inputs[1], validation)


@pytest.mark.parametrize("forbidden_partition", ["test", "reserved"])
def test_future_partition_is_never_accessed(monkeypatch, dataset, forbidden_partition):
    split = split_training_dataset(dataset)

    class GuardedSplit:
        train = split.train
        validation = split.validation

        def __getattr__(self, name):
            if name == forbidden_partition:
                raise AssertionError(f"Accessed forbidden partition: {name}")
            raise AssertionError(f"Unexpected split access: {name}")

    calls = []

    def guarded_split(source):
        assert source is dataset
        calls.append(source)
        return GuardedSplit()

    monkeypatch.setattr(ablation, "split_training_dataset", guarded_split)
    metrics = ablation.run_logistic_ablation(dataset)
    assert len(calls) == 1
    assert list(metrics) == list(EXPECTED_FEATURE_SETS)


def test_class_order_is_away_draw_home(observed_run):
    _, fits, _ = observed_run
    for model, _, _ in fits:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])


def test_predict_proba_has_three_columns(dataset, observed_run):
    _, _, predictions = observed_run
    for _, _, probabilities in predictions:
        assert probabilities.shape == (int(dataset["season"].eq(2024).sum()), 3)


def test_predict_proba_rows_sum_to_one(observed_run):
    _, _, predictions = observed_run
    for _, _, probabilities in predictions:
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_validation_accuracy_is_correct_and_bounded(dataset, observed_run):
    metrics, _, predictions = observed_run
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for name, (_, _, probabilities) in zip(metrics, predictions, strict=True):
        assert 0 <= metrics[name].accuracy <= 1
        assert metrics[name].accuracy == pytest.approx(
            np.mean(probabilities.argmax(axis=1) == target)
        )


def test_validation_log_loss_is_correct_finite_and_nonnegative(dataset, observed_run):
    metrics, _, predictions = observed_run
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for name, (_, _, probabilities) in zip(metrics, predictions, strict=True):
        score = metrics[name].log_loss
        assert np.isfinite(score) and score >= 0
        expected = -np.log(probabilities[np.arange(len(target)), target]).mean()
        assert score == pytest.approx(expected)


def test_validation_brier_is_mean_class_sum_finite_and_nonnegative(dataset, observed_run):
    metrics, _, predictions = observed_run
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for name, (_, _, probabilities) in zip(metrics, predictions, strict=True):
        score = metrics[name].brier_score
        assert np.isfinite(score) and score >= 0
        expected = sum(
            sum((row[class_id] - int(label == class_id)) ** 2 for class_id in range(3))
            for label, row in zip(target, probabilities, strict=True)
        ) / len(target)
        assert score == pytest.approx(expected)


def test_input_is_not_modified(dataset):
    before = dataset.copy(deep=True)
    ablation.run_logistic_ablation(dataset)
    pd.testing.assert_frame_equal(dataset, before)


def test_identical_input_produces_identical_results(dataset):
    first = ablation.run_logistic_ablation(dataset)
    second = ablation.run_logistic_ablation(dataset.copy(deep=True))
    assert first == second
