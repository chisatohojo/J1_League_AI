# 2026 J.LEAGUE official match-level xG coverage audit

## Scope and decision

This audit was performed on 2026-09-21 using only official J.LEAGUE.jp sources. It covers two distinct competitions and does not combine them:

- 2026 J1 100 Year Vision League: 200 completed matches
- 2026/27 ordinary J1: 80 completed matches out of a 380-match schedule; the 300 future matches were excluded

Both competitions are classified **A**: the currently completed matches have complete two-sided match-level xG, shots, and shots-on-target data and can be materialized as production source datasets after the parser is made competition/format aware.

This was a coverage and identity audit only. No rolling feature, model evaluation, prediction, accuracy, Log Loss, Brier score, feature selection, or parameter tuning was run. In particular, the already opened 80 ordinary-J1 results were not used to change a feature or model specification.

## Official discovery and route structure

The official schedule listings were queried in bounded, non-overlapping windows:

- 100 Year Vision League: `https://www.jleague.jp/j1/match/search-list/?category=j1&startdate=2026-01-01&enddate=2026-06-30&period=custom`
- ordinary J1: `https://www.jleague.jp/j1/match/search-list/?category=j1&startdate=2026-07-01&enddate=2026-09-21&period=custom`

Only actual `detailHref` values found in these listings were accepted. No path ID was generated from a date or guessed. The observed match routes were:

- detail: `/match/j1/2026/<official_match_path_id>`
- Full Time source: `/match/j1/2026/<official_match_path_id>/live-commentary/`

Every audited commentary page had the expected canonical URL. The official listing returned 200 unique `game-over` links for the 100 Year Vision League and 80 unique `game-over` links for ordinary J1.

## Competition identity and project linkage

| Check | 100 Year Vision League | 2026/27 ordinary J1 |
|---|---:|---:|
| Official competition name | `明治安田Ｊ１百年構想リーグ` | `明治安田Ｊ１リーグ` |
| Official completed links | 200 | 80 |
| Existing reference rows | 200 | 80 |
| Exact date/home/away links | 200 | 80 |
| Identity mismatches | 0 | 0 |
| Unresolved TeamMaster side occurrences | 0 | 0 |

The 100 Year Vision League listing contains the EAST/WEST regional rounds and the two-leg playoff placement rounds. The ordinary listing contains rounds 1 through 8. These official labels, names, dates, and home/away identities distinguish the competitions even though both use the `/match/j1/2026/` route family.

For every match, official full names resolved exactly through `source="jleague_official"`, short names resolved exactly through `source="jleague_data_site"`, and both representations agreed on the stable team ID. No trimming, Unicode normalization of identity strings, canonical fallback, or fuzzy matching was used.

One 100 Year Vision League page (`060606`, Machida vs Nagoya, 2026-06-06) displays the post-extra-time score 2-1, while the existing project row correctly stores the regulation score 0-0 and separate extra-time scores 2-1. Date, home, away, route identity, and both TeamMaster identities match exactly. This is a score-scope difference, not a match-linkage failure. A production collector must preserve the existing regulation/extra-time distinction rather than require page display score equality for this competition.

## Coverage

`COMPLETE` means both home and away numeric values were present. `PARTIAL` means exactly one side was present. A UI or translation label without numeric values was not counted.

### 2026 J1 100 Year Vision League

| Field | Complete | Partial | Missing | Coverage |
|---|---:|---:|---:|---:|
| xG | 200 | 0 | 0 | 100.00% |
| Shots | 200 | 0 | 0 | 100.00% |
| Shots on target | 200 | 0 | 0 | 100.00% |

All 200 official matches were completed and audited.

### 2026/27 ordinary J1

| Field | Complete | Partial | Missing | Coverage of completed matches |
|---|---:|---:|---:|---:|
| xG | 80 | 0 | 0 | 100.00% |
| Shots | 80 | 0 | 0 | 100.00% |
| Shots on target | 80 | 0 | 0 | 100.00% |

The local schedule invariant was 380 rows: 80 completed and 300 future. Only the 80 completed matches were opened. No result or xG was requested or generated for the future 300.

## Opening/middle/late samples

The full scan was started only after opening, middle, and late samples from each competition all exposed numeric values.

| Competition | Path ID | Date | Match | xG | Shots | SOT |
|---|---|---|---|---:|---:|---:|
| 100 Year Vision | `020601` | 2026-02-06 | 横浜FM vs 町田 | 1.96-0.53 | 15-8 | 4-4 |
| 100 Year Vision | `041201` | 2026-04-12 | 浦和 vs 東京Ｖ | 1.44-1.17 | 17-7 | 4-1 |
| 100 Year Vision | `060611` | 2026-06-06 | 川崎Ｆ vs 広島 | 0.60-1.49 | 11-20 | 5-7 |
| ordinary J1 | `080701` | 2026-08-07 | 横浜FM vs 鹿島 | 2.97-1.46 | 19-10 | 5-4 |
| ordinary J1 | `090216` | 2026-09-02 | 水戸 vs 鹿島 | 1.06-1.41 | 14-7 | 5-5 |
| ordinary J1 | `092002` | 2026-09-20 | Ｇ大阪 vs 神戸 | 1.47-2.13 | 14-16 | 3-5 |

