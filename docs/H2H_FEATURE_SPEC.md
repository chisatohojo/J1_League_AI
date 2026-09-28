# Ordinary-J1 strict-prior exact-pair W/D/L feature specification

Status: **READY_FOR_H2H_FEATURE_MATERIALIZATION**.

This document freezes exactly one feature family from the reviewed
`H2H_STADIUM_FEASIBILITY.md`: cumulative strictly-prior ordinary-J1 result
counts for an exact unordered team pair, expressed from the current target
home team's perspective. It does not create a builder, dataset, tests,
generated CSV, model, prediction, predictive metric, or parameter choice.

## 1. Source and scope

Sources of truth:

- `docs/H2H_STADIUM_FEASIBILITY.md`;
- `data/processed/jleague/{season}_matches_probe.csv`;
- `src/collect/matches.py` for validated completed-match semantics; and
- the existing TeamMaster exact identity contract.

Frozen boundary:

- competition: ordinary J1 only;
- seasons: 2015–2024;
- target matches: exactly 3,208;
- identity: `match_id`, `match_date`, `season`, `home_team_id`, and
  `away_team_id`; and
- result semantics: `0 = Away win`, `1 = Draw`, `2 = Home win`.

Expected target counts are 306 in each season from 2015 through 2020, 380 in
2021, 306 in 2022 and 2023, and 380 in 2024.

Only existing ordinary-J1 processed match data, existing TeamMaster IDs, and
the results of strictly earlier scoped matches may be used. Excluded are
2025, 2026/27 first 80, future 300, Hyakunen, League Cup, Emperor's Cup,
J2/J3, AFC, and external HTTP.

## 2. Frozen family and exact candidates

The frozen family is **strict-prior exact unordered team-pair W/D/L count
state**. It has exactly three future model candidates, in this order:

```text
prior_h2h_match_count
prior_h2h_home_team_win_count
prior_h2h_draw_count
```

The target-away-team win count is deterministically recoverable as:

```text
prior_h2h_match_count
- prior_h2h_home_team_win_count
- prior_h2h_draw_count
```

It must not be emitted as a fourth candidate or output column. No other H2H
value is a model candidate under this specification.

## 3. Exact pair identity

The pair key is exactly:

```text
tuple(sorted((home_team_id, away_team_id)))
```

It uses unordered exact TeamMaster IDs. The pair key is internal state and is
not written to the output. Current target orientation and historical match
orientation remain separately known so historical results can be expressed
from the current target home team's perspective.

Prohibited identity mechanisms include club-name fuzzy matching, manual pair
aliases, stadium-based identity, league position, player identity, inferred
team equivalence, and row-position joins. TeamMaster must not be modified by
the future builder.

## 4. Strict-prior chronology

For a target on date `D`, history contains only scoped ordinary-J1 matches
satisfying:

```text
historical_match_date < D
```

The target's own result is prohibited. A result from another match on date
`D` is also prohibited, even if file order or a kickoff time would place it
earlier. Kickoff order must not be inferred.

Use same-date conservative batching:

1. sort targets deterministically by `match_date`, then string `match_id`;
2. inspect the pair state as it existed at the start of the date;
3. emit every target row on that date; and
4. only after all rows on the date are emitted, update state with all of that
   date's results.

The frozen source contains no team appearing in more than one scoped match
on the same date. Any such future materialization input is a hard failure.
The sort order provides deterministic output; it never overrides the date-
batch information boundary.

## 5. Cross-season state and the 2015 left boundary

Pair state does **not** reset at a season boundary. The scoped 2015–2024
ordinary-J1 history is accumulated continuously. A 2020 target, for example,
may use a strictly earlier exact-pair meeting from any scoped season beginning
in 2015.

All pair state starts empty at the beginning of the 2015 scope. No pre-2015
match is loaded, inferred, or imputed. Therefore:

```text
prior_h2h_match_count == 0
```

means only that no strictly prior meeting exists in the available scoped
prefix beginning in 2015. It does not claim that the teams never met before
2015 or in another competition.

## 6. Candidate semantics

For each target:

### `prior_h2h_match_count`

The number of strictly prior scoped ordinary-J1 meetings for the exact
unordered pair.

