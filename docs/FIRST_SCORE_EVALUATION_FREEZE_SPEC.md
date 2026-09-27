# First-score profile retrospective evaluation freeze specification

Status: **FROZEN_FOR_ONE_EVALUATION**.

This document freezes one prespecified retrospective rolling-OOF evaluation
of the ordinary-J1 first-score profile family. It is a protocol document, not
an evaluation result. No model was fit, no prediction was generated, and no
Accuracy, Log Loss, Brier score, coefficient, or other target metric was newly
calculated while preparing this specification.

## 1. Research question

Evaluate once whether current-season prior scored-first and conceded-first
tendencies improve probability prediction when added to the known-good
Elo-only baseline.

The result must not be used to choose a feature subset, window, weight,
interaction, timing feature, or model parameter within this lane. This is one
evaluation of one frozen family.

## 2. Sources and data boundary

Source-of-truth documents and code:

- `docs/FIRST_SCORE_FEATURE_SPEC.md`
- `docs/FIRST_SCORE_FEATURE_DATASET.md`
- `src/features/first_score_profile.py`
- `src/modeling/player_workload_evaluation.py` for known-good Elo and model
  semantics

Frozen feature artifact:

`data/processed/features/2015_2024_j1_first_score_features.csv`

The target universe is exactly 3,208 ordinary-J1 matches from 2015–2024.
No other new data source may be introduced. The following are prohibited:

- 2025, which is a spent test season
- 2026/27 first 80 and future 300
- Hyakunen, League Cup, Emperor's Cup, J2/J3, and AFC
- external HTTP

## 3. Frozen folds and counts

Use exactly five expanding-season folds:

| Validation season | Training seasons | Train total | Train eligible | Validation total | Validation eligible |
|---:|:---|---:|---:|---:|---:|
| 2020 | 2015–2019 | 1,530 | 1,485 | 306 | 297 |
| 2021 | 2015–2020 | 1,836 | 1,782 | 380 | 370 |
| 2022 | 2015–2021 | 2,216 | 2,152 | 306 | 297 |
| 2023 | 2015–2022 | 2,522 | 2,449 | 306 | 297 |
| 2024 | 2015–2023 | 2,828 | 2,746 | 380 | 370 |

The primary matched pooled validation count is exactly **1,631**. The
operational pooled validation count is exactly **1,678**. A future evaluator
must rederive and assert every fold count; it must not alter filtering to make
the counts agree.

Validation on 2025 is prohibited.

## 4. Primary eligibility

A row is primary-eligible only when both
`home_first_score_available` and `away_first_score_available` are true and all
four frozen model-candidate rates are non-null, finite, and in `[0,1]`:

```text
home_scored_first_rate_prior
away_scored_first_rate_prior
home_conceded_first_rate_prior
away_conceded_first_rate_prior
```

The evaluator must hard-fail on:

- one side available and the other unavailable;
- an available side with any missing, infinite, or out-of-range candidate
  rate;
- an unavailable side with any non-null candidate rate; or
- any other partial availability/null state.

Rows where both sides are unavailable and all four rates are null are valid
but ineligible for the primary matched comparison. Counts, availability flags,
and no-goal rates are audit fields only and are not model inputs.

### Eligible match-ID audit

A read-only artifact audit compared match-ID sets without fitting a model,
generating predictions, or calculating target metrics. For every fold, both
the eligible training set and eligible validation set are exactly identical
between first-score, player-workload, and team-discipline evaluations:

| Fold | Train IDs equal | Validation IDs equal |
|---:|:---:|:---:|
| 2020 | yes | yes |
| 2021 | yes | yes |
| 2022 | yes | yes |
| 2023 | yes | yes |
| 2024 | yes | yes |

This exact set equality permits the existing matched W0/D0 pooled reference to
serve as the strict F0 sanity reference in Section 10.

## 5. Frozen Elo contract

Use the known-good implementation in
`src/modeling/player_workload_evaluation.py`, preferably by directly reusing
its `_add_elo` implementation. If direct reuse is impractical, the replacement
must be proven exactly equivalent by fixture and full replay tests before any
F1 result is observed.

The contract is:

