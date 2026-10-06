# Champion A Season Transition ST2 Artifact Preflight

Date: 2026-10-07 (Asia/Tokyo). Operation: REAL READ-ONLY PREFLIGHT ONLY.
Authorizing task attachment: `8dbe76a1-3bb0-46ba-86b0-d6ca98b097e6`.
Reviewed implementation approval: `APPROVED_FOR_ST2_PROSPECTIVE_ARTIFACT_PREFLIGHT`.

## 1. Execution authority and change boundary

Initial reviewed HEAD:
`3aa66652d45a9c290146002254a1419ccf926517`
(`feat: implement ST2 prospective artifact builder`).
Initial git status --short: empty (clean). Exact-HEAD gate: PASS.

Spec: `docs/CHAMPION_A_SEASON_TRANSITION_PROSPECTIVE_FREEZE_SPEC.md`.
Spec commit: `fb4cef5fea338b99d62f5b2a6c7be5079b4d6f33`.
Builder: `src/modeling/season_transition_st2_artifact.py`.
Tests: `tests/test_season_transition_st2_artifact.py`.

| Evidence | Committed SHA-256 | Live SHA-256 | Gate |
| --- | --- | --- | --- |
| Spec | `daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3` | `daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3` | PASS |
| Builder | `58de1d345262f77c396b6d536468f31f832984f097204ea27fa649a4ae48bc9d` | `58de1d345262f77c396b6d536468f31f832984f097204ea27fa649a4ae48bc9d` | PASS |

Committed bytes were obtained with git show from the reviewed implementation HEAD
using the process stdout BYTE stream, not PowerShell text re-encoding. Spec bytes
equal the required authoritative SHA. Live tests SHA-256:
`8ee59410c00dd6039a7eaa71a6f0294032773b89c520072d4a33e39b1e1ab345`, unchanged across the inspection.

No source, tests, spec, data, models, requirements, prediction records or prior
evidence was edited. The only handoff change is this evidence document:
`docs/CHAMPION_A_SEASON_TRANSITION_ARTIFACT_PREFLIGHT.md`.
Final publication requires git diff --check/staged check PASS and a clean
post-commit tree; no new production file is permitted. Push is not performed.

## 2. Absence and prior-evidence gates

These paths were checked for existence only, including non-followed filesystem
entries, before tests/source inspection and again after the real inspection:

| Path | Before | After |
| --- | --- | --- |
| data/processed/model_season_transition/st2_prospective_artifact_attempt.json | ABSENT | ABSENT |
| models/model_season_transition/season_transition_st2_20261006_v1/ | ABSENT | ABSENT |

No ST2 attempt marker or output directory was read, created, deleted, repaired or
overwritten. The prospective creation attempt has NOT been consumed.

The old retrospective marker at
`data/processed/model_season_transition/formal_season_transition_attempt.json`
was hashed read-only, never edited. Before/after SHA-256 both equal its accepted SHA:

```text
89dfe53743b291b6be45284c9f035ead2b419f4a96a197bd84b35bdebad104cf
```

The retrospective formal attempt remains untouched. It was not executed again.

## 3. Frozen builder constants

Static inspection/import checked, without building real features:

```text
SPEC_COMMIT = fb4cef5fea338b99d62f5b2a6c7be5079b4d6f33
SPEC_SHA = daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3
MODEL_VERSION = season_transition_st2_20261006_v1
ROLE = prospective_challenger
EXPECTED_ROWS = 3588
TRAINING_SEASONS = 2015..2025 inclusive
FEATURES = ("elo_diff",)
CLASS_ORDER = (0, 1, 2) = Away / Draw / Home
```

The frozen training manifest remains EXACTLY seven ordered columns:

```text
season,match_id,match_date,home_team_id,away_team_id,target_class,elo_diff
```

Ratings, appearance ordinals and match K are internal future replay state only.
No row-wise replay-trace columns or metadata are added. No real training manifest
or real elo_diff vector was generated in this preflight.

## 4. Focused synthetic reconfirmation: exactly once

