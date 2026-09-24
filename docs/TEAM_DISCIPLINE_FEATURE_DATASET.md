# J1 Team Discipline Feature Dataset

Status: `READY_FOR_DISCIPLINE_EVALUATION_FREEZE`

This artifact is the first event-derived team discipline profile for ordinary
J1 matches in 2015--2024. It is a data artifact only; no model fitting,
prediction, metric calculation, or feature selection was performed.

## Inputs and scope

- Matches: `data/processed/jleague/{season}_matches_probe.csv`, 2015--2024.
- Events: `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`.
- Consumed event types: `YELLOW_CARD`, `RED_CARD` only.
- GOAL and SUBSTITUTION rows are ignored by this feature family.
- Team identity is resolved exactly through the existing TeamMaster
  `jleague_data_site` aliases; no player identity is used.
- No J2, J3, Cup, AFC, 2025, 2026/27, or Hyakunen data is included.

The source event artifact contains 7,671 yellow-card rows and 301 red-card
rows. The 18 yellow-card rows with unresolved display-minute normalization are
still valid card events and are counted by event type; minute normalization is
not used by this feature.

## Output

`data/processed/features/2015_2024_j1_team_discipline_features.csv`

The output has 3,208 rows, one per J1 match, and these frozen columns:

```text
match_id
match_date
season
home_team_id
away_team_id
home_discipline_available
away_discipline_available
home_prior_j1_matches
away_prior_j1_matches
home_yellow_cards_per_match_prior
away_yellow_cards_per_match_prior
home_red_cards_per_match_prior
away_red_cards_per_match_prior
```

The generated artifact SHA-256 is:
`40a7581dd9fa9f85c3d2e2af3942a73390098f78c34664770cc1d28d06cf9f1f3`.

## Chronology and missing semantics

For a target match, only earlier ordinary J1 matches in the same season are
used. History resets at each season boundary; there is no cross-season carry.
Matches sharing a date are a conservative batch: all rows for the date are
emitted first, and only then are both team appearances and that date's card
events added to history. This prevents same-date result/event leakage.

If a team has no prior match in the season, its availability flag is false,
the prior-match count is zero, and both rate fields are null. No zero
imputation is performed. With at least one prior match, availability is true;
zero cards are represented as `0.0`, and rates are finite and non-negative.

## Coverage audit

| season | matches | home available | away available | pair available | home unavailable | away unavailable | both unavailable |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2016 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2017 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2018 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2019 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2020 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2021 | 380 | 370 | 370 | 370 | 10 | 10 | 10 |
| 2022 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2023 | 306 | 297 | 297 | 297 | 9 | 9 | 9 |
| 2024 | 380 | 370 | 370 | 370 | 10 | 10 | 10 |

All 3,208 match IDs are unique, all identity/date fields are populated, and
all source event identities are checked against the J1 match universe and the
corresponding home/away team ID. The same-date batching invariant is covered
by targeted tests.

## Implementation and gate

The builder is implemented in `src/features/team_discipline.py`; targeted
tests are in `tests/test_team_discipline.py`. The current gate is
`READY_FOR_DISCIPLINE_EVALUATION_FREEZE`: the artifact is ready for a separate
pre-specified evaluation protocol, but no evaluation has been run in this
work item.
