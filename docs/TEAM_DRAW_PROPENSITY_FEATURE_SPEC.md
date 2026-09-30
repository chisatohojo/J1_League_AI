# Ordinary-J1 team draw propensity feature specification

Status: **`READY_FOR_DRAW_PROPENSITY_FEATURE_MATERIALIZATION`**.

This document freezes the team draw-propensity family reviewed in
`TEAM_DRAW_PROPENSITY_FEASIBILITY.md`. It defines sources, chronology,
ownership, missingness, exact candidates, output schema, validation references,
and future materialization tests. It does not create a production builder,
feature CSV, model, prediction, predictive metric, or evaluation contract.

## 1. Frozen source scope

Sources of truth are:

- `data/processed/jleague/{season}_matches_probe.csv` for 2015–2024;
- `src/collect/matches.py` for completed-match and score/result validation;
- the existing TeamMaster exact identity contract;
- `src/features/form.py` for last-five state;
- `src/features/form_history.py` as evidence that form state can continue
  across supplied history segments; and
- `docs/TEAM_DRAW_PROPENSITY_FEASIBILITY.md` for the audited coverage
  references.

The frozen source universe is ordinary J1 only, seasons 2015 through 2024:

| Season | Targets | Team sides |
|---:|---:|---:|
| 2015 | 306 | 612 |
| 2016 | 306 | 612 |
| 2017 | 306 | 612 |
| 2018 | 306 | 612 |
| 2019 | 306 | 612 |
| 2020 | 306 | 612 |
| 2021 | 380 | 760 |
| 2022 | 306 | 612 |
| 2023 | 306 | 612 |
| 2024 | 380 | 760 |
| **Total** | **3,208** | **6,416** |

Every target has one stable `match_id`, calendar `match_date`, integer
`season`, two distinct exact TeamMaster IDs, nonnegative 90-minute scores, and
result class `0=Away win`, `1=Draw`, or `2=Home win`. Result must agree with
the scores. Only results from scoped matches on strictly earlier calendar
dates may affect a target.

Excluded completely are 2025, 2026/27, Hyakunen, League Cup, Emperor's Cup,
J2/J3, AFC, external HTTP, and inferred or fuzzy team identity. No excluded
match may enter either last-five or current-season state.

## 2. Ownership and reconciliation with existing form

### 2.1 Last-five source of truth

The future builder must **not implement a second last-five history state**.
It must call the existing `src/features/form.py::add_form_features` on the
validated, deterministically ordered 2015–2024 ordinary-J1 stream and directly
reuse:

```text
home_last5_draws
away_last5_draws
```

The feasibility audit established exact equality on all 3,208 targets between
these existing columns and the independently audited draw counts. This exact
reconciliation remains a materialization hard invariant.

Available-match counts must be derived from the same form output:

```text
home_last5_matches =
    home_last5_wins + home_last5_draws + home_last5_losses

away_last5_matches =
    away_last5_wins + away_last5_draws + away_last5_losses
```

The form points, wins, losses, and goal fields are inputs to reconciliation
only. They are not output columns or model candidates in this family. The
future dataset must not retain duplicate aliases for either existing draw
count, and a future model matrix must not add the same value under another
name.

`add_form_features` combines a team's home and away appearances and retains at
most five completed supplied matches. The future builder must pass only the
frozen ordinary-J1 stream. It must not use the broader operational
`load_form_history_with_ongoing` stream, because that route includes 2025,
Hyakunen, and 2026/27 data outside this specification.

### 2.2 State owned by this family

The only new history owned by the future draw-propensity builder is
**current-season strictly-prior draw state**. For each `(season, team_id)` it
tracks exactly:

```text
season_prior_draws
season_prior_matches
```

It increments matches after a completed scoped match and increments draws only
when `result == 1`. A season boundary creates a fresh zero state. It does not
copy, weight, or blend a previous season.

## 3. Strict-prior chronology

Normalize and validate the complete source universe, then sort it stably by:

```text
match_date, string match_id
```

For every calendar date `D`, the current-season state follows this exact
conservative batch:

1. read the state as of the start of `D` for every target on `D`;
2. emit every target row on `D`; and
3. only after all rows are emitted, apply all results from `D`.

