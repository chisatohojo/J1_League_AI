"""Identity-free previous-match A5 starter DF counts for ordinary J1.

The candidate is the count of explicit ``position == "DF"`` source rows in
the latest strictly earlier current-season match. It is not a formation or a
player-identity feature. No network access is performed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
from html import unescape
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping

import pandas as pd

from src.collect.teams import TeamMaster, load_team_master


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
STATS_DIR = ROOT / "data/processed/jleague_match_stats"
RAW_DIR = ROOT / "data/raw/jleague_match_stats"
OUTPUT_PATH = ROOT / "data/processed/features/2015_2024_j1_starter_df_features.csv"

EXPECTED = {
    **{year: 306 for year in range(2015, 2021)},
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
EXPECTED_SIDE_AVAILABLE = {
    **{year: (594, 18) for year in range(2015, 2021)},
    2021: (740, 20),
    2022: (594, 18),
    2023: (594, 18),
    2024: (740, 20),
}
EXPECTED_PAIR_AVAILABLE = {
    **{year: (297, 9) for year in range(2015, 2021)},
    2021: (370, 10),
    2022: (297, 9),
    2023: (297, 9),
    2024: (370, 10),
}
EXPECTED_PREVIOUS_DF = {
    2015: {3: 195, 4: 384, 5: 15},
    2016: {3: 147, 4: 446, 5: 1},
    2017: {2: 3, 3: 133, 4: 443, 5: 15},
    2018: {3: 166, 4: 405, 5: 23},
    2019: {3: 275, 4: 315, 5: 4},
    2020: {3: 193, 4: 383, 5: 18},
    2021: {2: 3, 3: 170, 4: 523, 5: 36, 6: 8},
    2022: {3: 167, 4: 393, 5: 34},
    2023: {2: 9, 3: 184, 4: 368, 5: 33},
    2024: {2: 3, 3: 239, 4: 464, 5: 33, 6: 1},
}
EXPECTED_CURRENT_DF = {2: 20, 3: 1928, 4: 4238, 5: 221, 6: 9}
EXPECTED_POSITION_TOTALS = {"GK": 6416, "DF": 23935, "MF": 27004, "FW": 13221}

OUTPUT_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
    "home_starter_df_available",
    "away_starter_df_available",
    "home_previous_match_id",
    "away_previous_match_id",
    "home_previous_match_date",
    "away_previous_match_date",
    "home_previous_match_starter_df_count",
    "away_previous_match_starter_df_count",
)
MATCH_COLUMNS = OUTPUT_COLUMNS[:5]
CURRENT_COLUMNS = (
    "match_id",
    "home_starter_df_count",
    "away_starter_df_count",
)
A5_FIELDS = ("position", "number", "name", "time")
POSITIONS = frozenset({"GK", "DF", "MF", "FW"})

_A5_SECTION = re.compile(
    r"<!--\s*A5[^>]*?Start\s*-->(.*?)<!--\s*A5[^>]*?End\s*-->", re.S
)
_TR = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
_TD = re.compile(r"<td\b([^>]*)>(.*?)</td>", re.S | re.I)
_CLASS = re.compile(r'\bclass\s*=\s*"([^"]+)"', re.I)
_TAG = re.compile(r"<[^>]+>")


class StarterDFError(ValueError):
    """Frozen source, identity, chronology, or output invariant failed."""


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or len(reader.fieldnames) != len(
                set(reader.fieldnames)
            ):
                raise StarterDFError(f"Invalid CSV columns: {path}")
            return list(reader)
    except OSError as exc:
        raise StarterDFError(f"Missing input: {path}") from exc


def _text(value, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or "\ufffd" in value
        or any(ord(char) < 32 for char in value)
    ):
        raise StarterDFError(f"Invalid {label}: {value!r}")
    return value


def _date(value, label: str = "match_date") -> date:
    try:
        return date.fromisoformat(_text(value, label))
    except ValueError as exc:
        raise StarterDFError(f"Invalid {label}: {value!r}") from exc


def _integer(value, label: str) -> int:
    if isinstance(value, bool):
        raise StarterDFError(f"Invalid integer {label}: {value!r}")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise StarterDFError(f"Invalid integer {label}: {value!r}") from exc
    if isinstance(value, float) and value != number:
        raise StarterDFError(f"Invalid integer {label}: {value!r}")
    if isinstance(value, str) and str(number) != value:
        raise StarterDFError(f"Invalid integer {label}: {value!r}")
    return number


def _html_text(value: str) -> str:
    return unescape(_TAG.sub("", value)).strip()


def _expected_url(match_id: str) -> str:
    return f"https://data.j-league.or.jp/SFMS02/?match_card_id={match_id}"


def _load_metadata(path: Path) -> dict:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StarterDFError(f"Duplicate metadata key {key!r}: {path}")
            result[key] = value
        return result

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise StarterDFError(f"Invalid metadata JSON: {path}") from exc


def _validate_raw_metadata(raw: bytes, metadata: Mapping, match_id: str) -> None:
    """Reconcile one cached HTML byte string with its metadata."""
    expected_url = _expected_url(match_id)
    digest = hashlib.sha256(raw).hexdigest()
    expected = {
        "requested_url": expected_url,
        "final_url": expected_url,
        "status": 200,
        "match_id": match_id,
        "bytes": len(raw),
        "sha256": digest,
    }
    observed = {key: metadata.get(key) for key in expected}
    if observed != expected:
        raise StarterDFError(
            f"Raw metadata mismatch for {match_id}: {observed} != {expected}"
        )


def _parse_a5(raw: bytes, *, match_id: str) -> tuple[tuple[int, int], Counter]:
    """Return home/away DF counts after validating the exact A5 contract."""
    start = raw.find(b"<!-- A5")
    stop = raw.find(b"<!-- A6", start)
    if start < 0 or stop <= start:
        raise StarterDFError(f"Missing A5/A6 source boundaries: {match_id}")
    html = raw[start:stop].decode("utf-8", errors="replace")
    sections = _A5_SECTION.findall(html)
    if len(sections) != 2:
        raise StarterDFError(
            f"Expected exactly two A5 side sections for {match_id}, got {len(sections)}"
        )

    df_counts = []
    position_totals = Counter()
    for side, fragment in zip(("home", "away"), sections):
        raw_rows = _TR.findall(fragment)
        rows = []
        for row_number, row_html in enumerate(raw_rows, 1):
            cells = []
            for attributes, body in _TD.findall(row_html):
                classes = _CLASS.findall(attributes)
                if len(classes) != 1:
                    raise StarterDFError(
                        f"A5 row has a missing/duplicate class: {match_id}/{side}/{row_number}"
                    )
                cells.append((classes[0], _html_text(body)))
            # The source wraps the player table in one layout tr with no td
            # cells. It is not a roster row; any tr with cells remains subject
            # to the exact frozen player-row shape below.
            if not cells:
                continue
            shape = tuple(field for field, _ in cells)
            if shape != A5_FIELDS:
                raise StarterDFError(
                    f"A5 row shape mismatch: {match_id}/{side}/{row_number}: {shape}"
                )
            values = dict(cells)
            if values["position"] not in POSITIONS:
                raise StarterDFError(
                    f"Invalid A5 position: {match_id}/{side}/{row_number}"
                )
            if not values["number"]:
                raise StarterDFError(
                    f"Blank A5 number: {match_id}/{side}/{row_number}"
                )
            if not values["name"] or "\ufffd" in values["name"]:
                raise StarterDFError(
                    f"Malformed A5 name: {match_id}/{side}/{row_number}"
                )
            if values["time"]:
                raise StarterDFError(
                    f"Nonempty A5 time: {match_id}/{side}/{row_number}"
                )
            rows.append(values)

        if len(rows) != 11:
            raise StarterDFError(
                f"A5 {side} side must contain exactly 11 rows: {match_id}"
            )

        names = [row["name"] for row in rows]
        if len(names) != len(set(names)):
            raise StarterDFError(
                f"Duplicate exact A5 player name within team-match: {match_id}/{side}"
            )
        positions = Counter(row["position"] for row in rows)
        if positions["GK"] != 1:
            raise StarterDFError(
                f"A5 side must contain exactly one GK: {match_id}/{side}"
            )
        position_totals.update(positions)
        df_counts.append(positions["DF"])
    return (df_counts[0], df_counts[1]), position_totals


def load_j1_matches(
    *,
    j1_dir: str | Path = J1_DIR,
    stats_dir: str | Path = STATS_DIR,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Load and exactly reconcile the frozen target universe by match ID."""
    master = team_master or load_team_master()
    output = []
    global_ids = set()
    for season, expected_count in EXPECTED.items():
        probes = _read_csv(Path(j1_dir) / f"{season}_matches_probe.csv")
        stats = _read_csv(Path(stats_dir) / f"{season}_match_stats.csv")
        if len(probes) != expected_count or len(stats) != expected_count:
            raise StarterDFError(
                f"{season} target count mismatch: {len(probes)}/{len(stats)}"
            )
        required_probe = {
            "match_id",
            "match_date",
            "season",
            "home_team",
            "away_team",
            "source_url",
        }
        required_stats = {
            "match_id",
            "home_team_id",
            "away_team_id",
            "source_url",
        }
        if any(required_probe - set(row) for row in probes) or any(
            required_stats - set(row) for row in stats
        ):
            raise StarterDFError(f"Missing target identity fields in {season}")
        probe_by_id = {}
        stats_by_id = {}
        for row in probes:
            mid = _text(row["match_id"], "match_id")
            if mid in probe_by_id or mid in global_ids:
                raise StarterDFError(f"Duplicate target match_id: {mid}")
            probe_by_id[mid] = row
        for row in stats:
            mid = _text(row["match_id"], "stats match_id")
            if mid in stats_by_id:
                raise StarterDFError(f"Duplicate match-stats match_id: {mid}")
            stats_by_id[mid] = row
        if set(probe_by_id) != set(stats_by_id):
            raise StarterDFError(f"Probe/match-stats match-ID sets differ in {season}")

        for mid, probe in probe_by_id.items():
            day = _date(probe["match_date"])
            if _integer(probe["season"], "season") != season or day.year != season:
                raise StarterDFError(f"Target season/date mismatch: {mid}")
            expected_url = _expected_url(mid)
            stat = stats_by_id[mid]
            if probe["source_url"] != expected_url or stat["source_url"] != expected_url:
                raise StarterDFError(f"Target source URL mismatch: {mid}")
            try:
                resolved_home = master.resolve_team_id(
                    probe["home_team"], source="jleague_data_site", on=day
                )
                resolved_away = master.resolve_team_id(
                    probe["away_team"], source="jleague_data_site", on=day
                )
            except Exception as exc:
                raise StarterDFError(f"TeamMaster resolution failed: {mid}") from exc
            home = _text(stat["home_team_id"], "home_team_id")
            away = _text(stat["away_team_id"], "away_team_id")
            if (home, away) != (resolved_home, resolved_away):
                raise StarterDFError(f"Probe/match-stats team identity mismatch: {mid}")
            if home == away:
                raise StarterDFError(f"Home and away team IDs must differ: {mid}")
            output.append(
                {
                    "match_id": mid,
                    "match_date": day.isoformat(),
                    "season": season,
                    "home_team_id": home,
                    "away_team_id": away,
                }
            )
            global_ids.add(mid)

    result = pd.DataFrame(output, columns=MATCH_COLUMNS)
    normalized = _normalize_matches(result)
    if len(normalized) != 3208 or set(normalized.season) != set(EXPECTED):
        raise StarterDFError("Target universe must be exactly 3,208 matches in 2015-2024")
    return normalized


