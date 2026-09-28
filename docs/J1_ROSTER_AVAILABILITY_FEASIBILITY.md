# J1 roster / availability feasibility audit

## Verdict

**`DEFER_PLAYER_IDENTITY`**

J.LEAGUE Data Site has a stable-looking, official profile-level `player_id`, and
dated official registration-change and injury notices exist.  That does **not**
yet make an ordinary-J1 2015--2024 point-in-time player layer safe.  The
existing SFMS02 player/minutes history has no official player ID, and the
limited official roster evidence does not supply a complete, historical,
effective-dated roster with an exact, auditable link to those rows.  A raw name
must therefore not be promoted to a longitudinal player identity.

Secondary blockers are (a) no demonstrated historical full-roster snapshot or
effective timestamp for each target kickoff and (b) no complete, versioned
injury/return archive.  An absence notice is positive evidence about a noticed
player only; its absence is never evidence that another player was available.

This is a source feasibility audit, not a collector, roster history, feature,
model, prediction, or metric run.  It follows roadmap item 10 in
`docs/NEXT_DATA_RESEARCH_ROADMAP.md` and the identity constraints in
`docs/JLEAGUE_PLAYER_IDENTITY_FEASIBILITY.md`.

## Scope and method

- Ordinary J1; historical local cache inspected read-only for 2015--2024.
- External inspection was limited to the official J.LEAGUE / J.LEAGUE Data
  Site pages linked below, plus representative 2015, 2019, 2024, and current
  2026 samples.  No player or season crawl, guessed URL/API, third-party
  source, or raw-source retention was used.
- No raw was newly saved.  Consequently no retrieval artifact is claimed to
  preserve an historical as-of page state.
- “Known before kickoff” means a source record with a preserved publication
  instant preceding that kickoff.  A page merely observable now is not proof
  of its earlier state.

## A. Local repository evidence

### Existing match/player sources

| Source | Audited observation | Consequence |
| --- | --- | --- |
| SFMS02 A5/A6 lineup and minutes materialization | 3,208 ordinary-J1 matches and 115,468 player-match rows are available, but the parsed player field is `player_name_raw`; the existing identity audit found zero official player-ID/profile links in 70,576 A5 cells and the SFMS02 cache. | Match-local exact name is usable only inside its parsed context.  It is not a roster identity or cross-match identity. |
| `src/features/player_workload.py` | Deliberately keys its history as `(season, team_id, exact raw name)` and documents that it is J1-only, not a stable player identity or total workload. | It cannot be reused as registration, transfer, or player-level availability history. |
| `docs/JLEAGUE_STARTING_XI_AUDIT.md` | All 6,416 XIs are structurally complete, but 70,576 starting-player cells have no official ID/profile link; 509 raw names occur for multiple teams.  Starting XI itself is a post-match page, not a proven target pre-kickoff source. | Target lineup/participation is unavailable for this lane and must not be used. |
| Previous-season J Stats | Existing profile artifacts are season-final team statistics; the historical in-season snapshot route was not established.  They are team profiles, not a player registration ledger. | They cannot reconstruct who was registered at a past kickoff or retained-player share. |
| `TeamMaster` | Exact, dated aliases resolve clubs only.  It has no player records, player aliases, or player-ID namespace crosswalk. | No TeamMaster change is appropriate or sufficient for this blocker. |

The identity audit also established official-ID-confirmed name collisions (for
example two distinct `セルジーニョ` profiles and two distinct `松田　陸`
profiles).  It found 22 same-name/date/different-team player registrations.
Thus raw name, whitespace/NFKC normalization, shirt number, current club, or
manual inference must not identify a person.

## B. Official roster / registration evidence

### Representative official samples

