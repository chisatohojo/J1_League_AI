# Public Windows migration Catalog contract

This checkpoint is unbuilt, untested WIP. Phase A is BLOCKED and Phase B is
NOT_AUTHORIZED. It grants no migration, native fixture, real Worker, Harness
execution or GUI permission.

## Public representation and runtime binding

The embedded Catalog uses schema version 2. Version 1 with literal machine
paths is rejected. The public representation contains fixed anchors:

| Field | Representation | Meaning |
| --- | --- | --- |
| Repository | `@documents/__SoftDev/J1_League_AI` | Windows MyDocuments plus the fixed repository suffix |
| Fixed / OldObserver Path and Runner FixedPath | `@repository/...` | Fixed shipping files below that repository |
| Fixed Path | `@local/...` | Smoke control, manifest/state and fixture assets below LocalApplicationData |
| Fixed Path | `@desktop/...` | The approved DesktopDirectory shortcut |
| Runner CandidatePath | Relative path, unchanged | Below the fixed reviewed Runner candidate root |
| Protected Path | Relative path, unchanged | Below the resolved fixed repository |

The 67 former absolute path entries are one Repository anchor, 55 repository
file references, ten LocalApplicationData file references and one Desktop
file reference. Conversion is field-specific; SHA values, Runner Changed flags,
ordering and candidate/protected relative paths are preserved.

Inspector resolves the embedded anchors before inspecting files. It does not
accept an external Catalog, root argument, environment-variable override,
current-directory fallback or search result as a binding. Known-folder
resolution must return an existing canonical absolute directory. Relative
components reject traversal, empty components, backslashes, invalid filename
characters and trailing dots/spaces. Resolved paths must remain below their
fixed anchor. OldObserver and Runner FixedPath accept only the repository
anchor. Unknown anchors and the wrong Repository anchor fail closed.

Absolute runtime paths remain necessary for held native handles, ancestor and
final-path checks, exact inventory comparisons, candidate mapping and plan
source/final destinations. Tokens never reach those native operations.

## Frozen evidence is retained

ReadPin canonical/final-path, ancestor/reparse, Volume/File ID and security
checks are retained. Root/UDF identities, 32-UDF inventory, CLEAN proofs,
fixed 42 files, old Observer five, protected five and Runner 19-file mapping
remain required. Candidate ledgers, source/file SHA checks, old Manifest/State
hashes and exact proposed new Manifest/State bytes remain unchanged.

Local static comparison resolved all 67 entries to the original absolute
paths, in the same order, with every non-path value unchanged except the
explicit schema version. No private path is recorded here. This comparison
does not establish compiled or runtime correctness.

Catalog byte SHA changed from
`2d149b891554d756b9c6df85278ff698a1b70fd55bc26ddeddbcea553109270b`
to
`650940ee3c2f4bab53e8a4b6b3d94bbe7493ef7e05a54200ca52d8d19d09d099`.
The embedded resource and Inspector source changes require new source and
binary bindings before any separately authorized execution. Existing isolated
binaries, journals, catalogs, manifests, states and receipts are not updated
or reinterpreted. In particular, historical source-binding receipts and their
HEAD/source hashes do not approve this checkpoint.

This is publication portability of the path representation, not approval of
another machine or Root. Frozen identity and metadata hashes still reject
another environment. No old metadata hash or identity was replaced to make
an inspection pass.

## Validation limits and follow-up

Historical 37/37 and other old isolated results apply only to their recorded
sources and binaries. No build, test, fault injection, Harness, native fixture,
real Worker or GUI was run for this source. The 105/legacy 69 cases and five
representative Pure Fake cases remain unexecuted.

Pure Fake Harness retains its Medium issue concerning abnormal-exit cleanup
and terminal snapshots and its two Low issues concerning gate-state reporting
and live/known resource accounting. Those repairs are separate work.

Future execution needs a separate review of this Catalog schema and resolver,
new source/binary binding evidence, and explicit execution authorization.
Keep all historical evidence and the local-only WIP branch unchanged.

