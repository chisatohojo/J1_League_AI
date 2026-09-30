# Ordinary-J1 team draw propensity feasibility audit

Status: **`PROCEED_TO_DRAW_PROPENSITY_FEATURE_SPEC`**.

This is an offline, label-free feasibility audit of team-level draw tendency
from strictly prior ordinary-J1 results. It did not fit a model, generate a
prediction, calculate Accuracy / Log Loss / Brier, inspect association with the
target result, rank features, tune smoothing, or compare windows. No feature
CSV was created and no HTTP request was made.

## 1. Scope and source contract

The source is exactly `data/processed/jleague/{season}_matches_probe.csv` for
2015 through 2024, resolved through the existing TeamMaster. The scope has
3,208 unique completed ordinary-J1 matches and 6,416 team sides:

| Season | Matches |
|---:|---:|
| 2015–2020 | 306 each |
| 2021 | 380 |
| 2022–2023 | 306 each |
| 2024 | 380 |
| **Total** | **3,208** |

The retained source fields are stable `match_id`, calendar `match_date`,
`season`, exact `home_team_id` / `away_team_id`, and completed 90-minute result
class (`0=Away`, `1=Draw`, `2=Home`). Team/date collisions, duplicate match IDs,
invalid result classes, and season/date mismatches hard-fail.

Excluded are 2025, the opened 2026/27 interim lockbox, future fixtures,
Hyakunen, League Cup, Emperor's Cup, J2/J3, AFC, and all external sources.

The audit also reviewed the current Model A Elo contract, the H2H feature and
evaluation documents, Domestic Competitive Rest chronology, the processed
match schema, and the established 2015–2024 count rules. The known draw loss
diagnosis was not used to select a window or parameter.

## 2. Frozen audit family

Only these two unsmoothed histories were audited:

1. current-season prior matches and draws, reset at every season boundary; and
2. the most recent **five** ordinary-J1 matches for each team, continuing
   across season boundaries.

The five-match window was specified before this audit. No 3/5/10 comparison,
Laplace correction, Bayesian prior, league shrinkage, exponential weighting,
or performance-based alternative was calculated.

For each state, raw draw count, available-match count, and their raw quotient
are retained. If available count is zero, both counts are zero and the rate is
null. It is never zero-filled and is never replaced with a league average.

## 3. Chronology contract

Targets are ordered deterministically by `match_date`, then string
`match_id`. For every calendar date:

1. read the current-season and last-five states for every target on the date;
2. emit every target's audit values; and
3. only then apply all completed results from that date.

Thus a target's own result and every same-date peer result are unavailable.
Kickoff time and input row order do not relax this boundary. Rebuilding from
reversed input produced an identical frame. Observed target-result uses,
same-date chronology violations, duplicate team/date appearances, and future
result uses were all zero.

Current-season state is keyed by `(season, team_id)`, which makes reset
explicit. Last-five state is keyed only by exact `team_id`, because its source
meaning is the team's recent ordinary-J1 appearances rather than a season
aggregate. A season break does not erase an observed recent match. This rule
was selected from source semantics, not performance.

History starts empty at the 2015 left edge. A promoted or newly appearing club
has an available count below five until enough scoped ordinary-J1 appearances
exist. A returning club retains its earlier in-scope ordinary-J1 appearances;
no J2/J3 or pre-2015 match is inferred. Availability therefore describes the
available scoped prefix, not the club's complete football history.

## 4. Coverage

Counts below are team-side counts except `Targets` and `Both full`. Bins are
mutually exclusive. `Both full` is the number of targets for which both teams
have five available prior ordinary-J1 matches.

| Season | Targets | Season prior 0 | 1–4 | 5+ | Last-5 0 | 1–4 | 5 | Both full |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 18 | 72 | 522 | 18 | 72 | 522 | 261 |
| 2016 | 306 | 18 | 72 | 522 | 3 | 12 | 597 | 293 |
| 2017 | 306 | 18 | 72 | 522 | 2 | 8 | 602 | 297 |
| 2018 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2019 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2020 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2021 | 380 | 20 | 80 | 660 | 1 | 4 | 755 | 375 |
| 2022 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2023 | 306 | 18 | 72 | 522 | 0 | 0 | 612 | 306 |
| 2024 | 380 | 20 | 80 | 660 | 2 | 8 | 750 | 370 |
| **Global** | **3,208** | **184** | **736** | **5,496** | **30** | **120** | **6,266** | **3,106** |

Current-season cold start is 184 / 6,416 team sides: the first appearance of
each participating club in each season. Available-scope last-five cold start is
30 / 6,416 sides. Full last-five history exists for 6,266 / 6,416 sides and for
both teams on 3,106 / 3,208 targets.

