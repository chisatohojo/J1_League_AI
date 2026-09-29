# J Stats prospective snapshot registry

## Purpose and boundary

`src/collect/jstats_snapshot_registry.py` is a read-only observation ledger for official J.LEAGUE.jp team cumulative snapshots. It verifies saved provenance and describes source states; it does not create model-ready features, reconstruct match-level values, fit a model, calculate predictive metrics, or consult the opened 2026/27 lockbox for selection.

## Physical snapshot contract

A physical snapshot is one retrieval event identified by `snapshot_id`. The registry requires its manifest, UTC `retrieved_at`, season, requested stat set, page records, raw HTML, requested/final URLs, HTTP status, and exact raw SHA-256. A raw mismatch is a hard failure.

A `COMPLETE` event must have one raw page per requested stat and a matching processed CSV. The CSV must use the frozen schema, contain the manifest `snapshot_id`, have no null team identity or duplicate `(team_id, stat_name)`, match exact TeamMaster official name/slug identity, contain the same 20 schedule clubs for every stat, and have exactly `20 × stat_count` rows. An `INCOMPLETE` event must not have a processed CSV.

Profiles are classified only by exact slug-set equality:

- `BASE_10`
- `SUPPLEMENTAL_27`
- `FULL_37`
- `UNKNOWN`

Counts alone never establish a profile.

## Source-state semantics

The displayed `source_updated_date_jst` is inspected on every saved page. One shared known date becomes the `source_state_date`. Mixed dates are `MIXED_SOURCE_STATE`; missing dates are `UNKNOWN_SOURCE_STATE`. Neither state is silently completed or admitted to the logical FULL_37 ledger. Retrieval time remains separate and is never substituted for the source update date.

## Logical FULL_37 state

A physical validated FULL_37 snapshot is one logical observation. A BASE_10 and SUPPLEMENTAL_27 pair may be represented logically as FULL_37 only when all of these are exact:

- same season and known `source_state_date`;
- exact BASE_10 and SUPPLEMENTAL_27 profiles;
- no stat overlap and exact FULL_37 union;
- the same exact 20 team IDs;
- both manifests/raw/processed artifacts pass registry validation.

The representation retains both source snapshot IDs. It does not merge or rewrite either physical directory or CSV. A shared date alone is insufficient.

## Transition structural audit

Adjacent ascending logical dates are compared only structurally. The audit retains ordinary-J1 completed match IDs in `(previous_source_state_date, source_state_date]`, counts each team's appearances, and emits `CLEAN_ONE_MATCH_PER_TEAM`, `MULTI_MATCH_INTERVAL`, `NO_MATCH_INTERVAL`, or `IDENTITY_MISMATCH`. It never subtracts cumulative stat values or attributes a delta to a match. The production-suitability conclusion in `J_STATS_SNAPSHOT_DELTA_FEASIBILITY.md` remains A=0.

## Current local audit

The 2026-09-30 task-time registry contained six physical retrievals: four COMPLETE and two INCOMPLETE. The 2026-09-14 BASE_10 and SUPPLEMENTAL_27 events form a valid reconstructed FULL_37 observation. Two physical FULL_37 captures have source date 2026-09-21, including the single bounded current capture `20260929T223909009656Z` (37 pages, 740 rows). Thus there are three valid logical FULL_37 observations over two distinct source-state dates. The only distinct-date transition, 2026-09-14 to 2026-09-21, is `CLEAN_ONE_MATCH_PER_TEAM` with ten ordinary-J1 matches.

The current capture's displayed date had not advanced beyond 2026-09-21. Future capture should wait until a completed matchday and a visibly advanced official update date, then perform one bounded FULL_37 run. Duplicate source dates remain immutable retrieval evidence, not a reason to overwrite or retry.

## Immutability and research separation

Raw and processed snapshots remain append-only and locally ignored by Git under the existing policy. The tracked registry, tests, and documentation do not add snapshot values to training data. The first-70 interim lockbox, later live results, and snapshot deltas must not select stats, tune a model, or alter Champion/Challenger decisions.
