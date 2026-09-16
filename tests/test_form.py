import pandas as pd
from pandas.testing import assert_frame_equal

from src.features.form import add_form_features


METRICS = ("points", "wins", "draws", "losses", "goals_for", "goals_against")
FEATURES = [f"{side}_last5_{metric}" for metric in METRICS for side in ("home", "away")]


def _matches(rows):
    frame = pd.DataFrame(
        rows, columns=["home_team_id", "away_team_id", "home_score", "away_score"]
    )
    frame["match_date"] = pd.date_range("2025-01-01", periods=len(frame))
    frame["result"] = [
        2 if home > away else 1 if home == away else 0
        for home, away in zip(frame["home_score"], frame["away_score"])
    ]
    return frame


def _form(frame, row, side):
    return frame.iloc[row][[f"{side}_last5_{metric}" for metric in METRICS]].tolist()


def test_first_match_has_zero_form():
    result = add_form_features(_matches([("A", "B", 2, 1)]))

    assert result[FEATURES].iloc[0].tolist() == [0] * 12
    assert all(dtype == "int64" for dtype in result[FEATURES].dtypes)


def test_second_match_uses_only_first_match():
    result = add_form_features(_matches([("A", "B", 2, 1), ("B", "A", 0, 0)]))

    assert _form(result, 1, "home") == [0, 0, 0, 1, 1, 2]
    assert _form(result, 1, "away") == [3, 1, 0, 0, 2, 1]


def test_only_last_five_matches_are_used():
    scores = [(10, 0), (0, 1), (1, 1), (2, 0), (0, 2), (3, 1), (0, 0)]
    result = add_form_features(_matches([("A", "B", *score) for score in scores]))

    assert _form(result, 6, "home") == [7, 2, 1, 2, 6, 5]
    assert _form(result, 6, "away") == [7, 2, 1, 2, 5, 6]


def test_home_and_away_history_are_combined():
    result = add_form_features(
        _matches([("A", "B", 2, 0), ("B", "A", 1, 1), ("A", "B", 0, 3), ("B", "A", 0, 0)])
    )

    assert _form(result, 3, "home") == [4, 1, 1, 1, 4, 3]
    assert _form(result, 3, "away") == [4, 1, 1, 1, 3, 4]


def test_current_result_does_not_change_its_own_features():
    rows = [("A", "B", 2, 1), ("B", "A", 0, 0), ("A", "B", 1, 0)]
    original = add_form_features(_matches(rows))
    rows[1] = ("B", "A", 9, 0)
    changed = add_form_features(_matches(rows))

    assert_frame_equal(original[FEATURES].iloc[[1]], changed[FEATURES].iloc[[1]])
    assert not original[FEATURES].iloc[[2]].equals(changed[FEATURES].iloc[[2]])


def test_future_results_do_not_change_past_features():
    rows = [("A", "B", 2, 1), ("B", "A", 1, 1), ("A", "B", 0, 3), ("B", "A", 0, 0)]
    original = add_form_features(_matches(rows))
    rows[2:] = [("A", "B", 8, 0), ("B", "A", 7, 0)]
    changed = add_form_features(_matches(rows))

    assert_frame_equal(original[FEATURES].iloc[:2], changed[FEATURES].iloc[:2])


def test_results_are_deterministic_and_input_is_preserved():
    matches = _matches([("A", "B", 2, 1), ("B", "A", 0, 0)])
    matches.index = pd.Index([8, 3], name="source_row")
    original = matches.copy(deep=True)

    first = add_form_features(matches)
    second = add_form_features(matches)

    assert_frame_equal(first, second)
    assert_frame_equal(matches, original)
    assert_frame_equal(first[original.columns], original)
    assert list(first.columns) == list(original.columns) + FEATURES
