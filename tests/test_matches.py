"""Unit tests for loading and validating synthetic completed-match data."""

from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.collect.matches import (
    DEFAULT_MATCHES_PATH,
    REQUIRED_COLUMNS,
    MatchValidationError,
    load_matches,
    validate_matches,
)


TEXT_COLUMNS = ("match_id", "home_team", "away_team", "stadium")
NUMERIC_COLUMNS = ("season", "round", "home_score", "away_score", "result")


@pytest.fixture
def matches() -> pd.DataFrame:
    """Three artificial matches cover home win, draw, and away win."""
    return pd.DataFrame(
        [
            ["001", 2026, 1, "2026-02-14", "クラブA", "クラブB", "会場A", 2, 1, 2],
            ["002", 2026, 2, "2026-02-21", "クラブB", "クラブC", "会場B", 0, 0, 1],
            ["003", 2026, 3, "2026-02-28", "クラブC", "クラブA", "会場C", 1, 3, 0],
        ],
        columns=[
            "match_id", "season", "round", "match_date", "home_team",
            "away_team", "stadium", "home_score", "away_score", "result",
        ],
        dtype=object,
    )


def test_default_path_points_to_project_raw_data() -> None:
    assert DEFAULT_MATCHES_PATH == (
        Path(__file__).resolve().parents[1] / "data" / "raw" / "matches.csv"
    )


@pytest.mark.parametrize("as_string", [False, True], ids=["path", "string"])
def test_load_valid_csv_preserves_ids_quotes_and_source(
    matches: pd.DataFrame, tmp_path: Path, as_string: bool
) -> None:
    matches.loc[0, "stadium"] = '会場A, "メイン"'
    csv_path = tmp_path / "matches.csv"
    matches.to_csv(csv_path, index=False, encoding="utf-8-sig")
    original_bytes = csv_path.read_bytes()

    loaded = load_matches(str(csv_path) if as_string else csv_path)

    assert loaded["match_id"].tolist() == ["001", "002", "003"]
    assert loaded["result"].tolist() == [2, 1, 0]
    assert loaded["home_score"].tolist() == [2, 0, 1]
    assert loaded["stadium"].iloc[0] == '会場A, "メイン"'
    assert loaded["match_date"].tolist() == [
        pd.Timestamp("2026-02-14"), pd.Timestamp("2026-02-21"),
        pd.Timestamp("2026-02-28"),
    ]
    assert loaded["match_date"].dtype == np.dtype("datetime64[ns]")
    for column in NUMERIC_COLUMNS:
        assert loaded[column].dtype == np.dtype("int64")
    for column in TEXT_COLUMNS:
        assert isinstance(loaded[column].dtype, pd.StringDtype)
    assert csv_path.read_bytes() == original_bytes


def test_load_csv_supports_explicit_encoding(
    matches: pd.DataFrame, tmp_path: Path
) -> None:
    csv_path = tmp_path / "matches.csv"
    matches.to_csv(csv_path, index=False, encoding="cp932")

    loaded = load_matches(csv_path, encoding="cp932")

    assert loaded["home_team"].tolist() == matches["home_team"].tolist()


def test_validate_returns_normalized_copy_and_preserves_order_and_extra_columns(
    matches: pd.DataFrame,
) -> None:
    matches = matches.iloc[[2, 0, 1]].copy()
    matches.index = pd.Index([42, 17, 8], name="source_row")
    matches.insert(0, "source_note", [None, "人工データ", "sample"])
    for column in TEXT_COLUMNS:
        matches[column] = matches[column].map(lambda value: f"  {value}\t")
    for column in NUMERIC_COLUMNS:
        matches[column] = matches[column].map(lambda value: f" {value}.0 ")
    original = matches.copy(deep=True)

    validated = validate_matches(matches)

    assert validated is not matches
    assert_frame_equal(matches, original)
    assert validated.index.equals(original.index)
    assert validated.columns.equals(original.columns)
    assert validated["match_id"].tolist() == ["003", "001", "002"]
    assert validated["source_note"].equals(original["source_note"])
    assert validated["result"].tolist() == [0, 2, 1]
    for column in TEXT_COLUMNS:
        assert isinstance(validated[column].dtype, pd.StringDtype)
        assert validated[column].tolist() == original[column].str.strip().tolist()
    for column in NUMERIC_COLUMNS:
        assert validated[column].dtype == np.dtype("int64")
    assert validated["match_date"].dtype == np.dtype("datetime64[ns]")
    assert_frame_equal(validate_matches(validated), validated)


