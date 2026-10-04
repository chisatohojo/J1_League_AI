# 2026/27 J1 ID namespace implementation freeze specification

## 1. Purpose and authority

This document freezes one implementation of the reviewed design in
`JLEAGUE_2026_27_ID_NAMESPACE_TRANSITION_SPEC.md`. It removes implementation
choices around the ongoing-v2 boundary, typed identifier schema, migration,
events, and immutable prospective-prediction compatibility.

This is a docs-only freeze. It does not change code, tests, raw snapshots,
processed data, models, or predictions, and it does not execute migration.

The implementation must preserve these absolute boundaries:

- no URL construction or discovery;
- no match-ID enumeration or synthetic ID;
- no fuzzy identity, home/away swap, date inference, or round inference;
- no score/result use as identity-bridge evidence;
- no automatic network access from `process_snapshot()` or migration;
- no rewrite of v1 snapshots/revisions or existing prediction rows; and
- no transition publication when any frozen gate is unresolved.

## 2. Frozen baseline

The only v1 accepted state authorized as the migration source is:

```yaml
format_version: ongoing-v1
revision_id: 71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538
revision_manifest_sha256: c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34
snapshot_id: 20261003T230410579984Z-794e906d
sequence: 8
observations_json_sha256: 5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc
schedule_csv_sha256: 599ad3dad9b30bf440d5e50b9867fd55d796b0a5a7bcc5a9d13a5b44526f1bd0
rows: 380
scheduled: 300
candidate: 0
completed: 80
nonblank_operational_match_id: 87
```

The deterministic v1 identity classification is:

```yaml
completed_with_data_site_and_match_page_ids: 80
completed_equal_cross_namespace_values: 0
scheduled_match_page_only: 7
scheduled_without_identifier: 293
```

All seven scheduled page identities have one exact archived evidence source in
an accepted v1 revision. Migration must recover its URL, SHA-256, fetched UTC,
snapshot, and revision by accepted-history traversal; blank provenance fields
in the latest schedule projection are not permission to invent provenance.

If `latest.json` does not point to the exact revision and manifest digest above
when the first v2 processing attempt begins, migration must stop before writing
a run or revision. A newer or different v1 latest requires a new docs freeze;
the implementation may not silently migrate an older baseline.

## 3. Frozen version boundary

```python
FORMAT_VERSION = "ongoing-v2"
```

The same constant remains the format version written to new raw snapshot,
run, and revision manifests. `COMPLETION_POLICY_VERSION` remains
`official-game-over-v1`. Add exactly:

```python
IDENTITY_BRIDGE_POLICY_VERSION = "official-id-namespace-bridge-v1"
V1_TO_V2_MIGRATION_POLICY_VERSION = "ongoing-v1-to-v2-id-namespace-v1"
```

Frozen boundary rules:

1. Existing ongoing-v1 raw snapshots, runs, revisions, and projections are
   immutable.
2. New captures use ongoing-v2 and continue sequence numbering after the
   verified v1 raw-snapshot chain; the first new snapshot sequence is 9.
3. Readers are version-aware. `read_latest()` can verify an existing v1 or v2
   latest revision. The normal v2 writer never emits v1 artifacts.
4. An already materialized v1 run/revision may be read or replayed without
   mutation. An unprocessed v1 snapshot may not create a new revision after
   the v2 implementation; it stops with an explicit migration-boundary error.
5. The first v2 snapshot may use the exact frozen v1 revision as its previous
   accepted state only through the migration function in Section 7.
6. Once a v2 revision is accepted, every later accepted predecessor must be
   v2. A v2-to-v1 rollback is forbidden.
7. A held first v2 attempt leaves v1 latest unchanged. A later v2 snapshot may
   retry from the same frozen v1 baseline through its own deterministic run.

There is no standalone synthetic raw snapshot and no rewrite-only migration
revision. The first accepted v2 revision contains a real new v2 source snapshot
and records the exact v1 migration dependency in its manifest.

## 4. Stable identity and namespace constants

Freeze:

```text
fixture_key = stable season-local lifecycle identity
```

The exact namespaces are:

```python
MATCH_PAGE_NAMESPACE = "jleague_match_page"
DATA_SITE_NAMESPACE = "jleague_data_site"
```

