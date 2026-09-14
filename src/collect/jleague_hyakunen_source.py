"""Read the separate 2026 J1 Hyakunen source format from verified local files.

This module does not fetch pages, infer competition winners, or change the
ordinary J1 parser. In particular, listing scores may include extra time.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata

from src.collect.jleague import HEADERS, SOURCE_BASE, _SearchTableParser, _numeric_syntax


COMPETITION_KEY = "j1_hyakunen_2026"
SOURCE_URL = (
    f"{SOURCE_BASE}/SFMS01/search?competition_frame_ids=35"
    "&competition_years=20261&tv_relay_station_name="
)
_COMPETITIONS = {
    "明治安田Ｊ１百年構想 EASTグループ": ("regional", "EAST"),
    "明治安田Ｊ１百年構想 WESTグループ": ("regional", "WEST"),
    "明治安田Ｊ１百年構想 プレーオフラウンド": ("playoff", None),
}


def _team_source_url(links: list[str]) -> str:
    if len(links) != 1 or re.fullmatch(r"https?://www\.jleague\.jp/club/[a-z0-9_-]+/profile/", links[0]) is None:
        raise ValueError("Expected one official team profile link per side.")
    return links[0]


def parse_listing(html: str) -> list[dict]:
    """Preserve source order and labels, without treating display scores as 90 minutes."""
    parser = _SearchTableParser()
    parser.feed(html)
    parser.close()
    if parser.table_count != 1 or parser.inside or len(parser.rows) < 2:
        raise ValueError("Expected one complete nonempty Hyakunen search-table.")
    header = parser.rows[0]
    if tuple(cell[1] for cell in header) != HEADERS or any(cell[0] != "th" for cell in header):
        raise ValueError("Unexpected Hyakunen search-table headers.")
    records = []
    seen_ids = set()
    for position, row in enumerate(parser.rows[1:], 1):
        if len(row) != len(HEADERS) or any(cell[0] != "td" for cell in row):
            raise ValueError(f"Source row {position}: expected 11 data cells.")
        values = [cell[1] for cell in row]
        if any(not value.strip() for value in values):
            raise ValueError(f"Source row {position}: missing source value.")
        season, competition, round_label, date_label, kickoff = values[:5]
        if season != "2026特別" or competition not in _COMPETITIONS:
            raise ValueError(f"Source row {position}: unexpected season or competition.")
        stage, group = _COMPETITIONS[competition]
        unit = "節" if stage == "regional" else "戦"
        parts = _numeric_syntax(rf"第([0-9]+){unit}第([0-9]+)日", round_label)
        number, day_number = map(int, parts.groups())
        if not 1 <= number <= (18 if stage == "regional" else 2) or day_number < 1:
            raise ValueError(f"Source row {position}: invalid round or leg.")
        parts = _numeric_syntax(r"26/([0-9]{2})/([0-9]{2})\([月火水木金土日](?:・[祝休])?\)", date_label)
        match_date = date(2026, *map(int, parts.groups())).isoformat()
        if re.fullmatch(r"[0-9]{2}:[0-9]{2}", kickoff) is None:
            raise ValueError(f"Source row {position}: invalid kickoff time.")
        time.fromisoformat(kickoff)
        scores = _numeric_syntax(r"([0-9]+)-([0-9]+)(?:\s*\(PK([0-9]+)-([0-9]+)\))?", values[6])
        home, away = map(int, scores.groups()[:2])
        pk_home, pk_away = (int(value) if value is not None else None for value in scores.groups()[2:])
        if pk_home is not None and pk_home == pk_away:
            raise ValueError(f"Source row {position}: tied PK score.")
        links = row[6][2]
        match_link = re.fullmatch(r"/SFMS02/\?match_card_id=([1-9][0-9]*)", links[0]) if len(links) == 1 else None
        if match_link is None:
            raise ValueError(f"Source row {position}: invalid match-card link.")
        match_id = match_link[1]
        if match_id in seen_ids:
            raise ValueError(f"Duplicate source match_id: {match_id}.")
        seen_ids.add(match_id)
        placement = None
        placement_matches = re.findall(r"([0-9]+)[‐-]([0-9]+)位決定戦", unicodedata.normalize("NFKC", values[10]))
        if stage == "playoff":
            if len(placement_matches) != 1:
                raise ValueError(f"Source row {position}: missing or ambiguous placement range.")
            low, high = map(int, placement_matches[0])
            if low not in range(1, 20, 2) or high != low + 1:
                raise ValueError(f"Source row {position}: invalid placement range.")
            placement = f"{low}-{high}"
        elif placement_matches:
            raise ValueError(f"Source row {position}: regional match has a playoff placement.")
        records.append({
            "match_id": match_id, "season": 2026, "competition_key": COMPETITION_KEY,
            "source_year_id": 20261, "source_frame_id": 35,
            "source_season_label": season, "competition": competition,
            "stage": stage, "group": group,
            "round": number if stage == "regional" else None,
            "leg": number if stage == "playoff" else None,
            "round_label": round_label, "match_date": match_date,
            "match_date_label": date_label, "kickoff_time": kickoff,
            "home_team": values[5], "away_team": values[7], "stadium": values[8],
            "home_team_source_url": _team_source_url(row[5][2]),
            "away_team_source_url": _team_source_url(row[7][2]),
            "source_url": SOURCE_BASE + links[0], "raw_score_text": values[6],
            "displayed_home_score": home, "displayed_away_score": away,
            "home_pk_score": pk_home, "away_pk_score": pk_away,
            "placement_range": placement, "broadcast_raw": values[10],
        })
    return records


@dataclass
class _Node:
    tag: str
    attrs: dict
    children: list = field(default_factory=list)

    def text(self) -> str:
        return "".join(child.text() if isinstance(child, _Node) else child for child in self.children).strip()

    def nodes(self, tag: str | None = None):
        for child in self.children:
            if isinstance(child, _Node):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.nodes(tag)

    def has_class(self, value: str) -> bool:
        return value in (self.attrs.get("class") or "").split()


class _DetailParser(HTMLParser):
    """Collect only scoreboard trees and the page's own repost identity."""

    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.roots = []
        self.stack = []
        self.script = None
        self.scripts = []
        self.identity_inputs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.script = []
        if tag == "input" and attrs.get("name") == "match_card_id" and attrs.get("type") == "hidden":
            self.identity_inputs.append(attrs.get("value"))
        node = _Node(tag, attrs)
        if self.stack:
            self.stack[-1].children.append(node)
        elif tag == "div" and (node.has_class("score-board-main") or node.has_class("score-board-pk")):
            self.roots.append(node)
        else:
            return
        if tag not in self._VOID:
            self.stack.append(node)

    def handle_data(self, data):
        if self.script is not None:
            self.script.append(data)
        if self.stack:
            self.stack[-1].children.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.script is not None:
            self.scripts.append("".join(self.script))
            self.script = None
        if not self.stack or tag in self._VOID:
            return
        if self.stack[-1].tag != tag:
            raise ValueError("Malformed detail scoreboard HTML.")
        self.stack.pop()


