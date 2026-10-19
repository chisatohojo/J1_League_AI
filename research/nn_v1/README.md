# NN research v1 (Phase 1.1 chronology preparation)

Independent research only. Champion A, the formal architecture benchmark,
production predictions, dashboard, tasks and main are unchanged.

The exact experiment is frozen in `frozen-spec.json` before any historical fit.
No tuning, random split, calibration, 2025 evaluation or 2026 inputs are allowed.
2020--2024 are previously explored validation years, not a fresh holdout.
2025 is a spent test and is used only in the final 3,588-row research fit.

## Reproduce

Use Python 3.12.14 and the repository's existing `requirements-lock.txt`.
Run from this worktree, with `PYTHONDONTWRITEBYTECODE=1`:

```powershell
python -B -m pytest tests/test_nn_research_v1.py
python -B -m src.modeling.nn_research_v1 --source-root <existing-data-repository> --output <new-empty-output> --audit-only
```

The audit-only command does not fit/evaluate a model. Phase 1.1 authorizes only
chronology implementation/audit/tests. Historical and final training require a
later execution instruction; they are not performed as part of this preparation.
Output directories must not exist: partial or completed runs cannot be reused.
There is no automatic retry or parameter selection.

## Chronology

Features use continuous Elo (initial 1500, K=30, HA=175) and a cross-season
five-match club history, with separate feature and final-result events.
For normal fixtures, results are available from the next calendar day's midnight
in JST. A club appearing twice on a feature date is rejected.
Cold starts use empty-history zero totals and an explicit
0--5 matches-available count, never an imputed future value.

Registered fixture **30700** has these distinct fields:

| Field | JST value / meaning |
|---|---|
| Fixture identity | `jleague_data_site_sfms02:30700`, Urawa home / Kawasaki away |
| Feature timestamp | 2024-08-24 19:03, original kickoff |
| History cutoff | 2024-08-24 00:00; only earlier-date completed results |
| Recorded source date | 2024-11-22, retained without editing the source CSV |
| Final label | Draw, final 90-minute score 1-1 |
| Result-effective timestamp | 2024-11-23 00:00, conservative next-day boundary |

The feature vector is frozen before the original match day. The final result is
applied once after the resumption day, using the ratings/history current at that
result event. No intermediate 1-0 halftime score enters completed history.
The result-effective boundary is a policy, not an invented final-whistle time.

All three research models use this same event stream. Exact equality to frozen
Champion A metric values is no longer an acceptance gate: its old source-date
chronology differs. Future comparisons are informational, and the formal
benchmark/Champion A remain unchanged. No historical performance was computed.

`timing-v1_1/evidence-manifest.json` records the three explicitly supplied official
URLs, retrieval timestamps, exact raw-body SHAs, reviewed facts and limitations.
Full fetched HTML stays in an independent local evidence store, not GitHub.
`reviewed-interruptions.json` registers 30700 and 13 reviewed minute-scale
within-day interruptions. Every source fixture's cached page/metadata must pass
the research audit. Unknown timing notes, missing/changed reviewed notes,
unverified structures, metadata/SHA conflicts or unsupported annotations STOP.

`audit/`, `audit-strict/`, `frozen-spec.initial.json` and
`frozen-spec.phase1-hold.json` retain earlier audit-only evidence and superseded
policies. `audit-timing-v1_1/` and `frozen-spec.json` are current. The nine features,
model hyperparameters and 3,588-row population are unchanged. No fixture is
dropped and no original CSV date is moved.

Historical publication/correction timestamps are also not proven by the final
cached result tables. Computational coverage is not proof of contemporaneous
availability. This is an original-feature-time historical reconstruction, not
proof of the original official publication/correction state. See
`audit-timing-v1_1/DATA_AUDIT.md`, `TIMING_POLICY.md` and `STATUS.md`.

## Interpretation and artifacts

Primary metric: multiclass Log Loss; Brier is the mean **sum** of three squared
class errors (not divided by 3). Accuracy is descriptive. Classes/probabilities
are ordered Away=0, Draw=1, Home=2. AI PICK is plain argmax.

Each fold fits a new training-only scaler and classifier. MLP optimization-loss
curves are training loss by epoch, not new validation-driven learning-size
experiments. Convergence warnings, iteration count and wall time are retained;
warnings never trigger a retry or a larger iteration budget. A finite fitted
model at the fixed iteration limit may be reported as nonconverged, not as a
technical exception or evidence of production readiness. Nonfinite loss,
invalid classes/probabilities or another fit/evaluation exception stop the run.

The final scaler and MLP are research artifacts only, with hashes, versions,
feature order and training manifest. Never connect these artifacts to live
prediction. Do not load untrusted joblib/pickle files.

MLP parameter semantics: [scikit-learn documentation](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPClassifier.html).

Phase A: BLOCKED. Phase B: NOT_AUTHORIZED.
