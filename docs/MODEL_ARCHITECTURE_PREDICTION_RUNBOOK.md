# Model Architecture Prospective Prediction Runbook

## Scope and frozen Candidate P

`src/modeling/model_architecture_prediction.py` generates prospective
Away/Draw/Home probabilities from the immutable Candidate P artifact:

```text
model_version: architecture_independent_poisson_v1
artifact: models/model_architecture/architecture_independent_poisson_v1/
artifact_hash: 655b5e46678c8ccce81b45b63833da5888fab94b4f5e267257c7496877b356f0
training_cutoff: 2025-12-06
```

The predictor validates the complete artifact bundle through
`load_poisson_artifact()`: payload checksums, metadata, training population,
pipeline structure, fitted state, version, cutoff, and the frozen artifact
hash. It never fits or updates Candidate P.

Candidate G is not implemented. It may later use the same output schema, but
must have its own frozen model version and artifact review.

## Cohort and next-date batch

The prospective boundary is fixed at:

```text
2026-09-22T07:16:21+09:00
```

The boundary defines the 300-fixture cohort. Completed rows remain cohort
members but are not targets. Each invocation selects the nearest unfinished
`match_date` and processes every unfinished fixture on that date as one batch;
later dates are not precomputed. The target date and batch size are derived
from the local schedule and are never hard-coded.

Every target requires an official, nonblank, unique `match_id`. `fixture_key`
is never substituted. Club names resolve through exact source/date-aware
TeamMaster aliases; fuzzy matching is prohibited.

## Strictly prior Elo chronology

Elo uses the repository's verified history chain and existing replay utility:

- initial rating 1500;
- K=30;
- home advantage=175 inside the update expectation;
- no season reset;
- `elo_diff = pre-match home rating - pre-match away rating`.

For target date `D`, only completed history with `match_date < D` is replayed.
Completed results on `D`, later results, target results, and same-date peer
results cannot enter the target state.

## Kickoff and no-backfill guard

Schedule dates and kickoff times are interpreted using the repository's J.League
local-time convention, `Asia/Tokyo`. Every kickoff must be an exact, valid
`YYYY-MM-DD HH:MM` local timestamp. The timezone-aware generation instant must
be strictly earlier than every kickoff in the selected batch. Missing,
malformed, ambiguous, equal, or already-passed kickoff chronology is a hard
failure. The pipeline never silently backfills a prediction after kickoff.

## Commands

Dry-run crosses schedule, cohort, identity, Elo, artifact, kickoff,
probability, existing-output, and append-plan validation, but writes nothing:

```powershell
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_prediction --dry-run
```

Production append:

```powershell
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_prediction
```

Review and push the implementation before running either command against the
real production paths.

## Append-only output

Output path:

```text
data/processed/predictions/model_architecture_prospective.csv
```

The immutable key is `(match_id, model_version)`. Existing keys are skipped and
reported; existing rows are never updated or overwritten. A malformed schema,
duplicate existing key, duplicate generated key, or invalid probability row is
a hard failure. Different frozen architecture model versions may share one
`match_id` in the common file.

The exact schema is:

```text
match_id
match_date
kickoff
home_team_id
away_team_id
prediction_generated_at
prospective_boundary
model_version
training_cutoff
history_cutoff_exclusive
artifact_hash
p_away
p_draw
p_home
predicted_class
```

Candidate P probabilities are used exactly in `[Away, Draw, Home]` order.
There is no recalibration, draw threshold, blending, or lambda output.

## Operational prohibitions

- Never refit Candidate P or regenerate its artifact from this predictor.
- Never backfill after kickoff.
- Never inspect outcomes or calculate Accuracy, Log Loss, Brier, or other
  performance metrics during prediction.
- Never merge or modify `xg_challenger_prospective.csv`.
- Never add Model A rows solely to populate this architecture output.
- Never fetch schedule, identity, history, or model data over the network.
