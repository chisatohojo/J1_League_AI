"""Compatibility entry point for the cached 2016 J1 comparison.

Run: python -m scripts.inspect_jleague_2016
Shared entry point: python -m scripts.inspect_jleague --year 2016
"""

import argparse

import pandas as pd

from scripts.inspect_jleague import ROOT, compare_years, render_review, run_inspection
from src.collect import jleague


OUTPUT_DIR = ROOT / "data/processed/jleague"


def read_cached_matches(year: int) -> tuple[pd.DataFrame, dict]:
    return jleague.read_cached_matches(year, raw_dir=ROOT / "data/raw/jleague")


def build_review_summary(matches: pd.DataFrame) -> dict:
    return jleague.build_review_summary(matches, expected_season=2016)


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    run_inspection(2016, root=ROOT, output_dir=OUTPUT_DIR)


if __name__ == "__main__":
    main()