def _normalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(matches, pd.DataFrame) or matches.columns.has_duplicates:
        raise StarterDFError("Matches must be a DataFrame with unique columns")
    if set(MATCH_COLUMNS) - set(matches.columns):
        raise StarterDFError("Match frame lacks frozen identity fields")
    records = []
    seen_ids = set()
    seen_team_dates = set()
    for raw in matches.loc[:, MATCH_COLUMNS].to_dict("records"):
        mid = _text(raw["match_id"], "match_id")
        if mid in seen_ids:
            raise StarterDFError(f"Duplicate target match_id: {mid}")
        day = raw["match_date"] if type(raw["match_date"]) is date else _date(
            raw["match_date"]
        )
        season = _integer(raw["season"], "season")
        if season not in EXPECTED or day.year != season:
            raise StarterDFError(f"Target season/date mismatch: {mid}")
        home = _text(raw["home_team_id"], "home_team_id")
        away = _text(raw["away_team_id"], "away_team_id")
        if home == away:
            raise StarterDFError(f"Target home and away IDs must differ: {mid}")
        for team in (home, away):
            key = (day, team)
            if key in seen_team_dates:
                raise StarterDFError(
                    f"Team appears twice on one target date: {day}/{team}"
                )
            seen_team_dates.add(key)
        seen_ids.add(mid)
        records.append(
            {
                "match_id": mid,
                "match_date": day,
                "season": season,
                "home_team_id": home,
                "away_team_id": away,
            }
        )
    return pd.DataFrame(records, columns=MATCH_COLUMNS)


