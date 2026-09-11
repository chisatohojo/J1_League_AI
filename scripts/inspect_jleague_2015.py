"""Offline-only inspection of the saved 2015 J1 HTML; never downloads data.

Run from the project root: python -m scripts.inspect_jleague_2015
Outputs are normalization candidates, not the production matches.csv.
"""

from collections import Counter
from datetime import date, time
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata

import pandas as pd

from src.collect.matches import REQUIRED_COLUMNS, load_matches, validate_matches


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data/raw/jleague/2015_j1_search.html"
OUTPUT_DIR = ROOT / "data/processed/jleague"
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
        raise ValueError(f"Unexpected 2015 source value: {value!r}")
    return match


def parse_matches_html(html: str) -> pd.DataFrame:
    """Parse a saved 2015 results table without I/O or changing source order."""
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
        if season != "2015":
            raise ValueError(f"Source row {position}: only season 2015 is allowed.")
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
        if year_suffix != 15:
            raise ValueError(f"Source row {position}: date year differs from season.")
        match_date = date(2015, month, day).isoformat()
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
            "match_id": link[1], "season": 2015, "round": round_number,
            "match_date": match_date, "home_team": values[5],
            "away_team": values[7], "stadium": values[8],
            "home_score": home_score, "away_score": away_score,
            "result": 1 if home_score == away_score else 2 if home_score > away_score else 0,
            "stage": stage, "competition": competition, "round_label": round_label,
            "kickoff_time": kickoff, "source_url": SOURCE_BASE + score_links[0],
        })
    return validate_matches(pd.DataFrame(records))


def summarize_matches(matches: pd.DataFrame) -> dict:
    """Reject incomplete 2015 coverage and describe the inspected matches."""
    if len(matches) != 306 or set(matches["season"]) != {2015}:
        raise ValueError("Expected exactly 306 matches from season 2015.")
    if set(matches["stage"]) != {"1st", "2nd"}:
        raise ValueError("Expected both 2015 stages only.")
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
        "season": 2015, "matches": len(matches), "stages": stages,
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


def main() -> None:
    """Reuse the local original; no network requests or alternate seasons."""
    argparse.ArgumentParser(description=__doc__).parse_args()
    raw = RAW_PATH.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    metadata_path = RAW_PATH.with_suffix(".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    if "sha256" in metadata and metadata["sha256"] != digest:
        raise ValueError("Raw HTML SHA-256 differs from acquisition metadata.")
    matches = parse_matches_html(raw.decode("utf-8-sig"))
    summary = summarize_matches(matches)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / "2015_matches_probe.csv"
    matches.to_csv(csv_path, index=False, encoding="utf-8", date_format="%Y-%m-%d")
    roundtrip = load_matches(csv_path)
    pd.testing.assert_frame_equal(matches, roundtrip)
    summary.update({
        "raw_path": RAW_PATH.relative_to(ROOT).as_posix(),
        "raw_sha256": digest, "raw_bytes": len(raw),
        "metadata_sha256_verified": "sha256" in metadata,
        "requested_url": metadata.get("requested_url"),
        "fetched_at_utc": metadata.get("fetched_at_utc"),
        "csv_path": csv_path.relative_to(ROOT).as_posix(),
        "csv_roundtrip_validated": True, "network_requests": 0,
    })
    summary_path = OUTPUT_DIR / "2015_matches_probe.summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"2015 offline probe: {len(matches)} matches; 153 per stage; CSV roundtrip passed.")
    print(f"CSV: {csv_path}\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
