"""Synthetic checks for four fixed stadium windows and validation-only scoring."""

from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS, add_matchup_context_features
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.stadium_window import STADIUM_WINDOW_COLUMNS, add_stadium_window_features
from src.features.stadium_window_history import OngoingStadiumWindowHistory
from src.features.training_dataset import DATASET_COLUMNS
from src.modeling import logistic_stadium_window_tuning as tuning
from src.modeling.logistic_final_ablation import CURRENT_BEST_COLUMNS, run_logistic_final_ablation
from src.modeling.logistic_form import FormLogisticMetrics


EXPECTED_WINDOWS = (3, 5, 8, 10)
EXPECTED_FEATURES = (
    "elo_diff",
    "home_stadium_window_matches", "home_stadium_window_points", "home_stadium_window_goal_diff",
    "away_stadium_window_matches", "away_stadium_window_points", "away_stadium_window_goal_diff",
    "home_days_since_last_match", "away_days_since_last_match",
    "home_has_previous_match", "away_has_previous_match",
)
FIXED_FEATURES = (EXPECTED_FEATURES[0], *EXPECTED_FEATURES[-4:])
PARTS = ("historical", "hyakunen", "ongoing")


@pytest.fixture(scope="module")
def synthetic():
    rows = []
    for season in range(2015, 2027):
        for match, (home_score, away_score) in enumerate(((3, 0), (0, 2), (1, 1), (0, 0), (2, 1), (1, 4))):
            home, away = ("A", "B") if match % 2 == 0 else ("B", "A")
            rows.append(dict(
                match_id=f"synthetic-{season}-{match}",
                match_date=pd.Timestamp(season, 3, match + 1),
                season=season, competition="J1", home_team=home, away_team=away,
                home_team_id=home, away_team_id=away, stadium="Other" if match == 2 else "Main",
                home_score=home_score, away_score=away_score,
                result=2 if home_score > away_score else 0 if home_score < away_score else 1,
            ))
    source = pd.DataFrame(rows)
    last_five = add_matchup_context_features(source)
    columns = (*DATASET_COLUMNS, *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS, *ELO_MOMENTUM_COLUMNS)
    positions = np.arange(len(source))
    dataset = pd.DataFrame({column: (positions * (number + 3)) % 37 + number / 10
                            for number, column in enumerate(columns)})
    for column in set(source.columns) & set(columns):
        dataset[column] = source[column].to_numpy(copy=True)
    for column in MATCHUP_CONTEXT_COLUMNS:
        dataset[column] = last_five[column].to_numpy(copy=True)
    dataset["home_elo"] = 1500.0
    dataset["away_elo"] = 1500.0
    dataset["elo_diff"] = positions * 3.0 + 0.25
    dataset["home_days_since_last_match"] = 20.0 + positions * 3
    dataset["away_days_since_last_match"] = 35.0 + positions * 2
    dataset["home_has_previous_match"] = positions % 2
    dataset["away_has_previous_match"] = (positions // 2) % 2
    dataset.index = pd.Index([11, 3, 11, 4, 0, 3] * 12, name="source_index")
    histories, feature_frames = {}, {}
    for window in EXPECTED_WINDOWS:
        generated = add_stadium_window_features(source, window)
        expected = dataset.loc[:, list(FIXED_FEATURES)].copy(deep=True)
        for column in STADIUM_WINDOW_COLUMNS:
            expected[column] = generated[column].to_numpy(copy=True)
        feature_frames[window] = expected.loc[:, list(EXPECTED_FEATURES)]
        # Misleading copies must never replace the five features from the base dataset.
        generated.loc[:, list(FIXED_FEATURES)] = -9999.0
        frames = [generated.iloc[:66], generated.iloc[66:69], generated.iloc[69:]]
        frames = [frame.iloc[::-1].copy(deep=True) for frame in frames]
        for frame in frames:
            frame.index = pd.Index([7] * len(frame), name="history_index")
        histories[window] = OngoingStadiumWindowHistory(*frames)
    return SimpleNamespace(dataset=dataset, histories=histories, features=feature_frames)


def _loader(histories, calls=None):
    def load(window):
        if calls is not None:
            calls.append(window)
        return histories[window]
    return load


@pytest.fixture(autouse=True)
def synthetic_loader(monkeypatch, synthetic):
    # Every test stays independent of local processed data and any external I/O.
    monkeypatch.setattr(tuning, "load_stadium_window_history_with_ongoing", _loader(synthetic.histories))


@pytest.fixture(scope="module")
def observed(synthetic):
    dataset = synthetic.dataset
    before = dataset.copy(deep=True)
    history_before = {window: [getattr(history, part).copy(deep=True) for part in PARTS]
                      for window, history in synthetic.histories.items()}
    fits, scaler_fits, predictions, constructors, split_inputs, accesses, loads, loss_labels = (
        [] for _ in range(8)
    )
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
        patch.setattr(tuning, "load_stadium_window_history_with_ongoing", _loader(synthetic.histories, loads))
        patch.setattr(tuning, "split_training_dataset", split)
        patch.setattr(tuning, "LogisticRegression", classifier)
        patch.setattr(Pipeline, "fit", fit)
        patch.setattr(StandardScaler, "fit", scaler_fit)
        patch.setattr(Pipeline, "predict_proba", predict)
        patch.setattr(tuning, "log_loss", loss)
        metrics = tuning.run_logistic_stadium_window_tuning(dataset)
    return dict(
        before=before, history_before=history_before, fits=fits, scaler_fits=scaler_fits,
        predictions=predictions, constructors=constructors, split_inputs=split_inputs,
        accesses=accesses, loads=loads, loss_labels=loss_labels, metrics=metrics,
    )


def test_exact_four_windows_and_eleven_features(observed):
    assert tuning.WINDOWS == EXPECTED_WINDOWS
    assert tuning.FEATURE_COLUMNS == EXPECTED_FEATURES
    assert len(EXPECTED_FEATURES) == 11
    assert tuple(observed["metrics"]) == tuple(observed["loads"]) == EXPECTED_WINDOWS
    assert len(observed["fits"]) == len(observed["scaler_fits"]) == len(observed["predictions"]) == 4


def test_identical_exact_classifier_arguments_with_penalty_omitted(observed):
    assert observed["constructors"] == [
        ((), dict(C=1.0, solver="lbfgs", max_iter=1000, random_state=0))
    ] * 4


def test_four_independent_two_step_pipelines_with_same_parameters(observed):
    models = [model for model, _, _ in observed["fits"]]
    assert len({id(model) for model in models}) == 4
    for model in models:
        assert isinstance(model, Pipeline)
        assert [name for name, _ in model.steps] == ["scaler", "logistic"]
        assert [type(step) for _, step in model.steps] == [StandardScaler, LogisticRegression]
        for step in ("scaler", "logistic"):
            assert model.named_steps[step].get_params() == models[0].named_steps[step].get_params()
        assert model.named_steps["logistic"].class_weight is None
    for step in ("scaler", "logistic"):
        assert len({id(model.named_steps[step]) for model in models}) == 4


def test_only_the_existing_24_columns_are_split_once(synthetic, observed):
    assert synthetic.dataset.shape == (72, 43)
    assert len(DATASET_COLUMNS) == 24
    assert len(observed["split_inputs"]) == 1
    assert_frame_equal(observed["split_inputs"][0], synthetic.dataset.loc[:, list(DATASET_COLUMNS)])


@pytest.mark.parametrize("partition", ["test", "reserved"])
def test_guarded_future_partitions_are_not_accessed(observed, partition):
    assert partition not in observed["accesses"]


def test_train_only_features_and_targets_align_by_id_with_duplicate_source_indexes(synthetic, observed):
    dataset = synthetic.dataset
    mask = dataset["season"].between(2015, 2023)
    assert not dataset.index.is_unique and dataset["match_id"].is_unique
    assert mask.sum() == 54
    for window, (_, frame, target) in zip(EXPECTED_WINDOWS, observed["fits"], strict=True):
        assert_frame_equal(frame.reset_index(drop=True), synthetic.features[window].loc[mask].reset_index(drop=True))
        assert_series_equal(target.reset_index(drop=True), dataset.loc[mask, "result"].reset_index(drop=True))


def test_scalers_fit_only_raw_train_values_and_train_statistics(synthetic, observed):
    mask = synthetic.dataset["season"].between(2015, 2023)
    for window, (scaler, frame), (model, _, _) in zip(
        EXPECTED_WINDOWS, observed["scaler_fits"], observed["fits"], strict=True,
    ):
        expected = synthetic.features[window].loc[mask]
        assert scaler is model.named_steps["scaler"]
        assert_frame_equal(frame.reset_index(drop=True), expected.reset_index(drop=True))
        assert scaler.n_samples_seen_ == len(expected)
        np.testing.assert_allclose(scaler.mean_, expected.mean().to_numpy())
        np.testing.assert_allclose(scaler.var_, expected.var(ddof=0).to_numpy())
        assert not np.allclose(scaler.mean_, synthetic.features[window].mean().to_numpy())


def test_predictions_use_validation_only_after_matching_shuffled_history_ids(synthetic, observed):
    mask = synthetic.dataset["season"].eq(2024)
    for window, (_, frame, _) in zip(EXPECTED_WINDOWS, observed["predictions"], strict=True):
        history = synthetic.histories[window].historical
        assert not history["match_id"].tolist() == synthetic.dataset["match_id"].iloc[:66].tolist()
        assert len(frame) == 6
        assert_frame_equal(frame.reset_index(drop=True), synthetic.features[window].loc[mask].reset_index(drop=True))


def test_only_six_stadium_columns_vary_and_five_base_columns_stay_raw(synthetic, observed):
    for records, mask in (
        (observed["fits"], synthetic.dataset["season"].between(2015, 2023)),
        (observed["predictions"], synthetic.dataset["season"].eq(2024)),
    ):
        expected = synthetic.dataset.loc[mask, list(FIXED_FEATURES)].reset_index(drop=True)
        for _, frame, _ in records:
            assert tuple(frame.columns) == EXPECTED_FEATURES
            assert_frame_equal(frame.loc[:, list(FIXED_FEATURES)].reset_index(drop=True), expected)
            assert frame[["home_days_since_last_match", "away_days_since_last_match"]].gt(14).all().all()
        stadium_frames = [frame.loc[:, list(STADIUM_WINDOW_COLUMNS)] for _, frame, _ in records]
        for first, second in zip(stadium_frames, stadium_frames[1:]):
            assert not first.equals(second)


def test_validation_changes_cannot_change_scaler_or_classifier_fits(synthetic, observed, monkeypatch):
    changed = synthetic.dataset.copy(deep=True)
    mask = changed["season"].eq(2024)
    changed.loc[mask, "result"] = (changed.loc[mask, "result"] + 1) % 3
    changed.loc[mask, "elo_diff"] += 500
    fitted = []
    original_fit = Pipeline.fit

    def fit(model, frame, target, **kwargs):
        fitted.append(model)
        return original_fit(model, frame, target, **kwargs)

    monkeypatch.setattr(Pipeline, "fit", fit)
    tuning.run_logistic_stadium_window_tuning(changed)
    for actual, (expected, _, _) in zip(fitted, observed["fits"], strict=True):
        for attribute in ("coef_", "intercept_"):
            np.testing.assert_array_equal(getattr(actual.named_steps["logistic"], attribute),
                                          getattr(expected.named_steps["logistic"], attribute))
        np.testing.assert_array_equal(actual.named_steps["scaler"].mean_, expected.named_steps["scaler"].mean_)


def test_class_order_and_three_valid_normalized_probabilities(observed):
    for (model, _, _), (_, frame, probabilities) in zip(observed["fits"], observed["predictions"], strict=True):
        np.testing.assert_array_equal(model.classes_, [0, 1, 2])
        assert probabilities.shape == (len(frame), 3)
        assert np.isfinite(probabilities).all()
        assert ((probabilities >= 0) & (probabilities <= 1)).all()
        np.testing.assert_allclose(probabilities.sum(axis=1), 1.0)


def test_missing_training_class_is_rejected_before_prediction(synthetic, monkeypatch):
    changed = synthetic.dataset.copy(deep=True)
    changed.loc[changed["season"].le(2023) & changed["result"].eq(1), "result"] = 0

    def forbidden_predict(*args, **kwargs):
        pytest.fail("A model without all three classes must not predict")

    monkeypatch.setattr(Pipeline, "predict_proba", forbidden_predict)
    with pytest.raises(ValueError, match=r"model\.classes_"):
        tuning.run_logistic_stadium_window_tuning(changed)


def test_validation_accuracy_and_log_loss_are_finite_and_use_correct_labels(synthetic, observed):
    target = synthetic.dataset.loc[synthetic.dataset["season"].eq(2024), "result"].to_numpy()
    assert observed["loss_labels"] == [[0, 1, 2]] * 4
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        assert np.isfinite(metrics.accuracy) and 0 <= metrics.accuracy <= 1
        assert metrics.accuracy == pytest.approx(np.mean(probabilities.argmax(axis=1) == target))
        assert np.isfinite(metrics.log_loss) and metrics.log_loss >= 0
        assert metrics.log_loss == pytest.approx(-np.log(probabilities[np.arange(len(target)), target]).mean())


def test_brier_sums_three_class_errors_then_averages_validation_rows(synthetic, observed):
    target = synthetic.dataset.loc[synthetic.dataset["season"].eq(2024), "result"].to_numpy()
    for metrics, (_, _, probabilities) in zip(observed["metrics"].values(), observed["predictions"], strict=True):
        expected = sum(sum((probability - int(label == actual)) ** 2
                           for label, probability in enumerate(row))
                       for actual, row in zip(target, probabilities, strict=True)) / len(target)
        assert np.isfinite(metrics.brier_score) and 0 <= metrics.brier_score <= 2
        assert metrics.brier_score == pytest.approx(expected)


def test_returns_only_four_metric_dataclasses_without_ranking_or_winner(observed):
    assert tuple(observed["metrics"]) == EXPECTED_WINDOWS
    for metrics in observed["metrics"].values():
        assert isinstance(metrics, FormLogisticMetrics)
        values = asdict(metrics)
        assert set(values) == {"accuracy", "log_loss", "brier_score"}
        assert all(isinstance(value, float) and np.isfinite(value) for value in values.values())


@pytest.mark.parametrize("perfect", [True, False])
def test_validation_performance_never_changes_the_four_candidates(synthetic, monkeypatch, perfect):
    loads, fitted, predicted = [], [], []
    target = synthetic.dataset.loc[synthetic.dataset["season"].eq(2024), "result"].to_numpy()
    original_fit = Pipeline.fit

    def fit(model, frame, labels, **kwargs):
        fitted.append(loads[-1])
        return original_fit(model, frame, labels, **kwargs)

    def predict(model, frame, **kwargs):
        predicted.append(loads[-1])
        probabilities = np.full((len(target), 3), 0.0001)
        chosen = target if perfect else (target + 1) % 3
        probabilities[np.arange(len(target)), chosen] = 0.9998
        return probabilities

    monkeypatch.setattr(tuning, "load_stadium_window_history_with_ongoing", _loader(synthetic.histories, loads))
    monkeypatch.setattr(Pipeline, "fit", fit)
    monkeypatch.setattr(Pipeline, "predict_proba", predict)
    metrics = tuning.run_logistic_stadium_window_tuning(synthetic.dataset)
    assert tuple(loads) == tuple(fitted) == tuple(predicted) == tuple(metrics) == EXPECTED_WINDOWS
    assert all(value.accuracy == float(perfect) for value in metrics.values())


@pytest.mark.parametrize("bad_id", [None, "", "   ", "duplicate"])
def test_base_missing_empty_or_duplicate_match_ids_are_rejected(synthetic, bad_id):
    changed = synthetic.dataset.copy(deep=True)
    changed.iloc[0, changed.columns.get_loc("match_id")] = (
        changed.iloc[1]["match_id"] if bad_id == "duplicate" else bad_id
    )
    with pytest.raises(ValueError, match="match_id"):
        tuning.run_logistic_stadium_window_tuning(changed)


@pytest.mark.parametrize("problem", ["null", "empty", "duplicate", "cross_source_duplicate", "fewer", "more", "different_set"])
def test_history_id_validity_count_and_set_must_match_base(synthetic, monkeypatch, problem):
    history = synthetic.histories[3]
    frames = [getattr(history, part).copy(deep=True) for part in PARTS]
    column = frames[0].columns.get_loc("match_id")
    if problem in ("null", "empty", "duplicate", "different_set"):
        replacement = {
            "null": None, "empty": "", "duplicate": frames[0].iloc[1]["match_id"],
            "different_set": "unmatched-history-id",
        }[problem]
        frames[0].iloc[0, column] = replacement
    elif problem == "cross_source_duplicate":
        frames[2].iloc[0, column] = frames[0].iloc[0]["match_id"]
    elif problem == "fewer":
        frames[2] = frames[2].iloc[:-1].copy(deep=True)
    else:
        extra = frames[2].iloc[:1].copy(deep=True)
        extra["match_id"] = "extra-history-id"
        frames[2] = pd.concat([frames[2], extra])
    histories = {**synthetic.histories, 3: OngoingStadiumWindowHistory(*frames)}
    monkeypatch.setattr(tuning, "load_stadium_window_history_with_ongoing", _loader(histories))
    with pytest.raises(ValueError):
        tuning.run_logistic_stadium_window_tuning(synthetic.dataset)


@pytest.mark.parametrize("window", [5, 8, 10])
def test_each_later_window_checks_its_own_history_ids(synthetic, monkeypatch, window):
    history = synthetic.histories[window]
    frames = [getattr(history, part).copy(deep=True) for part in PARTS]
    frames[0].iloc[0, frames[0].columns.get_loc("match_id")] = "different-match-id"
    histories = {**synthetic.histories, window: OngoingStadiumWindowHistory(*frames)}
    monkeypatch.setattr(tuning, "load_stadium_window_history_with_ongoing", _loader(histories))
    with pytest.raises(ValueError):
        tuning.run_logistic_stadium_window_tuning(synthetic.dataset)


def test_input_and_all_loaded_histories_remain_unchanged(synthetic, observed):
    assert_frame_equal(synthetic.dataset, observed["before"])
    for window, history in synthetic.histories.items():
        for part, before in zip(PARTS, observed["history_before"][window], strict=True):
            assert_frame_equal(getattr(history, part), before)


def test_repeat_calls_produce_identical_metrics(synthetic, observed):
    assert tuning.run_logistic_stadium_window_tuning(synthetic.dataset) == observed["metrics"]


def test_window_five_features_equal_existing_last_five_on_both_partitions(synthetic, observed):
    rename = {column: column.replace("_last5_", "_window_") for column in CURRENT_BEST_COLUMNS}
    position = EXPECTED_WINDOWS.index(5)
    for records, mask in (
        (observed["fits"], synthetic.dataset["season"].between(2015, 2023)),
        (observed["predictions"], synthetic.dataset["season"].eq(2024)),
    ):
        actual = records[position][1].reset_index(drop=True)
        expected = synthetic.dataset.loc[mask, list(CURRENT_BEST_COLUMNS)].rename(columns=rename)
        assert_frame_equal(actual, expected.reset_index(drop=True))


def test_window_five_metrics_reproduce_current_best_computed_dynamically(synthetic, observed, monkeypatch):
    monkeypatch.setattr(
        "src.modeling.logistic_final_ablation.FEATURE_SETS",
        {"current_best": CURRENT_BEST_COLUMNS},
    )
    current_best = run_logistic_final_ablation(synthetic.dataset)["current_best"]
    assert asdict(observed["metrics"][5]) == pytest.approx(asdict(current_best), abs=1e-12)
