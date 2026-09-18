"""Append recorded-match schedule gaps to the existing matchup training table."""

from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.schedule_gap_history import load_schedule_gap_history_with_ongoing
from src.features.training_dataset import DATASET_COLUMNS
from src.features.training_dataset_matchup import load_training_dataset_with_matchup_context


def load_training_dataset_with_context(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Return the existing 33 columns followed by five unchanged schedule gaps.

    Gaps describe previous recorded matches in the supplied completed-match
    stream, not true physical rest days including unprovided competitions.
    Reuse both loaders with identical arguments and require equal row counts
    and identical ordered, unique match IDs. Append only the five features by
    position, retaining values, dtypes and the base index without sorting or
    recalculating features. Existing loaders read local inputs; no files are
    written, network accessed or models fitted.
    """
    dataset = load_training_dataset_with_matchup_context(processed_dir, team_master=team_master)
    history = load_schedule_gap_history_with_ongoing(processed_dir, team_master=team_master)
    if tuple(dataset.columns) != (*DATASET_COLUMNS, *MATCHUP_CONTEXT_COLUMNS):
        raise ValueError("Expected the original 33 matchup training-dataset columns in order.")
    columns = ["match_id", *SCHEDULE_GAP_COLUMNS]
    frames = (history.historical, history.hyakunen, history.ongoing)
    gaps = pd.concat(
        [frame.loc[:, columns] for frame in frames if not frame.empty], ignore_index=True,
    )
    for frame in (dataset, gaps):
        ids = frame["match_id"]
        if ids.isna().any() or not ids.is_unique:
            raise ValueError("match_id must be nonmissing and unique in both inputs.")
    if len(dataset) != len(gaps) or dataset["match_id"].tolist() != gaps["match_id"].tolist():
        raise ValueError("Row count, match_id or row order does not match between inputs.")
    if gaps.loc[:, list(SCHEDULE_GAP_COLUMNS)].isna().any().any():
        raise ValueError("Schedule gap features must not contain missing values.")

    output = dataset.copy(deep=True)
    for column in SCHEDULE_GAP_COLUMNS:
        output[column] = gaps[column].array.copy()
    return output
