# Model A Operational Champion Artifact

## Purpose

This bundle persists the already-frozen operational Champion, Model A, so the
prospective xG pipeline can execute its exact fallback without refitting. It is
not a new model-selection run. No feature, training population, Elo setting,
Logistic parameter, threshold, or calibration rule was changed.

No Accuracy, Log Loss, Brier, confusion matrix, classification report,
holdout prediction, or prospective prediction was calculated while creating
the artifact.

## Relationship to the freeze

The source-of-truth specifications remain:

- `docs/MODEL_FREEZE_BEFORE_2026.md`
- `docs/2026_27_INTERIM_LOCKBOX_EVALUATION.md`
- `docs/PROJECT_STATUS_2026_09_20.md`

The artifact records hashes for those documents and all eleven ordinary-J1
training CSVs. It reproduces the fixed implementation used by the operational
Champion rather than selecting an alternative implementation.

## Frozen training population

Only completed ordinary J1 matches from 2015 through 2025 are included:

| Season | Rows |
|---:|---:|
| 2015 | 306 |
| 2016 | 306 |
| 2017 | 306 |
| 2018 | 306 |
| 2019 | 306 |
| 2020 | 306 |
| 2021 | 380 |
| 2022 | 306 |
| 2023 | 306 |
| 2024 | 380 |
| 2025 | 380 |
| **Total** | **3,588** |

The 2026 100 Year Vision League, the opened first 80 ordinary 2026/27 matches,
and the prospective future 300 fixtures are excluded. `future_rows_used=0`.

Target mapping is `0=Away`, `1=Draw`, `2=Home`. The resulting class counts are:

- Away: 1,231
- Draw: 897
- Home: 1,460

## Feature and Elo semantics

The one and only feature is:

```text
elo_diff = home pre-match Elo - away pre-match Elo
```

Elo is replayed chronologically using initial rating 1500, K=30, and home
advantage 175 inside expected-score calculation only. Home advantage is not
added to `elo_diff`.

## Model contract

The preprocessing/model pair is:

```text
StandardScaler
LogisticRegression(C=1, solver="lbfgs", max_iter=1000, random_state=0)
```

The scaler is fitted on all and only the 3,588 training rows. Serialized shapes
are one scaler input feature, Logistic coefficient shape `(3, 1)`, and
intercept shape `(3,)` with class order `[0, 1, 2]`.

## Artifact structure

```text
models/model_a/operational_champion_20260922_v1/
  scaler.joblib
  model.joblib
  metadata.json
  training_manifest.csv
  checksums.sha256
```

`training_manifest.csv` has one row per training match and contains season,
match identity/date, stable home/away IDs, target class, and pre-match
`elo_diff`. `metadata.json` records training coverage, class counts, feature
and parameter contracts, environment versions, numeric model state, source
hashes, and freeze-document references.

Published SHA-256 values:

- training manifest: `eea7498fabac6acc79a9c297468b470702288b61736b63d90214d741ab8fb32a`
- scaler: `a8a5f176944049c6825071b580c5fe40f5a5fb28f504f8880d028deaf2494750`
- model: `60636e4652bce98b76c394310947b1b8923a8bf18a640d9e7976497989ed54be`
- metadata: `bd1eb92c25bdb56a836ef7bfe3fcb13b0137a2ece01b6095e7d100e1f5afdd19`

Binary artifacts remain under the repository's existing ignored `models/`
policy; their local presence is an operational preflight requirement.

## Deterministic reproduction

The builder independently reconstructs the training frame twice and requires
exact equality. It then fits the frozen state twice and requires exact scaler
means/scales and Logistic classes/coefficients/intercepts. Finally, serialized
objects are reloaded and compared with the in-memory state.

Serialization-byte equality across unrelated library environments is not the
definition of model equivalence. Within the recorded environment, every file
is protected by SHA-256.

## Prospective fallback use

`src/modeling/xg_challenger_prediction.py` validates every Model A checksum,
metadata contract, feature width, and class order before use. If xG is
unavailable for either side, it passes only `elo_diff` through the persisted
scaler and `predict_proba`; it never calls `fit` or `fit_transform`.

Missing files, metadata mismatch, feature-order mismatch, or checksum mismatch
are hard failures. X0/X1 artifacts and behavior are unchanged.

