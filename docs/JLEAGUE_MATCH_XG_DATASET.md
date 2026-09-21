# J.LEAGUE official match-level xG dataset

## Purpose and status

`src/collect/jleague_match_xg.py` collects post-match observed statistics from official J.LEAGUE live-commentary pages. The current production datasets contain 660 complete match observations:

| Competition | Matches | xG | Shots | Shots on target |
|---|---:|---:|---:|---:|
| 2025 ordinary J1 | 380 | 380 | 380 | 380 |
| 2026 J1 100 Year Vision League | 200 | 200 | 200 | 200 |
| 2026/27 ordinary J1, completed through round 8 | 80 | 80 | 80 | 80 |
| **Total** | **660** | **660** | **660** | **660** |

These are source datasets, not feature datasets. No rolling feature, model evaluation, prediction, accuracy, Log Loss, Brier score, threshold, or parameter search was run while extending the collector.

## Official sources and competition separation

The collector uses only J.LEAGUE.jp:

- schedule listings: `https://www.jleague.jp/j1/match/search-list/`
- match commentary: `https://www.jleague.jp/match/j1/<page_year>/<official_match_path_id>/live-commentary/`

Path IDs come only from actual `detailHref` values. They are never generated or guessed. Filtered discovery requires the exact official `leagueDisplayName` and `state="game-over"` under an explicit competition configuration.

The following identities are separate even when they share page year 2026:

- `j1_2025`: 2025 ordinary J1
- `j1_hyakunen_2026`: 2026 J1 100 Year Vision League
- `j1_2026_2027`: 2026/27 ordinary J1

For 2026/27, the configured listing contains 80 completed and 300 future matches. Only the 80 completed `detailHref` values are fetched and materialized.

## Processed outputs

- `data/processed/jleague_match_xg/2025_j1_match_xg.csv`: 380 rows
- `data/processed/jleague_match_xg/2026_hyakunen_j1_match_xg.csv`: 200 rows
- `data/processed/jleague_match_xg/2026_27_j1_match_xg.csv`: 80 rows

The existing 2025 file was not rewritten. A read-only rebuild from its validated raw cache reproduced all 380 rows and all 19 existing columns exactly.

## Source formats

The parser supports two explicit, fail-closed source formats:

### `legacy_full_time_summary`

Used by 2025 and the 2026 100 Year Vision League. One sentence contains both named teams in the ordered segments: shots, shots on target, and expected goals. Both names must match across all three segments and the commentary identity.

### `two_widget_summary`

Used by 2026/27 ordinary J1. Home and away have separate one-sided Full Time sentences. Values are not assigned from page order: each sentence is bound to the explicit RSC `homeTeam:teamLogo` or `awayTeam:teamLogo` marker. Exactly one non-conflicting widget per side is required for a complete row.

The `auto` parser is available for fixture-level detection, but production competition configurations choose a source format explicitly. There is no ambiguous fallback or value guessing. Full-width numeric characters are NFKC-normalized only for numeric parsing; club identity strings are not trimmed or normalized.

## Processed schema

The 2026 files retain the 2025 fields and add explicit competition/source semantics:

| Column | Meaning |
|---|---|
| `competition`, `season` | Explicit dataset identity; 2026 special and 2026/27 ordinary are distinct |
| `match_id`, `match_date` | Existing project match identity and date |
| `home_team_id`, `away_team_id` | Stable TeamMaster IDs |
| `home_team_name`, `away_team_name` | J.LEAGUE.jp official full names |
| `home_score`, `away_score` | Existing project regulation scores |
| `home_xg`, `away_xg` | Numeric official match-level xG |
| `home_shots`, `away_shots` | Official shot totals |
| `home_shots_on_target`, `away_shots_on_target` | Official shots on target |
| `source_match_path_id`, `source_url` | Actual official path identity and commentary URL |
| `source_format` | `legacy_full_time_summary` or `two_widget_summary` |
| `source_home_score`, `source_away_score` | Scores displayed by the commentary page |
| `score_scope_status` | Regulation match or safely identified extra-time source score |
| `xg_time_scope` | `REGULATION` or explicit unresolved official-final scope |
| `retrieved_at` | UTC retrieval time from validated cache metadata |
| `raw_full_time_summary` | Exact source sentence, or deterministic home/away JSON for two widgets |

Rows are sorted by `match_date, match_id`.

## Extra-time score and xG scope

The 100 Year Vision League match `33017` (Machida vs Nagoya, 2026-06-06) is the single score-scope mismatch:

- existing regulation score retained in `home_score, away_score`: 0-0
- official page score retained separately: 2-1 after extra time
- `score_scope_status=EXTRA_TIME_SOURCE_SCORE`
- `xg_time_scope=OFFICIAL_FINAL_SCOPE_UNRESOLVED`

The existing regulation result is not overwritten. The official summary does not state safely whether its xG is limited to 90 minutes or includes extra time, so the value is retained without exclusion or correction and its scope remains explicit. A future feature task must decide policy separately.

All other 659 rows use `score_scope_status=REGULATION_MATCH` and `xg_time_scope=REGULATION`.

## Match identity and validation

Identity is fail-closed:

1. Exact official competition and completed state select actual `detailHref` values.
2. The commentary payload supplies date, full names, short names, and source score.
3. Full names resolve exactly with `source="jleague_official"`.
4. Short names resolve exactly with `source="jleague_data_site"`.
5. Both representations must resolve to the same stable team ID.
6. Date and short home/away names must match one existing reference row.
7. Regulation score/result must remain internally consistent.
8. A source-score difference is accepted only when the reference explicitly identifies extra time and its extra-time score equals the source score.

Unresolved identity, duplicate match/source URL, malformed numeric value, unexplained score mismatch, partial/missing coverage, or row-count mismatch prevents processed output from being written. Fuzzy matching and TeamMaster mutation are prohibited.

## Missing semantics

- `COMPLETE`: both sides have numeric xG, shots, and shots on target.
- `PARTIAL`: exactly one side has numeric xG.
- `MISSING`: neither side has numeric xG.

The page-wide `expected_goals` key or a translated `ゴール期待値` label is not evidence of data. Only numeric Full Time content counts.

## Raw cache and manifests

Competition-specific raw roots prevent collisions:

- `data/raw/jleague_match_xg/2025/`
- `data/raw/jleague_match_xg/2026_hyakunen/`
- `data/raw/jleague_match_xg/2026_27/`

Each HTML has a metadata sidecar containing requested/final URL, status, retrieval time, byte count, and SHA-256. Cache reuse requires all validation checks to pass.

Each competition manifest records competition, season, expected/completed/scheduled counts, future exclusions, downloads, cache hits, complete/partial/missing counts, identity mismatches, score-scope mismatches, source-format counts, request count, processed rows, source URLs, and completion status.

Initial 2026 materialization downloaded 201 entries for the 100 Year Vision League and 81 for 2026/27 ordinary J1, with zero cache hits because both namespaces were new.

## Chronology and leakage policy

xG, shots, and shots on target are post-match observations. A future rolling feature may use only matches completed before its target kickoff. The target match's own values and future matches are prohibited. Same-date matches must not become mutual history when safe kickoff ordering is unavailable.

No rolling window, aggregation, missing-value strategy, extra-time adjustment, or model feature is defined here.

## Commands

```text
python -m src.collect.jleague_match_xg --competition 2026_hyakunen
python -m src.collect.jleague_match_xg --competition 2026_27_j1
```

The legacy default invocation remains 2025-compatible.
