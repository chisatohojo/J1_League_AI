# J1 historical match event dataset

Status: **MATERIALIZED_AND_VALIDATED**.

## Source and scope

- Competition: ordinary J1 only
- Seasons: 2015-2024
- Source matches: 3,208
- Source: existing J.League Data Site SFMS02 cache and metadata
- External HTTP requests: 0
- Excluded: 2025, 2026/27, Hyakunen, Cups, J2, J3, and AFC

The production artifact is
`data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`.
Its SHA-256 is
`6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131`.
The adjacent `2015_2024_j1_match_events.validation.json` records the
machine-readable validation summary. Generated files are gitignored.

## Schema and normalization

The schema and event meaning remain frozen by
`docs/J1_MATCH_EVENT_DATASET_SPEC.md`. The artifact columns are:

`event_id`, `match_id`, `match_date`, `season`, `team_id`, `team_name`,
`side`, `event_type`, `player_name_raw`, `related_player_name_raw`,
`minute_raw`, `minute_normalized`, `minute_order_half`,
`minute_order_base`, `minute_order_added`, `normalization_flags`,
`source_section`, `source_row_index`, `null_reason`, `source`, `source_url`,
and `raw_sha256`.

The four source families are A2 `GOAL`, A7 `SUBSTITUTION`, A8
`YELLOW_CARD`, and A9 `RED_CARD`. Each A7 OUT/IN pair becomes one event. A2
is asymmetric in the official DOM: home rows are player/minute and away rows
are minute/player. The parser handles that source structure without changing
the raw player text.

Eighteen A8 rows contain the official raw minute token `***`. They retain
`minute_raw=***`, have null normalized minute fields, and carry
`null_reason=SOURCE_MINUTE_UNRESOLVED`. No minute is guessed or coerced.

## Provenance and identity

Every cached HTML file and metadata record passed URL, status, match ID,
byte-length, and SHA-256 validation. Probe names resolve exactly through the
`jleague_data_site` namespace; SFMS02 match-stat names resolve exactly through
`jleague_official`; both must resolve to the same stable `team_id`.

Player identity is match-local `player_name_raw` only. SFMS02 does not expose
a verified stable player ID for these rows. The dataset therefore supports
match-local event analysis, but not name-derived or longitudinal player
identity. Fuzzy matching, manual merging, and generated player IDs are not
used.

## Coverage

| Event type | Rows | Matches with event | Matches with zero events |
|---|---:|---:|---:|
| GOAL | 8,377 | 2,958 | 250 |
| SUBSTITUTION | 23,638 | 3,208 | 0 |
| YELLOW_CARD | 7,671 | 2,838 | 370 |
| RED_CARD | 301 | 286 | 2,922 |
| **Total** | **39,987** | **3,208 with any event** | **0 with no event** |

Raw source event rows are A2 8,377, A7 47,276, A8 7,671, and A9 301.
A7 therefore satisfies the required 2:1 raw-to-normalized ratio exactly.

The earlier broad A2 audit count of 11,335 included one outer layout `<tr>`
for each of the 2,958 matches where A2 is present. Excluding those layout rows
leaves 8,377 actual scoring rows, each mapped to one normalized GOAL event.

| Season | Matches | GOAL | SUBSTITUTION | YELLOW_CARD | RED_CARD | Total events |
|---|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 820 | 1,688 | 783 | 27 | 3,318 |
| 2016 | 306 | 805 | 1,745 | 840 | 23 | 3,413 |
| 2017 | 306 | 793 | 1,747 | 763 | 24 | 3,327 |
| 2018 | 306 | 813 | 1,760 | 738 | 23 | 3,334 |
| 2019 | 306 | 797 | 1,774 | 670 | 22 | 3,263 |
| 2020 | 306 | 866 | 2,649 | 664 | 20 | 4,199 |
| 2021 | 380 | 922 | 3,381 | 685 | 30 | 5,018 |
| 2022 | 306 | 771 | 2,730 | 692 | 44 | 4,237 |
| 2023 | 306 | 777 | 2,734 | 861 | 40 | 4,412 |
| 2024 | 380 | 1,013 | 3,430 | 975 | 48 | 5,466 |

## Score diagnostic

A2 event-side counts match the official result for 3,207 matches. There are
zero unexplained mismatches. Match `25153` is `NOT_CHECKABLE`: official A1
stores the adjudicated 0-3 score while A2 retains the five on-field scoring
rows. Those event rows are preserved without rewriting either the event
history or official score.

## Determinism and validation

`event_id` is a deterministic SHA-256 of match ID, side, source section,
source row index, and event type. All 39,987 IDs are non-null and globally
unique. Output ordering is deterministic by match date, string match ID,
normalized event order, section, source row, and event ID. Existing outputs
are never silently overwritten; publication occurs only after all source and
dataset invariants pass.

Validation outcome:

- source missing: 0
- malformed/unresolved source structures: 0
- TeamMaster unresolved: 0
- metadata/SHA failures: 0
- event ID collisions: 0
- score mismatches: 0
- score not-checkable: 1
- targeted tests: 22 passed

No model fitting, prediction, metric evaluation, feature generation, or
feature selection was performed.
