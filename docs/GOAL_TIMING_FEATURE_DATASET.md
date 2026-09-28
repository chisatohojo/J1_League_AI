# Ordinary J1 goal timing profile feature dataset

Status: **MATERIALIZED_AND_VALIDATED**.

Final gate: **READY_FOR_GOAL_TIMING_EVALUATION_FREEZE**.

## Purpose

This dataset provides leakage-safe, current-season prior first-goal, scoring,
and conceding timing means for ordinary-J1 target matches. It materializes
`docs/GOAL_TIMING_FEATURE_SPEC.md` without fitting a model or evaluating
predictive performance.

## Source and scope

- Target competition: ordinary J1 only
- Target seasons: 2015–2024
- Target rows: 3,208, one per unique match
- GOAL source:
  `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`
- Source SHA-256:
  `6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131`
- Builder: `src/features/goal_timing_profile.py`
- Output:
  `data/processed/features/2015_2024_j1_goal_timing_features.csv`
- Output SHA-256:
  `260e79cec4836243586556c0e253818ed063d27870d74649c939502287919e42`

The generated CSV is gitignored. No 2025, 2026/27, Hyakunen, League Cup,
Emperor's Cup, J2/J3, or AFC match is used. External HTTP requests were not
made.

## Minute and weighting semantics

Arithmetic uses the source artifact's `minute_normalized` value exactly:

- `45'+N` contributes 45;
- `90'+N` contributes 90; and
- `46'` contributes 46 despite `MINUTE_46_BOUNDARY_AMBIGUOUS`.

Stoppage time is not added back, and this family does not classify halves.
The full lexicographic key
`(minute_order_half, minute_order_base, minute_order_added)` identifies the
first GOAL in a match; `minute_normalized` alone is never used for ordering.

First-goal timing is match-weighted: one usable goal-containing match supplies
one observation to each participating team. Scoring and conceding timing are
GOAL-event-weighted: every GOAL supplies one scoring observation to the
scoring team and one conceding observation to its opponent.

A same-side or cross-side duplicate minimum key supplies one match-level
first-goal timing observation. Its individual GOAL rows remain separate
scoring and conceding observations. Artifact row order, `event_id`, and
`source_row_index` are not timing tie-breaks. Known match `20822` follows this
same-side duplicate rule.

## `NO_GOAL` and match 25153

A `NO_GOAL` match remains a target row but adds no first-goal, scoring, or
conceding timing observation. It is not represented as minute 0, 90, 91, or
an imputed value.

Match `25153` also remains a target row and receives normal prior-date
features. Its five A2 GOAL rows are completely excluded from later history
because the A1 adjudicated 0–3 score and A2 on-field 2–3 history cannot be
reconciled without reinterpreting source evidence.

The exclusion was independently checked on both teams' next targets:

| Team | Next target | First count/sum | Scoring count/sum | Conceding count/sum | Exclusion check |
|---|---:|---:|---:|---:|:---:|
| `team_0030` | `25156` | 15 / 568 | 20 / 1,049 | 19 / 958 | PASS |
| `team_0026` | `25173` | 13 / 430 | 15 / 790 | 18 / 966 | PASS |

Each output state equals an independent count over earlier 2021 source
matches with `25153` removed.

## Chronology and availability

All target rows on a date are calculated from history available at the start
of that date. The date's usable observations enter history only after every
target on that date has been emitted. The target's own GOAL rows cannot enter
its features. History resets at every season boundary with no prior-season
carry-over.

Each mean is null exactly when its own denominator is zero. A team's
`goal_timing_available` is true only when its first-goal, scoring, and
conceding denominators are all positive. A team can therefore have one or two
finite means while its overall timing profile remains unavailable; no value is
imputed.

## Output schema

Identity:

```text
match_id
match_date
season
home_team_id
away_team_id
```

Availability:

```text
home_goal_timing_available
away_goal_timing_available
```

Audit denominators:

```text
home_prior_first_goal_timing_observations
away_prior_first_goal_timing_observations
home_prior_scoring_goal_events
away_prior_scoring_goal_events
home_prior_conceding_goal_events
away_prior_conceding_goal_events
```

Audit sums:

```text
home_prior_first_goal_minute_normalized_sum
away_prior_first_goal_minute_normalized_sum
home_prior_scoring_minute_normalized_sum
away_prior_scoring_minute_normalized_sum
home_prior_conceding_minute_normalized_sum
away_prior_conceding_minute_normalized_sum
```

The exact six future model candidates are:

