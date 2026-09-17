"""Continuous matchup context preserves each source's schema and past results."""

from unittest.mock import Mock

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import matchup_context_history as history_module
from src.features.elo_history import (
    EloHistory,
    OngoingEloHistory,
    load_elo_history_with_ongoing,
)
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS


PARTS = ("historical", "hyakunen", "ongoing")
INPUT_COLUMNS = (
    "match_date", "home_team_id", "away_team_id", "stadium",
    "home_score", "away_score", "result",
)


def _wrap_sources(frames):
    return OngoingEloHistory(*(EloHistory(frame, {}) for frame in frames))


def _load_from(monkeypatch, sources):
    loader = Mock(return_value=sources)
    monkeypatch.setattr(history_module, "load_elo_history_with_ongoing", loader)
    return history_module.load_matchup_context_history_with_ongoing()


@pytest.fixture(scope="module")
def real_history():
    sources = load_elo_history_with_ongoing()
    originals = tuple(getattr(sources, name).matches.copy(deep=True) for name in PARTS)
    with pytest.MonkeyPatch.context() as patch:
        result = _load_from(patch, sources)
    return sources, originals, result


def _manual_context(prior, current):
    """Independently select raw earlier rows, then sum current-team outcomes."""
    home, away = current.home_team_id, current.away_team_id
    pair_rows = prior.loc[
        (prior.home_team_id.eq(home) & prior.away_team_id.eq(away))
        | (prior.home_team_id.eq(away) & prior.away_team_id.eq(home))
    ].tail(5)
    points_diff = goal_diff = 0
    for row in pair_rows.itertuples(index=False):
        goals_for, goals_against = (
            (row.home_score, row.away_score)
            if row.home_team_id == home else (row.away_score, row.home_score)
        )
        points_diff += 3 if goals_for > goals_against else -3 if goals_for < goals_against else 0
        goal_diff += goals_for - goals_against
    expected = [len(pair_rows), points_diff, goal_diff]
    for team in (home, away):
        rows = prior.loc[
            prior.stadium.eq(current.stadium)
            & (prior.home_team_id.eq(team) | prior.away_team_id.eq(team))
        ].tail(5)
        points = goals = 0
        for row in rows.itertuples(index=False):
            goals_for, goals_against = (
                (row.home_score, row.away_score)
                if row.home_team_id == team else (row.away_score, row.home_score)
            )
            points += 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0
            goals += goals_for - goals_against
        expected.extend((len(rows), points, goals))
    return expected


def test_real_completed_row_counts(real_history):
    _, _, result = real_history
    counts = [len(getattr(result, name)) for name in PARTS]
    assert counts == [3588, 200, 70]
    assert sum(counts) == 3858
    assert isinstance(result, history_module.OngoingMatchupContextHistory)


@pytest.mark.parametrize("name", PARTS)
def test_all_nine_features_are_appended_as_integers(real_history, name):
    sources, _, result = real_history
    frame = getattr(result, name)
    assert len(MATCHUP_CONTEXT_COLUMNS) == 9
    assert list(frame.columns) == [
        *getattr(sources, name).matches.columns, *MATCHUP_CONTEXT_COLUMNS,
    ]
    assert all(frame[column].dtype == "int64" for column in MATCHUP_CONTEXT_COLUMNS)


def test_first_historical_match_starts_with_empty_histories(real_history):
    _, _, result = real_history
    assert result.historical.iloc[0].loc[list(MATCHUP_CONTEXT_COLUMNS)].tolist() == [0] * 9


@pytest.mark.parametrize("boundary", (1, 2), ids=("hyakunen", "ongoing"))
def test_first_match_at_boundary_uses_last_five_previous_matches(real_history, boundary):
    _, originals, result = real_history
    prior = pd.concat(originals[:boundary], ignore_index=True)
    current = originals[boundary].iloc[0]
    assert prior.match_date.max() < current.match_date
    expected = _manual_context(prior, current)
    # Both real boundary fixtures have established head-to-head history.
    assert expected[0] > 0
    for offset, team in ((3, current.home_team_id), (6, current.away_team_id)):
        earlier_at_stadium = prior.loc[
            prior.stadium.eq(current.stadium)
            & (prior.home_team_id.eq(team) | prior.away_team_id.eq(team))
        ]
        assert expected[offset] == min(5, len(earlier_at_stadium))
        if not earlier_at_stadium.empty:
            assert expected[offset] > 0
    actual = getattr(result, PARTS[boundary]).iloc[0]
    assert actual.loc[list(MATCHUP_CONTEXT_COLUMNS)].tolist() == expected


@pytest.mark.parametrize("position,name", tuple(enumerate(PARTS)))
def test_real_sources_preserve_columns_dtypes_index_order_and_values(real_history, position, name):
    sources, originals, result = real_history
    assert_frame_equal(getattr(result, name).loc[:, originals[position].columns], originals[position])
    assert_frame_equal(getattr(sources, name).matches, originals[position])


def test_repeated_load_is_deterministic(real_history, monkeypatch):
    sources, originals, first = real_history
    second = _load_from(monkeypatch, sources)
    for position, name in enumerate(PARTS):
        assert_frame_equal(getattr(first, name), getattr(second, name))
        assert_frame_equal(getattr(sources, name).matches, originals[position])


