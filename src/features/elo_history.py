"""Replay ordinary J1, Hyakunen 2026, and confirmed ongoing 2026/27 results.

The existing match_date is authoritative here, including match 30700 on
2024-11-22 (second-half resumption). Its features do NOT reconstruct the rating
before the original 2024-08-24 kickoff. No dates or scores are corrected here.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.matches import REQUIRED_COLUMNS, load_matches, validate_matches
from src.collect.jleague_hyakunen import MATCH_DTYPES, validate_competition
from src.collect.jleague_ongoing import COMPLETION_POLICY, FORMAT_VERSION, read_latest
from src.collect.jleague_ongoing_source import COMPETITION_KEY
from src.collect.teams import TeamMaster, load_team_master
from src.features.elo import EloRatings


DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parents[2] / "data/processed/jleague"
SEASONS = tuple(range(2015, 2026))
ADDED_COLUMNS = ("home_team_id", "away_team_id", "home_elo", "away_elo", "elo_diff")


class EloHistoryError(ValueError):
    """Unsupported competition, conflicting chronology, or output columns."""


@dataclass
class EloHistory:
    """Chronological feature rows and a detached final rating for every roster ID."""

    matches: pd.DataFrame
    final_ratings: dict[str, float]


@dataclass
class HyakunenEloHistory:
    """Separate source schemas and independent rating snapshots at each boundary."""

    historical: EloHistory
    hyakunen: EloHistory


@dataclass
class OngoingEloHistory:
    """Detached source-specific histories through the confirmed 2026/27 results."""

    historical: EloHistory
    hyakunen: EloHistory
    ongoing: EloHistory


def _prepare_ordinary_matches(matches: pd.DataFrame, team_master: TeamMaster) -> pd.DataFrame:
    normalized = validate_matches(matches)
    if not {"competition", "stage"}.issubset(normalized.columns):
        raise EloHistoryError("Ordinary J1 input requires competition and stage.")
    if not normalized["season"].isin(SEASONS).all():
        raise EloHistoryError("Only ordinary J1 seasons 2015-2025 are supported.")
    if not normalized["match_date"].dt.year.eq(normalized["season"]).all():
        raise EloHistoryError("Ordinary J1 match_date must be within its season year.")
    for row in normalized[["season", "competition", "stage"]].drop_duplicates().itertuples(index=False):
        allowed = (
            {("Ｊ１ １ｓｔ", "1st"), ("Ｊ１ ２ｎｄ", "2nd")}
            if row.season in (2015, 2016) else {("Ｊ１", "full_season")}
        )
        if (row.competition, row.stage) not in allowed:
            raise EloHistoryError(f"Unsupported competition/stage in season {row.season}.")
    return _order_matches(normalized, team_master)


def _order_matches(normalized: pd.DataFrame, team_master: TeamMaster) -> pd.DataFrame:
    collisions = set(ADDED_COLUMNS) & set(normalized.columns)
    if collisions:
        raise EloHistoryError(f"Elo output columns already exist: {sorted(collisions)}.")
    resolved = team_master.add_team_ids(normalized)
    appearances = pd.concat([
        resolved[["match_date", f"{side}_team_id"]].rename(columns={f"{side}_team_id": "team_id"})
        for side in ("home", "away")
    ], ignore_index=True)
    repeated = appearances.duplicated(["match_date", "team_id"], keep=False)
    if repeated.any():
        examples = appearances.loc[repeated].drop_duplicates().head(5).to_dict("records")
        raise EloHistoryError(f"A team_id appears more than once on the same match_date: {examples}.")

    return resolved.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)


def _replay(ordered: pd.DataFrame, elo: EloRatings) -> EloHistory:
    """Use only each row's 90-minute result; retain the supplied Elo state."""
    ordered = ordered.copy(deep=True)
    home_ratings, away_ratings = [], []
    for row in ordered[["home_team_id", "away_team_id", "result"]].itertuples(index=False):
        before = elo.pre_match(row.home_team_id, row.away_team_id)
        home_ratings.append(before.home_rating)
        away_ratings.append(before.away_rating)
        elo.update(row.home_team_id, row.away_team_id, row.result)
    ordered["home_elo"] = home_ratings
    ordered["away_elo"] = away_ratings
    ordered["elo_diff"] = ordered["home_elo"] - ordered["away_elo"]
    return EloHistory(ordered, elo.ratings)


