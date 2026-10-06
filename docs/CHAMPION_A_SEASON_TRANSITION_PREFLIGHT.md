# Champion A Season Transition Read-Only Preflight Evidence

Date: 2026-10-06 (JST). This is STRUCTURAL / NONPERFORMANCE evidence only.
Task reference: `3d7cb69f-f7ae-4c5f-8a47-cc130c7ffc4a`.
Reviewed authority: `APPROVED_FOR_NEW_REAL_READ_ONLY_SEASON_TRANSITION_PREFLIGHT`.

Final document gate:
`READY_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_FORMAL_EVALUATION`.

Readiness ONLY for separate review/authorization. This document does NOT authorize
formal execution, state generation, fitting, scoring, candidate selection, model
activation, or prospective prediction. No candidate performance or research
decision is reported.

## 1. Historical failed attempt and distinct new authority

The old reviewed implementation HEAD
`beda5cc326c5d5e942bb810e4195d9138835ca78` had ONE real default preflight invocation
on 2026-10-06, exit code 1, automatic retries 0, and blocker
`BLOCKED_SEASON_TRANSITION_ARTIFACT_INTEGRITY: Noncanonical date/ID order`.
It stopped before real challenger replay/fit/prediction/metrics and created no
formal marker/result. The old invocation was NOT rerun or relabeled successful.

The separately reviewed ordering-correction spec and implementation allow ONE NEW
read-only preflight on `83754a50f016f45a012b147154fb32ab637f6a71`, not a retry on the old state or a
retry of a consumed formal attempt. New invocation count=1; automatic retries=0.
No formal attempt has been consumed by this task.

## 2. Reviewed HEAD, spec, implementation, and tree provenance

- Reviewed implementation/execution HEAD: `83754a50f016f45a012b147154fb32ab637f6a71`
  (`fix: canonicalize season transition source ordering`).
- Evaluator: `src/modeling/champion_a_season_transition_evaluation.py`.
- Evaluator committed/live byte equality: PASS.
- Evaluator SHA-256, before and after: `4c7a32be6d8f9d850c52b974bfb4d3117fb0ff8ba7ba6c908cd50ece5b27d32e`.
- Corrected spec: `docs/CHAMPION_A_SEASON_TRANSITION_RESEARCH_SPEC.md`.
- Corrected spec commit: `88b6d28ac12ae2232f29d5084e8d9ebf395292a9`.
- Committed/live corrected spec SHA-256, before and after:
  `efbf7995d2a8f5611d4002f5f9fe2299201d1d24c6e100dbf8662081e163cdd2`.
- Corrected spec commit ancestor of execution HEAD: PASS.
- Reviewed tests: `tests/test_champion_a_season_transition_evaluation.py`.
- Test SHA-256, before and after: `459f0b790d62d48a9cb31485b53afd4c0a8958fd03e2f0ef755510e37618f243`.
- Initial working tree: clean; exact reviewed HEAD gate PASS.
- Immediately after the real preflight, before evidence authoring: clean.
- Final tracked change: this evidence document ONLY. Final hand-off tree is clean
  after the evidence commit, checked by the task's final validation.
- No source/evaluator/test/spec/requirements changes. No checkout/reset or
  production evidence overwrite/repair.

## 3. Runtime and dependency provenance

| Component | Observed version/platform |
| --- | --- |
| Python | 3.12.14 |
| Platform | Windows-11-10.0.26200-SP0 |
| numpy | 2.5.3 |
| pandas | 3.0.5 |
| scipy | 1.18.1 |
| scikit-learn | 1.9.1 |

Frozen Windows runtime gate: PASS; no upgrade, fallback, or parameter change.

| Dependency file | Before SHA-256 | After SHA-256 | Match |
| --- | --- | --- | --- |
| `requirements.txt` | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` | PASS |
| `requirements-lock.txt` | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` | PASS |

Reviewed semantic authorities: frozen SHA gates PASS; all listed live bytes also
matched after preflight. Their code hashes are provenance, NOT execution permission
for workload/OOF/calibration/architecture lanes. Only reviewed pure expectation
and scoped offline source/master utilities are allowed by the frozen evaluator;
no expectation/replay operation ran on real evidence in this preflight.

