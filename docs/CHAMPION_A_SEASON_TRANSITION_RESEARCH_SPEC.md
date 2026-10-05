# Champion A Season Transition Research Specification

Freeze date: 2026-10-05 (JST).

Reviewed source HEAD: `533579c61ce18d602eabceadaa9ab48a0c44b092`
(`docs: record Champion A calibration evaluation`). Initial working tree: clean.
Task reference: dedicated docs-only instruction attachment
`4bc26f0c-ed1c-4fe1-9c95-85a80c71d5d6`.

Final freeze gate: `FROZEN_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_IMPLEMENTATION`.

This DOCS-ONLY freeze authorizes later evaluator implementation and synthetic/unit
tests ONLY. No real candidate replay, alternative Elo feature generation, fitting,
scoring, preflight, formal evaluation, marker/result creation, or activation occurs
or is authorized now.

## 1. Question and scope

Does Champion A lose useful accuracy because its Elo state is carried across J1
season boundaries with no uncertainty adjustment? This is a MODEL-STATE research
screen: only season-boundary Elo state handling and a fixed early-season adaptation
rule may change. Log Loss is the primary decision metric; Accuracy is context.

This is not calibration, external-information, lineup, player, xG, suspension,
home-advantage, architecture, or generic Elo hyperparameter research. No extra
feature, probability mapping, model family, interaction, or source is introduced.

## 2. Motivation, priority, and interpretation limits

Authorities reviewed:

- [Champion A targeted diagnostic](CHAMPION_A_OOF_TARGETED_DIAGNOSTIC.md), especially
  sections 2, 5, 9, 13, and 14.
- [Champion A calibration formal result](CHAMPION_A_CALIBRATION_EVALUATION_RESULT.md).
- `src/modeling/champion_a_oof_diagnostic.py`: source/provenance constants,
  `replay_elo`, `build_pipeline`, `add_metadata`, and accepted reference semantics.
- `src/modeling/player_workload_evaluation.py::_add_elo`: reviewed date-batched
  Champion A state traversal. Its workload evaluator is not executed or reused.
- `src/features/elo.py`: pure expectation and symmetric 90-minute update equations.

The frozen diagnostic established Gate A evidence PASS and Gate B evidence PASS.
Gate B decision eligibility was NOT CONSIDERED because priority was calibration
-> season transition -> inconclusive. The diagnostic's actual final gate remains
`PROCEED_TO_CALIBRATION_RESEARCH_SPEC`; it is not retrospectively rewritten.

The later separately frozen calibration attempt was consumed exactly once and
concluded `CLOSE_CALIBRATION_RESEARCH_LANE`. Its result and immutable marker remain
unchanged. Do not rerun, tune, repair, or reopen calibration, or import its evaluator
as a dependency of this lane. The present explicit task opens this NEW specification
task; old Gate B is motivation only, not a formal model decision.

2020-2024 has already been inspected diagnostically and in research. This is a
reused-historical RESEARCH SCREEN, not untouched final generalization evidence.
Chronological replay/fitting prevents target leakage, not human reuse of evidence.
Gate B cannot establish causality, offseason uncertainty, an optimal reset/K rule,
or candidate improvement. Class mix/confidence and observational group differences
remain limitations. No ST candidate performance is inspected in this freeze.

## 3. Four distinct hypotheses

| State/hypothesis | Frozen interpretation, not a finding |
| --- | --- |
| Current A / ST0 | Continuous no-reset Elo retains all prior deviation and uses K=30 throughout. |
| Season regression / ST1 | Offseason uncertainty may make previous Elo deviation too persistent; regress toward the fixed 1500 anchor. |
| Early K / ST2 | Early new-season completed results may deserve faster adaptation; increase symmetric match K for first-five involvement. |
| Combination / ST3 | Both boundary uncertainty adjustment and faster early adaptation may matter. |

These hypotheses are not causal claims and are not inferred improvements.

## 4. Unchanged Champion A contract

- Initial rating: float64 1500 for every frozen registered team ID used by the
  2015-2024 ordinary-J1 population.
- Baseline K=30; home advantage=175 in the Elo expected-score calculation ONLY.
- Expectation scale=400; use the reviewed stable `expected_score` semantics.
- Sole classifier feature: raw `elo_diff = home_rating - away_rating`, from
  date-batched pre-match ratings. Do NOT add 175 to this feature.
- ST0 has no season reset/regression and continuous state across all seasons.
- Completed 90-minute result only: 0=Away, 1=Draw, 2=Home. No penalties,
  aggregate winners, extra-time winner substitution, or uncompleted outcome.
- All same-date feature reads precede every result update on that date.
- Class order exactly `[0,1,2] = Away/Draw/Home`.
- Classifier pipeline exactly `StandardScaler()` followed by
  `LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000, random_state=0)`.
