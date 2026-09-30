"""Materialize the frozen ordinary-J1 team draw-propensity feature family.

Last-five state is owned by :mod:`src.features.form`; this module only adds
current-season strictly-prior draw state and the four frozen symmetric
candidates.  It has no modeling or predictive-evaluation dependencies.
"""

from __future__ import annotations

from collections import defaultdict
import csv
import hashlib
import json
import math
from numbers import Integral
import os
from pathlib import Path
import tempfile

import pandas as pd

from src.collect.matches import MatchValidationError, load_matches, validate_matches
from src.collect.teams import load_team_master
from src.features.form import add_form_features


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
OUTPUT_PATH = (
    ROOT
    / "data/processed/features/2015_2024_j1_draw_propensity_features.csv"
)

EXPECTED_SEASON_COUNTS = {
    **{season: 306 for season in range(2015, 2021)},
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
EXPECTED_COVERAGE = {
    2015: ((18, 72, 522), (18, 72, 522), 261),
    2016: ((18, 72, 522), (3, 12, 597), 293),
    2017: ((18, 72, 522), (2, 8, 602), 297),
    2018: ((18, 72, 522), (1, 4, 607), 301),
    2019: ((18, 72, 522), (1, 4, 607), 301),
    2020: ((18, 72, 522), (1, 4, 607), 301),
    2021: ((20, 80, 660), (1, 4, 755), 375),
    2022: ((18, 72, 522), (1, 4, 607), 301),
    2023: ((18, 72, 522), (0, 0, 612), 306),
    2024: ((20, 80, 660), (2, 8, 750), 370),
}

REQUIRED_INPUT_COLUMNS = (
    "match_id",
    "season",
    "round",
    "match_date",
    "home_team",
    "away_team",
    "stadium",
    "home_score",
    "away_score",
    "result",
    "competition",
    "stage",
    "home_team_id",
    "away_team_id",
)
IDENTITY_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
)
MODEL_CANDIDATES = (
    "mean_draw_rate_last5",
    "abs_draw_rate_diff_last5",
    "mean_season_prior_draw_rate",
    "abs_season_prior_draw_rate_diff",
)
OUTPUT_COLUMNS = (
    *IDENTITY_COLUMNS,
    "home_last5_draws",
    "home_last5_matches",
    "home_last5_draw_rate",
    "away_last5_draws",
    "away_last5_matches",
    "away_last5_draw_rate",
    "home_season_prior_draws",
    "home_season_prior_matches",
    "home_season_prior_draw_rate",
    "away_season_prior_draws",
    "away_season_prior_matches",
    "away_season_prior_draw_rate",
    *MODEL_CANDIDATES,
)


class DrawPropensityError(ValueError):
    """Frozen source, identity, chronology, or output invariant failed."""


def _team_ids_from_master() -> frozenset[str]:
    return frozenset(alias.team_id for alias in load_team_master().aliases)


def _validate_team_id(value, label: str, valid_team_ids: frozenset[str]) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise DrawPropensityError(f"{label} must be an exact nonblank team ID")
    if value not in valid_team_ids:
        raise DrawPropensityError(f"Unknown TeamMaster ID: {value}")
    return value


def _normalize_matches(
    matches: pd.DataFrame, *, valid_team_ids: frozenset[str] | set[str] | None = None
) -> pd.DataFrame:
    """Validate source semantics and return deterministic builder inputs."""
    if not isinstance(matches, pd.DataFrame) or matches.columns.has_duplicates:
        raise DrawPropensityError("Matches must be a DataFrame with unique columns")
    missing = set(REQUIRED_INPUT_COLUMNS) - set(matches.columns)
    if missing:
        raise DrawPropensityError(f"Matches lack required columns: {sorted(missing)}")
    try:
        normalized = validate_matches(matches)
    except MatchValidationError as exc:
        raise DrawPropensityError(str(exc)) from exc

    allowed_ids = (
        _team_ids_from_master()
        if valid_team_ids is None
        else frozenset(valid_team_ids)
    )
    if not allowed_ids:
        raise DrawPropensityError("At least one valid TeamMaster ID is required")

    seen_team_dates: set[tuple[pd.Timestamp, str]] = set()
    records = []
    for row in normalized.loc[:, list(REQUIRED_INPUT_COLUMNS)].itertuples(index=False):
        match_id = str(row.match_id)
        season = int(row.season)
        if season not in EXPECTED_SEASON_COUNTS:
            raise DrawPropensityError(f"Season outside frozen scope: {season}")
        match_date = pd.Timestamp(row.match_date)
        if match_date.year != season:
            raise DrawPropensityError(f"Season/date mismatch: {match_id}")
        home = _validate_team_id(row.home_team_id, "home_team_id", allowed_ids)
        away = _validate_team_id(row.away_team_id, "away_team_id", allowed_ids)
        if home == away:
            raise DrawPropensityError("home_team_id and away_team_id must differ")

        allowed_competition_stage = (
            {("Ｊ１ １ｓｔ", "1st"), ("Ｊ１ ２ｎｄ", "2nd")}
            if season in (2015, 2016)
            else {("Ｊ１", "full_season")}
        )
        if (row.competition, row.stage) not in allowed_competition_stage:
            raise DrawPropensityError(
                f"Non-ordinary-J1 competition/stage: {match_id}"
            )
        for team_id in (home, away):
            key = (match_date, team_id)
            if key in seen_team_dates:
                raise DrawPropensityError(
                    f"Team appears twice on one date: {team_id}/{match_date.date()}"
                )
            seen_team_dates.add(key)

        record = {column: getattr(row, column) for column in REQUIRED_INPUT_COLUMNS}
        record["match_id"] = match_id
        record["home_team_id"] = home
        record["away_team_id"] = away
        records.append(record)

    result = pd.DataFrame(records, columns=REQUIRED_INPUT_COLUMNS)
    return result.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)


