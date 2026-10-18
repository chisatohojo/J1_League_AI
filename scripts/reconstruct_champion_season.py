"""Offline retrospective Champion A reconstruction; never acquire data or call the live predictor."""
import argparse
import json
from pathlib import Path
import sys

from src.modeling.champion_retrospective import run_reconstruction, compare_saved_predictions


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--official-directory", required=True, type=Path, help="Explicit immutable revision directory, not latest.json")
    parser.add_argument("--manifest-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--stage", required=True, choices=("trial", "complete"))
    parser.add_argument("--resume", action="store_true", help="Reuse only verified days of the exact same run contract")
    parser.add_argument("--saved-runtime", type=Path, help="Read-only native saved predictions for the separate October 9 comparison")
    args = parser.parse_args(argv)
    try:
        if args.saved_runtime is not None and args.stage != "complete":
            parser.error("--saved-runtime requires --stage complete")
        result = run_reconstruction(args.source_root, args.official_directory, args.manifest_sha,
                                    args.output, stage=args.stage, resume=args.resume)
        if args.saved_runtime is not None:
            compare_saved_predictions(args.output, args.saved_runtime)
    except Exception:
        print("Retrospective reconstruction stopped; inspect pinned inputs and retained completed days.", file=sys.stderr)
        return 1
    print(json.dumps(dict(stage=args.stage, predicted=result["predicted_count"],
                         target=result["target_count"], metrics=result["metrics"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
