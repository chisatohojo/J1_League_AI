# J1 previous-match starter DF feature dataset (2015–2024)

This production feature dataset contains one row per ordinary J1 match and exactly two future model candidates: `home_previous_match_starter_df_count` and `away_previous_match_starter_df_count`. It was materialized offline from the locally cached SFMS02 A5 starter sections. No external HTTP, model fitting, prediction, feature selection, tuning, result-label comparison, or predictive metric computation was performed.

- Output: `data/processed/features/2015_2024_j1_starter_df_features.csv`
- Builder: `python -m src.features.starter_df`
- Scope: ordinary J1, 2015–2024, 3,208 matches and 6,416 team-match sides
- Output SHA-256: `056963dd4707f122754d596ac6865721052cc3a31589a3a02941faca683aa674`
- Final gate: **READY_FOR_STARTER_DF_EVALUATION_FREEZE**

## Definition and information boundary

For each target team, the candidate is the number of rows whose source position is exactly `DF` in that team's latest strictly earlier ordinary-J1 match in the current season. The state key is `(season, team_id)` and each new prior match replaces, rather than accumulates or averages, the earlier state. State is fully reset at each season boundary.

All matches on the same date are emitted from the state present at the start of that date. Only after all rows for that date are emitted are their A5 counts installed into state. Therefore the target match's own roster and same-date peer rosters are prohibited, and no kickoff ordering is inferred. The frozen source contains no team with multiple scoped matches on one date; such input is rejected.

This is an identity-free aggregate. Player names are checked only for exact duplicates within one team-match A5 roster. Names and shirt numbers are never linked across matches, normalized, fuzzily matched, merged, or converted into player IDs. Longitudinal player identity is not used.

The number is a **source-listed A5 starter DF count**. It must not be interpreted as a tactical formation, back three/back four, defensive line, or actual role. A6 bench rows and all other SFMS02 sections are excluded. No GK/MF/FW feature, position vector, ratio, difference, interaction, rolling statistic, lineup continuity, workload, substitution, goal, card, result, or score-state feature was added.

## Sources and validation

The target universe is the exact match-ID intersection contract established by the 2015–2024 probe CSVs, match-stats CSVs, and existing TeamMaster identity. Match IDs are never joined by row position. For every target match, the builder reads the cached HTML and metadata only:

- `data/raw/jleague_match_stats/{match_id}.html`
- `data/raw/jleague_match_stats/{match_id}.metadata.json`

The metadata must reproduce the expected SFMS02 URL in both `requested_url` and `final_url`, HTTP status 200, the target match ID, raw byte length, and a newly calculated SHA-256. Any mismatch fails materialization. The production audit found **0 metadata failures**.

Each validated page must contain exactly two A5 side sections. Each side must contain exactly 11 player rows, in the exact cell-class order `position`, `number`, `name`, `time`. Position must be one of case-sensitive `GK`, `DF`, `MF`, or `FW`; number and name must be nonblank; name must contain no replacement character; time must be empty; exact duplicate names are forbidden within the side; and exactly one row must be `GK`. Extra, missing, duplicated, or reordered cells fail rather than being repaired, clipped, coerced, or filtered.

### Frozen source reconciliation

| Item | Count |
| --- | ---: |
| Matches | 3,208 |
| Team-match sides / A5 sections | 6,416 |
| A5 player rows | 70,576 |
| Row-shape failures | 0 |
| Malformed names | 0 |
| Nonempty time cells | 0 |
| Invalid position rows | 0 |
| Sides with other than 11 rows | 0 |
| Sides with other than one GK | 0 |
| Metadata failures | 0 |

Position totals are GK 6,416, DF 23,935, MF 27,004, and FW 13,221. The current-match source DF-count distribution across 6,416 sides is `2: 20`, `3: 1,928`, `4: 4,238`, `5: 221`, and `6: 9`.

## Missingness and availability

