# GOAL timing / first-score state feasibility audit

Status: **READY_FOR_GOAL_TIMING_FEATURE_SPEC**.

This is a source-semantics and coverage audit only. It does not create a
feature dataset, fit a model, make predictions, select features, tune
parameters, or calculate predictive metrics.

## Source and scope

- Competition: ordinary J1 only
- Seasons: 2015–2024
- Match universe: 3,208 unique matches
- Event input: `GOAL` rows only
- Event artifact:
  `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`
- Contract and provenance:
  `docs/J1_MATCH_EVENT_DATASET_SPEC.md`,
  `docs/J1_MATCH_EVENT_DATASET.md`, and
  `src/collect/sfms02_match_events.py`
- Excluded from the audit: `YELLOW_CARD`, `RED_CARD`, `SUBSTITUTION`, 2025,
  2026/27, Hyakunen, Cups, Emperor's Cup, J2/J3, and AFC
- External HTTP requests: 0

All counts below were re-derived from the materialized artifact and the
2015–2024 match/stat identity files. They were not forced to the documented
reference counts. No persistent audit script or feature artifact was created.

## Identity validation

| Check | Result |
|---|---:|
| GOAL rows | 8,377 |
| Matches with GOAL | 2,958 |
| Matches with no GOAL | 250 |
| Season range | 2015–2024 |
| Unique `event_id` values | 8,377 / 8,377 |
| GOAL match IDs in the 3,208-match universe | 2,958 / 2,958 |
| Rows whose `team_id` differs from the target match's team for `side` | 0 |
| Matches with inconsistent side-to-team mapping | 0 |

The 3,208 match IDs are unique. Every GOAL row has `side` equal to `home` or
`away`, and its `team_id` equals that match's corresponding
`home_team_id`/`away_team_id` from the official match-stat identity record.

## Minute coverage

Every GOAL row has a nonblank value in all of `minute_raw`,
`minute_normalized`, `minute_order_half`, `minute_order_base`, and
`minute_order_added`.

| Observed minute representation | GOAL rows |
|---|---:|
| Integer form such as `09'` or `46'` | 7,628 |
| of which ordinary integer form excluding `46'` | 7,584 |
| `45'+N` | 181 |
| `90'+N` | 568 |
| `46'` (subset of integer form) | 44 |
| Unsupported tokens | 0 |
| Unresolved GOAL minutes | 0 |

The mutually exclusive syntax counts 7,628 + 181 + 568 = 8,377. The 44
`46'` rows are deliberately shown again as a boundary-sensitive subset, not
as an additional syntax category. Because no GOAL minute is unresolved,
there are no unresolved match IDs or raw tokens to report.

Observed normalization flags are:

| Flag | GOAL rows |
|---|---:|
| `FIRST_HALF_ADDED_TIME_CAPPED` | 181 |
| `SECOND_HALF_ADDED_TIME_CAPPED` | 568 |
| `MINUTE_46_BOUNDARY_AMBIGUOUS` | 44 |

All 181 `45'+N` rows have first-half added-time semantics and all 568
`90'+N` rows have second-half added-time semantics. All 44 `46'` rows, in 44
distinct matches, have `MINUTE_46_BOUNDARY_AMBIGUOUS`.

## Half-boundary semantics

The existing contract assigns `45'+N` the order key `(0, 45, N)` and
`90'+N` the order key `(1, 90, N)`. They can therefore be assigned to the
first and second half, respectively. Their normalized minute is capped at 45
or 90, so timing work must retain the full order key or raw token rather than
sort on `minute_normalized` alone.

The contract assigns `46'` the order key `(1, 46, 0)` for deterministic
ordering, but explicitly flags its half boundary as ambiguous. That ordering
key is not evidence that the source distinguishes a first-half 46th-minute
event from an early-second-half event. Consequently, a `46'` GOAL must not be
silently counted in either half.

Source-safe choices for a future specification are:

1. exclude each of the 44 affected matches from complete first-/second-half
   aggregate observations; or
