"""Schedule-gap continuity across the existing three completed-match sources."""

from types import SimpleNamespace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import schedule_gap_history as history_module
from src.features.elo_history import (
    DEFAULT_PROCESSED_DIR,
    EloHistory,
    OngoingEloHistory,
    load_elo_history_with_ongoing,
)
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS


PARTITIONS = ("historical", "hyakunen", "ongoing")
INPUT_COLUMNS = ["match_date", "home_team_id", "away_team_id"]


def _frames(source):
    return tuple(getattr(source, name).matches for name in PARTITIONS)


def _stream(source):
    return pd.concat(
        [frame.loc[:, INPUT_COLUMNS] for frame in _frames(source) if not frame.empty],
        ignore_index=True,
    )


def _expected_row(stream, position):
    """Find predecessors independently by filtering only the preceding rows."""
    current = stream.iloc[position]
    preceding = stream.iloc[:position]
    day = pd.Timestamp(current["match_date"]).date()
    gaps, flags = [], []
    for side in ("home", "away"):
        team = current[f"{side}_team_id"]
        played = preceding.loc[
            preceding["home_team_id"].eq(team) | preceding["away_team_id"].eq(team),
            "match_date",
        ]
        flags.append(int(not played.empty))
        gaps.append((day - pd.to_datetime(played).max().date()).days if len(played) else 0)
    return [*gaps, gaps[0] - gaps[1] if all(flags) else 0, *flags]


def _load(monkeypatch, source):
    monkeypatch.setattr(history_module, "load_elo_history_with_ongoing", lambda *a, **k: source)
    return history_module.load_schedule_gap_history_with_ongoing()


@pytest.fixture(scope="module")
def real_case():
    # All real-data tests share one verified Elo replay and one adapter result.
    source = load_elo_history_with_ongoing()
    originals = tuple(frame.copy(deep=True) for frame in _frames(source))
    with pytest.MonkeyPatch.context() as patch:
        result = _load(patch, source)
    return SimpleNamespace(source=source, originals=originals, result=result, stream=_stream(source))


@pytest.fixture
def synthetic_source():
    historical = pd.DataFrame({
        "match_id": pd.array(["h2", "h1", "h0"], dtype="string"),
        "match_date": pd.to_datetime([
            "2015-03-01 18:00:00", "2015-03-08 14:00:00", "2015-03-15 19:00:00",
        ]),
        "home_team_id": ["A", "B", "C"],
        "away_team_id": ["B", "C", "A"],
        "historical_only": pd.Categorical(["first", "first", "second"]),
        "home_elo": [1500.0, 1510.5, 1480.25],
    }, index=pd.Index([8, 8, -2], name="source_row"))
    hyakunen = pd.DataFrame({
        "playoff_round": pd.array([None, 2], dtype="Int64"),
        "match_date": pd.to_datetime(["2026-02-01 15:00:00", "2026-02-08 13:00:00"]),
        "home_team_id": pd.array(["A", "B"], dtype="string"),
        "away_team_id": pd.array(["C", "A"], dtype="string"),
        "match_id": ["s9", "s3"],
    }, index=pd.Index(["repeat", "repeat"], name="special_row"))
    ongoing = pd.DataFrame({
        "match_date": pd.array(["2026-08-08 18:00:00", "2026-08-15 19:00:00"], dtype="string"),
        "home_team_id": ["C", "A"],
        "away_team_id": ["B", "B"],
        "match_id": pd.array(["o7", "o2"], dtype="string"),
        "evidence": pd.array(["saved", None], dtype="string"),
    }, index=pd.Index([91, 91], name="ongoing_row"))
    return OngoingEloHistory(*(EloHistory(frame, {}) for frame in (historical, hyakunen, ongoing)))


def test_real_partition_counts(real_case):
    assert isinstance(real_case.result, history_module.OngoingScheduleGapHistory)
    counts = [len(getattr(real_case.result, name)) for name in PARTITIONS]
    assert counts == [3588, 200, 70]
    assert sum(counts) == 3858


@pytest.mark.parametrize("name", PARTITIONS)
def test_all_five_features_are_complete_integers(real_case, name):
    features = getattr(real_case.result, name).loc[:, list(SCHEDULE_GAP_COLUMNS)]
    assert features.shape[1] == 5
    assert not features.isna().any().any()
    assert all(pd.api.types.is_integer_dtype(dtype) for dtype in features.dtypes)


def test_first_historical_match_starts_with_zero_features(real_case):
    assert real_case.result.historical.loc[:, list(SCHEDULE_GAP_COLUMNS)].iloc[0].tolist() == [0] * 5


@pytest.mark.parametrize("name,local_position,offset", [
    ("historical", 18, 0),
    ("hyakunen", 0, 3588),
    ("ongoing", 0, 3788),
])
def test_previous_match_gaps_continue_across_boundaries(real_case, name, local_position, offset):
    expected = _expected_row(real_case.stream, offset + local_position)
    assert expected[-2:] == [1, 1]
    actual = getattr(real_case.result, name).loc[:, list(SCHEDULE_GAP_COLUMNS)].iloc[local_position]
    assert actual.tolist() == expected


def test_real_source_columns_dtypes_indices_and_order_are_preserved(real_case):
    for name, original in zip(PARTITIONS, real_case.originals):
        output = getattr(real_case.result, name)
        assert output.columns.tolist() == [*original.columns, *SCHEDULE_GAP_COLUMNS]
        assert_frame_equal(output.loc[:, original.columns], original)


def test_real_input_frames_are_not_mutated(real_case):
    for source, original in zip(_frames(real_case.source), real_case.originals):
        assert_frame_equal(source, original)


