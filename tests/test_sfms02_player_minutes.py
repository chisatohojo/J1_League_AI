"""Offline tests for normalized, match-local SFMS02 participation intervals."""

import csv
from pathlib import Path

import pytest

from src.collect.sfms02_player_minutes import (
    MinutesError, collect_history, normalize_minute, parse_match,
)


ROOT = Path(__file__).resolve().parents[1]


def _tr(**cells):
    return "<tr>" + "".join(f'<td class="{key}">{value}</td>' for key, value in cells.items()) + "</tr>"


def _side(prefix, *, substitutes=(), reds=(), bench_names=None, xi_names=None):
    xi_names = xi_names or [f"{prefix}{n}" for n in range(11)]
    bench_names = bench_names or [f"{prefix}B{n}" for n in range(3)]
    xi = "".join(_tr(position="GK" if n == 0 else "MF", name=name, time="")
                 for n, name in enumerate(xi_names))
    bench = "".join(_tr(position="GK" if n == 0 else "MF", name=name, time="")
                    for n, name in enumerate(bench_names))
    sub = "".join(_tr(change="▽", name=out, time=minute)
                  + _tr(change="▲", name=incoming, time="")
                  for out, incoming, minute in substitutes)
    red = "".join(_tr(name=name, time=minute) for name, minute in reds)
    return {5: xi, 6: bench, 7: sub, 9: red}


def _html(home=None, away=None):
    home = home if home is not None else _side("H")
    away = away if away is not None else _side("A")
    sections = "".join(
        f"<!-- A{number} Start --><table>{side[number]}</table><!-- A{number} End -->"
        for number in (5, 6, 7, 9) for side in (home, away)
    )
    return (sections + "<!-- A12 Start -->").encode("utf-8")


def _parse(raw):
    return parse_match(raw, match_id="12345", match_date="2020-03-01", season=2020,
                       home_team_id="team_0001", away_team_id="team_0002",
                       home_team="Home", away_team="Away")


def _player(rows, name):
    return next(row for row in rows if row["player_name_raw"] == name)


@pytest.mark.parametrize("raw,minute,flag", [
    ("12'", 12, None), ("46'", 46, "MINUTE_46_BOUNDARY_AMBIGUOUS"),
    ("45'+3", 45, "FIRST_HALF_ADDED_TIME_CAPPED"),
    ("90'+18", 90, "SECOND_HALF_ADDED_TIME_CAPPED"),
])
def test_minute_normalization_is_fixed(raw, minute, flag):
    assert normalize_minute(raw)[0] == minute
    assert normalize_minute(raw)[2] == flag
    assert normalize_minute("45'+3")[1] < normalize_minute("46'")[1]


@pytest.mark.parametrize("raw", ["", "HT", "91'", "44'+2", "90'+0", "-2'", "45+2"])
def test_unsupported_minutes_fail(raw):
    with pytest.raises(MinutesError):
        normalize_minute(raw)


def test_full_match_and_unused_bench_have_distinct_status():
    rows, audit = _parse(_html())
    assert len(rows) == 28 and audit["substitution_pairs"] == 0
    assert _player(rows, "H0")["appearance_type"] == "starter_full"
    assert _player(rows, "H0")["minutes_played_normalized"] == 90
    unused = _player(rows, "HB0")
    assert unused["appearance_type"] == "unused_substitute"
    assert unused["entered_minute_normalized"] is None
    assert unused["left_minute_normalized"] is None
    assert unused["minutes_played_normalized"] == 0


def test_enter_then_leave_and_gk_46_without_halftime_inference():
    home = _side("H", substitutes=(("H0", "HB0", "46'"), ("HB0", "HB1", "80'")))
    rows, audit = _parse(_html(home=home))
    assert audit["substitution_pairs"] == 2
    starter = _player(rows, "H0")
    gk = _player(rows, "HB0")
    assert starter["left_minute_normalized"] == 46
    assert starter["minutes_played_normalized"] == 46
    assert gk["appearance_type"] == "sub_entered_and_left"
    assert (gk["entered_minute_normalized"], gk["left_minute_normalized"],
            gk["minutes_played_normalized"]) == (46, 80, 34)
    assert "MINUTE_46_BOUNDARY_AMBIGUOUS" in gk["normalization_flags"]