Both identifiers are strings. `match_page_id` must match `[0-9]{6}` and the
exact official URL suffix. `data_site_match_id` must match `[1-9][0-9]*` and
the exact Data Site `/SFMS02/?match_card_id=...` link. Neither is converted to
integer. Equality of the two strings does not merge their namespaces.

The identity-bound fields are exactly:

```python
IDENTITY_BOUND_FIELDS = (
    "fixture_key",
    "competition_key",
    "home_club",
    "away_club",
    "match_date",
    "round",
)
```

`kickoff_time`, stadium, attendance, broadcast, and display labels are not
bridge identity fields. Their existing schedule/metadata change semantics
remain active.

## 5. Frozen observation schema

### 5.1 Typed fields

Add exactly these v2 fields to every observation:

```text
match_page_id
data_site_match_id
match_id_namespace
match_page_origin_snapshot
match_page_origin_revision
data_site_origin_snapshot
data_site_origin_revision
```

Retain `identity_origin_revision` as a legacy audit field. Do not remove or
rename existing evidence/completion provenance fields.

Internal JSON uses `null` for an absent ID, namespace, snapshot, or revision.
CSV renders those nulls as empty fields. Present IDs and all provenance values
are strings.

### 5.2 Operational projection

`match_id` remains a backward-compatible projection and is derived only by
this table:

| Status | Typed state | `match_id` | `match_id_namespace` |
| --- | --- | --- | --- |
| scheduled | match-page present | `match_page_id` | `jleague_match_page` |
| scheduled | no page; Data Site present | `data_site_match_id` | `jleague_data_site` |
| scheduled | neither present | null | null |
| candidate | Data Site required | `data_site_match_id` | `jleague_data_site` |
| completed | Data Site required | `data_site_match_id` | `jleague_data_site` |

For scheduled rows with both typed IDs, match-page remains the operational
projection. Candidate/completed rows without Data Site ID are invalid. No
other combination is accepted.

Each typed ID must be unique inside its namespace. In addition, projected
nonblank `match_id` remains globally unique across the 380 current rows because
legacy consumers and prediction keys do not include namespace. A cross-
namespace scalar collision that would duplicate projected `match_id` is HOLD,
not an invitation to relax legacy validation.

### 5.3 Exact CSV order

`schedule.csv` and `completed_matches.csv` use exactly this 45-column order:

```text
match_id
season
round
match_date
home_team
away_team
stadium
home_score
away_score
result
fixture_key
status
competition_key
source_season_label
source_year_id
source_frame_id
competition
stage
round_label
round_day
match_date_label
kickoff_time
home_club
away_club
home_team_source_url
away_team_source_url
raw_score_text
attendance_raw
broadcast_raw
source_url
listing_source_url
evidence_url
evidence_type
evidence_sha256
completion_origin_snapshot
evidence_fetched_at_utc
completion_origin_revision
identity_origin_revision
match_page_id
data_site_match_id
match_id_namespace
match_page_origin_snapshot
match_page_origin_revision
data_site_origin_snapshot
data_site_origin_revision
```

`observations.json` contains the same field set, with canonical sorted JSON
keys. `fixture_identity.csv` remains exactly:

```text
fixture_key,match_id,home_club,away_club
```

It is a legacy projection, not the typed bridge source of truth.

## 6. Frozen bridge ledger

Add `identity_bridges.csv` to every v2 immutable revision and to root
projections published through `latest.json`. It contains only established
two-namespace bridges, sorted by `fixture_key`, with exactly these columns:

```text
bridge_id
fixture_key
competition_key
match_page_id
data_site_match_id
match_page_evidence_url
match_page_evidence_type
match_page_evidence_sha256
match_page_evidence_fetched_at_utc
match_page_origin_snapshot
match_page_origin_revision
data_site_source_url
data_site_listing_sha256
data_site_listing_fetched_at_utc
data_site_origin_snapshot
data_site_origin_revision
established_snapshot
established_revision
bridge_policy_version
```

`bridge_policy_version` is always
`official-id-namespace-bridge-v1`. `bridge_id` is SHA-256 of the repository's
canonical `_json()` bytes for exactly:

```text
competition_key
fixture_key
match_page_id
data_site_match_id
match_page_origin_revision
data_site_origin_revision
bridge_policy_version
```

