# J1 League AI — project status (2026-09-20)

## Purpose and prediction contract

J1 ordinary league matches are predicted as `0=Away`, `1=Draw`, `2=Home` before the match. The primary metric is multiclass Log Loss, the secondary metric is multiclass Brier, and Accuracy is descriptive. Brier is `mean(sum((p - one_hot(y)) ** 2, axis=1))`; a uniform three-class forecast scores `2/3 = 0.666667`.

The project has moved from basic model exploration to a **new information layer / data platform** phase. The current task is to establish reproducible, time-stamped input histories and trustworthy new information, rather than extend the 2020–2024 feature search.

## Frozen candidates

| Candidate | Fixed specification | 2020–2024 pooled OOF (1,678 matches): Accuracy / Log Loss / Brier |
|---|---|---|
| A — Champion/reference | `elo_diff` only; initial Elo 1500, K=30, home advantage=175 within expected-score update only; `StandardScaler` + `LogisticRegression(C=1, solver="lbfgs", max_iter=1000, random_state=0)` | 0.466627 / 1.056065 / 0.635732 |
| B — Challenger | A plus home/away days since last domestic competitive match and home/away previous-match flags | 0.464839 / 1.055538 / 0.635051 |

B − A: Accuracy `-0.001788`, Log Loss `-0.000527`, Brier `-0.000681`; Log Loss improved in 3/5 folds. B's history is ordinary J1, J.League Cup and Emperor's Cup; for 2026 onward it also includes the 2026 J1 Hyakunen competition. AFC is absent. These figures and decisions are recorded in [MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md). Freeze date: **2026-09-20**. No feature, parameter, K/HA, rest definition, or threshold adjustment may be selected using the 2026 outcome.

## 2026/27 interim lockbox as recorded

The evaluation target is the **70 completed ordinary 2026/27 J1 matches**, not the 200 Hyakunen matches; 310 scheduled fixtures are future. Hyakunen's 200 regulation-time results update Elo and its dates enter Domestic Rest, but its rows are excluded from Logistic training. The recorded corrected interim result is:

| Model | Correct | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|---:|
| A | 40/70 | 0.571429 | 0.996370 | 0.592515 |
| B | 36/70 | 0.514286 | 1.026020 | 0.613140 |
| B − A | −4 | −0.057143 | +0.029650 | +0.020624 |

These are **reported repository artifacts**, not recalculated in this status audit. [2026_27_INTERIM_LOCKBOX_EVALUATION.md](2026_27_INTERIM_LOCKBOX_EVALUATION.md) calls them formal, but the code review below finds chronology/feature completeness concerns. The older freeze document's “unopened 2026 lockbox” line described its creation-time state and is now superseded by the opened interim evaluation. Do not infer a new model choice from 70/380 matches. Full-season evaluation should use the frozen specification after a separate, non-tuning reproducibility audit.

## 74-match training-count discrepancy

| Stage | Expected | Observed in repository | Explanation |
|---|---:|---:|---|
| 2015–2024 ordinary J1 CSVs | 3,208 | 3,208 | 2021 and 2024 each have 380; other years have 306 |
| 2025 ordinary J1 CSV | 380 | 380 | no date/result/team-ID missing |
| Concatenated `_j1()` input | 3,588 | 3,588 | IDs unique; all 49-team-master resolutions succeed |
| `_rest_features` rows | 3,588 | 3,588 | no missing generated feature cells |
| `_elo_features` rows | 3,588 | 3,588 | no missing generated Elo cells |
| `match_id` merge of training features | 3,588 | 3,588 | no exclusion or dropped IDs |
| Interim evaluation document's training count | 3,588 | **3,514 stated** | **74-row documentation discrepancy** |

The value `3,514` equals `3,208 + 306`, as if 2025 had 306 matches, but the repository has 380. That arithmetic is a possible origin, **not proven provenance** of the mistake. The current evaluator has no filter or missing-feature drop that removes 74 rows. The documented training count is therefore unsupported; do not silently edit the earlier evaluation report or rerun the lockbox as part of this audit. See [final_2026_lockbox_evaluation.py](../src/modeling/final_2026_lockbox_evaluation.py).

## Other reproducibility issues found (not repaired here)

