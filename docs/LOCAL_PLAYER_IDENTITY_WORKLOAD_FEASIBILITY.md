# Conservative local player identity for J1 workload: feasibility audit

Audit date: 2026-09-21. This is an **offline, read-only feasibility audit**, not a player master, feature dataset, prediction, or model evaluation. Input: `data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv` (2015–2024 ordinary J1 only). See `SFMS02_PLAYER_MINUTES_DATASET.md` for minute semantics and `JLEAGUE_PLAYER_IDENTITY_FEASIBILITY.md` for why official-ID-based longitudinal linkage remains unavailable. Web requests: **0**.

## Identity definition and safety boundary

The candidate `local_player_key` is the exact tuple **`(season, team_id, player_name_raw)`**. The raw string is not trimmed, normalized, fuzzily matched, or inferred from a shirt number. A change of team or season always starts a new key and discards the previous key's history, even if the display name is identical. This is deliberately narrower than real-person identity. It avoids cross-team and cross-season false merges, but cannot prove that two people with the same exact name within one team-season are distinct. A changed display name within the same team-season would instead split one person into two keys.

The 115,468 input rows are **listed matchday-squad player rows**, not 115,468 distinct people. They form 5,731 local keys across 3,208 matches and 6,416 team-match squads. There are 70,576 starter rows, 94,214 rows classified as having played (`appearance_type != unused_substitute`), and 21,254 unused-substitute rows. “Played” includes the 1,483 substitute appearances assigned zero *normalized* minutes by the documented 90-minute cap; it is not equivalent to `minutes_played_normalized > 0`.

## Same-team/same-season collision audit

| Check | Observed |
| --- | ---: |
| Duplicate `(match_id, team_id, player_name_raw)` rows | 0 |
| Same raw name in starter and bench for the same match/team | 0 (covered by the duplicate key check) |
| Team-match squads / squads with other than 11 starters | 6,416 / 0 |
| One team appearing in multiple J1 matches on one date | 0 |
| Missing raw names / minutes outside 0–90 / unused substitutes with positive minutes | 0 / 0 / 0 |
| Local keys with more than one observed shirt number in cached SFMS02 lineup cells | 3 / 5,731 |

The three number-change candidates are 2015 `team_0011` 東　隼也 (36/40), 2018 `team_0029` 趙　東建 (19/9), and 2018 `team_0011` 三田　啓貴 (7/8). Renumbering is possible; neither a number change nor its absence proves a collision or a stable identity. The existing minutes collector separately rejects impossible active-state transitions, unpaired substitutions, and duplicate match-local player rows, and checks team-minute conservation. This audit found **no observable same-team/same-season collision**, but the data has no official player ID with which to certify there are none. In particular, two namesakes taking turns across matches would not be detected by the within-match duplicate check.

## Cross-team and season resets

There are **142 `(season, raw name)` keys** (125 distinct raw strings) observed with more than one team in the same season. The prior identity audit also found **22 same-date/multiple-team name keys across four raw names**. Some are demonstrably different people; neither the 142 nor the 22 is a transfer count. They remain separate because `team_id` is part of the key. A same-date occurrence is not used as earlier history.

For a conservative *upper-bound diagnostic* of transfer information loss, 140 new team-local keys had the same exact raw name at another team on a **strictly earlier date in that season**. At those keys' first, second, and third squad rows, a previously played other-team row within 7/14/30 days existed as follows. These counts are **not confirmed transfers** and no other-team history is actually linked or used:

| New-team squad row | Candidate keys/rows | Other-team played history within 7d | Within 14d | Within 30d |
| --- | ---: | ---: | ---: | ---: |
| First | 140 | 15 | 29 | 54 |
| Second | 140 | 0 | 11 | 41 |
| Third | 140 | 0 | 1 | 24 |

These candidate comparisons refer to prior other-team appearances known before the new key's **first** date. They measure possible information forfeited by the reset, not loss of confirmed person-level history, and do not claim that other-team entries later in the season can be joined safely.

There are 5,731 first squad rows of local keys. For **3,115** of them, the same team and exact raw name appeared in an earlier season, but the year is intentionally not linked. Checking earlier-season *played* rows, **zero** were within the 7-, 14-, or 30-day window of those new-season rows in this J1 dataset. Thus the conservative season reset causes **no observed direct 7/14/30-day window-history loss across a season boundary** in these records; it can still affect longer lookbacks, starts-last-N, days-since-last-appearance, and interpretation of an offseason. Same-name recurrence is not proof of person continuity.

## Pre-match short-window history coverage

For each listed target player row, the audit checked whether that same local key had **at least one played row in a strictly earlier J1 match date**, with date difference in `[1, N]` days for N = 7, 14, 30. All rows on a date were queried against state from earlier dates and only then added as a batch. Sorting within a date by `match_id` is deterministic but does **not** make a same-date row usable as prior history. The target row's minutes, appearance state, or lineup are never used in its own check. Counts below are played-history presence; an unused bench listing alone does not satisfy them.