Therefore target-own results, same-date peer results, kickoff ordering, and
input file ordering cannot affect pre-match values. A team appearing in more
than one scoped match on one calendar date is a hard failure.

Existing form state is also pre-match: it records a team's features before
appending that team's current result. Because the future builder must hard-fail
on a repeated `(match_date, team_id)`, no same-date peer can enter the same
team's last-five state. Deterministic date/ID ordering is still required for
stable output, but it never relaxes the date-batch information boundary.

## 4. Frozen last-five semantics

For each target side:

```text
last5_draws       = existing form last5_draws
last5_matches     = existing form last5_wins + last5_draws + last5_losses
last5_draw_rate   = last5_draws / last5_matches, if last5_matches > 0
last5_draw_rate   = null, otherwise
```

Last-five history continues across season boundaries and is keyed by exact
TeamMaster ID. All state begins empty at the 2015 left edge. No pre-2015,
J2/J3, Cup, AFC, or inferred history is loaded. A returning club retains its
earlier in-scope ordinary-J1 appearances; a newly appearing club begins with
the history actually available in the scoped prefix.

`last5_matches` is an integer in `[0,5]`. When it is zero, `last5_draws` is
zero and the rate is null. Missing matches are not padded as non-draws.

## 5. Frozen current-season semantics

For each target side:

```text
season_prior_draws
season_prior_matches
season_prior_draw_rate = season_prior_draws / season_prior_matches
```

The quotient exists only when `season_prior_matches > 0`. The structural
zero/unknown-rate state is exactly:

```text
season_prior_matches = 0
season_prior_draws = 0
season_prior_draw_rate = null
```

Counts reset to zero at every season boundary. They use all and only strictly
prior ordinary-J1 results from the target season, without a fixed window,
weighting, smoothing, or prior-season contribution.

## 6. Exactly four model candidates

The future draw-propensity model-candidate family is exactly these four ordered
columns:

```text
mean_draw_rate_last5
abs_draw_rate_diff_last5
mean_season_prior_draw_rate
abs_season_prior_draw_rate_diff
```

Their definitions are frozen:

```text
mean_draw_rate_last5 =
    (home_last5_draw_rate + away_last5_draw_rate) / 2

abs_draw_rate_diff_last5 =
    abs(home_last5_draw_rate - away_last5_draw_rate)

mean_season_prior_draw_rate =
    (home_season_prior_draw_rate + away_season_prior_draw_rate) / 2

abs_season_prior_draw_rate_diff =
    abs(home_season_prior_draw_rate - away_season_prior_draw_rate)
```

Each derived value is present if and only if both required side rates are
present. If either side rate is null, both the corresponding mean and absolute
difference are null. Derived values are not partially computed and are not
imputed.

These definitions are swap-invariant. Swapping the two team identities and
their complete side-level values must leave all four candidates exactly
unchanged. This representation follows the predeclared semantic hypothesis of
two teams' general draw tendencies; it was not selected from predictive
results.

The following must not be parallel model candidates:

- raw home/away draw rates, draw counts, or available counts;
- existing `home_last5_draws` or `away_last5_draws` separately;
- form wins, losses, points, goals, or alternative windows;
- H2H draw counts or exact-pair history; or
- any orientation-specific draw propensity.

The first 12 non-identity values in the dataset are audit/provenance fields.
Only the final four columns are model candidates.

## 7. Exact ordered 21-column schema

The future artifact has exactly one row per target and exactly these columns,
in this order:

```text
match_id
match_date
season
home_team_id
away_team_id
home_last5_draws
home_last5_matches
home_last5_draw_rate
away_last5_draws
away_last5_matches
away_last5_draw_rate
home_season_prior_draws
home_season_prior_matches
home_season_prior_draw_rate
away_season_prior_draws
away_season_prior_matches
away_season_prior_draw_rate
mean_draw_rate_last5
abs_draw_rate_diff_last5
mean_season_prior_draw_rate
abs_season_prior_draw_rate_diff
```

The names follow the existing repository's `home_last5_draws` /
`away_last5_draws` convention, so no naming exception is needed. `result`,
scores, form wins/losses/points, and any internal state key must not appear.

