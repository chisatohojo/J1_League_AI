import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

import src.modeling.starter_df_evaluation as evaluation
from src.features.elo import EloRatings
from src.modeling.player_workload_evaluation import _add_elo as known_good_add_elo
from src.modeling.starter_df_evaluation import (
    CLASS_ORDER,
    EXISTING_MATCHED_BASELINE_REUSED,
    EXPECTED_COUNTS,
    FEATURE_COLUMNS,
    FEATURE_PATH,
    FEATURE_SHA256,
    FOLDS,
    KNOWN_A_Y_LL,
    KNOWN_A_Y_POOLED,
    S0_FEATURES,
    S1_FEATURES,
    FoldResult,
    StarterDFEvaluationError,
    _add_eligibility,
    _add_elo,
    _align_predictions,
    _assert_a_y_sanity,
    _assert_same_labels,
    _assert_same_match_ids,
    _fit,
    _fold_frames,
    _load_inputs,
    _load_target_matches,
    _merge_inputs,
    _metrics,
    _operational_probabilities,
    _pooled_metrics,
    _read_feature_artifact,
    _validate_exact_schema,
    _validate_feature_sha,
    _validate_frozen_counts,
    _validate_probabilities,
    _validate_target_feature_identity,
    frozen_decision,
)


@pytest.fixture(scope="module")
def artifact_parts():
    matches = _load_target_matches()
    features = _read_feature_artifact()
    _validate_target_feature_identity(matches, features)
    _validate_exact_schema(features)
    data = _add_eligibility(_merge_inputs(matches, features))
    return matches, features, data


def _elo_fixture():
    return pd.DataFrame(
        [
            {
                "match_id": "2",
                "match_date": pd.Timestamp("2020-01-01"),
                "home_team_id": "d",
                "away_team_id": "c",
                "result": 0,
                "elo_diff": 999.0,
            },
            {
                "match_id": "1",
                "match_date": pd.Timestamp("2020-01-01"),
                "home_team_id": "a",
                "away_team_id": "b",
                "result": 2,
                "elo_diff": 999.0,
            },
            {
                "match_id": "3",
                "match_date": pd.Timestamp("2020-01-02"),
                "home_team_id": "a",
                "away_team_id": "c",
                "result": 1,
                "elo_diff": 999.0,
            },
        ]
    )


def _feature_row(*, home_available=True, away_available=True):
    row = {"match_date": "2020-02-02"}
    for side, available in (
        ("home", home_available),
        ("away", away_available),
    ):
        row[f"{side}_starter_df_available"] = available
        row[f"{side}_previous_match_id"] = f"{side}-previous" if available else np.nan
        row[f"{side}_previous_match_date"] = (
            "2020-02-01" if available else np.nan
        )
        row[f"{side}_previous_match_starter_df_count"] = (
            4 if available else np.nan
        )
    return row


def _model_frames():
    train = pd.DataFrame(
        {
            "elo_diff": np.linspace(-2, 2, 9),
            "home_previous_match_starter_df_count": [3, 4, 5] * 3,
            "away_previous_match_starter_df_count": [5, 4, 3] * 3,
            "result": [0, 1, 2] * 3,
        }
    )
    validation = pd.DataFrame(
        {
            "elo_diff": [-1.0, 1.0],
            "home_previous_match_starter_df_count": [3, 5],
            "away_previous_match_starter_df_count": [5, 3],
            "result": [0, 2],
        }
    )
    return train, validation


def _fold_result(s0_ll, s1_ll):
    def metrics(ll):
        return {"accuracy": 0.0, "log_loss": ll, "brier": 1.0, "count": 1}

    return FoldResult(
        season=2020,
        train_total=1,
        train_eligible=1,
        validation_total=1,
        validation_eligible=1,
        s0=metrics(s0_ll),
        s1=metrics(s1_ll),
        delta_s1_minus_s0={
            "accuracy": 0.0,
            "log_loss": s1_ll - s0_ll,
            "brier": 0.0,
        },
        a_y=metrics(1.0),
        operational_s1=metrics(1.0),
    )


def test_01_class_order_is_exact():
    np.testing.assert_array_equal(CLASS_ORDER, np.array([0, 1, 2]))


def test_02_project_uniform_multiclass_brier_is_two_thirds():
    probabilities = np.full((3, 3), 1 / 3)
    assert _metrics(np.array([0, 1, 2]), probabilities)["brier"] == pytest.approx(
        2 / 3
    )


def test_03_elo_replay_exactly_reuses_known_good_implementation():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff.sort_index()
    expected = known_good_add_elo(rows).set_index("match_id").elo_diff.sort_index()
    pd.testing.assert_series_equal(actual, expected)


