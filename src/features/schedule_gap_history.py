"""Continue recorded-match schedule gaps across the three saved histories."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR, load_elo_history_with_ongoing
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS, add_schedule_gap_features


@dataclass
class OngoingScheduleGapHistory:
    """Original source-specific frames with five recorded-match gap columns."""

    historical: pd.DataFrame
    hyakunen: pd.DataFrame
    ongoing: pd.DataFrame


def load_schedule_gap_history_with_ongoing(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> OngoingScheduleGapHistory:
    """Compute schedule gaps once across historical, Hyakunen and ongoing rows.

    Reuse the Elo loader's completed matches and chronological order. These
    gaps cover the supplied recorded-match stream, not true physical rest days.
    Concatenate only dates and team IDs, then attach the five features by
    position to independent source copies. Original columns, dtypes, indices
    and row order remain intact, including an empty ongoing frame. No gap
    calculation is reimplemented; no files are written or data fetched.
    """
    history = load_elo_history_with_ongoing(processed_dir, team_master=team_master)
    frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    if any(set(SCHEDULE_GAP_COLUMNS) & set(frame.columns) for frame in frames):
        raise ValueError("Schedule gap output columns already exist.")
    inputs = ["match_date", "home_team_id", "away_team_id"]
    # Historical and Hyakunen are required by the loader; ongoing may be empty.
    combined = pd.concat(
        [frame.loc[:, inputs] for frame in frames if not frame.empty], ignore_index=True,
    )
    features = add_schedule_gap_features(combined).loc[:, list(SCHEDULE_GAP_COLUMNS)]
    outputs = []
    start = 0
    for frame in frames:
        output = frame.copy(deep=True)
        stop = start + len(frame)
        for column in SCHEDULE_GAP_COLUMNS:
            output[column] = features[column].iloc[start:stop].to_numpy(copy=True)
        outputs.append(output)
        start = stop
    return OngoingScheduleGapHistory(*outputs)
