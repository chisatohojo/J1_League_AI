# Substitution timing profile retrospective evaluation

## Status

Baseline sanity: **PASS**.

Final decision: **`CLOSE_RETROSPECTIVE_LANE`**.

This is the single formal evaluation authorized by
`SUBSTITUTION_TIMING_EVALUATION_FREEZE_SPEC.md`. The frozen feature family,
artifact digest, folds, eligibility, Elo replay, model inputs, pipeline,
metrics, and decision rule were not changed. No tuning or adaptive follow-up
experiment was run.

## Artifact and baseline sanity

The feature artifact SHA-256 was recomputed before model fitting and matched:

```text
898c7d53ed429d36920fd67b218333d837f5d2604c99c3556e47584721b9161f
```

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
All gates passed before either matched S0 or S1 was fit. Existing matched
baseline reference reused: **NO**.

## Primary matched comparison

S0 uses `elo_diff` only. S1 uses the same match IDs and labels and adds exactly
the frozen home and away prior mean normalized substitution minute. Deltas are
S1 minus S0; negative Log Loss or Brier is improvement.

| Fold | Train total | Train eligible | Validation total | Validation eligible | S0 Accuracy | S0 Log Loss | S0 Brier | S1 Accuracy | S1 Log Loss | S1 Brier | Delta Accuracy | Delta Log Loss | Delta Brier |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1,530 | 1,485 | 306 | 297 | 0.5117845117845118 | 1.0200551893806826 | 0.6092343529578926 | 0.5050505050505051 | 1.021327913097188 | 0.6106693510341484 | -0.006734006734006703 | +0.0012727237165053307 | +0.0014349980762558001 |
| 2021 | 1,836 | 1,782 | 380 | 370 | 0.5081081081081081 | 1.0228574687359941 | 0.6134256329675887 | 0.5 | 1.0250924788344504 | 0.6150071805368624 | -0.008108108108108136 | +0.0022350100984562804 | +0.0015815475692737557 |
| 2022 | 2,216 | 2,152 | 306 | 297 | 0.4074074074074074 | 1.0940335755002084 | 0.6610886571658463 | 0.4074074074074074 | 1.0953912586580525 | 0.6618719622322041 | 0.0 | +0.001357683157844125 | +0.00078330506635782 |
| 2023 | 2,522 | 2,449 | 306 | 297 | 0.4612794612794613 | 1.0610261822973375 | 0.6386518824398223 | 0.45454545454545453 | 1.0600308198470365 | 0.6381681886143028 | -0.006734006734006759 | -0.0009953624503009628 | -0.00048369382551949336 |
| 2024 | 2,828 | 2,746 | 380 | 370 | 0.4486486486486487 | 1.0809648055472723 | 0.6546244215147561 | 0.4540540540540541 | 1.0811658994045195 | 0.654628118049817 | +0.005405405405405406 | +0.0002010938572472032 | +0.000003696535060937478 |

S1 improved Log Loss in **1/5 folds** (2023 only).

### Primary pooled

Pooled metrics were calculated once from concatenated OOF targets and
probabilities, not from an average of fold metrics. The matched pooled sample
contains **1,631** matches.

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| S0 | 0.46842427958307786 | 1.0554404541978801 | 0.6352814612200155 |
| S1 | 0.4653586756591048 | 1.0562908322834426 | 0.6359569482131366 |
| S1 - S0 | -0.003065603923973037 | +0.000850378085562431 | +0.0006754869931211438 |

S1 worsened both primary decision metrics, pooled Log Loss and pooled Brier.
Accuracy is descriptive only and was not used for the decision.

## Operational comparison

For pair-eligible rows, Operational S1 uses the exact match-ID-aligned S1
probability. For all other rows it uses the same match's `A_Y` probability.
The operational pooled sample contains all **1,678** validation matches.

| Model | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|
| `A_Y` | 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |
| Operational S1 | 0.4642431466030989 | 1.0570410774905163 | 0.636415338100577 |
| Operational S1 - `A_Y` | -0.002383790226460125 | +0.0009756761667523151 | +0.0006829961713046284 |

The operational comparison is a deployment perspective only and did not
alter the primary decision.

## Frozen decision

**`CLOSE_RETROSPECTIVE_LANE`**

S1 pooled Log Loss was greater than or equal to S0, S1 pooled Brier was
greater than or equal to S0, and S1 Log Loss did not improve in 4/5 folds.
This satisfies the frozen close rule.

No home-only, away-only, difference, ratio, interaction, count, first/last
timing, zero-SUB rate, same-time frequency, window, halftime, intent,
player-specific, score-state, goal-timing combination, minimum-history,
imputation, smoothing, season carry-over, rolling/last-N, EWMA, regime
normalization, regularization, threshold, or nonlinear follow-up was run.

## Data discipline

- Existing matched baseline reference reused: **NO**
- Feature changes: **NO**
- Parameter changes: **NO**
- Tuning: **NOT RUN**
- Adaptive follow-up: **NOT RUN**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen, Cups, J2/J3, and AFC: **NOT USED**
- external HTTP: **NO**
