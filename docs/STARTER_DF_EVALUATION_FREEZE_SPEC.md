# Previous-match starter DF count retrospective evaluation freeze specification

Status: **FROZEN_FOR_ONE_EVALUATION**.

This document freezes one prespecified retrospective rolling-OOF evaluation
of the ordinary-J1 previous-match starter DF count family. It is a protocol
document, not an evaluation result. No S0 or S1 model was fit, no prediction
was generated, and no Accuracy, Log Loss, Brier score, coefficient,
correlation, or other target metric was newly calculated while preparing this
specification.

## 1. Research question

Evaluate once whether adding exactly these two candidates to the known-good
Elo-only baseline improves probability prediction:

```text
home_previous_match_starter_df_count
away_previous_match_starter_df_count
```

The two candidates must be added together. The result must not be used to try
one side alone, a difference, ratio, interaction, MF/FW count, or another
starter-position representation. This is one evaluation of one frozen family.

## 2. Sources and data boundary

Sources of truth:

- `docs/STARTER_BENCH_STRUCTURE_FEATURE_SPEC.md`;
- `docs/STARTER_DF_FEATURE_DATASET.md`;
- `src/features/starter_df.py`; and
- `src/modeling/player_workload_evaluation.py` for known-good Elo and model
  semantics.

Frozen feature artifact:

```text
data/processed/features/2015_2024_j1_starter_df_features.csv
```

Frozen SHA-256:

```text
056963dd4707f122754d596ac6865721052cc3a31589a3a02941faca683aa674
```

The future evaluator must recompute and assert this exact digest before any
formal model fit. It must not rematerialize raw A5 inside the evaluator.

The target universe is exactly 3,208 ordinary-J1 matches from 2015–2024. No
new data source may be introduced. Explicitly excluded are 2025, 2026/27
first 80, future 300, Hyakunen, League Cup, Emperor's Cup, J2/J3, AFC, and
external HTTP.

## 3. Frozen feature semantics and schema

For a target team, the candidate is the number of explicit SFMS02 A5 starter
rows satisfying case-sensitive `position == "DF"` in that team's latest
strictly earlier ordinary-J1 match in the current season. It is a source-listed
A5 starter DF count, not a formation, back line, tactical role, or inferred
defensive shape.

The exact artifact schema, in order, is:

```text
match_id
match_date
season
home_team_id
away_team_id
home_starter_df_available
away_starter_df_available
home_previous_match_id
away_previous_match_id
home_previous_match_date
away_previous_match_date
home_previous_match_starter_df_count
away_previous_match_starter_df_count
```

Only the final two columns are model candidates. Availability flags, previous
match IDs, and previous match dates are validation fields only.

Before any formal fit, the future evaluator must assert:

- the exact feature artifact SHA-256;
- exactly 3,208 rows and unique `match_id`;
- exact equality with the target match-ID set;
- exact season, match date, home team ID, and away team ID for every
  `match_id`;
- the exact ordered 13-column schema; and
- keyed one-to-one identity joins by `match_id`, never row-position joins.

For each side independently:

```text
available == false
  => previous_match_id is null
  => previous_match_date is null
  => previous_match_starter_df_count is null

available == true
  => previous_match_id is non-null
  => previous_match_date is non-null
  => previous_match_date < target match_date
  => previous_match_starter_df_count is a non-null integer in 2–6
```

Home and away availability are independent. Imputation, clipping, coercion,
source repair, and row-position fallback are prohibited.

## 4. Frozen availability, folds, and counts

A row is primary-eligible if and only if both availability flags are true and
both candidates are non-null, finite integers in 2–6. A one-side-only
available row would be structurally valid but primary-ineligible.

The artifact must reproduce this availability before any formal fit:

| Season | Pair eligible | Total |
|---:|---:|---:|
| 2015 | 297 | 306 |
| 2016 | 297 | 306 |
| 2017 | 297 | 306 |
| 2018 | 297 | 306 |
| 2019 | 297 | 306 |
| 2020 | 297 | 306 |
| 2021 | 370 | 380 |
| 2022 | 297 | 306 |
| 2023 | 297 | 306 |
| 2024 | 370 | 380 |
| **Total** | **3,116** | **3,208** |

The frozen artifact has 92 pair-unavailable matches: home-only 0, away-only
0, and both unavailable 92. These values must be rederived from the artifact,
not assumed or produced by changing a filter.

Use exactly five expanding-season folds:

| Validation season | Training seasons | Train total | Train eligible | Validation total | Validation eligible |
|---:|:---|---:|---:|---:|---:|
| 2020 | 2015–2019 | 1,530 | 1,485 | 306 | 297 |
| 2021 | 2015–2020 | 1,836 | 1,782 | 380 | 370 |
| 2022 | 2015–2021 | 2,216 | 2,152 | 306 | 297 |
| 2023 | 2015–2022 | 2,522 | 2,449 | 306 | 297 |
| 2024 | 2015–2023 | 2,828 | 2,746 | 380 | 370 |

