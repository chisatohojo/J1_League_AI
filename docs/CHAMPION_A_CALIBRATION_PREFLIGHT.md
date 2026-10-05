# Champion A Calibration Preflight Evidence

Status: `CHAMPION_A_CALIBRATION_PREFLIGHT_READY_FOR_REVIEW`.

This is REAL READ-ONLY PREFLIGHT evidence only. It records no calibration
performance, fitted challenger coefficients, transformed probabilities, candidate
ranking/selection, or formal research decision. Formal execution remains separately
reviewed and authorized; neither this document nor its final gate grants authority.

## 1. Authority and reviewed provenance

- Task authorization: `APPROVED_FOR_REAL_READ_ONLY_PREFLIGHT`, supplied in the
  dedicated preflight-only instruction on 2026-10-05 (JST).
- Task reference: user attachment
  `c09ac1aa-410a-4f4d-9436-7593e066c834`.
- Initial/reviewed implementation HEAD:
  `4ec25ca9a8fefcb43f9271d114ea0cdf29dd1f3b`
  (`feat: implement Champion A calibration evaluation`).
- Initial working tree: clean; exact initial HEAD gate: PASS.
- Specification: [CHAMPION_A_CALIBRATION_RESEARCH_SPEC.md](CHAMPION_A_CALIBRATION_RESEARCH_SPEC.md).
- Specification commit: `b5354705f1a7a32e64e2a0d484e22cd55f59d483`.
- Pinned/committed/live specification SHA-256:
  `821e2a35e99bb7c785cd5405aa241ba898ef452123428199ac671a6c50df2e07`.
- Implementation path: `src/modeling/champion_a_calibration_evaluation.py`.
- Implementation file SHA-256, reported by the real preflight:
  `27bb9708edb46e0d6798778effa34d5e222731351de63775a576ad0ef48d5286`.
- Implementation bytes match the committed file at reviewed HEAD: PASS.
- Specification commit is an ancestor of reviewed HEAD: PASS.
- No evaluator, tests, specification, dependencies, or accepted artifact changed.

## 2. Execution and safety reconfirmation

Preflight launch: **2026-10-05 19:25:42 JST** / **10:25:42 UTC**.
Post-run evidence/immutability verification timestamp: **19:26:15 JST** /
**10:26:15 UTC** on the same date.

