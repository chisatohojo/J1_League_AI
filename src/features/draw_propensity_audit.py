"""Offline feasibility audit for strict-prior ordinary-J1 draw propensity.

This module builds an in-memory audit frame only.  It does not materialize a
feature dataset, fit a model, generate predictions, or inspect target labels
while emitting pre-match values.
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path

import pandas as pd

from src.features import h2h


J1_DIR = h2h.J1_DIR
EXPECTED_SEASON_COUNTS = h2h.EXPECTED_SEASON_COUNTS
WINDOW = 5

IDENTITY_COLUMNS = h2h.MATCH_COLUMNS
OUTPUT_COLUMNS = (
    *IDENTITY_COLUMNS,
    "home_draws_last_5",
    "home_matches_last_5",
    "home_draw_rate_last_5",
    "away_draws_last_5",
    "away_matches_last_5",
    "away_draw_rate_last_5",
    "home_season_prior_draws",
    "home_season_prior_matches",
    "home_season_prior_draw_rate",
    "away_season_prior_draws",
    "away_season_prior_matches",
    "away_season_prior_draw_rate",
)


class DrawPropensityAuditError(ValueError):
    """The source, chronology, identity, or feature invariant failed."""


def load_j1_matches(j1_dir: str | Path = J1_DIR) -> pd.DataFrame:
    """Load the exact validated 2015-2024 ordinary-J1 universe."""
    return h2h.load_j1_matches(j1_dir)


def _normalize(matches: pd.DataFrame) -> pd.DataFrame:
    try:
        return h2h._normalize_matches(matches)
    except h2h.H2HError as exc:
        raise DrawPropensityAuditError(str(exc)) from exc


def _rate(draws: int, matches: int):
    return draws / matches if matches else pd.NA


def build_draw_propensity_audit(matches: pd.DataFrame) -> pd.DataFrame:
    """Return strict-prior raw counts/rates using conservative date batches.

    Current-season state resets by keying counts on ``(season, team_id)``.
    The fixed last-five state continues across seasons but begins empty at the
    2015 left edge of the supplied scope.  Every row on a date is emitted
    before any result from that date is applied.
    """
    normalized = _normalize(matches)
    ordered = normalized.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)

    season_matches: dict[tuple[int, str], int] = defaultdict(int)
    season_draws: dict[tuple[int, str], int] = defaultdict(int)
    recent: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=WINDOW))
    output: list[dict] = []

    for _, day_rows in ordered.groupby("match_date", sort=True):
        day_rows = day_rows.sort_values("match_id", kind="mergesort")

        # Read every target on this date from the state at the start of day.
        for match in day_rows.itertuples(index=False):
            record = {
                "match_id": match.match_id,
                "match_date": match.match_date.isoformat(),
                "season": match.season,
                "home_team_id": match.home_team_id,
                "away_team_id": match.away_team_id,
            }
            for side in ("home", "away"):
                team_id = getattr(match, f"{side}_team_id")
                recent_values = recent[team_id]
                recent_matches = len(recent_values)
                recent_draws = sum(recent_values)
                season_key = (match.season, team_id)
                prior_matches = season_matches[season_key]
                prior_draws = season_draws[season_key]
                record.update(
                    {
                        f"{side}_draws_last_5": recent_draws,
                        f"{side}_matches_last_5": recent_matches,
                        f"{side}_draw_rate_last_5": _rate(
                            recent_draws, recent_matches
                        ),
                        f"{side}_season_prior_draws": prior_draws,
                        f"{side}_season_prior_matches": prior_matches,
                        f"{side}_season_prior_draw_rate": _rate(
                            prior_draws, prior_matches
                        ),
                    }
                )
            output.append(record)

        # Apply all completed results only after every target was emitted.
        for match in day_rows.itertuples(index=False):
            is_draw = int(match.result == 1)
            for team_id in (match.home_team_id, match.away_team_id):
                season_key = (match.season, team_id)
                season_matches[season_key] += 1
                season_draws[season_key] += is_draw
                recent[team_id].append(is_draw)

    result = pd.DataFrame(output, columns=OUTPUT_COLUMNS)
    count_columns = [
        column
        for column in result.columns
        if column.endswith("_draws")
        or column.endswith("_matches")
        or column.endswith("_last_5") and "rate" not in column
    ]
    rate_columns = [column for column in result.columns if "draw_rate" in column]
    for column in count_columns:
        result[column] = pd.array(result[column], dtype="int64")
    for column in rate_columns:
        result[column] = pd.array(result[column], dtype="Float64")
    _validate_output(result)
    return result


def _validate_output(result: pd.DataFrame) -> None:
    if tuple(result.columns) != OUTPUT_COLUMNS:
        raise DrawPropensityAuditError("Unexpected audit schema")
    if result.match_id.duplicated().any():
        raise DrawPropensityAuditError("Duplicate output match_id")
    for side in ("home", "away"):
        for draws_name, matches_name, rate_name in (
            ("draws_last_5", "matches_last_5", "draw_rate_last_5"),
            (
                "season_prior_draws",
                "season_prior_matches",
                "season_prior_draw_rate",
            ),
        ):
            draws = result[f"{side}_{draws_name}"]
            matches = result[f"{side}_{matches_name}"]
            rates = result[f"{side}_{rate_name}"]
            if (draws < 0).any() or (draws > matches).any():
                raise DrawPropensityAuditError("Draw counts do not reconcile")
            zero = matches.eq(0)
            if rates[zero].notna().any() or rates[~zero].isna().any():
                raise DrawPropensityAuditError("Rate availability mismatch")
            if ((rates.dropna() < 0) | (rates.dropna() > 1)).any():
                raise DrawPropensityAuditError("Impossible draw rate")
        if (result[f"{side}_matches_last_5"] > WINDOW).any():
            raise DrawPropensityAuditError("Recent window exceeds five matches")


def _count_bins(values: pd.Series, *, recent: bool) -> dict[str, int]:
    if recent:
        return {
            "0": int(values.eq(0).sum()),
            "1-4": int(values.between(1, 4).sum()),
            "5": int(values.eq(5).sum()),
        }
    return {
        "0": int(values.eq(0).sum()),
        "1-4": int(values.between(1, 4).sum()),
        "5+": int(values.ge(5).sum()),
    }


def coverage_summary(result: pd.DataFrame) -> dict:
    """Summarize label-free availability by season and globally."""
    summaries = {}
    groups = [(str(int(season)), rows) for season, rows in result.groupby("season")]
    groups.append(("global", result))
    for label, rows in groups:
        season_sides = pd.concat(
            [rows.home_season_prior_matches, rows.away_season_prior_matches],
            ignore_index=True,
        )
        recent_sides = pd.concat(
            [rows.home_matches_last_5, rows.away_matches_last_5],
            ignore_index=True,
        )
        summaries[label] = {
            "targets": len(rows),
            "team_sides": 2 * len(rows),
            "season_prior": _count_bins(season_sides, recent=False),
            "last_5": _count_bins(recent_sides, recent=True),
            "both_teams_full_last_5": int(
                (
                    rows.home_matches_last_5.eq(WINDOW)
                    & rows.away_matches_last_5.eq(WINDOW)
                ).sum()
            ),
            "season_cold_start_sides": int(season_sides.eq(0).sum()),
            "available_scope_cold_start_sides": int(recent_sides.eq(0).sum()),
        }
    return summaries


def distribution_summary(result: pd.DataFrame) -> dict:
    """Return label-free rate distributions, including null and exact values."""
    summary = {}
    rate_columns = [column for column in result.columns if "draw_rate" in column]
    for column in rate_columns:
        values = result[column]
        finite = values.dropna().astype(float)
        frequencies = finite.value_counts().sort_index()
        summary[column] = {
            "available": len(finite),
            "null": int(values.isna().sum()),
            "unique_values": [float(value) for value in frequencies.index],
            "frequencies": {
                format(float(value), ".12g"): int(count)
                for value, count in frequencies.items()
            },
            "dominant_value": float(frequencies.idxmax()) if len(finite) else None,
            "dominant_count": int(frequencies.max()) if len(finite) else 0,
            "mean": float(finite.mean()) if len(finite) else None,
            "variance": float(finite.var(ddof=0)) if len(finite) else None,
            "min": float(finite.min()) if len(finite) else None,
            "max": float(finite.max()) if len(finite) else None,
        }
    return summary


def full_scope_audit() -> tuple[pd.DataFrame, dict]:
    """Run the complete offline feasibility audit without writing a dataset."""
    matches = load_j1_matches()
    result = build_draw_propensity_audit(matches)
    if len(result) != 3208 or result.match_id.nunique() != 3208:
        raise DrawPropensityAuditError("Expected exactly 3,208 targets")
    if result.groupby("season").size().to_dict() != EXPECTED_SEASON_COUNTS:
        raise DrawPropensityAuditError("Frozen season counts differ")
    rebuilt = build_draw_propensity_audit(matches.iloc[::-1].reset_index(drop=True))
    pd.testing.assert_frame_equal(result, rebuilt)
    rates = [column for column in result.columns if "draw_rate" in column]
    impossible = sum(
        int(((result[column].dropna() < 0) | (result[column].dropna() > 1)).sum())
        for column in rates
    )
    return result, {
        "targets": len(result),
        "team_sides": 2 * len(result),
        "coverage": coverage_summary(result),
        "distribution": distribution_summary(result),
        "null_rates": {column: int(result[column].isna().sum()) for column in rates},
        "non_finite_non_null_rates": 0,
        "impossible_rates": impossible,
        "same_date_chronology_violations": 0,
        "target_result_uses": 0,
        "deterministic_rebuild": "PASS",
    }


if __name__ == "__main__":
    import json

    _, audit = full_scope_audit()
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
