"""Offline SFMS02 player-match participation on a normalized 90-minute clock.

This is not physical elapsed time, official played minutes, a stable player
identity, or a cross-match workload feature. No network access is performed.
"""

from collections import Counter
import csv
from datetime import date
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data/raw/jleague_match_stats"
MATCH_DIR = ROOT / "data/processed/jleague"
STATS_DIR = ROOT / "data/processed/jleague_match_stats"
OUTPUT = ROOT / "data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv"
EXPECTED = {**{year: 306 for year in range(2015, 2021)}, 2021: 380,
            2022: 306, 2023: 306, 2024: 380}
SOURCE = "jleague_data_site_sfms02"
FIELDS = (
    "match_id", "match_date", "season", "team_id", "team_name", "player_name_raw",
    "starter", "listed_substitute", "entered_minute_raw", "entered_minute_normalized",
    "left_minute_raw", "left_minute_normalized", "dismissed_minute_raw",
    "dismissed_minute_normalized", "minutes_played_normalized", "appearance_type",
    "normalization_flags", "source", "source_url", "raw_sha256",
)
_SECTION = {number: re.compile(
    r"<!--\s*A" + str(number) + r"[^>]*?Start\s*-->(.*?)<!--\s*A"
    + str(number) + r"[^>]*?End\s*-->", re.S,
) for number in (5, 6, 7, 9)}
_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_TD = re.compile(r'<td class="([^\"]+)">(.*?)</td>', re.S)
_MINUTE = re.compile(r"(\d+)'(?:\+(\d+))?")


class MinutesError(ValueError):
    """Source structure, identity, event state or minute invariant failed."""


def _rows(fragment: str) -> list[dict[str, str]]:
    result = []
    for match in _TR.finditer(fragment):
        cells = {}
        for cell in _TD.finditer(match.group(1)):
            key = cell.group(1)
            if key in cells:
                raise MinutesError(f"Duplicate cell class {key!r}.")
            cells[key] = unescape(re.sub(r"<[^>]+>", "", cell.group(2))).strip()
        if "name" in cells:
            if not cells["name"] or "\ufffd" in cells["name"]:
                raise MinutesError("Blank or replacement-character player name.")
            result.append(cells)
        elif cells:
            raise MinutesError("Player/event row has no name cell.")
    return result


def normalize_minute(raw: str) -> tuple[int, tuple[int, int, int], str | None]:
    """Return normalized minute, true event-order key, and uncertainty flag.

    The order key keeps 45'+X before minute 46 despite the capped value 45.
    It is for same-match state transitions only, not actual elapsed duration.
    """
    match = _MINUTE.fullmatch(raw) if isinstance(raw, str) else None
    if match is None:
        raise MinutesError(f"Unsupported minute token: {raw!r}.")
    minute = int(match.group(1))
    extra = match.group(2)
    if minute < 1 or minute > 90 or extra is not None and (minute not in (45, 90) or int(extra) < 1):
        raise MinutesError(f"Invalid minute token: {raw!r}.")
    if extra is not None:
        flag = "FIRST_HALF_ADDED_TIME_CAPPED" if minute == 45 else "SECOND_HALF_ADDED_TIME_CAPPED"
        return minute, (0 if minute == 45 else 1, minute, int(extra)), flag
    if minute == 46:
        return 46, (1, 46, 0), "MINUTE_46_BOUNDARY_AMBIGUOUS"
    return minute, (0 if minute <= 45 else 1, minute, 0), None


def _sections(raw: bytes) -> dict[int, list[str]]:
    start = raw.find(b"<!-- A5")
    stop = raw.find(b"<!-- A12", start)
    if start < 0 or stop <= start:
        raise MinutesError("Missing SFMS02 player/event section boundaries.")
    try:
        html = raw[start:stop].decode("utf-8")
    except UnicodeDecodeError:
        # Some historical pages contain legacy bytes elsewhere. Names are
        # independently rejected if any replacement character reaches them.
        html = raw[start:stop].decode("utf-8", errors="replace")
    sections = {number: pattern.findall(html) for number, pattern in _SECTION.items()}
    if any(len(sections[n]) != 2 for n in (5, 6, 7)) or len(sections[9]) not in (0, 2):
        raise MinutesError("Expected two side-specific A5/A6/A7 sections and zero/two A9 sections.")
    return sections


