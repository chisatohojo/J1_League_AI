# Smoke refreeze migration tooling — Phase A

Current source is unbuilt, untested WIP. Phase A: BLOCKED. Phase B:
NOT_AUTHORIZED. Historical results below apply only to the original isolated
code and artifacts; they do not validate this public checkpoint. Native fixture,
real Worker, the 105/legacy 69 cases and five Pure Fake cases are not run.

Phase A is **not a deployment utility**. It can inspect the approved real
environment and print a proposed plan, but cannot back up or apply that plan.
The only write engine is compiled into `J1AI.SmokeMigration.Tests`, and can
construct only a newly generated mock child of the authorized artifacts root.
Neither executable accepts an arbitrary root, UDF, source, target, backup or
apply argument. Existing DashboardHost/Runner/Observer projects are not changed
or rebuilt by these projects.

## Read-only planner

`J1AI.SmokeMigration.dll --help` has no environment inspection side effects.
`J1AI.SmokeMigration.dll --inspect` performs read-only verification and prints
the JSON plan followed by its SHA-256. There is **no `--apply`**. The plan is
not persisted by the planner, and `RealApplyAvailable` is always false.

`approved-catalog.json` is an embedded, reviewable snapshot of the frozen 42
files, old Observer five-file bundle, protected five inputs and the reviewed
19-file Runner mapping. Public schema version 2 uses fixed Windows known-folder
anchors, resolved strictly before inspection. It remains specific to the
approved machine: frozen hashes and Root/UDF identities are unchanged, and
there is no path override, fallback, discovery or unknown-file adoption.
See [the public Catalog contract](UI_WINDOWS_SMOKE_MIGRATION_PUBLIC_CATALOG.md).
Prediction/feed inputs are hashed only, never parsed or evaluated.

Checks include exact fixed shipping/control file inventories, candidate ledger
and actual file sets (111 / 39 files), all content hashes, CLEAN and four proofs,
old manifest/state hashes, fixed Root/UDF object identities, 31 baseline UDFs
plus the approved fixed UDF, absence of intent/pending/backup/diagnostics and
related processes. WMI queries only relevant executable families; command lines
are inspected in memory, never printed/persisted, and unavailable identity
information fails closed. Real IPC/locks are never acquired or signalled.