2. retain unambiguous first-half and second-half counts and add an explicit
   unresolved-boundary bucket for the 44 `46'` GOAL rows.

Dropping a `46'` row while treating the remaining half counts as complete
would undercount the match and is not source-safe.

## Same-time ambiguity

The audit groups GOAL rows within each match by the complete
`(minute_order_half, minute_order_base, minute_order_added)` key. It does not
use `event_id`, CSV row order, or `source_row_index` to order home against
away at the same time key.

| Match-level condition | Matches |
|---|---:|
| Any time key containing multiple GOAL rows | 1 |
| A duplicated key containing one side only | 1 |
| A duplicated key containing both home and away | 0 |
| Earliest key containing both home and away | 0 |

There is one duplicated group in total. Match `20822` has two home GOAL rows
at `(0, 44, 0)` / `44'`; it has no cross-side tie. Because both increments
belong to the same side, their internal identity order does not change the
match-level score-state path. It must nevertheless be treated as a grouped
same-time event if a future feature attempts to label individual GOAL rows.

No observed match requires a home-versus-away tie-break at the same complete
time key. This is an observed coverage result, not permission to invent a
tie-break rule: a future implementation must classify any such case as
ambiguous if it appears in new data.

## First-score classification

A match is classified from the minimum complete time key. A side is unique
only if that key contains GOAL rows for that side and not the other side.
Source or artifact row order never breaks a cross-side tie.

| Classification | Matches |
|---|---:|
| `NO_GOAL` | 250 |
| `UNIQUE_FIRST_HOME` | 1,536 |
| `UNIQUE_FIRST_AWAY` | 1,421 |
| `AMBIGUOUS_FIRST_SIDE` | 0 |
| `NOT_CHECKABLE` | 1 |
| **Total** | **3,208** |

Thus, 2,957 matches have a usable unique first side after the source-internal
exception below is excluded. The raw A2 timing keys alone select one side in
all 2,958 goal-containing matches, but that larger number must not be reported
as usable coverage because it includes match `25153`.

### Match 25153

Match `25153` is **`NOT_CHECKABLE`** for goal-state features. Official A1
stores the adjudicated score as home 0–3 away, while A2 retains five on-field
GOAL rows: home at `09'` and `53'`, and away at `27'`, `70'`, and `87'`.
The A2 history therefore describes an on-field 2–3 path that cannot be made
consistent with the adjudicated A1 state without choosing a different
semantic target or rewriting source evidence.

The event history remains valid provenance and must not be altered, but match
`25153` must be excluded from first-score and scoring-state observations. A
future feature specification must also exclude it from both teams' eligible
prior-observation denominator rather than reinterpret it as a 0–3 event
sequence.

## Quantity feasibility

`SAFE_WITH_EXCLUSION` means the stated source exception is mandatory; it is
not an optional modelling choice.

| Quantity | Decision | Source-semantics basis and required handling |
|---|---|---|
| First goal minute | `SAFE_WITH_EXCLUSION` | All GOAL minutes resolve. Use the minimum full time key; represent `NO_GOAL` explicitly and exclude match `25153`. A `46'` value remains usable as the displayed first-goal minute but not as a half label. |
| First scoring side | `SAFE_WITH_EXCLUSION` | No minimum key contains both sides. Exclude `25153`; preserve an `AMBIGUOUS_FIRST_SIDE` path for future cross-side ties. |
| Team scored-first indicator | `SAFE_WITH_EXCLUSION` | Derive only from a unique first side. No-goal matches are neither scored-first nor conceded-first unless a later spec deliberately defines a separate encoding. Exclude `25153`. |
| Team conceded-first indicator | `SAFE_WITH_EXCLUSION` | Symmetric with scored-first; do not infer from final result. Exclude `25153`. |
| First-half goals for | `SAFE_WITH_EXCLUSION` | `45'+N` is first half. Do not assign `46'`; use an unresolved bucket or exclude the 44 affected matches from complete half aggregates. Exclude `25153`. |
| First-half goals against | `SAFE_WITH_EXCLUSION` | Same half-boundary rule, applied from the opponent perspective. Exclude `25153`. |
| Second-half goals for | `SAFE_WITH_EXCLUSION` | `90'+N` is second half. Do not silently assign `46'`; use the same unresolved/exclusion policy. Exclude `25153`. |
| Second-half goals against | `SAFE_WITH_EXCLUSION` | Same half-boundary rule, applied from the opponent perspective. Exclude `25153`. |
| Full equal/leading/trailing trajectory | `SAFE_WITH_EXCLUSION` | There are no cross-side same-key groups. Process equal keys as groups and never use artifact order to resolve opposing sides. The one same-side duplicate does not change the side-level path. Exclude `25153`; reject or mark ambiguous any future cross-side same-key group. |
| Equalizer / go-ahead classification | `SAFE_WITH_EXCLUSION` | Match/team-level state changes are recoverable with the same grouped-time rule. Do not attach a distinct within-key physical order to individual rows. Exclude `25153`; reject or mark ambiguous future cross-side same-key groups. |