The primary matched pooled validation count is exactly **1,631**. The
operational pooled validation count is exactly **1,678**. The evaluator must
rederive and assert every total, eligible, and pooled count. Count agreement
must never be obtained by changing eligibility or scope.

## 5. Frozen Elo contract

Use the known-good implementation in
`src/modeling/player_workload_evaluation.py`, preferably by directly reusing
`_add_elo`. If direct reuse is impractical, exact equivalence must be proven
before any S1 result is observed.

The contract is:

- initial rating: `1500`;
- K-factor: `30`;
- home advantage: `175`, used only in expected-score calculation;
- feature: `elo_diff = home pre-match Elo - away pre-match Elo`;
- chronology: every ordinary-J1 match from 2015–2024;
- deterministic ordering: `match_date`, then string `match_id`; and
- same-date conservative batch: capture every pre-match Elo on a date before
  applying any result update from that date.

Do not use `load_training_dataset().elo_diff`, a stored `elo_diff`, or legacy
K=20 / HA=0 Elo.

## 6. Frozen models

### S0: matched Elo baseline

Exactly one input:

```text
elo_diff
```

### S1: Elo plus previous-match starter DF counts

Exactly three inputs, in this order:

```text
elo_diff
home_previous_match_starter_df_count
away_previous_match_starter_df_count
```

Do not add availability flags, previous match IDs or dates, GK/MF/FW counts,
the full position vector, difference, ratio, interaction, prior mean, rolling
statistic, EWMA, trend, change, bench/squad size, identity, continuity,
workload, substitution timing, goal timing, discipline, or first-score data.

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

The scaler and Logistic Regression must be fit only on that fold's training
rows. Validation rows cannot influence preprocessing or fitting. Parameter
tuning is prohibited.

Class semantics and probability order are fixed:

```text
0 = Away win
1 = Draw
2 = Home win
class order = [0, 1, 2]
```

## 7. Mandatory A_Y sanity gate

The future evaluator must complete these steps in order:

1. recompute and assert the feature artifact SHA-256;
2. validate target/feature identity;
3. validate exact schema, side availability, and candidate invariants;
4. rederive and assert every fold total, eligible, and pooled count;
5. replay the known-good Elo chronology;
6. fit and evaluate each operational all-row `A_Y` baseline; and
7. assert every frozen `A_Y` reference below.

Only after all seven steps pass may matched S0 or S1 be fit.

For validation season `Y`, `A_Y` is Elo-only Logistic trained on all
ordinary-J1 rows from 2015 through `Y-1` and validated on all ordinary-J1 rows
in season `Y`.

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

Any mismatch yields `BLOCKED_REFERENCE_MISMATCH`. In that run, the evaluator
must not report a formal matched S0 result, fit S1, calculate an S1 metric, or
issue a formal lane decision.

## 8. No reused matched S0

The official starter-DF matched S0 must be calculated anew on the frozen
starter-DF eligible match-ID sets after the `A_Y` gate passes. Existing
matched metrics from workload W0, discipline D0, first-score F0, goal-timing
T0, substitution-timing S0, or any other lane must not be reused.

Equality of availability counts is not evidence that match-ID sets are equal
and is never grounds for predictive baseline reuse. Even if a nonpredictive
identity audit establishes exact match-ID equality, the formal starter-DF S0
calculation must not be skipped.

```text
existing matched baseline reference reused = NO
```

## 9. Primary matched comparison

Within each fold, restrict both S0 and S1 to the same pair-eligible rows. S0
and S1 must have exactly the same training match IDs, validation match IDs,
and labels.

Report per fold and pooled:

- Log Loss, primary;
- project multiclass Brier, secondary; and
- Accuracy, descriptive only.

Project Brier is:

```text
mean(sum((probability - one_hot_target) ** 2, axis=1))
```

Do not divide by three. Define every delta as `S1 - S0`.

For primary pooling, concatenate all five validation target arrays and their
S0/S1 probability matrices, then calculate pooled metrics exactly once on
1,631 rows. A simple or weighted average of fold metrics is not a pooled
metric. Report S0 pooled, S1 pooled, each delta, and the number of folds out
of five in which `S1 Log Loss < S0 Log Loss`.

## 10. Operational comparison

Operational S1 covers every validation row:

- for a pair-eligible row, use that same match's matched S1 probability; and
- for a pair-unavailable row, use that same match's `A_Y` probability.

Align by exact unique `match_id`. Row-position fallback is prohibited.
Duplicate, missing, extra, incomplete, null, or misaligned prediction IDs are
hard failures.