- initial rating: `1500`
- K-factor: `30`
- home advantage: `175`
- home advantage affects expected-score calculation only
- model feature: `elo_diff = home pre-match Elo - away pre-match Elo`
- chronology: all ordinary-J1 matches from 2015–2024
- deterministic ordering: `match_date`, then `match_id`
- same-date conservative batch: obtain every pre-match Elo on the date before
  updating any result from that date

Do not reuse legacy K=20 / HA=0 Elo, `load_training_dataset().elo_diff`, or
another stored Elo column.

## 6. Frozen models

### F0: matched Elo baseline

Exactly one input:

```text
elo_diff
```

### F1: Elo plus first-score profile

Exactly five inputs, in this order:

```text
elo_diff
home_scored_first_rate_prior
away_scored_first_rate_prior
home_conceded_first_rate_prior
away_conceded_first_rate_prior
```

Do not add availability flags, history counts, no-goal rates, home-away
differences, ratios, interactions, or any other value.

Both models use one pipeline:

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
Validation rows must never influence preprocessing or fitting.

Class semantics and probability order are fixed:

```text
0 = Away win
1 = Draw
2 = Home win
class order = [0, 1, 2]
```

## 7. Primary matched comparison

Within each fold, F0 and F1 must use exactly the same primary-eligible training
match IDs, validation match IDs, and labels. F0 is deliberately restricted to
the first-score-eligible sample so the only comparison is the addition of the
four first-score rates.

Report for each fold and for the pooled OOF sample:

- Log Loss, primary;
- project multiclass Brier, secondary; and
- Accuracy, descriptive only.

Project Brier is:

```text
mean(sum((probability - one_hot_target) ** 2, axis=1))
```

Do not divide by three. Accuracy has no role in the lane decision.

## 8. Operational comparison

For each validation season `Y`, define `A_Y` as Elo-only Logistic trained on
all ordinary-J1 rows from 2015 through `Y-1` and validated on every
ordinary-J1 row in season `Y`. It uses the same frozen Elo, pipeline, model
parameters, and class order.

Operational F1 uses:

- the matched F1 probability when the first-score pair is primary-eligible;
- the same match's `A_Y` probability when it is unavailable.

Align all substitutions by exact unique `match_id`. Row-position alignment is
prohibited. Differing ID sets, duplicate IDs, incomplete reindexing, or any
null aligned probability are hard failures.

Report Operational F1 versus `A_Y` separately from the primary comparison.
It is a deployment/sanity view and cannot modify the primary decision rule.

## 9. OOF pooling

For each comparison, concatenate all five validation target arrays and their
aligned probability matrices, then calculate pooled metrics once on the
concatenated data. A simple or weighted average of fold metrics is not the
pooled result.

The primary pooled arrays contain 1,631 rows for both F0 and F1. The
operational pooled arrays contain 1,678 rows for both `A_Y` and Operational
F1.

## 10. Mandatory baseline sanity gate

Baseline sanity must pass before F1 is fit or an F1 result is treated as an
official observation. The recommended execution order is:

1. validate inputs, identity, eligibility, fold counts, and match-ID sets;
2. replay known-good Elo and evaluate `A_Y`;
3. assert the operational baseline references below;
4. evaluate matched F0 and assert its pooled references below;
5. only after all assertions pass, fit and evaluate F1.

Use `rtol=0` and `atol=1e-12` for these reference assertions.

### Operational `A_Y` references

| Fold | Log Loss |
|---:|---:|
| 2020 | 1.023119734659012 |
| 2021 | 1.0253437210487792 |
| 2022 | 1.0940186385371449 |
| 2023 | 1.0604285568595655 |
| 2024 | 1.079241181120235 |

Pooled `A_Y`:

| Accuracy | Log Loss | Brier |
|---:|---:|---:|
| 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |

### Matched F0 references

Because the first-score eligible training and validation match-ID sets are
identical to the known-good workload/discipline sets, strict pooled references
are frozen as:

| Accuracy | Log Loss | Brier |
|---:|---:|---:|
| 0.46842427958307786 | 1.0554404541978801 | 0.6352814612200155 |

