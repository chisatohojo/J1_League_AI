# J1AI home dashboard

## Scope and source boundary

The repository had no frontend or design system. `web/` adds dependency-free
HTML/CSS/JavaScript with native ES modules and Node's built-in test runner.
No framework migration or npm install is needed. `scripts/serve_dashboard.py`
uses only Python's standard library.

The UI server does not load models, regenerate predictions, export CSVs, join
outcomes, collect data, or execute evaluations. The separate display adapter
described below joins only the approved Champion projection to validated official
results. Existing data, artifacts, sidecars, protocols and model code are unchanged.

No production Champion-only feed has been generated yet. The approved adapter
can project Champion A from the saved ST2 comparison artifact; the mixed CSV is
never a direct input to the UI. The default operational view remains empty.
The opt-in UI demo uses entirely synthetic 2030 fixtures and probabilities, with
a persistent demo banner and per-card DEMO/synthetic labels. It is not Champion
performance. ST2 is a static `Research Models / ST2 / SEALED` status only: no
challenger probabilities, outcomes, interim metrics, comparisons, or aggregates.

## Local startup

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.serve_dashboard
```

Open `http://127.0.0.1:8765/` for the unconnected operational view. Choose
“UIデモを見る” (`http://127.0.0.1:8765/?demo=1`) for the synthetic preview.
Stop with Ctrl+C. `--port` changes the port; binding is loopback only.
There are no external assets, fonts, data requests, or write endpoints.

## Screen and components

The screen flows vertically, without isolated result/prediction tabs:

```text
J1AI header / in-page navigation
Champion A status + explicit data-mode banner
01 前節の予想結果                 Reading guide (desktop sidebar)
   Teams → actual score           ST2 🔒 SEALED
   → saved probability bar → AI PICK / RESULT / HIT or MISS
02 次節の予想
   Teams → kickoff → saved probability bar → AI PICK
```

Both sections use `MatchCard` and `PredictionProbabilityBar`. HIT/MISS has text
and an icon, not color alone. No aggregate performance metric is displayed.
Equal highest probabilities are shown as a tie and excluded from HIT/MISS;
there is no arbitrary tie-break or threshold. AI PICK uses full input precision,
never rounded labels. Kickoff is displayed in Asia/Tokyo. Saved prediction time
is available in the card note's tooltip.

Desktop has two match-card columns and a subdued sidebar. At <=1100px cards
become one column; at <=760px the sidebar moves below both sections.
320px/375px viewports are tested for horizontal overflow. Cards and names wrap;
external numeric labels remain readable. Keyboard navigation, skip link, visible
focus, accessible bar labels, error/live regions, and reduced-motion support are
included.

### PredictionProbabilityBar

`web/components/prediction-probability-bar.js` exports the component and pure
display mapping `buildProbabilityView`. Props: `homeProbability`,
`drawProbability`, `awayProbability` (percentages), `homeColor`, `awayColor`
(six-digit hex), `homeLabel`, `awayLabel`.

One flex track contains HOME, DRAW, AWAY in that order, with no gap, rounded
corners and hidden overflow. Widths reflect supplied proportions. Numeric labels
are always visible below the track, including 0%; container queries show labels
inside segments when there is room. Tiny positive values can display `<0.1%`
rather than misleading zero. Contrast-aware text supports light team colors.

Display-only normalization fills 100% for totals within one percentage point
(including already-rounded 33/33/33). Largest-remainder rounding to 0.1 percentage
points gives deterministic labels. Props and saved data are never overwritten.
The operational feed separately requires percentages summing to 100 within 0.02;
the bar's broader tolerance is only a presentation helper. Invalid/negative/
nonfinite values fail rather than impute.

`web/team-colors.js` separates provisional accents, keyed by stable TeamMaster
IDs, from components. These are not verified official brand assets. Unknown IDs
use a neutral fallback; DRAW is always `#64748b`. No team/name/data mutation.

## Prepared Champion-only JSON boundary

A separately approved display export can be read explicitly:

```powershell
.\.venv\Scripts\python.exe -m scripts.serve_dashboard --data C:\path\champion-dashboard.json
```

No production export is created in the implementation task. The server snapshots
only the specified JSON at startup; restart to load an updated export. It never
searches for data, reads research CSVs, or joins results. Ad hoc extraction from a
mixed research artifact is not approved: use only the validated adapter below.

Schema v1 (exact keys, extra fields rejected recursively):