def test_04_legacy_and_stored_elo_are_not_used():
    rows = _elo_fixture()
    actual = _add_elo(rows).set_index("match_id").elo_diff
    assert not actual.eq(999.0).any()
    legacy = EloRatings(["a", "b", "c", "d"])
    legacy.update("a", "b", 2)
    legacy.update("d", "c", 0)
    legacy_diff = (
        legacy.pre_match("a", "c").home_rating
        - legacy.pre_match("a", "c").away_rating
    )
    assert legacy_diff == 0.0
    assert actual.loc["3"] != legacy_diff


def test_05_same_date_elo_is_conservatively_batched_and_deterministic():
    rows = _elo_fixture()
    first = _add_elo(rows).set_index("match_id").elo_diff
    second = _add_elo(rows.sample(frac=1, random_state=4)).set_index(
        "match_id"
    ).elo_diff
    assert first.loc["1"] == first.loc["2"] == 0.0
    pd.testing.assert_series_equal(first.sort_index(), second.sort_index())


def test_06_feature_artifact_sha_mismatch_hard_fails_before_fit(tmp_path):
    assert _validate_feature_sha(FEATURE_PATH) == FEATURE_SHA256
    changed = tmp_path / "features.csv"
    changed.write_text("changed", encoding="utf-8")
    with pytest.raises(StarterDFEvaluationError, match="SHA-256 mismatch"):
        _validate_feature_sha(changed)


def test_07_feature_artifact_schema_is_exact_ordered_13_columns(artifact_parts):
    _, features, _ = artifact_parts
    assert tuple(features.columns) == FEATURE_COLUMNS
    assert len(FEATURE_COLUMNS) == 13
    reordered = features.loc[:, list(FEATURE_COLUMNS[::-1])]
    with pytest.raises(StarterDFEvaluationError, match="ordered 13 columns"):
        _validate_exact_schema(reordered)


def test_08_target_feature_identity_is_exact_by_match_id(artifact_parts):
    matches, features, _ = artifact_parts
    _validate_target_feature_identity(matches, features)
    changed = features.copy()
    changed.loc[0, "home_team_id"] = "wrong-team"
    with pytest.raises(StarterDFEvaluationError, match="home_team_id"):
        _validate_target_feature_identity(matches, changed)


def test_09_available_side_requires_valid_prior_id_date_and_integer_df_count():
    assert _add_eligibility(pd.DataFrame([_feature_row()])).primary_eligible.iloc[0]
    invalid = (
        ("home_previous_match_id", np.nan),
        ("home_previous_match_date", "2020-02-02"),
        ("home_previous_match_date", "not-a-date"),
        ("home_previous_match_starter_df_count", np.nan),
        ("home_previous_match_starter_df_count", 3.5),
        ("home_previous_match_starter_df_count", 1),
        ("home_previous_match_starter_df_count", 7),
    )
    for field, value in invalid:
        row = _feature_row()
        row[field] = value
        with pytest.raises(StarterDFEvaluationError, match="Available home"):
            _add_eligibility(pd.DataFrame([row]))


def test_10_unavailable_side_requires_all_prior_fields_null():
    row = _feature_row(home_available=False)
    assert not _add_eligibility(pd.DataFrame([row])).primary_eligible.iloc[0]
    for field, value in (
        ("home_previous_match_id", "unexpected"),
        ("home_previous_match_date", "2020-02-01"),
        ("home_previous_match_starter_df_count", 4),
    ):
        broken = _feature_row(home_available=False)
        broken[field] = value
        with pytest.raises(StarterDFEvaluationError, match="Unavailable home"):
            _add_eligibility(pd.DataFrame([broken]))


def test_11_primary_eligibility_requires_both_sides_available():
    rows = pd.DataFrame(
        [
            _feature_row(),
            _feature_row(home_available=False),
            _feature_row(away_available=False),
        ]
    )
    assert _add_eligibility(rows).primary_eligible.tolist() == [True, False, False]


def test_12_one_side_only_available_is_structurally_valid_but_ineligible():
    result = _add_eligibility(
        pd.DataFrame([_feature_row(home_available=True, away_available=False)])
    )
    assert bool(result.home_starter_df_available.iloc[0])
    assert not bool(result.away_starter_df_available.iloc[0])
    assert not bool(result.primary_eligible.iloc[0])


def test_13_all_frozen_fold_counts_are_rederived(artifact_parts):
    _, _, data = artifact_parts
    _validate_frozen_counts(data)
    assert EXPECTED_COUNTS == {
        2020: (1530, 1485, 306, 297),
        2021: (1836, 1782, 380, 370),
        2022: (2216, 2152, 306, 297),
        2023: (2522, 2449, 306, 297),
        2024: (2828, 2746, 380, 370),
    }
    for season in FOLDS:
        frames = _fold_frames(data, season)
        assert (
            len(frames["train_all"]),
            len(frames["train"]),
            len(frames["validation_all"]),
            len(frames["validation"]),
        ) == EXPECTED_COUNTS[season]


