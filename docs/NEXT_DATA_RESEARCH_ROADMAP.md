# Next data research roadmap (2026-09-20)

## Starting point and evaluation discipline

The project is in a **new information layer / data platform** phase. Model A (Elo-only Logistic) remains the frozen Champion/reference and Model B (Elo + Domestic Competitive Rest) the frozen Challenger. The 2020–2024 OOF cycle is closed to repeated one-feature searches. The 2025 test is spent, and the first 70 completed 2026/27 ordinary J1 matches are an opened interim lockbox. Neither may be used to select or tune a new feature. The reported 70-match result does not change the frozen specifications; a completed 380-match evaluation is a later fixed-specification check.

The strictly-prior ordinary-J1 team draw-propensity dataset is materialized at
**`READY_TO_FREEZE_DRAW_PROPENSITY_EVALUATION`**. Its 3,208-row, 21-column
artifact reuses existing form output, adds only current-season draw state, and
fixes four symmetric candidates under SHA-256
`97b33269a11b62f94dbd4b83924b97cc1cb1cb250ae0eb636ca5d8ccc6ba36a5`.
No model evaluation has run. A separate one-time evaluation contract is the
next gate; 2025 and the opened 2026/27 results remain prohibited.

New sources should be acquired in a separate research cycle. Before any model experiment, record source terms, match/team identity, raw evidence, **observation timestamp**, revision behavior, availability time relative to kickoff, coverage and missingness by season, and a deterministic history-only feature contract. Preserve cumulative point-in-time snapshots for future validation. Evaluate coherent feature groups once under a newly declared validation protocol, without treating the opened lockbox as a search target. No performance gain is assumed below.

## Ranked source and feature investigations

| Priority | Source / feature group | Concrete feasibility question and next artifact | Point-in-time and identity gate |
|---:|---|---|---|
| 1 | J Stats **team cumulative snapshots**: fixed 37-stat prospective archive | The official 20-club ranking pages now have an append-only BASE_10/FULL_37 collector and a read-only integrity registry. Continue bounded FULL_37 captures after the official displayed update date advances; retain physical retrievals even when the displayed source date is unchanged. | These are cumulative observations, not reconstructed match rows or model features. A logical state requires one known source date, exact 37-stat/20-team identity, immutable raw hashes, and pre-target retrieval. Production match-level suitability remains A=0. |
| 2 | J Stats **player cumulative snapshots**: minutes, starts, goals, assists, xG, passing/defence, distance/sprints | The bounded current 2026/27 audit found complete embedded rankings for `score`, `distance`, and UI-confirmed `time`. Direct href/photo IDs agree 1,110/1,110, but the five remaining candidate routes return profile skeletons without person-specific identity fields. Status remains `DEFER_PLAYER_SNAPSHOT_IDENTITY`; no collector is authorized. | Exact TeamMaster club identity passed for all 1,122 ranking rows. Canonical player routes alone do not verify the five embedded candidates; require 5/5 official person identities before specification. Future same-state multi-club IDs are quarantined, and ranking absence is never zero. |
| 3 | SFMS02 **player minutes reconstruction** from Starting XI plus substitutions | On a small set of cached matches, establish starter/substitute entry/exit semantics, stoppage-time notation and complete minutes accounting. Then assess `minutes_last_7d`, `minutes_last_14d`, `starts_last_5`, consecutive starts, days since appearance and rotation load. | Require a deterministic short-term player identity policy and a publication-time rule. Current XI audit has 6,416/6,416 eleven-player lineups but no stable official player ID; minutes must not be attributed across uncertain identities. |
| 4 | Suspensions | Check official discipline rules, card carry-over, suspension announcements and player registration identity. Candidate group: suspended player/starter count and suspended minutes or goal/xG share, where underlying player data are reliable. | Suspension must be officially knowable before kickoff; match cards alone do not prove eligibility for the next match. |
| 5 | Match events | Audit official event rows for cards, goals, substitution timing, first goal, lead preservation and comebacks. Define a typed event schema and check 2015/2019/2024 samples before broad collection. | These are post-match observations and may enter only later-match histories. Regulation-time versus extra-time/PK semantics must remain explicit. |
| 6 | Referee history | Establish whether referee assignment and cards/fouls are available with an official timestamp. Candidate group: lagged referee profile, only if assignment is announced early enough. | Do not use the referee assigned after the prediction timestamp or current-match officiating statistics. |
| 7 | Schedule, stadium and travel | First audit kickoff datetime, weekday, home/alternate venue, team travel coordinates, recent distance and consecutive away fixtures. Distinguish venue identity from club identity and known schedule from later rescheduling. | Compute from the schedule known at the chosen prediction timestamp; a finalized historical fixture list can contain future corrections. |
| 8 | Weather | Determine whether archived forecasts **issued before kickoff** exist for the stadium/time; define forecast lead time and location. | Do not substitute realized match-day weather as if it were a historical pre-match forecast. |
| 9 | AFC Rest / Travel | Explore an official lightweight Japanese-club fixture stream containing club, match datetime and venue. Full results are unnecessary for rest/travel, provided coverage can be checked. | 2015–2024 delivery is mixed: legacy reports, archives, PDFs and derived keys. Resolve same-day/venue/team identity and completeness without inventing match IDs. AFC is not in frozen Domestic Rest. |
| 10 | Injury, roster and transfers | Audit official dated injury notices, registration/transfer records, prior-season minutes retained and squad continuity. Record whether historical announcements have stable player identity and effective dates. | Use the announcement/registration state actually known before prediction, not a later corrected roster or retrospective injury list. |

## Separate blocked source paths

- FootyStats historical xG has match-level promise but no verified full 2015/2019/2024 coverage, methodology consistency or approved free bulk path; investigate a licensed CSV/API sample before any collector.
- SofaScore historical lineup/rating/minutes lacks a confirmed official public structured path and sample-level player-ID coverage; investigate rights and source access first.
- J.LEAGUE.jp 2024 match stats HTML/RSC showed `0`/`0%` placeholder candidates. A browser request trace or official documented feed is needed to establish final values.
- The immutable 145-row J1–J2 Cup bridge regulation dataset remains provenance-complete and reusable as data. Its frozen formal Elo run was executed exactly once and returned **`CLOSE_CUP_BRIDGE_LANE`** (C−A pooled Log Loss `+0.0005008384174258751`, Brier `+0.0005719612389700757`, 2/5 folds improved). This model-research lane is closed; no tuning or adaptive follow-up is authorized.

## Order of work within a new cycle

1. Audit a small representative sample and legal/access conditions; do not start a broad crawl from a field label or season selector alone.
2. Define official identity, as-of timestamp, revision policy, match chronology and missing-data rules. Archive raw evidence and metadata.
3. Validate a coherent feature group on a separately declared period with one pre-registered comparison. Preserve the current freeze and record all attempted groups, including unsuccessful ones.
4. Keep future point-in-time snapshots independent of the already opened 2026/27 first-70 lockbox. Any later full-season 380 evaluation must follow its frozen protocol and cannot be used to backfit source or feature choices.

The interim evaluator's training count, same-date Elo replay and previous-target-match Domestic Rest history have now been audited and corrected; the current official 70-match result is recorded in [2026_27_INTERIM_LOCKBOX_EVALUATION.md](2026_27_INTERIM_LOCKBOX_EVALUATION.md). This was reproducibility work, not a new model research branch. Draw-class behavior (0/15 recall in the opened interim sample) is diagnostic only and may be revisited solely in a separate research cycle with new information layers, never by tuning on these 70 matches.
