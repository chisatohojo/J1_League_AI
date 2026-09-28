# Ordinary J1 team substitution timing feature dataset

Status: **MATERIALIZED_AND_VALIDATED**.

Final gate: **READY_FOR_SUBSTITUTION_TIMING_EVALUATION_FREEZE**.

## Purpose

This dataset provides leakage-safe, current-season prior mean substitution
timing for each home and away team in ordinary-J1 target matches. It
materializes `docs/SUBSTITUTION_TIMING_FEATURE_SPEC.md` without fitting a
model, generating predictions, or evaluating predictive performance.

## Source and scope

- Target competition: ordinary J1 only
- Target seasons: 2015–2024
- Target rows: 3,208, one per unique match
- Event source:
  `data/processed/sfms02_match_events/2015_2024_j1_match_events.csv`
- Source SHA-256:
  `6eaaedbc7ffc5ad02a1207392924ff817e6356a08fbf64f3fbbfca9c62ec1131`
- Builder: `src/features/substitution_timing.py`
- Output:
  `data/processed/features/2015_2024_j1_substitution_timing_features.csv`
- Output SHA-256:
  `898c7d53ed429d36920fd67b218333d837f5d2604c99c3556e47584721b9161f`

The generated CSV is gitignored. No 2025, 2026/27, Hyakunen, League Cup,
Emperor's Cup, J2/J3, or AFC match is used. External HTTP requests were not
made.

## Source and normalized event reconciliation

Only `event_type=SUBSTITUTION` rows are used. One normalized SUB row is one
raw A7 OUT/IN pair and one substitution event. Existing materialization
metadata was checked before building:

| Item | Count |
|---|---:|
| Total normalized event rows | 39,987 |
| Normalized SUB rows | 23,638 |
| Raw A7 rows | 47,276 |
| Raw A7 : normalized SUB ratio | 2:1 |
| SUB-covered matches | 3,208 |
| Team-match sides | 6,416 |
| Positive-SUB sides | 6,410 |
| Zero-SUB sides | 6 |

All selected event IDs are nonblank and unique. Match, date, season,
team-side, source-section, and target-universe identities were exact. All SUB
minute and order fields were resolved; unresolved and unsupported SUB minutes
were zero. The source artifact was read-only.

`player_name_raw` and `related_player_name_raw` were not used in state,
joining, or calculation. No stable or inferred longitudinal player identity
is required.

## Frozen feature family

The exact two future model candidates are:

```text
home_mean_substitution_minute_normalized_prior
away_mean_substitution_minute_normalized_prior
```

Availability, event-count denominators, and minute sums are audit fields. No
substitution-count, first/last timing, zero-SUB rate, same-time frequency,
window, halftime, intent, player-specific, score-state, difference, ratio,
interaction, rolling, EWMA, smoothing, or regime-adjusted feature is present.

## Timing arithmetic and weighting

Each team's history maintains:

```text
prior_substitution_events
prior_substitution_minute_normalized_sum
```

Every history-eligible normalized SUB increments the event denominator by one
and adds its stored `minute_normalized` to the sum. The mean is
`sum / denominator`. This is SUB-event-weighted; no match-level mean is
calculated first.

The observed source minute range was exactly 3–90. Arithmetic follows the
source without elapsed-time conversion:

- `45'+N` contributes 45;
- `90'+N` contributes 90; and
- `46'` contributes 46 and is retained despite boundary ambiguity.

A team match with zero SUB events adds no observation and leaves denominator
and sum unchanged. Zero SUB is not encoded as minute 0, minute 90, null, or
another surrogate. The feature is conditional mean timing among observed SUB
events, not substitution frequency.

Multiple normalized events sharing one complete time key remain independent.
For example, three SUB events at minute 60 add three to the denominator and
180 to the sum. They are not collapsed into an inferred official window.
Halftime and tactical/injury/forced intent are not inferred.

## Chronology and availability

State resets at every season boundary. Every target uses only current-season
events from dates strictly before its match date. All targets on a date are
emitted from start-of-date state; that date's SUB events are applied only
after all target rows for the date are complete. Target-own and same-date peer
events cannot leak into features.

Availability is determined only by a positive prior SUB-event denominator:

- denominator 0: sum 0, mean null, availability false;
- denominator positive: mean equals sum/denominator, is finite and within
  3–90, availability true; and
- home and away availability are independent.

No value is imputed. The observed data happens to make only each team's first
seasonal target unavailable, but the builder implements denominator-based
availability rather than that empirical shortcut.

## Output schema

Identity:

```text
match_id
match_date
season
home_team_id
away_team_id
```

Availability:

```text
home_substitution_timing_available
away_substitution_timing_available
```

Audit denominators:

```text
home_prior_substitution_events
away_prior_substitution_events
```

Audit sums:

```text
home_prior_substitution_minute_normalized_sum
away_prior_substitution_minute_normalized_sum
```

Candidate means:

```text
home_mean_substitution_minute_normalized_prior
away_mean_substitution_minute_normalized_prior
```

## Availability audit

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

Global availability reconciliation:

- pair available: 3,116;
- pair unavailable: 92;
- team-side available: 6,232 of 6,416; and
- team-side unavailable: 184.

## History update audit

All 23,638 normalized SUB source observations were applied to team state after
their match dates, including events on a team's final target date. Of these,
22,968 observations have at least one strictly later same-season target for
the same team and therefore can reach a published downstream feature row.

“Total history updates applied” is thus 23,638 and is deliberately distinct
from “observations reaching a later target,” 22,968. The latter excludes
end-of-season or otherwise last-target events that are valid state updates but
have no later target to consume them.

- denominator/sum invariant failures: 0;
- partial-invalid output rows: 0; and
- target, same-date, and prior-season leakage: 0.

## Determinism and write safety

Output order is `match_date`, then string `match_id`. A rebuild from reversed
input row order produced identical rows, values, order, and CSV bytes before
publication. The formal output SHA-256 is:

```text
898c7d53ed429d36920fd67b218333d837f5d2604c99c3556e47584721b9161f
```

Publication used a temporary file followed by an atomic rename. An existing
output is never silently overwritten.

## Regime limitation

The reviewed feasibility audit found a large substitution-count distribution
break between 2019 and 2020. Count and regime-normalized features are excluded.
Mean timing was descriptively more stable but is not assumed regime-free and
has not been shown to be predictive. This materialization does not change the
frozen feature family in response to coverage or observed values.

## Validation outcome

Validation passed for:

- frozen source SHA and metadata reconciliation;
- exact target, event, match, and team-side counts;
- raw A7 2:1 pairing evidence;
- event identity and fully resolved 3–90 minute range;
- SUB-event weighting and zero-SUB semantics;
- same-time and 45/46/90 boundary semantics;
- season reset, prior-date chronology, and same-date batching;
- denominator, sum, mean, missingness, and availability invariants;
- all frozen season/global availability references;
- byte-identical deterministic rebuild; and
- all 20 required fixture contracts plus source-integrity hard-fail cases.

## Final gate and data discipline

**READY_FOR_SUBSTITUTION_TIMING_EVALUATION_FREEZE**

- Accuracy / Log Loss / Brier / AUC / correlation: **NOT COMPUTED**
- Model fitting: **NO**
- Predictions: **NO**
- Feature selection: **NO**
- Parameter tuning: **NO**
- 2025: **NOT USED**
- 2026/27: **NOT USED**
- external HTTP: **NO**