`established_revision` is available before payload generation because revision
ID remains the hash of the frozen run inputs. An established ledger row is
copied byte-for-byte in meaning to later revision ledgers. It is never updated,
removed, or reassigned. Any purported correction is HOLD and requires a new
review/freeze rather than a second bridge for the fixture.

`identity_bridges.csv` is included in the revision manifest SHA map and
publication transaction. It is never created for a page-only or Data-Site-only
fixture.

## 7. Exact v1-to-v2 migration

Implement one pure offline migration function over the frozen accepted v1
records plus their verified accepted-revision history. It must not read HTTP,
modify v1, or use held revisions as provenance.

For every v1 row:

1. Revalidate all 380 fixture keys, coverage, statuses, operational ID
   uniqueness, revision file hashes, and the frozen baseline hashes.
2. Locate typed source evidence only through exact source URLs and accepted
   manifests.
3. Set `data_site_match_id` only when v1 `match_id` exactly equals the ID in
   that row's Data Site `source_url`.
4. Set `match_page_id` only when `evidence_url` is an exact official J1 page,
   its suffix agrees with the page identity, and evidence identity fields agree
   exactly with the observation.
5. Resolve each origin to the earliest accepted v1 revision in which that exact
   fixture/typed-ID/source combination was explicitly observed. The revision's
   source manifest supplies SHA and fetched UTC. A carried value is not a new
   origin.
6. Apply the operational projection from Section 5.2.
7. Materialize one bridge row for each exact completed two-ID pair already
   established by the v1 state. The current boundary v2 snapshot/revision are
   its `established_snapshot`/`established_revision`; v1 origins remain
   separately recorded. A held boundary revision is not accepted provenance;
   a later attempt from v1 materializes its own accepted-state candidates.
8. Assert the exact migrated classification `80 / 0 / 7 / 293` from Section 2.
9. Assert that all 80 completed cross-namespace pairs differ and all seven
   scheduled page identities have exactly one recoverable explicit origin.

Any v1 row not classifiable by these rules is a hard migration failure. ID
syntax, date proximity, row position, or current status may not substitute for
source provenance.

Every v2 revision whose previous accepted revision is the frozen v1 baseline
adds exactly:

```json
"migration": {
  "policy_version": "ongoing-v1-to-v2-id-namespace-v1",
  "source_revision_id": "71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538",
  "source_manifest_sha256": "c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34",
  "source_observations_sha256": "5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc",
  "source_row_count": 380,
  "migrated_bridge_count": 80,
  "migrated_match_page_only_count": 7
}
```

After a v2 revision is accepted, later v2 revisions do not repeat migration;
their ancestry reaches that accepted boundary through
`previous_accepted_revision_id`.

## 8. Frozen source parsing contract

`parse_listing()` supplies only Data Site identity:

- a valid SFMS02 link sets `data_site_match_id`;
- no link sets it to null;
- it never sets `match_page_id`;
- numeric score still requires a Data Site ID; and
- it applies the operational projection appropriate to the parsed status.

`parse_completion_evidence()` returns `match_page_id`, never an overloaded
`match_id`. Existing canonical, competition, date, round, home/away, score, and
game-over validation is unchanged.

`apply_completion_evidence()`:

- copies only the explicit evidence `match_page_id` into the typed page field;
- never replaces `data_site_match_id`;
- leaves candidate/completed operational ID in Data Site namespace;
- makes scheduled operational ID match-page when page evidence exists;
- rejects duplicate page IDs within the page namespace;
- does not treat equal scalar IDs as one source; and
- remains a pure copy operation over its input records.

Snapshot metadata continues to supply evidence/listing SHA and fetched UTC.
The caller attaches origin provenance; the HTML parser does not invent revision
origins.

## 9. Frozen processing order and transition gate

`process_snapshot()` performs exactly this conceptual order:

1. verify v2 snapshot bytes/manifest and lock the writer;
2. resolve current latest and frozen run inputs;
3. load v2 previous state, or apply Section 7 only at the frozen v1 boundary;
4. parse current listing into typed Data Site state;
5. parse/apply current explicit page evidence;
6. hydrate an already accepted bridge into the current row only when all
   identity-bound fields and any current typed IDs agree;
7. carry forward an eligible previous scheduled page identity into the typed
   page field when current explicit page evidence is absent;