- StandardScaler uses copy=True, with_mean=True, with_std=True and training-only
  statistics. Other estimator parameters remain locked runtime defaults, including
  no class weights or warm start; supply no sample weights.

`src/features/elo.py` has generic defaults K=20 and home advantage=0. Those defaults
are NOT Champion A: `_add_elo` explicitly selects K=30 and HA=175. Future code must
not accidentally substitute the generic defaults or change the existing engine.

For every candidate match, the common float64 update is:

```text
E_home = expected_score(R_home + 175.0, R_away)
delta  = match_K * (result / 2.0 - E_home)
R_home_after = R_home + delta
R_away_after = R_away - delta
```

Use one expectation and one symmetric delta for both teams, preserving the reviewed
operation order and zero-sum match update. Boundary regression is a separate state
operation; it does not change expectation scale, HA, feature definition, or labels.

## 5. Exact candidate registry and predeclared anchors

Exactly four total states, in fixed order ST0/ST1/ST2/ST3:

| Candidate | Name | Carry fraction | Match K | Transition mechanisms |
| --- | --- | --- | --- | ---: |
| ST0 | accepted A0 baseline | 1.0; no regression | 30 always | 0 |
| ST1 | SEASON_REGRESSION_ONLY | 0.75 at each boundary | 30 always | 1 |
| ST2 | EARLY_K_ONLY | 1.0; no regression | 45 iff either ordinal <=5; otherwise 30 | 1 |
| ST3 | SEASON_REGRESSION_PLUS_EARLY_K | 0.75 at each boundary | 45 iff either ordinal <=5; otherwise 30 | 2 |

Carry=0.75, early K=45, and first five appearances are predeclared structural
research anchors supplied by this task. They are NOT estimated from 2020-2024
performance, diagnostic magnitudes, real candidate fits, or candidate results.

No carry=0, carry=0.5, or carry=2/3; no K=35/40/50/60, first 3/6/10, promotion/status-specific reset,
different home/away K, adaptive confidence rule, alternative HA, or post-result
variant. If all challengers fail, this lane closes for this cycle, with no adaptive
"try another reset strength" follow-up. Classifier coefficients are learned only
in future authorized training folds, not selected by a tuning search.

## 6. Boundary, absence, and cold-start semantics

ST1/ST3 apply exactly this operation ONCE before any match of each new season
2016, 2017, ..., 2024 is read:

```text
rating_new = 1500.0 + 0.75 * (rating_old - 1500.0)
```

No operation before/during initialization of 2015, no second shrink on the first
date, no per-match/per-round reset, and no shrink triggered by an individual club's
return. Trigger is the global J1 season boundary, not elapsed days or promotion.

Apply to EVERY ID in the registered population state, including clubs inactive in
the immediately preceding J1 season. An absent club shrinks at EACH intervening
boundary, whether or not it plays in that season: after m such boundaries without
updates its deviation is `0.75**m * prior_deviation`. Established clubs shrink once
per boundary; no status-based exception exists.

All population IDs are initialized to 1500 in their own candidate state at the
beginning of 2015. A first-ever observed club remains 1500 until its first update,
since shrinking 1500 leaves 1500. There is no promotion initialization, lookup of
out-of-scope results, league-average replacement, alias-based state reset, or new
team insertion from an unrecognized ID. ST0/ST2 never regress; absent clubs retain
their ratings until an ordinary-J1 result or, for ST1/ST3, a global boundary update.

## 7. First-five identity and same-date policy

For each season independently, each team's current-match appearance ordinal is
`1 + number of that team's strictly earlier ordinary-J1 appearances in the season`.
Counts include home and away appearances equally and reset at every season. They
depend only on completed schedule identity/current match position, NOT result,
score, class, rating, or predicted confidence. Round number is not an ordinal.

For ST2/ST3, use one symmetric match K:

```text
match_K = 45.0 if (home_ordinal <= 5 OR away_ordinal <= 5) else 30.0
```

Ordinal 5 qualifies; 6 does not, unless the opponent still qualifies. Asynchronous
club schedules therefore need not share round/ordinal. A midseason first-appearing
club has its own first five; no special promoted/returning handling is added.

Canonical order is stable `match_date, match_id`. Preserve the existing rejection
of any `(calendar date, team ID)` appearing more than once; do not invent sequential
within-day behavior for duplicate-team fixtures. All same-date rows belong to one
season; malformed/interleaved season/date input is rejected, never silently fixed.

At every date:

1. Before the first date of a new season, apply its boundary operation if relevant
   and reset season appearance counters once.
2. Capture every row's ratings, raw Elo difference, ordinals, expectation and K
   before applying any result that date.
3. Only after all captures, apply completed results in canonical match-ID order
   using their captured expectation and K; advance appearance counts independently
   of the outcome. Duplicate-team rejection makes match updates disjoint that date.