def _validate_full_scope(matches: pd.DataFrame) -> None:
    if len(matches) != 3208 or matches.match_id.nunique() != 3208:
        raise DrawPropensityError("Expected exactly 3,208 unique targets")
    observed = matches.groupby("season").size().astype(int).to_dict()
    if observed != EXPECTED_SEASON_COUNTS:
        raise DrawPropensityError(
            f"Frozen season counts differ: {observed} != {EXPECTED_SEASON_COUNTS}"
        )


def load_j1_matches(j1_dir: str | Path = J1_DIR) -> pd.DataFrame:
    """Load exactly the validated ordinary-J1 2015-2024 source universe."""
    master = load_team_master()
    frames = []
    for season in range(2015, 2025):
        path = Path(j1_dir) / f"{season}_matches_probe.csv"
        frame = master.add_team_ids(load_matches(path))
        if not frame.season.eq(season).all():
            raise DrawPropensityError(f"{path.name} contains another season")
        frames.append(frame)
    normalized = _normalize_matches(
        pd.concat(frames, ignore_index=True),
        valid_team_ids=frozenset(alias.team_id for alias in master.aliases),
    )
    _validate_full_scope(normalized)
    return normalized


def _nullable_rate(draws: pd.Series, matches: pd.Series) -> pd.Series:
    return pd.array(draws / matches.mask(matches.eq(0)), dtype="Float64")


def _add_current_season_state(featured: pd.DataFrame) -> pd.DataFrame:
    """Add only current-season draw state with conservative date batches."""
    output = featured.copy(deep=True)
    values = {
        f"{side}_season_prior_{metric}": []
        for side in ("home", "away")
        for metric in ("draws", "matches")
    }
    state_matches: dict[tuple[int, str], int] = defaultdict(int)
    state_draws: dict[tuple[int, str], int] = defaultdict(int)

    for _, day_rows in output.groupby("match_date", sort=True):
        # Read the entire date before applying any result from the date.
        for row in day_rows.itertuples(index=False):
            for side in ("home", "away"):
                key = (row.season, getattr(row, f"{side}_team_id"))
                values[f"{side}_season_prior_draws"].append(state_draws[key])
                values[f"{side}_season_prior_matches"].append(state_matches[key])
        for row in day_rows.itertuples(index=False):
            is_draw = int(row.result == 1)
            for team_id in (row.home_team_id, row.away_team_id):
                key = (row.season, team_id)
                state_matches[key] += 1
                state_draws[key] += is_draw

    for column, column_values in values.items():
        output[column] = pd.array(column_values, dtype="int64")
    return output


def build_draw_propensity_features(
    matches: pd.DataFrame, *, valid_team_ids: frozenset[str] | set[str] | None = None
) -> pd.DataFrame:
    """Build the exact 21-column frozen family without writing or evaluating."""
    ordered = _normalize_matches(matches, valid_team_ids=valid_team_ids)

    # This is the sole last-five implementation and source of truth.
    featured = add_form_features(ordered)
    for side in ("home", "away"):
        featured[f"{side}_last5_matches"] = pd.array(
            featured[f"{side}_last5_wins"]
            + featured[f"{side}_last5_draws"]
            + featured[f"{side}_last5_losses"],
            dtype="int64",
        )
        featured[f"{side}_last5_draw_rate"] = _nullable_rate(
            featured[f"{side}_last5_draws"],
            featured[f"{side}_last5_matches"],
        )

    featured = _add_current_season_state(featured)
    for side in ("home", "away"):
        featured[f"{side}_season_prior_draw_rate"] = _nullable_rate(
            featured[f"{side}_season_prior_draws"],
            featured[f"{side}_season_prior_matches"],
        )

    featured["mean_draw_rate_last5"] = pd.array(
        (featured.home_last5_draw_rate + featured.away_last5_draw_rate) / 2,
        dtype="Float64",
    )
    featured["abs_draw_rate_diff_last5"] = pd.array(
        (featured.home_last5_draw_rate - featured.away_last5_draw_rate).abs(),
        dtype="Float64",
    )
    featured["mean_season_prior_draw_rate"] = pd.array(
        (
            featured.home_season_prior_draw_rate
            + featured.away_season_prior_draw_rate
        )
        / 2,
        dtype="Float64",
    )
    featured["abs_season_prior_draw_rate_diff"] = pd.array(
        (
            featured.home_season_prior_draw_rate
            - featured.away_season_prior_draw_rate
        ).abs(),
        dtype="Float64",
    )

    featured["match_id"] = featured.match_id.astype(str)
    featured["match_date"] = featured.match_date.dt.strftime("%Y-%m-%d")
    result = featured.loc[:, list(OUTPUT_COLUMNS)].copy()
    _validate_output(result, form_source=featured)
    return result