## 8. Logical types and invariants

Identity:

- `match_id`: non-null stable string, unique over all 3,208 rows;
- `match_date`: non-null ISO `YYYY-MM-DD`, with year equal to `season`;
- `season`: non-null integer in 2015–2024; and
- team IDs: non-null exact TeamMaster strings, distinct within each match.

Counts:

- non-null, nonnegative integers;
- `0 <= last5_draws <= last5_matches <= 5`; and
- `0 <= season_prior_draws <= season_prior_matches`.

Side rates:

- null if and only if the matching denominator is zero;
- otherwise finite floating-point values in `[0,1]`; and
- exactly equal in memory to draw count divided by denominator.

Derived candidates:

- null if and only if either required side rate is null;
- otherwise finite floating-point values in `[0,1]`; and
- exactly equal in memory to the frozen formulas in Section 6.

No row may be dropped for cold start or null candidates. Clipping, coercing an
invalid value, silently filling a null, or altering history to reproduce a
reference count is prohibited.

## 9. Frozen coverage references

These are validation references, not eligibility filters or performance
gates. The future builder must rederive and assert every value.

| Season | Targets | Season prior 0 | 1–4 | 5+ | Last-5 0 | 1–4 | 5 | Both full last-5 |
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

Coverage bins count team sides except `Targets` and `Both full last-5`. The
three season-prior bins sum to 6,416, as do the three last-five bins. Both
teams have a full last-five denominator on exactly 3,106 / 3,208 targets.

Expected null side rates follow directly: 184 current-season side rates and
30 last-five side rates. Materialization must report home/away null counts and
derived-candidate null counts but must not use them to filter rows.

## 10. Exact duplicate contract

For all 3,208 rows, joined strictly one-to-one by `match_id`:

```text
materialized home_last5_draws == existing form home_last5_draws
materialized away_last5_draws == existing form away_last5_draws
```

The required implementation is direct reuse of existing form output, not a
second rolling draw-state implementation. An optional independent calculation
may exist only as an audit assertion. It must not produce extra artifact or
model columns.

The materializer must also assert:

```text
home_last5_matches ==
    existing home_last5_wins + home_last5_draws + home_last5_losses

away_last5_matches ==
    existing away_last5_wins + away_last5_draws + away_last5_losses
```

## 11. Deterministic materialization and write safety

Identical inputs must produce identical rows, values, order, and serialized
bytes. Reversing input row order before normalization must not change output.
The canonical output order is `match_date`, then string `match_id`.

The future materializer must serialize one header plus exactly 3,208 data rows
as comma-delimited UTF-8 without BOM, CSV-minimal quoting, blank fields for
null, and LF (`\n`) line endings. Floating-point fields use one centrally
defined deterministic formatting path. A repeated in-memory build and a
temporary serialization must be byte-identical before publication. The final
file is written atomically and must not silently overwrite an existing file.
Its SHA-256 must be reported.

The planned output is:

```text
data/processed/features/2015_2024_j1_draw_propensity_features.csv
```

The generated artifact follows the repository's existing ignore policy. This
specification does not create it.

## 12. Prohibited variants and null handling

The builder, dataset, tests, later evaluation, and any response to later
results must not introduce:

- last 3, last 10, or another window;
- exponential or recency weighting;
- Laplace or Bayesian smoothing;
- league-average shrinkage;
- home-only or away-only propensity;
- current-season/previous-season blending;
- a performance-selected candidate subset; or
- an adaptive variant after formal results.

Materialization preserves nulls. It must not replace null with zero, league
mean, `1/3`, or any other fixed value. A later evaluation-freeze task must
predeclare exactly one training-fold-only preprocessing rule without reference
to validation outcomes. This document does not select that rule.

## 13. Required future materialization tests

The future implementation must include at least these **36** tests:

