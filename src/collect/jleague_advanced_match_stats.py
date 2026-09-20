"""Pure parser for J.LEAGUE.jp match-level advanced statistics."""

from html.parser import HTMLParser
import re

import pandas as pd


class _StatsParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.side = None
        self.text_kind = None
        self.text = []
        self.home_values = []
        self.away_values = []
        self.titles = []
        self.teams = []
        self.team_capture = False
        self.team_buffer = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if "o-team-comparison__stats-info--home" in classes:
            self.side = "home"
        elif "o-team-comparison__stats-info--away" in classes:
            self.side = "away"
        if tag == "div" and "o-team-comparison__club-name" in classes:
            self.team_capture = True
            self.team_buffer = []
        if tag == "p" and "o-team-comparison__stats-points" in classes:
            self.text_kind = "value"
            self.text = []
        elif tag == "p" and "o-team-comparison__stats-title" in classes:
            self.text_kind = "title"
            self.text = []
        elif tag == "p" and "o-team-comparison__club-name" in classes:
            self.text_kind = "team"
            self.text = []

    def handle_endtag(self, tag):
        if tag != "p" or self.text_kind is None:
            if tag == "div" and self.team_capture:
                value = "".join(self.team_buffer).strip()
                if value:
                    self.teams.append(value)
                self.team_capture = False
                self.team_buffer = []
            if tag == "div" and self.side is not None:
                self.side = None
            return
        value = "".join(self.text).strip()
        if self.text_kind == "value" and self.side in ("home", "away"):
            (self.home_values if self.side == "home" else self.away_values).append(value)
        elif self.text_kind == "title":
            self.titles.append(value)
        elif self.text_kind == "team":
            self.teams.append(value)
        self.text_kind = None
        self.text = []

    def handle_data(self, data):
        if self.team_capture:
            self.team_buffer.append(data)
        if self.text_kind is not None:
            self.text.append(data)


def parse_advanced_match_stats_html(
    html: str, *, expected_match_id: str | None = None,
) -> pd.DataFrame:
    """Parse one completed J.LEAGUE.jp match page without network access."""
    if not isinstance(html, str) or not html.strip() or "</html>" not in html.lower():
        raise ValueError("Incomplete HTML.")
    parser = _StatsParser()
    parser.feed(html)
    parser.close()
    if not parser.teams:
        parser.teams = _rsc_teams(html)
    if not parser.home_values or not parser.away_values:
        parser.home_values = [_rsc_value(html, label, "home") for label in ("Shots", "Shots on Target", "Possession")]
        parser.away_values = [_rsc_value(html, label, "away") for label in ("Shots", "Shots on Target", "Possession")]
        parser.titles = ["Shots", "Shots on Target", "Possession"]
    possession_labels = [label for label in parser.titles if label.startswith("Possession")]
    if parser.titles.count("Shots on Target") != 1 or len(possession_labels) != 1:
        raise ValueError("Required stat labels are missing or ambiguous.")
    if len(parser.teams) < 2 or parser.teams[0] == parser.teams[1]:
        raise ValueError("Home and away team names are missing or identical.")
    if len(parser.home_values) != len(parser.away_values) or len(parser.home_values) < 3:
        raise ValueError("Home/away stat structure is incomplete or ambiguous.")
    sot_index = parser.titles.index("Shots on Target")
    possession_index = parser.titles.index(possession_labels[0])
    home_sot = _integer(parser.home_values[sot_index], "home Shots on Target")
    away_sot = _integer(parser.away_values[sot_index], "away Shots on Target")
    home_possession = _percentage(parser.home_values[possession_index], "home Possession")
    away_possession = _percentage(parser.away_values[possession_index], "away Possession")
    if home_possession == 0 and away_possession == 0:
        raise ValueError("Possession is 0% for both teams; final match value is unavailable.")
    return pd.DataFrame([{
        "match_id": expected_match_id,
        "home_team": parser.teams[0],
        "away_team": parser.teams[1],
        "home_shots_on_target": home_sot,
        "away_shots_on_target": away_sot,
        "home_possession": home_possession,
        "away_possession": away_possession,
        "source_url": None,
    }])


def _integer(value: str, label: str) -> int:
    if not re.fullmatch(r"\d+", value):
        raise ValueError(f"{label} must be a nonnegative integer.")
    return int(value)


def _percentage(value: str, label: str) -> float:
    cleaned = value.strip().removesuffix("%").strip()
    try:
        parsed = float(cleaned)
    except ValueError as exc:
        raise ValueError(f"{label} must be numeric.") from exc
    if parsed < 0 or parsed > 100:
        raise ValueError(f"{label} must be between 0 and 100.")
    return parsed


def _rsc_teams(html: str) -> list[str]:
    return re.findall(r'o-team-comparison__club-name.*?children\\":\\"([^\\"]+)', html)[:2]


def _rsc_value(html: str, label: str, side: str) -> str:
    marker = f"{label}-info-{side}"
    start = html.find(marker)
    if start < 0:
        raise ValueError(f"Missing {label} for {side}.")
    children = '\\"children\\":['
    first = html.find(children, start)
    second = html.find(children, first + len(children))
    if second < 0:
        raise ValueError(f"Malformed {label} value for {side}.")
    token_start = second + len(children)
    token_end = html.find(",", token_start)
    if token_end < 0:
        raise ValueError(f"Malformed {label} value for {side}.")
    return html[token_start:token_end].strip().strip('"')
