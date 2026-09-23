# Previous-season J Stats retrospective evaluation

## Status

Completed once using the frozen protocol in
`PREVIOUS_SEASON_JSTATS_EVALUATION_FREEZE_SPEC.md`. This is retrospective
research using season-final/restated J Stats profiles retrieved in 2026; it is
not point-in-time backtest evidence or production promotion evidence.

2025 ordinary J1, the 2026/27 first 80 completed matches, and the future 300
fixtures were excluded from model selection and metrics.

## Primary matched comparison

Only rows with complete previous-season profiles for both teams were used. J0
and J1 used the same training rows, validation rows, labels, Elo state, and
frozen Logistic configuration.

| Fold | Matched rows | J0 Elo-only LL | J1 J Stats LL | J0 Brier | J1 Brier | J0 Acc. | J1 Acc. |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 306 | 1.016313 | 1.049337 | 0.608887 | 0.625603 | 0.506535 | 0.493464 |
| 2022 | 240 | 1.081692 | 1.091638 | 0.652400 | 0.654376 | 0.408333 | 0.433333 |
| 2023 | 240 | 1.050536 | 1.072991 | 0.631096 | 0.644867 | 0.470833 | 0.437500 |
| 2024 | 272 | 1.072811 | 1.083807 | 0.649206 | 0.655668 | 0.459559 | 0.397059 |
| **Pooled** | **1,058** | **1.053432** | **1.073160** | **0.634161** | **0.644229** | **0.464083** | **0.442344** |

J1 minus J0 pooled deltas:

- Log Loss: **+0.019729**
- Brier: **+0.010068**
- Accuracy: **-0.021739**
- folds with lower J1 Log Loss: **0 / 4**

## Secondary operational comparison

For each validation season `Y`, `A_Y` was refit using all ordinary-J1 matches
from 2015 through `Y-1`, and validated on all ordinary-J1 matches in `Y`.
The operational challenger used the matched J1 model when both profiles were
available and `A_Y` for unavailable pairs.

| Fold | Rows | A_Y LL | Operational J1 LL | A_Y Brier | Operational J1 Brier | A_Y Acc. | Operational J1 Acc. |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 380 | 1.025344 | 1.053895 | 0.614983 | 0.629592 | 0.507895 | 0.492105 |
| 2022 | 306 | 1.094018 | 1.097800 | 0.661022 | 0.659853 | 0.401961 | 0.421569 |
| 2023 | 306 | 1.060429 | 1.082652 | 0.638531 | 0.651439 | 0.460784 | 0.434641 |
| 2024 | 380 | 1.079241 | 1.087375 | 0.653170 | 0.658197 | 0.450000 | 0.402632 |
| **Pooled** | **1,372** | **1.063413** | **1.079373** | **0.641080** | **0.649136** | **0.457726** | **0.438776** |

Operational J1 minus `A_Y` pooled deltas:

- Log Loss: **+0.015960**
- Brier: **+0.008057**
- Accuracy: **-0.018950**

The production Model A artifact trained on 2015-2025 was not reused for these
historical folds.

## Frozen decision

`CLOSE_RETROSPECTIVE_LANE`.

The primary challenger did not improve pooled Log Loss or Brier and improved
Log Loss in 0 of 4 folds. No feature subset search, tuning, calibration,
threshold adjustment, or follow-up experiment was performed.

## Reproducibility and exclusions

- Elo: initial 1500, K 30, HA 175; HA is used only in expected-score updates.
- Logistic: train-only `StandardScaler`; `C=1.0`, `lbfgs`, `max_iter=1000`, `random_state=0`.
- Class order: Away=0, Draw=1, Home=2.
- Brier: mean row-wise sum of the three one-hot class errors.
- Future-result leakage and same-date policy follow the existing project convention.
- 2025 and 2026/27 opened data were not used.
