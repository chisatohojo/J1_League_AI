import hashlib
import numpy as np
import pandas as pd
import pytest

from src.collect.teams import load_team_master
from src.modeling.final_2026_lockbox_evaluation import (
    CLASS_ORDER, FEATURE_A, FEATURE_B, FROZEN_PREDICTIONS_SHA256,
    _elo_features, _j1, _rest_features, _target_elo_features,
    load_frozen_lockbox_target, metrics, preflight_inputs,
    validate_live_2026_inputs,
)


def test_frozen_input_preflight_and_feature_contract():
    inputs=preflight_inputs()
    assert inputs["2025_j1"]["rows"] == 380
    assert inputs["2025_cup"]["rows"] == 56
    assert inputs["2025_emperor"]["rows"] == 41
    assert inputs["2026_cup"]["rows"] == 4
    assert inputs["2026_emperor"]["rows"] == 19
    assert inputs["hyakunen"]["rows"] == 200
    assert (inputs["live_completed"]["rows"]
            + inputs["live_completed"]["scheduled_rows"]
            + inputs["live_completed"]["candidate_rows"] == 380)
    assert inputs["frozen_target"]["rows"] == 70
    assert inputs["schedule"]["rows"] == 380
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


def test_preflight_rejects_wrong_2025_training_count(tmp_path):
    wrong = tmp_path / "2025_j1.csv"
    wrong.write_text("match_id\n1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="2025_j1"):
        preflight_inputs({"2025_j1": wrong})


def _live_files(tmp_path, completed_count=80):
    tmp_path.mkdir(parents=True, exist_ok=True)
    clubs = [f"club-{number:02d}" for number in range(20)]
    rows = []
    fixtures = [(home, away) for home in clubs for away in clubs if away != home]
    for index, (home, away) in enumerate(fixtures):
        completed = index < completed_count
        rows.append({
            "match_id": str(10000 + index) if completed else "",
            "season": "2026", "round": str(index // 10 + 1),
            "match_date": f"2026-08-{index % 28 + 1:02d}",
            "home_team": home, "away_team": away,
            "home_score": "1" if completed else "",
            "away_score": "0" if completed else "",
            "result": "2" if completed else "",
            "fixture_key": f"j1_2026_2027:{home}:{away}",
            "status": "completed" if completed else "scheduled",
            "competition_key": "j1_2026_2027", "competition": "Ｊ１",
            "stage": "full_season",
        })
    schedule = pd.DataFrame(rows, dtype="string")
    completed = schedule.loc[schedule.status.eq("completed")].reset_index(drop=True)
    schedule_path, completed_path = tmp_path / "schedule.csv", tmp_path / "completed.csv"
    schedule.to_csv(schedule_path, index=False)
    completed.to_csv(completed_path, index=False)
    return schedule, completed, schedule_path, completed_path


def _prediction_file(tmp_path, completed, positions):
    frozen = completed.iloc[positions]
    predictions = frozen[["match_id", "match_date", "home_team", "away_team", "result"]].rename(
        columns={"result": "actual_class"}
    )
    predictions["model_a_p_away"] = "0.3"
    path = tmp_path / "predictions.csv"
    predictions.to_csv(path, index=False)
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), predictions


def test_live_completed_count_can_grow_from_70_to_80(tmp_path):
    _, _, schedule_70, completed_70 = _live_files(tmp_path / "at-70", 70)
    schedule, completed, schedule_80, completed_80 = _live_files(tmp_path / "at-80", 80)
    assert len(validate_live_2026_inputs(schedule_70, completed_70)[1]) == 70
    assert len(validate_live_2026_inputs(schedule_80, completed_80)[1]) == 80
    assert len(completed) + int(schedule.status.ne("completed").sum()) == 380


def test_saved_ids_freeze_70_and_exclude_ten_new_live_matches(tmp_path):
    _, completed, schedule_path, completed_path = _live_files(tmp_path, 80)
    # Deliberately omit the first ten live rows: selection by current ordering would fail.
    prediction_path, digest, predictions = _prediction_file(tmp_path, completed, list(range(10, 80)))
    paths = {
        "live_completed": completed_path, "schedule": schedule_path,
        "frozen_predictions": prediction_path,
    }
    inputs = preflight_inputs(paths, expected_prediction_sha256=digest)
    target = load_frozen_lockbox_target(
        completed_path, prediction_path, expected_prediction_sha256=digest,
    )
    assert inputs["live_completed"]["rows"] == 80
    assert len(target) == 70
    assert target.match_id.tolist() == predictions.match_id.tolist()
    assert set(completed.iloc[:10].match_id).isdisjoint(target.match_id)


def test_live_duplicate_or_malformed_completed_data_still_fails(tmp_path):
    schedule, _, schedule_path, completed_path = _live_files(tmp_path, 80)
    schedule.loc[1, "fixture_key"] = schedule.loc[0, "fixture_key"]
    schedule.to_csv(schedule_path, index=False)
    with pytest.raises(ValueError, match="fixture_key"):
        validate_live_2026_inputs(schedule_path, completed_path)

    _, completed, schedule_path, completed_path = _live_files(tmp_path / "bad-result", 80)
    completed.loc[0, "result"] = "0"
    completed.to_csv(completed_path, index=False)
    with pytest.raises(ValueError, match="completed_matches.csv|score/result"):
        validate_live_2026_inputs(schedule_path, completed_path)


def test_real_frozen_prediction_artifact_digest_and_ids_are_immutable():
    inputs = preflight_inputs()
    assert inputs["frozen_predictions"]["sha256"] == FROZEN_PREDICTIONS_SHA256
    assert len(inputs["frozen_target"]["match_ids"]) == 70
    assert inputs["frozen_target"]["match_ids"][-1] == "34584"


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
    target = load_frozen_lockbox_target(
        inputs["live_completed"]["path"], inputs["frozen_predictions"]["path"]
    )
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
