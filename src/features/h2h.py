"""Materialize frozen strict-prior exact-pair H2H count features."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from numbers import Integral
import os
from pathlib import Path
import tempfile

import pandas as pd

from src.collect.matches import load_matches
from src.collect.teams import load_team_master


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
OUTPUT_PATH = ROOT / "data/processed/features/2015_2024_j1_h2h_features.csv"

EXPECTED_SEASON_COUNTS = {
    **{season: 306 for season in range(2015, 2021)},
    2021: 380,
    2022: 306,
    2023: 306,
    2024: 380,
}
EXPECTED_AVAILABILITY = {
    2015: (153, 153),
    2016: (258, 48),
    2017: (271, 35),
    2018: (285, 21),
    2019: (286, 20),
    2020: (288, 18),
    2021: (356, 24),
    2022: (289, 17),
    2023: (303, 3),
    2024: (343, 37),
}
EXPECTED_PRIOR_COUNT_BINS = {
    "0": 376,
    "1": 376,
    "2": 265,
    "3": 265,
    "4": 224,
    "5-9": 860,
    "10+": 842,
}

MATCH_COLUMNS = (
    "match_id",
    "match_date",
    "season",
    "home_team_id",
    "away_team_id",
)
REQUIRED_INPUT_COLUMNS = (*MATCH_COLUMNS, "result")
MODEL_CANDIDATES = (
    "prior_h2h_match_count",
    "prior_h2h_home_team_win_count",
    "prior_h2h_draw_count",
)
OUTPUT_COLUMNS = (
    *MATCH_COLUMNS,
    "h2h_available",
    "previous_h2h_match_id",
    "previous_h2h_match_date",
    *MODEL_CANDIDATES,
)


class H2HError(ValueError):
    """Frozen source, identity, chronology, or output invariant failed."""


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise H2HError(f"{label} must be nonblank text")
    if value != value.strip() or any(ord(character) < 32 for character in value):
        raise H2HError(f"{label} must be exact nonblank text")
    return value


def _integer(value, label: str) -> int:
    if isinstance(value, bool):
        raise H2HError(f"{label} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise H2HError(f"{label} must be an integer") from exc
    try:
        if float(value) != number:
            raise H2HError(f"{label} must be an integer")
    except (TypeError, ValueError, OverflowError) as exc:
        raise H2HError(f"{label} must be an integer") from exc
    return number


def _date(value, label: str) -> date:
    if not isinstance(value, (str, date, pd.Timestamp)):
        raise H2HError(f"{label} must be an ISO date")
    if isinstance(value, str):
        stripped = value.strip()
        if len(stripped) != 10:
            raise H2HError(f"{label} must be an ISO date")
        value = stripped
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise H2HError(f"{label} must be an ISO date") from exc
    if (
        pd.isna(timestamp)
        or timestamp.tzinfo is not None
        or timestamp != timestamp.normalize()
    ):
        raise H2HError(f"{label} must be an ISO date")
    if isinstance(value, str) and timestamp.strftime("%Y-%m-%d") != value:
        raise H2HError(f"{label} must be an ISO date")
    return timestamp.date()


def _pair_key(home_team_id: str, away_team_id: str) -> tuple[str, str]:
    """Return the exact unordered TeamMaster-ID pair key."""
    home = _text(home_team_id, "home_team_id")
    away = _text(away_team_id, "away_team_id")
    if home == away:
        raise H2HError("home_team_id and away_team_id must differ")
    return tuple(sorted((home, away)))


def _normalize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(matches, pd.DataFrame) or matches.columns.has_duplicates:
        raise H2HError("Matches must be a DataFrame with unique columns")
    missing = set(REQUIRED_INPUT_COLUMNS) - set(matches.columns)
    if missing:
        raise H2HError(f"Matches lack required columns: {sorted(missing)}")

    records = []
    seen_ids = set()
    seen_team_dates = set()
    for raw in matches.loc[:, list(REQUIRED_INPUT_COLUMNS)].to_dict("records"):
        match_id = _text(raw["match_id"], "match_id")
        if match_id in seen_ids:
            raise H2HError(f"Duplicate target match_id: {match_id}")
        match_date = _date(raw["match_date"], "match_date")
        season = _integer(raw["season"], "season")
        if match_date.year != season:
            raise H2HError(f"Target season/date mismatch: {match_id}")
        home = _text(raw["home_team_id"], "home_team_id")
        away = _text(raw["away_team_id"], "away_team_id")
        _pair_key(home, away)
        result = _integer(raw["result"], "result")
        if result not in (0, 1, 2):
            raise H2HError(f"Invalid result class: {match_id}")
        for team_id in (home, away):
            key = (match_date, team_id)
            if key in seen_team_dates:
                raise H2HError(
                    f"Team appears twice on one target date: {match_date}/{team_id}"
                )
            seen_team_dates.add(key)
        seen_ids.add(match_id)
        records.append(
            {
                "match_id": match_id,
                "match_date": match_date,
                "season": season,
                "home_team_id": home,
                "away_team_id": away,
                "result": result,
            }
        )
    return pd.DataFrame(records, columns=REQUIRED_INPUT_COLUMNS)


def _validate_full_scope(matches: pd.DataFrame) -> None:
    if len(matches) != 3208 or matches.match_id.nunique() != 3208:
        raise H2HError("Expected exactly 3,208 unique ordinary-J1 targets")
    observed = matches.groupby("season").size().astype(int).to_dict()
    if observed != EXPECTED_SEASON_COUNTS:
        raise H2HError(
            f"Frozen season counts differ: {observed} != {EXPECTED_SEASON_COUNTS}"
        )


def load_j1_matches(j1_dir: str | Path = J1_DIR) -> pd.DataFrame:
    """Load and validate the exact 2015-2024 ordinary-J1 target universe."""
    master = load_team_master()
    frames = []
    for season in range(2015, 2025):
        path = Path(j1_dir) / f"{season}_matches_probe.csv"
        frame = master.add_team_ids(load_matches(path))
        frames.append(frame.loc[:, list(REQUIRED_INPUT_COLUMNS)])
    normalized = _normalize_matches(pd.concat(frames, ignore_index=True))
    _validate_full_scope(normalized)
    return normalized


def _new_pair_state(pair: tuple[str, str]) -> dict:
    return {
        "total_matches": 0,
        "wins": {pair[0]: 0, pair[1]: 0},
        "draws": 0,
        "latest_match_id": None,
        "latest_match_date": None,
    }


def _update_pair_state(state: dict, match) -> None:
    if match.result == 2:
        state["wins"][match.home_team_id] += 1
    elif match.result == 0:
        state["wins"][match.away_team_id] += 1
    else:
        state["draws"] += 1
    state["total_matches"] += 1
    state["latest_match_id"] = match.match_id
    state["latest_match_date"] = match.match_date
    if (
        sum(state["wins"].values()) + state["draws"]
        != state["total_matches"]
    ):
        raise H2HError("Pair W/D/L state does not reconcile to total matches")


def build_h2h_features(matches: pd.DataFrame) -> pd.DataFrame:
    """Build cumulative exact-pair H2H counts using conservative date batches."""
    normalized = _normalize_matches(matches)
    ordered = normalized.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    states: dict[tuple[str, str], dict] = {}
    output = []

    for _, day_rows in ordered.groupby("match_date", sort=True):
        day_rows = day_rows.sort_values("match_id", kind="mergesort")
        for match in day_rows.itertuples(index=False):
            pair = _pair_key(match.home_team_id, match.away_team_id)
            state = states.get(pair)
            available = state is not None and state["total_matches"] > 0
            output.append(
                {
                    "match_id": match.match_id,
                    "match_date": match.match_date.isoformat(),
                    "season": match.season,
                    "home_team_id": match.home_team_id,
                    "away_team_id": match.away_team_id,
                    "h2h_available": available,
                    "previous_h2h_match_id": (
                        state["latest_match_id"] if available else None
                    ),
                    "previous_h2h_match_date": (
                        state["latest_match_date"].isoformat() if available else None
                    ),
                    "prior_h2h_match_count": (
                        state["total_matches"] if available else 0
                    ),
                    "prior_h2h_home_team_win_count": (
                        state["wins"][match.home_team_id] if available else 0
                    ),
                    "prior_h2h_draw_count": state["draws"] if available else 0,
                }
            )

        # Results become history only after every target on the date is emitted.
        for match in day_rows.itertuples(index=False):
            pair = _pair_key(match.home_team_id, match.away_team_id)
            state = states.setdefault(pair, _new_pair_state(pair))
            _update_pair_state(state, match)

    result = pd.DataFrame(output, columns=OUTPUT_COLUMNS)
    for column in MODEL_CANDIDATES:
        result[column] = result[column].astype("int64")
    _validate_result(result, matches=ordered)
    return result


def _historical_events(matches: pd.DataFrame) -> dict[tuple[str, str], list[dict]]:
    events = defaultdict(list)
    for match in matches.itertuples(index=False):
        events[_pair_key(match.home_team_id, match.away_team_id)].append(
            {
                "match_id": match.match_id,
                "match_date": match.match_date,
                "home_team_id": match.home_team_id,
                "away_team_id": match.away_team_id,
                "result": match.result,
            }
        )
    return events


def _validate_result(result: pd.DataFrame, *, matches: pd.DataFrame) -> dict:
    """Independently validate every output against filtered source history."""
    if not isinstance(result, pd.DataFrame) or tuple(result.columns) != OUTPUT_COLUMNS:
        raise H2HError("Output schema differs from the frozen 11-column contract")
    normalized = _normalize_matches(matches)
    expected_order = normalized.sort_values(
        ["match_date", "match_id"], kind="mergesort"
    ).reset_index(drop=True)
    if len(result) != len(expected_order) or result.match_id.duplicated().any():
        raise H2HError("Output must contain one row per unique target match")
    if result.match_id.astype(str).tolist() != expected_order.match_id.tolist():
        raise H2HError("Output order must be match_date, string match_id")

    actual = result.set_index(result.match_id.astype(str), drop=False)
    if set(actual.index) != set(expected_order.match_id):
        raise H2HError("Output and target match-ID sets differ")
    events = _historical_events(normalized)
    audit = {
        "target_own_result_uses": 0,
        "same_date_result_uses": 0,
        "future_result_uses": 0,
        "latest_previous_mismatches": 0,
        "invariant_failures": 0,
    }

    for target in expected_order.itertuples(index=False):
        row = actual.loc[target.match_id]
        if (
            str(row.match_id) != target.match_id
            or _date(row.match_date, "output match_date") != target.match_date
            or _integer(row.season, "output season") != target.season
            or str(row.home_team_id) != target.home_team_id
            or str(row.away_team_id) != target.away_team_id
        ):
            raise H2HError(f"Output identity differs for {target.match_id}")

        pair = _pair_key(target.home_team_id, target.away_team_id)
        prior = [
            event
            for event in events[pair]
            if event["match_date"] < target.match_date
        ]
        if any(event["match_id"] == target.match_id for event in prior):
            audit["target_own_result_uses"] += 1
        if any(event["match_date"] == target.match_date for event in prior):
            audit["same_date_result_uses"] += 1
        if any(event["match_date"] > target.match_date for event in prior):
            audit["future_result_uses"] += 1

        total = len(prior)
        draws = sum(event["result"] == 1 for event in prior)
        home_wins = 0
        for event in prior:
            if event["result"] == 1:
                continue
            winner = (
                event["home_team_id"]
                if event["result"] == 2
                else event["away_team_id"]
            )
            home_wins += winner == target.home_team_id
        away_wins = total - home_wins - draws
        available = total > 0

        try:
            valid_boolean = (
                not pd.isna(row.h2h_available)
                and row.h2h_available in (True, False)
            )
        except (TypeError, ValueError):
            valid_boolean = False
        if not valid_boolean:
            raise H2HError("h2h_available must be boolean")
        if bool(row.h2h_available) != available:
            raise H2HError(f"Availability mismatch for {target.match_id}")
        for column, expected in (
            ("prior_h2h_match_count", total),
            ("prior_h2h_home_team_win_count", home_wins),
            ("prior_h2h_draw_count", draws),
        ):
            value = row[column]
            if (
                isinstance(value, bool)
                or not isinstance(value, Integral)
                or int(value) != expected
            ):
                raise H2HError(f"Invalid {column} for {target.match_id}")
        if away_wins < 0 or home_wins + draws > total:
            audit["invariant_failures"] += 1

        if not available:
            if (
                pd.notna(row.previous_h2h_match_id)
                or pd.notna(row.previous_h2h_match_date)
            ):
                raise H2HError("No-history target has non-null previous H2H audit")
        else:
            latest = max(
                prior,
                key=lambda event: (event["match_date"], event["match_id"]),
            )
            actual_previous_date = _date(
                row.previous_h2h_match_date, "previous_h2h_match_date"
            )
            if (
                str(row.previous_h2h_match_id) != latest["match_id"]
                or actual_previous_date != latest["match_date"]
                or actual_previous_date >= target.match_date
            ):
                audit["latest_previous_mismatches"] += 1

    if any(audit.values()):
        raise H2HError(f"Independent H2H output audit failed: {audit}")
    return audit


def availability_summary(result: pd.DataFrame, *, frozen: bool = False) -> dict:
    summary = {}
    for season, rows in result.groupby("season", sort=True):
        year = int(season)
        available = rows.h2h_available.astype(bool)
        values = {
            "targets": len(rows),
            "available": int(available.sum()),
            "unavailable": int((~available).sum()),
        }
        if frozen:
            expected_available, expected_unavailable = EXPECTED_AVAILABILITY[year]
            expected = {
                "targets": EXPECTED_SEASON_COUNTS[year],
                "available": expected_available,
                "unavailable": expected_unavailable,
            }
            if values != expected:
                raise H2HError(
                    f"Frozen availability mismatch for {year}: {values} != {expected}"
                )
        summary[str(year)] = values
    if frozen:
        available = sum(values["available"] for values in summary.values())
        unavailable = sum(values["unavailable"] for values in summary.values())
        if (available, unavailable) != (2832, 376):
            raise H2HError("Global availability must be 2,832 / 376")
    return summary


def prior_count_bins(result: pd.DataFrame, *, frozen: bool = False) -> dict:
    counts = result.prior_h2h_match_count
    observed = {
        "0": int(counts.eq(0).sum()),
        "1": int(counts.eq(1).sum()),
        "2": int(counts.eq(2).sum()),
        "3": int(counts.eq(3).sum()),
        "4": int(counts.eq(4).sum()),
        "5-9": int(counts.between(5, 9).sum()),
        "10+": int(counts.ge(10).sum()),
    }
    if frozen and observed != EXPECTED_PRIOR_COUNT_BINS:
        raise H2HError(
            f"Frozen prior-count bins differ: {observed} != {EXPECTED_PRIOR_COUNT_BINS}"
        )
    if sum(observed.values()) != len(result):
        raise H2HError("Prior-count bins do not reconcile to output rows")
    return observed


def candidate_distributions(result: pd.DataFrame) -> dict:
    distributions = {}
    for column in MODEL_CANDIDATES:
        values = result[column]
        if values.isna().any():
            raise H2HError(f"Candidate contains null: {column}")
        distributions[column] = {
            "min": int(values.min()),
            "median": float(values.median()),
            "mean": float(values.mean()),
            "max": int(values.max()),
            "frequency": {
                str(int(value)): int(count)
                for value, count in values.value_counts().sort_index().items()
            },
        }
    return distributions


def _csv_bytes(result: pd.DataFrame) -> bytes:
    return result.to_csv(index=False, lineterminator="\n", na_rep="").encode(
        "utf-8"
    )


def _write_once(result: pd.DataFrame, output_path: str | Path) -> str:
    output = Path(output_path)
    if output.exists():
        raise H2HError(f"Output already exists; refusing overwrite: {output}")
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
        raise H2HError("Written output SHA-256 differs from generated bytes")
    return digest


def materialize_h2h_features(
    *,
    j1_dir: str | Path = J1_DIR,
    output_path: str | Path = OUTPUT_PATH,
) -> tuple[pd.DataFrame, dict]:
    """Validate sources and atomically publish the frozen H2H artifact once."""
    matches = load_j1_matches(j1_dir)
    result = build_h2h_features(matches)
    audit = _validate_result(result, matches=matches)
    availability = availability_summary(result, frozen=True)
    bins = prior_count_bins(result, frozen=True)
    distributions = candidate_distributions(result)

    rebuilt = build_h2h_features(matches.iloc[::-1].reset_index(drop=True))
    if _csv_bytes(result) != _csv_bytes(rebuilt):
        raise H2HError("Rebuild is not byte-identical")
    digest = _write_once(result, output_path)
    summary = {
        "status": "READY_FOR_H2H_EVALUATION_FREEZE",
        "source_matches": len(matches),
        "source_unique_match_ids": int(matches.match_id.nunique()),
        "source_season_counts": {
            str(key): int(value)
            for key, value in matches.groupby("season").size().items()
        },
        "output": str(Path(output_path)),
        "output_rows": len(result),
        "output_unique_match_ids": int(result.match_id.nunique()),
        "exact_schema": tuple(result.columns) == OUTPUT_COLUMNS,
        "availability_by_season": availability,
        "available_global": 2832,
        "unavailable_global": 376,
        "prior_count_bins": bins,
        "candidate_distributions": distributions,
        "latest_h2h_audit": audit,
        "chronology": "PASS",
        "target_home_reorientation": "PASS",
        "invariants": "PASS",
        "deterministic_rebuild": "PASS",
        "output_sha256": digest,
    }
    return result, summary


if __name__ == "__main__":
    _, materialization_audit = materialize_h2h_features()
    print(json.dumps(materialization_audit, ensure_ascii=False, indent=2, sort_keys=True))
