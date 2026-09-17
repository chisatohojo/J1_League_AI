"""The matchup training table must append context without changing its base."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal, assert_series_equal

from src.features import training_dataset_matchup as module
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.matchup_context_history import load_matchup_context_history_with_ongoing
from src.features.training_dataset import DATASET_COLUMNS, load_training_dataset


def _frames(history):
    return (history.historical, history.hyakunen, history.ongoing)


def _combined(history):
    return pd.concat(
        [frame.loc[:, ["match_id", *MATCHUP_CONTEXT_COLUMNS]]
         for frame in _frames(history) if not frame.empty],
        ignore_index=True,
    )


def _patch_sources(monkeypatch, dataset, history):
    monkeypatch.setattr(module, "load_training_dataset", lambda *args, **kwargs: dataset)
    monkeypatch.setattr(
        module, "load_matchup_context_history_with_ongoing", lambda *args, **kwargs: history,
    )


@pytest.fixture(scope="module")
def real_sources():
    return load_training_dataset(), load_matchup_context_history_with_ongoing()


@pytest.fixture
def real_case(monkeypatch, real_sources):
    dataset, history = real_sources
    _patch_sources(monkeypatch, dataset, history)
    return dataset, history, module.load_training_dataset_with_matchup_context()


@pytest.fixture
def synthetic_case(monkeypatch):
    dataset = pd.DataFrame({column: range(6) for column in DATASET_COLUMNS})
    dataset["match_id"] = [f"match-{number}" for number in range(6)]
    context = pd.DataFrame({"match_id": dataset["match_id"]})
    for number, column in enumerate(MATCHUP_CONTEXT_COLUMNS):
        context[column] = [number * 10 + row for row in range(6)]
    context["home_score"] = 99
    history = SimpleNamespace(
        historical=context.iloc[:2].copy(),
        hyakunen=context.iloc[2:4].copy(),
        ongoing=context.iloc[4:].copy(),
    )
    _patch_sources(monkeypatch, dataset, history)
    return dataset, history


def test_real_dataset_has_3858_rows_and_33_columns(real_case):
    assert real_case[2].shape == (3858, 33)


def test_original_24_columns_values_dtypes_and_index_are_exact(real_case):
    dataset, _, output = real_case
    assert tuple(output.columns[:24]) == DATASET_COLUMNS
    assert_frame_equal(output.iloc[:, :24], dataset)


def test_appended_nine_columns_match_existing_context_in_order(real_case):
    _, history, output = real_case
    assert tuple(output.columns[24:]) == MATCHUP_CONTEXT_COLUMNS
    assert_frame_equal(output.iloc[:, 24:], _combined(history).iloc[:, 1:])


def test_real_match_ids_are_unique(real_case):
    assert real_case[2]["match_id"].is_unique


def test_real_match_ids_and_order_are_unchanged(real_case):
    dataset, _, output = real_case
    assert_series_equal(output["match_id"], dataset["match_id"])


def test_no_missing_feature_values_are_added(real_case):
    assert not real_case[2].iloc[:, 24:].isna().any().any()


def test_segments_remain_historical_then_hyakunen_then_ongoing(real_case):
    _, history, output = real_case
    offset = 0
    for frame in _frames(history):
        actual = output.iloc[offset:offset + len(frame)]
        assert actual["match_id"].tolist() == frame["match_id"].tolist()
        assert_frame_equal(
            actual.loc[:, list(MATCHUP_CONTEXT_COLUMNS)].reset_index(drop=True),
            frame.loc[:, list(MATCHUP_CONTEXT_COLUMNS)].reset_index(drop=True),
        )
        offset += len(frame)
    assert offset == len(output)


def test_no_scores_pk_extra_time_or_tiebreak_source_fields_leak(real_case):
    _, history, output = real_case
    expected = set(DATASET_COLUMNS) | set(MATCHUP_CONTEXT_COLUMNS)
    source_only = set().union(*(set(frame.columns) for frame in _frames(history))) - expected
    assert "home_score" in source_only
    assert not source_only.intersection(output.columns)
    assert set(output.columns) == expected


def test_repeated_calls_are_deterministic(real_case):
    output = real_case[2]
    repeated = module.load_training_dataset_with_matchup_context()
    assert repeated is not output
    assert_frame_equal(repeated, output)


def test_sources_are_unchanged_and_independent_of_output(synthetic_case):
    dataset, history = synthetic_case
    before = [frame.copy(deep=True) for frame in (dataset, *_frames(history))]
    output = module.load_training_dataset_with_matchup_context()
    for actual, expected in zip((dataset, *_frames(history)), before):
        assert_frame_equal(actual, expected)
    output.loc[0, "match_id"] = "changed"
    output.loc[0, MATCHUP_CONTEXT_COLUMNS[0]] = -999
    for actual, expected in zip((dataset, *_frames(history)), before):
        assert_frame_equal(actual, expected)


def test_mismatched_match_id_raises_explicit_error(synthetic_case):
    synthetic_case[1].hyakunen.loc[2, "match_id"] = "unknown-match"
    with pytest.raises(ValueError, match=r"(?i)(match_id|match id)"):
        module.load_training_dataset_with_matchup_context()


def test_reordered_match_ids_are_rejected(synthetic_case):
    history = synthetic_case[1]
    history.historical = history.historical.iloc[::-1].copy()
    with pytest.raises(ValueError, match=r"(?i)(order|match_id)"):
        module.load_training_dataset_with_matchup_context()


def test_row_count_mismatch_is_rejected(synthetic_case):
    history = synthetic_case[1]
    history.ongoing = history.ongoing.iloc[:1].copy()
    with pytest.raises(ValueError, match=r"(?i)(row|count|length)"):
        module.load_training_dataset_with_matchup_context()


@pytest.mark.parametrize("side", ["dataset", "context"])
@pytest.mark.parametrize("invalid_id", [None, "match-1"], ids=["missing", "duplicate"])
def test_missing_and_duplicate_ids_are_rejected_on_either_side(
    synthetic_case, side, invalid_id,
):
    dataset, history = synthetic_case
    target = dataset if side == "dataset" else history.historical
    target.loc[0, "match_id"] = invalid_id
    with pytest.raises(ValueError, match=r"(?i)(match_id|match id)"):
        module.load_training_dataset_with_matchup_context()


def test_missing_context_feature_is_rejected(synthetic_case):
    history = synthetic_case[1]
    history.hyakunen[MATCHUP_CONTEXT_COLUMNS[-1]] = pd.NA
    with pytest.raises(ValueError, match=r"(?i)(missing|nan|null)"):
        module.load_training_dataset_with_matchup_context()


@pytest.mark.parametrize("use_defaults", [True, False], ids=["defaults", "custom"])
def test_parameters_are_forwarded_to_both_loaders(monkeypatch, synthetic_case, use_defaults):
    dataset, history = synthetic_case
    calls = []

    def base_loader(processed_dir, *, team_master):
        calls.append(("base", processed_dir, team_master))
        return dataset

    def context_loader(processed_dir, *, team_master):
        calls.append(("context", processed_dir, team_master))
        return history

    monkeypatch.setattr(module, "load_training_dataset", base_loader)
    monkeypatch.setattr(module, "load_matchup_context_history_with_ongoing", context_loader)
    directory = module.DEFAULT_PROCESSED_DIR if use_defaults else Path("custom-processed")
    master = None if use_defaults else object()
    if use_defaults:
        module.load_training_dataset_with_matchup_context()
    else:
        module.load_training_dataset_with_matchup_context(directory, team_master=master)
    assert calls == [("base", directory, master), ("context", directory, master)]


def test_duplicate_index_and_extension_dtypes_are_preserved(synthetic_case):
    dataset, history = synthetic_case
    dataset["home_team"] = pd.array(["team"] * 6, dtype="string")
    dataset["result"] = pd.array([0, 1, 2, 0, 1, 2], dtype="Int64")
    dataset["competition"] = pd.Categorical(["league"] * 6)
    dataset["match_date"] = pd.date_range("2026-01-01", periods=6)
    dataset.index = pd.Index([7, 2, 7, 3, 2, 3], name="source_row")
    for frame in _frames(history):
        frame[MATCHUP_CONTEXT_COLUMNS[0]] = frame[MATCHUP_CONTEXT_COLUMNS[0]].astype("Int64")
        frame.index = pd.Index([80, 80], name="context_row")
    output = module.load_training_dataset_with_matchup_context()
    assert_frame_equal(output.iloc[:, :24], dataset)
    expected = _combined(history).iloc[:, 1:].copy()
    expected.index = dataset.index
    assert_frame_equal(output.iloc[:, 24:], expected)


def test_empty_ongoing_segment_is_supported(monkeypatch, synthetic_case):
    dataset, history = synthetic_case
    dataset = dataset.iloc[:4].copy()
    history.ongoing = history.ongoing.iloc[:0].copy()
    _patch_sources(monkeypatch, dataset, history)
    output = module.load_training_dataset_with_matchup_context()
    assert_frame_equal(output.iloc[:, :24], dataset)
    assert_frame_equal(output.iloc[:, 24:], _combined(history).iloc[:, 1:])