Concatenate the five folds and calculate operational pooled metrics exactly
once on 1,678 rows. Report pooled `A_Y`, Operational S1, and `Operational S1
- A_Y` deltas. The operational comparison is descriptive and must not affect
the lane decision.

## 11. Probability validation

Every probability matrix must be N x 3, finite, within `[0, 1]`, and have
rows summing approximately to one. The class order is exactly `[0, 1, 2]`.
Any violation is a hard failure.

## 12. Frozen decision rule

Only the primary matched comparison determines the decision. An improved fold
means `S1 Log Loss < S0 Log Loss`.

`CONTINUE_STARTER_DF_LANE` requires all of:

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

After this single formal result, do not test within the starter-position lane:

- home-only, away-only, difference, ratio, interaction, or share;
- GK, MF, FW, the full position vector, or an MF/FW combination;
- previous-versus-current change, prior mean, rolling, last-N, EWMA, trend,
  or variance;
- bench position, bench size, or squad size;
- player identity, lineup continuity, or workload;
- regularization tuning, threshold tuning, or a nonlinear model; or
- any other result-driven feature variant.

A poor result does not authorize feature fishing.

## 14. Required future evaluator tests

The future evaluator must include at least these 30 tests:

1. Logistic class/probability order is exactly `[0, 1, 2]`.
2. Project multiclass Brier for uniform three-class probabilities is `2/3`.
3. Known-good Elo replay matches exactly.
4. Legacy/stored Elo is not used.
5. Same-date Elo uses a conservative pre-match batch.
6. A feature artifact SHA mismatch hard-fails before formal fitting.
7. The feature artifact has the exact ordered 13-column schema.
8. Target and feature match identity are exact by `match_id`.
9. An available side requires non-null prior ID, prior date, and count; a
   strictly earlier prior date; and an integer DF count in 2–6.
10. An unavailable side requires null prior ID, prior date, and count.
11. Primary eligibility requires both sides to be available.
12. A one-side-only available row is structurally valid but
    primary-ineligible.
13. Every frozen fold total and eligible count is asserted.
14. Primary pooled validation count is exactly 1,631.
15. Operational pooled validation count is exactly 1,678.
16. S0 and S1 training match IDs are exactly equal.
17. S0 and S1 validation match IDs are exactly equal.
18. S0 and S1 labels are exactly equal.
19. `StandardScaler` and Logistic Regression fit training rows only.
20. S0 input is exactly `elo_diff`.
21. S1 inputs are exactly `elo_diff`,
    `home_previous_match_starter_df_count`, and
    `away_previous_match_starter_df_count`.
22. Probability matrices are N x 3, finite, in `[0,1]`, and have valid row
    sums.
23. Operational fallback uses the same match's `A_Y` probability by
    `match_id`.
24. Duplicate, missing, extra, incomplete, null, or misaligned prediction IDs
    hard-fail.
25. Pooled metrics use concatenated OOF targets and probabilities rather than
    fold metric averages.
26. Any `A_Y` mismatch yields `BLOCKED_REFERENCE_MISMATCH`, prevents formal
    matched S0 reporting, prevents S1 fitting and metrics, and prevents a
    formal decision.
27. The decision function covers `CONTINUE_STARTER_DF_LANE`.
28. The decision function covers `CLOSE_RETROSPECTIVE_LANE`.
29. The decision function covers `INCONCLUSIVE_NO_TUNING`.
30. Existing matched baseline reference reuse remains `NO`.

Additional tests are allowed, but feature variants are not.

## 15. Future result document

The authorized future formal run creates `docs/STARTER_DF_EVALUATION.md`. It
must contain:

- baseline sanity `PASS` or `FAIL`;
- a primary fold table with validation season, train total/eligible,
  validation total/eligible, S0/S1 Accuracy, Log Loss, Brier, and S1-minus-S0
  deltas;
- primary pooled S0, S1, and deltas;
- S1 Log Loss-improved folds out of five;
- operational pooled `A_Y`, Operational S1, and deltas;
- `existing matched baseline reference reused = NO`; and
- the exact frozen final decision.

No evaluator, evaluator test, result document, prediction artifact, or model
artifact is created by this freeze task.

## 16. Final gate and data discipline

**FROZEN_FOR_ONE_EVALUATION**

The research question, artifact digest, 13-column validation, availability,
folds, known-good Elo replay, exact S0/S1 inputs, mandatory `A_Y` gate,
matched and operational comparisons, probability checks, OOF pooling,
decision rule, and no-follow-up boundary are fully frozen.

- Feature artifact SHA frozen: **YES**
- Existing matched baseline reference reused: **NO**
- Decision rule frozen: **YES**
- Required future evaluator tests frozen: **30**
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
