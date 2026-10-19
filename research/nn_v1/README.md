# NN research v1 (Phase 1)

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

The audit-only command does not fit any model. The historical execution command
is blocked until the chronology issue below is resolved. There is no
acknowledgement flag to bypass it.
Output directories must not exist: partial or completed runs cannot be reused.
There is no automatic retry or parameter selection.

## Chronology

Features use only ordinary J1 results on earlier recorded match dates, continuous
Elo (initial 1500, K=30, HA=175), and a cross-season five-match club history.
All same-date feature reads precede result updates. A club appearing twice on a
date is rejected. Cold starts use empty-history zero totals and an explicit
0--5 matches-available count, never an imputed future value.

Source limitation requiring explicit disposition: match 30700 began on
2024-08-24 and resumed on 2024-11-22. The existing source and frozen reference use
the latter date. Those features are not features before its original kickoff.
The user explicitly requires original-kickoff timing. Therefore historical
fitting/evaluation and the final research-model fit are **HOLD / NOT_RUN**.
Neither acknowledging the resumption date nor silently dropping/moving the row
can authorize fitting. No trained historical model, performance comparison or
evaluation graph is claimed. The implementation and synthetic tests are saved
for continuation after a chronology policy is established.

`audit/` and `frozen-spec.initial.json` retain the initial, pre-clarification
audit/spec (no historical fits). `audit-strict/` and `frozen-spec.json` supersede
their chronology policy. The nine features and model hyperparameters are
unchanged. No source date or formal benchmark decision is modified.

Historical publication/correction timestamps are also not proven by the final
cached result tables. Computational coverage is not proof of contemporaneous
availability. See `audit-strict/DATA_AUDIT.md` and `STATUS.md`.

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