def load_validated_a5(
    matches: pd.DataFrame, *, raw_dir: str | Path = RAW_DIR
) -> tuple[pd.DataFrame, dict]:
    """Validate every scoped raw A5 and return only per-side DF counts."""
    normalized = _normalize_matches(matches)
    if len(normalized) != 3208:
        raise StarterDFError("Full raw validation requires exactly 3,208 targets")
    position_totals = Counter()
    current_distribution = Counter()
    records = []
    source = Path(raw_dir)
    for row in normalized.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).itertuples(index=False):
        raw_path = source / f"{row.match_id}.html"
        metadata_path = source / f"{row.match_id}.metadata.json"
        try:
            raw = raw_path.read_bytes()
        except OSError as exc:
            raise StarterDFError(f"Missing raw HTML: {raw_path}") from exc
        metadata = _load_metadata(metadata_path)
        _validate_raw_metadata(raw, metadata, row.match_id)
        (home_df, away_df), positions = _parse_a5(raw, match_id=row.match_id)
        position_totals.update(positions)
        current_distribution.update((home_df, away_df))
        records.append(
            {
                "match_id": row.match_id,
                "home_starter_df_count": home_df,
                "away_starter_df_count": away_df,
            }
        )

    audit = {
        "matches": len(normalized),
        "team_match_sides": 2 * len(normalized),
        "a5_side_sections": 2 * len(normalized),
        "a5_rows": 22 * len(normalized),
        "row_shape_failures": 0,
        "malformed_names": 0,
        "nonempty_time_cells": 0,
        "invalid_position_rows": 0,
        "sides_not_11_rows": 0,
        "sides_not_exactly_one_gk": 0,
        "metadata_failures": 0,
        "position_totals": dict(sorted(position_totals.items())),
        "current_source_df_distribution": dict(sorted(current_distribution.items())),
    }
    expected = {
        "matches": 3208,
        "team_match_sides": 6416,
        "a5_side_sections": 6416,
        "a5_rows": 70576,
        "row_shape_failures": 0,
        "malformed_names": 0,
        "nonempty_time_cells": 0,
        "invalid_position_rows": 0,
        "sides_not_11_rows": 0,
        "sides_not_exactly_one_gk": 0,
        "metadata_failures": 0,
        "position_totals": dict(sorted(EXPECTED_POSITION_TOTALS.items())),
        "current_source_df_distribution": dict(sorted(EXPECTED_CURRENT_DF.items())),
    }
    if audit != expected:
        raise StarterDFError(f"Frozen A5 source audit mismatch: {audit} != {expected}")
    return pd.DataFrame(records, columns=CURRENT_COLUMNS), audit


