"""Import or explicitly fetch an ongoing 2026/27 J1 snapshot, then validate it.

Cached import (no network):
  python -m scripts.update_jleague_ongoing capture --listing-html PATH \
      --evidence-html PATH --snapshot-id bootstrap-2026-09-15
Replay (no network):
  python -m scripts.update_jleague_ongoing replay SNAPSHOT_DIRECTORY

Only an explicit ``capture --fetch`` downloads the season listing. Optional
``--evidence-url`` arguments identify exact official match summary pages; no
match URL is guessed or enumerated and no other season is requested.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.request
import uuid

from src.collect.jleague_ongoing import create_snapshot, process_snapshot
from src.collect.jleague_ongoing_source import SOURCE_URL


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW = ROOT / "data/raw/jleague/2026_27/snapshots"
DEFAULT_OUTPUT = ROOT / "data/processed/jleague/2026_27"


def _fetch(url: str, destination: Path):
    """Save one response and its provenance; never overwrite or retry implicitly."""
    request = urllib.request.Request(url, headers={"User-Agent": "J1-Match-Predictor-Research/0.1"})
    started = datetime.now(timezone.utc).isoformat()
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        metadata = {
            "requested_url": url, "final_url": response.url, "status": response.status,
            "request_started_at_utc": started,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "content_type": response.headers.get("Content-Type", ""),
            "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
        }
    with destination.open("xb") as target:
        target.write(body)
    with destination.with_suffix(".metadata.json").open("x", encoding="utf-8", newline="\n") as target:
        target.write(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="Import cached sources or explicitly fetch new observations")
    source = capture.add_mutually_exclusive_group(required=True)
    source.add_argument("--listing-html", type=Path)
    source.add_argument("--fetch", action="store_true", help="Fetch just the regular 2026/27 J1 listing once")
    capture.add_argument("--evidence-html", action="append", type=Path, default=[])
    capture.add_argument("--evidence-url", action="append", default=[], help="Explicit official match-summary URL (requires --fetch)")
    capture.add_argument("--snapshot-id")
    capture.add_argument("--raw-root", type=Path, default=DEFAULT_RAW)
    capture.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    replay = subparsers.add_parser("replay", help="Reprocess an immutable snapshot without network access")
    replay.add_argument("snapshot_dir", type=Path)
    replay.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if args.command == "replay":
        snapshot = args.snapshot_dir
    else:
        if args.evidence_url and not args.fetch:
            parser.error("--evidence-url requires explicit --fetch; use --evidence-html for cached evidence.")
        if len(args.evidence_url) != len(set(args.evidence_url)):
            parser.error("Do not request the same evidence URL twice.")
        if any(not re.fullmatch(r"https://www\.jleague\.jp/match/j1/(2026|2027)/[0-9]{6}/", url) for url in args.evidence_url):
            parser.error("Evidence URLs must be exact official J1 match summary pages.")
        evidence = list(args.evidence_html)
        listing = args.listing_html
        if args.fetch:
            # These immutable acquisition files survive parse or publication
            # failures, and can subsequently be imported with --listing-html.
            acquisition = args.raw_root.parent / "acquisitions" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-") + uuid.uuid4().hex[:8])
            acquisition.mkdir(parents=True)
            listing = acquisition / "listing.html"
            _fetch(SOURCE_URL, listing)
            for index, url in enumerate(args.evidence_url, 1):
                time.sleep(1)
                path = acquisition / f"evidence_{index:03d}.html"
                _fetch(url, path)
                evidence.append(path)
        snapshot = create_snapshot(args.raw_root, listing_html=listing, evidence_html=evidence, snapshot_id=args.snapshot_id)
    summary = process_snapshot(snapshot, args.output_dir)
    print(json.dumps({
        "snapshot": str(snapshot), "revision_id": summary["revision_id"],
        "publication_status": summary["publication_status"],
        "counts": summary["counts"], "result_validation": summary["result_validation"],
        "publication_blocks": summary["publication_blocks"],
    }, ensure_ascii=False, indent=2))
    return 0 if summary["publication_status"] == "published" else 2


if __name__ == "__main__":
    raise SystemExit(main())
