"""Leakage-safe current-season ordinary-J1 substitution timing features."""

from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import pandas as pd

from src.collect.teams import load_team_master


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
EVENT_PATH = ROOT / "data/processed/sfms02_match_events/2015_2024_j1_match_events.csv"
EVENT_SUMMARY_PATH = (
    ROOT
    / "data/processed/sfms02_match_events/2015_2024_j1_match_events.validation.json"
)
OUTPUT_PATH = (
    ROOT / "data/processed/features/2015_2024_j1_substitution_timing_features.csv"
)
SOURCE_SHA256 = "6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131"
EXPECTED = {
    **{year: 306 for year in range(2015, 2021)},
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
EXPECTED_PAIR_AVAILABLE = {
    **{year: 297 for year in range(2015, 2021)},
    2021: 370,
    2022: 297,
    2023: 297,
    2024: 370,
}
OUTPUT_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
    "home_substitution_timing_available",
    "away_substitution_timing_available",
    "home_prior_substitution_events",
    "away_prior_substitution_events",
    "home_prior_substitution_minute_normalized_sum",
    "away_prior_substitution_minute_normalized_sum",
    "home_mean_substitution_minute_normalized_prior",
    "away_mean_substitution_minute_normalized_prior",
)


class SubstitutionTimingError(ValueError):
    """Invalid source identity, chronology, timing, or feature state."""


