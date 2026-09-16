import socket
from unittest.mock import Mock

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.features import form_history
from src.features.elo_history import DEFAULT_PROCESSED_DIR, EloHistory, OngoingEloHistory
from src.features.form import FORM_COLUMNS, METRICS


SEGMENTS = ("historical", "hyakunen", "ongoing")


@pytest.fixture(scope="module")
def real_history():
    required = [
        *(DEFAULT_PROCESSED_DIR / f"{year}_matches_probe.csv" for year in range(2015, 2026)),
        DEFAULT_PROCESSED_DIR / "2026_hyakunen/matches.csv",
        DEFAULT_PROCESSED_DIR / "2026_27/latest.json",
    ]
    if any(not path.is_file() for path in required):
        pytest.skip("Complete local J1 history is unavailable.")

    def reject_network(*args, **kwargs):
        raise AssertionError("Form history must not access the network.")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", reject_network)
        return form_history.load_form_history_with_ongoing()


def _prior_form(prior, team_id):
    matches = prior.loc[
        prior["home_team_id"].eq(team_id) | prior["away_team_id"].eq(team_id)
    ].tail(5)
    totals = [0] * len(METRICS)
    for row in matches.itertuples(index=False):
        home = row.home_team_id == team_id
        goals_for, goals_against = (
            (row.home_score, row.away_score) if home else (row.away_score, row.home_score)
        )
        win, draw, loss = int(goals_for > goals_against), int(goals_for == goals_against), int(goals_for < goals_against)
        values = [3 * win + draw, win, draw, loss, goals_for, goals_against]
        totals = [total + value for total, value in zip(totals, values)]
    return totals


def _assert_boundary_form(prior, current):
    first = current.iloc[0]
    inherited = 0
    for side in ("home", "away"):
        expected = _prior_form(prior, first[f"{side}_team_id"])
        actual = first[[f"{side}_last5_{metric}" for metric in METRICS]].tolist()
        assert actual == expected
        inherited += int(sum(expected[1:4]) > 0)
    assert inherited > 0


def _source_history(empty_ongoing=False):
    frames = []
    for number, (date, home, away, home_score, away_score) in enumerate([
        ("2025-12-01", "A", "B", 2, 1),
        ("2026-02-01", "B", "A", 0, 0),
        ("2026-08-01", "A", "B", 0, 3),
    ]):
        frame = pd.DataFrame({
            "match_date": pd.to_datetime([date]),
            "home_team_id": pd.array([home], dtype="string"),
            "away_team_id": pd.array([away], dtype="string"),
            "home_score": pd.array([home_score], dtype="Int64"),
            "away_score": pd.array([away_score], dtype="Int64"),
            "result": pd.array([2 if home_score > away_score else 1 if home_score == away_score else 0], dtype="Int64"),
            "home_elo": [1500.0 + number],
            f"{SEGMENTS[number]}_only": pd.array([pd.NA], dtype="Int64"),
        })
        if number == 0:
            second = frame.copy(deep=True)
            second["match_date"] = pd.to_datetime(["2025-12-08"])
            second["home_score"] = pd.array([1], dtype="Int64")
            second["result"] = pd.array([1], dtype="Int64")
            frame = pd.concat([frame, second], ignore_index=True)
        frame.index = pd.Index([8, 3] if number == 0 else [8], name="source_row")
        if number == 2 and empty_ongoing:
            frame = frame.iloc[:0].copy()
        frames.append(EloHistory(frame, {"A": 1500.0, "B": 1500.0}))
    return OngoingEloHistory(*frames)


def test_real_history_match_counts(real_history):
    counts = [len(getattr(real_history, name)) for name in SEGMENTS]
    assert counts == [3588, 200, 70]
    assert sum(counts) == 3858


def test_all_segments_have_twelve_integer_form_columns(real_history):
    assert len(FORM_COLUMNS) == 12
    for name in SEGMENTS:
        frame = getattr(real_history, name)
        assert list(frame.columns[-12:]) == list(FORM_COLUMNS)
        assert all(dtype == "int64" for dtype in frame[list(FORM_COLUMNS)].dtypes)


def test_first_historical_match_has_zero_form(real_history):
    assert real_history.historical.iloc[0][list(FORM_COLUMNS)].tolist() == [0] * 12


def test_hyakunen_inherits_historical_last_five_matches(real_history):
    _assert_boundary_form(real_history.historical, real_history.hyakunen)


def test_ongoing_inherits_prior_last_five_matches(real_history):
    prior = pd.concat([real_history.historical, real_history.hyakunen], ignore_index=True)
    _assert_boundary_form(prior, real_history.ongoing)


@pytest.mark.parametrize("empty_ongoing", [False, True])
def test_preserves_inputs_and_each_schema_in_one_form_call(monkeypatch, tmp_path, empty_ongoing):
    source = _source_history(empty_ongoing)
    originals = {name: getattr(source, name).matches.copy(deep=True) for name in SEGMENTS}
    loader = Mock(return_value=source)
    form = Mock(wraps=form_history.add_form_features)
    monkeypatch.setattr(form_history, "load_elo_history_with_ongoing", loader)
    monkeypatch.setattr(form_history, "add_form_features", form)
    master = object()

    result = form_history.load_form_history_with_ongoing(tmp_path, team_master=master)

    loader.assert_called_once_with(tmp_path, team_master=master)
    form.assert_called_once()
    assert len(form.call_args.args[0]) == sum(map(len, originals.values()))
    for name in SEGMENTS:
        original = originals[name]
        output = getattr(result, name)
        assert_frame_equal(getattr(source, name).matches, original)
        assert_frame_equal(output[original.columns], original)
        assert list(output.columns) == list(original.columns) + list(FORM_COLUMNS)
        assert all(dtype == "int64" for dtype in output[list(FORM_COLUMNS)].dtypes)
        assert output is not getattr(source, name).matches


def test_same_input_produces_same_result(monkeypatch):
    source = _source_history()
    monkeypatch.setattr(form_history, "load_elo_history_with_ongoing", Mock(return_value=source))

    first = form_history.load_form_history_with_ongoing()
    second = form_history.load_form_history_with_ongoing()

    for name in SEGMENTS:
        assert_frame_equal(getattr(first, name), getattr(second, name))
