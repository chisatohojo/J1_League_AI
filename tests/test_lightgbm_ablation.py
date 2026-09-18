"""Synthetic fixed LightGBM ablations; never load or evaluate held-out data."""

from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from lightgbm import LGBMClassifier
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import lightgbm_ablation as ablation


STADIUM_COLUMNS = (
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
)
RAW_GAP_COLUMNS = (
    "home_days_since_last_match", "away_days_since_last_match",
    "home_has_previous_match", "away_has_previous_match",
)
MOMENTUM_COLUMNS = (
    "home_elo_change_last5", "away_elo_change_last5", "elo_change_last5_diff",
    "home_elo_change_last5_matches", "away_elo_change_last5_matches",
)
H2H_COLUMNS = ("h2h_last5_matches", "h2h_last5_points_diff", "h2h_last5_goal_diff")
CONTEXT_COLUMNS = ("elo_diff", *STADIUM_COLUMNS, *RAW_GAP_COLUMNS)
ALL_NUMERIC_COLUMNS = (
    "home_elo", "away_elo", "elo_diff",
    "home_last5_points", "away_last5_points", "home_last5_wins", "away_last5_wins",
    "home_last5_draws", "away_last5_draws", "home_last5_losses", "away_last5_losses",
    "home_last5_goals_for", "away_last5_goals_for",
    "home_last5_goals_against", "away_last5_goals_against",
    *H2H_COLUMNS, *STADIUM_COLUMNS,
    "home_days_since_last_match", "away_days_since_last_match", "days_since_last_match_diff",
    "home_has_previous_match", "away_has_previous_match", *MOMENTUM_COLUMNS,
)
EXPECTED_SETS = {
    "elo_only": ("elo_diff",),
    "current_context": CONTEXT_COLUMNS,
    "current_context_momentum": (*CONTEXT_COLUMNS, *MOMENTUM_COLUMNS),
    "current_context_h2h_momentum": (*CONTEXT_COLUMNS, *MOMENTUM_COLUMNS, *H2H_COLUMNS),
    "all_numeric": ALL_NUMERIC_COLUMNS,
}
EXPECTED_PARAMETERS = dict(
    objective="multiclass", num_class=3, n_estimators=100, learning_rate=0.05,
    num_leaves=15, max_depth=-1, min_child_samples=20, subsample=1.0,
    colsample_bytree=1.0, reg_alpha=0.0, reg_lambda=0.0, random_state=0,
    n_jobs=1, verbosity=-1, deterministic=True, force_col_wise=True,
)


@pytest.fixture(scope="module")
def dataset():
    rng = np.random.default_rng(0)
    rows = []
    for season in range(2015, 2025):
        for match in range(9):
            row = dict(zip(ALL_NUMERIC_COLUMNS, rng.normal(10, 3, 34), strict=True))
            row.update(
                match_id=f"synthetic-{season}-{match}",
                match_date=pd.Timestamp(season, 3, match + 1), season=season,
                competition="J1", home_team="Home", away_team="Away",
                home_team_id="home", away_team_id="away", result=match % 3,
                elo_diff=(match % 3 - 1) * 50 + season - 2015,
                home_has_previous_match=match % 2,
                away_has_previous_match=(match + 1) % 2,
            )
            rows.append(row)
    frame = pd.DataFrame(rows, columns=[
        *DATASET_COLUMNS, *H2H_COLUMNS, *STADIUM_COLUMNS,
        "home_days_since_last_match", "away_days_since_last_match", "days_since_last_match_diff",
        "home_has_previous_match", "away_has_previous_match", *MOMENTUM_COLUMNS,
    ])
    # Native missing-value support must receive the supplied values unchanged.
    frame.loc[[0, 81], "home_elo_change_last5"] = np.nan
    frame.index = pd.Index([9, 2, 9] * 30, name="source_index")
    return frame


