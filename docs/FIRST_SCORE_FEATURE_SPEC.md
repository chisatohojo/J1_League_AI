# Ordinary J1 first-score profile feature specification

Status: **READY_FOR_FIRST_SCORE_FEATURE_MATERIALIZATION**.

This document freezes the source-safe specification for the first-score
profile family. It does not materialize a feature dataset, add production
code, add tests, fit a model, make predictions, select features, tune
parameters, or calculate predictive metrics.

## Source and scope

- Source events: `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`
- Source semantics: `docs/GOAL_TIMING_STATE_FEASIBILITY.md`
- Competition: ordinary J1 only
- Seasons: 2015–2024
- Match universe: 3,208 matches
- GOAL source rows: 8,377
- External HTTP: prohibited and not used
- Excluded: 2025, 2026/27, Hyakunen, Cups, Emperor's Cup, J2/J3, and AFC

Only `GOAL` events participate. Cards and substitutions are not inputs to this
family.

## Match-level classification

For every ordinary-J1 match, take the minimum complete time key

`(minute_order_half, minute_order_base, minute_order_added)`

among its GOAL rows. The classification is:

| Match classification | Definition |
|---|---|
| `SCORED_FIRST_HOME` | The minimum key contains home GOAL row(s) only |
| `SCORED_FIRST_AWAY` | The minimum key contains away GOAL row(s) only |
| `NO_GOAL` | The match has no GOAL rows |
| `AMBIGUOUS_FIRST_SIDE` | The minimum key contains both home and away GOAL rows |
| `NOT_CHECKABLE` | Source semantics prevent a safe first-score observation |

The known 2015–2024 coverage is:

| Classification / coverage | Matches |
|---|---:|
| `NO_GOAL` | 250 |
| Unique first-side usable | 2,957 |
| `AMBIGUOUS_FIRST_SIDE` | 0 |
| `NOT_CHECKABLE` | 1 |
| Known `NOT_CHECKABLE` match | `25153` |

Artifact row order, `event_id`, CSV order, and `source_row_index` must never
break a home/away tie. A same-minimum-key group containing multiple GOAL rows
from one side only remains unique for first-side purposes. Known match `20822`
has this same-side duplicate and is therefore safe for this classification.

For future data, every cross-side same-minimum-key match is
`AMBIGUOUS_FIRST_SIDE` and is excluded from both teams' eligible history
denominators.

## Team-level observation semantics

Each usable match contributes exactly one observation from each team's
perspective.

| Match class | Home observation | Away observation |
|---|---|---|
| `SCORED_FIRST_HOME` | `scored_first=1`, `conceded_first=0`, `no_goal=0` | `scored_first=0`, `conceded_first=1`, `no_goal=0` |
| `SCORED_FIRST_AWAY` | `scored_first=0`, `conceded_first=1`, `no_goal=0` | `scored_first=1`, `conceded_first=0`, `no_goal=0` |
| `NO_GOAL` | `scored_first=0`, `conceded_first=0`, `no_goal=1` | `scored_first=0`, `conceded_first=0`, `no_goal=1` |

For `AMBIGUOUS_FIRST_SIDE` and `NOT_CHECKABLE`, no team-level observation is
created. Neither team receives an eligible-match increment or any counter
increment.

## History and leakage semantics

For a target match, history consists only of usable ordinary-J1 matches in the
same season that finished before the target match date.

- The history resets at the start of every season.
- No prior-season carry-over is used.
- All target matches on a date are feature-calculated from the history before
  that date.
- The date's first-score observations are appended only after every target on
  that date has been calculated (conservative same-date batch).
- The target match itself is never included in its own history.
- A target row may exist even when its own match is `NOT_CHECKABLE`; its
  features use only the prior history, and its match observation is never
  appended to later history.

This date-level rule is required because kickoff order is not a frozen source
field for all historical matches.

## Frozen counters

Maintain the following counters independently for each team and season:

- `prior_first_score_eligible_matches`
- `prior_scored_first_matches`
- `prior_conceded_first_matches`
- `prior_no_goal_matches`

The invariant is mandatory for every team snapshot:

`prior_first_score_eligible_matches = prior_scored_first_matches + prior_conceded_first_matches + prior_no_goal_matches`

`25153` and every future `AMBIGUOUS_FIRST_SIDE` or `NOT_CHECKABLE` match are
excluded from all four counters. A `NO_GOAL` match is eligible and increments
`prior_no_goal_matches` for both teams.

## Frozen rates and missingness

When `prior_first_score_eligible_matches >= 1`:

```text
scored_first_rate_prior    = prior_scored_first_matches / prior_first_score_eligible_matches
conceded_first_rate_prior  = prior_conceded_first_matches / prior_first_score_eligible_matches
no_goal_rate_prior         = prior_no_goal_matches / prior_first_score_eligible_matches
```

For an available snapshot, all three rates are finite, in `[0, 1]`, and sum
to `1.0` within normal floating-point tolerance.

When `prior_first_score_eligible_matches == 0`:

```text
available = false
scored_first_rate_prior   = null
conceded_first_rate_prior = null
no_goal_rate_prior        = null
```

Missing history is not a real zero. If history is available and consists of
zero or more scored/conceded-first observations plus real `NO_GOAL`
observations, the corresponding zero rates are retained; for example, a
single prior `NO_GOAL` gives `0.0, 0.0, 1.0`.

