# Champion A Calibration Research Specification

Freeze date: 2026-10-05 (JST).

Reviewed source HEAD: `052ee98041bc114685bf5b260590e17087190345` (`docs: diagnose Champion A OOF residuals`). Initial working tree: clean.

Final freeze gate: `FROZEN_FOR_ONE_CHAMPION_A_CALIBRATION_IMPLEMENTATION`.

This is a DOCS-ONLY research freeze. It authorizes later evaluator implementation and synthetic tests only, not real calibration fitting, transformation, evaluation, marker creation, result generation, or prospective calibration.

## 1. Scope

Research question: can low-dimensional, strictly-prior multiclass probability recalibration improve proper scoring performance over unchanged Champion A?

The entire research population is the accepted 2020-2024 row-level Champion A OOF artifact. Calibration changes only a probability mapping. Base probabilities remain immutable; no earlier Champion A OOF, base-model refit, prediction, Elo replay, or new source is needed.

This is not a new-information or architecture experiment. It does not test Elo states, dynamic K, season reset, home advantage, lineup, xG, draw-propensity features, base-model class weights, or alternative architectures. Diagnostic metadata cannot become calibration inputs.

Allowed in this freeze: existing docs/code/dependency reads, accepted-pair read-only integrity/identity/chronology inspection, mathematical design, one specification document, static validation, and commit. No real calibration computation is authorized here.

## 2. Motivation

Authoritative evidence: [Champion A targeted diagnostic](CHAMPION_A_OOF_TARGETED_DIAGNOSTIC.md), especially sections 5, 6, 9, and 13-16. Its unchanged final gate is `PROCEED_TO_CALIBRATION_RESEARCH_SPEC`.

- Away is overpredicted in 4/5 diagnostic years (2021-2024).
- Draw is underpredicted in 4/5 diagnostic years (2021-2024).
- Both class/directions pass every frozen Gate A component, including nonsparse fixed-bin recurrence.
- Both persist in the established/non-first-five core: Away support 2021-2024; Draw support 2020/2021/2022/2024.
- Neither direction is localized to the frozen narrow transition subgroup. Every yearly share is below 0.80.
- Gate B evidence also passed, but calibration had frozen priority; no parallel transition decision was made.
- These diagnostic facts do NOT prove that any calibrator improves Log Loss.

Bias magnitudes are motivation, not parameter targets. In particular, no "+2.5% Draw" rule, positive-only draw bias constraint, class-frequency matching rule, or selected-bin calibration is introduced. Temperature and the two free biases are determined only by the frozen training objective in a later separately authorized attempt.

## 3. Reuse/generalization firewall

2020-2024 has already been inspected diagnostically. The proposed retrospective evaluation is a RESEARCH SCREEN, not an untouched final generalization test. Strictly-prior fitting prevents target-year training leakage; it does not erase human reuse of this historical evidence.

Even a passing result is not confirmed unseen improvement, a new Champion, or final operational gain. A pass can authorize only a separately frozen prospective calibration evaluation at a NEW boundary, using future previously unseen predictions.

Champion A's expanding-window base model differs between OOF years. This is an intentional screen of one shared calibration family trained on prior-year base probabilities, not an assertion that a single base-model checkpoint generated every year. Interyear distribution drift remains a limitation. It does not invalidate the verified chronological splits and does not justify regenerating earlier OOF.

2025 remains spent. Opened 2026/27 is forbidden for selection, parameter/optimizer design, tie-breaking, or gates.

## 4. Accepted immutable inputs

Exactly two data files may be loaded by the future evaluator; no discovery/globs or alternative artifacts:

| Input | Path | Exact SHA-256 |
| --- | --- | --- |
| Accepted OOF CSV | `data/processed/model_diagnostics/champion_a_oof_2020_2024.csv` | `cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59` |
| Accepted manifest | `data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json` | `b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10` |

Provenance and schema authority: [OOF diagnostic freeze specification](CHAMPION_A_OOF_DIAGNOSTIC_FREEZE_SPEC.md), sections 7-9.

| Item | Frozen requirement |
| --- | --- |
| Schema version | `champion_a_oof_diagnostic_v1` |
| Purpose | `diagnostic_only_not_formal_evaluation_not_model_input` |
| Generator commit | `6481780f208ffe95294bdb426a3e572a82a34a98` |
| Generator path / SHA | `src/modeling/champion_a_oof_diagnostic.py` / `40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78` |
| Generation task reference | `champion-a-oof-one-time-generation-approved-2026-10-05` |
| Generation provenance | fits=5; prediction_batches=5; automatic_retries=0; git_dirty=false |
| Manifest gates | input/source/chronology/folds/identity/classes/probabilities/references/serialization all PASS |
| Original diagnostic freeze SHA | `3167daf9ddff78ef4c3dceec64ed36782c6c36424baed239d83ce1191c023663` |
| CSV layout | 1678 rows; exactly the existing 34 columns in original order; UTF-8 without BOM; LF; no index; round-trip float parsing |
| Years / counts | 2020=306; 2021=380; 2022=306; 2023=306; 2024=380 |
| Identity | source match IDs as strings; unique; unchanged exact TeamMaster IDs; canonical `validation_year, match_date, match_id` order |
| Class order | `[0,1,2] = Away/Draw/Home`; no class reorder |

