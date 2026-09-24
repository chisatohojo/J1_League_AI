"""Parser-only contract for ordinary J1 SFMS02 match events.

This module never performs network access or writes a dataset.  It converts
one cached SFMS02 page into deterministic, match-local normalized events.
Player identity remains the exact source name; no longitudinal ID is made.
"""

from __future__ import annotations

import hashlib
import json
import re
from html import unescape

from src.collect.sfms02_player_minutes import _rows, _sections, normalize_minute


EVENT_TYPES = {"GOAL", "SUBSTITUTION", "YELLOW_CARD", "RED_CARD"}
SOURCE = "jleague_data_site_sfms02"


def _text(value: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _digest(value: dict) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _rows_from_fragment(fragment: str) -> list[list[str]]:
    result = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", fragment, re.S):
        cells = [_text(cell) for cell in re.findall(r"<td(?:\s[^>]*)?>(.*?)</td>", row, re.S)]
        if cells:
            result.append(cells)
    return result


def _section_fragments(text: str, number: int) -> list[str]:
    return re.findall(
        r"<!--\s*A" + str(number) + r"[^>]*Start\s*-->(.*?)<!--\s*A"
        + str(number) + r"[^>]*End\s*-->", text, re.S,
    )


def _minute(raw: str):
    value = raw.replace(" ", "")
    # Official pages are observed with both 45+1' and 45'+1' renderings.
    match = re.fullmatch(r"(\d+)(?:'\+|\+)(\d+)'", value)
    if match:
        base, added = int(match.group(1)), int(match.group(2))
        if base not in (45, 90) or added < 1:
            raise ValueError(f"Unsupported minute token: {raw!r}")
        return base, (0 if base == 45 else 1, base, added), None
    return normalize_minute(value)


def _event(base: dict, *, event_type: str, side: str, player: str,
           related: str | None, minute_raw: str | None, source_section: str,
           source_row_index: int, flags: list[str] | None = None,
           minute_parts: tuple[int, tuple[int, int, int], str | None] | None = None) -> dict:
    if event_type not in EVENT_TYPES or side not in {"home", "away"}:
        raise ValueError("Invalid event type or side.")
    row = dict(base, team_side=side, event_type=event_type,
               player_name_raw=player, related_player_name_raw=related,
               minute_raw=minute_raw, minute_normalized=None,
               minute_order_half=None, minute_order_base=None,
               minute_order_added=None, normalization_flags=sorted(flags or []),
               source_section=source_section, source_row_index=source_row_index,
               null_reason=None)
    if minute_parts is not None:
        minute, order, flag = minute_parts
        row.update(minute_normalized=minute, minute_order_half=order[0],
                   minute_order_base=order[1], minute_order_added=order[2])
        if flag:
            row["normalization_flags"] = sorted(set(row["normalization_flags"]) | {flag})
    identity = {key: row[key] for key in (
        "match_id", "team_side", "source_section", "source_row_index", "event_type",
    )}
    row["event_id"] = _digest(identity)
    return row


def parse_match_events(raw: bytes, *, match_id: str, match_date: str, season: int,
                       team_ids: dict[str, str], source_url: str,
                       raw_sha256: str | None = None) -> list[dict]:
    """Parse one cached SFMS02 page into normalized event rows.

    ``team_ids`` must contain exact ``home`` and ``away`` IDs.  A1 score is
    deliberately not reconstructed from events; it is only a separate audit.
    """
    if not match_id or set(team_ids) != {"home", "away"} or any(not team_ids[k] for k in team_ids):
        raise ValueError("Match identity and exact team IDs are required.")
    text = raw.decode("utf-8", errors="replace")
    base = {"match_id": str(match_id), "match_date": match_date, "season": season,
            "team_id": None, "team_name": None, "side": None, "source": SOURCE,
            "source_url": source_url, "raw_sha256": raw_sha256 or hashlib.sha256(raw).hexdigest()}
    events = []

    # A2: each side contains a nested table of [scorer, minute] rows.
    for side, marker in (("home", "left-area"), ("away", "right-area")):
        fragment = next((f for f in _section_fragments(text, 2) if f"class=\"{marker}\"" in f), "")
        table = re.search(rf'class="{marker}"\s*>\s*<table[^>]*>(.*?)</table>', fragment, re.S)
        for index, cells in enumerate(_rows_from_fragment(table.group(1) if table else "")):
            if len(cells) < 2 or not cells[0] or not cells[1]:
                raise ValueError("Malformed goal row.")
            try:
                    minute = _minute(cells[1])
            except Exception as exc:
                raise ValueError(f"Malformed goal minute: {cells[1]!r}") from exc
            events.append(_event(base, event_type="GOAL", side=side, player=cells[0],
                                 related=None, minute_raw=cells[1], source_section="A2",
                                 source_row_index=index, minute_parts=minute))

    sections = _sections(raw)
    for side_index, side in enumerate(("home", "away")):
        substitutions = _rows(sections[7][side_index])
        if len(substitutions) % 2:
            raise ValueError("Unpaired substitution row.")
        for index in range(0, len(substitutions), 2):
            out, incoming = substitutions[index:index + 2]
            if (out.get("change") not in {"▽", "笆ｽ", "�"}
                    or incoming.get("change") not in {"▲", "笆ｲ", "�"}
                    or incoming.get("time") or not out.get("time")
                    or out["name"] == incoming["name"]):
                raise ValueError("Malformed substitution pair.")
            minute = _minute(out["time"])
            events.append(_event(base, event_type="SUBSTITUTION", side=side,
                                 player=out["name"], related=incoming["name"],
                                 minute_raw=out["time"], source_section="A7",
                                 source_row_index=index, minute_parts=minute))

    for number, event_type in ((8, "YELLOW_CARD"), (9, "RED_CARD")):
        fragments = _section_fragments(text, number)
        for side_index, fragment in enumerate(fragments[:2]):
            side = ("home", "away")[side_index]
            for index, row in enumerate(_rows(fragment)):
                if not row.get("name") or not row.get("time"):
                    raise ValueError(f"Malformed {event_type} row.")
                minute = _minute(row["time"])
                events.append(_event(base, event_type=event_type, side=side,
                                     player=row["name"], related=None,
                                     minute_raw=row["time"], source_section=f"A{number}",
                                     source_row_index=index, minute_parts=minute))

    # A substitution and dismissal at the same displayed minute for the same
    # player has no source-established ordering. Preserve neither outcome by
    # silently choosing one; reject the ambiguous fixture like the minutes
    # parser does.
    for substitution in (event for event in events if event["event_type"] == "SUBSTITUTION"):
        for dismissal in (event for event in events if event["event_type"] == "RED_CARD"):
            if (substitution["side"] == dismissal["side"]
                    and substitution["player_name_raw"] == dismissal["player_name_raw"]
                    and substitution["minute_raw"] == dismissal["minute_raw"]):
                raise ValueError("Same-minute substitution/red order is ambiguous.")

    if len({event["event_id"] for event in events}) != len(events):
        raise ValueError("Duplicate event_id within match.")
    for event in events:
        event["team_id"] = team_ids[event["team_side"]]
        event["team_name"] = event["team_side"]
        event["side"] = event.pop("team_side")
    return sorted(events, key=lambda row: (
        row["minute_order_half"] if row["minute_order_half"] is not None else 9,
        row["minute_order_base"] if row["minute_order_base"] is not None else 999,
        row["minute_order_added"] if row["minute_order_added"] is not None else 0,
        row["source_section"], row["source_row_index"], row["event_id"],
    ))
