"""Select existing pre-match Elo and form values into one row per match."""

from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR
from src.features.form_history import load_form_history_with_ongoing


DATASET_COLUMNS = (
    "match_id", "match_date", "season", "competition",
    "home_team", "away_team", "home_team_id", "away_team_id",
    "home_elo", "away_elo", "elo_diff",
    "home_last5_points", "away_last5_points",
    "home_last5_wins", "away_last5_wins",
    "home_last5_draws", "away_last5_draws",
    "home_last5_losses", "away_last5_losses",
    "home_last5_goals_for", "away_last5_goals_for",
    "home_last5_goals_against", "away_last5_goals_against",
    "result",
)


def load_training_dataset(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Return the fixed 24 columns in historical/Hyakunen/ongoing row order.

    Reuse the completed-match selection and pre-match values from the existing
    form-history loader. result remains the target: 0=away win, 1=draw, 2=home
    win. Select columns before concatenating to exclude scores, PK/extra-time
    results and other source-specific fields. No source frame is modified;
    the returned frame has a fresh RangeIndex. No network or file writes occur.
    """
    history = load_form_history_with_ongoing(processed_dir, team_master=team_master)
    frames = (history.historical, history.hyakunen, history.ongoing)
    # Historical and Hyakunen are required; empty ongoing must not widen dtypes.
    return pd.concat(
        [frame.loc[:, list(DATASET_COLUMNS)] for frame in frames if not frame.empty],
        ignore_index=True,
    )
