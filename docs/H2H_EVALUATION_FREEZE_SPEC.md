# Ordinary-J1 strict-prior exact-pair H2H evaluation freeze specification

Status: **FROZEN_FOR_ONE_H2H_EVALUATION**

This document freezes one retrospective rolling out-of-fold evaluation of the
materialized strict-prior exact-pair H2H family. It authorizes no evaluation
in this task. No model was fit, no prediction was generated, and no predictive
metric or target-result association was newly calculated.

Sources of truth are:

- `docs/H2H_FEATURE_SPEC.md`;
- `docs/H2H_FEATURE_DATASET.md`;
- `src/features/h2h.py`; and
- `src/modeling/player_workload_evaluation.py` for the known-good Elo replay,
  probability validation, metrics, scaler, and Logistic Regression pattern.

## 1. Research question and single comparison

The future formal run asks exactly one question: on ordinary J1, does adding
the three frozen H2H candidates simultaneously to the known-good Elo-only
baseline improve three-class probability prediction?

The H2H candidates are exactly:

```text
prior_h2h_match_count
prior_h2h_home_team_win_count
prior_h2h_draw_count
```

They form one coherent family and must be evaluated together once. No single-
candidate ablation, subset, transform, alternative H2H definition, or other
variant is authorized.

## 2. Frozen artifact and scope

The exact feature artifact is:

```text
data/processed/features/2015_2024_j1_h2h_features.csv
```

Required SHA-256:

```text
ab51fd674ee1665591e4b4b152a92f12ffd020211db3e541047c3066815784ff
```

The future evaluator must calculate SHA-256 from the actual file before any
formal fit and assert exact equality. A mismatch is a hard failure and no S1
fit may occur.

Scope is exactly 3,208 ordinary-J1 matches from 2015 through 2024. Excluded
are 2025, 2026/27 first 80, future 300, Hyakunen, League Cup, Emperor's Cup,
J2/J3, AFC, stadium, and external HTTP.

## 3. Artifact schema and identity validation

The artifact must have exactly these 11 columns in this order:

```text
match_id
match_date
season
home_team_id
away_team_id
h2h_available
previous_h2h_match_id
previous_h2h_match_date
prior_h2h_match_count
prior_h2h_home_team_win_count
prior_h2h_draw_count
```

Only the final three columns are model inputs. `h2h_available`,
`previous_h2h_match_id`, and `previous_h2h_match_date` are audit fields only.

Before formal fitting, the evaluator must assert:

- artifact SHA-256 is exact;
- artifact row count is exactly 3,208;
- `match_id` is unique on all 3,208 rows;
- schema and column order are exact;
- target and feature `match_id` sets are exactly equal;
- `season`, `match_date`, `home_team_id`, and `away_team_id` agree exactly by
  `match_id`; and
- the join is one-to-one and keyed only by `match_id`.

Row-position joins, missing IDs, extra IDs, duplicate IDs, and identity
mismatches are hard failures.

All three candidates must be non-null, integer, and greater than or equal to
zero. Every row must also satisfy:

```text
prior_h2h_home_team_win_count + prior_h2h_draw_count
    <= prior_h2h_match_count

derived target-away wins =
    prior_h2h_match_count
    - prior_h2h_home_team_win_count
    - prior_h2h_draw_count
```

The derived value must be a nonnegative integer. It is a validation value,
not a fourth candidate.

## 4. Structural-zero and audit validation

For every row where `prior_h2h_match_count == 0`, require:

```text
prior_h2h_home_team_win_count == 0
prior_h2h_draw_count == 0
h2h_available == false
previous_h2h_match_id is null
previous_h2h_match_date is null
```

For every row where `prior_h2h_match_count > 0`, require:

```text
h2h_available == true
previous_h2h_match_id is non-null
previous_h2h_match_date is non-null
previous_h2h_match_date < target match_date
```

Structural zeros are valid model inputs. There is no H2H availability or
missing-value eligibility filter: all 3,208 rows must be feature-valid and
remain in their applicable train or validation fold.

## 5. Frozen source references

The evaluator must rederive and exactly assert these availability counts from
the artifact. They validate the source; they never filter evaluation rows.

| Season | Available | Unavailable |
|---:|---:|---:|
| 2015 | 153 | 153 |
| 2016 | 258 | 48 |
| 2017 | 271 | 35 |
| 2018 | 285 | 21 |
| 2019 | 286 | 20 |
| 2020 | 288 | 18 |
| 2021 | 356 | 24 |
| 2022 | 289 | 17 |
| 2023 | 303 | 3 |
| 2024 | 343 | 37 |
| **Global** | **2,832** | **376** |

The global `prior_h2h_match_count` bins must be:

| Count bin | Rows |
|---:|---:|
| 0 | 376 |
| 1 | 376 |
| 2 | 265 |
| 3 | 265 |
| 4 | 224 |
| 5–9 | 860 |
| 10+ | 842 |
| **Total** | **3,208** |

## 6. Frozen expanding folds

Use exactly five expanding rolling folds:

