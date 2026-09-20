import pytest

from src.collect.jleague_advanced_match_stats import parse_advanced_match_stats_html


def _html(home="Home FC", away="Away FC", sot=(3, 5), possession=(55, 45)):
    labels = ("Shots", "Shots on Target", "Possession", "Corner kicks")
    home_values = ("10", str(sot[0]), f"{possession[0]}%", "4")
    away_values = ("8", str(sot[1]), f"{possession[1]}%", "3")
    def values(side, values):
        return "".join(f'<div class="o-team-comparison__stats-info--{side}"><p class="o-team-comparison__stats-points">{v}</p></div>' for v in values)
    titles = "".join(f'<p class="o-team-comparison__stats-title">{label}</p>' for label in labels)
    return (
        '<html><body><div class="o-team-comparison__club-name"><p>' + home +
        '</p></div><div class="o-team-comparison__club-name"><p>' + away +
        '</p></div>' + values("home", home_values) + titles + values("away", away_values) +
        '</body></html>'
    )


@pytest.mark.parametrize("season", (2020, 2021, 2022, 2023, 2024, 2025))
def test_same_parser_handles_six_season_shapes(season):
    result = parse_advanced_match_stats_html(_html(), expected_match_id=str(season))
    assert result.loc[0, "match_id"] == str(season)
    assert result.loc[0, "home_shots_on_target"] == 3
    assert result.loc[0, "away_shots_on_target"] == 5
    assert result.loc[0, "home_possession"] == 55.0
    assert result.loc[0, "away_possession"] == 45.0


def test_shots_on_target_is_not_shots_and_input_is_unchanged():
    html = _html(sot=(2, 4))
    original = html[:]
    result = parse_advanced_match_stats_html(html)
    assert result.loc[0, "home_shots_on_target"] == 2
    assert html == original


@pytest.mark.parametrize("bad", (
    '<html><body></body></html>',
    _html(sot=("x", 2)),
    _html(sot=(-1, 2)),
    _html(possession=(101, 0)),
))
def test_invalid_values_are_rejected(bad):
    with pytest.raises(ValueError):
        parse_advanced_match_stats_html(bad)


def test_duplicate_label_is_rejected():
    html = _html().replace(
        '<p class="o-team-comparison__stats-title">Shots on Target</p>',
        '<p class="o-team-comparison__stats-title">Shots on Target</p>'
        '<p class="o-team-comparison__stats-title">Shots on Target</p>',
    )
    with pytest.raises(ValueError):
        parse_advanced_match_stats_html(html)
