"""Fixed season-based partitions of the existing 24-column training dataset."""

from dataclasses import dataclass

import pandas as pd

from src.features.training_dataset import DATASET_COLUMNS


@dataclass
class TimeSplit:
    """Independent copies retaining source columns, dtypes, indices and order."""

    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    reserved: pd.DataFrame


def split_training_dataset(dataset: pd.DataFrame) -> TimeSplit:
    """Split 2015-2023 / 2024 / 2025 / 2026 without shuffling or dropping rows.

    All season=2026 matches remain reserved, including 2026/27 matches played
    in calendar 2027. Earlier seasons must agree with their match-date year.
    Reject unknown seasons, duplicate/missing IDs and invalid chronology rather
    than silently losing rows or changing their order. No input mutation, file
    access, preprocessing or model training is performed.
    """
    if not isinstance(dataset, pd.DataFrame):
        raise TypeError("dataset must be a pandas DataFrame.")
    if tuple(dataset.columns) != DATASET_COLUMNS:
        raise ValueError("Expected the fixed 24 training-dataset columns in order.")
    ids = dataset["match_id"]
    if ids.isna().any() or ids.duplicated().any() or ids.astype("string").str.strip().eq("").any():
        raise ValueError("match_id must be nonmissing, nonempty and globally unique.")
    seasons = dataset["season"]
    if not seasons.isin(range(2015, 2027)).all():
        raise ValueError("Only seasons 2015-2026 belong to this fixed split.")
    dates = pd.to_datetime(dataset["match_date"], errors="raise")
    if dates.isna().any() or not dates.is_monotonic_increasing:
        raise ValueError("match_date must be nonmissing and in chronological order.")
    matching_year = dates.dt.year.eq(seasons)
    next_calendar_year = seasons.eq(2026) & dates.dt.year.eq(2027)
    if not (matching_year | next_calendar_year).all():
        raise ValueError("match_date does not agree with season.")

    return TimeSplit(
        train=dataset.loc[seasons.between(2015, 2023)].copy(deep=True),
        validation=dataset.loc[seasons.eq(2024)].copy(deep=True),
        test=dataset.loc[seasons.eq(2025)].copy(deep=True),
        reserved=dataset.loc[seasons.eq(2026)].copy(deep=True),
    )
