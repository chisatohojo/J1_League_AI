"""Synthetic matchup ablation checks; never load or evaluate real held-out data."""

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import logistic_matchup_ablation as ablation
from src.modeling.logistic_form import FormLogisticMetrics


H2H_COLUMNS = (
    "h2h_last5_matches", "h2h_last5_points_diff", "h2h_last5_goal_diff",
)
STADIUM_COLUMNS = (
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
)
EXPECTED_SETS = {
    "elo_only": ("elo_diff",),
    "elo_h2h": ("elo_diff", *H2H_COLUMNS),
    "elo_stadium": ("elo_diff", *STADIUM_COLUMNS),
    "elo_h2h_stadium": ("elo_diff", *H2H_COLUMNS, *STADIUM_COLUMNS),
}


@pytest.fixture(scope="module")
def dataset():
    rows = []
    for season in range(2015, 2027):
        for result in range(3):
            row = dict.fromkeys(DATASET_COLUMNS, np.nan)
            row.update(
                match_id=f"synthetic-{season}-{result}",
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
                h2h_last5_matches=(season + result) % 6,
                h2h_last5_points_diff=season % 7 - 2 * result,
                h2h_last5_goal_diff=3 * result - season % 5,
                home_stadium_last5_matches=(season + 2 * result) % 6,
                home_stadium_last5_points=(season + 3 * result) % 16,
                home_stadium_last5_goal_diff=season % 9 - 3 * result,
                away_stadium_last5_matches=(season + 3 * result) % 6,
                away_stadium_last5_points=(season + result) % 13,
                away_stadium_last5_goal_diff=2 * result - season % 7,
            )
            if season >= 2025:
                # These synthetic future rows must never reach either model operation.
                row.update(dict.fromkeys(("elo_diff", *MATCHUP_CONTEXT_COLUMNS), np.nan))
                row["result"] = 99
            rows.append(row)
    frame = pd.DataFrame(rows, columns=[*DATASET_COLUMNS, *MATCHUP_CONTEXT_COLUMNS])
    frame.index = pd.Index([9, 2, 9] * 12, name="source_index")
    return frame


@pytest.fixture(scope="module")
def observed(dataset):
    before = dataset.copy(deep=True)
    fits, predictions, split_inputs, accesses = [], [], [], []
    original_split = ablation.split_training_dataset
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

    def fit(model, frame, target, **kwargs):
        fits.append((model, frame.copy(deep=True), target.copy(deep=True)))
        return original_fit(model, frame, target, **kwargs)

    def predict(model, frame, **kwargs):
        probabilities = original_predict(model, frame, **kwargs)
        predictions.append((model, frame.copy(deep=True), probabilities.copy()))
        return probabilities

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ablation, "split_training_dataset", split)
        patch.setattr(Pipeline, "fit", fit)
        patch.setattr(Pipeline, "predict_proba", predict)
        metrics = ablation.run_logistic_matchup_ablation(dataset)
    return dict(
        before=before, fits=fits, predictions=predictions, metrics=metrics,
        split_inputs=split_inputs, accesses=accesses,
    )


def test_exact_feature_sets(observed):
    assert ablation.FEATURE_SETS == EXPECTED_SETS
    assert list(observed["metrics"]) == list(EXPECTED_SETS)
    for (_, frame, _), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert tuple(frame.columns) == columns


def test_feature_counts_are_one_four_seven_ten(observed):
    assert [frame.shape[1] for _, frame, _ in observed["fits"]] == [1, 4, 7, 10]
    assert [frame.shape[1] for _, frame, _ in observed["predictions"]] == [1, 4, 7, 10]


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


def test_each_feature_set_has_an_independent_pipeline(observed):
    models = [model for model, _, _ in observed["fits"]]
    assert len({id(model) for model in models}) == 4
    for position in (0, 1):
        assert len({id(model.steps[position][1]) for model in models}) == 4


def test_fit_uses_train_features_and_targets_only(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    for (_, features, target), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, train.loc[:, list(columns)])
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
    ablation.run_logistic_matchup_ablation(changed)
    for model, (original, _, _) in zip(fitted, observed["fits"], strict=True):
        np.testing.assert_array_equal(model.steps[1][1].coef_, original.steps[1][1].coef_)
        np.testing.assert_array_equal(model.steps[1][1].intercept_, original.steps[1][1].intercept_)


