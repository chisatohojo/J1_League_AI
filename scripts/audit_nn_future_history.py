"""Phase 2.5B offline evidence/chronology audit. No live fetch or inference."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys


def deny_network(event, args):
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                 "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto",
                 "http.client.connect", "urllib.Request"}:
        raise RuntimeError("Phase 2.5B forbids network acquisition: " + event)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(folder, name, value):
    body = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    with (folder / name).open("xb") as f:
        f.write(body); f.flush(); os.fsync(f.fileno())
    if (folder / name).read_bytes() != body:
        raise ValueError("report_readback")


def visible(raw):
    text = raw.decode("utf-8-sig", errors="strict")
    text = re.sub(r"<(script|style)\b[^>]*>.*?</\1\s*>", "", text, flags=re.S | re.I)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return html.unescape(re.sub(r"<[^>]*>", " ", text))


class Reader:
    def __init__(self, baseline):
        self.baseline = baseline
        self.reads = {}

    def read(self, path):
        path = Path(path).resolve()
        raw = path.read_bytes()
        digest = sha(raw)
        if str(path) in self.baseline and self.baseline[str(path)] != digest:
            raise ValueError("input_changed_since_preflight:" + str(path))
        if str(path) in self.reads and self.reads[str(path)] != digest:
            raise ValueError("input_changed_during_audit:" + str(path))
        self.reads[str(path)] = digest
        return raw

    def obj(self, path):
        return json.loads(self.read(path))


def execute(args):
    # Imports are inside the network-denied process; local gethostname is not IO.
    import numpy as np
    import pandas as pd
    from scripts.audit_nn_v2_completion_binding import LATEST, LATEST_SHA
    from scripts.audit_nn_v2_future_sources import checked_source
    from scripts.build_dashboard_feed import read_official_revision
    from src.collect.jleague_hyakunen import normalize_matches, validate_competition
    from src.collect.jleague_hyakunen_source import read_cached_sources, parse_detail
    from src.collect.jleague_ongoing_source import parse_completion_evidence
    from src.collect.teams import load_team_master
    from src.features import nn_future_history as adapter
    from src.features import nn_research_timing as timing
    from src.features.elo_history import _read_hyakunen_matches, _order_matches, _prepare_ongoing_matches
    from src.modeling.nn_research_v1 import load_source
    from src.modeling.nn_v2_completion_binding import Packet, name_only, validate_sealed_binding
    from src.modeling.nn_v2_pretraining_audit import no_learning

    source, runtime, output = args.source.resolve(), args.runtime.resolve(), args.output.resolve()
    if (output.exists() or output.is_relative_to(source) or output.is_relative_to(runtime)
            or output.is_relative_to(Path(__file__).resolve().parents[1])):
        raise ValueError("unsafe_output")
    baseline_bytes = args.protection.read_bytes()
    if sha(baseline_bytes) != args.protection_sha:
        raise ValueError("protection_sha")
    reader = Reader(json.loads(baseline_bytes)["files"])
    root = Path(__file__).resolve().parents[1]
    master = load_team_master(source / "data/master/teams.csv")
    pointer = reader.obj(runtime / "official/latest.json")
    if pointer != {"revision_id": LATEST, "manifest_sha256": LATEST_SHA}:
        raise ValueError("approved_revision_changed")
    publication = runtime / "official/revisions" / LATEST
    official = read_official_revision(publication, master, expected_sha=LATEST_SHA)
    for name in ("manifest.json", *official.manifest["files"]):
        reader.read(publication / name)
    # Revalidate the sealed four, including all original packets and A/B bytes.
    binding_bytes = reader.read(root / "research/nn_v2/phase2_5A/binding-manifest.json")
    binding_json = json.loads(binding_bytes)
    pins = binding_json["pins"]
    packets = []
    for rid in pins["revisions"]:
        p = runtime / "official/revisions" / name_only(rid)
        manifest = reader.read(p / "manifest.json")
        packets.append(Packet(rid, manifest, {n: reader.read(p / name_only(n)) for n in json.loads(manifest)["files"]}))
    snapshots = {}
    for sid in pins["snapshots"]:
        p = runtime / "snapshots" / name_only(sid)
        raw = reader.read(p / "manifest.json")
        snapshots[sid] = Packet(sid, raw, {s[k]: reader.read(p / name_only(s[k]))
                                         for s in json.loads(raw)["sources"] for k in ("html", "metadata")})
    binding = validate_sealed_binding(binding_bytes, adapter.BINDING_SHA, packets, snapshots, pins)
    binding_by_key = {b["fixture_key"]: b for b in binding["bindings"]}
    print("Approved revision and four sealed binding packets verified", flush=True)

    with no_learning() as forbidden_calls:
        historical, input_pins = load_source(source, root / "research/nn_v1/input-pins.json")
        cache_review = timing.review_cache(source, historical)
        if cache_review != reader.obj(root / "research/nn_v1/audit-timing-v1_1/source-timing-review.json"):
            raise ValueError("historical_cache_review_drift")
        reference_trace = []
        reference = timing.build_event_features(historical, trace=reference_trace)
        events = adapter.legacy_events(historical)
        queries = [adapter.Query(r.fixture_identity, r.home_team_id, r.away_team_id, r.feature_timestamp,
                                 r.history_cutoff_timestamp, r.history_cutoff_timestamp)
                   for r in reference.itertuples(index=False)]
        # An explicitly fictitious state probe drains the final 2025 result
        # boundary; it is not a real fixture, enrollment or probability request.
        final_day = max(pd.Timestamp(e.result_effective_at) for e in events)
        probe = adapter.Query("AUDIT_ONLY_LEGACY_FINAL_STATE", events[-1].home_team_id,
                              events[-1].away_team_id, (final_day + pd.Timedelta(hours=12)).isoformat(),
                              final_day.isoformat(), final_day.isoformat())
        queries.append(probe)
        universe = [adapter.Fixture(e.identity, e.home_team_id, e.away_team_id, e.original_kickoff, "completed")
                    for e in events]
        rows, trace = adapter.replay(events, queries, universe=universe,
                                    team_ids=sorted({a.team_id for a in master.aliases}),
                                    covered_through=max(q.history_cutoff for q in queries), timing_admissions={})
        by_id = {r["identity"]: r for r in rows}
        actual = np.array([[by_id[r.fixture_identity][c] for c in adapter.FEATURES]
                           for r in reference.itertuples(index=False)])
        expected = reference[list(adapter.FEATURES)].to_numpy(dtype=float)
        delta = float(np.abs(actual - expected).max())
        if not np.allclose(actual, expected, rtol=0, atol=1e-10):
            raise ValueError("historical_adapter_parity")
        applied_count = sum(t["event"] == "result_applied" for t in trace)
        if applied_count != len(historical):
            raise ValueError("legacy_final_results_not_drained")
        if [(t["match_id"], t["at"]) for t in reference_trace if t["event"] == "result_applied"] != [
                (t["identity"].split(":")[-1], t["result_effective_at"]) for t in trace if t["event"] == "result_applied"]:
            raise ValueError("legacy_result_event_order_drift")
        legacy_report = {"status": "PASS", "rows": len(reference), "features": list(adapter.FEATURES),
                         "max_absolute_delta": delta, "finite": bool(np.isfinite(actual).all()),
                         "ranges": {c: [float(actual[:, i].min()), float(actual[:, i].max())]
                                    for i, c in enumerate(adapter.FEATURES)},
                         "historical_acquisition_as_of_claim": False,
                         "result_events_applied_exactly_once": applied_count,
                         "real_fixture_feature_events": len(reference), "fictitious_final_state_probes": 1,
                         "final_state_probe": by_id[probe.identity],
                         "30700": asdict(next(e for e in events if e.match_id == "30700"))}
        print("3588 legacy rows / nine features agree with frozen v1.1", flush=True)

        special_path = source / "data/processed/jleague/2026_hyakunen/matches.csv"
        if sha(reader.read(special_path)) != "9f871594e5216c1c89e69fcef835c641f3a4b5dbefce8d138e79881494c71f8c":
            raise ValueError("hyakunen_pin")
        special = _read_hyakunen_matches(special_path)
        validate_competition(special)
        hraw = source / "data/raw/jleague/2026_hyakunen"
        records, details, acquisition = read_cached_sources(raw_dir=hraw)
        rebuilt = normalize_matches(records, details)
        # Compare every source/derived field, including PK/ET separation.
        pd.testing.assert_frame_equal(special, rebuilt, check_dtype=False)
        hyakunen = _order_matches(special, master)
        ongoing = _prepare_ongoing_matches(official.completed, master, official.observed_at)
        if set(hyakunen.match_id) & set(ongoing.match_id):
            raise ValueError("2026_data_site_ID_collision")
        for name, m in acquisition.items():
            if sha(reader.read(hraw / name)) != m["sha256"]:
                raise ValueError("hyakunen_raw_pin")
            if reader.obj((hraw / name).with_suffix(".metadata.json")) != m:
                raise ValueError("hyakunen_metadata_pin")

        # Inventory saved metadata, never construct URL sequences. A discovered
        # SFMS02 link from the listing is an acquisition candidate, not evidence.
        targets = set(hyakunen.source_url) | set(ongoing.source_url)
        inventory, articles = [], []
        for path in sorted((source / "data/raw").rglob("*.metadata.json")):
            m = json.loads(path.read_bytes())
            url = m.get("requested_url", "")
            if url in targets or ("jleague.jp/news/article/" in url):
                raw = path.with_name(path.name.removesuffix(".metadata.json") + ".html")
                record = {"metadata": str(path), "raw": str(raw), "url": url,
                          "metadata_sha256": sha(reader.read(path)), "exists": raw.is_file()}
                if raw.is_file():
                    body = reader.read(raw)
                    if m.get("status") != 200 or m.get("sha256") != sha(body) or m.get("bytes") != len(body):
                        raise ValueError("inventory_raw_metadata_mismatch")
                    record.update(raw_sha256=sha(body), fetched_at_utc=m["fetched_at_utc"])
                (inventory if url in targets else articles).append(record)
        sfms_by_url = {}
        for item in inventory:
            if item["exists"]:
                sfms_by_url.setdefault(item["url"], []).append(item)

        # Preserve every accepted schedule observation; do not reinterpret the
        # earliest saved post-match date as an original announced schedule.
        schedule_history = {}
        revision_inventory = []
        for p in sorted((runtime / "official/revisions").iterdir()):
            m = reader.obj(p / "manifest.json")
            if m["summary"]["publication_status"] != "published":
                continue
            observation = json.loads(reader.read(p / "observations.json"))
            if sha(reader.read(p / "observations.json")) != m["files"]["observations.json"]:
                raise ValueError("observation_sha")
            revision_inventory.append({"revision": p.name, "sequence": m["sequence"],
                                       "manifest_sha256": sha(reader.read(p / "manifest.json"))})
            for r in observation:
                schedule_history.setdefault(r["fixture_key"], []).append({
                    "sequence": m["sequence"], "revision": p.name,
                    "observed_at_utc": m["summary"]["observed_at_utc"],
                    **{k: r.get(k) for k in ("match_date", "kickoff_time", "status")}})
        revision_inventory.sort(key=lambda r: r["sequence"])

        evidence, missing, registry = [], [], []
        for label, frame in (("hyakunen", hyakunen), ("ongoing", ongoing)):
            for r in frame.itertuples(index=False):
                day = pd.Timestamp(r.match_date).strftime("%Y-%m-%d")
                identity = "jleague_data_site_sfms02:" + r.match_id if label == "hyakunen" else r.fixture_key
                report = {"identity": identity, "data_site_match_id": r.match_id,
                          "series": label, "home_team_id": r.home_team_id, "away_team_id": r.away_team_id,
                          "source_date": day, "source_reported_kickoff": day + "T" + r.kickoff_time + ":00+09:00",
                          "original_schedule": None, "actual_final_whistle_at": None,
                          "first_saved_pre_start_schedule": None,
                          "original_schedule_as_of_proven": False,
                          "research_next_day_boundary_candidate": (pd.Timestamp(day, tz="Asia/Tokyo")
                                                                   + pd.Timedelta(days=1)).isoformat(),
                          "result_effective_event_admitted": False,
                          "home_score_90": int(r.home_score), "away_score_90": int(r.away_score),
                          "historical_publication_as_of_proven": False,
                          "sfms02_candidate_url_from_saved_listing": r.source_url}
                if label == "hyakunen":
                    report.update(listing_raw_sha256=acquisition["j1_search.html"]["sha256"],
                                  listing_fetched_at_utc=acquisition["j1_search.html"]["fetched_at_utc"],
                                  pk_played=bool(r.pk_played), extra_time_played=bool(r.extra_time_played))
                else:
                    history = sorted(schedule_history[r.fixture_key], key=lambda s: s["sequence"])
                    report["saved_schedule_observations"] = history
                    pre_start = [s for s in history if pd.Timestamp(s["observed_at_utc"])
                                 < pd.Timestamp(report["source_reported_kickoff"])]
                    if pre_start:
                        report["first_saved_pre_start_schedule"] = pre_start[0]
                    report["date_changes_in_saved_revisions"] = len({s["match_date"] for s in history}) > 1
                    report["date_or_kickoff_changes_in_saved_revisions"] = len({(s["match_date"], s["kickoff_time"]) for s in history}) > 1
                    if report["date_or_kickoff_changes_in_saved_revisions"]:
                        registry.append({"identity": identity, "classification": "SAVED_DATE_OR_KICKOFF_CHANGE",
                                         "date_changed": report["date_changes_in_saved_revisions"],
                                         "saved_date_kickoff_values": [list(pair) for pair in sorted(
                                             {(s["match_date"], s["kickoff_time"]) for s in history})],
                                         "cause_proven": False,
                                         "interpretation": "Recorded kickoff differs from earlier schedule; do not infer postponement cause"})
                    if r.fixture_key in binding_by_key:
                        b = binding_by_key[r.fixture_key]
                        sid, entry = b["actual_snapshot"], b["actual_source"]
                        folder = runtime / "snapshots" / sid
                        report.update(binding_sha256=adapter.BINDING_SHA,
                                      original_publication_reference=b["original_publication_reference"],
                                      actual_snapshot=sid, declared_snapshot=b["declared_snapshot"],
                                      acquired_on_match_day_proven=False)
                    else:
                        sid = name_only(r.completion_origin_snapshot)
                        choices = [runtime / "snapshots" / sid, source / "data/raw/jleague/2026_27/snapshots" / sid]
                        folder = next((p for p in choices if p.is_dir()), None)
                        if folder is None:
                            raise ValueError("completion_snapshot_missing")
                        m = reader.obj(folder / "manifest.json")
                        candidates = [e for e in m["sources"] if e["sha256"] == r.evidence_sha256
                                      and e["source_url"] == r.evidence_url and e["fetched_at_utc"] == r.evidence_fetched_at_utc]
                        if len(candidates) != 1:
                            raise ValueError("unbound_completion_witness")
                        entry = candidates[0]
                    witness = checked_source(folder, entry)
                    reader.read(folder / name_only(entry["html"])); reader.read(folder / name_only(entry["metadata"]))
                    parsed = parse_completion_evidence((folder / entry["html"]).read_text("utf-8-sig"), source_url=entry["source_url"])
                    if (not parsed["verified"] or (parsed["fixture_key"], parsed["match_date"], parsed["home_score"], parsed["away_score"]) != (
                            r.fixture_key, day, int(r.home_score), int(r.away_score))):
                        raise ValueError("completion_identity_result")
                    if pd.Timestamp(witness["fetched_at_utc"]) > pd.Timestamp(official.observed_at):
                        raise ValueError("completion_acquired_after_revision")
                    report["completion_witness"] = witness
                    # Search visible timing signals, but absence on a different
                    # unreviewed template is explicitly NOT a timing admission.
                    text = visible(reader.read(folder / entry["html"]))
                    report["completion_page_timing_signals"] = sorted(set(timing.SIGNALS.findall(text)))
                    contexts = [text[max(0, m.start()-100):m.end()+180].strip()
                                for m in timing.SIGNALS.finditer(text)]
                    report["completion_page_timing_contexts"] = contexts
                    if contexts:
                        registry.append({"identity": identity, "classification": "VISIBLE_TIMING_WORDS_REQUIRE_CONTEXT",
                                         "raw_sha256": witness["raw_sha256"],
                                         "context_sha256": sha("\n".join(contexts).encode("utf-8")),
                                         "match_interruption_proven": False,
                                         "warning": "League breaks/editorial previews can contain the same words; not an automatic interruption"})

                detail_candidates = sfms_by_url.get(r.source_url, [])
                report["saved_sfms02_details"] = detail_candidates
                reviewed = []
                for candidate in detail_candidates:
                    raw = reader.read(candidate["raw"])
                    parsed = parse_detail(raw.decode("utf-8-sig"), expected_match_id=r.match_id)
                    if (parsed["home_score_90"], parsed["away_score_90"]) != (int(r.home_score), int(r.away_score)):
                        raise ValueError("SFMS02_regulation_mismatch")
                    for side in ("home", "away"):
                        team = master.resolve_team_id(parsed[side + "_team_detail"], source="jleague_official", on=day)
                        if team != getattr(r, side + "_team_id"):
                            raise ValueError("SFMS02_TeamMaster_mismatch")
                    try:
                        notes = timing.timing_notes(raw)
                        review = "NO_TIMING_SIGNAL_IN_RECOGNIZED_SFMS02_REMARKS" if not notes else "UNREVIEWED_TIMING_NOTE"
                    except ValueError as exc:
                        review, notes = "UNKNOWN_REMARKS_TEMPLATE", [str(exc)]
                    reviewed.append({"raw_sha256": candidate["raw_sha256"], "review": review, "notes": notes})
                    if notes:
                        registry.append({"identity": identity, "classification": review, "notes": notes})
                report["timing_detail_review"] = reviewed
                report["timing_evidence_status"] = ("CACHE_REMARKS_REVIEWED_ORIGINAL_SCHEDULE_UNPROVEN" if reviewed
                                                     and all(r["review"].startswith("NO_TIMING_SIGNAL") for r in reviewed)
                                                     else "MISSING_TIMING_DETAIL_OR_REVIEW")
                # Keep schedule provenance separate even for the eleven pages.
                reasons = ["ORIGINAL_SCHEDULE_OR_DATE_CHANGE_HISTORY_NOT_ESTABLISHED"]
                if not detail_candidates:
                    reasons.append("MISSING_RECOGNIZED_TIMING_REMARKS_OR_EQUIVALENT_OFFICIAL_ANNOTATION")
                    missing.append({"identity": identity, "data_site_match_id": r.match_id,
                                    "url": r.source_url, "url_basis": "EXACT_LINK_IN_SAVED_OFFICIAL_LISTING",
                                    "needed": "Official detail remarks / restart-postponement chronology with acquisition metadata",
                                    "network_fetched": False})
                report["hold_reasons"] = reasons
                report["source_fetched_at_utc"] = (report["completion_witness"]["fetched_at_utc"] if label == "ongoing"
                                                     else max([acquisition["j1_search.html"]["fetched_at_utc"]]
                                                              + [c["fetched_at_utc"] for c in detail_candidates]))
                evidence.append(report)

        appearances = []
        for row in evidence:
            for side in ("home", "away"):
                appearances.append((row["source_date"], row[side + "_team_id"]))
        duplicates = [list(k) for k, count in Counter(appearances).items() if count > 1]
        if duplicates:
            registry.append({"classification": "SAME_DAY_CLUB_COLLISION", "cases": duplicates})
        # No partly evidenced 2026 replay: make the refusal concrete. The exact
        # expected universe includes all 300; missing rows may not become zero.
        refusal = None
        if evidence:
            expected_universe = [adapter.Fixture(r["identity"], r["home_team_id"], r["away_team_id"],
                                                 r["source_reported_kickoff"], "completed") for r in evidence]
            try:
                adapter.replay((), (), team_ids=sorted({a.team_id for a in master.aliases}),
                               universe=expected_universe, covered_through=pd.Timestamp(official.observed_at).tz_convert("Asia/Tokyo").normalize().isoformat(),
                               timing_admissions={})
            except ValueError as exc:
                refusal = str(exc)
            if refusal != "missing_or_extra_completed_history":
                raise ValueError("incomplete_real_history_did_not_stop")
        scheduled = official.schedule[official.schedule.status.ne("completed")]
        summary = {
            "status": "HOLD_HISTORY_EVIDENCE_OR_ADAPTER", "HISTORY": "HOLD", "PREDICTION": "HOLD",
            "study_id": "nn_v2_residual_20261020_01", "model": "TRAINED_AND_SEALED_RESEARCH_ONLY",
            "revision": pointer, "revision_observed_at_utc": official.observed_at,
            "completed_count_basis": "validated accepted revision completed_matches.csv, not a fixed constant",
            "historical_rows": len(historical), "hyakunen_rows": len(hyakunen), "ongoing_completed_rows": len(ongoing),
            "ongoing_uncompleted_rows_excluded_from_results": len(scheduled),
            "hyakunen_detail_pages": sum(bool(r["saved_sfms02_details"]) for r in evidence if r["series"] == "hyakunen"),
            "missing_timing_detail_candidates": len(missing),
            "missing_by_series": {s: sum(not r["saved_sfms02_details"] for r in evidence if r["series"] == s)
                                  for s in ("hyakunen", "ongoing")},
            "timing_unadmitted_matches": sum(not r["result_effective_event_admitted"] for r in evidence),
            "original_schedule_unproven_matches": sum(not r["original_schedule_as_of_proven"] for r in evidence),
            "timing_registry_entries": len(registry), "same_day_club_collisions": len(duplicates),
            "saved_date_change_matches": sum(r.get("date_changes_in_saved_revisions", False) for r in evidence),
            "saved_kickoff_change_matches": sum(r.get("date_or_kickoff_changes_in_saved_revisions", False) for r in evidence),
            "visible_timing_word_pages_requiring_context": sum(bool(r.get("completion_page_timing_signals")) for r in evidence),
            "saved_pre_start_schedule_observations_present": sum(r["first_saved_pre_start_schedule"] is not None for r in evidence),
            "completion_witnesses_verified": len(ongoing), "sealed_completion_bindings": len(binding_by_key),
            "hyakunen_listing_result_identities_verified": len(hyakunen),
            "hyakunen_pk_matches_excluded_from_result": int(special.pk_played.sum()),
            "hyakunen_et_matches_using_90_minute_scores": int(special.extra_time_played.sum()),
            "adapter_implementation": "SYNTHETIC_AND_LEGACY_PARITY_VERIFIED_REAL_2026_EVIDENCE_HOLD",
            "implementation_defects": [], "real_2026_adapter_features_emitted": 0,
            "real_2026_replay_refusal": refusal,
            "evidence_gaps": ["Recognized remarks/equivalent timing chronology missing for listed candidates",
                              "Original schedule/date-change history not established; final result existence is insufficient"],
            "source_publication_time_proven": False, "network_fetches": 0, "real_data_fits": 0,
            "performance_evaluations": 0, "real_match_probability_calculations": 0,
            "T0_registrations": 0, "enrolled_targets": 0, "future_predictions_saved": 0,
            "forbidden_learning_or_inference_calls": len(forbidden_calls),
            "Phase_A": "BLOCKED", "Phase_B": "NOT_AUTHORIZED",
        }
    # Detect concurrent changes, including sources read by existing pure helpers.
    with ThreadPoolExecutor(max_workers=8) as pool:
        checked = dict(pool.map(lambda item: (item[0], sha(Path(item[0]).read_bytes())), reader.reads.items()))
    if checked != reader.reads or reader.obj(runtime / "official/latest.json") != pointer:
        raise ValueError("source_changed_during_audit")
    output.mkdir(exist_ok=False)
    for name, value in (("summary.json", summary), ("match-evidence.json", evidence),
                        ("missing-evidence.json", missing), ("timing-exception-registry.json", registry),
                        ("source-witness-inventory.json", {"details": inventory, "saved_official_articles": articles}),
                        ("accepted-revisions.json", revision_inventory), ("legacy-parity.json", legacy_report),
                        ("legacy-feature-audit.json", rows), ("legacy-event-audit.json", trace),
                        ("input-sha256.json", input_pins), ("source-sha256.json", reader.reads),
                        ("binding-reference.json", {"binding_sha256": adapter.BINDING_SHA, "revalidated": True,
                                                   "match_page_ids": [b["match_page_id"] for b in binding["bindings"]]})):
        write(output, name, value)
    write(output, "SHA256-MANIFEST.json", {p.name: sha(p.read_bytes()) for p in sorted(output.iterdir())})
    print(json.dumps(summary, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    sys.addaudithook(deny_network)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "runtime", "output", "protection"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--protection-sha", required=True)
    execute(parser.parse_args())
