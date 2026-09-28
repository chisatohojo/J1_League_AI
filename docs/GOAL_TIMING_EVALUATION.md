# Goal timing profile retrospective evaluation

## Status

Baseline sanity: **PASS**.

Final decision: **`CLOSE_RETROSPECTIVE_LANE`**.

This is the single formal evaluation authorized by
`GOAL_TIMING_EVALUATION_FREEZE_SPEC.md`. The frozen feature family, folds,
eligibility, Elo replay, model inputs, pipeline, metrics, and decision rule
were not changed. No tuning or adaptive follow-up experiment was run.

## Baseline sanity

The evaluator directly reused the known-good ordinary-J1 Elo replay from
`src/modeling/player_workload_evaluation.py`: initial rating 1500, K=30, home
advantage 175 in expected-score calculation only, pre-match
`home Elo - away Elo`, and same-date conservative batching.

Operational `A_Y` fold Log Loss matched every frozen full-precision reference
with `rtol=0`, `atol=1e-12`:

| Fold | `A_Y` Log Loss |
|---:|---:|
| 2020 | 1.023119734659012 |
| 2021 | 1.0253437210487792 |
| 2022 | 1.0940186385371449 |
| 2023 | 1.0604285568595655 |
| 2024 | 1.079241181120235 |

Pooled `A_Y` Accuracy, Log Loss, and Brier also matched the frozen references.
All `A_Y` gates passed before either matched T0 or T1 was fit. Existing
matched T0 reference reused: **NO**.

## Primary matched comparison

T0 uses `elo_diff` only. T1 uses the same match IDs and labels and adds exactly
the frozen home/away prior first-goal, scoring, and conceding timing means.
Deltas are T1 minus T0; negative Log Loss or Brier is improvement.

| Fold | Train total | Train eligible | Validation total | Validation eligible | T0 Accuracy | T0 Log Loss | T0 Brier | T1 Accuracy | T1 Log Loss | T1 Brier | Delta Accuracy | Delta Log Loss | Delta Brier |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1,530 | 1,435 | 306 | 288 | 0.5069444444444444 | 1.0186020764756418 | 0.6079725538516875 | 0.5208333333333334 | 1.0124924950777598 | 0.6031615109027487 | +0.01388888888888895 | -0.00610958139788198 | -0.0048110429489387485 |
| 2021 | 1,836 | 1,723 | 380 | 356 | 0.5084269662921348 | 1.0193752463048396 | 0.6111055491142675 | 0.47752808988764045 | 1.034213605862548 | 0.6215040978564974 | -0.030898876404494346 | +0.014838359557708403 | +0.010398548742229896 |
| 2022 | 2,216 | 2,079 | 306 | 289 | 0.41522491349480967 | 1.0857533036413085 | 0.6555345922966446 | 0.41522491349480967 | 1.091527879615239 | 0.6593073344277995 | 0.0 | +0.005774575973930496 | +0.0037727421311549714 |
| 2023 | 2,522 | 2,368 | 306 | 286 | 0.46853146853146854 | 1.0614987524160189 | 0.6383938633429102 | 0.458041958041958 | 1.0642627235725035 | 0.6395086224282519 | -0.010489510489510523 | +0.0027639711564846348 | +0.0011147590853417544 |
| 2024 | 2,828 | 2,654 | 380 | 357 | 0.4565826330532213 | 1.0741842600754528 | 0.6498907586299487 | 0.44537815126050423 | 1.0706450621244021 | 0.6477049094693841 | -0.011204481792717047 | -0.003539197951050621 | -0.0021858491605646346 |

T1 improved Log Loss in **2/5 folds** (2020 and 2024).

### Primary pooled

Pooled metrics were calculated once from concatenated OOF targets and
probabilities, not from an average of fold metrics. The matched pooled sample
contains **1,576** matches.

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| T0 | 0.4720812182741117 | 1.0514658086927438 | 0.6324180291336672 |
| T1 | 0.4631979695431472 | 1.0544599401005161 | 0.6342867463969474 |
| T1 - T0 | -0.008883248730964521 | +0.0029941314077723824 | +0.0018687172632801952 |

T1 worsened both primary decision metrics, pooled Log Loss and pooled Brier.
Accuracy is descriptive only and was not used for the decision.

## Operational comparison

For pair-eligible rows, Operational T1 uses the exact match-ID-aligned T1
probability. For all other rows it uses the same match's `A_Y` probability.
The operational pooled sample contains all **1,678** validation matches.

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| `A_Y` | 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |
| Operational T1 | 0.45887961859356374 | 1.0591173592674321 | 0.6375141587421143 |
| Operational T1 - `A_Y` | -0.007747318235995282 | +0.003051957943668082 | +0.001781816812841841 |

The operational comparison is a deployment perspective only and did not
alter the primary decision.

## Frozen decision

**`CLOSE_RETROSPECTIVE_LANE`**

T1 pooled Log Loss was greater than or equal to T0, T1 pooled Brier was
greater than or equal to T0, and T1 Log Loss did not improve in 3/5 folds.
This satisfies the frozen close rule.

No first-goal-only, scoring-only, conceding-only, subset, removal, home-only,
away-only, difference, ratio, interaction, rolling/last-N, EWMA, weighting,
minimum-history, imputation, smoothing, season carry-over, half, bucket,
first-score combination, trajectory, regularization, threshold, or nonlinear
follow-up was run.

## Data discipline

- Existing matched T0 reference reused: **NO**
- Feature changes: **NO**
- Parameter changes: **NO**
- Tuning: **NOT RUN**
- Adaptive follow-up: **NOT RUN**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen, Cups, J2/J3, and AFC: **NOT USED**
- external HTTP: **NO**
