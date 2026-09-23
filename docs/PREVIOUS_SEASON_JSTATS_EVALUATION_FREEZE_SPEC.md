# Previous-season J Stats retrospective evaluation freeze

Status: protocol frozen before retrospective model fitting or metric calculation.

## Purpose and limitation

This protocol tests whether the frozen six-stat previous-season J Stats profile
family contains retrospective signal beyond the existing Elo-only Logistic
model. The profile artifact contains season-final/restated values retrieved in
2026, not historical point-in-time snapshots. Results are therefore
retrospective research evidence, not production promotion evidence.

## Opened-data discipline

The following data are excluded from every fold, training set, validation set,
metric calculation, and feature-selection decision in this retrospective lane:

- 2025 ordinary J1
- 2026/27 first 80 completed matches
- 2026/27 future 300 fixtures and labels

The future 2026/27 fixtures remain untouched. The six-stat profile artifact and
feature dataset are read-only inputs for this protocol.

## Fixed folds

The seed season is 2020. Only the following expanding folds are evaluated:

| Fold | Training target seasons | Validation target season | Expected matched rows |
|---|---|---:|---:|
| 2021 | 2020 | 2021 | 306 |
| 2022 | 2020-2021 | 2022 | 240 |
| 2023 | 2020-2022 | 2023 | 240 |
| 2024 | 2020-2023 | 2024 | 272 |

The primary matched comparison is expected to contain 1,058 validation rows.
Implementations must derive and assert the observed counts; these values are
not a substitute for validation of the local artifact.

No validation-season row may enter its fold's training data. The 2020 season
is a training seed only and has no validation fold in this lane.

## Primary matched comparison

Both models use the same rows, labels, chronological Elo state, and fold
boundaries. Only rows where both home and away teams have all six previous-
season profile stats are included.

### J0: matched Elo-only comparator

Feature:

- `elo_diff`

### J1: matched previous-season J Stats challenger

Features:

- `elo_diff`
- home/away previous expected goals per match
- home/away previous shots on target per match
- home/away previous expected goals against per match
- home/away previous suffered shots on target per match
- home/away previous ball rate
- home/away previous pass rate

Availability flags, differences, ratios, interactions, and additional feature
selection are excluded.

## Elo and model configuration

Use the existing frozen J1-only Elo convention:

- initial rating: 1500
- K: 30
- home advantage: 175, used only in expected-score calculation
- feature: `elo_diff = home_elo - away_elo`

Replay is chronological and uses only prior J1 results. Same-date handling must
match the existing project convention and may not introduce future-result
leakage.

Both J0 and J1 use the existing Logistic Regression convention:

- `StandardScaler`, fit on the training fold only
- `LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)`
- classes: `0 = Away`, `1 = Draw`, `2 = Home`

No hyperparameter tuning, class weighting, calibration, draw threshold change,
or model replacement is permitted.

## Metrics and comparison

Report fold-level and pooled results for both models:

- primary: multiclass Log Loss
- secondary: project multiclass Brier,
  `mean(sum((p - y_onehot)^2, axis=1))`
- descriptive: Accuracy

Report J1 minus J0 deltas. Negative Log Loss/Brier deltas indicate improvement.

## Missing-profile policy

The primary comparison excludes rows without a complete profile on either side.
Missing values are not replaced with zero, a league average, J2/Cup profiles,
or availability flags.

For a separate operational diagnostic only, a missing-profile row may use a
fold-specific Elo-only fallback trained on that fold's ordinary-J1 history.
This fallback must not be mixed into the primary matched comparison.

Partial profiles are hard errors. A team with no previous-season profile is
represented by null profile values and `has_previous_j1_profile = false` in the
feature artifact.

## Frozen decision rule

After the metrics are computed, classify the retrospective lane as follows:

`CONTINUE_TO_PROSPECTIVE_FREEZE` requires all three:

1. pooled J1 Log Loss < pooled J0 Log Loss;
2. pooled J1 Brier < pooled J0 Brier; and
3. J1 Log Loss is lower than J0 in at least 3 of 4 folds.

`CLOSE_RETROSPECTIVE_LANE` applies when pooled Log Loss and pooled Brier are
both not better than J0 and J1 Log Loss is not lower in at least 3 of 4 folds.
Otherwise report `MIXED` without tuning or further search.

Accuracy is descriptive and is not a decision criterion.

## Freeze metadata

- profile retrieval: `20260923T010000000000Z`
- feature artifact: `data/processed/features/previous_season_jstats_features.csv`
- feature family: previous-season J Stats six-stat family
- evaluation code and metrics: not yet run

This document freezes the protocol before results are observed. A result that
does not meet the continuation rule does not justify feature-subset search,
parameter tuning, or retrospective reinterpretation.