The target result cannot affect its own feature. Same-date peer results cannot
affect another feature. Changing/adding future results cannot change earlier
features. Prior validation-season results may update Elo for LATER dates in that
season, exactly as Champion A already does; that is strictly-prior online state,
not target-year classifier fitting or recalibration.

## 8. Frozen source population, paths, and byte identity

Future evaluation uses ordinary J1 seasons 2015-2024 only: exactly 3208 completed
matches / 6416 team sides. Exclude 2025, 2026+, Hyakunen, Cups, J2/J3, AFC, playoffs
outside the frozen ordinary-J1 files, external HTTP, and alternative artifacts.
No globbing, broader directory discovery, silent extra-year filtering, or fallback.

The following hashes and counts are copied from the accepted OOF manifest and the
reviewed generator constants, NOT guessed. Ten local byte hashes were checked
read-only in this docs task; no match table was parsed for candidate features.

| Season | Exact source CSV path | Rows | SHA-256 |
| --- | --- | ---: | --- |
| 2015 | `data/processed/jleague/2015_matches_probe.csv` | 306 | `ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353` |
| 2016 | `data/processed/jleague/2016_matches_probe.csv` | 306 | `4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f` |
| 2017 | `data/processed/jleague/2017_matches_probe.csv` | 306 | `d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b` |
| 2018 | `data/processed/jleague/2018_matches_probe.csv` | 306 | `f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681` |
| 2019 | `data/processed/jleague/2019_matches_probe.csv` | 306 | `3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f` |
| 2020 | `data/processed/jleague/2020_matches_probe.csv` | 306 | `fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17` |
| 2021 | `data/processed/jleague/2021_matches_probe.csv` | 380 | `298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6` |
| 2022 | `data/processed/jleague/2022_matches_probe.csv` | 306 | `d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2` |
| 2023 | `data/processed/jleague/2023_matches_probe.csv` | 306 | `6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9` |
| 2024 | `data/processed/jleague/2024_matches_probe.csv` | 380 | `4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1` |

TeamMaster: `data/master/teams.csv`, SHA-256
`ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f`.
Use its existing reviewed alias resolution and EXACT stable string IDs, without
case/Unicode/ID normalization, remapping, inferred IDs, or status-based identities.
The replay roster is the sorted union of registered home/away IDs actually used by
these frozen source seasons, as in `_add_elo`; unused master entries are not matches.

Future loader verifies all byte hashes before parsing, the existing processed
match validation/schema contract, exact seasons/counts/unique IDs, completed result
classes, finite/valid fields, no self match, calendar date/season coherence,
canonical order, and no same-date team duplicate. Unrecognized IDs, partial input,
or any mismatch is technical STOP, not an eligible subset or repaired source.

## 9. Accepted ST0 reference: one strategy, zero new baseline fits

Choose ONLY the accepted immutable Champion A OOF pair as formal ST0 reference:

| Evidence | Exact path | SHA-256 |
| --- | --- | --- |
| CSV | `data/processed/model_diagnostics/champion_a_oof_2020_2024.csv` | `cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59` |
| Manifest | `data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json` | `b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10` |

Accepted provenance: generator commit `6481780f208ffe95294bdb426a3e572a82a34a98`,
generator SHA `40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78`,
original freeze commit `159ca0c7d71dfd10b9d3888971fb05c9f681855e`, original freeze SHA
`3167daf9ddff78ef4c3dceec64ed36782c6c36424baed239d83ce1191c023663`.
The manifest remains `champion_a_oof_diagnostic_v1` with unchanged purpose
`diagnostic_only_not_formal_evaluation_not_model_input`, 1678 rows / 34 columns in
original order, original dtypes/UTF-8/LF layout, class order, source/team contracts,
recorded generation authorization and PASS gates. This separately authorized model
state screen does not rewrite that purpose or regenerate its evidence.

ST0 probabilities are the exact saved `[p_away,p_draw,p_home]`, unmodified. No new
ST0 Elo replay, StandardScaler fit, LogisticRegression fit, prediction, OOF
generation, or baseline reconstruction is permitted, even as a reference gate.
ST0's independent continuous trajectory is already evidenced by the accepted
generation; the three challengers alone require new independent replay in formal.
Do not substitute calibration output, prospective predictions, or another A0.

Before challenger replay, verify source-to-OOF equality on EVERY validation row:
ordered ID, season/year, calendar date, exact home/away IDs, result, round, and
home/away name fields. Derive appearance ordinals/first-five masks from schedule
identity only and check against accepted metadata. No Elo replay is needed for this
identity gate; stored ST0 `elo_diff` remains accepted provenance, not recomputed.
The source identity/reference gates are mandatory even if aggregate scores match.

