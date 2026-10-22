# Weekend batch Phase 1 — offline only

Result: `WEEKEND_BATCH_OFFLINE_IMPLEMENTED_NOT_ACTIVATED`.

Based on the approved local DESIGN.md, using operational base commit
`5ac9052a221c6d8d563ec982bc48fbddb9e80bfa`. This separate feature branch does
not change the running operational worktree, UI branch, tasks, runtime, saved
predictions, Desktop shortcut, or models. No real estimator was loaded or run.

## Scope boundary

`src/modeling/weekend_batch.py` supplies a **synthetic-only** backend. It requires
an exclusively created temporary workspace, an explicit scope marker, a sibling
temporary fixture repository, and mock model/scaler objects marked
`synthetic_only=True`. The ordinary updater never constructs this capability.
Missing policy, or `weekend_policy: {"enabled": false}`, retains daily behavior.
Enabling the policy in a normal CLI config raises `weekend_offline_only` before
the update lock, status write, collector, or estimator. No production activation
switch, model loader, HTTP entry point, task registration, or executable sample
production config has been added.
Even when an offline capability is explicitly supplied, the updater refuses its
real collector/predictor defaults and requires explicit synthetic callbacks.

Synthetic policy schema: `enabled`, `friday` (exact Friday ISO date),
`deadline_seconds` (integer 1..900). It covers one explicitly selected weekend,
not an automatically rolling set of production weekends. Later weekends need
their own reservation and separately authorized activation.

## Reservation and coexistence

Reservations are create-new JSON under `weekend-reservations/<Friday>.json`.
They bind the Friday–Monday JST window, exact typed fixture identities and
TeamMaster IDs, source revision/SHA, actual creation UTC, and policy version.
Creation must precede Wednesday 07:00 JST and any saved fixture in the window.
Declaring a reservation never generates a prediction.

Morning execution validates the reservation before selecting ordinary daily
targets. Reserved Friday–Monday dates are excluded; Tuesday–Thursday targets
are left eligible. Candidate/missing IDs, scope/club/date/kickoff changes,
period-internal repeated club appearances, partial or legacy saved groups, and
late reservations HOLD. Revision advancement before freezing is accepted only
after validating the immutable publication and unchanged target identities.

A completely committed, validated v2 group is a no-op, not another inference.
Natural completion and an explicitly evidenced typed namespace transition are
allowed for the existing group: the original namespace ID must still appear in
the corresponding current typed-ID field. Schedule/scope changes instead HOLD
with `HOLD_REVIEW_ON_SCHEDULE_CHANGE`. Saved rows and original bindings remain
unchanged. Evening never calls the weekend or daily estimator.
Evening still performs read-only reservation/group applicability checks before
feed projection, so a changed kickoff/scope cannot bypass review just because
no estimator is called.

## Common snapshot and clock contract

Two different cutoffs are recorded:

- History cutoff D0: Friday 00:00 JST; every official fixture before D0 must be
  completed. No unfinished past fixture is silently skipped.
- Information cutoff: Friday 07:00 JST. Source observation, completed-result
  evidence, and all input-acquisition timestamps must be available by that point.

Actual freeze, generation and commit-check UTC are stored separately. Friday
execution must start at/after 07:00 and finish within its finite deadline and
before **every** target kickoff. Late starts, backward clocks and later-acquired
information HOLD; acquisition at 07:00:30 is not relabeled as available at 07:00.
For production integration this requires an approved pre-cutoff publication
strategy. Connecting a collector that only obtains a new publication after
07:00 is insufficient. No such collection/integration was implemented here.

Only the operational Elo replay is reused: initial 1500, K30, home advantage
175, no season reset, feature `home_rating - away_rating` without adding 175.
Toy training/special history and confirmed pre-window official results are
replayed once. The detached rating map is used for all target dates without
updating it between targets. No Saturday result, PK/extra-time winner, Form,
research feature, scaler fit, or target result is supplied. Input CSV projections
are checked against their byte witnesses; current source projections must match
their immutable CSVs. Reordering target processing leaves the map/features intact.

An immutable attempt record is created before estimator invocation. An incomplete
attempt cannot be automatically resumed or re-predicted. This is intentionally
more conservative than retrying failed I/O.

## Batch v2 and atomic visibility

Each v2 directory contains exactly:

- `predictions.csv`: existing Champion-only schema, preserving full probabilities
  and one actual generation timestamp across the complete group;
- `bindings.csv`: existing exact fixture-binding schema;
- `snapshot.json`: policy/scope, snapshot ID, Friday/Monday window and cutoffs,
  actual freeze UTC, exact targets, source revision/manifest and observation time,
  ordered history-event SHA/count, rating-map SHA/map, fixture features, input
  SHA/acquisition UTC, code SHA, fixed Champion identity, mock-estimator scope,
  reservation SHA and generation UTC;