def test_repeated_calls_are_deterministic(monkeypatch, real_case):
    repeated = _load(monkeypatch, real_case.source)
    for name in PARTITIONS:
        assert_frame_equal(getattr(repeated, name), getattr(real_case.result, name))


def test_home_away_role_changes_share_team_history(monkeypatch, synthetic_source):
    result = _load(monkeypatch, synthetic_source)
    assert result.historical.loc[:, list(SCHEDULE_GAP_COLUMNS)].iloc[1].tolist() == [7, 0, 0, 1, 0]
    assert result.historical.loc[:, list(SCHEDULE_GAP_COLUMNS)].iloc[2].tolist() == [7, 14, -7, 1, 1]


def test_large_season_boundary_gap_is_not_capped(monkeypatch, synthetic_source):
    result = _load(monkeypatch, synthetic_source)
    expected = _expected_row(_stream(synthetic_source), 3)
    assert expected[0] > 3650
    assert result.hyakunen.loc[:, list(SCHEDULE_GAP_COLUMNS)].iloc[0].tolist() == expected


def test_mixed_schemas_and_duplicate_indices_attach_features_by_position(monkeypatch, synthetic_source):
    originals = tuple(frame.copy(deep=True) for frame in _frames(synthetic_source))
    result = _load(monkeypatch, synthetic_source)
    stream = _stream(synthetic_source)
    offset = 0
    for name, original in zip(PARTITIONS, originals):
        output = getattr(result, name)
        assert output.columns.tolist() == [*original.columns, *SCHEDULE_GAP_COLUMNS]
        assert_frame_equal(output.loc[:, original.columns], original)
        for position in range(len(original)):
            assert output.loc[:, list(SCHEDULE_GAP_COLUMNS)].iloc[position].tolist() == _expected_row(
                stream, offset + position,
            )
        offset += len(original)
    for source, original in zip(_frames(synthetic_source), originals):
        assert_frame_equal(source, original)
    result.historical.iloc[0, result.historical.columns.get_loc("home_elo")] = -999.0
    assert_frame_equal(synthetic_source.historical.matches, originals[0])


def test_empty_ongoing_retains_schema_index_and_integer_features(monkeypatch, synthetic_source):
    synthetic_source.ongoing.matches = synthetic_source.ongoing.matches.iloc[:0].copy()
    original = synthetic_source.ongoing.matches.copy(deep=True)
    result = _load(monkeypatch, synthetic_source)
    assert result.ongoing.empty
    assert result.ongoing.columns.tolist() == [*original.columns, *SCHEDULE_GAP_COLUMNS]
    assert_frame_equal(result.ongoing.loc[:, original.columns], original)
    assert all(pd.api.types.is_integer_dtype(result.ongoing[column]) for column in SCHEDULE_GAP_COLUMNS)
    assert result.hyakunen.loc[:, list(SCHEDULE_GAP_COLUMNS)].iloc[-1].tolist() == _expected_row(
        _stream(synthetic_source), 4,
    )


@pytest.mark.parametrize("empty_ongoing", [False, True])
def test_one_feature_call_receives_only_three_columns_in_supplied_order(
    monkeypatch, synthetic_source, empty_ongoing,
):
    if empty_ongoing:
        synthetic_source.ongoing.matches = synthetic_source.ongoing.matches.iloc[:0].copy()
    expected = _stream(synthetic_source)
    feature_calls, concatenations = [], []
    add_features = history_module.add_schedule_gap_features
    concatenate = pd.concat

    def feature_spy(frame):
        feature_calls.append(frame.copy(deep=True))
        return add_features(frame)

    def concat_spy(frames, *args, **kwargs):
        frames = list(frames)
        concatenations.append(frames)
        return concatenate(frames, *args, **kwargs)

    monkeypatch.setattr(history_module, "add_schedule_gap_features", feature_spy)
    monkeypatch.setattr(history_module.pd, "concat", concat_spy)
    _load(monkeypatch, synthetic_source)
    assert len(feature_calls) == len(concatenations) == 1
    assert len(concatenations[0]) == (2 if empty_ongoing else 3)
    assert all(frame.columns.tolist() == INPUT_COLUMNS for frame in concatenations[0])
    assert_frame_equal(feature_calls[0], expected)


@pytest.mark.parametrize("custom_arguments", [False, True])
def test_elo_loader_is_called_once_with_forwarded_arguments(monkeypatch, synthetic_source, tmp_path, custom_arguments):
    calls = []

    def loader(processed_dir, *, team_master):
        calls.append((processed_dir, team_master))
        return synthetic_source

    monkeypatch.setattr(history_module, "load_elo_history_with_ongoing", loader)
    if custom_arguments:
        master = object()
        directory = tmp_path / "saved_history"
        history_module.load_schedule_gap_history_with_ongoing(directory, team_master=master)
        assert calls == [(directory, master)]
    else:
        history_module.load_schedule_gap_history_with_ongoing()
        assert calls == [(DEFAULT_PROCESSED_DIR, None)]


@pytest.mark.parametrize("name,empty", [
    ("historical", False), ("hyakunen", False), ("ongoing", False), ("ongoing", True),
])
def test_existing_output_columns_are_rejected(monkeypatch, synthetic_source, name, empty):
    frame = getattr(synthetic_source, name).matches
    if empty:
        frame = frame.iloc[:0].copy()
        getattr(synthetic_source, name).matches = frame
    frame[SCHEDULE_GAP_COLUMNS[0]] = pd.array([99] * len(frame), dtype="int64")
    with pytest.raises(ValueError, match="already exist"):
        _load(monkeypatch, synthetic_source)