### `prior_h2h_home_team_win_count`

The number of those prior meetings won by the current target's
`home_team_id`. Whether that team was home or away in the historical match is
irrelevant; the result must be reoriented to the current target home-team
perspective.

### `prior_h2h_draw_count`

The number of those prior meetings whose result was a draw. Draws are
orientation-invariant.

All candidates are cumulative counts over the available scoped prefix. They
are not windowed, averaged, weighted, normalized, or season-reset.

## 7. Result reorientation

For each historical match state update:

- `result == 2`: increment the historical home team's win count;
- `result == 0`: increment the historical away team's win count;
- `result == 1`: increment the pair draw count; and
- always increment the pair total count.

When emitting a target, select the win count for the current target's exact
`home_team_id`.

Example:

```text
past:   A home vs B away; A wins
target: B home vs A away
```

The past event is a loss from target-home-team B's perspective. It increments
neither `prior_h2h_home_team_win_count` nor `prior_h2h_draw_count` for that
target, but it does increment `prior_h2h_match_count` and the deterministically
derived target-away-team win count. Accumulating raw result classes without
orientation is prohibited.

## 8. Pair state representation

The future implementation may represent each exact pair's state differently
internally, but it must retain enough validated information to reproduce at
least:

```text
total_matches
wins_by_exact_team_id
draws
latest_match_id
latest_match_date
```

Both IDs in `wins_by_exact_team_id` must be the exact members of the pair.
The sum of both team win counts plus draws must equal total matches after
every update. State is cumulative, and latest match identity/date are
replacement-only audit values.

## 9. Structural zero and missingness

If a target pair has no prior scoped meeting, emit:

```text
prior_h2h_match_count = 0
prior_h2h_home_team_win_count = 0
prior_h2h_draw_count = 0
```

These are structural observed-prefix zeros, not imputations. Candidate nulls
are prohibited on every row, including the 2015 left boundary.

Availability and previous-match audit fields behave as follows:

```text
h2h_available == false
  => prior_h2h_match_count == 0
  => all three candidates == 0
  => previous_h2h_match_id is null
  => previous_h2h_match_date is null

h2h_available == true
  => prior_h2h_match_count > 0
  => previous_h2h_match_id is non-null
  => previous_h2h_match_date is non-null
  => previous_h2h_match_date < target match_date
```

The previous H2H match must be the exact latest strictly earlier scoped
ordinary-J1 match for that pair. Availability and previous identity/date are
audit fields, not model candidates.

## 10. Candidate invariants

Every row must satisfy:

```text
prior_h2h_match_count >= 0
prior_h2h_home_team_win_count >= 0
prior_h2h_draw_count >= 0

prior_h2h_home_team_win_count + prior_h2h_draw_count
    <= prior_h2h_match_count
```

All three values must be non-null integers. The derived target-away-team win
count must also be an integer greater than or equal to zero.

Furthermore:

- total zero requires home-team wins zero, draws zero, availability false,
  and null previous-match audit identity/date;
- total greater than zero requires availability true and complete previous-
  match audit identity/date; and
- every historical W/D/L update must reconcile exactly to the pair total.

Clipping, coercing invalid values, silently dropping targets, and changing
scope to satisfy a reference are prohibited.

## 11. Frozen availability references

The future builder must rederive availability from actual pair state and then
assert these values:

| Season | Target matches | H2H available | H2H unavailable |
|---:|---:|---:|---:|
| 2015 | 306 | 153 | 153 |
| 2016 | 306 | 258 | 48 |
| 2017 | 306 | 271 | 35 |
| 2018 | 306 | 285 | 21 |
| 2019 | 306 | 286 | 20 |
| 2020 | 306 | 288 | 18 |
| 2021 | 380 | 356 | 24 |
| 2022 | 306 | 289 | 17 |
| 2023 | 306 | 303 | 3 |
| 2024 | 380 | 343 | 37 |
| **Total** | **3,208** | **2,832** | **376** |

Global availability is 88.3%. The counts are frozen validation references,
not eligibility filters and not evidence of predictive value.

## 12. Frozen prior-count distribution

The exact global target distribution is:

