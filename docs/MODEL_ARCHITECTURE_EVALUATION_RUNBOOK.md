# Frozen Model Architecture Evaluation Runbook

## Status and scope

`src/modeling/model_architecture_evaluation.py` implements the frozen
historical comparison of exactly three candidates:

```text
A = Elo-only multinomial Logistic reference
P = architecture_independent_poisson_v1
G = architecture_lightgbm_form_v1
```

Implementation tests and synthetic fits are not the formal benchmark. This
implementation task does not authorize a real preflight or formal execution.
The real commands may be used only after the implementation commit has been
pushed, reviewed, and separately approved.

The retrospective source is ordinary J1 only, seasons 2015–2024, exactly
3,208 matches. The evaluator does not load 2025, Hyakunen, opened 2026/27,
future fixtures, prospective predictions, or operational P/G artifacts.

## Frozen chronology

The evaluator first constructs one complete chronological 2015–2024 state and
only then splits folds. Elo uses initial 1500, K=30, home advantage=175 for the
update expectation, no season reset, and same-date conservative batching.
Candidate G form is created once through `build_lightgbm_state_features()` over
that same full stream.

Consequently, a validation match may use completed matches from earlier dates
in its own validation season. Its own result, same-date results, and later
results cannot enter its pre-match state.

Frozen folds are:

| Validation | Training seasons | Train | Validation |
|---:|---|---:|---:|
| 2020 | 2015–2019 | 1,530 | 306 |
| 2021 | 2015–2020 | 1,836 | 380 |
| 2022 | 2015–2021 | 2,216 | 306 |
| 2023 | 2015–2022 | 2,522 | 306 |
| 2024 | 2015–2023 | 2,828 | 380 |

Pooled validation contains exactly 1,678 rows in fold order 2020 through 2024.

## Read-only preflight

After push/review, the first separately approved operational step is:

```powershell
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_evaluation --preflight
```

The default command is also preflight, but the explicit flag is preferred.
Preflight may load and validate the 2015–2024 source, build shared Elo and G
state, validate fold identities and P observation schemas, and fit/evaluate
Candidate A. It must not fit or predict P/G, create the formal marker, or write
the formal result.

Candidate A must reproduce every frozen fold Log Loss and the pooled reference
within absolute tolerance `1e-12`. Successful output is:

```text
READY_FOR_ONE_FORMAL_MODEL_ARCHITECTURE_BENCHMARK
```

Any `BLOCKED_REFERENCE_MISMATCH` stops the cycle. Do not modify parameters or
run formal evaluation.

## Formal one-shot

Inspect the preflight output. Only after explicit approval run exactly:

```powershell
.\.venv\Scripts\python.exe -m src.modeling.model_architecture_evaluation --formal --confirm-one-shot
```

Both flags are mandatory. Formal execution performs the complete preflight
first, then requires both the result and marker to be absent. It atomically
creates:

```text
data/processed/model_architecture/formal_benchmark_attempt.json
```

before any real P/G fit. The marker remains after success or failure. Never
delete or rename it to force another attempt, and never rerun formal after any
attempt.

The reserved result is:

```text
docs/MODEL_ARCHITECTURE_BENCHMARK_RESULT.md
```

The writer uses exclusive-create semantics and never overwrites a result.
Candidate-specific formal failure becomes `INCONCLUSIVE_NO_TUNING` and does not
trigger retry or parameter changes. Shared source/reference corruption aborts.

## Frozen metrics and decisions

Only multiclass Log Loss, multiclass Brier, and descriptive Accuracy are
calculated. Class order is `[0,1,2] = Away / Draw / Home`; prediction uses plain
argmax. There is no threshold, calibration, blending, feature importance, or
subgroup analysis.

P and G qualify individually only when all are true:

1. pooled Log Loss is lower than A;
2. fold Log Loss is lower than A in at least three of five folds;
3. pooled Brier is less than or equal to A.

If both qualify, retain lower pooled Log Loss. At an absolute Log Loss tie of
`1e-12` or less, retain lower pooled Brier. At a Brier tie of `1e-12` or less,
retain P. Candidate A remains Champion/reference regardless of the result.

Do not tune, add variants, change features or parameters, retry a candidate,
or perform adaptive follow-up after seeing the formal result.

## Prospective immutability

Historical results never replace Candidate A and never alter existing
prospective state. Do not modify or regenerate:

```text
models/model_architecture/architecture_independent_poisson_v1/
models/model_architecture/architecture_lightgbm_form_v1/
data/processed/predictions/model_architecture_prospective.csv
data/processed/predictions/xg_challenger_prospective.csv
```

Do not inspect prospective probabilities or outcomes as part of preflight or
formal evaluation.
