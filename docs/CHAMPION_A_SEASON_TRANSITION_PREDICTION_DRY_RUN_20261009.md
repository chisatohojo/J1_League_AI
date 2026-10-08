# ST2 prospective comparison: 2026-10-09 read-only dry-run evidence

## Scope and reviewed authority

Task: REAL READ-ONLY DRY-RUN ONLY / nonperformance evidence.
Authorizing task attachment: `65beeb3e-36bc-45de-8b38-10ccf7254535`.
Reviewed execution HEAD: `f906ec922c0a307a8a63cf409189a424389a833b`
(`fix: reject partial ST2 date batches`). Initial tracked working tree: clean.

Reviewed implementations:
`src/modeling/season_transition_st2_prediction.py` and
`src/modeling/prediction_identity.py`. No code/test/spec/data/model edits.

Freeze authority:
`docs/CHAMPION_A_SEASON_TRANSITION_PROSPECTIVE_FREEZE_SPEC.md`,
commit `fb4cef5fea338b99d62f5b2a6c7be5079b4d6f33`,
SHA-256 `daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3`.

Prospective boundary: `2026-10-06T18:24:19+09:00`.
Comparison/model version: `season_transition_st2_vs_a_20261006_v1`.

This task allowed only local read-only source/artifact validation, live Elo
reconstruction, persisted scaler transform/model predict_proba, and in-memory
comparison/binding construction. It did not authorize production append,
journal recovery, fitting, evaluation, source collection, v2 activation or promotion.

## Precheck

- Exact reviewed HEAD and clean tracked tree: PASS.
- Both persisted artifact directories and their exact five-file sets: PASS.
- Read-only A and ST2 artifact validators: PASS, without fit or prediction.
- ST2 attempt marker exists; state = `ATTEMPT_CONSUMED`: PASS.
- Common sidecar exists: PASS.
- ST2 prediction output absent: PASS.
- Writer lock and journal absent: PASS.
- No production authorization required, set or consumed for this task.

## Exactly one command invocation

```powershell
.\.venv\Scripts\python.exe -m src.modeling.season_transition_st2_prediction --dry-run
```

- Invocation count: `1`.
- Automatic/manual retries: `0`.
- Start UTC: `2026-10-08T08:33:57.9155083Z`.
- End UTC: `2026-10-08T08:34:00.0413373Z`.
- Exit code: `0`.

Complete stdout (one JSON line followed by the process newline):

```json
{"status": "DRY_RUN", "target_date": "2026-10-09", "target_count": 2, "already_predicted_count": 0, "would_append_count": 2, "source_revision": "71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538"}
```

Complete stderr: empty (zero characters). No warnings/errors were emitted.
Only operational fields were printed; no probabilities, Elo values or predicted classes.

## Published source and frozen cohort

Current accepted source revision:
`71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538`.

Source observed_at: `2026-10-03T23:04:09.053484+00:00`.
Manifest SHA-256: `c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34`.

The current revision is also the frozen boundary revision in this run.
It was validated as published, with latest-pointer/manifest/file hash integrity.
Each immutable revision file was covered once by the before/after hash audit
because these two authority roles resolved to the same directory.

Frozen snapshot ID: `20261003T230410579984Z-794e906d`.
Frozen cohort: exactly `300` fixtures, reconstructed from the pinned boundary
revision in canonical match_date/fixture_key order, not a later date filter.
Ordered fixture_key SHA-256:
`b63bce0289b80d096599a2f6343c48073c3617d919b3bf7153683e2089dfdcbf`.

Full schedule: `380` fixtures. Target date: `2026-10-09`.
Target count: `2`. Already predicted: `0`. Would append: `2`.
Actual prediction/binding append: `0` / NO.

## Frozen model integrity

| Branch | Model version | Artifact SHA-256 |
| --- | --- | --- |
| Champion A | `operational_champion_20260922_v1` | `2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1` |
| ST2 | `season_transition_st2_20261006_v1` | `f20359a1c12a4508d1a593e266a92f25fb8cab597bbbe3ace7a19ae5b0160c82` |

Artifact hash is the SHA-256 of exact checksums.sha256 bytes.
Both bundles passed their read-only validators before the command and were
validated again internally by the one dry-run. Neither estimator was fitted/refitted.
The consumed ST2 creation marker remained unchanged.

## Operational contract validation

The PASS statements below follow from successful completion of the reviewed
fail-closed dry-run path and the separate byte-immutability checks, not a second
prediction invocation or independent performance evaluation.

