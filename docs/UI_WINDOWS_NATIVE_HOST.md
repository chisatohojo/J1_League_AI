# Windows Dashboard NativeHost — Phase 1 core / Phase 2 opt-in GUI

## Scope

Baseline: `1091d03c2dd52b9cde09e91a313417aac4ed967f`.
The following core sections record the reviewed **Phase 1** contract;
the Phase 2 opt-in GUI and its validation are documented below. The WinExe targets
`net10.0-windows`, WinForms, x64, SDK `10.0.401`, with WebView2 SDK pinned to
`[1.0.4258.31]`. Phase 1 itself starts no Form/WebView2 instance, browser, CDP,
desktop integration, model, feed builder or research evaluator.

Default invocation and `--help` perform no identity lookup, IPC, file access or
process creation. `--core` is an explicit headless opt-in, not the desktop app.
It accepts `--repository PATH`, `--data JSON`, and a finite
`--startup-timeout SECONDS` in `(0,120]` (default 20). Deployment/root layout
changes and ordinary desktop activation belong to Phase 2.

Existing Python launcher, server, installer, web UI and their contracts remain
unchanged. No production core run or GUI smoke was performed in this phase.

## Repository/session identity and IPC

The source of truth is the existing Python `instance_id()`:
`sha256(str(root.resolve()).casefold().encode("utf-8")).hexdigest()[:24]`.
Native code does **not** substitute `.NET ToLowerInvariant()` or its path
canonicalizer. A hidden, bounded, isolated (`-I -S -X utf8`) venv Python helper
uses `runpy.run_path(..., run_name='j1ai_identity_only')` to call that exact
function, returning the resolved root and ID. The helper imports implementation
only: no `main`, server, feed/data discovery or supervisor. Failure stops
startup; there is no alternative namespace. Repository code and the venv are
trusted local executable inputs, as for the legacy launcher.

Unicode directories and a temporary junction are also exercised with real
CreateProcess/server cwd and IPC duplicate suppression, not just string tests.
Symlink metadata confirms the exact Python-resolved identity, **not** a full
native launch through a temporary symlink repository. That latter operation is
unproved here: public identity resolution rejects a symbolic link anywhere in
the input repository's ancestor chain before acquiring IPC/starting a server.
There is no alternative namespace. Junctions remain supported. Enabling
symlink-root launch requires a later authorized integration test/review.

IPC names are `Local\J1AI.Dashboard.<id>`, `.Stop`, and `.Show`.
`CreateMutexW(NULL,FALSE,name)` + `ERROR_ALREADY_EXISTS` implement **object
presence**, not an acquired mutex/`WaitOne()`. Kernel handles have SafeHandle
ownership. A duplicate creates no server and signals Show if available; a
legacy owner without Show is simply left running. Stop is manual-reset and
compatible with the old Python launcher; Show is auto-reset and coalesced to
one pending state flag. Stop takes priority during STARTING and RUNNING. Stop
is never reset by the host, avoiding lost concurrent requests.

Phase 1 Show cannot display/focus anything. Native `--stop` signals the current
repository/session owner. A legacy owner retains its existing **browser
untouched** semantics. A native owner closes its owned server; future native
window close is explicitly not implemented yet. No PID files or discovery of
unknown servers exist.

## Server process ownership

`OwnedServer.Start` creates an unnamed non-inheritable Job and sets
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. It passes that Job with
`PROC_THREAD_ATTRIBUTE_JOB_LIST` in STARTUPINFOEX to **CreateProcessW**, with
`CREATE_NO_WINDOW | EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED`.
`IsProcessInJob` must confirm membership before `ResumeThread`. No post-create
assignment or compatibility fallback exists; unsupported/failed creation is
fail-closed.

`PROC_THREAD_ATTRIBUTE_HANDLE_LIST` allows exactly:

- one inheritable duplicate of the repository gate;
- stdout pipe write handle;
- NUL handle shared by stdin/stderr.

Job, original gate, stop/show events, stdout reader and unrelated handles are
not inherited. The host immediately closes its temporary gate/write/NUL
duplicates after creation. The child-held gate prevents a new owner during
the child-only lifetime if the host crashes. The host's Job handle is never
inherited or duplicated into the server; its last close reclaims the child.
Only the newly created server is assigned; the host itself, browsers, and
future WebView2 processes are not assigned to this Job.

The command is exactly explicit venv Python with
`-u -m scripts.serve_dashboard --port 0`; cwd is the resolved repository root.
Only an explicitly supplied absolute `--data` path is appended. Native code
does not read that JSON. CreateProcess receives an explicit executable and
CRT-quoted arguments; there is no shell or process-name/PID search.

Cleanup closes the Job and waits up to five seconds on the retained process
handle. An additional **non-inherited host gate lease**, created before spawning,
is owned by `OwnedServer`; it is separate from both InstanceControls' original
gate and the child's inherited gate. Successful exit confirmation closes stdout,
the process handle and this lease. Close/Dispose is serialized and idempotent.

On timeout, WAIT_FAILED, or a wait exception, `CloseAndWait` throws
`CleanupFailed`. Lifecycle remains FAILED, does not emit Cleanup/Stopped and
does not report success. Although Lifecycle releases its own IPC handles, the
server's host gate lease still excludes both native and old Python launches.
The closed Job cannot be reused; stdout/process/lease remain strongly owned in
a pending-cleanup collection, not abandoned to GC/finalizers. A background
observer uses the actual retained-process Win32 wait (not the fault seam),
with 100 ms between nonblocking probes. Only WAIT_OBJECT_0 authorizes resource
release and removal from that collection. A failed native observation retains
ownership/exclusion rather than guessing that the child exited. Later confirmed
cleanup never rewrites the original failed Lifecycle run as success.

