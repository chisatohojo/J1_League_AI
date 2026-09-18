"""Synthetic checks for exactly eight fixed train/validation LightGBM runs."""

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMClassifier
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import lightgbm_ablation as baseline
from src.modeling import lightgbm_small_tuning as tuning


EXPECTED_FEATURES = {
    name: baseline.FEATURE_SETS[name] for name in ("current_context", "all_numeric")
}
PARAMETER_NAMES = (
    "n_estimators", "learning_rate", "num_leaves", "max_depth",
    "min_child_samples", "reg_alpha", "reg_lambda",
)
EXPECTED_PARAMETERS = {
    name: dict(zip(PARAMETER_NAMES, values, strict=True))
    for name, values in (
        ("very_small", (80, 0.03, 3, 2, 80, 0.0, 5.0)),
        ("small", (120, 0.03, 5, 3, 60, 0.0, 3.0)),
        ("small_regularized", (150, 0.03, 7, 3, 50, 0.5, 5.0)),
        ("conservative", (100, 0.05, 5, 3, 100, 1.0, 10.0)),
    )
}
EXPECTED_COMMON = dict(
    objective="multiclass", num_class=3, subsample=1.0, colsample_bytree=1.0,
    random_state=0, n_jobs=1, verbosity=-1, deterministic=True, force_col_wise=True,
)
COMBINATIONS = tuple(
    (feature, parameter) for feature in EXPECTED_FEATURES for parameter in EXPECTED_PARAMETERS
)


@pytest.fixture(scope="module")
def dataset():
    rng = np.random.default_rng(0)
    rows = []
    for season in range(2015, 2025):
        for match in range(36):
            row = dict(zip(EXPECTED_FEATURES["all_numeric"], rng.normal(10, 3, 34), strict=True))
            row.update(
                match_id=f"synthetic-{season}-{match}", season=season,
                match_date=pd.Timestamp(season, 3, 1) + pd.Timedelta(days=match),
                competition="J1", home_team="Home", away_team="Away",
                home_team_id="home", away_team_id="away", result=match % 3,
                elo_diff=(match % 3 - 1) * 50 + season - 2015,
                home_has_previous_match=match % 2,
                away_has_previous_match=(match + 1) % 2,
            )
            rows.append(row)
    frame = pd.DataFrame(rows, columns=[
        *DATASET_COLUMNS, *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS, *ELO_MOMENTUM_COLUMNS,
    ])
    frame.loc[[0, 324], "home_elo_change_last5"] = np.nan
    frame.index = pd.Index([9, 2, 9] * 120, name="source_index")
    return frame


@pytest.fixture(scope="module")
def observed(dataset):
    records = dict(
        before=dataset.copy(deep=True), constructors=[], fits=[], predictions=[],
        split_inputs=[], forbidden_accesses=[], losses=[],
    )
    original_split = tuning.split_training_dataset
    original_fit, original_predict = LGBMClassifier.fit, LGBMClassifier.predict_proba
    original_loss = tuning.log_loss

    def split(frame):
        records["split_inputs"].append(frame.copy(deep=True))
        partitions = original_split(frame)

        class AllowedPartitions:
            train = partitions.train.reset_index(drop=True)
            validation = partitions.validation.reset_index(drop=True)

            @property
            def test(self):
                records["forbidden_accesses"].append("test")
                pytest.fail("Test partition must not be accessed")

            @property
            def reserved(self):
                records["forbidden_accesses"].append("reserved")
                pytest.fail("Reserved partition must not be accessed")

        return AllowedPartitions()

    def construct(*args, **kwargs):
        records["constructors"].append((args, kwargs.copy()))
        return LGBMClassifier(*args, **kwargs)

    def fit(model, frame, target, *args, **kwargs):
        records["fits"].append((model, frame.copy(deep=True), target.copy(deep=True), args, kwargs.copy()))
        return original_fit(model, frame, target, *args, **kwargs)

    def predict(model, frame, *args, **kwargs):
        probabilities = original_predict(model, frame, *args, **kwargs)
        records["predictions"].append((model, frame.copy(deep=True), probabilities.copy(), args, kwargs.copy()))
        return probabilities

    def loss(target, probabilities, **kwargs):
        records["losses"].append((target.copy(deep=True), kwargs.copy()))
        return original_loss(target, probabilities, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("No pipeline, scaler or prior baseline model may run")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tuning, "split_training_dataset", split)
        patch.setattr(tuning, "LGBMClassifier", construct)
        patch.setattr(LGBMClassifier, "fit", fit)
        patch.setattr(LGBMClassifier, "predict_proba", predict)
        patch.setattr(tuning, "log_loss", loss)
        patch.setattr(Pipeline, "fit", forbidden)
        patch.setattr(StandardScaler, "fit_transform", forbidden)
        patch.setattr(baseline, "run_lightgbm_ablation", forbidden)
        records["metrics"] = tuning.run_lightgbm_small_tuning(dataset)
    return records


