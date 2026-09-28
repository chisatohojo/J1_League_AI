"""Leakage-safe current-season ordinary-J1 goal timing profile features."""

from __future__ import annotations

from collections import Counter, defaultdict
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
OUTPUT_PATH = ROOT / "data/processed/features/2015_2024_j1_goal_timing_features.csv"
SOURCE_SHA256 = "6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131"
EXPECTED = {
    **{year: 306 for year in range(2015, 2021)},
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
EXCLUDED_MATCH_IDS = frozenset({"25153"})
OUTPUT_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
    "home_goal_timing_available",
    "away_goal_timing_available",
    "home_prior_first_goal_timing_observations",
    "away_prior_first_goal_timing_observations",
    "home_prior_scoring_goal_events",
    "away_prior_scoring_goal_events",
    "home_prior_conceding_goal_events",
    "away_prior_conceding_goal_events",
    "home_prior_first_goal_minute_normalized_sum",
    "away_prior_first_goal_minute_normalized_sum",
    "home_prior_scoring_minute_normalized_sum",
    "away_prior_scoring_minute_normalized_sum",
    "home_prior_conceding_minute_normalized_sum",
    "away_prior_conceding_minute_normalized_sum",
    "home_mean_first_goal_minute_normalized_prior",
    "away_mean_first_goal_minute_normalized_prior",
    "home_mean_scoring_minute_normalized_prior",
    "away_mean_scoring_minute_normalized_prior",
    "home_mean_conceding_minute_normalized_prior",
    "away_mean_conceding_minute_normalized_prior",
)


class GoalTimingProfileError(ValueError):
    """Invalid source identity, chronology, timing, or feature state."""


def _read_csv(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise GoalTimingProfileError(f"Invalid CSV columns: {path}")
            return list(reader)
    except OSError as exc:
        raise GoalTimingProfileError(f"Missing input: {path}") from exc


def _validate_source_sha(
    path: str | Path, *, expected_sha256: str = SOURCE_SHA256
) -> str:
    source = Path(path)
    try:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as exc:
        raise GoalTimingProfileError(f"Missing event artifact: {source}") from exc
    if digest != expected_sha256:
        raise GoalTimingProfileError(
            f"Event artifact SHA-256 mismatch: {digest} != {expected_sha256}"
        )
    return digest


def load_j1_matches(*, j1_dir: str | Path = J1_DIR) -> pd.DataFrame:
    """Load and resolve the frozen 2015-2024 ordinary-J1 target universe."""
    master = load_team_master()
    frames = []
    for season, expected in EXPECTED.items():
        rows = _read_csv(Path(j1_dir) / f"{season}_matches_probe.csv")
        if len(rows) != expected:
            raise GoalTimingProfileError(
                f"{season} expected {expected} matches, got {len(rows)}"
            )
        frame = pd.DataFrame(rows)
        required = {"match_id", "season", "match_date", "home_team", "away_team"}
        if required - set(frame.columns) or frame.match_id.duplicated().any():
            raise GoalTimingProfileError(f"Invalid J1 identity columns for {season}")
        frame["match_id"] = frame.match_id.astype(str)
        frame["season"] = pd.to_numeric(frame.season, errors="raise").astype(int)
        if set(frame.season) != {season}:
            raise GoalTimingProfileError(f"Season mismatch in {season}")
        frame["match_date"] = pd.to_datetime(
            frame.match_date, format="%Y-%m-%d", errors="raise"
        ).dt.date
        if any(day.year != season for day in frame.match_date):
            raise GoalTimingProfileError(f"Date escaped season {season}")
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
            raise GoalTimingProfileError(
                f"J1 TeamMaster resolution failed for {season}"
            ) from exc
        if (frame.home_team_id == frame.away_team_id).any():
            raise GoalTimingProfileError(f"Same home/away team identity in {season}")
        frames.append(frame.loc[:, OUTPUT_COLUMNS[:5]])
    result = pd.concat(frames, ignore_index=True)
    if len(result) != 3208 or result.match_id.duplicated().any():
        raise GoalTimingProfileError(
            "J1 target universe must contain 3,208 unique matches"
        )
    if set(result.season) != set(EXPECTED):
        raise GoalTimingProfileError("J1 target seasons must be exactly 2015-2024")
    return result


def load_goal_events(*, event_path: str | Path = EVENT_PATH) -> pd.DataFrame:
    """Verify the frozen artifact and load its GOAL rows only."""
    _validate_source_sha(event_path)
    rows = _read_csv(Path(event_path))
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
        "normalization_flags",
    }
    if not rows or required - set(rows[0]):
        raise GoalTimingProfileError("Event artifact lacks required GOAL fields")
    frame = pd.DataFrame(rows)
    frame = frame.loc[frame.event_type.eq("GOAL")].copy()
    return _normalize_goals(frame)