If native exit observation remains impossible, the host keeps this bounded set
of resources and the gate until exit; it does not permit a second server or
claim cleanup. On host death Windows releases those handles; the child's own
inherited gate still excludes another owner until the child exits, and last Job
close reclaims that owned process tree. This is deliberately fail-closed, not
unconditional reclamation under persistent OS failure. A partially created
suspended process uses the same pending-cleanup path if termination cannot be
confirmed; only its retained, self-created process handle may be terminated.
No PID lookup, browser termination, or unknown-server adoption exists.

## State and readiness

```text
STOPPED -> STARTING -> RUNNING -> CLOSING -> CLEANUP -> STOPPED
                   \ failure -> FAILED -> CLEANUP -> STOPPED
cleanup wait failure -> FAILED + pending ownership/gate -> confirmed exit -> resource release
host crash -> OS closes last Job handle -> owned child reclaimed
```

RUNNING denotes server management only. STOP during readiness cancels startup
and follows normal cleanup. Server crash follows failure cleanup. Restart
requires a new gate; an unknown existing server is never adopted.

Readiness reads at most 16 startup lines, each bounded to 4096 characters, and
accepts only `J1AI dashboard: http://127.0.0.1:<1..65535>/`. No DNS hostname,
external host, userinfo, path suffix, query/demo, fragment or HTTPS fallback is
accepted. HttpClient disables proxies, redirects and cookies. GET of
`/api/dashboard` requires HTTP 200, application/json, a body no larger than
1 MiB, unique JSON properties, exact basic schemaVersion 1 / operational /
Champion A / `operational_champion_20260922_v1` structure. Round entries are
not interpreted and no probabilities/results/metrics are computed. The Python
server retains responsibility for full recursive Champion-only validation.

A total cancellation deadline bounds stdout and response waiting, including
slow/trickling IO. Failure/timeout closes the owned Job. Logs accept enum event
codes only, with UTC timestamps; no exceptions, stdout, URL, body or research
values are logged. ST2 stays SEALED.

## Offline build and tests

The preparation manifest under `%LOCALAPPDATA%\J1AI\Toolchains` selects the
explicit user-local dotnet executable, approved warm package cache and offline
NuGet configuration. No package is vendored. `signatureValidationMode=require`
and trusted Microsoft repository signatures remain unchanged. Before restore,
confirm the recorded SDK/package approval, single local source and cached
archive SHA; missing verified warm cache must stop instead of downloading.
Only the package's unused WPF assembly reference is removed from these
WinForms-only builds, resolving WindowsBase conflicts without suppressing
warnings or changing the package. bin/obj remain ignored. The two
`packages.lock.json` files for Host and Tests are tracked: Host locks the direct
WebView2 dependency, while Tests locks its project/transitive graph. Both
projects set `RestorePackagesWithLockFile=true` and `RestoreLockedMode=true`.
The lock files freeze exact version, dependency graph and NuGet content hash;
they do not replace package signature verification. Intentional dependency
updates require separately authorized review and lock regeneration. Other
incidental lock files remain ignored; no package/binary is vendored.

Run these commands directly in PowerShell (no script-policy override). The
manifest/config/cache must be the reviewed environment-preparation outputs:

```powershell
$tools = Join-Path $env:LOCALAPPDATA 'J1AI\Toolchains'
$env:DOTNET_ROOT = Join-Path $tools 'dotnet'
$env:DOTNET_ROOT_X64 = $env:DOTNET_ROOT
$env:DOTNET_CLI_HOME = Join-Path $tools 'dotnet-cli'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
$env:DOTNET_NOLOGO = '1'
$env:DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE = 'true'
$env:NUGET_PACKAGES = Join-Path $tools 'nuget\packages'
$dotnet = Join-Path $env:DOTNET_ROOT 'dotnet.exe'
$root = (Get-Location).Path
Push-Location windows
& $dotnet restore J1AI.DashboardHost.Tests/J1AI.DashboardHost.Tests.csproj --locked-mode --configfile (Join-Path $tools 'NuGet.offline.config') --no-http-cache
& $dotnet build J1AI.DashboardHost.Tests/J1AI.DashboardHost.Tests.csproj --no-restore -c Release --disable-build-servers -warnaserror
& $dotnet test J1AI.DashboardHost.Tests/J1AI.DashboardHost.Tests.csproj --no-restore -c Release -warnaserror "-p:TestPython=$root\.venv\Scripts\python.exe" "-p:TestLauncher=$root\scripts\launch_dashboard.py"
Pop-Location
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_launcher.py tests/test_dashboard_server.py -q
git diff --check
```

These execute offline `dotnet restore`, `dotnet build --no-restore`, and
`dotnet test --no-restore`, with telemetry/workload notifications disabled.
No external test framework/adapter is cached, so the Tests project uses an
explicit MSBuild VSTest target invoking a dependency-free executable assertion
runner. These are real assertions and Windows process tests, not VSTest adapter
discovery. Any failed assertion returns nonzero. Do not report them as xUnit,
MSTest, or GUI tests.

The runner checks unique case names and the expected case count (68 in Phase 1;
191 with Phase 2, cleanup-setup and fixed-Smoke non-GUI cases). A
separate negative control runs an intentional assertion failure and an
unexpected exception through the **same** MSBuild execution path:

```powershell
# EXPECTED failure: 2 executed / 0 passed / 2 failed, dotnet test exit 1.
# Use the same explicit dotnet/environment above; do not treat this as the suite.
& $dotnet test windows/J1AI.DashboardHost.Tests/J1AI.DashboardHost.Tests.csproj --no-restore -c Release -p:RunnerSelfTest=true
```

This distinguishes failure propagation from the primary passing suite; it is
not a zero-discovery VSTest success. Filters are rejected, not silently ignored.
Windows fault tests include a real CreateJobObject failure (named-event
collision), invalid JOB_LIST rejection, and a deliberately unassigned suspended
synthetic child rejected/reclaimed before ResumeThread. Job-configuration
failure and lifecycle cleanup failure are explicitly injected/mock paths;
they are not claimed as spontaneous OS failures. Inheritable Job/non-inheritable
gate corruption is rejected before child creation. Repeated failed spawns are
measured after priming CLR exception initialization (32 repetitions, no handle
growth); successful Job/child cleanup is separately measured over 20 cycles.