| Gate | Result |
| --- | --- |
| Frozen cohort count/order/hash validation | PASS |
| Current published revision, schedule/identity/completed-subset validation | PASS |
| Entire nearest unfinished calendar-date batch selection | PASS (2 fixtures) |
| Official nonblank IDs for every target | PASS |
| Explicit namespace / immutable identity witness resolution | PASS |
| Common sidecar baseline schema, uniqueness and exact coverage | PASS |
| No non-journal partial existing comparison batch | PASS (0 of 2 existing) |
| Champion A persisted artifact integrity | PASS |
| ST2 persisted artifact integrity | PASS |
| Ordinary 2015-2025 source hashes, population and identities | PASS |
| Hyakunen source integrity and regulation-time semantics | PASS |
| Strictly-prior official completed 2026/27 history integrity | PASS |
| Independent A/ST2 state and strict-date batching | PASS |
| Same-date team-duplicate rejection / capture-before-update chronology | PASS |
| Verified official kickoff still future at generation time | PASS |
| Trusted prediction time strictly after prospective boundary | PASS |
| Both probability branches: shape, class order, finite/range/sum only | PASS |
| Exact ordered 28-column output / model_version alias | PASS |
| One common-sidecar binding per comparison row structurally constructible | PASS |
| Prediction/binding appendability (in-memory validation only) | PASS |
| Would append count | 2 |
| Actual append | NO (0) |

Ordinary history and Hyakunen/strictly-prior ongoing results were used only to
reconstruct state, never joined to probabilities or scored. Hyakunen used K30
without ordinary ordinal contributions; ongoing ordinary ordinals reset while
ratings carried. Target-date results were not loaded/applied.

The probability structural gate reports no individual values. This document
contains no model feature values or predicted classes.

## Write firewall and immutable evidence

Common sidecar:
`data/processed/predictions/2026_27_prediction_fixture_bindings.csv`.

- Before SHA-256: `f32d34931dc0c253a885b2a862f825d8aaf462f86c18a881a5b6fb91183de7c5`.
- After SHA-256: `f32d34931dc0c253a885b2a862f825d8aaf462f86c18a881a5b6fb91183de7c5`.
- Exact byte identity: PASS.

Prediction output:
`data/processed/predictions/season_transition_st2_prospective.csv`.

- Before: ABSENT.
- After: ABSENT.
- Writer lock before/after: ABSENT / ABSENT.
- Writer journal before/after: ABSENT / ABSENT.
- Journal creation/recovery: NOT RUN.
- Prediction/sidecar/data/model evidence writes: ZERO.
- Protected files compared: `39`; differences: `0`.
- Artifact exact-five-file sets after run: PASS.
- Artifact/marker/input immutability: PASS.

The following hashes were captured before the invocation and independently
recomputed afterward. The single SHA column is identical before and after;
no source outcome or prediction value is included.

