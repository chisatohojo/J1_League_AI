# J.LEAGUE official match-level xG dataset

## Purpose and status

`src/collect/jleague_match_xg.py` collects post-match observed statistics from official J.LEAGUE live-commentary pages. The first production dataset covers all 380 ordinary J1 matches in 2025.

This is a source dataset, not a feature dataset. No rolling feature, model evaluation, prediction, threshold, or parameter search was run while creating it.

## Official sources

The collector uses only J.LEAGUE.jp:

- schedule listings: `https://www.jleague.jp/j1/match/search-list/`
- match commentary: `https://www.jleague.jp/match/j1/2025/<official_match_path_id>/live-commentary/`

The official match path IDs come from actual `detailHref` values in two bounded schedule queries. They are not generated from dates or guessed. The 2025 listing produced 380 unique official paths.

## Coverage

| Item | Count |
|---|---:|
| Existing ordinary J1 reference matches | 380 |
| Official commentary pages | 380 |
| Complete two-sided xG summaries | 380 |
| Partial xG summaries | 0 |
| Missing xG summaries | 0 |
| Identity mismatches | 0 |
| Processed rows | 380 |
| Unique Data Site `match_id` values | 380 |
| Shots available | 380 |
| Shots on target available | 380 |

## Processed schema

Output: `data/processed/jleague_match_xg/2025_j1_match_xg.csv`

| Column | Meaning |
|---|---|
| `season` | J1 season, currently 2025 |
| `match_id` | Existing J.League Data Site match ID used by the project |
| `match_date` | Official match date |
| `home_team_id`, `away_team_id` | Stable TeamMaster IDs |
| `home_team_name`, `away_team_name` | J.LEAGUE.jp official full club names |
| `home_score`, `away_score` | Scores verified against the existing 2025 J1 dataset |
| `home_xg`, `away_xg` | Numeric Full Time xG values |
| `home_shots`, `away_shots` | Full Time shot totals |
| `home_shots_on_target`, `away_shots_on_target` | Full Time shots on target |
| `source_match_path_id` | Six-digit official J.LEAGUE.jp path identity from `detailHref` |
| `source_url` | Official live-commentary URL |
| `retrieved_at` | UTC time recorded when that raw page was fetched |
| `raw_full_time_summary` | Original official Japanese Full Time sentence |

One match is one row. Rows are sorted by `match_date, match_id`.

## Parsing rule

The parser accepts only the numeric sentence beginning with `この試合のシュート：` and containing the three ordered segments:

1. shots
2. shots on target
3. expected goals

Both clubs must appear in the same order in all three segments. Full-width numeric characters are converted only for numeric parsing. Club names are not trimmed, normalized, or fuzzily matched.

The page-wide `expected_goals` key or the UI/translation label `ゴール期待値` is not evidence that a match has xG. A page without the numeric Full Time sentence is `MISSING`; a sentence with only one numeric xG side is `PARTIAL`. Negative or malformed values are rejected.

## Match identity

Identity is fail-closed and uses independent official representations:

1. Actual J.LEAGUE.jp `detailHref` determines the commentary URL.
2. The commentary payload supplies date, official full names, short names, and score.
3. Full names resolve exactly with `source="jleague_official"`.
4. Short names resolve exactly with `source="jleague_data_site"`.
5. Both representations must resolve to the same stable team ID.
6. Date, short home/away names, score, and deterministic result must match the existing 2025 J1 row.

Any unresolved identity, duplicate, conflicting source URL, score mismatch, or incomplete coverage prevents the processed CSV from being written. No fuzzy matching or TeamMaster mutation occurs.

## Raw cache and manifest

Raw root: `data/raw/jleague_match_xg/2025/`

- `schedule_1.html`, `schedule_2.html`: official bounded schedule listings
- `<source_match_path_id>.html`: 380 commentary pages
- one `.metadata.json` sidecar per HTML: requested/final URL, status, retrieval time, byte count, SHA-256
- `manifest.json`: expected matches, downloads/cache hits for the completing run, parse status counts, identity mismatch count, all source URLs, and completion flag

A cache entry is reused only when URL, status, byte count, and SHA-256 all validate. An invalid entry is fetched again. The first attempt stopped safely after one read timeout; the completing invocation reused 334 entries and downloaded the remaining 48. Across materialization there were 382 successful source downloads and one failed HTTP attempt.

## Missing and incomplete snapshot policy

Raw pages may be retained when a run is incomplete. The processed dataset is written only if all expected reference matches have complete two-sided xG and pass identity/invariant checks. The manifest records `complete=false` before raising on incomplete coverage.

For another season, including 2024, a partial result must not be called a complete dataset. The historical audit found only 96/380 complete 2024 summaries and 284 missing values. This task generated only the 2025 production dataset.

## Chronology and leakage policy

xG, shots, and shots on target are post-match observations. A target match's own values must never be used to predict that match. Any future feature must sort matches chronologically and aggregate only matches completed before the target kickoff.

Season-final totals are not generated here. Current-match values are not joined to model targets, and no feature calculation is part of this collector.

## Possible future feature groups

These are candidates only; no window or parameter is selected here:

- rolling xG for
- rolling xG against
- rolling xG difference
- goals minus xG
- goals conceded minus xGA

Any future experiment requires a separately declared history-only feature contract and validation protocol.