The previously reported fold F0 Log Loss values are `1.020055`, `1.022857`,
`1.094034`, `1.061026`, and `1.080965` for 2020–2024. These six-decimal display
values are diagnostic only and must not be used for a strict floating-point
assertion. The full-precision pooled values above are the mandatory matched F0
assertions.

If any mandatory reference differs, stop with
`BLOCKED_REFERENCE_MISMATCH`. Do not issue a formal first-score lane decision,
and do not inspect or report F1 as a valid challenger result from that run.

## 11. Frozen decision rule

Only the primary matched comparison determines the lane decision. Let an
improved fold mean `F1 Log Loss < F0 Log Loss` for that fold.

`CONTINUE_FIRST_SCORE_LANE` requires all of:

- F1 pooled Log Loss < F0 pooled Log Loss;
- F1 pooled Brier < F0 pooled Brier; and
- F1 Log Loss improves in at least 3 of 5 folds.

`CLOSE_RETROSPECTIVE_LANE` requires all of:

- F1 pooled Log Loss >= F0 pooled Log Loss;
- F1 pooled Brier >= F0 pooled Brier; and
- F1 Log Loss does not improve in at least 3 of 5 folds.

Every other outcome is `INCONCLUSIVE_NO_TUNING`.

Accuracy and the operational comparison do not participate in this rule.

## 12. No adaptive follow-up

After the single result is observed, do not test within this lane:

- scored-first-only or conceded-first-only subsets
- addition of no-goal rate
- rate differences, ratios, or interactions
- last-N, rolling 3/5/10, or EWMA variants
- home/away weighting or smoothing
- changed minimum-history thresholds or season carry-over
- first-goal minute, half split, or goal trajectory
- regularization or classification-threshold tuning
- nonlinear models

A poor result closes the lane according to the frozen rule; it does not
authorize feature-subset fishing.

## 13. Required future evaluator tests

The future evaluator must include at least these tests:

1. Logistic class/probability order is exactly `[0, 1, 2]`.
2. Project multiclass Brier for a uniform three-class probability is `2/3`.
3. Known-good Elo replay matches exactly.
4. Legacy K=20 / HA=0 Elo and stored legacy `elo_diff` are not used.
5. Same-date Elo uses a conservative pre-match batch.
6. Primary eligibility requires both sides and all four valid candidate rates;
   partial states hard-fail.
7. F0 and F1 matched training and validation match IDs are exactly equal.
8. Every frozen training, validation, eligible, and pooled count is asserted.
9. `StandardScaler` and the model are fit on training rows only.
10. Probability matrices are finite, in `[0,1]`, have three columns, and each
    row sums approximately to one.
11. Operational fallback uses the same match's `A_Y` probability by
    `match_id`.
12. Duplicate, missing, extra, or misaligned prediction IDs hard-fail.
13. Pooled metrics use concatenated OOF targets/predictions rather than fold
    metric averages.
14. Any mandatory baseline mismatch yields
    `BLOCKED_REFERENCE_MISMATCH` before a formal F1 decision.
15. The decision function is tested for continue, close, and inconclusive
    outcomes.

## 14. Future result document

The authorized future run creates `docs/FIRST_SCORE_EVALUATION.md`. It must
contain:

- a primary fold table with season, train total/eligible, validation
  total/eligible, F0 and F1 Accuracy/Log Loss/Brier, and F1-minus-F0 deltas;
- primary pooled F0/F1 metrics and deltas;
- the number of Log Loss-improved folds out of five;
- operational pooled `A_Y`/Operational-F1 metrics and deltas;
- baseline sanity `PASS` or `FAIL`; and
- the exact frozen final decision.

No result document, evaluator, or evaluator test is created by this freeze
task.

## 15. Final gate and data discipline

**FROZEN_FOR_ONE_EVALUATION**

The research question, data boundary, folds, eligibility, Elo replay, model
inputs, pipeline, metrics, matched/operational comparisons, sanity references,
decision rule, no-follow-up boundary, and future tests are fully frozen.

- Metrics newly computed: **NO**
- F1 fitted: **NO**
- Predictions generated: **NO**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen and other competitions: **NOT USED**
- external HTTP: **NO**