The proposed plan contains all 47 original/final paths and old/new hashes,
candidate paths, rewrite decisions, roles, dependencies and adoption reasons.
The original 42 plus old Observer five are indexed uniquely for future backup.
The execution Runner bundle replaces six and retains thirteen files; the
standalone legacy Product directory is retained, not adopted as the new Runner's
dependency. All five Observer execution files form the adoption unit, including
two unchanged support files. New manifest/state bytes are JSON base64 fields
(the serializer's byte-array representation), not loosely formatted JSON text.

Runner/Product revision R: `2f19f026b541c5e4cf9d8007847c0032a38c9f1f`.
Observer revision O: `05c1598f1fa087c39dc1450be65ed075675c1c4c`.
M: 4449 bytes, `15d60923e1b3f2f418c47c8d098f1e739aa66520a789c134fd86a8782153a09f`.
S: 302 bytes, `cac6b11167c135cc3bd5b70b25ce9f93a4772ad14fdd5ec39c96fd6fa9b9ed58`.
M changes only runner/product hashes. S changes only ManifestHash; the original
run, all four proofs and directory identities are preserved. Observer binding
is external to the manifest; R binaries are never rebuilt/relabelled as O or as
the new tooling revision. Actual fixed metadata remains at the old hashes.

## Isolation and mock capability

Authorized artifacts root:
`%LOCALAPPDATA%\J1AI\BuildCandidates\coordination-migration-tests-01`.
The setup created this directory relative to a held verified BuildCandidates
handle with `NtCreateFile(FILE_CREATE)`. Volume ID is `58a223d0a223b184`, root
File ID is `7aaa000000002e000000000000000000`. Owner is the approved current SID;
the protected DACL grants only that user and SYSTEM FullControl. No reparse
ancestor is accepted. The mock constructor requires this exact object identity
and an identical canonical local root; an environment/path override cannot
grant authority over another directory. This execution-specific root identity
must be reviewed again before any different build/test environment is allowed.

Every mock uses a unique `migration-test-<GUID>` child, private root/area DACLs,
single-component handle-relative creates, and separate active/candidate/backup
directories containing **synthetic sentinel bytes only**. No real binary, state,
UDF, fixture or prediction content is copied into mocks.

Only the test assembly imports NtCreateFile/NtSetInformationFile/SetSecurityInfo.
The planner's Native API surface uses OPEN_EXISTING read access. Native
GetSecurityInfo is used for Owner/DACL retrieval throughout. Directory pins
exclude delete sharing; Volume/File ID, reparse/type and security checks are
performed on held handles. File staging is flushed, read back and renamed
relative to the pinned active directory, then checked through the destination
name against the staged object's identity and hash.

Mock exclusion mirrors three **different** contracts: an existence gate (new
mutex object only, like InstanceControls), an existing exclusively opened
smoke.lock, and a waited Observer mutex whose acquire/release remain on the
same synchronous thread. Names are unique test names, never fixed Smoke IPC.

## Transaction and failure contract

Preflight -> exclusion -> 47 backups -> 47 hash readbacks -> create-new flushed
pending -> Runner six -> manifest -> state -> Observer five -> all 47 active
hash readbacks/inventory -> pending removal. Multiple files are not one atomic
operation. The pending marker is independent of staging names.

No active replacement begins before complete, verified backups. A failure after
pending creation retains pending and is unavailable/BLOCKED. No rollback, retry,
new CLEAN proof or alternate UDF is attempted. Missing/previous pending, unknown
files, identity/hash/security mismatch, contention and interrupted writes reject
reuse. The mock fixture is deleted only as **test cleanup**, not as transaction
rollback; backup/pending preservation is asserted before that cleanup.

Cleanup compares creation-time IDs, including file IDs separately retained from
test tampering expectations. It does not adopt unknown objects for deletion.
Directories/files are deleted by owned handle relative to pinned parents; no
recursive path delete or policy workaround is used. A cleanup failure prevents
further mock generation, reports NOT_RUN and fails the local commit gate.

Fault injection is explicit and distinguished from OS failures. Scenarios cover
backup start/mid/flush/readback/collision, pre-existing pending, source/target
same-bytes object replacement, marker flush, first/mid/metadata/Observer replace,
post-replace interruption, final content/inventory readback, duplicate gate,
lock and mutex contention. Real Windows probes cover directory rename refusal,
file replace refusal with a non-delete-sharing target handle, private/unprotected
DACL, owner SID validation and directory symlink tag `0xA000000C` rejection.
An actual foreign-owner reassignment is not attempted: the Owner test queries
the real owner and supplies a deliberately incompatible expected SID.

The observed held-target rename refusal on this Windows/NTFS environment is
STATUS_ACCESS_DENIED `0xC0000022`, translated error 5, not the initial anticipated
sharing error 32. Both native/translated values and retained pending are tested.
Flush/readback exceptions and process interruption are injected; they do not
prove physical power-loss durability or actual process-crash recovery.

## Explicit limits before a future Phase B

Windows atomic per-file rename does not supply an expected-target-File-ID CAS.
Pins prevent directory namespace replacement, and content/identity checks detect
the exercised before/after fault barriers, but Phase A does **not** prove absence
of an adversarial same-SID target rename in the last check-to-rename interval.
Do not reuse this test writer as a real apply engine. Phase B needs separately
reviewed real exclusion, destination-race threat model and native ownership
proof; any unproven required safety condition must block real application.
Same-user modification is not prevented merely by a User+SYSTEM DACL.

This mock success is not a real migration/GUI success. Real exclusion across
sessions/elevations, backup provisioning, exact restore/recovery procedure,
power-loss durability and real switching remain unproven. Existing Low items
(peer exit status, stdin cancellation, NOT_RUN accounting in the old runner,
historical Runner directory inventory) remain unchanged. Real WebView2/UDF reuse,
formal Stop, Runtime ownership, TCP observation, crashes and the original
unclassified communication candidate remain outside this task.

## Historical build and review evidence (original code only)

Use user-local SDK 10.0.401 with existing Desktop targeting pack 10.0.12,
verified offline source and unchanged signatureValidationMode=require. Both
projects have an empty package graph and no frozen ProjectReference. Tests
reference only the separately built new planner inside the authorized root.
Evaluate all output/intermediate/project-assets/copy paths before restore.
UseArtifactsOutput/ArtifactsPath isolate both builds, CLI/cache/temp/scratch/logs.
Restore uses locked mode (no package lock file is generated for this empty graph);
Release builds use --no-restore and disabled build servers/shared compilation.

These are development test artifacts marked `phase-a-uncommitted+<base O>`;
source hashes, dirty status and eventual local commit are recorded separately.
They are not formally adopted Runner/Product/Observer candidates. Preserve failed
build/test logs as well as the final run. The assertion runner, not dotnet test
discovery, supplies execution counts and nonzero failure status. Normal and
negative-control runs must be reported separately. Negative-control deliberately
disables backup/marker/final checks in the test assembly and must fail three
oracle assertions with exit 1; cleanup must still succeed.

Phase A local verification: the final executable assertion run registered and
executed **46 tests: 46 PASS, 0 FAIL, 0 NOT_RUN**. The separate negative-control
run registered/executed four (cleanup probe PASS plus three deliberately failing
oracles), exit 1; all three mutations were detected. An earlier 37-test run
passed; an intermediate 42-test run had one incorrect anticipated Win32 error
code and is preserved as a failed run, not added to the final count. The initial
compile had one nullable-flow error; the final two-project Release builds have
zero warnings/errors. Real read-only inspection and CLI help are separate from
the 46 assertions. No existing GUI/Observer test results are added to these
counts. No real GUI, backend, UDF initialization or production prediction is run.

Native API reference: [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile)
and [GetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getsecurityinfo).

Only an independent review is authorized next. Real backup creation, a limited
Phase B apply implementation/review, complete R/O/M/S approval, formal switching,
separate diagnostic-parent provisioning and a specifically authorized same-UDF
GUI run remain separate approval boundaries.
