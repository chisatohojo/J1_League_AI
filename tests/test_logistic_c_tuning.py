"""Fixed-C checks using only synthetic 2015-2024 matches."""

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import logistic_c_tuning as tuning
from src.modeling.logistic_final_ablation import CURRENT_BEST_COLUMNS
from src.modeling.logistic_form import FormLogisticMetrics


EXPECTED_FEATURES = (
    "elo_diff",
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
    "home_days_since_last_match", "away_days_since_last_match",
    "home_has_previous_match", "away_has_previous_match",
)
EXPECTED_C = (0.1, 0.3, 1.0, 3.0, 10.0)


@pytest.fixture(scope="module")
def dataset():
    columns = (*DATASET_COLUMNS, *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS, *ELO_MOMENTUM_COLUMNS)
    rows = []
    for season in range(2015, 2025):
        for match, result in enumerate((2, 0, 1, 1, 2, 0)):
            position = len(rows)
            row = dict.fromkeys(columns, np.nan)
            row.update({
                column: float((position * (number + 3)) % 37 - 18 + number / 10)
                for number, column in enumerate(EXPECTED_FEATURES)
            })
            row.update(
                match_id=f"synthetic-{season}-{match}",
                match_date=pd.Timestamp(season, 3, match + 1),
                season=season,
                competition="J1",
                home_team="Home",
                away_team="Away",
                home_team_id="home",
                away_team_id="away",
                home_elo=1500.0,
                away_elo=1500.0,
                elo_diff=(season - 2020) * 7 + match * 11 + 0.25,
                home_days_since_last_match=20.0 + position * 3,
                away_days_since_last_match=35.0 + position * 2,
                home_has_previous_match=match % 2,
                away_has_previous_match=(match // 2) % 2,
                result=result,
            )
            rows.append(row)
    frame = pd.DataFrame(rows, columns=columns)
    frame.index = pd.Index([11, 3, 11, 4, 0, 3] * 10, name="source_index")
    return frame


@pytest.fixture(scope="module")
def observed(dataset):
    before = dataset.copy(deep=True)
    fits, scaler_fits, predictions, constructors, split_inputs, accesses, loss_labels = [], [], [], [], [], [], []
    original_split = tuning.split_training_dataset
    original_fit, original_predict = Pipeline.fit, Pipeline.predict_proba
    original_scaler_fit, original_loss = StandardScaler.fit, tuning.log_loss

    def split(frame):
        split_inputs.append(frame.copy(deep=True))
        partitions = original_split(frame)

        class AllowedPartitions:
            train = partitions.train.reset_index(drop=True)
            validation = partitions.validation.reset_index(drop=True)

            @property
            def test(self):
                accesses.append("test")
                pytest.fail("Test partition must not be accessed")

            @property
            def reserved(self):
                accesses.append("reserved")
                pytest.fail("Reserved partition must not be accessed")

        return AllowedPartitions()

    def classifier(*args, **kwargs):
        constructors.append((args, kwargs.copy()))
        return LogisticRegression(*args, **kwargs)

    def fit(model, frame, target, **kwargs):
        fits.append((model, frame.copy(deep=True), target.copy(deep=True)))
        return original_fit(model, frame, target, **kwargs)

    def scaler_fit(scaler, frame, target=None, **kwargs):
        scaler_fits.append((scaler, frame.copy(deep=True)))
        return original_scaler_fit(scaler, frame, target, **kwargs)

    def predict(model, frame, **kwargs):
        probabilities = original_predict(model, frame, **kwargs)
        predictions.append((model, frame.copy(deep=True), probabilities.copy()))
        return probabilities

    def loss(target, probabilities, **kwargs):
        loss_labels.append(kwargs.get("labels"))
        return original_loss(target, probabilities, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tuning, "split_training_dataset", split)
        patch.setattr(tuning, "LogisticRegression", classifier)
        patch.setattr(Pipeline, "fit", fit)
        patch.setattr(StandardScaler, "fit", scaler_fit)
        patch.setattr(Pipeline, "predict_proba", predict)
        patch.setattr(tuning, "log_loss", loss)
        metrics = tuning.run_logistic_c_tuning(dataset)
    return dict(
        before=before, fits=fits, scaler_fits=scaler_fits, predictions=predictions,
        constructors=constructors, split_inputs=split_inputs, accesses=accesses,
        loss_labels=loss_labels, metrics=metrics,
    )


def test_exact_eleven_feature_composition_reuses_the_existing_best():
    assert tuning.FEATURE_COLUMNS == EXPECTED_FEATURES == CURRENT_BEST_COLUMNS
    assert len(tuning.FEATURE_COLUMNS) == 11


def test_only_five_fixed_c_values_are_evaluated(observed):
    assert tuning.C_VALUES == EXPECTED_C
    assert tuple(observed["metrics"]) == EXPECTED_C
    assert len(observed["fits"]) == len(observed["predictions"]) == 5
    assert tuple(model.named_steps["logistic"].C for model, _, _ in observed["fits"]) == EXPECTED_C


def test_exact_constructor_arguments_without_class_weights(observed):
    assert len(observed["constructors"]) == 5
    for (args, kwargs), c_value in zip(observed["constructors"], EXPECTED_C, strict=True):
        assert args == ()
        assert kwargs == dict(penalty="l2", C=c_value, solver="lbfgs", max_iter=1000, random_state=0)


def test_five_independent_pipelines_have_identical_settings_except_c(observed):
    models = [model for model, _, _ in observed["fits"]]
    assert len({id(model) for model in models}) == 5
    for model in models:
        assert isinstance(model, Pipeline)
        assert [name for name, _ in model.steps] == ["scaler", "logistic"]
        assert [type(step) for _, step in model.steps] == [StandardScaler, LogisticRegression]
        assert model.named_steps["scaler"].get_params() == models[0].named_steps["scaler"].get_params()
        parameters = model.named_steps["logistic"].get_params()
        baseline = models[0].named_steps["logistic"].get_params()
        parameters.pop("C")
        baseline.pop("C")
        assert parameters == baseline
        assert parameters["class_weight"] is None
    for step in ("scaler", "logistic"):
        assert len({id(model.named_steps[step]) for model in models}) == 5


@pytest.mark.parametrize("parameter, expected", [
    ("penalty", "l2"), ("solver", "lbfgs"), ("max_iter", 1000), ("random_state", 0),
])
def test_fixed_logistic_parameters(observed, parameter, expected):
    for model, _, _ in observed["fits"]:
        assert model.named_steps["logistic"].get_params()[parameter] == expected


def test_only_train_features_and_targets_are_fitted(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    for _, features, target in observed["fits"]:
        assert_frame_equal(features, train.loc[:, list(EXPECTED_FEATURES)])
        assert_series_equal(target, train["result"])


def test_scalers_fit_once_on_raw_train_values_with_train_only_statistics(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023), list(EXPECTED_FEATURES)]
    assert len(observed["scaler_fits"]) == 5
    for (scaler, frame), (model, _, _) in zip(observed["scaler_fits"], observed["fits"], strict=True):
        assert scaler is model.named_steps["scaler"]
        assert_frame_equal(frame, train)
        assert scaler.n_samples_seen_ == len(train)
        np.testing.assert_allclose(scaler.mean_, train.mean().to_numpy())
        np.testing.assert_allclose(scaler.var_, train.var(ddof=0).to_numpy())
        assert not np.allclose(scaler.mean_, dataset.loc[:, list(EXPECTED_FEATURES)].mean().to_numpy())


def test_validation_values_and_targets_do_not_affect_fitted_models(dataset, observed, monkeypatch):
    changed = dataset.copy(deep=True)
    mask = changed["season"].eq(2024)
    changed.loc[mask, "result"] = (changed.loc[mask, "result"] + 1) % 3
    changed.loc[mask, "elo_diff"] += 500
    fitted = []
    original_fit = Pipeline.fit

    def fit(model, frame, target, **kwargs):
        fitted.append(model)
        return original_fit(model, frame, target, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", fit)
    tuning.run_logistic_c_tuning(changed)
    for model, (original, _, _) in zip(fitted, observed["fits"], strict=True):
        for attribute in ("coef_", "intercept_"):
            np.testing.assert_array_equal(
                getattr(model.named_steps["logistic"], attribute),
                getattr(original.named_steps["logistic"], attribute),
            )
        np.testing.assert_array_equal(model.named_steps["scaler"].mean_, original.named_steps["scaler"].mean_)


def test_predictions_use_only_validation_features(dataset, observed):
    validation = dataset.loc[dataset["season"].eq(2024), list(EXPECTED_FEATURES)]
    for _, features, _ in observed["predictions"]:
        assert_frame_equal(features, validation)


def test_test_partition_is_not_accessed(observed):
    assert "test" not in observed["accesses"]


def test_reserved_partition_is_not_accessed(observed):
    assert "reserved" not in observed["accesses"]


def test_only_24_columns_are_passed_to_the_existing_splitter(dataset, observed):
    assert dataset.shape[1] == 43
    assert dataset["season"].between(2015, 2024).all()
    assert len(observed["split_inputs"]) == 1
    assert len(DATASET_COLUMNS) == 24
    assert_frame_equal(observed["split_inputs"][0], dataset.loc[:, list(DATASET_COLUMNS)])


def test_match_id_mapping_preserves_rows_despite_duplicate_source_and_reset_split_indexes(dataset, observed):
    assert not dataset.index.is_unique
    assert dataset["match_id"].is_unique
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    validation = dataset.loc[dataset["season"].eq(2024)]
    assert len(train) == 54 and len(validation) == 6
    for _, features, target in observed["fits"]:
        assert_frame_equal(features, train.loc[:, list(EXPECTED_FEATURES)])
        assert_series_equal(target, train["result"])
    for _, features, _ in observed["predictions"]:
        assert_frame_equal(features, validation.loc[:, list(EXPECTED_FEATURES)])


def test_raw_features_are_unchanged_and_exclude_target_metadata_and_unused_features(dataset, observed):
    excluded = set(dataset.columns) - set(EXPECTED_FEATURES)
    assert not dataset["elo_diff"].eq(dataset["home_elo"] - dataset["away_elo"]).any()
    assert dataset[["home_days_since_last_match", "away_days_since_last_match"]].gt(14).all().all()
    for records, mask in (
        (observed["fits"], dataset["season"].between(2015, 2023)),
        (observed["predictions"], dataset["season"].eq(2024)),
    ):
        for _, features, _ in records:
            assert tuple(features.columns) == EXPECTED_FEATURES
            assert excluded.isdisjoint(features.columns)
            assert_frame_equal(features, dataset.loc[mask, list(EXPECTED_FEATURES)])


def test_class_order_is_away_draw_home(observed):
    for model, _, _ in observed["fits"]:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])


