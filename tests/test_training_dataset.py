"""The training table only selects existing pre-match values and the target."""

import socket

import pandas as pd
import pytest

from src.features import training_dataset
from src.features.form_history import OngoingFormHistory


EXPECTED_COLUMNS = [
    "match_id", "match_date", "season", "competition",
    "home_team", "away_team", "home_team_id", "away_team_id",
    "home_elo", "away_elo", "elo_diff",
    "home_last5_points", "away_last5_points",
    "home_last5_wins", "away_last5_wins",
    "home_last5_draws", "away_last5_draws",
    "home_last5_losses", "away_last5_losses",
    "home_last5_goals_for", "away_last5_goals_for",
    "home_last5_goals_against", "away_last5_goals_against",
    "result",
]
ELO_COLUMNS = EXPECTED_COLUMNS[8:11]
FORM_COLUMNS = EXPECTED_COLUMNS[11:23]


@pytest.fixture(scope="module")
def real_dataset():
    """Exercise the public loader once against the saved local publication."""
    histories = []
    original_loader = training_dataset.load_form_history_with_ongoing

    def record_history(*args, **kwargs):
        history = original_loader(*args, **kwargs)
        histories.append(history)
        return history

    def forbid_network(*args, **kwargs):
        pytest.fail("Training dataset generation must not access the network.")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", forbid_network)
        patch.setattr(socket.socket, "connect_ex", forbid_network)
        patch.setattr(training_dataset, "load_form_history_with_ongoing", record_history)
        try:
            dataset = training_dataset.load_training_dataset()
        except FileNotFoundError as exc:
            pytest.skip(f"Saved local match data are unavailable: {exc}")
    assert len(histories) == 1
    return dataset, histories[0]


def test_real_dataset_has_one_row_per_match(real_dataset):
    dataset, _ = real_dataset
    assert len(dataset) == 3858
    assert dataset["match_id"].is_unique


def test_output_columns_match_the_fixed_order(real_dataset):
    dataset, _ = real_dataset
    assert dataset.columns.tolist() == EXPECTED_COLUMNS


def test_source_order_and_existing_values_are_preserved(real_dataset):
    dataset, history = real_dataset
    frames = (history.historical, history.hyakunen, history.ongoing)
    expected = pd.concat(
        [frame.loc[:, EXPECTED_COLUMNS] for frame in frames], ignore_index=True,
    )
    pd.testing.assert_frame_equal(dataset, expected)
    assert pd.to_datetime(dataset["match_date"]).is_monotonic_increasing


def test_elo_and_all_twelve_form_columns_have_no_missing_values(real_dataset):
    dataset, _ = real_dataset
    assert len(FORM_COLUMNS) == 12
    assert not dataset[ELO_COLUMNS + FORM_COLUMNS].isna().any().any()


def test_first_match_starts_with_initial_elo_and_zero_form(real_dataset):
    dataset, _ = real_dataset
    first = dataset.iloc[0]
    assert first["home_elo"] == 1500
    assert first["away_elo"] == 1500
    assert first[FORM_COLUMNS].eq(0).all()


def test_result_uses_only_existing_three_class_targets(real_dataset):
    dataset, _ = real_dataset
    assert dataset["result"].isin([0, 1, 2]).all()


def test_current_match_outcomes_and_source_metadata_are_excluded(real_dataset):
    dataset, history = real_dataset
    source_columns = set().union(
        history.historical.columns, history.hyakunen.columns, history.ongoing.columns,
    )
    excluded_columns = source_columns - set(EXPECTED_COLUMNS)
    assert {"home_score", "away_score"}.issubset(excluded_columns)
    assert excluded_columns.isdisjoint(dataset.columns)


@pytest.mark.parametrize("empty_ongoing", [False, True])
def test_repeated_loads_preserve_inputs_and_return_independent_frames(
    real_dataset, monkeypatch, empty_ongoing,
):
    _, history = real_dataset
    frames = [
        history.historical.iloc[:2].copy(deep=True),
        history.hyakunen.iloc[:2].copy(deep=True),
        history.ongoing.iloc[:0 if empty_ongoing else 2].copy(deep=True),
    ]
    for position, frame in enumerate(frames):
        frame.index = pd.Index(
            range(position * 10, position * 10 + len(frame) * 2, 2), name="source_row",
        )
    originals = [frame.copy(deep=True) for frame in frames]
    supplied_history = OngoingFormHistory(*frames)
    supplied_master = object()
    calls = []

    def load_history(processed_dir, *, team_master):
        calls.append((processed_dir, team_master))
        return supplied_history

    monkeypatch.setattr(training_dataset, "load_form_history_with_ongoing", load_history)
    first = training_dataset.load_training_dataset("saved-input", team_master=supplied_master)
    second = training_dataset.load_training_dataset("saved-input", team_master=supplied_master)
    assert calls == [("saved-input", supplied_master)] * 2
    expected = pd.concat(
        [frame.loc[:, EXPECTED_COLUMNS] for frame in originals if not frame.empty],
        ignore_index=True,
    )
    pd.testing.assert_frame_equal(first, expected)
    pd.testing.assert_frame_equal(first, second)
    first.loc[0, "home_elo"] = -1
    pd.testing.assert_frame_equal(second, expected)
    for frame, original in zip(frames, originals):
        pd.testing.assert_frame_equal(frame, original)
