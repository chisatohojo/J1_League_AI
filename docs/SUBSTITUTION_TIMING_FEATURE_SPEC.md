# Ordinary J1 team substitution timing feature specification

Status: **READY_FOR_SUBSTITUTION_TIMING_FEATURE_MATERIALIZATION**.

This document freezes the source-safe specification for one minimal team
substitution timing profile. It does not create a feature dataset, production
builder, test, generated CSV, model, prediction, or predictive metric.

## 1. Source and scope

Sources of truth:

- `docs/SUBSTITUTION_TACTICAL_PROFILE_FEASIBILITY.md`
- `docs/J1_MATCH_EVENT_DATASET_SPEC.md`
- `docs/J1_MATCH_EVENT_DATASET.md`

Frozen event artifact:

`data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`

Frozen source SHA-256:

```text
6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131
```

The target universe is exactly 3,208 ordinary-J1 matches from 2015–2024.
The source contains 23,638 normalized `SUBSTITUTION` rows covering all 3,208
matches, across 6,416 team-match sides: 6,410 with at least one SUB and 6
with zero SUB events.

Only rows with `event_type == SUBSTITUTION` are feature inputs. GOAL,
YELLOW_CARD, RED_CARD, score state, results, 2025, 2026/27, Hyakunen, Cups,
J2/J3, and AFC are excluded. External HTTP is prohibited.

## 2. Frozen feature family

The family name is **team substitution timing profile**. The exact two future
model candidates are:

```text
home_mean_substitution_minute_normalized_prior
away_mean_substitution_minute_normalized_prior
```

No other value is a model candidate under this specification. In particular,
the family excludes:

- substitution count or mean substitutions used per match;
- first or last substitution timing;
- zero-substitution rate;
- same-time multi-substitution frequency;
- substitution-window count;
- halftime substitution;
- tactical, injury, forced, concussion, goalkeeper-injury, or disciplinary
  intent classification;
- player-specific tendency, player-out/player-in identity, player quality,
  or starter importance;
- score state, goals, cards, and result form;
- home-away differences, ratios, and interactions;
- rolling-N, EWMA, smoothing, season carry-over, or regime normalization; and
- any other feature variant.

“Tactical substitution” is not an observed source label and must not be used
as an intent claim. Availability, denominators, and sums are audit fields,
not model inputs.

## 3. Normalized substitution event semantics

One normalized SUB row represents exactly one adjacent raw A7 OUT/IN pair and
therefore one substitution event. The reviewed materialization metadata
records 47,276 raw A7 rows and enforces the exact 2:1 raw-to-normalized ratio:

```text
47,276 raw A7 rows / 23,638 normalized SUB rows = 2
```

`player_name_raw` and `related_player_name_raw` are not used in feature
calculation. No stable player ID, player-name normalization, fuzzy match,
cross-team match, or cross-season player identity is required or permitted.

Every normalized SUB row remains an independent event. Two, three, or four
events sharing the same complete time key are not collapsed. They must not be
reinterpreted as one official substitution window.

## 4. Numeric minute semantics

All arithmetic uses the artifact's `minute_normalized` exactly as stored:

| Raw representation | Arithmetic value |
|---|---:|
| Ordinary integer minute | `minute_normalized` |
| `45'+N` | 45 |
| `90'+N` | 90 |
| `46'` | 46 |

Do not add stoppage time back to 45 or 90, create an elapsed-minute scale, or
classify either half. A `46'` SUB remains included with arithmetic value 46
despite `MINUTE_46_BOUNDARY_AMBIGUOUS`; it must not be called a halftime
substitution.

The frozen artifact's observed SUB `minute_normalized` range is 3 through 90.
The future builder must rederive and assert both bounds from the source rather
than coercing or filtering values to obtain them.

The complete key

```text
(minute_order_half, minute_order_base, minute_order_added)
```

is validated for source integrity. Because this family calculates only an
arithmetic mean, it does not use the key for first/last selection and needs no
tie-break by `event_id` or source row order.

## 5. Team history definition

Maintain these two states independently for each team within a season:

```text
prior_substitution_events
prior_substitution_minute_normalized_sum
```

For each history-eligible normalized SUB event belonging to the team:

```text
prior_substitution_events += 1
prior_substitution_minute_normalized_sum += minute_normalized
```

The derived value is:

```text
mean_substitution_minute_normalized_prior
  = prior_substitution_minute_normalized_sum
    / prior_substitution_events
```

Weighting is **SUB-event-weighted**. Do not calculate a per-match mean first
and then match-weight those means. Five SUB events in one match contribute
five observations. Three same-key events at normalized minute 60 contribute
three observations, denominator `+3`, and sum `+180`.