def _frame(rows):
    frame = pd.DataFrame(rows, columns=INPUT_COLUMNS)
    frame["match_date"] = pd.to_datetime(frame["match_date"])
    return frame


@pytest.fixture
def synthetic_sources():
    historical = _frame([
        ("2025-01-01", "A", "B", "Arena", 2, 2, 1),
        ("2025-01-02", "A", "C", "Arena ", 9, 0, 2),
        ("2025-01-03", "B", "A", "Arena", 1, 3, 0),
        ("2025-01-04", "A", "C", "arena", 8, 0, 2),
    ])
    hyakunen = _frame([("2026-01-01", "B", "A", "Arena", 0, 0, 1)])
    ongoing = _frame([("2026-08-01", "A", "B", "Arena", 1, 0, 2)])
    return _wrap_sources((historical, hyakunen, ongoing))


def test_reversed_roles_orient_h2h_to_current_home_team(monkeypatch, synthetic_sources):
    result = _load_from(monkeypatch, synthetic_sources)
    assert result.hyakunen.iloc[0].loc[list(MATCHUP_CONTEXT_COLUMNS[:3])].tolist() == [2, -3, -2]
    assert result.ongoing.iloc[0].loc[list(MATCHUP_CONTEXT_COLUMNS[:3])].tolist() == [3, 3, 2]


def test_stadium_uses_exact_string_and_combines_both_roles(monkeypatch, synthetic_sources):
    result = _load_from(monkeypatch, synthetic_sources)
    # The 9-0 at "Arena " and 8-0 at "arena" cannot enter "Arena" history.
    stadium_columns = list(MATCHUP_CONTEXT_COLUMNS[3:])
    assert result.hyakunen.iloc[0].loc[stadium_columns].tolist() == [2, 1, -2, 2, 4, 2]
    assert result.ongoing.iloc[0].loc[stadium_columns].tolist() == [3, 5, 2, 3, 2, -2]


def test_delegates_once_with_only_inputs_and_attaches_features_by_position(
    monkeypatch, synthetic_sources, tmp_path,
):
    frames = tuple(getattr(synthetic_sources, name).matches for name in PARTS)
    frames[0]["ordinary_only"] = pd.array([1, None, 3, 4], dtype="Int64")
    frames[1]["special_only"] = pd.Categorical(["playoff"])
    frames[2]["ongoing_only"] = pd.array([True], dtype="boolean")
    frames[0].index = pd.Index([8, 8, 2, 2], name="original_row")
    frames[1].index = pd.Index([8], name="special_row")
    frames[2].index = pd.Index([8], name="ongoing_row")
    originals = tuple(frame.copy(deep=True) for frame in frames)
    expected_inputs = pd.concat(
        [frame.loc[:, list(INPUT_COLUMNS)] for frame in originals], ignore_index=True,
    )
    assert expected_inputs.match_date.is_monotonic_increasing
    loader = Mock(return_value=synthetic_sources)
    monkeypatch.setattr(history_module, "load_elo_history_with_ongoing", loader)

    def add_features(combined):
        assert_frame_equal(combined, expected_inputs)
        output = combined.copy(deep=True)
        for offset, column in enumerate(MATCHUP_CONTEXT_COLUMNS):
            output[column] = range(offset * 100, offset * 100 + len(output))
        return output

    add = Mock(side_effect=add_features)
    monkeypatch.setattr(history_module, "add_matchup_context_features", add)
    master = object()
    result = history_module.load_matchup_context_history_with_ongoing(tmp_path, team_master=master)
    loader.assert_called_once_with(tmp_path, team_master=master)
    add.assert_called_once()
    start = 0
    for name, source, original in zip(PARTS, frames, originals):
        output = getattr(result, name)
        assert_frame_equal(output.loc[:, original.columns], original)
        assert_frame_equal(source, original)
        for offset, column in enumerate(MATCHUP_CONTEXT_COLUMNS):
            assert output[column].tolist() == list(range(offset * 100 + start, offset * 100 + start + len(source)))
        start += len(source)
        output.iloc[0, output.columns.get_loc("home_score")] = 999
        assert_frame_equal(source, original)


def test_empty_ongoing_keeps_schema_and_features(monkeypatch, synthetic_sources):
    empty = synthetic_sources.ongoing.matches.iloc[:0].copy(deep=True)
    empty["ongoing_only"] = pd.Series(index=empty.index, dtype="string")
    empty.index = pd.Index([], dtype="int64", name="empty_source")
    synthetic_sources.ongoing.matches = empty
    original = empty.copy(deep=True)
    result = _load_from(monkeypatch, synthetic_sources)
    assert result.ongoing.empty
    assert list(result.ongoing.columns) == [*original.columns, *MATCHUP_CONTEXT_COLUMNS]
    assert_frame_equal(result.ongoing.loc[:, original.columns], original)
    assert_frame_equal(synthetic_sources.ongoing.matches, original)
    assert all(result.ongoing[column].dtype == "int64" for column in MATCHUP_CONTEXT_COLUMNS)
    assert result.hyakunen.iloc[0].loc[list(MATCHUP_CONTEXT_COLUMNS)].tolist() == [2, -3, -2, 2, 1, -2, 2, 4, 2]
