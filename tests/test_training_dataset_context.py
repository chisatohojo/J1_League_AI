"""Strict positional composition of recorded-match context into training rows."""

from types import SimpleNamespace
from unittest.mock import Mock, patch, sentinel

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import training_dataset_context as subject
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.features.training_dataset_matchup import DEFAULT_PROCESSED_DIR


BASE_COLUMNS = DATASET_COLUMNS + MATCHUP_CONTEXT_COLUMNS
GAP_COLUMNS = (
    "home_days_since_last_match", "away_days_since_last_match",
    "days_since_last_match_diff", "home_has_previous_match", "away_has_previous_match",
)


def frames(history):
    return history.historical, history.hyakunen, history.ongoing


def combined_gaps(history):
    return pd.concat(
        [frame.loc[:, ["match_id", *GAP_COLUMNS]] for frame in frames(history) if not frame.empty],
        ignore_index=True,
    )


@pytest.fixture(scope="module")
def real_inputs():
    base = subject.load_training_dataset_with_matchup_context()
    history = subject.load_schedule_gap_history_with_ongoing()
    snapshots = [frame.copy(deep=True) for frame in (base, *frames(history))]
    return base, history, snapshots


@pytest.fixture(scope="module")
def real_output(real_inputs):
    base, history, _ = real_inputs
    with (
        patch.object(subject, "load_training_dataset_with_matchup_context", return_value=base),
        patch.object(subject, "load_schedule_gap_history_with_ongoing", return_value=history),
    ):
        return subject.load_training_dataset_with_context()


@pytest.fixture
def synthetic_inputs():
    base = pd.DataFrame({column: [0, 1, 2, 3] for column in BASE_COLUMNS})
    base["match_id"] = pd.array(["z", "b", "a", "y"], dtype="string")
    base["match_date"] = pd.date_range("2026-01-01", periods=4)
    base["competition"] = pd.array(["historical", "historical", "hyakunen", "ongoing"], dtype="string")
    base["home_elo"] = pd.array([1500.25, 1510.5, 1499.0, 1502.75], dtype="Float64")
    base.index = pd.Index([7, 7, -2, 10], name="source_row")
    gaps = pd.DataFrame({
        "match_id": base["match_id"].array.copy(),
        GAP_COLUMNS[0]: pd.array([0, 1234, 2, 5678], dtype="Int64"),
        GAP_COLUMNS[1]: pd.array([0, 7, 4, 30], dtype="Int64"),
        GAP_COLUMNS[2]: pd.array([0, 1227, -2, 5648], dtype="Int64"),
        GAP_COLUMNS[3]: pd.array([0, 1, 1, 1], dtype="Int8"),
        GAP_COLUMNS[4]: pd.array([0, 1, 1, 1], dtype="Int8"),
    })
    gaps.index = pd.Index([90, 90, -7, 12], name="history_row")
    history = SimpleNamespace(
        historical=gaps.iloc[:2].copy(deep=True),
        hyakunen=gaps.iloc[2:3].copy(deep=True),
        ongoing=gaps.iloc[3:].copy(deep=True),
    )
    return base, history


@pytest.fixture
def mock_loaders(monkeypatch):
    def install(base, history):
        base_loader, gap_loader = Mock(return_value=base), Mock(return_value=history)
        monkeypatch.setattr(subject, "load_training_dataset_with_matchup_context", base_loader)
        monkeypatch.setattr(subject, "load_schedule_gap_history_with_ongoing", gap_loader)
        return base_loader, gap_loader
    return install


def test_real_shape(real_output):
    assert real_output.shape == (3858, 38)


def test_real_original_33_columns_are_unchanged(real_inputs, real_output):
    assert_frame_equal(real_output.iloc[:, :33], real_inputs[0], check_exact=True)


def test_real_five_columns_follow_in_required_order(real_output):
    assert SCHEDULE_GAP_COLUMNS == GAP_COLUMNS
    assert tuple(real_output.columns) == BASE_COLUMNS + GAP_COLUMNS


def test_real_match_ids_are_unique_and_nonmissing(real_output):
    assert real_output["match_id"].is_unique
    assert real_output["match_id"].notna().all()


def test_real_match_id_order_matches_both_inputs(real_inputs, real_output):
    base, history, _ = real_inputs
    assert real_output["match_id"].tolist() == base["match_id"].tolist()
    assert real_output["match_id"].tolist() == combined_gaps(history)["match_id"].tolist()


def test_real_gap_features_have_no_missing_values(real_output):
    assert real_output.loc[:, list(GAP_COLUMNS)].notna().all().all()


def test_real_intervals_remain_historical_hyakunen_ongoing(real_inputs, real_output):
    offset = 0
    for frame in frames(real_inputs[1]):
        assert real_output.iloc[offset:offset + len(frame)]["match_id"].tolist() == frame["match_id"].tolist()
        offset += len(frame)
    assert offset == len(real_output)


def test_real_gap_values_and_dtypes_equal_recorded_history(real_inputs, real_output):
    expected = combined_gaps(real_inputs[1]).loc[:, list(GAP_COLUMNS)]
    assert_frame_equal(real_output.loc[:, list(GAP_COLUMNS)].reset_index(drop=True), expected, check_exact=True)


def test_real_sources_remain_unchanged(real_inputs, real_output):
    base, history, snapshots = real_inputs
    for original, snapshot in zip((base, *frames(history)), snapshots):
        assert_frame_equal(original, snapshot, check_exact=True)


def test_repeated_calls_are_deterministic(real_inputs, mock_loaders):
    mock_loaders(*real_inputs[:2])
    assert_frame_equal(
        subject.load_training_dataset_with_context(),
        subject.load_training_dataset_with_context(),
        check_exact=True,
    )


