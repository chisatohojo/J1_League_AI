"""Configurable stadium form continues across the three completed histories."""

from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import matchup_context_history, stadium_window_history as history_module
from src.features.elo_history import EloHistory, OngoingEloHistory, load_elo_history_with_ongoing
from src.features.stadium_window import STADIUM_WINDOW_COLUMNS, add_stadium_window_features


PARTS = ("historical", "hyakunen", "ongoing")
WINDOWS = (3, 5, 8, 10)
INPUT_COLUMNS = (
    "match_date", "home_team_id", "away_team_id", "stadium",
    "home_score", "away_score", "result",
)


def _wrap_sources(frames):
    return OngoingEloHistory(*(EloHistory(frame, {}) for frame in frames))


def _source_frames(sources):
    return tuple(getattr(sources, name).matches for name in PARTS)


def _load_from(monkeypatch, sources, window=5):
    monkeypatch.setattr(history_module, "load_elo_history_with_ongoing", Mock(return_value=sources))
    return history_module.load_stadium_window_history_with_ongoing(window)


@pytest.fixture(scope="module")
def real_history():
    # Read and replay the actual local data once; every wrapper uses these rows.
    sources = load_elo_history_with_ongoing()
    originals = tuple(frame.copy(deep=True) for frame in _source_frames(sources))
    with pytest.MonkeyPatch.context() as patch:
        results = {window: _load_from(patch, sources, window) for window in WINDOWS}
        patch.setattr(
            matchup_context_history, "load_elo_history_with_ongoing", Mock(return_value=sources),
        )
        last_five = matchup_context_history.load_matchup_context_history_with_ongoing()
    return sources, originals, results, last_five


def _manual_window(prior, current, window):
    """Select prior rows independently, combining both roles at the exact stadium."""
    expected = []
    for team in (current.home_team_id, current.away_team_id):
        rows = prior.loc[
            prior.stadium.eq(current.stadium)
            & (prior.home_team_id.eq(team) | prior.away_team_id.eq(team))
        ].tail(window)
        points = goal_difference = 0
        for row in rows.itertuples(index=False):
            goals_for, goals_against = (
                (row.home_score, row.away_score)
                if row.home_team_id == team else (row.away_score, row.home_score)
            )
            points += 3 if goals_for > goals_against else 1 if goals_for == goals_against else 0
            goal_difference += goals_for - goals_against
        expected.extend((len(rows), points, goal_difference))
    return expected


def test_real_completed_row_counts(real_history):
    _, _, results, _ = real_history
    result = results[5]
    counts = [len(getattr(result, name)) for name in PARTS]
    assert counts == [3588, 200, 70]
    assert sum(counts) == 3858
    assert isinstance(result, history_module.OngoingStadiumWindowHistory)


@pytest.mark.parametrize("window", WINDOWS)
def test_real_windows_work_and_start_with_empty_history(real_history, window):
    _, originals, results, _ = real_history
    result = results[window]
    assert result.historical.iloc[0].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == [0] * 6
    combined = pd.concat(originals, ignore_index=True)
    expected = _manual_window(combined.iloc[:-1], combined.iloc[-1], window)
    assert result.ongoing.iloc[-1].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == expected
    for name in PARTS:
        frame = getattr(result, name)
        for column in (STADIUM_WINDOW_COLUMNS[0], STADIUM_WINDOW_COLUMNS[3]):
            assert frame[column].between(0, window).all()
    assert result.historical[STADIUM_WINDOW_COLUMNS[0]].max() == window


@pytest.mark.parametrize("position,name", tuple(enumerate(PARTS)))
def test_six_integer_features_preserve_real_source_schema_and_values(real_history, position, name):
    sources, originals, results, _ = real_history
    original = originals[position]
    assert len(STADIUM_WINDOW_COLUMNS) == 6
    for result in results.values():
        output = getattr(result, name)
        assert list(output.columns) == [*original.columns, *STADIUM_WINDOW_COLUMNS]
        assert all(output[column].dtype == "int64" for column in STADIUM_WINDOW_COLUMNS)
        assert_frame_equal(output.loc[:, original.columns], original, check_exact=True)
        assert output is not getattr(sources, name).matches
    assert_frame_equal(getattr(sources, name).matches, original, check_exact=True)