def _normalize_current_counts(
    counts: pd.DataFrame, matches: pd.DataFrame
) -> pd.DataFrame:
    if not isinstance(counts, pd.DataFrame) or counts.columns.has_duplicates:
        raise StarterDFError("Current DF counts must have unique columns")
    if set(CURRENT_COLUMNS) - set(counts.columns):
        raise StarterDFError("Current DF count frame lacks frozen columns")
    records = []
    seen = set()
    for raw in counts.loc[:, CURRENT_COLUMNS].to_dict("records"):
        mid = _text(raw["match_id"], "DF-count match_id")
        if mid in seen:
            raise StarterDFError(f"Duplicate current DF count match_id: {mid}")
        values = {"match_id": mid}
        for side in ("home", "away"):
            field = f"{side}_starter_df_count"
            value = _integer(raw[field], field)
            if not 2 <= value <= 6:
                raise StarterDFError(f"Current A5 DF count outside frozen domain: {value}")
            values[field] = value
        records.append(values)
        seen.add(mid)
    match_ids = set(matches.match_id)
    if seen != match_ids:
        raise StarterDFError("Current A5 and target match-ID sets differ")
    return pd.DataFrame(records, columns=CURRENT_COLUMNS)


def build_starter_df_features(
    matches: pd.DataFrame, current_counts: pd.DataFrame
) -> pd.DataFrame:
    """Build replacement-only prior-match features with date batching."""
    normalized_matches = _normalize_matches(matches)
    normalized_counts = _normalize_current_counts(current_counts, normalized_matches)
    current = normalized_counts.set_index("match_id").to_dict("index")
    ordered = normalized_matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)

    output = []
    for season, season_rows in ordered.groupby("season", sort=True):
        history: dict[str, tuple[str, date, int]] = {}
        for _, day_rows in season_rows.groupby("match_date", sort=True):
            day_rows = day_rows.sort_values("match_id", kind="mergesort")
            for row in day_rows.itertuples(index=False):
                values = {
                    "match_id": row.match_id,
                    "match_date": row.match_date.isoformat(),
                    "season": int(season),
                    "home_team_id": row.home_team_id,
                    "away_team_id": row.away_team_id,
                }
                for side in ("home", "away"):
                    team = getattr(row, f"{side}_team_id")
                    state = history.get(team)
                    available = state is not None
                    values[f"{side}_starter_df_available"] = available
                    values[f"{side}_previous_match_id"] = state[0] if state else None
                    values[f"{side}_previous_match_date"] = (
                        state[1].isoformat() if state else None
                    )
                    values[f"{side}_previous_match_starter_df_count"] = (
                        state[2] if state else None
                    )
                output.append(values)

            # The date becomes history only after every target has been emitted.
            for row in day_rows.itertuples(index=False):
                for side in ("home", "away"):
                    team = getattr(row, f"{side}_team_id")
                    history[team] = (
                        row.match_id,
                        row.match_date,
                        int(current[row.match_id][f"{side}_starter_df_count"]),
                    )

    result = pd.DataFrame(output, columns=OUTPUT_COLUMNS)
    for field in (
        "home_previous_match_starter_df_count",
        "away_previous_match_starter_df_count",
    ):
        result[field] = result[field].astype("Int64")
    _validate_result(
        result, matches=ordered, current_counts=normalized_counts
    )
    return result


