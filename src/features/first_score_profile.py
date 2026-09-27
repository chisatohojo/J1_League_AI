"""Leakage-safe current-season ordinary-J1 first-score profile features."""

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
OUTPUT_PATH = ROOT / "data/processed/features/2015_2024_j1_first_score_features.csv"
EXPECTED = {
    **{year: 306 for year in range(2015, 2021)},
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
NOT_CHECKABLE_MATCH_IDS = frozenset({"25153"})
CLASSIFICATIONS = (
    "SCORED_FIRST_HOME",
    "SCORED_FIRST_AWAY",
    "NO_GOAL",
    "AMBIGUOUS_FIRST_SIDE",
    "NOT_CHECKABLE",
)
OUTPUT_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
    "home_first_score_available",
    "away_first_score_available",
    "home_prior_first_score_eligible_matches",
    "away_prior_first_score_eligible_matches",
    "home_prior_scored_first_matches",
    "away_prior_scored_first_matches",
    "home_prior_conceded_first_matches",
    "away_prior_conceded_first_matches",
    "home_prior_no_goal_matches",
    "away_prior_no_goal_matches",
    "home_scored_first_rate_prior",
    "away_scored_first_rate_prior",
    "home_conceded_first_rate_prior",
    "away_conceded_first_rate_prior",
    "home_no_goal_rate_prior",
    "away_no_goal_rate_prior",
)


class FirstScoreProfileError(ValueError):
    """Invalid source identity, chronology, classification, or feature state."""