def test_exactly_two_feature_sets_with_eleven_and_thirty_four_columns(observed):
    assert list(tuning.FEATURE_SETS) == ["current_context", "all_numeric"]
    assert tuning.FEATURE_SETS["current_context"] == (
        "elo_diff",
        "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
        "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
        "home_days_since_last_match", "away_days_since_last_match",
        "home_has_previous_match", "away_has_previous_match",
    )
    assert [len(columns) for columns in tuning.FEATURE_SETS.values()] == [11, 34]
    assert [features.shape[1] for _, features, *_ in observed["fits"]] == [11] * 4 + [34] * 4


@pytest.mark.parametrize("name", EXPECTED_FEATURES)
def test_feature_definition_is_reused_unchanged(name):
    assert tuning.FEATURE_SETS[name] is baseline.FEATURE_SETS[name]
    assert set(tuning.FEATURE_SETS[name]).isdisjoint({
        "match_id", "match_date", "season", "competition", "home_team", "away_team",
        "home_team_id", "away_team_id", "result", "elo_mean", "abs_elo_diff",
    })


def test_exactly_four_requested_parameter_sets_and_common_settings():
    assert list(tuning.PARAMETER_SETS) == list(EXPECTED_PARAMETERS)
    assert tuning.PARAMETER_SETS == EXPECTED_PARAMETERS
    assert tuning.COMMON_PARAMETERS == EXPECTED_COMMON


def test_exactly_eight_independent_classifiers_with_exact_settings(observed):
    assert len(observed["constructors"]) == len(observed["fits"]) == 8
    assert len({id(model) for model, *_ in observed["fits"]}) == 8
    for (args, kwargs), (feature, parameter), (model, features, *_) in zip(
        observed["constructors"], COMBINATIONS, observed["fits"], strict=True,
    ):
        assert args == ()
        assert kwargs == EXPECTED_COMMON | EXPECTED_PARAMETERS[parameter]
        assert tuple(features.columns) == EXPECTED_FEATURES[feature]
        assert type(model) is LGBMClassifier
        assert model.get_params()["class_weight"] is None