@pytest.mark.parametrize("column", REQUIRED_COLUMNS)
def test_rejects_missing_required_columns(matches: pd.DataFrame, column: str) -> None:
    with pytest.raises(MatchValidationError, match=column):
        validate_matches(matches.drop(columns=[column]))


@pytest.mark.parametrize("column", REQUIRED_COLUMNS)
@pytest.mark.parametrize("value", [None, "", " \t "], ids=["null", "empty", "blank"])
def test_rejects_missing_required_values(
    matches: pd.DataFrame, column: str, value: object
) -> None:
    matches.loc[0, column] = value
    with pytest.raises(MatchValidationError, match=column):
        validate_matches(matches)


@pytest.mark.parametrize(
    ("column", "value"),
    [("stadium", pd.NA), ("home_score", np.nan), ("match_date", pd.NaT)],
)
def test_rejects_pandas_missing_values(
    matches: pd.DataFrame, column: str, value: object
) -> None:
    matches.loc[0, column] = value
    with pytest.raises(MatchValidationError, match=column):
        validate_matches(matches)


def test_rejects_duplicate_match_id_after_trimming(matches: pd.DataFrame) -> None:
    matches.loc[1, "match_id"] = " 001 "
    with pytest.raises(MatchValidationError, match="match_id"):
        validate_matches(matches)


def test_rejects_same_match_with_different_id_and_round(matches: pd.DataFrame) -> None:
    duplicate = matches.iloc[[0]].copy()
    duplicate.loc[0, "match_id"] = "other_id"
    duplicate.loc[0, "round"] = 9
    duplicate.loc[0, "home_team"] = " クラブA "
    duplicate.loc[0, "season"] = "2026"
    combined = pd.concat([matches, duplicate], ignore_index=True)

    with pytest.raises(MatchValidationError):
        validate_matches(combined)


def test_allows_same_teams_on_a_different_date(matches: pd.DataFrame) -> None:
    later_match = matches.iloc[[0]].copy()
    later_match.loc[0, "match_id"] = "004"
    later_match.loc[0, "match_date"] = "2026-09-12"
    later_match.loc[0, "round"] = 30

    validated = validate_matches(pd.concat([matches, later_match], ignore_index=True))

    assert len(validated) == 4


def test_rejects_identical_home_and_away_teams_after_trimming(
    matches: pd.DataFrame,
) -> None:
    matches.loc[0, "away_team"] = " クラブA "
    with pytest.raises(MatchValidationError, match="home_team|away_team"):
        validate_matches(matches)


@pytest.mark.parametrize("column", NUMERIC_COLUMNS)
@pytest.mark.parametrize("value", ["invalid", 1.5, True, np.inf])
def test_rejects_invalid_numeric_values(
    matches: pd.DataFrame, column: str, value: object
) -> None:
    matches.loc[0, column] = value
    with pytest.raises(MatchValidationError, match=column):
        validate_matches(matches)


@pytest.mark.parametrize("value", [str(2**63), 2**63, -(2**63) - 1, "1e1000"])
def test_rejects_numbers_outside_int64(matches: pd.DataFrame, value: object) -> None:
    matches.loc[0, "home_score"] = value
    with pytest.raises(MatchValidationError, match="home_score"):
        validate_matches(matches)


def test_preserves_large_integer_precision(matches: pd.DataFrame) -> None:
    matches.loc[0, "home_score"] = str(2**63 - 1)
    matches.loc[0, "away_score"] = str(2**63 - 2)

    validated = validate_matches(matches)

    assert validated.loc[0, "home_score"] == 2**63 - 1
    assert validated.loc[0, "away_score"] == 2**63 - 2
    assert validated.loc[0, "result"] == 2


@pytest.mark.parametrize("column", ["season", "round"])
@pytest.mark.parametrize("value", [0, -1])
def test_rejects_nonpositive_season_and_round(
    matches: pd.DataFrame, column: str, value: int
) -> None:
    matches.loc[0, column] = value
    with pytest.raises(MatchValidationError, match=column):
        validate_matches(matches)


@pytest.mark.parametrize("column", ["home_score", "away_score"])
def test_rejects_negative_scores(matches: pd.DataFrame, column: str) -> None:
    matches.loc[0, column] = -1
    with pytest.raises(MatchValidationError, match=column):
        validate_matches(matches)


@pytest.mark.parametrize("value", [-1, 3, "Home Win"])
def test_rejects_invalid_result(matches: pd.DataFrame, value: object) -> None:
    matches.loc[0, "result"] = value
    with pytest.raises(MatchValidationError, match="result"):
        validate_matches(matches)