| Protected relative path | Before = after SHA-256 | Immutability |
| --- | --- | --- |
| `data/master/teams.csv` | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` | PASS |
| `data/processed/jleague/2015_matches_probe.csv` | `ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353` | PASS |
| `data/processed/jleague/2016_matches_probe.csv` | `4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f` | PASS |
| `data/processed/jleague/2017_matches_probe.csv` | `d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b` | PASS |
| `data/processed/jleague/2018_matches_probe.csv` | `f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681` | PASS |
| `data/processed/jleague/2019_matches_probe.csv` | `3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f` | PASS |
| `data/processed/jleague/2020_matches_probe.csv` | `fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17` | PASS |
| `data/processed/jleague/2021_matches_probe.csv` | `298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6` | PASS |
| `data/processed/jleague/2022_matches_probe.csv` | `d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2` | PASS |
| `data/processed/jleague/2023_matches_probe.csv` | `6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9` | PASS |
| `data/processed/jleague/2024_matches_probe.csv` | `4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1` | PASS |
| `data/processed/jleague/2025_matches_probe.csv` | `c94411ed299ff90d86c3b55a3b17bd3e0dfc127d58c060109658d235bb24d18d` | PASS |
| `data/processed/jleague/2026_27/latest.json` | `c202a103ce7d852cd661a3c956c5e6568ff4fde0a9bc0f7e374ff90d5ff59caf` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/change_log.csv` | `87ca1f9f6b57b49e6d5e7be844677a2156acc1017e82dc6cb4058dda71e28013` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/changes.json` | `55859cc416b6ae3a7607fbefe023a31b8622208b5507079a958a0ab7db3b91c4` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/completed_matches.csv` | `ba9f96d4cbdf4a85e57a578ef46b358d77fbd94669c8c849bfdbf26bd262614d` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/fixture_identity.csv` | `953537cdc3418dad978b0ddbc0cf289876bade1ebb35a1adbdb6af53edc1d739` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/manifest.json` | `c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/observations.json` | `5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/review.md` | `62df19e27804e8c566d66d9cf099892d9f0a7bd15a7316b189c561fc3a029ace` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/schedule.csv` | `599ad3dad9b30bf440d5e50b9867fd55d796b0a5a7bcc5a9d13a5b44526f1bd0` | PASS |
| `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538/update_summary.json` | `7e5b4d0f0fb27be566cdfdd286ab73ace56cf59931bd73767beb76a78510cbcb` | PASS |
| `data/processed/jleague/2026_hyakunen/matches.csv` | `9f871594e5216c1c89e69fcef835c641f3a4b5dbefce8d138e79881494c71f8c` | PASS |
| `data/processed/model_season_transition/st2_prospective_artifact_attempt.json` | `883f1c8beef1b902a1f37dad7ce683f4aef76fe544b4525440f8419b346a402d` | PASS |
| `data/processed/predictions/2026_27_prediction_fixture_bindings.csv` | `f32d34931dc0c253a885b2a862f825d8aaf462f86c18a881a5b6fb91183de7c5` | PASS |
| `data/raw/jleague/2026_27/snapshots/20261003T230410579984Z-794e906d/manifest.json` | `dfbb3fd9ddaaf066bb4e8da027e2dda304b9dc0569cf406d15f05c9d1d1ab27e` | PASS |
| `docs/CHAMPION_A_SEASON_TRANSITION_PROSPECTIVE_FREEZE_SPEC.md` | `daa26ac92394edcaaa32c07e9b382cb744e380a454e10b548afeff3cf5a28fe3` | PASS |
| `models/model_a/operational_champion_20260922_v1/checksums.sha256` | `2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1` | PASS |
| `models/model_a/operational_champion_20260922_v1/metadata.json` | `bd1eb92c25bdb56a836ef7bfe3fcb13b0137a2ece01b6095e7d100e1f5afdd19` | PASS |
| `models/model_a/operational_champion_20260922_v1/model.joblib` | `60636e4652bce98b76c394310947b1b8923a8bf18a640d9e7976497989ed54be` | PASS |
| `models/model_a/operational_champion_20260922_v1/scaler.joblib` | `a8a5f176944049c6825071b580c5fe40f5a5fb28f504f8880d028deaf2494750` | PASS |
| `models/model_a/operational_champion_20260922_v1/training_manifest.csv` | `eea7498fabac6acc79a9c297468b470702288b61736b63d90214d741ab8fb32a` | PASS |
| `models/model_season_transition/season_transition_st2_20261006_v1/checksums.sha256` | `f20359a1c12a4508d1a593e266a92f25fb8cab597bbbe3ace7a19ae5b0160c82` | PASS |
| `models/model_season_transition/season_transition_st2_20261006_v1/metadata.json` | `b7e63d1aa8eeb92609250d44f4d80f6f48a6178504366da162df4a5fe55daf68` | PASS |
| `models/model_season_transition/season_transition_st2_20261006_v1/model.joblib` | `fade7e499b3431f222d096e2457e0617576a05d2d6703990bc80af2cfd723879` | PASS |
| `models/model_season_transition/season_transition_st2_20261006_v1/scaler.joblib` | `d6f86513a8254e3450bdee3613996efecfa1baad70dc3f4dd3decb35887f25a3` | PASS |
| `models/model_season_transition/season_transition_st2_20261006_v1/training_manifest.csv` | `61bff7b8ae9fe137327d91a88fbe1b717422b65034cf4a38dc3c70c4579f051a` | PASS |
| `src/modeling/prediction_identity.py` | `0ceef3f74643ef96731eb7a292758f3ff47d904808c5027b79d1f9deb339fa80` | PASS |
| `src/modeling/season_transition_st2_prediction.py` | `de299b6c11f4970740de8a71ccee689edf034185785d17c845669b4730fd02fc` | PASS |

## No-peeking and execution firewall

- Actual append = NO.
- Probability values recorded/exposed = NO.
- Elo values recorded/exposed = NO.
- Predicted classes recorded/exposed = NO.
- Metrics = NOT RUN.
- 2025 performance = NOT INSPECTED.
- Prospective performance = NOT INSPECTED.
- Prospective outcomes joined = NO.
- Network / source collection or update = NO.
- Production authorization = NOT USED.
- Production append = NOT RUN.
- Fit/refit/calibration/tuning = NOT RUN.
- Ongoing-v2 activation / production promotion = NOT RUN.
- Pytest = NOT RUN.
- Full pytest = NOT RUN.
- Code/tests/spec/data/models/sidecar edits = NO.
- Push = NOT PERFORMED.

Only this evidence document is added. Validate git diff --check and commit it
with `docs: dry-run ST2 comparison for 2026-10-09`; do not push.

## Final readiness gate

```text
READY_FOR_ONE_ST2_PROSPECTIVE_20261009_PRODUCTION_APPEND
```

Readiness only: a separate reviewed task and exact production authorization
remain required. No production append was executed or authorized by this dry-run.

Status: `ST2_PROSPECTIVE_20261009_DRY_RUN_READY_FOR_REVIEW`.