def _normalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    required = set(OUTPUT_COLUMNS[:5])
    if required - set(matches.columns):
        raise GoalTimingProfileError("Match frame lacks required identity columns")
    result = matches.copy(deep=True)
    result["match_id"] = result.match_id.astype(str)
    result["season"] = pd.to_numeric(result.season, errors="raise").astype(int)
    result["match_date"] = pd.to_datetime(
        result.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    if result.match_id.duplicated().any():
        raise GoalTimingProfileError("Duplicate target match_id")
    if result.loc[:, OUTPUT_COLUMNS[3:5]].isna().any().any():
        raise GoalTimingProfileError("Blank target team identity")
    if (result.home_team_id == result.away_team_id).any():
        raise GoalTimingProfileError("Target home and away team IDs must differ")
    return result.loc[:, OUTPUT_COLUMNS[:5]]


def _normalize_goals(events: pd.DataFrame) -> pd.DataFrame:
    required = {
        "event_id",
        "match_id",
        "match_date",
        "season",
        "team_id",
        "side",
        "event_type",
        "minute_normalized",
        "minute_order_half",
        "minute_order_base",
        "minute_order_added",
    }
    if required - set(events.columns):
        raise GoalTimingProfileError("GOAL frame lacks required fields")
    result = events.copy(deep=True)
    if not result.event_type.eq("GOAL").all():
        raise GoalTimingProfileError("Goal timing builder accepts GOAL rows only")
    if result.event_id.isna().any() or result.event_id.eq("").any():
        raise GoalTimingProfileError("GOAL event_id must be nonblank")
    if result.event_id.duplicated().any():
        raise GoalTimingProfileError("Duplicate GOAL event_id")
    if not result.side.isin({"home", "away"}).all():
        raise GoalTimingProfileError("Invalid GOAL side")
    result["match_id"] = result.match_id.astype(str)
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
            raise GoalTimingProfileError(f"Unresolved/noninteger GOAL minute: {field}")
        result[field] = values.astype(int)
    if (result.minute_normalized < 0).any():
        raise GoalTimingProfileError("GOAL minute_normalized must be nonnegative")
    return result


def _validate_event_identity(matches: pd.DataFrame, events: pd.DataFrame) -> None:
    identity = matches.set_index("match_id")
    if not set(events.match_id).issubset(identity.index):
        raise GoalTimingProfileError("GOAL references a match outside target universe")
    for row in events.itertuples(index=False):
        match = identity.loc[row.match_id]
        if row.season != int(match.season) or row.match_date != match.match_date:
            raise GoalTimingProfileError(f"GOAL date/season mismatch: {row.match_id}")
        expected_team = match[f"{row.side}_team_id"]
        if row.team_id != expected_team:
            raise GoalTimingProfileError(
                f"GOAL team/side identity mismatch: {row.match_id}"
            )


def _first_goal_value(goals: pd.DataFrame, *, match_id: str) -> int:
    keys = list(
        zip(
            goals.minute_order_half,
            goals.minute_order_base,
            goals.minute_order_added,
        )
    )
    minimum = min(keys)
    values = {
        int(value)
        for value, key in zip(goals.minute_normalized, keys)
        if key == minimum
    }
    if len(values) != 1:
        raise GoalTimingProfileError(
            f"Minimum GOAL key has inconsistent normalized minutes: {match_id}"
        )
    return values.pop()


def _empty_state() -> dict[str, int]:
    return {
        "first_count": 0,
        "first_sum": 0,
        "scoring_count": 0,
        "scoring_sum": 0,
        "conceding_count": 0,
        "conceding_sum": 0,
    }


def _snapshot(state: dict[str, int]) -> dict[str, int | float | bool | None]:
    for value in state.values():
        if not isinstance(value, int) or value < 0:
            raise GoalTimingProfileError("Invalid goal timing history state")
    available = all(
        state[key] > 0
        for key in ("first_count", "scoring_count", "conceding_count")
    )
    return {
        **state,
        "available": available,
        "first_mean": (
            state["first_sum"] / state["first_count"]
            if state["first_count"]
            else None
        ),
        "scoring_mean": (
            state["scoring_sum"] / state["scoring_count"]
            if state["scoring_count"]
            else None
        ),
        "conceding_mean": (
            state["conceding_sum"] / state["conceding_count"]
            if state["conceding_count"]
            else None
        ),
    }


def build_goal_timing_features(
    matches: pd.DataFrame,
    events: pd.DataFrame,
    *,
    excluded_match_ids: set[str] | frozenset[str] = EXCLUDED_MATCH_IDS,
) -> pd.DataFrame:
    """Build target rows from strictly prior-date, same-season GOAL history."""
    normalized_matches = _normalize_matches(matches)
    normalized_events = _normalize_goals(events)
    _validate_event_identity(normalized_matches, normalized_events)
    excluded = {str(match_id) for match_id in excluded_match_ids}
    by_match = {
        match_id: group
        for match_id, group in normalized_events.groupby("match_id", sort=False)
    }
    ordered = normalized_matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if ordered.season.tolist() != sorted(ordered.season.tolist()):
        raise GoalTimingProfileError("Target chronology is not season ordered")

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
                    state = _snapshot(history[getattr(row, f"{side}_team_id")])
                    values[f"{side}_goal_timing_available"] = state["available"]
                    values[f"{side}_prior_first_goal_timing_observations"] = state[
                        "first_count"
                    ]
                    values[f"{side}_prior_scoring_goal_events"] = state[
                        "scoring_count"
                    ]
                    values[f"{side}_prior_conceding_goal_events"] = state[
                        "conceding_count"
                    ]
                    values[
                        f"{side}_prior_first_goal_minute_normalized_sum"
                    ] = state["first_sum"]
                    values[f"{side}_prior_scoring_minute_normalized_sum"] = state[
                        "scoring_sum"
                    ]
                    values[f"{side}_prior_conceding_minute_normalized_sum"] = state[
                        "conceding_sum"
                    ]
                    values[
                        f"{side}_mean_first_goal_minute_normalized_prior"
                    ] = state["first_mean"]
                    values[f"{side}_mean_scoring_minute_normalized_prior"] = state[
                        "scoring_mean"
                    ]
                    values[
                        f"{side}_mean_conceding_minute_normalized_prior"
                    ] = state["conceding_mean"]
                output.append(values)

            # Only after every target on this date is emitted may the date enter history.
            for row in day_rows.itertuples(index=False):
                if row.match_id in excluded:
                    continue
                goals = by_match.get(row.match_id)
                if goals is None:
                    continue
                first_value = _first_goal_value(goals, match_id=row.match_id)
                for team_id in (row.home_team_id, row.away_team_id):
                    history[team_id]["first_count"] += 1
                    history[team_id]["first_sum"] += first_value
                for goal in goals.itertuples(index=False):
                    scoring_team = row.home_team_id if goal.side == "home" else row.away_team_id
                    conceding_team = row.away_team_id if goal.side == "home" else row.home_team_id
                    minute = int(goal.minute_normalized)
                    history[scoring_team]["scoring_count"] += 1
                    history[scoring_team]["scoring_sum"] += minute
                    history[conceding_team]["conceding_count"] += 1
                    history[conceding_team]["conceding_sum"] += minute

    result = pd.DataFrame(output, columns=OUTPUT_COLUMNS)
    observed_max = (
        int(normalized_events.minute_normalized.max())
        if not normalized_events.empty
        else None
    )
    _validate_result(result, matches=ordered, observed_minute_max=observed_max)
    return result


def _validate_result(
    result: pd.DataFrame,
    *,
    matches: pd.DataFrame,
    observed_minute_max: int | None,
) -> None:
    if tuple(result.columns) != OUTPUT_COLUMNS:
        raise GoalTimingProfileError("Output schema differs from frozen contract")
    if len(result) != len(matches) or result.match_id.duplicated().any():
        raise GoalTimingProfileError("Output must preserve one row per target match")
    expected = matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if result.match_id.tolist() != expected.match_id.tolist():
        raise GoalTimingProfileError("Output order must be match_date, match_id")
    expected_identity = expected.copy()
    expected_identity["match_date"] = expected_identity.match_date.map(
        lambda value: value.isoformat()
    )
    try:
        pd.testing.assert_frame_equal(
            result.loc[:, OUTPUT_COLUMNS[:5]].reset_index(drop=True),
            expected_identity.loc[:, OUTPUT_COLUMNS[:5]].reset_index(drop=True),
            check_dtype=False,
            obj="goal timing output identity",
        )
    except AssertionError as exc:
        raise GoalTimingProfileError("Output identity differs from target universe") from exc

    for side in ("home", "away"):
        definitions = (
            (
                f"{side}_prior_first_goal_timing_observations",
                f"{side}_prior_first_goal_minute_normalized_sum",
                f"{side}_mean_first_goal_minute_normalized_prior",
            ),
            (
                f"{side}_prior_scoring_goal_events",
                f"{side}_prior_scoring_minute_normalized_sum",
                f"{side}_mean_scoring_minute_normalized_prior",
            ),
            (
                f"{side}_prior_conceding_goal_events",
                f"{side}_prior_conceding_minute_normalized_sum",
                f"{side}_mean_conceding_minute_normalized_prior",
            ),
        )
        positive_denominators = []
        for denominator_name, sum_name, mean_name in definitions:
            denominator = result[denominator_name]
            sums = result[sum_name]
            means = result[mean_name]
            if denominator.isna().any() or denominator.lt(0).any():
                raise GoalTimingProfileError("Timing denominators must be nonnegative")
            if not all(float(value).is_integer() for value in denominator):
                raise GoalTimingProfileError("Timing denominators must be integers")
            if sums.isna().any() or sums.lt(0).any() or not sums.map(math.isfinite).all():
                raise GoalTimingProfileError("Timing sums must be finite and nonnegative")
            zero = denominator.eq(0)
            positive = denominator.gt(0)
            positive_denominators.append(positive)
            if sums.loc[zero].ne(0).any():
                raise GoalTimingProfileError("Zero denominator has a nonzero sum")
            if means.loc[zero].notna().any():
                raise GoalTimingProfileError("Zero denominator has a non-null mean")
            if means.loc[positive].isna().any():
                raise GoalTimingProfileError("Positive denominator has a null mean")
            if positive.any():
                expected_mean = sums.loc[positive] / denominator.loc[positive]
                if not all(
                    math.isclose(actual, wanted, rel_tol=0, abs_tol=1e-12)
                    for actual, wanted in zip(means.loc[positive], expected_mean)
                ):
                    raise GoalTimingProfileError("Timing mean differs from sum/denominator")
                if not means.loc[positive].map(math.isfinite).all():
                    raise GoalTimingProfileError("Timing mean must be finite")
                if means.loc[positive].lt(0).any():
                    raise GoalTimingProfileError("Timing mean is negative")
                if (
                    observed_minute_max is not None
                    and means.loc[positive].gt(observed_minute_max).any()
                ):
                    raise GoalTimingProfileError("Timing mean exceeds source minute range")
        available = result[f"{side}_goal_timing_available"]
        expected_available = (
            positive_denominators[0]
            & positive_denominators[1]
            & positive_denominators[2]
        )
        if not available.isin([True, False]).all() or (
            available.astype(bool) != expected_available
        ).any():
            raise GoalTimingProfileError("Goal timing availability mismatch")


def _source_audit(
    matches: pd.DataFrame,
    events: pd.DataFrame,
    *,
    excluded_match_ids: set[str] | frozenset[str] = EXCLUDED_MATCH_IDS,
) -> dict:
    excluded = {str(match_id) for match_id in excluded_match_ids}
    excluded_events = events.loc[events.match_id.isin(excluded)]
    eligible_events = events.loc[~events.match_id.isin(excluded)]
    eligible_goal_matches = set(eligible_events.match_id)
    values = {
        "target_rows": len(matches),
        "source_goal_rows": len(events),
        "source_goal_matches": events.match_id.nunique(),
        "no_goal_matches": len(matches) - events.match_id.nunique(),
        "excluded_matches": len(excluded & set(matches.match_id)),
        "excluded_goal_rows": len(excluded_events),
        "history_eligible_goal_rows": len(eligible_events),
        "usable_first_goal_matches": len(eligible_goal_matches),
        "team_history_first_goal_increments": 2 * len(eligible_goal_matches),
        "scoring_goal_observations": len(eligible_events),
        "conceding_goal_observations": len(eligible_events),
    }
    expected = {
        "target_rows": 3208,
        "source_goal_rows": 8377,
        "source_goal_matches": 2958,
        "no_goal_matches": 250,
        "excluded_matches": 1,
        "excluded_goal_rows": 5,
        "history_eligible_goal_rows": 8372,
        "usable_first_goal_matches": 2957,
        "team_history_first_goal_increments": 5914,
        "scoring_goal_observations": 8372,
        "conceding_goal_observations": 8372,
    }
    if values != expected:
        raise GoalTimingProfileError(f"Full source audit mismatch: {values} != {expected}")
    return values


def materialization_summary(
    matches: pd.DataFrame, events: pd.DataFrame, result: pd.DataFrame
) -> dict:
    availability = {}
    for season, rows in result.groupby("season", sort=True):
        home = rows.home_goal_timing_available.astype(bool)
        away = rows.away_goal_timing_available.astype(bool)
        availability[str(int(season))] = {
            "total": len(rows),
            "home_available": int(home.sum()),
            "away_available": int(away.sum()),
            "pair_available": int((home & away).sum()),
            "either_unavailable": int((~(home & away)).sum()),
            "both_unavailable": int((~home & ~away).sum()),
        }
    source_by_season = {}
    eligible = events.loc[~events.match_id.isin(EXCLUDED_MATCH_IDS)]
    for season in sorted(EXPECTED):
        rows = eligible.loc[eligible.season.eq(season)]
        source_by_season[str(season)] = {
            "usable_first_goal_matches": rows.match_id.nunique(),
            "eligible_scoring_goal_events": len(rows),
            "eligible_conceding_goal_events": len(rows),
        }
    return {
        **_source_audit(matches, events),
        "availability_by_season": availability,
        "source_observations_by_season": source_by_season,
    }


def materialize_goal_timing_features(
    *,
    j1_dir: str | Path = J1_DIR,
    event_path: str | Path = EVENT_PATH,
    output_path: str | Path = OUTPUT_PATH,
) -> pd.DataFrame:
    """Validate and materialize the frozen 2015-2024 feature artifact."""
    matches = load_j1_matches(j1_dir=j1_dir)
    events = load_goal_events(event_path=event_path)
    _validate_event_identity(matches, events)
    _source_audit(matches, events)
    result = build_goal_timing_features(matches, events)
    output = Path(output_path)
    if output.exists():
        raise GoalTimingProfileError(
            f"Output already exists; refusing overwrite: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=output.parent,
            prefix=output.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            result.to_csv(handle, index=False, lineterminator="\n")
        os.rename(temporary, output)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    return result


if __name__ == "__main__":
    materialized = materialize_goal_timing_features()
    loaded_matches = load_j1_matches()
    loaded_events = load_goal_events()
    summary = materialization_summary(loaded_matches, loaded_events, materialized)
    summary["source_sha256"] = SOURCE_SHA256
    summary["output"] = str(OUTPUT_PATH)
    summary["output_sha256"] = hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
