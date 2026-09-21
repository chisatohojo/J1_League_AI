# Pre-match rolling xG feature specification

## Status

- Specification version: `v1`
- Frozen at: `2026-09-22T07:16:21+09:00`
- Status: **FROZEN BEFORE PROSPECTIVE EVALUATION**
- Primary purpose: define one small, leakage-safe rolling xG feature group for a future challenger to the existing frozen Elo baseline.

This document fixes the feature definition before any evaluation of that challenger. It does not create a feature dataset, fit a model, generate predictions, or calculate Accuracy, Log Loss, Brier score, or feature importance.

## Evidence and scope

The source of truth is:

- [JLEAGUE_MATCH_XG_DATASET.md](JLEAGUE_MATCH_XG_DATASET.md)
- [2026_MATCH_XG_COVERAGE_AUDIT.md](2026_MATCH_XG_COVERAGE_AUDIT.md)
- [J_STATS_MATCH_LEVEL_ROUTE_DEEP_AUDIT.md](J_STATS_MATCH_LEVEL_ROUTE_DEEP_AUDIT.md)
- [MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md)
- [PROJECT_STATUS_2026_09_20.md](PROJECT_STATUS_2026_09_20.md)

The production source contains 660 official post-match observations with complete two-sided xG, shots, and shots on target:

| Competition | Matches | Role in this specification |
|---|---:|---|
| 2025 ordinary J1 | 380 | rolling history; ordinary-J1 model target candidates |
| 2026 J1 100 Year Vision League | 200 | rolling history only |
| 2026/27 ordinary J1 through round 8 | 80 | opened rolling history; ordinary-J1 model target candidates, never prospective evaluation targets |

The official public match-level advanced-stat route is not available consistently before late 2024, and the first complete ordinary-J1 season is 2025. This feature therefore does not claim 2015–2024 coverage and must not be retrofitted with season aggregates or inferred xG.

## Frozen decisions

| Item | Decision |
|---|---|
| Primary window | Last 5 eligible completed matches |
| Aggregation | Arithmetic mean per match |
| Competition transition | Continuous team history; no reset |
| 100 Year Vision treatment | Carry into 2026/27 ordinary J1 with weight 1.0 |
| Same-date treatment | Start-of-date state for every match; batch update after the date |
| Extra-time scope ambiguity | Exclude the one unresolved-scope observation from primary history |
| Minimum history | 5 eligible prior matches |
| Missing values | Nullable; never zero-filled or team-mean-imputed |
| Home/away split | None; one overall team history |
| Missing-history prediction | Exact fallback to the frozen baseline |
| First challenger group | Four xG means only; no shots, SOT, or goal-minus-xG fields |

No alternative window, decay, competition weight, clipping rule, or threshold is authorized by this specification.

## Observation construction

Each eligible completed source match produces one observation per team:

| Team role | `xg_for` | `xg_against` |
|---|---|---|
| Home | `home_xg` | `away_xg` |
| Away | `away_xg` | `home_xg` |

The observation key must retain at least competition, source match identity, match date, and stable `team_id`. Team identity must be exact and stable; fuzzy matching is prohibited.

Only numeric, two-sided official match-level xG is eligible. Translation labels, season aggregates, inferred values, or one-sided values do not qualify. Shots and shots on target remain source columns but are outside this first feature group.

## Chronology and leakage protection

For target match date `D`, a team's rolling history may contain only eligible observations with:

```text
history.match_date < D
```

The target match itself and every future match are excluded. `match_id` is used only for deterministic storage and output ordering; it must not create a causal order among matches on the same date.

All matches on one calendar date form a batch:

1. Freeze the history state at the start of the date.
2. Generate every target feature on that date from that same state.
3. Do not let same-date matches become mutual history.
4. After all matches on the date are complete, append their eligible observations in one batch.

This conservative policy matches the existing project chronology safeguards for Elo, Domestic Rest, and player workload. It remains the `v1` rule even if exact kickoff times become available later; changing to intraday updates would require a new specification and evaluation cycle.

