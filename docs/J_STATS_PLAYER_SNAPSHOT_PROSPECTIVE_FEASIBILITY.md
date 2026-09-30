# J Stats player snapshot prospective feasibility

Audit date: 2026-09-30 (JST)

## Verdict

**`DEFER_PLAYER_SNAPSHOT_IDENTITY`**

The current official 2026/27 J1 player ranking response is bounded and structurally suitable for prospective point-in-time capture: one HTML response contains the visible top 10 and the complete embedded ranking, every sampled club maps exactly to TeamMaster, and the three pages share one displayed update date. The stable-player-identity gate nevertheless fails. A direct numeric `/player/{id}/` profile link exists for 128/130 `score` rows and 491/496 `distance` and `time` rows, not every row. The remaining rows contain a numeric `legacyPlayerPhotoLookup.playerId`, but no direct profile URL. This audit does not assume that photo lookup identifier is a stable profile identity.

No production collector, feature dataset, player crosswalk, model fit, prediction, or metric evaluation was created. The existing team snapshot stream and opened lockbox were not changed.

## Scope and request discipline

The audit used only official J.LEAGUE.jp 2026/27 ordinary-J1 player pages linked or enumerated by the current player-stats UI:

| slug | official route | why inspected |
|---|---|---|
| `score` | `https://www.jleague.jp/j1/stats/player/2026-27/score/search-list/` | required count-type example and navigation discovery page |
| `distance` | `https://www.jleague.jp/j1/stats/player/2026-27/distance/search-list/` | required physical cumulative example |
| `time` | `https://www.jleague.jp/j1/stats/player/2026-27/time/search-list/` | official UI listed `time` as `出場時間`; no historical-route inference was used |

The `score` response's current 2026/27 filter data explicitly lists both `distance` and `time`, so the latter routes were acquired only after UI confirmation. No numeric player-ID probing, endpoint guessing, pagination crawl, club-filter crawl, third-party source, or historical backfill was performed.

There were exactly **3 direct official page GETs** for retained raw evidence: one per route, each HTTP 200, zero redirects, exact requested/final URL, and `text/html; charset=utf-8`. Earlier route discovery used three official-site search queries and two browser page opens; that research tool does not expose wire-level request counts and those operations are not represented as retained raw acquisitions.

Raw HTML, response headers, and a metadata/hash manifest are retained outside production snapshot directories at:

`data/raw/research/jstats_player_snapshot_feasibility/20260930T1045499012760Z/`

The research directory is ignored by Git. It is not a player snapshot and is not registered by the team snapshot registry.

## Page and complete-ranking structure

All three pages identify `2026/27`, J1, the exact stat slug/label, and `2026/9/21 更新`. The ordinary HTML initially renders ten `.m-ranking-player-list-item` rows. Those rows agree exactly on profile href, player name, and raw value with the first ten RSC records.

The same single page response contains the full `rankingList[0].data`. Its row count equals the page's `loadMore.max`; `loadMore` uses `end=10` and `step=10`, so “もっと見る” is client-side disclosure of already embedded records. No additional page, API, or load-more request is needed to obtain the audited ranking.

| stat | label / unit | rows = unique numeric candidates = `loadMore.max` | direct profile links | null / blank values | clubs | position distribution | observed value range |
|---|---|---:|---:|---:|---:|---|---|
| `score` | 得点ランキング / goals | 130 | 128 (98.46%) | 0 | 20 | DF 25, MF 49, FW 56 | 1–10 |
| `distance` | 総走行距離 / km | 496 | 491 (98.99%) | 0 | 20 | GK 31, DF 155, MF 195, FW 115 | 0.2–93.2 |
| `time` | 出場時間 / minutes | 496 | 491 (98.99%) | 0 | 20 | GK 31, DF 155, MF 195, FW 115 | 1–720 |

There are no exact duplicate `(player numeric candidate, club)` rows, no conflicting names for one numeric candidate, and no same candidate attached to multiple clubs within any page. The `distance` and `time` pages have exactly the same 496 player IDs and `(player ID, club)` pairs. Cross-stat comparison also found no player-ID/club conflict.

These findings establish complete extraction of the ranking returned by the source, not complete roster coverage. `score` has no zero row and starts at one. `time` and `distance` also have no zero row. An absent player must therefore remain missing; it must not be converted to zero minutes, zero goals, inactivity, or non-registration. The source sample does not prove whether the ranking includes every registered player or only players satisfying an appearance/value condition.

## Stable player identity

For rows with an href, the ranking row itself directly supplies one numeric `/player/{id}/` URL, and its ID agrees with `legacyPlayerPhotoLookup.playerId`. No row contains two conflicting numeric candidates.

The direct-link gaps are:

| numeric photo-lookup candidate | displayed player | club | affected sampled stats |
|---:|---|---|---|
| `1300872` | 中山 雄太 | 町田 | `score`, `distance`, `time` |
| `1618852` | 福田 心之助 | 京都 | `score`, `distance`, `time` |
| `1644969` | 名和田 我空 | G大阪 | `distance`, `time` |
| `1100304` | 奈良 竜樹 | 福岡 | `distance`, `time` |
| `1642070` | 髙橋 仁胡 | C大阪 | `distance`, `time` |

These records are retained by the prototype as `UNRESOLVED_NO_DIRECT_PROFILE_LINK`. Their numeric photo-lookup candidates are evidence, but are not promoted to exact official player identity. Name-only, shirt-number, fuzzy, NFKC, SFMS02, or current-club inference is forbidden.

No sampled ID appears in multiple club rows, so the current pages provide no positive transfer case from which to determine whether a transferred player's cumulative value follows the player, is split by club, or is assigned to the current club. The collector must preserve any future multi-club occurrence and stop for a semantics decision; it must not auto-deduplicate it.

## Club identity

Every one of the 1,122 sampled rows contains a club object with current official code, short display name, and full official name. For every row, `(club.code, club.fullName)` matches exactly one current `jleague_official` TeamMaster alias and resolves to the same permanent `team_id` on the audit date. Each page contains all 20 schedule clubs. No out-of-scope or former J1 club, fuzzy match, Unicode fallback, or new manual alias was required.

Player identity and club identity were validated independently. Exact club mapping does not repair an unresolved player identity.

## Source-state semantics

All sampled pages displayed the same date, `2026-09-21`. The page states that J1 data is normally updated one to two days after a match. It exposes no exact source update time, revision ID, historical version selector, or as-of mechanism. `retrieved_at` must therefore remain separate from `source_updated_date_jst`; a displayed date must not be converted to midnight.

Any future point-in-time use would require the immutable raw observation to satisfy:

`snapshot.retrieved_at < future target kickoff`

A later retrieval must never be applied retrospectively to an earlier target, even when its displayed source date is earlier than or equal to that target date. Revisions can only be represented by retaining later physical observations; no official revision history was found.

## Candidate schema (not implemented)

A later specification may start from:

```text
snapshot_id
retrieved_at
source_updated_date_jst
competition
season
stat_name
stat_label
rank_raw
player_id
player_id_candidate_source
player_name_raw
position_raw
uniform_number_raw
club_team_id
official_club_name
official_club_slug
stat_value
raw_value
unit
source_url
player_profile_url
raw_sha256
identity_status
identity_reason
```

`player_id` must be null when exact profile identity is not established. A photo-lookup candidate may be retained separately with its source and `UNRESOLVED_NO_DIRECT_PROFILE_LINK`; it must not silently become the key. Missing ranking rows remain absent, not synthetic zero rows.

## Recommended first stat family

There is **no authorized first production profile while identity is deferred**. If the identity gate is later resolved, the recommended first bounded family is `time` (出場時間): the UI explicitly exposes it for 2026/27, its unit and cumulative interpretation are the clearest of the three samples, it has no null values, its 496-row embedded coverage is substantially broader than the positive-goal ranking, and its complete response agrees exactly with `loadMore.max`. This recommendation is based only on source semantics, not predictive usefulness.

`time` still does not prove complete registered-roster coverage, and absent rows must remain missing. It also does not authorize workload features, SFMS02 joins, or retrospective player history.

## Prototype boundary

`src/collect/jstats_player_snapshot_prototype.py` is an offline-only strict parser. It has no HTTP client, retry loop, processed-data writer, model dependency, or production snapshot path. It validates season/category/stat identity, displayed date, complete embedded count, visible/embedded agreement, numeric values, direct player profile IDs, position syntax, and exact current-J1 TeamMaster club identity. Fixture tests fail closed on conflicting IDs, out-of-scope clubs, and visible/RSC disagreement.

## Limitations and exact next gate

- Only three representative current pages were inspected; no all-stat crawl was performed.
- Ranking completeness means complete source-response extraction, not complete roster enumeration.
- The official update time, revision history, and transfer aggregation semantics remain unavailable.
- J.LEAGUE.jp player IDs were not joined to Data Site IDs or SFMS02 names.
- No historical point-in-time player snapshot was inferred or reconstructed.

The next gate is an official-source identity clarification or later bounded source state in which every ranking row directly exposes a numeric profile URL, or an official contract proving that the embedded photo-lookup ID is the same stable player-profile namespace. Then rerun the same bounded audit and require 100% direct identity coverage, zero conflicts, exact club identity, explicit transfer handling, and immutable pre-target timestamp rules before writing a collector specification.
