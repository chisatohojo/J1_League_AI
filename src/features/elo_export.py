"""Export the existing completed-match Elo replay as two deterministic CSVs."""

from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster, load_team_master
from src.features.elo_history import DEFAULT_PROCESSED_DIR, load_elo_history_with_ongoing


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data/processed/elo"
MATCH_COLUMNS = (
    "match_id", "match_date", "competition", "season", "home_team", "away_team",
    "home_team_id", "away_team_id", "home_elo", "away_elo", "elo_diff", "result",
)
RATING_COLUMNS = ("team_id", "canonical_name", "rating", "last_match_date")


def export_elo_history(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR, team_master: TeamMaster | None = None,
) -> tuple[Path, Path]:
    """Replay saved inputs and return the written match-history/current paths.

    Keep the loader's row order and pre-match values verbatim. The current
    snapshot includes every registered ID, even clubs absent from 2026/27.
    Dates describe each club's last processed match, not the observation time;
    an ID that has never played has a blank date and its initial rating.

    UTF-8, LF, fixed columns, ISO dates and 17 significant float digits make
    re-export deterministic and preserve binary64 values on round-trip reads.
    Only the two output files are written; no fetch or source update occurs.
    """
    master = load_team_master() if team_master is None else team_master
    history = load_elo_history_with_ongoing(processed_dir, team_master=master)
    parts = (history.historical, history.hyakunen, history.ongoing)
    matches = pd.concat(
        [part.matches.loc[:, list(MATCH_COLUMNS)] for part in parts if not part.matches.empty],
        ignore_index=True,
    )

    last_dates = {}
    for row in matches.itertuples(index=False):
        last_dates[row.home_team_id] = row.match_date
        last_dates[row.away_team_id] = row.match_date
    names = {alias.team_id: alias.canonical_name for alias in master.aliases}
    current = pd.DataFrame([
        (team_id, names[team_id], history.ongoing.final_ratings[team_id],
         last_dates.get(team_id, pd.NaT))
        for team_id in sorted(names)
    ], columns=RATING_COLUMNS)

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    paths = (directory / "match_elo_history.csv", directory / "current_ratings.csv")
    for frame, path in zip((matches, current), paths):
        frame.to_csv(
            path, index=False, encoding="utf-8", lineterminator="\n",
            date_format="%Y-%m-%d", float_format="%.17g", na_rep="",
        )
    return paths
