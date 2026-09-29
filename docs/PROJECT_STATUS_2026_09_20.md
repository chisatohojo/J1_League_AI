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

## 2026/27 chronology-corrected official interim lockbox

The evaluation target is the **70 completed ordinary 2026/27 J1 matches**, not the 200 Hyakunen matches; 310 scheduled fixtures are future and unused. Hyakunen's 200 regulation-time results update Elo and its dates enter Domestic Rest, but its rows are excluded from Logistic training. The current official interim result is documented in [2026_27_INTERIM_LOCKBOX_EVALUATION.md](2026_27_INTERIM_LOCKBOX_EVALUATION.md):

This is an immutable opened-lockbox statement, not a requirement that the live
2026/27 publication remain at 70 completed matches. As of the 2026-09-29 local
publication, live progress is 80 completed / 300 scheduled. Tests treat that
publication as mutable while binding the interim target to the 70 IDs in the
SHA-256-validated saved prediction artifact. The additional ten matches are
live history only and do not enter the frozen interim target.

| Model | Correct | Accuracy | Log Loss | Brier |
|---|---:|---:|---:|---:|
| A | 40/70 | 0.571429 | 0.996370 | 0.592515 |
| B | 38/70 | 0.542857 | 1.001462 | 0.596178 |
| B − A | −2 | −0.028571 | +0.005092 | +0.003663 |

These figures are transcribed from the completed chronology-corrected evaluation; **no prediction or metric was recomputed for this status update**. The freeze document's “unopened 2026 lockbox” describes its creation-time state and is superseded as a status statement. The 70-match result must not be used to choose a model or tune the frozen specifications. The full 380-match evaluation remains a later fixed-specification check.

### Draw-class diagnostic, not a model-selection instruction

Actual outcomes are Away/Draw/Home = **22/15/33**. A predicts these classes **33/0/37** times; B predicts them **35/0/35** times. Both correctly classify **0/15 draws** (draw recall **0%**); among the actual draws, each predicts Away 6 times and Home 9 times. This means Draw is never the **argmax class**, not that its predicted probability is zero. This opened interim sample is a diagnostic only: no draw correction, threshold adjustment or model change follows from it.

## Training count: 3,588 confirmed

| Stage | Expected | Observed in repository | Explanation |
|---|---:|---:|---|
| 2015–2024 ordinary J1 CSVs | 3,208 | 3,208 | 2021 and 2024 each have 380; other years have 306 |
| 2025 ordinary J1 CSV | 380 | 380 | no date/result/team-ID missing |
| Concatenated `_j1()` input | 3,588 | 3,588 | IDs unique; all 49-team-master resolutions succeed |
| `_rest_features` rows | 3,588 | 3,588 | no missing generated feature cells |
| `_elo_features` rows | 3,588 | 3,588 | no missing generated Elo cells |
| `match_id` merge of training features | 3,588 | 3,588 | no exclusion or dropped IDs |
| Current official evaluation's Logistic training input | 3,588 | 3,588 | all ordinary J1 rows 2015–2025 after feature joins |

The earlier report's `3,514` was a **documentation error**, not a 74-row exclusion. Its possible arithmetic origin (`3,208 + 306`) is unproven; 2025 actually has 380 matches. The current official evaluation document correctly states 3,588. See [final_2026_lockbox_evaluation.py](../src/modeling/final_2026_lockbox_evaluation.py).

## Chronology correction and historical run status

1. The previous evaluator omitted earlier completed 2026/27 ordinary J1 target matches from Model B's Domestic Rest history. It is corrected: **50 target matches / 97 team appearances** have changed Rest features; the first affected match was **2026-08-14, ID 34527**. Each date's target events enter Rest history only for later dates.
2. Target Elo and Rest use **same-date batching**. There are 15 date buckets, **12** with multiple matches; 11 exact-kickoff-time groups also contain multiple matches. No same-date match result enters another match's pre-match feature. The corrected Elo difference changed for **0/70** actual targets because no club played twice on a target date.
3. `preflight_inputs()` hard-fails on the static 2025 J1/Cup/Emperor counts
   **380/56/41**, 2026 Cup/Emperor **4/19**, Hyakunen **200**, the full live
   schedule **380**, and the immutable saved-prediction target **70**. The
   live completed/future split is validated structurally and may advance; it
   is not the source of frozen target membership.
4. The first interim run lacked 2026 Cup/Emperor inputs and used the wrong Brier reduction; it is **invalid**. The later 36/70 Model B report used the correct inputs/Brier scale but had the Rest chronology bug; it is **superseded**, not the current official result. The original `270` target assumption (200 Hyakunen + 70 ordinary J1) was withdrawn in [2026_LOCKBOX_PROTOCOL_CORRECTION.md](2026_LOCKBOX_PROTOCOL_CORRECTION.md).

These corrections restore the frozen chronology contract; they do not authorize tuning or further 2026-driven model selection.

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
| Frozen Cup-bridged J1+J2 Elo | Equal J1+J2 plus 145 regulation-time Cup events | 1.056566 | +0.000501 | **Closed** by the only formal run; C−A Brier `+0.0005719612389700757`, 2/5 folds improved; no tuning or adaptive follow-up |
| J2 initial=1400 | Fixed division prior | 1.056353 | +0.000288 | Closed; 1/5 folds improved |
| Promotion-Calibrated J1+J2 | Prior-season mean offset | 1.056243 | +0.000178 | Closed; pooled worse, first-time/early group worse |
| Returning-History Hybrid | J2 carry-over for returning teams | 1.056399 | +0.000333* | Closed; pooled worse, early group worse |
| Davidson | Draw-explicit Elo outcome model | N/A | N/A | Closed in freeze; no persisted pooled number found |
| Lineup Continuity | Previous two Starting XI overlap | N/A | N/A | Closed; pooled Log Loss did not improve per freeze |

The J2/promotion numbers come from [ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md](ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md) and [ELO_PROMOTION_RESET_EVALUATION.md](ELO_PROMOTION_RESET_EVALUATION.md). `*` The Hybrid document reports `+0.000333`; subtraction of the two separately rounded six-decimal scores gives `+0.000334`. The source document's difference is retained rather than inventing extra precision. The later Cup bridge dataset resolved all 145 regulation-time results and its separately frozen formal run is recorded in [CUP_BRIDGE_EVALUATION.md](CUP_BRIDGE_EVALUATION.md): A/B/C pooled Log Loss `1.056065401323764` / `1.057002111148765` / `1.05656623974119`, final decision **`CLOSE_CUP_BRIDGE_LANE`**.

## Deferred information and research discipline

FootyStats historical match xG, SofaScore player ratings, J.LEAGUE.jp final detailed match stats, AFC integration, and stable player identity remain data-path/identity tasks. J Stats team cumulative snapshots are a prospective archive only; no match-level reconstruction or model evaluation is approved. See [DATA_PIPELINE_STATUS.md](DATA_PIPELINE_STATUS.md) and [NEXT_DATA_RESEARCH_ROADMAP.md](NEXT_DATA_RESEARCH_ROADMAP.md).

2025 is a spent test and cannot be used for a new model choice. The first 70 completed 2026/27 matches are an opened interim lockbox and cannot be used for feature selection or tuning. Future feature groups require a new research cycle with point-in-time snapshots and independent validation. The 2020–2024 OOF cycle is closed to repeated small-feature searches.
