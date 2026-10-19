"""Wholly synthetic bytes/labels: never load stored match or model data."""

import copy
import csv
import io
import json
import socket

import pytest

from src.modeling.nn_v2_completion_binding import (
    ACTUAL, ALLOWED, DECLARED, Packet, digest, encoded, reconcile,
    snapshot, validate_sealed_binding,
)


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def html(page_id, home, away, marker):
    return f'''<!-- SYNTHETIC {marker}: no saved official HTML -->
    <link rel="canonical" href="https://www.jleague.jp/match/j1/2026/{page_id}/">
    <div class="o-page-header--game-details o-page-header--game-details--post-game">
    <div class="a-tournament-logo--j1"><img alt="明治安田Ｊ１リーグ"></div>
    <p class="o-page-header__date">2026/10/11 (日) 18:00 KO</p>
    <p class="o-page-header__section">第9節</p>
    <a class="o-page-header__club--home" href="/club/{home}/"></a>
    <a class="o-page-header__club--away" href="/club/{away}/"></a>
    <p class="o-page-header__match-score">3</p><p class="o-page-header__match-score">0</p></div>
    <section id="game-over" class="p-game-details-summary-tab__game-over"><h3>試合終了</h3>
    <p class="o-team-comparison__score">3</p><p class="o-team-comparison__score">0</p></section>'''.encode()


def make_snapshot(sid, mutate=None):
    hour = "13" if sid == ACTUAL else "23"
    sources, files = [], {}
    for i, page in enumerate([None, *ALLOWED]):
        raw_name = "listing.html" if page is None else f"evidence_{i:03}.html"
        meta_name = raw_name.replace(".html", ".metadata.json")
        url = "https://data.j-league.or.jp/SFMS01/search?synthetic=1" if page is None else (
            f"https://www.jleague.jp/match/j1/2026/{page}/")
        raw = b"SYNTHETIC LISTING" if page is None else html(page, *ALLOWED[page], sid)
        clock = f"2026-10-17T{hour}:00:0{i}+00:00"
        meta = {"requested_url": url, "final_url": url, "status": 200,
                "request_started_at_utc": clock, "fetched_at_utc": clock,
                "content_type": "text/html; charset=utf-8", "bytes": len(raw), "sha256": digest(raw)}
        if mutate:
            raw, meta = mutate(sid, page, raw, meta)
            meta.update(bytes=len(raw), sha256=digest(raw))
        files[raw_name], files[meta_name] = raw, encoded(meta)
        sources.append({"html": raw_name, "metadata": meta_name, "source_url": url,
                        "sha256": digest(raw), "metadata_sha256": digest(encoded(meta)),
                        "fetched_at_utc": meta["fetched_at_utc"], "kind": "listing" if page is None else "evidence"})
    m = {"snapshot_id": sid, "format_version": "ongoing-v2", "competition_key": "j1_2026_2027",
         "previous_snapshot_id": ACTUAL if sid == DECLARED else "synthetic-previous",
         "listing_fetched_at_utc": sources[0]["fetched_at_utc"],
         "observed_at_utc": f"2026-10-17T{hour}:00:04+00:00",
         "created_at_utc": f"2026-10-17T{hour}:00:05+00:00",
         "sources": sources, "input_fingerprint": digest(encoded(sources))}
    return Packet(sid, encoded(m), files)


