# Substitution timing profile retrospective evaluation freeze specification

Status: **FROZEN_FOR_ONE_EVALUATION**.

This document freezes one prespecified retrospective rolling-OOF evaluation
of the ordinary-J1 team substitution timing profile family. It is a protocol
document, not an evaluation result. No S0 or S1 model was fit, no prediction
was generated, and no Accuracy, Log Loss, Brier score, coefficient,
correlation, or other target metric was newly calculated while preparing this
specification.

## 1. Research question

Evaluate once whether the coherent two-value current-season prior team
substitution timing profile improves probability prediction when added to the
known-good Elo-only baseline.

The exact family is the home and away prior mean normalized substitution
minute. The result must not be used to select a side, transform, adjacent
substitution statistic, window, or alternative timing representation. This is
one evaluation of one frozen family.

## 2. Sources and data boundary

Sources of truth:

- `docs/SUBSTITUTION_TIMING_FEATURE_SPEC.md`
- `docs/SUBSTITUTION_TIMING_FEATURE_DATASET.md`
- `src/features/substitution_timing.py`
- `src/modeling/player_workload_evaluation.py` for known-good Elo and model
  semantics

Frozen feature artifact:

`data/processed/features/2015_2024_j1_substitution_timing_features.csv`

Frozen feature artifact SHA-256:

```text
898c7d53ed429d36920fd67b218333d837f5d2604c99c3556e47584721b9161f
```

The future evaluator must recompute and assert this digest before any formal
model fit. A mismatch is a hard failure.

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
| 2020 | 2015–2019 | 1,530 | 1,485 | 306 | 297 |
| 2021 | 2015–2020 | 1,836 | 1,782 | 380 | 370 |
| 2022 | 2015–2021 | 2,216 | 2,152 | 306 | 297 |
| 2023 | 2015–2022 | 2,522 | 2,449 | 306 | 297 |
| 2024 | 2015–2023 | 2,828 | 2,746 | 380 | 370 |

The underlying season pair-availability counts are:

| Season | Pair available |
|---:|---:|
| 2015 | 297 |
| 2016 | 297 |
| 2017 | 297 |
| 2018 | 297 |
| 2019 | 297 |
| 2020 | 297 |
| 2021 | 370 |
| 2022 | 297 |
| 2023 | 297 |
| 2024 | 370 |

The primary matched pooled validation count is exactly **1,631**. The
operational pooled validation count is exactly **1,678**. The future evaluator
must rederive and assert every count from the artifact. Filtering must not be
changed to make a count agree. Validation on 2025 is prohibited.

## 4. Artifact integrity and primary eligibility

Before any model fit, validate each side independently:

```text
prior_substitution_events == 0
  => prior_substitution_minute_normalized_sum == 0
  => mean_substitution_minute_normalized_prior is null
  => substitution_timing_available == false

prior_substitution_events > 0
  => mean == sum / denominator
  => mean is finite and 3 <= mean <= 90
  => substitution_timing_available == true
```

Denominators must be nonnegative integers and sums finite and nonnegative.
Imputation is prohibited.

A row is primary-eligible only when both
`home_substitution_timing_available` and
`away_substitution_timing_available` are true and both frozen candidate means
are non-null, finite, and within 3–90:

```text
home_mean_substitution_minute_normalized_prior
away_mean_substitution_minute_normalized_prior
```

Home and away availability are independent. One side may validly be
available while the other is unavailable; that row is a valid artifact row
but is primary-ineligible. Only a contradiction among a side's flag,
denominator, sum, and mean is a hard failure.

Availability flags, denominators, and sums are validation fields only and are
never model inputs.

## 5. Frozen Elo contract

Use the known-good implementation in
`src/modeling/player_workload_evaluation.py`, preferably by directly reusing
its `_add_elo` implementation. If direct reuse is impractical, exact
equivalence must be proven before any S1 result is observed.

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

### S0: matched Elo baseline

Exactly one input:

```text
elo_diff
```

### S1: Elo plus substitution timing profile

Exactly three inputs, in this order:

```text
elo_diff
home_mean_substitution_minute_normalized_prior
away_mean_substitution_minute_normalized_prior
```

Do not add availability flags, denominators, sums, substitution counts,
first/last timing, differences, ratios, interactions, or any other value.

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
Validation rows cannot influence preprocessing or fitting. Parameter tuning
is prohibited.

Class semantics and probability order are fixed:

```text
0 = Away win
1 = Draw
2 = Home win
class order = [0, 1, 2]
```

## 7. Mandatory pre-S0/S1 baseline gate

The future evaluator must complete these steps in order:

1. recompute and assert the feature artifact SHA-256;
2. validate target/feature identity and source boundary;
3. validate feature invariants and primary eligibility;
4. rederive and assert every fold total, eligible, and pooled count;
5. replay the known-good Elo chronology;
6. fit and evaluate each operational all-row `A_Y` baseline; and
7. assert every mandatory `A_Y` reference below.

Only after all seven steps pass may matched S0 or S1 be fit.

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

If any reference differs, stop with `BLOCKED_REFERENCE_MISMATCH`. Matched S0
must not be reported, S1 must not be fit, no S1 metric may be produced, and no
formal substitution-timing decision may be issued from that run.

## 8. No reused matched baseline reference

Pair-count equality with another feature lane does not prove match-ID set
equality. No workload W0, discipline D0, first-score F0, goal-timing T0, or
other matched predictive metric may be reused as an S0 sanity reference.

No substitution-timing S0 predictive metric was calculated during freeze
preparation. After the `A_Y` gate passes in the formal evaluation, S0 must be
calculated for the first time on the official substitution-timing matched
sample. Even if a future nonpredictive identity check proves equivalence with
another lane's match-ID set, formal S0 calculation must not be omitted.

