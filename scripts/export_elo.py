"""Export saved Elo history offline: python -m scripts.export_elo."""

import argparse
from pathlib import Path

from src.collect.teams import DEFAULT_TEAM_MASTER_PATH, load_team_master
from src.features.elo_export import DEFAULT_OUTPUT_DIR, export_elo_history
from src.features.elo_history import DEFAULT_PROCESSED_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed-dir", type=Path, default=DEFAULT_PROCESSED_DIR,
                        help="Existing jleague input directory (read only).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Directory for the two regenerated Elo CSVs.")
    parser.add_argument("--team-master", type=Path, default=DEFAULT_TEAM_MASTER_PATH,
                        help="Existing team alias master CSV (read only).")
    args = parser.parse_args(argv)
    paths = export_elo_history(
        args.processed_dir, output_dir=args.output_dir,
        team_master=load_team_master(args.team_master),
    )
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
