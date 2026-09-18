"""Compose the 38-column context table and existing Elo momentum by position."""

from types import SimpleNamespace
from unittest.mock import Mock, sentinel

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import training_dataset_full as subject
from src.features.elo_history import DEFAULT_PROCESSED_DIR
from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS


BASE_COLUMNS = DATASET_COLUMNS + MATCHUP_CONTEXT_COLUMNS + SCHEDULE_GAP_COLUMNS
MOMENTUM_COLUMNS = (
    "home_elo_change_last5", "away_elo_change_last5", "elo_change_last5_diff",
    "home_elo_change_last5_matches", "away_elo_change_last5_matches",
)


def frames(history):
    return history.historical, history.hyakunen, history.ongoing


def combined_momentum(history):
    return pd.concat(
        [frame.loc[:, ["match_id", *MOMENTUM_COLUMNS]]
         for frame in frames(history) if not frame.empty],
        ignore_index=True,
    )


@pytest.fixture(scope="module")
def real_inputs():
    base = subject.load_training_dataset_with_context()
    history = subject.load_elo_momentum_history_with_ongoing()
    snapshots = [frame.copy(deep=True) for frame in (base, *frames(history))]
    return base, history, snapshots


@pytest.fixture
def mock_loaders(monkeypatch):
    def install(base, history):
        loaders = Mock(return_value=base), Mock(return_value=history)
        monkeypatch.setattr(subject, "load_training_dataset_with_context", loaders[0])
        monkeypatch.setattr(subject, "load_elo_momentum_history_with_ongoing", loaders[1])
        return loaders
    return install


@pytest.fixture
def real_output(real_inputs, mock_loaders):
    mock_loaders(*real_inputs[:2])
    return subject.load_training_dataset_full()


@pytest.fixture
def synthetic_inputs():
    base = pd.DataFrame({column: [0, 1, 2, 3] for column in BASE_COLUMNS})
    base["match_id"] = pd.array(["z", "b", "a", "y"], dtype="string")
    base["home_elo"] = pd.array([1500.25, 1510.5, 1499.0, 1502.75], dtype="Float64")
    base["match_date"] = pd.date_range("2026-01-01", periods=4)
    base.index = pd.Index([7, 7, -2, 10], name="source_row")
    momentum = pd.DataFrame({
        "match_id": base["match_id"].array.copy(),
        MOMENTUM_COLUMNS[0]: pd.array([0, 1234.5, -2.25, 5678.75], dtype="Float64"),
        MOMENTUM_COLUMNS[1]: pd.array([0, 7.5, 4.25, -30.75], dtype="Float64"),
        MOMENTUM_COLUMNS[2]: pd.array([0, 1227, -6.5, 5709.5], dtype="Float64"),
        MOMENTUM_COLUMNS[3]: pd.array([0, 1, 4, 5], dtype="Int8"),
        MOMENTUM_COLUMNS[4]: pd.array([0, 1, 2, 5], dtype="Int64"),
    })
    momentum.index = pd.Index([90, 90, -7, 12], name="history_row")
    history = SimpleNamespace(
        historical=momentum.iloc[:2].copy(deep=True),
        hyakunen=momentum.iloc[2:3].copy(deep=True),
        ongoing=momentum.iloc[3:].copy(deep=True),
    )
    return base, history


def test_real_shape_schema_and_original_38_columns(real_inputs, real_output):
    assert real_output.shape == (3858, 43)
    assert ELO_MOMENTUM_COLUMNS == MOMENTUM_COLUMNS
    assert tuple(real_output.columns) == BASE_COLUMNS + MOMENTUM_COLUMNS
    assert_frame_equal(real_output.iloc[:, :38], real_inputs[0], check_exact=True)


def test_real_ids_are_unique_nonmissing_and_ordered_across_three_parts(real_inputs, real_output):
    base, history, _ = real_inputs
    assert real_output["match_id"].is_unique
    assert real_output["match_id"].notna().all()
    assert real_output["match_id"].tolist() == base["match_id"].tolist()
    assert [len(frame) for frame in frames(history)] == [3588, 200, 70]
    offset = 0
    for frame in frames(history):
        assert real_output.iloc[offset:offset + len(frame)]["match_id"].tolist() == frame["match_id"].tolist()
        offset += len(frame)
    assert offset == len(real_output)


def test_real_momentum_values_and_dtypes_match_history_without_missing_values(real_inputs, real_output):
    actual = real_output.loc[:, list(MOMENTUM_COLUMNS)]
    expected = combined_momentum(real_inputs[1]).loc[:, list(MOMENTUM_COLUMNS)]
    assert actual.notna().all().all()
    assert_frame_equal(actual.reset_index(drop=True), expected, check_exact=True)


def test_real_calls_are_repeatable_and_do_not_mutate_inputs(real_inputs, real_output):
    repeated = subject.load_training_dataset_full()
    assert repeated is not real_output
    assert_frame_equal(repeated, real_output, check_exact=True)
    base, history, snapshots = real_inputs
    for source, snapshot in zip((base, *frames(history)), snapshots):
        assert_frame_equal(source, snapshot, check_exact=True)


