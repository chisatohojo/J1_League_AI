# Pre-match rolling xG feature dataset

## Status

The frozen `v1` definition in [ROLLING_XG_FEATURE_SPEC.md](ROLLING_XG_FEATURE_SPEC.md) is implemented by `src/features/rolling_xg.py` and materialized at:

```text
data/processed/features/2025_2026_27_j1_rolling_xg_features.csv
```

The output has **660 unique match rows**. This task built and validated features only. It did not fit a model, generate a prediction, calculate Accuracy, Log Loss or Brier score, inspect feature importance, or compare windows.

## Sources and exact linkage

| Partition | Source rows | Feature rows | Exact identity mismatches |
|---|---:|---:|---:|
| 2025 ordinary J1 | 380 | 380 | 0 |
| 2026 J1 100 Year Vision League | 200 | 200 | 0 |
| 2026/27 ordinary J1 completed through round 8 | 80 | 80 | 0 |
| **Total** | **660** | **660** | **0** |

Each xG row was joined to its existing normalized match row by `match_id`, then checked for exact `match_date`, `home_team_id`, and `away_team_id`. Reference names were resolved through TeamMaster with `source="jleague_data_site"`; no trimming, Unicode normalization, canonical-name fallback, fuzzy matching, or new alias was used.

The three production xG source CSVs were read only and were not rewritten.

## Frozen calculation

For each club and target match, the builder computes arithmetic means over the last five eligible completed matches:

- `xg_for` is the club's own xG, regardless of whether it was home or away.
- `xg_against` is its opponent's xG.
- home and away appearances share one team history.
- every eligible match has weight `1.0`.
- history continues without reset from 2025 ordinary J1 through the 100 Year Vision League and into 2026/27 ordinary J1.

The four production model-candidate fields are:

- `home_last5_xg_for`
- `home_last5_xg_against`
- `away_last5_xg_for`
- `away_last5_xg_against`

No xG difference, shots, shots-on-target, finishing deviation, decay, competition weight, venue split, clipping, or imputation was added.

## Chronology and same-date batching

Features for all matches on a calendar date are generated from the state at the start of that date. Only after every row on that date has been generated are eligible observations appended to history. `match_id` orders stored rows deterministically but never establishes within-date causality.

The complete provenance audit compared every history match date with its target date:

- same-date or future history references: **0**
- target self-references: **0**
- history count range: **0–5**

The production CSV omits history ID lists. The in-memory result retains them in `DataFrame.attrs["rolling_xg_history_audit"]`, and `rolling_xg_history_audit()` returns a detached table for tests and diagnostics.

## Extra-time exclusion

100 Year Vision match `33017` remains present as a normal target row. Its pre-match features are generated from prior eligible history.

Because its official-final xG time scope is unresolved, its own xG is not appended to either club's later history:

- excluded source rows: `33017` only
- later history lists containing `33017`: **0**
- target row `33017` present: **yes**

`xg_history_excluded_source_match` identifies the source row. Per-side cumulative prior exclusion counts are audit fields; no value is estimated or corrected.

## Insufficient history and availability

A side is available only with five eligible prior observations. With zero through four observations, both rolling values are null. They are not zero-filled, forward-filled, or replaced by league/team means.

| Competition | Rows | Home available | Away available | Pair available | Unavailable team appearances |
|---|---:|---:|---:|---:|---:|
| 2025 ordinary J1 | 380 | 330 | 330 | 328 | 100 |
| 2026 100 Year Vision | 200 | 194 | 191 | 186 | 15 |
| 2026/27 ordinary J1 | 80 | 80 | 80 | 80 | 0 |
| **Total** | **660** | **604** | **601** | **594** | **115** |

There are **66 pair-unavailable matches** and **594 pair-available matches**. Promoted or newly observed clubs receive no special treatment; they become available only after accumulating their own five eligible observations.

## Output schema

| Columns | Meaning |
|---|---|
| `competition`, `season`, `match_id`, `match_date` | Exact target identity |
| `home_team_id`, `away_team_id` | Stable TeamMaster identities |
| four `*_last5_xg_*` columns | Nullable last-five arithmetic means |
| `home_xg_history_count`, `away_xg_history_count` | Eligible count capped at five |
| `home_xg_available`, `away_xg_available` | True exactly when count is five |
| `xg_pair_available` | True only when both sides are available |
| two `*_prior_xg_scope_exclusion_count` columns | Cumulative pre-target scope exclusions for audit |
| `xg_history_excluded_source_match` | Whether this target's source observation is excluded from later history |

Validation confirmed that unavailable sides always have null rolling values and available sides always have non-null, nonnegative rolling means.

## Manual chronology spot checks

The following histories were reconstructed directly from the in-memory audit. IDs are ordered oldest to newest within the five-match window.

| Segment | Target | Home prior IDs | Away prior IDs | Home xG for/against | Away xG for/against |
|---|---|---|---|---:|---:|
| 2025 opening | `31361` | none | none | null/null | null/null |
| 2025 mid-season | `32343` | `32293,32304,32316,32324,32336` | `32297,32309,32314,32328,32335` | 1.150/1.366 | 1.684/0.894 |
| 100 Year Vision opening | `32923` | `32484,32494,32507,32514,32521` | `32482,32491,32510,32512,32523` | 1.664/0.942 | 0.918/1.054 |
| 100 Year Vision mid-season | `33061` | `33035,33042,33046,33051,33057` | `33036,33042,33045,33048,33053` | 1.668/1.280 | 0.930/1.228 |
| 2026/27 opening | `34517` | `33089,33095,33102,32997,33020` | `33089,33096,33099,32986,33015` | 1.174/0.982 | 1.288/1.286 |
| Current completed boundary | `34595` | `34541,34548,34566,34569,34580` | `34545,34556,34559,34575,34586` | 1.044/1.666 | 1.634/0.992 |

The opening 100 Year Vision row demonstrates continuity from 2025. The opening 2026/27 row demonstrates continuity from the special competition. The final sample demonstrates that completed 2026/27 matches update later dates.

## Future 300 fixtures

The 300 fixtures that were future at the specification freeze timestamp (`2026-09-22T07:16:21+09:00`) are deliberately absent. Pre-generating their values now would make later-round histories stale because intervening completed xG does not yet exist.

Future features must be generated point-in-time from matches completed strictly before each target date, using the same frozen five-match, same-date batch, scope exclusion, and missing-value rules. The future fixture results and xG were neither read nor generated in this task.

## Leakage and evaluation discipline

2025 and the first 80 matches of 2026/27 are opened data. Their feature values were generated solely to establish a historical production dataset and validate chronology/availability. No outcome performance was inspected.

This dataset does not authorize model fitting or evaluation. Any future challenger must follow the frozen baseline-fallback interface and the prospective boundary in the specification without changing the feature definition after outcomes are opened.
