# Team substitution usage/timing profile feasibility

Status: **READ_ONLY_FEASIBILITY_AUDIT_COMPLETE**.

Final verdict: **PROCEED_TO_SUBSTITUTION_FEATURE_SPEC**.

## Purpose and boundary

This document audits whether the existing normalized ordinary-J1
`SUBSTITUTION` events can support a leakage-safe team-level current-season
prior profile. It is a source-feasibility audit, not a feature specification
or predictive evaluation.

Only `SUBSTITUTION` rows were used for the descriptive analysis. GOAL,
YELLOW_CARD, RED_CARD, score state, match result, player performance, player
quality, starter strength, and lineup continuity were not analyzed or joined.
No cross-season or cross-team player-name linking was attempted.

No feature dataset, collector, builder, test, generated CSV, model,
prediction, or predictive metric was created.

## Source and reconciliation

Sources of truth:

- `docs/J1_MATCH_EVENT_DATASET_SPEC.md`
- `docs/J1_MATCH_EVENT_DATASET.md`
- `src/collect/sfms02_match_events.py`
- `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`
- its adjacent materialization validation JSON

Scope is exactly 3,208 ordinary-J1 matches from 2015 through 2024. The event
artifact SHA-256 was recomputed and matched:

```text
6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131
```

| Reconciliation item | Observed |
|---|---:|
| Total normalized event rows | 39,987 |
| Normalized `SUBSTITUTION` rows | 23,638 |
| Matches with at least one `SUBSTITUTION` | 3,208 |
| Raw A7 rows | 47,276 |
| Raw A7 : normalized SUB ratio | 2:1 |

Raw A7 count is recorded by the reviewed materialization summary. The
collector derives it as two raw rows for each normalized substitution and
hard-fails unless `raw A7 == 2 * normalized SUB`. The parser requires an
adjacent `▽` OUT row followed by an `▲` IN row, a present OUT minute, an empty
IN minute, two distinct nonblank names, and no unpaired row. One such pair
becomes one normalized event: outgoing player in `player_name_raw`, incoming
player in `related_player_name_raw`.

## Normalized SUB schema and integrity

The usable identity and timing fields are `event_id`, `match_id`,
`match_date`, `season`, `team_id`, `side`, `minute_raw`,
`minute_normalized`, `minute_order_half`, `minute_order_base`, and
`minute_order_added`. Provenance includes `source_section`,
`source_row_index`, `source`, `source_url`, and `raw_sha256`.

Read-only artifact validation found:

- all 39,987 global `event_id` values and all 23,638 SUB IDs are unique;
- SUB seasons are exactly 2015–2024;
- SUB match IDs equal the complete 3,208-match target ID set;
- `side` values are exactly `home` and `away`;
- every SUB row has `source_section=A7`;
- target match/date/team-side identity mismatches: 0;
- null `minute_raw`, normalized minute, or any complete-key component: 0;
- unresolved SUB minutes: 0;
- unsupported SUB minute tokens: 0; and
- non-null outgoing and incoming raw names: 23,638 each.

The 18 unresolved `***` minutes documented for the full event dataset are A8
card rows, not substitutions.

### Minute variants

Arithmetic timing uses `minute_normalized` exactly as stored. First/last
ordering uses the complete lexicographic key
`(minute_order_half, minute_order_base, minute_order_added)`; sorting only by
`minute_normalized` is unsafe.

| Variant | SUB rows | Stored semantics |
|---|---:|---|
| exact `45'` | 12 | normalized 45 |
| `45'+1` through `45'+6` | 35 | normalized/capped 45; added component retained for ordering |
| exact `46'` | 1,717 | normalized 46; `MINUTE_46_BOUNDARY_AMBIGUOUS` |
| exact `90'` | 346 | normalized 90 |
| `90'+1` through `90'+11` | 1,137 | normalized/capped 90; added component retained for ordering |

Observed normalized SUB minutes range from 3 through 90. No elapsed-minute
conversion or restoration of added time is source-authorized.

## Match and team-side coverage

“Every match has a substitution” does not imply that both teams substituted.