def test_only_validation_is_evaluated(dataset, observed):
    validation = dataset.loc[dataset["season"].eq(2024)]
    assert len(observed["predictions"]) == 4
    for (_, features, _), columns in zip(observed["predictions"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, validation.loc[:, list(columns)])


def test_test_partition_not_accessed(dataset, observed):
    assert "test" not in observed["accesses"]
    assert dataset.loc[dataset["season"].eq(2025), "result"].eq(99).all()


def test_reserved_partition_not_accessed(dataset, observed):
    assert "reserved" not in observed["accesses"]
    assert dataset.loc[dataset["season"].eq(2026), "result"].eq(99).all()


def test_split_receives_only_existing_24_columns(dataset, observed):
    assert dataset.shape[1] == 33
    assert len(observed["split_inputs"]) == 1
    assert_frame_equal(observed["split_inputs"][0], dataset.loc[:, list(DATASET_COLUMNS)])


def test_match_id_mapping_preserves_duplicate_indices_and_row_order(dataset, observed):
    assert not dataset.index.is_unique
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    validation = dataset.loc[dataset["season"].eq(2024)]
    assert_frame_equal(observed["fits"][-1][1], train.loc[:, list(EXPECTED_SETS["elo_h2h_stadium"])])
    assert_frame_equal(observed["predictions"][-1][1], validation.loc[:, list(EXPECTED_SETS["elo_h2h_stadium"])])
    assert len(observed["fits"][-1][1]) == 27
    assert len(observed["predictions"][-1][1]) == 3


def test_precomputed_elo_is_used_without_recalculation(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    assert not train["elo_diff"].eq(train["home_elo"] - train["away_elo"]).all()
    for _, features, _ in observed["fits"]:
        assert_series_equal(features["elo_diff"], train["elo_diff"])


def test_unused_ordinary_form_columns_can_be_missing(dataset, observed):
    ordinary_form = [column for column in DATASET_COLUMNS if "last5" in column]
    assert dataset.loc[:, ordinary_form].isna().all().all()
    for _, features, _ in [*observed["fits"], *observed["predictions"]]:
        assert np.isfinite(features.to_numpy()).all()
        assert not set(ordinary_form).intersection(features.columns)


def test_class_order(observed):
    for model, _, _ in observed["fits"]:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])


def test_incomplete_class_order_is_rejected(dataset):
    missing_draws = dataset.loc[~(dataset["season"].le(2023) & dataset["result"].eq(1))]
    with pytest.raises(ValueError, match="model.classes_"):
        ablation.run_logistic_matchup_ablation(missing_draws)


def test_probabilities_have_three_columns(observed):
    for _, features, probabilities in observed["predictions"]:
        assert probabilities.shape == (len(features), 3)


def test_probabilities_are_finite_and_sum_to_one(observed):
    for _, _, probabilities in observed["predictions"]:
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_accuracy_uses_validation_targets(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"]
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        assert np.isfinite(metrics.accuracy) and 0 <= metrics.accuracy <= 1
        assert metrics.accuracy == pytest.approx(accuracy_score(target, probabilities.argmax(axis=1)))


def test_log_loss_uses_validation_probabilities(dataset, observed):
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
        assert np.isfinite(metrics.brier_score) and 0 <= metrics.brier_score <= 2
        assert metrics.brier_score == pytest.approx(expected)


def test_return_contains_only_numeric_metrics_for_all_four_models(observed):
    assert set(observed["metrics"]) == set(EXPECTED_SETS)
    for metrics in observed["metrics"].values():
        assert isinstance(metrics, FormLogisticMetrics)
        values = asdict(metrics)
        assert set(values) == {"accuracy", "log_loss", "brier_score"}
        assert all(isinstance(value, float) and np.isfinite(value) for value in values.values())


def test_input_is_unchanged(dataset, observed):
    assert_frame_equal(dataset, observed["before"])


def test_same_input_produces_same_metrics(dataset, observed):
    assert ablation.run_logistic_matchup_ablation(dataset) == observed["metrics"]
