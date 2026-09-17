"""Append venue form to the existing training table after strict row alignment."""

from pathlib import Path

import pandas as pd

from src.collect.teams import TeamMaster
from src.features.elo_history import DEFAULT_PROCESSED_DIR
from src.features.training_dataset import DATASET_COLUMNS, load_training_dataset
from src.features.venue_form import VENUE_FORM_COLUMNS
from src.features.venue_form_history import load_venue_form_history_with_ongoing


def load_training_dataset_with_venue_form(
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR, *, team_master: TeamMaster | None = None,
) -> pd.DataFrame:
    """Return the original 24 columns followed by exactly four venue features.

    Both existing loaders use the same input arguments. Require equal row
    counts and identical ordered, unique match IDs; never sort or silently join
    unmatched rows. Preserve the base table's values, dtypes, columns and index.
    No feature logic is reimplemented and no files or network are accessed
    beyond the existing loaders' read-only local inputs.
    """
    dataset = load_training_dataset(processed_dir, team_master=team_master)
    history = load_venue_form_history_with_ongoing(processed_dir, team_master=team_master)
    if tuple(dataset.columns) != DATASET_COLUMNS:
        raise ValueError("Expected the original 24 training-dataset columns in order.")
    columns = ["match_id", *VENUE_FORM_COLUMNS]
    frames = (history.historical, history.hyakunen, history.ongoing)
    venue = pd.concat(
        [frame.loc[:, columns] for frame in frames if not frame.empty], ignore_index=True,
    )
    for frame in (dataset, venue):
        ids = frame["match_id"]
        if ids.isna().any() or not ids.is_unique:
            raise ValueError("match_id must be nonmissing and unique in both inputs.")
    if len(dataset) != len(venue) or dataset["match_id"].tolist() != venue["match_id"].tolist():
        raise ValueError("Row count, match_id or row order does not match between inputs.")
    if venue.loc[:, list(VENUE_FORM_COLUMNS)].isna().any().any():
        raise ValueError("Venue form features must not contain missing values.")

    output = dataset.copy(deep=True)
    for column in VENUE_FORM_COLUMNS:
        output[column] = venue[column].array.copy()
    return output
