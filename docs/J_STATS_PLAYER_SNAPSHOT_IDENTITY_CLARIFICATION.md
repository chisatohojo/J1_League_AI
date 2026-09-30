# J Stats player snapshot identity clarification

Audit date: 2026-09-30 (JST)

## Verdict

**`DEFER_PLAYER_SNAPSHOT_IDENTITY`**

The bounded namespace evidence improved but did not satisfy the acceptance contract. Across the three saved 2026/27 ranking pages, every row with both a direct profile href and `legacyPlayerPhotoLookup.playerId` has exactly the same numeric ID: 1,110/1,110 agreements and zero mismatches. The five remaining embedded candidates each return HTTP 200 at the already-observed official `/player/{numeric_id}/` route and expose an exact matching canonical URL. However, all five retained HTML responses contain only the player-profile skeleton and generic metadata. They expose no player-specific displayed name, club field, career/history identity, or player-specific Data Site relation. A canonical route alone does not prove that the ranking candidate and a displayed official person identity are the same.

Consequently, zero of five candidates are promoted to `VERIFIED_EMBEDDED_PLAYER_ID`. No production collector, manual alias, player crosswalk, feature, prediction, model fit, or metric evaluation was created.

## Existing ranking namespace consistency

The saved `score`, `distance`, and `time` raw pages from the prior audit were re-read offline. For each row, the direct href ID was compared with the independently embedded photo-lookup ID before any profile request.

| stat | rows | direct href rows | exact href/photo agreement | mismatch | duplicate candidate | conflicting name | conflicting club |
|---|---:|---:|---:|---:|---:|---:|---:|
| `score` | 130 | 128 | 128 | 0 | 0 | 0 | 0 |
| `distance` | 496 | 491 | 491 | 0 | 0 | 0 | 0 |
| `time` | 496 | 491 | 491 | 0 | 0 | 0 | 0 |
| **total** | **1,122** | **1,110** | **1,110** | **0** | **0** | **0** | **0** |

This proves that the two numeric fields use the same values for all directly linked sampled rows. It does not by itself prove that the photo-lookup field is an official person identity when the direct href is absent.

## Bounded official profile verification

Only the five source-provided candidates were requested. The URL shape was not invented: `/player/{numeric_id}/` was observed directly in 1,110 ranking rows. Each candidate received exactly one direct GET with no retry and no redirect following.

| candidate | ranking raw name | ranking club | HTTP / redirects | requested and final official route | canonical ID | player-specific name / club | result |
|---:|---|---|---|---|---:|---|---|
| `1300872` | 中山 雄太 | `machida` | 200 / 0 | `/player/1300872/` | `1300872` | absent / absent | `UNVERIFIED_MISSING_PROFILE_IDENTITY_FIELDS` |
| `1618852` | 福田 心之助 | `kyoto` | 200 / 0 | `/player/1618852/` | `1618852` | absent / absent | `UNVERIFIED_MISSING_PROFILE_IDENTITY_FIELDS` |
| `1644969` | 名和田 我空 | `gosaka` | 200 / 0 | `/player/1644969/` | `1644969` | absent / absent | `UNVERIFIED_MISSING_PROFILE_IDENTITY_FIELDS` |
| `1100304` | 奈良 竜樹 | `fukuoka` | 200 / 0 | `/player/1100304/` | `1100304` | absent / absent | `UNVERIFIED_MISSING_PROFILE_IDENTITY_FIELDS` |
| `1642070` | 髙橋 仁胡 | `cosaka` | 200 / 0 | `/player/1642070/` | `1642070` | absent / absent | `UNVERIFIED_MISSING_PROFILE_IDENTITY_FIELDS` |

All responses were `text/html; charset=utf-8` from `www.jleague.jp`. Their canonical numeric IDs match the candidates, but the title and Open Graph metadata are generic J.LEAGUE values. The `p-player-profile` area contains skeleton blocks rather than person fields. Exact ranking names occur zero times in the corresponding response bodies. Club names elsewhere in site-wide navigation/footer are not profile-club evidence and were not used.

