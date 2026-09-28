# Goal timing profile retrospective evaluation freeze specification

Status: **FROZEN_FOR_ONE_EVALUATION**.

This document freezes one prespecified retrospective rolling-OOF evaluation
of the ordinary-J1 goal timing profile family. It is a protocol document, not
an evaluation result. No T0 or T1 model was fit, no prediction was generated,
and no Accuracy, Log Loss, Brier score, coefficient, correlation, or other
target metric was newly calculated while preparing this specification.

## 1. Research question

Evaluate once whether the coherent six-value current-season prior goal timing
profile—first-goal, scoring, and conceding timing for home and away—improves
probability prediction when added to the known-good Elo-only baseline.

The result must not be used to select a subset, window, weighting, difference,
ratio, interaction, or another timing representation. This is one evaluation
of one frozen family.

## 2. Sources and data boundary

Source-of-truth documents and code:

- `docs/GOAL_TIMING_FEATURE_SPEC.md`
- `docs/GOAL_TIMING_FEATURE_DATASET.md`
- `src/features/goal_timing_profile.py`
- `src/modeling/player_workload_evaluation.py` for known-good Elo and model
  semantics

Frozen feature artifact:

`data/processed/features/2015_2024_j1_goal_timing_features.csv`

The target universe is exactly 3,208 ordinary-J1 matches from 2015–2024. No
new data source may be introduced. The following are prohibited:

- 2025, which is a spent test season;
- 2026/27 first 80 and future 300;
- Hyakunen, League Cup, Emperor's Cup, J2/J3, and AFC; and
- external HTTP.

## 3. Frozen folds and counts

Use exactly five expanding-season folds:

| Validation season | Training seasons | Train total | Train eligible | Validation total | Validation eligible |
|---:|:---|---:|---:|---:|---:|
| 2020 | 2015–2019 | 1,530 | 1,435 | 306 | 288 |
| 2021 | 2015–2020 | 1,836 | 1,723 | 380 | 356 |
| 2022 | 2015–2021 | 2,216 | 2,079 | 306 | 289 |
| 2023 | 2015–2022 | 2,522 | 2,368 | 306 | 286 |
| 2024 | 2015–2023 | 2,828 | 2,654 | 380 | 357 |

The underlying season pair-availability counts are:

| Season | Pair available |
|---:|---:|
| 2015 | 291 |
| 2016 | 286 |
| 2017 | 285 |
| 2018 | 286 |
| 2019 | 287 |
| 2020 | 288 |
| 2021 | 356 |
| 2022 | 289 |
| 2023 | 286 |
| 2024 | 357 |

The primary matched pooled validation count is exactly **1,576**. The
operational pooled validation count is exactly **1,678**. The future evaluator
must rederive and assert every count; it must not change filtering to make a
count agree. Validation on 2025 is prohibited.

## 4. Primary eligibility and artifact integrity

A row is primary-eligible only when both
`home_goal_timing_available` and `away_goal_timing_available` are true and all
six frozen candidate means are non-null, finite, nonnegative, and no greater
than the artifact's observed `minute_normalized` maximum:

```text
home_mean_first_goal_minute_normalized_prior
away_mean_first_goal_minute_normalized_prior
home_mean_scoring_minute_normalized_prior
away_mean_scoring_minute_normalized_prior
home_mean_conceding_minute_normalized_prior
away_mean_conceding_minute_normalized_prior
```

The evaluator must validate the frozen denominator/mean semantics before
deriving eligibility:

- an available team must have all three positive denominators and three valid
  means;
- a team with availability false must have at least one zero denominator;
- every zero denominator requires its corresponding mean to be null;
- every positive denominator requires a finite, range-valid mean; and
- no mean may be imputed.

One team may be available while its opponent is unavailable. That is a valid
artifact row but is primary-ineligible because pair availability requires both
sides. Likewise, an unavailable team may validly have one or two finite means
when the corresponding individual denominators are positive. “Partial state”
is a hard failure only when a team's availability, denominators, sums, and
means contradict their frozen semantics; valid pair asymmetry is not a hard
failure.

Availability flags, denominators, and sums are validation fields only and are
never model inputs.

## 5. Frozen Elo contract

Use the known-good implementation in
`src/modeling/player_workload_evaluation.py`, preferably by directly reusing
its `_add_elo` implementation. If direct reuse is impractical, exact
equivalence must be proven before any T1 result is observed.