1. The evaluator builds target Domestic Rest from 2015–2025 J1, Cups and Hyakunen, but `_rest_features(j1, ..., target)` is not given earlier completed 2026/27 ordinary J1 matches. **120 of 140 target team appearances** have an earlier target match on a previous date. For **97**, that prior target match is later than their latest supplied 2026 Hyakunen/Cup event, so the omitted ordinary J1 match changes the last-event date under the current input set. A full feature audit is still needed.
2. Target Elo replay sorts by `match_date, match_id` and updates after each row. The 70 target rows contain **11 groups of multiple matches at the same recorded kickoff time**; 30 later rows in those groups can see results from another simultaneously starting match. This violates the intended same-time pre-match rule. The report's “target results only after each prediction” does not establish cross-match safety.
3. `preflight_inputs()` asserts row counts for 2026 Cup/Emperor, Hyakunen and target, but only existence for 2025 J1/Cup/Emperor; their 380/56/41 counts were observed here, not hard-failed by that helper.
4. The first interim run had missing 2026 Cup/Emperor inputs and an elementwise Brier mean (one-third of this project's Brier scale). It was invalidated; the saved corrected report uses the proper scale. The original `270` target assumption (200 Hyakunen + 70 ordinary J1) was likewise withdrawn in [2026_LOCKBOX_PROTOCOL_CORRECTION.md](2026_LOCKBOX_PROTOCOL_CORRECTION.md).

These are **audit findings**, not permission to tune models using the opened lockbox. Resolve the data/chronology implementation questions in a separately scoped correction task before asserting the reported interim scores are fully protocol compliant.

## Experiment ledger: processed successfully, not frozen for production

The freeze lists **19** non-production experiments. The table lists a pooled Log Loss only when a repository document records it. `N/A` means that no persistent result was safely established by this read-only review; it is not a zero or an inferred score. Reference Elo-only Log Loss is `1.056065`.

| Experiment | Idea | Pooled Log Loss | vs Elo-only | Status / reason |
|---|---|---:|---:|---|
| Old 11-context model | Elo + stadium + league rest | N/A | N/A | Closed in freeze; not selected as champion |
| Shots | Match-stat extension | N/A | N/A | Closed in freeze; no persisted pooled number found |
| CatBoost | Fixed tree-family comparison | N/A | N/A | Closed; no persisted pooled number found |
| MLP | Fixed small neural model | N/A | N/A | Closed; no persisted pooled number found |
| Independent Poisson | Team attack/defence goal model | N/A | N/A | Closed; corrected score orientation, but no persisted result in docs |
| Dixon-Coles | Low-score adjustment | N/A | N/A | Closed; no persisted pooled number found |
| Poisson time decay | Recent-match weighting | N/A | N/A | Closed; no persisted pooled number found |
| Elo-assisted Poisson | Elo attacker difference | N/A | N/A | Closed; no persisted pooled number found |
| Dynamic attack/defence Poisson | Online goal strengths | N/A | N/A | Closed; no persisted pooled number found |
| Manager | Pre-match manager context | N/A | N/A | Closed; identity coverage and selection limit |
| Recent Form | Last-five points/goals | N/A | N/A | Closed in freeze |
| Elo Parity | `abs(elo_diff)` | N/A | N/A | Closed; pooled improvement absent per freeze |
| Promotion Reset | Returning team Elo reset to 1500 | 1.055671 | −0.000394 | Closed; only 2/5 folds improved, early promoted matches worsened |
| Equal J1+J2 Elo | J2 league Elo updates | 1.057002 | +0.000937 | Closed; returning subgroup improved, pooled worsened |
| J2 initial=1400 | Fixed division prior | 1.056353 | +0.000288 | Closed; 1/5 folds improved |
| Promotion-Calibrated J1+J2 | Prior-season mean offset | 1.056243 | +0.000178 | Closed; pooled worse, first-time/early group worse |
| Returning-History Hybrid | J2 carry-over for returning teams | 1.056399 | +0.000333* | Closed; pooled worse, early group worse |
| Davidson | Draw-explicit Elo outcome model | N/A | N/A | Closed in freeze; no persisted pooled number found |
| Lineup Continuity | Previous two Starting XI overlap | N/A | N/A | Closed; pooled Log Loss did not improve per freeze |

The J2/promotion numbers come from [ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md](ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md) and [ELO_PROMOTION_RESET_EVALUATION.md](ELO_PROMOTION_RESET_EVALUATION.md). `*` The Hybrid document reports `+0.000333`; subtraction of the two separately rounded six-decimal scores gives `+0.000334`. The source document's difference is retained rather than inventing extra precision. The separate Cup cross-division bridge audit found 145 identity candidates (68 League Cup, 77 Emperor's Cup), but zero matches with safely usable regulation-time result in its evaluation; it is **unevaluated, not rejected on performance**.

## Deferred information and research discipline

FootyStats historical match xG, SofaScore player ratings, J.LEAGUE.jp final detailed stats, AFC integration, stable player identity, and regulation-time Cup bridge results remain data-path/identity tasks. See [DATA_PIPELINE_STATUS.md](DATA_PIPELINE_STATUS.md) and [NEXT_DATA_RESEARCH_ROADMAP.md](NEXT_DATA_RESEARCH_ROADMAP.md).

2025 is a spent test and cannot be used for a new model choice. The first 70 completed 2026/27 matches are an opened interim lockbox and cannot be used for feature selection or tuning. Future feature groups require a new research cycle with point-in-time snapshots and independent validation. The 2020–2024 OOF cycle is closed to repeated small-feature searches.
