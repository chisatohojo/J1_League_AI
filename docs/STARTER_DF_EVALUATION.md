# Previous-match starter DF count retrospective evaluation

Status: **COMPLETE — CLOSE_RETROSPECTIVE_LANE**.

The single formal retrospective rolling-OOF evaluation frozen in
`STARTER_DF_EVALUATION_FREEZE_SPEC.md` was implemented and executed exactly
once. Baseline sanity passed before any matched S0 or S1 fit. The evaluated
family adds the home and away previous-match source-listed A5 starter DF
counts together to the known-good Elo-only baseline.

## Validation and baseline sanity

- Baseline sanity: **PASS**
- Feature artifact SHA-256: **PASS**
  (`056963dd4707f122754d596ac6865721052cc3a31589a3a02941faca683aa674`)
- Exact ordered 13-column schema: **PASS**
- Target/feature keyed identity: **PASS**
- Feature invariants and no imputation: **PASS**
- Frozen availability, fold, and pooled counts: **PASS**
- S0/S1 training IDs, validation IDs, and labels: **PASS**
- Probability shape, finiteness, range, row sums, and class order: **PASS**
- Existing matched baseline reference reused: **NO**

The known-good Elo replay used initial rating 1500, K=30, home advantage 175
in expected-score calculation only, and same-date conservative batching.

## Mandatory all-row A_Y gate

Every frozen fold Log Loss reference matched with `rtol=0` and
`atol=1e-12`:

| Validation season | A_Y Accuracy | A_Y Log Loss | A_Y Brier | Rows |
|---:|---:|---:|---:|---:|
| 2020 | 0.5065359477124183 | 1.023119734659012 | 0.6117572218710644 | 306 |
| 2021 | 0.5078947368421053 | 1.0253437210487792 | 0.6149829138674616 | 380 |
| 2022 | 0.4019607843137255 | 1.0940186385371449 | 0.6610224339161608 | 306 |
| 2023 | 0.46078431372549017 | 1.0604285568595655 | 0.638530529273072 | 306 |
| 2024 | 0.45 | 1.079241181120235 | 0.6531695943664019 | 380 |
| **Pooled** | **0.466626936829559** | **1.056065401323764** | **0.6357323419292724** | **1,678** |

Only after this gate passed were the official starter-DF matched S0 and S1
fit.

## Primary matched comparison

S0 used exactly `elo_diff`. S1 used exactly `elo_diff`,
`home_previous_match_starter_df_count`, and
`away_previous_match_starter_df_count`, in that order. Deltas are S1 minus
S0. Log Loss is primary, project multiclass Brier is secondary, and Accuracy
is descriptive only.

| Season | Train total / eligible | Validation total / eligible | S0 Accuracy | S0 Log Loss | S0 Brier | S1 Accuracy | S1 Log Loss | S1 Brier | Δ Accuracy | Δ Log Loss | Δ Brier |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 1,530 / 1,485 | 306 / 297 | 0.5117845117845118 | 1.0200551893806826 | 0.6092343529578926 | 0.4983164983164983 | 1.0141568041969733 | 0.6058793271010933 | -0.013468013468013462 | -0.0058983851837093315 | -0.003355025856799365 |
| 2021 | 1,836 / 1,782 | 380 / 370 | 0.5081081081081081 | 1.0228574687359941 | 0.6134256329675887 | 0.5135135135135135 | 1.023595034676723 | 0.6132846233914017 | 0.00540540540540535 | 0.0007375659407289348 | -0.00014100957618701226 |
| 2022 | 2,216 / 2,152 | 306 / 297 | 0.4074074074074074 | 1.0940335755002084 | 0.6610886571658463 | 0.4107744107744108 | 1.0986907139477418 | 0.6639320283362397 | 0.003367003367003407 | 0.004657138447533349 | 0.0028433711703933495 |
| 2023 | 2,522 / 2,449 | 306 / 297 | 0.4612794612794613 | 1.0610261822973375 | 0.6386518824398223 | 0.45791245791245794 | 1.0586981148000991 | 0.6370202499679801 | -0.0033670033670033517 | -0.002328067497238351 | -0.0016316324718421704 |
| 2024 | 2,828 / 2,746 | 380 / 370 | 0.4486486486486487 | 1.0809648055472723 | 0.6546244215147561 | 0.4540540540540541 | 1.0844790486856055 | 0.6568089883523228 | 0.005405405405405406 | 0.0035142431383332617 | 0.002184566837566737 |

S1 improved fold Log Loss in **2 / 5** folds (2020 and 2023).

### Primary pooled OOF

The five validation target and probability arrays were concatenated before
metrics were calculated. No fold-metric average was used.

| Model | Accuracy | Log Loss | Brier | n |
|---|---:|---:|---:|---:|
| S0 | 0.46842427958307786 | 1.0554404541978801 | 0.6352814612200155 | 1,631 |
| S1 | 0.46842427958307786 | 1.0557550360690813 | 0.6353547658801693 | 1,631 |
| **Δ S1 − S0** | **0.0** | **0.000314581871201147** | **0.0000733046601537619** | — |

S1 therefore worsened both pooled primary metrics: Log Loss and Brier.

## Operational pooled comparison

For pair-eligible validation matches, Operational S1 used the same match's
matched S1 probability. For pair-unavailable matches, it used the same
match's A_Y probability. Alignment was by exact unique `match_id`.

| Model | Accuracy | Log Loss | Brier | n |
|---|---:|---:|---:|---:|
| A_Y | 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 | 1,678 |
| Operational S1 | 0.46722288438617404 | 1.0565202886790601 | 0.635830022614838 | 1,678 |
| **Δ Operational S1 − A_Y** | **0.000595947556615035** | **0.0004548873552960855** | **0.0000976806855655934** | — |

This operational comparison is descriptive and did not participate in the
decision.

## Frozen decision

**CLOSE_RETROSPECTIVE_LANE**

The frozen close rule is satisfied:

- S1 pooled Log Loss is greater than or equal to S0 pooled Log Loss;
- S1 pooled Brier is greater than or equal to S0 pooled Brier; and
- S1 Log Loss did not improve in 3 of 5 folds.

Accuracy was not used in this decision. No result-driven alternative was
tested.

## Boundaries

- Feature changes: **NO**
- Parameter changes: **NO**
- Tuning: **NOT RUN**
- Adaptive follow-up: **NOT RUN**
- Additional feature variant: **NOT RUN**
- Prediction CSV/model artifact/serialized estimator: **NOT CREATED**
- 2025: **NOT USED**
- 2026/27 first 80: **NOT USED**
- future 300: **NOT USED**
- Hyakunen, League Cup, Emperor's Cup, J2/J3, and AFC: **NOT USED**
- external HTTP: **NO**