Eight cleanup regression cases use actual Windows synthetic processes/Jobs:
timeout, WAIT_FAILED, wait exception, failed Lifecycle state, concurrent close,
GC ownership retention, repeated failure-cycle handle counts and host death
while cleanup is pending. Fault **routing** is injected: a test-only extra,
non-inherited Job handle delays child termination; a zero-duration real wait
produces WAIT_TIMEOUT, and a separate invalid probe handle produces actual
WAIT_FAILED/ERROR_INVALID_HANDLE without corrupting the owned process handle.
The wait-exception case is entirely injected. These are not claims that the OS
spontaneously exceeded the production five-second deadline. After releasing
the test Job handle, real retained-handle waits confirm OS termination and
stdout/process/gate reclamation, restart, and survival of an independent
synthetic instance in a separate Job. One child explicitly closes its inherited
gate early, proving that the host cleanup lease independently prevents a
duplicate. The abnormal-host test is jobless at the test-parent level, as before.
No mock substitutes for these process/gate assertions.

Coverage includes Python identity (Unicode, ASCII-case alias, `..`, directory
junction, symlink), old/new gate/Stop interoperability, Show coalescing and
Stop priority, duplicate suppression, command-line roundtrip, explicit-data
non-read, real suspended creation Job membership, handle allowlist, Job closure,
host abnormal termination, inherited-gate lifetime, restart, unrelated process
survival, handle counts, readiness validation/deadlines, crashes, fixed-code
diagnostics and side-effect-free default/help.

All spawned servers are temporary synthetic fixtures, never the production
repository server. Host-crash tests duplicate the synthetic child's retained
process handle into the test parent; the synthetic host is **not** assigned to
a test parent Job, so its own Job cleanup is actually tested. Forced termination
uses retained handles exclusively for processes created by that test. Temporary
directories have checked, unique OS-temp prefixes before recursive removal.

Symlink creation is not permitted in this non-admin environment. Junction
creation uses a temporary reparse point; the symlink identity check uses the
existing Windows `Users\All Users` symbolic link's path metadata only, without
IPC or reading any file under its target. The test requires a genuine symlink
and equal resolved identity; it is not silently skipped. No privilege/policy
change is made. These observations are for this Windows 11 x64 environment,
not proof that every Windows/policy combination supports the required Job API.

Validation on this environment: offline locked restore/build PASS (0 warnings/errors),
68/68 runner cases PASS including real Windows integration, negative-control
exit propagation PASS, Python launcher/server regression 190/190 PASS. No
production server/feed/GUI was used. The protected feed's SHA-256 remains
`a14216d22717dcb384c149c712e424511d0f0af7ad8d5f25ffee4bd026c53af8`.

## Phase 1 handoff checklist (historical)

- Native Form/WebView2 ownership, close/crash handling and profile isolation.
- Navigation/popup/permission/host-object/DevTools security restrictions.
- Delivering/consuming pending Show on the UI thread and best-effort foreground.
- Renderer/runtime failure handling distinct from native window close.
- Shortcut migration, deployment/runtime checks and explicit data selection.
- User-run GUI smoke: first open, duplicate click, X close, restart, native
  crash, server crash, renderer crash, external navigation rejection and no
  impact on personal browsers.

No shortcut migration, production JSON read/generation, real GUI, source update,
model/prediction/Elo/evaluation or performance inspection is part of Phase 1.

## Phase 2: explicit native GUI

Implementation baseline: `0e8eb0481df57fa8670278a04c3d70e48dc31706`.
Only explicit `--gui [--repository ROOT] [--data EXPLICIT_JSON]` starts the
native `J1 AI Predict` Form. No arguments remain a no-op; `--help` does not
resolve identity, create IPC/profile or start a process. `--gui`, `--core`
and `--stop` are mutually exclusive. Phase 1 Core, Python launcher/server,
shortcut installer and web files are unchanged. There is no desktop shortcut
migration or production-feed GUI authorization in this phase.

`GuiEntry` acquires the existing repository/session gate **before** preflight
or Form creation. A duplicate signals the existing Show event and returns,
without another server/Form/profile. This also excludes an old Python or Core
owner: legacy owners without a displayable native window are left unchanged.
`--stop` continues to signal the same Stop event; its meaning for Python is
unchanged. A GUI owner closes its own native window and owned server.

### STA and lifecycle

`StaPump` starts a dedicated STA thread before any Form/WebView2 construction,
installs `WindowsFormsSynchronizationContext`, and runs `Application.Run`
with an `ApplicationContext` that has **no MainForm**. Closing a Form must not
prematurely end the pump while cleanup awaits. Async initialization/readiness
returns to that STA context; no assumption is made about async Main's thread.
Only the retained-process cleanup wait runs in `Task.Run`. The pump's thread
exit is joined before GUI entry completes. `DashboardForm.RequireUi` checks
STA and thread identity. `OnUiAsync` marshals through `BeginInvoke` only after
Show creates the handle; it never creates an HWND from a background thread.

```text
gate -> preflight -> Form/loading -> server/readiness -> WebView2 -> RUNNING
STARTING + SHOW -> one pending flag -> one restore after initialization
RUNNING + SHOW -> restore own minimized Form; Activate best effort
X or STOP -> coalesced close request -> WebView2 disposal -> Form.IsDisposed
          -> runtime exit observation -> owned server exit confirmation -> gate release
failure -> FAILED -> same disposal/owned-server cleanup (no automatic restart)
```

FormClosing requests closure but is cancelled until the coordinator handles
it. Neither FormClosing, FormClosed nor HandleDestroyed proves disposal.
The control/controller is disposed before the Form; `IsDisposed` and its
disposal completion signal provide evidence. HWND recreation is not a close.
Stop is checked before Show during startup and running. Only this Form is
restored/activated, with no foreign-window lookup or focus coercion.