| Object | Keys / requirements |
| --- | --- |
| Root | `schemaVersion: 1`, `mode: "operational"`, `model`, `updatedAt`, `previousRound`, `nextRound` |
| `model` | `name: "Champion A"`, `version: "operational_champion_20260922_v1"` |
| `updatedAt` | Timezone-qualified ISO timestamp or `null` |
| Each round | Nonempty `label`, `matches` array (0–100) |
| Each match | Unique `id`, `homeTeam`, `awayTeam`, `kickoffAt`, `prediction`; previous matches also require `result` |
| Each team | `id` in `team_XXXX` form, nonempty `name`; home and away differ |
| `prediction` | `source: "saved_pre_match"`, `generatedAt` strictly before kickoff, `probabilities` |
| `probabilities` | Exactly `home`, `draw`, `away`: finite percentages in [0,100], sum within 0.02 of 100 |
| `result` | Exactly `homeScore`, `awayScore`: nonnegative JS-safe integers; forbidden for next matches |

Strings are bounded to 200 characters. Timestamps:
`YYYY-MM-DDTHH:mm:ss[.fraction]Z` or explicit `±HH:mm` offset. Invalid input stops
startup or UI; no automatic demo/research fallback. GET routes are an explicit
static-asset/API allowlist, not a directory server. Arbitrary repository/model/
data/test files are not served.

The server's schema validator checks shape and asserted provenance, not independent
source identity. The adapter performs the additional source/binding checks below.
A hand-edited JSON tag is not proof of saved-prediction provenance.

## Champion-only display feed adapter (awaiting review)

`scripts/build_dashboard_feed.py` is a projection/export component, not a model.
Implementation and tests use temporary synthetic data only. Real feed generation
requires a separately reviewed/authorized task; do not run the production command
as part of implementation validation.

Fixed inputs relative to the repository:

- `data/processed/predictions/season_transition_st2_prospective.csv`
- `data/processed/predictions/2026_27_prediction_fixture_bindings.csv`
- Published revisions under `data/processed/jleague/2026_27/`
- `data/master/teams.csv`

The frozen comparison version is `season_transition_st2_vs_a_20261006_v1`.
Champion metadata must equal `operational_champion_20260922_v1` and artifact hash
`2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1`.
No model artifact is opened. The mixed CSV's current two-row digest is deliberately
not pinned: the same frozen schema may receive future complete-date appends.

Champion allowlist, applied while parsing and **before any result join**:

```text
fixture_key, match_id, match_date, kickoff,
home_team_id, away_team_id, home_team_name, away_team_name,
prediction_generated_at, source_revision,
champion_a_model_version, champion_a_artifact_hash,
a_p_away, a_p_draw, a_p_home
```

`comparison_version` is checked and discarded. All other mixed cells remain
opaque, including research probabilities/classes and Elo/class fields. They are
not converted into named columns or joined, logged, evaluated or exported.
Champion probabilities are finite 0..1 values summing to 1 within 1e-12; output
uses exactly `float(value) * 100` in HOME/DRAW/AWAY order, without rounding or
renormalization. The frontend computes AI PICK.

The common sidecar's exact schema and global uniqueness keys are checked. For the
requested artifact/version, every saved row needs exactly one matching binding;
missing, orphan, duplicate and conflicting identities stop the adapter. Coverage
of unrelated artifacts is not inferred by opening their research CSVs. Namespace,
witness revision and manifest SHA are verified against accepted witness data.
The witness can be older than the prediction's source revision; both must have
been observed before generation, and no later than the current publication.

`read_latest()` is reused for the accepted pointer, manifest and file hashes.
Additional gates validate publication/policy, the full 20-club/380-fixture/38-round
population, fixture identity projection, typed v2 IDs, completed subset equality,
score/result consistency, explicit official game-over provenance and evidence
timing. Candidate scores never become results. A v1 witness needs explicit
official page namespace evidence; v2 follows the typed identity contract.
Journal/lock presence stops the adapter; it never performs recovery.

For an ongoing-v1 witness only, an exactly blank pair of `evidence_sha256` and
`evidence_fetched_at_utc` is accepted on a scheduled/candidate row. This requires
an immutable published revision with matching sidecar witness ID/manifest SHA
and every manifested file hash; exact fixture_key, saved match ID, TeamMaster
home/away IDs, date and kickoff; `jleague_match_page` namespace; an allowed
`official_scheduled_identity`, `official_completion_unconfirmed` or
`official_game_over_section` evidence type; and the canonical J.League J1 page
URL whose ID exactly matches the saved prediction. Witness observation must be
no later than source observation, then saved generation, strictly before kickoff.
These existing identity/publication/chronology gates are not bypassed. This is
a URL-and-immutable-publication identity witness, not proof of fetched page-body
content: missing SHA/time are never invented, filled in, or persisted.

For v1, a partially blank pair always fails. With both fields present, SHA must
be 64 lowercase hex characters and fetched_at a timezone-qualified timestamp
no later than witness observed_at. The exception never applies to completed
rows. Existing ongoing-v2 typed identity/provenance validation and all completed
result game-over/SHA/time provenance checks are unchanged. Regression tests use
synthetic repositories only; real-data preflight and feed generation require a
separate authorized task.