| Season | Target matches | Matches with SUB | Home side with SUB | Away side with SUB | Both sides with SUB | Neither side | SUB events |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 306 | 305 | 306 | 305 | 0 | 1,688 |
| 2016 | 306 | 306 | 305 | 306 | 305 | 0 | 1,745 |
| 2017 | 306 | 306 | 305 | 306 | 305 | 0 | 1,747 |
| 2018 | 306 | 306 | 306 | 305 | 305 | 0 | 1,760 |
| 2019 | 306 | 306 | 305 | 306 | 305 | 0 | 1,774 |
| 2020 | 306 | 306 | 306 | 306 | 306 | 0 | 2,649 |
| 2021 | 380 | 380 | 380 | 380 | 380 | 0 | 3,381 |
| 2022 | 306 | 306 | 306 | 306 | 306 | 0 | 2,730 |
| 2023 | 306 | 306 | 306 | 306 | 306 | 0 | 2,734 |
| 2024 | 380 | 380 | 380 | 379 | 379 | 0 | 3,430 |

There are exactly 6,416 team-match sides: 6,410 with at least one SUB and 6
with zero SUB events.

## Team-side substitution count distribution

Each normalized OUT/IN pair counts as one substitution used. Distribution is
over all team-match sides, including zero-event sides.

| Season | Mean | Median | Min | Max | 0 | 1 | 2 | 3 | 4 | 5 | >=6 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 2.758 | 3 | 0 | 3 | 1 | 18 | 109 | 484 | 0 | 0 | 0 |
| 2016 | 2.851 | 3 | 0 | 3 | 1 | 11 | 66 | 534 | 0 | 0 | 0 |
| 2017 | 2.855 | 3 | 0 | 3 | 1 | 13 | 60 | 538 | 0 | 0 | 0 |
| 2018 | 2.876 | 3 | 0 | 3 | 1 | 4 | 65 | 542 | 0 | 0 | 0 |
| 2019 | 2.899 | 3 | 0 | 3 | 1 | 10 | 39 | 562 | 0 | 0 | 0 |
| 2020 | 4.328 | 5 | 1 | 5 | 0 | 3 | 24 | 78 | 171 | 336 | 0 |
| 2021 | 4.449 | 5 | 2 | 6 | 0 | 0 | 17 | 68 | 237 | 433 | 5 |
| 2022 | 4.461 | 5 | 1 | 6 | 0 | 2 | 14 | 64 | 158 | 368 | 6 |
| 2023 | 4.467 | 5 | 1 | 6 | 0 | 1 | 19 | 57 | 157 | 372 | 6 |
| 2024 | 4.513 | 5 | 0 | 7 | 1 | 0 | 10 | 81 | 195 | 452 | 21 |

### Regime-shift audit

A clear artifact-level break is present. In 2015–2019, every side has at most
three substitutions, median is three, and season means are 2.758–2.899. In
2020 the median becomes five, maximum becomes five, and mean becomes 4.328;
2021–2024 remain centered on five with occasional six or seven.

The artifact alone establishes the distribution change, not its official
rule, rationale, effective date, exception policy, or competition-law
interpretation. Those cannot be asserted from the permitted repo sources.
Raw substitution count is therefore materially regime-sensitive. A
current-season reset keeps each target's history within its season, but a
rolling-OOF model would still learn across sharply different season-level
feature distributions. No rule adjustment, quota normalization, or percentage
feature is designed here.

## Timing distribution

Timing is calculated only for the 6,410 positive-SUB team-match sides. Within
each side, first and last use the complete key; the mean is the arithmetic
mean of the stored `minute_normalized` values. No result label is used.

| Season | N | First mean | First median | First min/max | Mean-SUB mean | Mean-SUB median | Last mean | Last median | Last min/max |
|---:|---:|---:|---:|:---:|---:|---:|---:|---:|:---:|
| 2015 | 611 | 60.427 | 62 | 8 / 90 | 71.235 | 72.333 | 81.748 | 84 | 51 / 90 |
| 2016 | 611 | 60.069 | 62 | 10 / 90 | 71.505 | 72.333 | 82.236 | 84 | 58 / 90 |
| 2017 | 611 | 61.507 | 64 | 6 / 90 | 72.869 | 74.000 | 83.337 | 84 | 46 / 90 |
| 2018 | 611 | 60.684 | 63 | 6 / 89 | 71.991 | 73.000 | 82.496 | 84 | 6 / 90 |
| 2019 | 611 | 60.750 | 63 | 7 / 90 | 72.242 | 72.667 | 82.728 | 84 | 46 / 90 |
| 2020 | 612 | 56.069 | 58 | 3 / 86 | 70.006 | 70.367 | 82.969 | 84 | 58 / 90 |
| 2021 | 760 | 56.439 | 60 | 3 / 89 | 70.734 | 71.250 | 83.517 | 84.5 | 46 / 90 |
| 2022 | 612 | 55.951 | 59 | 6 / 83 | 69.912 | 70.250 | 82.871 | 83 | 46 / 90 |
| 2023 | 612 | 57.199 | 60 | 6 / 88 | 71.195 | 71.667 | 83.582 | 84 | 46 / 90 |
| 2024 | 759 | 56.209 | 59 | 3 / 85 | 71.252 | 71.400 | 83.921 | 85 | 57 / 90 |

