# Ordinary J1 goal timing profile feature specification

Status: **READY_FOR_GOAL_TIMING_FEATURE_MATERIALIZATION**.

This document freezes the source-safe specification for the current-season
prior goal timing mean family. It does not create a feature dataset,
production module, tests, generated CSV, model, prediction, or predictive
metric.

## 1. Source and scope

- Competition: ordinary J1 only
- Seasons: 2015–2024
- Target universe: 3,208 matches
- Event source:
  `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`
- Frozen source SHA-256:
  `6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131`
- GOAL rows: 8,377
- Matches with GOAL: 2,958
- `NO_GOAL` matches: 250
- Source semantics: `docs/GOAL_TIMING_STATE_FEASIBILITY.md`
- Dataset contract: `docs/J1_MATCH_EVENT_DATASET.md`

Only `GOAL` events are inputs. `SUBSTITUTION`, `YELLOW_CARD`, `RED_CARD`,
2025, 2026/27, Hyakunen, League Cup, Emperor's Cup, J2/J3, and AFC are
excluded. External HTTP is prohibited.

## 2. Frozen feature family

The family is the current-season prior goal timing profile. The exact future
model-candidate values are:

```text
home_mean_first_goal_minute_normalized_prior
away_mean_first_goal_minute_normalized_prior
home_mean_scoring_minute_normalized_prior
away_mean_scoring_minute_normalized_prior
home_mean_conceding_minute_normalized_prior
away_mean_conceding_minute_normalized_prior
```

No other value is a model candidate under this specification. In particular,
do not create first-score-side or no-goal rates, goal volume, goals per match,
goal difference, result form, half splits, early/late buckets,
equalizer/go-ahead or trajectory features, last-N/rolling/EWMA variants,
home-away differences, ratios, or interactions.

## 3. Numeric minute semantics

Every arithmetic timing value uses the existing artifact's
`minute_normalized` exactly as stored. No new elapsed-minute conversion is
permitted:

| Raw representation | Value used in a mean |
|---|---:|
| Ordinary integer minute | `minute_normalized` |
| `45'+N` | 45 |
| `90'+N` | 90 |
| `46'` | 46 |

Do not add stoppage time back to 45 or 90, and do not place those values on a
new elapsed-time scale. Every candidate name includes `minute_normalized` so
it is not mistaken for literal elapsed time.

The complete lexicographic key

```text
(minute_order_half, minute_order_base, minute_order_added)
```

is used only to identify a match's first GOAL. Sorting first goals by
`minute_normalized` alone is prohibited. Artifact row order, `event_id`, and
`source_row_index` must not break a same-key tie.

If multiple GOAL rows share the minimum complete key, whether from one side or
both sides, the match still supplies exactly one first-goal timing observation.
All rows at one complete key must agree on `minute_normalized`; disagreement is
a hard source-integrity failure.

## 4. Mandatory exclusion: match 25153

Match `25153` is completely excluded from goal timing history because A1
stores an adjudicated 0–3 result while A2 retains a five-GOAL on-field 2–3
history. The sources are not reinterpreted.

The target row for `25153` remains in the 3,208-match target universe and
receives features from history strictly before its date. After target rows for
that date are emitted, none of its following source values enter history:

- its match-level first-goal timing observation;
- its two home scoring GOAL events;
- its three away scoring GOAL events; or
- any corresponding conceding GOAL events.

The future builder must derive the exclusion from the artifact and verify that
`25153` contains five GOAL rows. The expected history-eligible GOAL total is
8,372 (`8,377 - 5`), but it must be rederived before being asserted rather
than obtained by changing classification to meet the reference.

## 5. Match-level first-goal observation

For every match other than `25153`:

- when at least one GOAL exists, take the minimum complete order key and use
  that key's single `minute_normalized` value as one
  `first_goal_minute_normalized` observation;
- when no GOAL exists, create no first-goal timing observation.

A `NO_GOAL` match must not be represented as minute 0, 90, 91, or an imputed
value. The expected usable match-level first-goal observation count is 2,957:
2,958 goal-containing matches minus `25153`. The future builder must rederive
and assert this count.

The first-goal value is about timing, not first-scoring side. A cross-side
minimum-key tie therefore remains one usable first-goal timing observation;
no side tie-break is needed or allowed.

## 6. Team history states

