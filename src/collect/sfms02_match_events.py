"""Parser-only contract for cached SFMS02 match events."""
from __future__ import annotations
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from html import unescape
from src.collect.sfms02_player_minutes import _rows, _sections, normalize_minute
from src.collect.teams import load_team_master

EVENT_TYPES = {"GOAL", "SUBSTITUTION", "YELLOW_CARD", "RED_CARD"}
SOURCE = "jleague_data_site_sfms02"
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data/raw/jleague_match_stats"
MATCH_DIR = ROOT / "data/processed/jleague"
STATS_DIR = ROOT / "data/processed/jleague_match_stats"
OUTPUT_DIR = ROOT / "data/processed/sfms02_match_events"
OUTPUT = OUTPUT_DIR / "2015_2024_j1_match_events.csv"
SUMMARY = OUTPUT_DIR / "2015_2024_j1_match_events.validation.json"
EXPECTED = {**{year: 306 for year in range(2015, 2021)}, 2021: 380,
            2022: 306, 2023: 306, 2024: 380}
FIELDS = (
    "event_id", "match_id", "match_date", "season", "team_id", "team_name",
    "side", "event_type", "player_name_raw", "related_player_name_raw",
    "minute_raw", "minute_normalized", "minute_order_half", "minute_order_base",
    "minute_order_added", "normalization_flags", "source_section",
    "source_row_index", "null_reason", "source", "source_url", "raw_sha256",
)
# SFMS02 A1 records the adjudicated 0-3 result, while A2 retains the five
# on-field scoring rows.  Event rows are preserved; score reconstruction is
# explicitly not asserted for this source-internal restatement.
SCORE_NOT_CHECKABLE = {
    "25153": "official A1 adjudicated score differs from retained A2 event history",
}

class MatchEventError(ValueError):
    """A source, identity, parser, or dataset invariant failed."""

def _text(value):
    return unescape(re.sub(r"<[^>]+>", "", value)).strip()

def _digest(value):
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

def _rows_from_fragment(fragment):
    result = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", fragment, re.S):
        cells = [_text(cell) for cell in re.findall(r"<td(?:\s[^>]*)?>(.*?)</td>", row, re.S)]
        if cells:
            result.append(cells)
    return result

def _section_fragments(text, number):
    return re.findall(r"<!--\s*A" + str(number) + r"[^>]*Start\s*-->(.*?)<!--\s*A" + str(number) + r"[^>]*End\s*-->", text, re.S)

def _minute(raw):
    value = raw.replace(" ", "")
    match = re.fullmatch(r"(\d+)(?:'\+|\+)(\d+)'", value)
    if match:
        base, added = int(match.group(1)), int(match.group(2))
        if base not in (45, 90) or added < 1:
            raise ValueError(f"Unsupported minute token: {raw!r}")
        return base, (0 if base == 45 else 1, base, added), None
    return normalize_minute(value)

def _validate_player(name, context):
    if not name or "\ufffd" in name:
        raise ValueError(f"Malformed {context} player name.")

def _event(base, *, event_type, side, player, related, minute_raw, source_section,
           source_row_index, flags=None, minute_parts=None, null_reason=None):
    if event_type not in EVENT_TYPES or side not in {"home", "away"}:
        raise ValueError("Invalid event type or side.")
    row = dict(base, team_side=side, event_type=event_type, player_name_raw=player,
               related_player_name_raw=related, minute_raw=minute_raw, minute_normalized=None,
               minute_order_half=None, minute_order_base=None, minute_order_added=None,
               normalization_flags=sorted(flags or []), source_section=source_section,
               source_row_index=source_row_index, null_reason=null_reason)
    if minute_parts is not None:
        minute, order, flag = minute_parts
        row.update(minute_normalized=minute, minute_order_half=order[0], minute_order_base=order[1], minute_order_added=order[2])
        if flag:
            row["normalization_flags"] = sorted(set(row["normalization_flags"]) | {flag})
    identity = {key: row[key] for key in ("match_id", "team_side", "source_section", "source_row_index", "event_type")}
    row["event_id"] = _digest(identity)
    return row

