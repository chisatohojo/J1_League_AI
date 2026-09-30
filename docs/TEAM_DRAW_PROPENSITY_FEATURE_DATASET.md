# Ordinary-J1 team draw propensity feature dataset

Status: **`READY_TO_FREEZE_DRAW_PROPENSITY_EVALUATION`**.

The frozen specification in `TEAM_DRAW_PROPENSITY_FEATURE_SPEC.md` has been
materialized and validated. This status means that the dataset, provenance,
schema, and SHA-256 are fixed sufficiently for a separate task to freeze an
evaluation contract. It is not permission to run an evaluation.

No model was fitted, no prediction was generated, and no Accuracy, Log Loss,
Brier, coefficient, feature importance, target correlation, mutual
information, 2025 evaluation, or 2026/27 evaluation was calculated.

## 1. Artifact and source scope

| Item | Materialized value |
|---|---:|
| Ordinary-J1 seasons | 2015–2024 |
| Target rows | 3,208 |
| Unique `match_id` values | 3,208 |
| Team sides | 6,416 |
| Output columns | 21 |
| File bytes | 402,605 |
| Physical CSV lines | 3,209 (header + 3,208 rows) |

Output:

```text
data/processed/features/2015_2024_j1_draw_propensity_features.csv
```

SHA-256:

```text
97b33269a11b62f94dbd4b83924b97cc1cb1cb250ae0eb636ca5d8ccc6ba36a5
```

The artifact is generated data and remains ignored by the repository's
`/data/processed/*` policy. It was not force-added to Git.

Only the ten fixed local
`data/processed/jleague/{2015..2024}_matches_probe.csv` files and the existing
TeamMaster were loaded. Season counts are:

| Season | Targets | Team sides |
|---:|---:|---:|
| 2015 | 306 | 612 |
| 2016 | 306 | 612 |
| 2017 | 306 | 612 |
| 2018 | 306 | 612 |
| 2019 | 306 | 612 |
| 2020 | 306 | 612 |
| 2021 | 380 | 760 |
| 2022 | 306 | 612 |
| 2023 | 306 | 612 |
| 2024 | 380 | 760 |
| **Total** | **3,208** | **6,416** |

2025, 2026/27, Hyakunen, League Cup, Emperor's Cup, J2/J3, AFC, and external
HTTP were not used.

## 2. Exact schema and model candidates

The artifact has exactly this ordered 21-column schema:

```text
match_id
match_date
season
home_team_id
away_team_id
home_last5_draws
home_last5_matches
home_last5_draw_rate
away_last5_draws
away_last5_matches
away_last5_draw_rate
home_season_prior_draws
home_season_prior_matches
home_season_prior_draw_rate
away_season_prior_draws
away_season_prior_matches
away_season_prior_draw_rate
mean_draw_rate_last5
abs_draw_rate_diff_last5
mean_season_prior_draw_rate
abs_season_prior_draw_rate_diff
```

Only the final four columns are frozen model candidates, in this exact order:

```text
mean_draw_rate_last5
abs_draw_rate_diff_last5
mean_season_prior_draw_rate
abs_season_prior_draw_rate_diff
```

The first five columns are target identity and the next 12 are audit and
provenance fields. Result and score are not output columns.

## 3. Last-five source and reconciliation

The builder directly called `src/features/form.py::add_form_features` on the
validated and sorted ordinary-J1 stream. It did not implement another
last-five rolling state.

It directly reused `home_last5_draws` and `away_last5_draws`. Denominators were
calculated from the same form output as:

```text
last5_matches = last5_wins + last5_draws + last5_losses
```

Both materialized draw-count columns reconcile exactly to the existing form
output for **3,208 / 3,208** match IDs. Denominators never exceed five. Form
history combines home and away appearances, continues across seasons, and
starts empty at the 2015 left boundary.

## 4. Current-season state and chronology

The only new history state is keyed by `(season, team_id)` and contains prior
draw and match counts. It resets to zero at every season boundary.

Input was normalized and sorted by calendar `match_date`, then string
`match_id`. For each date, the builder read and emitted every target's
current-season state before applying any result from that date. Target-own
result uses, same-date peer-result uses, repeated same-date team appearances,
and chronology violations were all **0**.

Last-five values are also strictly pre-match. The source invariant forbids a
team from appearing in two matches on one date, so a same-date peer result
cannot enter that team's existing form state.