Formal-only: recompute ST0 fold/1678-row pooled Accuracy/LL/Brier from saved raw p,
and compare both the accepted manifest and the following accepted references with
`rtol=0, atol=1e-12`, before any challenger replay or fit. No new reference metric is
computed now; the values below are copied historical baseline evidence.

| Validation year | n | Accuracy | Log Loss | Brier |
| --- | ---: | --- | --- | --- |
| 2020 | 306 | 0.5065359477124183 | 1.023119734659012 | 0.6117572218710644 |
| 2021 | 380 | 0.5078947368421053 | 1.0253437210487792 | 0.6149829138674616 |
| 2022 | 306 | 0.4019607843137255 | 1.0940186385371449 | 0.6610224339161608 |
| 2023 | 306 | 0.46078431372549017 | 1.0604285568595655 | 0.638530529273072 |
| 2024 | 380 | 0.45 | 1.079241181120235 | 0.6531695943664019 |
| pooled | 1678 | 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |

Preflight may compare recorded constants but must not recompute these scores.
Reference mismatch is technical STOP before challenger state generation.

## 10. Replay and expanding folds

Each challenger owns fresh float64 state and independent counters initialized at
the beginning of 2015; never copy ratings/features/state from ST0 or another
challenger. A successful formal run generates exactly THREE full canonical replays,
one each for ST1/ST2/ST3 over the 3208 rows, held in memory. It does not restart
state at a validation boundary, seed from 2019/2020 checkpoints, or run extra
fold-specific/confirmation replays. Full-stream generation is leakage-safe only
because every feature is captured strictly before its target/date outcomes and is
prefix-invariant to subsequent outcomes, including future validation rows.

Then select training/validation rows from each candidate's own features using:

| Validation y | Training seasons | Train n | Validation n | Training ordered-ID SHA-256 | Validation ordered-ID SHA-256 |
| --- | --- | ---: | ---: | --- | --- |
| 2020 | 2015-2019 | 1530 | 306 | `65b199341adc5ff9c7fc9c09dcfd73b1c4087e5d4f73cd71571fd4a69cddb158` | `66e2faeb3a51f0ea8e49bd76d1c484d191054997d8753c5acbc8663d3bbf1d35` |
| 2021 | 2015-2020 | 1836 | 380 | `a5a1265db672da0747a01fe0a69ab548ae684871be4f45efc4d1d1563e4ea266` | `9cd6cfa337ffb0477108775595a56bedb1edca7d05c4f099888bad54f41ded1e` |
| 2022 | 2015-2021 | 2216 | 306 | `dcd657ec4693b73a32fc27a6ee3dfc6b4c7c6efcde0c90328cdaeed9ce4b6cab` | `970c316240ee1597bf823d90711995bce334ba3e767f24d6c2d971088fc11803` |
| 2023 | 2015-2022 | 2522 | 306 | `405d0a8913098d6509381825a2299f494649b804af4528585d200e85c8c7013d` | `7a7e5f5dbf26a0ba046dbf8a59a441a05df535bd9b3730299e2e2b2bc9f46cc9` |
| 2024 | 2015-2023 | 2828 | 380 | `54a43cb0b98414d0768f1ad55f4e2adf474cf154080b0af1043792bed8f2304a` | `40ccf48bbadc5398d54f11e79f9f2c5f1e914a4ecede086caa3eef77dd72d915` |

Train is exactly all source rows with `2015 <= season < y`; validation is exactly
season y. Require exact counts, ID disjointness, canonical relative order, hashes,
and `max(train.match_date) < min(validation.match_date)`. No missing/eligible subset.
Ordered-ID hashes use SHA-256 of UTF-8
`json.dumps(ids_as_strings, ensure_ascii=False, separators=(',', ':'))`.

Pooled validation concatenates 2020 -> 2021 -> 2022 -> 2023 -> 2024 exactly once:
1678 rows; ordered-ID SHA
`0546d0e440f159b8507579933e0cca8deba635f1179b233bcd5e64c889547fe6`.
Every candidate uses precisely the same target IDs/order/labels as ST0.

## 11. Classifier fit and application

For each candidate/fold, fit a fresh section-4 pipeline on its own training raw
`elo_diff` and training labels only. StandardScaler never sees validation rows;
the classifier never fits target-year labels. No warm start, coefficient/scaler
reuse, inner CV, window selection, class/sample weights, calibration, additional
feature/metadata, interaction, or hyperparameter tuning.

After fitting, verify estimator classes `[0,1,2]`, finite trained parameters and
training scaler state. Predict the complete validation feature matrix exactly
once, without target labels in the prediction interface. Join labels only for
scoring. Treat `ConvergenceWarning` as an error, as in the reviewed generator;
any fit/prediction exception, nonfinite state/feature/parameter/probability, bad
shape/class/identity, or convergence failure stops the entire attempt. No candidate
dropping, altered max_iter/tolerance, replacement fit, probability repair, or retry.

