"""Collect regular J2 league results from the official SFMS01 listings.

Only SFMS01 listing pages are used; SFMS02 pages are intentionally not fetched.
"""

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

import pandas as pd

from src.collect.teams import TeamMasterError, load_team_master


EXPECTED_COUNTS = {year: 462 for year in range(2015, 2024)} | {2024: 380}
OUTPUT_COLUMNS = (
    "match_id", "season", "match_date", "competition", "competition_raw",
    "stage", "round", "home_team", "away_team", "home_team_id",
    "away_team_id", "home_score", "away_score", "result", "source_url",
)


def _text(parts):
    return " ".join("".join(parts).split())


class _J2TableParser(HTMLParser):
    """Parse only table.table-base00.search-table result rows."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self._table = False
        self._depth = 0
        self._row = None
        self._cell = None
        self._cell_index = None
        self._score_link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and "table-base00" in (attrs.get("class") or "").split() and "search-table" in (attrs.get("class") or "").split():
            self._table = True
            self._depth = 1
            return
        if not self._table:
            return
        if tag == "table":
            self._depth += 1
        elif tag == "tr":
            self._row = []
            self._score_link = None
        elif tag == "td" and self._row is not None:
            self._cell = []
            self._cell_index = len(self._row)
        elif tag == "a" and self._cell is not None and self._cell_index in (5, 6):
            href = attrs.get("href") or ""
            if re.search(r"SFMS02/\?match_card_id=\d+", href):
                self._score_link = href

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if not self._table:
            return
        if tag == "td" and self._cell is not None:
            self._row.append(_text(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if len(self._row) in (10, 11) and self._score_link:
                self.rows.append((tuple(self._row), self._score_link))
            self._row = None
            self._score_link = None
        elif tag == "table":
            self._depth -= 1
            if self._depth == 0:
                self._table = False


def _match_id(href):
    match = re.search(r"match_card_id=(\d+)", href)
    if not match:
        raise ValueError(f"missing SFMS02 match_card_id: {href!r}")
    return match.group(1)


def _score(value):
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", value)
    if not match:
        raise ValueError(f"invalid regular-time score: {value!r}")
    home, away = map(int, match.groups())
    result = 2 if home > away else 0 if home < away else 1
    return home, away, result


def parse_j2_sfms01_html(html: str, *, expected_season: int) -> pd.DataFrame:
    if not isinstance(html, str) or not html:
        raise ValueError("HTML must be nonempty text")
    parser = _J2TableParser()
    parser.feed(html)
    parser.close()
    rows = []
    for cells, href in parser.rows:
        if len(cells) == 11:
            season_raw, competition_raw, round_raw, date_raw, _kickoff, home, score_raw, away, _venue, _attendance, _other = cells
        else:
            season_raw, round_raw, date_raw, _kickoff, home, score_raw, away, _venue, _attendance, _other = cells
            competition_raw = season_raw
        if not re.search(rf"\b{int(expected_season)}\b", season_raw):
            raise ValueError(f"season mismatch: {season_raw!r}")
        date_match = re.search(r"(\d{2})/(\d{2})/(\d{2})", date_raw)
        if not date_match:
            raise ValueError(f"invalid match date: {date_raw!r}")
        yy, month, day = map(int, date_match.groups())
        match_date = pd.Timestamp(int(expected_season), month, day)
        home_score, away_score, result = _score(score_raw)
        match_id = _match_id(href)
        rows.append({
            "match_id": match_id,
            "season": int(expected_season),
            "match_date": match_date,
            "competition": "j2",
            "competition_raw": competition_raw,
            "stage": "full_season",
            "round": round_raw,
            "home_team": home,
            "away_team": away,
            "home_score": home_score,
            "away_score": away_score,
            "result": result,
            "source_url": "https://data.j-league.or.jp" + href if href.startswith("/") else href,
        })
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"no J2 result rows for season {expected_season}")
    if frame.match_id.duplicated().any():
        raise ValueError(f"duplicate match_id in season {expected_season}")
    return frame


def _fetch_listing(url, raw_dir, *, interval=0.25):
    root = Path(raw_dir)
    root.mkdir(parents=True, exist_ok=True)
    season = re.search(r"competition_years=(\d+)", url).group(1)
    html_path = root / f"{season}.html"
    metadata_path = root / f"{season}.metadata.json"
    if html_path.exists() and metadata_path.exists():
        body = html_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if (metadata.get("requested_url") == url and metadata.get("final_url") == url
                and metadata.get("status") == 200 and metadata.get("season") == int(season)
                and metadata.get("bytes") == len(body)
                and metadata.get("sha256") == sha256(body).hexdigest()):
            return body, True
    request = Request(url, headers={"User-Agent": "J1-League-AI research prototype"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
        final_url = response.geturl()
        status = response.status
    html_path.write_bytes(body)
    metadata_path.write_text(json.dumps({
        "requested_url": url, "final_url": final_url, "status": status,
        "season": int(season), "bytes": len(body),
        "sha256": sha256(body).hexdigest(),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    time.sleep(interval)
    return body, False


def collect_j2_history(*, years=range(2015, 2025), raw_dir="data/raw/jleague_j2",
                       output_path="data/processed/jleague_j2/2015_2024_j2_matches.csv",
                       interval=0.25):
    years = tuple(int(year) for year in years)
    if any(year not in EXPECTED_COUNTS for year in years):
        raise ValueError("only seasons 2015-2024 are supported")
    master = load_team_master()
    frames, diagnostics = [], []
    for year in years:
        url = f"https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=2&competition_years={year}&lang=ja"
        body, cache_hit = _fetch_listing(url, raw_dir, interval=interval)
        html = body.decode("utf-8", errors="replace")
        frame = parse_j2_sfms01_html(html, expected_season=year)
        if len(frame) != EXPECTED_COUNTS[year]:
            raise ValueError(f"season {year}: expected {EXPECTED_COUNTS[year]} rows, got {len(frame)}")
        ids = {"home": [], "away": []}
        for row in frame.itertuples(index=False):
            for side in ("home", "away"):
                name = getattr(row, f"{side}_team")
                try:
                    team_id = master.resolve_team_id(name, source="jleague_data_site", on=row.match_date)
                except TeamMasterError as exc:
                    raise ValueError(f"unresolved team: season={year}, match_id={row.match_id}, side={side}, name={name!r}") from exc
                ids[side].append(team_id)
        frame["home_team_id"] = ids["home"]
        frame["away_team_id"] = ids["away"]
        diagnostics.append({"season": year, "matches": len(frame), "cache_hit": cache_hit,
                            "unique_clubs": len(set(frame.home_team) | set(frame.away_team))})
        frames.append(frame)
    output = pd.concat(frames, ignore_index=True).loc[:, list(OUTPUT_COLUMNS)]
    output = output.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    if output.match_id.duplicated().any() or output.home_team.eq(output.away_team).any():
        raise ValueError("invalid full J2 history identity")
    if output[["match_date", "home_team_id", "away_team_id", "home_score", "away_score"]].isna().any().any():
        raise ValueError("missing required J2 field")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False, encoding="utf-8")
    output.attrs["diagnostics"] = pd.DataFrame(diagnostics)
    return output