def test_missing_training_class_is_rejected_before_prediction(dataset, monkeypatch):
    missing_draws = dataset.loc[~(dataset["season"].le(2023) & dataset["result"].eq(1))]

    def forbidden_predict(*args, **kwargs):
        pytest.fail("A model with missing classes must not predict")

    monkeypatch.setattr(Pipeline, "predict_proba", forbidden_predict)
    with pytest.raises(ValueError, match="model.classes_"):
        tuning.run_logistic_c_tuning(missing_draws)


def test_probabilities_have_three_classes_and_sum_to_one(observed):
    for _, features, probabilities in observed["predictions"]:
        assert probabilities.shape == (len(features), 3)
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_accuracy_uses_validation_targets_and_is_in_range(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        assert np.isfinite(metrics.accuracy) and 0 <= metrics.accuracy <= 1
        assert metrics.accuracy == pytest.approx(np.mean(probabilities.argmax(axis=1) == target))


def test_log_loss_uses_validation_with_explicit_class_order_and_is_finite_nonnegative(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    assert observed["loss_labels"] == [[0, 1, 2]] * 5
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = -np.log(probabilities[np.arange(len(target)), target]).mean()
        assert np.isfinite(metrics.log_loss) and metrics.log_loss >= 0
        assert metrics.log_loss == pytest.approx(expected)


def test_brier_sums_class_errors_and_averages_validation_matches(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = sum(
            sum((probability - int(label == actual)) ** 2 for label, probability in enumerate(row))
            for actual, row in zip(target, probabilities, strict=True)
        ) / len(target)
        assert np.isfinite(metrics.brier_score) and 0 <= metrics.brier_score <= 2
        assert metrics.brier_score == pytest.approx(expected)


def test_results_contain_only_numeric_metrics_without_ranking_or_a_winner(observed):
    assert tuple(observed["metrics"]) == EXPECTED_C
    for metrics in observed["metrics"].values():
        assert isinstance(metrics, FormLogisticMetrics)
        values = asdict(metrics)
        assert set(values) == {"accuracy", "log_loss", "brier_score"}
        assert all(isinstance(value, float) and np.isfinite(value) for value in values.values())


@pytest.mark.parametrize("outcome", ["excellent", "poor"])
def test_validation_outcomes_never_add_or_remove_c_candidates(dataset, monkeypatch, outcome):
    fitted_c, predicted_c = [], []
    original_fit = Pipeline.fit
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()

    def fit(model, frame, labels, **kwargs):
        fitted_c.append(model.named_steps["logistic"].C)
        return original_fit(model, frame, labels, **kwargs)

    def predict(model, frame, **kwargs):
        predicted_c.append(model.named_steps["logistic"].C)
        assert len(frame) == len(target)
        probabilities = np.full((len(target), 3), 0.0001)
        predicted = target if outcome == "excellent" else (target + 1) % 3
        probabilities[np.arange(len(target)), predicted] = 0.9998
        return probabilities

    monkeypatch.setattr(Pipeline, "fit", fit)
    monkeypatch.setattr(Pipeline, "predict_proba", predict)
    metrics = tuning.run_logistic_c_tuning(dataset)
    assert tuple(fitted_c) == tuple(predicted_c) == tuple(metrics) == EXPECTED_C
    assert all(value.accuracy == (1.0 if outcome == "excellent" else 0.0) for value in metrics.values())


def test_input_dataframe_is_unchanged(dataset, observed):
    assert_frame_equal(dataset, observed["before"])


def test_same_input_produces_identical_metrics(dataset, observed):
    assert tuning.run_logistic_c_tuning(dataset) == observed["metrics"]