Freeze fold-major fit/prediction order: 2020 ST1/ST2/ST3, then 2021, 2022, 2023,
2024 in the same candidate order. Successful full formal execution has exactly
15 LogisticRegression fits, 15 training-only scaler fits, 15 validation prediction
batches, 3 challenger replays, and ZERO ST0 fits/predictions/replays. No extra fit
for ranking, final selection, refitting a winner, or production artifact creation.

## 12. Primary metrics and numerical semantics

For ST0/ST1/ST2/ST3, all five folds and pooled: n, Accuracy, multiclass Log Loss,
multiclass Brier; candidate-minus-ST0 deltas for Accuracy/LL/Brier on identical rows.
Negative LL/Brier delta is improvement. Use raw float64 arrays in class order
Away/Draw/Home; require nonempty N x 3, finite values in [0,1] and row sums within
`rtol=0, atol=1e-12`. This follows the existing Champion A probability domain, not
the calibration lane's log-input domain. No clipping/normalization of p arrays.

```text
Accuracy = mean(argmax(p, axis=1) == result)
Log Loss = sklearn.metrics.log_loss(result, p, labels=[0,1,2])
Brier    = mean(sum_k (p_k - 1[result=k])**2)
```

Argmax exact ties select the first class index. Brier is NOT divided by three.
Log Loss retains the locked sklearn/project loss-only float64 epsilon semantics;
it does not preprocess probabilities or introduce calibration. No weights.
Pooled metrics operate on concatenated 1678 row predictions/labels, not the
unweighted mean of five fold scores. All decisions use stored full-precision
float64 values; rounding is display only and cannot enter a gate or tie-break.

## 13. Exactly two context-only transition views

Freeze masks solely from the ordinary-J1 source identity/schedule, checked against
accepted OOF metadata, independent of candidate predictions or outcomes:

1. `opening`: recorded round <=5 (validated positive integral round).
2. `any_team_first5`: home season appearance ordinal <=5 OR away ordinal <=5,
   exactly section 7. This is not necessarily equal to the opening mask.

For every ST state, report n / LL / Brier in each view for each validation year and
pooled. Views may overlap and are reported separately; no union/intersection is an
additional candidate population. Concatenate selected rows for pooled context.
For an empty synthetic view report n=0, LL=null, Brier=null; no imputation/threshold
or removal of a primary fold. No extra subgroup/bin/club/status searches, complements,
sparse exclusions, significance tests, or minimum effect sizes.

These views cannot create/veto a pass, select a family, break ties, or authorize
new variants after results. Primary evaluation always retains all 1678 rows.

## 14. Exact challenger pass rule

A challenger ST1/ST2/ST3 passes ONLY if ALL:

1. Its pooled LL < ST0 pooled LL.
2. Its fold LL < ST0 fold LL in at least 3 of the 5 fixed validation folds.
3. Its pooled Brier <= ST0 pooled Brier.

Direct full-precision comparisons: LL equality is not improvement; Brier equality
passes. No epsilon margin, effect-size threshold, significance test, or tolerance
softening. Accuracy, individual-year Brier, context metrics, diagnostic Gate B,
parameter magnitude, 2025, and 2026+ are excluded. Fivefold denominator is fixed;
technical failure cannot remove a fold/candidate or mean a failed research gate.

## 15. Multiple-pass selection and research decisions

Among passing challengers ONLY:

1. Find minimum full-precision pooled LL, L_min.
2. Tied set is every passing candidate with
   `abs(candidate_LL - L_min) <= 1e-12`, rtol=0, anchored at that SINGLE minimum.
3. Prefer fewer transition mechanisms: ST1=1, ST2=1, ST3=2.
4. If still tied, fixed ST1 -> ST2 -> ST3 order.

No chained pairwise-close comparisons; no Brier, Accuracy, opening/first-five score,
parameter magnitude, 2025, or 2026+ tie-break. A nonpassing candidate cannot win.

Exactly two research outcomes:

- No challenger passes: `CLOSE_SEASON_TRANSITION_RESEARCH_LANE`,
  selected_candidate=null, with no adaptive follow-up in this cycle.
- At least one passes: `PROCEED_TO_SEASON_TRANSITION_PROSPECTIVE_FREEZE`,
  selected_candidate exactly one of ST1/ST2/ST3 under the frozen tie rule.

Technical STOP is NOT a research decision; never fill partial candidates, infer a
winner, or publish a manual research conclusion after failure.

## 16. Runtime, provenance, and dependency firewalls

Freeze the reviewed Windows runtime: Python 3.12.14, numpy 2.5.3, pandas 3.0.5,
scipy 1.18.1, scikit-learn 1.9.1. No upgrade/platform fallback to rescue a mismatch.