The contract is:

- initial rating: `1500`;
- K-factor: `30`;
- home advantage: `175` in expected-score calculation only;
- feature: `elo_diff = home pre-match Elo - away pre-match Elo`;
- chronology: every ordinary-J1 match from 2015–2024;
- deterministic ordering: `match_date`, then `match_id`; and
- same-date conservative batch: obtain all pre-match Elo values on a date
  before updating any result from that date.

Do not use `load_training_dataset().elo_diff`, legacy K=20 / HA=0 Elo, or a
stored Elo column.

## 6. Frozen models

### T0: matched Elo baseline

Exactly one input:

```text
elo_diff
```

### T1: Elo plus goal timing profile

Exactly seven inputs, in this order:

```text
elo_diff
home_mean_first_goal_minute_normalized_prior
away_mean_first_goal_minute_normalized_prior
home_mean_scoring_minute_normalized_prior
away_mean_scoring_minute_normalized_prior
home_mean_conceding_minute_normalized_prior
away_mean_conceding_minute_normalized_prior
```

Do not add availability flags, denominators, sums, differences, ratios,
interactions, or any other value.

Both models use exactly:

```text
StandardScaler()
LogisticRegression(
    C=1.0,
    solver="lbfgs",
    max_iter=1000,
    random_state=0,
)
```

The scaler and Logistic Regression are fit on that fold's training rows only.
Validation rows cannot influence preprocessing or fitting.

Class semantics and probability order are fixed:

```text
0 = Away win
1 = Draw
2 = Home win
class order = [0, 1, 2]
```

## 7. Mandatory pre-T1 baseline gate

The future evaluator must complete these steps in order:

1. validate target/feature identity, source boundary, timing artifact
   invariants, eligibility, and all fold counts;
2. replay the known-good Elo chronology;
3. fit and evaluate each operational all-row `A_Y` baseline;
4. assert every mandatory `A_Y` reference below; and
5. only after all assertions pass, fit matched T0 and T1.

For validation season `Y`, `A_Y` is Elo-only Logistic trained on every
ordinary-J1 match from 2015 through `Y-1` and validated on every ordinary-J1
match in season `Y`.

Use `rtol=0` and `atol=1e-12` for all reference assertions.

| Fold | Known-good `A_Y` Log Loss |
|---:|---:|
| 2020 | 1.023119734659012 |
| 2021 | 1.0253437210487792 |
| 2022 | 1.0940186385371449 |
| 2023 | 1.0604285568595655 |
| 2024 | 1.079241181120235 |

Pooled `A_Y` references:

| Accuracy | Log Loss | Brier |
|---:|---:|---:|
| 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |

If any reference differs, stop with `BLOCKED_REFERENCE_MISMATCH`. T1 must not
be fit and no formal goal timing decision may be issued from that run.

## 8. No reused matched T0 reference

The goal timing pair-eligible match-ID set differs from the prior workload,
discipline, and first-score matched samples. Therefore no existing
`KNOWN_F0_POOLED`, W0, D0, or other matched metric reference may be reused for
T0.

No goal timing T0 predictive metric was calculated during freeze preparation.
After the `A_Y` gate passes in the formal evaluation, T0 will be calculated for
the first time as the official matched baseline. T0 and T1 must then use
exactly the same training match IDs, validation match IDs, and labels in every
fold. T0 is not required to match a prior lane's baseline metric.

## 9. Primary matched comparison

Within each fold, restrict both T0 and T1 to the same primary-eligible rows.
Report fold and pooled:

- Log Loss, primary;
- project multiclass Brier, secondary; and
- Accuracy, descriptive only.

Project Brier is:

```text
mean(sum((probability - one_hot_target) ** 2, axis=1))
```

Do not divide by three. Accuracy has no role in the lane decision.

## 10. Operational comparison

Operational T1 uses:

- the matched T1 probability when the validation row is goal-timing
  pair-eligible; and
- the same match's `A_Y` probability otherwise.

Align probabilities by exact unique `match_id`. Row-position fallback is
prohibited. Duplicate, missing, extra, incomplete, or null-aligned IDs are
hard failures.

Report Operational T1 versus `A_Y` separately. The operational comparison is
a deployment/sanity view and cannot alter the primary decision.

## 11. OOF pooling

