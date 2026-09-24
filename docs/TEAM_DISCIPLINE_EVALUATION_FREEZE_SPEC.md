# Team Discipline Evaluation Freeze Specification

Status: `FROZEN_FOR_ONE_EVALUATION`

This document freezes one prespecified retrospective evaluation of the
materialized ordinary-J1 team discipline feature family. It is a protocol
document, not an evaluation result. No model fitting, prediction, or metric
calculation was performed when this specification was created.

## 1. Purpose

Evaluate once whether the frozen team discipline profile adds information to
the existing Elo-only baseline in historical rolling OOF validation. This is
not an adaptive feature search. After results are observed, do not change the
window, card weights, feature subset, interactions, thresholds, or parameters.

## 2. Evaluation seasons

| validation | training |
|---:|:---|
| 2020 | 2015--2019 |
| 2021 | 2015--2020 |
| 2022 | 2015--2021 |
| 2023 | 2015--2022 |
| 2024 | 2015--2023 |

Training contains only seasons strictly before validation. Do not use 2025,
2026/27 first 80, future 2026/27 matches, Hyakunen, J2, J3, Cups, or AFC.

## 3. Frozen data source

Feature artifact:
`data/processed/features/2015_2024_j1_team_discipline_features.csv`

Builder: `src/features/team_discipline.py`.

The artifact has one row per ordinary-J1 match (3,208 rows). It consumes only
`YELLOW_CARD` and `RED_CARD` rows from the materialized SFMS02 event dataset.
Player identity, goals, and substitutions are not used.

## 4. Models

### D0: Elo-only matched baseline

Exactly one feature: `elo_diff`.

### D1: Elo + discipline

Exactly these five features:

```text
elo_diff
home_yellow_cards_per_match_prior
away_yellow_cards_per_match_prior
home_red_cards_per_match_prior
away_red_cards_per_match_prior
```

Availability flags and prior-match counts are validation fields only, not model
inputs. Do not create difference, ratio, interaction, weighted-card, timing,
or other transformed features.

## 5. Elo contract

Use the existing frozen ordinary-J1 Elo replay:

- initial Elo: `1500`
- K: `30`
- home advantage: `175`
- `elo_diff = home Elo - away Elo`

Home advantage is used only inside expected-score calculation. Preserve the
existing same-date conservative batching and ordinary-J1 chronology.

## 6. Logistic contract

Use multinomial three-class Logistic Regression with class order:

```text
0 = Away
1 = Draw
2 = Home
```

For each fold, fit preprocessing on training rows only:

- `StandardScaler`
- `LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)`

No tuning or alternative preprocessing is permitted.

## 7. Primary matched evaluation

D0 and D1 use identical validation rows: both home and away discipline profiles
must be available and all four discipline rate values must be finite, non-null,
and non-negative.

Expected eligible validation counts are derived from the artifact and checked,
not blindly substituted:

| season | eligible rows |
|---:|---:|
| 2020 | 297 |
| 2021 | 370 |
| 2022 | 297 |
| 2023 | 297 |
| 2024 | 370 |
| pooled | 1,631 |

Training eligibility uses the same matched rule. Expected eligible training
counts, to be re-derived from the artifact, are 1,485, 1,782, 2,152, 2,449,
and 2,746 for folds 2020 through 2024 respectively.

Rows without a pair-available profile are excluded from this primary matched
comparison; they are not zero-filled.

## 8. Operational fallback comparison

This is a separate comparison over every ordinary-J1 validation match.

For validation season `Y`, `A_Y` is a fold-specific Elo-only baseline trained
on ordinary J1 seasons 2015 through `Y-1` and validated on all ordinary-J1
matches in season `Y`, using the existing Elo and Logistic contracts.

For operational D1:

- pair profile available: use D1 probability;
- pair profile unavailable: use the corresponding `A_Y` probability.

Do not impute discipline values in fallback rows. Do not use the production
Model A artifact trained through 2025 for historical folds. All probability
arrays must be aligned by `match_id`, not implicit row position.

Expected full validation counts are 306, 380, 306, 306, and 380, pooled
1,678.

## 9. Metrics and decision rule

Report fold-level and pooled Log Loss, project multiclass Brier, and descriptive
Accuracy. Brier is:

`mean(sum((p - one_hot) ** 2, axis=1))`

Pooled metrics must use concatenated OOF predictions, not a simple mean of fold
metrics.

`CONTINUE_DISCIPLINE_LANE` requires pooled D1 Log Loss and Brier both below D0,
and D1 Log Loss below D0 in at least 3 of 5 folds.

`CLOSE_RETROSPECTIVE_LANE` requires pooled D1 Log Loss and Brier both at least
D0, and D1 Log Loss at least D0 in at least 3 of 5 folds.

Otherwise report `INCONCLUSIVE_NO_TUNING`. No result permits automatic feature
or parameter search.

## 10. Leakage and integrity safeguards

Later evaluation must assert that target cards, same-date peer events, future
seasons, or validation labels are not used for a target's features, fitting,
preprocessing, or model choice. History resets at season boundaries; source
match IDs and team IDs remain exact and unique; eligibility is derived from the
frozen artifact.

## 11. Closed searches and boundary

Do not test yellow-only, red-only, side-only, alternative windows, weighted
cards, per-90 rates, timing, referee/opponent adjustments, thresholds,
regularization, interactions, or nonlinear transforms in this lane.

This specification authorizes one evaluation only. It does not authorize CSV
modification, feature regeneration, model implementation, or commit/push.
New information layers require a separate research cycle.
