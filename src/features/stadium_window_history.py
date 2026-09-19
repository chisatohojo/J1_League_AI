"""Continue configurable team/stadium histories across completed competitions."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR, load_elo_history_with_ongoing
from src.features.stadium_window import STADIUM_WINDOW_COLUMNS, add_stadium_window_features


@dataclass
class OngoingStadiumWindowHistory:
    """Original source-specific frames with six stadium window columns added."""

    historical: pd.DataFrame
    hyakunen: pd.DataFrame
    ongoing: pd.DataFrame


def load_stadium_window_history_with_ongoing(
    window: int, processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    *, team_master: TeamMaster | None = None,
) -> OngoingStadiumWindowHistory:
    """Apply one window calculation across historical, Hyakunen and ongoing rows.

    Reuse the Elo loader's completed rows and chronology. Concatenate only the
    seven required inputs, and forward window unchanged to the existing feature
    function, which owns its validation and calculation. Attach six columns by
    position to independent source copies, preserving schemas, dtypes, indices
    and row order, including empty ongoing data. No stadium normalization,
    feature logic reimplementation, file writes or network access occurs.
    """
    history = load_elo_history_with_ongoing(processed_dir, team_master=team_master)
    frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    if any(set(STADIUM_WINDOW_COLUMNS) & set(frame.columns) for frame in frames):
        raise ValueError("Stadium window output columns already exist.")
    inputs = [
        "match_date", "home_team_id", "away_team_id", "stadium",
        "home_score", "away_score", "result",
    ]
    # Historical and Hyakunen are required by the loader; ongoing may be empty.
    combined = pd.concat(
        [frame.loc[:, inputs] for frame in frames if not frame.empty], ignore_index=True,
    )
    features = add_stadium_window_features(combined, window).loc[:, list(STADIUM_WINDOW_COLUMNS)]
    outputs = []
    start = 0
    for frame in frames:
        output = frame.copy(deep=True)
        stop = start + len(frame)
        for column in STADIUM_WINDOW_COLUMNS:
            output[column] = features[column].iloc[start:stop].to_numpy(copy=True)
        outputs.append(output)
        start = stop
    return OngoingStadiumWindowHistory(*outputs)
