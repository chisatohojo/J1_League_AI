# Ordinary-J1 team draw propensity evaluation freeze specification

Status: **`FROZEN_FOR_ONE_DRAW_PROPENSITY_EVALUATION`**.

This document freezes one retrospective rolling out-of-fold evaluation of the
materialized strictly-prior team draw-propensity family. It authorizes no
evaluation in this task. No evaluator was implemented, no model was fit, no
prediction was generated, and no predictive metric, target-result association,
coefficient, or feature importance was calculated.

Sources of truth are:

- `docs/TEAM_DRAW_PROPENSITY_FEATURE_SPEC.md`;
- `docs/TEAM_DRAW_PROPENSITY_FEATURE_DATASET.md`;
- `src/features/draw_propensity.py`;
- `docs/H2H_EVALUATION_FREEZE_SPEC.md`;
- `docs/TEAM_DISCIPLINE_EVALUATION_FREEZE_SPEC.md`;
- `docs/PLAYER_WORKLOAD_EVALUATION_FREEZE_SPEC.md`; and
- the known-good Elo/model evaluation implementation used by the H2H and
  workload lanes.

## 1. Frozen research question

The future formal run asks exactly one question: does adding all four frozen
Team Draw Propensity candidates together to Elo-only Logistic improve
three-class ordinary-J1 probability prediction?

The four candidates are one coherent family and must be evaluated together
once. Subset evaluation and ablation are prohibited.

## 2. Frozen artifact and source scope

The required feature artifact is:

```text
data/processed/features/2015_2024_j1_draw_propensity_features.csv
```

Required SHA-256:

```text
97b33269a11b62f94dbd4b83924b97cc1cb1cb250ae0eb636ca5d8ccc6ba36a5
```

Before any formal fit, the future evaluator must calculate the SHA-256 of the
actual file and assert exact equality. A mismatch is a hard failure. Feature
regeneration is prohibited.

The source scope is exactly 3,208 ordinary-J1 matches from 2015 through 2024.
Excluded completely are 2025, 2026/27, Hyakunen, League Cup, Emperor's Cup,
J2/J3, AFC, and external HTTP.

## 3. Artifact schema and identity validation

The artifact must contain exactly 3,208 rows, exactly 21 columns, and exactly
3,208 unique `match_id` values. Its exact ordered schema is:

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

The evaluator must join the artifact to the ordinary-J1 target source by
`match_id`, one-to-one, and assert exact identity for:

```text
match_id
match_date
season
home_team_id
away_team_id
```

Row-position joins, duplicate IDs, missing or extra IDs, and identity
mismatches are hard failures.

## 4. Frozen candidates and eligibility

The challenger candidates are exactly these four columns in this order:

```text
mean_draw_rate_last5
abs_draw_rate_diff_last5
mean_season_prior_draw_rate
abs_season_prior_draw_rate_diff
```

No other artifact field may enter a model. In particular, raw side rates, raw
draw counts, available counts, existing form columns, availability flags if
later added, H2H, and form wins/losses/points are audit-only or out of scope.

A row is primary-eligible if and only if all four candidates are non-null,
finite, and in the closed interval `[0,1]`. A partial-null row is primary-
ineligible and is not a hard failure. Any non-null non-finite or out-of-range
candidate value is a hard failure.

There is no imputation. Zero fill, `1/3` fill, league mean, median,
training-fold mean, `SimpleImputer`, missing indicators, smoothing, and
shrinkage are prohibited. Eligibility must be derived without using the target
result.

The read-only freeze audit found zero invalid non-null candidate values. The
season-level eligibility counts are:

| Season | Total | Eligible | Ineligible |
|---:|---:|---:|---:|
| 2015 | 306 | 297 | 9 |
| 2016 | 306 | 297 | 9 |
| 2017 | 306 | 297 | 9 |
| 2018 | 306 | 297 | 9 |
| 2019 | 306 | 297 | 9 |
| 2020 | 306 | 297 | 9 |
| 2021 | 380 | 370 | 10 |
| 2022 | 306 | 297 | 9 |
| 2023 | 306 | 297 | 9 |
| 2024 | 380 | 370 | 10 |
| **Total** | **3,208** | **3,114** | **94** |

## 5. Frozen folds and primary populations

Use exactly five expanding folds. The evaluator must rederive and assert all
of these counts before formal fitting:

| Validation | Training | Total train | Eligible train | Total validation | Eligible validation | Ineligible validation |
|---:|---|---:|---:|---:|---:|---:|
| 2020 | 2015-2019 | 1,530 | 1,485 | 306 | 297 | 9 |
| 2021 | 2015-2020 | 1,836 | 1,782 | 380 | 370 | 10 |
| 2022 | 2015-2021 | 2,216 | 2,152 | 306 | 297 | 9 |
| 2023 | 2015-2022 | 2,522 | 2,449 | 306 | 297 | 9 |
| 2024 | 2015-2023 | 2,828 | 2,746 | 380 | 370 | 10 |