def _event_minute(raw, *, source_section):
    if raw == "***" and source_section in {"A8", "A9"}:
        return None, "SOURCE_MINUTE_UNRESOLVED"
    return _minute(raw), None

def parse_match_events(raw: bytes, *, match_id: str, match_date: str, season: int, team_ids: dict[str, str], team_names: dict[str, str], source_url: str, raw_sha256: str | None = None):
    if (not match_id or set(team_ids) != {"home", "away"} or set(team_names) != {"home", "away"}
            or any(not team_ids[k] for k in team_ids) or any(not team_names[k] for k in team_names)
            or team_ids["home"] == team_ids["away"]):
        raise ValueError("Match identity and exact team IDs are required.")
    text = raw.decode("utf-8", errors="replace")
    base = {"match_id": str(match_id), "match_date": match_date, "season": season, "team_id": None, "team_name": None, "side": None, "source": SOURCE, "source_url": source_url, "raw_sha256": raw_sha256 or hashlib.sha256(raw).hexdigest()}
    events = []
    fragments = _section_fragments(text, 2)
    if len(fragments) > 1:
        raise ValueError("Unexpected duplicate A2 section.")
    if fragments:
        fragment = fragments[0]
        for marker, side in (("left-area", "home"), ("right-area", "away")):
            table = re.search(rf'class="{marker}"\s*>\s*<table[^>]*>(.*?)</table>', fragment, re.S)
            if table is None:
                raise ValueError("Malformed A2 side container.")
            for index, source_cells in enumerate(_rows_from_fragment(table.group(1))):
                # SFMS02 mirrors the cells: home is [player, minute], while
                # away is [minute, player].  Preserve the source player text.
                cells = source_cells if side == "home" else list(reversed(source_cells))
                if len(cells) < 2 or not cells[0] or not cells[1]:
                    raise ValueError("Malformed goal row.")
                _validate_player(cells[0], "goal")
                try:
                    minute = _minute(cells[1])
                except Exception as exc:
                    raise ValueError(f"Malformed goal minute: {cells[1]!r}") from exc
                events.append(_event(base, event_type="GOAL", side=side, player=cells[0], related=None, minute_raw=cells[1], source_section="A2", source_row_index=index, minute_parts=minute))
    sections = _sections(raw)
    for side_index, side in enumerate(("home", "away")):
        substitutions = _rows(sections[7][side_index])
        if len(substitutions) % 2:
            raise ValueError("Unpaired substitution row.")
        for index in range(0, len(substitutions), 2):
            out, incoming = substitutions[index:index + 2]
            if (out.get("change") != "\u25bd" or incoming.get("change") != "\u25b2" or incoming.get("time") or not out.get("time") or out["name"] == incoming["name"]):
                raise ValueError("Malformed substitution pair.")
            _validate_player(out["name"], "substitution")
            _validate_player(incoming["name"], "substitution")
            minute = _minute(out["time"])
            events.append(_event(base, event_type="SUBSTITUTION", side=side, player=out["name"], related=incoming["name"], minute_raw=out["time"], source_section="A7", source_row_index=index, minute_parts=minute))
    for number, event_type in ((8, "YELLOW_CARD"), (9, "RED_CARD")):
        fragments = _section_fragments(text, number)
        if len(fragments) not in (0, 2):
            raise ValueError(f"A{number} requires zero or two side sections.")
        for side_index, fragment in enumerate(fragments):
            if re.search(r"<tr\b", fragment) and not re.search(r'<td class="name">', fragment):
                raise ValueError(f"Malformed A{number} side section.")
            for index, row in enumerate(_rows(fragment)):
                if not row.get("name") or not row.get("time"):
                    raise ValueError(f"Malformed {event_type} row.")
                _validate_player(row["name"], event_type.lower())
                minute_parts, null_reason = _event_minute(
                    row["time"], source_section=f"A{number}")
                events.append(_event(
                    base, event_type=event_type, side=("home", "away")[side_index],
                    player=row["name"], related=None, minute_raw=row["time"],
                    source_section=f"A{number}", source_row_index=index,
                    minute_parts=minute_parts, null_reason=null_reason))
    for substitution in (e for e in events if e["event_type"] == "SUBSTITUTION"):
        for dismissal in (e for e in events if e["event_type"] == "RED_CARD"):
            if substitution["side"] == dismissal["side"] and substitution["player_name_raw"] == dismissal["player_name_raw"] and substitution["minute_raw"] == dismissal["minute_raw"]:
                raise ValueError("Same-minute substitution/red order is ambiguous.")
    if len({e["event_id"] for e in events}) != len(events):
        raise ValueError("Duplicate event_id within match.")
    for event in events:
        event["team_id"] = team_ids[event["team_side"]]
        event["team_name"] = team_names[event["team_side"]]
        event["side"] = event.pop("team_side")
    return sorted(events, key=lambda row: (row["minute_order_half"] if row["minute_order_half"] is not None else 9, row["minute_order_base"] if row["minute_order_base"] is not None else 999, row["minute_order_added"] if row["minute_order_added"] is not None else 0, row["source_section"], row["source_row_index"], row["event_id"]))

