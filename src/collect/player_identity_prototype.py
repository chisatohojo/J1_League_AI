"""Strict, offline helpers for the official-player-identity prototype.

This module does not collect pages, create an internal player master, normalize
names, or infer registration intervals.  It distinguishes an official page
that merely enumerates display names from one that actually exposes stable
profile IDs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Iterable, Mapping
from urllib.parse import parse_qs, urljoin, urlparse


SOURCE_NAMESPACE = "jleague_data_site"
LINK_STATUSES = frozenset({"EXACT", "UNRESOLVED", "AMBIGUOUS", "COLLISION"})


class PlayerIdentityPrototypeError(ValueError):
    """The prototype input or official source structure is unsafe."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or "\ufffd" in value:
        raise PlayerIdentityPrototypeError(f"Invalid {label}: {value!r}")
    return value


def _season(value: object) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise PlayerIdentityPrototypeError(f"Invalid season: {value!r}") from exc
    if result < 1993 or result > 9999 or str(result) != str(value):
        raise PlayerIdentityPrototypeError(f"Invalid season: {value!r}")
    return result


@dataclass(frozen=True)
class EnumeratedDisplayPlayer:
    official_player_name: str
    official_player_id: str | None
    source_profile_url: str | None


@dataclass(frozen=True)
class SFPR01EnumerationAudit:
    season: int
    team_id: str
    source_team_name: str
    source_url: str
    players: tuple[EnumeratedDisplayPlayer, ...]

    @property
    def display_player_count(self) -> int:
        return len(self.players)

    @property
    def id_bearing_player_count(self) -> int:
        return sum(player.official_player_id is not None for player in self.players)

    @property
    def id_enumeration_complete(self) -> bool:
        return bool(self.players) and self.id_bearing_player_count == len(self.players)


@dataclass(frozen=True)
class OfficialPlayerRecord:
    season: int
    team_id: str
    official_player_id: str
    official_player_name: str
    source_namespace: str
    source_profile_url: str


@dataclass(frozen=True)
class PlayerLink:
    season: int
    team_id: str
    sfms02_player_name_raw: str
    official_player_id: str
    official_player_name: str
    source_namespace: str
    source_profile_url: str
    link_status: str
    link_reason: str


@dataclass(frozen=True)
class LinkageAudit:
    links: tuple[PlayerLink, ...]
    unique_status_counts: Mapping[str, int]
    player_match_status_counts: Mapping[str, int]
    sfms02_unique_players: int
    sfms02_player_match_rows: int

    @property
    def exact_linkage_rate(self) -> float:
        if not self.sfms02_unique_players:
            return 0.0
        return self.unique_status_counts["EXACT"] / self.sfms02_unique_players


class _SFPR01Parser(HTMLParser):
    def __init__(self, source_url: str):
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self.page_text: list[str] = []
        self.players: list[EnumeratedDisplayPlayer] = []
        self._in_name_cell = False
        self._cell_text: list[str] = []
        self._cell_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "th" and "name-c" in classes:
            if self._in_name_cell:
                raise PlayerIdentityPrototypeError("Nested SFPR01 player-name cells")
            self._in_name_cell = True
            self._cell_text = []
            self._cell_links = []
        elif tag == "a" and self._in_name_cell and values.get("href"):
            self._cell_links.append(values["href"] or "")

    def handle_data(self, data: str) -> None:
        self.page_text.append(data)
        if self._in_name_cell:
            self._cell_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "th" or not self._in_name_cell:
            return
        name = _text("".join(self._cell_text).strip(), "official player name")
        identities = []
        for href in self._cell_links:
            absolute = urljoin(self.source_url, href)
            parsed = urlparse(absolute)
            query = parse_qs(parsed.query, keep_blank_values=True)
            ids = query.get("player_id", [])
            if (parsed.scheme, parsed.netloc, parsed.path) == (
                    "https", "data.j-league.or.jp", "/SFIX04/") and len(ids) == 1:
                player_id = ids[0]
                if not re.fullmatch(r"[1-9][0-9]*", player_id):
                    raise PlayerIdentityPrototypeError("Invalid Data Site player_id link")
                identities.append((player_id, absolute))
        if len(set(identities)) > 1:
            raise PlayerIdentityPrototypeError(f"Multiple player IDs in one SFPR01 cell: {name!r}")
        identity = identities[0] if identities else (None, None)
        self.players.append(EnumeratedDisplayPlayer(name, identity[0], identity[1]))
        self._in_name_cell = False
        self._cell_text = []
        self._cell_links = []


