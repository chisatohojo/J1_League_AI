# J.League 2026/27 prediction binding bootstrap record

Date: 2026-10-04  
Operation: single production artifact bootstrap

## 1. Scope

This record covers the one-time exclusive creation and read-only validation of:

```text
data/processed/predictions/2026_27_prediction_fixture_bindings.csv
```

It does not activate ongoing-v2 or authorize any live collection, result update,
prediction, XG update, or migration.

## 2. Authorizing preflight commit

The bootstrap began from clean exact HEAD:

```text
f5ec5c2e6aa902ce1e39814f6d4d75b149bda59a
docs: record ongoing v2 activation preflight
```

The authorizing report gate was:

```text
READY_FOR_PRODUCTION_SIDECAR_BOOTSTRAP
```

## 3. Pre-bootstrap invariants

Before the builder was called:

- the production sidecar did not exist;
- the working tree was clean;
- production latest pointed to the exact frozen revision;
- the frozen v1 manifest, observations, and schedule hashes were exact;
- both immutable prediction hashes, schemas, and row counts were exact; and
- the identity witness revision was published and internally hash-consistent.

The production ongoing state was:

| Field | Value |
| --- | --- |
| revision | `71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538` |
| format | `ongoing-v1` |
| sequence | 8 |
| publication | `published` |
| manifest SHA-256 | `c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34` |
| observations SHA-256 | `5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc` |
| schedule SHA-256 | `599ad3dad9b30bf440d5e50b9867fd55d796b0a5a7bcc5a9d13a5b44526f1bd0` |

## 4. Frozen prediction artifact hashes

| Artifact | Rows | Pre-bootstrap SHA-256 |
| --- | ---: | --- |
| `data/processed/predictions/xg_challenger_prospective.csv` | 2 | `32fedd4f6b71d8f83e3275feb56653ff80b24a11514c7fd3df1854f58679d6aa` |
| `data/processed/predictions/model_architecture_prospective.csv` | 4 | `e47d8a5df136939d3d629c4c0826e23c382786b3d99856987a3964b5842854ec` |

## 5. Identity witness revision and hash

```text
revision: 2758a644ff46888993f79fa44987079b187196e0ed204fb863ea645ff647dd3c
manifest SHA-256: c7bfa3b9bd113c1c34e016625a23935ce6bb712de4cdcc9b47bd5187fce044c2
```

The witness was published. Every file named by its manifest matched its recorded
hash.

## 6. Bootstrap method

The existing offline implementation was used directly:

```text
src.modeling.prediction_identity.build_frozen_prediction_bindings
```

It was invoked exactly once with the repository root, frozen witness revision,
production sidecar output path, and all frozen defaults. It created the file
exclusively. The CSV was not hand-written, parameters and mappings were not
overridden, and there was no retry.

## 7. Sidecar path

```text
data/processed/predictions/2026_27_prediction_fixture_bindings.csv
```

This was the only production data artifact created by the task.

## 8. Exact schema

The exact 11-column schema and header are:

```text
prediction_artifact
prediction_match_id
model_version
fixture_key
prediction_id_namespace
identity_witness_revision_id
identity_witness_manifest_sha256
match_date
home_team_id
away_team_id
prediction_generated_at
```

## 9. Sidecar row count

```text
6
```

All six frozen prediction rows are covered. There are no partial, extra, or
orphan binding rows.

## 10. Sidecar SHA-256

```text
f32d34931dc0c253a885b2a862f825d8aaf462f86c18a881a5b6fb91183de7c5
```

This is the immutable production binding bootstrap baseline.

## 11. Sidecar byte size

```text
2241 bytes
```

The sidecar was not modified after this hash and size were recorded.

## 12. Artifact breakdown

| Prediction artifact | Binding rows |
| --- | ---: |
| `data/processed/predictions/xg_challenger_prospective.csv` | 2 |
| `data/processed/predictions/model_architecture_prospective.csv` | 4 |
| total | 6 |

## 13. Fixture breakdown

| Fixture key | Match-page ID | Match date | Home | Away | Binding rows |
| --- | --- | --- | --- | --- | ---: |
| `j1_2026_2027:kashima:gosaka` | `100903` | 2026-10-09 | `team_0008` | `team_0005` | 3 |
| `j1_2026_2027:kashiwa:kobe` | `100901` | 2026-10-09 | `team_0009` | `team_0011` | 3 |

Every row has `prediction_id_namespace = jleague_match_page`. No Data Site ID
was inferred, invented, or inserted.

## 14. Uniqueness validation

Both frozen uniqueness contracts passed:

- primary key `(prediction_artifact, prediction_match_id, model_version)`;
- fixture-aware key `(prediction_artifact, fixture_key, model_version)`.

There are no duplicates under either key.

## 15. Complete-sidecar validation

The real production sidecar was immediately passed to:

```text
src.modeling.prediction_identity.validate_complete_sidecar
```

Result: **PASS**. Coverage is 6/6 across both frozen prediction artifacts, with
no orphan row and no identity, date, team, or `prediction_generated_at`
mismatch.

Focused non-network validation also passed:

```text
tests/test_prediction_identity.py: 6 passed
```

## 16. Original prediction hashes after bootstrap

| Artifact | Rows | Post-bootstrap SHA-256 | Changed |
| --- | ---: | --- | --- |
| `data/processed/predictions/xg_challenger_prospective.csv` | 2 | `32fedd4f6b71d8f83e3275feb56653ff80b24a11514c7fd3df1854f58679d6aa` | NO |
| `data/processed/predictions/model_architecture_prospective.csv` | 4 | `e47d8a5df136939d3d629c4c0826e23c382786b3d99856987a3964b5842854ec` | NO |

All other files under the production ongoing and prediction artifact trees were
also hash- and mtime-identical before and after the builder invocation.

## 17. Production latest after bootstrap

The production ongoing state remains:

| Field | Value |
| --- | --- |
| revision | `71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538` |
| format | `ongoing-v1` |
| sequence | 8 |
| publication | `published` |

No v2 revision, latest update, root projection update, or identity bridge was
created.

## 18. Explicit actions not performed

- source or test code change: NOT PERFORMED
- live HTTP or capture: NOT RUN
- new J1 snapshot: NOT CREATED
- production `process_snapshot()`: NOT RUN
- v1-to-v2 migration materialization: NOT RUN
- latest or root projection update: NOT RUN
- production `identity_bridges.csv`: NOT CREATED
- result update: NOT RUN
- XG update: NOT RUN
- prediction generation or regeneration: NOT RUN
- evaluation: NOT RUN
- model fit or refit: NOT RUN
- existing prediction CSV modification: NOT PERFORMED

## 19. Final gate

The sidecar was created once, has the exact schema and six rows, passes both
uniqueness contracts and complete validation, leaves the immutable predictions
unchanged, and leaves production ongoing at v1 sequence 8.

```text
PRODUCTION_SIDECAR_BOOTSTRAPPED
```

This means only that the immutable prediction binding prerequisite now exists.
It does not authorize immediate v2 capture or migration. The next live
operational sequence must wait for the separately authorized 2026-10-09 update
task; nothing was fetched in this bootstrap.
