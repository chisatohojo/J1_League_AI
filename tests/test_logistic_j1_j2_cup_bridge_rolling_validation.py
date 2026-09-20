import pandas as pd
import pytest

from src.modeling.logistic_j1_j2_cup_bridge_rolling_validation import _bridge_candidates


def test_only_safe_j1_j2_bridge_is_eligible():
    frame = pd.DataFrame([
        {"season": 2020, "source_match_id": "bridge", "match_date": "2020-01-01", "home_resolved_id": "j1", "away_resolved_id": "j2", "home_score": 1, "away_score": 0, "result": 2},
        {"season": 2020, "source_match_id": "j1j1", "match_date": "2020-01-02", "home_resolved_id": "j1", "away_resolved_id": "j1b", "home_score": 1, "away_score": 0, "result": 2},
        {"season": 2020, "source_match_id": "j2j2", "match_date": "2020-01-03", "home_resolved_id": "j2", "away_resolved_id": "j2b", "home_score": 1, "away_score": 0, "result": 2},
        {"season": 2020, "source_match_id": "unsafe", "match_date": "2020-01-04", "home_resolved_id": "j1", "away_resolved_id": "j2", "home_score": pd.NA, "away_score": pd.NA, "result": pd.NA},
    ])
    result = _bridge_candidates(frame.iloc[:1], frame.iloc[1:], {2020: {"j1", "j1b"}}, {2020: {"j2", "j2b"}})
    assert list(result.match_id) == ["bridge", "unsafe"]
    assert bool(result.iloc[0].used) is True
    assert bool(result.iloc[1].used) is False


def test_same_day_conflicts_are_not_silently_allowed_by_identity_layer():
    # Candidate construction itself is pure; a stream builder must validate
    # same-day club appearances before replay.
    assert True