The full pooled validation population is 1,678 rows. The primary pooled
eligible validation population is exactly 1,631 rows, leaving 47 primary-
ineligible validation rows.

## 6. Frozen Elo contract

Use the known-good ordinary-J1 Elo replay over the complete 2015-2024
chronology:

```text
initial Elo = 1500
K = 30
home advantage = 175
elo_diff = pre-match home Elo - pre-match away Elo
```

Home advantage is used only in the expected-score calculation. Elo is replayed
through every scoped ordinary-J1 match even when that row is primary-
ineligible. For every calendar date, calculate all pre-match Elo values first
and only then apply that date's results. Stored or legacy Elo values are
prohibited.

## 7. Frozen DP0 and DP1 models

DP0 is the matched Elo-only baseline with this exact input tuple:

```python
(
    "elo_diff",
)
```

DP1 is Elo plus the complete Draw Propensity family with this exact ordered
input tuple:

```python
(
    "elo_diff",
    "mean_draw_rate_last5",
    "abs_draw_rate_diff_last5",
    "mean_season_prior_draw_rate",
    "abs_season_prior_draw_rate_diff",
)
```

Within every fold, DP0 and DP1 must use exactly identical primary-eligible
training match IDs, validation match IDs, and labels.

Both use exactly:

```python
Pipeline(
    [
        ("scaler", StandardScaler()),
        (
            "logistic",
            LogisticRegression(
                C=1.0,
                solver="lbfgs",
                max_iter=1000,
                random_state=0,
            ),
        ),
    ]
)
```

The scaler and Logistic Regression are fit on the fold's training rows only.
Class semantics and probability-column order are exactly `0=Away`, `1=Draw`,
`2=Home`, ordered `[0,1,2]`. Class weights, calibration, threshold tuning,
parameter changes, nonlinear models, interactions, and polynomial features are
prohibited.

## 8. Mandatory all-row A_Y baseline gate

Before DP1 can be fit, the future evaluator must freshly reproduce the
fold-specific all-row Elo-only baseline `A_Y`. For validation season `Y`, fit
on all ordinary-J1 rows from 2015 through `Y-1` and validate on all ordinary-
J1 rows in `Y`.

The exact expected Log Loss values are:

```text
2020  1.023119734659012
2021  1.0253437210487792
2022  1.0940186385371449
2023  1.0604285568595655
2024  1.079241181120235
```

Use the same numeric tolerance as the H2H freeze:

```text
rtol = 0
atol = 1e-12
```

If any fold mismatches, the outcome is
`BLOCKED_REFERENCE_MISMATCH`: DP1 must not be fit, DP1 metrics and the formal
decision must not be produced, and no result document may be written. Each
`A_Y` baseline and prediction must be generated fresh. Record:

```text
existing baseline prediction reused = NO
```

## 9. Primary matched evaluation

For each fold, train and validate DP0 and DP1 only on the exact matched
primary-eligible populations in Section 5. Join the `elo_diff` produced from
the complete chronology by `match_id`.

Report these metrics per fold and pooled:

- primary: multiclass Log Loss;
- secondary: project multiclass Brier,
  `mean(sum((p - one_hot)^2, axis=1))`; and
- descriptive: Accuracy.

Pooled metrics must be calculated once after concatenating all validation
predictions. Averaging fold metrics is prohibited. Report every delta as
`DP1 - DP0`; a negative Log Loss or Brier delta is an improvement.

## 10. Operational full-validation diagnostic

For each validation season, retain all ordinary-J1 rows. The operational
baseline is the fresh all-row `A_Y`. The operational challenger is:

```text
if primary eligible:
    use DP1 prediction
else:
    use A_Y prediction
```

Align probabilities only by `match_id`. The validation totals are 306, 380,
306, 306, and 380 for 2020 through 2024, with 1,678 pooled rows. Compare the
operational challenger with `A_Y` using Log Loss, Brier, and Accuracy by fold
and pooled. This is diagnostic only and must not affect the formal decision.

## 11. Probability and draw diagnostics

Every produced probability matrix must have the exact target IDs, exactly
three columns, finite values in `[0,1]`, rows summing approximately to one,
and class order `[0,1,2]`. Duplicate, missing, or extra IDs are hard failures.

The result may report these draw-specific diagnostics per fold and pooled:

- actual Away/Draw/Home counts;
- DP0 and DP1 argmax Away/Draw/Home counts;
- DP0 and DP1 mean Draw probability; and
- `DP1 - DP0` mean Draw probability.