def _read_csv(path):
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise MatchEventError(f"Invalid CSV columns: {path}.")
            return list(reader)
    except OSError as exc:
        raise MatchEventError(f"Missing input CSV: {path}.") from exc

def _verified_raw(match_id, raw_dir):
    url = f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}"
    raw_path = Path(raw_dir) / f"{match_id}.html"
    metadata_path = Path(raw_dir) / f"{match_id}.metadata.json"
    try:
        raw = raw_path.read_bytes()
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MatchEventError(f"Missing or invalid SFMS02 cache for {match_id}.") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if (metadata.get("requested_url") != url or metadata.get("final_url") != url
            or metadata.get("status") != 200
            or str(metadata.get("match_id")) != str(match_id)
            or metadata.get("bytes") != len(raw)
            or metadata.get("sha256") != digest):
        raise MatchEventError(f"Invalid SFMS02 metadata/SHA-256 for {match_id}.")
    return raw, digest, url

def _validate_event(row, source_match_ids):
    required = ("event_id", "match_id", "match_date", "team_id", "team_name",
                "side", "event_type", "player_name_raw", "minute_raw",
                "source_section", "source", "source_url", "raw_sha256")
    if any(row.get(key) in (None, "") for key in required):
        raise MatchEventError(f"Blank required event field: {row.get('event_id')}.")
    if row["match_id"] not in source_match_ids or row["season"] not in EXPECTED:
        raise MatchEventError("Event escaped the frozen match/season scope.")
    if row["side"] not in {"home", "away"} or row["event_type"] not in EVENT_TYPES:
        raise MatchEventError("Invalid event side/type.")
    expected_section = {"GOAL": "A2", "SUBSTITUTION": "A7",
                        "YELLOW_CARD": "A8", "RED_CARD": "A9"}[row["event_type"]]
    if row["source_section"] != expected_section or row["source"] != SOURCE:
        raise MatchEventError("Event source section/provenance mismatch.")
    if "\ufffd" in row["player_name_raw"] or not re.fullmatch(r"[0-9a-f]{64}", row["raw_sha256"]):
        raise MatchEventError("Unsafe player name or raw SHA-256.")
    related = row.get("related_player_name_raw")
    if row["event_type"] == "SUBSTITUTION":
        if not related or "\ufffd" in related or related == row["player_name_raw"]:
            raise MatchEventError("Invalid substitution player pair.")
    elif related not in (None, ""):
        raise MatchEventError("Only substitutions may have a related player.")
    minute = row.get("minute_normalized")
    if minute is None:
        if row.get("null_reason") != "SOURCE_MINUTE_UNRESOLVED" or row["minute_raw"] != "***":
            raise MatchEventError("Unexplained unresolved event minute.")
    elif type(minute) is not int or not 1 <= minute <= 90 or row.get("null_reason") is not None:
        raise MatchEventError("Invalid normalized event minute.")

