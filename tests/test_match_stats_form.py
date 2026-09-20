import numpy as np
import pandas as pd
import pytest

from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS, add_match_stats_form_features


def games(count=6):
    rows = []
    pairs = [("A", "B"), ("C", "A"), ("A", "D"), ("B", "A"), ("A", "C"), ("D", "A"), ("A", "B"), ("C", "A")]
    for i, (home, away) in enumerate(pairs[:count]):
        rows.append({
            "match_id": str(i + 1), "match_date": pd.Timestamp("2020-01-01") + pd.Timedelta(days=i),
            "home_team_id": home, "away_team_id": away,
            "home_shots": 10 + i, "away_shots": 1 + i,
            "home_ck": 5 + i, "away_ck": 2 + i,
            "home_fk": 7 + i, "away_fk": 3 + i,
        })
    return pd.DataFrame(rows)


def test_first_match_is_zero_and_output_is_int64():
    result = add_match_stats_form_features(games(1))
    assert (result.loc[0, list(MATCH_STATS_FORM_COLUMNS)] == 0).all()
    assert all(result[column].dtype == "int64" for column in MATCH_STATS_FORM_COLUMNS)


def test_team_perspective_and_home_away_history_continue():
    result = add_match_stats_form_features(games(4), window=5)
    # Match 4 is B home vs A away: B has match 1 away; A has matches 1-3.
    assert result.loc[3, "home_stats_lastn_shots_for"] == 1
    assert result.loc[3, "home_stats_lastn_shots_against"] == 10
    assert result.loc[3, "away_stats_lastn_shots_for"] == 10 + 2 + 12
    assert result.loc[3, "away_stats_lastn_shots_against"] == 1 + 11 + 3
    assert result.loc[3, "away_stats_lastn_shots_diff"] == 9
    assert result.loc[3, "home_stats_lastn_ck_diff"] == 2 - 5
    assert result.loc[3, "away_stats_lastn_fk_diff"] == (7 - 3) + (4 - 8) + (9 - 5)


def test_current_match_and_future_values_do_not_leak():
    before = add_match_stats_form_features(games(5))
    changed = games(6)
    changed.loc[5, ["home_shots", "away_shots", "home_ck", "away_ck", "home_fk", "away_fk"]] = 999
    after = add_match_stats_form_features(changed)
    pd.testing.assert_frame_equal(before, after.iloc[:5].loc[:, before.columns])


@pytest.mark.parametrize("window", [1, 3, 5, 8])
def test_supported_windows(window):
    result = add_match_stats_form_features(games(8), window=window)
    assert len(result) == 8


def test_window_limits_to_recent_matches():
    result = add_match_stats_form_features(games(8), window=1)
    # Match 8 is C home vs A; C's latest prior match is match 5 away, A's is match 7 home.
    assert result.loc[7, "home_stats_lastn_shots_for"] == 5
    assert result.loc[7, "away_stats_lastn_shots_for"] == 16
    result3 = add_match_stats_form_features(games(8), window=3)
    assert result3.loc[7, "away_stats_lastn_shots_for"] == 16 + 6 + 14


@pytest.mark.parametrize("bad_window", [0, -1, 1.5, True, float("nan")])
def test_invalid_window_rejected(bad_window):
    with pytest.raises(ValueError):
        add_match_stats_form_features(games(1), window=bad_window)


def test_validation_rejects_bad_input_and_existing_outputs():
    with pytest.raises(TypeError):
        add_match_stats_form_features([], window=5)
    with pytest.raises(ValueError):
        add_match_stats_form_features(games(2).iloc[::-1])
    bad = games(2).copy()
    bad.loc[1, "home_team_id"] = None
    with pytest.raises(ValueError): add_match_stats_form_features(bad)
    bad = games(2).copy()
    bad.loc[1, "home_team_id"] = "A"
    with pytest.raises(ValueError): add_match_stats_form_features(bad)
    bad = games(2).copy()
    bad["home_shots"] = bad["home_shots"].astype(object)
    bad.loc[1, "home_shots"] = 1.5
    with pytest.raises(ValueError): add_match_stats_form_features(bad)
    bad = games(2).copy()
    bad.loc[1, "home_ck"] = -1
    with pytest.raises(ValueError): add_match_stats_form_features(bad)
    bad = games(2).copy()
    bad.loc[0, "home_shots"] = np.nan
    with pytest.raises(ValueError): add_match_stats_form_features(bad)
    bad = games(2).copy()
    bad["home_stats_lastn_shots_for"] = 0
    with pytest.raises(ValueError): add_match_stats_form_features(bad)


def test_same_team_same_day_rejected_input_unchanged_and_index_order_preserved():
    data = games(3).set_index(pd.Index([9, 4, 7], name="row"))
    data.loc[data.index[2], "match_date"] = data.loc[data.index[1], "match_date"]
    original = data.copy(deep=True)
    with pytest.raises(ValueError): add_match_stats_form_features(data)
    pd.testing.assert_frame_equal(data, original)
    good = games(3).set_index(pd.Index([9, 4, 7], name="row"))
    output = add_match_stats_form_features(good)
    assert output.index.equals(good.index)
    assert output.index.tolist() == [9, 4, 7]


def test_deterministic_and_stats_are_sums_not_averages():
    data = games(3)
    first = add_match_stats_form_features(data, window=5)
    second = add_match_stats_form_features(data, window=5)
    pd.testing.assert_frame_equal(first, second)
    assert first.loc[3 - 1, "home_stats_lastn_shots_for"] == 10 + 2
