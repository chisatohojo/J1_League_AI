import pandas as pd
import pytest

from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS
from src.features import training_dataset_match_stats as module


def _base():
    return pd.DataFrame({
        "match_id": ["2", "1"], "match_date": ["2024-01-02", "2024-01-01"],
        "season": [2024, 2024], "home_team_id": ["h2", "h1"],
        "away_team_id": ["a2", "a1"], "result": [2, 0],
    })


def _history():
    return pd.DataFrame({
        "match_id": ["1", "2"], "match_date": ["2024-01-01", "2024-01-02"],
        "season": [2024, 2024], "home_team_id": ["h1", "h2"],
        "away_team_id": ["a1", "a2"],
        **{column: [0, 1] for column in MATCH_STATS_FORM_COLUMNS},
    })


def test_joins_by_match_id_preserves_dataset_order_and_schema(monkeypatch):
    base = _base()
    history = _history()
    monkeypatch.setattr(module, "load_training_dataset_with_context", lambda *a, **k: base.copy(deep=True))
    monkeypatch.setattr(module, "load_match_stats_form_history", lambda **k: history.copy(deep=True))
    result = module.load_training_dataset_with_match_stats()
    assert result["match_id"].tolist() == ["2", "1"]
    assert list(result.columns) == list(base.columns) + list(MATCH_STATS_FORM_COLUMNS)
    assert result.loc[:, list(MATCH_STATS_FORM_COLUMNS)].dtypes.eq("int64").all()
    assert not any(c in result.columns for c in ("home_shots", "away_shots", "home_ck", "away_ck", "home_fk", "away_fk"))
    assert base.equals(_base())


def test_metadata_mismatch_is_rejected(monkeypatch):
    base = _base()
    history = _history()
    history.loc[0, "home_team_id"] = "wrong"
    monkeypatch.setattr(module, "load_training_dataset_with_context", lambda *a, **k: base.copy(deep=True))
    monkeypatch.setattr(module, "load_match_stats_form_history", lambda **k: history.copy(deep=True))
    with pytest.raises(ValueError, match="home_team_id"):
        module.load_training_dataset_with_match_stats()