Manifest and CSV hash/schema/provenance checks are mandatory. The manifest CSV SHA must match actual bytes. Existing schema, dtype, derived-column, ordered-ID and reference contracts remain unchanged; invalid evidence is a technical STOP, not a failed candidate. Source/chronology gates are accepted recorded provenance, not a license to reload historical source CSVs.

The existing manifest purpose remains immutable. This separately authorized lane consumes its frozen probabilities as calibration research evidence; neither the CSV's diagnostic columns nor its purpose is rewritten into a football-feature dataset.

Calibrator input is exactly the float64 matrix:

~~~text
p = [p_away, p_draw, p_home]
~~~

Require shape N x 3, nonempty rows, finite values, every `p_k > 0`, every `p_k <= 1`, and row sums equal 1 with `rtol=0, atol=1e-12`. No missing values, imputation, clipping, smoothing, or manual renormalization. Any `p <= 0` is a technical STOP. Labels used for fitting must be exactly in [0,1,2], with all three classes present in each prior training fold; absent classes are a technical STOP, not a substitute prior.

No Elo, club, phase, favorite/promoted flag, match metadata, or target-year identity is an input to the mapping. Year/date/ID are used only by the loader to enforce frozen splits and output identity. Fitting receives prior p and prior labels only; applying receives target p and a previously fitted parameter vector only.

This freeze inspected bytes, schema, probability-domain invariants, labels, counts, date separation, and ordered IDs using read-only parsing. It did not call `diagnose()`, metric evaluators, transforms, logarithms of real probabilities, or any fitting function.

## 5. Rolling calibration chronology

2020 is calibration warm-up ONLY. It is not a calibration evaluation fold: no accepted prior calibration history exists before it inside this artifact. Do not invent 2016-2019 OOF or refit A to add history.

| Evaluation year | Calibration training years | Training n | Evaluation n | Last training date | First evaluation date |
| --- | --- | --- | --- | --- | --- |
| 2021 | 2020 | 306 | 380 | 2020-12-19 | 2021-02-26 |
| 2022 | 2020-2021 | 686 | 306 | 2021-12-04 | 2022-02-18 |
| 2023 | 2020-2022 | 992 | 306 | 2022-11-05 | 2023-02-17 |
| 2024 | 2020-2023 | 1298 | 380 | 2023-12-03 | 2024-02-23 |

For evaluation year y, train is exactly all accepted rows with `2020 <= validation_year < y`; evaluate is exactly `validation_year == y`. Preserve their relative canonical order. Train/evaluation IDs must be disjoint and `max(train.match_date) < min(evaluation.match_date)` must pass.

For each candidate/fold, fit from scratch on all prior rows, starting again at identity. No carry-forward initialization, online/round updates, target-year fitting, inner CV, history-window selection, year-specific family, or refit after seeing y. Earlier evaluation-year outcomes may enter later folds only because they are then prior history under this precommitted schedule.

Target-year labels must be withheld from fitting/application interfaces and objective closures. Apply the fitted fold mapping once to the complete target-year p matrix; only afterward join its labels for scoring. Loading labels for artifact-integrity checks is not permission to expose them to the calibrator.

Ordered-ID SHA uses the existing convention:

~~~python
sha256(json.dumps(ids_as_ordered_strings,
                  ensure_ascii=False,
                  separators=(",", ":")).encode("utf-8"))
~~~

| Evaluation year | Calibration training ordered-ID SHA-256 | Evaluation ordered-ID SHA-256 |
| --- | --- | --- |
| 2021 | `66e2faeb3a51f0ea8e49bd76d1c484d191054997d8753c5acbc8663d3bbf1d35` | `9cd6cfa337ffb0477108775595a56bedb1edca7d05c4f099888bad54f41ded1e` |
| 2022 | `7b46320d22f92ade52007b02cb495adcc012455d857e7cda4b98d89fe6547e81` | `970c316240ee1597bf823d90711995bce334ba3e767f24d6c2d971088fc11803` |
| 2023 | `4545189f99cc234f3754c4ae96712d207a0d4ad86d64cc40e14c632980c3daf8` | `7a7e5f5dbf26a0ba046dbf8a59a441a05df535bd9b3730299e2e2b2bc9f46cc9` |
| 2024 | `0bbb249147c37452c098f85fe48b1f8658db91905888131f0a690bc27a83c391` | `40ccf48bbadc5398d54f11e79f9f2c5f1e914a4ecede086caa3eef77dd72d915` |

