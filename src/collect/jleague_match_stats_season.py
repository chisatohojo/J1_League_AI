"""Season-level wrapper around the single-match J.League stats collector."""

from __future__ import annotations

from pathlib import Path
import re
import time

import pandas as pd

from src.collect.jleague_match_stats import OUTPUT_COLUMNS, fetch_match_stats
from src.collect.matches import load_matches
from src.collect.teams import TeamMaster, TeamMasterError, load_team_master

SEASON_OUTPUT_COLUMNS = (
    "match_id", "home_team", "away_team", "home_team_id", "away_team_id",
    "home_shots", "away_shots", "home_ck", "away_ck", "home_fk", "away_fk", "source_url",
)


def collect_match_stats_for_season(
    matches: pd.DataFrame, *, season: int, raw_dir: str | Path,
    output_path: str | Path, request_interval_seconds: float = 0.25,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Collect and validate one season without mutating ``matches``."""
    if season != 2015:
        raise ValueError("This prototype is intentionally limited to 2015.")
    source = matches.copy(deep=True)
    required = {"match_id", "match_date", "home_team", "away_team", "season"}
    if not required.issubset(source.columns):
        raise ValueError("Existing match dataset lacks required columns.")
    source = source.loc[source["season"].eq(season)].copy(deep=True)
    if len(source) != 306 or source["match_id"].isna().any() or not source["match_id"].is_unique:
        raise ValueError("2015 existing dataset must contain 306 unique nonmissing match IDs.")
    source["match_id"] = source["match_id"].astype(str)
    team_master = team_master or load_team_master()

    frames = []
    failures: list[str] = []
    for index, match_id in enumerate(source["match_id"]):
        try:
            frame = fetch_match_stats(match_id, raw_dir=raw_dir)
            if len(frame) != 1:
                raise ValueError("fetch returned other than one row")
            row = frame.iloc[0]
            existing = source.iloc[index]
            match_date = existing["match_date"]
            try:
                existing_home_id = team_master.resolve_team_id(existing["home_team"], source="jleague_data_site", on=match_date)
                existing_away_id = team_master.resolve_team_id(existing["away_team"], source="jleague_data_site", on=match_date)
                stats_home_id = team_master.resolve_team_id(row["home_team"], source="jleague_official", on=match_date)
                stats_away_id = team_master.resolve_team_id(row["away_team"], source="jleague_official", on=match_date)
            except TeamMasterError as error:
                raise ValueError(f"team alias resolution failed on {match_id} ({match_date.date()}): {error}") from error
            if (existing_home_id, existing_away_id) != (stats_home_id, stats_away_id):
                raise ValueError(
                    f"team identity mismatch: existing=({existing_home_id}, {existing_away_id}), "
                    f"official=({stats_home_id}, {stats_away_id})"
                )
            enriched = frame.copy(deep=True)
            enriched.insert(3, "home_team_id", existing_home_id)
            enriched.insert(4, "away_team_id", existing_away_id)
            frames.append(enriched.loc[:, list(SEASON_OUTPUT_COLUMNS)])
        except Exception as error:
            failures.append(f"{match_id}: {error}")
        if index + 1 < len(source) and request_interval_seconds:
            time.sleep(request_interval_seconds)
    if failures:
        raise RuntimeError("2015 match stats collection failed:\n" + "\n".join(failures))

    result = pd.concat(frames, ignore_index=True).loc[:, list(SEASON_OUTPUT_COLUMNS)]
    _validate_result(result, source, team_master=team_master)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, encoding="utf-8")
    return result


def collect_2015_match_stats(
    *, matches_path: str | Path = "data/processed/jleague/2015_matches_probe.csv",
    raw_dir: str | Path = "data/raw/jleague_match_stats",
    output_path: str | Path = "data/processed/jleague_match_stats/2015_match_stats.csv",
    request_interval_seconds: float = 0.25,
    team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    return collect_match_stats_for_season(
        load_matches(Path(matches_path)), season=2015, raw_dir=raw_dir,
        output_path=output_path, request_interval_seconds=request_interval_seconds, team_master=team_master,
    )


def _validate_result(result: pd.DataFrame, source: pd.DataFrame, *, team_master: TeamMaster | None = None) -> None:
    if len(result) != 306 or not result["match_id"].is_unique:
        raise ValueError("Collected result must contain 306 unique rows.")
    if set(result["match_id"]) != set(source["match_id"]):
        raise ValueError("Collected match_id set does not exactly match the existing dataset.")
    merged = source[["match_id", "home_team", "away_team"]].merge(
        result[["match_id", "home_team", "away_team"]], on="match_id", how="outer", suffixes=("_dataset", "_official"), indicator=True,
    )
    if not (merged["_merge"] == "both").all():
        raise ValueError("Collected match_id set has missing or extra IDs.")
    if result[["home_team_id", "away_team_id"]].isna().any().any():
        raise ValueError("Resolved team IDs contain missing values.")
    if (result["home_team_id"] == result["away_team_id"]).any():
        raise ValueError("Home and away team IDs must differ.")
    if result[["home_shots", "away_shots", "home_ck", "away_ck", "home_fk", "away_fk"]].isna().any().any():
        raise ValueError("Collected stats contain missing values.")
    for column in ("home_shots", "away_shots", "home_ck", "away_ck", "home_fk", "away_fk"):
        if not pd.api.types.is_integer_dtype(result[column]) or (result[column] < 0).any():
            raise ValueError(f"{column} must contain nonnegative integers.")
    if result["source_url"].isna().any() or result["source_url"].eq("").any():
        raise ValueError("source_url must be present for every row.")
    url_ids = result["source_url"].map(
        lambda value: re.search(r"[?&]match_card_id=([^&]+)", value).group(1)
        if re.search(r"[?&]match_card_id=([^&]+)", value) else None
    )
    if not url_ids.equals(result["match_id"]):
        raise ValueError("source_url match_card_id does not match match_id.")
