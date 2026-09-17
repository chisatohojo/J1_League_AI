"""Continue venue-specific form across all three completed-match histories."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR, load_elo_history_with_ongoing
from src.features.venue_form import VENUE_FORM_COLUMNS, add_venue_form_features


@dataclass
class OngoingVenueFormHistory:
    """Original source-specific frames with only four venue-form columns added."""

    historical: pd.DataFrame
    hyakunen: pd.DataFrame
    ongoing: pd.DataFrame


def load_venue_form_history_with_ongoing(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> OngoingVenueFormHistory:
    """Read saved completed matches and compute venue form once without resets.

    Keep the Elo loader's chronological order. Concatenate only the six inputs
    needed for venue form, then copy the four result columns by position into
    each original frame's copy. Existing columns, dtypes, indices and row order
    remain intact, including an empty ongoing frame. No writes or network I/O.
    """
    history = load_elo_history_with_ongoing(processed_dir, team_master=team_master)
    frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    if any(set(VENUE_FORM_COLUMNS) & set(frame.columns) for frame in frames):
        raise ValueError("Venue form output columns already exist.")
    inputs = ["match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result"]
    # Historical and Hyakunen are required by the loader; ongoing may be empty.
    combined = pd.concat(
        [frame.loc[:, inputs] for frame in frames if not frame.empty], ignore_index=True,
    )
    features = add_venue_form_features(combined).loc[:, list(VENUE_FORM_COLUMNS)]
    outputs = []
    start = 0
    for frame in frames:
        output = frame.copy(deep=True)
        stop = start + len(frame)
        for column in VENUE_FORM_COLUMNS:
            output[column] = features[column].iloc[start:stop].to_numpy(copy=True)
        outputs.append(output)
        start = stop
    return OngoingVenueFormHistory(*outputs)
