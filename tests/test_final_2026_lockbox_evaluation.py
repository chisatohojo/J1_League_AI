import numpy as np
import pandas as pd
import pytest

from src.collect.teams import load_team_master
from src.modeling.final_2026_lockbox_evaluation import (
    CLASS_ORDER, FEATURE_A, FEATURE_B, _elo_features, _j1, _rest_features,
    _target_elo_features, metrics, preflight_inputs,
)


def test_frozen_input_preflight_and_feature_contract():
    inputs=preflight_inputs()
    assert inputs["2026_cup"]["rows"] == 4
    assert inputs["2026_emperor"]["rows"] == 19
    assert inputs["target"]["rows"] == 70
    assert FEATURE_A == ("elo_diff",)
    assert FEATURE_B == ("elo_diff", "home_domestic_days_since_last_competitive_match",
                         "away_domestic_days_since_last_competitive_match",
                         "home_domestic_has_previous_competitive_match",
                         "away_domestic_has_previous_competitive_match")
def test_project_multiclass_brier_scale():
    p=np.full((1,3),1/3); y=np.array([0])
    assert metrics(y,p)["brier"] == pytest.approx(2/3)


def test_preflight_does_not_predict():
    assert "probabilities" not in preflight_inputs()


def _matches(rows):
    frame = pd.DataFrame(rows, columns=(
        "match_id", "match_date", "home_team_id", "away_team_id", "result"
    ))
    frame["match_date"] = pd.to_datetime(frame.match_date)
    return frame


def test_target_rest_uses_only_completed_previous_dates():
    history = _matches([("h", "2026-08-01", "a", "b", 2)])
    targets = _matches([
        ("m1", "2026-08-04", "a", "c", 0),
        ("m2", "2026-08-06", "c", "a", 2),
        ("m3", "2026-08-09", "a", "b", 1),
    ])
    domestic = _matches([])
    original_history = history.copy(deep=True)
    original_targets = targets.copy(deep=True)
    result = _rest_features(history, domestic, targets, include_completed_targets=True).set_index("match_id")
    assert result.loc["m1", "home_domestic_days_since_last_competitive_match"] == 3
    assert result.loc["m1", "away_domestic_has_previous_competitive_match"] == 0
    assert result.loc["m2", "away_domestic_days_since_last_competitive_match"] == 2
    assert result.loc["m3", "home_domestic_days_since_last_competitive_match"] == 3
    pd.testing.assert_frame_equal(history, original_history)
    pd.testing.assert_frame_equal(targets, original_targets)


def test_same_date_target_rest_is_bucketed_and_deterministic():
    history = _matches([("h", "2026-08-01", "a", "b", 2)])
    targets = _matches([
        ("m2", "2026-08-04", "c", "a", 1),
        ("m1", "2026-08-04", "a", "d", 0),
        ("m3", "2026-08-05", "a", "b", 2),
    ])  # No kickoff-time field: the whole date must be one bucket.
    def run(frame):
        return _rest_features(history, _matches([]), frame,
                              include_completed_targets=True).set_index("match_id").sort_index()
    result = run(targets)
    assert result.loc["m1", "home_domestic_days_since_last_competitive_match"] == 3
    assert result.loc["m2", "away_domestic_days_since_last_competitive_match"] == 3
    assert result.loc["m3", "home_domestic_days_since_last_competitive_match"] == 1
    pd.testing.assert_frame_equal(result, run(targets.iloc[::-1].copy()))


def test_same_kickoff_elo_reads_all_before_bucket_update():
    history = _matches([("h", "2026-08-01", "a", "b", 2)])
    targets = _matches([
        ("m2", "2026-08-04", "a", "d", 2),
        ("m1", "2026-08-04", "a", "c", 0),
        ("m3", "2026-08-05", "a", "b", 1),
    ])
    targets["kickoff_time"] = ["19:00", "19:00", "19:00"]
    roster = {"a", "b", "c", "d"}
    result = _target_elo_features(history, targets, roster).set_index("match_id")
    assert result.loc["m1", "elo_diff"] == result.loc["m2", "elo_diff"]
    assert result.loc["m3", "elo_diff"] != result.loc["m1", "elo_diff"]
    pd.testing.assert_frame_equal(
        result.sort_index(),
        _target_elo_features(history, targets.iloc[::-1].copy(), roster).set_index("match_id").sort_index(),
    )
    sequential = _elo_features(pd.concat([history, targets], ignore_index=True), roster).set_index("match_id")
    assert sequential.loc["m1", "elo_diff"] != sequential.loc["m2", "elo_diff"]


def test_future_elo_history_is_rejected():
    future = _matches([("h", "2026-08-05", "a", "b", 2)])
    targets = _matches([("m", "2026-08-04", "a", "c", 0)])
    with pytest.raises(ValueError, match="precede"):
        _target_elo_features(future, targets, {"a", "b", "c"})


def test_frozen_target_and_training_row_contract_without_fit():
    inputs = preflight_inputs()
    target = pd.read_csv(inputs["target"]["path"])
    assert len(target) == 70
    assert target.match_id.is_unique
    assert target.kickoff_time.notna().all()
    assert len(_j1("data/processed/jleague", load_team_master())) == 3588
    assert CLASS_ORDER == (0, 1, 2)
    assert FEATURE_A == ("elo_diff",)
    assert FEATURE_B == (
        "elo_diff", "home_domestic_days_since_last_competitive_match",
        "away_domestic_days_since_last_competitive_match",
        "home_domestic_has_previous_competitive_match",
        "away_domestic_has_previous_competitive_match",
    )