def bundle(*, mutate_source=None, mutate_row=None, mutate_bridge=None):
    snapshots = {sid: make_snapshot(sid, mutate_source) for sid in [ACTUAL, DECLARED]}
    pins = {"snapshots": {sid: digest(p.manifest) for sid, p in snapshots.items()}, "revisions": {}}
    revisions, previous, origin_id, bridges = [], "synthetic-previous-revision", None, None
    entries = json.loads(snapshots[ACTUAL].manifest)["sources"][1:]
    for seq in range(11, 15):
        sid = ACTUAL if seq == 12 else DECLARED if seq == 13 else f"synthetic-snapshot-{seq}"
        run = {"snapshot_id": sid, "snapshot_sha256": pins["snapshots"].get(sid, "a" * 64),
               "previous_accepted_revision_id": previous}
        revision_id = digest(encoded(run))
        if seq == 12:
            origin_id = revision_id
        rows = []
        for i, ((page, (home, away)), entry) in enumerate(zip(ALLOWED.items(), entries)):
            row = {"fixture_key": f"j1_2026_2027:{home}:{away}", "competition_key": "j1_2026_2027",
                   "match_date": "2026-10-11", "round": 9, "home_club": home, "away_club": away,
                   "home_score": 3, "away_score": 0, "result": 2,
                   "data_site_match_id": str(34001 + i), "match_id": str(34001 + i),
                   "match_id_namespace": "jleague_data_site", "match_page_id": page if seq > 11 else None,
                   "status": "completed" if seq > 11 else "candidate",
                   "evidence_sha256": entry["sha256"], "evidence_fetched_at_utc": entry["fetched_at_utc"],
                   "evidence_url": entry["source_url"], "completion_origin_snapshot": ACTUAL if seq == 12 else DECLARED,
                   "completion_origin_revision": previous if seq >= 14 else None,
                   "match_page_origin_snapshot": ACTUAL, "match_page_origin_revision": origin_id}
            if mutate_row:
                mutate_row(seq, row)
            rows.append(row)
        if seq == 12:
            bridges = [{"fixture_key": r["fixture_key"], "match_page_id": r["match_page_id"],
                        "data_site_match_id": r["data_site_match_id"],
                        "match_page_evidence_sha256": r["evidence_sha256"],
                        "match_page_evidence_fetched_at_utc": r["evidence_fetched_at_utc"],
                        "match_page_evidence_url": r["evidence_url"],
                        "match_page_origin_snapshot": ACTUAL, "match_page_origin_revision": origin_id,
                        "established_snapshot": ACTUAL, "established_revision": origin_id} for r in rows]
        these_bridges = copy.deepcopy(bridges or [{"fixture_key": "synthetic-unused"}])
        if mutate_bridge:
            mutate_bridge(seq, these_bridges)
        # Nonempty synthetic CSV for the candidate revision; no target is completed.
        completed = rows if seq > 11 else [dict(rows[0], fixture_key="synthetic-unused")]
        files = {"observations.json": encoded(rows), "completed_matches.csv": csv_bytes(completed),
                 "identity_bridges.csv": csv_bytes(these_bridges)}
        m = {"sequence": seq, "snapshot_id": sid, "format_version": "ongoing-v2", "run": run,
             "summary": {"publication_status": "published", "observed_at_utc": "2026-10-18T00:00:00+00:00"},
             "files": {n: digest(v) for n, v in files.items()}}
        packet = Packet(revision_id, encoded(m), files)
        revisions.append(packet); pins["revisions"][revision_id] = digest(packet.manifest)
        previous = revision_id
    return revisions, snapshots, pins


def run(data):
    return reconcile(*data, verified_at_utc="2026-10-20T01:00:00+00:00")


def test_complete_four_preserve_bad_declaration_and_late_acquisition():
    data = bundle(); m = run(data)
    assert len(m["bindings"]) == 4
    assert m["phase2_4_history"] == m["phase2_4_prediction"] == "HOLD"
    for b in m["bindings"]:
        assert b["actual_snapshot"] == ACTUAL != b["original_publication_reference"]["completion_origin_snapshot"]
        assert b["known_available_at_utc"].startswith("2026-10-17")
        assert b["available_at_match_day_proven"] is False
    assert validate_sealed_binding(encoded(m), digest(encoded(m)), *data) == m


@pytest.mark.parametrize("field,value", [
    ("match_page_id", "999999"), ("fixture_key", "j1_2026_2027:chiba:shimizu"),
    ("home_club", "mito"), ("away_club", "chiba"), ("round", 10),
    ("match_date", "2026-10-12"), ("home_score", 4), ("status", "candidate"),
    ("data_site_match_id", "101101"), ("match_id_namespace", "jleague_match_page"),
    ("completion_origin_snapshot", ACTUAL), ("match_page_origin_snapshot", DECLARED),
    ("evidence_fetched_at_utc", "2026-10-11T00:00:00+00:00"), ("result", 1),
])
def test_repinned_publication_disagreement_rejected(field, value):
    def mutate(seq, row):
        if seq == 14 and row["home_club"] == "chiba":
            row[field] = value
    with pytest.raises((ValueError, KeyError)):
        run(bundle(mutate_row=mutate))


