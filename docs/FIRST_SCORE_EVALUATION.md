# First-score profile retrospective evaluation

## Status

Baseline sanity: **PASS**.

Final decision: **`CLOSE_RETROSPECTIVE_LANE`**.

This is the single formal evaluation authorized by
`FIRST_SCORE_EVALUATION_FREEZE_SPEC.md`. The frozen feature family, folds,
eligibility, Elo replay, model inputs, pipeline, metrics, and decision rule
were not changed. No tuning or adaptive follow-up experiment was run.

## Frozen sample counts

| Fold | Train total | Train eligible | Validation total | Validation eligible |
|---:|---:|---:|---:|---:|
| 2020 | 1,530 | 1,485 | 306 | 297 |
| 2021 | 1,836 | 1,782 | 380 | 370 |
| 2022 | 2,216 | 2,152 | 306 | 297 |
| 2023 | 2,522 | 2,449 | 306 | 297 |
| 2024 | 2,828 | 2,746 | 380 | 370 |

The primary matched pooled validation contains 1,631 matches. The
operational pooled validation contains all 1,678 matches.

## Baseline sanity

The evaluator directly reused the known-good ordinary-J1 Elo replay from
`src/modeling/player_workload_evaluation.py`: initial rating 1500, K=30, home
advantage 175 in expected-score calculation only, pre-match
`home Elo - away Elo`, and same-date conservative batching.

Operational `A_Y` fold Log Loss matched the frozen full-precision references:

| Fold | `A_Y` Log Loss |
|---:|---:|
| 2020 | 1.023119734659012 |
| 2021 | 1.0253437210487792 |
| 2022 | 1.0940186385371449 |
| 2023 | 1.0604285568595655 |
| 2024 | 1.079241181120235 |

Pooled `A_Y` and matched F0 also matched every frozen full-precision
reference with `rtol=0`, `atol=1e-12`. All baseline gates passed before F1 was
fit.

## Primary matched comparison

F0 uses `elo_diff` only. F1 uses the same rows and adds exactly the home/away
prior scored-first and conceded-first rates. Deltas are F1 minus F0; negative
Log Loss or Brier is improvement.

| Fold | F0 Accuracy | F0 Log Loss | F0 Brier | F1 Accuracy | F1 Log Loss | F1 Brier | Delta Accuracy | Delta Log Loss | Delta Brier |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 0.511785 | 1.020055 | 0.609234 | 0.508418 | 1.012928 | 0.603998 | -0.003367 | -0.007127 | -0.005236 |
| 2021 | 0.508108 | 1.022857 | 0.613426 | 0.494595 | 1.038252 | 0.623541 | -0.013514 | +0.015394 | +0.010115 |
| 2022 | 0.407407 | 1.094034 | 0.661089 | 0.410774 | 1.101361 | 0.664379 | +0.003367 | +0.007327 | +0.003290 |
| 2023 | 0.461279 | 1.061026 | 0.638652 | 0.464646 | 1.063265 | 0.639416 | +0.003367 | +0.002239 | +0.000764 |
| 2024 | 0.448649 | 1.080965 | 0.654624 | 0.443243 | 1.084797 | 0.657127 | -0.005405 | +0.003832 | +0.002502 |

F1 improved Log Loss in **1/5 folds** (2020 only).

### Primary pooled

Pooled metrics were computed from concatenated OOF targets and probabilities,
not by averaging fold metrics.

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| F0 | 0.46842427958307786 | 1.0554404541978801 | 0.6352814612200155 |
| F1 | 0.46474555487431024 | 1.0602461472368276 | 0.6379287313992348 |
| F1 - F0 | -0.0036787247087676223 | +0.004805693038947512 | +0.0026472701792192854 |

F1 worsened both primary decision metrics: pooled Log Loss and pooled Brier.
Accuracy is descriptive only and was not used for the decision.

## Operational comparison

For pair-available rows, Operational F1 uses the match-ID-aligned F1
probability. For unavailable rows it uses the same match's `A_Y` probability.

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| `A_Y` | 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |
| Operational F1 | 0.4636471990464839 | 1.060885605910642 | 0.6383318925561943 |
| Operational F1 - `A_Y` | -0.0029797377830751426 | +0.00482020458687793 | +0.002599550626921854 |

The operational comparison is a deployment perspective only and did not
alter the primary decision.

## Frozen decision

**`CLOSE_RETROSPECTIVE_LANE`**

F1 pooled Log Loss was greater than or equal to F0, F1 pooled Brier was
greater than or equal to F0, and F1 Log Loss did not improve in 4/5 folds.
This satisfies the frozen close rule.

No scored-first-only, conceded-first-only, no-goal, difference, ratio,
interaction, smoothing, minimum-history, rolling-window, EWMA, season
carry-over, timing, half, trajectory, regularization, threshold, or nonlinear
follow-up was run.

## Data discipline

- Feature changes: **NO**
- Parameter changes: **NO**
- Tuning: **NOT RUN**
- Adaptive follow-up: **NOT RUN**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen, Cups, J2/J3, and AFC: **NOT USED**
- external HTTP: **NO**