| Reviewed authority | Before/after SHA-256 | Match |
| --- | --- | --- |
| `src/features/elo.py` | `f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4` | PASS |
| `src/modeling/player_workload_evaluation.py` | `7517880be643e7891eb7d0eb426d1dd57744ef5f7b730ce7713457e953457d76` | PASS |
| `src/modeling/champion_a_oof_diagnostic.py` | `40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78` | PASS |
| `src/collect/matches.py` | `0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c` | PASS |
| `src/collect/teams.py` | `b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c` | PASS |

## 4. Reconfirmation before the new real preflight

Focused synthetic/unit file executed exactly ONCE:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_champion_a_season_transition_evaluation.py -q
```

Result: `98 passed in 19.77s`, exit code 0. All 47 numbered contract functions
remain represented. Production-data/network guards stayed active. Synthetic
replays/fits and temporary-root safety tests are NOT real preflight/model
execution or production marker/result creation.

Import check, exit code 0, stdout/stderr empty: PASS.

```text
.\.venv\Scripts\python.exe -c "import src.modeling.champion_a_season_transition_evaluation"
```

Help check, exit code 0, stderr empty: PASS.

```text
.\.venv\Scripts\python.exe -m src.modeling.champion_a_season_transition_evaluation --help
```

Import/help are side-effect safe; synthetic import/help auditing tests passed.
Full pytest: NOT RUN. `PYTHONDONTWRITEBYTECODE=1` and pytest
`-p no:cacheprovider` (via `PYTEST_ADDOPTS`) suppressed repository cache writes;
these are hygiene settings, not model/preprocessing changes.

## 5. Exactly one NEW real default preflight

Command, with NO flags:

```text
.\.venv\Scripts\python.exe -m src.modeling.champion_a_season_transition_evaluation
```

- New default real preflight invocation count: 1.
- Historical old invocation rerun count: 0.
- Automatic retries: 0.
- Start UTC: `2026-10-06T05:11:32.6334403+00:00`.
- End UTC: `2026-10-06T05:11:33.8904537+00:00`.
- JST interval: 2026-10-06 14:11:32-14:11:33 (+09:00).
- Exit code: 0.
- Stderr: empty.
- Returned gate: `READY_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_FORMAL_EVALUATION`.
- Source rows: 3208 (6416 team sides).
- Pooled OOF rows: 1678.
- Registered population team count: 30 (exact IDs used by the frozen
  source population, not every unused TeamMaster entry).

Stdout is captured below with only document newline normalization (CRLF to LF).
No candidate features/probabilities/metrics are present.

```json
{
  "status": "READY_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_FORMAL_EVALUATION",
  "head": "83754a50f016f45a012b147154fb32ab637f6a71",
  "spec_commit": "88b6d28ac12ae2232f29d5084e8d9ebf395292a9",
  "spec_sha": "efbf7995d2a8f5611d4002f5f9fe2299201d1d24c6e100dbf8662081e163cdd2",
  "evaluator_sha": "4c7a32be6d8f9d850c52b974bfb4d3117fb0ff8ba7ba6c908cd50ece5b27d32e",
  "input_hashes": {
    "data/processed/jleague/2015_matches_probe.csv": "ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353",
    "data/processed/jleague/2016_matches_probe.csv": "4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f",
    "data/processed/jleague/2017_matches_probe.csv": "d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b",
    "data/processed/jleague/2018_matches_probe.csv": "f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681",
    "data/processed/jleague/2019_matches_probe.csv": "3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f",
    "data/processed/jleague/2020_matches_probe.csv": "fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17",
    "data/processed/jleague/2021_matches_probe.csv": "298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6",
    "data/processed/jleague/2022_matches_probe.csv": "d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2",
    "data/processed/jleague/2023_matches_probe.csv": "6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9",
    "data/processed/jleague/2024_matches_probe.csv": "4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1",
    "data/master/teams.csv": "ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f",
    "data/processed/model_diagnostics/champion_a_oof_2020_2024.csv": "cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59",
    "data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json": "b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10"
  },
  "runtime": {
    "python": "3.12.14",
    "platform": "Windows-11-10.0.26200-SP0",
    "numpy": "2.5.3",
    "pandas": "3.0.5",
    "scipy": "1.18.1",
    "scikit-learn": "1.9.1",
    "requirements_sha256": "887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda",
    "lock_sha256": "3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04"
  },
  "source_n": 3208,
  "pooled_n": 1678,
  "registered_teams": 30,
  "folds": [
    {
      "year": 2020,
      "training_n": 1530,
      "validation_n": 306
    },
    {
      "year": 2021,
      "training_n": 1836,
      "validation_n": 380
    },
    {
      "year": 2022,
      "training_n": 2216,
      "validation_n": 306
    },
    {
      "year": 2023,
      "training_n": 2522,
      "validation_n": 306
    },
    {
      "year": 2024,
      "training_n": 2828,
      "validation_n": 380
    }
  ],
  "candidate_replay": "NOT RUN",
  "candidate_fit": "NOT RUN",
  "candidate_prediction": "NOT RUN",
  "candidate_metrics": "NOT RUN",
  "marker_created": false,
  "result_created": false
}
```

## 6. Immutable frozen inputs: observed before AND after

Before snapshot UTC: `2026-10-06T05:10:34.340102+00:00`.
After snapshot UTC: `2026-10-06T05:12:07.090323+00:00`.

All thirteen exact paths matched their frozen expected SHA BEFORE preflight.
Independent read-only byte hashing after success matched every before value and
every frozen expected value. No alternative artifact/source, directory discovery,
row subset, normalization/repair of source bytes, or source rewrite was used.

| Exact frozen input | Observed before SHA-256 | Observed after SHA-256 | Frozen/before/after match |
| --- | --- | --- | --- |
| `data/processed/jleague/2015_matches_probe.csv` | `ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353` | `ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353` | PASS |
| `data/processed/jleague/2016_matches_probe.csv` | `4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f` | `4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f` | PASS |
| `data/processed/jleague/2017_matches_probe.csv` | `d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b` | `d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b` | PASS |
| `data/processed/jleague/2018_matches_probe.csv` | `f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681` | `f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681` | PASS |
| `data/processed/jleague/2019_matches_probe.csv` | `3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f` | `3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f` | PASS |
| `data/processed/jleague/2020_matches_probe.csv` | `fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17` | `fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17` | PASS |
| `data/processed/jleague/2021_matches_probe.csv` | `298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6` | `298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6` | PASS |
| `data/processed/jleague/2022_matches_probe.csv` | `d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2` | `d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2` | PASS |
| `data/processed/jleague/2023_matches_probe.csv` | `6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9` | `6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9` | PASS |
| `data/processed/jleague/2024_matches_probe.csv` | `4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1` | `4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1` | PASS |
| `data/master/teams.csv` | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` | PASS |
| `data/processed/model_diagnostics/champion_a_oof_2020_2024.csv` | `cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59` | `cd8157303789fe2e929ccb74aeaabab09fa3c1a3a26338b10addaa2183a74f59` | PASS |
| `data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json` | `b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10` | `b66f0fd9707e8d8835fcaec98962014e245296e97bd664f337b2e85066409f10` | PASS |