Existing matched baseline reference reused: **NO**.

## 9. Primary matched comparison

Within each fold, restrict both S0 and S1 to the same primary-eligible rows.
S0 and S1 must use exactly the same training match IDs, validation match IDs,
and labels.

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

Operational S1 uses:

- the matched S1 probability when the validation row is substitution-timing
  pair-eligible; and
- the same match's `A_Y` probability otherwise.

Align probabilities by exact unique `match_id`. Row-position fallback is
prohibited. Duplicate, missing, extra, incomplete, null, or misaligned IDs are
hard failures.

Report Operational S1 versus `A_Y` separately. The operational comparison is
a deployment/sanity view and cannot alter the primary decision.

## 11. OOF pooling

For the primary comparison, concatenate all five validation target arrays and
their S0/S1 probability matrices, then calculate pooled metrics once on 1,631
rows. For the operational comparison, concatenate all validation targets and
their `A_Y`/Operational-S1 probabilities, then calculate pooled metrics once
on 1,678 rows.

A simple or weighted average of fold metrics is not a pooled metric.

## 12. Frozen decision rule

Only the primary matched comparison determines the lane decision. Let an
improved fold mean `S1 Log Loss < S0 Log Loss`.

`CONTINUE_SUBSTITUTION_TIMING_LANE` requires all of:

- S1 pooled Log Loss < S0 pooled Log Loss;
- S1 pooled Brier < S0 pooled Brier; and
- S1 Log Loss improves in at least 3 of 5 folds.

`CLOSE_RETROSPECTIVE_LANE` requires all of:

- S1 pooled Log Loss >= S0 pooled Log Loss;
- S1 pooled Brier >= S0 pooled Brier; and
- S1 Log Loss does not improve in at least 3 of 5 folds.

Every other outcome is `INCONCLUSIVE_NO_TUNING`.

Accuracy and the operational comparison do not participate in this rule.

## 13. No adaptive follow-up

After this single evaluation, do not test within the lane:

- home-only, away-only, home-away difference, ratio, or interaction;
- substitution count or its combination with timing;
- first or last substitution timing;
- zero-SUB rate or same-time multi-substitution frequency;
- window count, halftime, tactical/injury intent, or player-specific
  tendency;
- score-state substitution or combination with goal timing;
- changed minimum-history thresholds, imputation, smoothing, or season
  carry-over;
- rolling 3/5/10, last-N, EWMA, or regime normalization; or
- regularization tuning, threshold tuning, or nonlinear models.

A poor result closes the lane according to the frozen rule; it does not
authorize variant fishing.

## 14. Required future evaluator tests

The future evaluator must include at least these 19 tests:

1. Logistic class/probability order is exactly `[0, 1, 2]`.
2. Project multiclass Brier for uniform three-class probabilities is `2/3`.
3. Known-good Elo replay matches exactly.
4. Legacy K=20 / HA=0 Elo and stored legacy `elo_diff` are not used.
5. Same-date Elo uses a conservative pre-match batch.
6. A feature artifact SHA mismatch hard-fails before formal model fitting.
7. Primary eligibility requires both sides' availability.
8. An available side requires positive denominator, finite range-valid mean,
   and mean equal to sum/denominator.
9. An unavailable side requires zero denominator, zero sum, and null mean.
10. A one-side-only available row is valid but primary-ineligible.
11. S0 and S1 training IDs, validation IDs, and labels are exactly equal.
12. Every frozen total, eligible, and pooled count is asserted.
13. `StandardScaler` and Logistic Regression fit training rows only.
14. Probability matrices are N x 3, finite, in `[0,1]`, and row sums are
    approximately one.
15. Operational fallback uses the same match's `A_Y` probability by
    `match_id`.
16. Duplicate, missing, extra, incomplete, or misaligned prediction IDs
    hard-fail.
17. Pooled metrics use concatenated OOF targets and predictions, not fold
    metric averages.
18. Any `A_Y` reference mismatch yields `BLOCKED_REFERENCE_MISMATCH` before
    matched S0 reporting, S1 fitting, or a formal decision.
19. The decision function is tested for continue, close, and inconclusive
    outcomes.

Feature variants must not be added by the evaluator or its tests.

## 15. Future result document

The authorized future run creates
`docs/SUBSTITUTION_TIMING_EVALUATION.md`. It must contain:

- baseline sanity `PASS` or `FAIL`;
- a primary fold table with season, train total/eligible, validation
  total/eligible, S0/S1 Accuracy, Log Loss, Brier, and S1-minus-S0 deltas;
- primary pooled S0/S1 metrics and deltas;
- the number of Log Loss-improved folds out of five;
- operational pooled `A_Y`/Operational-S1 metrics and deltas;
- `existing matched baseline reference reused = NO`; and
- the exact frozen final decision.

No evaluator, evaluator test, result document, prediction artifact, or model
artifact is created by this freeze task.

## 16. Final gate and data discipline

**FROZEN_FOR_ONE_EVALUATION**

The research question, artifact digest, data boundary, folds, eligibility,
Elo replay, model inputs, pipeline, baseline gate, metrics,
matched/operational comparisons, pooling, decision rule, and no-follow-up
boundary are fully frozen.

- Feature artifact SHA frozen: **YES**
- Existing matched baseline reference reused: **NO**
- Decision rule frozen: **YES**
- Required evaluator tests frozen: **19**
- Metrics newly computed: **NO**
- S0 fitted: **NO**
- S1 fitted: **NO**
- Predictions generated: **NO**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen and Cups: **NOT USED**
- J2/J3 and AFC: **NOT USED**
- external HTTP: **NO**
