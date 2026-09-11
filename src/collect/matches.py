"""Load and validate completed J1 matches without modifying the source data."""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

import pandas as pd


REQUIRED_COLUMNS = (
    "match_id", "season", "round", "match_date", "home_team", "away_team",
    "stadium", "home_score", "away_score", "result",
)
TEXT_COLUMNS = ("match_id", "home_team", "away_team", "stadium")
NUMERIC_COLUMNS = ("season", "round", "home_score", "away_score", "result")
DEFAULT_MATCHES_PATH = Path(__file__).resolve().parents[2] / "data/raw/matches.csv"


class MatchValidationError(ValueError):
    """The input does not satisfy the completed-match data contract."""


def load_matches(
    path: str | Path = DEFAULT_MATCHES_PATH, *, encoding: str = "utf-8-sig"
) -> pd.DataFrame:
    """Read a local CSV and return validated, typed matches.

    UTF-8 with or without a BOM is supported by default. CSV values stay as
    strings until validation, preserving identifiers such as ``0001``.
    File access and decoding errors propagate to the caller.
    """
    with Path(path).open(encoding=encoding, newline="") as source:
        reader = csv.reader(source, strict=True)
        try:
            columns = next(reader, [])
            rows = []
            for row in reader:
                if len(row) != len(columns):
                    raise MatchValidationError(
                        f"CSV line {reader.line_num}: expected {len(columns)} "
                        f"columns, found {len(row)}."
                    )
                rows.append(row)
        except csv.Error as exc:
            raise MatchValidationError(
                f"Invalid CSV at line {reader.line_num}: {exc}"
            ) from exc

    return validate_matches(pd.DataFrame(rows, columns=columns))


def _reject_rows(invalid: pd.Series, message: str) -> None:
    """Identify data row positions, independent of the caller's index labels."""
    positions = [str(position) for position, bad in enumerate(invalid, 1) if bad]
    if positions:
        sample = ", ".join(positions[:5])
        suffix = ", ..." if len(positions) > 5 else ""
        raise MatchValidationError(f"{message} (data rows: {sample}{suffix}).")


def _integer_column(values: pd.Series, column: str) -> pd.Series:
    integers = []
    for position, value in enumerate(values, 1):
        try:
            # Decimal avoids rounding a fractional or oversized CSV value
            # through float before deciding whether it is a valid int64.
            number = Decimal(str(value))
            if (
                not number.is_finite()
                or number != number.to_integral_value()
                or not -(2**63) <= number <= 2**63 - 1
            ):
                raise ValueError
            integers.append(int(number))
        except (InvalidOperation, ValueError, OverflowError) as exc:
            raise MatchValidationError(
                f"{column} must be a finite int64 integer (data row: {position})."
            ) from exc
    return pd.Series(integers, index=values.index, dtype="int64")


def _date_column(values: pd.Series) -> pd.Series:
    dates = []
    for position, value in enumerate(values, 1):
        try:
            if isinstance(value, str):
                value = value.strip()
                if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
                    raise ValueError
            elif not isinstance(value, date):
                raise ValueError
            timestamp = pd.Timestamp(value)
            if (
                pd.isna(timestamp)
                or timestamp.tzinfo is not None
                or timestamp != timestamp.normalize()
            ):
                raise ValueError
            dates.append(timestamp.as_unit("ns"))
        except (ValueError, TypeError, OverflowError) as exc:
            raise MatchValidationError(
                "match_date must be a valid YYYY-MM-DD calendar date "
                f"within datetime64[ns] range (data row: {position})."
            ) from exc
    return pd.Series(dates, index=values.index, dtype="datetime64[ns]")


def validate_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized copy or raise :class:`MatchValidationError`.

    Required fields cannot be null or blank. Numeric fields must be finite
    int64 integers; seasons and rounds are positive and scores nonnegative.
    Results are 0 (away win), 1 (draw), or 2 (home win), consistent with scores.
    Dates accept YYYY-MM-DD strings or naive midnight date/datetime values.
    IDs and (season, date, home team, away team) fixtures must be unique.
    Additional columns, index labels, and row/column order are preserved.
    No sorting, imputation, team-alias mapping, or result correction is done.
    """
    if not isinstance(matches, pd.DataFrame):
        raise TypeError("matches must be a pandas DataFrame.")
    if matches.columns.has_duplicates:
        duplicates = matches.columns[matches.columns.duplicated()].tolist()
        raise MatchValidationError(f"Duplicate column names: {duplicates}.")
    missing = [column for column in REQUIRED_COLUMNS if column not in matches]
    if missing:
        raise MatchValidationError(f"Missing required columns: {', '.join(missing)}.")
    if matches.empty:
        raise MatchValidationError("matches must contain at least one data row.")

    normalized = matches.copy(deep=True)
    for column in REQUIRED_COLUMNS:
        values = normalized[column]
        blank = values.astype("string").str.strip().eq("").fillna(False)
        _reject_rows(values.isna() | blank, f"Missing required value in {column}")

    for column in TEXT_COLUMNS:
        normalized[column] = normalized[column].astype("string").str.strip()
    for column in NUMERIC_COLUMNS:
        normalized[column] = _integer_column(normalized[column], column)
    normalized["match_date"] = _date_column(normalized["match_date"])

    for column in ("season", "round"):
        _reject_rows(normalized[column] <= 0, f"{column} must be positive")
    for column in ("home_score", "away_score"):
        _reject_rows(normalized[column] < 0, f"{column} must be nonnegative")
    _reject_rows(~normalized["result"].isin([0, 1, 2]), "result must be 0, 1, or 2")
    expected_result = (
        (normalized["home_score"] > normalized["away_score"]).astype("int64") * 2
        + (normalized["home_score"] == normalized["away_score"]).astype("int64")
    )
    _reject_rows(
        normalized["result"] != expected_result,
        "result contradicts home_score and away_score",
    )
    _reject_rows(
        normalized["home_team"] == normalized["away_team"],
        "home_team and away_team must differ",
    )
    _reject_rows(normalized["match_id"].duplicated(keep=False), "Duplicate match_id")
    _reject_rows(
        normalized.duplicated(
            subset=["season", "match_date", "home_team", "away_team"], keep=False
        ),
        "Duplicate match: season, match_date, home_team, away_team",
    )
    return normalized