def test_14_primary_pooled_validation_count_is_1631(artifact_parts):
    _, _, data = artifact_parts
    assert sum(len(_fold_frames(data, year)["validation"]) for year in FOLDS) == 1631


def test_15_operational_pooled_validation_count_is_1678(artifact_parts):
    _, _, data = artifact_parts
    assert (
        sum(len(_fold_frames(data, year)["validation_all"]) for year in FOLDS)
        == 1678
    )


def test_16_s0_s1_training_ids_must_be_exactly_equal():
    _assert_same_match_ids(["a", "b"], ["b", "a"], context="train")
    with pytest.raises(StarterDFEvaluationError, match="matched IDs differ"):
        _assert_same_match_ids(["a", "b"], ["a", "c"], context="train")


def test_17_s0_s1_validation_ids_must_be_exactly_equal():
    _assert_same_match_ids(["v1", "v2"], ["v2", "v1"], context="validation")
    with pytest.raises(StarterDFEvaluationError, match="matched IDs differ"):
        _assert_same_match_ids(["v1", "v2"], ["v1"], context="validation")


def test_18_s0_s1_labels_must_be_exactly_equal():
    _assert_same_labels([0, 1, 2], [0, 1, 2], context="fixture")
    with pytest.raises(StarterDFEvaluationError, match="matched labels differ"):
        _assert_same_labels([0, 1, 2], [0, 2, 1], context="fixture")


def test_19_scaler_and_logistic_fit_training_rows_only(monkeypatch):
    train, validation = _model_frames()
    scaler_fit = StandardScaler.fit
    logistic_fit = LogisticRegression.fit
    observed = []

    def spy_scaler(self, x, y=None, **kwargs):
        observed.append(("scaler", len(x)))
        return scaler_fit(self, x, y, **kwargs)

    def spy_logistic(self, x, y, **kwargs):
        observed.append(("logistic", len(x)))
        return logistic_fit(self, x, y, **kwargs)

    monkeypatch.setattr(StandardScaler, "fit", spy_scaler)
    monkeypatch.setattr(LogisticRegression, "fit", spy_logistic)
    _fit(train, validation, S0_FEATURES)
    assert observed == [("scaler", 9), ("logistic", 9)]


def test_20_s0_feature_is_exactly_elo_diff():
    assert S0_FEATURES == ("elo_diff",)
    train, validation = _model_frames()
    _fit(train, validation, S0_FEATURES)
    with pytest.raises(StarterDFEvaluationError, match="Unfrozen"):
        _fit(train, validation, ("elo_diff", "home_previous_match_starter_df_count"))


def test_21_s1_features_and_order_are_exact():
    assert S1_FEATURES == (
        "elo_diff",
        "home_previous_match_starter_df_count",
        "away_previous_match_starter_df_count",
    )
    train, validation = _model_frames()
    _fit(train, validation, S1_FEATURES)
    with pytest.raises(StarterDFEvaluationError, match="Unfrozen"):
        _fit(train, validation, tuple(reversed(S1_FEATURES)))


def test_22_probability_validation_rejects_shape_range_nan_and_bad_sum():
    _validate_probabilities(np.eye(3))
    for invalid in (
        np.array([[0.5, 0.5]]),
        np.array([[0.5, 0.5, np.nan]]),
        np.array([[1.1, -0.1, 0.0]]),
        np.array([[0.2, 0.2, 0.2]]),
    ):
        with pytest.raises(StarterDFEvaluationError):
            _validate_probabilities(invalid)


def test_23_operational_fallback_uses_same_match_a_y_by_id():
    a_y = np.array(
        [[0.1, 0.2, 0.7], [0.2, 0.3, 0.5], [0.4, 0.3, 0.3]]
    )
    s1 = np.array([[0.8, 0.1, 0.1], [0.1, 0.8, 0.1]])
    result = _operational_probabilities(
        a_y,
        ["m2", "m1", "m3"],
        s1,
        ["m3", "m1"],
        ["m1", "m2", "m3"],
        ["m1", "m3"],
    )
    np.testing.assert_array_equal(
        result,
        np.array([[0.1, 0.8, 0.1], [0.1, 0.2, 0.7], [0.8, 0.1, 0.1]]),
    )


def test_24_bad_prediction_ids_or_incomplete_rows_hard_fail():
    probabilities = np.array([[0.2, 0.3, 0.5], [0.4, 0.3, 0.3]])
    for source, target in (
        (["a", "a"], ["a", "b"]),
        (["a", "b"], ["a", "c"]),
        (["a", "b"], ["a"]),
    ):
        with pytest.raises(StarterDFEvaluationError):
            _align_predictions(probabilities, source, target)
    with pytest.raises(StarterDFEvaluationError, match="source IDs differ"):
        _align_predictions(probabilities[:1], ["a", "b"], ["a", "b"])
    with pytest.raises(StarterDFEvaluationError, match="IDs are invalid"):
        _operational_probabilities(
            probabilities,
            ["a", "b"],
            np.array([[0.2, 0.3, 0.5]]),
            ["b"],
            ["a", "b"],
            ["a"],
        )