When no strictly earlier current-season match exists, the side's availability is `false` and all three previous-match audit values—ID, date, and DF count—are null. When state exists, availability is `true`, the previous ID/date identify the exact latest strictly earlier same-season match for that team, and the count is an integer. No value is imputed as zero, four, or a season mean. Home and away states are independent; one-sided availability is structurally valid even though none occurs in this frozen dataset.

| Season | Matches | Home available | Away available | Sides available / unavailable | Pairs available / unavailable | Home-only / away-only / both unavailable |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2015 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2016 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2017 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2018 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2019 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2020 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2021 | 380 | 370 | 370 | 740 / 20 | 370 / 10 | 0 / 0 / 10 |
| 2022 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2023 | 306 | 297 | 297 | 594 / 18 | 297 / 9 | 0 / 0 / 9 |
| 2024 | 380 | 370 | 370 | 740 / 20 | 370 / 10 | 0 / 0 / 10 |
| **Total** | **3,208** | **3,116** | **3,116** | **6,232 / 184** | **3,116 / 92** | **0 / 0 / 92** |

These counts were derived from chronology, not inferred from side totals or hardcoded season-opener flags.

## Previous-match DF distributions

Entries are `DF count: available sides` after exact replacement-state chronology.

| Season | Distribution |
| --- | --- |
| 2015 | 3: 195; 4: 384; 5: 15 |
| 2016 | 3: 147; 4: 446; 5: 1 |
| 2017 | 2: 3; 3: 133; 4: 443; 5: 15 |
| 2018 | 3: 166; 4: 405; 5: 23 |
| 2019 | 3: 275; 4: 315; 5: 4 |
| 2020 | 3: 193; 4: 383; 5: 18 |
| 2021 | 2: 3; 3: 170; 4: 523; 5: 36; 6: 8 |
| 2022 | 3: 167; 4: 393; 5: 34 |
| 2023 | 2: 9; 3: 184; 4: 368; 5: 33 |
| 2024 | 2: 3; 3: 239; 4: 464; 5: 33; 6: 1 |
| **Global** | **2: 18; 3: 1,869; 4: 4,124; 5: 212; 6: 9** |

The global total is 6,232 available sides.

## Exact output schema

The CSV has exactly these 13 columns in order:

1. `match_id`
2. `match_date`
3. `season`
4. `home_team_id`
5. `away_team_id`
6. `home_starter_df_available`
7. `away_starter_df_available`
8. `home_previous_match_id`
9. `away_previous_match_id`
10. `home_previous_match_date`
11. `away_previous_match_date`
12. `home_previous_match_starter_df_count`
13. `away_previous_match_starter_df_count`

Only the final two columns are candidate features; availability, previous match IDs, and previous dates are audit fields. IDs are strings, dates use ISO `YYYY-MM-DD`, season is integer, availability is boolean, and DF counts are nullable integers. No pair-availability column was added. Rows are deterministically ordered by `match_date`, then string `match_id`.

The output contains 3,208 rows and 3,208 unique match IDs. Partial-invalid rows, output invariant failures, target-roster use, same-date leakage, and prior-season carryover are all **0**. Target-own exclusion, same-date batching, current-season reset, latest-previous-match replacement, and the identity-free contract all passed.

## Determinism, safety, and closed lanes

Rebuilding in memory from the same validated inputs produced the same rows, values, ordering, and serialized bytes: **byte-identical rebuild PASS**. The production writer is atomic and refuses to overwrite an existing output. The generated CSV is gitignored.

The following boundaries remain closed: no predictive evaluation or result-label comparison; no Accuracy, Log Loss, Brier, AUC, correlation, mutual information, coefficient, or feature importance; no model fitting, predictions, feature selection, or tuning. Data from 2025, 2026/27 first80, future300, Hyakunen, League Cup, Emperor's Cup, J2/J3, and AFC was not used. External HTTP was not used.