Runtime `ProcessFailed` is distinct from a user's close request and produces
a failed run; browser/renderer failures do not mean the Form was destroyed.
A fixed error notification and enum-only local log are used, without exception
messages, paths, stdout, response bodies or prediction values. Browser-process
exit is observed through WebView2's environment event, never a startup PID.
Controller initialization/exit cleanup is bounded (five seconds each). Failure
is not reported as successful shutdown; no browser PID is searched or killed.

If Form disposal throws before disposal is confirmed, the STA pump, server
and controls stay strongly owned awaiting that confirmation; a second server
is not allowed. If disposal is confirmed but runtime exit cannot be confirmed,
the owned server is still reclaimed and the run fails. If server cleanup wait
fails, the unchanged Phase 1 pending reaper retains its stdout/process/gate
lease until real exit confirmation. Failure never becomes success afterward.

### Policy preflight and isolated environment

Before starting a server, inspect the process's nonempty `WEBVIEW2_*`
environment variables and all configured WebView2 policy values in HKLM/HKCU,
Registry64/Registry32. Nonempty loader/browser/profile/channel/debug overrides
are rejected, not erased or overridden. Registry override checks conservatively
reject even entries naming other apps, rather than relying on precedence
guesses for AppId, EXE or wildcard. Other unknown configured WebView2 policies
also fail closed. No registry, policy, permissions, PATH or trust setting is
modified. Inspection is repeated before environment creation.

The sole reviewed legacy exception is the root DWORD
`RendererCodeIntegrityEnabled` with value 0 or 1. Environment review on
2026-10-10 found value **0** at both:

- HKLM / Registry64: `SOFTWARE\Policies\Microsoft\Edge\WebView2`.
- HKLM / Registry32: the same logical path, exposed physically under
  `SOFTWARE\WOW6432Node\Policies\Microsoft\Edge\WebView2`.