Warm-up 2020 ordered-ID SHA equals the 2021 training SHA above. Hashes were computed from accepted IDs, not from any new model outputs.

## 6. Candidate definitions

Exactly identity A0 plus the following three research challengers. No additional family or candidate variant is permitted in this cycle.

| Candidate | Free vector, in exact order | Fixed quantities | Free parameter count | Identity initialization | Bounds, in vector order |
| --- | --- | --- | --- | --- | --- |
| A0 IDENTITY | none | q=p unchanged | 0 | none | none |
| C1 TEMPERATURE ONLY | (tau,) | all b=0 | 1 | (1.0,) | ((0.0,None),) |
| C2 CLASS BIAS ONLY | (b_draw,b_home) | tau=1; b_away=0 | 2 | (0.0,0.0) | ((None,None),(None,None)) |
| C3 TEMPERATURE + CLASS BIAS | (tau,b_draw,b_home) | b_away=0 | 3 | (1.0,0.0,0.0) | ((0.0,None),(None,None),(None,None)) |

Tau is the inverse-temperature multiplier as written here, not a separately optimized T with tau=1/T. Tau=0 is allowed. Biases are unbounded in either direction; b_away is fixed exactly zero for identifiability and has no gradient entry.

A0 is the exact saved p matrix, not softmax(log(p)) and not a fitted model. It retains original values even if a row sum differs from 1 by an allowed rounding amount. C1-C3 identity unit cases agree with normalized p within numerical tolerance, not necessarily bit-for-bit for approximately normalized inputs; no identity shortcut or input repair is added.

Excluded: vector scaling, full matrix/Dirichlet, one-vs-rest Platt, isotonic, beta, spline/bin calibration, draw uplift, class weights, per-season/per-bin families, interactions, or subsets. If a frozen family is incompatible with the reviewed runtime, BLOCK rather than replace/drop it.

## 7. Mathematical transform

For row i and class k:

~~~text
ell_ik = log(p_ik)
z_ik   = tau * ell_ik + b_k
a_i    = logsumexp(z_i)
log_q_ik = z_ik - a_i
q_ik   = exp(log_q_ik)
~~~

Use float64, natural logarithms, and `scipy.special.logsumexp(z, axis=1, keepdims=True)` with stable log-sum-exp semantics. C1 fixes all b=0; C2 fixes tau=1; C3 fits all its permitted coordinates. Only softmax supplies normalization. No extra normalization, clipping, calibration bins, weighting, or smoothing is allowed.

Check inputs, parameter vectors, log(p), z, logsumexp, log_q, objective, and gradient for finite values. Reject wrong dimensions or tau<0; do not repair. Application must yield finite N x 3 q, `0 < q_k <= 1`, sums within `rtol=0, atol=1e-12`. A numerical underflow to q=0 is a technical numerical STOP, not a request to clip or cap parameters. This numerical-domain policy applies consistently in objective evaluations and target application; no fallback family.

The objective computes true-class log probabilities from stable log_q directly, not by taking log of a potentially underflowed array. The checks above still reject nonrepresentable positive q. Tau=0/all b=0 is the uniform mathematical unit case, covered only synthetically during implementation.

## 8. Fit objective and optimizer

### Objective and analytic gradient

For N prior calibration-training observations:

~~~text
L(theta) = mean_i [logsumexp(z_i) - z_i,y_i]
         = mean_i [-log_q_i,y_i]

dL/db_j = mean_i [q_ij - 1[y_i=j]], j in {Draw,Home}
dL/dtau = mean_i [sum_k q_ik * log(p_ik) - log(p_i,y_i)]

C1 gradient = (dL/dtau,)
C2 gradient = (dL/db_draw,dL/db_home)
C3 gradient = (dL/dtau,dL/db_draw,dL/db_home)
~~~

There is no free b_away entry. Objective and gradient use exactly the same prior rows, class order, float64 transform, and mean reduction. Return `(float64_scalar_objective, float64_gradient_vector)` together to the optimizer with `jac=True`.

No regularization, sample/class weights, pseudo-observations, prior/shrinkage, Brier/Accuracy optimization, calibration-bin loss, or draw-specific objective. Analytical equations make these low-dimensional objectives convex in their free coordinates; this does not guarantee a finite minimizer for every possible dataset. Numerical/optimizer failure remains technical STOP, not an alternate initialization or penalty.

### Exact optimizer call

Freeze `scipy.optimize.minimize`, `method="L-BFGS-B"`, analytic objective/gradient, the exact vectors/bounds in section 6, one identity start per candidate/fold:

~~~python
minimize(
    fun=objective_and_gradient,
    x0=identity_vector_float64,
    args=(),
    method="L-BFGS-B",
    jac=True,
    bounds=candidate_bounds,
    tol=None,
    callback=None,
    options={
        "maxcor": 10,
        "maxiter": 15000,
        "maxfun": 15000,
        "ftol": 2.220446049250313e-09,
        "gtol": 1e-05,
        "maxls": 20,
    },
)
~~~