| Dependency/authority path | Frozen SHA-256 |
| --- | --- |
| `requirements.txt` | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` |
| `requirements-lock.txt` | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` |
| `src/features/elo.py` | `f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4` |
| `src/modeling/player_workload_evaluation.py` | `7517880be643e7891eb7d0eb426d1dd57744ef5f7b730ce7713457e953457d76` |
| `src/modeling/champion_a_oof_diagnostic.py` | `40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78` |
| `src/collect/matches.py` | `0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c` |
| `src/collect/teams.py` | `b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c` |

The latter code files are reviewed semantic/provenance authorities, NOT permission
to execute another lane. A dedicated evaluator may reuse the pure `expected_score`
and explicitly scoped offline match/master loaders/validators only after auditing
their read-only call graph. Own candidate state locally; do not mutate the existing
Elo engine/private state or alter defaults. No workload feature reader/evaluator,
OOF generator execution (`reconstruct`, `run_generation`, `diagnose`), calibration
evaluator, architecture/P/G evaluator, operational model loader, xG/suspension,
network/collector execution, or prospective predictor dependency.

Future implementation pins THIS committed reviewed spec's actual commit/SHA and
its own reviewed implementation/test evidence after review, not a guessed/circular
self-hash in this document. Changed code/spec/runtime/input requires separate
review, never silent adaptation under a consumed formal attempt.

## 17. Workflow, paths, and read-only preflight

Freeze the sequence:

1. This docs-only research specification.
2. Dedicated evaluator implementation + synthetic/unit tests ONLY.
3. Separately authorized push/review.
4. Separately authorized real READ-ONLY preflight, with no candidate replay/fit,
   alternative Elo values, predictions, candidate scores, or selection.
5. Separately authorized preflight evidence commit/push/review.
6. Explicit reviewed-HEAD/clean-tree formal one-shot exactly once.
7. Exclusive generated formal result document.
8. Separately authorized commit/push/review.
9. Only if pass, a separate prospective freeze at a NEW boundary.

No real candidate replay/fit/performance in steps 1-4; step 2 permits isolated
synthetic toy replays/fits only. No push is authorized in this task.

Future paths (NONE created now):

```text
src/modeling/champion_a_season_transition_evaluation.py
tests/test_champion_a_season_transition_evaluation.py
data/processed/model_season_transition/formal_season_transition_attempt.json
docs/CHAMPION_A_SEASON_TRANSITION_PREFLIGHT.md
docs/CHAMPION_A_SEASON_TRANSITION_EVALUATION_RESULT.md
```

Default future CLI is read-only preflight; formal requires BOTH `--formal` and
`--confirm-one-shot`. These are design only; no CLI is implemented/executed now.

Preflight validates reviewed HEAD/clean tree/spec/implementation hashes, scoped
source/master/accepted-pair SHA/schema/provenance/counts/IDs/date separation, labels,
schedule-only ordinals/context masks, registry/structural anchors/model parameters,
runtime/locks, forbidden import/path firewall, and dedicated marker/result absence.
It may inspect recorded baseline constants but must not recompute metrics, replay
any Elo state (including ST0), fit/predict, probe real convergence, select a candidate,
or write datasets/models/cache/marker/result. Import/help have no task IO, state
generation, fit, performance, network, or filesystem mutation.

Successful future preflight gate:
`READY_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_FORMAL_EVALUATION`, meaning separately
reviewable readiness ONLY, not formal authority.

## 18. Formal authority, immutable marker, and publication

Future formal requires separately approved task provenance in
`CHAMPION_A_SEASON_TRANSITION_AUTHORIZATION`: exactly an object with
`approved_execution_head` and nonblank `task_reference`, identifying that exact
clean reviewed HEAD and a distinct formal task, not old OOF/calibration authority.
No extra source/model/parameter/path override. This task supplies NO formal authority.

Sequence: validate explicit authority/approved HEAD/clean tree and absent result;
acquire dedicated nonblocking Windows process-level exclusive lock; refuse an
existing/partial marker or result; exclusive-create (`xb`) marker and flush/fsync;
ONLY THEN run input/runtime/identity/reference integrity gates; ONLY THEN generate
the three challenger replays and perform the fifteen fits/applications. Concurrent
second execution refuses before any replay/fit. Lock is nonpersistent synchronization,
not a replacement/repair for the consumed marker and not another lane's lock.

Marker path is the section-17 dedicated season-transition path. Freeze schema
`champion_a_season_transition_attempt_v1`, immutable state `ATTEMPT_CONSUMED`.
Record task/approved execution HEAD, implementation/spec commit and SHA, expected
source/master/OOF hashes, runtime/dependency lock provenance, and UTC timestamp.
Compute marker SHA after creation; never change its bytes/state to SUCCESS/FAILED.

