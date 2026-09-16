"""Continue pre-match form across the three existing completed-match histories."""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR, load_elo_history_with_ongoing
from src.features.form import FORM_COLUMNS, add_form_features


@dataclass
class OngoingFormHistory:
    """Source-specific DataFrames with their original schemas plus form columns."""

    historical: pd.DataFrame
    hyakunen: pd.DataFrame
    ongoing: pd.DataFrame


def load_form_history_with_ongoing(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> OngoingFormHistory:
    """Read saved completed matches and compute form once across all intervals.

    Reuse the Elo loader's verified selection and chronological order. Only the
    six form inputs are concatenated, so source-specific columns and dtypes
    never need to be reconciled. Attach form values by position to independent
    copies, preserving each original frame's columns, dtypes, index and order.
    No files are written and no network access or new Elo logic is introduced.
    """
    history = load_elo_history_with_ongoing(processed_dir, team_master=team_master)
    frames = (history.historical.matches, history.hyakunen.matches, history.ongoing.matches)
    inputs = ["match_date", "home_team_id", "away_team_id", "home_score", "away_score", "result"]
    # The loader requires historical and Hyakunen matches; ongoing may be empty.
    combined = pd.concat(
        [frame.loc[:, inputs] for frame in frames if not frame.empty], ignore_index=True,
    )
    features = add_form_features(combined).loc[:, list(FORM_COLUMNS)]
    outputs = []
    start = 0
    for frame in frames:
        output = frame.copy(deep=True)
        stop = start + len(frame)
        for column in FORM_COLUMNS:
            output[column] = features[column].iloc[start:stop].to_numpy(copy=True)
        outputs.append(output)
        start = stop
    return OngoingFormHistory(*outputs)
