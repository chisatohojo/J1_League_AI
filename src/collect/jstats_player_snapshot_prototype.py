"""Offline feasibility parser for current J Stats player ranking pages.

This is not a collector.  It performs no network access and publishes no
snapshot or feature data.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from src.collect.jstats_team_snapshots import SCHEDULE, expected_club_slugs
from src.collect.teams import TeamMaster, load_team_master


@dataclass(frozen=True)
class PlayerStat:
    slug: str
    label: str
    unit: str


STATS = {
    "score": PlayerStat("score", "得点ランキング", "goals"),
    "distance": PlayerStat("distance", "総走行距離", "km"),
    "time": PlayerStat("time", "出場時間", "minutes"),
}


class PlayerSnapshotPrototypeError(ValueError):
    """A bounded feasibility page violates an observed source contract."""


@dataclass(frozen=True)
class PlayerRow:
    player_id: str | None
    player_id_candidate: str
    player_id_candidate_source: str
    player_name_raw: str
    position_raw: str
    position_group: str
    club_team_id: str
    official_club_name: str
    official_club_slug: str
    stat_value: str
    raw_value: str
    player_profile_url: str
    identity_status: str


@dataclass(frozen=True)
class PlayerPageAudit:
    stat_slug: str
    stat_label: str
    unit: str
    source_updated_date_jst: str
    row_count: int
    unique_player_ids: int
    player_id_coverage: int
    numeric_candidate_coverage: int
    unresolved_identity_rows: int
    duplicate_exact_rows: int
    conflicting_player_names: int
    multi_club_player_ids: int
    null_values: int
    unique_clubs: int
    position_distribution: dict[str, int]
    visible_rows: int
    embedded_rows: int
    load_more_max: int
    rows: tuple[PlayerRow, ...]


class _Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []
        self.text_parts = []
        self.visible = []
        self._script_parts = []
        self._in_script = False
        self._player_href = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "script":
            self._in_script = True
            self._script_parts = []
        elif tag == "a" and "m-ranking-player-list-item__link" in classes:
            self._player_href = attrs.get("href")
        elif tag == "div" and "m-ranking-player-list-item" in classes:
            self.visible.append((self._player_href, attrs.get("name"), attrs.get("score")))

    def handle_data(self, data):
        if self._in_script:
            self._script_parts.append(data)
        else:
            self.text_parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.scripts.append("".join(self._script_parts))
            self._in_script = False
        elif tag == "a":
            self._player_href = None


def _rsc_values(page: _Page, key: str):
    values = []
    decoder = json.JSONDecoder(parse_float=Decimal)
    pattern = re.compile(rf'"{re.escape(key)}"\s*:')
    for script in page.scripts:
        if not script.startswith("self.__next_f.push(") or not script.endswith(")"):
            continue
        try:
            push = json.loads(script[len("self.__next_f.push("):-1])
        except (TypeError, ValueError) as exc:
            raise PlayerSnapshotPrototypeError("Malformed Next.js flight payload") from exc
        if not isinstance(push, list) or len(push) < 2 or not isinstance(push[1], str):
            continue
        payload = push[1]
        for match in pattern.finditer(payload):
            try:
                start = match.end()
                while start < len(payload) and payload[start].isspace():
                    start += 1
                values.append(decoder.raw_decode(payload, start)[0])
            except ValueError as exc:
                raise PlayerSnapshotPrototypeError(f"Malformed RSC {key}") from exc
    return values


def discover_player_stat_options(raw: bytes) -> dict[str, str]:
    """Read official stat option values/labels from a current player page."""
    page = _parse_html(raw)
    options = {}

    def visit(value):
        if isinstance(value, list):
            for child in value:
                visit(child)
            return
        if not isinstance(value, dict):
            return
        slug, label = value.get("value"), value.get("label")
        if isinstance(slug, str) and isinstance(label, str):
            previous = options.setdefault(slug, label)
            if previous != label:
                raise PlayerSnapshotPrototypeError(f"Conflicting option label for {slug}")
        for child in value.values():
            if isinstance(child, (dict, list)):
                visit(child)

    stats_filters = []
    for filter_list in _rsc_values(page, "filterList"):
        if isinstance(filter_list, list):
            stats_filters.extend(
                item for item in filter_list
                if isinstance(item, dict) and item.get("id") == "stats"
            )
    if len(stats_filters) != 1:
        raise PlayerSnapshotPrototypeError("Expected exactly one official stats filter")
    visit(stats_filters[0].get("groups", []))
    return options


def _parse_html(raw: bytes) -> _Page:
    if not isinstance(raw, bytes):
        raise PlayerSnapshotPrototypeError("Expected raw response bytes")
    try:
        html = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise PlayerSnapshotPrototypeError("Page is not lossless UTF-8") from exc
    page = _Page()
    page.feed(html)
    return page


def _number(value) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        raise PlayerSnapshotPrototypeError(f"Non-numeric stat value: {value!r}")
    raw = str(value)
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", raw):
        raise PlayerSnapshotPrototypeError(f"Non-numeric stat value: {raw!r}")
    try:
        if not Decimal(raw).is_finite():
            raise PlayerSnapshotPrototypeError(f"Non-finite stat value: {raw!r}")
    except InvalidOperation as exc:
        raise PlayerSnapshotPrototypeError(f"Non-numeric stat value: {raw!r}") from exc
    return raw


def parse_player_page(
    raw: bytes,
    *,
    stat: PlayerStat,
    expected_slugs: set[str],
    master: TeamMaster,
    observed_date: date | str,
) -> PlayerPageAudit:
    """Strictly audit one complete ranking embedded in an offline HTML response."""
    if STATS.get(stat.slug) != stat:
        raise PlayerSnapshotPrototypeError(f"Unapproved feasibility stat: {stat.slug!r}")
    page = _parse_html(raw)
    text = " ".join(page.text_parts)
    if "2026/27" not in text or "Ｊ１" not in text:
        raise PlayerSnapshotPrototypeError("Page does not identify 2026/27 ordinary J1")
    dates = set(re.findall(r"(20[0-9]{2})/([0-9]{1,2})/([0-9]{1,2})\s*更新", text))
    if len(dates) != 1:
        raise PlayerSnapshotPrototypeError("Expected exactly one displayed update date")
    year, month, day = next(iter(dates))
    source_date = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    datetime.fromisoformat(source_date)

    rankings = _rsc_values(page, "rankingList")
    if len(rankings) != 1 or not isinstance(rankings[0], list) or len(rankings[0]) != 1:
        raise PlayerSnapshotPrototypeError(f"Expected one RSC rankingList; got {len(rankings)}")
    ranking = rankings[0][0]
    if (
        ranking.get("id") != f"ranking-{stat.slug}"
        or ranking.get("category") != "j1"
        or str(ranking.get("year")) != "2026"
        or ranking.get("stats") != {"value": stat.slug, "label": stat.label}
    ):
        raise PlayerSnapshotPrototypeError("Ranking season/category/stat identity mismatch")
    data = ranking.get("data")
    if not isinstance(data, list) or not data:
        raise PlayerSnapshotPrototypeError("Ranking data is empty or invalid")
    load_more_values = [
        value for value in _rsc_values(page, "loadMore")
        if isinstance(value, dict) and {"max", "end", "step"} <= set(value)
    ]
    if len(load_more_values) != 1:
        raise PlayerSnapshotPrototypeError("Expected exactly one loadMore contract")
    load_more = load_more_values[0]
    if load_more.get("max") != len(data):
        raise PlayerSnapshotPrototypeError("Embedded row count does not match loadMore.max")

    aliases = master.aliases
    rows = []
    for item in data:
        if not isinstance(item, dict):
            raise PlayerSnapshotPrototypeError("Ranking row is not an object")
        href = item.get("href")
        match = re.fullmatch(r"/player/([0-9]+)/", href or "")
        lookup = item.get("legacyPlayerPhotoLookup")
        direct_id = match.group(1) if match else None
        lookup_id = str(lookup.get("playerId", "")) if isinstance(lookup, dict) else ""
        if lookup_id and not re.fullmatch(r"[0-9]+", lookup_id):
            raise PlayerSnapshotPrototypeError("Ranking row has a non-numeric player ID candidate")
        candidates = {candidate for candidate in (direct_id, lookup_id) if candidate}
        if len(candidates) != 1:
            raise PlayerSnapshotPrototypeError("Ranking row has conflicting player ID candidates")
        player_id = next(iter(candidates))
        name = item.get("name")
        if not isinstance(name, str) or not name or item.get("playerName") != name:
            raise PlayerSnapshotPrototypeError("Player name fields are missing or inconsistent")
        position_raw = item.get("position")
        position = re.fullmatch(r"(GK|DF|MF|FW)(?: [0-9]+)?", position_raw or "")
        if not position:
            raise PlayerSnapshotPrototypeError(f"Invalid player position: {position_raw!r}")
        club = item.get("club")
        if not isinstance(club, dict):
            raise PlayerSnapshotPrototypeError("Player row lacks club identity")
        slug, club_name = club.get("code"), club.get("fullName")
        if not isinstance(slug, str) or slug not in expected_slugs or not isinstance(club_name, str):
            raise PlayerSnapshotPrototypeError(f"Club is outside current J1: {slug!r}")
        matches = [
            alias for alias in aliases
            if alias.source == "jleague_official"
            and alias.source_club_id == slug
            and alias.source_name == club_name
        ]
        if len(matches) != 1:
            raise PlayerSnapshotPrototypeError(f"Exact TeamMaster club identity failed: {slug!r}")
        team_id = master.resolve_team_id(club_name, source="jleague_official", on=observed_date)
        if team_id != matches[0].team_id:
            raise PlayerSnapshotPrototypeError(f"TeamMaster club identity conflict: {slug!r}")
        value = _number(item.get("score"))
        rows.append(PlayerRow(
            player_id=direct_id,
            player_id_candidate=player_id,
            player_id_candidate_source=(
                "DIRECT_PROFILE_LINK"
                if direct_id else "LEGACY_PLAYER_PHOTO_LOOKUP"
            ),
            player_name_raw=name,
            position_raw=position_raw,
            position_group=position.group(1),
            club_team_id=team_id,
            official_club_name=club_name,
            official_club_slug=slug,
            stat_value=value,
            raw_value=value,
            player_profile_url=href or "",
            identity_status=(
                "EXACT_OFFICIAL_PROFILE_ID_AND_CLUB"
                if direct_id else "UNRESOLVED_NO_DIRECT_PROFILE_LINK"
            ),
        ))

    expected_visible = min(10, len(rows))
    if len(page.visible) != expected_visible:
        raise PlayerSnapshotPrototypeError("Visible ranking row count mismatch")
    for visible, row in zip(page.visible, rows):
        href, name, value = visible
        if href != row.player_profile_url or name != row.player_name_raw or _number(value) != row.stat_value:
            raise PlayerSnapshotPrototypeError("Visible and embedded ranking rows disagree")

    exact = Counter((row.player_id_candidate, row.official_club_slug) for row in rows)
    names = defaultdict(set)
    clubs = defaultdict(set)
    for row in rows:
        names[row.player_id_candidate].add(row.player_name_raw)
        clubs[row.player_id_candidate].add(row.official_club_slug)
    return PlayerPageAudit(
        stat_slug=stat.slug,
        stat_label=stat.label,
        unit=stat.unit,
        source_updated_date_jst=source_date,
        row_count=len(rows),
        unique_player_ids=len(names),
        player_id_coverage=sum(bool(row.player_profile_url) for row in rows),
        numeric_candidate_coverage=sum(bool(row.player_id_candidate) for row in rows),
        unresolved_identity_rows=sum(row.identity_status.startswith("UNRESOLVED") for row in rows),
        duplicate_exact_rows=sum(count - 1 for count in exact.values() if count > 1),
        conflicting_player_names=sum(len(values) > 1 for values in names.values()),
        multi_club_player_ids=sum(len(values) > 1 for values in clubs.values()),
        null_values=0,
        unique_clubs=len({row.official_club_slug for row in rows}),
        position_distribution=dict(sorted(Counter(row.position_group for row in rows).items())),
        visible_rows=len(page.visible),
        embedded_rows=len(rows),
        load_more_max=load_more["max"],
        rows=tuple(rows),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug", choices=tuple(STATS))
    parser.add_argument("html", type=Path)
    args = parser.parse_args(argv)
    audit = parse_player_page(
        args.html.read_bytes(),
        stat=STATS[args.slug],
        expected_slugs=expected_club_slugs(SCHEDULE),
        master=load_team_master(),
        observed_date=date.today(),
    )
    output = asdict(audit)
    output.pop("rows")
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
