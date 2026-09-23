# Player workload retrospective evaluation freeze

Freeze timestamp: `2026-09-23T14:01:32+09:00`

This document freezes the retrospective protocol before any model fitting,
prediction, or metric calculation. It does not change the existing workload
feature artifact or the previous-season J Stats lane.

## Purpose and data limitations

The lane tests whether the existing local J1 player-workload aggregate feature
family contains retrospective signal beyond frozen Elo-only Logistic. The
dataset contains 3,208 ordinary J1 matches from 2015-2024.

Player identity is the exact local key `(season, team_id, player_name_raw)`.
No cross-season, cross-team, fuzzy, or inferred official-player identity is
used. `minutes_played_normalized` is reconstructed on a 0-90 regulation clock,
not actual elapsed minutes or total football workload. Cup, AFC, J2, training,
injury, and other non-J1 workload are absent.

The previous-match squad reference is historical information and never uses
the target match's lineup or minutes. Same-date matches are batched according
to the existing workload builder policy.

## Fixed folds

Use all five expanding folds:

| Fold | Training ordinary J1 | Validation |
|---|---|---|
| 2020 | 2015-2019 | 2020 |
| 2021 | 2015-2020 | 2021 |
| 2022 | 2015-2021 | 2022 |
| 2023 | 2015-2022 | 2023 |
| 2024 | 2015-2023 | 2024 |

2025, 2026/27 first 80, and future 300 are excluded and their labels are not
used. Counts must be derived from the local artifact, not silently replaced by
hard-coded assumptions.

## Frozen workload family

W0 is Elo-only with `elo_diff`.

W1 adds exactly these six workload features per side:

- `prev_starters_mean_minutes_7d`
- `prev_starters_mean_minutes_14d`
- `prev_starters_mean_minutes_30d`
- `prev_squad_mean_minutes_7d`
- `prev_squad_mean_minutes_14d`
- `prev_squad_mean_minutes_30d`

Thus W1 has `elo_diff` plus 12 workload values. No sums, history counts,
thresholds, squad sizes, starter counts, availability flags, differences,
ratios, interactions, or other workload/stat features enter the primary model.

## Primary eligibility

For a primary matched row, both home and away must satisfy:

- `has_previous_j1_match == 1`;
- `prev_reference_from_prior_season == 0`;
- all 12 workload values are finite and non-negative.

Rows failing eligibility are excluded from the primary W0/W1 comparison. They
are not zero-imputed, mean-imputed, or replaced with another competition's
workload. Partial or invalid workload values hard-fail validation.

Read-only audit of the current artifact:

| Season | Rows | Primary eligible | Ineligible |
|---:|---:|---:|---:|
| 2020 | 306 | 297 | 9 |
| 2021 | 380 | 370 | 10 |
| 2022 | 306 | 297 | 9 |
| 2023 | 306 | 297 | 9 |
| 2024 | 380 | 370 | 10 |

Derived from the artifact using the frozen training ranges, the training totals
and eligible rows are:

| Fold | Training seasons | Total training rows | Eligible training rows |
|---:|---|---:|---:|
| 2020 | 2015-2019 | 1,530 | 1,485 |
| 2021 | 2015-2020 | 1,836 | 1,782 |
| 2022 | 2015-2021 | 2,216 | 2,152 |
| 2023 | 2015-2022 | 2,522 | 2,449 |
| 2024 | 2015-2023 | 2,828 | 2,746 |

The corresponding eligible validation counts are 297, 370, 297, 297, and 370.

### Validation ineligible-reason audit

The following reason counts are match-level and **non-exclusive**: one row may
appear in more than one reason column. There is no silent precedence rule.

| Validation season | Total | Eligible | Ineligible | A: expected unavailable | B: prior-season reference | C: true partial/invalid anomaly |
|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 306 | 297 | 9 | 1 | 9 | 0 |
| 2021 | 380 | 370 | 10 | 1 | 10 | 0 |
| 2022 | 306 | 297 | 9 | 1 | 9 | 0 |
| 2023 | 306 | 297 | 9 | 0 | 9 | 0 |
| 2024 | 380 | 370 | 10 | 2 | 10 | 0 |

Reason semantics are:

- **A, expected unavailable**: either side has `has_previous_j1_match == 0`,
  so null workload aggregates are expected and are not an anomaly.
- **B, prior-season reference**: either side has
  `prev_reference_from_prior_season == 1`; this is finite workload data but is
  excluded by the primary eligibility rule.
- **C, true partial/invalid anomaly**: a previous-J1 reference exists but the
  frozen workload values are missing, non-finite, negative, or structurally
  inconsistent. This category is a hard-fail condition.

The table's reason counts are non-exclusive. After separating A from C, the
true partial/invalid anomaly count is **0 in every validation season**, and
**0 among primary-eligible rows**. No primary-eligible row has a missing,
non-finite, or negative frozen workload value. For every season,
`eligible + ineligible = total`; for every training fold, eligible rows are no
greater than total rows and use exactly the frozen season range.

## Elo and Logistic model

Replay the full ordinary-J1 chronology for Elo, not only eligible rows:

- initial rating: 1500
- K: 30
- home advantage: 175, used only in expected-score updates
- feature: `elo_diff = home rating - away rating`

Use `match_date, match_id` ordering and the existing same-date batch policy.
The target result is not used before the target prediction.

Both W0 and W1 use:

- `StandardScaler`, fit on the training fold only;
- `LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)`;
- class order `0 = Away`, `1 = Draw`, `2 = Home`.

## Primary comparison and metrics

W0 and W1 use the same eligible training rows, validation rows, labels, and
Elo state. Report fold and pooled results:

- primary: multiclass Log Loss;
- secondary: project multiclass Brier,
  `mean(sum((p-y_onehot)^2, axis=1))`;
- descriptive: Accuracy.

Pooled metrics are computed directly from concatenated validation predictions,
not by averaging fold metrics. Report W1 minus W0 deltas; negative Log Loss or
Brier means improvement.

## Operational comparison

For each validation season `Y`, define `A_Y` as a fold-specific Elo-only
baseline:

- training: all ordinary J1 matches from 2015 through `Y-1`;
- validation: all ordinary J1 matches in season `Y`;
- same frozen Elo and Logistic settings above.

For every validation match, the operational challenger uses W1 when the pair
is primary-eligible and uses `A_Y` otherwise. Compare this operational output
with `A_Y` over the complete validation season, reporting fold and pooled Log
Loss, Brier, and Accuracy. Align predictions by `match_id`, never by row
position. Do not reuse a production Model A artifact trained on future seasons.

## Frozen decision rule

`CONTINUE_TO_PROSPECTIVE_FREEZE` requires pooled W1 Log Loss and Brier both
below W0, and W1 Log Loss below W0 in at least 3 of 5 folds.

`CLOSE_RETROSPECTIVE_LANE` requires pooled W1 Log Loss and Brier both greater
than or equal to W0, and W1 Log Loss greater than or equal to W0 in at least 3
of 5 folds. Otherwise report `MIXED`.

Accuracy is not a decision criterion. After results are observed, no window,
starter/squad subset, sum/mean choice, threshold, feature subset, or parameter
tuning is permitted.

## Outputs and exclusions

Future implementation may use:

- `src/modeling/player_workload_evaluation.py`
- `tests/test_player_workload_evaluation.py`
- `docs/PLAYER_WORKLOAD_EVALUATION.md`

Those files are not created by this freeze-only audit. Model fitting,
`predict_proba`, Accuracy, Log Loss, Brier, 2025 evaluation, 2026 evaluation,
feature selection, and prediction are not performed in this stage.