## Competition transition policy

Team history is continuous across:

```text
2025 ordinary J1
    -> 2026 J1 100 Year Vision League
    -> 2026/27 ordinary J1
```

There is no season or competition reset. Every eligible match has weight `1.0`; the 100 Year Vision League is neither down-weighted nor up-weighted.

This is the most conservative non-tuned policy that preserves recent official information for the same clubs. A reset would discard the immediately preceding competitive history, while a special competition weight would introduce an unfitted parameter. The competitions' format difference remains a limitation, but it is not converted into an outcome-driven adjustment.

The 100 Year Vision rows are history observations only. They are not ordinary-J1 Logistic training targets under this feature specification.

## Extra-time policy

Source match `33017` is marked `score_scope_status=EXTRA_TIME_SOURCE_SCORE` and `xg_time_scope=OFFICIAL_FINAL_SCOPE_UNRESOLVED`. The official summary does not safely establish whether its xG covers 90 or 120 minutes.

The primary rolling feature therefore excludes that match's xG observation for both clubs. It is not corrected, divided, converted to a 90-minute estimate, or silently treated as regulation-time xG. The source row remains in the production dataset with its quality fields intact.

The rolling window is the last five **eligible** observations. An excluded unresolved-scope match does not consume one of those five positions. Its prior occurrence is exposed through an audit-only exclusion count, not through a model feature.

## Primary rolling window

The primary window is a fixed window of the last **5 eligible completed matches** for that team, independent of venue and competition.

For team `t` before target date `D`:

```text
H(t, D) = the five most recent eligible team observations with match_date < D

rolling_xg_for     = mean(xg_for over H(t, D))
rolling_xg_against = mean(xg_against over H(t, D))
```

A match-count window is used instead of a calendar-day window because xG is a per-match performance observation. Five observations preserve a consistent denominator across fixture gaps, postponements, and off-season transitions. A day window would mix performance with schedule density, which is already represented by the separate Domestic Rest and workload feature families.

Five is frozen as a modest recent-form horizon, not selected from 2025 or the opened 2026/27 results. No last-3, last-10, day-window, EWMA, or decay comparison is permitted in this research cycle. No secondary diagnostic window is defined.

## Final feature contract

The first xG challenger may consume only these four numeric xG fields:

- `home_last5_xg_for`
- `away_last5_xg_for`
- `home_last5_xg_against`
- `away_last5_xg_against`

The feature dataset contract must also expose these routing and audit fields:

- `home_last5_xg_history_count`
- `away_last5_xg_history_count`
- `home_last5_xg_available`
- `away_last5_xg_available`
- `home_prior_xg_scope_exclusion_count`
- `away_prior_xg_scope_exclusion_count`

`history_count` is the number of eligible observations available to the rolling calculation, capped at 5. `available` is `1` only when `history_count == 5`; otherwise it is `0`. Scope-exclusion counts are cumulative pre-target audit metadata and are not model features.

The following are deliberately excluded from the first group:

- `rolling_xg_diff`: it is a deterministic linear combination of xG for and against.
- shots and shots on target: they would create a separate feature experiment.
- goals-for-minus-xG and goals-against-minus-xGA: they add score semantics and a separate finishing/prevention hypothesis.
- venue-specific rolling values: a five-match home/away split would fragment an already short history.
- sums, clipping, winsorization, log transforms, decay, or competition normalization.

Raw rolling xG means are emitted. Any eventual `StandardScaler` must be fitted on model-training rows only.

## Insufficient history and promoted clubs

If a team has fewer than five eligible prior observations:

- both numeric rolling means for that team are null;
- `history_count` reports `0` through `4`;
- `available=0`;
- no zero fill is allowed;
- no league, team, promoted-club, or opponent mean imputation is allowed.

The same rule applies to promoted, newly admitted, renamed, or newly observed clubs. History may follow a club only through an already verified stable `team_id`; names alone do not transfer history. A club without five official source observations remains unavailable until it accumulates five.