HKCU had no corresponding value; no additional loader, AppId/EXE/wildcard,
debugger, browser-argument or profile override was present. This entry is
classified as **legacy/undocumented for WebView2**, not an active supported
WebView2 policy. Microsoft's [Edge legacy policy documentation](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/renderercodeintegrityenabled)
states that Edge ignores it from 119 onward. [Enterprise management](https://learn.microsoft.com/en-us/deployedge/webview2-enterprise)
separates browser policies from WebView2 policies; the [WebView2 supported list](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-webview-policies)
does not include this entry. Loader/environment overrides are independently
documented by [CreateAsync](https://learn.microsoft.com/en-us/dotnet/api/microsoft.web.webview2.core.corewebview2environment.createasync)
and the pinned SDK's API XML.

Preflight GO is based on that **official supported-policy scope**, not proof
that an undocumented value is internally ignored or that any particular
renderer mitigation is enabled. Runtime process mitigation flags were not
measured. Additional dangerous overrides still cause STOP. No protection is
disabled and no debug/security-bypass arguments are added.

Use installed Evergreen Runtime 154 or newer, stable channel only, with the
pinned SDK. Missing/preview/older runtime, profile or initialization failure
is fail-closed. `CreateAsync` receives a dedicated
`%LOCALAPPDATA%\J1AI\Dashboard\<repo-id>\webview2-profile`, exclusive access,
extensions disabled, OS primary-account SSO disabled and empty extra arguments.
Reparse-point profile ancestry and an unwritable profile are rejected; the
resulting environment's profile path is verified. Profiles are **not deleted**,
including synthetic-test profiles. Personal Edge/Chrome profiles are unused.
There is no CDP, external browser or `--app` fallback.

### Navigation, resource policy and CSP

`DashboardNavigation` parses the URI and compares scheme, host and dynamic
port exactly, also checking canonical raw authority. No URL-prefix check
authorizes a request. Userinfo, encoded paths, backslashes, malformed URLs,
numeric host aliases, other ports/schemes and arbitrary paths are rejected.
Document navigation permits only `/` and `/index.html`, anchors, and the exact
optional `/?demo=1`; demo is never an automatic fallback.

The resource route allowlist is exactly:

```text
/
/index.html
/styles.css
/app.js
/components/prediction-probability-bar.js
/dashboard-data.js
/team-colors.js
/demo-data.js
/api/dashboard
```

NavigationStarting checks redirects and documents. FrameNavigationStarting
cancels all frame navigation. The **three-argument** WebResourceRequested
filter covers all supported resource contexts and request-source kinds;
only GETs from document sources on allowed routes pass. Worker-source requests
are denied. Missing mandatory SDK/runtime APIs cause initialization failure,
not a permissive fallback. Popup/new-window, download, permission, external
protocol, authentication and certificate-error handlers deny their requests.
Default download location is isolated within the dedicated profile as an
additional precaution, not a replacement for cancellation. DevTools, browser
accelerator keys, context menus, default script dialogs, host objects, web
messaging, error pages, autofill and password autosave are disabled.

WebResourceRequested does **not** intercept every scheme (notably data/ws).
CSP therefore supplements, and never replaces, these request guards. Only an
allowed HTML document GET is intercepted using a deferral **before** WebView2
sends its pending request. A strict, no-proxy/no-cookie/no-redirect HttpClient
makes one owned-loopback fetch. HTTP 200, text/html, a five-second deadline and
1 MiB cap are required. Exact entity bytes/MIME and end-to-end response headers
are preserved; hop-by-hop transport headers are omitted. CSP and no-store are
added using `CreateWebResourceResponse`, assigned to the pending request's
`Response`, and the deferral is completed. This replaces that request; it is
not a second fetch or a response-received header mutation. No other route is
proxy-fetched, particularly `/api/dashboard`. JSON display-file contents are
not read by the host; the unchanged readiness probe validates basic API schema.

CSP defaults to none, allows scripts/styles/connect only at the owned origin,
disallows frames/workers/objects/base/form actions, and uses a sandbox without
popup/download permissions. Inline styles remain necessary for the existing
probability-bar implementation; inline scripts are not allowed. Data **images**
support the existing fixed SVG favicon, but general data document navigation
is denied. These are page-level controls, not an OS firewall or proof that the
Evergreen runtime/updater never performs its own background communication.

### Phase 2 validation and remaining manual checks

Normal `dotnet test` runs **191** cases: all 68 original Phase 1 cases, 53
GUI lifecycle/policy/mock assertions, three cleanup-setup failure cases, and
67 fixed-Smoke non-GUI assertions,
without opening GUI. The assertion runner
still checks unique names, exact count and nonzero exit on failures. The
negative-control intentionally reports 2 failed cases and exit 1. Both tracked
lock files, approved package/cache and signature configuration are unchanged.

Explicit synthetic GUI mode is separate from normal tests:

```powershell
# Same explicit dotnet environment; announce synthetic GUI use before running.
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --synthetic-gui-tests "$root\.venv\Scripts\python.exe" "$root\scripts\launch_dashboard.py" "$root\web"
```

It copies implementation-only UI assets to a fresh OS-temp repository, starts
only a synthetic Python loopback server, and uses empty synthetic API data and
a deliberately nonexistent explicit --data path. No production server/feed
is used. Its **10** cases cover STA/await/marshal, minimized
restore, HWND recreation vs disposal, actual WebView2/UI loading, single-fetch
HTML interception, CSP enforcement (inline script/worker/connect), popup and
download prevention, permission denial, route filtering, explicit demo, real
IPC duplicate/Show/Stop, X/cleanup/restart, unrelated server survival, retained
handle synthetic-server crash and startup Show/Stop competition. Each GUI case
checks actual window/server/runtime completion and gate reuse where applicable.

The suite distinguishes actual WebView2 from mocks:

- Seven cases use the real WebView2 Runtime, including document initialization
  interrupted by Close/Stop, an HTTP failure, and the five-second HTTP timeout.
- Two cases use real WinForms/IPC without initializing WebView2 (STA ownership
  and Stop/Show during server readiness).
- One case uses a real Form and cleanup deadline with a **mock unresolved SDK
  Task**. It does not stall an actual `CreateAsync` or
  `EnsureCoreWebView2Async` operation.
- The actual allowed-navigation negative control must fail the same rejection
  assertion used for the blocked navigation. The standalone negative-control
  CLI intentionally exits 1; it is not a passing test run.

The review run passed 121/121 non-GUI assertions, 10/10 synthetic GUI cases,
and cleanup 30/30 twice. This Low-fix run passed **124/124** non-GUI cases
(including the three new setup failures), **30/30** cleanup repetitions,
a no-restore build with zero warnings/errors, and **190/190** Python focused
cases. The runner negative control reported the expected two failures and
exit 1. Synthetic GUI is **not rerun** for this Low fix: the previous
attempt to remove eight newly created synthetic profiles was blocked by
environment policy, and this task must not add more such profiles or bypass
that policy. The previous GUI PASS is historical evidence, not a new run.

Cleanup fixtures now scope observer-created Job duplicates **before** calling
`OwnedServer.Start`, including setup exceptions before it returns. Each scope
owns and closes its duplicate once; early release and final cleanup are
idempotent. Three non-GUI Windows tests inject an observer exception, a real
`CreateProcessW` missing-executable failure, and a synthetic creation exception.
They confirm a non-inherited duplicate becomes an invalid OS handle without
GC, delays or deletion retries, and that the gate can be reacquired. Product
Job ownership, retained interpreter waits and the pending reaper are unchanged.

The original single-threaded synthetic HTTP fixture could stall behind a
Chromium speculative idle connection in the expanded security test; the
synthetic fixture now uses ThreadingHTTPServer and bounded test-client timeout.
No production server change or security relaxation was needed. The expanded
suite is rerun after that fixture correction, with no residual synthetic
server/runner processes. Profiles remain intentionally retained.

Renderer/browser ProcessFailed handling and disposal-failure retention are
unit/mock fault injections, **not** a claim that an actual runtime crash was
induced. Real host-crash/Job cleanup is covered by the preserved Phase 1 tests;
GUI runtime crash/visual behavior and Windows focus restrictions remain manual
smoke items. Visual GUI smoke and production-feed GUI are not executed here.
Actual renderer/browser crash recovery, a stalled real SDK initialization
Task, production-feed GUI smoke, and user-visible GUI error notification and
manual foreground/minimize/DPI/taskbar smoke remain **unproven**, despite
synthetic minimized-Form assertions. Mock coverage does
not establish actual SDK cancellation or runtime crash recovery. Production
smoke must also confirm no impact on existing shortcuts or personal browsers;
shortcut migration and production use remain separately gated.
Python launcher/server focused regression: 190 cases. Build must finish with
zero warnings/errors; mandatory failures prohibit commit.

### Fixed-profile manual Smoke runner (separate approval required)

The test assembly now has a separate fixed-fixture runner. It does **not**
change the product, its CLI, or the existing ten random-repository GUI cases.
Do not use `--synthetic-gui-tests` as a substitute: it still creates new UDFs.
There are no new packages and no arbitrary repository/UDF/backend/data overrides.

Read-only entry (no GUI, fixture, UDF, lock or state creation):

```powershell
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --smoke-preflight
```

It reports UNINITIALIZED or a validated CLEAN fixture and the exact plan SHA.
An uninitialized plan is **not** permission to provision or launch. First-use
requires a subsequent explicit user approval of the reported paths and plan SHA.
Future, separately authorized commands are:

```powershell
# NOT authorized/executed by the harness implementation task:
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --smoke-run --approve-first-use <approved-plan-sha>
# After confirmed CLEAN shutdown, reuse the same fixture/UDF:
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --smoke-run
# Existing fixed-fixture event only; no server/window/profile creation:
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --smoke-show
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --smoke-stop
```

The fixed root is
`%LOCALAPPDATA%\J1AI\Smoke\dashboard-v1\fixtures\J1AI-native-test-dashboard-smoke-v1`.
Identity comes exclusively from the existing Python `instance_id()` (including
when the path does not exist); `WebViewPreflight.ProfilePath()` selects
`%LOCALAPPDATA%\J1AI\Dashboard\<that-id>\webview2-profile`.
The first approved allocation is at most **one** UDF. Subsequent runs add
**zero** UDFs. All existing UDFs are inventoried by path metadata only and never
entered, repaired, copied, cleared or deleted. A collision with the product ID,
an existing unapproved UDF or even its parent directory fails closed.

The immutable fixture manifest binds root/identity/UDF, production identity,
the original UDF path set, exact UI asset hashes, Python/identity-authority/
runner/product/SDK/backend hashes and the available Runtime version. Copied
assets are verified again; code, Runtime, inventory or asset changes require
review, not automatic manifest refresh or a new profile. Only the existing
synthetic Python backend can be started, through the existing `OwnedServer`.
It binds `127.0.0.1:0`, supplies an empty synthetic API response and never opens
the explicit nonexistent `must-not-be-read.json` data argument. No product
server, saved feed, model or research artifact is loaded.

Safety/state contract:

- A non-shared file handle excludes concurrent Smoke runs across sessions.
  The unchanged identity-based named gate/Stop/Show still owns GUI/server IPC.
- UNINITIALIZED has no persistent fixture. Provisioning needs the exact first-use
  plan SHA; unknown/partial directories are rejected, not overwritten.
- Before startup, a write-through `run.intent` and RUNNING state are persisted.
  State replacement uses a flushed, create-new `.pending` file and rename.
  A surviving intent, partial write, malformed/duplicate metadata, previous
  RUNNING/BLOCKED state or missing proof prohibits automatic reuse.
- CLEAN requires the actual Form disposal, exact environment UDF mapping,
  Runtime exit event, complete owned-server resource cleanup and permitted
  UDF inventory delta. Inspect's verified root/UDF volume/file IDs remain in
  RUNNING and are compared with retained directory handles before GUI startup;
  reuse never registers a replacement ID. Finish revalidates both retained
  handles and path identities before CLEAN. Missing/mismatched/unbound handles
  cannot authorize CLEAN. Only approved first use registers new directory IDs.
  Initializing/failed SDK paths lacking proof remain BLOCKED; controller/PID
  disappearance is not proof. The intent is removed only after CLEAN is durable.
- Reparse points, UNC/ADS/traversal paths and unapproved locations are rejected.
  Existing verified directory ancestry is acquired root-to-leaf, held with
  list/read-attributes access and read/write sharing but no share-delete, and
  final handle paths are checked. One run lease retains root, UDF, ancestry
  and the cross-session file lock through GUI use and cleanup. Real Win32 tests
  verify rename/delete denial and concurrent directory/child-file read/write;
  actual WebView2 compatibility/reuse still requires separately approved GUI
  smoke. This is not an authentication boundary against a hostile process with
  the same user SID.
- A separate self-created worker owns the GUI, server Job and fixture lease.
  Its supervisor waits at most five minutes, requests the same fixture's Stop,
  then waits at most twenty seconds. No worker/browser is forcibly killed.
  A still-live worker retains ownership; unfinished state denies reuse. Parent
  stdin disconnect is remembered even before IPC acquisition and acts as Stop.
  `--smoke-worker` is the supervisor's internal entry, not a manual launch mode.
- No UDF deletion, alternate-profile fallback, registry edits, CDP, security
  flags, production shortcut changes or personal-browser operations are used.

The Smoke identity helper has one monotonic ten-second deadline from invocation
through output validation: process/tree exit and concurrent bounded stdout and
stderr reads must all finish within it. Each stream is capped at 4095 decoded
characters during reading; overflow fails immediately. A test-assembly-only
create-time, non-inherited KillOnClose Job owns the venv broker, interpreter and
pipe-holding descendants. Timeout/failure terminates only that owned Job, then
allows at most five additional seconds to confirm zero active Job processes,
the retained startup handle's exit, and completion of both stream reads before
releasing resources. Cleanup never converts a failed deadline into success.
Unconfirmed cleanup reports `identity_cleanup_unconfirmed` and retains resources
in an explicit pending reaper, rather than awaiting indefinitely or abandoning
ownership to GC. No PID/name discovery, personal-browser kill or product Job
change is involved.

Non-GUI verification:

```powershell
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --smoke-fixture-tests "$root\.venv\Scripts\python.exe" "$root\scripts\launch_dashboard.py"
# Intentional two invalid states: MUST exit 1 (not a passing suite).
& $dotnet windows/J1AI.DashboardHost.Tests/bin/Release/net10.0-windows/J1AI.DashboardHost.Tests.dll --smoke-negative-control
```

The 67 cases use in-memory evidence and fresh OS-temp namespaces, not real UDFs
or the fixed fixture. Actual Windows tests cover file-handle exclusion across
processes, named Show/Stop, junction rejection, metadata-only rejection of an
existing OS symlink, retained directory handles blocking rename, file-ID
replacement detection and bounded supervision of a non-GUI child without kill.
Identity uses the real Python authority. Other cases cover allocation limits,
manifest/provenance, unfinished journal/state, cleanup proofs, source/assets,
readonly non-mutation and validator negative controls. Symlink creation is not
claimed: no elevation/Developer Mode change is used.

The original 39 cases are retained. Twelve directory-boundary tests cover
Inspect/Begin/Bind replacement, reparse substitution, identity mismatch, failed
handle acquisition, retained-handle rename/delete denial, first-use conflict,
shared read/write compatibility and missing cleanup proof. Sixteen identity
helper tests use real Windows Jobs/processes/pipes, covering hung helpers,
descendants holding either stream, concurrent overflow, partial output, exit
failure, retry after timeout, unrelated-process survival and handle counts.
The former twelve-second pipe-holding success is rejected using the actual
ten-second configuration; tree/streams/handles are confirmed reclaimed.
Injected faults are not spontaneous OS failures or actual WebView2 crashes.

This implementation validation is non-GUI only. The historical GUI 10/10 PASS
is not a new run. The original implementation run passed 163/163 total Native assertions,
39/39 Smoke cases and 190/190 focused Python cases; no-restore Release build
had zero warnings/errors. Both runner and Smoke negative controls reported the
expected two failures and exit 1. Actual read-only Smoke preflight reported
UNINITIALIZED without creating the fixed fixture/UDF. The existing 31 UDF paths
and all five protected input hashes were unchanged.

The subsequent review-fix run passed **191/191** total Native assertions,
including **67/67** Smoke cases (28 added), and **190/190** focused Python cases.
No-restore Release build had zero warnings/errors. Both negative controls
again produced two expected failures and exit 1, including MSBuild failure
propagation. The old Begin/Bind replacement now fails with `directory_replaced`,
retains the original IDs in RUNNING and cannot reach CLEAN. The old inherited
pipe case failed with `identity_timeout` in approximately 10.022 seconds,
including confirmed tree/stream/handle cleanup. Eight repeated short timeouts
after priming left the process handle count unchanged (391 to 391).
Read-only preflight again reported UNINITIALIZED; fixed fixture/UDF remained
absent, all 31 existing UDF paths and five protected hashes matched, and no
new test temporary directories or dashboard/helper processes remained.
No real WebView2/GUI case was run for these fixes. File-sharing compatibility
is Win32-only evidence, not proof of actual SDK profile reuse.

Fixed-fixture provisioning, actual UDF reuse, renderer/browser
crashes, real SDK initialization stalls, production-feed smoke and manual
notification/focus/minimize/DPI/taskbar/personal-browser checks remain unproven.
Retained UDF cache size may grow even when the UDF **count** is fixed; a dynamic
port changes the origin. Future manual smoke must check fresh backend requests,
not accept cached display as proof. An uncertain crash requires a new explicit
recovery review; no automatic repair/delete/reallocation is provided.

Future user-run GUI smoke: first launch, duplicate launch during loading,
minimized Show, X/restart, --stop, failure notification, real renderer/runtime
failure, external-navigation refusal, taskbar/DPI behavior, no impact on
personal browsers. Desktop shortcut migration and production-feed display
require separate explicit authorization. ST2 remains SEALED; no model,
prediction, Elo, metrics, source update or feed generation occurs in Phase 2.

### Independent fixed-Smoke Network Observer (review only)

`windows/J1AI.SmokeNetworkObserver` is a standalone, package-free .NET 10 Windows
console project. Its only project reference is from its own new assertion runner;
neither project references/rebuilds DashboardHost or DashboardHost.Tests. The
frozen Smoke runner, backend, manifest, state and UDF are not rewritten. The
initial unknown TCP candidate remains **unclassified**: a new observation
cannot reconstruct or retroactively clear it.

The new observer has no GUI/backend launch command, HTTP client, CDP, packet
capture, profile override or browser kill operation. The implementation task
builds these two projects only and runs **158 value/Fake-only assertions**. No
real TCP collector, formal Stop, GUI or WebView2 initialization is executed.
The historical GUI 10/10 and Native/Python results above are not new results.

Future entry points (NOT authorization to execute them):

```powershell
# Read-only: prints a prospective plan plus its SHA; creates nothing.
& $dotnet windows/J1AI.SmokeNetworkObserver/bin/Release/net10.0-windows/J1AI.SmokeNetworkObserver.dll --plan <future-approved-absolute-evidence-directory>
# Only after independent review and explicit approval of the exact saved plan bytes:
& $dotnet windows/J1AI.SmokeNetworkObserver/bin/Release/net10.0-windows/J1AI.SmokeNetworkObserver.dll --observe <plan.json> --approve <sha256-of-plan-file>
```

`--plan` does not collect TCP/process data or create directories, locks, manifests,
state, journal or UDF. Save/approve a plan in a subsequent authorized task; a
newline/BOM added when saving changes the file SHA and must be accounted for.
The evidence destination must be one canonical child of
`%LOCALAPPDATA%\J1AI\Diagnostics\NetworkObserver`, outside Smoke control/UDF.
**No concrete evidence directory or plan file is created by this implementation.**
Its exact absolute path, parent preparation, plan SHA, ACL, capacity and retention
need approval before observation. The writer requires approved ancestors to
already exist and refuses an existing session directory. It pins ancestry and
the new directory without share-delete, rejects reparse/ambiguous paths, sets
an explicit current-user/SYSTEM inheritable DACL and never deletes/overwrites
evidence. Proposed retention: seven days or until review is complete, then a
separately authorized cleanup; hard caps are 4 MiB per document and 64 MiB per
session. No automatic rotation/deletion. Same-user/admin interference is not an
authentication boundary.

Plans bind identity `8f96edbb39b7d4d47cdad47c`, immutable manifest
`ce8e230e4deb35b67298f0dcdfecb421cf282125b7ae509de794df91b599cf67`, initial CLEAN
state `f7f87885a0b5f66f65e065295bc60a9c989a63ce654b5502dac014a36e1d04a7`, its
existing root/UDF file IDs, all 32 UDF paths, the observer hash, exact executable
paths/hashes and frozen runner/backend/product/SDK/identity-authority hashes.
Assets are checked against the unchanged manifest. This is a plan for the next
observation from that exact baseline, not automatic approval after another run.
No independent Python identity implementation or new manifest is introduced.

Observation/ownership contract:

- An observer-specific named mutex excludes concurrent observers. Abandonment
  fails closed. The operator must wait for `OBSERVER_READY` and keep this observer alive before separately
  starting the approved existing Smoke runner. Ready requires a durable header
  and successful empty baseline query. No automatic GUI launch follows.
- Local WMI process metadata is transient, not logged. Exact argv parsing,
  approved executable hashes (held read-only, no write/delete sharing), exact
  single UDF argument, worker/supervisor and runtime parent chains, and retained
  query/synchronize-only process handles establish an **OS-scoped** identity.
  [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)
  supplies the full PID+creation FILETIME; WMI's microsecond
  birth must match it. Parent birth ordering, PID reuse and unidentified runtime
  descendants are checked. Metadata disappearance is recorded separately from
  a signaled retained process handle. Personal/unrelated TCP rows are discarded
  in memory before evidence serialization; unknown attribution records an error,
  not a guessed socket owner.
- The unchanged runner does not export its readiness URL. The observer therefore
  uses the OS listener owned by its verified synthetic backend/interpreter chain:
  exact script/root/nonexistent `--data` argv, approved Python images, same worker,
  PID+birth and exactly one `127.0.0.1` LISTEN socket with a dynamic valid port.
  No literal port or header/HTTP-response guessing. Missing, multiple, wildcard,
  changed or unverified listeners stop the workflow with INCONCLUSIVE evidence;
  the GUI safety gate stays BLOCKED. Real interoperability is **not yet tested**.
- [GetExtendedTcpTable](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable)
  with `TCP_TABLE_OWNER_PID_ALL` queries IPv4 and IPv6 after each
  250 ms scheduling delay. Actual query interval/duration, UTC bounds, sequence
  and gaps are persisted; this is not a guaranteed 250 ms sampling frequency.
  Missing sequences, backwards/nonfinite timing, query failure or >1.5 s query/
  interval gaps fail closed. A single snapshot cannot authorize PASS. A stalled
  WMI/native query is bounded by the caller; no replacement collector is started.
  The session deadline is six minutes, followed by bounded Stop/cleanup handling.
  Successfully collected partial-family rows are retained even if the other
  family query fails. No network records from unrelated processes are saved.
- IP parsing rejects noncanonical IPv4 forms. Mapped IPv6 is normalized explicitly;
  original addresses, family, scope spelling and native row bytes remain evidence.
  Loopback/private/link-local/ULA/public/unspecified/invalid are distinct. Only
  the exact verified backend address **and** port are allowed. Other loopback
  endpoints are denied. LISTEN/BOUND/CLOSED are not outbound traffic proof and
  require review rather than automatic permission. SYN, established and closing
  states do not establish application payload transmission.

Evidence/Stop contract:

1. Capture only attributable raw rows plus acquisition/ownership diagnostics.
2. Create-new pending JSON, durable flush, read-back equality, atomic no-overwrite
   rename and final read-back.
3. Classify and durably save the per-snapshot verdict.
4. Only then request the unchanged runner's fixed-identity `--smoke-stop` on denial
   or uncertainty. A write failure attempts a durable failure diagnostic first,
   requests Stop and remains INCONCLUSIVE; it never produces a success result.

Stop uses argv arrays/Windows quoting, no shell and no guessed PID/event. Only
the self-created exact Stop CLI/helper tree belongs to a separate create-time,
non-inherited KillOnClose Job. Its acknowledgement/exit/tree cleanup are bounded
and distinct from Runtime exit. No GUI/browser is assigned to that Job or killed.
Unconfirmed cleanup retains the command handle; no success is reported. All Stop
tests use Fake; this new Win32 adapter is build/static-review evidence only.

Results distinguish `PASS_OBSERVED_SCOPE`, `BLOCKED` and `INCONCLUSIVE`, along
with READY/OBSERVING/NORMAL_END/UNAUTHORIZED/OWNERSHIP_UNKNOWN/WRITE_FAILED/GAP/
CRASH phases. A final result requires its matching SHA receipt and successful
observer exit; missing/pending/failed evidence is not PASS. Only a new matching
RUNNING run followed by the frozen runner's CLEAN Runtime-event/server/Job/window
proofs, signaled retained handles and unchanged inventory confirms normal end.
An arbitrary caller-supplied end flag cannot authorize PASS. Cookies, URLs, HTTP
payloads, predictions, personal command lines and unrelated traffic are excluded.

Limits and next gate:

- External OS identity is **not** direct SDK `GetProcessInfos` identity. Evidence
  explicitly says SDK identity is not asserted. The Runtime exit event is read
  from the unchanged runner's matching CLEAN record, not invented from a PID.
  If direct SDK PID attestation is required, this independent observer cannot
  provide it; do not call that unverified property PASS or modify the frozen
  runner/manifest automatically.
- TCP polling can miss short-lived connections and processes; UDP/QUIC, shared
  DNS resolver attribution and payloads are outside scope. PASS_OBSERVED_SCOPE
  never means absence of all external communication. Observer crash/missing
  result leaves the observation incomplete; the frozen Smoke supervisor remains
  responsible for its own bounded lifetime. Real capture/performance, WMI/ACL
  access, endpoint discovery and Stop interoperability remain unproven.
- Fake tests cover IP/endpoints/states, PID/birth/lineage, gaps, write/flush/read/
  commit/receipt faults, evidence-before-Stop, collector/observer failure and
  exclusion of unrelated sockets. Six internal test-only mutants (private allowed,
  all loopback ports allowed, PID-only, missing snapshots treated as empty,
  Stop-before-raw and unknown backend PASS) must fail the SAME assertions and exit 1.
  There is no CLI/environment switch to activate mutants in the observer.
- After code review/main integration, require a new read-only approval plan with
  exact diagnostic path/ACL/retention, fresh plan/binary hashes, unchanged frozen
  fixture/UDF and baseline, readiness/start/Stop/end evidence procedure and explicit
  permission for one same-UDF observation. No second GUI run, evidence destination
  provisioning, profile mutation, production-feed smoke or production use is
  authorized by the implementation or its Fake tests.
