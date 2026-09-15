"""Parse ongoing ordinary J1 fixtures and explicit official completion evidence.

All functions are offline. A numeric Data Site score is only a candidate;
completion requires a separately archived official match page with its own
match-specific ``section#game-over`` and matching fixture identity and scores.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, time
from html.parser import HTMLParser
import re

from src.collect.jleague import HEADERS, SOURCE_BASE, _SearchTableParser, _numeric_syntax


COMPETITION_KEY = "j1_2026_2027"
SOURCE_URL = (
    f"{SOURCE_BASE}/SFMS01/search?competition_frame_ids=1"
    "&competition_years=2026&tv_relay_station_name="
)
COMPLETION_POLICY_VERSION = "official-game-over-v1"
_CLUB = r"[a-z0-9_-]+"
_MATCH_URL = r"https://www\.jleague\.jp/match/j1/(2026|2027)/([0-9]{6})/"


def _club_link(links: list[str]) -> tuple[str, str]:
    match = re.fullmatch(rf"https?://www\.jleague\.jp/club/({_CLUB})/profile/", links[0]) if len(links) == 1 else None
    if match is None:
        raise ValueError("Expected one official club profile per side.")
    return match[1], links[0]


def _fixture_key(home: str, away: str) -> str:
    if home == away:
        raise ValueError("The fixture has the same home and away club.")
    return f"{COMPETITION_KEY}:{home}:{away}"


def _season_date(year: int, month: int, day: int) -> str:
    parsed = date(year, month, day)
    # This explicitly limits evidence to the verified ordinary cross-year season.
    # Small schedule changes inside the season do not affect fixture identity.
    if not date(2026, 8, 1) <= parsed <= date(2027, 6, 30):
        raise ValueError("Date outside the verified 2026/27 ordinary J1 season.")
    return parsed.isoformat()


def parse_listing(html: str) -> list[dict]:
    """Keep source order and original labels; never infer completion from scores."""
    parser = _SearchTableParser()
    parser.feed(html)
    parser.close()
    if parser.table_count != 1 or parser.inside or len(parser.rows) < 2:
        raise ValueError("Expected one complete nonempty ongoing J1 search-table.")
    if tuple(cell[1] for cell in parser.rows[0]) != HEADERS or any(cell[0] != "th" for cell in parser.rows[0]):
        raise ValueError("Unexpected ongoing J1 search-table headers.")
    records = []
    seen_keys, seen_ids = set(), set()
    for position, row in enumerate(parser.rows[1:], 1):
        if len(row) != len(HEADERS) or any(cell[0] != "td" for cell in row):
            raise ValueError(f"Source row {position}: expected 11 data cells.")
        values = [cell[1] for cell in row]
        season, competition, round_label, date_label, kickoff = values[:5]
        if season != "2026/27" or _numeric_syntax(r"J1", competition) is None:
            raise ValueError(f"Source row {position}: unexpected season or competition.")
        parts = _numeric_syntax(r"第([0-9]+)節第([0-9]+)日", round_label)
        round_number, round_day = map(int, parts.groups())
        if not 1 <= round_number <= 38 or round_day < 1:
            raise ValueError(f"Source row {position}: invalid round/day.")
        parts = _numeric_syntax(r"(26|27)/([0-9]{2})/([0-9]{2})\([月火水木金土日](?:・[祝休])?\)", date_label)
        year, month, day = map(int, parts.groups())
        match_date = _season_date(2000 + year, month, day)
        if kickoff:
            if re.fullmatch(r"[0-9]{2}:[0-9]{2}", kickoff) is None:
                raise ValueError(f"Source row {position}: invalid kickoff time.")
            time.fromisoformat(kickoff)
        home_club, home_url = _club_link(row[5][2])
        away_club, away_url = _club_link(row[7][2])
        if not values[5] or not values[7] or values[5] == values[7]:
            raise ValueError(f"Source row {position}: missing or identical team names.")
        fixture_key = _fixture_key(home_club, away_club)
        if fixture_key in seen_keys:
            raise ValueError(f"Duplicate fixture_key: {fixture_key}.")
        seen_keys.add(fixture_key)
        links = row[6][2]
        match_id = None
        source_url = SOURCE_URL
        if links:
            link = re.fullmatch(r"/SFMS02/\?match_card_id=([1-9][0-9]*)", links[0]) if len(links) == 1 else None
            if link is None:
                raise ValueError(f"Source row {position}: invalid match-card link.")
            match_id, source_url = link[1], SOURCE_BASE + links[0]
            if match_id in seen_ids:
                raise ValueError(f"Duplicate match_id: {match_id}.")
            seen_ids.add(match_id)
        if values[6] == "vs":
            status, home_score, away_score, result = "scheduled", None, None, None
        else:
            parts = _numeric_syntax(r"([0-9]+)-([0-9]+)", values[6])
            if match_id is None:
                raise ValueError(f"Source row {position}: score candidate has no official match_id.")
            home_score, away_score = map(int, parts.groups())
            result = 1 if home_score == away_score else 2 if home_score > away_score else 0
            status = "candidate"
        records.append({
            "fixture_key": fixture_key, "match_id": match_id, "season": 2026,
            "competition_key": COMPETITION_KEY, "source_season_label": season,
            "source_year_id": 2026, "source_frame_id": 1,
            "competition": competition, "stage": "full_season", "round": round_number,
            "round_label": round_label, "round_day": round_day,
            "match_date": match_date, "match_date_label": date_label,
            "kickoff_time": kickoff, "home_team": values[5], "away_team": values[7],
            "home_club": home_club, "away_club": away_club,
            "home_team_source_url": home_url, "away_team_source_url": away_url,
            "stadium": values[8], "home_score": home_score, "away_score": away_score,
            "result": result, "status": status, "raw_score_text": values[6],
            "attendance_raw": values[9], "broadcast_raw": values[10],
            "source_url": source_url, "listing_source_url": SOURCE_URL,
            "evidence_url": "", "evidence_type": "",
        })
    return records


@dataclass
class _Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)

    def text(self) -> str:
        return "".join(child.text() if isinstance(child, _Node) else child for child in self.children).strip()

    def has_class(self, value: str) -> bool:
        return value in (self.attrs.get("class") or "").split()

    def nodes(self):
        for child in self.children:
            if isinstance(child, _Node):
                yield child
                yield from child.nodes()


class _OfficialMatchParser(HTMLParser):
    """Collect real header/game-over subtrees, never scripts or loading placeholders."""

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.roots, self.stack, self.canonicals, self.excluded = [], [], [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        target = "o-page-header--game-details" in classes or (tag == "section" and attrs.get("id") == "game-over")
        exclude = tag in {"script", "style", "template", "noscript"} or any("skeleton" in item for item in classes)
        # React streaming uses hidden outer containers for real rendered nodes;
        # ignore explicitly hidden targets/children, without discarding those
        # outer transport containers or interpreting hydration scripts.
        exclude = exclude or bool((self.stack or target) and (attrs.get("aria-hidden") == "true" or "hidden" in attrs))
        if self.excluded or exclude:
            if tag not in self._VOID:
                self.excluded.append(tag)
            return
        if tag == "link" and "canonical" in (attrs.get("rel") or "").split():
            self.canonicals.append(attrs.get("href"))
        node = _Node(tag, attrs)
        if self.stack:
            self.stack[-1].children.append(node)
        elif node.has_class("o-page-header--game-details") or (tag == "section" and attrs.get("id") == "game-over"):
            self.roots.append(node)
        else:
            return
        if tag not in self._VOID:
            self.stack.append(node)

    def handle_data(self, data):
        if self.stack and not self.excluded:
            self.stack[-1].children.append(data)

    def handle_endtag(self, tag):
        if tag in self._VOID:
            return
        if self.excluded:
            if self.excluded[-1] != tag:
                raise ValueError("Malformed excluded official HTML subtree.")
            self.excluded.pop()
            return
        if self.stack:
            if self.stack[-1].tag != tag:
                raise ValueError("Malformed official match HTML subtree.")
            self.stack.pop()


def _one_class(root: _Node, class_name: str) -> _Node:
    nodes = [node for node in root.nodes() if node.has_class(class_name)]
    if len(nodes) != 1:
        raise ValueError(f"Expected one official {class_name}.")
    return nodes[0]


def _scores(root: _Node, class_name: str) -> list[int]:
    nodes = [node for node in root.nodes() if node.has_class(class_name)]
    if len(nodes) != 2:
        raise ValueError(f"Expected two official {class_name} values.")
    return [int(_numeric_syntax(r"[0-9]+", node.text())[0]) for node in nodes]


def parse_completion_evidence(html: str, *, source_url: str) -> dict:
    """Read an explicit completed section bound to the page's canonical fixture.

    A missing game-over section is unverified, including numeric live scores.
    Malformed, conflicting, or ambiguous evidence raises instead of guessing.
    """
    url = re.fullmatch(_MATCH_URL, source_url)
    if url is None:
        raise ValueError("Completion evidence must use an official ordinary J1 match URL.")
    parser = _OfficialMatchParser()
    parser.feed(html)
    parser.close()
    if parser.stack or parser.excluded or parser.canonicals != [source_url]:
        raise ValueError("Incomplete official HTML or mismatched/ambiguous canonical URL.")
    headers = [node for node in parser.roots if node.has_class("o-page-header--game-details")]
    game_overs = [node for node in parser.roots if node.tag == "section" and node.attrs.get("id") == "game-over"]
    if len(headers) != 1 or len(game_overs) > 1:
        raise ValueError("Missing or ambiguous official match identity/completion section.")
    header = headers[0]
    logo = _one_class(header, "a-tournament-logo--j1")
    logo_images = [node for node in logo.nodes() if node.tag == "img"]
    if len(logo_images) != 1 or logo_images[0].attrs.get("alt") != "明治安田Ｊ１リーグ":
        raise ValueError("Official evidence has an unrecognized competition logo.")
    parts = _numeric_syntax(
        r"(2026|2027)/([0-9]{1,2})/([0-9]{1,2})\s*\([月火水木金土日](?:・[祝休])?\)(?:\s+[0-9]{2}:[0-9]{2}\s+KO)?",
        _one_class(header, "o-page-header__date").text(),
    )
    year, month, day = map(int, parts.groups())
    match_date = _season_date(year, month, day)
    if year != int(url[1]) or url[2][:4] != f"{month:02d}{day:02d}":
        raise ValueError("Official header date differs from the canonical match URL.")
    round_number = int(_numeric_syntax(r"第([0-9]+)節", _one_class(header, "o-page-header__section").text())[1])
    if not 1 <= round_number <= 38:
        raise ValueError("Official round outside the verified season format.")
    clubs = []
    for side in ("home", "away"):
        node = _one_class(header, f"o-page-header__club--{side}")
        link = re.fullmatch(rf"/club/({_CLUB})/", node.attrs.get("href") or "")
        if node.tag != "a" or link is None:
            raise ValueError("Official header is missing its club identity links.")
        clubs.append(link[1])
    fixture_key = _fixture_key(*clubs)
    verified = bool(game_overs)
    home_score = away_score = None
    if verified:
        over = game_overs[0]
        labels = [node.text() for node in over.nodes() if node.tag == "h3"]
        if labels != ["試合終了"] or not over.has_class("p-game-details-summary-tab__game-over"):
            raise ValueError("The match-specific game-over section lacks the explicit final label.")
        if not header.has_class("o-page-header--game-details--post-game"):
            raise ValueError("Game-over evidence conflicts with the official match header state.")
        displayed = _scores(over, "o-team-comparison__score")
        if displayed != _scores(header, "o-page-header__match-score"):
            raise ValueError("Game-over scores conflict with the official match header.")
        home_score, away_score = displayed
    return {
        "competition_key": COMPETITION_KEY, "fixture_key": fixture_key,
        "match_date": match_date, "round": round_number,
        "home_club": clubs[0], "away_club": clubs[1],
        "home_score": home_score, "away_score": away_score,
        "verified": verified, "source_url": source_url,
        "evidence_type": "official_game_over_section" if verified else "official_completion_unconfirmed",
        "completion_policy_version": COMPLETION_POLICY_VERSION,
    }


def apply_completion_evidence(records: list[dict], evidence_records: list[dict]) -> list[dict]:
    """Promote only candidates with exact official club/date/round/score agreement."""
    evidence_by_key = {}
    records_by_key = {record["fixture_key"]: record for record in records}
    if len(records_by_key) != len(records):
        raise ValueError("Ambiguous duplicate fixture keys.")
    for evidence in evidence_records:
        key = evidence["fixture_key"]
        if key in evidence_by_key or key not in records_by_key:
            raise ValueError("Duplicate evidence or evidence for a fixture absent from this snapshot.")
        record = records_by_key[key]
        if evidence.get("competition_key") != COMPETITION_KEY or any(
            evidence[field] != record[field] for field in ("home_club", "away_club", "match_date", "round")
        ):
            raise ValueError("Official completion evidence differs from the source fixture identity.")
        if evidence["verified"] and (
            record["status"] != "candidate" or not record["match_id"] or any(
                evidence[field] != record[field] for field in ("home_score", "away_score")
            )
        ):
            raise ValueError("Official completion evidence conflicts with the candidate score or match_id.")
        evidence_by_key[key] = evidence
    result = []
    for record in records:
        copy = dict(record)
        evidence = evidence_by_key.get(record["fixture_key"])
        if evidence:
            copy["evidence_url"] = evidence["source_url"]
            copy["evidence_type"] = evidence["evidence_type"]
            if evidence["verified"]:
                copy["status"] = "completed"
        result.append(copy)
    return result


def validate_fixture_coverage(records: list[dict]) -> dict:
    """Check the full published fixture set against the official 20-club format."""
    clubs = {record[side] for record in records for side in ("home_club", "away_club")}
    club_count = 20
    expected_rounds = 2 * (club_count - 1)
    expected_pairs = {(home, away) for home in clubs for away in clubs if home != away}
    pairs = Counter((record["home_club"], record["away_club"]) for record in records)
    if len(clubs) != club_count or len(records) != club_count * (club_count - 1) or pairs != Counter(dict.fromkeys(expected_pairs, 1)):
        raise ValueError("Incomplete or duplicated ordinary J1 home/away fixture coverage.")
    rounds = Counter(record["round"] for record in records)
    if rounds != Counter(dict.fromkeys(range(1, expected_rounds + 1), club_count // 2)):
        raise ValueError("Incomplete ordinary J1 rounds.")
    for number in rounds:
        appearances = Counter(record[side] for record in records if record["round"] == number for side in ("home_club", "away_club"))
        if appearances != Counter(dict.fromkeys(clubs, 1)):
            raise ValueError(f"Invalid club appearances in round {number}.")
    ids = [record["match_id"] for record in records if record["match_id"] is not None]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate official match_id in fixture coverage.")
    return {
        "competition_key": COMPETITION_KEY, "club_count": club_count,
        "round_count": expected_rounds, "fixture_count": len(records),
        "match_id_count": len(ids), "directed_pair_count": len(pairs),
        "club_appearances": dict(sorted(Counter(record[side] for record in records for side in ("home_club", "away_club")).items())),
        "home_appearances": dict(sorted(Counter(record["home_club"] for record in records).items())),
        "away_appearances": dict(sorted(Counter(record["away_club"] for record in records).items())),
        "round_counts": dict(sorted(rounds.items())),
        "statuses": dict(sorted(Counter(record["status"] for record in records).items())),
        "date_min": min(record["match_date"] for record in records),
        "date_max": max(record["match_date"] for record in records),
    }