def build_elo_history(matches: pd.DataFrame, *, team_master: TeamMaster) -> EloHistory:
    """Replay ordinary 2015-2025 history, starting every registered ID at 1500.

    Return a validated copy sorted by date and lexical match_id, with a fresh
    RangeIndex. All source columns remain. Partial histories omit unsupplied
    results; use load_elo_history for the complete eleven-year input set.
    """
    ordered = _prepare_ordinary_matches(matches, team_master)
    return _replay(ordered, EloRatings(sorted({alias.team_id for alias in team_master.aliases})))


def _read_ordinary_matches(processed_dir: str | Path) -> pd.DataFrame:
    frames = []
    for season in SEASONS:
        path = Path(processed_dir) / f"{season}_matches_probe.csv"
        frame = load_matches(path)
        if not frame["season"].eq(season).all():
            raise EloHistoryError(f"{path.name} contains rows outside season {season}.")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def load_elo_history(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> EloHistory:
    """Read all eleven existing yearly CSVs and replay; never save output files.

    Missing files fail explicitly. Only the fixed ordinary-J1 filenames are
    read: special 2026 and ongoing 2026/27 directories are not traversed.
    """
    matches = _read_ordinary_matches(processed_dir)
    master = load_team_master() if team_master is None else team_master
    return build_elo_history(matches, team_master=master)


def build_elo_history_with_hyakunen(
    ordinary_matches: pd.DataFrame, hyakunen_matches: pd.DataFrame, *, team_master: TeamMaster,
) -> HyakunenEloHistory:
    """Continue one Elo instance from ordinary J1 through all 200 special matches.

    Hyakunen input must have the existing normalized schema/MATCH_DTYPES. Its
    own competition validator handles null playoff rounds without inventing a
    round number. PK/ET/tie winners are never Elo inputs. Separate DataFrames
    preserve the exact historical schema and the special competition's fields.
    """
    historical, special = _prepare_history_with_hyakunen(ordinary_matches, hyakunen_matches, team_master)
    elo = EloRatings(sorted({alias.team_id for alias in team_master.aliases}))
    historical_result = _replay(historical, elo)
    special_result = _replay(special, elo)
    return HyakunenEloHistory(historical_result, special_result)


def _prepare_history_with_hyakunen(ordinary_matches, hyakunen_matches, team_master):
    historical = _prepare_ordinary_matches(ordinary_matches, team_master)
    validate_competition(hyakunen_matches)
    special = _order_matches(hyakunen_matches, team_master)
    if set(historical["match_id"]) & set(special["match_id"]):
        raise EloHistoryError("Duplicate match_id across historical and Hyakunen inputs.")
    if historical["match_date"].max() >= special["match_date"].min():
        raise EloHistoryError("Hyakunen matches must follow the historical matches.")
    return historical, special


def _read_hyakunen_matches(path: Path) -> pd.DataFrame:
    """Restore the existing normalized CSV types without reading the tie table."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            columns = next(reader, [])
            if len(columns) != len(set(columns)) or set(MATCH_DTYPES) - set(columns):
                raise EloHistoryError("Invalid Hyakunen normalized CSV header.")
            rows = []
            for row in reader:
                if len(row) != len(columns):
                    raise EloHistoryError(f"Invalid Hyakunen CSV width on line {reader.line_num}.")
                rows.append(row)
    except csv.Error as exc:
        raise EloHistoryError("Invalid Hyakunen CSV.") from exc
    frame = pd.DataFrame(rows, columns=columns, dtype="string").replace("", pd.NA)
    if frame.empty:
        raise EloHistoryError("Hyakunen input must contain the completed competition.")
    for column, dtype in MATCH_DTYPES.items():
        if dtype == "bool":
            if not frame[column].isin(["True", "False"]).all():
                raise EloHistoryError(f"Invalid boolean in {column}.")
            frame[column] = frame[column].map({"True": True, "False": False}).astype(bool)
        elif dtype == "datetime64[ns]":
            if not frame[column].str.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}").fillna(False).all():
                raise EloHistoryError(f"Invalid calendar date in {column}.")
            frame[column] = pd.to_datetime(frame[column], format="%Y-%m-%d").astype(dtype)
        else:
            frame[column] = frame[column].astype(dtype)
    return frame


def load_elo_history_with_hyakunen(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> HyakunenEloHistory:
    """Read only the eleven ordinary CSVs and 2026_hyakunen/matches.csv; no writes.

    playoff_ties.csv and the ongoing 2026/27 data are intentionally not read.
    """
    historical = _read_ordinary_matches(processed_dir)
    special = _read_hyakunen_matches(Path(processed_dir) / "2026_hyakunen/matches.csv")
    master = load_team_master() if team_master is None else team_master
    return build_elo_history_with_hyakunen(historical, special, team_master=master)


def _prepare_ongoing_matches(schedule, team_master, observed_at):
    """Select already-confirmed results; never infer completion from a score."""
    if not isinstance(schedule, pd.DataFrame):
        raise TypeError("schedule must be a pandas DataFrame.")
    required = set(REQUIRED_COLUMNS) | {
        "status", "fixture_key", "competition_key", "competition", "stage",
        "evidence_type", "evidence_url", "evidence_sha256",
        "evidence_fetched_at_utc", "completion_origin_snapshot",
    }
    if schedule.columns.has_duplicates or required - set(schedule.columns):
        raise EloHistoryError("Ongoing input requires the published schedule columns.")
    if not schedule["status"].isin(["scheduled", "candidate", "completed"]).all():
        raise EloHistoryError("Unknown or missing ongoing match status.")
    observed = pd.Timestamp(observed_at)
    if pd.isna(observed) or observed.tzinfo is None:
        raise EloHistoryError("observed_at must be a timezone-aware snapshot timestamp.")
    # The saved observation time, not the wall clock, makes replays reproducible.
    cutoff = observed.tz_convert("Asia/Tokyo").tz_localize(None).normalize()
    selected = schedule.loc[schedule["status"].eq("completed")].copy(deep=True)
    if selected.empty:
        # validate_matches intentionally rejects empty input; retain its contract.
        selected["match_date"] = pd.Series(index=selected.index, dtype="datetime64[ns]")
        selected["match_id"] = selected["match_id"].astype("string")
        return _order_matches(selected, team_master)
    normalized = validate_matches(selected)
    identity = {
        "season": 2026, "competition_key": COMPETITION_KEY,
        "competition": "Ｊ１", "stage": "full_season",
        "evidence_type": "official_game_over_section",
    }
    if any(not normalized[column].eq(value).fillna(False).all() for column, value in identity.items()):
        raise EloHistoryError("Expected confirmed ordinary 2026/27 J1 results.")
    for column in ("fixture_key", "evidence_url", "evidence_sha256",
                   "evidence_fetched_at_utc", "completion_origin_snapshot"):
        if normalized[column].astype("string").str.strip().fillna("").eq("").any():
            raise EloHistoryError(f"Missing completed-match provenance: {column}.")
    keys = normalized["fixture_key"].astype("string")
    if keys.duplicated().any() or not keys.str.fullmatch(r"j1_2026_2027:[a-z0-9_-]+:[a-z0-9_-]+").all():
        raise EloHistoryError("Invalid or duplicate completed fixture_key.")
    dates = normalized["match_date"]
    if not dates.between("2026-08-01", "2027-06-30").all() or dates.gt(cutoff).any():
        raise EloHistoryError("Completed match_date is outside the season or after the snapshot observation.")
    return _order_matches(normalized, team_master)


def build_elo_history_with_ongoing(
    ordinary_matches: pd.DataFrame, hyakunen_matches: pd.DataFrame, schedule: pd.DataFrame,
    *, team_master: TeamMaster, observed_at: str | pd.Timestamp,
) -> OngoingEloHistory:
    """Continue one Elo instance through the completed subset of a saved schedule.

    schedule is already reviewed by the ongoing adapter; this API does not
    establish new official evidence. Only status=completed rows reach result
    validation, team resolution or Elo. observed_at is the saved publication's
    timezone-aware observation time, not today's clock. Dates and lexical IDs
    determine order. All outputs are in memory and previous APIs are unchanged.
    """
    historical, special = _prepare_history_with_hyakunen(ordinary_matches, hyakunen_matches, team_master)
    ongoing = _prepare_ongoing_matches(schedule, team_master, observed_at)
    previous_ids = set(historical["match_id"]) | set(special["match_id"])
    if previous_ids & set(ongoing["match_id"]):
        raise EloHistoryError("Duplicate match_id across prior history and ongoing results.")
    if not ongoing.empty and special["match_date"].max() >= ongoing["match_date"].min():
        raise EloHistoryError("Ongoing results must follow the Hyakunen matches.")
    elo = EloRatings(sorted({alias.team_id for alias in team_master.aliases}))
    historical_result = _replay(historical, elo)
    special_result = _replay(special, elo)
    ongoing_result = _replay(ongoing, elo)
    return OngoingEloHistory(historical_result, special_result, ongoing_result)


def _read_ongoing_csv(path):
    """Read nullable schedule fields without numeric inference or result validation."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, strict=True)
        columns = next(reader, [])
        if not columns or len(columns) != len(set(columns)):
            raise EloHistoryError("Invalid ongoing CSV header.")
        rows = []
        for row in reader:
            if len(row) != len(columns):
                raise EloHistoryError(f"Invalid ongoing CSV width on line {reader.line_num}.")
            rows.append(row)
    return pd.DataFrame(rows, columns=columns, dtype="string")


def load_elo_history_with_ongoing(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> OngoingEloHistory:
    """Read the fixed historical CSVs and one verified latest 2026/27 revision.

    Ignore top-level viewing copies. Check that completed_matches.csv is exactly
    the confirmed schedule subset in the same immutable publication. Never
    fetch, process a snapshot, publish, write data or persist Elo output.
    """
    directory = Path(processed_dir)
    latest = read_latest(directory / "2026_27")
    if latest is None:
        raise FileNotFoundError("No published 2026/27 latest.json.")
    revision, manifest = latest
    if manifest["format_version"] != FORMAT_VERSION or manifest["completion_policy"] != COMPLETION_POLICY:
        raise EloHistoryError("Unsupported ongoing publication format or completion policy.")
    if not {"schedule.csv", "completed_matches.csv"}.issubset(manifest["files"]):
        raise EloHistoryError("Published manifest does not cover both ongoing CSVs.")
    schedule = _read_ongoing_csv(revision / "schedule.csv")
    completed = _read_ongoing_csv(revision / "completed_matches.csv")
    if "status" not in schedule:
        raise EloHistoryError("Published schedule has no status column.")
    expected = schedule.loc[schedule["status"].eq("completed")].reset_index(drop=True)
    if not expected.equals(completed):
        raise EloHistoryError("Published completed_matches.csv disagrees with the schedule subset.")
    historical = _read_ordinary_matches(directory)
    special = _read_hyakunen_matches(directory / "2026_hyakunen/matches.csv")
    master = load_team_master() if team_master is None else team_master
    return build_elo_history_with_ongoing(
        historical, special, schedule, team_master=master,
        observed_at=manifest["summary"]["observed_at_utc"],
    )
