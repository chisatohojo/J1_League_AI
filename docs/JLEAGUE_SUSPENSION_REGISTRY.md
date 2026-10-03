# J.LEAGUE suspension PIT registry

## Purpose and boundary

`src.collect.jleague_suspension_registry` is a read-only integrity registry for immutable prospective J.LEAGUE suspension snapshots. It audits physical snapshot integrity, schema generation, linkage counts, capture-time kickoff provenance, evidence timing, unresolved player identity, and repeated notice versions.

The registry is not a feature builder and does not decide model eligibility. It never captures notices, discovers URLs, reads the current schedule, repairs data, migrates schemas, writes an index, fills missing suspensions as zero, fits a model, evaluates a model, or creates predictions. Its CLI prints a deterministic JSON observation summary to stdout only.

Default roots are:

```text
data/raw/jleague_suspensions/<snapshot_id>/
data/processed/jleague_suspensions/<snapshot_id>.csv
```

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m src.collect.jleague_suspension_registry
```

## Physical integrity

Every raw snapshot directory must contain a valid UTF-8 JSON-object `manifest.json`. The directory name and manifest `snapshot_id` must match, status must be exactly `COMPLETE` or `INCOMPLETE`, and `retrieved_at` must be timezone-aware UTC.

The registry requires a nonempty unique list of canonical operator-supplied notice URLs. Manifest page notice IDs, requested URLs, and raw HTML filenames must be unique. Each page URL must correspond exactly to its notice ID and belong to `source_urls`. Raw filenames must be safe basenames; every referenced `notice_*.html` must exist, have the recorded SHA-256, and match `response_size` when present. Missing, duplicated, extra, or modified raw pages are hard failures.

A `COMPLETE` snapshot requires exactly its `<snapshot_id>.csv` and all declared page/count contracts. An `INCOMPLETE` snapshot must not have a processed CSV and exposes no row evidence. A valid incomplete attempt remains in the physical registry with `integrity_status = VALID_INCOMPLETE`; it is never promoted or repaired.

## Schema generations

Generation is inferred only from the exact processed CSV header and the manifest field contract. Snapshot IDs and timestamps are never used as generation hints.

### `LEGACY_V1`

Legacy snapshots use the exact 23-column header that predates commit `aa643ba7`. They do not contain:

```text
target_kickoff_time
target_kickoff_at
schedule_sha256
kickoff_link_status
```

and their manifests do not contain the V2 schedule-provenance field set. Legacy snapshots are valid immutable observations, not damaged V2 snapshots. The registry supplies blank kickoff fields in memory only and classifies every legacy evidence row as `NOT_ASSESSABLE_LEGACY`. It never backfills from the current schedule.

### `KICKOFF_V2`

V2 snapshots use the exact current `src.collect.jleague_suspensions.CSV_FIELDS` header and require all of these manifest fields:

```text
schedule_path
schedule_sha256
exact_kickoff_linkage_count
unresolved_kickoff_count
```

The registry validates the frozen schedule SHA and kickoff values stored inside the snapshot. It does not read `data/processed/jleague/2026_27/schedule.csv` and does not require a historical SHA to match any later live schedule revision.

A legacy CSV with a V2 manifest, a V2 CSV with a legacy manifest, or a partial V2 manifest is a rejected hybrid state.

## Processed evidence integrity

For every COMPLETE snapshot, the registry verifies:

- exact header for its generation;
- row `snapshot_id` and `retrieved_at` against the manifest;
- notice IDs and source URLs against raw-page provenance;
- nonblank competition and exact `2026/27` season semantics;
- canonical ISO target dates;
- no duplicate source/player/club/target identity inside one snapshot;
- manifest row, team-link, match-link, unresolved-match, and player-link counts.

For KICKOFF_V2 it additionally verifies:

- one valid lowercase 64-hex `schedule_sha256` shared by manifest and all rows;
- the exact frozen kickoff-status enum;
- `EXACT` kickoff requires exact match linkage, exact source `HH:MM`, and a timezone-aware `+09:00` instant;
- the frozen clock/date and timestamp represent the same `Asia/Tokyo` instant;
- unresolved kickoff statuses never carry an invented timestamp;
- exact/unresolved kickoff counts match the processed rows.

These are integrity gates for captured evidence, not feature-readiness gates.

## Evidence timing status

The row-level `evidence_status` enum is exactly:

```text
PRE_KICKOFF_CONFIRMED
NOT_ASSESSABLE_LEGACY
NOT_ASSESSABLE_MATCH
NOT_ASSESSABLE_KICKOFF
POST_KICKOFF_RETRIEVAL
POST_KICKOFF_PUBLICATION
INVALID_TIME_PROVENANCE
```

Classification precedence is deterministic:

1. Legacy rows are `NOT_ASSESSABLE_LEGACY` with no schedule reconstruction.
2. Non-exact match linkage is `NOT_ASSESSABLE_MATCH`.
3. Non-exact kickoff linkage is `NOT_ASSESSABLE_KICKOFF`.
4. Invalid timestamps or impossible publication/update/retrieval ordering are `INVALID_TIME_PROVENANCE` and are never repaired.
5. Publication at or after kickoff is `POST_KICKOFF_PUBLICATION`.
6. Retrieval at or after kickoff is `POST_KICKOFF_RETRIEVAL`.
7. Only strict pre-kickoff publication and retrieval, plus a blank or strict pre-kickoff update, produce `PRE_KICKOFF_CONFIRMED`.

`PRE_KICKOFF_CONFIRMED` means only that this exact archived page version was observed with internally consistent evidence before the frozen target kickoff. It does not establish complete notice coverage, absence of other suspensions, player-level usability, or model eligibility.

## Notice versions

Repeated captures of the same `notice_id` are retained as separate physical observations. `NoticeVersion` orders them by `retrieved_at` and `snapshot_id`; earlier versions remain visible. Cross-snapshot repetition is expected and is never collapsed into a destructive “latest truth.” Duplicate source-target rows remain prohibited only within one processed snapshot.

## First live confirmed observation

The first real `PRE_KICKOFF_CONFIRMED` suspension observation is:

```text
snapshot_id                    20261003T224234521936Z
evidence rows                  7
exact match rows               7
exact kickoff rows             7
PRE_KICKOFF_CONFIRMED rows     7
distinct exact target matches  4
exact player linkage           0
```

All player identities remain unresolved. This milestone establishes exact match/time provenance only; it does not authorize name normalization, a player master, workload linkage, a suspension feature, or model use.

The same official notice was preserved immediately earlier in snapshot `20261003T221607715238Z`. At that observation, all seven rows correctly recorded `match_link_status = UNRESOLVED_NO_MATCH_ID` and `kickoff_link_status = UNRESOLVED_NO_MATCH`, because the local schedule identity state had not yet frozen the required official match IDs. It is a valid KICKOFF_V2 observation, not a failed snapshot.

The ongoing schedule revision pipeline subsequently published revision `fec1af40fe78218ba6b53719a415dff0496f9ab0703576587032370bfe68171a` with the explicitly evidenced match identities. A later immutable capture then recorded exact match/kickoff provenance. Both versions remain visible: the earlier observation preserves the unresolved identity state known then, and the later observation preserves the subsequently exact state. Neither is rewritten, merged, or collapsed into “latest truth.”

Across the current registry, 17 evidence rows remain player-unresolved. These are archive observation counts, not season coverage.

## Absence and identity policy

The archive contains only explicitly observed operator-supplied notices. No registry row means **unknown**, never “no suspended player.” The registry creates no team-level zero, match-level zero, suspended-player count, coverage percentage, or absence-derived feature.

`player_link_status = UNRESOLVED` remains unresolved. The registry does not normalize player names, create a player master, join player minutes, or infer identity from team/name similarity.

## Summary semantics

The CLI reports counts of physical COMPLETE/INCOMPLETE snapshots, schema generations, evidence rows, exact match/kickoff observations, timing statuses, unresolved player rows, distinct observed notice IDs, and distinct exactly linked target IDs. These are archive observation counts only. They are not historical or season coverage claims.

Historical production status remains **C — unsafe**. Prospective collection remains **B / operational prospective capture**. No model evaluation or prediction is part of this registry.