def _validate_result(
    result: pd.DataFrame, *, matches: pd.DataFrame, current_counts: pd.DataFrame
) -> None:
    """Validate exact identity, chronology, latest-match state, and nulls."""
    if tuple(result.columns) != OUTPUT_COLUMNS:
        raise StarterDFError("Output schema differs from frozen 13-column contract")
    normalized_matches = _normalize_matches(matches)
    normalized_counts = _normalize_current_counts(current_counts, normalized_matches)
    expected = normalized_matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if len(result) != len(expected) or result.match_id.duplicated().any():
        raise StarterDFError("Output must contain one row per unique target match")
    if result.match_id.tolist() != expected.match_id.tolist():
        raise StarterDFError("Output order must be match_date, match_id")
    expected_identity = expected.copy()
    expected_identity["match_date"] = expected_identity.match_date.map(date.isoformat)
    try:
        pd.testing.assert_frame_equal(
            result.loc[:, MATCH_COLUMNS].reset_index(drop=True),
            expected_identity.loc[:, MATCH_COLUMNS].reset_index(drop=True),
            check_dtype=False,
            obj="starter DF output identity",
        )
    except AssertionError as exc:
        raise StarterDFError("Output identity differs from target universe") from exc

    current = normalized_counts.set_index("match_id").to_dict("index")
    actual = result.set_index("match_id")
    history: dict[tuple[int, str], tuple[str, date, int]] = {}
    for (season, day), day_rows in expected.groupby(
        ["season", "match_date"], sort=True
    ):
        day_rows = day_rows.sort_values("match_id", kind="mergesort")
        for match in day_rows.itertuples(index=False):
            output_row = actual.loc[match.match_id]
            for side in ("home", "away"):
                team = getattr(match, f"{side}_team_id")
                state = history.get((int(season), team))
                available_field = f"{side}_starter_df_available"
                id_field = f"{side}_previous_match_id"
                date_field = f"{side}_previous_match_date"
                count_field = f"{side}_previous_match_starter_df_count"
                if output_row[available_field] not in (True, False):
                    raise StarterDFError("Availability must be logical boolean")
                if state is None:
                    if output_row[available_field] is not False and bool(
                        output_row[available_field]
                    ):
                        raise StarterDFError("Unavailable side marked available")
                    if (
                        pd.notna(output_row[id_field])
                        or pd.notna(output_row[date_field])
                        or pd.notna(output_row[count_field])
                    ):
                        raise StarterDFError("Unavailable side has non-null audit state")
                else:
                    previous_id, previous_date, previous_count = state
                    if not bool(output_row[available_field]):
                        raise StarterDFError("Available side marked unavailable")
                    if (
                        output_row[id_field] != previous_id
                        or output_row[date_field] != previous_date.isoformat()
                        or int(output_row[count_field]) != previous_count
                    ):
                        raise StarterDFError(
                            "Available state is not the exact latest previous match"
                        )
                    if previous_date >= day or not 2 <= previous_count <= 6:
                        raise StarterDFError("Invalid strictly-prior DF state")
        for match in day_rows.itertuples(index=False):
            for side in ("home", "away"):
                team = getattr(match, f"{side}_team_id")
                history[(int(season), team)] = (
                    match.match_id,
                    match.match_date,
                    int(current[match.match_id][f"{side}_starter_df_count"]),
                )