@pytest.fixture(scope="module")
def observed(dataset):
    records = dict(
        before=dataset.copy(deep=True), constructors=[], fits=[], predictions=[],
        split_inputs=[], forbidden_accesses=[], losses=[],
    )
    original_split = ablation.split_training_dataset
    original_fit, original_predict = LGBMClassifier.fit, LGBMClassifier.predict_proba
    original_loss = ablation.log_loss

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

    def forbidden_preprocessing(*args, **kwargs):
        pytest.fail("A pipeline or StandardScaler must not preprocess LightGBM features")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ablation, "split_training_dataset", split)
        patch.setattr(ablation, "LGBMClassifier", construct)
        patch.setattr(LGBMClassifier, "fit", fit)
        patch.setattr(LGBMClassifier, "predict_proba", predict)
        patch.setattr(ablation, "log_loss", loss)
        patch.setattr(Pipeline, "fit", forbidden_preprocessing)
        patch.setattr(StandardScaler, "fit_transform", forbidden_preprocessing)
        records["metrics"] = ablation.run_lightgbm_ablation(dataset)
    return records


def test_exactly_five_feature_sets_with_requested_counts(observed):
    assert list(ablation.FEATURE_SETS) == list(EXPECTED_SETS)
    assert list(observed["metrics"]) == list(EXPECTED_SETS)
    assert [len(columns) for columns in ablation.FEATURE_SETS.values()] == [1, 11, 16, 19, 34]
    assert [features.shape[1] for _, features, *_ in observed["fits"]] == [1, 11, 16, 19, 34]


@pytest.mark.parametrize("name,columns", EXPECTED_SETS.items())
def test_each_model_uses_exact_requested_features(name, columns, observed):
    assert ablation.FEATURE_SETS[name] == columns
    position = list(EXPECTED_SETS).index(name)
    assert tuple(observed["fits"][position][1].columns) == columns
    assert tuple(observed["predictions"][position][1].columns) == columns


def test_all_numeric_excludes_target_identifiers_metadata_and_new_features():
    excluded = {
        "match_id", "match_date", "season", "competition", "home_team", "away_team",
        "home_team_id", "away_team_id", "result", "elo_mean", "abs_elo_diff",
    }
    assert excluded.isdisjoint(ablation.FEATURE_SETS["all_numeric"])


def test_all_five_classifiers_use_identical_fixed_parameters_without_class_weights(observed):
    assert len(observed["constructors"]) == 5
    for args, kwargs in observed["constructors"]:
        assert args == ()
        assert kwargs == EXPECTED_PARAMETERS
    models = [model for model, *_ in observed["fits"]]
    assert len({id(model) for model in models}) == 5
    for model in models:
        assert model.get_params()["class_weight"] is None
        for name, value in EXPECTED_PARAMETERS.items():
            assert model.get_params()[name] == value