## 5. Null semantics and invariants

For both last-five and current-season side histories:

```text
matches == 0  => draws == 0 and rate is null
matches > 0   => rate == draws / matches
```

Each derived pair is null if either required side rate is null. CSV nulls are
serialized as blank fields. No zero, `1/3`, league mean, smoothing, shrinkage,
forward fill, or backward fill was applied.

Observed side-rate nulls are:

| Family | Home null | Away null | Team-side null total | Derived null per candidate |
|---|---:|---:|---:|---:|
| Last five | 14 | 16 | 30 | 21 |
| Current season | 92 | 92 | 184 | 92 |

Counts below zero, draws above their denominator, last-five denominators above
five, non-null non-finite rates, rates outside `[0,1]`, derived formula
mismatches, null-propagation failures, identity failures, and schema failures
were all **0**.

## 6. Coverage by season and globally

Bins are team-side counts except `Targets` and `Both full last-5`.

| Season | Targets | Season prior 0 | 1–4 | 5+ | Last-5 0 | 1–4 | 5 | Both full last-5 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 18 | 72 | 522 | 18 | 72 | 522 | 261 |
| 2016 | 306 | 18 | 72 | 522 | 3 | 12 | 597 | 293 |
| 2017 | 306 | 18 | 72 | 522 | 2 | 8 | 602 | 297 |
| 2018 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2019 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2020 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2021 | 380 | 20 | 80 | 660 | 1 | 4 | 755 | 375 |
| 2022 | 306 | 18 | 72 | 522 | 1 | 4 | 607 | 301 |
| 2023 | 306 | 18 | 72 | 522 | 0 | 0 | 612 | 306 |
| 2024 | 380 | 20 | 80 | 660 | 2 | 8 | 750 | 370 |
| **Global** | **3,208** | **184** | **736** | **5,496** | **30** | **120** | **6,266** | **3,106** |

All season and global values exactly reproduce the frozen references.

## 7. Label-free candidate distributions

These summaries use feature values only. No target outcome relationship was
calculated.

| Candidate | Non-null | Null | Min | Median | Mean | Max | Unique |
|---|---:|---:|---:|---:|---:|---:|---:|
| `mean_draw_rate_last5` | 3,187 | 21 | 0.0 | 0.2 | 0.249990 | 0.9 | 25 |
| `abs_draw_rate_diff_last5` | 3,187 | 21 | 0.0 | 0.2 | 0.205585 | 1.0 | 21 |
| `mean_season_prior_draw_rate` | 3,116 | 92 | 0.0 | 0.25 | 0.259262 | 1.0 | 753 |
| `abs_season_prior_draw_rate_diff` | 3,116 | 92 | 0.0 | 0.1 | 0.142282 | 1.0 | 708 |

No distribution was used to alter a candidate, window, formula, missingness
rule, or feature subset.

## 8. Determinism and artifact validation

The builder was run on the canonical input, reversed input, and a repeated
copy. Canonical serialization, reversed-input serialization, and repeated
serialization were byte-identical.

The production materializer was then run again to a separate temporary path.
That file had 3,208 rows, 21 columns, the same SHA-256, and bytes exactly equal
to the published artifact. The temporary directory was removed after the
comparison.

Serialization is comma-delimited UTF-8 without BOM, CSV-minimal quoting, LF
line endings, blank nulls, and one centrally defined float format. Publication
was atomic and refused overwrite. Deterministic rebuild and byte-identical
status are both **PASS**.

## 9. Validation result and next gate

- Source rows: **3,208**
- Output rows: **3,208**
- Output columns: **21**
- Unique match IDs: **3,208**
- Form reconciliation: **3,208 / 3,208**
- Coverage-reference failures: **0**
- Chronology violations: **0**
- Invariant failures: **0**
- Deterministic rebuild: **PASS**
- Byte-identical temporary rebuild: **PASS**
- Materialization tests: **39 passed**
- Full pytest: **2,242 passed / 0 failed / 26 warnings**
- Predictive evaluation: **NOT RUN**
- Feature variants added: **NO**

Final gate: **`READY_TO_FREEZE_DRAW_PROPENSITY_EVALUATION`**.

The next task may freeze, but must not silently execute, a one-time evaluation
contract against the fixed SHA-256 above. Null preprocessing remains
unselected until that contract is frozen.