Invalid authority/already-existing evidence refuses before a new attempt. Every
failure after marker creation (including partial write, missing/malformed source,
reference, replay, fit, prediction, numerical, or publication failure) permanently
consumes the attempt. Preserve marker and any partial result; no deletion, overwrite,
repair, rollback, regeneration, debug rerun, adjusted settings, or manual retry.
Report technical STOP, failure stage and attempted/completed replay/fit/application
counts; do not manufacture a research decision. Do not touch calibration's marker.

After ALL final checks succeed, build the result in memory, recheck all frozen
source/master/OOF byte hashes and immutable marker SHA, then exclusive-create the
dedicated result document. Existing/partial result refuses; publication failure
preserves evidence without cleanup. No permanent alternative-feature dataset,
prediction CSV/JSON, calibrator/model bundle, pickle, plot data, or selected-model
refit. Only the generated result is a future tracked output; marker stays ignored
local evidence. Push remains separately authorized.

## 19. Formal result contract

Future result records exact source/master/OOF identities and gates; execution task,
HEAD, implementation/spec hashes, runtime/lock; immutable marker path/SHA/state;
three replays/15 challenger fits/15 predictions if complete, ST0 counts zero,
retry=0; fold source/target counts/ordered IDs; all frozen state rules; all trained
classifier/scaler provenance and convergence evidence (in document, not artifacts).

Report ST0-ST3 fold/pooled n/Accuracy/LL/Brier, matched deltas, LL-improved folds /5,
each pass component, tied set, selected candidate/null, exact research decision,
and the TWO context views only. Use full-precision stored values for decisions.
Document training-only preprocessing, date-batched strict-prior state, no baseline
reconstruction/calibration, reused-historical limits, closed prior lane, no tuning,
2025/2026+ exclusion, and unchanged existing predictions/Champion A. Technical
failure creates no automatic replacement result or research outcome.

## 20. Exactly 47 mandatory future synthetic/unit requirements

This is a frozen contract count, NOT a test execution claim. Future tests visibly
map to `test_contract_01_*` through `test_contract_47_*` or equivalent explicit
numbered mapping. Use toy arrays/DataFrames/isolated temporary files only; real
source/OOF/model/prediction paths and network are guarded against access in tests.