Global summaries are:

| Statistic | N | Mean | Median | Min | Max |
|---|---:|---:|---:|---:|---:|
| First substitution | 6,410 | 58.427 | 61 | 3 | 90 |
| Team-match mean substitution minute | 6,410 | 71.280 | 72 | 6 | 90 |
| Last substitution | 6,410 | 82.977 | 84 | 6 | 90 |

First-substitution timing shifts earlier by roughly four to five normalized
minutes from 2020 onward, consistent descriptively with more events per side.
Mean timing stays in a narrower season range (69.912–72.869), and last timing
in 81.748–83.921. Thus timing is less regime-sensitive than raw count, but it
is not regime-free. This is a source-distribution observation, not a claim of
predictive superiority.

## Same-time multiple substitutions

Exact duplicate complete keys were audited within team-match side:

| Item | Count |
|---|---:|
| Matches with a same-side duplicate key | 1,966 |
| Team-match sides with a duplicate key | 3,325 |
| Duplicate-key groups | 4,543 |
| Groups of size 2 | 3,949 |
| Groups of size 3 | 567 |
| Groups of size 4 | 27 |
| Maximum group size | 4 |
| Groups disagreeing on normalized minute | 0 |

Every OUT/IN pair remains an individual substitution event, including when
multiple pairs share one key. Exact-key co-occurrence is observable and may be
described as such. Minute precision does not prove that the events consumed
one official substitution opportunity/window. No window identifier exists,
so substitution-window reconstruction is **UNSAFE / NOT SUPPORTED**.

The sharp rise in duplicate groups after 2019 is also count/regime-sensitive:
annual groups increase from 55–90 in 2015–2019 to 727–975 in 2020–2024.

## Halftime and intent limitations

The schema has no halftime marker. Exact 45, `45'+N`, and ambiguous 46-minute
events cannot be reclassified as halftime substitutions. A “halftime
substitution rate” is therefore **not source-safe**.

The schema also has no reason code for tactical, injury, concussion, forced,
goalkeeper injury, or disciplinary response. Player names and timing do not
identify intent. Individual reason classification is prohibited, and
“tactical substitution” cannot be treated as an observed causal label.

Recommended safe naming is **team substitution usage profile** for count
descriptions and **team substitution timing profile** for the proposed
family. “Tactical profile” should not be used without qualification.

## Player identity dependency

The source preserves match-local outgoing and incoming raw names but provides
no verified stable player ID. Team-level count and timing aggregates require
only resolved `team_id`, match identity, side, and minute fields; they do not
require longitudinal player identity. Player names should be ignored for the
proposed family. Player-specific tendencies remain unsupported because name
normalization, fuzzy matching, and cross-season/cross-team stitching are
prohibited.

## Leakage-safe chronology feasibility

A future builder can be source-safe under this exact chronology:

1. maintain state independently by team and season;
2. reset all state at each season boundary;
3. emit target features only from current-season matches strictly before the
   target date;
4. emit every target on a date before applying any event from that date;
5. update each team with its own normalized SUB events only after the date's
   targets are complete; and
6. never use the target match's events.

This conservative batching avoids target and same-date leakage without
kickoff-order assumptions.

## Current-season prior availability

Read-only simulation used season reset and same-date conservative batching.
“Usage” becomes available after one prior team match, including a zero-SUB
match. “Timing” becomes available after at least one prior SUB event. On this
artifact their observed availability counts coincide: every team's first
target is unavailable, and all later targets have positive prior SUB history.