Executed once, exit code 0:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_season_transition_st2_artifact.py -q
```

Captured stdout:

```text
........................................................................ [ 75%]
.......................                                                  [100%]
95 passed in 7.10s
```

No retry, edit or second focused pytest invocation occurred. The focused tests
guard all real data/model IO and network; their fits/serialization/reloads run
only on tiny synthetic temporary roots. These synthetic operations are NOT real
production fit counts.

Then executed, each exit code 0:

```powershell
.\.venv\Scripts\python.exe -c "import src.modeling.season_transition_st2_artifact"
.\.venv\Scripts\python.exe -m src.modeling.season_transition_st2_artifact --help
```

Import stdout: empty. Help stdout:

```text
usage: season_transition_st2_artifact.py [-h] [--create-artifact]

Frozen ST2 one-fit artifact builder; real creation needs separate reviewed
authorization.

options:
  -h, --help         show this help message and exit
  --create-artifact  Future authorized real one-shot ONLY (not implementation
                     validation)
```

No no-flag module execution, --create-artifact invocation or full pytest occurred.

## 5. Exactly one real read-only structural inspection

One in-memory orchestration of the reviewed helpers, in this order:

```python
snapshots = snapshot_inputs(ROOT)
matches, master = load_sources(snapshots)
ordered = validate_source(matches, master)
runtime = runtime_provenance()
```

Inspection invocations: 1. Exit code: 0.
Start UTC: `2026-10-06T22:53:41.121012+00:00`.
End UTC: `2026-10-06T22:53:41.427906+00:00`.
All pinned bytes were captured and SHA-verified BEFORE any CSV/master parsing.
The source loader consumed those already-verified byte snapshots, not reopened
or mutable source content. There was no alternate source, glob/rglob, extra-year
filtering, dropped row, deduplication or evidence repair.

Runtime protection replaced replay/manifest/fit/artifact/write functions with
hard-fail guards, including _capture, _apply, match_k, build_training_manifest,
serialize_manifest, validate_training_manifest, fit_frozen_st2, fitted_state,
create_artifact, load_artifact and exclusive_write. Estimator construction,
fit/fit_transform, prediction and score methods were also hard-fail guarded.
Production data/model reads were limited to the exact pinned input allowlist;
production mutation and network connections were blocked. Forbidden calls: 0.

Only structural/nonperformance summaries were emitted; no actual score/result
rows, probabilities, fitted state or predictive-performance figures were displayed.

## 6. Exact production source SHA evidence, before and after

Exactly eleven ordinary J1 source CSVs, 2015-2025 inclusive. Every observed
before/after value equals the frozen builder pin.

| Exact source path | Before SHA-256 | After SHA-256 | Gate |
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
| `data/processed/jleague/2025_matches_probe.csv` | `c94411ed299ff90d86c3b55a3b17bd3e0dfc127d58c060109658d235bb24d18d` | `c94411ed299ff90d86c3b55a3b17bd3e0dfc127d58c060109658d235bb24d18d` | PASS |

Exact per-season population:

| Season | Rows |
| --- | --- |
| 2015 | 306 |
| 2016 | 306 |
| 2017 | 306 |
| 2018 | 306 |
| 2019 | 306 |
| 2020 | 306 |
| 2021 | 380 |
| 2022 | 306 |
| 2023 | 306 |
| 2024 | 380 |
| 2025 | 380 |

Total: 3,588 matches / 7,176 team sides. Exact input rows preserved.
Canonical date range: `2015-03-07` through `2025-12-06`.
Registered TeamMaster IDs: 49; IDs appearing in these sources: 31.
Canonical ordered match-ID sequence SHA-256 (identity ONLY, UTF-8 keys followed by
LF including final LF):

```text
12fc636e0db2195bde5cdd0d3f39304ca57fed1b61875319eec195462e50bb89
```

This identity hash is not a generated training-manifest hash or a feature vector.

| Structural gate | Result |
| --- | --- |
| Exact eleven filenames / per-file season and row counts | PASS |
| Aggregate source population / no filtering or repair | PASS |
| Required CSV schema and field widths | PASS |
| Ordinary J1 competition/stage semantics | PASS |
| Completed result 0/1/2 and score consistency | PASS |
| Season/date coherence and valid calendar dates | PASS |
| Unique match IDs / no duplicate fixture / exact source strings | PASS |
| Exact TeamMaster alias/date/ID resolution | PASS |
| No self match after alias resolution | PASS |
| No duplicate (calendar date, team ID) | PASS |
| Canonical in-memory ascending match_date, match_id ordering | PASS |
| Source ID set/count preserved / stable canonicalization | PASS |
| No real generated Elo feature column | PASS |
| Exclusion of Hyakunen / ongoing / prospective sources | PASS |

Reading 2025 was authorized ONLY as frozen post-selection classifier TRAINING
evidence for structural validation. 2025 is spent, not fresh selection evidence;
no 2025 ST2 performance, prediction, delta, tuning or model choice was inspected.

## 7. TeamMaster, dependency, code and spec pins

All 26 pinned inputs, including the eleven source rows above, were rehashed AFTER
structural inspection. Every before == after == expected. Code authority files
were read only as bytes; other-lane evaluators/predictors were not imported or run.
No ongoing or Hyakunen DATA was read merely because its code authority is pinned.

| Exact authority path | Before SHA-256 | After SHA-256 | Gate |
| --- | --- | --- | --- |
| `data/master/teams.csv` | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` | PASS |
| `requirements.txt` | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` | PASS |
| `requirements-lock.txt` | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` | PASS |
| `src/features/elo.py` | `f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4` | `f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4` | PASS |
| `src/features/elo_history.py` | `e9a66cb8e6d905780fcd8dc88867b21a3de16865eb3c1ef35e3ae0cc5cc1c86a` | `e9a66cb8e6d905780fcd8dc88867b21a3de16865eb3c1ef35e3ae0cc5cc1c86a` | PASS |
| `src/modeling/champion_a_season_transition_evaluation.py` | `4c7a32be6d8f9d850c52b974bfb4d3117fb0ff8ba7ba6c908cd50ece5b27d32e` | `4c7a32be6d8f9d850c52b974bfb4d3117fb0ff8ba7ba6c908cd50ece5b27d32e` | PASS |
| `src/modeling/champion_a_oof_diagnostic.py` | `40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78` | `40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78` | PASS |
| `src/modeling/model_a_artifact.py` | `69ff3712d5e286b131687fa21b7804cdcc63abb7478bf218fe10a53f77800e8c` | `69ff3712d5e286b131687fa21b7804cdcc63abb7478bf218fe10a53f77800e8c` | PASS |
| `src/modeling/xg_challenger_prediction.py` | `d9a4fa3db1d4fa6ac090371cee4e0bc10918029de6c43be40af2934674b1aec4` | `d9a4fa3db1d4fa6ac090371cee4e0bc10918029de6c43be40af2934674b1aec4` | PASS |
| `src/modeling/prediction_identity.py` | `e9e31ce7b7cf079d8b10dd96a173d8fa31435196982361f2e612524f94177b41` | `e9e31ce7b7cf079d8b10dd96a173d8fa31435196982361f2e612524f94177b41` | PASS |
| `src/collect/matches.py` | `0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c` | `0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c` | PASS |
| `src/collect/teams.py` | `b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c` | `b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c` | PASS |
| `src/collect/jleague_ongoing.py` | `5e91025142d583d09f2417724f9cbaeed50339275390d46000d3a73179cbe956` | `5e91025142d583d09f2417724f9cbaeed50339275390d46000d3a73179cbe956` | PASS |
| `src/collect/jleague_ongoing_source.py` | `573a8c6fa4ada4d7d1c7efd64885c9caadb98faf142934e632c41a12811da1d2` | `573a8c6fa4ada4d7d1c7efd64885c9caadb98faf142934e632c41a12811da1d2` | PASS |
| `docs/CHAMPION_A_SEASON_TRANSITION_PROSPECTIVE_FREEZE_SPEC.md` | `daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3` | `daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3` | PASS |