For the primary comparison, concatenate all five validation target arrays and
their T0/T1 probability matrices, then calculate pooled metrics once on 1,576
rows. For the operational comparison, concatenate all validation targets and
their `A_Y`/Operational-T1 probabilities, then calculate pooled metrics once
on 1,678 rows.

A simple or weighted average of fold metrics is not a pooled metric.

## 12. Frozen decision rule

Only the primary matched comparison determines the lane decision. Let an
improved fold mean `T1 Log Loss < T0 Log Loss`.

`CONTINUE_GOAL_TIMING_LANE` requires all of:

- T1 pooled Log Loss < T0 pooled Log Loss;
- T1 pooled Brier < T0 pooled Brier; and
- T1 Log Loss improves in at least 3 of 5 folds.

`CLOSE_RETROSPECTIVE_LANE` requires all of:

- T1 pooled Log Loss >= T0 pooled Log Loss;
- T1 pooled Brier >= T0 pooled Brier; and
- T1 Log Loss does not improve in at least 3 of 5 folds.

Every other outcome is `INCONCLUSIVE_NO_TUNING`.

Accuracy and the operational comparison do not participate in this rule.

## 13. No adaptive follow-up

After this single evaluation, do not test within the lane:

- first-goal-only, scoring-only, conceding-only, or any subset of the six
  means;
- removal of first-goal, scoring, or conceding timing;
- home-only, away-only, differences, ratios, or interactions;
- last-N, rolling 3/5/10, EWMA, weighting changes, or conversion from
  event-weighting to match-weighting;
- changed minimum-history thresholds, imputation, smoothing, or season
  carry-over;
- half splits, timing buckets, first-score-side combinations, or score
  trajectories; or
- regularization tuning, threshold tuning, or nonlinear models.

A poor result closes the lane according to the frozen rule; it does not
authorize subset fishing.

## 14. Required future evaluator tests

The future evaluator must include at least these tests:

1. Logistic class/probability order is exactly `[0, 1, 2]`.
2. Project multiclass Brier for uniform three-class probabilities is `2/3`.
3. Known-good Elo replay matches exactly.
4. Legacy K=20 / HA=0 Elo and stored legacy `elo_diff` are not used.
5. Same-date Elo uses a conservative pre-match batch.
6. Primary eligibility requires both teams' availability.
7. An available pair requires all six means to be non-null, finite,
   nonnegative, and within the observed source-minute range.
8. An unavailable team may validly retain finite individual means, but the
   target pair remains primary-ineligible.
9. T0 and T1 training IDs, validation IDs, and labels are exactly equal.
10. Every frozen total, eligible, and pooled count is asserted.
11. `StandardScaler` and Logistic Regression fit training rows only.
12. Probability matrices are N x 3, finite, in `[0,1]`, and row sums are
    approximately one.
13. Operational fallback uses the same match's `A_Y` probability by
    `match_id`.
14. Duplicate, missing, extra, or misaligned prediction IDs hard-fail.
15. Pooled metrics use concatenated OOF targets and predictions, not fold
    metric averages.
16. Any `A_Y` reference mismatch yields `BLOCKED_REFERENCE_MISMATCH` before T1
    fitting or a formal decision.
17. The decision function is tested for continue, close, and inconclusive
    outcomes.

## 15. Future result document

The authorized future run creates `docs/GOAL_TIMING_EVALUATION.md`. It must
contain:

- a primary fold table with season, train total/eligible, validation
  total/eligible, T0/T1 Accuracy, Log Loss, Brier, and T1-minus-T0 deltas;
- primary pooled T0/T1 metrics and deltas;
- the number of Log Loss-improved folds out of five;
- operational pooled `A_Y`/Operational-T1 metrics and deltas;
- baseline sanity `PASS` or `FAIL`; and
- the exact frozen final decision.

No evaluator, evaluator test, result document, prediction artifact, or model
artifact is created by this freeze task.

## 16. Final gate and data discipline

**FROZEN_FOR_ONE_EVALUATION**

The research question, data boundary, folds, eligibility, Elo replay, model
inputs, pipeline, baseline gate, metrics, matched/operational comparisons,
pooling, decision rule, and no-follow-up boundary are fully frozen.

- Existing matched T0 reference reused: **NO**
- Metrics newly computed: **NO**
- T0 fitted: **NO**
- T1 fitted: **NO**
- Predictions generated: **NO**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen and Cups: **NOT USED**
- external HTTP: **NO**