| Season | Team sides | Usage sides available | Usage pairs available | Timing sides available | Timing pairs available |
|---:|---:|---:|---:|---:|---:|
| 2015 | 612 | 594 | 297 | 594 | 297 |
| 2016 | 612 | 594 | 297 | 594 | 297 |
| 2017 | 612 | 594 | 297 | 594 | 297 |
| 2018 | 612 | 594 | 297 | 594 | 297 |
| 2019 | 612 | 594 | 297 | 594 | 297 |
| 2020 | 612 | 594 | 297 | 594 | 297 |
| 2021 | 760 | 740 | 370 | 740 | 370 |
| 2022 | 612 | 594 | 297 | 594 | 297 |
| 2023 | 612 | 594 | 297 | 594 | 297 |
| 2024 | 760 | 740 | 370 | 740 | 370 |
| **Total** | **6,416** | **6,232** | **3,116** | **6,232** | **3,116** |

This is an availability estimate only. It does not authorize imputation or a
minimum-history threshold.

## Candidate-family audit

Ratings are based only on source semantics, cross-season comparability,
regime sensitivity, and identity requirements.

| # | Candidate | Rating | Reason |
|---:|---|:---:|---|
| 1 | Prior mean substitutions used per match | B | Precisely observable without player identity, but the 2019/2020 count break is material. |
| 2 | Prior mean first substitution minute | B | Source-safe with complete-key ordering, but an extreme statistic that shifts earlier when more substitutions are used. |
| 3 | Prior mean substitution `minute_normalized` | A | Fully resolved, directly aggregable, and descriptively more stable across seasons than count. |
| 4 | Prior mean last substitution minute | A | Source-safe and season distributions are relatively stable, although it remains an event-count-dependent extreme. |
| 5 | Prior fraction of matches with zero substitutions | B | Source-safe, but only 6/6,416 sides are zero and the value is nearly degenerate and regime-sensitive. |
| 6 | Prior same-time multi-substitution frequency | B | Exact-key co-occurrence is observable, but strongly regime/count-sensitive and must not be called a window. |
| 7 | Prior substitution-window count | C | No window identity; equal minute keys do not establish one official opportunity. |
| 8 | Prior halftime substitution rate | C | No halftime marker; 45/added-time/46 values cannot safely infer halftime. |
| 9 | Player-specific substitution tendency | C | Requires prohibited longitudinal player identity and name linkage. |

`A` means source-safe and reasonably stable, `B` source-safe but materially
limited or regime-sensitive, and `C` unsafe or unsupported. Ratings do not
express predictive value.

## Recommended coherent family for the next specification

Proceed with one minimal **team substitution timing profile** consisting only
of the home and away current-season prior mean substitution
`minute_normalized` values. Do not include count, first, last, same-time,
window, halftime, intent, or player-specific values in that initial family.

For each team, the next specification should freeze:

- numerator: sum of `minute_normalized` over all of that team's prior
  current-season normalized SUB events;
- denominator: number of those prior SUB events;
- value: numerator divided by denominator, so weighting is per SUB event;
- missing semantics: null and unavailable when the denominator is zero; no
  imputation;
- same-time semantics: every normalized OUT/IN pair remains a separate event
  and contributes separately;
- season reset: no prior-season carry-over; and
- chronology: strict prior-date history with same-date conservative batching.

The denominator and availability flag would be audit fields, not automatic
model inputs. Exact column names, schema, validation references, and fixture
tests remain work for the future feature specification; they are not frozen
here.

## Limitations

- The official cause of the count-regime break is not established by the
  permitted repository evidence.
- Normalized 45/90 values are capped source semantics, not elapsed time.
- `46'` is boundary-ambiguous.
- Same-minute events do not identify an official substitution window.
- Halftime and substitution reason/intent are not observable.
- No stable longitudinal player identity exists.
- Timing remains indirectly affected by the number of substitutions used.
- Availability is high in this artifact but does not prove future coverage.
- No target-label relationship or predictive performance was inspected.

## Final verdict

**PROCEED_TO_SUBSTITUTION_FEATURE_SPEC**

The normalized SUB source has complete timing, exact match/team-side identity,
complete ordinary-J1 coverage, valid raw-pair reconciliation, and supports
team aggregation without player identity. The count regime shift, absent
reason codes, absent halftime marker, and absent window identity rule out a
broad “tactical” family. They do not block a prespecified, minimal team
substitution timing family based on prior mean `minute_normalized`.

- Accuracy / Log Loss / Brier / AUC / correlation: **NOT COMPUTED**
- Model fitting: **NO**
- Predictions: **NO**
- Feature dataset: **NOT CREATED**
- 2025: **NOT USED**
- 2026/27: **NOT USED**
- Hyakunen, Cups, J2/J3, AFC: **NOT USED**
- external HTTP: **NO**
