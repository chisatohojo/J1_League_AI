"""Continuous venue form without changing source-specific match schemas."""

import socket
from unittest.mock import Mock

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import venue_form_history
from src.features.elo_history import DEFAULT_PROCESSED_DIR, EloHistory, OngoingEloHistory
from src.features.venue_form import VENUE_FORM_COLUMNS


PARTS = ("historical", "hyakunen", "ongoing")
INPUT_COLUMNS = [
    "match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result",
]


@pytest.fixture(scope="module")
def saved_history():
    paths = [DEFAULT_PROCESSED_DIR / f"{year}_matches_probe.csv" for year in range(2015, 2026)]
    paths.extend([
        DEFAULT_PROCESSED_DIR / "2026_hyakunen/matches.csv",
        DEFAULT_PROCESSED_DIR / "2026_27/latest.json",
    ])
    if not all(path.is_file() for path in paths):
        pytest.skip("Saved historical, Hyakunen and ongoing data are required.")

    original_loader = venue_form_history.load_elo_history_with_ongoing
    captured = []

    def capture_loader(*args, **kwargs):
        history = original_loader(*args, **kwargs)
        captured.append(history)
        return history

    def deny_network(*args, **kwargs):
        raise AssertionError("Venue form history must not access the network.")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket, "socket", deny_network)
        patch.setattr(socket, "create_connection", deny_network)
        patch.setattr(venue_form_history, "load_elo_history_with_ongoing", capture_loader)
        enriched = venue_form_history.load_venue_form_history_with_ongoing()
    assert len(captured) == 1
    return captured[0], enriched


@pytest.fixture
def sample_history():
    matches = pd.DataFrame([
        ("2025-01-01", "A", "B", 2, 0, 2),
        ("2025-01-02", "B", "A", 0, 4, 0),
        ("2025-01-03", "A", "B", 1, 1, 1),
        ("2025-01-04", "B", "A", 2, 0, 2),
        ("2026-02-01", "A", "B", 0, 3, 0),
        ("2026-02-02", "B", "A", 1, 1, 1),
        ("2026-08-01", "A", "B", 4, 2, 2),
        ("2026-08-02", "B", "A", 0, 1, 0),
    ], columns=INPUT_COLUMNS)
    matches["match_date"] = pd.to_datetime(matches["match_date"])
    historical = matches.iloc[:4].copy()
    hyakunen = matches.iloc[4:6].copy()
    ongoing = matches.iloc[6:].copy()
    historical["round"] = pd.array([1, 2, 3, 4], dtype="int64")
    historical["home_elo"] = pd.array([1500, 1510, 1520, 1530], dtype="float32")
    historical["historical_only"] = pd.Categorical(["first", "first", "second", "second"])
    historical.index = pd.Index([8, 2, 8, 4], name="source_row")
    hyakunen["round"] = pd.array([1, None], dtype="Int64")
    hyakunen["home_elo"] = pd.array([1540, 1550], dtype="float64")
    hyakunen["pk_home_score"] = pd.array([None, 4], dtype="Int64")
    hyakunen.index = pd.Index(["same", "same"], name="fixture")
    ongoing["round"] = pd.array(["1", "2"], dtype="string")
    ongoing["home_elo"] = pd.array([1560, 1570], dtype="Float64")
    ongoing["status"] = pd.array(["completed", "completed"], dtype="string")
    ongoing.index = pd.MultiIndex.from_tuples([(9, "b"), (3, "a")], names=["batch", "row"])
    return OngoingEloHistory(*(EloHistory(frame, {}) for frame in (historical, hyakunen, ongoing)))


def _load_sample(monkeypatch, history):
    monkeypatch.setattr(venue_form_history, "load_elo_history_with_ongoing", Mock(return_value=history))
    return venue_form_history.load_venue_form_history_with_ongoing()


def test_saved_match_counts(saved_history):
    _, result = saved_history
    counts = tuple(len(getattr(result, part)) for part in PARTS)
    assert counts == (3588, 200, 70)
    assert sum(counts) == 3858


def test_four_features_in_every_interval(saved_history):
    original, result = saved_history
    for part in PARTS:
        before = getattr(original, part).matches
        after = getattr(result, part)
        assert list(after.columns) == [*before.columns, *VENUE_FORM_COLUMNS]
        assert after.loc[:, list(VENUE_FORM_COLUMNS)].dtypes.eq("int64").all()


def test_first_historical_match_has_zero_features(saved_history):
    _, result = saved_history
    assert result.historical.loc[:, list(VENUE_FORM_COLUMNS)].iloc[0].eq(0).all()


