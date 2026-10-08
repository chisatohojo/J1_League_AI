# J1AI home dashboard

## Scope and source boundary

The repository had no frontend or design system. `web/` adds dependency-free
HTML/CSS/JavaScript with native ES modules and Node's built-in test runner.
No framework migration or npm install is needed. `scripts/serve_dashboard.py`
uses only Python's standard library.

This implementation does not load models, regenerate predictions, export CSVs,
join outcomes, collect data, or execute evaluations. Existing data, artifacts,
prediction identity sidecars, research protocols, and model/evaluation code are
unchanged.

There is currently **no dedicated saved Champion-only prediction feed**. Existing
prospective CSVs belong to research lanes, even where they include Champion A
columns, and are not inputs to this UI. The default operational view is empty.
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

No production export is created in this task. The server validates/snapshots only
the specified JSON at startup; restart to load an updated export. It never searches
for data, reads research CSVs, or joins results. Source probabilities must already
have been saved before kickoff; extracting A from a mixed research artifact is
not an approved feed.

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

This schema validates shape and asserted provenance, **not** independent fixture
identity, TeamMaster membership, source hashes or result timing. The future
Champion-only export needs a separately approved adapter that validates saved
fixture provenance and completed-outcome identity before supplying data.
A hand-edited JSON tag is not proof of saved-prediction provenance.

## Validation

```powershell
node --test web/tests/probability-bar.test.mjs web/tests/dashboard.test.mjs
node --test web/tests/browser.test.mjs
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard_server.py -q
.\.venv\Scripts\python.exe -m scripts.serve_dashboard --help
git diff --check
```

Node 24 was used. Browser tests use installed Chrome/Edge in hidden headless mode,
synthetic local HTTP fixtures, no downloads or dependencies. Other platforms can
set `J1AI_BROWSER_PATH` to a local Chromium executable; absent a browser the suite
explicitly skips. `J1AI_SCREENSHOT_DIR` optionally saves demo screenshots to a
specified local directory (not required or committed). No production/model IO.

Remaining work: approved dedicated Champion-only feed/identity validation,
official color confirmation, and any separately requested production hosting.