## 7. Corrected ordering and structural gates

Corrected source canonicalization: PASS. The reviewed loader verifies ALL frozen
source/master/OOF hashes before parsing. Each exact source receives per-file
completed-match semantic validation (schema, exact season/count, unique IDs,
valid result/scores/date/teams/fixtures and season/date coherence), without
requiring raw physical rows to already be sorted. Exact TeamMaster alias/date/ID
resolution is preserved.

The complete ten tables are concatenated in 2015->2024 order, stable-sorted
ascending `match_date, match_id` with `kind="stable"`, then
`reset_index(drop=True)`. ONLY this in-memory canonical stream is used for source
validation, schedule metadata/ordinals, source-to-OOF identity, fold extraction
and ordered-ID validation. No result/score/rating/prediction sorting key or
row dropping/filtering/deduplication is used. Direct replay canonical-order
assertions remain strict. Stable sort is deterministic canonicalization of
already byte-verified frozen evidence, NOT corruption repair, feature engineering,
candidate-specific behavior, tuning, or acceptance of changed source bytes.

The old raw-physical-order blocker did NOT occur on this new reviewed HEAD.
The synthetic raw-order regression additionally reconfirmed that exact unsorted
frozen bytes are accepted/canonicalized, whereas physically reordered bytes
against the ORIGINAL expected SHA fail BEFORE parse/canonicalization.