## Home and away treatment

The rolling history is team-centric and combines the club's home and away matches. The current target side only determines whether that team's values populate the `home_*` or `away_*` output columns.

No home-only or away-only xG history is created in `v1`. This avoids doubling the feature count and avoids estimating means from very small venue-specific samples.

## Missing semantics and baseline fallback

The future comparison has two deterministic prediction paths:

1. **Both teams available:** the xG challenger may use the frozen baseline inputs plus the four numeric xG fields.
2. **Either team unavailable:** return the exact frozen baseline probability vector for that match.

There is no probability blending and no fitted fallback weight. Availability and history counts route the prediction but are not additional challenger model features. Consequently, the challenger remains defined for every prospective target without pretending that missing xG equals zero.

If an xG challenger is later fitted, its xG branch may be fitted only on ordinary-J1 training rows where both teams are available. The baseline branch retains its own frozen training protocol. The estimator, training cutoff, and preprocessing must be frozen in a separate evaluation protocol before any prospective metric is opened.

## Separation from other feature groups

This specification covers xG only. Domestic Rest, player workload, suspensions, lineup information, and other availability signals remain separate feature groups. They must not be combined with xG in the first xG challenger evaluation.

Likewise, the 100 Year Vision competition's use as xG history does not alter its separate Elo, Rest, or Logistic-target policies.

## Opened-data discipline

- 2025 is already a spent test and cannot select this window, feature set, missing rule, or transition policy.
- The first 80 completed 2026/27 ordinary-J1 matches are already opened and cannot be evaluation targets for this feature group.
- Their xG may be used as lagged history for later targets and, if the later model protocol permits, as pre-freeze fitting data. Their observed performance must not be used to revise this specification.
- No xG model metric, prediction, feature importance, or window comparison was calculated while writing this document.

## Prospective evaluation protocol

The prospective boundary is the specification freeze timestamp:

```text
2026-09-22T07:16:21+09:00
```

The untouched target cohort is the set of 2026/27 ordinary-J1 fixtures that were still future at that timestamp. Under the current 380-match schedule this is 300 fixtures following the opened first 80, operationally beginning with the first ordinary-J1 kickoff after the freeze (expected from round 9 onward).

The boundary is based on official match identity and kickoff status, not solely on a round label. A postponed earlier-round match played after the freeze is eligible; a nominal round-9 match already completed before the freeze would not be. Before any evaluation, persist a target manifest containing the 300 official match identities and their freeze-time schedule status without outcomes or probabilities.

One prospective evaluation is to be run after the fixed cohort has completed, rather than repeatedly inspecting interim metrics. Rescheduling may change chronology, but it must not change cohort membership except for an officially cancelled match that never produces a completed result; such exclusions must be documented without replacement.

For every prospective target:

- use only xG observations from dates strictly before the target date;
- use the same-date batch policy;
- never use the target's own xG, score, shots, or result;
- never use future observations;
- apply the frozen eligibility, five-match, transition, and fallback rules unchanged.

The first 80 opened matches are history/development data only. A later descriptive full-season 380-row summary must be clearly separated from the untouched prospective result and must not be presented as a fresh holdout.

After results are opened, no last-window change, competition weighting, reset, clipping, missing-value rule, feature addition/removal, or baseline adjustment is allowed. Any materially new source or hypothesis starts a separate research cycle.

## Implementation acceptance criteria for a later task

A future implementation must demonstrate, before model fitting:

- exact 660-row source linkage at the current source cutoff;
- deterministic team-observation construction;
- no target or future observation in history;
- no same-date mutual history;
- exclusion of unresolved-scope match `33017` from the primary rolling input;
- no zero or mean imputation;
- stable five-observation means and counts;
- baseline fallback whenever either side is unavailable;
- no modification of the existing frozen baseline;
- deterministic output under input row reordering.

These checks authorize feature construction only. They do not authorize model selection or evaluation against already opened outcomes.
