# J1–J2 Cup bridge Elo formal evaluation freeze specification

Status: **`FROZEN_FOR_ONE_CUP_BRIDGE_EVALUATION`**

Freeze date: 2026-09-29

This document freezes one retrospective expanding-window evaluation. It does
not authorize a formal run in this task. No model was fit, no prediction was
generated, no target-result association was performed, and no Accuracy, Log
Loss, or Brier value was newly calculated while preparing this specification.

Sources of truth are:

- `docs/CUP_J1_J2_REGULATION_RESULT_DATASET.md`;
- `docs/CUP_J1_J2_REGULATION_RESULT_FEASIBILITY.md`;
- `docs/J1_J2_CROSS_DIVISION_BRIDGE_AUDIT.md`;
- `docs/ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md`;
- `docs/H2H_EVALUATION_FREEZE_SPEC.md`;
- `src/modeling/player_workload_evaluation.py` for the known-good J1-only Elo,
  pipeline, probability, and metric contracts; and
- the existing J1+J2 rolling-validation implementation for B's input and
  population contract, subject to the stricter same-date batching frozen here.

## 1. Single research question

The formal run asks exactly one question:

> Does adding the frozen 145 J1–J2 Cup bridge events, using only their
> regulation-time results, to the common J1+J2 league Elo stream improve
> ordinary-J1 three-class probability prediction?

The Cup bridge is the only authorized difference between B and C. The formal
run must also compare C with the current J1-only production reference A. No
other feature, rating policy, parameter, data source, or target population may
change.

## 2. Frozen Cup artifacts

The future evaluator must hash the actual bytes of both files before any
model fit and assert exact equality.

| Artifact | Exact path | Rows | SHA-256 |
|---|---|---:|---|
| Candidate manifest | `data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_candidates.csv` | 145 | `f44aa8785c80b48dc03acc4c206cbd59c4acc048d22d59579c865fbe990b5dc3` |
| Regulation result dataset | `data/processed/cup_regulation_results/2015_2024_j1_j2_bridge_regulation.csv` | 145 | `f7dc0151299a01d8dcad5e0a1235759cad53d9784740bf81320cc0b5fb985b64` |

An absent file, byte mismatch, or hash mismatch is a hard failure. The run
must stop as `BLOCKED_ARTIFACT_MISMATCH`; A, B, and C must not be fit, no
formal metric may be calculated, and no adoption decision may be emitted.

The candidate manifest has exactly these columns in this order:

```text
candidate_key
competition
season
source_match_id
match_date
home_team
away_team
home_team_id
away_team_id
source_url
```

The result dataset has exactly these columns in this order:

```text
candidate_key
competition
season
source_match_id
match_date
home_team_id
away_team_id
regulation_home_score
regulation_away_score
regulation_result
extra_time_played
penalty_shootout_played
final_home_score
final_away_score
source_url
source_type
raw_sha256
resolution_status
resolution_reason
```

## 3. Exact Cup membership and pre-fit gate

The 145 candidates are immutable. Source availability, model output, or
diagnostics must never add, remove, replace, or reorder membership for
selection purposes.

| Season | J.League Cup | Emperor's Cup | Total |
|---:|---:|---:|---:|
| 2015 | 0 | 6 | 6 |
| 2016 | 0 | 5 | 5 |
| 2017 | 0 | 8 | 8 |
| 2018 | 16 | 12 | 28 |
| 2019 | 14 | 7 | 21 |
| 2020 | 1 | 1 | 2 |
| 2021 | 0 | 6 | 6 |
| 2022 | 12 | 14 | 26 |
| 2023 | 12 | 13 | 25 |
| 2024 | 13 | 5 | 18 |
| **Total** | **68** | **77** | **145** |

Before any fit, assert all of the following:

- both schemas and column orders are exact;
- both artifacts contain exactly 145 rows;
- `candidate_key` is unique in each artifact and the key sets are exactly
  equal;
- the competition counts are exactly 68 `jleague_cup` and 77
  `emperors_cup`;
- the season/competition distribution equals the table above;
- every result row has
  `resolution_status == "CONFIRMED_REGULATION_SCORE"`;
- unresolved rows are exactly zero;
- `regulation_home_score` and `regulation_away_score` are non-null,
  nonnegative integers;
- `regulation_result` is an integer in `{0, 1, 2}` and equals 2 when the
  regulation home score is greater, 0 when it is lower, and 1 when tied;