```text
home_mean_first_goal_minute_normalized_prior
away_mean_first_goal_minute_normalized_prior
home_mean_scoring_minute_normalized_prior
away_mean_scoring_minute_normalized_prior
home_mean_conceding_minute_normalized_prior
away_mean_conceding_minute_normalized_prior
```

Availability, denominators, and sums are audit fields and are not
automatically model inputs.

## Global source reconciliation

| Item | Count |
|---|---:|
| Target matches | 3,208 |
| Source GOAL rows | 8,377 |
| Source GOAL matches | 2,958 |
| `NO_GOAL` matches | 250 |
| Excluded matches | 1 |
| Excluded GOAL rows | 5 |
| History-eligible GOAL rows | 8,372 |
| Usable match-level first-goal observations | 2,957 |
| Team-history first-goal increments | 5,914 |
| Scoring GOAL observations | 8,372 |
| Conceding GOAL observations | 8,372 |

Scoring and conceding totals are equal because each eligible GOAL is counted
once from each perspective.

| Season | Usable first-goal matches | Eligible scoring events | Eligible conceding events |
|---:|---:|---:|---:|
| 2015 | 283 | 820 | 820 |
| 2016 | 287 | 805 | 805 |
| 2017 | 288 | 793 | 793 |
| 2018 | 279 | 813 | 813 |
| 2019 | 289 | 797 | 797 |
| 2020 | 286 | 866 | 866 |
| 2021 | 345 | 917 | 917 |
| 2022 | 270 | 771 | 771 |
| 2023 | 282 | 777 | 777 |
| 2024 | 348 | 1,013 | 1,013 |
| **Total** | **2,957** | **8,372** | **8,372** |

## Availability audit

`either unavailable` means at least one side is unavailable; `both
unavailable` means neither side has a complete three-mean profile.

| Season | Total | Home available | Away available | Pair available | Either unavailable | Both unavailable |
|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 294 | 293 | 291 | 15 | 10 |
| 2016 | 306 | 290 | 290 | 286 | 20 | 12 |
| 2017 | 306 | 290 | 289 | 285 | 21 | 12 |
| 2018 | 306 | 291 | 292 | 286 | 20 | 9 |
| 2019 | 306 | 291 | 289 | 287 | 19 | 13 |
| 2020 | 306 | 291 | 292 | 288 | 18 | 11 |
| 2021 | 380 | 362 | 362 | 356 | 24 | 12 |
| 2022 | 306 | 293 | 291 | 289 | 17 | 11 |
| 2023 | 306 | 290 | 291 | 286 | 20 | 11 |
| 2024 | 380 | 363 | 364 | 357 | 23 | 10 |
| **Total** | **3,208** | **3,055** | **3,053** | **3,011** | **197** | **111** |

Required 2020–2024 pair-availability counts are:

| Season | Pair available |
|---:|---:|
| 2020 | 288 |
| 2021 | 356 |
| 2022 | 289 |
| 2023 | 286 |
| 2024 | 357 |

## Validation and determinism

Validation passed for:

- frozen source SHA-256 and read-only source use;
- 3,208 unique targets and exact TeamMaster identities;
- 8,377 unique-ID, resolved-minute GOAL rows;
- exact event match/date/season/team/side identity;
- `45'+N = 45`, `90'+N = 90`, and `46' = 46` arithmetic;
- complete-key first-goal selection and same-time group semantics;
- full `25153` history exclusion;
- same-date batching, season reset, and no target leakage;
- denominator, sum, mean, missingness, range, and availability invariants;
- zero partial-invalid rows; and
- all 19 frozen fixture contracts plus source-integrity hard-fail cases.

A full rebuild from the same inputs was byte-identical and reproduced SHA-256
`260e79cec4836243586556c0e253818ed063d27870d74649c939502287919e42`.
Existing output is never silently overwritten.

## Limitations

- Means use normalized/capped source minutes, not literal elapsed time.
- First-goal timing intentionally discards first-scoring-side identity.
- Same-key GOAL rows have no finer physical order.
- `46'` is usable for timing means but remains unsuitable for a half split.
- `NO_GOAL` and match `25153` supply no timing-history observation.
- Same-date batching is conservative and may omit an earlier same-day kickoff
  from a later kickoff's history.
- Availability coverage did not change the frozen family.
- No goal volume, result, half, state, equalizer/go-ahead, shot, or xG feature
  is included.

No Log Loss, Brier score, Accuracy, correlation, AUC, coefficient, feature
importance, or other predictive metric was observed or computed. No model was
fit and no prediction, feature selection, or parameter tuning was performed.