| Strict-prior pair meetings | Targets |
|---:|---:|
| 0 | 376 |
| 1 | 376 |
| 2 | 265 |
| 3 | 265 |
| 4 | 224 |
| 5–9 | 860 |
| 10+ | 842 |
| **Total** | **3,208** |

The future materialization must derive this distribution from
`prior_h2h_match_count` and assert it exactly. It must not alter chronology,
cross-season behavior, identity, or bins to make the counts agree.

## 13. Exact future output schema

One row represents one target match. The exact ordered 11-column schema is:

```text
match_id
match_date
season
home_team_id
away_team_id
h2h_available
previous_h2h_match_id
previous_h2h_match_date
prior_h2h_match_count
prior_h2h_home_team_win_count
prior_h2h_draw_count
```

Only the final three columns are model candidates. The pair key and derived
target-away-team win count must not appear. No extra availability, result,
rate, recency, or orientation column may be added.

Logical types are:

- `match_id` and team IDs: strings;
- `match_date`: ISO `YYYY-MM-DD`;
- `season`: integer;
- `h2h_available`: boolean;
- previous H2H match ID: nullable string;
- previous H2H date: nullable ISO `YYYY-MM-DD`; and
- all three candidates: non-null integers.

## 14. Target identity and output invariants

The future builder must hard-fail unless:

- the target universe contains exactly 3,208 rows and 3,208 unique match IDs;
- season values and counts match Section 1 exactly;
- all dates are valid ISO dates and their year equals season;
- home and away TeamMaster IDs are nonblank, exact, and distinct;
- target identity is joined and compared by `match_id`, never row position;
- output contains exactly one row for every target match ID;
- identity columns exactly reproduce the target universe;
- output order is exactly `match_date`, then string `match_id`;
- every candidate and audit field satisfies Sections 9 and 10;
- the previous match is the exact latest strictly prior meeting for the pair;
- all availability and distribution references are reproduced; and
- target-own and same-date result use are both zero.

Duplicate match IDs and one team appearing twice on one date are hard
failures. No target may be dropped because it lacks history.

## 15. Deterministic materialization and write safety

Identical inputs must produce identical rows, values, order, and serialized
bytes. The future implementation must freeze one CSV encoding, dialect, null
representation, boolean representation, and line ending, and prove a byte-
identical rebuild in a temporary location.

The planned production output is:

```text
data/processed/features/2015_2024_j1_h2h_features.csv
```

It must be gitignored, written atomically, and never silently overwrite an
existing output. The materialization report must publish its SHA-256. No such
artifact is created by this specification task.

## 16. Explicitly prohibited variants

The future builder, dataset, tests, evaluation, and any response to later
results must not add:

- latest H2H result;
- draw rate, win rate, points per match, or any ratio;
- same-orientation or reverse-orientation splits;
- home-only or away-only H2H;
- recency or days since latest H2H;
- last 3, last 5, a 3-year window, or a 5-year window;
- EWMA, decay, weights, draw-specific weight, trend, or interaction; or
- target-away-team win count as a candidate or output column.

The older repository `last5` H2H logic is outside this frozen family and must
not be reused as the future builder's semantics. Tests may validate the
frozen family only; they must not introduce feature variants.

## 17. Source and adjacent-lane boundaries

The H2H state may use only prior ordinary-J1 result state and exact TeamMaster
IDs. It must not use stadium, xG, player data, cards, goals, substitutions,
starter DF, workload, or lineup continuity.

Stadium remains **DEFER_STADIUM** because stable venue ID is absent and
pre-match provenance is not established:

```text
STADIUM_PREMATCH_PROVENANCE_UNPROVEN
```

No stadium identity or history may enter this family.

The following reviewed lanes remain closed and must not be reintroduced:

- PLAYER WORKLOAD — `CLOSE_RETROSPECTIVE_LANE`
- LINEUP CONTINUITY — closed
- DISCIPLINE — `CLOSE_RETROSPECTIVE_LANE`
- FIRST SCORE — `CLOSE_RETROSPECTIVE_LANE`
- GOAL TIMING — `CLOSE_RETROSPECTIVE_LANE`
- SUBSTITUTION TIMING — `CLOSE_RETROSPECTIVE_LANE`
- STARTER DF — `CLOSE_RETROSPECTIVE_LANE`

