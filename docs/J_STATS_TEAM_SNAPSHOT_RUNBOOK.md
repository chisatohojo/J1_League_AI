# J Stats team snapshot collector runbook

This collector saves **observed point-in-time season-to-date values**, not match-level stats or model features. Scope is official J.LEAGUE.jp 2026/27 ordinary J1 club rankings only. The exact 10-stat allowlist and known limitations are documented in [the collector design](J_STATS_TEAM_SNAPSHOT_COLLECTOR_DESIGN.md).

## Capture

From the repository root, with the project environment installed:

```powershell
.\.venv\Scripts\python.exe -m src.collect.jstats_team_snapshots
```

One run requests each allowlisted `/2026-27/{stat}/search-list/` page once and reads all 20 clubs from its embedded RSC ranking. It validates the 10 visible rows against the embedded data, the 20 club slugs against the local 2026/27 J1 schedule, and exact official names/slugs against TeamMaster. No club-by-club or JavaScript-bundle requests are needed. There is no automation or automatic retry.

The timestamp-based `snapshot_id` identifies one retrieval event. Raw HTML and `manifest.json` are saved under `data/raw/jstats_team_snapshots/<snapshot_id>/`; the complete 200-row CSV is saved at `data/processed/jstats_team_snapshots/<snapshot_id>.csv`. Both paths are ignored by Git. Existing snapshot IDs are never overwritten. Do not edit or replace raw pages after capture; the manifest holds each page's SHA-256.

If any page, identity, stat value, or 20-club check fails, the run stops. Fetched pages may remain with an `INCOMPLETE` manifest, but **no processed CSV is published**. Diagnose the source change and rerun as a new retrieval event; never treat an incomplete directory as an official snapshot.

`retrieved_at` is the collector's UTC run time. `source_updated_date_jst` is the day displayed on the official page. The site does not expose a verified update time or synchronized per-club match count, so `source_updated_at` and `games_played` remain null. Do not backfill either from schedule counts or turn a displayed update date into midnight. Retain `source_url`, raw HTML, and hash for later review.

For future manual captures, wait until a J1 matchday ends **and** the official stats page visibly updates. Source lag and revisions are not yet characterized, so immediate post-match auto-capture is not assumed safe. New observations must have new snapshot IDs. This data-collection stream is independent of the frozen Champion/Challenger evaluation and the opened 2026/27 lockbox. Snapshot differences, match-level reconstruction, historical backfill, prediction, and model evaluation are outside this collector's scope.