def _atomic_write_csv(path, rows):
    path = Path(path)
    if path.exists():
        raise MatchEventError(f"Output already exists; refusing overwrite: {path}.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        os.rename(temp, path)
    except Exception:
        if temp is not None:
            temp.unlink(missing_ok=True)
        raise

def _atomic_write_json(path, value):
    path = Path(path)
    if path.exists():
        raise MatchEventError(f"Summary already exists; refusing overwrite: {path}.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.rename(temp, path)
    except Exception:
        if temp is not None:
            temp.unlink(missing_ok=True)
        raise

def _materialize(*, expected_counts, matches_dir, stats_dir, raw_dir, output_path,
                 summary_path, team_master):
    if set(expected_counts) != set(range(min(expected_counts), max(expected_counts) + 1)):
        raise MatchEventError("Season scope must be contiguous.")
    all_rows, source_ids, season_counts = [], set(), {}
    type_rows, type_matches = Counter(), defaultdict(set)
    raw_rows = Counter()
    score = Counter()
    unresolved_minutes = 0
    for season, expected in expected_counts.items():
        matches = _read_csv(Path(matches_dir) / f"{season}_matches_probe.csv")
        stats = _read_csv(Path(stats_dir) / f"{season}_match_stats.csv")
        match_ids = [row.get("match_id", "") for row in matches]
        stats_ids = [row.get("match_id", "") for row in stats]
        if len(matches) != expected or len(stats) != expected:
            raise MatchEventError(f"Season {season} source count mismatch.")
        if len(set(match_ids)) != expected or len(set(stats_ids)) != expected:
            raise MatchEventError(f"Season {season} duplicate match ID.")
        if set(match_ids) != set(stats_ids):
            raise MatchEventError(f"Season {season} probe/stats ID sets differ.")
        by_stats = {row["match_id"]: row for row in stats}
        season_events = Counter()
        for match in sorted(matches, key=lambda row: (row["match_date"], row["match_id"])):
            mid = match["match_id"]
            if mid in source_ids:
                raise MatchEventError(f"Global duplicate match ID: {mid}.")
            source_ids.add(mid)
            if int(match.get("season", -1)) != season or date.fromisoformat(match["match_date"]).year != season:
                raise MatchEventError(f"Season/date mismatch for {mid}.")
            stat = by_stats[mid]
            if stat["home_team_id"] == stat["away_team_id"] or stat["home_team"] == stat["away_team"]:
                raise MatchEventError(f"Same home/away identity for {mid}.")
            for side in ("home", "away"):
                probe_id = team_master.resolve_team_id(
                    match[f"{side}_team"], source="jleague_data_site", on=match["match_date"])
                stats_id = team_master.resolve_team_id(
                    stat[f"{side}_team"], source="jleague_official", on=match["match_date"])
                if probe_id != stats_id or stats_id != stat[f"{side}_team_id"]:
                    raise MatchEventError(f"TeamMaster mismatch for {mid}/{side}.")
            raw, digest, url = _verified_raw(mid, raw_dir)
            if match.get("source_url") != url or stat.get("source_url") != url:
                raise MatchEventError(f"Source URL mismatch for {mid}.")
            try:
                events = parse_match_events(
                    raw, match_id=mid, match_date=match["match_date"], season=season,
                    team_ids={"home": stat["home_team_id"], "away": stat["away_team_id"]},
                    team_names={"home": stat["home_team"], "away": stat["away_team"]},
                    source_url=url, raw_sha256=digest)
            except Exception as exc:
                raise MatchEventError(
                    f"Parser failure: match_id={mid}, season={season}, reason={exc}") from exc
            goals = Counter(event["side"] for event in events if event["event_type"] == "GOAL")
            if goals["home"] != int(match["home_score"]) or goals["away"] != int(match["away_score"]):
                if mid not in SCORE_NOT_CHECKABLE:
                    score["mismatched"] += 1
                    raise MatchEventError(f"A2/official score mismatch for {mid}.")
                score["not_checkable"] += 1
            else:
                score["checked"] += 1
                score["matched"] += 1
            event_types = set()
            for event in events:
                _validate_event(event, source_ids)
                event_types.add(event["event_type"])
                type_rows[event["event_type"]] += 1
                type_matches[event["event_type"]].add(mid)
                season_events[event["event_type"]] += 1
                unresolved_minutes += int(event["minute_normalized"] is None)
                event["normalization_flags"] = ";".join(event["normalization_flags"])
                all_rows.append(event)
            raw_rows["A2"] += sum(event["event_type"] == "GOAL" for event in events)
            raw_rows["A7"] += 2 * sum(event["event_type"] == "SUBSTITUTION" for event in events)
            raw_rows["A8"] += sum(event["event_type"] == "YELLOW_CARD" for event in events)
            raw_rows["A9"] += sum(event["event_type"] == "RED_CARD" for event in events)
        season_counts[str(season)] = {
            "source_matches": expected, **{kind: season_events[kind] for kind in sorted(EVENT_TYPES)},
            "total_event_rows": sum(season_events.values()),
        }
    expected_total = sum(expected_counts.values())
    if len(source_ids) != expected_total:
        raise MatchEventError("Full source match count mismatch.")
    event_ids = [row["event_id"] for row in all_rows]
    if len(event_ids) != len(set(event_ids)):
        raise MatchEventError("Global event_id collision.")
    if raw_rows["A7"] != 2 * type_rows["SUBSTITUTION"]:
        raise MatchEventError("A7 raw/normalized 2:1 invariant failed.")
    all_rows.sort(key=lambda row: (
        row["match_date"], row["match_id"],
        row["minute_order_half"] if row["minute_order_half"] is not None else 9,
        row["minute_order_base"] if row["minute_order_base"] is not None else 999,
        row["minute_order_added"] if row["minute_order_added"] is not None else 0,
        row["source_section"], row["source_row_index"], row["event_id"]))
    output_path, summary_path = Path(output_path), Path(summary_path)
    if output_path.exists() or summary_path.exists():
        raise MatchEventError("Refusing to overwrite an existing materialization artifact.")
    _atomic_write_csv(output_path, all_rows)
    output_sha = hashlib.sha256(output_path.read_bytes()).hexdigest()
    summary = {
        "status": "MATERIALIZED_AND_VALIDATED", "source_matches": expected_total,
        "total_event_rows": len(all_rows), "output_path": str(output_path),
        "output_sha256": output_sha, "raw_source_rows": dict(raw_rows),
        "event_types": {kind: {"rows": type_rows[kind],
            "matches_with_event": len(type_matches[kind]),
            "matches_with_zero_events": expected_total - len(type_matches[kind])}
            for kind in sorted(EVENT_TYPES)},
        "matches_with_any_event": len({row["match_id"] for row in all_rows}),
        "zero_event_matches": expected_total - len({row["match_id"] for row in all_rows}),
        "season_counts": season_counts, "unresolved_minute_rows": unresolved_minutes,
        "team_identity_unresolved": 0, "source_missing": 0,
        "malformed_unresolved": 0, "event_id_collisions": 0,
        "score_diagnostic": {
            "checked": score["checked"], "matched": score["matched"],
            "mismatched": score["mismatched"],
            "not_checkable": score["not_checkable"],
            "not_checkable_matches": {
                mid: reason for mid, reason in SCORE_NOT_CHECKABLE.items() if mid in source_ids},
        },
        "a7_raw_to_normalized_ratio": 2,
        "external_http_requests": 0,
    }
    try:
        _atomic_write_json(summary_path, summary)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return summary

def collect_history(*, matches_dir=MATCH_DIR, stats_dir=STATS_DIR, raw_dir=RAW_DIR,
                    output_path=OUTPUT, summary_path=SUMMARY, team_master=None):
    """Materialize the frozen 2015-2024 ordinary-J1 event dataset offline."""
    if sum(EXPECTED.values()) != 3208 or min(EXPECTED) != 2015 or max(EXPECTED) != 2024:
        raise MatchEventError("Frozen ordinary-J1 scope is not 2015-2024 / 3,208 matches.")
    return _materialize(
        expected_counts=EXPECTED, matches_dir=matches_dir, stats_dir=stats_dir,
        raw_dir=raw_dir, output_path=output_path, summary_path=summary_path,
        team_master=team_master or load_team_master())

if __name__ == "__main__":
    print(json.dumps(collect_history(), ensure_ascii=False, indent=2))