def _read_csv(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise FirstScoreProfileError(f"Invalid CSV columns: {path}")
            return list(reader)
    except OSError as exc:
        raise FirstScoreProfileError(f"Missing input: {path}") from exc


def load_j1_matches(*, j1_dir: str | Path = J1_DIR) -> pd.DataFrame:
    """Load and resolve the frozen 2015-2024 ordinary-J1 target universe."""
    master = load_team_master()
    frames = []
    for season, expected in EXPECTED.items():
        rows = _read_csv(Path(j1_dir) / f"{season}_matches_probe.csv")
        if len(rows) != expected:
            raise FirstScoreProfileError(
                f"{season} expected {expected} matches, got {len(rows)}"
            )
        frame = pd.DataFrame(rows)
        required = {"match_id", "season", "match_date", "home_team", "away_team"}
        if required - set(frame.columns) or frame.match_id.duplicated().any():
            raise FirstScoreProfileError(f"Invalid J1 identity columns for {season}")
        if set(frame.season.astype(int)) != {season}:
            raise FirstScoreProfileError(f"Season mismatch in {season}")
        frame["match_id"] = frame.match_id.astype(str)
        frame["season"] = frame.season.astype(int)
        frame["match_date"] = pd.to_datetime(
            frame.match_date, format="%Y-%m-%d", errors="raise"
        ).dt.date
        if any(day.year != season for day in frame.match_date):
            raise FirstScoreProfileError(f"Date escaped season {season}")
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
            raise FirstScoreProfileError(
                f"J1 TeamMaster resolution failed for {season}"
            ) from exc
        if (frame.home_team_id == frame.away_team_id).any():
            raise FirstScoreProfileError(f"Same home/away team identity in {season}")
        frames.append(frame.loc[:, OUTPUT_COLUMNS[:5]])
    result = pd.concat(frames, ignore_index=True)
    if len(result) != 3208 or result.match_id.duplicated().any():
        raise FirstScoreProfileError(
            "J1 target universe must contain 3,208 unique matches"
        )
    if set(result.season.astype(int)) != set(EXPECTED):
        raise FirstScoreProfileError("J1 target seasons must be exactly 2015-2024")
    return result


def load_goal_events(*, event_path: str | Path = EVENT_PATH) -> pd.DataFrame:
    """Load only GOAL rows after validating their frozen source fields."""
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
        raise FirstScoreProfileError("Event dataset lacks required GOAL fields")
    frame = pd.DataFrame(rows)
    frame = frame.loc[frame.event_type.eq("GOAL")].copy()
    if frame.empty:
        raise FirstScoreProfileError("Event dataset contains no GOAL rows")
    if frame.event_id.isna().any() or frame.event_id.eq("").any():
        raise FirstScoreProfileError("GOAL event_id must be nonblank")
    if frame.event_id.duplicated().any():
        raise FirstScoreProfileError("GOAL event_id must be unique")
    if not frame.side.isin({"home", "away"}).all():
        raise FirstScoreProfileError("Invalid GOAL side")
    frame["match_id"] = frame.match_id.astype(str)
    frame["season"] = pd.to_numeric(frame.season, errors="raise").astype(int)
    frame["match_date"] = pd.to_datetime(
        frame.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    minute_fields = (
        "minute_normalized",
        "minute_order_half",
        "minute_order_base",
        "minute_order_added",
    )
    if frame.minute_raw.isna().any() or frame.minute_raw.eq("").any():
        raise FirstScoreProfileError("GOAL minute_raw must be nonblank")
    for field in minute_fields:
        values = pd.to_numeric(frame[field], errors="coerce")
        if values.isna().any():
            raise FirstScoreProfileError(f"Unresolved GOAL minute field: {field}")
        frame[field] = values.astype(int)
    return frame


def _normalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    required = set(OUTPUT_COLUMNS[:5])
    if required - set(matches.columns):
        raise FirstScoreProfileError("Match frame lacks required identity columns")
    result = matches.copy(deep=True)
    result["match_id"] = result.match_id.astype(str)
    result["season"] = pd.to_numeric(result.season, errors="raise").astype(int)
    result["match_date"] = pd.to_datetime(
        result.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    if result.match_id.duplicated().any():
        raise FirstScoreProfileError("Duplicate target match_id")
    if result[list(OUTPUT_COLUMNS[3:5])].isna().any().any():
        raise FirstScoreProfileError("Blank target team identity")
    if (result.home_team_id == result.away_team_id).any():
        raise FirstScoreProfileError("Target home and away team IDs must differ")
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
        "minute_order_half",
        "minute_order_base",
        "minute_order_added",
    }
    if required - set(events.columns):
        raise FirstScoreProfileError("GOAL frame lacks required fields")
    result = events.copy(deep=True)
    if not result.event_type.eq("GOAL").all():
        raise FirstScoreProfileError("First-score builder accepts GOAL rows only")
    if result.event_id.isna().any() or result.event_id.eq("").any():
        raise FirstScoreProfileError("GOAL event_id must be nonblank")
    if result.event_id.duplicated().any():
        raise FirstScoreProfileError("Duplicate GOAL event_id")
    if not result.side.isin({"home", "away"}).all():
        raise FirstScoreProfileError("Invalid GOAL side")
    result["match_id"] = result.match_id.astype(str)
    result["season"] = pd.to_numeric(result.season, errors="raise").astype(int)
    result["match_date"] = pd.to_datetime(
        result.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    for field in ("minute_order_half", "minute_order_base", "minute_order_added"):
        values = pd.to_numeric(result[field], errors="coerce")
        if values.isna().any():
            raise FirstScoreProfileError(f"Unresolved GOAL order field: {field}")
        result[field] = values.astype(int)
    return result


def _validate_event_identity(matches: pd.DataFrame, events: pd.DataFrame) -> None:
    identity = matches.set_index("match_id")
    if not set(events.match_id).issubset(identity.index):
        raise FirstScoreProfileError("GOAL references a match outside target universe")
    for row in events.itertuples(index=False):
        match = identity.loc[row.match_id]
        if row.season != int(match.season) or row.match_date != match.match_date:
            raise FirstScoreProfileError(
                f"GOAL date/season mismatch: {row.match_id}"
            )
        expected_team = match[f"{row.side}_team_id"]
        if row.team_id != expected_team:
            raise FirstScoreProfileError(
                f"GOAL team/side identity mismatch: {row.match_id}"
            )


def classify_first_score(
    matches: pd.DataFrame,
    events: pd.DataFrame,
    *,
    not_checkable_match_ids: set[str] | frozenset[str] = NOT_CHECKABLE_MATCH_IDS,
) -> pd.DataFrame:
    """Classify every target match without using row order as a tie-break."""
    normalized_matches = _normalize_matches(matches)
    normalized_events = _normalize_goals(events)
    _validate_event_identity(normalized_matches, normalized_events)
    forced = {str(match_id) for match_id in not_checkable_match_ids}
    by_match = {
        match_id: group
        for match_id, group in normalized_events.groupby("match_id", sort=False)
    }
    rows = []
    for match in normalized_matches.itertuples(index=False):
        if match.match_id in forced:
            classification = "NOT_CHECKABLE"
        elif match.match_id not in by_match:
            classification = "NO_GOAL"
        else:
            goals = by_match[match.match_id]
            keys = list(
                zip(
                    goals.minute_order_half,
                    goals.minute_order_base,
                    goals.minute_order_added,
                )
            )
            minimum = min(keys)
            first_sides = {
                side for side, time_key in zip(goals.side, keys) if time_key == minimum
            }
            if first_sides == {"home"}:
                classification = "SCORED_FIRST_HOME"
            elif first_sides == {"away"}:
                classification = "SCORED_FIRST_AWAY"
            elif first_sides == {"home", "away"}:
                classification = "AMBIGUOUS_FIRST_SIDE"
            else:
                raise FirstScoreProfileError(
                    f"Invalid first-side state: {match.match_id}"
                )
        rows.append({"match_id": match.match_id, "classification": classification})
    result = pd.DataFrame(rows, columns=("match_id", "classification"))
    if len(result) != len(normalized_matches) or result.match_id.duplicated().any():
        raise FirstScoreProfileError("Classification must be one row per target match")
    if not result.classification.isin(CLASSIFICATIONS).all():
        raise FirstScoreProfileError("Unknown first-score classification")
    return result


def _empty_counter() -> dict[str, int]:
    return {"eligible": 0, "scored": 0, "conceded": 0, "no_goal": 0}


def _snapshot(values: dict[str, int]) -> dict[str, int | float | bool | None]:
    eligible = values["eligible"]
    if eligible != values["scored"] + values["conceded"] + values["no_goal"]:
        raise FirstScoreProfileError("First-score denominator invariant failed")
    if eligible == 0:
        return {
            "available": False,
            "eligible": 0,
            "scored": 0,
            "conceded": 0,
            "no_goal": 0,
            "scored_rate": None,
            "conceded_rate": None,
            "no_goal_rate": None,
        }
    return {
        "available": True,
        "eligible": eligible,
        "scored": values["scored"],
        "conceded": values["conceded"],
        "no_goal": values["no_goal"],
        "scored_rate": values["scored"] / eligible,
        "conceded_rate": values["conceded"] / eligible,
        "no_goal_rate": values["no_goal"] / eligible,
    }


def build_first_score_features(
    matches: pd.DataFrame,
    events: pd.DataFrame,
    *,
    not_checkable_match_ids: set[str] | frozenset[str] = NOT_CHECKABLE_MATCH_IDS,
) -> pd.DataFrame:
    """Build one pre-match row per target using same-season prior dates only."""
    normalized_matches = _normalize_matches(matches)
    normalized_events = _normalize_goals(events)
    classifications = classify_first_score(
        normalized_matches,
        normalized_events,
        not_checkable_match_ids=not_checkable_match_ids,
    ).set_index("match_id")["classification"]
    ordered = normalized_matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if ordered.season.tolist() != sorted(ordered.season.tolist()):
        raise FirstScoreProfileError("Target chronology is not season ordered")

    output = []
    for season, season_rows in ordered.groupby("season", sort=True):
        history: defaultdict[str, dict[str, int]] = defaultdict(_empty_counter)
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
                    values[f"{side}_first_score_available"] = state["available"]
                    values[f"{side}_prior_first_score_eligible_matches"] = state["eligible"]
                    values[f"{side}_prior_scored_first_matches"] = state["scored"]
                    values[f"{side}_prior_conceded_first_matches"] = state["conceded"]
                    values[f"{side}_prior_no_goal_matches"] = state["no_goal"]
                    values[f"{side}_scored_first_rate_prior"] = state["scored_rate"]
                    values[f"{side}_conceded_first_rate_prior"] = state["conceded_rate"]
                    values[f"{side}_no_goal_rate_prior"] = state["no_goal_rate"]
                output.append(values)

            # The entire date enters history only after all target rows are emitted.
            for row in day_rows.itertuples(index=False):
                classification = classifications.loc[row.match_id]
                if classification in {"NOT_CHECKABLE", "AMBIGUOUS_FIRST_SIDE"}:
                    continue
                home = history[row.home_team_id]
                away = history[row.away_team_id]
                home["eligible"] += 1
                away["eligible"] += 1
                if classification == "SCORED_FIRST_HOME":
                    home["scored"] += 1
                    away["conceded"] += 1
                elif classification == "SCORED_FIRST_AWAY":
                    away["scored"] += 1
                    home["conceded"] += 1
                elif classification == "NO_GOAL":
                    home["no_goal"] += 1
                    away["no_goal"] += 1
                else:
                    raise FirstScoreProfileError(
                        f"Unhandled classification: {classification}"
                    )

    result = pd.DataFrame(output, columns=OUTPUT_COLUMNS)
    _validate_result(result, matches=ordered)
    return result


def _validate_result(result: pd.DataFrame, *, matches: pd.DataFrame) -> None:
    if tuple(result.columns) != OUTPUT_COLUMNS:
        raise FirstScoreProfileError("Output schema differs from frozen contract")
    if len(result) != len(matches) or result.match_id.duplicated().any():
        raise FirstScoreProfileError("Output must preserve one row per target match")
    expected_order = matches.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if result.match_id.tolist() != expected_order.match_id.tolist():
        raise FirstScoreProfileError("Output order must be match_date, match_id")
    expected_identity = expected_order.copy()
    expected_identity["match_date"] = expected_identity.match_date.map(
        lambda value: value.isoformat()
    )
    pd.testing.assert_frame_equal(
        result.loc[:, OUTPUT_COLUMNS[:5]].reset_index(drop=True),
        expected_identity.loc[:, OUTPUT_COLUMNS[:5]].reset_index(drop=True),
        check_dtype=False,
        obj="first-score output identity",
    )
    for side in ("home", "away"):
        available = result[f"{side}_first_score_available"]
        eligible = result[f"{side}_prior_first_score_eligible_matches"]
        scored = result[f"{side}_prior_scored_first_matches"]
        conceded = result[f"{side}_prior_conceded_first_matches"]
        no_goal = result[f"{side}_prior_no_goal_matches"]
        counts = pd.concat([eligible, scored, conceded, no_goal], axis=1)
        if counts.isna().any().any() or counts.lt(0).any().any():
            raise FirstScoreProfileError("First-score counters must be nonnegative")
        if not all(float(value).is_integer() for value in counts.to_numpy().flat):
            raise FirstScoreProfileError("First-score counters must be integers")
        if (eligible != scored + conceded + no_goal).any():
            raise FirstScoreProfileError("First-score denominator invariant failed")
        if (available != eligible.gt(0)).any():
            raise FirstScoreProfileError("Availability/count semantics mismatch")
        rates = result.loc[
            :,
            [
                f"{side}_scored_first_rate_prior",
                f"{side}_conceded_first_rate_prior",
                f"{side}_no_goal_rate_prior",
            ],
        ]
        if rates.loc[available].isna().any().any():
            raise FirstScoreProfileError("Available row has a null rate")
        if rates.loc[~available].notna().any().any():
            raise FirstScoreProfileError("Unavailable row has a non-null rate")
        for value in rates.loc[available].to_numpy().flat:
            if not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
                raise FirstScoreProfileError("Rate is not finite in [0, 1]")
        sums = rates.loc[available].sum(axis=1)
        if not sums.map(lambda value: math.isclose(value, 1.0, abs_tol=1e-12)).all():
            raise FirstScoreProfileError("First-score rates do not sum to one")


def _validate_full_source(
    matches: pd.DataFrame, events: pd.DataFrame, classifications: pd.DataFrame
) -> None:
    if len(matches) != 3208 or matches.match_id.nunique() != 3208:
        raise FirstScoreProfileError("Full target universe is not 3,208 matches")
    if set(matches.season.astype(int)) != set(EXPECTED):
        raise FirstScoreProfileError("Full target seasons are not 2015-2024")
    if len(events) != 8377:
        raise FirstScoreProfileError(f"Expected 8,377 GOAL rows, got {len(events)}")
    if events.match_id.nunique() != 2958:
        raise FirstScoreProfileError("Expected 2,958 GOAL matches")
    if len(matches) - events.match_id.nunique() != 250:
        raise FirstScoreProfileError("Expected 250 zero-GOAL matches")
    counts = Counter(classifications.classification)
    if counts["NO_GOAL"] != 250:
        raise FirstScoreProfileError("Expected 250 NO_GOAL classifications")
    if counts["SCORED_FIRST_HOME"] + counts["SCORED_FIRST_AWAY"] != 2957:
        raise FirstScoreProfileError("Expected 2,957 usable unique first sides")
    if counts["AMBIGUOUS_FIRST_SIDE"] != 0:
        raise FirstScoreProfileError("Expected zero historical ambiguous first sides")
    not_checkable = set(
        classifications.loc[
            classifications.classification.eq("NOT_CHECKABLE"), "match_id"
        ]
    )
    if not_checkable != {"25153"}:
        raise FirstScoreProfileError("25153 must be the sole NOT_CHECKABLE match")


def materialization_summary(
    matches: pd.DataFrame,
    events: pd.DataFrame,
    result: pd.DataFrame,
    classifications: pd.DataFrame,
) -> dict:
    joined = matches.loc[:, ["match_id", "season"]].merge(
        classifications, on="match_id", validate="one_to_one"
    )
    availability = {}
    for season, rows in result.groupby("season", sort=True):
        home = rows.home_first_score_available.astype(bool)
        away = rows.away_first_score_available.astype(bool)
        availability[str(int(season))] = {
            "total": len(rows),
            "home_available": int(home.sum()),
            "away_available": int(away.sum()),
            "pair_available": int((home & away).sum()),
            "either_unavailable": int((~(home & away)).sum()),
            "both_unavailable": int((~home & ~away).sum()),
        }
    by_season_classification = {
        str(int(season)): {
            name: int((rows.classification == name).sum())
            for name in CLASSIFICATIONS
        }
        for season, rows in joined.groupby("season", sort=True)
    }
    return {
        "target_rows": len(result),
        "goal_rows": len(events),
        "goal_matches": events.match_id.nunique(),
        "zero_goal_matches": len(matches) - events.match_id.nunique(),
        "classification": {
            name: int((classifications.classification == name).sum())
            for name in CLASSIFICATIONS
        },
        "classification_by_season": by_season_classification,
        "availability_by_season": availability,
    }


def materialize_first_score_features(
    *,
    j1_dir: str | Path = J1_DIR,
    event_path: str | Path = EVENT_PATH,
    output_path: str | Path = OUTPUT_PATH,
) -> pd.DataFrame:
    """Validate and materialize the frozen 2015-2024 feature artifact."""
    matches = load_j1_matches(j1_dir=j1_dir)
    events = load_goal_events(event_path=event_path)
    classifications = classify_first_score(matches, events)
    _validate_full_source(matches, events, classifications)
    result = build_first_score_features(matches, events)
    output = Path(output_path)
    if output.exists():
        raise FirstScoreProfileError(
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
    materialized = materialize_first_score_features()
    loaded_matches = load_j1_matches()
    loaded_events = load_goal_events()
    loaded_classifications = classify_first_score(loaded_matches, loaded_events)
    summary = materialization_summary(
        loaded_matches, loaded_events, materialized, loaded_classifications
    )
    summary["output"] = str(OUTPUT_PATH)
    summary["output_sha256"] = hashlib.sha256(OUTPUT_PATH.read_bytes()).hexdigest()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