The values above are source sanity checks, not model inputs or performance results.

## Source-format compatibility with the 2025 collector

The existing `src/collect/jleague_match_xg.py` components have different compatibility levels.

| Component | Compatibility | Finding |
|---|---|---|
| Actual `detailHref` discovery | Partial | The extraction principle is reusable, but 2026 must filter by official competition name and `game-over` state. A generic calendar-year scan would mix the two competitions and future ordinary fixtures. |
| Commentary route/canonical check | Reusable | Both competitions use the observed 2026 live-commentary route and canonical URL. |
| Match identity payload | Reusable | Date, full/short names, and page score remain available. |
| TeamMaster exact validation | Reusable | All 560 audited side occurrences resolve without aliases or fuzzy logic. |
| Full Time parser: 100 Year Vision | Reusable | All 200 pages use the 2025-style single sentence containing both named teams. |
| Full Time parser: ordinary J1 | Change required | Each page contains two one-sided Full Time widget sentences, one for home and one for away. The current parser rejects these as multiple conflicting summaries. |
| Strict score equality | Change required for 100 Year Vision | At least one extra-time page displays the post-extra-time score while the reference row stores regulation and extra-time scores separately. |
| Cache/manifest design | Reusable with namespacing | URL/SHA-256 validation is suitable, but caches and manifests must be separated by competition and reference dataset. |

The numeric source uses full-width characters such as `１．９６`. The existing NFKC numeric conversion is sufficient and should be retained. Identity strings must remain exact and must not be normalized.

## Required collector changes

Before production materialization:

1. Add explicit competition configurations for `j1_hyakunen_2026` and `j1_2026_2027`; do not infer a competition from the year alone.
2. Parse only actual listing records whose official competition name and completion state match the requested dataset.
3. Retain the current combined two-team summary parser for the 100 Year Vision League.
4. Add a fail-closed parser for the ordinary-J1 two-widget format. It must bind each numeric sentence to its home/away widget in the DOM/RSC structure; a page-wide unordered pair is not sufficient for production.
5. Keep `COMPLETE`, `PARTIAL`, and `MISSING` explicit for each field. Translation keys or labels without values remain `MISSING`.
6. Join to the appropriate existing dataset using exact date/home/away and exact TeamMaster identities.
7. For the 100 Year Vision League, preserve regulation, extra-time, and penalty semantics from the reference data. Also retain an extra-time indicator because the scope of a page-level xG total is not separately documented in the summary text.
8. Use separate raw-cache and processed-output namespaces plus a manifest recording expected, complete, partial, missing, identity, and competition counts.

No production code was changed in this audit.

## Missing semantics

- `COMPLETE`: two numeric side values are present and structurally attributable to the match sides.
- `PARTIAL`: exactly one numeric side value is present.
- `MISSING`: neither side has a numeric value.

The page-wide `expected_goals` key, `ゴール期待値` label, or translation content alone is not evidence of match-level xG.

## Chronology and opened-80 discipline

xG, shots, and shots on target are observed post-match data. Any future rolling feature must use only matches completed before the target kickoff. A target match's own statistics and future statistics are prohibited.

The 80 ordinary-J1 matches were already opened result data before this audit. This audit only checked source coverage and linkage. It did not evaluate predictive performance or select a feature. The 80-match findings must not be used to retune the frozen models or choose xG feature parameters.

## Request accounting

The final systematic pass used 282 successful official GET requests: two schedule listings and 280 unique commentary pages. Its six sample pages were retained in memory and were not fetched again during the full scan.

Across the complete investigation, 315 official GET requests were made. The additional 33 were bounded structure/parser diagnostics while identifying the 2026 two-widget format and verifying the one extra-time score-scope discrepancy. No future ordinary match detail page was fetched, no non-official host was used, and no raw production cache was written.

## Recommended next implementation

Implement a small competition-aware extension of the existing collector, with fixture tests for both the combined two-team and split home/away widget formats. Materialize the two competitions into separate source datasets and manifests. Do not build a rolling feature or run a model in that task. After materialization, independently audit whether extra-time match summaries represent 90 or 120 minutes before treating 100 Year Vision xG as directly comparable with ordinary 90-minute J1 xG.

Final classifications:

- 2026 J1 100 Year Vision League: **A**, with an explicit extra-time scope flag/limitation.
- 2026/27 ordinary J1 completed matches: **A**, after adding the observed two-widget parser.