def availability_summary(result: pd.DataFrame, *, frozen: bool = False) -> dict:
    """Return actual side/pair availability and optionally assert references."""
    summary = {}
    for season, rows in result.groupby("season", sort=True):
        year = int(season)
        home = rows.home_starter_df_available.astype(bool)
        away = rows.away_starter_df_available.astype(bool)
        pair = home & away
        values = {
            "total_matches": len(rows),
            "home_available": int(home.sum()),
            "away_available": int(away.sum()),
            "side_available": int(home.sum() + away.sum()),
            "side_unavailable": int((~home).sum() + (~away).sum()),
            "pair_available": int(pair.sum()),
            "pair_unavailable": int((~pair).sum()),
            "home_only_available": int((home & ~away).sum()),
            "away_only_available": int((~home & away).sum()),
            "both_unavailable": int((~home & ~away).sum()),
        }
        if frozen:
            side_available, side_unavailable = EXPECTED_SIDE_AVAILABLE[year]
            pair_available, pair_unavailable = EXPECTED_PAIR_AVAILABLE[year]
            expected = {
                "total_matches": EXPECTED[year],
                "home_available": pair_available,
                "away_available": pair_available,
                "side_available": side_available,
                "side_unavailable": side_unavailable,
                "pair_available": pair_available,
                "pair_unavailable": pair_unavailable,
                "home_only_available": 0,
                "away_only_available": 0,
                "both_unavailable": pair_unavailable,
            }
            if values != expected:
                raise StarterDFError(
                    f"Frozen availability mismatch for {year}: {values} != {expected}"
                )
        summary[str(year)] = values
    if frozen:
        side_available = sum(v["side_available"] for v in summary.values())
        pair_available = sum(v["pair_available"] for v in summary.values())
        home_only = sum(v["home_only_available"] for v in summary.values())
        away_only = sum(v["away_only_available"] for v in summary.values())
        both_unavailable = sum(v["both_unavailable"] for v in summary.values())
        if (
            side_available != 6232
            or 2 * len(result) - side_available != 184
            or pair_available != 3116
            or len(result) - pair_available != 92
            or (home_only, away_only, both_unavailable) != (0, 0, 92)
        ):
            raise StarterDFError("Global frozen availability mismatch")
    return summary