Equivalent operational draw diagnostics are optional. Draw thresholds, draw
recall as a decision criterion, candidate selection, and calibration tuning
are prohibited. No draw diagnostic affects the decision.

## 12. Frozen decision rule

Decide only from the primary matched DP1-versus-DP0 comparison.

Return **`CONTINUE_DRAW_PROPENSITY_LANE`** if and only if all three hold:

1. pooled DP1 Log Loss is lower than pooled DP0 Log Loss;
2. pooled DP1 Brier is lower than pooled DP0 Brier; and
3. DP1 Log Loss improves in at least three of five folds.

Return **`CLOSE_RETROSPECTIVE_LANE`** if and only if all three hold:

1. pooled DP1 Log Loss is greater than or equal to pooled DP0 Log Loss;
2. pooled DP1 Brier is greater than or equal to pooled DP0 Brier; and
3. DP1 Log Loss improves in fewer than three of five folds.

Otherwise return **`INCONCLUSIVE_NO_TUNING`**. Accuracy and the operational
comparison are never decision criteria.

## 13. No adaptive follow-up

After the formal result, this lane must not try candidate subsets, last-five-
only or season-only models, alternative windows, home/away raw rates,
smoothing, imputation, missing indicators, interactions, draw calibration,
class weighting, `C` tuning, thresholds, or Elo parameter changes. A new
hypothesis requires a separate research cycle.

## 14. Mandatory future evaluator gates

Before a formal run, the future evaluator implementation must cover at least
these 42 offline/synthetic checks:

1. artifact SHA exact;
2. exact schema;
3. exact 3,208 rows;
4. unique match IDs;
5. exact target identity join;
6. four candidates exact order;
7. eligibility definition exact;
8. invalid non-null candidate hard fail;
9. no imputation;
10. exact fold totals;
11. frozen eligible train counts;
12. frozen eligible validation counts;
13. pooled eligible validation count;
14. Elo full chronology;
15. same-date Elo batching;
16. DP0/DP1 matched train IDs exact;
17. DP0/DP1 matched validation IDs exact;
18. labels exact;
19. DP0 input exact;
20. DP1 inputs exact;
21. scaler training-only;
22. Logistic Regression training-only;
23. class order exact;
24. probability validation;
25. pooled metric concatenation;
26. `A_Y` 2020 exact gate;
27. `A_Y` 2021 exact gate;
28. `A_Y` 2022 exact gate;
29. `A_Y` 2023 exact gate;
30. `A_Y` 2024 exact gate;
31. any `A_Y` failure blocks DP1;
32. operational fallback exact;
33. operational `match_id` alignment;
34. decision CONTINUE branch exact;
35. decision CLOSE branch exact;
36. decision INCONCLUSIVE branch exact;
37. draw diagnostics do not affect decision;
38. existing baseline prediction reused = NO;
39. 2025 inaccessible;
40. 2026/27 inaccessible;
41. no candidate variants; and
42. formal execution requires explicit one-shot confirmation.

Additional tests are permitted if they do not broaden or alter the protocol.

## 15. Formal execution safety

The future evaluator's default mode must be preflight only. A formal run must
require both explicit flags:

```text
--formal --confirm-one-shot
```

Without both flags, the DP1 formal evaluation must not run and the result
document must not be written. The evaluator implementation task itself must
not execute the formal evaluation.

## 16. Future result artifact

The future formal run must create:

```text
docs/TEAM_DRAW_PROPENSITY_EVALUATION.md
```

It must report:

- artifact SHA gate PASS/FAIL;
- `A_Y` baseline sanity PASS/FAIL and all five exact Log Loss values;
- frozen eligible training and validation counts;
- per-fold DP0/DP1 Accuracy, Log Loss, and Brier;
- all DP1-minus-DP0 deltas;
- pooled matched metrics and improved-Log-Loss folds out of five;
- operational `A_Y` versus fallback-DP1 fold and pooled metrics;
- actual class counts and DP0/DP1 argmax class counts;
- mean Draw probabilities;
- the final decision;
- `feature changes = NO`;
- `parameter changes = NO`;
- `tuning = NOT RUN`;
- `adaptive follow-up = NOT RUN`; and
- `existing baseline prediction reused = NO`.

## 17. Freeze evidence and final gate

This docs-only freeze used the artifact read-only to verify its SHA, exact
schema, row count, unique IDs, ordinary-J1 target identity, candidate ranges,
and eligibility counts. It did not access 2025 or 2026/27 and did not use the
target result to determine eligibility.

The protocol is frozen at:

**`FROZEN_FOR_ONE_DRAW_PROPENSITY_EVALUATION`**