The only Data Site relation found in the profile HTML is the same generic `https://data.j-league.or.jp/SFTP01/` records link on every page. There is no person-specific Data Site URL, `player_id=` parameter, career identity, or same-ID corroboration in the retained responses. No guessed Data Site ID, name search, hidden endpoint, client API, or third-party result was used.

## Request and raw-evidence contract

Official profile GET count: **5**. Automatic retries: **0**. Additional player/profile searches: **0**.

Raw HTML, response headers, retrieval timestamps, byte counts, SHA-256 values, candidate IDs, ranking names, ranking club slugs, and identity outcomes are retained in the ignored research area:

`data/raw/research/jstats_player_identity_clarification/20260930T1118588904751Z/`

This directory is research evidence, not a player snapshot and not a production registry entry.

## Identity-source contract

The current safe states are:

- `DIRECT_PROFILE_LINK`: ranking row directly contains `/player/{id}/`, the ID is numeric, and it equals the row's photo-lookup ID.
- `UNVERIFIED_NO_DIRECT_PROFILE_LINK`: a numeric photo-lookup candidate exists but no direct profile href or independently verified official person identity is available.
- `VERIFIED_EMBEDDED_PLAYER_ID`: reserved for a future candidate whose official profile response supplies the exact candidate ID plus person-specific identity evidence. It is **not assigned by this audit**.

Names are retained as raw source observations. Name equality, NFKC, fuzzy matching, shirt number, or current club can never create a player identity. If a future official profile shows a different display name under the same verified numeric identity, both raw names must be retained and the difference audited; neither string is normalized into the other.

Club identity remains independent. The ranking pages have exact TeamMaster `jleague_official` mapping for all 1,122 rows and no same-state player/club conflict. The profile responses do not expose usable player-club identity, so ranking club identity cannot be claimed as profile corroboration.

## Acceptance-contract result

| condition | result |
|---|---|
| direct href ID equals photo ID for 100% of directly linked rows | PASS: 1,110/1,110 |
| mismatch equals zero | PASS |
| all five candidates resolve to an official person profile | **FAIL: canonical route only; person fields 0/5** |
| profile numeric identity equals candidate | PARTIAL: canonical ID 5/5, displayed person identity absent |
| profile identity does not conflict with ranking person | **NOT ESTABLISHED** |
| duplicate/conflicting candidate absent | PASS |
| same source state has no player ID with conflicting club | PASS in the three sampled rankings |

Because required identity conditions are not all satisfied, the embedded photo ID namespace is not approved as the snapshot `player_id`.

## Transfer and multi-club fail-closed rule

No current sampled candidate appears under multiple clubs. Future snapshot specification must still group by `(snapshot_id, player_id)` before publication. If one player ID has more than one club in the same source state, every affected row is quarantined as:

`AMBIGUOUS_MULTI_CLUB_PLAYER_STATE`

The system must not select a current club, merge values, sum rows, or deduplicate automatically. A separate source-semantics audit is required before release. Conflicting names for one numeric candidate similarly fail closed as `CONFLICTING_PLAYER_IDENTITY`.

## Ranking missingness

A future `time` capture, if ever authorized, represents only:

**official ranking rows observed at that point in time**

It is not a complete roster snapshot. A player absent from the ranking has `NOT_OBSERVED_IN_RANKING` semantics, not zero minutes, inactive, unregistered, or unavailable. No synthetic zero row may be created.

## Recommended first family and next gate

There is no authorized production family while identity remains deferred. Conditional on later identity approval, `time` remains the first specification candidate because it is an official UI route with clear cumulative-minute units, 496 observed rows, no null values, one source-state contract, and the broadest sampled coverage. Predictive usefulness is not part of this choice.

The exact next gate is official, player-specific identity evidence for all five embedded candidates: either a direct ranking href in a later source state, a profile response that includes the candidate numeric ID with displayed person/club identity, or an official documented contract explicitly defining `legacyPlayerPhotoLookup.playerId` as the same stable profile namespace. A future audit must use direct official evidence, rerun all conflict checks, and reach 5/5 verified before a collector specification can proceed.