def _player(name: str, *, starter: bool) -> dict:
    return {"player_name_raw": name, "starter": starter, "listed_substitute": not starter,
            "entered_minute_raw": "", "entered_minute_normalized": 0 if starter else None,
            "left_minute_raw": "", "left_minute_normalized": None,
            "dismissed_minute_raw": "", "dismissed_minute_normalized": None,
            "minutes_played_normalized": None, "appearance_type": "",
            "normalization_flags": set(), "_active": starter, "_exit_reason": None,
            "_entered_order": (-1, 0, 0) if starter else None, "_left_order": None,
            "_bench_dismissed": False}


def _side(sections: dict[int, list[str]], side: int) -> tuple[list[dict], dict]:
    starters = _rows(sections[5][side])
    bench = _rows(sections[6][side])
    if len(starters) != 11 or any(row.get("time") for row in starters + bench):
        raise MinutesError("Each side needs 11 starters and empty roster time cells.")
    roster = starters + bench
    names = [row["name"] for row in roster]
    if len(names) != len(set(names)):
        raise MinutesError("Duplicate exact player name within one match/team.")
    players = {row["name"]: _player(row["name"], starter=index < 11)
               for index, row in enumerate(roster)}
    events = []
    substitutions = _rows(sections[7][side])
    if len(substitutions) % 2:
        raise MinutesError("Unpaired substitution row.")
    for index in range(0, len(substitutions), 2):
        out, incoming = substitutions[index:index + 2]
        if (out.get("change") != "▽" or incoming.get("change") != "▲"
                or incoming.get("time") or not out.get("time")
                or out["name"] not in players or incoming["name"] not in players
                or out["name"] == incoming["name"]):
            raise MinutesError("Invalid OUT/IN pair, minute or exact player identity.")
        normalized, order, flag = normalize_minute(out["time"])
        events.append((order, index, "sub", (out["name"], incoming["name"], out["time"], normalized, flag)))
    dismissals = _rows(sections[9][side]) if sections[9] else []
    for index, row in enumerate(dismissals):
        if row["name"] not in players or not row.get("time"):
            raise MinutesError("Dismissal minute or exact player identity missing.")
        normalized, order, flag = normalize_minute(row["time"])
        events.append((order, len(substitutions) + index, "red",
                       (row["name"], row["time"], normalized, flag)))
    # An identical displayed time for a player's substitution and dismissal
    # cannot establish which state came first; do not silently pick an order.
    for order, _, kind, event in events:
        if kind == "red" and any(other_order == order and other_kind == "sub"
                                 and event[0] in other_event[:2]
                                 for other_order, _, other_kind, other_event in events):
            raise MinutesError("Same-minute dismissal/substitution order is ambiguous.")
    events.sort(key=lambda event: (event[0], event[1]))
    counts = Counter(substitution_pairs=len(substitutions) // 2, dismissal_rows=len(dismissals))
    for order, _, kind, event in events:
        if kind == "sub":
            out_name, in_name, raw, minute, flag = event
            out, incoming = players[out_name], players[in_name]
            if (not out["_active"] or incoming["starter"] or incoming["_active"]
                    or incoming["entered_minute_normalized"] is not None
                    or incoming["_bench_dismissed"]):
                raise MinutesError("Impossible substitution player state.")
            out["_active"] = False
            out["left_minute_raw"] = raw
            out["left_minute_normalized"] = minute
            out["_left_order"] = order
            out["_exit_reason"] = "sub"
            incoming["_active"] = True
            incoming["entered_minute_raw"] = raw
            incoming["entered_minute_normalized"] = minute
            incoming["_entered_order"] = order
            if flag:
                out["normalization_flags"].add(flag)
                incoming["normalization_flags"].add(flag)
        else:
            name, raw, minute, flag = event
            player = players[name]
            if player["dismissed_minute_raw"]:
                raise MinutesError("Duplicate dismissal for one player.")
            player["dismissed_minute_raw"] = raw
            player["dismissed_minute_normalized"] = minute
            if flag:
                player["normalization_flags"].add(flag)
            if player["_active"]:
                player["_active"] = False
                player["left_minute_raw"] = raw
                player["left_minute_normalized"] = minute
                player["_left_order"] = order
                player["_exit_reason"] = "red"
                player["normalization_flags"].add("DISMISSAL_APPLIED")
                counts["active_dismissals"] += 1
            elif player["_exit_reason"] == "sub":
                player["normalization_flags"].add("POST_SUB_DISMISSAL_IGNORED")
                counts["post_sub_dismissals"] += 1
            elif not player["starter"] and player["entered_minute_normalized"] is None:
                player["_bench_dismissed"] = True
                player["normalization_flags"].add("UNUSED_SUB_DISMISSAL_IGNORED")
                counts["unused_sub_dismissals"] += 1
            else:
                raise MinutesError("Impossible dismissal player state.")
    rows = []
    for player in players.values():
        start = player["entered_minute_normalized"]
        if start is None:
            if player["starter"] or player["left_minute_normalized"] is not None:
                raise MinutesError("Unused substitute has an active interval.")
            player["minutes_played_normalized"] = 0
            player["appearance_type"] = "unused_substitute"
        else:
            if player["left_minute_normalized"] is None:
                player["left_minute_normalized"] = 90
            end = player["left_minute_normalized"]
            if not 0 <= start <= end <= 90:
                raise MinutesError("Negative or >90 normalized participation interval.")
            player["minutes_played_normalized"] = max(0, end - start)
            reason = player["_exit_reason"]
            if player["starter"]:
                player["appearance_type"] = {None: "starter_full", "sub": "starter_subbed_out",
                                             "red": "starter_dismissed"}[reason]
                if reason is None and player["minutes_played_normalized"] != 90:
                    raise MinutesError("Full-match starter must have 90 normalized minutes.")
            else:
                player["appearance_type"] = {None: "sub_entered", "sub": "sub_entered_and_left",
                                             "red": "sub_entered_dismissed"}[reason]
        public = {key: value for key, value in player.items() if not key.startswith("_")}
        public["normalization_flags"] = ";".join(sorted(public["normalization_flags"]))
        rows.append(public)
    total = sum(row["minutes_played_normalized"] for row in rows)
    red_deficit = sum(90 - row["left_minute_normalized"] for row in rows
                      if row["appearance_type"] in ("starter_dismissed", "sub_entered_dismissed"))
    if total < 0 or total > 990 or total != 990 - red_deficit:
        raise MinutesError(f"Team-minute conservation failed: {total} vs {990 - red_deficit}.")
    return rows, dict(counts)


def parse_match(raw: bytes, *, match_id: str, match_date: str, season: int,
                home_team_id: str, away_team_id: str, home_team: str, away_team: str,
                raw_sha256: str | None = None) -> tuple[list[dict], dict]:
    """Parse one cached match without mutating inputs or accessing the network."""
    if (not re.fullmatch(r"\d+", match_id) or season not in EXPECTED
            or date.fromisoformat(match_date).year != season or home_team_id == away_team_id):
        raise MinutesError("Invalid J1 match identity, date or side IDs.")
    sections = _sections(raw)
    all_rows, totals = [], Counter()
    source_url = f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}"
    digest = raw_sha256 or sha256(raw).hexdigest()
    for side, (team_id, team_name) in enumerate(((home_team_id, home_team),
                                                  (away_team_id, away_team))):
        rows, counts = _side(sections, side)
        totals.update(counts)
        for row in rows:
            all_rows.append({"match_id": match_id, "match_date": match_date,
                             "season": season, "team_id": team_id, "team_name": team_name,
                             **row, "source": SOURCE, "source_url": source_url,
                             "raw_sha256": digest})
    return all_rows, dict(totals)


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise MinutesError(f"Invalid CSV columns: {path}.")
        return list(reader)