History is maintained independently for each team within a season.

### First-goal timing

Maintain:

```text
prior_first_goal_timing_observations
prior_first_goal_minute_normalized_sum
```

For every prior usable goal-containing match, increment the observation count
once and add the match-level first-goal value for both participating teams.
Which side scored first is irrelevant. `NO_GOAL` and `25153` increment neither
counter.

```text
mean_first_goal_minute_normalized_prior
  = prior_first_goal_minute_normalized_sum
    / prior_first_goal_timing_observations
```

This is match-weighted: one goal-containing match contributes one observation
to each participating team, regardless of its total goals.

### Scoring timing

Maintain:

```text
prior_scoring_goal_events
prior_scoring_minute_normalized_sum
```

For each history-eligible GOAL row, increment the scoring team's event count
and add that row's `minute_normalized` value.

```text
mean_scoring_minute_normalized_prior
  = prior_scoring_minute_normalized_sum / prior_scoring_goal_events
```

This is GOAL-event-weighted. A team scoring three times in one match contributes
three observations. Do not first average within each match and then give every
match equal weight.

### Conceding timing

Maintain:

```text
prior_conceding_goal_events
prior_conceding_minute_normalized_sum
```

For each history-eligible GOAL row, increment the opponent of the scoring team
and add the same `minute_normalized` value.

```text
mean_conceding_minute_normalized_prior
  = prior_conceding_minute_normalized_sum / prior_conceding_goal_events
```

This is also GOAL-event-weighted. Every eligible GOAL contributes exactly one
scoring event to one team and one conceding event to its opponent. Global
scoring and conceding event counts must therefore be equal.

Same-key duplicate GOAL rows remain separate scoring/conceding events, even
though a minimum-key group supplies only one match-level first-goal timing
observation.

## 7. Chronology and leakage contract

Only current-season prior history is permitted:

- reset every team state at the start of each season;
- do not carry prior-season values forward;
- calculate a target from usable matches with dates strictly before its date;
- calculate all targets on one date from the history available at the start of
  that date;
- append all usable observations from the date only after all of that date's
  target rows have been emitted; and
- never use a target's own GOAL rows in its features.

`match_id` ordering is for deterministic output only. It must not allow
information flow between same-date matches.

## 8. Missingness and availability

Each mean follows its own denominator:

- denominator `0` means the corresponding mean is null;
- denominator `>= 1` means the corresponding mean is `sum / denominator` and
  is finite;
- a real zero minute, should one be present in an otherwise valid future
  source, is data and must not be confused with missing history.

A team's `goal_timing_available` flag is true only when all three denominators
are at least one:

```text
prior_first_goal_timing_observations >= 1
prior_scoring_goal_events >= 1
prior_conceding_goal_events >= 1
```

When available is true, all three means are non-null and finite. When it is
false, at least one denominator is zero, but each mean independently retains
its own denominator-based null semantics. For example, a team may have finite
first-goal and scoring means, a null conceding mean, and overall availability
false. Imputation is prohibited.

A future evaluation may consider a target pair eligible only when all six
candidate means are present through both teams' availability. That evaluation
rule is not executed or otherwise extended here.

## 9. `46'` and same-time semantics

This family does not classify halves. A GOAL carrying
`MINUTE_46_BOUNDARY_AMBIGUOUS` remains eligible for:

- complete-key first-goal ordering;
- scoring timing; and
- conceding timing.

Its arithmetic value is 46. It must not be reinterpreted as first-half or
second-half evidence.

For any future cross-side same-minimum-key case, create one match-level
first-goal timing observation using the shared normalized value and count all
individual GOAL rows in their respective scoring/conceding histories. Do not
resolve the side tie. The same rule applies to same-side duplicate minimum-key
rows: one first-goal observation, but every GOAL remains event-weighted in
scoring and conceding histories.

## 10. Frozen target-row schema

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

Candidate means:

```text
home_mean_first_goal_minute_normalized_prior
away_mean_first_goal_minute_normalized_prior
home_mean_scoring_minute_normalized_prior
away_mean_scoring_minute_normalized_prior
home_mean_conceding_minute_normalized_prior
away_mean_conceding_minute_normalized_prior
```

Only the six means are future model candidates. Availability, denominators,
and sums are audit fields and are not automatically supplied to a model.

## 11. Future materialization validation contract

