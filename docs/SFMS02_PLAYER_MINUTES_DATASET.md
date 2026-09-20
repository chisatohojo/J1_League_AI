# SFMS02 J1 player-match normalized minutes dataset

## Scope and provenance

This offline dataset covers all 3,208 ordinary J1 matches in 2015–2024. It uses the existing J.League Data Site SFMS02 HTML and validated metadata in `data/raw/jleague_match_stats/`, aligned by `match_id` to the season J1 match probes and processed match stats. The source cache is not rewritten; this build made zero web requests. Run `python -m src.collect.sfms02_player_minutes` to create `data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv`. The collector refuses to overwrite an existing output.

One row represents one listed matchday-squad player (11 starters plus listed substitutes) for one match and team. Team identity comes from the existing stable J1 `team_id`; player identity is **only the exact match-local raw name**. The output does not establish a longitudinal or cross-team player identity.

## Minute semantics

`minutes_played_normalized` is a consistently reconstructed interval on a 0–90 regulation clock, **not physical elapsed playing time or an official player-minute statistic**. It is `max(0, left_minute_normalized - entered_minute_normalized)`. A starter enters at 0; an unused listed substitute has null entry/exit and 0 minutes; an active player without an exit is assigned exit 90.

- An ordinary displayed minute is used as written. In particular `46'` is 46, not inferred to be halftime; the row receives `MINUTE_46_BOUNDARY_AMBIGUOUS` because halftime and early-second-half timing cannot be distinguished from that token.
- `45'+X` is capped at 45 (`FIRST_HALF_ADDED_TIME_CAPPED`); `90'+X` is capped at 90 (`SECOND_HALF_ADDED_TIME_CAPPED`). Original minute strings remain in the raw fields. Event ordering still places first-half added time before minute 46.
- Adjacent SFMS02 substitution OUT/IN rows form one pair. The IN player inherits the OUT minute. A substitute can later go OUT; a goalkeeper change follows the same rule as any other substitution.
- An A9 dismissal ends participation only when the named player is active on the pitch. A dismissal recorded after substitution OUT or for an unused bench player is preserved but does not shorten the interval. These cases are explicitly flagged, not silently repaired.
- An entered substitute may have 0 normalized minutes after a `90'+X` cap. This remains an appearance, not an unused substitute.

Impossible state transitions, unsupported minute tokens, missing exact match-local names, unpaired substitutions, duplicate player rows, and out-of-range minutes are errors. The team-minute invariant is checked against 990 minus the normalized remaining minutes lost to active dismissals; 990 is not imposed on dismissed teams.

## Schema

`match_id`, `match_date`, `season`, `team_id`, `team_name`, `player_name_raw`, `starter`, `listed_substitute`, `entered_minute_raw`, `entered_minute_normalized`, `left_minute_raw`, `left_minute_normalized`, `dismissed_minute_raw`, `dismissed_minute_normalized`, `minutes_played_normalized`, `appearance_type`, `normalization_flags`, `source`, `source_url`, `raw_sha256`.

`appearance_type` is one of `starter_full`, `starter_subbed_out`, `starter_dismissed`, `sub_entered`, `sub_entered_and_left`, `sub_entered_dismissed`, `unused_substitute`. Flags are semicolon-separated; counts below are **player-row counts**, so one substitution event may flag two players.

## Full-history quality audit

| Season | Matches | Player rows |
| --- | ---: | ---: |
| 2015 | 306 | 11,015 |
| 2016 | 306 | 11,015 |
| 2017 | 306 | 11,016 |
| 2018 | 306 | 11,014 |
| 2019 | 306 | 11,011 |
| 2020 | 306 | 11,013 |
| 2021 | 380 | 13,676 |
| 2022 | 306 | 11,012 |
| 2023 | 306 | 11,014 |
| 2024 | 380 | 13,682 |
| **Total** | **3,208** | **115,468** |

There are 6,416 team-match lineups, all with exactly 11 starters: 70,576 starter rows and 44,892 listed-substitute rows. Positive normalized minutes occur on 92,731 rows; 21,254 rows are unused substitutes. Another 1,483 played rows have 0 normalized minutes under the capping convention.

| Appearance type | Rows |
| --- | ---: |
| starter_full | 46,809 |
| starter_subbed_out | 23,504 |
| starter_dismissed | 263 |
| sub_entered | 23,468 |
| sub_entered_and_left | 134 |
| sub_entered_dismissed | 36 |
| unused_substitute | 21,254 |

Across **all roster rows**, normalized minutes have min 0, median 74.5, mean 54.9441, max 90. All 23,638 substitution pairs link exactly and have an OUT minute. All 301 dismissal rows are accounted for: 299 active dismissals applied, one post-substitution dismissal ignored for the interval, and one unused-bench dismissal ignored for the interval. The 134 entered-then-left cases are represented. The feasibility audit's 62 goalkeeper substitutions are handled through the same pairing/state rule; a goalkeeper fixture is included in tests.

| Normalization flag | Player rows |
| --- | ---: |
| FIRST_HALF_ADDED_TIME_CAPPED | 80 |
| SECOND_HALF_ADDED_TIME_CAPPED | 2,313 |
| MINUTE_46_BOUNDARY_AMBIGUOUS | 3,434 |
| DISMISSAL_APPLIED | 299 |
| POST_SUB_DISMISSAL_IGNORED | 1 |
| UNUSED_SUB_DISMISSAL_IGNORED | 1 |

Validation found zero duplicate match/team/player rows, zero missing match/team/player identity, zero minutes outside [0, 90], zero unused substitutes with positive minutes, and zero full-match starters with other than 90 normalized minutes. All 3,208 raw cache entries passed URL, status, size and SHA-256 metadata checks; all matches joined one-to-one to J1 probes and stats. The parser also checks team-minute conservation for each of the 6,416 team matches. There were no parser/state/conservation failures in the full build.

## Limitation and future use

Raw names can be ambiguous or change between matches. No fuzzy matching, normalized-name player master, transfer linkage, or stable player ID is inferred here. Consequently this dataset alone must **not** be used to construct player `minutes_last_7d`, `minutes_last_14d`, or other cross-match workload features. Those are possible future candidates only after a safe stable-player-ID linkage and separate leakage audit. No feature generation, predictions, or model evaluation were performed in this work.
