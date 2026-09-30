# J Stats team snapshot collector runbook

This collector saves **observed point-in-time season-to-date values**, not match-level stats or model features. Scope is official J.LEAGUE.jp 2026/27 ordinary J1 club rankings only. The fixed allowlists and known limitations are documented in [the collector design](J_STATS_TEAM_SNAPSHOT_COLLECTOR_DESIGN.md).

## Capture

From the repository root, with the project environment installed:

```powershell
.\.venv\Scripts\python.exe -m src.collect.jstats_team_snapshots
```

The default is the existing BASE_10 capture. For the prospective 37-stat contract use:

```powershell
.\.venv\Scripts\python.exe -m src.collect.jstats_team_snapshots --profile full
```

`--profile full` is exactly the existing `STATS + SUPPLEMENTAL_STATS`: 37 unique fixed slugs, 37 official page requests, 20 clubs per page, and 740 unique `(team_id, stat_name)` rows. It adds no unobserved route. All 37 pages must expose the same non-null official update date or the manifest remains `INCOMPLETE` and no CSV is published.

One run requests each allowlisted `/2026-27/{stat}/search-list/` page once and reads all 20 clubs from its embedded RSC ranking. It validates the 10 visible rows against the embedded data, the 20 club slugs against the local 2026/27 J1 schedule, and exact official names/slugs against TeamMaster. No club-by-club or JavaScript-bundle requests are needed. There is no automation or automatic retry.

The timestamp-based `snapshot_id` identifies one retrieval event. Raw HTML and `manifest.json` are saved under `data/raw/jstats_team_snapshots/<snapshot_id>/`; a complete CSV (200 rows for BASE_10 or 740 for FULL_37) is saved at `data/processed/jstats_team_snapshots/<snapshot_id>.csv`. Both paths are ignored by Git. Existing snapshot IDs are never overwritten. Do not edit or replace raw pages after capture; the manifest holds each page's SHA-256.

If any page, identity, stat value, or 20-club check fails, the run stops. Fetched pages may remain with an `INCOMPLETE` manifest, but **no processed CSV is published**. Diagnose the source change and rerun as a new retrieval event; never treat an incomplete directory as an official snapshot.

`retrieved_at` is the collector's UTC run time. `source_updated_date_jst` is the day displayed on the official page. The site does not expose a verified update time or synchronized per-club match count, so `source_updated_at` and `games_played` remain null. Do not backfill either from schedule counts or turn a displayed update date into midnight. Retain `source_url`, raw HTML, and hash for later review.

For future manual captures, wait until a J1 matchday ends **and** the official stats page visibly updates. Source lag and revisions are not yet characterized, so immediate post-match auto-capture is not assumed safe. New observations must have new snapshot IDs. This data-collection stream is independent of the frozen Champion/Challenger evaluation and the opened 2026/27 lockbox. Snapshot differences, match-level reconstruction, historical backfill, prediction, and model evaluation are outside this collector's scope.

## One-page source-state probe and capture gate

After a matchday, wait until the following day or later and run the lightweight probe from the repository root:

```powershell
.\.venv\Scripts\python.exe -m src.collect.jstats_snapshot_probe
```

The probe makes exactly one request to the existing allowlisted `shoot` page. It requires HTTP 200 without a redirect, the exact official URL and HTML content type, then uses the collector's existing parser to validate all 20 schedule clubs and exact TeamMaster identities. Output retains the URL, UTC retrieval time, official source-state date, raw SHA-256, latest saved logical FULL_37 date, and one of:

- `SOURCE_STATE_ADVANCED`: the official displayed date is newer than the registry date.
- `SOURCE_STATE_UNCHANGED`: it equals the registry date; do nothing.
- `SOURCE_STATE_REGRESSED`: it is older; stop and investigate.
- `SOURCE_STATE_UNKNOWN`: the date, schema, identity, HTTP provenance, or registry state could not be validated; stop and investigate.

Probe HTML and its manifest are kept separately under `data/raw/jstats_snapshot_probes/<probe_id>/`. They are observations for update detection only and are never registered as FULL_37 snapshots.

To enable the explicit gate, use:

```powershell
.\.venv\Scripts\python.exe -m src.collect.jstats_snapshot_probe --capture-if-advanced
```

The command first makes the one-page probe request. Only `SOURCE_STATE_ADVANCED` calls the existing FULL_37 collector, once and without automatic retry. Thus an unchanged run uses one official request and zero FULL_37 requests; an advanced successful run uses `1 + 37 = 38`. A failed full capture stops after the pages already requested, retains the collector's `INCOMPLETE` evidence, and is not retried automatically.

The probe date is only a trigger. It is **not** evidence that all pages share that date. The existing FULL_37 collector still fetches every one of the 37 pages and independently requires one uniform, non-null source date before publishing a COMPLETE CSV. After a successful capture, the registry contains the new logical date; an immediate rerun therefore returns `SOURCE_STATE_UNCHANGED` and creates no duplicate physical snapshot. Existing duplicate observations remain immutable.

Recommended operation:

```text
matchday ends
↓
wait until the following day or later, then probe
↓
UNCHANGED → do nothing
↓
ADVANCED → capture FULL_37 once
↓
verify the read-only registry
```

Do not schedule an immediate post-match capture: the official source can update after a lag. Offline tests inject a synthetic fetch response and registry report into the same probe/gate functions; tests never access the network.

## Read-only registry

Audit every saved physical snapshot and the logical FULL_37 ledger with:

```powershell
.\.venv\Scripts\python.exe -m src.collect.jstats_snapshot_registry
```

The registry recomputes raw SHA-256, validates manifest/HTTP provenance and COMPLETE/INCOMPLETE publication rules, checks processed schema/stat/team identity against TeamMaster and the schedule, and classifies exact BASE_10, SUPPLEMENTAL_27, FULL_37, or UNKNOWN profiles. A BASE_10 and SUPPLEMENTAL_27 pair is represented as one logical FULL_37 state only under the strict same-season/date, disjoint-stat, exact-union, same-20-team contract. No raw or CSV is physically merged. See [the registry contract](J_STATS_PROSPECTIVE_SNAPSHOT_REGISTRY.md).