| Validation season | Training seasons | Train n | Validation n |
|---:|---|---:|---:|
| 2020 | 2015–2019 | 1,530 | 306 |
| 2021 | 2015–2020 | 1,836 | 380 |
| 2022 | 2015–2021 | 2,216 | 306 |
| 2023 | 2015–2022 | 2,522 | 306 |
| 2024 | 2015–2023 | 2,828 | 380 |

The concatenated validation population is exactly 1,678 rows. Structural-zero
rows are ordinary rows in these counts. No matched subset and no fallback
evaluation are defined.

## 7. Known-good Elo replay

Prefer direct reuse of `_add_elo` from
`src/modeling/player_workload_evaluation.py`. Any equivalent implementation
must reproduce its exact contract:

- initial rating: `1500`;
- K-factor: `30`;
- home advantage: `175`, used only inside expected-score calculation;
- feature: pre-match home rating minus pre-match away rating;
- source stream: every ordinary-J1 match from 2015 through 2024;
- deterministic order: `match_date`, then string `match_id`; and
- same-date conservative batching: calculate every pre-match value for a date
  before applying any result from that date.

The future evaluator must not use a stored `elo_diff`,
`load_training_dataset().elo_diff`, the legacy K=20 configuration, or zero
home advantage.

## 8. Exact model inputs and pipeline

S0 inputs, in exact order:

```python
(
    "elo_diff",
)
```

S1 inputs, in exact order:

```python
(
    "elo_diff",
    "prior_h2h_match_count",
    "prior_h2h_home_team_win_count",
    "prior_h2h_draw_count",
)
```

S1 therefore has exactly four model inputs. The pipeline is exactly:

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

The scaler and Logistic Regression must fit only that fold's training rows.
Validation rows must not affect preprocessing or fitting. Parameter tuning is
prohibited.

Class semantics and probability order are fixed:

```text
0 = Away win
1 = Draw
2 = Home win
class order = [0, 1, 2]
```

## 9. Mandatory all-row A_Y gate

The future evaluator must execute these gates in this exact order:

1. calculate and assert the artifact SHA-256;
2. validate target/feature identity;
3. validate schema, structural-zero semantics, and candidate invariants;
4. rederive and assert frozen source distributions and fold counts;
5. replay known-good Elo;
6. fit and evaluate all-row S0=`A_Y` on all five folds; and
7. assert every frozen `A_Y` reference below.

For validation season `Y`, `A_Y` is the Elo-only Logistic pipeline trained on
every ordinary-J1 row from 2015 through `Y-1` and validated on every row in
season `Y`. The freshly fitted `A_Y` in this formal H2H run is the official S0;
no separate baseline result is copied or substituted.

Use `rtol=0` and `atol=1e-12` for every reference assertion.

| Validation season | `A_Y` Log Loss |
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

If any gate or reference differs, stop with
`BLOCKED_REFERENCE_MISMATCH`. In that run S1 must not be fit, no S1 metric may
be calculated or reported, and no formal lane decision may be issued.

```text
existing baseline prediction reused from another lane = NO
```

## 10. Primary S0/S1 comparison

Only after the complete `A_Y` gate passes may S1 be fit. Within every fold,
S0 and S1 must use exactly the same training match IDs, validation match IDs,
and labels. Every fold uses all rows.

Report per fold:

- Log Loss, primary;
- project multiclass Brier, secondary; and
- Accuracy, descriptive only.

Project Brier is exactly:

```text
mean(
    sum(
        (probability - one_hot_target) ** 2,
        axis=1
    )
)
```

Do not divide Brier by three. Every metric delta is `S1 - S0`.

For pooled metrics, concatenate the five validation target arrays and their
S0 and S1 probability matrices, then calculate each pooled metric exactly
once on 1,678 rows. A simple or weighted average of fold metrics is not the
pooled metric. Report pooled S0, pooled S1, their deltas, and the number of
folds out of five where `S1 Log Loss < S0 Log Loss`.

## 11. Mandatory Draw diagnostic

The Draw diagnostic is mandatory and descriptive. For every fold and for the
concatenated 1,678-row pooled population, report:

- actual label counts in Away/Draw/Home order;
- S0 argmax prediction counts in Away/Draw/Home order;
- S1 argmax prediction counts in Away/Draw/Home order;
- S0 mean predicted Draw probability;
- S1 mean predicted Draw probability; and
- Draw-probability delta `S1 - S0`.

Argmax predictions use probability columns in exact class order `[0, 1, 2]`.
Draw probability is the class-1 probability. Pooled diagnostics must be
derived from the concatenated labels and probabilities, not from averaging
fold diagnostics.

These values must not participate in the decision. Do not change a threshold,
class weight, calibration method, or model because of the diagnostic. Do not
add a Draw-specific model.

## 12. Probability validation

Every probability matrix must:

- have shape `N x 3`;
- contain only finite values;
- contain values within `[0, 1]`;
- have rows summing approximately to one; and
- use exact class order `[0, 1, 2]`.

The validation semantics should directly reuse the known-good
`_validate_probabilities` contract. Any invalid probability matrix is a hard
failure.

## 13. Frozen decision rule

Only the primary probability metrics determine the decision. An improved fold
means:

```text
S1 Log Loss < S0 Log Loss
```

