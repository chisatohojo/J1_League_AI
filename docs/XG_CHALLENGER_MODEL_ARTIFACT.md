# XG Challenger model artifact

## Status

The frozen X0/X1 training protocol in [XG_CHALLENGER_FREEZE_SPEC.md](XG_CHALLENGER_FREEZE_SPEC.md) has been executed once. The resulting immutable bundle is:

```text
models/xg_challenger/xg_challenger_20260922_v1/
```

Model fitting and structural integrity checks were performed. No prediction, Accuracy, Log Loss, Brier score, confusion matrix, classification report, feature importance, coefficient interpretation, model selection, or future-target evaluation was performed.

## Model roles

- **X0 (`xg_x0_20260922_v1`)** is the matched-sample Elo-only comparator. It isolates the effect of training on the recent xG-eligible sample.
- **X1 (`xg_x1_20260922_v1`)** is the XG Challenger branch. It adds only the four frozen rolling xG means.
- **Model A** remains the unchanged Operational Champion. It was not loaded, refitted, serialized, or overwritten by artifact creation.

## Frozen training population

Exactly **594** completed, pair-available rows were used:

| Competition | Rows |
|---|---:|
| 2025 ordinary J1 | 328 |
| 2026 J1 100 Year Vision League | 186 |
| 2026/27 ordinary J1 opened first 80 | 80 |
| **Total** | **594** |

Validation before fitting confirmed:

- duplicate match IDs: 0
- missing model features: 0
- missing targets: 0
- identity mismatches between rolling xG and Elo histories: 0
- future prospective rows used: 0
- training cutoff: `2026-09-22T07:16:21+09:00`

The exact ordered match-ID list is in `training_manifest.csv` rather than being reconstructed from counts.

## Target

The fixed class order is:

- `0`: Away win
- `1`: Draw
- `2`: Home win

Class counts in the 594-row fitting population are:

| Away | Draw | Home |
|---:|---:|---:|
| 185 | 152 | 257 |

All targets use the 90-minute regulation result. PK and extra-time final winners are not labels. Hyakunen match `33017` is retained as a regulation draw target; its own unresolved-scope xG remains excluded from subsequent rolling history.

## Features and preprocessing

X0 feature order:

1. `elo_diff`

X1 feature order:

1. `elo_diff`
2. `home_last5_xg_for`
3. `home_last5_xg_against`
4. `away_last5_xg_for`
5. `away_last5_xg_against`

Each model has an independent `StandardScaler` fitted only on the same 594 training rows. The fitted dimensions are:

| Model | Scaler samples | Scaler features | Logistic coefficient shape | Intercept shape |
|---|---:|---:|---:|---:|
| X0 | 594 | 1 | `3 x 1` | `3` |
| X1 | 594 | 5 | `3 x 5` | `3` |

All scaler means/scales and Logistic coefficients/intercepts are finite. Their numerical states are stored in `metadata.json` for reproducibility, but they were not interpreted.

## Estimator

Both models use:

```text
StandardScaler
LogisticRegression(
    C=1,
    solver="lbfgs",
    max_iter=1000,
    random_state=0,
)
```

`class_weight` remains unset. No tuning, threshold, calibration, interaction, polynomial term, or alternate model was introduced. The fitted `classes_` values are exactly `[0, 1, 2]`.

## Artifact structure

```text
xg_challenger_20260922_v1/
├── x0_scaler.joblib
├── x0_model.joblib
├── x1_scaler.joblib
├── x1_model.joblib
├── training_manifest.csv
├── feature_schema.json
├── metadata.json
└── checksums.sha256
```

The binary model directory is under the existing ignored `models/` tree. Source code, tests, and this document remain reviewable repository changes.

## Hashes

| Artifact | SHA-256 |
|---|---|
| X0 scaler | `110c3be2a16f4fd9a1f40970542112e688c0e480dfbeec2e0efe788742d68fb7` |
| X0 model | `31b845726bdfcf17346a2071ee928b1b82bb7cf73fd1ab88851dc81fda27d2b9` |
| X1 scaler | `3edcd3c42e912c5f0fbc2620dbcb7263ec7db05d412894968a158673e4750f3a` |
| X1 model | `fda9c5992b34b269e3382063112222548985748505fdb2f2cc3aa329cb3d33cf` |
| Training manifest | `89563212324da61fd684ca90940a77a7811c06281be2ac207c801cebac24324f` |
| Feature schema | `0a3efc5f6397f8b9af6ab01e56f65a3ce5937c40679249c823e1c48abf098695` |
| Metadata | `31d144e21456aef54fc60ebf683bab6c384ac73b972c031e74604bb48c2152f0` |

Additional frozen identities:

- ordered training match-ID hash: `214896ccef0a6bfd2af4d2b1bc783091d29fe61b58f31b3df13740741ff410de`
- rolling feature specification hash: `bc4763e037af992222c7cd5e927fdae57414a55ca4b9bd721de4e1bc2a34c2b7`
- training protocol hash: `1dd0e210637a7281f2aeb975d0cd050a249128e2c53705da35bf19403b8b921a`

`checksums.sha256` covers the four binary objects plus the manifest, schema, and metadata. `metadata.json` additionally records every source dataset path and SHA-256, including TeamMaster, 2015–2025 ordinary J1 history, Hyakunen, the exact published first-80 revision, all three xG sources, and the rolling feature CSV.

## Training manifest

`training_manifest.csv` has one row per fitted match and contains:

- competition, season, match ID/date, and stable home/away team IDs;
- regulation target class;
- `elo_diff`;
- the four rolling xG model inputs;
- a canonical SHA-256 for each feature row.

It contains no prediction, probability, correctness field, loss, or metric.

## Reproducibility

The artifact builder performs these non-performance checks:

- independently rebuild the 594-row training frame twice and require exact equality;
- require exact feature order and target classes;
- save each scaler and model separately;
- reload every binary object and require exact numerical scaler/model state equality;
- record Python and dependency versions;
- record repository commit and dirty-worktree state at creation;
- hash every source and artifact.

Environment recorded at creation:

- Python `3.12.14`
- NumPy `2.5.3`
- pandas `3.0.5`
- scikit-learn `1.9.1`
- SciPy `1.18.1`
- joblib `1.6.0`

Joblib byte-for-byte equality across library implementations is not required. The manifest, feature values, targets, scaler state, class order, coefficient state, and source hashes define numerical reproducibility.

## Prospective boundary and fallback

The prospective boundary remains `2026-09-22T07:16:21+09:00`. The 300 fixtures that were future at that boundary were not read as results, used as labels, used for scaler fitting, or passed to either model.

For a future target:

- pair available: generate matched X0 and X1 branch predictions from these frozen artifacts;
- pair unavailable: do not impute and do not invoke X1; the operational X1 record uses the exact stored Model A probability vector;
- update point-in-time Elo and rolling xG state only after a completed date batch;
- never refit the X0/X1 weights.

Prediction generation, append-only prediction storage, and prospective evaluation are separate future tasks. They were not performed during artifact creation.