def test_features_reach_direct_classifier_without_scaling_or_imputation(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    for (model, features, *_), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert type(model) is LGBMClassifier
        assert_frame_equal(features, train.loc[:, list(columns)])
    assert observed["fits"][-1][1]["home_elo_change_last5"].isna().any()


def test_fit_and_predict_receive_no_early_stopping_or_extra_arguments(observed):
    for *_, args, kwargs in [*observed["fits"], *observed["predictions"]]:
        assert args == ()
        assert kwargs == {}


def test_fit_uses_only_train_features_and_targets(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    assert len(observed["fits"]) == 5
    for (_, features, target, *_), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, train.loc[:, list(columns)])
        assert_series_equal(target, train["result"])


def test_only_validation_features_and_targets_are_evaluated(dataset, observed):
    validation = dataset.loc[dataset["season"].eq(2024)]
    assert len(observed["predictions"]) == len(observed["losses"]) == 5
    for (_, features, *_), columns in zip(observed["predictions"], EXPECTED_SETS.values(), strict=True):
        assert_frame_equal(features, validation.loc[:, list(columns)])
    for target, kwargs in observed["losses"]:
        assert_series_equal(target, validation["result"])
        assert kwargs["labels"] == [0, 1, 2]


@pytest.mark.parametrize("partition", ["test", "reserved"])
def test_forbidden_partition_is_never_accessed(partition, observed):
    assert partition not in observed["forbidden_accesses"]


def test_split_receives_only_existing_24_columns(dataset, observed):
    assert dataset.shape[1] == 43
    assert len(observed["split_inputs"]) == 1
    assert_frame_equal(observed["split_inputs"][0], dataset.loc[:, list(DATASET_COLUMNS)])


def test_match_id_mapping_preserves_order_with_duplicate_source_indices(dataset, observed):
    assert not dataset.index.is_unique
    columns = list(ALL_NUMERIC_COLUMNS)
    assert_frame_equal(observed["fits"][-1][1], dataset.iloc[:81].loc[:, columns])
    assert_frame_equal(observed["predictions"][-1][1], dataset.iloc[81:].loc[:, columns])
    assert_series_equal(observed["fits"][-1][2], dataset.iloc[:81]["result"])


def test_class_order_is_away_draw_home(observed):
    assert tuple(ablation.CLASS_ORDER) == (0, 1, 2)
    for model, *_ in observed["fits"]:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])


def test_probabilities_have_three_columns(observed):
    for _, features, probabilities, *_ in observed["predictions"]:
        assert probabilities.shape == (len(features), 3)


def test_probabilities_are_finite_and_sum_to_one(observed):
    for _, _, probabilities, *_ in observed["predictions"]:
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_accuracy_matches_validation_predictions_and_is_in_range(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities, *_) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        assert np.isfinite(metrics.accuracy) and 0 <= metrics.accuracy <= 1
        assert metrics.accuracy == pytest.approx(np.mean(probabilities.argmax(axis=1) == target))


def test_log_loss_matches_validation_probabilities_and_is_finite(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities, *_) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = -np.log(probabilities[np.arange(len(target)), target]).mean()
        assert np.isfinite(metrics.log_loss) and metrics.log_loss >= 0
        assert metrics.log_loss == pytest.approx(expected)


def test_brier_score_sums_classes_then_averages_matches(dataset, observed):
    target = dataset.loc[dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities, *_) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = sum(
            sum((probability - int(label == actual)) ** 2 for label, probability in enumerate(row))
            for actual, row in zip(target, probabilities, strict=True)
        ) / len(target)
        assert np.isfinite(metrics.brier_score) and 0 <= metrics.brier_score <= 2
        assert metrics.brier_score == pytest.approx(expected)


def test_input_dataset_is_unchanged(dataset, observed):
    assert_frame_equal(dataset, observed["before"])


def test_identical_input_produces_exactly_the_same_results(dataset, observed):
    assert ablation.run_lightgbm_ablation(dataset) == observed["metrics"]


def test_return_contains_only_five_models_and_three_numeric_metrics(observed):
    assert list(observed["metrics"]) == list(EXPECTED_SETS)
    for metrics in observed["metrics"].values():
        assert isinstance(metrics, ablation.LightGBMMetrics)
        values = asdict(metrics)
        assert set(values) == {"accuracy", "log_loss", "brier_score"}
        assert all(isinstance(value, float) and np.isfinite(value) for value in values.values())


def test_wrong_class_order_is_rejected_before_evaluation(dataset, monkeypatch):
    class WrongClassOrder:
        classes_ = np.array([2, 1, 0])

        def fit(self, features, target):
            return self

        def predict_proba(self, features):
            pytest.fail("An invalid class order must be rejected before prediction")

    monkeypatch.setattr(ablation, "LGBMClassifier", lambda **kwargs: WrongClassOrder())
    with pytest.raises(ValueError, match="model.classes_"):
        ablation.run_lightgbm_ablation(dataset)