1. Source scope is ordinary J1 2015–2024 only.
2. Output has exactly 3,208 targets and 6,416 team sides.
3. Every frozen season target count is exact.
4. A duplicate target match ID hard-fails.
5. Team identity is validated against exact TeamMaster IDs.
6. An invalid result class hard-fails.
7. A result/score inconsistency hard-fails.
8. A self-match hard-fails.
9. One team appearing twice on one date hard-fails.
10. A target result is unavailable before that target is emitted.
11. Same-date peer results are unavailable before all date rows are emitted.
12. Current-season state resets at the season boundary.
13. Existing form last-five state continues across a season boundary.
14. The 2015 left edge starts with empty available-scope history.
15. A returning club retains earlier in-scope ordinary-J1 last-five history.
16. J2 and Cup matches cannot enter either history.
17. Zero current-season history emits `draws=0`, `matches=0`, `rate=null`.
18. Zero last-five history emits `draws=0`, `matches=0`, `rate=null`.
19. Last-five denominator is exactly the form W/D/L sum and never exceeds 5.
20. Every draw count is at most its matching denominator.
21. Every non-null rate is finite and in `[0,1]`.
22. Each side rate is null if and only if its denominator is zero.
23. Each derived pair propagates null if either required side rate is null.
24. Both pair means exactly match their frozen formulas.
25. Both absolute differences exactly match their frozen formulas.
26. Swapping complete home/away side values leaves all four candidates exact.
27. Both materialized last-five draw counts exactly reconcile to existing form
    for all 3,208 match IDs.
28. Current-season global and season-by-season coverage references are exact.
29. Last-five global and season-by-season coverage references are exact.
30. Both teams have full last-five history on exactly 3,106 targets.
31. Reversed input order produces identical normalized output.
32. Repeated build and temporary serialization are byte-identical.
33. Output has exactly the ordered 21-column schema.
34. Model candidates are exactly the ordered four columns in Section 6.
35. Output has no target-result or score field.
36. Builder imports and execution have no model-fitting, prediction,
    evaluation-metric, or target-association dependency.

Additional invariant tests are allowed. Additional feature variants are not.

## 14. Future materialization deliverables

The separately authorized materialization task is expected to create:

```text
src/features/draw_propensity.py
tests/test_draw_propensity.py
docs/TEAM_DRAW_PROPENSITY_FEATURE_DATASET.md
data/processed/features/2015_2024_j1_draw_propensity_features.csv
```

The dataset document and completion report must include scope, exact schema,
source/form reconciliation, chronology, reset/cross-season behavior,
cold-start/null behavior, season/global coverage, candidate distributions,
invariant failures, deterministic rebuild status, and artifact SHA-256. No
predictive metric may be calculated during materialization.

## 15. Future evaluation boundary

Evaluation is not frozen or run here. Only after materialization fixes the
dataset SHA-256 may a separate task freeze one evaluation contract. Its planned
boundary is:

- reproduce frozen Model A fresh as the reference;
- Challenger = Model A plus exactly the four candidates in Section 6;
- no candidate-subset comparison or alternative preprocessing;
- no 2025 or opened 2026/27 result;
- one formal evaluation only; and
- no adaptive tuning or variant after results.

That future document must uniquely freeze training-fold-only null preprocessing
before fitting. These planned constraints do not authorize evaluation now.

## 16. No predictive evaluation

This specification does not calculate or inspect Accuracy, Log Loss, Brier,
AUC, target-result correlation, mutual information, coefficients, feature
importance, or another target-label relationship. No model was fitted, no
prediction was generated, and no feature dataset was materialized. The 2025
spent test and opened 2026/27 lockbox were not used.

## 17. Final gate

**`READY_FOR_DRAW_PROPENSITY_FEATURE_MATERIALIZATION`**

The ordinary-J1 2015–2024 scope, existing-form ownership of last-five state,
new current-season-only state, season reset, cross-season continuation,
same-date batching, null semantics, four swap-invariant candidates, exact
21-column schema, coverage references, deterministic output, prohibited
variants, and 36 future tests are frozen.

- Model candidates: **EXACTLY FOUR**
- Output columns: **EXACTLY TWENTY-ONE**
- Required future materialization tests: **36**
- Last-five source of truth: **`src/features/form.py`**
- Predictive evaluation: **NOT RUN**
- Feature dataset: **NOT CREATED**
- Production builder/tests: **NOT CREATED**
- 2025: **NOT USED**
- 2026/27: **NOT USED**
- External HTTP: **NO**