def parse_sfpr01_enumeration(raw: bytes, *, season: int, team_id: str,
                             source_team_name: str, source_url: str) -> SFPR01EnumerationAudit:
    """Audit one saved SFPR01 result without network access or name normalization."""
    season = _season(season)
    team_id = _text(team_id, "team_id")
    source_team_name = _text(source_team_name, "source team name")
    source_url = _text(source_url, "source_url")
    parsed_url = urlparse(source_url)
    query = parse_qs(parsed_url.query, keep_blank_values=True)
    if ((parsed_url.scheme, parsed_url.netloc, parsed_url.path) !=
            ("https", "data.j-league.or.jp", "/SFPR01/search")
            or query.get("competition_year") != [str(season)]
            or len(query.get("competition_id", [])) != 1
            or len(query.get("team_id", [])) != 1):
        raise PlayerIdentityPrototypeError("Source URL is not the expected official SFPR01 season result")
    try:
        html = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PlayerIdentityPrototypeError("SFPR01 source is not strict UTF-8") from exc
    parser = _SFPR01Parser(source_url)
    parser.feed(html)
    parser.close()
    if parser._in_name_cell:
        raise PlayerIdentityPrototypeError("Unclosed SFPR01 player-name cell")
    page_text = "".join(parser.page_text)
    if source_team_name not in page_text or not parser.players:
        raise PlayerIdentityPrototypeError("SFPR01 team identity or player rows are missing")
    return SFPR01EnumerationAudit(
        season=season,
        team_id=team_id,
        source_team_name=source_team_name,
        source_url=source_url,
        players=tuple(parser.players),
    )


def _official_record(record: OfficialPlayerRecord) -> OfficialPlayerRecord:
    season = _season(record.season)
    team_id = _text(record.team_id, "official team_id")
    player_id = _text(record.official_player_id, "official_player_id")
    name = _text(record.official_player_name, "official player name")
    namespace = _text(record.source_namespace, "source_namespace")
    profile_url = _text(record.source_profile_url, "source_profile_url")
    parsed = urlparse(profile_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (namespace != SOURCE_NAMESPACE or not re.fullmatch(r"[1-9][0-9]*", player_id)
            or (parsed.scheme, parsed.netloc, parsed.path) !=
            ("https", "data.j-league.or.jp", "/SFIX04/")
            or query.get("player_id") != [player_id]):
        raise PlayerIdentityPrototypeError("Official player record has an invalid namespace/profile identity")
    return OfficialPlayerRecord(season, team_id, player_id, name, namespace, profile_url)


def link_exact_player_identities(
        sfms02_rows: Iterable[Mapping[str, object]],
        official_players: Iterable[OfficialPlayerRecord], *,
        known_collision_names: Iterable[str] = (),
) -> LinkageAudit:
    """Link exact season/team/raw-name keys; never normalize or infer a person."""
    official_index: dict[tuple[int, str, str], list[OfficialPlayerRecord]] = defaultdict(list)
    seen_official = set()
    for value in official_players:
        if not isinstance(value, OfficialPlayerRecord):
            raise TypeError("official_players must contain OfficialPlayerRecord values")
        record = _official_record(value)
        identity = (record.season, record.team_id, record.official_player_id)
        if identity in seen_official:
            raise PlayerIdentityPrototypeError(f"Duplicate official player record: {identity}")
        seen_official.add(identity)
        official_index[(record.season, record.team_id, record.official_player_name)].append(record)

    collisions = frozenset(_text(name, "known collision name") for name in known_collision_names)
    row_keys = []
    for row in sfms02_rows:
        if not isinstance(row, Mapping):
            raise TypeError("sfms02_rows must contain mappings")
        row_keys.append((_season(row.get("season")), _text(row.get("team_id"), "SFMS02 team_id"),
                         _text(row.get("player_name_raw"), "player_name_raw")))
    if not row_keys:
        raise PlayerIdentityPrototypeError("At least one SFMS02 row is required")

    links = []
    by_key = {}
    for key in sorted(set(row_keys)):
        season, team_id, name = key
        candidates = official_index.get(key, [])
        ids = {candidate.official_player_id for candidate in candidates}
        if len(ids) == 1:
            candidate = candidates[0]
            link = PlayerLink(season, team_id, name, candidate.official_player_id,
                              candidate.official_player_name, candidate.source_namespace,
                              candidate.source_profile_url, "EXACT",
                              "exact season, team_id and raw display name resolved one official ID")
        elif len(ids) > 1:
            status = "COLLISION" if name in collisions else "AMBIGUOUS"
            link = PlayerLink(season, team_id, name, "", "", "", "", status,
                              "exact scoped name resolved multiple official IDs")
        elif name in collisions:
            link = PlayerLink(season, team_id, name, "", "", "", "", "COLLISION",
                              "known same-name people exist but no scoped official ID record is available")
        else:
            link = PlayerLink(season, team_id, name, "", "", "", "", "UNRESOLVED",
                              "no exact scoped official ID record")
        by_key[key] = link
        links.append(link)

    unique_counts = Counter(link.link_status for link in links)
    row_counts = Counter(by_key[key].link_status for key in row_keys)
    for status in LINK_STATUSES:
        unique_counts.setdefault(status, 0)
        row_counts.setdefault(status, 0)
    return LinkageAudit(
        links=tuple(links),
        unique_status_counts=dict(sorted(unique_counts.items())),
        player_match_status_counts=dict(sorted(row_counts.items())),
        sfms02_unique_players=len(links),
        sfms02_player_match_rows=len(row_keys),
    )
