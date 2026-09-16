"""Replay completed ordinary J1 matches from 2015-2025 without writing data.

The existing match_date is authoritative here, including match 30700 on
2024-11-22 (second-half resumption). Its features do NOT reconstruct the rating
before the original 2024-08-24 kickoff. No dates or scores are corrected here.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.matches import load_matches, validate_matches
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


def build_elo_history(matches: pd.DataFrame, *, team_master: TeamMaster) -> EloHistory:
    """Replay the supplied history once, starting every registered ID at 1500.

    The input is validated and copied, then sorted by date and lexical match_id.
    The returned index is a fresh RangeIndex. Names and all additional source
    fields are retained. Ratings persist across seasons with no corrections.
    Partial histories are supported for tests, but omit all unsupplied results;
    use load_elo_history for the complete 2015-2025 input set.
    """
    normalized = validate_matches(matches)
    collisions = set(ADDED_COLUMNS) & set(normalized.columns)
    if collisions:
        raise EloHistoryError(f"Elo output columns already exist: {sorted(collisions)}.")
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

    resolved = team_master.add_team_ids(normalized)
    appearances = pd.concat([
        resolved[["match_date", f"{side}_team_id"]].rename(columns={f"{side}_team_id": "team_id"})
        for side in ("home", "away")
    ], ignore_index=True)
    repeated = appearances.duplicated(["match_date", "team_id"], keep=False)
    if repeated.any():
        examples = appearances.loc[repeated].drop_duplicates().head(5).to_dict("records")
        raise EloHistoryError(f"A team_id appears more than once on the same match_date: {examples}.")

    ordered = resolved.sort_values(["match_date", "match_id"], kind="stable").reset_index(drop=True)
    elo = EloRatings(sorted({alias.team_id for alias in team_master.aliases}))
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


def load_elo_history(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> EloHistory:
    """Read all eleven existing yearly CSVs and replay; never save output files.

    Missing files fail explicitly. Only the fixed ordinary-J1 filenames are
    read: special 2026 and ongoing 2026/27 directories are not traversed.
    """
    frames = []
    for season in SEASONS:
        path = Path(processed_dir) / f"{season}_matches_probe.csv"
        frame = load_matches(path)
        if not frame["season"].eq(season).all():
            raise EloHistoryError(f"{path.name} contains rows outside season {season}.")
        frames.append(frame)
    master = load_team_master() if team_master is None else team_master
    return build_elo_history(pd.concat(frames, ignore_index=True), team_master=master)