Rate nulls reconcile exactly to zero denominators: current-season rates have
184 null team sides (92 home, 92 away); last-five rates have 30 (14 home, 16
away). Non-null non-finite values, rates outside `[0,1]`, and draw counts above
their denominators are all zero.

## 5. Label-free distributions

| Rate | Available | Null | Exact unique values | Dominant value (count) | Population variance |
|---|---:|---:|---:|---:|---:|
| Home last-5 | 3,194 | 14 | 10 | 0.2 (1,291) | 0.036516 |
| Away last-5 | 3,192 | 16 | 10 | 0.2 (1,263) | 0.037953 |
| Home season prior | 3,116 | 92 | 194 | 0.0 (217) | 0.023743 |
| Away season prior | 3,116 | 92 | 199 | 0.0 (224) | 0.023785 |

Combined home/away last-five rates have 6,386 available values, 30 nulls, 10
unique values, and variance 0.037235. The exact observed values are:

```text
0, 0.2, 0.25, 1/3, 0.4, 0.5, 0.6, 2/3, 0.8, 1.0
```

With a full five-match denominator, the support is exactly
`0 / 0.2 / 0.4 / 0.6 / 0.8 / 1.0`. Values `0.25`, `1/3`, `0.5`, and `2/3`
come from the explicitly retained denominators below five; they are not padded
five-match observations. Current-season rates have 217 unique values across
both sides because their denominator grows through the season.

Every count and rate is non-constant. Home/away last-five draw counts each
take six values; season-prior draw counts each take 16 values. The family is
therefore non-degenerate without reference to target outcomes.

## 6. Deterministic redundancy

The following algebra is intentional and must remain explicit in the audit
contract:

```text
draw_rate = draws / matches_available       when matches_available > 0
draw_rate = null                            when matches_available == 0
```

There are no exact duplicate columns within the proposed 12 side-level value
columns. None is exactly equal to frozen Model A's pre-match `elo_diff` over
the 3,208 rows. This is a deterministic equality check only; no correlation,
mutual information, coefficient, importance, or model metric was calculated.

The repository's older generic form implementation already exposes
`home_last5_draws` and `away_last5_draws`. On this ordinary-J1 scope they are
exactly equal to `home_draws_last_5` and `away_draws_last_5`. A future builder
should reuse or explicitly reconcile that logic rather than create two model
columns with the same value. The new contract adds the necessary denominator,
nullable raw rate, current-season state, and explicit same-date/cold-start
rules.

H2H draw history is not a duplicate of this family. H2H conditions on one
exact unordered team pair; this audit summarizes each team's overall prior
ordinary-J1 draw tendency against all opponents.

## 7. Proposed feature contract

A future feature dataset should retain this exact ordered base schema:

```text
match_id
match_date
season
home_team_id
away_team_id

home_draws_last_5
home_matches_last_5
home_draw_rate_last_5
away_draws_last_5
away_matches_last_5
away_draw_rate_last_5

home_season_prior_draws
home_season_prior_matches
home_season_prior_draw_rate
away_season_prior_draws
away_season_prior_matches
away_season_prior_draw_rate
```

Identity fields are non-null strings except `season`, which is integer.
Counts are non-null integers. Rates are nullable finite floating-point values
in `[0,1]`, null if and only if their matching count is zero. Target result is
not an output field. Missing values must not be silently filled or shrunk.

For the later feature specification, the minimal swap-invariant derived
candidate set proposed for review is:

```text
mean_draw_rate_last_5
abs_draw_rate_diff_last_5
mean_season_prior_draw_rate
abs_season_prior_draw_rate_diff
```

Each is null unless both component rates are available. The raw home/away
rates and counts remain provenance/audit fields; they should not also be added
as parallel model candidates because mean and absolute difference are their
deterministic transforms. No predictive claim is made for any of these four.
On rows where both sides are available, all four proposed derived fields are
non-degenerate. The next specification must freeze their exact naming,
missingness handling, and model-candidate status before any evaluation.

## 8. Verdict and next gate

Verdict: **`PROCEED_TO_DRAW_PROPENSITY_FEATURE_SPEC`**.

The exact TeamMaster identity, 3,208-target source universe, strict-prior
chronology, season reset, cross-season last-five rule, zero-history behavior,
coverage, finite-rate invariants, and same-date boundary are implementable and
auditable. The family is non-degenerate and can be constructed without the
target result. Predictive performance is deliberately not a verdict condition.

The next gate is a separate feature specification that freezes the exact
schema, derived candidate set, null handling, deterministic reconciliation
with existing form counts, and a one-time future evaluation protocol. This
audit does **not** authorize materialization, model fitting, 2025 evaluation,
or 2026/27 evaluation.

Audit implementation: `src/features/draw_propensity_audit.py`. It constructs
only an in-memory audit frame; it has no writer or production feature-builder
entry point.
