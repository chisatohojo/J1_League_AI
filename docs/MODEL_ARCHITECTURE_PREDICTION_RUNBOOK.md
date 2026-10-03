# Model Architecture Prospective Prediction Runbook

## Scope and frozen candidates

`src/modeling/model_architecture_prediction.py` generates prospective
Away/Draw/Home probabilities from one explicitly selected immutable artifact:

```text
model_version: architecture_independent_poisson_v1
artifact: models/model_architecture/architecture_independent_poisson_v1/
artifact_hash: 655b5e46678c8ccce81b45b63833da5888fab94b4f5e267257c7496877b356f0
training_cutoff: 2025-12-06
```

```text
selector: lightgbm
model_version: architecture_lightgbm_form_v1
artifact: models/model_architecture/architecture_lightgbm_form_v1/
artifact_hash: 767ae8bce062386079118994182d067f782ad98576e3351890edf7586cecc516
training_cutoff: 2025-12-06
```

The predictor validates the complete artifact bundle through
`load_poisson_artifact()`: payload checksums, metadata, training population,
pipeline structure, fitted state, version, cutoff, and the frozen artifact
hash. It never fits or updates Candidate P.

Candidate G is loaded only through `load_lightgbm_artifact()`, which validates
the complete bundle, fitted LightGBM state, version, cutoff, 3,588-row training
population, and frozen artifact hash. The predictor never fits either
candidate or regenerates either artifact. Omitting `--model` retains the
Candidate P default. Accepted selectors are exactly `poisson` and `lightgbm`;
there is no combined mode.

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

## Candidate G form state

Candidate G uses the same target identity and `elo_diff` path as Candidate P,
plus exactly these ordered fields:

```text
home_last5_matches_available
away_last5_matches_available
home_last5_points
away_last5_points
home_last5_goals_for
away_last5_goals_for
home_last5_goals_against
away_last5_goals_against
```

Together with the leading `elo_diff`, these are the frozen nine model inputs.
Form is replayed through `add_form_features_to_targets()` over the supplied
chain `2015–2025 ordinary J1 → 2026 Hyakunen → completed 2026/27`. For target
date `D`, every history row must satisfy `match_date < D`; results on `D` and
later are excluded. Home/away appearances share one last-five history across
seasons and competitions. Availability is exactly wins + draws + losses.

Targets are read-only. No target score, result, synthetic 0-0, sentinel, or
dummy outcome is appended to history to obtain form state.

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
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_prediction --model poisson --dry-run
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_prediction --model lightgbm --dry-run
```

Production append:

```powershell
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_prediction --model poisson
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_prediction --model lightgbm
```

The legacy commands without `--model` remain aliases for Candidate P.

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

Both candidates use probabilities exactly in `[Away, Draw, Home]` order and
plain argmax. There is no recalibration, draw threshold, blending, feature
output, feature importance, or lambda output. Existing Candidate P rows remain
immutable when Candidate G rows with the same `match_id` are appended under
their different model version.

## Operational prohibitions

- Never refit Candidate P or Candidate G, or regenerate either artifact from
  this predictor.
- Never backfill Candidate G and never fabricate target outcomes for form.
- Never backfill after kickoff.
- Never inspect outcomes or calculate Accuracy, Log Loss, Brier, or other
  performance metrics during prediction.
- Never merge or modify `xg_challenger_prospective.csv`.
- Never add Model A rows solely to populate this architecture output.
- Never fetch schedule, identity, history, or model data over the network.