These are the current L-BFGS-B runtime defaults made explicit, not values chosen from diagnostic magnitudes, real fits, or performance. No `disp`/`iprint` option, finite-difference gradient, parallel workers, Hessian/Hessian-vector callback, adaptive stopping callback, generic tol override, or extra option is supplied. eps/finite_diff_rel_step/workers retain runtime defaults and are inactive under the analytic gradient.

Local primary evidence inspected read-only: SciPy 1.18.1 `scipy/optimize/_lbfgsb_py.py::_minimize_lbfgsb`. Its signature has maxcor=10, maxiter/maxfun=15000, ftol=2.220446049250313e-09, gtol=1e-05, maxls=20. The local source byte SHA is `1add9425fb6c634339839a2f20c16c7a6a14f68db6f38e4f57e3366006439fd4`; no optimizer was called during this task.

Stopping semantics are the reviewed implementation's relative objective-reduction ftol condition OR projected-gradient infinity norm <=gtol. An optimizer success based on ftol is not reclassified as failure merely because gradient convergence used a different stopping reason.

Require result.success=True AND result.status=0, correct x/jac shape, finite x/fun/jac, and admissible bounds. Wrap the minimize/objective/gradient call in a warnings context with simplefilter("error") for all warning categories; do not suppress or reinterpret a warning. Any exception/warning, unsuccessful status, nonfinite intermediate/final value, shape error, or infeasible parameter stops the ENTIRE formal attempt. Record success/status/message/nit/nfev/njev/fun/jac, the final parameter vector, and projected-gradient infinity norm (context, not a new success gate). At tau=0 the projected gradient removes a positive derivative blocked by the lower bound.

No multiple starts, random initialization, warm start, retry, additional optimizer call at returned x, changed bounds/tolerances, candidate dropping, or adaptive solver. Formal execution has exactly 12 minimize calls if all four folds and all three challengers succeed; fewer only if a technical STOP interrupts it. Freeze fold-major order: 2021 C1/C2/C3, then 2022, 2023, 2024.

### Runtime/dependency contract

| Component | Frozen value |
| --- | --- |
| Platform / Python | repository Windows runtime / Python 3.12.14 |
| numpy | 2.5.3 |
| pandas | 3.0.5 |
| scipy | 1.18.1 |
| scikit-learn | 1.9.1 |
| requirements.txt SHA | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` |
| requirements-lock.txt SHA | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` |

No dependency upgrade or platform substitution to fix a mismatch. Determinism is required within this locked runtime and canonical row order; no claim of bitwise equivalence across arbitrary platforms.

## 9. Evaluation population

Exactly four evaluation folds: 2021/2022/2023/2024, counts 380/306/306/380, pooled n=1372. No eligible subset, cold-start exclusion, sparse filtering, imputation, or unmatched baseline population.

Pooled arrays concatenate target-year arrays in 2021->2024 canonical order. Exact pooled ordered-ID SHA:

~~~text
ae3c676eb346a2e1a77271c1a2b1ed8d5008adadce796d05d555394a61b3708e
~~~

Each target appears once per candidate and once in A0. The baseline is the accepted p for that exact row, never a new Champion A fit or existing prospective/operational prediction. Each candidate's target-year application must preserve that identical order and count.

2020 baseline reference checks, if performed later for artifact integrity, are NOT a fifth calibration evaluation fold. The original manifest pooled n=1678 is not the new screen's pooled n=1372.

## 10. Metrics

For A0/C1/C2/C3, every evaluation year and pooled 2021-2024: n, Accuracy, multiclass Log Loss, and Brier. Also report candidate minus A0 delta Accuracy/LL/Brier. Negative LL/Brier delta is improvement. Accuracy is context only.

Use the project's existing evaluation conventions:

~~~text
Accuracy = mean(argmax(probabilities, class order [0,1,2]) == result)
Log Loss = sklearn.metrics.log_loss(result, probabilities,
                                   labels=[0,1,2])
Brier    = mean(sum_k (probability_k - 1[result=k])**2)
~~~

Default normalized mean Log Loss, no weights; Brier sums the three class terms and is NOT divided by 3. Argmax exact ties select the first index, Away before Draw before Home. Use float64 and unrounded values for all decisions.

Numerical reconciliation: no p or q array is clipped or renormalized for calibration. Fit NLL is the stable, unpenalized log_q objective in section 8. Reported evaluation LL retains sklearn 1.9.1's existing loss-only machine-epsilon convention, as in the accepted OOF freeze; this is not probability preprocessing, draw uplift, or smoothing. This objective/scoring numerical distinction is explicit and cannot be switched after results. The raw positive p/q arrays remain the inputs to all reported metrics.

Pooled metrics are calculated over all 1372 row-level predictions/labels, not an unweighted average of four fold metrics. Do not substitute the accepted 1678-row pooled metric. No new 1372-row baseline value is calculated in this docs-only task.