| Season/sample | Official evidence | What it proves | What it does not prove |
| --- | --- | --- | --- |
| 2015 | [2015-08-07 registration additions/changes/deletions](https://aboutj.jleague.jp/corporate/pressrelease/article/7966) | A dated J.LEAGUE release lists J1 additions, including club, shirt number, name, biographical fields and previous club. | The displayed release has no official player ID, complete roster baseline, effective timestamp, later-correction history, or full club-season state. |
| 2019 | [2019-03-15 registration additions/changes/deletions](https://aboutj.jleague.jp/corporate/pressrelease/article/11021) | A dated official change record exists and is explicitly partitioned by competition and club. | It is a delta, not a complete as-of roster.  No official player ID/effective instant is displayed. |
| 2024 | [2024-03-15 registration additions/changes/deletions](https://aboutj.jleague.jp/corporate/pressrelease/article/14945) and [2024 registration-window notice](https://www.jleague.jp/news/article/27070/) | The release contains additions and deletions, while the window notice gives season-level permitted periods. | A permitted window is not evidence that an individual registration was effective at a particular kickoff.  Neither page supplies a complete historical roster or a stable player ID. |
| Current 2026/27 context | [Data Site SFIX02 registration-player list](https://data.j-league.or.jp/SFIX02/search?lang=ja&selectValue=1&selectValueTeam=10) and [2026 special-season registration rule notice](https://www.jleague.jp/news/article/31575/) | A current roster route and current rules are publicly visible. | The current route is not a retained 2015/2019/2024 snapshot or an historical as-of replay mechanism.  Current display must not be projected backward. |

The Data Site [SFIX04 profile sample](https://data.j-league.or.jp/SFIX04/?player_id=11446)
does provide a numeric Data Site `player_id`; existing audit evidence shows it
can remain on one profile across clubs/seasons.  That is useful
profile-level identity evidence, not a historic registration record: the
displayed annual appearance rows do not enumerate zero-appearance registrants,
full in/out intervals, or all raw SFMS02 aliases.

J.LEAGUE.jp profile URLs use a separate numeric namespace.  In the absence of
an official crosswalk, the two namespace values must remain distinct.  No
name-based bridge is permitted.

### Historical PIT result

The limited official releases demonstrate *some dated changes*, but no source
in this audit demonstrates all of the following for every club/target:

1. a complete roster baseline before the target;
2. every addition, deletion, loan/transfer and correction through target
   kickoff;
3. an explicit individual effective date/time (rather than a publication date
   or registration-window rule);
4. a preserved historical page/version as it existed before kickoff; and
5. an exact official player-ID linkage to historical SFMS02 rows.

Accordingly, historical roster PIT availability is **not established**.  A
present-day roster or profile cannot fill any missing interval.

## C. Injury / availability evidence

### Representative official samples

| Season/sample | Official evidence | Positive evidence available | Unresolved safety issue |
| --- | --- | --- | --- |
| 2019 | [Cerezo injury notice, 2019-07-14 15:42](https://www.jleague.jp/news/article/14995/) | Club announcement date/time, named players, injury details and estimated recovery periods. | No official player ID in the notice; no demonstrated complete club archive, return record, revision history, or preserved historical as-of state. |
| 2024 | [Sapporo injury notice, 2024-09-28 17:10](https://www.jleague.jp/news/article/28975/) | Club announcement date/time, named players and diagnosis are published by J.LEAGUE.jp. | It reports a subset of announced injuries, not the entire unavailable/available roster; no return status or archive completeness is established. |
| Current 2026/27 | [Kashima injury notice, 2026-07-21 19:00](https://www.jleague.jp/news/article/34474/) | A current official timestamped, player-named injury report exists. | It supports a *prospective capture* possibility only if captured and frozen before a target kickoff; it does not reconstruct historical state. |

The pages show that official announcements can carry a publication timestamp
and sometimes an expected absence period.  They do not establish a uniform
schema, `updated_at`/revision log, official player identifier, match-specific
unavailability designation, recovery/return announcement, or full coverage
across all clubs and seasons.  The originating club pages linked by the league
are club-specific and were not crawled; their archive completeness is therefore
unknown, not assumed.

**Injury archive / completeness verdict: deferred.**  An announcement may be
retained as `officially_notified_unavailable` only after its own exact identity
and pre-kickoff publication instant are verified.  Missing announcement means
`unknown`, never `healthy`, zero unavailable players, or available minutes.

## D. Identity gate

The source evidence improves neither of the two required production joins:

1. **Roster record -> stable person:** Data Site profile IDs are official and
   may be transfer-stable, but the sampled dated roster-change releases expose
   names/shirt numbers rather than those IDs.  J.LEAGUE.jp and Data Site IDs
   are separate namespaces without a confirmed official crosswalk.
2. **Stable person -> SFMS02 historical rows:** SFMS02 contains no official
   player ID and the required complete, effective-dated historical official
   roster has not been established.  Exact string equality alone still leaves
   known collisions, alias changes, and transfers unresolved.

Result: **stable player identity remains deferred for this use.**  Do not
create a durable ID from a raw name, normalize names, infer from squad number,
or infer prior affiliation from the current profile/club.

## E. Future contracts, conditional on a new source audit

### Minimum roster/transfer record

Each retained official record would need at least:

`source_namespace`, `official_player_id`, `official_club_id`, `season`,
`registration_status`, `effective_at` (null if not explicit), `published_at`,
`updated_at` (null if absent), `retrieved_at`, `source_url`, `raw_sha256`, and
an auditable snapshot/version identifier.  Data Site and J.LEAGUE.jp IDs must
be stored in their native namespaces.  A record is person-feature eligible
only with an exact official ID and exact club identity; `unresolved` and
`ambiguous` must remain explicit states.

For a target kickoff `T`, use only a record whose original publication/capture
is before `T`, whose effective time is explicitly known to be no later than
`T`, and whose later correction is not projected back.  If timing or current
state is unknown, preserve unknown; do not synthesize an interval.

### Conditional squad-continuity candidates

Only after the roster contract and identity gate pass, possible source-level
candidates are: registered squad size, exact-ID retained-player count,
exact-ID incoming/outgoing count, and prior-season minutes retained share.
The last candidate additionally requires a safe historical player/minutes
identity join.  No values were calculated here; target lineup, participation,
result, and post-match information remain prohibited.

### Conditional availability candidates

Only after the injury contract and identity gate pass, retain a three-state
coverage model rather than a health assumption:

- `officially_notified_unavailable`: a timestamped, exact-ID notice before
  target kickoff;
- `unknown`: no complete status evidence, including no notice; and
- `resolved_not_unavailable`: only an explicit, timestamped official return or
  availability record, never inferred from silence or later participation.

Possible derived fields (not implemented) could then include count of
officially-notified unavailable players, previous-starter count, and prior
minutes share, each accompanied by identity/coverage denominators and unknown
counts.  These are not zero-filled substitutes for unknown state.

## F. Point-in-time rules for any later implementation

1. Compare source publication/retrieval timestamp with target kickoff; use only
   evidence available before target kickoff.
2. Preserve raw source, URL, retrieval timestamp and SHA-256 when collecting;
   retain `updated_at` or version evidence when the publisher exposes it.
3. Do not retrospectively apply later corrections, current rosters, current
   club affiliation, estimated transfer dates, or observed target participation.
4. Do not use target lineup, result, cards, minutes, or post-match reports.
5. Require exact official player identity before a person-level aggregation;
   leave no-ID, ambiguous and collision records unresolved.
6. Treat all missing injury/availability evidence as unknown.  No announcement
   is not a fitness assertion.

## Exit criteria

Move to a roster/availability feature specification only after a bounded,
official-source audit can demonstrate a reproducible historical snapshot or
versioned ledger covering complete rosters and effective dates, an official
crosswalk or exact-ID roster-to-SFMS02 linkage policy with measured coverage,
and a versioned injury/return archive whose missingness is retained.  Until
then, do not build a production collector or feature layer.