8. establish typed bridges that pass every gate below;
9. run the separate existing completion inheritance rule;
10. derive operational `match_id`/namespace from status;
11. calculate changes/events and publication blocks;
12. run coverage, completed-match validation, CSV round-trip, and prediction
    compatibility preflight;
13. write the immutable revision, then publish all projections atomically only
    when no block exists.

Accepted bridge hydration is not new evidence and emits no new bridge event.
It preserves both typed IDs and their original ledger provenance across later
listings. A changed identity-bound field, a different current Data Site ID, or
conflicting current page evidence prevents hydration and produces
`identity_conflict`; the accepted bridge is not edited.

Page carry may occur even when a current scheduled/candidate row has a Data
Site ID, because the IDs are now separate fields. It still requires previous
accepted scheduled page provenance and exact `IDENTITY_BOUND_FIELDS`. Current
explicit page evidence always wins; disagreement is never hidden by carry.

Bridge establishment requires all of:

1. immutable previous accepted state;
2. exact page provenance from either (a) a previous accepted scheduled page
   identity or (b) current explicit match-page evidence;
3. current Data Site ID observed in the current raw listing;
4. exact equality of all `IDENTITY_BOUND_FIELDS`;
5. current explicit page evidence absent or exactly agreeing;
6. no same-namespace reuse by another fixture;
7. no existing different bridge for either typed identifier or fixture;
8. fresh snapshot/accepted-baseline chronology;
9. valid operational projection with no global projected-ID duplicate; and
10. the prediction compatibility gate in Section 11.

Path (a) is the scheduled namespace transition. Path (b) permits a fixture
with no previous page ID to establish both typed identities from two exact
official sources in one snapshot, including the normal candidate/completed
evidence workflow. Path (b) may not override a different previous typed page
ID or an existing bridge. Both paths use the same uniqueness, identity-field,
event, and HOLD rules.

Candidate/completed score and completion checks are independent gates. A valid
score does not repair a failed identity bridge. Date/round/home-away change,
missing previous provenance, explicit disagreement, reuse, or ambiguity is
HOLD. Kickoff/stadium/attendance/broadcast/display-only changes do not block
the bridge, but their existing change events remain.

## 10. Frozen event semantics

Keep the existing event columns and deterministic event-ID construction. Add
exactly these event types:

```text
identity_bridge_established
identity_namespace_transition
```

Rules:

- `identity_linked`: first operational ID appears where none existed; no
  cross-namespace relation is implied.
- `identity_bridge_established`: a second typed source ID passes the bridge
  gate. Emit once per comparison when the accepted bridge first appears,
  whether the two scalar values are equal or different.
- `identity_namespace_transition`: operational namespace changes from
  `jleague_match_page` to `jleague_data_site`. Emit even when scalar IDs are
  equal.
- A valid bridge/transition suppresses the old scalar-only
  `identity_conflict` for that exact change.
- A failed bridge emits `identity_conflict` and blocks publication.
- `result_candidate`, `completed`, `schedule_changed`, and other existing
  events may coexist with the two new events.

Before/after JSON includes typed IDs, operational ID/namespace, status, and all
identity-bound fields. Provenance-only fields remain excluded from generic
`metadata_changed`, while the bridge ledger and bridge event retain their
provenance. Same-input replay emits no duplicate bridge or event.

V1-to-v2 normalization itself is not a source observation and emits no change
event. The current v2 snapshot is compared against the fully migrated previous
semantic state; only an actual current-source difference generates events.

The blocking event set remains:

```text
missing_from_snapshot
identity_conflict
completion_unconfirmed
```

The two valid new event types are not publication blocks.

## 11. Frozen prospective-prediction compatibility

### 11.1 Immutable files and baselines

Never rewrite existing rows in:

```text
data/processed/predictions/xg_challenger_prospective.csv
data/processed/predictions/model_architecture_prospective.csv
```

Frozen read-only baselines are:

```yaml
xg_challenger:
  sha256: 32fedd4f6b71d8f83e3275feb56653ff80b24a11514c7fd3df1854f58679d6aa
  rows: 2
model_architecture:
  sha256: e47d8a5df136939d3d629c4c0826e23c382786b3d99856987a3964b5842854ec
  rows: 4
```

All six rows bind the two fixtures below through match-page IDs:

