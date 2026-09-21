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

## Future workload integration

A later research cycle may combine eligible pre-kickoff snapshots with previous-match starters, previous squads, or lagged player minutes. Unresolved player identities must remain an explicit coverage limitation. Target-match lineups and post-match data are prohibited.

No workload feature, historical suspension feature, model evaluation, or prediction was performed by this implementation.
