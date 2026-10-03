# J.LEAGUE suspension snapshot collector runbook

## Scope

`src.collect.jleague_suspensions` captures prospective point-in-time snapshots of explicitly observed J.LEAGUE official suspension notices for the 2026/27 ordinary J1 season. It does not search archives, backfill 2015～2024, infer unlisted matches, build features, or run a model.

The operator supplies each canonical official notice URL. This is deliberate: the collector must not guess article IDs or treat search results as a complete archive.

## Run

From the repository root:

```powershell
python -m src.collect.jleague_suspensions --url https://www.jleague.jp/news/article/34896/
```

Repeat `--url` when one publication event has multiple confirmed official notice pages. Each URL is requested once, with at least 0.25 seconds between requests.

## Snapshot semantics

Every run receives a UTC timestamp-based `snapshot_id`. Raw pages and `manifest.json` are written to:

```text
data/raw/jleague_suspensions/<snapshot_id>/
```

A complete normalized CSV is written to:

```text
data/processed/jleague_suspensions/<snapshot_id>.csv
```

Existing snapshot IDs are never overwritten. Re-fetching the same notice in a later run is allowed and produces a new point-in-time version. `retrieved_at` is the collector observation time; it is never substituted for `published_at` or `updated_at`.

The initial snapshot may observe a notice after its listed target kickoff. Such a row starts the prospective archive but is not evidence that this collector possessed the information before that historical kickoff.

## Capture-time schedule provenance

At the beginning of each snapshot run, the collector requires the configured schedule path to be a regular file and reads it once as exact bytes. The same bytes are used both to parse linkage rows and to compute SHA-256. `manifest.json` records:

- `schedule_path`: repository-relative POSIX path when the schedule is inside the repository, otherwise a normalized absolute path;
- `schedule_sha256`: lowercase SHA-256 of the exact schedule bytes used by the run;
- `exact_kickoff_linkage_count` and `unresolved_kickoff_count` for a COMPLETE snapshot.

Every processed row repeats the same `schedule_sha256`. The collector does not copy or modify the schedule. If a later schedule revision changes even non-semantic bytes, a later snapshot receives a different hash and therefore cannot silently reinterpret the earlier capture.

An INCOMPLETE manifest retains `schedule_path` and the observed `schedule_sha256` when the schedule was successfully read. Already fetched raw notice bytes remain immutable, and no processed CSV is published.

## Official timing

The parser requires one `NewsArticle` JSON-LD record and a timezone-aware `datePublished`. A timezone-aware `dateModified` is retained when present. Missing or malformed publication time makes the snapshot incomplete; no time is guessed from the title or article date.

## Match linkage

Only explicit `２０２６／２７明治安田Ｊ１リーグ...` target rows are processed. Linkage uses:

1. canonical competition family (`j1`);
2. explicit target date;
3. exact TeamMaster `team_id`;
4. target round as a consistency check.

The round alone is never an identity. A unique schedule fixture with no `match_id` remains `UNRESOLVED_NO_MATCH_ID`; zero/multiple candidates remain unresolved/ambiguous. Opponent may be reported from a unique schedule candidate, but it does not turn a missing match ID into an exact match.

Club names resolve only through `source=jleague_data_site` exact aliases. There is no trim, NFKC, canonical fallback, fuzzy match, or automatic TeamMaster update.

## Kickoff evidence and status

Future processed snapshots add these capture-time fields:

| Field | Meaning |
|---|---|
| `target_kickoff_time` | Exact raw `kickoff_time` string from the unique schedule candidate; no whitespace or display normalization |
| `target_kickoff_at` | Canonical ISO 8601 instant constructed explicitly in `Asia/Tokyo`, or blank when unresolved |
| `schedule_sha256` | SHA-256 of the exact schedule bytes used for this snapshot |
| `kickoff_link_status` | Kickoff-evidence outcome, independent of `match_link_status` |

The only accepted operational clock format is zero-padded 24-hour ASCII `HH:MM`, from `00:00` through `23:59`. For example, `2026-10-09` plus `19:00` becomes `2026-10-09T19:00:00+09:00`. The machine's local timezone is never used.

`kickoff_link_status` has exactly these meanings:

| Status | Meaning |
|---|---|
| `EXACT` | Match linkage is exact, raw clock is valid, and a `+09:00` timestamp was emitted |
| `UNRESOLVED_MISSING` | Match linkage is exact but the raw clock is blank |
| `UNRESOLVED_INVALID` | Match linkage is exact but the raw clock is not exact `HH:MM` |
| `UNRESOLVED_NO_MATCH` | No exact target match was established; no timestamp is emitted |
| `AMBIGUOUS` | Multiple schedule candidates exist; no kickoff value or timestamp is selected |

Exact match linkage does not imply exact kickoff linkage. Missing or malformed clocks remain explicit and never receive midnight, noon, or another guessed time. These fields preserve evidence only; they do not declare a row eligible for modeling. A future registry may compare immutable publication/retrieval and kickoff evidence under a separately frozen rule.

## Player linkage

`player_name_raw` preserves the official notice text, including its internal spacing. The sampled notice does not expose an official player ID. Unless an exact `(season, team_id, player_name_raw)` identity set is explicitly supplied for diagnostics, `player_link_status` is `UNRESOLVED`. The collector does not join player minutes/workload data and does not create a player master.

## Multi-match policy

One processed row is emitted for each target row explicitly present in the official table. Blank-player continuation rows may inherit only from their immediately preceding explicit player row. The suspension code or rules are never used to invent a second match or competition carry-over.

## Duplicate and incomplete policy

Duplicate URL/notice identities and duplicate source/player/club/target rows are rejected. If fetching, decoding, metadata parsing, table parsing, or duplicate validation fails:

- already fetched raw bytes remain in the snapshot directory;
- `manifest.json` remains `INCOMPLETE` and records the error;
- no processed CSV is published.

Identity and match-link statuses are data quality outcomes, not parse failures, and are retained explicitly rather than guessed.

Snapshots created before this schema extension remain immutable in their original schema. They are not migrated or backfilled from the current schedule, because doing so would replace capture-time evidence with later state.

## Future workload integration

A later research cycle may combine eligible pre-kickoff snapshots with previous-match starters, previous squads, or lagged player minutes. Unresolved player identities must remain an explicit coverage limitation. Target-match lineups and post-match data are prohibited.

No workload feature, suspension feature, eligibility flag, historical backfill, model evaluation, or prediction is produced by this collector.

The immutable snapshot archive can be audited without network or filesystem mutation through the read-only registry documented in [JLEAGUE_SUSPENSION_REGISTRY.md](JLEAGUE_SUSPENSION_REGISTRY.md). The registry preserves both `LEGACY_V1` and `KICKOFF_V2` observations and never reconstructs legacy kickoff evidence from the current schedule.

After official match IDs become available through the ongoing schedule revision pipeline, a later immutable capture of the same notice may gain exact match/kickoff provenance. Never rewrite the earlier snapshot: its unresolved linkage state is valid capture-time evidence and remains part of notice version history.
