# Team Discipline Retrospective Evaluation

## Status

Final decision: `CLOSE_RETROSPECTIVE_LANE`.

This is the single valid evaluation specified by
`TEAM_DISCIPLINE_EVALUATION_FREEZE_SPEC.md`. The initial run was invalidated
before decision because it reused legacy `elo_diff` values with K=20 and no
home advantage. This replacement run uses the frozen known-good ordinary-J1
Elo replay: initial 1500, K=30, home advantage=175, and same-date conservative
batching.

No feature, parameter, eligibility rule, fold, metric, or decision rule was
changed. No tuning or adaptive follow-up was run.

## Frozen sample counts

| Fold | Train total | Train eligible | Validation total | Validation eligible |
|---:|---:|---:|---:|---:|
| 2020 | 1,530 | 1,485 | 306 | 297 |
| 2021 | 1,836 | 1,782 | 380 | 370 |
| 2022 | 2,216 | 2,152 | 306 | 297 |
| 2023 | 2,522 | 2,449 | 306 | 297 |
| 2024 | 2,828 | 2,746 | 380 | 370 |

Primary matched pooled validation contains 1,631 matches. Operational pooled
validation contains all 1,678 matches.

## Primary matched comparison

D0 uses `elo_diff`. D1 uses the same training and validation rows, adding the
four frozen prior discipline rates.

| Fold | D0 LL | D1 LL | Delta LL | D0 Brier | D1 Brier | Delta Brier | D0 Accuracy | D1 Accuracy | Delta Accuracy |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1.020055 | 1.020946 | +0.000891 | 0.609234 | 0.610100 | +0.000866 | 0.511785 | 0.488215 | -0.023569 |
| 2021 | 1.022857 | 1.035092 | +0.012235 | 0.613426 | 0.621315 | +0.007889 | 0.508108 | 0.489189 | -0.018919 |
| 2022 | 1.094034 | 1.098152 | +0.004118 | 0.661089 | 0.663779 | +0.002691 | 0.407407 | 0.414141 | +0.006734 |
| 2023 | 1.061026 | 1.061711 | +0.000685 | 0.638652 | 0.639089 | +0.000437 | 0.461279 | 0.461279 | +0.000000 |
| 2024 | 1.080965 | 1.085048 | +0.004083 | 0.654624 | 0.657242 | +0.002617 | 0.448649 | 0.448649 | +0.000000 |
| **Pooled** | **1.055440** | **1.060179** | **+0.004739** | **0.635281** | **0.638392** | **+0.003111** | **0.468424** | **0.461067** | **-0.007357** |

D1 improved Log Loss in 0/5 folds.

## Operational comparison

For each fold, A_Y is the frozen Elo-only model trained on all ordinary-J1
matches from 2015 through Y-1. Operational D1 uses D1 for pair-available rows
and the same match-ID-aligned A_Y probability for unavailable rows.

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| A_Y | 0.466627 | 1.056065 | 0.635732 |
| Operational D1 | 0.460072 | 1.060821 | 0.638782 |
| Operational D1 - A_Y | -0.006555 | +0.004755 | +0.003050 |

Fold A_Y Log Loss values were 1.023120, 1.025344, 1.094019, 1.060429,
and 1.079241 for 2020 through 2024.

## Baseline sanity

`PASS`.

- Operational A_Y pooled metrics exactly match the known-good baseline at
  full floating-point precision.
- Primary matched D0 exactly matches the known-good W0 pooled metrics:
  Accuracy 0.46842427958307786, Log Loss 1.0554404541978801, and Brier
  0.6352814612200155.
- Fold counts and eligible match-ID sets match the frozen audit.

## Frozen decision

`CLOSE_RETROSPECTIVE_LANE`.

D1 worsened pooled Log Loss and Brier, and did not improve Log Loss in any of
the five folds. Per the frozen rule, no yellow-only, red-only, weighting,
window, interaction, feature subset, regularization, threshold, or nonlinear
follow-up was run.

## Data discipline

- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen: **NOT USED**
- external HTTP: **NOT USED**
- feature/parameter changes: **NONE**