Return `CONTINUE_H2H_LANE` if and only if all three conditions hold:

- S1 pooled Log Loss < S0 pooled Log Loss;
- S1 pooled Brier < S0 pooled Brier; and
- S1 Log Loss improves in at least 3 of 5 folds.

Return `CLOSE_RETROSPECTIVE_LANE` if and only if all three conditions hold:

- S1 pooled Log Loss >= S0 pooled Log Loss;
- S1 pooled Brier >= S0 pooled Brier; and
- S1 Log Loss does not improve in at least 3 of 5 folds.

Every other outcome is `INCONCLUSIVE_NO_TUNING`.

Accuracy, actual-class counts, argmax counts, mean Draw probability, and its
delta are prohibited from entering the decision.

## 14. No adaptive follow-up

After the single formal result, this H2H lane must not try:

- target-away wins;
- latest H2H result;
- draw rate, win rate, or points per match;
- same/reverse orientation, home-only, or away-only splits;
- recency or days since H2H;
- last 3, last 5, 3-year, or 5-year windows;
- EWMA, decay, general or draw-specific weights;
- ratios or interactions; or
- any result-driven parameter, threshold, feature, or model change.

Any future window or alternative-family research requires a separate
pre-frozen lane. This result cannot authorize an adaptive variant.

## 15. Required future evaluator tests

The future evaluator must implement at least these 36 tests:

1. Class/probability order is exactly `[0, 1, 2]`.
2. Project multiclass Brier for uniform three-class probabilities is `2/3`.
3. Known-good Elo replay is exact.
4. Stored or legacy Elo is prohibited.
5. Same-date Elo uses conservative batching.
6. A feature artifact SHA mismatch hard-fails before formal fitting.
7. The feature artifact has the exact ordered 11-column schema.
8. Target and feature identity are exact by `match_id`.
9. All three candidates are non-null, nonnegative integers.
10. Target-home wins plus draws do not exceed total.
11. Derived target-away wins are nonnegative integers.
12. Zero-history rows satisfy every structural-zero invariant.
13. Positive-history rows satisfy every availability/audit invariant.
14. Every frozen season availability count is exact.
15. Global available/unavailable counts are exactly 2,832/376.
16. Every frozen prior-count bin is exact.
17. Every fold train and validation count is exact.
18. Pooled validation count is exactly 1,678.
19. S0 and S1 training match IDs are exactly equal.
20. S0 and S1 validation match IDs are exactly equal.
21. S0 and S1 labels are exactly equal.
22. `StandardScaler` and Logistic Regression fit training rows only.
23. S0 input is exactly `elo_diff`.
24. S1 inputs are exactly the four frozen inputs in exact order.
25. All probability matrices satisfy the frozen validation contract.
26. Pooled metrics use concatenated OOF targets and probabilities, not fold
    metric averages.
27. Any `A_Y` mismatch blocks S1, S1 metrics, and the formal decision.
28. The `CONTINUE_H2H_LANE` decision branch is exact.
29. The `CLOSE_RETROSPECTIVE_LANE` decision branch is exact.
30. The `INCONCLUSIVE_NO_TUNING` decision branch is exact.
31. Actual class-count diagnostics are derived exactly from labels.
32. S0 argmax class-count diagnostics are exact.
33. S1 argmax class-count diagnostics are exact.
34. Mean Draw probability and `S1 - S0` delta are exact.
35. Draw diagnostics cannot enter the decision function.
36. Existing baseline prediction reused from another lane remains `NO`.

Additional validation tests are allowed. Feature variants are not.

## 16. Future result document

The future formal evaluator must create `docs/H2H_EVALUATION.md` containing at
least:

- baseline sanity `PASS` or `FAIL`;
- the five `A_Y` fold Log Loss values;
- a primary fold table containing season, train n, validation n, S0 and S1
  Accuracy/Log Loss/Brier, and every `S1 - S0` delta;
- pooled S0, S1, and deltas calculated once on `n=1,678`;
- S1 Log Loss improved folds out of five;
- per-fold and pooled actual Away/Draw/Home counts;
- per-fold and pooled S0 and S1 argmax Away/Draw/Home counts;
- per-fold and pooled S0/S1 mean Draw probabilities and their delta;
- the final decision;
- `existing baseline prediction reused from another lane = NO`;
- `feature changes = NO`;
- `parameter changes = NO`;
- `tuning = NOT RUN`; and
- `adaptive follow-up = NOT RUN`.

## 17. Freeze boundaries and final gate

This freeze task performed no evaluation implementation, evaluator tests,
model fit, prediction, predictive-metric calculation, feature selection,
parameter tuning, or target-result association calculation. The artifact was
inspected read-only only to confirm its identity and frozen header.

Data discipline:

- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen: **NOT USED**
- League Cup: **NOT USED**
- Emperor's Cup: **NOT USED**
- J2/J3: **NOT USED**
- AFC: **NOT USED**
- Stadium: **NOT USED**
- external HTTP: **NO**

The complete protocol is frozen for exactly one formal evaluation.

Final gate: **FROZEN_FOR_ONE_H2H_EVALUATION**