- manifest/result `competition`, `season`, `source_match_id`, `match_date`,
  `home_team_id`, and `away_team_id` match exactly by `candidate_key`;
- the manifest's `home_team_id` and `away_team_id` are non-null and different;
  and
- no team appears in more than one frozen Cup candidate on one calendar date.

The result artifact intentionally does not repeat the manifest's raw
`home_team`/`away_team` strings. Home/away identity equality therefore means
ordered stable TeamMaster IDs plus the exact candidate key, season, date, and
source match ID. The manifest SHA separately protects its raw names and source
URL. The result `source_url` is provenance for the score source and need not
equal the manifest detail URL, because 58 JFA results use season schedule JSON.

Any duplicate, null, invalid score, identity mismatch, distribution mismatch,
or unresolved row is a hard failure before fitting.

## 4. Evaluation population

Logistic training and validation targets are ordinary J1 matches only.

Permitted rating-history events are exactly:

- ordinary J1 league, 2015–2024;
- J2 league, 2015–2024, for B and C only; and
- the frozen 145 Cup bridge events, for C only.

The ordinary-J1 target source has 3,208 rows. The J2 history source has 4,538
rows. The future evaluator must reject seasons outside 2015–2024 and must not
read 2025, 2026/27, Hyakunen, AFC, J3, J1–J1 Cup, J2–J2 Cup, identity-unsafe
Cup rows, any Cup row outside the manifest, or any current lockbox artifact.

The five expanding folds are exact:

| Validation season | Training seasons | Train n | Validation n |
|---:|---|---:|---:|
| 2020 | 2015–2019 | 1,530 | 306 |
| 2021 | 2015–2020 | 1,836 | 380 |
| 2022 | 2015–2021 | 2,216 | 306 |
| 2023 | 2015–2022 | 2,522 | 306 |
| 2024 | 2015–2023 | 2,828 | 380 |

The concatenated validation population is exactly 1,678 ordinary-J1 rows.
A, B, and C must use identical training match IDs, validation match IDs,
validation order, and target labels within every fold. There is no eligibility
filter, matched subset, or fallback prediction.

## 5. Frozen A/B/C definitions

### A — current J1-only reference

- rating events: ordinary J1 only;
- every club starts at 1500;
- K-factor: 30;
- J1 home advantage: 175 inside expected-score calculation;
- model input: pre-match `home_rating - away_rating`, named `elo_diff`; and
- Logistic targets: ordinary J1 only.

A is the production reference and the only baseline used for adoption.
Stored predictions from another lane must not be copied. A must be freshly
replayed, fit, and evaluated in the formal evaluator.

### B — Equal J1+J2 league Elo

- rating events: ordinary J1 plus J2 league;
- one common rating population;
- every club starts at 1500, regardless of first division observed;
- K-factor: 30;
- J1 and J2 league home advantage: 175;
- no Cup rating event;
- model input: `elo_diff`; and
- Logistic training and validation targets: ordinary J1 only.

J2 matches update Elo state but are never Logistic rows. J2 initial=1400,
promotion reset, promotion calibration, returning-only hybrid, or any other
division policy is prohibited.

### C — Equal J1+J2 plus frozen Cup bridge

C is identical to B except that all 145 frozen Cup events are added to the
rating stream. No Cup row is a Logistic training or validation target. No
other difference from B is authorized.

## 6. Elo update contract

All event types use:

```text
initial rating = 1500
K = 30
actual home score = regulation_result / 2
rating scale = 400
```

For one event with event-specific home advantage `HA`:

```text
expected_home = 1 / (1 + 10 ** ((away_rating - (home_rating + HA)) / 400))
delta = 30 * (regulation_result / 2 - expected_home)
new_home_rating = home_rating + delta
new_away_rating = away_rating - delta
```

The event-specific home advantage is frozen as:

| Event | Home advantage |
|---|---:|
| Ordinary J1 league | 175 |
| J2 league | 175 |
| Frozen Cup bridge | **0** |

Cup `HA=0` is a provenance constraint, not a tuned value. The Cup home/away
slot does not prove ordinary-league-equivalent venue advantage for all 145
events. The formal run must not compare Cup HA 0 with 175 or any other value,
infer neutral venues, switch by competition, or use venue data.

Only `regulation_result` may update Cup Elo. `extra_time_played`,
`penalty_shootout_played`, `final_home_score`, `final_away_score`, match winner,
and tie winner are audit fields and must never affect Elo.

## 7. Chronology and same-date batching

Construct competition-qualified event keys:

```text
j1:<match_id>
j2:<match_id>
jleague_cup:<source_match_id>
emperors_cup:<source_match_id>
```

Event keys must be unique. Process events by normalized `match_date`.
Within one calendar date, use conservative batching:

1. read all event pre-match ratings for that date;
2. record every ordinary-J1 target's `elo_diff` from those pre-match ratings;
3. only after all reads are complete, apply every result from that date.

No kickoff/order inference is permitted. No event on a date can affect a J1,
J2, or Cup pre-match rating on that same date. The combined J1/J2/Cup stream
must reassert that no team has multiple event appearances on one date. A Cup
event can affect a target only when `cup.match_date < target.match_date`.

For deterministic auditing, sort dates ascending and event keys as strings
within a date. The sort is not permission to update sequentially within that
date.

The `elo_diff` model feature is always raw pre-match home rating minus raw
pre-match away rating. Do not add 175 or 0 to the feature itself.

## 8. Probability model

A, B, and C use the same single input in this exact order:

```python
(
    "elo_diff",
)
```

The pipeline is exactly:

```python
Pipeline(
    [
        ("scaler", StandardScaler()),
        (
            "logistic",
            LogisticRegression(
                C=1.0,
                solver="lbfgs",
                max_iter=1000,
                random_state=0,
            ),
        ),
    ]
)
```

The scaler and Logistic Regression fit only the fold's ordinary-J1 training
rows. Validation rows, J2 rows, and Cup rows must never enter scaler/model fit.
J2 and Cup affect only `elo_diff` through prior rating updates.

Class semantics and probability column order are exact:

```text
0 = Away win
1 = Draw
2 = Home win
class order = [0, 1, 2]
```

The evaluator must assert `model.classes_ == [0, 1, 2]`, probability shape
`(n, 3)`, finite values in `[0, 1]`, and row sums equal to one within the
existing numerical probability-validation contract.

## 9. Mandatory A reference gate

After all artifact/population/chronology gates pass, freshly replay and fit A
on all five folds. Use `rtol=0` and `atol=1e-12` for every A reference
assertion.

| Validation season | A Log Loss |
|---:|---:|
| 2020 | 1.023119734659012 |
| 2021 | 1.0253437210487792 |
| 2022 | 1.0940186385371449 |
| 2023 | 1.0604285568595655 |
| 2024 | 1.079241181120235 |

Pooled A references over the concatenated 1,678 rows are:

| Accuracy | Log Loss | Brier |
|---:|---:|---:|
| 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |

If any A reference differs, stop as `BLOCKED_REFERENCE_MISMATCH`. B and C must
not be fit, no B/C metric may be calculated or reported, and no formal
decision may be issued.

## 10. Mandatory B persisted-result sanity gate

Only after A passes may B be freshly replayed, fit, and evaluated. The only
persisted B metrics found in the repository have six-decimal precision:

| Accuracy | Log Loss | Brier |
|---:|---:|---:|
| 0.460072 | 1.057002 | 0.636552 |

No higher-precision persisted B value exists, and this freeze task must not
manufacture one. Compare B by exact six-decimal presentation:

```text
format(B accuracy, ".6f") == "0.460072"
format(B log loss, ".6f") == "1.057002"
format(B Brier, ".6f") == "0.636552"
```

These are sanity references, not values to substitute for fresh predictions.
No persisted B fold reference is frozen. If any pooled six-decimal check
differs, stop as `BLOCKED_REFERENCE_MISMATCH`; C must not be fit and no formal
decision may be issued.

## 11. Formal challenger gate order

The future evaluator must execute the following order:

1. hash and verify both frozen Cup artifacts;
2. validate both schemas, exact membership, Cup score invariants, and
   manifest/result identity;
3. load only the permitted J1/J2 history and validate all source seasons,
   identities, event keys, and row counts;
4. rederive and assert the five fold counts and 1,678-row pooled population;
5. validate the three stream definitions, event-specific HA, and chronology;
6. freshly replay, fit, and evaluate A;
7. assert every exact A fold and pooled reference;
8. freshly replay, fit, and evaluate B;
9. assert B's persisted pooled six-decimal sanity references; and
10. only then freshly replay, fit, and evaluate C once.

No C Elo replay that associates Cup results with J1 targets, no C fit, and no
C metric is permitted before all preceding gates pass.

## 12. Metrics and deltas

For every fold and pooled output, report:

- Accuracy;
- multiclass Log Loss with labels `[0, 1, 2]`; and
- multiclass Brier.

