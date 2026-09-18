"""Synthetic 2015-2024 checks; never load real data or held-out seasons."""

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import logistic_final_ablation as ablation
from src.modeling.logistic_form import FormLogisticMetrics
from src.modeling.logistic_schedule_gap_ablation import FEATURE_SETS as GAP_FEATURE_SETS


CURRENT_BEST = (
    "elo_diff",
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
    "home_days_since_last_match", "away_days_since_last_match",
    "home_has_previous_match", "away_has_previous_match",
)
MOMENTUM = (
    "home_elo_change_last5", "away_elo_change_last5", "elo_change_last5_diff",
    "home_elo_change_last5_matches", "away_elo_change_last5_matches",
)
H2H = ("h2h_last5_matches", "h2h_last5_points_diff", "h2h_last5_goal_diff")
ALL_NUMERIC = (
    "home_elo", "away_elo", "elo_diff",
    "home_last5_points", "away_last5_points",
    "home_last5_wins", "away_last5_wins",
    "home_last5_draws", "away_last5_draws",
    "home_last5_losses", "away_last5_losses",
    "home_last5_goals_for", "away_last5_goals_for",
    "home_last5_goals_against", "away_last5_goals_against",
    "h2h_last5_matches", "h2h_last5_points_diff", "h2h_last5_goal_diff",
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
    "home_days_since_last_match", "away_days_since_last_match", "days_since_last_match_diff",
    "home_has_previous_match", "away_has_previous_match",
    "home_elo_change_last5", "away_elo_change_last5", "elo_change_last5_diff",
    "home_elo_change_last5_matches", "away_elo_change_last5_matches",
)
EXPECTED_SETS = {
    "current_best": CURRENT_BEST,
    "current_best_momentum": (*CURRENT_BEST, *MOMENTUM),
    "current_best_momentum_h2h": (*CURRENT_BEST, *MOMENTUM, *H2H),
    "all_numeric": ALL_NUMERIC,
}


