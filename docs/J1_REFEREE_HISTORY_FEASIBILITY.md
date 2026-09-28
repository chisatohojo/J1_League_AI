# J1 Referee History Feasibility Audit

## Verdict

`DEFER_REFEREE_ASSIGNMENT_PROVENANCE`

The local historical source is sufficient to retain an exact **display-name
label** for the main referee of every ordinary J1 match in 2015–2024.  It is
not sufficient to prove that the target-match referee assignment was publicly
known before kickoff.  A present-day final match page is retrospective evidence
only, not point-in-time (PIT) evidence.  No referee feature, collector, model
fit, prediction, metric, or feature selection was performed in this audit.

## Scope and method

- Scope: ordinary J1 only; calendar seasons 2015–2024 in the existing local
  cache, read-only.
- Local primary source: `data/raw/jleague_match_stats/{match_id}.html`, the
  official J.League Data Site `SFMS02` match-card cache and its verified
  metadata.
- Processed sources inspected: `jleague_match_stats` and the materialized
  `sfms02_match_events` dataset.  The latter remains a post-match event source.
- Identity infrastructure inspected: read-only `TeamMaster`.  It contains club
  aliases, not referee identities, and was not changed.
- External check: exactly six official J.LEAGUE Data Site pages, observed on
  2026-09-28 JST: four `SFMS01` ordinary-J1 season listings (2015, 2019, 2024,
  2026) and the current `SFIX08` / `SFIX09` referee-list pages.  No third-party
  source, ID enumeration, or broad crawl was used.

## A. Historical main-referee identity

The 2015–2024 ordinary-J1 scope is 3,208 matches (2015–2020: 306 each; 2021:
380; 2022–2023: 306 each; 2024: 380).  All 3,208 required raw HTML files and
metadata files were present and read without mutation.

| Audit item | Observation |
|---|---:|
| SFMS02 rows with a `主審` field | 3,208 / 3,208 |
| Blank/missing main-referee values | 0 |
| Main-referee values containing U+FFFD | 0 |
| Distinct exact raw main-referee strings | 57 |
| `主審` value containing a profile anchor | 0 |
| Official referee/staff ID in the match-card field | 0 |

The match card stores the main referee as a visible text value under `主審`; it
does not link that value to a referee profile.  The two current official list
pages inspected also exposed neither a `staff_id`-style identifier nor an
individual referee profile link.  Consequently the raw string can be preserved
as an opaque, exact source label, but it is **not** a verified stable referee
identity.  This audit did not trim, normalize, transliterate, fuzzy-match, or
manually merge names.  It therefore cannot rule out a future same-name collision
or prove that spelling changes denote the same person.

The existing processed match-stats schema contains only SH, CK, and FK and does
not retain a referee field.  The existing event schema contains no referee field
either.  They are therefore not a hidden alternative identity source.

## B. Pre-match assignment provenance

The official season-listing samples were fetched from the same bounded route:

- [2015 SFMS01](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2015&tv_relay_station_name=)
- [2019 SFMS01](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2019&tv_relay_station_name=)
- [2024 SFMS01](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2024&tv_relay_station_name=)
- [2026 SFMS01](https://data.j-league.or.jp/SFMS01/search?competition_frame_ids=1&competition_years=2026&tv_relay_station_name=)

| Sample | `主審` on listing | publication/update timestamp | historical as-of replay evidence |
|---|---|---|---|
| 2015 | absent | absent | absent |
| 2019 | absent | absent | absent |
| 2024 | absent | absent | absent |
| current 2026/27 route | absent | absent | absent |

The current 2026 route returned 80 completed match-card links, but no main
referee assignment in the listing.  The historical pages are likewise current
retrospective responses, not retained snapshots of their pre-kickoff state.
`SFMS02` supplies the referee only on the completed match card and its local
metadata records retrieval time, not an official assignment publication time.

The current official referee-list pages establish only a season-level pool of
officials.  They do not map an official to a particular fixture.  They cannot
establish a target assignment, its lead time, or a historical revision trail.
No inspected official page proves that a target fixture's referee was published
before its kickoff; none permits reconstruction of that historical as-of state.

Accordingly, final pages that show `主審` are explicitly rejected as PIT proof.
The audit does not infer that an assignment was unknown in reality; it records
that the required official, timestamped evidence was not found in this bounded
source check.

## C. Lagged profile feasibility, conditional on a future assignment source

Only after a stable referee identity and PIT-safe target assignment source are
separately established, the following completed-match history is source-level
feasible:

| Candidate historical input | Existing source status | Permitted interpretation |
|---|---|---|
| Prior officiated match count | SFMS02 `主審`, 3,208/3,208 | Exact raw-name label only; not a stable-person profile yet |
| Prior yellow cards | SFMS02 event A8, 7,671 rows / 2,838 matches | Post-match count; an A8-absent match is a source-observed zero |
| Prior red cards | SFMS02 event A9, 301 rows / 286 matches | Post-match count; an A9-absent match is a source-observed zero |
| Home/away outcome distribution | completed ordinary J1 match cache | Post-match result only |
| Fouls | not available | `FK` is free kicks, not fouls; no substitution or inference allowed |

The event dataset is `MATERIALIZED_AND_VALIDATED` for 3,208 source matches and
retains raw SHA-256/source-section provenance.  Its cards may support a future
lagged history, but they do not make the target-match referee assignment known
before kickoff.  No referee/card aggregation or feature dataset was produced.

## D. Candidate chronology contract for a later specification

This is a proposed safety contract, not an approved feature implementation.

1. Join a target only when an official source proves that its main-referee
   assignment was published before that target's kickoff, with the source URL,
   observed/published timestamp, raw SHA-256, and revision policy retained.
2. Build the referee history only from matches completed before the target
   kickoff.  The target match's cards, fouls, score, and result are prohibited.
3. If same-date kickoff order or completion order is unavailable, use
   conservative batching: expose no same-date completed match to another
   same-date target.
4. Preserve exact source labels until a stable official referee key is proven.
   Do not fuzzy-match or manually normalize names; fail closed on unresolved or
   ambiguous identity.
5. Treat missing cards only according to the validated SFMS02 section contract;
   do not manufacture fouls from free kicks or infer unavailable values.

## What would clear this defer gate

Before a referee feature specification, retain a small official pre-kickoff
assignment artifact for multiple seasons, including a timestamp that precedes
the named fixture's kickoff, stable fixture identity, assigned-main-referee
identity, raw payload/SHA-256, and a revision/as-of policy.  It must be possible
to distinguish an original assignment from a later correction or final-page
backfill.  Until then, the historical completed-match source is useful for
research only and is not approved for a predictive referee layer.
