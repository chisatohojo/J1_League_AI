"""Offline extraction of manager names from cached SFMS02 pages."""

from __future__ import annotations

from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

import pandas as pd

from src.collect.matches import load_matches

OUTPUT_COLUMNS = (
    "match_id", "season", "match_date", "home_team_id", "away_team_id",
    "home_manager_name", "away_manager_name", "home_manager_staff_id",
    "away_manager_staff_id", "source_url",
)
EXPECTED_MATCH_COUNTS = {2015: 306, 2016: 306, 2017: 306, 2018: 306, 2019: 306,
                         2020: 306, 2021: 380, 2022: 306, 2023: 306, 2024: 380}


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


class _ManagerParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, set[str]]] = []
        self._text: list[str] = []
        self._heading: list[str] = []
        self._side: str | None = None
        self._name_depth: int | None = None
        self._name_text: list[str] = []
        self.managers: dict[str, list[str]] = {"home": [], "away": []}
        self._manager_section = False

    def handle_comment(self, data):
        # The cached pages contain an explicit A10 manager-area marker.  The
        # marker is more stable than the page's localized/legacy-encoded text.
        if "A10" in data and "Start" in data:
            self._manager_section = True

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        self._stack.append((tag, classes))
        if tag == "h4" and "two-column-table-st-base" in classes:
            self._text = []
        if tag == "div" and classes.intersection({"two-column-table-box-l", "two-column-table-box-r"}):
            self._side = "home" if "two-column-table-box-l" in classes else "away"
        if tag == "td" and "name" in classes and self._heading:
            self._name_depth = len(self._stack)
            self._name_text = []

    def handle_data(self, data):
        if self._stack and self._stack[-1][0] == "h4":
            self._text.append(data)
        if self._name_depth is not None:
            self._name_text.append(data)

    def handle_endtag(self, tag):
        if not self._stack:
            raise ValueError("Malformed HTML")
        current_tag, classes = self._stack[-1]
        if tag == "h4" and "two-column-table-st-base" in classes:
            if self._manager_section or _clean("".join(self._text)) == "監督":
                self._heading.append("manager")
            self._text = []
        if tag == "td" and self._name_depth == len(self._stack):
            value = _clean("".join(self._name_text))
            if self._side in self.managers and self._heading and value:
                self.managers[self._side].append(value)
            self._name_depth = None
            self._name_text = []
        if tag == "div" and classes.intersection({"two-column-table-box-l", "two-column-table-box-r"}):
            self._side = None
        self._stack.pop()


def parse_match_managers_html(html: str, *, expected_match_id: str,
                              source_url: str | None = None) -> pd.DataFrame:
    if not isinstance(expected_match_id, str) or not expected_match_id.strip():
        raise ValueError("expected_match_id must be nonempty")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("HTML must be nonempty")
    match_id = expected_match_id.strip()
    if source_url:
        query_id = parse_qs(urlparse(source_url).query).get("match_card_id", [None])[0]
        if query_id != match_id:
            raise ValueError("source_url match_card_id mismatch")
    parser = _ManagerParser()
    parser.feed(html)
    parser.close()
    values = {}
    for side in ("home", "away"):
        candidates = parser.managers[side]
        if len(candidates) != 1:
            raise ValueError(f"{side} manager must have exactly one candidate")
        values[side] = candidates[0]
    return pd.DataFrame([{
        "match_id": match_id,
        "home_manager_name": values["home"], "away_manager_name": values["away"],
        "home_manager_staff_id": None, "away_manager_staff_id": None,
        "source_url": source_url,
    }], columns=("match_id", "home_manager_name", "away_manager_name",
                  "home_manager_staff_id", "away_manager_staff_id", "source_url"))


def load_cached_match_managers(match_id: str, *, raw_dir: str | Path = "data/raw/jleague_match_stats") -> pd.DataFrame:
    match_id = str(match_id)
    root = Path(raw_dir)
    raw_path, meta_path = root / f"{match_id}.html", root / f"{match_id}.metadata.json"
    if not raw_path.exists() or not meta_path.exists():
        raise FileNotFoundError(f"missing SFMS02 cache for {match_id}")
    raw = raw_path.read_bytes()
    try:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise ValueError(f"invalid metadata for {match_id}") from error
    url = f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}"
    if (metadata.get("requested_url") != url or metadata.get("final_url") != url
            or metadata.get("status") != 200 or metadata.get("match_id") != match_id
            or metadata.get("bytes") != len(raw)
            or metadata.get("sha256") != sha256(raw).hexdigest()):
        raise ValueError(f"invalid SFMS02 cache for {match_id}")
    return parse_match_managers_html(raw.decode("utf-8", errors="replace"),
                                     expected_match_id=match_id, source_url=url)


def collect_match_manager_history(*, seasons=range(2015, 2025),
                                   matches_dir: str | Path = "data/processed/jleague",
                                   stats_dir: str | Path = "data/processed/jleague_match_stats",
                                   raw_dir: str | Path = "data/raw/jleague_match_stats",
                                   output_path: str | Path = "data/processed/jleague_match_managers/2015_2024_match_managers.csv") -> pd.DataFrame:
    frames = []
    for season in seasons:
        if season not in EXPECTED_MATCH_COUNTS:
            raise ValueError(f"unsupported season: {season}")
        matches = load_matches(Path(matches_dir) / f"{season}_matches_probe.csv")
        stats = pd.read_csv(Path(stats_dir) / f"{season}_match_stats.csv", dtype={"match_id": str})
        source = matches.merge(stats[["match_id", "home_team_id", "away_team_id"]],
                               on="match_id", how="inner", validate="one_to_one")
        if len(source) != EXPECTED_MATCH_COUNTS[season]:
            raise ValueError(f"season {season} match count mismatch")
        rows = []
        for row in source.itertuples(index=False):
            parsed = load_cached_match_managers(row.match_id, raw_dir=raw_dir)
            item = parsed.iloc[0].to_dict()
            item.update(season=season, match_date=pd.to_datetime(row.match_date),
                        home_team_id=row.home_team_id, away_team_id=row.away_team_id)
            rows.append(item)
        frames.append(pd.DataFrame(rows))
    result = pd.concat(frames, ignore_index=True).loc[:, list(OUTPUT_COLUMNS)]
    result = result.sort_values(["match_date", "match_id"], kind="mergesort").reset_index(drop=True)
    if len(result) != 3208 or not result["match_id"].is_unique:
        raise ValueError("history must contain 3208 unique matches")
    if result[["home_manager_name", "away_manager_name"]].isna().any().any():
        raise ValueError("manager names must not be missing")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8")
    return result


def manager_transition_candidates(history: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for team_id, group in history.sort_values(["match_date", "match_id"]).groupby("home_team_id"):
        previous = None
        previous_id = None
        for row in group.itertuples(index=False):
            current = row.home_manager_staff_id or row.home_manager_name
            if previous is not None and current != previous:
                rows.append((team_id, previous_id, row.match_id, previous, current, row.match_date))
            previous, previous_id = current, row.match_id
    for team_id, group in history.sort_values(["match_date", "match_id"]).groupby("away_team_id"):
        previous = None
        previous_id = None
        for row in group.itertuples(index=False):
            current = row.away_manager_staff_id or row.away_manager_name
            if previous is not None and current != previous:
                rows.append((team_id, previous_id, row.match_id, previous, current, row.match_date))
            previous, previous_id = current, row.match_id
    return pd.DataFrame(rows, columns=["team_id", "previous_match_id", "current_match_id",
                                       "previous_manager", "current_manager", "match_date"])
