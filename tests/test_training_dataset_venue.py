"""Strict alignment and source preservation for the 28-column training table."""

import socket
from unittest.mock import Mock

import pandas as pd
import pytest

from src.features import training_dataset_venue as module
from src.features.venue_form_history import OngoingVenueFormHistory


VENUE_COLUMNS = (
    "home_last5_home_points", "away_last5_away_points",
    "home_last5_home_goal_diff", "away_last5_away_goal_diff",
)
SEGMENTS = ("historical", "hyakunen", "ongoing")


@pytest.fixture(scope="module")
def real_data():
    base_loader = Mock(wraps=module.load_training_dataset)
    venue_loader = Mock(wraps=module.load_venue_form_history_with_ongoing)
    sources = {}

    def load_base(*args, **kwargs):
        sources["base"] = base_loader(*args, **kwargs)
        return sources["base"]

    def load_venue(*args, **kwargs):
        sources["venue"] = venue_loader(*args, **kwargs)
        return sources["venue"]

    def forbid_network(*args, **kwargs):
        pytest.fail("Dataset generation must not access the network.")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(module, "load_training_dataset", load_base)
        patch.setattr(module, "load_venue_form_history_with_ongoing", load_venue)
        patch.setattr(socket.socket, "connect", forbid_network)
        patch.setattr(socket.socket, "connect_ex", forbid_network)
        try:
            output = module.load_training_dataset_with_venue_form()
        except FileNotFoundError as exc:
            pytest.skip(f"Saved local match data are unavailable: {exc}")
    base_loader.assert_called_once()
    venue_loader.assert_called_once()
    return output, sources["base"], sources["venue"]


@pytest.fixture
def sources():
    base = pd.DataFrame(0, index=range(4), columns=module.DATASET_COLUMNS)
    base["match_id"] = pd.array(["h-1", "h-2", "special", "current"], dtype="string")
    base["match_date"] = pd.to_datetime(["2015-03-01", "2025-12-01", "2026-02-01", "2026-08-01"])
    base["season"] = pd.array([2015, 2025, 2026, 2026], dtype="Int64")
    base["competition"] = pd.Categorical(["J1", "J1", "Hyakunen", "J1"])
    base["elo_diff"] = pd.Series([0.0, -12.5, 30.0, 8.0], dtype="float32")
    base.index = pd.Index([9, 2, 9, 1], name="source_row")
    venue = pd.DataFrame({"match_id": base["match_id"].to_numpy()})
    for number, column in enumerate(VENUE_COLUMNS):
        venue[column] = [number + 10 * row for row in range(4)]
    venue["home_score"] = 99
    venue["away_score"] = 88
    venue["tie_winner"] = "post-match field"
    parts = [venue.iloc[:2].copy(), venue.iloc[2:3].copy(), venue.iloc[3:].copy()]
    for part in parts:
        part.index = pd.Index([40] * len(part), name="venue_source_row")
    return base, OngoingVenueFormHistory(*parts)


def _install_sources(monkeypatch, sources):
    base, venue = sources
    loaders = (Mock(return_value=base), Mock(return_value=venue))
    monkeypatch.setattr(module, "load_training_dataset", loaders[0])
    monkeypatch.setattr(module, "load_venue_form_history_with_ongoing", loaders[1])
    return loaders


def test_real_row_count(real_data):
    assert len(real_data[0]) == 3858


def test_exactly_28_columns(real_data):
    assert real_data[0].shape == (3858, 28)


def test_original_24_columns_are_completely_preserved(real_data):
    output, base, _ = real_data
    pd.testing.assert_frame_equal(output.iloc[:, :24], base)


def test_appended_columns_have_the_fixed_order(real_data):
    assert tuple(real_data[0].columns[24:]) == VENUE_COLUMNS


def test_unique_ids_and_original_row_order(real_data):
    output, base, _ = real_data
    assert output["match_id"].is_unique
    pd.testing.assert_series_equal(output["match_id"], base["match_id"])


def test_venue_columns_have_no_missing_values(real_data):
    assert not real_data[0].loc[:, list(VENUE_COLUMNS)].isna().any().any()


def test_segment_order_and_venue_values_are_preserved(real_data):
    output, _, history = real_data
    frames = [getattr(history, name) for name in SEGMENTS]
    assert [len(frame) for frame in frames] == [3588, 200, 70]
    expected = pd.concat([frame.loc[:, ["match_id", *VENUE_COLUMNS]] for frame in frames], ignore_index=True)
    assert output["match_id"].tolist() == expected["match_id"].tolist()
    pd.testing.assert_frame_equal(output.loc[:, list(VENUE_COLUMNS)], expected.loc[:, list(VENUE_COLUMNS)])


def test_post_match_information_is_not_added(real_data):
    output, base, history = real_data
    source_columns = set().union(*(getattr(history, name).columns for name in SEGMENTS))
    excluded = source_columns - set(base.columns) - set(VENUE_COLUMNS)
    assert {"home_score", "away_score"}.issubset(excluded)
    assert excluded.isdisjoint(output.columns)
    assert output.columns.tolist() == base.columns.tolist() + list(VENUE_COLUMNS)


@pytest.mark.parametrize("empty_ongoing", [False, True])
def test_determinism_and_forwarded_loader_arguments(monkeypatch, sources, empty_ongoing):
    base, history = sources
    if empty_ongoing:
        base = base.iloc[:-1].copy()
        history.ongoing = history.ongoing.iloc[:0].copy()
    loaders = _install_sources(monkeypatch, (base, history))
    master = object()
    first = module.load_training_dataset_with_venue_form("local-input", team_master=master)
    second = module.load_training_dataset_with_venue_form("local-input", team_master=master)
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == len(base)
    for loader in loaders:
        assert loader.call_count == 2
        loader.assert_called_with("local-input", team_master=master)


def test_source_frames_dtypes_and_indices_are_unchanged(monkeypatch, sources):
    base, history = sources
    original_base = base.copy(deep=True)
    originals = [getattr(history, name).copy(deep=True) for name in SEGMENTS]
    _install_sources(monkeypatch, sources)
    output = module.load_training_dataset_with_venue_form()
    pd.testing.assert_frame_equal(output.iloc[:, :24], original_base)
    assert output[VENUE_COLUMNS[0]].tolist() == [0, 10, 20, 30]
    output.iloc[0, 0] = "output-only change"
    output.iloc[0, 24] = -999
    pd.testing.assert_frame_equal(base, original_base)
    for name, original in zip(SEGMENTS, originals):
        pd.testing.assert_frame_equal(getattr(history, name), original)


@pytest.mark.parametrize("problem", ["count", "match_id", "order"])
def test_misaligned_inputs_are_rejected(monkeypatch, sources, problem):
    base, history = sources
    if problem == "count":
        history.ongoing = history.ongoing.iloc[:0].copy()
    elif problem == "match_id":
        history.hyakunen.loc[:, "match_id"] = "wrong-match"
    else:
        history.historical = history.historical.iloc[::-1].copy()
    _install_sources(monkeypatch, (base, history))
    with pytest.raises(ValueError, match="Row count, match_id or row order"):
        module.load_training_dataset_with_venue_form()


@pytest.mark.parametrize("source", ["base", "venue"])
def test_duplicate_ids_are_rejected(monkeypatch, sources, source):
    base, history = sources
    if source == "base":
        base.iloc[1, 0] = base.iloc[0, 0]
    else:
        history.hyakunen.loc[:, "match_id"] = base.iloc[0, 0]
    _install_sources(monkeypatch, (base, history))
    with pytest.raises(ValueError, match="unique"):
        module.load_training_dataset_with_venue_form()
