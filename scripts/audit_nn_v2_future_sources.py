"""Audit saved sources only; no models are loaded and no T0 is registered."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.build_dashboard_feed import read_official_revision
from src.collect.teams import load_team_master
from src.collect.jleague_hyakunen import validate_competition
from src.features.elo_history import _read_hyakunen_matches, _order_matches, _prepare_ongoing_matches
from src.modeling.nn_v2_pretraining_audit import future_capacity


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, obj):
    with Path(path).open("x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False); f.write("\n")


def checked_source(folder, entry):
    for key in ("html", "metadata"):
        if Path(entry[key]).name != entry[key]:
            raise ValueError("Source path escape")
    raw, meta = folder/entry["html"], folder/entry["metadata"]
    if sha(raw) != entry["sha256"] or sha(meta) != entry["metadata_sha256"]:
        raise ValueError("Raw/metadata witness hash mismatch")
    m = json.loads(meta.read_bytes())
    if (m["sha256"] != entry["sha256"] or m["status"] != 200 or m["bytes"] != raw.stat().st_size
            or m["requested_url"] != entry["source_url"] or m["final_url"] != entry["source_url"]
            or m["fetched_at_utc"] != entry["fetched_at_utc"]):
        raise ValueError("Witness metadata contract mismatch")
    return {"url": entry["source_url"], "raw_sha256": entry["sha256"],
            "metadata_sha256": entry["metadata_sha256"], "fetched_at_utc": entry["fetched_at_utc"]}


def audit(source, runtime, output):
    output.mkdir(exist_ok=False)
    start = datetime.now(timezone.utc)
    pointer = json.loads((runtime/"official/latest.json").read_bytes())
    master = load_team_master(source/"data/master/teams.csv")
    directory = runtime/"official/revisions"/pointer["revision_id"]
    official = read_official_revision(directory, master, expected_sha=pointer["manifest_sha256"])
    schedule = official.schedule.copy()
    capacity = future_capacity(schedule, start)
    provisional = schedule["round"].astype(int).isin(capacity.get("provisional_rounds", []))
    schedule["capacity_only_not_enrolled"] = provisional
    schedule["official_id_missing"] = schedule.match_page_id.eq("")
    schedule["kickoff_missing"] = schedule.kickoff_time.eq("")
    columns = ["fixture_key", "round", "match_date", "home_team_id", "away_team_id", "status", "match_page_id",
               "data_site_match_id", "kickoff_time", "capacity_only_not_enrolled", "official_id_missing", "kickoff_missing"]
    schedule[columns].to_csv(output/"schedule-identity-audit.csv", index=False)
    schedule.loc[schedule.official_id_missing, columns].to_csv(output/"missing-official-ids.csv", index=False)
    schedule.loc[schedule.kickoff_missing, columns].to_csv(output/"missing-kickoffs.csv", index=False)
    counts = {}
    for label, rows in (("all_380", schedule), ("unstarted_280", schedule[schedule.status.eq("scheduled")]),
                         ("capacity_200_not_enrolled", schedule[provisional])):
        counts[label] = {"fixtures": len(rows), "official_ids_known": int((~rows.official_id_missing).sum()),
                         "official_ids_pending": int(rows.official_id_missing.sum()),
                         "kickoffs_known": int((~rows.kickoff_missing).sum()), "kickoffs_pending": int(rows.kickoff_missing.sum())}
    rounds = []
    for n, games in schedule.groupby("round", sort=False):
        rounds.append({"round": int(n), "fixtures": len(games), "dates": sorted(games.match_date.unique()),
                       "ids_pending": int(games.official_id_missing.sum()), "kickoffs_pending": int(games.kickoff_missing.sum())})
    rounds.sort(key=lambda item: item["round"])
    write(output/"rounds.json", rounds)
    witness = []
    latest_snapshot = runtime/"snapshots"/official.manifest["snapshot_id"]
    sm = json.loads((latest_snapshot/"manifest.json").read_bytes())
    for entry in sm["sources"]:
        witness.append(checked_source(latest_snapshot, entry))
    provenance_gaps = []
    for row in schedule[schedule.status.eq("completed")].itertuples(index=False):
        name = row.completion_origin_snapshot
        if Path(name).name != name:
            raise ValueError("Snapshot identity escape")
        candidates = [runtime/"snapshots"/name, source/"data/raw/jleague/2026_27/snapshots"/name]
        folder = next((f for f in candidates if f.is_dir()), None)
        if folder is None:
            raise ValueError("Completed source snapshot missing")
        manifest = json.loads((folder/"manifest.json").read_bytes())
        matches = [e for e in manifest["sources"] if e["sha256"] == row.evidence_sha256 and e["source_url"] == row.evidence_url]
        if len(matches) != 1:
            alternatives = []
            for base in (runtime/"snapshots", source/"data/raw/jleague/2026_27/snapshots"):
                for candidate in sorted(base.glob("*/manifest.json")):
                    cm = json.loads(candidate.read_bytes())
                    for e in cm.get("sources", []):
                        if (e["sha256"] == row.evidence_sha256 and e["source_url"] == row.evidence_url
                                and e["fetched_at_utc"] == row.evidence_fetched_at_utc):
                            checked_source(candidate.parent, e)
                            alternatives.append({"snapshot": candidate.parent.name, "raw_sha256": e["sha256"],
                                                 "metadata_sha256": e["metadata_sha256"], "adopted": False})
            provenance_gaps.append({"fixture_key": row.fixture_key, "match_date": row.match_date,
                "declared_snapshot": name, "declared_snapshot_matching_entries": len(matches),
                "evidence_url": row.evidence_url, "evidence_sha256": row.evidence_sha256,
                "fetched_at_utc": row.evidence_fetched_at_utc, "diagnostic": "ORIGIN_SNAPSHOT_WITNESS_MISMATCH",
                "verified_alternative_raw_locations_not_adopted": alternatives, "status": "HOLD"})
            continue
        w = checked_source(folder, matches[0])
        if w["fetched_at_utc"] != row.evidence_fetched_at_utc or pd.Timestamp(w["fetched_at_utc"]) > pd.Timestamp(official.observed_at):
            raise ValueError("Completion witness clock mismatch")
        w.update(fixture_key=row.fixture_key, match_page_id=row.match_page_id, snapshot=name)
        witness.append(w)
    # Regulation results only; no Elo/Form inference or prediction is performed.
    special_path = source/"data/processed/jleague/2026_hyakunen/matches.csv"
    if sha(special_path) != "9f871594e5216c1c89e69fcef835c641f3a4b5dbefce8d138e79881494c71f8c":
        raise ValueError("Fixed Hyakunen input changed")
    special = _read_hyakunen_matches(special_path)
    validate_competition(special)
    ordered = _order_matches(special, master)
    # completed is the original published table; schedule already has resolved
    # IDs added by the dashboard reader and must not be resolved a second time.
    ongoing = _prepare_ongoing_matches(official.completed, master, official.observed_at)
    if set(ordered.match_id) & set(ongoing.match_id):
        raise ValueError("2026 history ID collision")
    if not np.isfinite(ordered[["home_score", "away_score", "result"]].to_numpy(dtype=float)).all():
        raise ValueError("Invalid regulation history")
    hsummary = json.loads((special_path.parent/"summary.json").read_bytes())
    hraw = source/"data/raw/jleague/2026_hyakunen"
    for name, meta in hsummary["acquisition"].items():
        path = hraw/name
        if Path(name).name != name or sha(path) != meta["sha256"]:
            raise ValueError("Hyakunen raw source mismatch")
        mp = path.with_suffix(".metadata.json")
        if json.loads(mp.read_bytes()) != meta:
            raise ValueError("Hyakunen acquisition metadata changed")
    nearest = min(schedule.loc[schedule.status.eq("scheduled"), "match_date"])
    past_unresolved = schedule[schedule.match_date.lt(nearest) & ~schedule.status.eq("completed")]
    detail_ids = {name.removeprefix("match_").removesuffix(".html") for name in hsummary["acquisition"] if name.startswith("match_")}
    history = {"historical_training_rows": 3588, "hyakunen_regulation_results": len(ordered),
        "ongoing_completed_results": len(ongoing), "hyakunen_raw_sources_sha_verified": len(hsummary["acquisition"]),
        "hyakunen_detailed_pages_available": len(detail_ids), "hyakunen_detail_pages_missing": len(special)-len(detail_ids),
        "hyakunen_pk_matches": int(special.pk_played.sum()), "hyakunen_et_matches": int(special.extra_time_played.sum()),
        "ongoing_completion_witnesses_sha_verified": len(witness)-len(sm["sources"]),
        "ongoing_completion_origin_binding_gaps": len(provenance_gaps),
        "next_scheduled_date_only_not_enrollment": nearest, "prior_unresolved_results": len(past_unresolved),
        "last_ongoing_result_date": ongoing.match_date.max().strftime("%Y-%m-%d"),
        "scope": ["ordinary J1 2015-2025 event policy v1.1", "2026 Hyakunen regulation scores only", "accepted 2026/27 completed regulation results only"],
        "excluded": ["PK winners/scores", "extra-time scores", "Cup/AFC", "ST2", "retrospective predictions"],
        "source_publication_time_proven": False, "acquisition_times_and_sha_available": True,
        "future_nn_elo_form_adapter": "NOT_IMPLEMENTED_OR_PIT_VERIFIED",
        "2026_interruption_registry_review": "NOT_COMPLETED",
        "status": "HOLD"}
    write(output/"history-audit.json", history)
    write(output/"witness-audit.json", witness)
    write(output/"provenance-gaps.json", provenance_gaps)
    report = {"revision": pointer, "observed_at_utc": official.observed_at, "audited_at_utc": start.isoformat(),
        "saved_source_age_seconds": (start-pd.Timestamp(official.observed_at).to_pydatetime()).total_seconds(),
        "freshness": "Saved accepted observation only; no claim about live official changes",
        "status_counts": official.manifest["summary"]["counts"], "counts": counts, "capacity": capacity,
        "history": history, "real_T0": None, "enrolled_fixtures": 0, "real_probabilities_computed": 0,
        "real_predictions_saved": 0, "network_fetches": 0,
        "enrollment_v1_kickoff_contract": "All 200 kickoffs must be non-null; current 100 unknown cannot pass",
        "postponement_cause_or_interruption_proof": "Date dispersion alone does not establish cause; unknown temporal cases must HOLD"}
    if json.loads((runtime/"official/latest.json").read_bytes()) != pointer:
        raise ValueError("Latest pointer changed during audit")
    write(output/"source-audit.json", report)
    write(output/"SHA256-MANIFEST.json", {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps({"status": "AUDIT_COMPLETED_HOLD", "counts": counts, "history": history}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("source-root", "runtime", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    a = p.parse_args()
    audit(a.source_root, a.runtime, a.output)