@pytest.mark.parametrize("window", WINDOWS)
@pytest.mark.parametrize("boundary", (1, 2), ids=("hyakunen", "ongoing"))
def test_real_first_match_at_each_boundary_uses_previous_stadium_history(real_history, window, boundary):
    _, originals, results, _ = real_history
    prior = pd.concat(originals[:boundary], ignore_index=True)
    current = originals[boundary].iloc[0]
    assert prior.match_date.max() < current.match_date
    expected = _manual_window(prior, current, window)
    # A nonzero count makes this sensitive to a reset between source frames.
    assert expected[0] + expected[3] > 0
    actual = getattr(results[window], PARTS[boundary]).iloc[0]
    assert actual.loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == expected


def test_real_history_does_not_reset_at_ordinary_season_boundaries(real_history):
    _, originals, results, _ = real_history
    historical = originals[0]
    seasons = historical.season.drop_duplicates().tolist()
    assert seasons == list(range(2015, 2026))
    inherited_boundary = False
    for season in seasons[1:]:
        season_start = int(np.flatnonzero(historical.season.eq(season).to_numpy())[0])
        prior = historical.iloc[:season_start]
        current = historical.iloc[season_start]
        expected = _manual_window(prior, current, 5)
        # A season opener can use a team/stadium pair absent from prior data.
        inherited_boundary |= expected[0] + expected[3] > 0
        actual = results[5].historical.iloc[season_start]
        assert actual.loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == expected
    assert inherited_boundary


@pytest.mark.parametrize("name", PARTS)
def test_window_five_exactly_matches_existing_history_loader(real_history, name):
    _, _, results, last_five = real_history
    old_columns = [column.replace("_window_", "_last5_") for column in STADIUM_WINDOW_COLUMNS]
    expected = getattr(last_five, name).loc[:, old_columns].rename(
        columns=dict(zip(old_columns, STADIUM_WINDOW_COLUMNS)),
    )
    actual = getattr(results[5], name).loc[:, list(STADIUM_WINDOW_COLUMNS)]
    assert_frame_equal(actual, expected, check_exact=True)


def test_repeated_real_load_is_deterministic_and_does_not_mutate_sources(real_history, monkeypatch):
    sources, originals, results, _ = real_history
    repeated = _load_from(monkeypatch, sources, 5)
    for name, source, original in zip(PARTS, _source_frames(sources), originals):
        assert_frame_equal(getattr(repeated, name), getattr(results[5], name), check_exact=True)
        assert_frame_equal(source, original, check_exact=True)


def _frame(rows):
    frame = pd.DataFrame(rows, columns=INPUT_COLUMNS)
    frame["match_date"] = pd.to_datetime(frame["match_date"])
    return frame


@pytest.fixture
def synthetic_sources():
    historical = _frame([
        ("2024-12-01", "A", "B", "Arena", 2, 2, 1),
        ("2024-12-02", "A", "C", "Arena ", 9, 0, 2),
        ("2025-01-03", "B", "A", "Arena", 1, 3, 0),
        ("2025-01-04", "A", "C", "arena", 8, 0, 2),
        ("2025-12-01", "A", "B", "Arena", 0, 2, 0),
    ]).astype({"home_team_id": "string", "home_score": "int16", "result": "int8"})
    hyakunen = _frame([
        ("2026-01-01", "B", "A", "Arena", 0, 0, 1),
        ("2026-01-02", "A", "B", "Arena", 4, 1, 2),
    ]).astype({"away_score": "Int64"})
    ongoing = _frame([
        ("2026-08-01", "A", "B", "Arena", 1, 0, 2),
        ("2026-08-02", "B", "A", "Arena", 2, 1, 2),
    ]).astype({"home_score": "Int32", "result": "int32"})
    historical["ordinary_only"] = pd.array([1, None, 3, 4, 5], dtype="Int64")
    historical["home_stadium_last5_matches"] = np.arange(len(historical), dtype="int16")
    hyakunen["special_only"] = pd.Categorical(["regional", "playoff"])
    ongoing["ongoing_only"] = pd.array([True, None], dtype="boolean")
    ongoing["provenance"] = pd.array(["first", "second"], dtype="string")
    hyakunen = hyakunen.loc[:, list(reversed(hyakunen.columns))]
    historical.index = pd.Index([8, 8, 2, 2, 8], name="original_row")
    hyakunen.index = pd.Index([8, 8], name="special_row")
    ongoing.index = pd.Index([8, 8], name="ongoing_row")
    return _wrap_sources((historical, hyakunen, ongoing))