## Uncommitted resolver repair: static review only

The current repair replaces all Environment.GetFolderPath calls in the Planner
and Tests projects with KnownFolderPaths.Get, defined in Inspector.cs. This
uses the existing Planner assembly reference; it adds no file, ProjectReference
or project change. Tests must reference a freshly built matching Planner DLL
in a future approved build; the old DLL does not provide this new helper.
WorkerEnvironment.cs and MockSandbox.cs require call-site-only edits to avoid
leaving a fallback route outside ObservationSession.cs.

Migration-path acquisition sites are Inspector.SpecialFolderPath,
ObservationPaths.FixedPath and Dotnet, WorkerEnvironment.ValidatedExpected
(Windows and LocalApplicationData), and MockSandbox.Allowed: six direct
KnownFolderPaths.Get call sites. No GetFolderPath call remains in these two
projects. Environment enumeration for Worker whitelist validation is unchanged
and does not supply a Known Folder fallback.

Fourteen pre-existing GetFolderPath calls remain outside the Migration projects:
SmokeNetworkObserver/Approval.cs (seven), SmokeNetworkObserver/CoordinationSession.cs
(one), DashboardHost/Diagnostics.cs (one), DashboardHost/WebViewPreflight.cs
(one), DashboardHost.Tests/Program.cs (two), DashboardHost.Tests/SmokeCoordination.cs
(one), and DashboardHost.Tests/SmokeRunner.cs (one). Those product/legacy-test
sources and their frozen binaries are outside this repair and remain unchanged;
the Migration projects have no ProjectReference to them.

| Known Folder | Official KNOWNFOLDERID |
| --- | --- |
| LocalApplicationData | F1B32785-6FBA-4FCF-9D55-7B8E7F157091 |
| Documents / MyDocuments | FDD39AD0-238F-46AF-ADB4-6C85480369C7 |
| DesktopDirectory | B4BFCC3A-DB2C-424C-B029-7FE99A87C641 |
| Windows (existing Worker environment path) | F38BF404-1D43-42F2-9305-67DE0B28FC23 |

The P/Invoke takes an input Guid reference, unsigned DWORD flags, native-sized
token and output pointer, and preserves the signed HRESULT. Flags are zero;
token is NULL for the current user. It accepts only S_OK (zero), rejects NULL
or blank results, requires canonical absolute existing directories, and frees
every non-NULL returned pointer in finally with CoTaskMemFree, including error
and validation-exception paths. DLL lookup is restricted to System32. There
is no environment, current-directory or GetFolderPath fallback and no creation
flag or default/other-user token. Existing fixed suffixes, RootId, Catalog
bytes, source-independent frozen SHA values and identity checks are unchanged.

Relative components now reject CON, PRN, AUX, NUL, COM1..COM9, LPT1..LPT9,
COM¹/²/³ and LPT¹/²/³, without case sensitivity. The first dot separates the
device stem, so extensions do not bypass rejection; spaces immediately before
that dot do not bypass it either. Existing absolute-path, traversal, empty
component, ADS, invalid-character and trailing-dot/space checks remain.