Builder and tests were separately rehashed before/after and remained equal to the
section 1 SHA values. The spec also remains committed/live identical and unchanged.

## 8. Exact locked runtime

runtime_provenance(): PASS. Every version equals the builder-pinned stack.

| Component | Observed / required |
| --- | --- |
| python | `3.12.14` |
| numpy | `2.5.3` |
| pandas | `3.0.5` |
| scipy | `1.18.1` |
| scikit-learn | `1.9.1` |
| joblib | `1.6.0` |
| platform | `Windows-11-10.0.26200-SP0` |

requirements.txt and requirements-lock.txt also matched the exact section 7 pins
before/after. No dependency installation, upgrade or parameter-default change.

## 9. One-shot readiness: static inspection ONLY

Reviewed builder function references below are code-inspection evidence, not
executed production artifact operations.

| Frozen one-shot requirement | Static evidence | Gate |
| --- | --- | --- |
| Separate exact-HEAD authorization and clean tree | repository_state / validate_authorization; approved_execution_head equals current reviewed commit; task_reference required | PASS |
| Existing marker/artifact refused before source reads | create_artifact calls os.path.lexists before snapshot_inputs | PASS |
| Explicit frozen byte inputs checked before parsing | snapshot_inputs returns only after every pin matches; load_sources consumes snapshots | PASS |
| Exclusive attempt marker creation | exclusive_write uses open("xb") | PASS |
| Marker durable before first fit | marker exclusive_write flushes and fsyncs before fit_frozen_st2 | PASS |
| Immutable consumed state | marker payload state ATTEMPT_CONSUMED; no marker-update path | PASS |
| One fit path, no determinism refit | create_artifact contains one fit_frozen_st2 call; scaler.fit_transform and model.fit each occur once | PASS |
| Exact successful fit counts | progress guards require attempts/completed 1 each; prediction batches and retry count 0 | PASS |
| ConvergenceWarning/failure is technical STOP | fit warning escalated; orchestration preserves marker and partial directory | PASS |
| No retry/delete/overwrite/repair | existing evidence fails closed; exception reports consumed attempt; no cleanup/retry loop | PASS |
| Post-fit immutability checks | source/spec/dependency/code pins, builder bytes, marker SHA and repository state checked again | PASS |
| Exact five artifact files / checksum coverage | ARTIFACT_FILES; four sorted checksum entries exclude checksum file itself | PASS |
| Bundle hash | SHA-256 of exact checksums.sha256 bytes | PASS |
| Reload without fit/predict | reload checks byte hashes, seven-column manifest, identity/state linkage, width/classes/counts/finite state; no fitting/prediction | PASS |
| No metrics or prediction dependency/call | no sklearn.metrics imports; no predict/predict_proba/score calls | PASS |
| Explicit creation flag, no default create | main requires --create-artifact plus separate authorization object | PASS |

