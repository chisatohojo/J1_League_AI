"""Synthetic checks for venue ablation, without evaluating held-out seasons."""

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.features.venue_form import VENUE_FORM_COLUMNS
from src.modeling import logistic_venue_ablation as ablation


EXPECTED_SETS = {
    "elo_only": ("elo_diff",),
    "elo_venue_points": ("elo_diff", "venue_points_diff"),
    "elo_venue_goals": ("elo_diff", "venue_goal_diff"),
    "elo_venue_points_goals": ("elo_diff", "venue_points_diff", "venue_goal_diff"),
}


@pytest.fixture(scope="module")
def dataset():
    rows = []
    for season in range(2015, 2027):
        for result in range(3):
            row = dict.fromkeys(DATASET_COLUMNS, np.nan)
            row.update(
                match_id=f"{season}-{result}",
                match_date=pd.Timestamp(season, 3, result + 1),
                season=season,
                competition="J1",
                home_team="Home",
                away_team="Away",
                home_team_id="home",
                away_team_id="away",
                home_elo=1500.0,
                away_elo=1500.0,
                elo_diff=float((season - 2020) * 11 + (result - 1) * 43),
                result=result,
                home_last5_home_points=(season + 3 * result) % 16,
                away_last5_away_points=(season + result) % 13,
                home_last5_home_goal_diff=season % 7 - 3 * result,
                away_last5_away_goal_diff=2 * result - season % 5,
            )
            if season >= 2025:
                # Poison unused features/targets to expose accidental model use.
                row.update(dict.fromkeys(("elo_diff", *VENUE_FORM_COLUMNS), np.nan))
                row["result"] = 99
            rows.append(row)
    frame = pd.DataFrame(rows, columns=[*DATASET_COLUMNS, *VENUE_FORM_COLUMNS])
    # Repeated index labels across every partition must not duplicate rows.
    frame.index = pd.Index([9, 2, 9] * 12, name="source_index")
    return frame


@pytest.fixture(scope="module")
def observed(dataset):
    before = dataset.copy(deep=True)
    fits, predictions, feature_inputs, split_inputs, accesses = [], [], [], [], []
    original_split = ablation.split_training_dataset
    original_features = ablation.build_feature_frame
    original_fit, original_predict = Pipeline.fit, Pipeline.predict_proba

    def split(frame):
        split_inputs.append(frame.copy(deep=True))
        partitions = original_split(frame)

        class AllowedPartitions:
            train = partitions.train
            validation = partitions.validation

            @property
            def test(self):
                accesses.append("test")
                pytest.fail("Test partition must not be accessed")

            @property
            def reserved(self):
                accesses.append("reserved")
                pytest.fail("Reserved partition must not be accessed")

        return AllowedPartitions()

    def features(frame):
        feature_inputs.append(frame.copy(deep=True))
        return original_features(frame)

    def fit(model, frame, target, **kwargs):
        fits.append((model, frame.copy(deep=True), target.copy(deep=True)))
        return original_fit(model, frame, target, **kwargs)

    def predict(model, frame, **kwargs):
        probabilities = original_predict(model, frame, **kwargs)
        predictions.append((model, frame.copy(deep=True), probabilities.copy()))
        return probabilities

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ablation, "split_training_dataset", split)
        patch.setattr(ablation, "build_feature_frame", features)
        patch.setattr(Pipeline, "fit", fit)
        patch.setattr(Pipeline, "predict_proba", predict)
        metrics = ablation.run_logistic_venue_ablation(dataset)
    return dict(
        before=before, fits=fits, predictions=predictions, metrics=metrics,
        feature_inputs=feature_inputs, split_inputs=split_inputs, accesses=accesses,
    )


def test_exact_feature_sets(observed):
    assert ablation.FEATURE_SETS == EXPECTED_SETS
    assert list(observed["metrics"]) == list(EXPECTED_SETS)
    for (_, frame, _), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert tuple(frame.columns) == columns


def test_venue_points_diff():
    frame = pd.DataFrame({
        "elo_diff": [10, -20], "home_last5_home_points": [12, 1],
        "away_last5_away_points": [4, 7], "home_last5_home_goal_diff": [5, -3],
        "away_last5_away_goal_diff": [-2, 4],
    })
    assert ablation.build_feature_frame(frame)["venue_points_diff"].tolist() == [8, -6]


def test_venue_goal_diff():
    frame = pd.DataFrame({
        "elo_diff": [10, -20], "home_last5_home_points": [12, 1],
        "away_last5_away_points": [4, 7], "home_last5_home_goal_diff": [5, -3],
        "away_last5_away_goal_diff": [-2, 4],
    })
    assert ablation.build_feature_frame(frame)["venue_goal_diff"].tolist() == [7, -7]