| prediction ID | fixture_key | match date | home TeamMaster | away TeamMaster |
| --- | --- | --- | --- | --- |
| `100903` | `j1_2026_2027:kashima:gosaka` | 2026-10-09 | `team_0008` | `team_0005` |
| `100901` | `j1_2026_2027:kashiwa:kobe` | 2026-10-09 | `team_0009` | `team_0011` |

The exact identity witness is accepted v1 revision
`2758a644ff46888993f79fa44987079b187196e0ed204fb863ea645ff647dd3c`,
manifest SHA-256
`c7bfa3b9bd113c1c34e016625a23935ce6bb712de4cdcc9b47bd5187fce044c2`.

### 11.2 Binding sidecar

Freeze one common append-only sidecar path:

```text
data/processed/predictions/2026_27_prediction_fixture_bindings.csv
```

Its exact columns are:

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

The primary key is
`(prediction_artifact, prediction_match_id, model_version)`. Also require unique
`(prediction_artifact, fixture_key, model_version)`. `prediction_artifact` is
the repo-relative POSIX path. The namespace for the six frozen rows is
`jleague_match_page`.

The implementation provides an explicit offline bootstrap builder that:

1. verifies both frozen prediction file hashes and schemas;
2. verifies the exact identity witness revision and manifest hash;
3. resolves every prediction row one-to-one by original ID, date, and exact
   TeamMaster home/away IDs;
4. writes all six binding rows to a new file using exclusive creation; and
5. refuses overwrite, partial input, extra prediction rows, or ambiguity.

The implementation task builds code/tests only; it must not execute this
bootstrap against production data unless a later operational task explicitly
authorizes it.

### 11.3 Prediction and evaluation behavior

When a new bridge or namespace transition affects a fixture present in either
frozen prospective file, the binding sidecar must exist, validate, and cover
every existing row in both files before that revision can publish. Otherwise
the transition is HOLD. A v2 revision with no newly bridged/transitioned
predicted fixture reports `NOT_REQUIRED`; it does not fabricate a sidecar.

Each prediction command requires a valid, complete sidecar before reading a v2
schedule, even when its immediate target fixture has no prior prediction.

Predictors retain immutable output key `(match_id, model_version)`, but their
already-predicted gate additionally checks bindings by
`(prediction_artifact, fixture_key, model_version)`. A later Data Site ID must
therefore return `ALREADY_PREDICTED`; it must not append a second prediction.

Future successful prediction appends must create a matching binding through a
locked, journaled, replayable operation. A run journal freezes both rows before
the first append. Recovery may append a missing suffix exactly once but may
never edit an existing prediction or binding row. Schema/hash/key mismatch is
a hard failure.

Later evaluation joins only:

```text
immutable prediction key
  -> prediction binding fixture_key
  -> accepted v2 identity bridge fixture_key
  -> data_site_match_id
  -> completed outcome
```

It verifies one-to-one cardinality plus exact competition, date, home and away
TeamMaster identities. Direct prediction-ID to completed-ID join and row-order
fallback are prohibited. Existing prediction CSV schemas remain unchanged.

## 12. Frozen revision artifacts and CLI surface

V2 revision payload is the v1 payload plus `identity_bridges.csv`. Root
`PROJECTIONS` also adds that filename. `latest.json` remains the two-field
pointer contract (`revision_id`, `manifest_sha256`). Held revisions never
replace root projections.

V2 summary adds:

```text
match_page_id_count
data_site_match_id_count
identity_bridge_count
identity_bridge_policy
migration                 # present only on first v2 revision
prediction_binding_status # VALID | MISSING | INVALID | NOT_REQUIRED
```

Retain `match_id_count` for the operational projection and
`source_requests_during_processing = 0`.

The update CLI does not add URL discovery, retry, or background fetch. Existing
explicit `--evidence-url` behavior remains. Its printed summary adds the three
typed identity counts, migration policy/status, and prediction-binding status.
Replay remains network-free.

## 13. Frozen implementation scope

The one implementation may change only the files needed for this contract,
expected to include:

```text
src/collect/jleague_ongoing.py
src/collect/jleague_ongoing_source.py
scripts/update_jleague_ongoing.py
tests/test_jleague_ongoing_update.py
tests/test_jleague_ongoing_source.py
src/modeling/xg_challenger_prediction.py
tests/test_xg_challenger_prediction.py
src/modeling/model_architecture_prediction.py
tests/test_model_architecture_prediction.py
docs/JLEAGUE_2026_27_UPDATE_DESIGN.md
docs/JLEAGUE_2026_27_ID_NAMESPACE_TRANSITION_SPEC.md
docs/XG_CHALLENGER_PREDICTION_RUNBOOK.md
docs/MODEL_ARCHITECTURE_PREDICTION_RUNBOOK.md
```

