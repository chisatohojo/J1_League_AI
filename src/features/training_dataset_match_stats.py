"""Integrate pre-match SH/CK/FK rolling features into the context dataset."""

from pathlib import Path

import pandas as pd

from src.features.elo_history import DEFAULT_PROCESSED_DIR
from src.features.match_stats_form import MATCH_STATS_FORM_COLUMNS
from src.features.match_stats_form_history import load_match_stats_form_history
from src.features.training_dataset import DATASET_COLUMNS
from src.features.training_dataset_context import load_training_dataset_with_context


def load_training_dataset_with_match_stats(
    window: int = 5,
    processed_dir: str | Path = DEFAULT_PROCESSED_DIR,
    *,
    team_master=None,
) -> pd.DataFrame:
    """Return the existing context dataset plus pre-match match-stat features."""
    dataset = load_training_dataset_with_context(processed_dir, team_master=team_master)
    # Match-stat history is intentionally limited to ordinary J1 2015--2025;
    # do not carry 2026 reserved/ongoing rows into this integration.
    dataset = dataset.loc[dataset["season"].between(2015, 2025)].copy(deep=True)
    stats_dir = Path(processed_dir).parent / "jleague_match_stats"
    history = load_match_stats_form_history(
        window=window, matches_dir=processed_dir, stats_dir=stats_dir,
    )
    _require_unique_ids(dataset, "training dataset")
    _require_unique_ids(history, "match-stats history")
    if set(dataset["match_id"].astype(str)) != set(history["match_id"].astype(str)):
        raise ValueError("Training dataset and match-stats history match_id sets differ.")

    indexed = history.copy(deep=True)
    indexed["match_id"] = indexed["match_id"].astype(str)
    indexed = indexed.set_index("match_id")
    ids = dataset["match_id"].astype(str)
    aligned = indexed.loc[ids]
    for column in ("match_date", "season", "home_team_id", "away_team_id"):
        left = dataset[column].astype(str).reset_index(drop=True)
        right = aligned[column].astype(str).reset_index(drop=True)
        if not left.equals(right):
            raise ValueError(f"{column} mismatch between training dataset and stats history.")

    collisions = set(MATCH_STATS_FORM_COLUMNS) & set(dataset.columns)
    if collisions:
        raise ValueError(f"Rolling feature columns already exist: {sorted(collisions)}")
    output = dataset.copy(deep=True)
    for column in MATCH_STATS_FORM_COLUMNS:
        output[column] = aligned[column].to_numpy(copy=True)
    return output


def _require_unique_ids(frame: pd.DataFrame, label: str) -> None:
    if "match_id" not in frame or frame["match_id"].isna().any() or not frame["match_id"].astype(str).is_unique:
        raise ValueError(f"{label} match_id must be nonmissing and unique.")