def test_25_pooled_metrics_use_concatenated_oof_predictions():
    targets = [np.array([0]), np.array([0, 0, 0])]
    probabilities = [
        np.array([[0.01, 0.49, 0.50]]),
        np.array([[0.90, 0.05, 0.05]] * 3),
    ]
    pooled = _pooled_metrics(targets, probabilities)
    simple_mean = np.mean(
        [_metrics(y, p)["log_loss"] for y, p in zip(targets, probabilities)]
    )
    expected = _metrics(np.concatenate(targets), np.concatenate(probabilities))
    assert pooled == expected
    assert pooled["log_loss"] != pytest.approx(simple_mean)


def test_26_a_y_mismatch_blocks_matched_formal_evaluation(monkeypatch):
    assert KNOWN_A_Y_LL == {
        2020: 1.023119734659012,
        2021: 1.0253437210487792,
        2022: 1.0940186385371449,
        2023: 1.0604285568595655,
        2024: 1.079241181120235,
    }
    assert KNOWN_A_Y_POOLED == {
        "accuracy": 0.466626936829559,
        "log_loss": 1.056065401323764,
        "brier": 0.6357323419292724,
    }
    exact = {
        "contexts": [
            {"season": season, "metrics": {"log_loss": value}}
            for season, value in KNOWN_A_Y_LL.items()
        ],
        "pooled": KNOWN_A_Y_POOLED,
    }
    _assert_a_y_sanity(exact)
    wrong = {"contexts": [dict(item) for item in exact["contexts"]], "pooled": exact["pooled"]}
    wrong["contexts"][0] = {
        "season": 2020,
        "metrics": {"log_loss": KNOWN_A_Y_LL[2020] + 1e-6},
    }
    with pytest.raises(StarterDFEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        _assert_a_y_sanity(wrong)

    marker = {"matched_called": False}
    monkeypatch.setattr(evaluation, "_validate_feature_sha", lambda *args: None)
    monkeypatch.setattr(evaluation, "_load_inputs", lambda *args: pd.DataFrame())
    monkeypatch.setattr(evaluation, "_add_eligibility", lambda frame: frame)
    monkeypatch.setattr(evaluation, "_validate_frozen_counts", lambda frame: None)
    monkeypatch.setattr(evaluation, "_add_elo", lambda frame: frame)
    monkeypatch.setattr(evaluation, "_evaluate_a_y", lambda frame: {"bad": True})

    def reject(_a_y):
        raise StarterDFEvaluationError("BLOCKED_REFERENCE_MISMATCH")

    def forbidden(_data, _a_y):
        marker["matched_called"] = True
        return {}

    monkeypatch.setattr(evaluation, "_assert_a_y_sanity", reject)
    monkeypatch.setattr(evaluation, "_evaluate_matched_after_sanity", forbidden)
    with pytest.raises(StarterDFEvaluationError, match="BLOCKED_REFERENCE_MISMATCH"):
        evaluation.evaluate_starter_df()
    assert not marker["matched_called"]


def test_27_decision_continue_starter_df_lane():
    folds = [_fold_result(1.0, 0.9 if index < 3 else 1.1) for index in range(5)]
    pooled = {
        "s0": {"log_loss": 1.0, "brier": 1.0},
        "s1": {"log_loss": 0.9, "brier": 0.9},
    }
    assert frozen_decision(folds, pooled) == "CONTINUE_STARTER_DF_LANE"


def test_28_decision_close_retrospective_lane():
    folds = [_fold_result(1.0, 0.9 if index < 2 else 1.1) for index in range(5)]
    pooled = {
        "s0": {"log_loss": 1.0, "brier": 1.0},
        "s1": {"log_loss": 1.1, "brier": 1.1},
    }
    assert frozen_decision(folds, pooled) == "CLOSE_RETROSPECTIVE_LANE"


def test_29_decision_inconclusive_without_tuning():
    folds = [_fold_result(1.0, 0.9 if index < 3 else 1.1) for index in range(5)]
    pooled = {
        "s0": {"log_loss": 1.0, "brier": 1.0},
        "s1": {"log_loss": 0.9, "brier": 1.1},
    }
    assert frozen_decision(folds, pooled) == "INCONCLUSIVE_NO_TUNING"


def test_30_existing_matched_baseline_reference_reused_remains_no():
    assert EXISTING_MATCHED_BASELINE_REUSED is False
    assert "substitution" not in " ".join(S1_FEATURES)
    assert _load_inputs is not None