For future formal pre-fit integrity gates, recompute accepted A-only fivefold/1678-row reference metrics using unchanged p and compare to the accepted manifest and original section-9 reference values with `rtol=0, atol=1e-12`. This is baseline verification only, not base fitting or a new diagnostic. Count/schema/identity must match exactly. Reference mismatch stops before any challenger fit.

For calibration context ONLY, report mean predicted probability, empirical class frequency, and empirical-minus-predicted bias for Away/Draw/Home by evaluation year and pooled for A0 and each challenger. No ECE/MCE, bin/subset search, frequency-matching selection, significance/CI, or additional pass/fail criterion.

## 11. Candidate decision gate

Candidate C passes ONLY if all three are true on full-precision metrics:

1. C pooled LL < A0 pooled LL.
2. C fold LL < A0 fold LL in at least 3 of the 4 fixed evaluation folds.
3. C pooled Brier <= A0 pooled Brier.

These are direct strict/non-strict numerical comparisons, with no epsilon margin, significance criterion, or minimum gain added to the pass rule. A LL equality is not improvement. Brier equality passes. The 1e-12 reference/tie tolerances do not soften these pass requirements.

Accuracy cannot create or veto a pass. Calibration context, club/phase metadata, diagnostic sign recurrence, individual-year Brier, and parameter magnitudes cannot add a criterion.

The denominator remains four even for a bad fold. Technical failure does not remove a candidate/fold or yield "no candidate passes"; it stops the attempted execution without a research decision.

Future formal run has exactly two possible research decisions:

- No challenger passes: `CLOSE_CALIBRATION_RESEARCH_LANE`; selected_candidate=null.
- At least one passes: `PROCEED_TO_CALIBRATION_PROSPECTIVE_FREEZE`; select exactly one via section 12.

Technical failures are not a third research decision. Use technical STOP statuses such as `BLOCKED_CALIBRATION_REFERENCE_MISMATCH`, `BLOCKED_CALIBRATION_OPTIMIZER_FAILURE`, or `BLOCKED_CALIBRATION_ARTIFACT_INTEGRITY`, preserving consumed-attempt evidence. Do not turn optimizer failure into candidate failure.

## 12. Multiple-candidate selection

Among passing candidates ONLY:

1. Compute the minimum full-precision pooled LL, L_min.
2. Define the tied set as every passing C with `abs(LL_C - L_min) <= 1e-12` (`rtol=0`).
3. Select the tied candidate with fewest free parameters: C1=1, C2=2, C3=3.
4. If still tied, fixed candidate order C1, C2, C3.

This minimum-anchored tie set is deterministic and avoids chained/nontransitive pairwise "close" comparisons. A slightly higher LL within the frozen tie band can win on simplicity; a difference outside it cannot. A nonpassing candidate cannot win a tie. No Brier/Accuracy/class-bias-size/2025/2026+ tie-breaker.

Tie tolerance is numerical, not an effect-size threshold or an extra evaluation opportunity.

## 13. Formal one-shot protocol

Future workflow is frozen, but NONE of its real-data execution steps is authorized now:

1. This docs-only specification freeze.
2. Dedicated evaluator implementation + synthetic/unit tests ONLY.
3. Push/review in a separate authorized workflow (no push in this task).
4. Real read-only preflight, with no real challenger fit/transformation/performance.
5. Push/review if a preflight document is separately authorized and committed.
6. Explicit separately authorized, reviewed-HEAD, clean-tree formal calibration execution exactly once.
7. Formal result document.
8. Push/review separately authorized.
9. Only after a pass, a separate prospective freeze at a new boundary.

Frozen future paths use the dedicated lane naming proposed in the task, separate from architecture and OOF generation:

~~~text
src/modeling/champion_a_calibration_evaluation.py
tests/test_champion_a_calibration_evaluation.py
data/processed/model_calibration/formal_calibration_attempt.json
docs/CHAMPION_A_CALIBRATION_EVALUATION_RESULT.md
~~~

Future default CLI is read-only preflight. Formal requires BOTH explicit flags and a separately reviewed execution task:

~~~powershell
.\.venv\Scripts\python.exe -m src.modeling.champion_a_calibration_evaluation
.\.venv\Scripts\python.exe -m src.modeling.champion_a_calibration_evaluation --formal --confirm-one-shot
~~~

These commands are design only, not executed in this task. Neither a freeze gate nor command flags alone provide task authority. Future implementation must require an authorization provenance object with the approved execution HEAD and a distinct formal task reference; it is not a source/parameter override. The approved execution HEAD includes any subsequently reviewed preflight-doc commit, rather than incorrectly requiring HEAD to remain the original implementation-only commit.