def test_identical_pipeline_configuration(observed):
    assert len(observed["fits"]) == 4
    for model, features, _ in observed["fits"]:
        assert isinstance(model, Pipeline)
        assert [type(step) for _, step in model.steps] == [StandardScaler, LogisticRegression]
        classifier = model.steps[1][1]
        assert (classifier.solver, classifier.max_iter, classifier.random_state) == ("lbfgs", 1000, 0)
        scaler = model.steps[0][1]
        assert scaler.n_samples_seen_ == len(features)
        np.testing.assert_allclose(scaler.mean_, features.mean().to_numpy())


def test_fit_uses_train_only(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    expected = ablation.build_feature_frame(train)
    for (_, features, target), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, expected.loc[:, list(columns)])
        assert_series_equal(target, train["result"])


def test_validation_targets_do_not_affect_fit(dataset, observed, monkeypatch):
    changed = dataset.copy(deep=True)
    mask = changed["season"].eq(2024)
    changed.loc[mask, "result"] = (changed.loc[mask, "result"] + 1) % 3
    fitted = []
    original_fit = Pipeline.fit

    def fit(model, frame, target, **kwargs):
        fitted.append(model)
        return original_fit(model, frame, target, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", fit)
    ablation.run_logistic_venue_ablation(changed)
    for model, (original, _, _) in zip(fitted, observed["fits"], strict=True):
        np.testing.assert_array_equal(model.steps[1][1].coef_, original.steps[1][1].coef_)
        np.testing.assert_array_equal(model.steps[1][1].intercept_, original.steps[1][1].intercept_)


def test_only_validation_is_evaluated(dataset, observed):
    expected = ablation.build_feature_frame(dataset.loc[dataset["season"].eq(2024)])
    assert len(observed["predictions"]) == 4
    for (_, features, _), columns in zip(observed["predictions"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, expected.loc[:, list(columns)])


def test_test_partition_not_accessed(observed):
    assert "test" not in observed["accesses"]
    assert all(not frame["season"].eq(2025).any() for frame in observed["feature_inputs"])


def test_reserved_partition_not_accessed(observed):
    assert "reserved" not in observed["accesses"]
    assert all(not frame["season"].eq(2026).any() for frame in observed["feature_inputs"])


def test_split_receives_only_existing_24_columns(dataset, observed):
    assert len(observed["split_inputs"]) == 1
    assert_frame_equal(observed["split_inputs"][0], dataset.loc[:, list(DATASET_COLUMNS)])


def test_match_id_mapping_preserves_rows_with_duplicate_indices(dataset, observed):
    assert not dataset.index.is_unique
    assert len(observed["feature_inputs"]) == 2
    train, validation = observed["feature_inputs"]
    assert_frame_equal(train, dataset.loc[dataset["season"].between(2015, 2023)])
    assert_frame_equal(validation, dataset.loc[dataset["season"].eq(2024)])


def test_class_order(observed):
    for model, _, _ in observed["fits"]:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])


def test_incomplete_class_order_is_rejected(dataset):
    missing_draws = dataset.loc[~(dataset["season"].le(2023) & dataset["result"].eq(1))]
    with pytest.raises(ValueError, match="model.classes_"):
        ablation.run_logistic_venue_ablation(missing_draws)


def test_probabilities_have_three_columns(observed):
    for _, features, probabilities in observed["predictions"]:
        assert probabilities.shape == (len(features), 3)


def test_probabilities_sum_to_one(observed):
    for _, _, probabilities in observed["predictions"]:
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_accuracy(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"]
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        assert 0 <= metrics.accuracy <= 1
        assert metrics.accuracy == pytest.approx(accuracy_score(target, probabilities.argmax(axis=1)))


def test_log_loss(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"]
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        assert np.isfinite(metrics.log_loss) and metrics.log_loss >= 0
        assert metrics.log_loss == pytest.approx(log_loss(target, probabilities, labels=[0, 1, 2]))


def test_brier_score_sums_classes_and_averages_matches(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = sum(
            sum((probability - int(label == actual)) ** 2 for label, probability in enumerate(row))
            for actual, row in zip(target, probabilities, strict=True)
        ) / len(target)
        assert np.isfinite(metrics.brier_score) and metrics.brier_score >= 0
        assert metrics.brier_score == pytest.approx(expected)


def test_input_is_unchanged(dataset, observed):
    assert_frame_equal(dataset, observed["before"])
    features = ablation.build_feature_frame(dataset.iloc[:3])
    features.iloc[0, 0] = -9999
    assert_frame_equal(dataset, observed["before"])


def test_same_input_produces_same_metrics(dataset, observed):
    assert ablation.run_logistic_venue_ablation(dataset) == observed["metrics"]
