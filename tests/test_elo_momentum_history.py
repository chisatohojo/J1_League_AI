"""Integration and isolation checks for the continuous Elo momentum adapter."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import elo_momentum_history
from src.features.elo_history import (
    DEFAULT_PROCESSED_DIR,
    EloHistory,
    EloRatings,
    OngoingEloHistory,
    load_elo_history_with_ongoing,
)
from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS, add_elo_momentum_features


PARTS = ("historical", "hyakunen", "ongoing")
INPUTS = ["match_date", "home_team_id", "away_team_id", "home_elo", "away_elo"]


def _frames(history):
    return tuple(getattr(history, part).matches for part in PARTS)


def _inputs(history):
    return pd.concat([frame.loc[:, INPUTS] for frame in _frames(history) if not frame.empty],
                     ignore_index=True)


def _oracle(rows, position):
    """Independently scan only prior rows, merge roles, then retain their tail(5)."""
    current = rows.iloc[position]
    prior = rows.iloc[:position]
    expected = {}
    for side in ("home", "away"):
        team_id = current[f"{side}_team_id"]
        appearances = pd.concat([
            prior.loc[prior[f"{role}_team_id"].eq(team_id), f"{role}_elo"]
            for role in ("home", "away")
        ]).sort_index().tail(5)
        expected[f"{side}_elo_change_last5"] = (
            float(current[f"{side}_elo"] - appearances.iloc[0]) if len(appearances) else 0.0
        )
        expected[f"{side}_elo_change_last5_matches"] = len(appearances)
    expected["elo_change_last5_diff"] = (
        expected["home_elo_change_last5"] - expected["away_elo_change_last5"]
    )
    return expected


def _assert_features(row, expected):
    for column in ELO_MOMENTUM_COLUMNS:
        if column.endswith("_matches"):
            assert row[column] == expected[column]
        else:
            assert row[column] == pytest.approx(expected[column])


def _load_mocked(monkeypatch, source):
    monkeypatch.setattr(elo_momentum_history, "load_elo_history_with_ongoing",
                        Mock(return_value=source))
    return elo_momentum_history.load_elo_momentum_history_with_ongoing()


@pytest.fixture(scope="module")
def saved_history():
    # Perform the existing loader's I/O and Elo replay just once for this module.
    source = load_elo_history_with_ongoing()
    snapshots = tuple(frame.copy(deep=True) for frame in _frames(source))
    ratings = tuple(dict(getattr(source, part).final_ratings) for part in PARTS)
    with patch.object(elo_momentum_history, "load_elo_history_with_ongoing",
                      return_value=source) as loader:
        result = elo_momentum_history.load_elo_momentum_history_with_ongoing()
    loader.assert_called_once_with(DEFAULT_PROCESSED_DIR, team_master=None)
    return SimpleNamespace(source=source, snapshots=snapshots, ratings=ratings,
                           result=result, inputs=_inputs(source))


@pytest.fixture
def synthetic_history():
    a_ratings = [1000, 1011, 1040, 1030, 1075, 1060, 1088, 1120, 1100, 1190, 1180]
    b_ratings = [1500, 1490, 1475, 1498, 1470, 1460, 1480, 1505, 1520, 1510, 1540]
    dates = [*pd.date_range("2025-11-01", periods=4),
             *pd.date_range("2026-02-01", periods=4),
             *pd.date_range("2026-08-01", periods=3)]
    records = []
    for position, (date, a_rating, b_rating) in enumerate(zip(dates, a_ratings, b_ratings)):
        a_home = position % 2 == 0
        records.append({
            "match_id": f"match-{100 - position}",
            "match_date": date,
            "home_team_id": "A" if a_home else "B",
            "away_team_id": "B" if a_home else "A",
            "home_elo": float(a_rating if a_home else b_rating),
            "away_elo": float(b_rating if a_home else a_rating),
            "result": "H" if a_home else "A",
            "home_score": 2,
            "away_score": 1,
        })
    all_rows = pd.DataFrame(records).astype({
        "match_id": "string", "home_team_id": "string", "away_team_id": "string",
        "result": "string", "home_score": "Int64", "away_score": "Int64",
    })
    historical = all_rows.iloc[:4].copy(deep=True)
    hyakunen = all_rows.iloc[4:8].copy(deep=True)
    ongoing = all_rows.iloc[8:].copy(deep=True)
    historical["ordinary_stage"] = pd.Categorical(["full"] * 4)
    hyakunen["pk_winner"] = pd.array([pd.NA, "A", pd.NA, "B"], dtype="string")
    hyakunen["playoff_leg"] = pd.array([pd.NA, pd.NA, 1, 2], dtype="Int64")
    ongoing["status"] = pd.array(["completed"] * 3, dtype="string")
    ongoing["evidence_url"] = pd.array(["saved-evidence"] * 3, dtype="string")
    historical.index = pd.Index([9, 9, 3, 1], name="historical_row")
    hyakunen.index = pd.Index(["same", "same", "z", "a"], name="special_row")
    ongoing.index = pd.MultiIndex.from_tuples(
        [("late", 2), ("late", 2), ("early", 1)], names=["revision", "row"],
    )
    return OngoingEloHistory(*[
        EloHistory(frame, {"A": 1234.5, "B": 1456.5})
        for frame in (historical, hyakunen, ongoing)
    ])


def test_saved_row_counts(saved_history):
    result = saved_history.result
    assert isinstance(result, elo_momentum_history.OngoingEloMomentumHistory)
    assert [len(getattr(result, part)) for part in PARTS] == [3588, 200, 70]
    assert sum(len(getattr(result, part)) for part in PARTS) == 3858


@pytest.mark.parametrize("part", PARTS)
def test_saved_source_columns_and_feature_types(saved_history, part):
    original = getattr(saved_history.source, part).matches
    output = getattr(saved_history.result, part)
    assert_frame_equal(output.loc[:, original.columns], original)
    assert list(output.columns) == [*original.columns, *ELO_MOMENTUM_COLUMNS]
    for column in ELO_MOMENTUM_COLUMNS:
        expected_dtype = "int64" if column.endswith("_matches") else "float64"
        assert str(output[column].dtype) == expected_dtype


def test_first_saved_historical_row_has_no_previous_appearances(saved_history):
    first = saved_history.result.historical.iloc[0]
    assert first.loc[list(ELO_MOMENTUM_COLUMNS)].eq(0).all()


@pytest.mark.parametrize("part", PARTS)
def test_saved_continuity_matches_independent_prior_tail5(saved_history, part):
    if part == "historical":
        # Cross an ordinary season boundary as well as both competition boundaries.
        dates = saved_history.source.historical.matches["match_date"]
        local_position = next(i for i, year in enumerate(dates.dt.year)
                              if year != dates.iloc[0].year)
    else:
        local_position = 0
    offset = sum(len(getattr(saved_history.source, earlier).matches)
                 for earlier in PARTS[:PARTS.index(part)])
    expected = _oracle(saved_history.inputs, offset + local_position)
    counts = [expected[f"{side}_elo_change_last5_matches"] for side in ("home", "away")]
    assert max(counts) == 5
    if part != "historical":
        assert min(counts) == 5
    _assert_features(getattr(saved_history.result, part).iloc[local_position], expected)


def test_saved_source_frames_and_rating_snapshots_are_unchanged(saved_history):
    for part, snapshot, ratings in zip(PARTS, saved_history.snapshots, saved_history.ratings):
        original = getattr(saved_history.source, part)
        assert_frame_equal(original.matches, snapshot)
        assert original.final_ratings == ratings


def test_saved_repeated_calls_are_deterministic(saved_history, monkeypatch):
    repeated = _load_mocked(monkeypatch, saved_history.source)
    for part in PARTS:
        assert_frame_equal(getattr(repeated, part), getattr(saved_history.result, part))


def test_every_synthetic_row_matches_independent_prior_tail5(synthetic_history, monkeypatch):
    result = _load_mocked(monkeypatch, synthetic_history)
    rows = _inputs(synthetic_history)
    actual = pd.concat([getattr(result, part).loc[:, list(ELO_MOMENTUM_COLUMNS)]
                        for part in PARTS], ignore_index=True)
    for position in range(len(rows)):
        _assert_features(actual.iloc[position], _oracle(rows, position))


def test_role_changes_share_the_same_team_history(synthetic_history, monkeypatch):
    result = _load_mocked(monkeypatch, synthetic_history)
    # A switches from home to away; its preceding home appearance still counts.
    second = result.historical.iloc[1]
    assert second["away_team_id"] == "A"
    assert second["away_elo_change_last5"] == 11.0
    assert second["away_elo_change_last5_matches"] == 1
    # The first Hyakunen row follows an away appearance in the historical part.
    boundary = result.hyakunen.iloc[0]
    assert boundary["home_team_id"] == "A"
    assert boundary["home_elo_change_last5"] == 75.0
    assert boundary["home_elo_change_last5_matches"] == 4


def test_tail5_excludes_older_appearances_across_both_boundaries(synthetic_history, monkeypatch):
    result = _load_mocked(monkeypatch, synthetic_history)
    assert result.hyakunen.iloc[2]["home_elo_change_last5"] == 1088.0 - 1011.0
    first_ongoing = result.ongoing.iloc[0]
    # Its five priors are the last historical row and all four Hyakunen rows.
    assert first_ongoing["home_elo_change_last5"] == 1100.0 - 1030.0
    assert first_ongoing["home_elo_change_last5"] != 1100.0 - 1000.0
    for part in PARTS:
        counts = getattr(result, part).loc[:, list(ELO_MOMENTUM_COLUMNS[-2:])]
        assert counts.le(5).all().all()
    assert first_ongoing["home_elo_change_last5_matches"] == 5
    assert first_ongoing["away_elo_change_last5_matches"] == 5


def test_different_schemas_duplicate_indices_and_order_are_preserved(synthetic_history, monkeypatch):
    snapshots = tuple(frame.copy(deep=True) for frame in _frames(synthetic_history))
    result = _load_mocked(monkeypatch, synthetic_history)
    for part, snapshot in zip(PARTS, snapshots):
        output = getattr(result, part)
        assert output is not getattr(synthetic_history, part).matches
        assert_frame_equal(output.loc[:, snapshot.columns], snapshot)
        assert list(output.columns) == [*snapshot.columns, *ELO_MOMENTUM_COLUMNS]
        assert_frame_equal(getattr(synthetic_history, part).matches, snapshot)


def test_output_mutation_cannot_change_source_frames(synthetic_history, monkeypatch):
    snapshots = tuple(frame.copy(deep=True) for frame in _frames(synthetic_history))
    result = _load_mocked(monkeypatch, synthetic_history)
    for part, snapshot in zip(PARTS, snapshots):
        output = getattr(result, part)
        output.iloc[0, output.columns.get_loc("home_elo")] = -999.0
        output.iloc[0, output.columns.get_loc("match_id")] = "changed-output"
        assert_frame_equal(getattr(synthetic_history, part).matches, snapshot)


def test_single_loader_and_momentum_calls_use_only_five_inputs(synthetic_history, monkeypatch):
    loader = Mock(return_value=synthetic_history)
    momentum = Mock(wraps=add_elo_momentum_features)
    monkeypatch.setattr(elo_momentum_history, "load_elo_history_with_ongoing", loader)
    monkeypatch.setattr(elo_momentum_history, "add_elo_momentum_features", momentum)
    directory = Path("unused-processed-directory")
    master = object()
    elo_momentum_history.load_elo_momentum_history_with_ongoing(directory, team_master=master)
    loader.assert_called_once_with(directory, team_master=master)
    momentum.assert_called_once()
    assert momentum.call_args.kwargs == {}
    assert len(momentum.call_args.args) == 1
    passed = momentum.call_args.args[0]
    assert list(passed.columns) == INPUTS
    assert_frame_equal(passed, _inputs(synthetic_history))


def test_poisoned_results_scores_and_extra_columns_do_not_affect_features(synthetic_history, monkeypatch):
    baseline = _load_mocked(monkeypatch, synthetic_history)

    class ForbiddenInput:
        def __float__(self):
            raise AssertionError("A result, score, or metadata value was used as a rating")

        def __int__(self):
            raise AssertionError("A result, score, or metadata value was interpreted")

        def __bool__(self):
            raise AssertionError("A result, score, or metadata value was inspected")

    for frame in _frames(synthetic_history):
        for column in ("result", "home_score", "away_score", "pk_score", "extra_metadata"):
            frame[column] = [ForbiddenInput() for _ in range(len(frame))]
    poisoned = _load_mocked(monkeypatch, synthetic_history)
    for part in PARTS:
        assert_frame_equal(
            getattr(poisoned, part).loc[:, list(ELO_MOMENTUM_COLUMNS)],
            getattr(baseline, part).loc[:, list(ELO_MOMENTUM_COLUMNS)],
        )


def test_adapter_never_updates_elo_after_source_loading(synthetic_history, monkeypatch):
    update = Mock(side_effect=AssertionError("The adapter must not update Elo ratings"))
    monkeypatch.setattr(EloRatings, "update", update)
    result = _load_mocked(monkeypatch, synthetic_history)
    assert len(result.ongoing) == 3
    update.assert_not_called()


def test_empty_ongoing_keeps_its_schema_index_and_typed_features(synthetic_history, monkeypatch):
    synthetic_history.ongoing.matches = synthetic_history.ongoing.matches.iloc[:0].copy(deep=True)
    original = synthetic_history.ongoing.matches.copy(deep=True)
    momentum = Mock(wraps=add_elo_momentum_features)
    monkeypatch.setattr(elo_momentum_history, "add_elo_momentum_features", momentum)
    result = _load_mocked(monkeypatch, synthetic_history)
    assert result.ongoing.empty
    assert_frame_equal(result.ongoing.loc[:, original.columns], original)
    assert list(result.ongoing.columns) == [*original.columns, *ELO_MOMENTUM_COLUMNS]
    for column in ELO_MOMENTUM_COLUMNS:
        assert str(result.ongoing[column].dtype) == (
            "int64" if column.endswith("_matches") else "float64"
        )
    momentum.assert_called_once()
    assert_frame_equal(momentum.call_args.args[0], _inputs(synthetic_history))
    _assert_features(result.hyakunen.iloc[-1], _oracle(_inputs(synthetic_history), 7))


@pytest.mark.parametrize("part,column", [
    ("historical", ELO_MOMENTUM_COLUMNS[0]),
    ("hyakunen", ELO_MOMENTUM_COLUMNS[1]),
    ("ongoing", ELO_MOMENTUM_COLUMNS[2]),
    ("historical", ELO_MOMENTUM_COLUMNS[3]),
    ("hyakunen", ELO_MOMENTUM_COLUMNS[4]),
])
def test_existing_feature_columns_are_rejected(synthetic_history, monkeypatch, part, column):
    getattr(synthetic_history, part).matches[column] = -123
    snapshots = tuple(frame.copy(deep=True) for frame in _frames(synthetic_history))
    with pytest.raises(ValueError, match="(?i)(already exist|collision)"):
        _load_mocked(monkeypatch, synthetic_history)
    for frame, snapshot in zip(_frames(synthetic_history), snapshots):
        assert_frame_equal(frame, snapshot)


def test_existing_feature_is_rejected_even_in_empty_ongoing(synthetic_history, monkeypatch):
    empty = synthetic_history.ongoing.matches.iloc[:0].copy(deep=True)
    empty[ELO_MOMENTUM_COLUMNS[0]] = pd.array([], dtype="float64")
    synthetic_history.ongoing.matches = empty
    with pytest.raises(ValueError, match="(?i)(already exist|collision)"):
        _load_mocked(monkeypatch, synthetic_history)