Current official rows are joined **only by fixture_key**, not scalar match_id.
Each fixture is one-to-one and home/away TeamMaster IDs must agree. Output ID is
fixture_key, so a namespace transition does not change UI identity. Prediction
display names must be canonical or exact, date-valid registered aliases resolving
to their stated IDs; output uses canonical names. No fuzzy matching or guessed
correction. All saved fixtures are validated; unresolved IDs are not dropped.

Saved date batches must be complete against their prediction-source revision's
unfinished fixtures for that day, with one source revision/generation time per
batch. Selection then uses **current official calendar dates**: latest completed
date with saved predictions for previous, earliest unfinished predicted date for
next. Every saved eligible fixture on the selected day is included. A validated
official reschedule may change the displayed date/kickoff, never probabilities;
saved generation must still precede current kickoff. Unsaved fixtures are not
predicted or added. No eligible rows means an empty array, not demo fallback.
Date-based labels avoid guessing round numbers. `updatedAt` is the official
publication's observed_at, never adapter execution time.

Output is exactly the schema v1 above, revalidated with
`scripts.serve_dashboard.validate_dashboard_data()`. Only previous matches receive
official home/away scores. No aggregate metrics are computed. The CLI's errors
are generic and never echo mixed source cell values.

After separate production authorization, the entry point is
`python -m scripts.build_dashboard_feed`, with optional `--output PATH`.
Default output: `data/processed/dashboard/champion_home.json` (ignored, never
force-add). Build and validate the entire payload first, then write a temporary
file in the destination directory, flush, fsync and atomically replace. Failure
preserves the previous valid JSON and removes the owned temporary file. Protected
input/model directories cannot be CLI output destinations. To view a subsequently
approved feed, serve with `--data data/processed/dashboard/champion_home.json`.

## Validation

```powershell
node --test web/tests/probability-bar.test.mjs web/tests/dashboard.test.mjs
node --test web/tests/browser.test.mjs
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_server.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_feed.py tests/test_dashboard_server.py -q
.\.venv\Scripts\python.exe -m scripts.build_dashboard_feed --help
.\.venv\Scripts\python.exe -m scripts.serve_dashboard --help
git diff --check
```

Node 24 was used. Browser tests use installed Chrome/Edge in hidden headless mode,
synthetic local HTTP fixtures, no downloads or dependencies. Other platforms can
set `J1AI_BROWSER_PATH` to a local Chromium executable; absent a browser the suite
explicitly skips. `J1AI_SCREENSHOT_DIR` optionally saves demo screenshots to a
specified local directory (not required or committed). No production/model IO.

## Champion A scheduled updates (disabled by default)

`scripts/update_champion_dashboard.py` provides a separate operational lane. It
never runs the ST2 comparison predictor or changes research CSVs, evaluation data,
models, or original official revisions. Its source root is read-only; all fetched
observations, accepted publications, prediction batches, status, and display JSON
go into a separate runtime directory outside the source/code repositories.

The morning slot checks the official calendar and predicts the earliest unsaved
match date within `lookahead_days` (default 7). It requires the entire unfinished
date batch to be scheduled, identified, and still before kickoff. Later dates are
handled on later runs. Saved fixtures are skipped. The evening slot checks results
and rebuilds the display without inference. Both slots reuse the existing
official parser, immutable publisher, namespace/binding checks, game-over evidence
policy, and feed validator. Candidate scores never become completed results.

The independent Champion predictor verifies the five frozen artifact hashes and
training source hashes before deserialization. It replays the frozen training
manifest and approved regulation results with Champion's K=30/home advantage=175,
and only passes pre-match Elo difference to the saved scaler/estimator. It calls
`transform`/`predict_proba`, never `fit`. Same-day and future results are excluded.
New prediction CSVs contain only Champion columns and identity/provenance fields.

Predictions and bindings are committed together as a new, SHA-manifested batch
directory. Existing batches are never overwritten; changed hashes and duplicate
fixture keys stop updates. Publication validates the complete candidate feed
before committing predictions, then flushes/fsyncs and atomically replaces the
display JSON. A failure preserves the last good display. If a display write fails
after a prediction batch is saved, the next explicit update reads that batch
instead of predicting it again. Kickoff is checked again immediately before
saving. An exclusive `update.lock` rejects overlapping jobs. Abandoned locks and
incomplete initialization require inspection; they are never automatically cleared.

Each network request has the existing finite 30-second timeout, no automatic
retry, and at most `max_evidence_pages` (default 20) game-over page requests plus
one listing request per job. Only official page identities from the validated
publication/listing are used; Data Site IDs are never converted into guessed
match-page IDs. Missing page evidence can leave results as candidates. Conflicting
identities or a held publication stop the update and leave the display intact.
The current adapter supports the verified 2026/27 regular J1 season only.

