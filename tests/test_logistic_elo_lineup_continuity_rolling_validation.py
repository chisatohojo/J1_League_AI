import numpy as np
import pandas as pd
import pytest

from src.modeling.logistic_elo_lineup_continuity_rolling_validation import (
    CURRENT_FEATURES, LINEUP_FEATURES, previous_two_lineup_overlap,
    parse_starting_xi_html,
)


def _frame():
    return pd.DataFrame([
        {"match_id":"1","match_date":"2020-01-01","home_team_id":"a","away_team_id":"b","home_xi":frozenset("abcdefghijk"),"away_xi":frozenset("klmnopqrstu"),"result":2},
        {"match_id":"2","match_date":"2020-01-08","home_team_id":"b","away_team_id":"a","home_xi":frozenset("klmnopqrstu"),"away_xi":frozenset("abcdefghijx"),"result":0},
        {"match_id":"3","match_date":"2020-01-15","home_team_id":"a","away_team_id":"b","home_xi":frozenset("abcdefghijy"),"away_xi":frozenset("klmnopqrsv"),"result":2},
    ])


def test_only_previous_two_matches_and_home_away_history_continue():
    out = previous_two_lineup_overlap(_frame())
    assert pd.isna(out.loc[out.match_id == "1", "home_prev2_lineup_overlap"]).all()
    assert pd.isna(out.loc[out.match_id == "2", "home_prev2_lineup_overlap"]).all()
    assert out.loc[out.match_id == "3", "home_prev2_lineup_overlap"].item() == 10
    assert out.loc[out.match_id == "3", "away_prev2_lineup_overlap"].item() == 11


def test_target_lineup_change_does_not_change_previous_feature():
    first = previous_two_lineup_overlap(_frame())
    changed = _frame(); changed.loc[2, "home_xi"] = frozenset("zzzzzzzzzzz")
    second = previous_two_lineup_overlap(changed)
    assert first.loc[2, "home_prev2_lineup_overlap"] == second.loc[2, "home_prev2_lineup_overlap"]


def test_overlap_range_and_input_unchanged():
    source = _frame(); before = source.copy(deep=True)
    out = previous_two_lineup_overlap(source)
    values = out[["home_prev2_lineup_overlap", "away_prev2_lineup_overlap"]].stack().dropna()
    assert values.between(0, 11).all()
    pd.testing.assert_frame_equal(source, before)


def test_chronology_uses_date_then_match_id():
    source = _frame().iloc[[2, 0, 1]].reset_index(drop=True)
    out = previous_two_lineup_overlap(source)
    assert out.loc[out.match_id == "3", "home_prev2_lineup_overlap"].item() == 10


def test_feature_sets_are_fixed():
    assert CURRENT_FEATURES == ("elo_diff",)
    assert LINEUP_FEATURES == ("elo_diff", "home_prev2_lineup_overlap", "away_prev2_lineup_overlap", "home_lineup_overlap_missing", "away_lineup_overlap_missing")


def test_starting_xi_requires_two_distinct_sides():
    names = "".join(f'<tr><td class="position">DF</td><td class="number">{i}</td><td class="name">P{i}</td></tr>' for i in range(11))
    html = f'<div class="two-column-table-box-l"><!-- A5 Start --><table>{names}</table></div><div class="two-column-table-box-r"><!-- A5 Start --><table>{names.replace("P", "Q")}</table></div>'
    home, away = parse_starting_xi_html(html)
    assert len(home) == len(away) == 11


def test_missing_history_is_nan_not_zero():
    out = previous_two_lineup_overlap(_frame())
    assert out.loc[0, "home_prev2_lineup_overlap"] != 0
    assert np.isnan(out.loc[0, "home_prev2_lineup_overlap"])