Future directory file set remains exactly:

```text
checksums.sha256
metadata.json
model.joblib
scaler.joblib
training_manifest.csv
```

These are a future contract, not files generated or production-reloaded here.
A failed future attempt after marker creation permanently consumes that attempt;
no automatic/manual retry, parameter change, partial-artifact repair or replacement.

## 10. Actions NOT performed on real data

```text
real build_training_manifest = NOT RUN
real _capture / _apply / match_k replay path = NOT RUN
real ST2 replay = NOT RUN
real elo_diff generation = NOT RUN
real training manifest generation/serialization = NOT RUN
real estimator construction = NOT RUN
real scaler fit / fit_transform = NOT RUN
real classifier fit = NOT RUN
real artifact creation = NOT RUN
real artifact reload = NOT RUN
ST2 artifact attempt marker creation = NOT RUN
production model/scaler serialization = NOT RUN
prediction = NOT RUN
metrics = NOT RUN
2025 performance = NOT INSPECTED
Hyakunen = NOT READ
ongoing 2026/27 = NOT READ
prospective outcomes = NOT READ
prediction CSV / sidecar = NOT READ OR MODIFIED
network = NO
--create-artifact = NOT RUN
full pytest = NOT RUN
production activation / Champion promotion = NOT RUN
source/test/spec/data/model/requirements modifications = NO
push = NOT PERFORMED
```

## 11. Publication validation and final readiness gate

Before evidence-document creation, git status --short was again empty.
Final pre-commit tree change set: this document ONLY (staged addition); no other
tracked or untracked change. git diff --check: PASS; git diff --cached --check:
PASS. Builder/spec/tests were rehashed again at publication validation and remain
equal to section 1. Commit only this document as:

```text
docs: preflight ST2 prospective artifact creation
```

The committed handoff must have a clean tree, confirmed in the final task report.
Attempt marker and ST2 output directory remain absent; prior retrospective marker
SHA remains unchanged. No production file was created by this preflight.

```text
READY_FOR_ONE_ST2_PROSPECTIVE_ARTIFACT_CREATION
```

This is READINESS ONLY, not execution authorization. A separate exact-HEAD
authorization is still required for the future one-shot creation. Never rerun a
creation attempt after its marker is consumed. This preflight did not set formal
artifact authorization or execute the creation CLI.

Review status:
`ST2_PROSPECTIVE_ARTIFACT_PREFLIGHT_READY_FOR_REVIEW`.