@pytest.mark.parametrize("part", ["hyakunen", "ongoing"])
def test_boundary_uses_last_five_previous_same_venue_matches(saved_history, part):
    original, result = saved_history
    previous_parts = PARTS[:PARTS.index(part)]
    previous = pd.concat([getattr(original, name).matches for name in previous_parts], ignore_index=True)
    first = getattr(result, part).iloc[0]
    assert previous["match_date"].max() < first["match_date"]
    for side, opponent in (("home", "away"), ("away", "home")):
        previous_same_venue = previous.loc[
            previous[f"{side}_team_id"].eq(first[f"{side}_team_id"])
        ].tail(5)
        assert len(previous_same_venue) == 5
        goal_diffs = previous_same_venue[f"{side}_score"] - previous_same_venue[f"{opponent}_score"]
        points = sum(3 if difference > 0 else 1 if difference == 0 else 0 for difference in goal_diffs)
        assert first[f"{side}_last5_{side}_points"] == points
        assert first[f"{side}_last5_{side}_goal_diff"] == goal_diffs.sum()


def test_home_and_away_histories_stay_separate(monkeypatch, sample_history):
    result = _load_sample(monkeypatch, sample_history)
    values = pd.concat([getattr(result, part) for part in PARTS], ignore_index=True)
    assert values.loc[:, list(VENUE_FORM_COLUMNS)].values.tolist() == [
        [0, 0, 0, 0],
        [0, 0, 0, 0],
        [3, 0, 2, -2],
        [0, 3, -4, 4],
        [4, 1, 2, -2],
        [3, 3, -2, 2],
        [4, 4, -1, 1],
        [4, 4, -2, 2],
    ]


def test_preserves_schemas_dtypes_order_indices_and_input(monkeypatch, sample_history, saved_history):
    snapshots = {part: getattr(sample_history, part).matches.copy(deep=True) for part in PARTS}
    sample_result = _load_sample(monkeypatch, sample_history)
    for original, result in ((sample_history, sample_result), saved_history):
        for part in PARTS:
            before = getattr(original, part).matches
            after = getattr(result, part)
            assert after is not before
            assert list(after.columns) == [*before.columns, *VENUE_FORM_COLUMNS]
            assert_frame_equal(after.loc[:, before.columns], before)
    for part in PARTS:
        assert_frame_equal(getattr(sample_history, part).matches, snapshots[part])
    sample_result.historical.iloc[0, sample_result.historical.columns.get_loc("home_score")] = 99
    assert_frame_equal(sample_history.historical.matches, snapshots["historical"])


def test_reuses_venue_form_once_for_all_intervals(monkeypatch, sample_history):
    loader = Mock(return_value=sample_history)
    add_features = Mock(wraps=venue_form_history.add_venue_form_features)
    monkeypatch.setattr(venue_form_history, "load_elo_history_with_ongoing", loader)
    monkeypatch.setattr(venue_form_history, "add_venue_form_features", add_features)
    master = object()
    venue_form_history.load_venue_form_history_with_ongoing("saved-directory", team_master=master)
    loader.assert_called_once_with("saved-directory", team_master=master)
    add_features.assert_called_once()
    combined = add_features.call_args.args[0]
    expected = pd.concat([
        getattr(sample_history, part).matches.loc[:, INPUT_COLUMNS] for part in PARTS
    ], ignore_index=True)
    assert_frame_equal(combined, expected)


def test_same_input_gives_same_result(monkeypatch, sample_history):
    first = _load_sample(monkeypatch, sample_history)
    second = _load_sample(monkeypatch, sample_history)
    for part in PARTS:
        assert_frame_equal(getattr(first, part), getattr(second, part))


def test_empty_ongoing_preserves_schema_and_prior_features(monkeypatch, sample_history):
    complete = _load_sample(monkeypatch, sample_history)
    empty = sample_history.ongoing.matches.iloc[:0].copy()
    sample_history.ongoing = EloHistory(empty, {})
    result = _load_sample(monkeypatch, sample_history)
    assert_frame_equal(result.historical, complete.historical)
    assert_frame_equal(result.hyakunen, complete.hyakunen)
    assert result.ongoing.empty
    assert list(result.ongoing.columns) == [*empty.columns, *VENUE_FORM_COLUMNS]
    assert_frame_equal(result.ongoing.loc[:, empty.columns], empty)
    assert result.ongoing.loc[:, list(VENUE_FORM_COLUMNS)].dtypes.eq("int64").all()


def test_existing_venue_feature_is_not_silently_overwritten(monkeypatch, sample_history):
    sample_history.hyakunen.matches[VENUE_FORM_COLUMNS[0]] = 99
    with pytest.raises(ValueError, match="already exist"):
        _load_sample(monkeypatch, sample_history)
