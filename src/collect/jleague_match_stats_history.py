"""Sequential multi-season wrapper for the verified J1 match-stats collector."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from src.collect.jleague_match_stats_season import (
    EXPECTED_MATCH_COUNTS, SEASON_OUTPUT_COLUMNS,
    collect_match_stats_for_season,
)
from src.collect.matches import load_matches
from src.collect.teams import TeamMaster, load_team_master


YEARS = tuple(range(2016, 2026))


def collect_match_stats_history(
    *,
    years: tuple[int, ...] = YEARS,
    matches_dir: str | Path = "data/processed/jleague",
    raw_dir: str | Path = "data/raw/jleague_match_stats",
    output_dir: str | Path = "data/processed/jleague_match_stats",
    request_interval_seconds: float = 0.25,
    team_master: TeamMaster | None = None,
) -> tuple[dict[int, pd.DataFrame], dict[str, int]]:
    """Collect requested ordinary seasons, reusing valid raw caches."""
    unknown_years = [year for year in years if year not in EXPECTED_MATCH_COUNTS]
    if unknown_years:
        raise ValueError(f"Unsupported ordinary J1 seasons: {unknown_years}")
    if 2015 in years:
        raise ValueError("2015 is already complete; do not collect it in this wrapper.")
    master = team_master or load_team_master()
    raw_root = Path(raw_dir)
    before = {path.name for path in raw_root.glob("*.html")} if raw_root.exists() else set()
    results: dict[int, pd.DataFrame] = {}
    for year in years:
        try:
            results[year] = collect_match_stats_for_season(
                load_matches(Path(matches_dir) / f"{year}_matches_probe.csv"),
                season=year, raw_dir=raw_root,
                output_path=Path(output_dir) / f"{year}_match_stats.csv",
                request_interval_seconds=request_interval_seconds,
                team_master=master,
            )
        except Exception as error:
            raise RuntimeError(f"season={year}: {error}") from error
    after = {path.name for path in raw_root.glob("*.html")} if raw_root.exists() else set()
    return results, {"network_fetches": len(after - before), "cache_hits": sum(len(frame) for frame in results.values()) - len(after - before)}


def read_completed_2015_stats(
    path: str | Path = "data/processed/jleague_match_stats/2015_match_stats.csv",
) -> pd.DataFrame:
    """Read the already completed 2015 output without fetching anything."""
    result = pd.read_csv(path)
    if tuple(result.columns) != SEASON_OUTPUT_COLUMNS or len(result) != EXPECTED_MATCH_COUNTS[2015]:
        raise ValueError("Completed 2015 match-stats output has an invalid schema or row count.")
    return result