| # | Mandatory behavior |
| --- | --- |
| 1 | Exact registry/order ST0-ST3, names/anchors/mechanism counts; no extra family/feature or variant. |
| 2 | ST1 regression exactly `1500 + 0.75*(old-1500)` for deviations of both signs; fixed anchor, not league mean/status-dependent. |
| 3 | Boundary applies exactly once before first new-season read, not once per date/match/club appearance. |
| 4 | No boundary adjustment before 2015 initialization. |
| 5 | All registered population IDs shrink at every boundary, including clubs absent multiple seasons; no return-triggered extra reset. |
| 6 | Rating 1500 remains 1500; first-ever observed clubs start at 1500 without promotion priors. |
| 7 | ST1 K always30, including early appearances. |
| 8 | ST2 never regresses; carry state exactly continuously. |
| 9 | ST2 K45 iff either current season ordinal <=5; schedule-only counters reset, both sides, ordinal 5/6 and asymmetric appearances. |
| 10 | ST2 K30 when BOTH ordinals >5; round does not substitute for ordinal. |
| 11 | Single symmetric K/expectation/delta for both teams; zero-sum match update and no home/away K distinction. |
| 12 | ST3 composes the exact ST1 boundary and ST2 early-K rules, no additional intervention. |
| 13 | Independent candidate state/counters, repeat toy replay determinism and future-prefix invariance; no state/feature reuse. |
| 14 | All same-date reads precede all updates, canonical order; reject same-date team duplicates and malformed season/date interleaving. |
| 15 | Current-target and same-date peer result mutations cannot change target features; earlier validation results affect later dates only. |
| 16 | Exact initial1500, explicit baselineK30, HA175 and reviewed stable scale400 expectation; never generic K20 defaults. |
| 17 | Raw elo_diff excludes HA; one feature only, no round/ordinal/status/metadata/classifier interaction. |
| 18 | Exact five folds/counts/source-target ordered IDs and strict date separation; no eligible subset/extra/missing fold. |
| 19 | Explicit source/master/OOF SHA/schema/provenance gates reject corrupt/missing/partial/reordered evidence; accepted ST0 reference mismatch stops before replay. |
| 20 | Exact stable TeamMaster IDs/alias mapping/registered roster; unknown/self-match IDs rejected, no implicit insertion/remapping. |
| 21 | Reject 2025 source/OOF/lookups/discovery; no silent filtering or selection use. |
| 22 | Reject 2026+ and opened results/prediction lookup/rewrite; no lockbox-dependent design/selection. |
| 23 | StandardScaler training-only fit/statistics; target features cannot influence preprocessing. |
| 24 | Exact frozen LogisticRegression kwargs/locked defaults/classes; finite state, convergence warning/failure STOP, no additional model. |
| 25 | No class/sample weights, pseudo-observations, regularization changes, or calibration mapping. |
| 26 | Fresh one classifier fit and one target prediction batch per challenger/fold; ST0 accepted probabilities copied unchanged, zero baseline fit/replay. |
| 27 | Successful toy orchestration exactly3 independent replays/15 scaler fits/15 challenger classifier fits/15 predictions, frozen fold-major order; no winner refit. |
| 28 | No retry, restart, warm start, coefficient/scaler reuse, inner CV, or adaptive parameter change. |
| 29 | Accuracy/LL/Brier and deltas/class order; argmax ties, Brier no /3, loss-only epsilon convention, probability/shape/finite gates. |
| 30 | Pooled primary scores over all concatenated1678 target rows, not unweighted fold mean; matched IDs/labels across every state. |
| 31 | Strict pooled LL improvement AND >=3/5 strict fold LL improvements, equality not improvement and denominator fixed. |
| 32 | Pooled Brier <= baseline; equality passes, tiny worsening fails without tie/reference tolerance leakage. |
| 33 | Accuracy cannot create/veto pass or select a candidate. |
| 34 | Exactly opening/any_team_first5 context masks, per-year/pooled n/LL/Brier and empty-view null semantics; context cannot gate/tie-break. |
| 35 | Passing-only minimum-anchored atol1e-12/rtol0 tied set, including nontransitive-close values; nonpassing candidates excluded. |
| 36 | Fewer transition mechanisms wins within tied set: ST1/ST2=1, ST3=2; not number/magnitude of classifier coefficients. |
| 37 | Remaining exact tie uses ST1/ST2/ST3 order; exactly two research outcomes, technical STOP not a decision. |
| 38 | Separate exact reviewed authority/HEAD/clean tree plus durable exclusive marker BEFORE any replay/fit and pre-fit gates. |
| 39 | Consumed marker remains immutable after pre-fit/replay/fit/prediction/publication failure; no overwrite/delete/repair/rollback. |
| 40 | Existing/partial marker/result and concurrent second process refuse with zero new replay/fit; exclusive publication races preserve evidence. |
| 41 | Failed formal attempt never retries, drops a candidate/fold, manually selects, or creates replacement result; stage/counts preserved. |
| 42 | Import/help no task IO, replay, fit, metrics, network, or mutation. |
| 43 | Default read-only preflight validates structural identities without ANY candidate/ST0 replay, fit/prediction/metrics/selection/marker/result write. |
| 44 | No network/HTTP/collection execution; test network guards catch calls. |
| 45 | No operational prediction/artifact/activation dependency; pass permits separate NEW prospective freeze only. |
| 46 | No calibration evaluator dependency/execution; closed calibration result/marker untouched. |
| 47 | No architecture/P/G, workload/xG/player/suspension evaluator execution/dependency; explicit offline source-only access. |

No tests/code are implemented or run in this task. Future tests may stub frozen
counts/hashes with synthetic equivalents, never add production bypass options.

## 21. 2025, 2026+, and prospective firewalls

2025 is spent and excluded entirely: no reads/discovery, replay, fits, evaluation,
candidate/reset/K/threshold design, interpretation for selection, or tie-break.
Opened 2026/27 and all 2026+ outcomes, lockbox performance, prospective xG results,
or saved operational predictions are forbidden for selection/tuning and are not
inspected or rewritten. No new source is collected.

A retrospective pass does NOT make a new Champion, activate production, alter
historical/persisted/opened predictions, or prove unseen improvement. It permits
ONLY a separately frozen NEW prospective boundary on previously unseen future
matches, with its own training/update/comparison/one-shot rules before outcomes.
Opened evidence cannot be relabeled unseen. No prospective work is authorized here.

## 22. This-task evidence and final freeze gate

Only reviewed code/docs and frozen input hashes/counts/provenance were inspected.
Source SHA values came from reviewed generator constants/accepted manifest and
were verified as bytes; no alternative Elo values, replay, classifier/calibrator
fit, prediction, candidate metric/delta/ranking, or formal decision was computed.
Existing accepted sources/master/OOF, diagnostic, closed calibration result/marker,
reviewed code/tests/spec/preflight and requirements remain byte-identical.

No ST module/test/preflight/marker/result, permanent derived dataset/model/cache,
2025/2026+ access, network, tuning, pytest, or push. Calibration was not rerun or
modified. Sole new file is this specification; static content/identity/count/test
numbering checks and `git diff --check` only. Commit message:
`docs: freeze Champion A season transition research`.

`FROZEN_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_IMPLEMENTATION`

This gate authorizes ONLY future evaluator implementation and synthetic/unit
tests. It does NOT authorize real candidate replay/fit, preflight, formal evaluation,
marker/result creation, production artifact creation, prediction, or activation.
No ST candidate improvement or causality is asserted.
