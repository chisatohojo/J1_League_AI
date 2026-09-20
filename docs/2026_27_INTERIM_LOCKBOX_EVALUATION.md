# 2026/27 Interim Lockbox Evaluation

Evaluation date: 2026-09-20. This is the **chronology-corrected official
interim evaluation** of 70/380 completed 2026/27 ordinary J1 matches, not
the full-season final evaluation. The other 310 scheduled matches were not
used. The corrected results do not authorize model selection or retuning.

## Preflight

Hard-fail input counts passed: 2025 ordinary J1=380, J.League Cup=56,
Emperor's Cup=41; 2026 J.League Cup=4, Emperor's Cup=19, Hyakunen=200;
2026/27 completed target=70, full schedule=380 (310 future excluded).
The uniform three-class Brier invariant was asserted before evaluation:
`2/3 = 0.666667` under `mean(sum((p - one_hot)^2, axis=1))`.

Logistic training used **3,588** completed ordinary J1 matches from
2015–2025, including all 380 from 2025. The earlier `3,514` report was a
documentation count error, not a 74-match drop. Hyakunen and 2026/27
target matches were never Logistic training rows. Both models retained the
frozen Elo (`initial=1500`, `K=30`, `HA=175`) and Logistic
(`StandardScaler`, `C=1`, `lbfgs`, `max_iter=1000`, `random_state=0`) settings.
Model A used `elo_diff`; Model B additionally used the four frozen Domestic
Competitive Rest columns. AFC was not used.

## Chronology correction

- The previous Model B evaluation omitted completed 2026/27 target matches
  from later Domestic Rest history. The correction changes Rest features for
  **50 target matches / 97 team appearances**; the first is 2026-08-14,
  match ID `34527`.
- Target Elo and Rest now use calendar-date buckets: features for every match
  on a date are read before that date's target results/events update state.
  There are 15 date buckets, **12** containing multiple matches (and 11
  multi-match exact-kickoff buckets). Kickoff times exist for all 70, but
  verified final-whistle times do not; same-date
  batching is the conservative no-leakage policy.
- No club played twice on one target date, so the Elo-difference feature
  changed for **0/70** targets despite the safer replay implementation.
- Hyakunen's 200 regulation-time results update Elo and its dates update
  Domestic Rest; PK/extra-time winners do not replace 90-minute results.
  Hyakunen remains outside evaluation targets and Logistic training.

## Corrected interim metrics

| model | correct / 70 | accuracy | log loss | Brier |
|---|---:|---:|---:|---:|
| A Elo-only | 40 / 70 | 57.14% | 0.996370 | 0.592515 |
| B Elo + Domestic Rest | 38 / 70 | 54.29% | 1.001462 | 0.596178 |
| B - A | -2 | -2.86 pp | +0.005092 | +0.003663 |

Log Loss is primary, Brier secondary, and accuracy descriptive. Positive
Log Loss/Brier differences mean B is worse on this interim sample; no frozen
model specification is changed in response.

### Difference from the previous chronology-bugged report (new − old)

The prior report stated A: 40/70, 0.571429, 0.996370, 0.592515;
B: 36/70, 0.514286, 1.026020, 0.613140. It is superseded by the
corrected table above.

| model | correct | accuracy | log loss | Brier |
|---|---:|---:|---:|---:|
| A | 0 | 0.000000 | +0.000000 | +0.000000 |
| B | +2 | +0.028571 | -0.024558 | -0.016962 |

A's six-decimal values reproduce the earlier run. Its unrounded differences
from the previously rounded Log Loss/Brier figures are below `2e-7`.

## Class diagnostics

Actual counts Away/Draw/Home: **22 / 15 / 33** (31.43% / 21.43% /
47.14%). Class order throughout is `[0,1,2]` = Away/Draw/Home.

| model | actual Away correct/recall | Draw correct/recall | Home correct/recall | predicted Away/Draw/Home |
|---|---:|---:|---:|---|
| A | 17/22, 77.27% | 0/15, 0.00% | 23/33, 69.70% | 33 / 0 / 37 |
| B | 17/22, 77.27% | 0/15, 0.00% | 21/33, 63.64% | 35 / 0 / 35 |

Confusion matrices use rows=actual and columns=predicted, order Away/Draw/Home:

- A: `[[17, 0, 5], [6, 0, 9], [10, 0, 23]]`
- B: `[[17, 0, 5], [6, 0, 9], [12, 0, 21]]`

## Confidence and calibration

| model | mean max probability | mean P(Away/Draw/Home) |
|---|---:|---|
| A | 0.474946 | 0.352882 / 0.249249 / 0.397869 |
| B | 0.475563 | 0.359232 / 0.250876 / 0.389891 |

Fixed max-probability buckets (`<.40`, `[.40,.50)`, `[.50,.60)`,
`[.60,.70)`, `>=.70`):

| bucket | A count | A correct | A accuracy | A mean confidence | B count | B correct | B accuracy | B mean confidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| <.40 | 11 | 7 | 63.64% | .3812 | 12 | 7 | 58.33% | .3829 |
| [.40,.50) | 34 | 17 | 50.00% | .4480 | 35 | 15 | 42.86% | .4514 |
| [.50,.60) | 20 | 12 | 60.00% | .5339 | 17 | 12 | 70.59% | .5379 |
| [.60,.70) | 5 | 4 | 80.00% | .6287 | 6 | 4 | 66.67% | .6253 |
| >=.70 | 0 | 0 | — | — | 0 | 0 | — | — |

Actual rates Away/Draw/Home: 31.43% / 21.43% / 47.14%.

## Head-to-head

- Both correct: 38
- A only correct: 2
- B only correct: 0
- Both wrong: 30
- Argmax disagreement: 2; A correct on 2/2 (100%), B correct on 0/2 (0%).

## Leakage and freeze audit

- All same-date target features were generated from the Elo/Rest state at
  the start of that date; target results and target Rest events entered state
  only for later dates. The target's own and future results did not enter its
  features. No same-date target result was available to a peer prediction.
- Future 310 schedule rows were excluded from fit, replay and evaluation.
- Rest used only prior-date ordinary J1, J.League Cup, Emperor's Cup and
  Hyakunen events. Completed earlier target J1 matches were carried forward.
- AFC was excluded.
- Hyakunen regulation-time results only were used for Elo; PK/extra-time
  winners were not used.
- Logistic training contained exactly 3,588 ordinary J1 rows from
  2015–2025; it excluded Hyakunen and all 2026 target rows. Scaler fit used
  those training rows only.
- Class order was `[0,1,2]`; probability rows summed to one.
- Frozen features, K, HA, C and the Rest definition were not tuned or
  changed after observing results. Only chronology implementation was
  corrected.

Per-match output:
`data/processed/modeling/2026_27_interim_lockbox_predictions.csv`

The first preliminary run was invalid because 2026 Cup/Emperor inputs were
absent and it used the wrong Brier reduction. The subsequent report included
those inputs and the correct Brier scale but retained the Domestic Rest
chronology bug. Neither prior run is the current official interim result.
The full-season 380-match evaluation remains future work under the same
frozen specifications.
