"""Parser-only contract for cached SFMS02 match events."""
from __future__ import annotations
import hashlib
import json
import re
from html import unescape
from src.collect.sfms02_player_minutes import _rows, _sections, normalize_minute

EVENT_TYPES = {"GOAL", "SUBSTITUTION", "YELLOW_CARD", "RED_CARD"}
SOURCE = "jleague_data_site_sfms02"

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

def _event(base, *, event_type, side, player, related, minute_raw, source_section, source_row_index, flags=None, minute_parts=None):
    if event_type not in EVENT_TYPES or side not in {"home", "away"}:
        raise ValueError("Invalid event type or side.")
    row = dict(base, team_side=side, event_type=event_type, player_name_raw=player,
               related_player_name_raw=related, minute_raw=minute_raw, minute_normalized=None,
               minute_order_half=None, minute_order_base=None, minute_order_added=None,
               normalization_flags=sorted(flags or []), source_section=source_section,
               source_row_index=source_row_index, null_reason=None)
    if minute_parts is not None:
        minute, order, flag = minute_parts
        row.update(minute_normalized=minute, minute_order_half=order[0], minute_order_base=order[1], minute_order_added=order[2])
        if flag:
            row["normalization_flags"] = sorted(set(row["normalization_flags"]) | {flag})
    identity = {key: row[key] for key in ("match_id", "team_side", "source_section", "source_row_index", "event_type")}
    row["event_id"] = _digest(identity)
    return row

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
            for index, cells in enumerate(_rows_from_fragment(table.group(1))):
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
                events.append(_event(base, event_type=event_type, side=("home", "away")[side_index], player=row["name"], related=None, minute_raw=row["time"], source_section=f"A{number}", source_row_index=index, minute_parts=_minute(row["time"])))
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