def _score(value: str) -> int:
    return int(_numeric_syntax(r"[0-9]+", value)[0])


def parse_detail(html: str, *, expected_match_id: str) -> dict:
    """Extract 90-minute and incremental extra-time scores from the official detail."""
    if re.fullmatch(r"[1-9][0-9]*", expected_match_id) is None:
        raise ValueError("Invalid expected match_id.")
    parser = _DetailParser()
    parser.feed(html)
    parser.close()
    if parser.stack:
        raise ValueError("Incomplete detail scoreboard HTML.")
    # SFMS02 carries its own match identity in its repost form, not in match links.
    identities = list(parser.identity_inputs)
    pattern = r"form\.append\(\s*'<input\s+type=\"hidden\"\s+name=\"match_card_id\"\s+value=\"([0-9]+)\"\s*/>'\s*\)"
    for script in parser.scripts:
        identities.extend(re.findall(pattern, script))
    if identities != [expected_match_id]:
        raise ValueError("Detail page match_id is missing, duplicated, or differs from the expected match.")
    mains = [node for node in parser.roots if node.has_class("score-board-main")]
    if len(mains) != 1:
        raise ValueError("Expected exactly one detail score-board-main.")
    main = mains[0]
    rows = [node for node in main.nodes("tr") if any(
        child.attrs.get("id") in {"team-name-l", "team-name-r"} for child in node.nodes("th")
    )]
    if len(rows) != 1:
        raise ValueError("Expected one detail home/away scoreboard row.")
    cells = [node for node in rows[0].children if isinstance(node, _Node)]
    if (
        [node.tag for node in cells] != ["th", "td", "td", "td", "th"]
        or cells[0].attrs.get("id") != "team-name-l"
        or cells[4].attrs.get("id") != "team-name-r"
        or not cells[1].has_class("score") or not cells[3].has_class("score")
        or not cells[2].has_class("time")
        or len([node for node in main.nodes("td") if node.has_class("score")]) != 2
    ):
        raise ValueError("Unexpected detail home/away scoreboard layout.")
    home_name, away_name = cells[0].text(), cells[4].text()
    if not home_name or not away_name or home_name == away_name:
        raise ValueError("Missing or identical detail teams.")
    home_team_source_url = _team_source_url([node.attrs.get("href", "") for node in cells[0].nodes("a")])
    away_team_source_url = _team_source_url([node.attrs.get("href", "") for node in cells[4].nodes("a")])
    displayed_home, displayed_away = _score(cells[1].text()), _score(cells[3].text())
    periods = {}
    dls = [node for node in cells[2].children if isinstance(node, _Node)]
    for dl in dls:
        values = [node for node in dl.children if isinstance(node, _Node)]
        if (
            dl.tag != "dl" or [node.tag for node in values] != ["dd", "dt", "dd"]
            or not values[0].has_class("left-area") or not values[2].has_class("right-area")
        ):
            raise ValueError("Unexpected detail period sides or layout.")
        label = values[1].text()
        if label in periods:
            raise ValueError("Duplicate detail period.")
        periods[label] = (_score(values[0].text()), _score(values[2].text()))
    if list(periods) not in (["前半", "後半"], ["前半", "後半", "延長前半", "延長後半"]):
        raise ValueError("Missing, unknown, or out-of-order detail period.")
    home_90 = periods["前半"][0] + periods["後半"][0]
    away_90 = periods["前半"][1] + periods["後半"][1]
    extra_time = "延長前半" in periods
    et_home = periods["延長前半"][0] + periods["延長後半"][0] if extra_time else None
    et_away = periods["延長前半"][1] + periods["延長後半"][1] if extra_time else None
    if (home_90 + (et_home or 0), away_90 + (et_away or 0)) != (displayed_home, displayed_away):
        raise ValueError("Detail periods do not sum to the displayed score.")
    pk_summaries = []
    pk_grid_present = False
    for block in (node for node in parser.roots if node.has_class("score-board-pk")):
        for row in block.nodes("tr"):
            cells = [node for node in row.children if isinstance(node, _Node)]
            if not any(node.tag == "th" and node.text() == "PK戦" for node in cells):
                continue
            # The separate player/kick grid also has a PK戦 heading, but nested tables.
            if any(list(node.nodes("table")) for node in cells):
                pk_grid_present = True
                continue
            if (
                [node.tag for node in cells] != ["td", "th", "td"]
                or cells[1].text() != "PK戦"
                or not cells[0].has_class("left-area") or not cells[2].has_class("right-area")
            ):
                raise ValueError("Malformed detail PK summary.")
            pk_summaries.append((_score(cells[0].text()), _score(cells[2].text())))
    if len(pk_summaries) > 1:
        raise ValueError("Duplicate detail PK summaries.")
    if pk_grid_present and not pk_summaries:
        raise ValueError("Detail PK kick grid has no numeric summary.")
    pk_home, pk_away = pk_summaries[0] if pk_summaries else (None, None)
    if pk_home is not None and pk_home == pk_away:
        raise ValueError("Tied detail PK score.")
    return {
        "home_score_90": home_90, "away_score_90": away_90,
        "extra_time_played": extra_time,
        "home_extra_time_score": et_home, "away_extra_time_score": et_away,
        "displayed_home_score": displayed_home, "displayed_away_score": displayed_away,
        "home_pk_score": pk_home, "away_pk_score": pk_away,
        "home_team_detail": home_name, "away_team_detail": away_name,
        "home_team_source_url": home_team_source_url,
        "away_team_source_url": away_team_source_url,
    }