The already-reviewed synthetic suite was run once, before the real preflight:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_champion_a_calibration_evaluation.py -q
```

Result: **131 passed in 97.04s (0:01:37)**; exit code 0. These tests use synthetic
arrays, DataFrames, temporary equivalents, and production/network guards. Temporary
synthetic fits are not real OOF calibrator fits. Full pytest: NOT RUN.

Import and help reconfirmation both exited 0:

```powershell
python -c "import src.modeling.champion_a_calibration_evaluation"
.\.venv\Scripts\python.exe -m src.modeling.champion_a_calibration_evaluation --help
```

Import safety: PASS. Help safety: PASS. Neither command evaluates or opens
production evidence. `PYTHONDONTWRITEBYTECODE=1` was set for Python commands;
pytest cache-provider writes were disabled through
`PYTEST_ADDOPTS='-p no:cacheprovider'`. These prevent cache writes and do not change
the frozen evaluator/model/optimizer contract.

The following real evaluator CLI was invoked **exactly once**, with no flags:

```powershell
.\.venv\Scripts\python.exe -m src.modeling.champion_a_calibration_evaluation
```

- Default preflight invocation count: **1**.
- Default preflight exit code: **0**.
- Default preflight status: **`PREFLIGHT_PASS`**.
- Automatic retry: **0**.
- Formal CLI executions: **0**.
- `candidate_fit = NOT RUN`.
- `candidate_transform = NOT RUN`.
- `candidate_metrics = NOT RUN`.
- `marker_created = false`.
- `result_created = false`.

## 3. Immutable accepted inputs

Only the two frozen accepted evidence files were read for real artifact
validation. No historical source CSV, TeamMaster, model bundle, alternative OOF,
2025, or 2026+ evidence was opened or discovered.

| Input | SHA-256 before preflight | SHA-256 after preflight | Outcome |
| --- | --- | --- | --- |
| `data/processed/model_diagnostics/champion_a_oof_2020_2024.csv` | `cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59` | `cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59` | Expected SHA matches; unchanged |
| `data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json` | `b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10` | `b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10` | Expected SHA matches; unchanged |

Artifact SHA/schema/provenance validation: PASS. Exact 34-column order/dtypes,
1678 rows, unique canonical target IDs, recorded provenance/reference contract,
finite strictly positive raw probabilities and sum tolerance: PASS. Recorded
manifest reference constants were checked, not recomputed as evaluation scores.
The formal A-only baseline metric recomputation was NOT RUN.

| OOF year | Rows |
| --- | ---: |
| 2020 | 306 |
| 2021 | 380 |
| 2022 | 306 |
| 2023 | 306 |
| 2024 | 380 |
| Total accepted OOF | 1678 |

No probability repair, clipping, normalization, smoothing, or calibration mapping
was performed. Structural validation of saved derived columns is not a challenger
performance calculation.

## 4. Rolling chronology and identity

2020 is calibration warm-up only. Evaluation years are exactly 2021-2024.

| Evaluation year | Prior calibration years | Training n | Evaluation n |
| --- | --- | ---: | ---: |
| 2021 | 2020 | 306 | 380 |
| 2022 | 2020-2021 | 686 | 306 |
| 2023 | 2020-2022 | 992 | 306 |
| 2024 | 2020-2023 | 1298 | 380 |

- Exact rolling counts: PASS.
- Canonical relative order and frozen per-year/train/evaluation ordered-ID hashes:
  PASS.
- Train/evaluation ID disjointness: PASS.
- `max(train.match_date) < min(eval.match_date)` for every fold: PASS.
- All three classes present in every prior training fold; class order `[0,1,2]`
  (Away/Draw/Home): PASS.
- Pooled evaluation target count: **1372**, not the 1678-row diagnostic pool.
- Pooled ordered-ID SHA-256:
  `ae3c676eb346a2e1a77271c1a2b1ed8d5008adadce796d05d555394a61b3708e`:
  PASS.

These are population/chronology assertions, not fitted-fold evaluations.

## 5. Candidate, optimizer, and runtime contract

Registry validation: PASS; exactly **A0 / C1 / C2 / C3**, in that order, with
0 / 1 / 2 / 3 free coordinates. Identity initialization, tau lower bound, fixed
Away bias, and unbounded free class biases match the freeze. No candidate was
fitted, applied, scored, ranked, or selected on real evidence.

Optimizer static contract validation: PASS. The runtime exposes
`scipy.optimize.minimize`; the implementation retains `method='L-BFGS-B'`,
`jac=True`, `args=()`, `tol=None`, `callback=None`, and exactly these options:

```text
maxcor = 10
maxiter = 15000
maxfun = 15000
ftol = 2.220446049250313e-09
gtol = 1e-05
maxls = 20
```

No optimizer was called on real OOF rows. Exact call/bounds/options, fresh identity
starts, and no-retry behavior were reconfirmed only by the synthetic suite.

| Runtime component | Observed value |
| --- | --- |
| Platform | Windows-11-10.0.26200-SP0 |
| Python | 3.12.14 |
| numpy | 2.5.3 |
| pandas | 3.0.5 |
| scipy | 1.18.1 |
| scikit-learn | 1.9.1 |
| `requirements.txt` SHA-256 | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` |
| `requirements-lock.txt` SHA-256 | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` |

Runtime/dependency contract: PASS. No upgrades, fallbacks, or contract changes.

## 6. Absence checks, change boundary, and non-actions

Existence checks only, before and after preflight and again before commit:

- `data/processed/model_calibration/formal_calibration_attempt.json`: ABSENT.
- `docs/CHAMPION_A_CALIBRATION_EVALUATION_RESULT.md`: ABSENT.
- This preflight document was absent before execution/creation; no overwrite.

Tree-state evidence:

- Initial tree: clean at the exact reviewed implementation HEAD.
- After tests and real preflight, before this document: clean, including all
  nonignored untracked-file checks.
- Final authorized change boundary: this new preflight document only.
- `git diff --check` and staged document whitespace check: PASS.
- Docs-only commit leaves a clean working tree; final check is reported in the
  task handoff. No source/test/spec/dependency change is included.

No other production dataset/model/cache/result was created by preflight. Evidence
is the reviewed read-only preflight call path, explicit NOT RUN/false output,
unchanged accepted-pair hashes, absence checks, clean post-execution tree, and
disabled bytecode/pytest cache writes. Only isolated temporary synthetic fixtures
were created by tests; no permanent derived artifacts were produced.

| Action / use | This task |
| --- | --- |
| Real C1 / C2 / C3 fits | 0 / 0 / 0 |
| Minimize on real OOF rows | NO |
| Real calibration probability transformations | 0 |
| Real candidate performance / deltas / selection | NOT RUN |
| Formal research decision | NOT PRODUCED |
| Formal evaluation / formal CLI | NO |
| Formal marker created | NO |
| Formal result created | NO |
| Champion A fit/refit / predict_proba / Elo replay | NOT RUN |
| OOF regeneration / diagnose() | NOT RUN |
| Historical source CSV / TeamMaster / model bundle access | NO |
| 2025 used | NO |
| 2026+ used / outcomes inspected / saved predictions rewritten | NO |
| Network / HTTP / collection | NO |
| Production prediction / activation / artifact creation | NO |
| Tuning / adaptive follow-up | NOT RUN |
| Full pytest | NOT RUN |
| Push | NOT PERFORMED |

## 7. Final preflight gate

`READY_FOR_ONE_CHAMPION_A_CALIBRATION_FORMAL_EVALUATION`

This gate means ready for **separate review and explicit formal authorization
only**. It does not authorize formal execution by itself. Any future authority
must identify its own reviewed approved execution HEAD, including this docs-only
commit if reviewed, and a distinct formal task reference. No real calibration
research result exists from this preflight.
