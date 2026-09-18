"""Append existing pre-match Elo momentum to the context training dataset."""

from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR
from src.features.elo_momentum import ELO_MOMENTUM_COLUMNS
from src.features.elo_momentum_history import load_elo_momentum_history_with_ongoing
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.schedule_gap import SCHEDULE_GAP_COLUMNS
from src.features.training_dataset import DATASET_COLUMNS
from src.features.training_dataset_context import load_training_dataset_with_context


def load_training_dataset_full(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Return 38 unchanged context columns followed by five Elo momentum columns.

    Reuse both loaders with identical arguments. Require equal row counts and
    identical ordered, unique match IDs before appending features by position.
    Preserve the base values, dtypes, column order and index, and the momentum
    dtypes. result remains the target; scores and other post-match fields are
    excluded. No feature logic is reimplemented, source frames modified, files
    written, network accessed or models fitted.
    """
    dataset = load_training_dataset_with_context(processed_dir, team_master=team_master)
    history = load_elo_momentum_history_with_ongoing(processed_dir, team_master=team_master)
    if tuple(dataset.columns) != (*DATASET_COLUMNS, *MATCHUP_CONTEXT_COLUMNS, *SCHEDULE_GAP_COLUMNS):
        raise ValueError("Expected the original 38 context training-dataset columns in order.")
    columns = ["match_id", *ELO_MOMENTUM_COLUMNS]
    frames = (history.historical, history.hyakunen, history.ongoing)
    momentum = pd.concat(
        [frame.loc[:, columns] for frame in frames if not frame.empty], ignore_index=True,
    )
    for frame in (dataset, momentum):
        ids = frame["match_id"]
        if ids.isna().any() or not ids.is_unique:
            raise ValueError("match_id must be nonmissing and unique in both inputs.")
    if len(dataset) != len(momentum) or dataset["match_id"].tolist() != momentum["match_id"].tolist():
        raise ValueError("Row count, match_id or row order does not match between inputs.")
    if momentum.loc[:, list(ELO_MOMENTUM_COLUMNS)].isna().any().any():
        raise ValueError("Elo momentum features must not contain missing values.")

    output = dataset.copy(deep=True)
    for column in ELO_MOMENTUM_COLUMNS:
        output[column] = momentum[column].array.copy()
    return output