def test_fit_uses_only_unmodified_train_features_and_targets(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    assert len(train) > 200
    for (_, features, target, *_), (name, _) in zip(observed["fits"], COMBINATIONS, strict=True):
        assert_frame_equal(features, train.loc[:, list(EXPECTED_FEATURES[name])])
        assert_series_equal(target, train["result"])
    assert observed["fits"][-1][1]["home_elo_change_last5"].isna().any()


def test_only_validation_features_and_targets_are_evaluated(dataset, observed):
    validation = dataset.loc[dataset["season"].eq(2024)]
    assert len(observed["predictions"]) == len(observed["losses"]) == 8
    for (_, features, *_), (name, _) in zip(observed["predictions"], COMBINATIONS, strict=True):
        assert_frame_equal(features, validation.loc[:, list(EXPECTED_FEATURES[name])])
    for target, kwargs in observed["losses"]:
        assert_series_equal(target, validation["result"])
        assert kwargs["labels"] == [0, 1, 2]


@pytest.mark.parametrize("partition", ["test", "reserved"])
def test_forbidden_partition_is_never_accessed(partition, observed):
    assert partition not in observed["forbidden_accesses"]


def test_split_receives_only_original_24_columns(dataset, observed):
    assert dataset.shape[1] == 43
    assert len(observed["split_inputs"]) == 1
    assert_frame_equal(observed["split_inputs"][0], dataset.loc[:, list(DATASET_COLUMNS)])


def test_match_id_mapping_preserves_duplicate_indices_and_row_order(dataset, observed):
    assert not dataset.index.is_unique
    columns = list(EXPECTED_FEATURES["all_numeric"])
    assert_frame_equal(observed["fits"][-1][1], dataset.iloc[:324].loc[:, columns])
    assert_frame_equal(observed["predictions"][-1][1], dataset.iloc[324:].loc[:, columns])
    assert_series_equal(observed["fits"][-1][2], dataset.iloc[:324]["result"])


def test_fit_and_predict_have_no_early_stopping_or_extra_arguments(observed):
    for *_, args, kwargs in [*observed["fits"], *observed["predictions"]]:
        assert args == ()
        assert kwargs == {}


def test_class_order_and_probability_shape_and_normalization(observed):
    assert tuning.CLASS_ORDER is baseline.CLASS_ORDER
    assert tuple(tuning.CLASS_ORDER) == (0, 1, 2)
    for model, features, probabilities, *_ in observed["predictions"]:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])
        assert probabilities.shape == (len(features), 3)
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_metrics_match_validation_formulas_and_ranges(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for (feature, parameter), (_, _, probabilities, *_) in zip(
        COMBINATIONS, observed["predictions"], strict=True,
    ):
        metrics = observed["metrics"][feature][parameter]
        assert np.isfinite(metrics.accuracy) and 0 <= metrics.accuracy <= 1
        assert metrics.accuracy == pytest.approx(np.mean(probabilities.argmax(axis=1) == target))
        assert np.isfinite(metrics.log_loss) and metrics.log_loss >= 0
        assert metrics.log_loss == pytest.approx(-np.log(probabilities[np.arange(len(target)), target]).mean())
        expected_brier = sum(
            sum((probability - int(label == actual)) ** 2 for label, probability in enumerate(row))
            for actual, row in zip(target, probabilities, strict=True)
        ) / len(target)
        assert np.isfinite(metrics.brier_score) and 0 <= metrics.brier_score <= 2
        assert metrics.brier_score == pytest.approx(expected_brier)


def test_input_is_unchanged(dataset, observed):
    assert_frame_equal(dataset, observed["before"])


def test_identical_input_produces_exactly_identical_metrics(dataset, observed):
    assert tuning.run_lightgbm_small_tuning(dataset) == observed["metrics"]


def test_return_contains_all_eight_metric_sets_without_a_winner(observed):
    assert list(observed["metrics"]) == list(EXPECTED_FEATURES)
    assert tuning.LightGBMMetrics is baseline.LightGBMMetrics
    for parameters in observed["metrics"].values():
        assert list(parameters) == list(EXPECTED_PARAMETERS)
        for metrics in parameters.values():
            values = asdict(metrics)
            assert isinstance(metrics, baseline.LightGBMMetrics)
            assert set(values) == {"accuracy", "log_loss", "brier_score"}
            assert all(isinstance(value, float) and np.isfinite(value) for value in values.values())


def test_same_eight_configurations_run_regardless_of_validation_outcomes(dataset, monkeypatch):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    calls, results = [], []

    class ControlledClassifier:
        classes_ = np.array([0, 1, 2])

        def __init__(self, **kwargs):
            self.parameters = kwargs.copy()

        def fit(self, features, train_target):
            calls.append((tuple(features.columns), self.parameters))
            return self

        def predict_proba(self, features):
            probabilities = np.full((len(features), 3), 0.05)
            probabilities[np.arange(len(features)), (target + shift) % 3] = 0.9
            return probabilities

    monkeypatch.setattr(tuning, "LGBMClassifier", ControlledClassifier)
    expected_calls = [
        (EXPECTED_FEATURES[feature], EXPECTED_COMMON | EXPECTED_PARAMETERS[parameter])
        for feature, parameter in COMBINATIONS
    ]
    for shift in (0, 1):
        calls.clear()
        results.append(tuning.run_lightgbm_small_tuning(dataset))
        assert calls == expected_calls
        assert list(results[-1]) == list(EXPECTED_FEATURES)
        assert all(list(parameters) == list(EXPECTED_PARAMETERS) for parameters in results[-1].values())
    assert results[0] != results[1]