The implementation must not modify or materialize production `data/`, models,
predictions, existing raw snapshots/revisions, suspension artifacts, or
historical 2015–2025 artifacts. Adding code for the future sidecar/bootstrap is
allowed; creating the production sidecar is not.

## 14. Frozen test contract

Synthetic tests must cover at least:

1. ongoing-v2 written to new snapshot/run/revision manifests;
2. v1 artifacts remain byte-identical/readable and unprocessed v1 input stops;
3. exact frozen-baseline acceptance and any revision/hash/count mismatch stop;
4. v1 migration classification 80 completed bridges, 7 page-only, 293 blank;
5. migration recovers earliest accepted explicit provenance and ignores held
   revisions;
6. exact 45-column schedule/completed schema and JSON null/CSV blank semantics;
7. match-page leading-zero string preservation and Data Site syntax;
8. page-only/Data-only/both/neither operational projection for each status;
9. namespace-local uniqueness and global operational uniqueness;
10. equal-scalar cross-namespace bridge still records both namespaces;
11. differing-scalar bridge publishes with both IDs preserved;
12. current scheduled Data Site ID plus carried prior page ID can bridge;
13. current explicit exact page plus Data Site ID can establish a same-snapshot
    bridge when no previous page ID exists;
14. candidate transition emits result/bridge/namespace events without conflict;
15. completed transition also passes the separate game-over gate;
16. missing provenance, date change, round change, side change, explicit page
    conflict, and cross-fixture reuse each HOLD without latest mutation;
17. bridge ledger exact schema, deterministic bridge ID/order, no deletion or
    reassignment;
18. accepted bridge hydration preserves original IDs/provenance without a new
    bridge event and rejects changed bound fields or IDs;
19. kickoff/stadium/attendance/broadcast/display-only change does not block;
20. identifier disappearance/status regression keeps accepted bridge and HOLDs
    where required;
21. old completion inheritance remains separate and unchanged;
22. stale snapshot cannot roll back v2 identity state;
23. same snapshot replay produces identical summary/revision/projections and no
    duplicate events/bridges;
24. raw tamper, revision tamper, writer lock, publication rollback, fixture
    coverage, and zero-network protections remain;
25. prediction binding bootstrap verifies both frozen files, six rows, hashes,
    witness, exact fixtures/date/teams, exclusive creation, and replay refusal;
26. prior prediction files remain byte-identical after simulated transition;
27. differing later Data Site ID is already predicted by fixture/model and
    cannot append a second row;
28. prediction journal recovery is suffix-only and rejects conflicting rows;
29. evaluation bridge is one-to-one and fails missing/ambiguous/date/team
    mismatch without rewriting prediction output; and
30. current prediction metric/refit/outcome prohibitions remain.

No test may perform external HTTP or create a real snapshot, bridge, binding,
prediction, or migration artifact outside pytest temporary directories.

Implementation validation must run targeted ongoing source/update tests,
targeted XG and architecture prediction tests, full pytest, and
`git diff --check`.

## 15. Explicit non-goals

- operational migration or production sidecar creation;
- live capture, HTTP, URL discovery, or evidence backfill;
- prediction generation, regeneration, evaluation, or model work;
- rewrite of existing prediction rows or schemas;
- change to the fixture-key definition;
- more than the two frozen official namespaces;
- automatic identity correction after an established bridge;
- date/round/home-away correction policy beyond HOLD;
- migration of historical 2015–2025 match identities; and
- suspension/J Stats schema redesign in this implementation.

## 16. Freeze gate

The repository evidence is sufficient to freeze this one implementation. The
v1 boundary, v2 schema, migration algorithm, transition gate, event semantics,
bridge ledger, and prediction compatibility have no remaining implementation
choice.

```text
FROZEN_FOR_ONE_ID_NAMESPACE_IMPLEMENTATION
```

This gate authorizes only a future code-and-synthetic-tests implementation of
this exact contract. It does not authorize production migration, sidecar
materialization, capture, prediction, evaluation, or push.