## 6. Zero-substitution match semantics

A prior team match with zero SUB events exists in chronology but adds nothing
to either timing state. It does not contribute minute 0, minute 90, a null
observation, or any missing-value surrogate.

This feature measures the average timing **conditional on a normalized SUB
event having occurred**. It does not encode match-level substitution
frequency or count, explicitly or implicitly through a fabricated
observation.

## 7. Chronology and leakage contract

Only current-season prior history is permitted:

- reset every team state at the start of each season;
- never carry prior-season state forward;
- calculate a target only from same-season SUB events with dates strictly
  before the target's `match_date`;
- calculate all target rows on one date from state available at the start of
  that date;
- update all team states for that date only after every target row on the
  date has been emitted; and
- never use the target match's own SUB events.

This same-date conservative batch also excludes peer-match events from other
matches on the target date. `match_id` ordering is for deterministic output
only and must not create within-date information flow.

## 8. Missingness and availability

For each team:

```text
prior_substitution_events == 0
  => prior_substitution_minute_normalized_sum == 0
  => mean_substitution_minute_normalized_prior is null
  => substitution_timing_available == false

prior_substitution_events >= 1
  => mean == sum / denominator
  => mean is finite and 3 <= mean <= 90
  => substitution_timing_available == true
```

Imputation is prohibited. Home and away availability are independent. A row
with only one side available is structurally valid; it is not a partial-state
failure. A failure exists only when a side's denominator, sum, mean, and
availability contradict these semantics.

Availability depends on at least one prior SUB event, not merely at least one
prior match. The reviewed artifact happens to have timing availability after
each team's first seasonal target, but this observed coincidence must not be
generalized. In future data, a team with prior matches but zero prior SUB
events remains timing-unavailable.

Availability flags and audit state are not model candidates.

## 9. Frozen output schema

One row represents one ordinary-J1 target match. The exact schema is:

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
home_substitution_timing_available
away_substitution_timing_available
```

Audit denominators:

```text
home_prior_substitution_events
away_prior_substitution_events
```

Audit sums:

```text
home_prior_substitution_minute_normalized_sum
away_prior_substitution_minute_normalized_sum
```

Candidate means:

```text
home_mean_substitution_minute_normalized_prior
away_mean_substitution_minute_normalized_prior
```

Only the final two means are future model candidates.

## 10. Frozen availability references

The future builder must rederive and assert these current-season-prior,
same-date-batched references. Filtering must not be changed to make counts
agree.

| Season | Target matches | Pair available |
|---:|---:|---:|
| 2015 | 306 | 297 |
| 2016 | 306 | 297 |
| 2017 | 306 | 297 |
| 2018 | 306 | 297 |
| 2019 | 306 | 297 |
| 2020 | 306 | 297 |
| 2021 | 380 | 370 |
| 2022 | 306 | 297 |
| 2023 | 306 | 297 |
| 2024 | 380 | 370 |
| **Total** | **3,208** | **3,116** |

Global references:

- pair available: 3,116;
- pair unavailable: 92;
- team-side available: 6,232 of 6,416; and
- team-side unavailable: 184.

Pair availability requires both side flags to be true. These are validation
references, not permission to redefine availability or source scope.

## 11. Source validation contract

The future builder must hard-fail unless all of the following hold:

- exactly 3,208 unique ordinary-J1 target match rows;
- target seasons exactly 2015–2024;
- source artifact SHA-256 exactly matches the frozen digest;
- exactly 39,987 total normalized event rows and exactly 23,638 selected SUB
  rows;
- SUB match coverage exactly 3,208;
- every selected `event_id` is nonblank and unique;
- every selected `event_type` is exactly `SUBSTITUTION`;
- every selected `source_section` is exactly `A7`;
- every selected side is `home` or `away`;
- match, date, season, team, and side identity agrees exactly with the target
  universe;
- `minute_raw`, `minute_normalized`, `minute_order_half`,
  `minute_order_base`, and `minute_order_added` are resolved;
- `minute_normalized` is numeric and its observed range is exactly 3–90;
- no player field participates in state, identity, joining, or calculation;
- the source artifact remains read-only;
- target leakage, same-date leakage, and prior-season carry-over are absent;
  and
- every frozen availability reference is reproduced.

When the existing materialization metadata is available, it must also confirm
47,276 raw A7 rows and the exact raw-A7-to-normalized-SUB ratio of 2:1.
Absence or disagreement of required source evidence is a hard failure; values
must not be reconstructed by altering event classification.

## 12. Result invariants

For both home and away state independently, the future output must satisfy:

- denominator is a nonnegative integer;
- sum is finite and nonnegative;
- denominator zero implies sum zero, mean null, and availability false;
- denominator positive implies mean exactly `sum / denominator` within the
  future implementation's frozen numeric tolerance, finite, within 3–90, and
  availability true;
- availability is equivalent to a positive denominator; and
- no value is imputed.

A partial or inconsistent state is a hard failure. Home availability need not
equal away availability.

## 13. Same-time and boundary examples

Complete-key-equal events remain separate observations:

```text
three SUB events at normalized minute 60
=> denominator increment = 3
=> sum increment = 180
=> contribution mean = 60
```

They are not converted to one window and require no physical time tie-break.

Boundary arithmetic is fixed:

```text
45'+N => 45
90'+N => 90
46'    => 46 and remains included
```

No value is labeled as halftime from these minute representations.

## 14. Rule-regime boundary

The reviewed source audit found a large substitution-count distribution break
between 2019 and 2020. Count, frequency, quota, and regime-normalized values
are therefore excluded from this family.

Mean substitution timing was descriptively more stable across seasons than
count but is not claimed to be regime-free. This is a source-comparability
choice only; it is not evidence of predictive superiority. The frozen family
must not be changed in response to availability or future predictive results.

## 15. Required future fixture tests

The future implementation must include at least these 20 tests:

1. The first target has denominator 0, sum 0, null mean, and availability
   false.
2. One prior SUB at 60 yields denominator 1, sum 60, mean 60, and availability
   true.
3. Prior SUB events at 60, 70, and 80 yield event-weighted mean 70.
4. Multiple SUB events in one prior match are all counted individually.
5. Three same-time SUB events at 60 yield denominator 3, sum 180, and mean 60.
6. A prior zero-SUB match leaves timing state unchanged and availability false
   when the denominator remains zero.
7. Target-match SUB events cannot enter their own features.
8. Same-date peer SUB events cannot enter target features.
9. Prior-day SUB events are available on the next date.
10. A season boundary resets denominator, sum, mean, and availability.
11. `45'+N` contributes 45.
12. `90'+N` contributes 90.
13. `46'` contributes 46 and is not excluded.
14. Home and away team histories update independently.
15. Rebuilding identical input produces identical rows, values, order, and
    bytes.