After verifying explicit authority/approved HEAD/clean tree and absent result path, formal execution must exclusive-create the attempt marker before pre-fit integrity gates and before any calibrator fitting/application. If the marker already exists, or exclusive creation loses a race, refuse with zero challenger fits. An existing result document also refuses formal execution. Hold a process-level exclusive lock throughout the attempt; no unrelated architecture/OOF marker interaction.

Marker semantics:

- Exclusive creation (`xb`), flushed/durable before fits; schema `champion_a_calibration_attempt_v1`.
- Immutable state `ATTEMPT_CONSUMED`, recording task authorization, execution HEAD, evaluator/spec SHA, expected input SHA, runtime/lock provenance, and UTC timestamp.
- Marker bytes/state are never updated to SUCCESS/FAILED; final success/failure is reported separately. Compute marker SHA after creation for the result/provenance.
- Any later failure, including artifact/reference/optimizer/numerical failure, leaves the marker as consumed evidence.
- Never overwrite, delete, repair, roll back, or regenerate a marker, including a partial/unreadable marker. Second formal run is refused.
- No automatic or manual retry after consuming the attempt; no debug rerun or adjusted optimizer. Concurrent second run is refused before fitting.

If artifact bytes are unavailable/mismatched after marker consumption, STOP; a missing/malformed input does not grant another attempt. Invalid authority or an already-existing marker/result is refused before starting a new attempt. This distinction must be tested.

After all twelve fits/applications and all final validation succeed, assemble the result in memory and exclusive-create its document. Failure/partial result remains evidence; do not repair/overwrite it. No permanent derived prediction array, calibrator bundle, CSV/JSON summary, plot data, pickle, or model artifact is created. Recheck accepted-pair SHA before result publication.

## 14. Prospective firewall

Even after a retrospective pass, do NOT alter Champion A historical or existing prospective probabilities. No recalibration/rewrite of opened 2026/27 lockbox, rolling-xG, P/G, or any already-persisted Model A prediction.

A pass permits only a separately frozen prospective specification. That future freeze must define a NEW prospective boundary, eligible unseen matches, artifact/training policy, update policy, comparison, and one-shot rules before predictions/outcomes are consumed. None of these downstream actions is authorized here; Champion A remains unchanged.

## 15. 2025 policy

2025 remains spent and excluded entirely from this retrospective screen. No reads, fits, evaluation, family selection, optimizer selection, protocol design, or tie-breaking from 2025.

Future possibility only: AFTER one family and protocol are fully frozen by the retrospective research decision, a later separately authorized prospective-artifact task MAY consider 2025 OOF labels as training-only data for that already-frozen calibrator. It must be explicitly authorized, cannot adapt the selected family or frozen hyperparameters/protocol, and cannot be reported as test performance.

Training-only fitting, if later authorized, would estimate that family's trainable coefficients; it is not permission to redesign the family/bounds/objective/optimizer/gates from 2025 outcomes. This task does NOT authorize 2025 OOF generation, access, fitting, or artifact construction.

## 16. 2026/27 policy

Opened 2026/27 remains forbidden for candidate/optimizer selection, parameter design, retrospective tie-breaks, or research gates. Do not inspect its outcomes or change its saved predictions.

Any future prospective calibration evaluation must start at a separately frozen NEW boundary and consume only future previously unseen matches. An already-opened interim lockbox cannot be relabeled unseen or used to select this protocol.

## 17. Future implementation design

Implement later in `src/modeling/champion_a_calibration_evaluation.py`; do not implement now.

Use small deterministic functions separating accepted-artifact loading/validation, split identity checks, pure transform/objective/gradient, one-call fitting, target-only application, metric/decision functions, read-only preflight, and one-shot formal orchestration.

Import/help must have no accepted-file read, optimizer call, transform, metric evaluation, filesystem mutation, or network dependency. No historical source reader, Champion A pipeline, Elo replay, architecture evaluator, prospective predictor, operational model loader, OOF generation CLI, or data collector is required or permitted.

Existing pure accepted-row validation can be reused only if its call graph is read-only and cannot invoke reconstruction/diagnosis/source loading. Preflight must not invoke helper functions that recompute screen metrics. Formal baseline reference validation may reuse frozen metric-only helpers, without calling their generator CLI, `reconstruct()`, `run_generation()`, or `diagnose()`.

Keep label/metadata access outside the application API. Maintain frozen candidate registry/order, float64 arrays, fresh identity initialization for every fit, and full target identity assertions. All fitted parameters and target arrays remain in memory until the result document is built. Synthetic test fixtures must not open the production pair or historical sources.

Implementation must pin the committed reviewed SHA/commit of THIS specification after this docs commit is reviewed; do not embed a guessed self-commit or circular self-hash in this document. Additional code/spec/runtime changes require review before formal authority, not silent adaptation.

## 18. Future test contract

Exactly 45 mandatory synthetic/unit test requirements are frozen below. This is a contract count, not a claim that tests exist or passed. No tests are implemented or run now. Synthetic fitting is permitted only in the later implementation task; no production fit/evaluation can appear in tests.

