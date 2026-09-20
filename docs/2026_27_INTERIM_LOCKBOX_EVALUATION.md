# 2026/27 Interim Lockbox Evaluation

Evaluation date: 2026-09-20. This is the corrected formal evaluation of 70
completed ordinary J1 matches, not the full-season 380-match evaluation.
Future 310 scheduled matches were excluded.

## Preflight

Required inputs passed: 2025 J1=380, League Cup=56, Emperor's Cup=41;
2026 League Cup=4, Emperor's Cup=19, Hyakunen=200, target=70. The uniform
three-class Brier invariant was asserted before evaluation: `2/3 = 0.666667`.

Training used only ordinary J1 2015–2025 (3,514 matches). Hyakunen rows were
Elo-state/rest-history events only, never Logistic targets. Frozen Elo and
Logistic parameters were unchanged.

## Formal metrics

| model | correct / 70 | accuracy | log loss | Brier |
|---|---:|---:|---:|---:|
| A Elo-only | 40 / 70 | 57.14% | 0.996370 | 0.592515 |
| B Elo + Domestic Rest | 36 / 70 | 51.43% | 1.026020 | 0.613140 |
| B - A | -4 | -5.71 pp | +0.029650 | +0.020624 |

## Class diagnostics

Actual counts Away/Draw/Home: 22 / 15 / 33.

| model | recall Away/Draw/Home | predicted Away/Draw/Home |
|---|---|---|
| A | 77.27% / 0.00% / 69.70% | 33 / 0 / 37 |
| B | 77.27% / 0.00% / 57.58% | 39 / 1 / 30 |

Confusion matrices use rows=actual and columns=predicted, order Away/Draw/Home:

- A: `[[17, 0, 5], [6, 0, 9], [10, 0, 23]]`
- B: `[[17, 0, 5], [9, 0, 6], [13, 1, 19]]`

## Confidence and calibration

| model | mean max probability | mean P(Away/Draw/Home) |
|---|---:|---|
| A | 0.474946 | 0.352882 / 0.249249 / 0.397869 |
| B | 0.465653 | 0.391614 / 0.261914 / 0.346472 |

Fixed buckets `<.40`, `.40-.50`, `.50-.60`, `.60-.70`, `>=.70`:

| model | counts | correct | accuracy | mean confidence |
|---|---|---|---|---|
| A | 11,34,20,5,0 | 7,17,12,4,0 | 63.64%,50.00%,60.00%,80.00%,— | .3812,.4480,.5339,.6287,— |
| B | 14,34,18,4,0 | 5,18,10,3,0 | 35.71%,52.94%,55.56%,75.00%,— | .3824,.4458,.5342,.6171,— |

Actual rates Away/Draw/Home: 31.43% / 21.43% / 47.14%.

## Head-to-head

- Both correct: 36
- A only correct: 4
- B only correct: 0
- Both wrong: 30
- Argmax disagreement: 7; A correct on 4, B correct on 0.

## Leakage and freeze audit

- Target results were used only after each prediction.
- Future 310 matches were excluded.
- Rest used only prior-date J1, League Cup, Emperor's Cup and Hyakunen events.
- AFC was excluded.
- Hyakunen regulation-time results only were used for Elo; PK/extra-time
  winners were not used.
- Logistic training excluded Hyakunen and all 2026 target rows.
- Class order was `[0,1,2]`; probability rows summed to one.
- No post-lockbox retuning or specification change was performed.

Per-match output:
`data/processed/modeling/2026_27_interim_lockbox_predictions.csv`

The earlier run was invalid because 2026 Cup/Emperor inputs were absent and
used the wrong Brier reduction; it is not part of the formal result above.
