# Player workload retrospective evaluation

## Status and limitation

This is the single retrospective evaluation specified by
`PLAYER_WORKLOAD_EVALUATION_FREEZE_SPEC.md`. The workload features cover local
ordinary-J1 normalized minutes only. They omit Cup, AFC, J2, training, injury,
and other workload. Player identity is the exact local key
`(season, team_id, player_name_raw)`, not a stable official player identity.

The result is research evidence only. No 2025 or 2026/27 match data were loaded
or evaluated, and no feature search or tuning followed observation of results.

## Frozen fold counts

| Fold | Train total | Train eligible | Validation total | Validation eligible |
|---:|---:|---:|---:|---:|
| 2020 | 1,530 | 1,485 | 306 | 297 |
| 2021 | 1,836 | 1,782 | 380 | 370 |
| 2022 | 2,216 | 2,152 | 306 | 297 |
| 2023 | 2,522 | 2,449 | 306 | 297 |
| 2024 | 2,828 | 2,746 | 380 | 370 |

Primary pooled eligible validation contains 1,631 matches. Operational pooled
validation contains all 1,678 matches.

## Primary matched comparison

W0 uses `elo_diff`. W1 uses the same rows, labels, and Elo state, adding the
frozen 12 starter/squad mean-minute features.

| Fold | W0 Log Loss | W1 Log Loss | W0 Brier | W1 Brier | W0 Accuracy | W1 Accuracy |
|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1.020055 | 1.054112 | 0.609234 | 0.629759 | 0.511785 | 0.481481 |
| 2021 | 1.022857 | 1.036341 | 0.613426 | 0.622620 | 0.508108 | 0.491892 |
| 2022 | 1.094034 | 1.096455 | 0.661089 | 0.662703 | 0.407407 | 0.404040 |
| 2023 | 1.061026 | 1.055578 | 0.638652 | 0.634551 | 0.461279 | 0.464646 |
| 2024 | 1.080965 | 1.080967 | 0.654624 | 0.654280 | 0.448649 | 0.416216 |
| **Pooled** | **1.055440** | **1.064150** | **0.635281** | **0.640574** | **0.468424** | **0.451870** |

Pooled W1 minus W0:

- Log Loss: **+0.008710**
- Brier: **+0.005292**
- Accuracy: **-0.016554**
- folds with lower W1 Log Loss: **1 / 5**

## Operational comparison

For each fold, `A_Y` is trained on every ordinary-J1 match from 2015 through
`Y-1`. The operational challenger uses W1 on primary-eligible rows and the
same match-ID-aligned `A_Y` prediction on ineligible rows.

| Fold | A_Y Log Loss | Operational W1 Log Loss | A_Y Brier | Operational W1 Brier | A_Y Accuracy | Operational W1 Accuracy |
|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1.023120 | 1.055951 | 0.611757 | 0.631367 | 0.506536 | 0.480392 |
| 2021 | 1.025344 | 1.037880 | 0.614983 | 0.623511 | 0.507895 | 0.492105 |
| 2022 | 1.094019 | 1.096632 | 0.661022 | 0.662716 | 0.401961 | 0.401961 |
| 2023 | 1.060429 | 1.056056 | 0.638531 | 0.634923 | 0.460784 | 0.460784 |
| 2024 | 1.079241 | 1.079724 | 0.653170 | 0.653223 | 0.450000 | 0.418421 |
| **Pooled** | **1.056065** | **1.064680** | **0.635732** | **0.640903** | **0.466627** | **0.451132** |

Operational W1 minus `A_Y` pooled:

- Log Loss: **+0.008615**
- Brier: **+0.005171**
- Accuracy: **-0.015495**

## Frozen decision

`CLOSE_RETROSPECTIVE_LANE`.

W1 worsened pooled Log Loss and Brier and improved Log Loss in only 1 of 5
folds. Per the frozen protocol, no starter-only, squad-only, window subset,
sum-minute, history-count, threshold, feature subset, or parameter experiment
was run afterward. This decision does not modify Model A or any other frozen
candidate.

## Reproducibility discipline

- all 3,208 ordinary-J1 matches were joined one-to-one by `match_id`;
- Elo used initial 1500, K=30, HA=175 and full ordinary-J1 chronology;
- same-date matches received pre-match Elo before that date's updates;
- scaler fitting was training-fold only;
- Logistic parameters and class order remained frozen;
- pooled metrics were calculated directly from concatenated probabilities;
- 2025 metrics: **NOT COMPUTED**;
- 2026/27 metrics: **NOT COMPUTED**;
- future 300 labels: **NOT USED**;
- tuning and feature search: **NOT RUN**.
