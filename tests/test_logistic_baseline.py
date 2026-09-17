"""Small synthetic checks for the fixed Elo-only logistic baseline."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import logistic_baseline as baseline
from src.modeling.time_split import split_training_dataset


@pytest.fixture
def dataset():
    rows = []
    for season in (2015, 2023, 2024, 2025, 2026):
        for target, elo_diff in enumerate((-120.0, 0.0, 160.0)):
            row = dict.fromkeys(DATASET_COLUMNS, np.nan)
            row.update(
                match_id=f"{season}-{target}",
                match_date=f"{season}-03-{target + 1:02d}",
                season=season,
                elo_diff=elo_diff if season != 2026 else np.nan,
                result=target if season != 2026 else np.nan,
            )
            rows.append(row)
    # Unused columns and reserved feature/target values deliberately contain NaN.
    return pd.DataFrame(rows, columns=DATASET_COLUMNS)


@pytest.fixture
def result(dataset):
    return baseline.run_logistic_baseline(dataset)


def test_uses_only_elo_diff(result):
    assert baseline.FEATURE_COLUMNS == ("elo_diff",)
    assert result.model.n_features_in_ == 1
    assert result.model.feature_names_in_.tolist() == ["elo_diff"]


def test_fits_once_on_train_only(dataset, monkeypatch):
    calls = []
    original_fit = baseline.LogisticRegression.fit

    def fit(model, x, y, *args, **kwargs):
        calls.append((x.copy(deep=True), y.copy(deep=True)))
        return original_fit(model, x, y, *args, **kwargs)

    monkeypatch.setattr(baseline.LogisticRegression, "fit", fit)
    baseline.run_logistic_baseline(dataset)
    train = dataset.loc[dataset.season.between(2015, 2023)]
    assert len(calls) == 1
    pd.testing.assert_frame_equal(calls[0][0], train[["elo_diff"]])
    pd.testing.assert_series_equal(calls[0][1], train["result"])


def test_evaluation_targets_do_not_affect_fit(dataset, result):
    changed = dataset.copy(deep=True)
    evaluation = changed.season.isin((2024, 2025))
    changed.loc[evaluation, "result"] = (changed.loc[evaluation, "result"] + 1) % 3
    other = baseline.run_logistic_baseline(changed)
    np.testing.assert_array_equal(other.model.coef_, result.model.coef_)
    np.testing.assert_array_equal(other.model.intercept_, result.model.intercept_)


def test_reserved_is_never_accessed_and_only_validation_test_are_evaluated(dataset, monkeypatch):
    class GuardedSplit(SimpleNamespace):
        @property
        def reserved(self):
            raise AssertionError("The baseline must not access reserved data")

    split = split_training_dataset(dataset)
    monkeypatch.setattr(
        baseline, "split_training_dataset",
        lambda data: GuardedSplit(train=split.train, validation=split.validation, test=split.test),
    )
    calls = []
    original_predict = baseline.LogisticRegression.predict_proba

    def predict(model, x):
        calls.append(x.copy(deep=True))
        return original_predict(model, x)

    monkeypatch.setattr(baseline.LogisticRegression, "predict_proba", predict)
    baseline.run_logistic_baseline(dataset)
    assert len(calls) == 2
    pd.testing.assert_frame_equal(calls[0], split.validation[["elo_diff"]])
    pd.testing.assert_frame_equal(calls[1], split.test[["elo_diff"]])


def test_model_class_order(result):
    np.testing.assert_array_equal(result.model.classes_, [0, 1, 2])


def test_probability_shape(dataset, result):
    for season in (2024, 2025):
        x = dataset.loc[dataset.season.eq(season), ["elo_diff"]]
        assert result.model.predict_proba(x).shape == (len(x), 3)


def test_probability_sums(dataset, result):
    x = dataset.loc[dataset.season.isin((2024, 2025)), ["elo_diff"]]
    probabilities = result.model.predict_proba(x)
    assert np.isfinite(probabilities).all()
    assert ((0 <= probabilities) & (probabilities <= 1)).all()
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_accuracy_values(result):
    for metrics in (result.validation_metrics, result.test_metrics):
        assert 0 <= metrics.accuracy <= 1


def test_log_loss_values(result):
    for metrics in (result.validation_metrics, result.test_metrics):
        assert np.isfinite(metrics.log_loss)
        assert metrics.log_loss >= 0


def test_multiclass_brier_values(dataset, result):
    for season, metrics in ((2024, result.validation_metrics), (2025, result.test_metrics)):
        rows = dataset.loc[dataset.season.eq(season)]
        probabilities = result.model.predict_proba(rows[["elo_diff"]])
        expected = sum(
            sum((probability - int(label == target)) ** 2 for label, probability in enumerate(row))
            for target, row in zip(rows.result, probabilities, strict=True)
        ) / len(rows)
        assert np.isfinite(metrics.brier_score)
        assert metrics.brier_score >= 0
        assert metrics.brier_score == pytest.approx(expected)


def test_repeatable(dataset, result):
    other = baseline.run_logistic_baseline(dataset)
    assert other.validation_metrics == result.validation_metrics
    assert other.test_metrics == result.test_metrics
    np.testing.assert_array_equal(other.model.coef_, result.model.coef_)
    np.testing.assert_array_equal(other.model.intercept_, result.model.intercept_)


def test_input_is_unchanged(dataset):
    original = dataset.copy(deep=True)
    baseline.run_logistic_baseline(dataset)
    pd.testing.assert_frame_equal(dataset, original)


@pytest.mark.parametrize("classes", ([0, 1], [2, 1, 0]))
def test_rejects_invalid_class_order(dataset, monkeypatch, classes):
    original_fit = baseline.LogisticRegression.fit

    def fit(model, x, y, *args, **kwargs):
        original_fit(model, x, y, *args, **kwargs)
        model.classes_ = np.asarray(classes)
        return model

    monkeypatch.setattr(baseline.LogisticRegression, "fit", fit)
    with pytest.raises(ValueError):
        baseline.run_logistic_baseline(dataset)
