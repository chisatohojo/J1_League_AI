# Ordinary J1 first-score profile feature dataset

Status: **MATERIALIZED_AND_VALIDATED**.

Final gate: **READY_FOR_FIRST_SCORE_EVALUATION_FREEZE**.

## Purpose

This dataset provides leakage-safe, current-season prior first-score profiles
for ordinary-J1 target matches. It materializes the frozen contract in
`docs/FIRST_SCORE_FEATURE_SPEC.md`; it does not evaluate predictive value or
add the features to a model.

## Source and scope

- Target competition: ordinary J1 only
- Target seasons: 2015–2024
- Target rows: 3,208, one per unique match
- GOAL source:
  `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`
- GOAL rows validated: 8,377
- Matches with GOAL: 2,958
- Matches with no GOAL: 250
- Source semantics: `docs/GOAL_TIMING_STATE_FEASIBILITY.md`
- Feature specification: `docs/FIRST_SCORE_FEATURE_SPEC.md`
- Builder: `src/features/first_score_profile.py`
- Output:
  `data/processed/features/2015_2024_j1_first_score_features.csv`
- Output SHA-256:
  `aa5beb436695e0382ab39039f9b98de85aec73cfafc29765b060a451f1435f9a`

The generated CSV is gitignored. No 2025, 2026/27, Hyakunen, Cup, Emperor's
Cup, J2/J3, or AFC match is used. External HTTP requests were not made.

## Source classification audit

The complete GOAL order key is
`(minute_order_half, minute_order_base, minute_order_added)`. Home and away
are never ordered by artifact row order, `event_id`, or `source_row_index`.

| Classification | Matches |
|---|---:|
| `SCORED_FIRST_HOME` | 1,536 |
| `SCORED_FIRST_AWAY` | 1,421 |
| `NO_GOAL` | 250 |
| `AMBIGUOUS_FIRST_SIDE` | 0 |
| `NOT_CHECKABLE` | 1 |
| **Total** | **3,208** |

The unique first-side usable total is 2,957. Known match `20822` contains a
same-side duplicate time key and remains a valid unique-side observation. No
historical minimum key contains both home and away.

`NO_GOAL` is a usable observation, not missing data. It increments the
eligible and no-goal counters for both teams and contributes the team-level
state `scored_first=0`, `conceded_first=0`, `no_goal=1`.

## Denominator and chronology

For each team, the denominator is the count of usable ordinary-J1 matches in
the same season whose match date is strictly earlier than the target date:

```text
prior_first_score_eligible_matches
  = prior_scored_first_matches
  + prior_conceded_first_matches
  + prior_no_goal_matches
```

All matches on the same date are emitted from the history available before
that date. Their observations enter history only after every target row on
that date has been generated. Match ID order affects output determinism only;
it does not permit same-date information flow. History resets at every season
boundary and has no prior-season carry-over.

When the denominator is zero, availability is false and all three rates are
null. When it is positive, availability is true, real zeros remain `0.0`, and
the scored-first, conceded-first, and no-goal rates are finite values in
`[0,1]` that sum to one.

## Mandatory exclusion and ambiguity handling

Match `25153` is the sole `NOT_CHECKABLE` observation. Its target row remains
in the dataset and has ordinary prior-history features (home eligible 17,
away eligible 18), but its A1 adjudicated 0–3 result and A2 on-field 2–3 event
history are not reinterpreted. Its observation is not appended to either
team's history.

The actual next target for `team_0030` is match `25156`, whose eligible count
remains 17; the next target for `team_0026` is match `25173`, whose eligible
count remains 18. Both equal the independently counted usable prior matches
with `25153` excluded.

Any future cross-side same-minimum-key match is
`AMBIGUOUS_FIRST_SIDE`. Its target row may remain, but neither team receives
an eligible or component-counter increment. Silent tie-breaking is prohibited.

The first-score family does not classify halves. A `46'` GOAL participates in
the complete-key first-side decision despite retaining
`MINUTE_46_BOUNDARY_AMBIGUOUS`; it is not reused as a half feature.

## Output schema

Identity:

```text
match_id
match_date
season
home_team_id
away_team_id
```

Availability and audit counters:

```text
home_first_score_available
away_first_score_available
home_prior_first_score_eligible_matches
away_prior_first_score_eligible_matches
home_prior_scored_first_matches
away_prior_scored_first_matches
home_prior_conceded_first_matches
away_prior_conceded_first_matches
home_prior_no_goal_matches
away_prior_no_goal_matches
```

Rates:

```text
home_scored_first_rate_prior
away_scored_first_rate_prior
home_conceded_first_rate_prior
away_conceded_first_rate_prior
home_no_goal_rate_prior
away_no_goal_rate_prior
```

The exact future model-candidate values are:

```text
home_scored_first_rate_prior
away_scored_first_rate_prior
home_conceded_first_rate_prior
away_conceded_first_rate_prior
```

Availability, counts, and no-goal rates are audit/support fields and are not
automatically model inputs.

## Availability audit

`either unavailable` means at least one side is unavailable; `both
unavailable` means neither side has an eligible prior observation.

| Season | Total | Home available | Away available | Pair available | Either unavailable | Both unavailable |
|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2016 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2017 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2018 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2019 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2020 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2021 | 380 | 370 | 370 | 370 | 10 | 10 |
| 2022 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2023 | 306 | 297 | 297 | 297 | 9 | 9 |
| 2024 | 380 | 370 | 370 | 370 | 10 | 10 |
| **Total** | **3,208** | **3,116** | **3,116** | **3,116** | **92** | **92** |

Required 2020–2024 pair-availability counts are therefore:

| Season | Pair available |
|---:|---:|
| 2020 | 297 |
| 2021 | 370 |
| 2022 | 297 |
| 2023 | 297 |
| 2024 | 370 |

There are 3,207 usable match observations, producing 6,414 eligible
team-level observations. One `NOT_CHECKABLE` match is excluded, zero
ambiguous matches are excluded, and 250 matches contribute `NO_GOAL`
observations for both teams.

## Validation and determinism

Validation passed for:

- exactly 3,208 unique target match IDs and the frozen season counts
- exact TeamMaster home/away identity and differing home/away IDs
- 8,377 unique-ID GOAL rows, all with resolved complete time keys
- event match/team/side identity against the target universe
- all five classification states and the mandatory `25153` exclusion
- same-date batching, season reset, and no target leakage
- denominator/component equality on every home and away snapshot
- complete null rates only when the eligible count is zero
- finite `[0,1]` rates summing to one on every available snapshot
- zero partial-invalid output rows
- all 14 frozen fixture contracts

A full rebuild from the same inputs was byte-identical and reproduced SHA-256
`aa5beb436695e0382ab39039f9b98de85aec73cfafc29765b060a451f1435f9a`.
Existing output is never silently overwritten.

## Limitations

- The features describe displayed first-score side, not exact elapsed seconds.
- Future cross-side same-key observations remain unusable without finer source
  evidence.
- Match `25153` supplies no first-score history observation.
- Same-date batching is intentionally conservative and may omit an earlier
  same-day match from a later kickoff's history.
- The family contains no goal timing means, half splits, trajectories,
  equalizer/go-ahead features, rolling windows, goal volume, goal difference,
  or result form.
- Availability coverage did not change the frozen feature definition.

No Log Loss, Brier score, Accuracy, correlation, AUC, coefficient, feature
importance, or other predictive metric was observed or computed. No model was
fit and no prediction, feature selection, or parameter tuning was performed.
