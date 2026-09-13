"""Parse and inspect cached J.League Data Site results for verified seasons.

HTML parsing is independent of files; cache reads never perform network I/O.
"""

from collections import Counter
from datetime import date, time
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata

import pandas as pd

from src.collect.matches import REQUIRED_COLUMNS, validate_matches


SUPPORTED_SEASONS = (2015, 2016)
SOURCE_BASE = "https://data.j-league.or.jp"
HEADERS = (
    "シーズン", "大会", "節", "試合日", "K/O時刻", "ホーム", "スコア",
    "アウェイ", "スタジアム", "入場者数", "インターネット中継・TV放送",
)


class _SearchTableParser(HTMLParser):
    """Collect text and links only inside the unique search-table table."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_count = 0
        self.inside = False
        self.rows = []
        self.row = None
        self.cell_tag = None
        self.parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table":
            if self.inside:
                raise ValueError("Nested table inside search-table.")
            if "search-table" in (attrs.get("class") or "").split():
                self.table_count += 1
                self.inside = True
        if not self.inside:
            return
        if tag == "tr":
            if self.row is not None:
                raise ValueError("Unclosed row inside search-table.")
            self.row = []
        elif tag in ("th", "td"):
            if self.row is None or self.cell_tag is not None:
                raise ValueError("Invalid cell inside search-table.")
            self.cell_tag, self.parts, self.links = tag, [], []
        elif tag == "a" and self.cell_tag:
            self.links.append(attrs.get("href") or "")

    def handle_data(self, data):
        if self.inside and self.cell_tag:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if not self.inside:
            return
        if tag in ("th", "td"):
            if self.cell_tag != tag or self.row is None:
                raise ValueError("Mismatched cell inside search-table.")
            self.row.append((tag, "".join(self.parts).strip(), self.links))
            self.cell_tag = None
        elif tag == "tr":
            if self.row is None or self.cell_tag is not None:
                raise ValueError("Incomplete row inside search-table.")
            self.rows.append(self.row)
            self.row = None
        elif tag == "table":
            if self.row is not None:
                raise ValueError("Incomplete table.")
            self.inside = False


def _numeric_syntax(pattern: str, value: str) -> re.Match:
    # Normalize full-width syntax, never club/stadium names or source labels.
    match = re.fullmatch(pattern, unicodedata.normalize("NFKC", value))
    if match is None:
        raise ValueError(f"Unexpected source value: {value!r}")
    return match


def parse_matches_html(html: str, *, expected_season: int) -> pd.DataFrame:
    """Parse a saved, explicitly selected 2015/2016 table without I/O."""
    if expected_season not in SUPPORTED_SEASONS:
        raise ValueError("Only the verified 2015 and 2016 seasons are supported.")
    parser = _SearchTableParser()
    parser.feed(html)
    parser.close()
    if parser.table_count != 1 or parser.inside or not parser.rows:
        raise ValueError("Expected one complete search-table.")
    header = parser.rows[0]
    if tuple(cell[1] for cell in header) != HEADERS or any(
        cell[0] != "th" for cell in header
    ):
        raise ValueError("Unexpected search-table headers.")
    records = []
    for position, row in enumerate(parser.rows[1:], 1):
        if len(row) != 11 or any(cell[0] != "td" for cell in row):
            raise ValueError(f"Source row {position}: expected 11 data cells.")
        values = [cell[1] for cell in row]
        season, competition, round_label, date_label, kickoff = values[:5]
        if season != str(expected_season):
            raise ValueError(f"Source row {position}: expected season {expected_season}.")
        stage = _numeric_syntax(r"J1\s+(1st|2nd)", competition)[1]
        round_parts = _numeric_syntax(r"第([0-9]+)節第([0-9]+)日", round_label)
        round_number, day_number = map(int, round_parts.groups())
        if not 1 <= round_number <= 17 or day_number < 1:
            raise ValueError(f"Source row {position}: invalid stage round/day.")
        date_parts = _numeric_syntax(
            r"([0-9]{2})/([0-9]{2})/([0-9]{2})\([^()]+\)",
            date_label,
        )
        year_suffix, month, day = map(int, date_parts.groups())
        if year_suffix != expected_season % 100:
            raise ValueError(f"Source row {position}: date year differs from season.")
        match_date = date(expected_season, month, day).isoformat()
        if re.fullmatch(r"[0-9]{2}:[0-9]{2}", kickoff) is None:
            raise ValueError(f"Source row {position}: invalid kickoff time.")
        time.fromisoformat(kickoff)
        scores = _numeric_syntax(r"([0-9]+)-([0-9]+)", values[6])
        home_score, away_score = map(int, scores.groups())
        score_links = row[6][2]
        link = re.fullmatch(r"/SFMS02/\?match_card_id=([0-9]+)", score_links[0]) if (
            len(score_links) == 1
        ) else None
        if link is None:
            raise ValueError(f"Source row {position}: invalid score match-card link.")
        records.append({
            "match_id": link[1], "season": expected_season, "round": round_number,
            "match_date": match_date, "home_team": values[5],
            "away_team": values[7], "stadium": values[8],
            "home_score": home_score, "away_score": away_score,
            "result": 1 if home_score == away_score else 2 if home_score > away_score else 0,
            "stage": stage, "competition": competition, "round_label": round_label,
            "kickoff_time": kickoff, "source_url": SOURCE_BASE + score_links[0],
        })
    return validate_matches(pd.DataFrame(records))


def summarize_matches(matches: pd.DataFrame, *, expected_season: int) -> dict:
    """Reject incomplete coverage for the verified 2015/2016 two-stage format."""
    if expected_season not in SUPPORTED_SEASONS:
        raise ValueError("Only the verified 2015 and 2016 seasons are supported.")
    if len(matches) != 306 or set(matches["season"]) != {expected_season}:
        raise ValueError(f"Expected exactly 306 matches from season {expected_season}.")
    if set(matches["stage"]) != {"1st", "2nd"}:
        raise ValueError(f"Expected both {expected_season} stages only.")
    stages = {}
    for stage, group in matches.groupby("stage", sort=True):
        rounds = group["round"].value_counts().sort_index().to_dict()
        clubs = Counter(group["home_team"]) + Counter(group["away_team"])
        if len(group) != 153 or rounds != dict.fromkeys(range(1, 18), 9):
            raise ValueError(f"Incomplete rounds in stage {stage}.")
        if len(clubs) != 18 or set(clubs.values()) != {17}:
            raise ValueError(f"Incomplete club appearances in stage {stage}.")
        stages[stage] = {
            "matches": len(group), "round_counts": rounds,
            "date_min": group["match_date"].min().date().isoformat(),
            "date_max": group["match_date"].max().date().isoformat(),
            "club_appearances": dict(sorted(clubs.items())),
        }
    if set(stages["1st"]["club_appearances"]) != set(stages["2nd"]["club_appearances"]):
        raise ValueError("The two stages have different clubs.")
    return {
        "season": expected_season, "matches": len(matches), "stages": stages,
        "date_min": matches["match_date"].min().date().isoformat(),
        "date_max": matches["match_date"].max().date().isoformat(),
        "clubs": sorted(set(matches["home_team"]) | set(matches["away_team"])),
        "stadiums": sorted(matches["stadium"].unique().tolist()),
        "match_id_count": int(matches["match_id"].nunique()),
        "match_ids": matches["match_id"].tolist(),
        "required_missing": matches[list(REQUIRED_COLUMNS)].isna().sum().to_dict(),
        "duplicate_match_ids": int(matches["match_id"].duplicated().sum()),
        "duplicate_matches": int(matches.duplicated(
            ["season", "match_date", "home_team", "away_team"]
        ).sum()),
        "adjacent_date_decreases": int((matches["match_date"].diff() < pd.Timedelta(0)).sum()),
        "result_counts": matches["result"].value_counts().sort_index().to_dict(),
        "source_row_order_preserved": True,
    }


def read_cached_matches(year: int, *, raw_dir: Path) -> tuple[pd.DataFrame, dict]:
    """Require a complete, verifiable local cache; never fetch on failure."""
    if year not in SUPPORTED_SEASONS:
        raise ValueError("Only 2015 and 2016 caches are supported.")
    raw_path = Path(raw_dir) / f"{year}_j1_search.html"
    raw = raw_path.read_bytes()
    metadata = json.loads(raw_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    expected_url = (
        f"{SOURCE_BASE}/SFMS01/search?competition_frame_ids=1"
        f"&competition_years={year}&tv_relay_station_name="
    )
    if (
        metadata.get("requested_url") != expected_url
        or metadata.get("final_url") != expected_url
        or metadata.get("status") != 200
        or metadata.get("bytes") != len(raw)
        or metadata.get("sha256") != hashlib.sha256(raw).hexdigest()
        or not metadata.get("fetched_at_utc")
    ):
        raise ValueError(f"{year} cache metadata or SHA-256 mismatch; no refetch performed.")
    return parse_matches_html(raw.decode("utf-8-sig"), expected_season=year), metadata


def build_review_summary(matches: pd.DataFrame, *, expected_season: int) -> dict:
    """Verify the selected season coverage and include all requested human-review fields."""
    matches = validate_matches(matches)
    extra_columns = {"stage", "competition", "round_label", "kickoff_time", "source_url"}
    missing_columns = extra_columns - set(matches.columns)
    if missing_columns:
        raise ValueError(f"Missing research columns: {', '.join(sorted(missing_columns))}")
    summary = summarize_matches(matches, expected_season=expected_season)
    clubs = summary["clubs"]
    counts = {
        club: {
            "total": int(((matches.home_team == club) | (matches.away_team == club)).sum()),
            "home": int((matches.home_team == club).sum()),
            "away": int((matches.away_team == club).sum()),
        }
        for club in clubs
    }
    if any(count != {"total": 34, "home": 17, "away": 17} for count in counts.values()):
        raise ValueError("Expected each club to play 34 matches: 17 home and 17 away.")
    for stage, group in matches.groupby("stage"):
        pairs = Counter(tuple(sorted(pair)) for pair in zip(group.home_team, group.away_team))
        if len(pairs) != 153 or set(pairs.values()) != {1}:
            raise ValueError(f"Stage {stage} must contain all 153 club pairs exactly once.")
    if matches.duplicated(["home_team", "away_team"]).any():
        raise ValueError("Annual home/away matchups must each occur exactly once.")

    blank_counts = {
        column: int(matches[column].astype("string").str.strip().eq("").sum())
        for column in matches
    }
    missing_counts = matches.isna().sum().to_dict()
    if any(blank_counts.values()) or any(missing_counts.values()):
        raise ValueError("Review columns contain missing or blank values.")
    expected_result = (
        (matches.home_score > matches.away_score).astype("int64") * 2
        + (matches.home_score == matches.away_score).astype("int64")
    )
    display = matches.copy()
    display["match_date"] = display["match_date"].dt.strftime("%Y-%m-%d")
    summary.update({
        "columns": matches.columns.tolist(), "club_count": len(clubs),
        "club_match_counts": counts,
        "round_counts": matches["round"].value_counts().sort_index().to_dict(),
        "missing_counts": missing_counts, "blank_counts": blank_counts,
        "duplicate_rows": int(matches.duplicated().sum()),
        "same_team_rows": int((matches.home_team == matches.away_team).sum()),
        "score_result_mismatches": int((matches.result != expected_result).sum()),
        "negative_score_rows": int(((matches.home_score < 0) | (matches.away_score < 0)).sum()),
        "total_goals": int(matches.home_score.sum() + matches.away_score.sum()),
        "random_state": 42,
        "first_five": display.head(5).to_dict("records"),
        "last_five": display.tail(5).to_dict("records"),
        "random_ten": display.sample(n=10, random_state=42).to_dict("records"),
    })
    return summary