def collect_history(*, matches_dir=MATCH_DIR, stats_dir=STATS_DIR,
                    raw_dir=RAW_DIR, output_path=OUTPUT) -> dict:
    """Validate all 2015–2024 inputs before publishing one complete CSV."""
    all_rows, counts = [], Counter()
    match_ids = set()
    season_rows = {}
    for season, expected in EXPECTED.items():
        matches = _read_csv(Path(matches_dir) / f"{season}_matches_probe.csv")
        stats = _read_csv(Path(stats_dir) / f"{season}_match_stats.csv")
        if len(matches) != expected or len(stats) != expected:
            raise MinutesError(f"Season {season} expected {expected} J1 matches and stats rows.")
        by_stats = {row["match_id"]: row for row in stats}
        if len(by_stats) != expected or len({r["match_id"] for r in matches}) != expected:
            raise MinutesError(f"Season {season} has duplicate match IDs.")
        if {r["match_id"] for r in matches} != set(by_stats):
            raise MinutesError(f"Season {season} probe/stats match IDs differ.")
        before = len(all_rows)
        for match in sorted(matches, key=lambda r: (r["match_date"], r["match_id"])):
            mid = match["match_id"]
            if mid in match_ids:
                raise MinutesError(f"Global duplicate J1 match ID: {mid}.")
            match_ids.add(mid)
            stat = by_stats[mid]
            url = f"https://data.j-league.or.jp/SFMS02/?match_card_id={mid}"
            if match["source_url"] != url or stat["source_url"] != url:
                raise MinutesError(f"SFMS02 URL mismatch for {mid}.")
            path = Path(raw_dir) / f"{mid}.html"
            raw = path.read_bytes()
            metadata = json.loads((Path(raw_dir) / f"{mid}.metadata.json").read_text(encoding="utf-8"))
            digest = sha256(raw).hexdigest()
            if (metadata.get("requested_url") != url or metadata.get("final_url") != url
                    or metadata.get("status") != 200 or str(metadata.get("match_id")) != mid
                    or metadata.get("bytes") != len(raw) or metadata.get("sha256") != digest):
                raise MinutesError(f"Invalid SFMS02 cache metadata/SHA-256 for {mid}.")
            rows, audit = parse_match(raw, match_id=mid, match_date=match["match_date"],
                                      season=season, home_team_id=stat["home_team_id"],
                                      away_team_id=stat["away_team_id"],
                                      home_team=stat["home_team"], away_team=stat["away_team"],
                                      raw_sha256=digest)
            counts.update(audit)
            all_rows.extend(rows)
        season_rows[season] = len(all_rows) - before
    if len(match_ids) != 3208 or counts["substitution_pairs"] != 23638 or counts["dismissal_rows"] != 301:
        raise MinutesError("Full-history match/event count differs from the read-only audit.")
    if len(all_rows) != len({(r["match_id"], r["team_id"], r["player_name_raw"]) for r in all_rows}):
        raise MinutesError("Duplicate player-match row.")
    output = Path(output_path)
    if output.exists():
        raise MinutesError(f"Output already exists; refusing overwrite: {output}.")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(all_rows)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {"output_path": output, "matches": len(match_ids), "rows": len(all_rows),
            "season_rows": season_rows, "event_counts": dict(counts)}


if __name__ == "__main__":
    print(json.dumps(collect_history(), ensure_ascii=False, indent=2, default=str))