- `manifest.json`: `champion-weekend-v2`, `SYNTHETIC_ONLY`, policy/window, official
  revision/SHA, fixture-set SHA, snapshot/model/input identities, output-file SHA,
  generation and commit-check UTC, count, completeness PASS, COMMITTED state.

Files are exclusively staged outside `batches`, flushed, fsynced, reread, hashed,
and semantically validated. A single same-filesystem directory rename publishes
the group at `batches/weekend-v2-<manifest-body-SHA256>`. COMMITTED means visible
at that final content-addressed location; a COMMITTED manifest still inside a
`.pending-*` directory is not a published batch. The manifest's commit UTC is
the pre-publication authorization check, not a claim of a measured kernel rename
instant. The clock/deadline and all pins are checked again immediately before
rename.

Legacy and weekend publishers share an exclusive publication lock. While holding
it the weekend writer rereads all saved batches, refuses any overlapping fixture
or existing period, and rechecks source/input/reservation/code pins. Canonical
CSV bytes, bindings, contexts and manifests are never replaced. Readers distinguish
legacy hex-directory manifests from v2-prefixed directories, verify their address,
exact schemas, hashes, identities, timestamps, feature map and binding coverage,
and reject a missing context or attempted downgrade to a legacy manifest.

Failure before rename publishes zero weekend rows. Pending evidence and attempt
records remain for investigation, never automatic cleanup/recovery. Handled
publication-lock ownership is checked before release; abandoned locks are not
reclaimed. Disk power-loss durability, adversarial Windows ACL/TOCTOU behavior
and a production worker were **not** certified by these synthetic tests.

## Feed projection and rollback

The existing updater builds and validates both schema-v1 home and schema-v2
rounds before committing added predictions. Native Champion-only CSV and legacy
readers remain supported. Only the UI branch's Friday–Monday selection logic was
ported for v1; previous-round selection and v2 round selection remain intact.
No snapshot, rating map, local path or manifest metadata enters schema-v1 UI data.
Only saved predictions are projected, without rounding or filling unsaved dates.

Before the batch boundary, failure preserves prior predictions and display.
After the boundary, a later display failure must **not** roll back or regenerate
the committed predictions. The test demonstrates that a read-only/no-inference
reprojection recovers display without changing archive bytes. Incomplete attempts
without a committed group remain HOLD and require independent inspection.

Operational rollback is a future approved procedure: disable new weekend writes,
retain compatible readers and every committed group, and inspect reservations,
locks and attempts before allowing daily ownership again. Do not hand a v2 store
to an old reader, delete a saved batch, convert the current partly saved weekend,
or use a display failure as permission to re-predict. Keep the last valid display
and explicitly report its error/staleness until a separately approved repair.

The existing current weekend is protected: its five saved Saturday predictions
are not recalculated, its five unsaved Sunday fixtures are not predicted, and it
is never relabeled as a common-snapshot batch. UI deployment, Desktop migration,
automatic JSON reload and actual feed regeneration are separate tasks.

## Validation

402 synthetic checks passed with warnings treated as errors, covering the new
backend, legacy scheduled updates, feed projection, server schema and fixture
bindings. No tests use the real estimator, real runtime or official network.
New-backend tests additionally reject reads of operational/research runtime and
source/model data across existing worktrees, and replace estimator loading and
socket connection with failures.

Cases include Friday1+Saturday4+Sunday5, Monday, full month boundary and pure
year-boundary calendar checks; real season bounds are not widened to fabricate
out-of-season fixtures. Also covered: reservations on Wednesday/Thursday,
weekday coexistence, late or missing evidence, future results, incomplete past
history, mutated in-memory source projections, scope/identity changes, partial
legacy savings, no-op rerun, pre-commit disk/crash points, shared-lock contention,
concurrent daily overlap, version downgrade, post-commit schedule/completion,
feed failure after commit, forbidden real estimator and escaped workspace.

The broader regressions found two test-only portability/resource issues: implicit
cp932 reading of a UTF-8 feed and unclosed expected HTTPError responses. The tests
now specify UTF-8/close responses; no server/native implementation or warning
threshold was weakened. Earlier fixture-UTC failures and intermediate logs are
retained locally and are not reported as final PASS executions.

Results/SHA/protection counts are recorded in
`WEEKEND_BATCH_PHASE1_VALIDATION.json`. Private JUnit/logs, full protection maps
and the original design stay outside Git. No production feed or prediction was
generated. Production source acquisition/cutoff integration, full frozen-input
verification with the real loader, manifest-reader deployment, reservation
activation, actual inference and task/runtime/GUI changes each need separate
approval. Passing Phase 1 does not authorize them.
