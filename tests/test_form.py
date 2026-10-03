import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features.form import FORM_COLUMNS, add_form_features, add_form_features_to_targets


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


def test_existing_builder_still_ignores_optional_duplicate_match_id_column():
    matches = _matches([("A", "B", 1, 0), ("C", "D", 0, 0)]).assign(match_id="duplicate")
    result = add_form_features(matches)
    assert result["match_id"].tolist() == ["duplicate", "duplicate"]


def _targets(rows, date="2026-08-01"):
    return pd.DataFrame(
        [
            {
                "match_id": match_id,
                "match_date": date,
                "home_team_id": home,
                "away_team_id": away,
            }
            for match_id, home, away in rows
        ]
    )


def _empty_history():
    return pd.DataFrame(columns=[
        "match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result"
    ])


def test_target_state_with_no_history_is_all_zero_and_read_only():
    history = _empty_history()
    targets = _targets([("t1", "A", "B"), ("t2", "C", "D")])
    history_before = history.copy(deep=True)
    targets_before = targets.copy(deep=True)

    result = add_form_features_to_targets(history, targets)

    assert result[list(FORM_COLUMNS)].eq(0).all().all()
    assert all(dtype == "int64" for dtype in result[list(FORM_COLUMNS)].dtypes)
    assert_frame_equal(history, history_before)
    assert_frame_equal(targets, targets_before)


def test_target_state_replays_one_prior_match_and_unifies_home_away_history():
    history = _matches([("A", "B", 2, 0)])
    targets = _targets([("t", "C", "A")])

    result = add_form_features_to_targets(history, targets)

    assert _form(result, 0, "away") == [3, 1, 0, 0, 2, 0]
    assert _form(result, 0, "home") == [0, 0, 0, 0, 0, 0]


def test_target_state_caps_at_five_and_continues_across_season_and_competition_as_supplied():
    scores = [(10, 0), (0, 1), (1, 1), (2, 0), (0, 2), (3, 1)]
    history = _matches([("A", "B", *score) for score in scores])
    history["match_date"] = pd.to_datetime(
        ["2024-12-01", "2025-01-01", "2025-05-01", "2025-12-01", "2026-03-01", "2026-07-01"]
    )
    history["competition"] = ["J1", "J1", "J1", "J1", "Hyakunen", "ongoing J1"]

    result = add_form_features_to_targets(history, _targets([("t", "A", "C")]))

    assert _form(result, 0, "home") == [7, 2, 1, 2, 6, 5]


def test_target_batch_rows_observe_same_state_and_never_modify_each_other():
    history = _matches([("A", "B", 1, 1)])
    targets = _targets([("t1", "A", "C"), ("t2", "B", "D")])

    result = add_form_features_to_targets(history, targets)

    assert _form(result, 0, "home") == [1, 0, 1, 0, 1, 1]
    assert _form(result, 1, "home") == [1, 0, 1, 0, 1, 1]
    assert _form(result, 0, "away") == [0, 0, 0, 0, 0, 0]
    assert _form(result, 1, "away") == [0, 0, 0, 0, 0, 0]


def test_target_state_requires_one_date_and_rejects_same_team_twice():
    targets = _targets([("t1", "A", "B"), ("t2", "C", "D")])
    targets.loc[1, "match_date"] = "2026-08-02"
    with pytest.raises(ValueError, match="share one valid calendar date"):
        add_form_features_to_targets(_empty_history(), targets)

    duplicate_team = _targets([("t1", "A", "B"), ("t2", "A", "C")])
    with pytest.raises(ValueError, match="cannot appear twice"):
        add_form_features_to_targets(_empty_history(), duplicate_team)


@pytest.mark.parametrize("history_date", ["2026-08-01", "2026-08-02"])
def test_target_state_rejects_same_date_and_later_history(history_date):
    history = _matches([("A", "B", 1, 0)])
    history["match_date"] = pd.to_datetime([history_date])
    with pytest.raises(ValueError, match="strictly before"):
        add_form_features_to_targets(history, _targets([("t", "A", "C")]))


def test_target_state_rejects_invalid_result_and_same_date_duplicate_history_team():
    invalid = _matches([("A", "B", 1, 0)]).assign(result=0)
    with pytest.raises(ValueError, match="agree with"):
        add_form_features_to_targets(invalid, _targets([("t", "A", "C")]))

    duplicate = _matches([("A", "B", 1, 0), ("C", "A", 0, 0)])
    duplicate["match_date"] = pd.to_datetime(["2026-07-01", "2026-07-01"])
    with pytest.raises(ValueError, match="cannot appear twice"):
        add_form_features_to_targets(duplicate, _targets([("t", "A", "D")]))


def test_target_state_exactly_matches_existing_strictly_prior_form_semantics():
    history = _matches([("A", "B", 2, 0), ("C", "A", 1, 1), ("B", "C", 0, 3)])
    target = _targets([("t", "A", "C")], date="2025-01-04")
    target_state = add_form_features_to_targets(history, target)

    # Two different hypothetical outcomes prove the target outcome cannot affect its own form state.
    appended_home = pd.concat(
        [history, _matches([("A", "C", 4, 0)]).assign(match_date=pd.Timestamp("2025-01-04"))],
        ignore_index=True,
    )
    appended_away = pd.concat(
        [history, _matches([("A", "C", 0, 4)]).assign(match_date=pd.Timestamp("2025-01-04"))],
        ignore_index=True,
    )
    existing_home = add_form_features(appended_home).iloc[-1]
    existing_away = add_form_features(appended_away).iloc[-1]

    assert target_state.iloc[0][list(FORM_COLUMNS)].tolist() == existing_home[list(FORM_COLUMNS)].tolist()
    assert target_state.iloc[0][list(FORM_COLUMNS)].tolist() == existing_away[list(FORM_COLUMNS)].tolist()
