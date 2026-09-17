"""Append matchup context to the training table after strict row alignment."""

from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR
from src.features.matchup_context import MATCHUP_CONTEXT_COLUMNS
from src.features.matchup_context_history import load_matchup_context_history_with_ongoing
from src.features.training_dataset import DATASET_COLUMNS, load_training_dataset


def load_training_dataset_with_matchup_context(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Return the original 24 columns followed by exactly nine context features.

    Reuse both loaders with identical arguments. Require equal row counts and
    identical ordered, unique match IDs before attaching features by position.
    Preserve the base table's values, dtypes, columns and index without sorting
    or joining unmatched rows. No feature logic is reimplemented, and local
    input reads remain with the existing loaders; no writes or network access.
    """
    dataset = load_training_dataset(processed_dir, team_master=team_master)
    history = load_matchup_context_history_with_ongoing(processed_dir, team_master=team_master)
    if tuple(dataset.columns) != DATASET_COLUMNS:
        raise ValueError("Expected the original 24 training-dataset columns in order.")
    columns = ["match_id", *MATCHUP_CONTEXT_COLUMNS]
    frames = (history.historical, history.hyakunen, history.ongoing)
    context = pd.concat(
        [frame.loc[:, columns] for frame in frames if not frame.empty], ignore_index=True,
    )
    for frame in (dataset, context):
        ids = frame["match_id"]
        if ids.isna().any() or not ids.is_unique:
            raise ValueError("match_id must be nonmissing and unique in both inputs.")
    if len(dataset) != len(context) or dataset["match_id"].tolist() != context["match_id"].tolist():
        raise ValueError("Row count, match_id or row order does not match between inputs.")
    if context.loc[:, list(MATCHUP_CONTEXT_COLUMNS)].isna().any().any():
        raise ValueError("Matchup context features must not contain missing values.")

    output = dataset.copy(deep=True)
    for column in MATCHUP_CONTEXT_COLUMNS:
        output[column] = context[column].array.copy()
    return output
