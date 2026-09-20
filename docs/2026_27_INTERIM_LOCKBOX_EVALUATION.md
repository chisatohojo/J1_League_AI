# 2026/27 Interim Lockbox Evaluation

> **INVALID / PRELIMINARY RUN — not a formal result.** The original run used
> incomplete 2026 Cup/Emperor inputs and used the wrong multiclass Brier
> reduction. The metrics below are retained only as an audit trail and must
> not be used for model selection. A corrected rerun is required after the
> preflight fixes.

Evaluation date: 2026-09-20

This is a one-shot evaluation of the frozen Model A and Model B. The 70
completed ordinary J1 matches are the target; the remaining 310 scheduled
matches are excluded. No specification, parameter, feature, or threshold was
changed after observing these results.

## Frozen protocol

- Training: 3,514 completed ordinary J1 matches from 2015–2025.
- Model A: `elo_diff` only.
- Model B: `elo_diff` plus the four frozen Domestic Competitive Rest columns.
- Elo: initial 1500, K=30, home advantage=175 (HA only in expected-score calculation).
- Logistic: StandardScaler and LogisticRegression(C=1, solver=`lbfgs`, max_iter=1000, random_state=0).
- Hyakunen matches are Elo-state/rest-history events only, never Logistic targets.
- Class order: Away=0, Draw=1, Home=2.

## Headline metrics

| model | correct / 70 | accuracy | log loss | Brier |
|---|---:|---:|---:|---:|
| A Elo-only | 40 / 70 | 57.14% | 0.996370 | 0.197505 |
| B Elo + Domestic Rest | 30 / 70 | 42.86% | 1.080188 | 0.215564 |
| B - A | -10 | -14.29 pp | +0.083818 | +0.018059 |

## Class diagnostics

Actual counts (Away/Draw/Home): 22 / 15 / 33.

| model | Away recall | Draw recall | Home recall | predicted Away/Draw/Home |
|---|---:|---:|---:|---:|
| A | 77.27% | 0.00% | 69.70% | 33 / 0 / 37 |
| B | 86.36% | 0.00% | 33.33% | 54 / 0 / 16 |

Confusion matrices use rows=actual and columns=predicted, in the order
Away/Draw/Home:

Model A:

```text
[[17, 0, 5], [6, 0, 9], [10, 0, 23]]
```

Model B:

```text
[[19, 0, 3], [13, 0, 2], [22, 0, 11]]
```

## Confidence and calibration sanity

| model | mean max probability | overall accuracy | mean P(Away/Draw/Home) |
|---|---:|---:|---|
| A | 0.474946 | 57.14% | 0.352882 / 0.249249 / 0.397869 |
| B | 0.479658 | 42.86% | 0.452560 / 0.272803 / 0.274637 |

Fixed confidence buckets (`<.40`, `.40-.50`, `.50-.60`, `.60-.70`, `>=.70`):

| model | counts | accuracy by bucket | mean confidence by bucket |
|---|---|---|---|
| A | 11, 34, 20, 5, 0 | 63.64%, 50.00%, 60.00%, 80.00%, — | .3812, .4480, .5339, .6287, — |
| B | 15, 26, 22, 6, 1 | 26.67%, 38.46%, 59.09%, 50.00%, 0.00% | .3769, .4437, .5432, .6226, .7019 |

Actual rates Away/Draw/Home are 31.43% / 21.43% / 47.14%.

## Head-to-head

- Both correct: 28
- A only correct: 12
- B only correct: 2
- Both wrong: 28
- Different argmax: 21 matches; on this fixed subset A was correct on 12 and B on 2.

## Leakage audit

- Target rows: 70; target IDs unique.
- Future schedule rows excluded: 310.
- Logistic targets: ordinary J1 2015–2025 only.
- Target result was used only after its prediction, for evaluation and subsequent Elo state.
- Hyakunen 200/200 regulation results were used for Elo chronology, not Logistic fitting.
- Rest history was restricted to events strictly earlier than each target date; AFC was not read.
- Probability rows sum to one and class order is `[0, 1, 2]`.

The generated per-match predictions are stored in the ignored working artifact
`data/processed/modeling/2026_27_interim_lockbox_predictions.csv`.

## Freeze conclusion

This is an interim 70-match generalization result, not the completed 380-match
season evaluation. Model A remains the frozen reference and Model B remains the
frozen challenger. The result does not authorize post-lockbox tuning or model
specification changes.
