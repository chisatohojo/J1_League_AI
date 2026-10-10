# Windows Dashboard NativeHost — Phase 1 core

## Scope

Baseline: `1091d03c2dd52b9cde09e91a313417aac4ed967f`.
This is lifecycle infrastructure, **not a finished GUI**. The WinExe targets
`net10.0-windows`, WinForms, x64, SDK `10.0.401`, with WebView2 SDK pinned to
`[1.0.4258.31]`. No Form/WebView2 instance, browser, CDP, desktop integration,
model, feed builder or research evaluator is started.

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
handle before releasing the host gate. Cleanup timeout is failure, not
success; any surviving child retains its own gate until Windows reclaims it.
A partially created suspended process can only be terminated through the
retained, self-created process handle. No browser termination exists.

## State and readiness

```text
STOPPED -> STARTING -> RUNNING -> CLOSING -> CLEANUP -> STOPPED
                   \ failure -> FAILED -> CLEANUP -> STOPPED
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
warnings or changing the package. bin/obj/local restore lock files are ignored.

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
& $dotnet restore J1AI.DashboardHost.Tests/J1AI.DashboardHost.Tests.csproj --configfile (Join-Path $tools 'NuGet.offline.config') --no-http-cache
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

The runner checks unique case names and the expected case count (60). A
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

Validation on this environment: offline restore/build PASS (0 warnings/errors),
60/60 runner cases PASS including real Windows integration, negative-control
exit propagation PASS, Python launcher/server regression 190/190 PASS. No
production server/feed/GUI was used. The protected feed's SHA-256 remains
`a14216d22717dcb384c149c712e424511d0f0af7ad8d5f25ffee4bd026c53af8`.

## Phase 2 review gates (not implemented)

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