A future builder must hard-fail unless all of the following hold:

- exactly 3,208 unique target match rows;
- seasons exactly 2015–2024 and ordinary J1 only;
- exactly 8,377 source GOAL rows, rederived from the event artifact;
- every GOAL match ID belongs to the target universe;
- every GOAL `event_id` is nonblank and unique;
- every GOAL side is `home` or `away`;
- match, date, season, team, and side identities agree exactly;
- `minute_normalized` and all complete order-key fields are resolved;
- `25153` remains a target and is absent from every timing-history update;
- `25153` has five source GOAL rows and leaves 8,372 eligible GOAL rows;
- usable first-goal match observations equal 2,957;
- the source artifact is read-only and retains the frozen SHA-256;
- target leakage, same-date leakage, and prior-season carry-over are absent;
- all denominators and sums are nonnegative;
- denominator zero implies the corresponding mean is null;
- denominator positive implies the corresponding mean equals sum/denominator,
  is finite, and lies within the observed `minute_normalized` source range;
- availability equals the conjunction of all three positive denominators; and
- no partial or structurally inconsistent row is published.

Source-level history totals must also reconcile:

- 2,957 usable match-level first-goal timing observations;
- 5,914 team-history first-goal increments, two per usable match;
- 8,372 scoring GOAL event observations; and
- 8,372 conceding GOAL event observations.

These expected values are validation references, not permission to coerce or
reclassify source rows to achieve them.

## 12. Required future fixture tests

The future implementation must include at least these tests:

1. First target: all denominators zero, all means null, availability false.
2. One prior home GOAL at `10'`: both teams' first-goal mean is 10; home
   scoring mean is 10 and conceding mean null; away scoring mean is null and
   conceding mean 10.
3. A prior 0–0 match changes no timing denominator.
4. Scoring events at `10'`, `20'`, `30'` produce event-weighted mean 20.
5. Multiple GOAL rows in one match still produce one first-goal observation.
6. Each GOAL minute enters the scorer's scoring history and the opponent's
   conceding history symmetrically.
7. Target-match GOAL rows are not used in their own features.
8. Same-date peer GOAL rows are not used.
9. Prior-day observations are available on the next date.
10. A season boundary resets every timing history state.
11. A `25153`-equivalent `NOT_CHECKABLE` target row exists but adds no timing
    observation or event.
12. `45'+N` uses value 45 in means while first-goal ordering uses the full key.
13. `90'+N` uses value 90 in means.
14. `46'` uses value 46 and is not excluded for half ambiguity.
15. A cross-side same-minimum-key group supplies one first-goal observation
    without a side tie-break.
16. A same-side duplicate minimum-key group supplies one first-goal
    observation.
17. Rebuilding from identical input produces identical rows, values, order,
    and bytes.
18. A mismatched match/team/side identity hard-fails.
19. Any denominator/mean partial or inconsistent state hard-fails.

## 13. Future materialization audit

The materialization report must include:

- target rows, source GOAL rows, and usable GOAL rows after `25153` exclusion;
- usable match-level and team-history first-goal observation counts;
- `NO_GOAL` and excluded-match counts;
- scoring and conceding GOAL event counts, which must match globally;
- by season: total target matches, home available, away available, pair
  available, either unavailable, and both unavailable; and
- by season or in total: first-goal, scoring, and conceding source observation
  counts.

Pair-availability counts for 2020–2024 must be fixed before any evaluation
freeze. Availability results must not be used to redefine this feature family.

## 14. Explicit boundaries

This specification does not reopen the first-score profile evaluation and
does not expand into half timing, score-state trajectories, equalizer or
go-ahead analysis, goal volume, finishing efficiency, shots, or xG.

No Log Loss, Brier, Accuracy, correlation, AUC, coefficient, feature
importance, or target-label relationship is calculated or inspected. Model
fitting, prediction, feature selection, parameter tuning, and adaptive
follow-up are prohibited.

## 15. Final gate

**READY_FOR_GOAL_TIMING_FEATURE_MATERIALIZATION**

The source scope, exclusion, minute arithmetic, first-goal ordering,
event/match weighting, chronology, missingness, availability, schema,
validation contract, and required fixture tests are fully frozen.

- Metrics: **NOT COMPUTED**
- Model fitting: **NO**
- Predictions: **NO**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- external HTTP: **NO**