def test_exact_stadium_and_reversed_roles_continue_across_both_boundaries(monkeypatch, synthetic_sources):
    result = _load_from(monkeypatch, synthetic_sources, 3)
    # Neither the 9-0 at "Arena " nor the 8-0 at "arena" belongs to "Arena".
    assert result.historical.iloc[2].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == [1, 1, 0, 1, 1, 0]
    assert result.hyakunen.iloc[0].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == [3, 4, 0, 3, 4, 0]
    assert result.ongoing.iloc[0].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == [3, 4, 1, 3, 4, -1]
    assert result.ongoing.iloc[1].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == [3, 1, -4, 3, 7, 4]


def test_delegates_once_with_only_seven_inputs_and_attaches_by_position(
    monkeypatch, synthetic_sources, tmp_path,
):
    frames = _source_frames(synthetic_sources)
    originals = tuple(frame.copy(deep=True) for frame in frames)
    expected_inputs = pd.concat(
        [frame.loc[:, list(INPUT_COLUMNS)] for frame in originals], ignore_index=True,
    )
    loader = Mock(return_value=synthetic_sources)
    monkeypatch.setattr(history_module, "load_elo_history_with_ongoing", loader)
    window, master = object(), object()

    def calculate(combined, received_window):
        assert received_window is window
        assert_frame_equal(combined, expected_inputs, check_exact=True)
        output = combined.copy(deep=True)
        # A calculator index unrelated to source indices exposes label alignment.
        output.index = pd.Index(range(100, 100 + len(output)), name="calculated_row")
        for offset, column in enumerate(STADIUM_WINDOW_COLUMNS):
            output[column] = range(offset * 100, offset * 100 + len(output))
        return output

    calculator = Mock(side_effect=calculate)
    monkeypatch.setattr(history_module, "add_stadium_window_features", calculator)
    result = history_module.load_stadium_window_history_with_ongoing(
        window, tmp_path, team_master=master,
    )
    loader.assert_called_once_with(tmp_path, team_master=master)
    calculator.assert_called_once()
    assert calculator.call_args.args[1] is window
    start = 0
    for name, source, original in zip(PARTS, frames, originals):
        output = getattr(result, name)
        assert list(output.columns) == [*original.columns, *STADIUM_WINDOW_COLUMNS]
        assert_frame_equal(output.loc[:, original.columns], original, check_exact=True)
        assert_frame_equal(source, original, check_exact=True)
        for offset, column in enumerate(STADIUM_WINDOW_COLUMNS):
            assert output[column].tolist() == list(
                range(offset * 100 + start, offset * 100 + start + len(source)),
            )
        start += len(source)
        output.iloc[0, output.columns.get_loc("home_score")] = 999
        assert_frame_equal(source, original, check_exact=True)