def _validate_output(result: pd.DataFrame, *, form_source: pd.DataFrame) -> None:
    if tuple(result.columns) != OUTPUT_COLUMNS:
        raise DrawPropensityError("Output does not have the frozen 21-column schema")
    if result.match_id.duplicated().any() or len(result) != len(form_source):
        raise DrawPropensityError("Output target identity is not one-to-one")
    if "result" in result or "home_score" in result or "away_score" in result:
        raise DrawPropensityError("Target result or score leaked into output")

    for side in ("home", "away"):
        if not result[f"{side}_last5_draws"].equals(
            form_source[f"{side}_last5_draws"]
        ):
            raise DrawPropensityError("Last-five draw count differs from form")
        expected_matches = (
            form_source[f"{side}_last5_wins"]
            + form_source[f"{side}_last5_draws"]
            + form_source[f"{side}_last5_losses"]
        )
        if not result[f"{side}_last5_matches"].equals(expected_matches):
            raise DrawPropensityError("Last-five denominator differs from form W/D/L")
        if (result[f"{side}_last5_matches"] > 5).any():
            raise DrawPropensityError("Last-five denominator exceeds five")

        for prefix in ("last5", "season_prior"):
            draws = result[f"{side}_{prefix}_draws"]
            matches = result[f"{side}_{prefix}_matches"]
            rate = result[f"{side}_{prefix}_draw_rate"]
            if (draws < 0).any() or (draws > matches).any():
                raise DrawPropensityError("Draw count does not reconcile")
            zero = matches.eq(0)
            if rate[zero].notna().any() or rate[~zero].isna().any():
                raise DrawPropensityError("Rate null does not match denominator")
            finite = rate.dropna().astype(float)
            if (
                not finite.map(math.isfinite).all()
                or not finite.between(0, 1).all()
            ):
                raise DrawPropensityError("Rate is non-finite or outside [0,1]")

    pairs = (
        ("home_last5_draw_rate", "away_last5_draw_rate", MODEL_CANDIDATES[:2]),
        (
            "home_season_prior_draw_rate",
            "away_season_prior_draw_rate",
            MODEL_CANDIDATES[2:],
        ),
    )
    for home_column, away_column, (mean_column, difference_column) in pairs:
        home, away = result[home_column], result[away_column]
        expected_null = home.isna() | away.isna()
        for column in (mean_column, difference_column):
            if not result[column].isna().equals(expected_null):
                raise DrawPropensityError("Derived candidate null propagation failed")
        expected_mean = (home + away) / 2
        expected_difference = (home - away).abs()
        if not result[mean_column].equals(expected_mean):
            raise DrawPropensityError("Derived mean differs from frozen formula")
        if not result[difference_column].equals(expected_difference):
            raise DrawPropensityError(
                "Derived absolute difference differs from frozen formula"
            )


def _count_bins(values: pd.Series, *, last_five: bool) -> tuple[int, int, int]:
    return (
        int(values.eq(0).sum()),
        int(values.between(1, 4).sum()),
        int(values.eq(5).sum() if last_five else values.ge(5).sum()),
    )