def _read_cache(path: Path, *, expected_url: str) -> tuple[str, dict]:
    raw = path.read_bytes()
    metadata = json.loads(path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError(f"Invalid cache metadata: {path.name}.")
    try:
        timestamp = datetime.fromisoformat(metadata["fetched_at_utc"])
        valid_time = timestamp.tzinfo is not None and timestamp.utcoffset() == timedelta(0)
    except (KeyError, ValueError, TypeError):
        valid_time = False
    content_type = metadata.get("content_type", "")
    if (
        metadata.get("requested_url") != expected_url or metadata.get("final_url") != expected_url
        or metadata.get("status") != 200 or type(metadata.get("status")) is not int
        or metadata.get("bytes") != len(raw) or type(metadata.get("bytes")) is not int
        or metadata.get("sha256") != hashlib.sha256(raw).hexdigest()
        or not valid_time or not isinstance(content_type, str)
        or re.fullmatch(r"text/html\s*;\s*charset\s*=\s*UTF-8", content_type, re.IGNORECASE) is None
    ):
        raise ValueError(f"Cache metadata or SHA-256 mismatch: {path.name}; no refetch performed.")
    return raw.decode("utf-8-sig"), metadata


def read_cached_sources(*, raw_dir: Path) -> tuple[list[dict], dict[str, dict], dict]:
    """Require verified listing and every playoff leg 2 detail; never fetch on failure."""
    raw_dir = Path(raw_dir)
    html, listing_metadata = _read_cache(raw_dir / "j1_search.html", expected_url=SOURCE_URL)
    records = parse_listing(html)
    details = {}
    metadata = {"j1_search.html": listing_metadata}
    for record in records:
        path = raw_dir / f"match_{record['match_id']}.html"
        required = record["stage"] == "playoff" and record["leg"] == 2
        if not required and not path.exists():
            continue
        html, detail_metadata = _read_cache(path, expected_url=record["source_url"])
        detail = parse_detail(html, expected_match_id=record["match_id"])
        if any(detail[column] != record[column] for column in ("home_team_source_url", "away_team_source_url")):
            raise ValueError(f"Detail home/away team identity differs from listing: {record['match_id']}.")
        details[record["match_id"]] = detail
        metadata[path.name] = detail_metadata
    return records, details, metadata
