# J.League 2026/27 ongoing-v2 activation preflight

Date: 2026-10-04  
Mode: read-only production preflight plus docs report

## 1. Scope

This preflight verifies, without activating ongoing-v2, that the frozen
ongoing-v1 production state is still the exact migration baseline, the v1-to-v2
migration helper classifies that state deterministically in memory, and the six
immutable prospective prediction rows can be bound through the frozen identity
witness. It does not authorize or perform an operational migration.

The preflight began with a clean working tree at exact HEAD
`b93e232537d0d19f306e45ac0c8d6fec2cfb3954`.

## 2. Reviewed implementation commit

Reviewed implementation:

```text
b93e232537d0d19f306e45ac0c8d6fec2cfb3954
feat: implement ongoing ID namespace v2
```

Authoritative contract:
`docs/JLEAGUE_2026_27_ID_NAMESPACE_IMPLEMENTATION_FREEZE_SPEC.md`.

The implementation freeze remains
`FROZEN_FOR_ONE_ID_NAMESPACE_IMPLEMENTATION`. No source or test code was
changed during this preflight.

## 3. Frozen production v1 baseline verification

`data/processed/jleague/2026_27/latest.json` still points to the exact frozen
baseline:

| Check | Observed | Result |
| --- | --- | --- |
| revision ID | `71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538` | PASS |
| format version | `ongoing-v1` | PASS |
| sequence | 8 | PASS |
| publication status | `published` | PASS |
| total fixtures | 380 | PASS |
| completed | 80 | PASS |
| candidate | 0 | PASS |
| scheduled | 300 | PASS |
| nonblank operational `match_id` | 87 | PASS |

No newer or different baseline was adopted.

## 4. Production artifact hashes

| Protected artifact | SHA-256 | Result |
| --- | --- | --- |
| `latest.json` | `c202a103ce7d852cd661a3c956c5e6568ff4fde0a9bc0f7e374ff90d5ff59caf` | unchanged |
| frozen v1 `manifest.json` | `c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34` | exact / unchanged |
| frozen v1 `observations.json` | `5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc` | exact / unchanged |
| frozen v1 `schedule.csv` | `599ad3dad9b30bf440d5e50b9867fd55d796b0a5a7bcc5a9d13a5b44526f1bd0` | exact / unchanged |
| frozen v1 `completed_matches.csv` | `ba9f96d4cbdf4a85e57a578ef46b358d77fbd94669c8c849bfdbf26bd262614d` | unchanged |
| `xg_challenger_prospective.csv` | `32fedd4f6b71d8f83e3275feb56653ff80b24a11514c7fd3df1854f58679d6aa` | exact / unchanged |
| `model_architecture_prospective.csv` | `e47d8a5df136939d3d629c4c0826e23c382786b3d99856987a3964b5842854ec` | exact / unchanged |

## 5. Read-only migration simulation result

`src.collect.jleague_ongoing.migrate_v1_to_v2` was called directly against the
real frozen v1 revision. Its return values were inspected in memory only. The
required preflight sentinels were used:

```text
established_snapshot = PREFLIGHT_ONLY_SNAPSHOT
established_revision = PREFLIGHT_ONLY_REVISION
```

Neither sentinel was persisted. `process_snapshot()` was not called, and no raw
snapshot, run, revision, root projection, or bridge ledger was created.

The helper returned 380 migrated rows. Its migration metadata identified the
exact frozen source revision, manifest hash, observations hash, source row count
380, bridge count 80, page-only count 7, and policy
`ongoing-v1-to-v2-id-namespace-v1`.

## 6. 80 / 7 / 293 classification result

| Migrated class | Count | Contract result |
| --- | ---: | --- |
| completed with both namespaces | 80 | PASS |
| scheduled with match-page ID only | 7 | PASS |
| scheduled with both IDs blank | 293 | PASS |
| candidate | 0 | PASS |

For all 80 completed rows, operational `match_id` projects from
`data_site_match_id` with namespace `jleague_data_site`. For all seven page-only
rows, it projects from the exact `match_page_id` in the evidence URL with
namespace `jleague_match_page`. The seven rows all recover accepted-history
origin revision, origin snapshot, evidence SHA-256, and fetched UTC. All 293
blank rows retain blank typed IDs, operational ID, and namespace.

Namespace-local match-page IDs, namespace-local Data Site IDs, and nonblank
operational IDs are each unique.

## 7. Bridge simulation result

The migration returned exactly 80 bridges. Every completed pair satisfies
`match_page_id != data_site_match_id`. Bridge IDs, fixture keys, match-page IDs,
and Data Site IDs are unique in their required domains. No bridge was written to
production.

## 8. Frozen prediction hash verification

| Prediction artifact | Rows | SHA-256 result |
| --- | ---: | --- |
| `data/processed/predictions/xg_challenger_prospective.csv` | 2 | exact |
| `data/processed/predictions/model_architecture_prospective.csv` | 4 | exact |
| total | 6 | PASS |

Both schemas and row counts passed the frozen binding builder's exact checks.
The existing prediction rows and bytes were not changed.