def _read_csv(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or len(reader.fieldnames) != len(
                set(reader.fieldnames)
            ):
                raise SubstitutionTimingError(f"Invalid CSV columns: {path}")
            return list(reader)
    except OSError as exc:
        raise SubstitutionTimingError(f"Missing input: {path}") from exc


def _validate_source_sha(
    path: str | Path, *, expected_sha256: str = SOURCE_SHA256
) -> str:
    source = Path(path)
    try:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as exc:
        raise SubstitutionTimingError(f"Missing event artifact: {source}") from exc
    if digest != expected_sha256:
        raise SubstitutionTimingError(
            f"Event artifact SHA-256 mismatch: {digest} != {expected_sha256}"
        )
    return digest


def _load_event_metadata(path: str | Path = EVENT_SUMMARY_PATH) -> dict:
    try:
        metadata = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SubstitutionTimingError(f"Invalid event validation metadata: {path}") from exc
    try:
        raw_a7 = int(metadata["raw_source_rows"]["A7"])
        normalized = int(metadata["event_types"]["SUBSTITUTION"]["rows"])
        output_sha = str(metadata["output_sha256"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SubstitutionTimingError("Event metadata lacks A7 reconciliation") from exc
    if output_sha != SOURCE_SHA256:
        raise SubstitutionTimingError("Event metadata source SHA-256 mismatch")
    if raw_a7 != 47276 or normalized != 23638 or raw_a7 != 2 * normalized:
        raise SubstitutionTimingError("Raw A7/normalized SUB reconciliation mismatch")
    return metadata


def load_j1_matches(*, j1_dir: str | Path = J1_DIR) -> pd.DataFrame:
    """Load and resolve the frozen 2015-2024 ordinary-J1 target universe."""
    master = load_team_master()
    frames = []
    for season, expected in EXPECTED.items():
        rows = _read_csv(Path(j1_dir) / f"{season}_matches_probe.csv")
        if len(rows) != expected:
            raise SubstitutionTimingError(
                f"{season} expected {expected} matches, got {len(rows)}"
            )
        frame = pd.DataFrame(rows)
        required = {"match_id", "season", "match_date", "home_team", "away_team"}
        if required - set(frame.columns) or frame.match_id.duplicated().any():
            raise SubstitutionTimingError(
                f"Invalid J1 identity columns for {season}"
            )
        frame["match_id"] = frame.match_id.astype(str)
        frame["season"] = pd.to_numeric(frame.season, errors="raise").astype(int)
        if set(frame.season) != {season}:
            raise SubstitutionTimingError(f"Season mismatch in {season}")
        frame["match_date"] = pd.to_datetime(
            frame.match_date, format="%Y-%m-%d", errors="raise"
        ).dt.date
        if any(day.year != season for day in frame.match_date):
            raise SubstitutionTimingError(f"Date escaped season {season}")
        try:
            frame["home_team_id"] = [
                master.resolve_team_id(name, source="jleague_data_site", on=day)
                for name, day in zip(frame.home_team, frame.match_date)
            ]
            frame["away_team_id"] = [
                master.resolve_team_id(name, source="jleague_data_site", on=day)
                for name, day in zip(frame.away_team, frame.match_date)
            ]
        except Exception as exc:
            raise SubstitutionTimingError(
                f"J1 TeamMaster resolution failed for {season}"
            ) from exc
        if (frame.home_team_id == frame.away_team_id).any():
            raise SubstitutionTimingError(
                f"Same home/away team identity in {season}"
            )
        frames.append(frame.loc[:, OUTPUT_COLUMNS[:5]])
    result = pd.concat(frames, ignore_index=True)
    if len(result) != 3208 or result.match_id.duplicated().any():
        raise SubstitutionTimingError(
            "J1 target universe must contain 3,208 unique matches"
        )
    if set(result.season) != set(EXPECTED):
        raise SubstitutionTimingError(
            "J1 target seasons must be exactly 2015-2024"
        )
    return result


def _normalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    required = set(OUTPUT_COLUMNS[:5])
    if required - set(matches.columns):
        raise SubstitutionTimingError("Match frame lacks required identity columns")
    result = matches.copy(deep=True)
    result["match_id"] = result.match_id.astype(str)
    result["season"] = pd.to_numeric(result.season, errors="raise").astype(int)
    result["match_date"] = pd.to_datetime(
        result.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    if result.match_id.duplicated().any():
        raise SubstitutionTimingError("Duplicate target match_id")
    if result.loc[:, OUTPUT_COLUMNS[3:5]].isna().any().any():
        raise SubstitutionTimingError("Blank target team identity")
    if (result.home_team_id == result.away_team_id).any():
        raise SubstitutionTimingError("Target home and away team IDs must differ")
    return result.loc[:, OUTPUT_COLUMNS[:5]]


def _normalize_substitutions(events: pd.DataFrame) -> pd.DataFrame:
    required = {
        "event_id",
        "match_id",
        "match_date",
        "season",
        "team_id",
        "side",
        "event_type",
        "minute_raw",
        "minute_normalized",
        "minute_order_half",
        "minute_order_base",
        "minute_order_added",
        "source_section",
    }
    if required - set(events.columns):
        raise SubstitutionTimingError("SUB frame lacks required fields")
    result = events.copy(deep=True)
    if not result.event_type.eq("SUBSTITUTION").all():
        raise SubstitutionTimingError(
            "Substitution timing builder accepts SUBSTITUTION rows only"
        )
    if result.event_id.isna().any() or result.event_id.astype(str).eq("").any():
        raise SubstitutionTimingError("SUB event_id must be nonblank")
    if result.event_id.duplicated().any():
        raise SubstitutionTimingError("Duplicate SUB event_id")
    if not result.source_section.eq("A7").all():
        raise SubstitutionTimingError("SUB source_section must be A7")
    if not result.side.isin({"home", "away"}).all():
        raise SubstitutionTimingError("Invalid SUB side")
    if result.minute_raw.isna().any() or result.minute_raw.astype(str).eq("").any():
        raise SubstitutionTimingError("Unresolved SUB minute_raw")
    result["event_id"] = result.event_id.astype(str)
    result["match_id"] = result.match_id.astype(str)
    result["team_id"] = result.team_id.astype(str)
    result["season"] = pd.to_numeric(result.season, errors="raise").astype(int)
    result["match_date"] = pd.to_datetime(
        result.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    for field in (
        "minute_normalized",
        "minute_order_half",
        "minute_order_base",
        "minute_order_added",
    ):
        values = pd.to_numeric(result[field], errors="coerce")
        if values.isna().any() or not values.map(
            lambda value: float(value).is_integer()
        ).all():
            raise SubstitutionTimingError(
                f"Unresolved/noninteger SUB minute: {field}"
            )
        result[field] = values.astype(int)
    if result.empty:
        return result
    if result.minute_normalized.lt(3).any() or result.minute_normalized.gt(90).any():
        raise SubstitutionTimingError("SUB minute must be within frozen range 3-90")
    return result


def load_substitution_events(
    *, event_path: str | Path = EVENT_PATH
) -> pd.DataFrame:
    """Validate the frozen artifact and return normalized SUB rows only."""
    _validate_source_sha(event_path)
    rows = _read_csv(Path(event_path))
    if len(rows) != 39987:
        raise SubstitutionTimingError(
            f"Expected 39,987 normalized events, got {len(rows)}"
        )
    frame = pd.DataFrame(rows)
    if "event_type" not in frame.columns:
        raise SubstitutionTimingError("Event artifact lacks event_type")
    selected = frame.loc[frame.event_type.eq("SUBSTITUTION")].copy()
    if len(selected) != 23638:
        raise SubstitutionTimingError(
            f"Expected 23,638 normalized SUB rows, got {len(selected)}"
        )
    result = _normalize_substitutions(selected)
    if result.minute_normalized.min() != 3:
        raise SubstitutionTimingError("Observed SUB minute minimum must be 3")
    if result.minute_normalized.max() != 90:
        raise SubstitutionTimingError("Observed SUB minute maximum must be 90")
    return result


def _validate_event_identity(matches: pd.DataFrame, events: pd.DataFrame) -> None:
    identity = matches.set_index("match_id")
    if not set(events.match_id).issubset(identity.index):
        raise SubstitutionTimingError(
            "SUB references a match outside target universe"
        )
    for row in events.itertuples(index=False):
        match = identity.loc[row.match_id]
        if row.season != int(match.season) or row.match_date != match.match_date:
            raise SubstitutionTimingError(
                f"SUB date/season mismatch: {row.match_id}"
            )
        if row.team_id != match[f"{row.side}_team_id"]:
            raise SubstitutionTimingError(
                f"SUB team/side identity mismatch: {row.match_id}"
            )


def _source_audit(matches: pd.DataFrame, events: pd.DataFrame) -> dict:
    counts = events.groupby(["match_id", "side"]).size()
    values = {
        "target_rows": len(matches),
        "total_normalized_event_rows": 39987,
        "normalized_substitution_rows": len(events),
        "substitution_covered_matches": events.match_id.nunique(),
        "team_match_sides": 2 * len(matches),
        "positive_substitution_sides": len(counts),
        "zero_substitution_sides": 2 * len(matches) - len(counts),
        "observed_minute_min": int(events.minute_normalized.min()),
        "observed_minute_max": int(events.minute_normalized.max()),
    }
    expected = {
        "target_rows": 3208,
        "total_normalized_event_rows": 39987,
        "normalized_substitution_rows": 23638,
        "substitution_covered_matches": 3208,
        "team_match_sides": 6416,
        "positive_substitution_sides": 6410,
        "zero_substitution_sides": 6,
        "observed_minute_min": 3,
        "observed_minute_max": 90,
    }
    if values != expected:
        raise SubstitutionTimingError(
            f"Full substitution source audit mismatch: {values} != {expected}"
        )
    return values


def _empty_state() -> dict[str, int]:
    return {"count": 0, "sum": 0}


def _snapshot(state: dict[str, int]) -> dict[str, int | float | bool | None]:
    if (
        not isinstance(state["count"], int)
        or not isinstance(state["sum"], int)
        or state["count"] < 0
        or state["sum"] < 0
    ):
        raise SubstitutionTimingError("Invalid substitution timing history state")
    return {
        "count": state["count"],
        "sum": state["sum"],
        "mean": state["sum"] / state["count"] if state["count"] else None,
        "available": state["count"] > 0,
    }


def build_substitution_timing_features(
    matches: pd.DataFrame, events: pd.DataFrame
) -> pd.DataFrame:
    """Build target rows from strictly prior-date, same-season SUB history."""
    normalized_matches = _normalize_matches(matches)
    normalized_events = _normalize_substitutions(events)
    _validate_event_identity(normalized_matches, normalized_events)
    by_match = {
        match_id: group
        for match_id, group in normalized_events.groupby("match_id", sort=False)
    }
    ordered = normalized_matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if ordered.season.tolist() != sorted(ordered.season.tolist()):
        raise SubstitutionTimingError("Target chronology is not season ordered")

    output = []
    for season, season_rows in ordered.groupby("season", sort=True):
        history: defaultdict[str, dict[str, int]] = defaultdict(_empty_state)
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
                    team_id = getattr(row, f"{side}_team_id")
                    state = _snapshot(history[team_id])
                    values[f"{side}_substitution_timing_available"] = state[
                        "available"
                    ]
                    values[f"{side}_prior_substitution_events"] = state["count"]
                    values[
                        f"{side}_prior_substitution_minute_normalized_sum"
                    ] = state["sum"]
                    values[
                        f"{side}_mean_substitution_minute_normalized_prior"
                    ] = state["mean"]
                output.append(values)

            # Only after every target on this date is emitted may the date enter history.
            for row in day_rows.itertuples(index=False):
                substitutions = by_match.get(row.match_id)
                if substitutions is None:
                    continue
                for event in substitutions.itertuples(index=False):
                    state = history[event.team_id]
                    state["count"] += 1
                    state["sum"] += int(event.minute_normalized)

    result = pd.DataFrame(output, columns=OUTPUT_COLUMNS)
    _validate_result(
        result,
        matches=ordered,
        observed_minute_min=3,
        observed_minute_max=90,
    )
    return result


def _validate_result(
    result: pd.DataFrame,
    *,
    matches: pd.DataFrame,
    observed_minute_min: int,
    observed_minute_max: int,
) -> None:
    if tuple(result.columns) != OUTPUT_COLUMNS:
        raise SubstitutionTimingError("Output schema differs from frozen contract")
    if len(result) != len(matches) or result.match_id.duplicated().any():
        raise SubstitutionTimingError("Output must preserve one row per target match")
    expected = matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if result.match_id.tolist() != expected.match_id.tolist():
        raise SubstitutionTimingError("Output order must be match_date, match_id")
    expected_identity = expected.copy()
    expected_identity["match_date"] = expected_identity.match_date.map(
        lambda value: value.isoformat()
    )
    try:
        pd.testing.assert_frame_equal(
            result.loc[:, OUTPUT_COLUMNS[:5]].reset_index(drop=True),
            expected_identity.loc[:, OUTPUT_COLUMNS[:5]].reset_index(drop=True),
            check_dtype=False,
            obj="substitution timing output identity",
        )
    except AssertionError as exc:
        raise SubstitutionTimingError(
            "Output identity differs from target universe"
        ) from exc

    if (observed_minute_min, observed_minute_max) != (3, 90):
        raise SubstitutionTimingError("Observed SUB minute range must be 3-90")
    for side in ("home", "away"):
        denominator = result[f"{side}_prior_substitution_events"]
        sums = result[f"{side}_prior_substitution_minute_normalized_sum"]
        means = result[f"{side}_mean_substitution_minute_normalized_prior"]
        available = result[f"{side}_substitution_timing_available"]
        if denominator.isna().any() or denominator.lt(0).any():
            raise SubstitutionTimingError("Timing denominators must be nonnegative")
        if not all(float(value).is_integer() for value in denominator):
            raise SubstitutionTimingError("Timing denominators must be integers")
        if sums.isna().any() or sums.lt(0).any() or not sums.map(math.isfinite).all():
            raise SubstitutionTimingError("Timing sums must be finite and nonnegative")
        zero = denominator.eq(0)
        positive = denominator.gt(0)
        if sums.loc[zero].ne(0).any() or means.loc[zero].notna().any():
            raise SubstitutionTimingError("Invalid zero-denominator timing state")
        if means.loc[positive].isna().any():
            raise SubstitutionTimingError("Positive denominator has a null mean")
        if positive.any():
            expected_mean = sums.loc[positive] / denominator.loc[positive]
            if not all(
                math.isclose(actual, wanted, rel_tol=0, abs_tol=1e-12)
                for actual, wanted in zip(means.loc[positive], expected_mean)
            ):
                raise SubstitutionTimingError(
                    "Timing mean differs from sum/denominator"
                )
            if (
                not means.loc[positive].map(math.isfinite).all()
                or means.loc[positive].lt(observed_minute_min).any()
                or means.loc[positive].gt(observed_minute_max).any()
            ):
                raise SubstitutionTimingError("Timing mean is outside source range")
        if not available.isin([True, False]).all() or (
            available.astype(bool) != positive
        ).any():
            raise SubstitutionTimingError("Substitution timing availability mismatch")


def _availability_summary(result: pd.DataFrame) -> dict:
    availability = {}
    for season, rows in result.groupby("season", sort=True):
        home = rows.home_substitution_timing_available.astype(bool)
        away = rows.away_substitution_timing_available.astype(bool)
        values = {
            "total": len(rows),
            "home_available": int(home.sum()),
            "away_available": int(away.sum()),
            "pair_available": int((home & away).sum()),
            "either_unavailable": int((~(home & away)).sum()),
            "both_unavailable": int((~home & ~away).sum()),
        }
        expected = {
            "total": EXPECTED[int(season)],
            "pair_available": EXPECTED_PAIR_AVAILABLE[int(season)],
        }
        if values["total"] != expected["total"] or values["pair_available"] != expected[
            "pair_available"
        ]:
            raise SubstitutionTimingError(
                f"Availability mismatch for {season}: {values}"
            )
        availability[str(int(season))] = values
    pair_available = sum(row["pair_available"] for row in availability.values())
    side_available = sum(
        row["home_available"] + row["away_available"]
        for row in availability.values()
    )
    if pair_available != 3116 or len(result) - pair_available != 92:
        raise SubstitutionTimingError("Global pair availability mismatch")
    if side_available != 6232 or 2 * len(result) - side_available != 184:
        raise SubstitutionTimingError("Global side availability mismatch")
    return availability


def _downstream_usable_observations(
    matches: pd.DataFrame, events: pd.DataFrame
) -> int:
    last_target = {}
    for row in matches.itertuples(index=False):
        for side in ("home", "away"):
            key = (int(row.season), getattr(row, f"{side}_team_id"))
            last_target[key] = max(last_target.get(key, row.match_date), row.match_date)
    return sum(
        event.match_date < last_target[(int(event.season), event.team_id)]
        for event in events.itertuples(index=False)
    )


def materialization_summary(
    matches: pd.DataFrame,
    events: pd.DataFrame,
    result: pd.DataFrame,
    *,
    metadata: dict,
) -> dict:
    return {
        **_source_audit(matches, events),
        "source_sha256": SOURCE_SHA256,
        "raw_a7_rows": int(metadata["raw_source_rows"]["A7"]),
        "raw_a7_to_normalized_substitution_ratio": 2,
        "output_rows": len(result),
        "total_substitution_source_observations": len(events),
        "total_history_updates_applied": len(events),
        "history_observations_reaching_later_target": _downstream_usable_observations(
            matches, events
        ),
        "denominator_sum_invariant_failures": 0,
        "partial_invalid_rows": 0,
        "availability_by_season": _availability_summary(result),
        "pair_available": 3116,
        "pair_unavailable": 92,
        "team_side_available": 6232,
        "team_side_unavailable": 184,
        "deterministic_rebuild": "PASS",
    }


def _csv_bytes(result: pd.DataFrame) -> bytes:
    return result.to_csv(index=False, lineterminator="\n").encode("utf-8")


def materialize_substitution_timing_features(
    *,
    j1_dir: str | Path = J1_DIR,
    event_path: str | Path = EVENT_PATH,
    event_summary_path: str | Path = EVENT_SUMMARY_PATH,
    output_path: str | Path = OUTPUT_PATH,
) -> tuple[pd.DataFrame, dict]:
    """Validate and materialize the frozen 2015-2024 feature artifact."""
    matches = load_j1_matches(j1_dir=j1_dir)
    metadata = _load_event_metadata(event_summary_path)
    events = load_substitution_events(event_path=event_path)
    _validate_event_identity(matches, events)
    _source_audit(matches, events)
    result = build_substitution_timing_features(matches, events)
    rebuilt = build_substitution_timing_features(
        matches.iloc[::-1].reset_index(drop=True),
        events.iloc[::-1].reset_index(drop=True),
    )
    if _csv_bytes(result) != _csv_bytes(rebuilt):
        raise SubstitutionTimingError("Rebuild is not byte-identical")
    summary = materialization_summary(
        matches, events, result, metadata=metadata
    )

    output = Path(output_path)
    if output.exists():
        raise SubstitutionTimingError(
            f"Output already exists; refusing overwrite: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
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
            handle.write(_csv_bytes(result))
        os.rename(temporary, output)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    summary["output"] = str(output)
    summary["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    return result, summary


if __name__ == "__main__":
    _, audit = materialize_substitution_timing_features()
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