def test_added_time_caps_are_recorded_and_zero_minutes_is_not_unused():
    home = _side("H", substitutes=(("H1", "HB1", "45'+3"),
                                   ("H2", "HB2", "90'+3")))
    rows, _ = _parse(_html(home=home))
    assert _player(rows, "H1")["minutes_played_normalized"] == 45
    assert _player(rows, "HB1")["minutes_played_normalized"] == 45
    late = _player(rows, "HB2")
    assert late["minutes_played_normalized"] == 0
    assert late["appearance_type"] == "sub_entered"
    assert "SECOND_HALF_ADDED_TIME_CAPPED" in late["normalization_flags"]


def test_active_and_off_pitch_dismissals_are_distinguished():
    home = _side("H", substitutes=(("H1", "HB1", "63'"),),
                 reds=(("H2", "60'"), ("H1", "64'"), ("HB2", "45'+2")))
    rows, audit = _parse(_html(home=home))
    assert audit["active_dismissals"] == 1
    assert audit["post_sub_dismissals"] == 1
    assert audit["unused_sub_dismissals"] == 1
    assert _player(rows, "H2")["appearance_type"] == "starter_dismissed"
    assert _player(rows, "H2")["minutes_played_normalized"] == 60
    assert _player(rows, "H1")["left_minute_normalized"] == 63
    assert "POST_SUB_DISMISSAL_IGNORED" in _player(rows, "H1")["normalization_flags"]
    assert _player(rows, "HB2")["minutes_played_normalized"] == 0
    assert "UNUSED_SUB_DISMISSAL_IGNORED" in _player(rows, "HB2")["normalization_flags"]


def test_entered_substitute_can_be_dismissed():
    rows, audit = _parse(_html(home=_side("H", substitutes=(("H1", "HB1", "55'"),),
                                       reds=(("HB1", "70'"),))))
    player = _player(rows, "HB1")
    assert audit["active_dismissals"] == 1
    assert player["appearance_type"] == "sub_entered_dismissed"
    assert player["minutes_played_normalized"] == 15


@pytest.mark.parametrize("home", [
    _side("H", xi_names=["H0"] * 11),
    _side("H", substitutes=(("HB1", "HB2", "20'"),)),  # OUT before entering
    _side("H", substitutes=(("H1", "HB1", "20'"), ("H2", "HB1", "30'"))),
    _side("H", substitutes=(("H1", "HB1", "20'"),), reds=(("H1", "20'"),)),
])
def test_impossible_or_ambiguous_states_fail(home):
    with pytest.raises(MinutesError):
        _parse(_html(home=home))


@pytest.mark.parametrize("mid,season,person,expected_type,expected_minutes", [
    ("16803", 2015, "野沢　拓也", "starter_dismissed", 63),
    ("16810", 2015, "岡田　翔平", "sub_entered_and_left", 24),
    ("16902", 2015, "イ　ホスン", "sub_entered", 44),
    ("27377", 2022, "ディエゴ　ピトゥカ", "starter_subbed_out", 63),
    ("28320", 2023, "三田　啓貴", "unused_substitute", 0),
])
def test_audited_cached_cases(mid, season, person, expected_type, expected_minutes):
    path = ROOT / "data/raw/jleague_match_stats" / f"{mid}.html"
    if not path.exists():
        pytest.skip("Local SFMS02 cache unavailable")
    rows, _ = parse_match(path.read_bytes(), match_id=mid, match_date=f"{season}-03-01",
                          season=season, home_team_id="team_0001", away_team_id="team_0002",
                          home_team="H", away_team="A")
    row = _player(rows, person)
    assert row["appearance_type"] == expected_type
    assert row["minutes_played_normalized"] == expected_minutes


def test_incomplete_history_does_not_publish_processed_output(tmp_path):
    output = tmp_path / "minutes.csv"
    with pytest.raises((FileNotFoundError, MinutesError)):
        collect_history(matches_dir=tmp_path, stats_dir=tmp_path,
                        raw_dir=tmp_path, output_path=output)
    assert not output.exists()


def test_parser_is_deterministic_and_match_local_only():
    raw = _html()
    before = bytes(raw)
    first = _parse(raw)
    assert first == _parse(raw)
    assert raw == before
    assert all(row["source"] == "jleague_data_site_sfms02" for row in first[0])
    assert all("player_id" not in row for row in first[0])