@pytest.fixture(scope="module")
def dataset():
    rows = []
    for season in range(2015, 2025):
        for match, result in enumerate((2, 0, 1, 1, 2, 0)):
            position = len(rows)
            row = {
                column: float((position * (number + 3)) % 37 - 18 + number / 10)
                for number, column in enumerate(ALL_NUMERIC)
            }
            row.update(
                match_id=f"synthetic-{season}-{match}",
                match_date=pd.Timestamp(season, 3, match + 1),
                season=season,
                competition="J1",
                home_team="Home",
                away_team="Away",
                home_team_id="home",
                away_team_id="away",
                home_elo=1500.0 + position,
                away_elo=1480.0 + position,
                home_days_since_last_match=20.0 + position * 3,
                away_days_since_last_match=35.0 + position * 2,
                days_since_last_match_diff=-1000.0 - position,
                home_has_previous_match=match % 2,
                away_has_previous_match=(match // 2) % 2,
                elo_change_last5_diff=700.0 + position,
                result=result,
            )
            rows.append(row)
    columns = [
        *DATASET_COLUMNS, *H2H, *CURRENT_BEST[1:7],
        "home_days_since_last_match", "away_days_since_last_match", "days_since_last_match_diff",
        "home_has_previous_match", "away_has_previous_match", *MOMENTUM,
    ]
    frame = pd.DataFrame(rows, columns=columns)
    frame.index = pd.Index([11, 3, 11, 4, 0, 3] * 10, name="source_index")
    return frame


@pytest.fixture(scope="module")
def observed(dataset):
    before = dataset.copy(deep=True)
    fits, scaler_fits, predictions, split_inputs, accesses, loss_labels = [], [], [], [], [], []
    original_split = ablation.split_training_dataset
    original_fit = Pipeline.fit
    original_scaler_fit = StandardScaler.fit
    original_predict = Pipeline.predict_proba
    original_loss = ablation.log_loss

    def split(frame):
        split_inputs.append(frame.copy(deep=True))
        partitions = original_split(frame)

        class AllowedPartitions:
            # Retrieval must use match_id even when the splitter resets indexes.
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
        patch.setattr(ablation, "split_training_dataset", split)
        patch.setattr(Pipeline, "fit", fit)
        patch.setattr(StandardScaler, "fit", scaler_fit)
        patch.setattr(Pipeline, "predict_proba", predict)
        patch.setattr(ablation, "log_loss", loss)
        metrics = ablation.run_logistic_final_ablation(dataset)
    return dict(
        before=before, fits=fits, scaler_fits=scaler_fits, predictions=predictions,
        split_inputs=split_inputs, accesses=accesses, loss_labels=loss_labels, metrics=metrics,
    )


def test_exactly_four_fixed_feature_sets(observed):
    assert ablation.FEATURE_SETS == EXPECTED_SETS
    assert list(observed["metrics"]) == list(EXPECTED_SETS)


def test_a_is_the_existing_eleven_feature_best():
    assert ablation.FEATURE_SETS["current_best"] == CURRENT_BEST
    assert ablation.FEATURE_SETS["current_best"] == GAP_FEATURE_SETS["elo_stadium_gap_raw"]
    assert len(CURRENT_BEST) == 11


def test_b_adds_only_five_momentum_features():
    assert ablation.FEATURE_SETS["current_best_momentum"] == (*CURRENT_BEST, *MOMENTUM)
    assert len(ablation.FEATURE_SETS["current_best_momentum"]) == 16


def test_c_adds_only_three_h2h_features():
    assert ablation.FEATURE_SETS["current_best_momentum_h2h"] == (*CURRENT_BEST, *MOMENTUM, *H2H)
    assert len(ablation.FEATURE_SETS["current_best_momentum_h2h"]) == 19


def test_d_has_exactly_the_specified_34_numeric_features():
    assert ablation.FEATURE_SETS["all_numeric"] == ALL_NUMERIC
    assert len(set(ablation.FEATURE_SETS["all_numeric"])) == 34


def test_target_and_metadata_are_never_features():
    excluded = {
        "match_id", "match_date", "season", "competition",
        "home_team", "away_team", "home_team_id", "away_team_id", "result",
    }
    for columns in ablation.FEATURE_SETS.values():
        assert excluded.isdisjoint(columns)


def test_every_fit_and_prediction_uses_the_specified_column_order(observed):
    for records in (observed["fits"], observed["predictions"]):
        assert [frame.shape[1] for _, frame, _ in records] == [11, 16, 19, 34]
        for (_, frame, _), columns in zip(records, EXPECTED_SETS.values(), strict=True):
            assert tuple(frame.columns) == columns


def test_all_four_models_use_identical_independent_pipelines(observed):
    models = [model for model, _, _ in observed["fits"]]
    assert len(models) == len({id(model) for model in models}) == 4
    for model in models:
        assert isinstance(model, Pipeline)
        assert [name for name, _ in model.steps] == ["scaler", "logistic"]
        assert [type(step) for _, step in model.steps] == [StandardScaler, LogisticRegression]
    for step in ("scaler", "logistic"):
        assert len({id(model.named_steps[step]) for model in models}) == 4
        assert all(
            model.named_steps[step].get_params() == models[0].named_steps[step].get_params()
            for model in models
        )


@pytest.mark.parametrize("parameter, expected", [("solver", "lbfgs"), ("max_iter", 1000), ("random_state", 0)])
def test_fixed_logistic_parameters(observed, parameter, expected):
    for model, _, _ in observed["fits"]:
        assert model.named_steps["logistic"].get_params()[parameter] == expected


def test_fit_uses_only_train_features_and_targets(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    assert len(observed["fits"]) == 4
    for (_, features, target), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, train.loc[:, list(columns)])
        assert_series_equal(target, train["result"])


def test_scalers_fit_once_on_raw_train_values_inside_the_pipelines(dataset, observed):
    assert len(observed["scaler_fits"]) == 4
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    for (scaler, features), (model, _, _), columns in zip(
        observed["scaler_fits"], observed["fits"], EXPECTED_SETS.values(), strict=True,
    ):
        assert scaler is model.named_steps["scaler"]
        assert_frame_equal(features, train.loc[:, list(columns)])
        assert scaler.n_samples_seen_ == len(train)
        np.testing.assert_allclose(scaler.mean_, features.mean().to_numpy())
        np.testing.assert_allclose(scaler.var_, features.var(ddof=0).to_numpy())
        assert not np.allclose(scaler.mean_, dataset.loc[:, list(columns)].mean().to_numpy())


def test_validation_targets_do_not_affect_fitted_models(dataset, observed, monkeypatch):
    changed = dataset.copy(deep=True)
    mask = changed["season"].eq(2024)
    changed.loc[mask, "result"] = (changed.loc[mask, "result"] + 1) % 3
    fitted = []
    original_fit = Pipeline.fit

    def fit(model, frame, target, **kwargs):
        fitted.append(model)
        return original_fit(model, frame, target, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", fit)
    ablation.run_logistic_final_ablation(changed)
    for model, (original, _, _) in zip(fitted, observed["fits"], strict=True):
        for attribute in ("coef_", "intercept_"):
            np.testing.assert_array_equal(
                getattr(model.named_steps["logistic"], attribute),
                getattr(original.named_steps["logistic"], attribute),
            )


def test_predict_proba_receives_only_validation_features(dataset, observed):
    validation = dataset.loc[dataset["season"].eq(2024)]
    assert len(observed["predictions"]) == 4
    for (_, features, _), columns in zip(observed["predictions"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, validation.loc[:, list(columns)])


def test_test_partition_is_never_accessed(observed):
    assert "test" not in observed["accesses"]


def test_reserved_partition_is_never_accessed(observed):
    assert "reserved" not in observed["accesses"]


def test_splitter_receives_only_the_existing_24_columns(dataset, observed):
    assert dataset.shape[1] == 43
    assert dataset["season"].between(2015, 2024).all()
    assert len(observed["split_inputs"]) == 1
    assert len(DATASET_COLUMNS) == 24
    assert_frame_equal(observed["split_inputs"][0], dataset.loc[:, list(DATASET_COLUMNS)])


def test_match_id_mapping_preserves_rows_despite_reset_split_and_duplicate_input_indexes(dataset, observed):
    assert not dataset.index.is_unique
    assert dataset["match_id"].is_unique
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    validation = dataset.loc[dataset["season"].eq(2024)]
    assert len(train) == 54 and len(validation) == 6
    assert_frame_equal(observed["fits"][-1][1], train.loc[:, list(ALL_NUMERIC)])
    assert_frame_equal(observed["predictions"][-1][1], validation.loc[:, list(ALL_NUMERIC)])


def test_precomputed_values_are_not_recalculated_or_transformed(dataset, observed):
    for records, mask in (
        (observed["fits"], dataset["season"].between(2015, 2023)),
        (observed["predictions"], dataset["season"].eq(2024)),
    ):
        source = dataset.loc[mask]
        for difference, home, away in (
            ("elo_diff", "home_elo", "away_elo"),
            ("days_since_last_match_diff", "home_days_since_last_match", "away_days_since_last_match"),
            ("elo_change_last5_diff", "home_elo_change_last5", "away_elo_change_last5"),
        ):
            assert not source[difference].eq(source[home] - source[away]).any()
        assert source[["home_days_since_last_match", "away_days_since_last_match"]].gt(14).all().all()
        for (_, features, _), columns in zip(records, EXPECTED_SETS.values(), strict=True):
            assert_frame_equal(features, source.loc[:, list(columns)])


def test_fitted_class_order_is_away_draw_home(observed):
    for model, _, _ in observed["fits"]:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])


def test_missing_training_class_is_rejected_before_prediction(dataset, monkeypatch):
    missing_draws = dataset.loc[~(dataset["season"].le(2023) & dataset["result"].eq(1))]

    def forbidden_predict(*args, **kwargs):
        pytest.fail("A model with missing classes must not predict")

    monkeypatch.setattr(Pipeline, "predict_proba", forbidden_predict)
    with pytest.raises(ValueError, match="model.classes_"):
        ablation.run_logistic_final_ablation(missing_draws)


def test_probabilities_have_three_class_columns(observed):
    for _, features, probabilities in observed["predictions"]:
        assert probabilities.shape == (len(features), 3)


def test_probabilities_are_finite_and_sum_to_one(observed):
    for _, _, probabilities in observed["predictions"]:
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_accuracy_uses_validation_targets_and_is_in_range(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        assert np.isfinite(metrics.accuracy) and 0 <= metrics.accuracy <= 1
        assert metrics.accuracy == pytest.approx(np.mean(probabilities.argmax(axis=1) == target))


def test_log_loss_is_finite_nonnegative_and_uses_validation_with_explicit_class_order(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    assert observed["loss_labels"] == [[0, 1, 2]] * 4
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = -np.log(probabilities[np.arange(len(target)), target]).mean()
        assert np.isfinite(metrics.log_loss) and metrics.log_loss >= 0
        assert metrics.log_loss == pytest.approx(expected)


def test_brier_sums_squared_errors_over_classes_then_averages_matches(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = sum(
            sum((probability - int(label == actual)) ** 2 for label, probability in enumerate(row))
            for actual, row in zip(target, probabilities, strict=True)
        ) / len(target)
        assert np.isfinite(metrics.brier_score) and 0 <= metrics.brier_score <= 2
        assert metrics.brier_score == pytest.approx(expected)


def test_result_contains_only_four_metric_records_without_selecting_a_winner(observed):
    assert list(observed["metrics"]) == list(EXPECTED_SETS)
    for metrics in observed["metrics"].values():
        assert isinstance(metrics, FormLogisticMetrics)
        values = asdict(metrics)
        assert set(values) == {"accuracy", "log_loss", "brier_score"}
        assert all(isinstance(value, float) and np.isfinite(value) for value in values.values())


def test_input_dataframe_is_unchanged(dataset, observed):
    assert_frame_equal(dataset, observed["before"])


def test_same_input_produces_identical_results(dataset, observed):
    assert ablation.run_logistic_final_ablation(dataset) == observed["metrics"]