| # | Frozen requirement |
| --- | --- |
| 1 | Accepted-pair SHA/schema/provenance/reference contract rejects corruption, missing/partial evidence, wrong manifest, reordered headers/IDs/dtypes; synthetic fixtures only. |
| 2 | Only OOF years 2020-2024 accepted; no silent filtering of extra years. |
| 3 | Evaluation years exactly 2021-2024; 2020 warm-up only. |
| 4 | Exact prior counts 306/686/992/1298, evaluation counts 380/306/306/380, and ordered-ID/count/date contract. |
| 5 | Target-year rows never enter fitting; date separation and train/evaluation identity are enforced. |
| 6 | Exact class order [0,1,2]; wrong order/labels/missing training class rejects. |
| 7 | Inputs strictly positive and finite; p=0/negative/NaN/infinity reject; output underflow/nonfinite rejects without repair. |
| 8 | Probability sum gate rtol=0/atol=1e-12, with no renormalization; wrong shape/range rejects. |
| 9 | Stable softmax/logsumexp, finite objective/gradient, tau=0 unit cases, correct float64 output. |
| 10 | C1 identity at tau=1 within rtol=0/atol=1e-12. |
| 11 | C2 identity at zero biases within the same tolerance. |
| 12 | C3 identity at tau=1/zero biases within the same tolerance. |
| 13 | b_away fixed zero, no extra free coordinate or gradient entry. |
| 14 | C1 analytic gradient, vector order and mean-NLL objective. |
| 15 | C2 analytic gradient, vector order and mean-NLL objective. |
| 16 | C3 analytic gradient, vector order and mean-NLL objective. |
| 17 | Synthetic central finite-difference gradient cross-check: step=1e-6, rtol=1e-5/atol=1e-7, interior admissible parameters; not a production optimizer option. |
| 18 | Every candidate/fold starts at its exact identity vector; repeated synthetic fit/application deterministic in the locked runtime. |
| 19 | Exact tau lower bound, unbounded biases, exact minimize options; infeasible result rejects rather than projects. |
| 20 | Optimizer success/status/shape/finite checks; any candidate/fold failure stops the entire attempt. |
| 21 | Exactly one minimize call per attempted candidate/fold, no random/multiple starts/restart/retry/warm start. |
| 22 | No regularization, pseudo-data or extra objective term. |
| 23 | No sample/class weights; equal row mean reduction. |
| 24 | Target labels inaccessible to objective/fit/apply closures; application only p plus fitted parameters, exactly once per target-year candidate. |
| 25 | No Champion A fitting/predict_proba; execution guard catches base-model calls. |
| 26 | No Elo replay or state dependency. |
| 27 | No historical source CSV/TeamMaster/model bundle loading; file-open guards. |
| 28 | No 2025 access, including lookup/discovery/tie-breaks. |
| 29 | No 2026+ access/outcome inspection or existing prospective prediction rewrite. |
| 30 | Accuracy/LL/Brier and deltas on synthetic rows; argmax ties, Brier no /3, frozen loss-only epsilon semantics versus unclipped fit objective; reference mismatch STOP. |
| 31 | Pooled metrics calculated from all concatenated target rows, never unweighted fold mean or 1678-row diagnostic pool. |
| 32 | Strict per-fold LL improvement counts; exact equality is not improvement; full precision. |
| 33 | Pooled Brier non-worsening gate; equality passes, no reference/tie tolerance leakage into gate. |
| 34 | Accuracy and calibration context excluded from pass/selection. |
| 35 | >=3/4 fold rule and strict pooled LL conjunction; no denominator reduction. |
| 36 | Multiple passing candidates: lowest pooled LL anchored tied set, nonpassing candidates excluded. |
| 37 | atol=1e-12/rtol=0 complexity tie-break and C1/C2/C3 order, including nontransitive-close synthetic values. |
| 38 | Exactly three challenger definitions plus unfitted, value-preserving A0. |
| 39 | No extra calibration family, bin/subset/season-conditioned candidate, or post-hoc criterion. |
| 40 | Explicit reviewed task/HEAD authority and exclusive marker creation before fits; existing marker/result and concurrent second execution refuse. |
| 41 | Consumed marker persists after pre-fit gate/optimizer/application/result-write failure; no retry. |
| 42 | No overwrite/delete/repair/rollback of accepted pair, marker, result, or persisted predictions; no permanent derived datasets. |
| 43 | Import/help/default preflight no candidate fit/transform/evaluation and no marker/result write; preflight candidate performance absent. |
| 44 | No network/HTTP/data collection path. |
| 45 | No production prediction/activation dependency; retrospective pass only permits a separate prospective freeze, never promotion. |

Tests may use temporary synthetic files and stubbed constants in test fixtures to exercise real gates, never production bypass options. Finite-difference checks are synthetic validation only; production uses analytic gradients. Optimizer failures and marker races must be tested without consuming the real marker.