## 18. Relationship to Elo and the draw issue

Both H2H state and Elo are derived from past match results, so their source
information partly overlaps. Elo is team-level strength state; this H2H
family is exact-pair conditional state. The semantic distinction does not
establish predictive improvement.

The project's known difficulty producing Draw as the argmax may motivate
auditing a draw-related source, but this specification does not assume that
`prior_h2h_draw_count` improves Draw prediction. Draw rate is not added, and
no target-result association is inspected at specification time.

## 19. Required future materialization tests

The future implementation must include at least these 30 tests:

1. Exact pair identity is unordered.
2. Pair identity uses exact TeamMaster IDs only.
3. A target's own result is excluded.
4. Same-date results are excluded by date batching.
5. Only strictly earlier dates enter history.
6. Pair state carries across a season boundary.
7. The 2015 left boundary starts with empty state.
8. A scoped zero makes no inference about pre-2015 history.
9. A same-orientation historical result is expressed from the target home
   team's perspective.
10. A reverse-orientation historical result is correctly reoriented.
11. A draw is orientation-invariant.
12. Previous H2H match ID/date identify the exact latest strictly prior pair
    meeting.
13. No-history candidates are structural zeros.
14. No-history previous H2H ID/date are null.
15. Available-history previous H2H ID/date are non-null and strictly earlier.
16. Home-team wins plus draws cannot exceed total matches.
17. The derived target-away-team win count is a nonnegative integer.
18. All three candidate counts are non-null integers.
19. Output has exactly the ordered 11-column schema.
20. Output has exactly 3,208 target rows.
21. Output has exactly 3,208 unique match IDs.
22. Every frozen season target count is reproduced.
23. Every frozen season availability count is reproduced.
24. Global available/unavailable counts are exactly 2,832/376.
25. Global prior-count bins 0, 1, 2, 3, 4, 5–9, and 10+ are exact.
26. Input row order does not change output rows, values, or output order.
27. Rebuilding identical input produces byte-identical serialization.
28. A duplicate target match ID hard-fails.
29. One team appearing twice on one date hard-fails.
30. The model candidate family remains exactly the three frozen candidates.

Additional validation tests are allowed. Feature variants are not.

## 20. Future materialization deliverables and audit

The separately authorized future materialization task is expected to create:

```text
src/features/h2h.py
tests/test_h2h.py
docs/H2H_FEATURE_DATASET.md
data/processed/features/2015_2024_j1_h2h_features.csv  # generated, gitignored
```

The dataset document and completion report must include at least:

- scope, source, target identity, and exact pair identity;
- chronology, same-date batching, and cross-season state;
- the 2015 left-boundary limitation;
- exact candidate definitions and structural-zero semantics;
- audit fields, exact schema, and logical data types;
- season/global availability and prior-count distribution;
- actual candidate distributions and invariant failures;
- target-own and same-date exclusion results;
- deterministic byte-identical rebuild status; and
- output SHA-256.

No predictive metric may be calculated during materialization.

## 21. No predictive evaluation

This specification does not calculate or inspect Accuracy, Log Loss, Brier,
AUC, target-result correlation, mutual information, coefficient, feature
importance, or any other target-label relationship. Model fitting,
prediction, feature selection, parameter tuning, and adaptive follow-up are
prohibited. Coverage and source distributions are validation references, not
predictive evidence.

## 22. Final gate

**READY_FOR_H2H_FEATURE_MATERIALIZATION**

The exact family, three candidates, unordered TeamMaster pair identity,
target-home result reorientation, no-reset cross-season state, 2015 left
boundary, structural zeros, audit fields, date batching, 11-column schema,
coverage/distribution references, deterministic output, prohibited variants,
source boundaries, and 30 required future tests are fully frozen.

- Model candidates: **EXACTLY THREE**
- Output columns: **EXACTLY ELEVEN**
- Required future materialization tests: **30**
- Predictive metrics: **NOT COMPUTED**
- Model fitting: **NO**
- Predictions: **NO**
- Feature builder/dataset/tests: **NOT CREATED**
- Stadium: **DEFERRED**
- 2025: **NOT USED**
- 2026/27: **NOT USED**
- external HTTP: **NO**
