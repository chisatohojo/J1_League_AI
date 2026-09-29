"""Strict, offline prototypes for official domestic-Cup regulation scores.

This module does not fetch, build the 145-row bridge dataset, or update Elo.
It only resolves an already identified match when the official source exposes
an explicit first-half plus second-half score.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup


CONFIRMED = "CONFIRMED_REGULATION_SCORE"
UNRESOLVED = "UNRESOLVED_REGULATION_SCORE"


class CupRegulationError(ValueError):
    """Source identity, schema, or score arithmetic is unsafe."""


def _integer(value, field):
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise CupRegulationError(f"invalid {field}")
    return int(text)


def _result(home, away):
    return 2 if home > away else 0 if home < away else 1


def _team_id(value, field):
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        raise CupRegulationError(f"invalid {field}")
    return text


def _utf8_soup(raw, source):
    try:
        return BeautifulSoup(raw.decode("utf-8"), "html.parser")
    except UnicodeDecodeError as exc:
        raise CupRegulationError(f"invalid UTF-8 {source} source") from exc


def _jleague_url(source_url, source_match_id):
    parsed = urlparse(source_url)
    query = parse_qs(parsed.query)
    if (parsed.scheme != "https" or parsed.hostname != "data.j-league.or.jp"
            or parsed.path != "/SFMS02/"
            or query.get("match_card_id") != [str(source_match_id)]):
        raise CupRegulationError("J.League source URL/match identity mismatch")


def _periods_from_html(container):
    periods = {}
    for block in container.select("td.time dl"):
        label_node = block.find("dt")
        left = block.select_one("dd.left-area")
        right = block.select_one("dd.right-area")
        if label_node is None or left is None or right is None:
            raise CupRegulationError("malformed J.League period row")
        label = label_node.get_text(" ", strip=True)
        if label in periods:
            raise CupRegulationError("duplicate J.League period row")
        periods[label] = (
            _integer(left.get_text("", strip=True), f"{label} home score"),
            _integer(right.get_text("", strip=True), f"{label} away score"),
        )
    return periods


def _pk_from_html(soup):
    labels = [node for node in soup.find_all(["dt", "th", "td"])
              if node.get_text(" ", strip=True) == "PK戦"]
    if not labels:
        return False, None, None
    if len(labels) != 1:
        raise CupRegulationError("ambiguous J.League PK row")
    parent = labels[0].find_parent(["dl", "tr"])
    left = parent.select_one(".left-area") if parent else None
    right = parent.select_one(".right-area") if parent else None
    if left is None or right is None:
        raise CupRegulationError("malformed J.League PK row")
    home = _integer(left.get_text("", strip=True), "home PK score")
    away = _integer(right.get_text("", strip=True), "away PK score")
    if home == away:
        raise CupRegulationError("tied J.League PK score")
    return True, home, away


def parse_jleague_sfms02(
    raw: bytes, *, season: int, source_match_id: str, match_date: str,
    home_team_id: str, away_team_id: str, expected_home_team: str,
    expected_away_team: str, source_url: str,
    expected_home_aliases=(), expected_away_aliases=(),
    expected_home_club_ids=(), expected_away_club_ids=(),
):
    """Resolve one known SFMS02 match from explicit period rows."""
    _jleague_url(source_url, source_match_id)
    home_team_id = _team_id(home_team_id, "home_team_id")
    away_team_id = _team_id(away_team_id, "away_team_id")
    if home_team_id == away_team_id:
        raise CupRegulationError("identical home/away team IDs")
    if not raw:
        raise CupRegulationError("empty J.League source")
    soup = _utf8_soup(raw, "J.League")
    board = soup.select_one(".score-board-main")
    if board is None:
        raise CupRegulationError("missing J.League score board")
    home = board.select_one("#team-name-l")
    away = board.select_one("#team-name-r")
    if home is None or away is None:
        raise CupRegulationError("missing J.League home/away identity")
    home_names = {expected_home_team, *expected_home_aliases}
    away_names = {expected_away_team, *expected_away_aliases}
    for node, names, allowed in (
        (home, home_names, set(expected_home_club_ids)),
        (away, away_names, set(expected_away_club_ids)),
    ):
        source_name = node.get_text(" ", strip=True)
        if not source_name:
            raise CupRegulationError("J.League home/away identity mismatch")
        if not allowed:
            if source_name not in names:
                raise CupRegulationError("J.League home/away identity mismatch")
            continue
        link = node.find("a", href=True)
        link_url = urlparse(link["href"] if link else "")
        club_match = re.match(r"^/club/([^/]+)/", link_url.path)
        if (link_url.scheme not in {"http", "https"}
                or link_url.hostname != "www.jleague.jp"
                or club_match is None or club_match.group(1) not in allowed):
            raise CupRegulationError("J.League club identity mismatch")
    source_dates = {
        node.get_text("", strip=True)
        for node in soup.select(".two-column-table-bottom td")
        if re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2}", node.get_text("", strip=True))
    }
    expected_date = str(match_date).replace("-", "/")
    if source_dates != {expected_date} or not expected_date.startswith(f"{int(season):04d}/"):
        raise CupRegulationError("J.League match date mismatch")
    totals = board.select("td.score")
    if len(totals) != 2:
        raise CupRegulationError("invalid J.League final-score cells")
    final_home = _integer(totals[0].get_text("", strip=True), "final home score")
    final_away = _integer(totals[1].get_text("", strip=True), "final away score")
    periods = _periods_from_html(board)
    if not {"前半", "後半"}.issubset(periods):
        raise CupRegulationError("explicit first/second-half scores are required")
    regulation_home = periods["前半"][0] + periods["後半"][0]
    regulation_away = periods["前半"][1] + periods["後半"][1]

    long_extra = ("延長前半", "延長後半")
    short_extra = ("延前", "延後")
    present = [pair for pair in (long_extra, short_extra) if any(key in periods for key in pair)]
    if len(present) > 1 or (present and not all(key in periods for key in present[0])):
        raise CupRegulationError("incomplete or ambiguous extra-time periods")
    extra_time = bool(present)
    extra_home = sum(periods[key][0] for key in present[0]) if present else 0
    extra_away = sum(periods[key][1] for key in present[0]) if present else 0
    if (final_home, final_away) != (
        regulation_home + extra_home, regulation_away + extra_away
    ):
        raise CupRegulationError("J.League period/final score mismatch")
    pk_played, _, _ = _pk_from_html(soup)
    return {
        "competition": "jleague_cup", "season": int(season),
        "source_match_id": str(source_match_id), "match_date": str(match_date),
        "home_team_id": home_team_id, "away_team_id": away_team_id,
        "regulation_home_score": regulation_home,
        "regulation_away_score": regulation_away,
        "regulation_result": _result(regulation_home, regulation_away),
        "extra_time_played": extra_time, "penalty_shootout_played": pk_played,
        "final_home_score": final_home, "final_away_score": final_away,
        "source_url": source_url, "source_type": "jleague_data_site_sfms02",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "resolution_status": CONFIRMED,
        "resolution_reason": "explicit_first_and_second_half_scores",
    }


def parse_jfa_schedule_result(
    raw: bytes, *, season: int, source_match_id: str, match_date: str,
    home_team_id: str, away_team_id: str, expected_home_team: str,
    expected_away_team: str, source_url: str,
):
    """Resolve one known JFA row without trusting a detached item or digest."""
    parsed = urlparse(source_url)
    expected_path = f"/match/emperorscup_{int(season)}/match/schedule.json"
    if parsed.scheme != "https" or parsed.hostname != "www.jfa.jp" or parsed.path != expected_path:
        raise CupRegulationError("JFA source URL/season mismatch")
    match = re.fullmatch(rf"{int(season)}-m([0-9]+)", str(source_match_id))
    if match is None:
        raise CupRegulationError("JFA source match identity mismatch")
    number = int(match.group(1))
    if not raw:
        raise CupRegulationError("empty JFA source")
    try:
        payload = json.loads(raw)
        items = payload["matchScheduleList"]["matchSchedule"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CupRegulationError("invalid JFA schedule source") from exc
    if not isinstance(items, list):
        raise CupRegulationError("invalid JFA schedule source")
    selected = []
    for item in items:
        if not isinstance(item, dict):
            raise CupRegulationError("invalid JFA schedule row")
        try:
            item_number = _integer(item.get("matchNumber"), "JFA matchNumber")
        except CupRegulationError:
            raise CupRegulationError("invalid JFA schedule row") from None
        if item_number == number:
            selected.append(item)
    if len(selected) != 1:
        raise CupRegulationError("JFA source match identity is missing or duplicated")
    item = selected[0]
    if item.get("matchDate") != str(match_date).replace("-", "/"):
        raise CupRegulationError("JFA match date mismatch")
    if (item.get("homeTeamName") != expected_home_team
            or item.get("awayTeamName") != expected_away_team):
        raise CupRegulationError("JFA home/away identity mismatch")
    home_team_id = _team_id(home_team_id, "home_team_id")
    away_team_id = _team_id(away_team_id, "away_team_id")
    if home_team_id == away_team_id:
        raise CupRegulationError("identical home/away team IDs")
    score = item.get("score")
    if not isinstance(score, dict):
        raise CupRegulationError("missing JFA score object")
    final_home = _integer(score.get("homeScore"), "JFA final home score")
    final_away = _integer(score.get("awayScore"), "JFA final away score")
    pk_home, pk_away = score.get("homePKScore"), score.get("awayPKScore")
    if (pk_home is None) != (pk_away is None):
        raise CupRegulationError("partial JFA PK score")
    pk_played = pk_home is not None
    if pk_played:
        parsed_pk_home = _integer(pk_home, "JFA home PK score")
        parsed_pk_away = _integer(pk_away, "JFA away PK score")
        if parsed_pk_home == parsed_pk_away:
            raise CupRegulationError("tied JFA PK score")
    ex_flag = score.get("exMatch") if "exMatch" in score else None
    if ex_flag is not None and not isinstance(ex_flag, bool):
        raise CupRegulationError("invalid JFA exMatch flag")
    period_keys = (
        "homeTeamScore1st", "awayTeamScore1st",
        "homeTeamScore2nd", "awayTeamScore2nd",
    )
    base = {
        "competition": "emperors_cup", "season": int(season),
        "source_match_id": source_match_id, "match_date": str(match_date),
        "home_team_id": home_team_id, "away_team_id": away_team_id,
        "extra_time_played": ex_flag,
        "penalty_shootout_played": pk_played,
        "final_home_score": final_home, "final_away_score": final_away,
        "source_url": source_url, "source_type": "jfa_schedule_json",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
    }
    present = [key in score for key in period_keys]
    if not all(present):
        if any(present):
            raise CupRegulationError("partial JFA regulation-period score")
        return {
            **base, "regulation_home_score": None, "regulation_away_score": None,
            "regulation_result": None, "resolution_status": UNRESOLVED,
            "resolution_reason": "official_detail_or_report_required",
        }
    regulation_home = _integer(score[period_keys[0]], period_keys[0]) + _integer(
        score[period_keys[2]], period_keys[2]
    )
    regulation_away = _integer(score[period_keys[1]], period_keys[1]) + _integer(
        score[period_keys[3]], period_keys[3]
    )
    extra_keys = (
        "homeTeamScore1ex", "awayTeamScore1ex",
        "homeTeamScore2ex", "awayTeamScore2ex",
    )
    extra_present = [key in score for key in extra_keys]
    if any(extra_present) and not all(extra_present):
        raise CupRegulationError("partial JFA extra-time score")
    has_extra_periods = all(extra_present)
    if ex_flag is False and has_extra_periods:
        raise CupRegulationError("JFA exMatch/extra-time fields conflict")
    extra_home = sum(_integer(score[key], key) for key in extra_keys[::2]) if has_extra_periods else 0
    extra_away = sum(_integer(score[key], key) for key in extra_keys[1::2]) if has_extra_periods else 0
    if has_extra_periods or ex_flag is not True:
        if (final_home, final_away) != (
            regulation_home + extra_home, regulation_away + extra_away
        ):
            raise CupRegulationError("JFA period/final score mismatch")
    return {
        **base, "regulation_home_score": regulation_home,
        "regulation_away_score": regulation_away,
        "regulation_result": _result(regulation_home, regulation_away),
        "extra_time_played": bool(ex_flag is True or has_extra_periods),
        "resolution_status": CONFIRMED,
        "resolution_reason": "explicit_first_and_second_half_scores",
    }


def parse_jfa_match_page(
    raw: bytes, *, season: int, source_match_id: str, match_date: str,
    home_team_id: str, away_team_id: str, expected_home_team: str,
    expected_away_team: str, source_url: str,
):
    """Resolve a legacy JFA detail page from explicit score-breakdown rows."""
    match = re.fullmatch(rf"{int(season)}-m([0-9]+)", str(source_match_id))
    if match is None:
        raise CupRegulationError("JFA detail source match identity mismatch")
    number = int(match.group(1))
    parsed = urlparse(source_url)
    expected_path = f"/match/emperorscup_{int(season)}/match_page/m{number}.html"
    if (parsed.scheme != "https" or parsed.hostname != "www.jfa.jp"
            or parsed.path != expected_path or parsed.query or parsed.fragment):
        raise CupRegulationError("JFA detail source URL/match identity mismatch")
    if not raw:
        raise CupRegulationError("empty JFA detail source")
    soup = _utf8_soup(raw, "JFA detail")
    schedule = soup.select_one(
        "#header-schedule-result .text-schedule, #header-schedule-score .text-schedule"
    )
    if schedule is None:
        raise CupRegulationError("missing JFA detail schedule")
    date_match = re.search(
        r"([0-9]{4})年([0-9]{1,2})月([0-9]{1,2})日",
        schedule.get_text(" ", strip=True),
    )
    if date_match is None:
        raise CupRegulationError("missing JFA detail match date")
    source_date = f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
    if source_date != str(match_date) or not source_date.startswith(f"{int(season):04d}-"):
        raise CupRegulationError("JFA detail match date mismatch")
    board = soup.select_one("#score-board-header")
    if board is None:
        raise CupRegulationError("missing JFA detail score board")
    flags = board.select(".flag")
    totals = board.select(".total-score")
    if len(flags) != 2 or len(totals) != 2:
        raise CupRegulationError("invalid JFA detail teams/final scores")
    team_names = []
    for flag in flags:
        text_nodes = [node.get_text(" ", strip=True) for node in flag.select("p")]
        team_names.append(next((text for text in reversed(text_nodes) if text), ""))
    if team_names != [expected_home_team, expected_away_team]:
        raise CupRegulationError("JFA detail home/away identity mismatch")
    home_team_id = _team_id(home_team_id, "home_team_id")
    away_team_id = _team_id(away_team_id, "away_team_id")
    if home_team_id == away_team_id:
        raise CupRegulationError("identical home/away team IDs")
    final_home = _integer(totals[0].get_text("", strip=True), "JFA detail final home score")
    final_away = _integer(totals[1].get_text("", strip=True), "JFA detail final away score")
    groups = []
    for group in board.select(".score-detail ul.inner-score"):
        rows = []
        for item in group.select("li"):
            cells = item.select("span")
            if len(cells) != 3:
                raise CupRegulationError("malformed JFA detail period row")
            rows.append((
                cells[1].get_text(" ", strip=True),
                _integer(cells[0].get_text("", strip=True), "JFA detail home period score"),
                _integer(cells[2].get_text("", strip=True), "JFA detail away period score"),
            ))
        if rows:
            groups.append(rows)
    if not groups or [row[0] for row in groups[0]] != ["前半", "後半"]:
        raise CupRegulationError("explicit JFA first/second-half scores are required")
    regulation_home = sum(row[1] for row in groups[0])
    regulation_away = sum(row[2] for row in groups[0])
    extra_home = extra_away = 0
    extra_time = False
    pk_played = False
    for group in groups[1:]:
        labels = [row[0] for row in group]
        if labels in (["延前", "延後"], ["延長前半", "延長後半"]):
            if extra_time:
                raise CupRegulationError("duplicate JFA detail extra-time group")
            extra_time = True
            extra_home = sum(row[1] for row in group)
            extra_away = sum(row[2] for row in group)
        elif labels in (["PK"], ["PK戦"]):
            if pk_played or group[0][1] == group[0][2]:
                raise CupRegulationError("invalid JFA detail PK group")
            pk_played = True
        else:
            raise CupRegulationError("unknown JFA detail score group")
    if (final_home, final_away) != (
        regulation_home + extra_home, regulation_away + extra_away
    ):
        raise CupRegulationError("JFA detail period/final score mismatch")
    return {
        "competition": "emperors_cup", "season": int(season),
        "source_match_id": str(source_match_id), "match_date": str(match_date),
        "home_team_id": home_team_id, "away_team_id": away_team_id,
        "regulation_home_score": regulation_home,
        "regulation_away_score": regulation_away,
        "regulation_result": _result(regulation_home, regulation_away),
        "extra_time_played": extra_time,
        "penalty_shootout_played": pk_played,
        "final_home_score": final_home, "final_away_score": final_away,
        "source_url": source_url, "source_type": "jfa_match_page",
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "resolution_status": CONFIRMED,
        "resolution_reason": "explicit_first_and_second_half_scores",
    }