No listed quantity is `UNSAFE` for the observed 2015–2024 source when these
exclusions are enforced. Calling any of them unconditionally safe would be
incorrect because of match `25153`, and half aggregates additionally require
explicit `46'` handling.

## Candidate coherent feature families

No features are created in this audit. The source supports the following
future, prior-only families:

1. **First-score profile (recommended next family):** season-to-date prior
   scored-first rate and prior conceded-first rate. This has 2,957 uniquely
   classified goal-match observations plus an explicit no-goal state, needs
   only the single `25153` exclusion, and is distinct from simply recreating
   result form or goal difference.
2. **Goal-timing profile:** prior mean first-goal minute, prior mean scoring
   minute for, and prior mean scoring minute against. It must retain added-time
   order semantics, define no-goal denominators, and exclude `25153`.
3. **Half-timing profile:** prior first-/second-half scoring and conceding
   tendency. It is coherent only with a frozen unresolved/exclusion policy for
   the 44 boundary-ambiguous `46'` rows.

Any later specification must use only matches completed before the target
kickoff and must batch same-date matches conservatively where kickoff order is
unavailable. It must freeze treatment of `NO_GOAL`, denominators, minimum
history, season reset/carryover, `25153`, `46'`, and future cross-side ties
before materialization.

Simple total-goals-per-match, recent goal difference, and result-form
families are not recommended here. They would substantially duplicate Elo or
existing result features and do not isolate the new first-score/timing
information layer.

## Limitations

- SFMS02 supplies displayed minute tokens, not seconds, so events sharing a
  minute key cannot be given a finer physical time.
- `source_row_index` is identity within a side. It is not evidence for
  physical ordering across home and away.
- `event_id` and CSV order are deterministic identities/orderings, not
  physical tie-break evidence.
- The zero observed cross-side ties do not prove that later seasons or other
  competitions will have none.
- The 44 `46'` rows cannot support complete half aggregates without an
  explicit unresolved or exclusion policy.
- A2 event history and A1 adjudicated state conflict for match `25153`; this
  audit does not choose one source meaning over the other.
- This audit establishes source feasibility only. It observes no target-label
  relationship and provides no evidence of predictive usefulness.

## Final gate

**READY_FOR_GOAL_TIMING_FEATURE_SPEC**

The GOAL source has complete minute/order coverage, exact match/team/side
identity, no observed cross-side same-time ambiguity, and 2,957 usable unique
first-side matches. A prior-only team feature can therefore be specified, as
long as the specification freezes the mandatory `25153` exclusion, preserves
an ambiguity path for future cross-side ties, and treats `46'` as unresolved
for half aggregates.

Predictive metrics: **NOT COMPUTED**. Model fitting: **NO**. Predictions,
feature selection, and parameter tuning: **NO**. 2025: **NOT USED**. 2026/27
first 80: **NOT USED**. Future 300: **NOT USED**.