An external config may supply `evidence_urls`, an explicit list of exact HTTPS
official J1 match-page URLs for 2026/2027. The default is an empty list. Wildcards,
queries, fragments, other hosts/competitions, malformed IDs and duplicate entries
are rejected. These URLs join already-known page URLs within the same total
`max_evidence_pages` limit; overlap is fetched once. No page ID is guessed or
enumerated. The existing snapshot parser/publisher verifies the fetched URL,
canonical, competition, date, round, home/away clubs, fixture key and separate
page/Data Site namespaces. A scheduled page can establish identity; only exact
candidate scores plus explicit game-over evidence establish completion. Operator
URLs do not bypass any publication or prediction-binding checks.

### Activation after reviewing the implementation

No real-data update or task registration is part of the synthetic development
checks. Before activation, select the actual read-only data/model source and a
new writable runtime outside every repository. Confirm the frozen artifacts,
Python >=3.12 environment/dependencies, official IDs, and available official page
evidence. Live network acquisition and the real frozen estimator have not been
executed by these synthetic checks.

1. Copy `config/dashboard-update.example.json` to an operator-owned path outside
   Git. Set `source_root` and `runtime_root`; keep `enabled: false` until activation
   is approved. The source must contain the accepted saved Champion projection,
   original binding sidecar, official revisions, their accepted raw snapshot,
   TeamMaster, and fixed artifacts. The accepted snapshot/run is copied with its
   original hashes into the new runtime so observation sequence and predecessor
   comparisons continue without resetting or rewriting source history.
   Times default to `07:00` / `22:00`, timezone `Asia/Tokyo`.
2. After approval, set `enabled: true`. From this code checkout, use the selected
   environment's Python for the first explicit update:

   ```powershell
   & $python -B -m scripts.update_champion_dashboard --config $config --slot morning
   ```

   Use `--slot evening` for results/display only. A nonzero exit means failure;
   inspect the runtime's status and retained acquisition/publication evidence.
   Do not repeatedly retry or clear locks without understanding the failure.
3. After a successful first update, start a separate loopback display server:

   ```powershell
   & $python -B -m scripts.serve_dashboard --port 0 --data "$runtime/view/champion_home.json" --reload --status "$runtime/view/update-status.json" --poll-seconds 60
   ```

   Open the URL it prints. Keep existing servers on 52453 and 51406 unchanged.
   The new screen polls every 60 seconds and offers **表示を再読込**. It shows the
   update state, last successful update time and official observation time.
   Reloading is GET-only: it cannot invoke acquisition, prediction, or training.
   Invalid/research-shaped JSON, stale publication rollback, and read failures
   preserve the last normal cards and show a safe error. Demo mode does not poll.
   Stop only this new console server with Ctrl+C.
4. Inspect the task plan first (this command registers nothing):

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/register_champion_update_tasks.ps1 -Config $config -Python $python
   ```

   This execution policy applies only to that PowerShell process; no persistent
   user/machine policy is changed. After approval, repeat with `-Register`. The two task names are
   `J1AI-Champion-Morning` and `J1AI-Champion-Evening`. Registration requires Windows
   local timezone **Tokyo Standard Time** and refuses existing task names.
   Tasks run as the current limited interactive user (login required), have a
   15-minute execution limit, ignore overlapping instances, start after a missed
   trigger when available, and configure no automatic failure retry. The shared
   runtime lock also prevents the morning/evening tasks from overlapping.
5. To change times, edit the external config and update the two corresponding
   triggers in Task Scheduler; changing config alone does not modify an already
   registered trigger. To pause, disable only these two tasks and set config
   `enabled: false`. Do not remove another task or process.

The existing real-data display remains a saved prediction snapshot until this new
runtime is explicitly connected. UI availability is not approval of Migration,
Native DashboardHost, WebView2/UDF, or Phase A/B. Phase A remains BLOCKED and
Phase B NOT_AUTHORIZED.

### Synthetic validation

```powershell
& $python -B -m pytest tests/test_champion_dashboard_update.py tests/test_dashboard_feed.py tests/test_dashboard_server.py -q -p no:cacheprovider
node --test web/tests/probability-bar.test.mjs web/tests/dashboard.test.mjs web/tests/browser.test.mjs
```

These checks use synthetic temporary inputs and estimator doubles. They cover
successful append/display, idempotence, source immutability, exclusive locks,
kickoff crossing, invalid probabilities/IDs/results, acquisition and inference
failure, pending transactions, immutable archive verification, Champion-only
prediction contracts, and real headless-browser polling/error preservation.
Task script parsing and plan-only execution do not register or run tasks.