@pytest.mark.parametrize(
    ("home_score", "away_score", "result"),
    [(2, 1, 0), (2, 1, 1), (0, 0, 0), (0, 0, 2), (1, 3, 1), (1, 3, 2)],
)
def test_rejects_score_result_contradictions(
    matches: pd.DataFrame, home_score: int, away_score: int, result: int
) -> None:
    matches.loc[0, ["home_score", "away_score", "result"]] = [
        home_score, away_score, result,
    ]
    with pytest.raises(MatchValidationError, match="result"):
        validate_matches(matches)


@pytest.mark.parametrize(
    "value",
    [
        "2024-02-29", date(2024, 2, 29), datetime(2024, 2, 29),
        pd.Timestamp("2024-02-29"),
    ],
    ids=["iso_string", "date", "datetime", "timestamp"],
)
def test_accepts_supported_calendar_dates(matches: pd.DataFrame, value: object) -> None:
    matches.loc[0, "match_date"] = value
    validated = validate_matches(matches)
    assert validated.loc[0, "match_date"] == pd.Timestamp("2024-02-29")
    assert validated["match_date"].dtype == np.dtype("datetime64[ns]")


@pytest.mark.parametrize(
    "value",
    [
        "not-a-date", "2026-02-30", "2025-02-29", "2026-13-01",
        "02/03/2026", "2026-2-14", "2026-02-14T00:00:00",
        "2500-01-01", 20260214, datetime(2026, 2, 14, 12),
        datetime(2026, 2, 14, tzinfo=timezone.utc),
        pd.Timestamp("2026-02-14 00:00:00.000000001"),
    ],
)
def test_rejects_invalid_or_ambiguous_dates(
    matches: pd.DataFrame, value: object
) -> None:
    matches.loc[0, "match_date"] = value
    with pytest.raises(MatchValidationError, match="match_date"):
        validate_matches(matches)


def test_rejects_empty_dataframe(matches: pd.DataFrame) -> None:
    with pytest.raises(MatchValidationError):
        validate_matches(matches.iloc[0:0])


def test_rejects_duplicate_dataframe_columns(matches: pd.DataFrame) -> None:
    duplicate_columns = pd.concat([matches, matches[["stadium"]]], axis=1)
    with pytest.raises(MatchValidationError, match="stadium"):
        validate_matches(duplicate_columns)


def test_validation_failure_does_not_mutate_input(matches: pd.DataFrame) -> None:
    matches.loc[0, "home_team"] = " クラブA "
    matches.loc[0, "home_score"] = "-1"
    original = matches.copy(deep=True)

    with pytest.raises(MatchValidationError):
        validate_matches(matches)

    assert_frame_equal(matches, original)


@pytest.mark.parametrize("content", ["", "\n \n", ",".join(REQUIRED_COLUMNS) + "\n"])
def test_rejects_csv_without_matches(tmp_path: Path, content: str) -> None:
    csv_path = tmp_path / "matches.csv"
    csv_path.write_text(content, encoding="utf-8")
    with pytest.raises(MatchValidationError):
        load_matches(csv_path)


@pytest.mark.parametrize("column_count_change", [-1, 1])
def test_rejects_csv_rows_with_wrong_number_of_fields(
    matches: pd.DataFrame, tmp_path: Path, column_count_change: int
) -> None:
    csv_path = tmp_path / "matches.csv"
    lines = matches.to_csv(index=False).splitlines()
    if column_count_change < 0:
        lines[1] = lines[1].rsplit(",", 1)[0]
    else:
        lines[1] += ",unexpected"
    csv_path.write_text("\n".join(lines), encoding="utf-8")

    with pytest.raises(MatchValidationError):
        load_matches(csv_path)


def test_rejects_duplicate_csv_header(matches: pd.DataFrame, tmp_path: Path) -> None:
    csv_path = tmp_path / "matches.csv"
    duplicate_columns = pd.concat([matches, matches[["stadium"]]], axis=1)
    duplicate_columns.to_csv(csv_path, index=False, encoding="utf-8")
    with pytest.raises(MatchValidationError, match="stadium"):
        load_matches(csv_path)


def test_load_csv_runs_value_validation(matches: pd.DataFrame, tmp_path: Path) -> None:
    csv_path = tmp_path / "matches.csv"
    matches.loc[0, "result"] = 0
    matches.to_csv(csv_path, index=False, encoding="utf-8")
    with pytest.raises(MatchValidationError, match="result"):
        load_matches(csv_path)


def test_missing_csv_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_matches(tmp_path / "missing.csv")