## 9. Identity witness verification

The immutable published witness revision is:

```text
revision: 2758a644ff46888993f79fa44987079b187196e0ed204fb863ea645ff647dd3c
manifest SHA-256: c7bfa3b9bd113c1c34e016625a23935ce6bb712de4cdcc9b47bd5187fce044c2
```

The revision is published, the manifest hash is exact, and every artifact named
by its manifest is internally hash-consistent. Only the two frozen mappings were
validated:

| match-page ID | fixture key | match date | home TeamMaster | away TeamMaster |
| --- | --- | --- | --- | --- |
| `100903` | `j1_2026_2027:kashima:gosaka` | 2026-10-09 | `team_0008` | `team_0005` |
| `100901` | `j1_2026_2027:kashiwa:kobe` | 2026-10-09 | `team_0009` | `team_0011` |

No other mapping was inferred.

## 10. Temporary six-row sidecar bootstrap result

`src.modeling.prediction_identity.build_frozen_prediction_bindings` was invoked
with the repository and immutable witness as read-only inputs. Its output path
was inside an OS temporary directory outside the repository.

The temporary result contained exactly six rows: two XG rows and four model
architecture rows. Its fixture set contained only the two frozen fixture keys,
and every row used namespace `jleague_match_page`. Both uniqueness contracts
passed:

- `(prediction_artifact, prediction_match_id, model_version)`
- `(prediction_artifact, fixture_key, model_version)`

`validate_complete_sidecar` passed against the temporary file with complete
one-to-one coverage. The temporary directory and file were then deleted.

## 11. Production sidecar absence confirmation

The production path below did not exist before, during, or after the preflight:

```text
data/processed/predictions/2026_27_prediction_fixture_bindings.csv
```

No production prediction binding sidecar was created.

## 12. Protected artifact before/after verification

The protected baseline, completed-match, and prediction files listed in Section
4 were hashed immediately before and after the in-memory migration and temporary
bootstrap checks. Their content hashes and mtimes were identical. The production
latest pointer still targets the same ongoing-v1 revision at sequence 8.

Focused non-network tests also passed:

```text
tests/test_prediction_identity.py: 6 passed
tests/test_jleague_ongoing_update.py: 29 passed
```

## 13. First-v2 expected behavior

The first real v2 processing attempt must use the frozen v1 revision above as
its migration source and a newly authorized immutable Data Site listing as its
real source snapshot. That real snapshot is the migration boundary. There is no
standalone rewrite-only migration revision.

The implementation must not guess identifiers, enumerate URLs, or infer
outcomes. A complete, validated production prediction sidecar must exist before
a transition affecting an already predicted fixture can publish.

The predicted 2026-10-09 fixtures retain their known match-page identities:

- Kashima vs G Osaka: `100903`
- Kashiwa vs Kobe: `100901`

Their future Data Site `match_card_id` values are unknown and must come only
from a future immutable Data Site listing observation. If that observation
supplies different Data Site IDs and every gate passes, the conceptual event set
includes `identity_bridge_established` and `identity_namespace_transition`, plus
candidate or completed events supported by the real source state. Even if two
scalar values happen to be equal, namespace provenance still determines the
transition semantics.

## 14. Frozen future operational activation sequence

This sequence is documented for a later separately authorized task and was not
executed here:

1. Separately authorize and materialize the production prediction binding sidecar.
2. Revalidate its six rows and immutable prediction hashes.
3. Wait until the 2026-10-09 matches have actually completed.
4. Fetch a new immutable Data Site listing only in the later operational task.
5. Use explicit official match pages for completion verification where required.
6. Create the first real ongoing-v2 snapshot.
7. Process it once.
8. Verify v1-to-v2 migration metadata.
9. Verify bridge/event counts and prediction compatibility.
10. If held, do not repair by guessing; inspect the held revision.
11. If published, verify root/latest projection and immutable revision hashes.
12. Only then update and publish completed XG for 2026-10-09.
13. Verify that 2026-10-10 becomes the nearest unfinished date.
14. Run the rolling-XG dry-run for 2026-10-10.
15. Keep production prediction as a separate explicit action.

## 15. Explicit actions not performed

- live HTTP: NOT RUN
- `capture --fetch`: NOT RUN
- real snapshot creation: NOT RUN
- `process_snapshot()` on production: NOT RUN
- production v1-to-v2 migration: NOT RUN
- production latest or root projection update: NOT RUN
- production `identity_bridges.csv` creation: NOT RUN
- production prediction sidecar creation: NOT RUN
- prediction: NOT RUN
- XG collection or update: NOT RUN
- evaluation: NOT RUN
- model fit or refit: NOT RUN
- production raw/data/model/prediction modification: NOT RUN

## 16. Final gate

Every exact read-only invariant passed:

```text
READY_FOR_PRODUCTION_SIDECAR_BOOTSTRAP
```

This gate authorizes nothing automatically. It means only that a next,
separately reviewed task may create the real six-row prediction binding sidecar.
It does not authorize v2 snapshot capture, production migration, the 2026-10-09
result update, prediction, or XG update.