def coverage_summary(result: pd.DataFrame, *, frozen: bool = False) -> dict:
    """Return season/global source coverage and optionally assert references."""
    summary = {}
    groups = [(int(season), rows) for season, rows in result.groupby("season")]
    for season, rows in groups:
        season_values = pd.concat(
            [rows.home_season_prior_matches, rows.away_season_prior_matches],
            ignore_index=True,
        )
        last5_values = pd.concat(
            [rows.home_last5_matches, rows.away_last5_matches], ignore_index=True
        )
        observed = {
            "targets": len(rows),
            "team_sides": 2 * len(rows),
            "season_prior_0_1_4_5_plus": _count_bins(
                season_values, last_five=False
            ),
            "last5_0_1_4_5": _count_bins(last5_values, last_five=True),
            "both_full_last5": int(
                (rows.home_last5_matches.eq(5) & rows.away_last5_matches.eq(5)).sum()
            ),
        }
        if frozen:
            expected = EXPECTED_COVERAGE[season]
            if (
                observed["targets"] != EXPECTED_SEASON_COUNTS[season]
                or observed["season_prior_0_1_4_5_plus"] != expected[0]
                or observed["last5_0_1_4_5"] != expected[1]
                or observed["both_full_last5"] != expected[2]
            ):
                raise DrawPropensityError(
                    f"Frozen coverage differs for {season}: {observed}"
                )
        summary[str(season)] = observed

    global_season = tuple(
        sum(values["season_prior_0_1_4_5_plus"][index] for values in summary.values())
        for index in range(3)
    )
    global_last5 = tuple(
        sum(values["last5_0_1_4_5"][index] for values in summary.values())
        for index in range(3)
    )
    global_both = sum(values["both_full_last5"] for values in summary.values())
    summary["global"] = {
        "targets": len(result),
        "team_sides": 2 * len(result),
        "season_prior_0_1_4_5_plus": global_season,
        "last5_0_1_4_5": global_last5,
        "both_full_last5": global_both,
    }
    if frozen and (global_season, global_last5, global_both) != (
        (184, 736, 5496),
        (30, 120, 6266),
        3106,
    ):
        raise DrawPropensityError("Frozen global coverage differs")
    return summary


def candidate_distributions(result: pd.DataFrame) -> dict:
    """Return label-free distributions for only the four frozen candidates."""
    distributions = {}
    for column in MODEL_CANDIDATES:
        values = result[column]
        finite = values.dropna().astype(float)
        distributions[column] = {
            "non_null": len(finite),
            "null": int(values.isna().sum()),
            "min": float(finite.min()),
            "median": float(finite.median()),
            "mean": float(finite.mean()),
            "max": float(finite.max()),
            "unique": int(finite.nunique()),
        }
    return distributions


def _csv_bytes(result: pd.DataFrame) -> bytes:
    return result.to_csv(
        index=False,
        sep=",",
        quotechar='"',
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        lineterminator="\n",
        na_rep="",
        float_format="%.15g",
    ).encode("utf-8")


def _write_once(result: pd.DataFrame, output_path: str | Path) -> str:
    output = Path(output_path)
    if output.exists():
        raise DrawPropensityError(f"Output already exists; refusing overwrite: {output}")
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
    if output.read_bytes() != content:
        raise DrawPropensityError("Published bytes differ from generated bytes")
    return hashlib.sha256(content).hexdigest()


def materialize_draw_propensity_features(
    *,
    j1_dir: str | Path = J1_DIR,
    output_path: str | Path = OUTPUT_PATH,
) -> tuple[pd.DataFrame, dict]:
    """Validate, rebuild, and atomically publish the frozen feature artifact."""
    matches = load_j1_matches(j1_dir)
    result = build_draw_propensity_features(matches)
    _validate_full_scope(result)
    coverage = coverage_summary(result, frozen=True)
    distributions = candidate_distributions(result)

    rebuilt = build_draw_propensity_features(
        matches.iloc[::-1].reset_index(drop=True)
    )
    first_bytes = _csv_bytes(result)
    rebuilt_bytes = _csv_bytes(rebuilt)
    if first_bytes != rebuilt_bytes:
        raise DrawPropensityError("Reversed-input rebuild is not byte-identical")
    repeated = build_draw_propensity_features(matches.copy(deep=True))
    if first_bytes != _csv_bytes(repeated):
        raise DrawPropensityError("Repeated build is not byte-identical")

    digest = _write_once(result, output_path)
    output = Path(output_path)
    if output.read_bytes() != first_bytes:
        raise DrawPropensityError("Artifact validation failed after publication")
    summary = {
        "status": "READY_TO_FREEZE_DRAW_PROPENSITY_EVALUATION",
        "source_matches": len(matches),
        "team_sides": 2 * len(matches),
        "output": str(output),
        "output_rows": len(result),
        "output_columns": len(result.columns),
        "output_unique_match_ids": int(result.match_id.nunique()),
        "model_candidates": MODEL_CANDIDATES,
        "coverage": coverage,
        "candidate_distributions": distributions,
        "form_reconciliation_rows": len(result),
        "invariant_failures": 0,
        "chronology_violations": 0,
        "deterministic_rebuild": "PASS",
        "byte_identical": "PASS",
        "output_sha256": digest,
        "model_evaluation": "NOT RUN",
    }
    return result, summary


if __name__ == "__main__":
    _, materialization_audit = materialize_draw_propensity_features()
    print(json.dumps(materialization_audit, ensure_ascii=False, indent=2, sort_keys=True))