def test_source_outcome_and_postgame_fields_are_excluded(synthetic_inputs, mock_loaders):
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
    output = subject.load_training_dataset_with_context()
    assert tuple(output.columns) == BASE_COLUMNS + GAP_COLUMNS
    assert not set(forbidden).intersection(output.columns)
    assert output["result"].equals(base["result"])


def test_duplicate_custom_index_and_extension_dtypes_are_preserved(synthetic_inputs, mock_loaders):
    base, history = synthetic_inputs
    mock_loaders(base, history)
    output = subject.load_training_dataset_with_context()
    assert_frame_equal(output.iloc[:, :33], base, check_exact=True)
    assert_frame_equal(
        output.loc[:, list(GAP_COLUMNS)].reset_index(drop=True),
        combined_gaps(history).loc[:, list(GAP_COLUMNS)], check_exact=True,
    )


def test_recorded_gaps_are_not_recomputed_or_capped(synthetic_inputs, mock_loaders):
    mock_loaders(*synthetic_inputs)
    output = subject.load_training_dataset_with_context()
    # Supplied recorded-stream gaps are authoritative, even across omitted matches.
    assert output[GAP_COLUMNS[0]].tolist() == [0, 1234, 2, 5678]
    assert output["match_id"].tolist() == ["z", "b", "a", "y"]


def test_output_and_sources_are_detached_in_both_directions(synthetic_inputs, mock_loaders):
    base, history = synthetic_inputs
    sources = (base, *frames(history))
    before = [frame.copy(deep=True) for frame in sources]
    mock_loaders(base, history)
    output = subject.load_training_dataset_with_context()
    for column, value in (("home_elo", 42.5), ("competition", "changed"), (GAP_COLUMNS[0], pd.NA)):
        output.iloc[0, output.columns.get_loc(column)] = value
    for original, snapshot in zip(sources, before):
        assert_frame_equal(original, snapshot, check_exact=True)
    output_snapshot = output.copy(deep=True)
    base.iloc[1, base.columns.get_loc("home_elo")] = pd.NA
    base.iloc[1, base.columns.get_loc("competition")] = "source changed"
    for frame in frames(history):
        frame.iloc[-1, frame.columns.get_loc(GAP_COLUMNS[1])] = pd.NA
    assert_frame_equal(output, output_snapshot, check_exact=True)


@pytest.mark.parametrize("use_defaults", [True, False])
def test_loader_arguments_are_forwarded_once(synthetic_inputs, mock_loaders, tmp_path, use_defaults):
    loaders = mock_loaders(*synthetic_inputs)
    if use_defaults:
        subject.load_training_dataset_with_context()
        expected_dir, expected_master = DEFAULT_PROCESSED_DIR, None
    else:
        expected_dir, expected_master = tmp_path, sentinel.team_master
        subject.load_training_dataset_with_context(expected_dir, team_master=expected_master)
    for loader in loaders:
        loader.assert_called_once_with(expected_dir, team_master=expected_master)


def test_empty_ongoing_is_skipped_without_widening_dtypes(synthetic_inputs, mock_loaders):
    base, history = synthetic_inputs
    base = base.iloc[:-1].copy(deep=True)
    history.ongoing = history.ongoing.iloc[:0].astype(object)
    mock_loaders(base, history)
    output = subject.load_training_dataset_with_context()
    assert_frame_equal(output.iloc[:, :33], base, check_exact=True)
    assert_frame_equal(
        output.loc[:, list(GAP_COLUMNS)].reset_index(drop=True),
        combined_gaps(history).loc[:, list(GAP_COLUMNS)], check_exact=True,
    )


@pytest.mark.parametrize("change", ["different_id", "reordered_ids"])
def test_id_or_order_mismatch_raises_explicit_error(synthetic_inputs, mock_loaders, change):
    base, history = synthetic_inputs
    if change == "different_id":
        history.ongoing["match_id"] = "another-match"
    else:
        history.historical = history.historical.iloc[::-1].copy(deep=True)
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)match_id|row order|alignment"):
        subject.load_training_dataset_with_context()


@pytest.mark.parametrize("shorter_input", ["base", "history"])
def test_row_count_mismatch_raises_explicit_error(synthetic_inputs, mock_loaders, shorter_input):
    base, history = synthetic_inputs
    if shorter_input == "base":
        base = base.iloc[:-1].copy(deep=True)
    else:
        history.ongoing = history.ongoing.iloc[:0].copy(deep=True)
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)row count|rowcount|length"):
        subject.load_training_dataset_with_context()


@pytest.mark.parametrize("invalid_input", ["base", "history"])
@pytest.mark.parametrize("invalid_id", ["duplicate", "missing"])
def test_duplicate_or_missing_ids_are_rejected(synthetic_inputs, mock_loaders, invalid_input, invalid_id):
    base, history = synthetic_inputs
    frame = base if invalid_input == "base" else history.hyakunen
    value = base["match_id"].iloc[0] if invalid_id == "duplicate" else pd.NA
    frame.iloc[-1, frame.columns.get_loc("match_id")] = value
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)match_id.*(nonmissing|missing|unique)|(?:duplicate|missing).*match_id"):
        subject.load_training_dataset_with_context()


@pytest.mark.parametrize("column", GAP_COLUMNS)
def test_missing_gap_values_are_rejected(synthetic_inputs, mock_loaders, column):
    base, history = synthetic_inputs
    history.hyakunen.iloc[0, history.hyakunen.columns.get_loc(column)] = pd.NA
    mock_loaders(base, history)
    with pytest.raises(ValueError, match=r"(?i)missing|nan|null"):
        subject.load_training_dataset_with_context()


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
    with pytest.raises(ValueError, match=r"(?i)33|columns|schema"):
        subject.load_training_dataset_with_context()