| Real structural gate | Result |
| --- | --- |
| Exact 2015-2024 ordinary-J1 source SHA/schema/counts | PASS |
| Exact total 3208 matches / 6416 sides and season counts | PASS |
| TeamMaster stable registered IDs/alias/date identity; no self matches | PASS |
| Accepted OOF CSV/manifest SHA/schema/provenance, 1678 rows / 34 columns | PASS |
| Global unique IDs, valid season/calendar dates, no same-date team duplicate | PASS |
| Deterministic canonical in-memory ordering/index | PASS |
| Every source-to-accepted-OOF target ID/year/date/team/result/round/name | PASS |
| Schedule-only season ordinals, first-five flags/status/context metadata | PASS |
| Exact expanding-fold counts/disjoint IDs/strict date separation | PASS |
| Frozen training/validation/pooled ordered-ID hashes | PASS |
| Registry ST0/ST1/ST2/ST3 order and static carry/K/first-five contract | PASS |
| Frozen numeric/sole-feature/classifier anchors | PASS |
| Spec/evaluator/runtime/dependency/semantic-code provenance | PASS |
| Recorded reference constants/provenance, WITHOUT score recomputation | PASS |

## 8. Fold identity and counts (nonperformance)

Every ordered-ID comparison below passed inside the ONE real preflight. The
hashes identify canonical source/target rows; they are not candidate metrics.
For every fold: train seasons 2015..y-1, validation season y,
disjoint IDs and `max(train.match_date) < min(validation.match_date)`: PASS.

| Year | Train n | Validation n | Training ordered-ID SHA-256 | Validation ordered-ID SHA-256 | Gate |
| --- | --- | --- | --- | --- | --- |
| 2020 | 1530 | 306 | `65b199341adc5ff9c7fc9c09dcfd73b1c4087e5d4f73cd71571fd4a69cddb158` | `66e2faeb3a51f0ea8e49bd76d1c484d191054997d8753c5acbc8663d3bbf1d35` | PASS |
| 2021 | 1836 | 380 | `a5a1265db672da0747a01fe0a69ab548ae684871be4f45efc4d1d1563e4ea266` | `9cd6cfa337ffb0477108775595a56bedb1edca7d05c4f099888bad54f41ded1e` | PASS |
| 2022 | 2216 | 306 | `dcd657ec4693b73a32fc27a6ee3dfc6b4c7c6efcde0c90328cdaeed9ce4b6cab` | `970c316240ee1597bf823d90711995bce334ba3e767f24d6c2d971088fc11803` | PASS |
| 2023 | 2522 | 306 | `405d0a8913098d6509381825a2299f494649b804af4528585d200e85c8c7013d` | `7a7e5f5dbf26a0ba046dbf8a59a441a05df535bd9b3730299e2e2b2bc9f46cc9` | PASS |
| 2024 | 2828 | 380 | `54a43cb0b98414d0768f1ad55f4e2adf474cf154080b0af1043792bed8f2304a` | `40ccf48bbadc5398d54f11e79f9f2c5f1e914a4ecede086caa3eef77dd72d915` | PASS |

Pooled canonical validation order: 2020->2021->2022->2023->2024, exactly 1678 rows.
Pooled ordered-ID SHA-256: `0546d0e440f159b8507579933e0cca8deba635f1179b233bcd5e64c889547fe6`; PASS.
No eligible subset/extra/missing fold or baseline reconstruction.

