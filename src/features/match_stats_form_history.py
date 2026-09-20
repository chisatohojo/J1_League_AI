"""Load completed J1 match-stat files and compute one continuous history."""

from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from src.collect.jleague_match_stats_season import EXPECTED_MATCH_COUNTS, SEASON_OUTPUT_COLUMNS
from src.collect.matches import load_matches
from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS, add_match_stats_form_features


SEASONS = tuple(range(2015, 2026))
STATS_COLUMNS = (
    "home_shots", "away_shots", "home_ck", "away_ck", "home_fk", "away_fk",
)
OUTPUT_COLUMNS = (
    "match_id", "match_date", "season", "home_team_id", "away_team_id",
    *MATCH_STATS_FORM_COLUMNS,
)


def load_match_stats_form_history(
    *, window: int = 5,
    matches_dir: str | Path = "data/processed/jleague",
    stats_dir: str | Path = "data/processed/jleague_match_stats",
) -> pd.DataFrame:
    """Return 2015--2025 rows with one continuous pre-match stats history.

    Each season is validated and joined by ``match_id`` before all seasons are
    concatenated in the existing match-dataset chronology. Season boundaries
    do not reset team histories.
    """
    frames = []
    for season in SEASONS:
        matches = load_matches(Path(matches_dir) / f"{season}_matches_probe.csv")
        stats_path = Path(stats_dir) / f"{season}_match_stats.csv"
        stats = pd.read_csv(stats_path)
        _validate_season(matches, stats, season)
        stats_by_id = stats.copy(deep=True)
        stats_by_id["match_id"] = stats_by_id["match_id"].astype(str)
        stats_by_id = stats_by_id.set_index("match_id")
        selected_columns = ["match_id", "match_date", "season"]
        if {"home_team_id", "away_team_id"}.issubset(matches.columns):
            selected_columns += ["home_team_id", "away_team_id"]
        else:
            selected_columns += ["home_team", "away_team"]
        selected = matches.loc[:, selected_columns].copy(deep=True)
        selected["match_id"] = selected["match_id"].astype(str)
        if "home_team_id" not in selected:
            selected["home_team_id"] = selected["match_id"].map(stats_by_id["home_team_id"])
            selected["away_team_id"] = selected["match_id"].map(stats_by_id["away_team_id"])
        else:
            selected["home_team_id"] = selected["home_team_id"].astype(str)
            selected["away_team_id"] = selected["away_team_id"].astype(str)
        for column in STATS_COLUMNS:
            selected[column] = selected["match_id"].map(stats_by_id[column])
        if selected[list(STATS_COLUMNS)].isna().any().any():
            raise ValueError(f"season={season}: stats join produced missing values.")
        frames.append(selected)

    combined = pd.concat(frames, ignore_index=True)
    if not combined["match_date"].is_monotonic_increasing:
        raise ValueError("Combined match chronology is not ascending.")
    features = add_match_stats_form_features(combined.loc[:, ["match_date", "home_team_id", "away_team_id", *STATS_COLUMNS]], window=window)
    output = combined.loc[:, ["match_id", "match_date", "season", "home_team_id", "away_team_id"]].copy(deep=True)
    for column in MATCH_STATS_FORM_COLUMNS:
        output[column] = features[column].to_numpy(copy=True)
    return output.loc[:, list(OUTPUT_COLUMNS)]


def _validate_season(matches: pd.DataFrame, stats: pd.DataFrame, season: int) -> None:
    expected = EXPECTED_MATCH_COUNTS[season]
    if len(matches) != expected or len(stats) != expected:
        raise ValueError(f"season={season}: expected {expected} rows in both inputs.")
    if tuple(stats.columns) != SEASON_OUTPUT_COLUMNS:
        raise ValueError(f"season={season}: unexpected stats schema.")
    for frame, label in ((matches, "matches"), (stats, "stats")):
        ids = frame["match_id"].astype(str)
        if ids.isna().any() or not ids.is_unique:
            raise ValueError(f"season={season}: {label} match_id must be unique and nonmissing.")
    match_ids = matches["match_id"].astype(str)
    stats_ids = stats["match_id"].astype(str)
    if set(match_ids) != set(stats_ids):
        raise ValueError(f"season={season}: match_id sets do not match.")
    stats_index = stats.copy(deep=True)
    stats_index["match_id"] = stats_ids
    stats_index = stats_index.set_index("match_id")
    if {"home_team_id", "away_team_id"}.issubset(matches.columns):
        for side in ("home", "away"):
            if not matches[f"{side}_team_id"].astype(str).equals(stats_index.loc[match_ids, f"{side}_team_id"].astype(str).reset_index(drop=True)):
                raise ValueError(f"season={season}: {side}_team_id mismatch.")
    for column in STATS_COLUMNS:
        if stats[column].isna().any() or not pd.api.types.is_integer_dtype(stats[column]) or (stats[column] < 0).any():
            raise ValueError(f"season={season}: invalid stats column {column}.")
    if stats["source_url"].isna().any() or stats["source_url"].eq("").any():
        raise ValueError(f"season={season}: source_url contains missing values.")
    url_ids = stats["source_url"].map(lambda value: re.search(r"[?&]match_card_id=([^&]+)", value).group(1) if re.search(r"[?&]match_card_id=([^&]+)", value) else None)
    if not url_ids.astype(str).equals(stats_ids.reset_index(drop=True)):
        raise ValueError(f"season={season}: source_url match_card_id mismatch.")