The Brier definition is exact:

```text
mean(sum((probability - one_hot_target) ** 2, axis=1))
```

Do not divide by three.

For pooled metrics, concatenate the five validation probability matrices and
labels in validation-season order and calculate once over all 1,678 rows.
Averaging fold metrics is prohibited.

Report per-fold and pooled deltas with challenger first:

```text
C - B  # isolation diagnostic
C - A  # production comparison
```

Lower Log Loss and Brier are better. Accuracy is descriptive only. B versus C
must not affect adoption.

## 13. Frozen production decision

For each fold:

```text
improved_vs_A = C Log Loss < A Log Loss
non_improved_vs_A = C Log Loss >= A Log Loss
```

Return exactly one status:

### `ADOPT_CUP_BRIDGED_ELO`

Only if all are true:

- pooled C Log Loss `<` pooled A Log Loss;
- pooled C Brier `<` pooled A Brier; and
- C Log Loss improves against A in at least 3 of 5 folds.

### `CLOSE_CUP_BRIDGE_LANE`

Only if all are true:

- pooled C Log Loss `>=` pooled A Log Loss;
- pooled C Brier `>=` pooled A Brier; and
- C Log Loss does not improve against A in at least 3 of 5 folds.

### `INCONCLUSIVE_NO_TUNING`

For every other outcome.

Accuracy, C-versus-B results, subgroup results, and event counts are forbidden
from the decision.

## 14. Diagnostic-only outputs

The formal report may include the following after the formal run:

- B-versus-C fold and pooled deltas;
- Cup event counts available in each fold's rating history;
- validation actual Away/Draw/Home counts;
- A/B/C argmax class counts;
- A/B/C mean Draw probability;
- returning-promoted subgroup metrics;
- first-time-promoted subgroup metrics; and
- promotion appearances 1–3 subgroup metrics.

Diagnostics are descriptive. They cannot change the frozen decision, create a
new threshold, authorize a subgroup model, or motivate another evaluation.

## 15. No adaptive follow-up

After the one formal result, this lane must not try:

- another Cup K or HA;
- competition-specific K or HA;
- League Cup only or Emperor's Cup only;
- season, promoted-club, returning-club, or other subsets;
- recency weighting or Cup match weighting;
- PK or extra-time winner;
- score margin;
- candidate additions, unresolved identities, or candidate reselection;
- target-derived calibration; or
- any other result-responsive parameter or feature search.

`INCONCLUSIVE_NO_TUNING` is a terminal no-tuning result, not permission for a
second variant. A poor result does not authorize “Cup K=15”, Cup HA=175, or a
different bridge subset.

## 16. Future implementation requirements

The next task may implement the evaluator and tests, but must not start formal
mode. At minimum its tests must prove:

1. both artifact SHA mismatches fail before any fit;
2. exact schemas, counts, season distribution, and unique candidate keys;
3. manifest/result ordered stable identity equality;
4. score/result invariants and zero unresolved rows;
5. forbidden seasons and competitions are rejected;
6. A/B/C use identical J1 fold rows and labels;
7. fold and pooled counts are exact;
8. class/probability order is `[0, 1, 2]`;
9. uniform three-class Brier is `2/3` under the project definition;
10. scaler and Logistic Regression fit training rows only;
11. initial rating, K, and event-specific HA are exact;
12. Cup HA is zero while both league HAs are 175;
13. Cup regulation result, not final/extra-time/PK outcome, drives updates;
14. same-date events are conservatively batched;
15. a same-date Cup result cannot change a same-date J1 target feature;
16. only strictly prior Cup dates can affect a target;
17. A fresh replay passes all exact frozen references;
18. an A mismatch blocks B, C, their metrics, and the decision;
19. B fresh replay passes only the frozen six-decimal sanity contract;
20. a B mismatch blocks C, C metrics, and the decision;
21. C differs from B only by the 145 Cup events;
22. pooled metrics are calculated once from concatenated rows;
23. fold and pooled `C-B` and `C-A` deltas are retained;
24. all three decision branches follow the exact inequalities above; and
25. diagnostic values cannot affect the decision.

## 17. Boundary of this freeze task

This task creates only this specification and performs static consistency,
artifact-hash, existing-test, and repository-diff checks. It does not create
an evaluator, fit A/B/C, produce probabilities, calculate formal metrics, or
issue a Cup bridge adoption decision.

Exactly one formal evaluation may occur only after the future evaluator and
its tests have been implemented with formal mode still disabled and reviewed
against this document.
