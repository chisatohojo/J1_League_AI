from html import escape
import socket

import pandas as pd
import pytest

from src.collect.jleague_match_stats import (
    OUTPUT_COLUMNS, parse_match_stats_html,
)


def fixture_html(home="ベガルタ仙台", away="モンテディオ山形", values=(8, 11, 4, 8, 20, 17)):
    labels = ("SH", "CK", "FK")
    stats = "".join(
        f'<dl class="score-board-base"><dd class="left-area"><div class="left-score">{left}</div></dd>'
        f'<dt>{label}</dt><dd class="right-area"><div class="right-score">{right}</div></dd></dl>'
        for label, (left, right) in zip(labels, zip(values[::2], values[1::2]))
    )
    return f'''<html><body><div class="score-board-main"><table><tr>
        <th id="team-name-l" class="team-name"><a>{escape(home)}</a></th>
        <th id="team-name-r" class="team-name"><a>{escape(away)}</a></th>
        </tr></table></div><div class="score-board-other">{stats}</div></body></html>'''


@pytest.mark.parametrize("match_id, values", [("16803", (8, 11, 4, 8, 20, 17)), ("21623", (10, 9, 6, 8, 15, 16)), ("30619", (13, 13, 4, 8, 12, 15))])
def test_samples_parse_with_same_parser(match_id, values):
    result = parse_match_stats_html(fixture_html(values=values), expected_match_id=match_id)
    assert result.loc[0, "match_id"] == match_id
    assert result.loc[0, "home_team"] == "ベガルタ仙台"
    assert result.loc[0, "away_team"] == "モンテディオ山形"
    assert result.loc[0, ["home_shots", "away_shots"]].tolist() == list(values[:2])
    assert result.loc[0, ["home_ck", "away_ck"]].tolist() == list(values[2:4])
    assert result.loc[0, ["home_fk", "away_fk"]].tolist() == list(values[4:])


def test_output_columns_and_sh_is_not_shots_on_target():
    result = parse_match_stats_html(fixture_html(), expected_match_id="16803")
    assert result.columns.tolist() == list(OUTPUT_COLUMNS)
    assert "home_shots_on_target" not in result.columns


def test_source_url_id_must_match():
    with pytest.raises(ValueError):
        parse_match_stats_html(fixture_html(), expected_match_id="16803", source_url="https://data.j-league.or.jp/SFMS02/?match_card_id=21623")


@pytest.mark.parametrize("html, expected", [
    (fixture_html().replace("<div class=\"left-score\">8</div>", ""), "SH"),
    (fixture_html().replace("<dt>CK</dt>", "<dt>OTHER</dt>"), "CK"),
    (fixture_html().replace("<dt>FK</dt>", "<dt>OTHER</dt>"), "FK"),
    (fixture_html().replace(">8</div>", ">x</div>"), "integer"),
    (fixture_html(values=(-1, 11, 4, 8, 20, 17)), "integer"),
])
def test_invalid_stats_are_rejected(html, expected):
    with pytest.raises(ValueError, match=expected):
        parse_match_stats_html(html, expected_match_id="16803")


@pytest.mark.parametrize("home, away", [("", "Away"), ("Same", "Same")])
def test_invalid_teams_are_rejected(home, away):
    with pytest.raises(ValueError):
        parse_match_stats_html(fixture_html(home, away), expected_match_id="16803")


@pytest.mark.parametrize("html", ["", "<html><body>", fixture_html().replace("score-board-other", "other")])
def test_incomplete_or_unexpected_structure_is_rejected(html):
    with pytest.raises(ValueError):
        parse_match_stats_html(html, expected_match_id="16803")


def test_invalid_match_id_is_rejected():
    with pytest.raises(ValueError):
        parse_match_stats_html(fixture_html(), expected_match_id="")


def test_parser_is_deterministic_and_does_not_access_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("parser attempted network access")
    monkeypatch.setattr(socket, "socket", forbidden)
    first = parse_match_stats_html(fixture_html(), expected_match_id="16803")
    second = parse_match_stats_html(fixture_html(), expected_match_id="16803")
    pd.testing.assert_frame_equal(first, second)
