# Previous-season J Stats feature dataset

## Status

Feature dataset materialization is complete. Model fitting, evaluation, prediction, and feature selection were not run.

Output:

```text
data/processed/features/previous_season_jstats_features.csv
```

The dataset contains 2,438 ordinary-J1 target fixtures:

| Target | Profile | Rows |
|---|---:|---:|
| 2020 ordinary J1 | 2019 | 306 |
| 2021 ordinary J1 | 2020 | 380 |
| 2022 ordinary J1 | 2021 | 306 |
| 2023 ordinary J1 | 2022 | 306 |
| 2024 ordinary J1 | 2023 | 380 |
| 2025 ordinary J1 | 2024 | 380 |
| 2026/27 ordinary J1 schedule | 2025 | 380 |

There are 2,438 unique target fixtures, one row per ordinary-J1 fixture.
Historical 2020-2025 rows have a populated, unique official `match_id` and an
empty `fixture_key`. The 2026/27 schedule has a unique non-empty `fixture_key`;
its official `match_id` is preserved as supplied by the schedule (80 completed
rows are populated and 300 future rows are blank). A `fixture_key` is never
copied into `match_id` and is not presented as an official match identity.

2026 J1百年構想リーグ is not included. The 2026/27 rows include future fixtures, but no score, result, or match statistics are used.

## Mapping and identity

The explicit ordinary-J1 mapping in `PREVIOUS_SEASON_JSTATS_FEATURE_SPEC.md` is the only mapping source. No arithmetic `N-1` fallback is used.

- historical target names resolve through `source=jleague_data_site`
- 2026/27 schedule slugs resolve through exact TeamMaster `source_club_id` under `jleague_data_site`
- profile rows are joined by stable `team_id`
- team names are never joined directly across namespaces
- fuzzy, substring, normalized, guessed, or manual mappings are not used

## Feature values

The six frozen candidate interface fields are represented as home/away values:

- xG and xGA fields use the artifact's validated `derived_value` per match
- shots on target and suffered shots on target use validated `derived_value` per match
- possession and pass success use the official profile `raw_value`
- profile retrieval ID is retained for both sides

No rounding or reverse conversion is performed during the join. A present previous profile must contain all six stats; partial profiles hard-fail. A team without a mapped previous-season J1 profile receives null values and `has_previous_j1_profile=false`.

## Availability diagnostics

Pair availability by target season:

| Target | Home missing appearances | Away missing appearances | Both profiles available |
|---|---:|---:|---:|
| 2020 | 34 | 34 | 240/306 |
| 2021 | 38 | 38 | 306/380 |
| 2022 | 34 | 34 | 240/306 |
| 2023 | 34 | 34 | 240/306 |
| 2024 | 57 | 57 | 272/380 |
| 2025 | 57 | 57 | 272/380 |
| 2026/27 | 57 | 57 | 272/380 |

These missing appearances are promoted/no-previous-profile cases under the explicit mapping. They are not filled with zero, league average, J2, Cup, or another club's profile. No partial-profile errors, duplicate target IDs, or mapping violations were observed.

## Leakage safeguards

- target competition must be ordinary J1
- target season uses only its explicitly mapped previous profile season
- same-season final profile is rejected by construction
- 2026 Hyakunen is rejected as a target
- target score/result and future match data are not read as features
- one target fixture produces one row

## Provenance

All profile rows use retrieval ID `20260923T010000000000Z`. The source artifact is the COMPLETE raw-backed profile artifact. This dataset is a feature materialization artifact only; it is not a model result.
