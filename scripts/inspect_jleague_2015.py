"""Compatibility entry point for the cached 2015 J1 inspection.

Run: python -m scripts.inspect_jleague_2015
Shared entry point: python -m scripts.inspect_jleague --year 2015
"""

import argparse

import pandas as pd

from scripts.inspect_jleague import ROOT, run_inspection
from src.collect import jleague


SOURCE_BASE = jleague.SOURCE_BASE
HEADERS = jleague.HEADERS
OUTPUT_DIR = ROOT / "data/processed/jleague"


def parse_matches_html(html: str, *, expected_season: int = 2015) -> pd.DataFrame:
    """Keep the original default while delegating all parsing."""
    return jleague.parse_matches_html(html, expected_season=expected_season)


def summarize_matches(matches: pd.DataFrame, *, expected_season: int = 2015) -> dict:
    return jleague.summarize_matches(matches, expected_season=expected_season)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    run_inspection(2015, root=ROOT, output_dir=OUTPUT_DIR)


if __name__ == "__main__":
    main()