| Season | All listed rows | Played history 7d | 14d | 30d | Starter rows | Starter history 7d | 14d | 30d |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2015 | 11,015 | 4,871 (44.2%) | 7,705 (70.0%) | 8,838 (80.2%) | 6,732 | 3,827 (56.8%) | 5,872 (87.2%) | 6,310 (93.7%) |
| 2016 | 11,015 | 5,430 (49.3%) | 7,855 (71.3%) | 8,891 (80.7%) | 6,732 | 4,219 (62.7%) | 5,859 (87.0%) | 6,290 (93.4%) |
| 2017 | 11,016 | 4,517 (41.0%) | 7,427 (67.4%) | 8,836 (80.2%) | 6,732 | 3,541 (52.6%) | 5,624 (83.5%) | 6,295 (93.5%) |
| 2018 | 11,014 | 5,357 (48.6%) | 7,815 (71.0%) | 8,651 (78.5%) | 6,732 | 4,064 (60.4%) | 5,748 (85.4%) | 6,097 (90.6%) |
| 2019 | 11,011 | 4,034 (36.6%) | 7,526 (68.3%) | 8,720 (79.2%) | 6,732 | 3,147 (46.7%) | 5,750 (85.4%) | 6,267 (93.1%) |
| 2020 | 11,013 | 7,459 (67.7%) | 8,696 (79.0%) | 9,217 (83.7%) | 6,732 | 5,202 (77.3%) | 5,944 (88.3%) | 6,123 (91.0%) |
| 2021 | 13,676 | 7,575 (55.4%) | 10,115 (74.0%) | 11,504 (84.1%) | 8,360 | 5,396 (64.5%) | 7,090 (84.8%) | 7,811 (93.4%) |
| 2022 | 11,012 | 5,828 (52.9%) | 7,776 (70.6%) | 9,245 (84.0%) | 6,732 | 4,182 (62.1%) | 5,482 (81.4%) | 6,308 (93.7%) |
| 2023 | 11,014 | 4,526 (41.1%) | 7,847 (71.2%) | 9,188 (83.4%) | 6,732 | 3,263 (48.5%) | 5,581 (82.9%) | 6,307 (93.7%) |
| 2024 | 13,682 | 6,835 (50.0%) | 9,859 (72.1%) | 11,602 (84.8%) | 8,360 | 4,931 (59.0%) | 6,947 (83.1%) | 7,907 (94.6%) |
| **Total** | **115,468** | **56,432 (48.9%)** | **82,621 (71.6%)** | **94,692 (82.0%)** | **70,576** | **41,772 (59.2%)** | **59,897 (84.9%)** | **65,715 (93.1%)** |

As a separate diagnostic, counting an earlier **squad listing** rather than earlier *play* yields 67,275 / 95,814 / 105,448 all-row matches for 7/14/30 days. This is not playing-time evidence. A missing within-window played row is **not** necessarily an unavailable feature: for an observed J1-only window it can legitimately mean zero J1 minutes, an unused bench player, a recent arrival, a long fixture gap, or season start. It is also not a measure of identity error. Conversely, the J1-only log cannot establish total football workload: J2, Cup, AFC, training, and other matches are absent. Normalized minutes are not exact physical elapsed minutes.

## Team-level aggregation readiness (design only)

A possible future pre-match design is to take each club's **last completed J1 match before the target date** and use its then-known starting XI or entire listed squad as the reference group. For each reference member, sum *strictly earlier* local-key `minutes_played_normalized` in the 7-/14-day window, then aggregate with, for example, a mean or sum and an explicit count of members with no observed history. A previous-match XI is known before the target; the **target match's own XI must never be used**. The same-date batch rule applies to reference-squad and workload-state updates. A reference squad is not a forecast of the next XI, so any aggregate is a proxy, not an actual target-lineup load. Do not silently equate missing team history or non-J1 activity with zero total load. No threshold, imputation, feature column, or production rule was selected here.

This is technically feasible as an **in-scope J1-only local-history proxy**; the complete 6,416 team-match squads and exact 11 starters support a deterministic prior-match reference set. It is not yet a validated total-workload or stable-player-identity feature. Any implementation would need a separate leakage/identity review, explicit policy for first matches/new local keys, and evaluation in a new research cycle. The earlier verdict C for *official-ID-based longitudinal production linkage* is unchanged.

## Verdict

**B — locally usable for further feasibility/prototype work, with explicit season/team reset and coverage loss; not authorized for production modeling by this audit.** No observable within-match/same-team-season contradiction was found, and prior-play presence is high for 30-day starter rows (93.1%), but exact same-name collision across matches remains unprovable, 7-day presence varies with schedule, and resets discard potentially relevant cross-team or longer-term history. Cross-season or cross-team stitching, fuzzy/normalized names, and inferred official player IDs remain prohibited. A future official-player-ID linkage is deferred, not fabricated from these rows.