def previous_df_distribution(result: pd.DataFrame, *, frozen: bool = False) -> dict:
    """Return actual previous-match candidate distributions by season/global."""
    by_season = {}
    global_counts = Counter()
    for season, rows in result.groupby("season", sort=True):
        counts = Counter()
        for side in ("home", "away"):
            values = rows[f"{side}_previous_match_starter_df_count"].dropna()
            counts.update(int(value) for value in values)
        year = int(season)
        observed = dict(sorted(counts.items()))
        if frozen and observed != EXPECTED_PREVIOUS_DF[year]:
            raise StarterDFError(
                f"Frozen previous-match DF distribution mismatch for {year}: {observed}"
            )
        by_season[str(year)] = observed
        global_counts.update(counts)
    observed_global = dict(sorted(global_counts.items()))
    expected_global = dict(
        sorted(sum((Counter(values) for values in EXPECTED_PREVIOUS_DF.values()), Counter()).items())
    )
    if frozen and observed_global != expected_global:
        raise StarterDFError("Global previous-match DF distribution mismatch")
    if frozen and sum(global_counts.values()) != 6232:
        raise StarterDFError("Available previous-match DF total must be 6,232")
    return {"by_season": by_season, "global": observed_global}


def _csv_bytes(result: pd.DataFrame) -> bytes:
    return result.to_csv(index=False, lineterminator="\n", na_rep="").encode("utf-8")


def materialization_summary(
    result: pd.DataFrame, *, source_audit: dict, deterministic_rebuild: str
) -> dict:
    availability = availability_summary(result, frozen=True)
    distributions = previous_df_distribution(result, frozen=True)
    return {
        "status": "READY_FOR_STARTER_DF_EVALUATION_FREEZE",
        "source": source_audit,
        "output_rows": len(result),
        "unique_match_ids": int(result.match_id.nunique()),
        "exact_schema": tuple(result.columns) == OUTPUT_COLUMNS,
        "team_side_available": 6232,
        "team_side_unavailable": 184,
        "pair_available": 3116,
        "pair_unavailable": 92,
        "home_only_available": 0,
        "away_only_available": 0,
        "both_unavailable": 92,
        "partial_invalid_rows": 0,
        "invariant_failures": 0,
        "target_own_exclusion": "PASS",
        "same_date_batching": "PASS",
        "season_reset": "PASS",
        "previous_match_replacement": "PASS",
        "identity_free_contract": "PASS",
        "availability_by_season": availability,
        "previous_match_df_distribution": distributions,
        "deterministic_rebuild": deterministic_rebuild,
    }


def _write_once(result: pd.DataFrame, output_path: str | Path) -> str:
    output = Path(output_path)
    if output.exists():
        raise StarterDFError(f"Output already exists; refusing overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    content = _csv_bytes(result)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb",
            dir=output.parent,
            prefix=output.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.rename(temporary, output)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    if digest != hashlib.sha256(content).hexdigest():
        raise StarterDFError("Written output SHA-256 differs from generated bytes")
    return digest


def materialize_starter_df_features(
    *,
    j1_dir: str | Path = J1_DIR,
    stats_dir: str | Path = STATS_DIR,
    raw_dir: str | Path = RAW_DIR,
    output_path: str | Path = OUTPUT_PATH,
) -> tuple[pd.DataFrame, dict]:
    """Validate all frozen sources and atomically publish the feature CSV once."""
    matches = load_j1_matches(j1_dir=j1_dir, stats_dir=stats_dir)
    current_counts, source_audit = load_validated_a5(matches, raw_dir=raw_dir)
    result = build_starter_df_features(matches, current_counts)
    availability_summary(result, frozen=True)
    previous_df_distribution(result, frozen=True)

    rebuilt = build_starter_df_features(
        matches.iloc[::-1].reset_index(drop=True),
        current_counts.iloc[::-1].reset_index(drop=True),
    )
    if _csv_bytes(result) != _csv_bytes(rebuilt):
        raise StarterDFError("Rebuild is not byte-identical")
    summary = materialization_summary(
        result, source_audit=source_audit, deterministic_rebuild="PASS"
    )
    digest = _write_once(result, output_path)
    summary["output"] = str(Path(output_path))
    summary["output_sha256"] = digest
    return result, summary


if __name__ == "__main__":
    _, audit = materialize_starter_df_features()
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
