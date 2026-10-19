# NN Phase 1.1: original-feature and final-result chronology

Research-only policy: `nn_original_kickoff_events_v1_1`.
No original CSV, production model, benchmark decision or operational data changes.
This phase permits audit/tests, not historical fit/evaluate/final-fit.

## Official evidence

The three explicitly supplied official URLs were retrieved into a separate local
evidence store. URL, UTC/JST retrieval time, status, body length and SHA-256 are in
`timing-v1_1/evidence-manifest.json`; raw HTML is not committed to GitHub.

- [SFMS02 official record, 30700](https://data.j-league.or.jp/SFMS02/?match_card_id=30700): original 2024-08-24 19:03 kickoff, interruption at halftime, November restart, final 1-1.
- [Official resumption announcement](https://www.jleague.jp/news/article/28819/): second-half restart on 2024-11-22 at 19:00 with Urawa leading 1-0.
- [Official match page](https://www.jleague.jp/match/j1/2024/112201/lineup/): Urawa/Kawasaki, round 28, November 22, finished 1-1.

The website route `2024/112201` is not the SFMS02 ID namespace. The research
fixture identity is `jleague_data_site_sfms02:30700`, TeamMaster home `team_0030`,
away `team_0010`, ordinary J1 2024, round 28. Identity, date, source kickoff and
final score/Draw must all agree; changed or ambiguous input stops processing.

These later records establish event chronology. They do **not** establish what
was published or corrected as of August 24. No strict historical-publication
as-of claim is made.

## Two different events

| Item | ID30700 |
|---|---|
| Original kickoff / feature timestamp | 2024-08-24 19:03 JST |
| Conservative feature-history cutoff | 2024-08-24 00:00 JST |
| Allowed feature history | Completed ordinary-J1 results on dates before August 24 |
| Recorded source date | 2024-11-22, retained verbatim |
| Label | Final 90-minute Draw (1-1), not the halftime 1-0 |
| Result-effective timestamp | 2024-11-23 00:00 JST |

The next-day result timestamp is a conservative daily policy boundary after the
recorded final day, not a guessed final-whistle time. The same daily rule applies
to ordinary matches. Same-day results never enter a feature vector.

The event engine freezes all required features from then-effective history.
It separately applies each final result once when effective. Pending and
halftime results are absent from Elo and Form. A result event uses the Elo state
current at its completion boundary; it does not retroactively use August's
snapshot to update November's ratings. Last-five Form is ordered by completed
result events, across seasons. Ordering within a day is stable by source date
and fixture ID. All feature/result events must be processed exactly once.

Source `match_date`, fixture identity, year/fold membership and all 3,588 rows are
retained. Only feature metadata/history eligibility for the registered fixture
is separated from that source date. There is no row exclusion or global date
shift. Event metadata must validate before this fixture can reach any model API.

## Other interruptions and fail-closed behavior

The frozen registry includes the one cross-date resumption and 13 individually
reviewed minute-scale interruptions in the ordinary-J1 cache. Those 13 retain
their ordinary daily policy; their specific IDs, note hashes, source date,
kickoff and cached raw-body hashes are fixed. A generic minute-count pattern is
not sufficient to admit a new interruption.

For all 3,588 source IDs, the audit reads cached official HTML and metadata only:
URL/namespace/ID, HTTP status, body size and SHA must agree. It recognizes the
verified remarks block and the verified empty-remarks template (last coach block,
legend, then match-information section). JavaScript session-replay commands are
not match evidence; visible unreviewed timing text is rejected. Missing/changed
reviewed notes, new timing cases, malformed/unknown templates, invalid remark
encoding, unknown temporal annotations or conflicting identity cause STOP.
There is no network fallback, ID guessing or automatic repair.

This is an audit of the pinned ordinary-J1 source/cache, not a claim that every
historical publication state or every undocumented real-world interruption can
be recovered from final tables alone.

## Fair comparison

The Elo-only Logistic, nine-feature Logistic and nine-feature MLP share the same
event-derived dataset. Only their declared feature subset/classifier differs.
The original hyperparameters, class order and expanding-window years are fixed.

The old frozen Champion A reference uses source-date features for 30700. Its
metrics must therefore not be an equality gate for this new research chronology.
Future metric deltas may be recorded as informational comparisons. No formal
benchmark value or Champion decision is rewritten, and no performance delta was
computed in Phase 1.1.

`audit-timing-v1_1/legacy-feature-delta.csv` records numerical feature differences;
`chronology-comparison.json` records their scope. The cache ledger and event table
are in that same audit directory. No historical learning/score inspection is
required for these chronology checks.

Phase A: BLOCKED. Phase B: NOT_AUTHORIZED.