## 19. Preflight contract

Future real preflight is read-only and may validate:

- Reviewed HEAD, clean tree, implementation/spec hashes, separately reviewed implementation/test evidence.
- Exact CSV/manifest SHA/schema/provenance, positive finite p, counts, four folds, ordered IDs, date separation, class order/presence.
- Candidate registry/parameterization, identity initialization, bounds, optimizer implementation/options and pinned runtime availability.
- Absence of the dedicated formal marker and result path (existence checks only; no mutation).
- No forbidden imports/paths/source loading/network/model fitting dependencies; synthetic test evidence only.

Preflight must not call minimize on real rows, transform real p into q/log_q, fit/refit A, compute candidate metrics/deltas, select a candidate, or reveal formal performance. It may inspect recorded manifest/reference constants for equality without recomputing evaluation scores. Do not probe real optimizer convergence to debug future formal fits.

Use the same pure structural validators for preflight/formal. Full baseline-reference recomputation is reserved for formal pre-fit gates, and is not a preflight candidate evaluation. No derived JSON/CSV/model/plot/cache, marker, or result is written by preflight. A separately authorized preflight-doc task may record nonperformance checks.

Future preflight PASS means ready for a separately authorized one-shot; it is not authority to run formal. No preflight was run in this docs-only task.

## 20. Formal result contract

Future result path: `docs/CHAMPION_A_CALIBRATION_EVALUATION_RESULT.md`. Not created now.

Record for A0/C1/C2/C3:

- Training/evaluation row counts and ordered-ID hashes for all four folds; pooled n=1372.
- A0 has no fitted parameters/optimizer calls; C1/C2/C3 fitted parameters per fold in frozen order, including fixed tau/b_away where appropriate.
- Optimizer identity initialization/options/bounds, success/status/message/nit/nfev/njev/fun/jac and projected gradient; one call per candidate/fold, retries=0.
- Fold and pooled Accuracy/LL/Brier; candidate-minus-A0 deltas on identical rows.
- LL-improved folds / 4, pooled Brier comparison, three-component pass/fail per candidate.
- Per-year/pooled mean p or q, empirical A/D/H frequencies, biases as context only.
- Selected candidate, or null; minimum-anchored tie set/tolerance/complexity rule; exact final research decision.
- Accepted CSV SHA, manifest SHA, input/schema/reference gates, implementation/spec commit/SHA, execution authorization task/HEAD, runtime/dependency/lock provenance.
- Immutable formal marker path/SHA/state, expected 12 fits/12 target applications if complete, actual counts, no A refit/replay/OOF regeneration/2025/2026+ use.
- Explicit research-screen/unseen/prospective firewalls, unchanged Champion A/persisted predictions, no tuning/adaptive follow-up, no production artifact/push absent separate authority.

If any technical failure occurs, no research decision or selected candidate is produced. Preserve the consumed marker and report the technical STOP with failure stage/counts to the user; never fill in missing candidates, reinterpret partial metrics, or retry to obtain a result document. The immutable marker is minimum failure evidence; a diagnostic failure document is a separate authorization, not an automatic overwrite/repair.

## 21. Explicit non-goals

This task performed no calibrator/model fit, Champion A refit, predict_proba, Elo replay, OOF regeneration, diagnose(), real calibration transform, objective/gradient evaluation on real p, candidate scoring/LL comparison, tuning, or formal/preflight execution.

No 2025 or 2026+ data/outcomes/predictions were read. No HTTP/collection, prospective prediction/calibration, activation, base feature change, architecture/closed-lane reevaluation, one-shot marker/result creation, derived dataset/model artifact, implementation/test edit, dependency change, pytest, or push.

Only accepted-pair integrity/domain/counts/ordered identities/date separation and local dependency/optimizer source were inspected. All observed numerical facts here are artifact structure/provenance or existing diagnostic facts, not newly evaluated candidate results.

Validation for this document: accepted OOF CSV/manifest SHA checked before and after and unchanged; 22-section structure, 45 test requirements, internal links, exact counts/identity hashes, candidate/optimizer/gate contracts checked statically; `git diff --check` PASS. Only this new specification is staged/committed with message `docs: freeze Champion A calibration research`; no push.

## 22. Final freeze gate

`FROZEN_FOR_ONE_CHAMPION_A_CALIBRATION_IMPLEMENTATION`

Accepted identity, 2020 warm-up/2021-2024 chronology, exactly C1-C3, mathematical/gradient/numerical/optimizer contracts, scoring/pass/tie rules, 2025/2026 firewalls, and future implementation/test/preflight/one-shot/result workflow are unambiguous.

This gate authorizes ONLY evaluator implementation and synthetic tests. It does NOT authorize real calibrator fitting, real probability transformation, formal evaluation, marker creation, result generation, 2025 access, production artifact creation, or prospective calibration. Real execution remains a separately reviewed/authorized task.
