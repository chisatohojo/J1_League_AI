# ST2 prospective comparison: 2026-10-09 production append record

## Scope and Git classification

Task: POST-PRODUCTION RECORDING ONLY. Authorizing task attachment:
`b6b78846-848a-4d84-bba6-86865e95ba85`.

The production append already succeeded exactly once. This task did not rerun
prediction, dry-run, tests, preflight, state replay or probability generation.
It records the existing immutable evidence and commits the authorized identity
registry suffix; it does not amend the previous dry-run commit.

`data/processed/predictions/2026_27_prediction_fixture_bindings.csv` is an
intentionally Git-tracked, append-only production identity registry.
`git ls-files --error-unmatch` confirmed its tracked status.

`data/processed/predictions/season_transition_st2_prospective.csv` is intentionally
ignored local immutable prospective evidence. `git check-ignore -v` confirmed
the existing `.gitignore:22:/data/processed/*` policy. The prediction CSV is not
force-added or committed.

A modified tracked sidecar immediately after an authorized append is EXPECTED
production mutation. The previous task's immediate-clean-tree condition conflicted
with this tracked-sidecar operation; it did not invalidate the successful append.
The original sidecar is not restored. Clean tracked state is established by this
separate authorized recording commit.

## Original production execution

- Execution HEAD: `897bdcac87037c2b4e76ab5e40d24a1a56ad170b`.
- Reviewed implementation HEAD: `f906ec922c0a307a8a63cf409189a424389a833b`.
- Production invocation count: `1`.
- Retries: `0`.
- Start UTC: `2026-10-08T10:32:42.1733704Z`.
- End UTC: `2026-10-08T10:32:44.6453153Z`.
- Exit code: `0`.
- Complete stderr: empty (zero characters).

Complete operational stdout:

```json
{"status": "COMPLETE", "target_date": "2026-10-09", "target_count": 2, "already_predicted_count": 0, "would_append_count": 2, "source_revision": "71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538"}
```

Target date: `2026-10-09`. Target count: `2`.
Actual prediction rows appended: `2`.
Actual common-sidecar bindings appended: `2`.
Comparison/model version: `season_transition_st2_vs_a_20261006_v1`.

## Immutable prediction artifact

Path: `data/processed/predictions/season_transition_st2_prospective.csv`.

SHA-256:
`da2e23157a281b9d2681efa1b9066253623a53e56dbd45da5d9f53aaf4758669`.

Local artifact existence: PASS. Prediction rows: `2`.
Exact ordered frozen schema: `28` columns, PASS.
One-to-one coverage by the two appended sidecar bindings: PASS.

Read-only recording validation inspected only operational metadata and the header;
it did not parse individual Elo, probability or predicted-class columns.
The full artifact was read as uninterpreted bytes solely for SHA-256 validation.
No result/probability join or performance evaluation occurred.

## Append-only identity registry

Path: `data/processed/predictions/2026_27_prediction_fixture_bindings.csv`.

| Property | Before | After |
| --- | --- | --- |
| Rows | 6 | 8 |
| SHA-256 | `f32d34931dc0c253a885b2a862f825d8aaf462f86c18a881a5b6fb91183de7c5` | `1722c487b5fdf60709382ff8b696bbfff3b0cf4499128299e8c18b8eda9a8db1` |

Read-only comparison against the exact pre-append Git HEAD blob confirmed:

- Original six rows/header remain an exact byte-identical prefix: PASS.
- Exactly two suffix rows appended; no existing row modified/deleted/reordered: PASS.
- Exact unchanged 11-column sidecar schema: PASS.
- Both suffix rows have prediction_artifact =
  `data/processed/predictions/season_transition_st2_prospective.csv`: PASS.
- Both suffix rows have model_version =
  `season_transition_st2_vs_a_20261006_v1`: PASS.
- Unique prediction key (prediction_artifact, prediction_match_id, model_version): PASS.
- Unique fixture-aware key (prediction_artifact, fixture_key, model_version): PASS.
- Exact prediction/binding identity, date, team-ID and generation-time coverage: PASS.
- Git sidecar diff: two additions, zero deletions.

The two identity suffix rows are committed because the registry is tracked.
The associated prediction values remain only in the ignored local artifact.

## Source and model provenance

Source revision:
`71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538`.

Source observed_at: `2026-10-03T23:04:09.053484+00:00`.

ST2 model version: `season_transition_st2_20261006_v1`.
ST2 artifact hash:
`f20359a1c12a4508d1a593e266a92f25fb8cab597bbbe3ace7a19ae5b0160c82`.

Champion A model version: `operational_champion_20260922_v1`.
Champion A artifact hash:
`2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1`.

Protected 41 files unchanged: PASS. Their hashes were compared with the original
pre-production snapshot, both after append and again during this recording task.
This covers both frozen model bundles, consumed ST2 marker, historical inputs,
current/frozen ongoing revision, latest pointer, TeamMaster, raw boundary manifest,
freeze spec, reviewed dry-run document and implementation code.

Writer journal absent: PASS. Writer lock absent: PASS.
No recovery, source update, artifact rebuild, model fit/refit or further prediction
date was executed.

## No-peeking and recording boundary

- Probabilities exposed = NO.
- Elo exposed = NO.
- Predicted classes exposed = NO.
- Metrics = NOT RUN.
- Prospective outcomes joined = NO.
- Network = NO.
- Production retry = NO.
- Dry-run rerun = NO.
- Prediction CSV committed = NO.
- Tests/full pytest = NOT RUN.
- Previous dry-run commit amended = NO.
- Sidecar restored = NO.
- Code/tests/spec/data/model regeneration = NO.
- Push = NOT PERFORMED.

Exactly two authorized tracked changes:

1. `data/processed/predictions/2026_27_prediction_fixture_bindings.csv`.
2. `docs/CHAMPION_A_SEASON_TRANSITION_PREDICTION_APPEND_20261009.md`.

Validate git diff --check, stage only these paths, and commit as
`data: record ST2 comparison for 2026-10-09`. Do not push.
The authorized registry append is preserved; no prediction values are stored here.

## Final gate

```text
ST2_PROSPECTIVE_20261009_PRODUCTION_APPEND_RECORDED_AWAITING_REVIEW
```
