"""Explicit research-only reconciliation of four stored completion witnesses.

Pure byte inputs; no file writes, network, model loading or prediction path.
This does not repair a publication or make the broader HISTORY gate READY.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
import csv
import hashlib
import io
import json
from pathlib import PurePosixPath

from src.collect.jleague_ongoing_source import parse_completion_evidence


STUDY = "nn_v2_residual_20261020_01"
ACTUAL = "20261017T133613718777Z-21f0d67d"
DECLARED = "20261017T231757938417Z-edbc58a3"
ALLOWED = {
    "101101": ("chiba", "nagasaki"),
    "101102": ("mito", "shimizu"),
    "101103": ("tokyov", "hiroshima"),
    "101104": ("kawasakif", "nagoya"),
}
KEYS = {"j1_2026_2027:" + ":".join(clubs) for clubs in ALLOWED.values()}


@dataclass(frozen=True)
class Packet:
    """One source directory, identified independently from its content hash."""

    name: str
    manifest: bytes
    files: dict[str, bytes]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def require(condition, code):
    if not condition:
        raise ValueError(code)


def utc(value):
    parsed = datetime.fromisoformat(value)
    require(parsed.utcoffset() == timedelta(0), "timestamp_not_utc")
    return parsed


def object_json(data):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    def invalid_constant(_):
        raise ValueError("nonfinite_json")
    return json.loads(data, object_pairs_hook=unique, parse_constant=invalid_constant)


def name_only(name):
    require(isinstance(name, str) and PurePosixPath(name).name == name
            and "\\" not in name and name not in {"", ".", ".."}, "unsafe_name")
    return name


def checked_packet(packet, pin):
    require(digest(packet.manifest) == pin, "manifest_sha_mismatch")
    name_only(packet.name)
    return object_json(packet.manifest)


def revision(packet, pin):
    m = checked_packet(packet, pin)
    require(m["format_version"] == "ongoing-v2"
            and m["summary"]["publication_status"] == "published", "unaccepted_revision")
    require(digest(encoded(m["run"])) == packet.name, "revision_identity_mismatch")
    require(set(packet.files) == set(m["files"]), "revision_file_set_mismatch")
    for name, expected in m["files"].items():
        require(digest(packet.files[name_only(name)]) == expected, "revision_file_sha_mismatch")
    rows = object_json(packet.files["observations.json"])
    require(len({r["fixture_key"] for r in rows}) == len(rows), "duplicate_fixture")
    # Both typed namespaces must have a single fixture owner.
    for field in ("match_page_id", "data_site_match_id"):
        ids = [r[field] for r in rows if r.get(field)]
        require(len(set(ids)) == len(ids), "identity_collision")
    selected = {r["fixture_key"]: r for r in rows if r["fixture_key"] in KEYS}
    require(set(selected) == KEYS, "incomplete_four")
    # Published completed CSV must agree with the source observation, including
    # the erroneous origin fields; never silently replace that declaration.
    completed = list(csv.DictReader(io.StringIO(packet.files["completed_matches.csv"].decode("utf-8"))))
    require(len({r["fixture_key"] for r in completed}) == len(completed), "duplicate_completed")
    by_key = {r["fixture_key"]: r for r in completed}
    for key, row in selected.items():
        if row["status"] == "completed":
            require(key in by_key, "completed_missing")
            for field, value in row.items():
                if field in by_key[key]:
                    require(by_key[key][field] == ("" if value is None else str(value)),
                            "completed_projection_mismatch")
    return m, selected


def snapshot(packet, pin):
    m = checked_packet(packet, pin)
    require(m["snapshot_id"] == packet.name and m["format_version"] == "ongoing-v2"
            and m["competition_key"] == "j1_2026_2027", "snapshot_identity_mismatch")
    require(digest(encoded(m["sources"])) == m["input_fingerprint"], "snapshot_fingerprint")
    require(bool(m["sources"]) and m["sources"][0]["kind"] == "listing", "listing_missing")
    wanted = []
    urls = []
    for index, entry in enumerate(m["sources"]):
        require(entry["kind"] == ("listing" if index == 0 else "evidence"), "source_kind")
        raw_name, meta_name = name_only(entry["html"]), name_only(entry["metadata"])
        require(meta_name == raw_name.removesuffix(".html") + ".metadata.json", "metadata_name")
        wanted.extend([raw_name, meta_name]); urls.append(entry["source_url"])
        raw, metadata = packet.files[raw_name], packet.files[meta_name]
        require(digest(raw) == entry["sha256"] and digest(metadata) == entry["metadata_sha256"],
                "raw_metadata_sha_mismatch")
        meta = object_json(metadata)
        require(meta["requested_url"] == meta["final_url"] == entry["source_url"]
                and type(meta["status"]) is int and meta["status"] == 200
                and type(meta["bytes"]) is int and meta["bytes"] == len(raw)
                and meta["sha256"] == entry["sha256"]
                and "text/html" in meta["content_type"].lower(), "metadata_contract")
        require(meta["fetched_at_utc"] == entry["fetched_at_utc"], "fetch_clock_mismatch")
        require(utc(meta["request_started_at_utc"]) <= utc(meta["fetched_at_utc"])
                <= utc(m["observed_at_utc"]) <= utc(m["created_at_utc"]), "clock_order")
    require(len(set(wanted)) == len(wanted) and len(set(urls)) == len(urls)
            and set(wanted) == set(packet.files), "snapshot_file_set")
    require(m["listing_fetched_at_utc"] == m["sources"][0]["fetched_at_utc"]
            and utc(m["observed_at_utc"]) == max(utc(e["fetched_at_utc"]) for e in m["sources"]),
            "observation_clock_mismatch")
    return m


def selected_evidence(packet, manifest, page_id):
    url = f"https://www.jleague.jp/match/j1/2026/{page_id}/"
    entries = [e for e in manifest["sources"] if e["kind"] == "evidence" and e["source_url"] == url]
    require(len(entries) == 1, "evidence_cardinality")
    entry = entries[0]
    parsed = parse_completion_evidence(packet.files[entry["html"]].decode("utf-8-sig"), source_url=url)
    home, away = ALLOWED[page_id]
    expected = {"fixture_key": f"j1_2026_2027:{home}:{away}", "competition_key": "j1_2026_2027",
                "match_date": "2026-10-11", "round": 9, "home_club": home, "away_club": away,
                "match_page_id": page_id, "verified": True, "evidence_type": "official_game_over_section"}
    require(all(parsed[k] == v for k, v in expected.items()), "official_identity_or_finish")
    return entry, parsed


def reconcile(revisions, snapshots, pins, *, verified_at_utc):
    """Validate the complete chain and return a deterministic additive binding.

    Caller supplies externally pinned manifests, not hashes recomputed after
    accepting arbitrary replacements. Exceptions mean HOLD; no partial READY.
    """
    require(set(snapshots) == {ACTUAL, DECLARED}, "snapshot_set")
    require(set(pins) == {"revisions", "snapshots"}, "pin_schema")
    require(set(pins["revisions"]) == {p.name for p in revisions}
            and len(revisions) == len(pins["revisions"])
            and set(pins["snapshots"]) == set(snapshots), "pin_set")
    sm = {sid: snapshot(p, pins["snapshots"][sid]) for sid, p in snapshots.items()}
    require(all(sid == p.name for sid, p in snapshots.items()), "snapshot_map_identity")
    require(sm[DECLARED]["previous_snapshot_id"] == ACTUAL, "snapshot_lineage")
    require(utc(sm[ACTUAL]["created_at_utc"]) < utc(sm[DECLARED]["listing_fetched_at_utc"]),
            "snapshot_clock_lineage")
    chain = [(p, *revision(p, pins["revisions"][p.name])) for p in revisions]
    chain.sort(key=lambda item: item[1]["sequence"])
    require([m["sequence"] for _, m, _ in chain] == list(range(11, 11 + len(chain)))
            and len(chain) >= 4, "revision_sequence")
    for previous, current in zip(chain, chain[1:]):
        require(current[1]["run"]["previous_accepted_revision_id"] == previous[0].name,
                "revision_lineage")
    pre, original, mixed = chain[:3]
    require(original[1]["snapshot_id"] == ACTUAL and mixed[1]["snapshot_id"] == DECLARED,
            "revision_snapshot_binding")
    for packet, manifest, _ in (original, mixed):
        require(manifest["run"]["snapshot_sha256"] == pins["snapshots"][manifest["snapshot_id"]],
                "run_snapshot_sha")
    now = utc(verified_at_utc)
    require(all(now >= utc(m["summary"]["observed_at_utc"]) for _, m, _ in chain),
            "verification_backdated")
    bindings = []
    for page_id in ALLOWED:
        entry, parsed = selected_evidence(snapshots[ACTUAL], sm[ACTUAL], page_id)
        newer, reparsed = selected_evidence(snapshots[DECLARED], sm[DECLARED], page_id)
        require(parsed == reparsed and entry["sha256"] != newer["sha256"], "reacquired_evidence_mismatch")
        key = parsed["fixture_key"]
        candidate, first = pre[2][key], original[2][key]
        require(candidate["status"] == "candidate", "prior_not_candidate")
        data_id = candidate["data_site_match_id"]
        require(isinstance(data_id, str) and data_id.isascii() and data_id.isdigit()
                and len(data_id) == 5, "data_site_identity")
        result = 2 if parsed["home_score"] > parsed["away_score"] else (
            0 if parsed["home_score"] < parsed["away_score"] else 1)
        fields = ("fixture_key", "competition_key", "match_date", "round", "home_club", "away_club",
                  "home_score", "away_score")
        for _, _, rows in chain:
            require(all(rows[key][f] == parsed[f] for f in fields), "published_identity_or_score")
            require(rows[key]["data_site_match_id"] == candidate["data_site_match_id"]
                    and rows[key]["match_id_namespace"] == "jleague_data_site"
                    and rows[key]["match_id"] == candidate["data_site_match_id"]
                    and rows[key]["result"] == result, "typed_namespace_or_result")
        require(first["completion_origin_snapshot"] == ACTUAL, "initial_origin")
        for _, m, rows in chain[1:]:
            r = rows[key]
            require(r["status"] == "completed" and r["match_page_id"] == page_id
                    and r["evidence_sha256"] == entry["sha256"]
                    and r["evidence_fetched_at_utc"] == entry["fetched_at_utc"]
                    and r["evidence_url"] == entry["source_url"]
                    and r["match_page_origin_snapshot"] == ACTUAL
                    and r["match_page_origin_revision"] == original[0].name, "retained_witness_mismatch")
            require(utc(entry["fetched_at_utc"]) <= utc(r.get("evidence_fetched_at_utc")), "evidence_clock")
            require(utc(entry["fetched_at_utc"]) <= utc(m["summary"]["observed_at_utc"]),
                    "publication_before_fetch")
        for _, _, rows in chain[2:]:
            require(rows[key]["completion_origin_snapshot"] == DECLARED, "original_discrepancy_lost")
        bridges = list(csv.DictReader(io.StringIO(original[0].files["identity_bridges.csv"].decode("utf-8"))))
        bridges = [b for b in bridges if b["fixture_key"] == key]
        require(len(bridges) == 1, "bridge_cardinality")
        bridge = bridges[0]
        require(bridge["match_page_id"] == page_id
                and bridge["data_site_match_id"] == candidate["data_site_match_id"]
                and bridge["match_page_evidence_sha256"] == entry["sha256"]
                and bridge["match_page_evidence_fetched_at_utc"] == entry["fetched_at_utc"]
                and bridge["match_page_evidence_url"] == entry["source_url"]
                and bridge["match_page_origin_snapshot"] == ACTUAL
                and bridge["match_page_origin_revision"] == original[0].name
                and bridge["established_snapshot"] == ACTUAL
                and bridge["established_revision"] == original[0].name, "bridge_origin")
        for packet, _, _ in chain[2:]:
            carried = list(csv.DictReader(io.StringIO(packet.files["identity_bridges.csv"].decode("utf-8"))))
            require([b for b in carried if b["fixture_key"] == key] == [bridge], "bridge_changed")
        require(utc(entry["fetched_at_utc"]).date().isoformat() == "2026-10-17", "unexpected_fetch_day")
        latest = chain[-1][2][key]
        bindings.append({
            "fixture_key": key, "match_page_id": page_id, "match_page_namespace": "jleague_match_page",
            "data_site_match_id": candidate["data_site_match_id"], "data_site_namespace": "jleague_data_site",
            "identity_and_regulation_result": parsed, "publication_revision": chain[-1][0].name,
            "original_publication_reference": {k: latest.get(k) for k in (
                "completion_origin_snapshot", "completion_origin_revision", "evidence_sha256",
                "evidence_fetched_at_utc", "match_page_origin_snapshot", "match_page_origin_revision")},
            "first_completed_revision": original[0].name, "first_mixed_origin_revision": mixed[0].name,
            "actual_snapshot": ACTUAL, "actual_source": dict(entry),
            "declared_snapshot": DECLARED, "declared_source": dict(newer),
            "declared_origin_matches_published_raw": False,
            "diagnosis": "BRIDGE_HYDRATION_RETAINS_OLD_WITNESS_WITH_NEW_COMPLETION_ORIGIN",
            "decision": "ADOPT_RESEARCH_REFERENCE_ONLY",
            "reason": "Original accepted revision, typed bridge, raw, metadata, strict parser and later independent reacquisition agree.",
            "human_review_basis": "Compare sequences 11/12/13 and unchanged bridge; retain the invalid declared origin separately.",
            "known_available_at_utc": entry["fetched_at_utc"],
            "available_at_match_day_proven": False,
        })
    require(len(bindings) == 4 and {b["fixture_key"] for b in bindings} == KEYS, "incomplete_four")
    return {"schema": "nn_v2_completion_witness_binding_v1", "study_id": STUDY,
            "verified_at_utc": verified_at_utc, "status": "COMPLETION_WITNESS_RECONCILED_RESEARCH_ONLY",
            "pins": pins, "bindings": bindings, "original_publication_modified": False,
            "phase2_4_history": "HOLD", "phase2_4_prediction": "HOLD",
            "not_authorized": ["real_probability_calculation", "prediction", "enrollment", "T0", "operational_repair"]}


def validate_sealed_binding(content, expected_sha, revisions, snapshots, pins):
    """Verify the seal AND regenerate from exact pinned source packets."""
    require(digest(content) == expected_sha, "binding_sha_mismatch")
    manifest = object_json(content)
    expected = reconcile(revisions, snapshots, pins, verified_at_utc=manifest["verified_at_utc"])
    require(manifest == expected, "binding_content_mismatch")
    return manifest