Only these two values are frozen as future model candidates:

- `scored_first_rate_prior`
- `conceded_first_rate_prior`

`no_goal_rate_prior` is retained for audit and consistency only. It is exactly
`1 - scored_first_rate_prior - conceded_first_rate_prior` and is not
automatically supplied to a model.

## Frozen target-row schema

One future output row represents one ordinary-J1 target match.

Identity columns:

```text
match_id
match_date
season
home_team_id
away_team_id
```

Audit and availability columns:

```text
home_first_score_available
away_first_score_available
home_prior_first_score_eligible_matches
away_prior_first_score_eligible_matches
home_prior_scored_first_matches
away_prior_scored_first_matches
home_prior_conceded_first_matches
away_prior_conceded_first_matches
home_prior_no_goal_matches
away_prior_no_goal_matches
```

Rate columns:

```text
home_scored_first_rate_prior
away_scored_first_rate_prior
home_conceded_first_rate_prior
away_conceded_first_rate_prior
home_no_goal_rate_prior
away_no_goal_rate_prior
```

The exact future model-candidate set is:

```text
home_scored_first_rate_prior
away_scored_first_rate_prior
home_conceded_first_rate_prior
away_conceded_first_rate_prior
```

Availability flags, counters, and `no_goal_rate_prior` are audit/support
columns and are not automatically model inputs.

## Mandatory source exceptions

### Match 25153

Match `25153` is a mandatory exclusion from first-score observations and both
teams' prior eligible denominators. A1 contains the adjudicated 0–3 score
while A2 retains five on-field GOAL rows describing a 2–3 history. The
specification does not reinterpret one source as the other.

If `25153` is itself a target row, that row remains in the 3,208-match target
universe and receives features calculated from history strictly before its
date. Its event observation is not appended to history after the date.

### `46'` minute

The first-score family does not use half classification. Therefore a `46'`
GOAL may participate in minimum full-time-key ordering, while retaining its
`MINUTE_46_BOUNDARY_AMBIGUOUS` flag. The flag does not by itself invalidate
first-score-side classification. `46'` semantics must not be reused to create
half features in this family.

## Explicitly out of scope

This family does not create or derive:

- first-goal-minute means, scoring-minute means, or conceding-minute means
- first-/second-half splits
- score trajectories, equalizer rates, or go-ahead rates
- recent last-N, rolling 3/5/10, or EWMA variants
- home-away differences, ratios, or interactions
- first-goal-minute buckets
- total goals, goal difference, or result form

The first-score state is frozen as an independent coherent family; those
families require separate specifications.

## Future materialization validation contract

A future builder must hard-fail on any partial or inconsistent result and
must assert:

- exactly 3,208 target rows
- unique `match_id`
- ordinary J1 2015–2024 scope only
- source GOAL row count 8,377
- exact match/team/side identity
- `25153` absent from every history denominator
- ambiguous first-side matches absent from every history denominator
- `NO_GOAL` observations included as eligible observations
- conservative same-date batching
- season reset with no prior-season carry-over
- no target leakage
- `eligible = scored_first + conceded_first + no_goal`
- available rows have `eligible >= 1`, finite rates, rates in `[0,1]`, and
  three-rate sum approximately 1
- unavailable rows have `eligible == 0` and all three rates null

Any partial row, non-null rate for an unavailable snapshot, denominator
violation, or identity mismatch is a hard failure.

## Required fixture tests to freeze

The future implementation must include at least these tests:

1. First target match: unavailable and null rates.
2. One prior scored-first match: rates `1.0, 0.0, 0.0`.
3. One prior conceded-first match: rates `0.0, 1.0, 0.0`.
4. One prior 0–0 match: rates `0.0, 0.0, 1.0`.
5. Three prior observations (scored-first, conceded-first, no-goal): all rates
   `1/3`.
6. Target GOAL rows are never used in their own features.
7. A same-date peer match is never used.
8. A prior-day observation is used on the following day.
9. Season reset removes prior-season history.
10. `25153`-equivalent `NOT_CHECKABLE`: target row exists, history denominator
    does not change.
11. Cross-side same-first-key: `AMBIGUOUS_FIRST_SIDE`, excluded from history.
12. Same-side same-first-key: unique first side and eligible.
13. `46'` as first GOAL: usable for first-side classification, not half
    classification.
14. Deterministic rebuild produces identical output.

## Availability audit plan

During future materialization, report by season and in total:

- total matches
- home available
- away available
- both available (pair available)
- either unavailable
- both unavailable
- usable team observations
- excluded `NOT_CHECKABLE`
- excluded `AMBIGUOUS_FIRST_SIDE`
- `NO_GOAL` observations

The 2020–2024 pair-availability counts must be frozen before any later model
evaluation. Availability counts must not be used to redefine this feature
family after the fact.

## Final gate

**READY_FOR_FIRST_SCORE_FEATURE_MATERIALIZATION**

The match classification, team observation semantics, exclusions,
same-date batching, season reset, denominator invariant, missingness rules,
target schema, validation contract, and required fixture tests are frozen.

Metrics: **NOT COMPUTED**. Model fitting: **NO**. Prediction, feature
selection, and parameter tuning: **NO**. 2025: **NOT USED**. First 80 of
2026/27: **NOT USED**. Future 300: **NOT USED**. External HTTP: **NO**.
