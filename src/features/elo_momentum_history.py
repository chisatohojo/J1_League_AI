"""Continue pre-match Elo momentum across all three completed-match histories."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR, load_elo_history_with_ongoing
from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS, add_elo_momentum_features


@dataclass
class OngoingEloMomentumHistory:
    """Original source-specific frames with five Elo momentum columns added."""

    historical: pd.DataFrame
    hyakunen: pd.DataFrame
    ongoing: pd.DataFrame


def load_elo_momentum_history_with_ongoing(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> OngoingEloMomentumHistory:
    """Compute momentum once across historical, Hyakunen and ongoing rows.

    Reuse the Elo loader's completed rows, pre-match ratings and chronology.
    Pass only dates, team IDs and pre-match Elo to the existing momentum API;
    results and scores are excluded, with no additional Elo updates. Attach
    five features by position to independent source copies, preserving columns,
    dtypes, indices and row order, including an empty ongoing frame. No
    momentum logic is reimplemented, files written or network accessed.
    """
    history = load_elo_history_with_ongoing(processed_dir, team_master=team_master)
    frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    if any(set(ELO_MOMENTUM_COLUMNS) & set(frame.columns) for frame in frames):
        raise ValueError("Elo momentum output columns already exist.")
    inputs = ["match_date", "home_team_id", "away_team_id", "home_elo", "away_elo"]
    # Historical and Hyakunen are required by the loader; ongoing may be empty.
    combined = pd.concat(
        [frame.loc[:, inputs] for frame in frames if not frame.empty], ignore_index=True,
    )
    features = add_elo_momentum_features(combined).loc[:, list(ELO_MOMENTUM_COLUMNS)]
    outputs = []
    start = 0
    for frame in frames:
        output = frame.copy(deep=True)
        stop = start + len(frame)
        for column in ELO_MOMENTUM_COLUMNS:
            output[column] = features[column].iloc[start:stop].to_numpy(copy=True)
        outputs.append(output)
        start = stop
    return OngoingEloMomentumHistory(*outputs)
