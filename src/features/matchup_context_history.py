"""Continue H2H and team/stadium form across all completed-match histories."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR, load_elo_history_with_ongoing
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS, add_matchup_context_features


@dataclass
class OngoingMatchupContextHistory:
    """Original source-specific frames with only nine context columns added."""

    historical: pd.DataFrame
    hyakunen: pd.DataFrame
    ongoing: pd.DataFrame


def load_matchup_context_history_with_ongoing(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> OngoingMatchupContextHistory:
    """Compute context once across historical, Hyakunen and ongoing matches.

    Reuse the Elo loader's completed rows and chronological order. Concatenate
    only the seven required inputs, preserving stadium strings as supplied.
    Attach the nine features by position to independent copies of the original
    frames, keeping their schemas, dtypes, indices and row order unchanged.
    Empty ongoing history is supported. No files are written or data fetched.
    """
    history = load_elo_history_with_ongoing(processed_dir, team_master=team_master)
    frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    if any(set(MATCHUP_CONTEXT_COLUMNS) & set(frame.columns) for frame in frames):
        raise ValueError("Matchup context output columns already exist.")
    inputs = [
        "match_date", "home_team_id", "away_team_id", "stadium",
        "home_score", "away_score", "result",
    ]
    # Historical and Hyakunen are required by the loader; ongoing may be empty.
    combined = pd.concat(
        [frame.loc[:, inputs] for frame in frames if not frame.empty], ignore_index=True,
    )
    features = add_matchup_context_features(combined).loc[:, list(MATCHUP_CONTEXT_COLUMNS)]
    outputs = []
    start = 0
    for frame in frames:
        output = frame.copy(deep=True)
        stop = start + len(frame)
        for column in MATCHUP_CONTEXT_COLUMNS:
            output[column] = features[column].iloc[start:stop].to_numpy(copy=True)
        outputs.append(output)
        start = stop
    return OngoingMatchupContextHistory(*outputs)
