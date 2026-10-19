"""Offline four-match witness audit; creates only a new research report folder."""

import argparse
import csv
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path

from scripts.build_dashboard_feed import read_official_revision
from src.collect.teams import load_team_master
from src.collect.jleague_ongoing import _hydrate_accepted_bridges, _parse_snapshot
from src.modeling.nn_v2_completion_binding import (
    ACTUAL, DECLARED, KEYS, Packet, digest, encoded, name_only, reconcile, require,
    validate_sealed_binding,
)


LATEST = "f2a2fdeb171367d422b520cea7d492d99edb4a25c9b713ce0fb72a8f38f285c7"
LATEST_SHA = "b8eee29d3b5ff286e50c2a171a56cff7da9afaab5ee3bc0ca64447f1b50a8e87"
SNAPSHOT_PINS = {
    ACTUAL: "899efe33feab8797cdf61df6805bb5d95f76d067e5a2816f0446d1367a70983c",
    DECLARED: "05d8f3a95b964e08d76fcd430a8e9d1f2e1dacf11f4bc74839d365ac490ac522",
}


def audit(runtime, source, output, source_pin_file, source_pin_sha):
    runtime, source, output = runtime.resolve(), source.resolve(), output.resolve()
    require(not output.exists() and not output.is_relative_to(runtime)
            and not output.is_relative_to(source), "unsafe_output")
    # No mkdir, model loading, collector execution or imports with side effects
    # before all source reads, pins, parser and complete-set checks succeed.
    source_pins = source_pin_file.read_bytes()
    require(digest(source_pins) == source_pin_sha, "protection_baseline_sha")
    protected = json.loads(source_pins)["files"]
    read_hashes = {}

    def read(path):
        value = path.read_bytes()
        actual = digest(value)
        require(actual == protected[str(path)], "source_changed_since_precheck")
        read_hashes[str(path.relative_to(runtime))] = actual
        return value

    pointer = json.loads(read(runtime / "official/latest.json"))
    require(pointer == {"revision_id": LATEST, "manifest_sha256": LATEST_SHA}, "latest_changed")
    packets = []
    for path in sorted((runtime / "official/revisions").iterdir()):
        manifest = json.loads(read(path / "manifest.json"))
        if 11 <= manifest["sequence"] <= 18:
            packets.append(Packet(path.name, read(path / "manifest.json"),
                                  {n: read(path / name_only(n)) for n in manifest["files"]}))
    snapshots = {}
    for sid in SNAPSHOT_PINS:
        path = runtime / "snapshots" / sid
        manifest_bytes = read(path / "manifest.json")
        m = json.loads(manifest_bytes)
        snapshots[sid] = Packet(sid, manifest_bytes,
                               {e[k]: read(path / name_only(e[k])) for e in m["sources"] for k in ("html", "metadata")})
    pins = {"snapshots": SNAPSHOT_PINS,
            "revisions": {p.name: digest(p.manifest) for p in packets}}
    require(len(packets) == 8 and LATEST in pins["revisions"], "incomplete_revision_chain")
    verified_at = datetime.now(timezone.utc).isoformat()
    binding = reconcile(packets, snapshots, pins, verified_at_utc=verified_at)
    master = load_team_master(source / "data/master/teams.csv")
    official = read_official_revision(runtime / "official/revisions" / LATEST, master, expected_sha=LATEST_SHA)
    require(official.manifest["summary"]["counts"] == {"completed": 100, "candidate": 0, "scheduled": 280},
            "official_state_changed")
    require(set(official.schedule.loc[official.schedule.fixture_key.isin(KEYS), "fixture_key"]) == KEYS,
            "official_fixture_missing")
    # Independently reproduce the observed mixing using existing pure helpers.
    original = next(p for p in packets if json.loads(p.manifest)["sequence"] == 12)
    mixed = next(p for p in packets if json.loads(p.manifest)["sequence"] == 13)
    previous = json.loads(original.files["observations.json"])
    current = _parse_snapshot(runtime / "snapshots" / DECLARED, json.loads(snapshots[DECLARED].manifest))
    before = {r["fixture_key"]: dict(r) for r in current if r["fixture_key"] in KEYS}
    bridges = list(csv.DictReader(io.StringIO(original.files["identity_bridges.csv"].decode())))
    require(not _hydrate_accepted_bridges(current, bridges, previous), "bridge_replay_conflict")
    mixed_rows = {r["fixture_key"]: r for r in json.loads(mixed.files["observations.json"])}
    replay = []
    for row in current:
        key = row["fixture_key"]
        if key not in KEYS:
            continue
        fields = ("evidence_sha256", "evidence_fetched_at_utc", "completion_origin_snapshot",
                  "match_page_origin_snapshot")
        require(all(row[k] == mixed_rows[key][k] for k in fields), "cause_replay_mismatch")
        replay.append({"fixture_key": key, "before": {k: before[key][k] for k in fields},
                       "after": {k: row[k] for k in fields}, "matches_saved_sequence_13": True})
    # Re-read all inputs after pure-helper reads to detect concurrent updates.
    for relative, expected in read_hashes.items():
        require(digest((runtime / relative).read_bytes()) == expected, "source_changed_during_audit")
    output.mkdir(exist_ok=False)

    def write(name, value):
        body = encoded(value)
        with (output / name).open("xb") as target:
            target.write(body); target.flush(); os.fsync(target.fileno())
        require((output / name).read_bytes() == body, "report_readback")

    write("binding-manifest.json", binding)
    binding_sha = digest((output / "binding-manifest.json").read_bytes())
    validate_sealed_binding((output / "binding-manifest.json").read_bytes(), binding_sha,
                            packets, snapshots, pins)
    write("cause-replay.json", replay)
    write("source-sha256.json", read_hashes)
    write("binding-seal.json", {"study_id": binding["study_id"], "binding_sha256": binding_sha,
                                "source_pin_sha256": source_pin_sha, "verified_at_utc": verified_at,
                                "raw_source_network_fetches": 0, "probability_calculations": 0,
                                "fits": 0, "evaluations": 0, "T0": None, "enrolled": 0,
                                "real_predictions_saved": 0})
    write("SHA256-MANIFEST.json", {p.name: digest(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps({"gate": binding["status"], "bindings": 4, "binding_sha256": binding_sha,
                      "HISTORY": "HOLD", "PREDICTION": "HOLD"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("runtime", "source", "output", "source-pin-file"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--source-pin-sha", required=True)
    args = parser.parse_args()
    audit(args.runtime, args.source, args.output, args.source_pin_file, args.source_pin_sha)
