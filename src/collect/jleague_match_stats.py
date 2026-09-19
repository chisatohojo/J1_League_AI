"""Prototype parser and cache-aware fetcher for one J.League official record."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import pandas as pd


STAT_LABELS = ("SH", "CK", "FK")
OUTPUT_COLUMNS = (
    "match_id", "home_team", "away_team", "home_shots", "away_shots",
    "home_ck", "away_ck", "home_fk", "away_fk", "source_url",
)


class _OfficialRecordParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.teams: dict[str, str] = {}
        self.stats: dict[str, tuple[int, int]] = {}
        self._tag_stack: list[str] = []
        self._class_stack: list[set[str]] = []
        self._id_stack: list[str] = []
        self._text_parts: list[str] = []
        self._current_label: str | None = None
        self._current_values: dict[str, str] = {}
        self._in_stats = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        element_id = attributes.get("id") or ""
        self._tag_stack.append(tag)
        self._class_stack.append(classes)
        self._id_stack.append(element_id)
        if element_id in ("team-name-l", "team-name-r"):
            self._text_parts = []
        if "score-board-other" in classes:
            self._in_stats = True
        if self._in_stats and tag == "dl" and "score-board-base" in classes:
            self._current_label = None
            self._current_values = {}
        if self._in_stats and tag == "dt":
            self._text_parts = []
        if self._in_stats and tag == "div" and classes.intersection({"left-score", "right-score"}):
            self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._tag_stack and (
            any(element_id in ("team-name-l", "team-name-r") for element_id in self._id_stack)
            or self._in_stats and self._tag_stack[-1] in {"dt", "div"}
        ):
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._tag_stack:
            raise ValueError("Malformed HTML: unexpected closing tag.")
        element_id = self._id_stack[-1]
        classes = self._class_stack[-1]
        text = "".join(self._text_parts).strip()
        if element_id in ("team-name-l", "team-name-r") and text:
            self.teams[element_id] = text
        if self._in_stats and tag == "dt" and text in STAT_LABELS:
            self._current_label = text
        if self._in_stats and tag == "div" and classes.intersection({"left-score", "right-score"}):
            side = "home" if "left-score" in classes else "away"
            self._current_values[side] = text
        if self._in_stats and tag == "dl" and "score-board-base" in classes:
            label = self._current_label
            if label is not None:
                if label in self.stats:
                    raise ValueError(f"Ambiguous duplicate statistic: {label}")
                if set(self._current_values) != {"home", "away"}:
                    raise ValueError(f"Incomplete statistic: {label}")
                self.stats[label] = (
                    _parse_nonnegative_int(self._current_values["home"], label),
                    _parse_nonnegative_int(self._current_values["away"], label),
                )
            self._current_label = None
            self._current_values = {}
        if tag == "div" and "score-board-other" in classes:
            self._in_stats = False
        closing_team = element_id in ("team-name-l", "team-name-r")
        self._tag_stack.pop()
        self._class_stack.pop()
        self._id_stack.pop()
        if closing_team or tag in {"dt", "div"}:
            self._text_parts = []

    def close(self) -> None:
        super().close()


def _parse_nonnegative_int(value: str, label: str) -> int:
    if not re.fullmatch(r"\d+", value):
        raise ValueError(f"{label} must be a nonnegative integer: {value!r}")
    return int(value)


def _validate_match_id(match_id: str) -> str:
    if not isinstance(match_id, str) or not match_id.strip():
        raise ValueError("expected_match_id must be nonempty.")
    return match_id.strip()


def _decode_html(raw: bytes) -> str:
    # The live page declares UTF-8 but may contain a few malformed legacy
    # bytes; replacement keeps the official team/stat text parseable.
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("utf-8-sig", errors="replace")


def parse_match_stats_html(
    html: str, *, expected_match_id: str, source_url: str | None = None,
) -> pd.DataFrame:
    """Parse one official record without network or filesystem access."""
    match_id = _validate_match_id(expected_match_id)
    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML must be nonempty.")
    if source_url is not None:
        query_id = parse_qs(urlparse(source_url).query).get("match_card_id", [None])[0]
        if query_id is not None and query_id != match_id:
            raise ValueError("source_url match_card_id does not match expected_match_id.")
    parser = _OfficialRecordParser()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError) as error:
        raise ValueError(str(error)) from error
    if set(parser.teams) != {"team-name-l", "team-name-r"}:
        raise ValueError("Missing home or away team in official record.")
    home_team, away_team = parser.teams["team-name-l"], parser.teams["team-name-r"]
    if not home_team or not away_team or home_team == away_team:
        raise ValueError("Invalid home/away team values.")
    if set(parser.stats) != set(STAT_LABELS):
        raise ValueError("Official record must contain exactly SH, CK and FK.")
    row = {
        "match_id": match_id, "home_team": home_team, "away_team": away_team,
        "home_shots": parser.stats["SH"][0], "away_shots": parser.stats["SH"][1],
        "home_ck": parser.stats["CK"][0], "away_ck": parser.stats["CK"][1],
        "home_fk": parser.stats["FK"][0], "away_fk": parser.stats["FK"][1],
        "source_url": source_url,
    }
    return pd.DataFrame([row], columns=OUTPUT_COLUMNS)


def fetch_match_stats(
    match_id: str, *, raw_dir: str | Path = "data/raw/jleague_match_stats",
) -> pd.DataFrame:
    """Fetch one official page, reusing a verified raw HTML/metadata cache."""
    match_id = _validate_match_id(match_id)
    raw_root = Path(raw_dir)
    raw_root.mkdir(parents=True, exist_ok=True)
    url = f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}"
    raw_path = raw_root / f"{match_id}.html"
    metadata_path = raw_root / f"{match_id}.metadata.json"
    raw = None
    if raw_path.exists() and metadata_path.exists():
        candidate = raw_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (
            metadata.get("requested_url") == url and metadata.get("final_url") == url
            and metadata.get("status") == 200 and metadata.get("match_id") == match_id
            and metadata.get("bytes") == len(candidate)
            and metadata.get("sha256") == hashlib.sha256(candidate).hexdigest()
        ):
            raw = candidate
    if raw is None:
        request = Request(url, headers={"User-Agent": "J1-League-AI research prototype"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            final_url = response.geturl()
            status = response.status
        raw_path.write_bytes(raw)
        metadata = {
            "requested_url": url, "final_url": final_url, "status": status,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "match_id": match_id,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return parse_match_stats_html(_decode_html(raw), expected_match_id=match_id, source_url=url)