def test_source_scores_pk_extra_time_and_postmatch_fields_are_excluded(synthetic_inputs, mock_loaders):
    base, history = synthetic_inputs
    forbidden = (
        "home_score", "away_score", "home_goals", "away_goals", "home_pk", "away_pk",
        "home_score_pk", "away_score_pk", "extra_time", "home_score_et", "away_score_et",
        "tie_winner", "winner", "home_elo_after", "away_elo_after", "postgame_result",
    )
    for frame in frames(history):
        for column in forbidden:
            frame[column] = 999
    mock_loaders(base, history)
    output = subject.load_training_dataset_full()
    assert tuple(output.columns) == BASE_COLUMNS + MOMENTUM_COLUMNS
    assert not set(forbidden).intersection(output.columns)
    assert output["result"].equals(base["result"])


@pytest.mark.parametrize("empty_ongoing", [False, True])
def test_positional_values_duplicate_index_and_nullable_dtypes_are_preserved(
    synthetic_inputs, mock_loaders, empty_ongoing,
):
    base, history = synthetic_inputs
    if empty_ongoing:
        base = base.iloc[:-1].copy(deep=True)
        history.ongoing = history.ongoing.iloc[:0].astype(object)
    mock_loaders(base, history)
    output = subject.load_training_dataset_full()
    assert_frame_equal(output.iloc[:, :38], base, check_exact=True)
    assert_frame_equal(
        output.loc[:, list(MOMENTUM_COLUMNS)].reset_index(drop=True),
        combined_momentum(history).loc[:, list(MOMENTUM_COLUMNS)], check_exact=True,
    )


def test_output_and_sources_are_detached_in_both_directions(synthetic_inputs, mock_loaders):
    base, history = synthetic_inputs
    sources = (base, *frames(history))
    snapshots = [frame.copy(deep=True) for frame in sources]
    mock_loaders(base, history)
    output = subject.load_training_dataset_full()
    output.iloc[0, output.columns.get_loc("home_elo")] = pd.NA
    output.iloc[0, output.columns.get_loc(MOMENTUM_COLUMNS[0])] = pd.NA
    for source, snapshot in zip(sources, snapshots):
        assert_frame_equal(source, snapshot, check_exact=True)
    output_snapshot = output.copy(deep=True)
    base.iloc[1, base.columns.get_loc("home_elo")] = pd.NA
    for frame in frames(history):
        frame.iloc[-1, frame.columns.get_loc(MOMENTUM_COLUMNS[1])] = pd.NA
    assert_frame_equal(output, output_snapshot, check_exact=True)


@pytest.mark.parametrize("use_defaults", [True, False])
def test_arguments_are_forwarded_once_to_both_loaders(synthetic_inputs, mock_loaders, tmp_path, use_defaults):
    loaders = mock_loaders(*synthetic_inputs)
    if use_defaults:
        subject.load_training_dataset_full()
        directory, master = DEFAULT_PROCESSED_DIR, None
    else:
        directory, master = tmp_path, sentinel.team_master
        subject.load_training_dataset_full(directory, team_master=master)
    for loader in loaders:
        loader.assert_called_once_with(directory, team_master=master)


@pytest.mark.parametrize("change", ["different_id", "reordered_ids", "shorter_base", "shorter_history"])
def test_id_order_and_row_count_mismatches_raise_explicit_errors(synthetic_inputs, mock_loaders, change):
    base, history = synthetic_inputs
    if change == "different_id":
        history.ongoing["match_id"] = "another-match"
    elif change == "reordered_ids":
        history.historical = history.historical.iloc[::-1].copy(deep=True)
    elif change == "shorter_base":
        base = base.iloc[:-1].copy(deep=True)
    else:
        history.ongoing = history.ongoing.iloc[:0].copy(deep=True)
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)match_id|row order|row count|length|alignment"):
        subject.load_training_dataset_full()


@pytest.mark.parametrize("invalid_input", ["base", "history"])
@pytest.mark.parametrize("invalid_id", ["duplicate", "missing"])
def test_missing_or_duplicate_ids_are_rejected(synthetic_inputs, mock_loaders, invalid_input, invalid_id):
    base, history = synthetic_inputs
    frame = base if invalid_input == "base" else history.hyakunen
    value = base["match_id"].iloc[0] if invalid_id == "duplicate" else pd.NA
    frame.iloc[-1, frame.columns.get_loc("match_id")] = value
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)match_id.*(nonmissing|missing|unique)|(?:duplicate|missing).*match_id"):
        subject.load_training_dataset_full()


@pytest.mark.parametrize("column", MOMENTUM_COLUMNS)
def test_missing_momentum_values_are_rejected(synthetic_inputs, mock_loaders, column):
    base, history = synthetic_inputs
    history.hyakunen.iloc[0, history.hyakunen.columns.get_loc(column)] = pd.NA
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)missing|nan|null"):
        subject.load_training_dataset_full()


@pytest.mark.parametrize("schema_change", ["missing", "extra", "reordered"])
def test_invalid_base_schema_is_rejected(synthetic_inputs, mock_loaders, schema_change):
    base, history = synthetic_inputs
    if schema_change == "missing":
        base = base.drop(columns=BASE_COLUMNS[-1])
    elif schema_change == "extra":
        base = base.assign(unexpected_score=3)
    else:
        base = base.loc[:, [BASE_COLUMNS[1], BASE_COLUMNS[0], *BASE_COLUMNS[2:]]]
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)38|columns|schema"):
        subject.load_training_dataset_full()