16. A match/team/side identity mismatch hard-fails.
17. A duplicate SUB `event_id` hard-fails.
18. Any unresolved SUB minute or order component hard-fails.
19. Any denominator/sum/mean/availability inconsistency hard-fails.
20. Every frozen season and global availability count is reproduced.

Feature variants must not be added by the implementation or tests.

## 16. Future materialization audit

The future builder and materialization report must include:

Source reconciliation:

- target rows and total normalized event rows;
- normalized SUB rows and SUB-covered matches;
- total, positive-SUB, and zero-SUB team-match sides;
- frozen source SHA-256; and
- raw A7 row count and ratio when available from materialization metadata.

Output reconciliation:

- output rows;
- total history SUB observations actually applied;
- denominator/sum invariant failures; and
- partial-invalid rows.

Season-level availability:

- total targets;
- home available;
- away available;
- pair available;
- either unavailable; and
- both unavailable.

The report must assert the ten frozen pair counts, global pair available
3,116, pair unavailable 92, side available 6,232, and side unavailable 184.
It must also publish the output SHA-256.

## 17. Explicit non-goals and data discipline

This specification does not authorize any adjacent substitution family,
score-state analysis, goal-timing combination, model evaluation, feature
selection, or tuning. In particular, it does not authorize count, first/last
timing, zero-SUB rate, same-time frequency, window, halftime, intent, or
player-specific features.

No Accuracy, Log Loss, Brier score, AUC, correlation, coefficient, feature
importance, or target-label comparison is calculated or inspected.

## 18. Final gate

**READY_FOR_SUBSTITUTION_TIMING_FEATURE_MATERIALIZATION**

The source scope, two-value family, normalized event semantics, minute
arithmetic, event weighting, zero-SUB semantics, chronology, missingness,
availability, output schema, source validation, result invariants, audit
references, and required fixture tests are fully frozen.

- Model candidates: **EXACTLY TWO**
- Metrics: **NOT COMPUTED**
- Model fitting: **NO**
- Predictions: **NO**
- Feature dataset: **NOT CREATED**
- Production builder: **NOT CREATED**
- Tests: **NOT CREATED**
- 2025: **NOT USED**
- 2026/27: **NOT USED**
- external HTTP: **NO**