References: [SHGetKnownFolderPath](https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath),
[CoTaskMemFree](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-cotaskmemfree),
[KNOWNFOLDERID](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid),
[Windows names](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file#naming-conventions).

### Future limited cases: all NOT_RUN

These are expected results for separately authorized verification, not current
PASS results. HRESULT and allocation-counter injection needs a separately
reviewed test-only seam; no public root, token, Catalog or native-function
override was added for this repair. Do not inject failures into the preserved
environment or alter historical evidence.

| Planned case | Expected result |
| --- | --- |
| KF-01: normal LocalApplicationData, Documents, Desktop and Windows | Exact original paths; S_OK; non-NULL allocation freed once; zero filesystem creation |
| KF-02: failure HRESULT, NULL output; environment variables contain usable paths | Stop without fallback; no pointer free needed |
| KF-03: failure HRESULT with allocated output | Stop before decoding; allocation freed once |
| KF-04: nonzero positive HRESULT with allocated output | Reject, allocation freed once |
| KF-05: S_OK with NULL, empty or whitespace output | Reject; every non-NULL allocation freed once |
| KF-06: relative, UNC/device, ADS, noncanonical, trailing-dot/space or unavailable base | Reject; allocation freed once |
| KF-07: managed validation exception after allocation | Original failure propagates; allocation freed once |
| KF-08: unsupported SpecialFolder | Reject before API call |
| KF-09: valid base redirected to a different fixed Root or metadata set | Existing downstream identity/SHA checks block approval |
| RN-01: all listed reserved stems, case variants and extensions | Reject every component before native file access |
| RN-02: NUL.txt, com1.log, COM¹, LPT³.cfg, NUL .txt | Reject |
| RN-03: normal.txt, computer.txt and all existing Catalog suffixes | Accept lexical validation |
| RN-04: absolute/drive-relative/UNC suffixes, traversal, empty components, ADS and invalid characters | Preserve rejection |
| RN-05: dot/space-ending components and reserved names in intermediate directories | Reject |

No C# build, test, native execution or HRESULT injection has been performed
for this repair. No new binary SHA, receipt or binding exists. CaseSupervisor's
historical HEAD/path/source bindings remain unchanged and require separate
future review. Historical 37/37 PASS and the Pure Fake Harness Medium/Low
findings remain historical and unresolved, respectively.

## Checkpoint file inventory

These are the complete 19 file changes from main. The original final source
is preserved except for the documented public path/schema changes.

| File | Purpose |
| --- | --- |
| docs/UI_WINDOWS_NATIVE_HOST.md | Link migration tooling; replace personal paths and literal SID in historical documentation |
| docs/UI_WINDOWS_SMOKE_MIGRATION_PHASE_A.md | Planner/transaction contract; distinguish historical results from current untested WIP |
| docs/UI_WINDOWS_SMOKE_MIGRATION_PUBLIC_CATALOG.md | Public Catalog binding, evidence limits and complete change inventory |
| windows/J1AI.SmokeMigration/Contracts.cs | Frozen hashes, metadata and plan contracts |
| windows/J1AI.SmokeMigration/Inspector.cs | Read-only planner with strict Catalog anchor resolution |
| windows/J1AI.SmokeMigration/NativeRead.cs | Held native read, identity and security checks |
| windows/J1AI.SmokeMigration/Program.cs | Read-only CLI and failure reporting |
| windows/J1AI.SmokeMigration/J1AI.SmokeMigration.csproj | Isolated planner project and embedded Catalog |
| windows/J1AI.SmokeMigration/approved-catalog.json | Field-specific schema 2 anchors; original content hashes and mappings |
| windows/J1AI.SmokeMigration.Tests/Program.cs | Test dispatch and outcome accounting |
| windows/J1AI.SmokeMigration.Tests/Transaction.cs | Isolated transaction and pending/failure contract |
| windows/J1AI.SmokeMigration.Tests/MockSandbox.cs | Owned mock creation, identity checks and cleanup |
| windows/J1AI.SmokeMigration.Tests/ObservationSession.cs | Fixed observation binding and durable journal |
| windows/J1AI.SmokeMigration.Tests/CaseSupervisor.cs | Owned process supervision and evidence corroboration |
| windows/J1AI.SmokeMigration.Tests/WorkerEnvironment.cs | Worker environment whitelist |
| windows/J1AI.SmokeMigration.Tests/ObservationDeadline.cs | Observation outcome and deadline rules |
| windows/J1AI.SmokeMigration.Tests/JournalValidation.cs | Journal identity, record and summary validation |
| windows/J1AI.SmokeMigration.Tests/HardeningTests.cs | Limited precheck and terminal Oracle definitions; not executed here |
| windows/J1AI.SmokeMigration.Tests/J1AI.SmokeMigration.Tests.csproj | Isolated test project referencing the separately built planner |