Registry/static contract PASS:

| State | Reference/carry | K rule | Mechanisms |
| --- | --- | --- | --- |
| ST0 | Accepted saved OOF reference ONLY; carry1.0 | Baseline30, NOT replayed | 0 |
| ST1 | 0.75 at every 2016-2024 global boundary | Always30 | 1 |
| ST2 | 1.0, no regression | 45 iff either season ordinal<=5, else30 | 1 |
| ST3 | 0.75 at every 2016-2024 global boundary | Same rule as ST2 | 2 |

Ordinals count prior home AND away appearances and reset by season; round is not
ordinal. Initial1500, HA175 in reviewed scale400 expectation ONLY, raw
`elo_diff` sole classifier feature, same-date all-reads-before-updates, training-only
StandardScaler and frozen LogisticRegression parameters remain unchanged.
These are STATIC rules, not generated real state/features or fitted parameters.

## 9. Performance, formal, and production firewalls

The following statuses apply to the REAL preflight, not synthetic temporary-root
unit tests. Default `preflight()` performed structural validation only; no real
challenger/baseline replay, model construction/fit/prediction, performance,
gate/selection, or formal path was executed.

| Operation | Real-preflight status |
| --- | --- |
| ST0 replay | NOT RUN |
| ST1 replay | NOT RUN |
| ST2 replay | NOT RUN |
| ST3 replay | NOT RUN |
| real season regression | NOT RUN |
| alternative real elo_diff | NOT RUN |
| real scaler fit | NOT RUN |
| real classifier fit | NOT RUN |
| real prediction | NOT RUN |
| ST0 metrics recomputed | NOT RUN |
| candidate metrics | NOT RUN |
| candidate deltas | NOT RUN |
| candidate gate/selection | NOT RUN |
| candidate selection | NOT RUN |
| baseline_gate() | NOT RUN |
| formal CLI | NOT RUN |

| Forbidden production action/access | Status |
| --- | --- |
| production marker created | NO |
| production formal result created | NO |
| 2025 | NO |
| 2026+ | NO |
| lockbox/prospective access | NO |
| network/collection | NO |
| production prediction | NO |
| production artifact creation | NO |
| code/test/spec/data/requirements modification | NO |
| push | NO |

Formal marker:
`data/processed/model_season_transition/formal_season_transition_attempt.json`.
Formal result:
`docs/CHAMPION_A_SEASON_TRANSITION_EVALUATION_RESULT.md`.
Both were ABSENT before and after preflight and are rechecked during final
validation. They were not read, created, deleted, repaired, or overwritten.
This evidence document was ABSENT before execution; it is the sole authorized
new tracked file, not a formal result.

No derived feature dataset/model/prediction/cache/result artifact appeared from
this preflight: returned marker/result fields are false; dedicated
`data/processed/model_season_transition` stayed absent; sampled repository cache
directory modification metadata stayed unchanged; bytecode/pytest cache writes
were disabled; the tree was still clean after execution. The reviewed read-only
call path and synthetic preflight guards prohibit other production writes.
No 2025/2026+/lockbox/model-directory discovery or inspection was used to check this.

## 10. Validation, commit boundary, and final gate

`git diff --check`: PASS. Before staging, the sole changed/new tracked candidate
is `docs/CHAMPION_A_SEASON_TRANSITION_PREFLIGHT.md`. Stage ONLY this document,
recheck marker/result absence, commit with:

```text
docs: preflight Champion A season transition evaluation
```

Final hand-off validates that the evidence commit contains ONLY this document
and the working tree is clean. No further pytest, real preflight, formal run,
code/spec/test/data change, or push follows this success.

`READY_FOR_ONE_CHAMPION_A_SEASON_TRANSITION_FORMAL_EVALUATION`

Readiness ONLY. Separate reviewed-HEAD/clean-tree FORMAL authorization is still
required. This preflight does not authorize a formal attempt, any real state/fit/
performance, a research decision, production activation, or prospective work.