def test_empty_ongoing_is_excluded_from_combined_inputs_and_keeps_its_schema(monkeypatch, synthetic_sources):
    empty = synthetic_sources.ongoing.matches.iloc[:0].copy(deep=True)
    # These empty dtypes must not upcast scores supplied to the calculator.
    empty = empty.astype({"home_score": "float64", "away_score": "float64", "result": "float64"})
    empty.index = pd.Index([], dtype="int64", name="empty_source")
    synthetic_sources.ongoing.matches = empty
    original = empty.copy(deep=True)
    expected_inputs = pd.concat(
        [frame.loc[:, list(INPUT_COLUMNS)] for frame in _source_frames(synthetic_sources)[:2]],
        ignore_index=True,
    )
    calculator = Mock(wraps=add_stadium_window_features)
    monkeypatch.setattr(history_module, "add_stadium_window_features", calculator)
    result = _load_from(monkeypatch, synthetic_sources, 3)
    calculator.assert_called_once()
    assert_frame_equal(calculator.call_args.args[0], expected_inputs, check_exact=True)
    assert result.ongoing.empty
    assert list(result.ongoing.columns) == [*original.columns, *STADIUM_WINDOW_COLUMNS]
    assert_frame_equal(result.ongoing.loc[:, original.columns], original, check_exact=True)
    assert_frame_equal(synthetic_sources.ongoing.matches, original, check_exact=True)
    assert all(result.ongoing[column].dtype == "int64" for column in STADIUM_WINDOW_COLUMNS)
    assert result.hyakunen.iloc[0].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == [3, 4, 0, 3, 4, 0]


@pytest.mark.parametrize("window", (True, 0, -1, 1.5))
def test_invalid_window_is_forwarded_unchanged_to_actual_calculator(monkeypatch, synthetic_sources, window):
    originals = tuple(frame.copy(deep=True) for frame in _source_frames(synthetic_sources))
    loader = Mock(return_value=synthetic_sources)
    calculator = Mock(wraps=add_stadium_window_features)
    monkeypatch.setattr(history_module, "load_elo_history_with_ongoing", loader)
    monkeypatch.setattr(history_module, "add_stadium_window_features", calculator)
    with pytest.raises(ValueError, match="positive integer"):
        history_module.load_stadium_window_history_with_ongoing(window)
    loader.assert_called_once_with(history_module.DEFAULT_PROCESSED_DIR, team_master=None)
    calculator.assert_called_once()
    assert calculator.call_args.args[1] is window
    for source, original in zip(_source_frames(synthetic_sources), originals):
        assert_frame_equal(source, original, check_exact=True)


def test_numpy_integer_window_reaches_actual_calculator_unchanged(monkeypatch, synthetic_sources):
    window = np.int64(3)
    calculator = Mock(wraps=add_stadium_window_features)
    monkeypatch.setattr(history_module, "add_stadium_window_features", calculator)
    result = _load_from(monkeypatch, synthetic_sources, window)
    calculator.assert_called_once()
    assert calculator.call_args.args[1] is window
    assert result.ongoing.iloc[0].loc[list(STADIUM_WINDOW_COLUMNS)].tolist() == [3, 4, 1, 3, 4, -1]


@pytest.mark.parametrize("name,column", [
    (PARTS[position % len(PARTS)], column)
    for position, column in enumerate(STADIUM_WINDOW_COLUMNS)
])
def test_new_feature_collisions_in_any_source_are_rejected(monkeypatch, synthetic_sources, name, column):
    getattr(synthetic_sources, name).matches[column] = 999
    originals = tuple(frame.copy(deep=True) for frame in _source_frames(synthetic_sources))
    calculator = Mock(wraps=add_stadium_window_features)
    monkeypatch.setattr(history_module, "add_stadium_window_features", calculator)
    with pytest.raises(ValueError, match="already exist"):
        _load_from(monkeypatch, synthetic_sources)
    calculator.assert_not_called()
    for source, original in zip(_source_frames(synthetic_sources), originals):
        assert_frame_equal(source, original, check_exact=True)


def test_empty_ongoing_output_column_collision_is_rejected(monkeypatch, synthetic_sources):
    empty = synthetic_sources.ongoing.matches.iloc[:0].copy(deep=True)
    empty[STADIUM_WINDOW_COLUMNS[-1]] = pd.Series(index=empty.index, dtype="int64")
    synthetic_sources.ongoing.matches = empty
    with pytest.raises(ValueError, match="already exist"):
        _load_from(monkeypatch, synthetic_sources)
