import math

import pandas as pd
import pytest

from src.features.elo import EloRatings, K_FACTOR
from src.modeling.logistic_elo_k_tuning import K_CANDIDATES, FEATURE_COLUMNS, run_logistic_elo_k_tuning


def test_default_and_custom_k_factor():
    assert K_FACTOR == 20.0
    assert EloRatings(["a", "b"]).update("a", "b", 2).after.home_rating == pytest.approx(1510)
    assert EloRatings(["a", "b"], k_factor=10).update("a", "b", 2).after.home_rating == pytest.approx(1505)


@pytest.mark.parametrize("value", [True, False, 0, -1, float("nan"), float("inf"), -float("inf")])
def test_invalid_k_factor_rejected(value):
    with pytest.raises(ValueError):
        EloRatings(["a", "b"], k_factor=value)


def test_k_candidates_and_features_are_fixed():
    assert K_CANDIDATES == (10.0, 15.0, 20.0, 30.0, 40.0)
    assert len(FEATURE_COLUMNS) == 11


def test_k20_replay_matches_existing_elo_history():
    from src.features.elo_history import load_elo_history_with_ongoing
    from src.modeling.logistic_elo_k_tuning import _replay
    history = load_elo_history_with_ongoing()
    frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    replay = _replay(frames, 20.0)
    existing = pd.concat([frame.loc[:, ["match_id", "home_elo", "away_elo", "elo_diff"]] for frame in frames], ignore_index=True)
    pd.testing.assert_frame_equal(replay, existing, check_dtype=False)


def test_k20_matches_current_logistic_best_on_real_data():
    from src.features.training_dataset_full import load_training_dataset_full
    from src.modeling.logistic_final_ablation import run_logistic_final_ablation
    result = run_logistic_elo_k_tuning(load_training_dataset_full())
    reference = run_logistic_final_ablation(load_training_dataset_full())["current_best"]
    assert set(result) == set(K_CANDIDATES)
    assert result[20.0] == reference
    for metrics in result.values():
        assert 0 <= metrics.accuracy <= 1
        assert math.isfinite(metrics.log_loss) and metrics.log_loss >= 0
        assert math.isfinite(metrics.brier_score) and metrics.brier_score >= 0
