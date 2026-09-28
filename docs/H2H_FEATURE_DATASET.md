# Ordinary-J1 strict-prior exact-pair H2H feature dataset

Status: **READY_FOR_H2H_EVALUATION_FREEZE**

Predictive metrics: **NOT COMPUTED**

This document records the materialized dataset governed by
`docs/H2H_FEATURE_SPEC.md` and the source boundary in
`docs/H2H_STADIUM_FEASIBILITY.md`. It is a source/chronology validation
artifact, not predictive evidence. No model was fit, no prediction was made,
and no target-label relationship was calculated.

## Scope and source

The dataset contains exactly 3,208 completed ordinary-J1 matches from 2015
through 2024. The only match sources are the existing local
`data/processed/jleague/{season}_matches_probe.csv` files. The materializer
uses `src.collect.matches.load_matches` and the existing TeamMaster exact
mapping. It does not use fuzzy matching, manual aliases, row-position joins,
other competitions, player data, stadium data, pre-2015 data, 2025 data,
2026/27 data, future matches, or external HTTP.

The target identity is the exact tuple of `match_id`, `match_date`, `season`,
`home_team_id`, and `away_team_id`. Source and output both contain 3,208
unique match IDs. Team identity is restricted to exact TeamMaster IDs.

| Season | Targets |
|---:|---:|
| 2015 | 306 |
| 2016 | 306 |
| 2017 | 306 |
| 2018 | 306 |
| 2019 | 306 |
| 2020 | 306 |
| 2021 | 380 |
| 2022 | 306 |
| 2023 | 306 |
| 2024 | 380 |
| **Total** | **3,208** |

## Pair identity and chronology

The internal pair identity is exactly the unordered TeamMaster-ID key:

```python
tuple(sorted((home_team_id, away_team_id)))
```

It is not written to the output. Targets are processed in `match_date`, then
string `match_id`, order. A target on date `D` can use only exact-pair matches
whose date is strictly less than `D`.

Processing is conservative by date: every target on a date is emitted from
the state at the beginning of that date, and only then are all results from
that date applied. Target-own, same-date, future-date, and inferred kickoff
order information are excluded. One team appearing in two scoped matches on
one date is a hard failure.

Pair state carries across season boundaries without reset. It begins empty at
the 2015 scope boundary. Pre-2015 meetings are neither loaded nor inferred;
therefore zero means no meeting in the available 2015-and-later prefix, not no
meeting in all football history.

## Frozen candidates and target-home orientation

The model-candidate family is exactly these three columns, in this order:

1. `prior_h2h_match_count`: number of strictly prior exact-pair matches.
2. `prior_h2h_home_team_win_count`: strictly prior wins by the current
   target's home team, regardless of its orientation in the historical match.
3. `prior_h2h_draw_count`: strictly prior exact-pair draws.

For every historical result, `2` increments the historical home team's wins,
`0` increments the historical away team's wins, and `1` increments draws.
The current target home team's count is selected only when emitting the
target. Target-away wins are intentionally absent and can be derived as total
minus target-home wins minus draws.

When no prior history exists, all three candidates are structural observed-
prefix zeros, `h2h_available` is false, and both previous-match audit fields
are null. This is not imputation. Candidate values are always non-null
integers.

## Exact output schema

The CSV has exactly 11 columns in this order:

| Position | Column | Logical type |
|---:|---|---|
| 1 | `match_id` | string |
| 2 | `match_date` | ISO `YYYY-MM-DD` |
| 3 | `season` | integer |
| 4 | `home_team_id` | string |
| 5 | `away_team_id` | string |
| 6 | `h2h_available` | boolean |
| 7 | `previous_h2h_match_id` | nullable string |
| 8 | `previous_h2h_match_date` | nullable ISO `YYYY-MM-DD` |
| 9 | `prior_h2h_match_count` | non-null integer |
| 10 | `prior_h2h_home_team_win_count` | non-null integer |
| 11 | `prior_h2h_draw_count` | non-null integer |

For an available row, the previous-match fields identify the exact pair's
latest strictly prior ordinary-J1 match, and its date is earlier than the
target date. For an unavailable row, both fields are null.

## Availability

Availability was rederived from the materialized state, not copied onto rows.

| Season | Targets | Available | Unavailable |
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

The global `prior_h2h_match_count` bins are exact and mutually exclusive:

| Prior count | Rows |
|---:|---:|
| 0 | 376 |
| 1 | 376 |
| 2 | 265 |
| 3 | 265 |
| 4 | 224 |
| 5-9 | 860 |
| 10+ | 842 |
| **Total** | **3,208** |

## Actual label-free candidate distributions

These are source distributions only. No association with the target result
was inspected.

| Candidate | Min | Median | Mean | Max |
|---|---:|---:|---:|---:|
| `prior_h2h_match_count` | 0 | 5.0 | 6.164589 | 19 |
| `prior_h2h_home_team_win_count` | 0 | 2.0 | 2.350062 | 13 |
| `prior_h2h_draw_count` | 0 | 1.0 | 1.435162 | 7 |

Exact integer frequencies:

```text
prior_h2h_match_count
0:376, 1:376, 2:265, 3:265, 4:224, 5:224, 6:162, 7:162,
8:156, 9:156, 10:127, 11:127, 12:109, 13:109, 14:85, 15:85,
16:64, 17:64, 18:36, 19:36

prior_h2h_home_team_win_count
0:917, 1:612, 2:459, 3:363, 4:271, 5:195, 6:149, 7:104,
8:58, 9:44, 10:25, 11:5, 12:4, 13:2

prior_h2h_draw_count
0:1144, 1:845, 2:509, 3:352, 4:192, 5:95, 6:55, 7:16
```

## Validation and leakage audit

An independent validator filters source events by exact pair and
`historical_match_date < target_match_date`; it does not trust the builder's
accumulated state. Results:

| Check | Result |
|---|---:|
| Exact schema | PASS |
| Target identity | PASS |
| Chronology | PASS |
| Target-home reorientation | PASS |
| Latest previous H2H mismatch | 0 |
| Target-own result use | 0 |
| Same-date result use | 0 |
| Future-date result use | 0 |
| Invariant failures | 0 |
| Deterministic byte-identical rebuild | PASS |

Every row satisfies nonnegative integer counts, target-home wins plus draws
less than or equal to total, and nonnegative integer derived target-away wins.
For every pair state, both teams' wins plus draws equal total matches.

## Serialization and write safety

Output path:

```text
data/processed/features/2015_2024_j1_h2h_features.csv
```

The file is covered by the existing `/data/processed/*` ignore rule; no
`.gitignore` change was made. Serialization is UTF-8 with a header, no index,
LF (`\n`) line endings, and empty fields as the single null representation.
A reversed-input rebuild produced identical rows, order, values, and bytes.
Production publication used a temporary file and atomic rename, and refuses
to overwrite an existing output.

SHA-256:

```text
ab51fd674ee1665591e4b4b152a92f12ffd020211db3e541047c3066815784ff
```

## Closed boundaries

No target-away win candidate, latest-result feature, rate, points-per-match,
orientation split, recency, days-since value, last-3/last-5 window, year
window, EWMA, decay, weight, ratio, or interaction was added. The older
`src/features/matchup_context.py` last-five semantics were not reused.

Stadium remains **DEFER_STADIUM** with
**STADIUM_PREMATCH_PROVENANCE_UNPROVEN**. Player workload, lineup continuity,
discipline, first score, goal timing, substitution timing, and starter-DF
lanes remain closed and were not reintroduced.

Final gate: **READY_FOR_H2H_EVALUATION_FREEZE**
