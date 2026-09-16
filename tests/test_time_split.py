"""Fixed chronological partitions retain every existing training-table value."""

import socket

import pandas as pd
import pytest

from src.features.training_dataset import DATASET_COLUMNS, load_training_dataset
from src.modeling.time_split import split_training_dataset


PARTITIONS = (
    ("train", set(range(2015, 2024))),
    ("validation", {2024}),
    ("test", {2025}),
    ("reserved", {2026}),
)


@pytest.fixture(scope="module")
def real_dataset():
    def forbid_network(*args, **kwargs):
        pytest.fail("Time splitting must not access the network.")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", forbid_network)
        patch.setattr(socket.socket, "connect_ex", forbid_network)
        try:
            return load_training_dataset()
        except FileNotFoundError as exc:
            pytest.skip(f"Saved local match data are unavailable: {exc}")


@pytest.fixture(scope="module")
def real_split(real_dataset):
    return split_training_dataset(real_dataset)


def test_real_partition_counts(real_dataset, real_split):
    counts = [len(getattr(real_split, name)) for name, _ in PARTITIONS]
    assert counts == [2828, 380, 380, 270]
    assert sum(counts) == len(real_dataset) == 3858


@pytest.mark.parametrize("name,seasons", PARTITIONS)
def test_partition_seasons(real_split, name, seasons):
    assert set(getattr(real_split, name)["season"]) == seasons


def test_original_24_columns_are_preserved(real_dataset, real_split):
    assert real_dataset.columns.tolist() == list(DATASET_COLUMNS)
    assert len(real_dataset.columns) == 24
    for name, _ in PARTITIONS:
        pd.testing.assert_index_equal(
            getattr(real_split, name).columns, real_dataset.columns,
        )


def test_match_ids_are_unique_within_and_between_partitions(real_split):
    seen = set()
    for name, _ in PARTITIONS:
        match_ids = getattr(real_split, name)["match_id"]
        assert match_ids.is_unique
        assert seen.isdisjoint(match_ids)
        seen.update(match_ids)


def test_partitions_cover_every_original_match_id(real_dataset, real_split):
    actual = set().union(*(
        set(getattr(real_split, name)["match_id"]) for name, _ in PARTITIONS
    ))
    assert actual == set(real_dataset["match_id"])


def test_original_chronological_rows_and_values_are_preserved(real_dataset, real_split):
    for name, seasons in PARTITIONS:
        actual = getattr(real_split, name)
        expected = real_dataset.loc[real_dataset["season"].isin(seasons)]
        pd.testing.assert_frame_equal(actual, expected)
        assert pd.to_datetime(actual["match_date"]).is_monotonic_increasing


def test_input_is_not_modified(real_dataset):
    before = real_dataset.copy(deep=True)
    split_training_dataset(real_dataset)
    pd.testing.assert_frame_equal(real_dataset, before)


def test_same_input_produces_same_results(real_dataset, real_split):
    repeated = split_training_dataset(real_dataset)
    for name, _ in PARTITIONS:
        pd.testing.assert_frame_equal(
            getattr(repeated, name), getattr(real_split, name),
        )


@pytest.fixture
def small_dataset():
    seasons = [2015, 2023, 2024, 2025, 2026, 2026]
    dates = ["2015-03-01", "2023-12-01", "2024-03-01", "2025-03-01",
             "2026-03-01", "2027-03-01"]
    dataset = pd.DataFrame(0, index=range(len(seasons)), columns=DATASET_COLUMNS)
    dataset["match_id"] = [f"match-{i}" for i in range(len(seasons))]
    dataset["match_date"] = dates
    dataset["season"] = seasons
    dataset.index = pd.Index([40, 10, 90, 30, 70, 20], name="source_row")
    return dataset


def test_cross_year_2026_season_remains_reserved_with_original_indices(small_dataset):
    before = small_dataset.copy(deep=True)
    split = split_training_dataset(small_dataset)
    for name, seasons in PARTITIONS:
        actual = getattr(split, name)
        expected = before.loc[before["season"].isin(seasons)]
        pd.testing.assert_frame_equal(actual, expected)
        actual.loc[:, "home_elo"] = -1
    assert split.reserved["match_date"].tolist() == ["2026-03-01", "2027-03-01"]
    pd.testing.assert_frame_equal(small_dataset, before)


@pytest.mark.parametrize(
    "column,value",
    [
        ("match_id", "match-1"),
        ("season", 2027),
        ("match_date", "2016-03-01"),
    ],
)
def test_invalid_rows_are_rejected_without_modifying_input(small_dataset, column, value):
    small_dataset.loc[40, column] = value
    before = small_dataset.copy(deep=True)
    with pytest.raises(ValueError):
        split_training_dataset(small_dataset)
    pd.testing.assert_frame_equal(small_dataset, before)