@pytest.mark.parametrize("field,value", [
    ("fetched_at_utc", "2026-10-11T01:00:00+00:00"),
    ("request_started_at_utc", "2026-10-19T00:00:00+00:00"),
    ("fetched_at_utc", "2026-10-17T13:00:01"),
    ("status", 302), ("status", True), ("content_type", "application/json"),
    ("requested_url", "https://evil.example/"), ("final_url", "https://evil.example/"),
])
def test_repinned_metadata_corruption_rejected(field, value):
    def mutate(sid, page, raw, meta):
        if sid == ACTUAL and page == "101101":
            meta[field] = value
        return raw, meta
    with pytest.raises(ValueError):
        run(bundle(mutate_source=mutate))


@pytest.mark.parametrize("old,new", [
    (b"101101/", b"101102/"), (b"/club/chiba/", b"/club/mito/"),
    ("試合終了".encode(), "試合中".encode()),
    ("第9節".encode(), "第10節".encode()),
    (b"2026/10/11", b"2026/10/12"),
    ("明治安田Ｊ１リーグ".encode(), "明治安田Ｊ２リーグ".encode()),
])
def test_repinned_official_html_disagreement_rejected(old, new):
    def mutate(sid, page, raw, meta):
        return (raw.replace(old, new) if sid == ACTUAL and page == "101101" else raw), meta
    with pytest.raises(ValueError):
        run(bundle(mutate_source=mutate))


def test_raw_metadata_and_snapshot_tamper_rejected():
    revisions, snapshots, pins = bundle()
    p = snapshots[ACTUAL]; files = dict(p.files); files["evidence_001.html"] += b"tamper"
    snapshots[ACTUAL] = Packet(p.name, p.manifest, files)
    with pytest.raises(ValueError, match="raw_metadata_sha"):
        run((revisions, snapshots, pins))
    snapshots[ACTUAL] = Packet("changed-snapshot", p.manifest, p.files)
    with pytest.raises(ValueError, match="snapshot_identity"):
        run((revisions, snapshots, pins))


def test_manifest_pin_and_seal_tamper_rejected():
    data = bundle(); m = run(data)
    with pytest.raises(ValueError, match="binding_sha"):
        validate_sealed_binding(encoded(m) + b" ", digest(encoded(m)), *data)
    data[2]["snapshots"][ACTUAL] = "0" * 64
    with pytest.raises(ValueError, match="manifest_sha"):
        run(data)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "conflict", "extra", "backdate", "erase_mismatch"])
def test_even_resealed_binding_cannot_change_scope_or_history(mutation):
    data = bundle(); m = run(data)
    if mutation == "missing":
        m["bindings"].pop()
    elif mutation in {"duplicate", "conflict", "extra"}:
        extra = copy.deepcopy(m["bindings"][0])
        if mutation == "conflict":
            extra["actual_snapshot"] = DECLARED
        if mutation == "extra":
            extra["match_page_id"] = "999999"
        m["bindings"].append(extra)
    elif mutation == "backdate":
        m["verified_at_utc"] = "2026-10-11T00:00:00+00:00"
    else:
        m["bindings"][0]["original_publication_reference"]["completion_origin_snapshot"] = ACTUAL
    with pytest.raises(ValueError):
        validate_sealed_binding(encoded(m), digest(encoded(m)), *data)


def test_competing_bridge_rejected():
    def mutate(seq, rows):
        if seq == 14:
            rows.append(dict(rows[0], match_page_id="999999"))
    with pytest.raises(ValueError, match="bridge_changed"):
        run(bundle(mutate_bridge=mutate))


def test_collision_rejected():
    def mutate(seq, row):
        if seq == 14 and row["home_club"] == "mito":
            row["match_page_id"] = "101101"
    with pytest.raises(ValueError, match="identity_collision"):
        run(bundle(mutate_row=mutate))


def test_pure_validator_writes_nothing_and_never_uses_network(monkeypatch):
    data = bundle(); original = copy.deepcopy(data)
    def forbidden(*args, **kwargs):
        raise AssertionError("No file or network operations are permitted")
    monkeypatch.setattr("builtins.open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    assert run(data)["status"] == "COMPLETION_WITNESS_RECONCILED_RESEARCH_ONLY"
    assert data == original
