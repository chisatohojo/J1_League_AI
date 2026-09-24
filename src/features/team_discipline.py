"""Leakage-safe current-season J1 team discipline history features."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
import csv
from datetime import date
import json
from pathlib import Path

import pandas as pd

from src.collect.teams import load_team_master


ROOT = Path(__file__).resolve().parents[2]
J1_DIR = ROOT / "data/processed/jleague"
EVENT_PATH = ROOT / "data/processed/sfms02_match_events/2015_2024_j1_match_events.csv"
OUTPUT_PATH = ROOT / "data/processed/features/2015_2024_j1_team_discipline_features.csv"
EXPECTED = {**{year: 306 for year in range(2015, 2021)}, 2021: 380,
            2022: 306, 2023: 306, 2024: 380}
CARD_TYPES = {"YELLOW_CARD", "RED_CARD"}
OUTPUT_COLUMNS = (
    "match_id", "match_date", "season", "home_team_id", "away_team_id",
    "home_discipline_available", "away_discipline_available",
    "home_prior_j1_matches", "away_prior_j1_matches",
    "home_yellow_cards_per_match_prior", "away_yellow_cards_per_match_prior",
    "home_red_cards_per_match_prior", "away_red_cards_per_match_prior",
)


class TeamDisciplineError(ValueError):
    """Invalid source identity, chronology, or feature invariant."""


def _read_csv(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise TeamDisciplineError(f"Invalid CSV columns: {path}")
            return list(reader)
    except OSError as exc:
        raise TeamDisciplineError(f"Missing input: {path}") from exc


def load_j1_matches(*, j1_dir: str | Path = J1_DIR) -> pd.DataFrame:
    master = load_team_master()
    frames = []
    for season, expected in EXPECTED.items():
        rows = _read_csv(Path(j1_dir) / f"{season}_matches_probe.csv")
        if len(rows) != expected:
            raise TeamDisciplineError(f"{season} expected {expected} matches, got {len(rows)}")
        frame = pd.DataFrame(rows)
        required = {"match_id", "season", "match_date", "home_team", "away_team"}
        if required - set(frame.columns) or frame.match_id.duplicated().any():
            raise TeamDisciplineError(f"Invalid J1 identity columns for {season}")
        if set(frame.season.astype(int)) != {season}:
            raise TeamDisciplineError(f"Season mismatch in {season}")
        frame["match_id"] = frame.match_id.astype(str)
        frame["match_date"] = pd.to_datetime(frame.match_date, format="%Y-%m-%d", errors="raise").dt.date
        try:
            frame["home_team_id"] = [master.resolve_team_id(name, source="jleague_data_site", on=day)
                                      for name, day in zip(frame.home_team, frame.match_date)]
            frame["away_team_id"] = [master.resolve_team_id(name, source="jleague_data_site", on=day)
                                      for name, day in zip(frame.away_team, frame.match_date)]
        except Exception as exc:
            raise TeamDisciplineError(f"J1 TeamMaster resolution failed for {season}") from exc
        if (frame.home_team_id == frame.away_team_id).any():
            raise TeamDisciplineError(f"Same-side team identity in {season}")
        frames.append(frame.loc[:, ["match_id", "match_date", "season", "home_team_id", "away_team_id"]])
    result = pd.concat(frames, ignore_index=True)
    if len(result) != 3208 or result.match_id.duplicated().any():
        raise TeamDisciplineError("J1 match universe must contain 3,208 unique matches")
    return result


def load_card_events(*, event_path: str | Path = EVENT_PATH) -> pd.DataFrame:
    rows = _read_csv(Path(event_path))
    required = {"event_id", "match_id", "match_date", "season", "team_id", "side", "event_type"}
    if required - set(rows[0]) if rows else required:
        raise TeamDisciplineError("Event dataset lacks required identity columns")
    frame = pd.DataFrame(rows)
    if frame.event_id.duplicated().any() or frame.match_id.isna().any():
        raise TeamDisciplineError("Event IDs must be unique and match IDs non-null")
    # The frozen event artifact is shared by multiple event-derived features;
    # discipline consumes only card rows and deliberately ignores goals and
    # substitutions after validating the common identity columns.
    frame = frame.loc[frame.event_type.isin(CARD_TYPES)].copy()
    if not frame.side.isin({"home", "away"}).all():
        raise TeamDisciplineError("Invalid event side")
    frame["match_id"] = frame.match_id.astype(str)
    frame["season"] = frame.season.astype(int)
    frame["match_date"] = pd.to_datetime(frame.match_date, format="%Y-%m-%d", errors="raise").dt.date
    return frame


def _validate_event_identity(matches: pd.DataFrame, events: pd.DataFrame) -> None:
    identity = matches.set_index("match_id")
    if not set(events.match_id).issubset(identity.index):
        raise TeamDisciplineError("Card event references a match outside the J1 universe")
    for row in events.itertuples(index=False):
        match = identity.loc[row.match_id]
        if row.season != int(match.season) or row.match_date != match.match_date:
            raise TeamDisciplineError(f"Event date/season mismatch: {row.match_id}")
        expected_team = match[f"{row.side}_team_id"]
        if row.team_id != expected_team:
            raise TeamDisciplineError(f"Event team/side mismatch: {row.match_id}")


def build_team_discipline_features(matches: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Build one pre-match row per match using strictly prior dates.

    Same-date matches are a conservative batch: their events and appearances
    are added only after every feature row for that date is produced.
    """
    required = set(OUTPUT_COLUMNS[:5])
    if required - set(matches.columns) or matches.match_id.duplicated().any():
        raise TeamDisciplineError("Invalid match identity frame")
    matches = matches.copy(deep=True)
    events = events.copy(deep=True)
    # Keep the public builder deterministic for both CSV-loaded data and
    # in-memory fixtures: identity/date validation uses the same types.
    matches["match_id"] = matches.match_id.astype(str)
    matches["season"] = matches.season.astype(int)
    matches["match_date"] = pd.to_datetime(
        matches.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    events["match_id"] = events.match_id.astype(str)
    events["season"] = events.season.astype(int)
    events["match_date"] = pd.to_datetime(
        events.match_date, format="%Y-%m-%d", errors="raise"
    ).dt.date
    _validate_event_identity(matches, events)
    ordered = matches.sort_values(["match_date", "match_id"], kind="mergesort").reset_index(drop=True)
    if ordered.season.astype(int).tolist() != sorted(ordered.season.astype(int).tolist()):
        raise TeamDisciplineError("Input chronology is not season ordered")
    event_by_match = {mid: group for mid, group in events.groupby("match_id", sort=False)}
    history = defaultdict(lambda: {"matches": 0, "yellow": 0, "red": 0})
    output = []
    previous_season = None
    position = 0
    while position < len(ordered):
        day = ordered.iloc[position].match_date
        season = int(ordered.iloc[position].season)
        if previous_season is None or season != previous_season:
            history = defaultdict(lambda: {"matches": 0, "yellow": 0, "red": 0})
            previous_season = season
        end = position
        while end < len(ordered) and ordered.iloc[end].match_date == day:
            end += 1
        day_rows = ordered.iloc[position:end]
        for row in day_rows.itertuples(index=False):
            values = {"match_id": row.match_id, "match_date": row.match_date.isoformat(),
                      "season": season, "home_team_id": row.home_team_id,
                      "away_team_id": row.away_team_id}
            for side in ("home", "away"):
                team = getattr(row, f"{side}_team_id")
                prior = history[team]
                available = prior["matches"] > 0
                values[f"{side}_discipline_available"] = available
                values[f"{side}_prior_j1_matches"] = prior["matches"]
                values[f"{side}_yellow_cards_per_match_prior"] = (
                    prior["yellow"] / prior["matches"] if available else None)
                values[f"{side}_red_cards_per_match_prior"] = (
                    prior["red"] / prior["matches"] if available else None)
            output.append(values)
        # Only after all same-date target rows are emitted may this date enter history.
        for row in day_rows.itertuples(index=False):
            for side in ("home", "away"):
                team = getattr(row, f"{side}_team_id")
                prior = history[team]
                prior["matches"] += 1
            event_rows = event_by_match.get(row.match_id)
            if event_rows is not None:
                for event in event_rows.itertuples(index=False):
                    bucket = history[event.team_id]
                    bucket["yellow"] += int(event.event_type == "YELLOW_CARD")
                    bucket["red"] += int(event.event_type == "RED_CARD")
        position = end
    result = pd.DataFrame(output, columns=OUTPUT_COLUMNS)
    _validate_result(result, matches=ordered)
    return result


def _validate_result(result: pd.DataFrame, *, matches: pd.DataFrame) -> None:
    if len(result) != len(matches) or result.match_id.duplicated().any():
        raise TeamDisciplineError("Output must preserve one row per J1 match")
    if set(result.match_id) != set(matches.match_id):
        raise TeamDisciplineError("Output match IDs differ from J1 universe")
    for side in ("home", "away"):
        available = result[f"{side}_discipline_available"]
        count = result[f"{side}_prior_j1_matches"]
        rates = result[[f"{side}_yellow_cards_per_match_prior", f"{side}_red_cards_per_match_prior"]]
        if (available != count.gt(0)).any() or count.lt(0).any():
            raise TeamDisciplineError("Availability/count semantics mismatch")
        if rates.loc[available].isna().any().any() or rates.loc[~available].notna().any().any():
            raise TeamDisciplineError("Missing-history rate semantics mismatch")
        if rates.loc[available].lt(0).any().any():
            raise TeamDisciplineError("Negative discipline rate")


def materialize_team_discipline_features(*, j1_dir: str | Path = J1_DIR,
                                          event_path: str | Path = EVENT_PATH,
                                          output_path: str | Path = OUTPUT_PATH) -> pd.DataFrame:
    matches = load_j1_matches(j1_dir=j1_dir)
    events = load_card_events(event_path=event_path)
    result = build_team_discipline_features(matches, events)
    output = Path(output_path)
    if output.exists():
        raise TeamDisciplineError(f"Output already exists; refusing overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as handle:
        result.to_csv(handle, index=False)
    return result


if __name__ == "__main__":
    result = materialize_team_discipline_features()
    print(json.dumps({"rows": len(result), "output": str(OUTPUT_PATH)}, ensure_ascii=False))
