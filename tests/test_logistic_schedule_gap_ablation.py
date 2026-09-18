"""Synthetic schedule-gap ablations; never load real data or held-out metrics."""

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
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import logistic_schedule_gap_ablation as ablation
from src.modeling.logistic_form import FormLogisticMetrics
from src.modeling.logistic_matchup_ablation import FEATURE_SETS as MATCHUP_FEATURE_SETS


H2H_COLUMNS = (
    "h2h_last5_matches", "h2h_last5_points_diff", "h2h_last5_goal_diff",
)
STADIUM_COLUMNS = (
    "home_stadium_last5_matches", "home_stadium_last5_points", "home_stadium_last5_goal_diff",
    "away_stadium_last5_matches", "away_stadium_last5_points", "away_stadium_last5_goal_diff",
)
RAW_GAP_COLUMNS = ("home_days_since_last_match", "away_days_since_last_match")
FLAG_COLUMNS = ("home_has_previous_match", "away_has_previous_match")
DIFF_COLUMN = "days_since_last_match_diff"
EXPECTED_SETS = {
    "elo_stadium": ("elo_diff", *STADIUM_COLUMNS),
    "elo_stadium_gap_diff": ("elo_diff", *STADIUM_COLUMNS, DIFF_COLUMN, *FLAG_COLUMNS),
    "elo_stadium_gap_raw": ("elo_diff", *STADIUM_COLUMNS, *RAW_GAP_COLUMNS, *FLAG_COLUMNS),
    "elo_h2h_stadium_gap_raw": (
        "elo_diff", *H2H_COLUMNS, *STADIUM_COLUMNS, *RAW_GAP_COLUMNS, *FLAG_COLUMNS,
    ),
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
                home_days_since_last_match=20 + (season - 2015) * 17 + result * 9,
                away_days_since_last_match=35 + (season - 2015) * 11 + result * 7,
                days_since_last_match_diff=-200 + season % 7 * 13 - result * 19,
                home_has_previous_match=(season + result) % 2,
                away_has_previous_match=(season + result // 2) % 2,
            )
            if season >= 2025:
                row.update(dict.fromkeys(
                    ("elo_diff", *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS), np.nan,
                ))
                row["result"] = 99
            rows.append(row)
    frame = pd.DataFrame(rows, columns=[
        *DATASET_COLUMNS, *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS,
    ])
    frame.index = pd.Index([9, 2, 9] * 12, name="source_index")
    return frame


@pytest.fixture(scope="module")
def observed(dataset):
    before = dataset.copy(deep=True)
    fits, predictions, split_inputs, accesses, loss_labels = [], [], [], [], []
    original_split = ablation.split_training_dataset
    original_fit, original_predict = Pipeline.fit, Pipeline.predict_proba
    original_log_loss = ablation.log_loss

    def split(frame):
        split_inputs.append(frame.copy(deep=True))
        partitions = original_split(frame)

        class AllowedPartitions:
            # A splitter's index must never be used to retrieve source rows.
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

    def predict(model, frame, **kwargs):
        probabilities = original_predict(model, frame, **kwargs)
        predictions.append((model, frame.copy(deep=True), probabilities.copy()))
        return probabilities

    def loss(target, probabilities, **kwargs):
        loss_labels.append(kwargs.get("labels"))
        return original_log_loss(target, probabilities, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ablation, "split_training_dataset", split)
        patch.setattr(Pipeline, "fit", fit)
        patch.setattr(Pipeline, "predict_proba", predict)
        patch.setattr(ablation, "log_loss", loss)
        metrics = ablation.run_logistic_schedule_gap_ablation(dataset)
    return dict(
        before=before, fits=fits, predictions=predictions, metrics=metrics,
        split_inputs=split_inputs, accesses=accesses, loss_labels=loss_labels,
    )


def test_exactly_four_fixed_feature_sets(observed):
    assert ablation.FEATURE_SETS == EXPECTED_SETS
    assert list(observed["metrics"]) == list(EXPECTED_SETS)
    for (_, frame, _), columns in zip(observed["fits"], EXPECTED_SETS.values(), strict=True):
        assert tuple(frame.columns) == columns


def test_feature_counts_are_seven_ten_eleven_fourteen(observed):
    assert [frame.shape[1] for _, frame, _ in observed["fits"]] == [7, 10, 11, 14]
    assert [frame.shape[1] for _, frame, _ in observed["predictions"]] == [7, 10, 11, 14]


def test_a_reuses_existing_elo_stadium_composition():
    assert ablation.FEATURE_SETS["elo_stadium"] == MATCHUP_FEATURE_SETS["elo_stadium"]


def test_b_adds_difference_and_flags_without_raw_gaps():
    columns = ablation.FEATURE_SETS["elo_stadium_gap_diff"]
    assert columns == (*MATCHUP_FEATURE_SETS["elo_stadium"], DIFF_COLUMN, *FLAG_COLUMNS)
    assert set(RAW_GAP_COLUMNS).isdisjoint(columns)


def test_c_adds_raw_gaps_and_flags_without_difference():
    columns = ablation.FEATURE_SETS["elo_stadium_gap_raw"]
    assert columns == (*MATCHUP_FEATURE_SETS["elo_stadium"], *RAW_GAP_COLUMNS, *FLAG_COLUMNS)
    assert DIFF_COLUMN not in columns


def test_d_adds_raw_gaps_and_flags_to_existing_elo_h2h_stadium():
    columns = ablation.FEATURE_SETS["elo_h2h_stadium_gap_raw"]
    assert columns == (*MATCHUP_FEATURE_SETS["elo_h2h_stadium"], *RAW_GAP_COLUMNS, *FLAG_COLUMNS)
    assert DIFF_COLUMN not in columns


def test_previous_match_flags_are_present_in_b_c_d_only(observed):
    assert set(FLAG_COLUMNS).isdisjoint(observed["fits"][0][1].columns)
    for _, features, _ in observed["fits"][1:]:
        assert set(FLAG_COLUMNS).issubset(features.columns)


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
    ablation.run_logistic_schedule_gap_ablation(changed)
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
    future = dataset.loc[dataset["season"].eq(2025)]
    assert future["result"].eq(99).all()
    assert future.loc[:, ["elo_diff", *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS]].isna().all().all()


def test_reserved_partition_not_accessed(dataset, observed):
    assert "reserved" not in observed["accesses"]
    future = dataset.loc[dataset["season"].eq(2026)]
    assert future["result"].eq(99).all()
    assert future.loc[:, ["elo_diff", *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS]].isna().all().all()


def test_split_receives_only_existing_24_columns(dataset, observed):
    assert dataset.shape[1] == 38
    assert len(observed["split_inputs"]) == 1
    assert_frame_equal(observed["split_inputs"][0], dataset.loc[:, list(DATASET_COLUMNS)])


def test_match_id_mapping_preserves_duplicate_source_indices_and_order(dataset, observed):
    assert not dataset.index.is_unique
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    validation = dataset.loc[dataset["season"].eq(2024)]
    columns = list(EXPECTED_SETS["elo_h2h_stadium_gap_raw"])
    assert_frame_equal(observed["fits"][-1][1], train.loc[:, columns])
    assert_frame_equal(observed["predictions"][-1][1], validation.loc[:, columns])
    assert len(observed["fits"][-1][1]) == 27
    assert len(observed["predictions"][-1][1]) == 3


def test_precomputed_elo_is_used_without_recalculation(dataset, observed):
    train = dataset.loc[dataset["season"].between(2015, 2023)]
    assert not train["elo_diff"].eq(train["home_elo"] - train["away_elo"]).all()
    for _, features, _ in observed["fits"]:
        assert_series_equal(features["elo_diff"], train["elo_diff"])


def test_raw_gaps_above_fourteen_are_not_capped_or_transformed(dataset, observed):
    for records, mask in (
        (observed["fits"], dataset["season"].between(2015, 2023)),
        (observed["predictions"], dataset["season"].eq(2024)),
    ):
        expected = dataset.loc[mask, list(RAW_GAP_COLUMNS)]
        assert expected.gt(14).all().all()
        for _, features, _ in records[2:]:
            assert_frame_equal(features.loc[:, list(RAW_GAP_COLUMNS)], expected)


def test_precomputed_difference_is_not_rederived_from_raw_gaps(dataset, observed):
    for records, mask in (
        (observed["fits"], dataset["season"].between(2015, 2023)),
        (observed["predictions"], dataset["season"].eq(2024)),
    ):
        source = dataset.loc[mask]
        recalculated = source[RAW_GAP_COLUMNS[0]] - source[RAW_GAP_COLUMNS[1]]
        assert not source[DIFF_COLUMN].eq(recalculated).any()
        assert_series_equal(records[1][1][DIFF_COLUMN], source[DIFF_COLUMN])


def test_precomputed_previous_match_flags_are_used_unchanged(dataset, observed):
    for records, mask in (
        (observed["fits"], dataset["season"].between(2015, 2023)),
        (observed["predictions"], dataset["season"].eq(2024)),
    ):
        expected = dataset.loc[mask, list(FLAG_COLUMNS)]
        assert expected.eq(0).any().all() and expected.eq(1).any().all()
        for _, features, _ in records[1:]:
            assert_frame_equal(features.loc[:, list(FLAG_COLUMNS)], expected)


def test_unused_ordinary_form_columns_can_be_missing(dataset, observed):
    ordinary_form = [column for column in DATASET_COLUMNS if "last5" in column]
    assert dataset.loc[:, ordinary_form].isna().all().all()
    for _, features, _ in [*observed["fits"], *observed["predictions"]]:
        assert np.isfinite(features.to_numpy()).all()
        assert not set(ordinary_form).intersection(features.columns)


def test_class_order_is_away_draw_home(observed):
    for model, _, _ in observed["fits"]:
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])


def test_incomplete_class_order_is_rejected(dataset):
    missing_draws = dataset.loc[~(dataset["season"].le(2023) & dataset["result"].eq(1))]
    with pytest.raises(ValueError, match="model.classes_"):
        ablation.run_logistic_schedule_gap_ablation(missing_draws)


def test_log_loss_receives_explicit_class_labels(observed):
    assert len(observed["loss_labels"]) == 4
    for labels in observed["loss_labels"]:
        assert list(labels) == [0, 1, 2]


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


def test_return_contains_only_numeric_metrics_without_selecting_a_winner(observed):
    assert set(observed["metrics"]) == set(EXPECTED_SETS)
    for metrics in observed["metrics"].values():
        assert isinstance(metrics, FormLogisticMetrics)
        values = asdict(metrics)
        assert set(values) == {"accuracy", "log_loss", "brier_score"}
        assert all(isinstance(value, float) and np.isfinite(value) for value in values.values())


def test_input_is_unchanged(dataset, observed):
    assert_frame_equal(dataset, observed["before"])


def test_same_input_produces_same_metrics(dataset, observed):
    assert ablation.run_logistic_schedule_gap_ablation(dataset) == observed["metrics"]
