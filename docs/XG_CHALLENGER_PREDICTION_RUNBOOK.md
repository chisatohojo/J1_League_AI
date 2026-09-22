# XG Challenger Prospective Prediction Runbook

## Purpose and fixed boundary

`src/modeling/xg_challenger_prediction.py` produces prospective pre-match
probabilities from the frozen X0/X1 artifact bundle. It does not fit a scaler
or model and does not calculate Accuracy, Log Loss, Brier, or any other
performance measure.

The prospective boundary is fixed at:

```text
2026-09-22T07:16:21+09:00
```

The cohort is the 300 ordinary 2026/27 J1 fixtures that were unfinished at
that boundary. The opened first 80 matches are history only and cannot receive
new prospective records.

## One date per run

Each invocation reads only schedule identity/status fields and selects the
nearest unfinished calendar date in the prospective cohort. Every match on
that date is processed as one batch. Later fixtures are not predicted.

An official nonblank `match_id` is mandatory. `fixture_key` identifies the
scheduled pairing but is never promoted to an official match ID. If the local
schedule does not yet contain official IDs for the next batch, the run stops
without writing predictions.

## Pre-match chronology

Elo uses the existing frozen replay: initial rating 1500, K=30, home advantage
175, with `elo_diff = home_rating - away_rating`. Only completed matches from
dates before the target date are visible. Home advantage is used inside the
Elo expected-score update and is not added to `elo_diff`.

Rolling xG uses the last five eligible completed observations from 2025
ordinary J1 through the 2026 100 Year Vision League and ongoing 2026/27 J1.
Targets on the same date never enter one another's history. Match `33017`
remains excluded from history because its official-final time scope is
unresolved. Target score, result, actual class, and target xG are neither
required nor accepted by the feature builder.

## X0, X1, and Model A fallback

- X0 uses `elo_diff` and is generated only for the same rows eligible for X1.
- X1 uses the exact five-column order stored in artifact metadata.
- Neither scaler nor Logistic model is refitted.
- If either team's five-match xG history is unavailable, X0 and raw X1 are
  null and operational probabilities must equal the frozen Model A vector.
- No persisted Model A artifact currently exists in this repository. A run
  that actually needs fallback therefore hard-fails unless an externally
  validated frozen Model A probability provider is supplied. Reconstructing
  Model A by refitting is explicitly prohibited.

The class order is always `0=Away, 1=Draw, 2=Home`. `predicted_class` is plain
argmax; no draw threshold or probability adjustment exists.

## Artifact validation

Before probability generation, the pipeline validates:

- every SHA-256 entry in `checksums.sha256`;
- artifact and model versions;
- training cutoff and prospective boundary;
- X0/X1 ordered feature lists;
- class order and serialized feature widths;
- `future_rows_used == 0`.

Any discrepancy stops the run before output.

## Commands

Dry-run performs target selection, feature generation, artifact validation,
and probability generation but does not cross the append boundary:

```powershell
.venv\Scripts\python.exe -m src.modeling.xg_challenger_prediction --dry-run
```

Production run:

```powershell
.venv\Scripts\python.exe -m src.modeling.xg_challenger_prediction
```

The current local schedule has 300 future fixtures but no official `match_id`
for any of them. As of 2026-09-22, the nearest batch is two matches on
2026-10-09; both dry-run and production mode correctly stop before probability
generation until those IDs are published locally.

## Append-only output

The output path is:

```text
data/processed/predictions/xg_challenger_prospective.csv
```

The immutable key is `(match_id, model_version)`. Existing keys are reported as
`ALREADY_PREDICTED` behavior and skipped. Existing rows are never rewritten;
new rows are appended with a fixed schema. An invalid schema or duplicate key
already present in the file is a hard failure.

## Per-matchday operation

1. Publish the official schedule update containing next-date `match_id` values.
2. Publish completed match-level xG for all earlier dates.
3. Run targeted tests.
4. Run `--dry-run` and check target date/count, artifact validation, xG
   eligibility, and fallback readiness.
5. Run production once.
6. A repeat run must append zero rows and report existing keys only.

Do not precompute all remaining fixtures. Do not inspect outcomes when creating
records. Later evaluation must join outcomes in a separate workflow after the
prospective cohort is completed; this prediction module must not import or
calculate evaluation metrics.
