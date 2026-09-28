# Starter / bench structure feasibility

## Status and purpose

This is an offline, read-only feasibility audit of the cached SFMS02 A5
starter and A6 listed-substitute sections for ordinary J1 in 2015–2024. It
asks whether an identity-free, team-level, pre-match-safe feature family can
be defined without reopening the player-workload, lineup-continuity, or
substitution-timing lanes.

Final verdict:
**`PROCEED_TO_STARTER_BENCH_STRUCTURE_FEATURE_SPEC`**.

The reason to proceed is not roster size. Starter count is constant and bench
size is almost constant. The surviving independent source axis is the
explicit A5 `td.position` field. A strictly prior, current-season previous
match starter `DF` count is source-stable, identity-free, nontrivially
variable, and available on 6,232 of 6,416 target team-sides. This audit does
not freeze or build that feature.

No result label, predictive metric, model, prediction, feature selection, or
parameter tuning was used.

## Source and scope

- Competition: ordinary J1 only
- Seasons: 2015–2024
- Matches: 3,208
- Team-match sides: 6,416
- Raw source: `data/raw/jleague_match_stats/{match_id}.html`
- Cache metadata: `data/raw/jleague_match_stats/{match_id}.metadata.json`
- Reconciliation artifact:
  `data/processed/sfms02_player_minutes/2015_2024_j1_player_minutes.csv`
- Source sections used for the audit: A5 and A6 only
- External HTTP requests: 0

The audit followed `src/collect/sfms02_player_minutes.py` and the contracts in
`SFMS02_PLAYER_MINUTES_DATASET.md`, `PLAYER_WORKLOAD_FEATURE_DATASET.md`,
`J1_MATCH_EVENT_DATASET_SPEC.md`, and `J1_MATCH_EVENT_DATASET.md`. The player
identity limitations in `JLEAGUE_PLAYER_IDENTITY_FEASIBILITY.md`,
`LOCAL_PLAYER_IDENTITY_WORKLOAD_FEASIBILITY.md`, and
`J1_LAGGED_LINEUP_CONTINUITY_FEASIBILITY.md` remain in force.

A5 means the listed starter roster and A6 means the listed substitute roster.
Player names were used only to check integrity within one team-match and to
reconcile raw rows to the existing artifact. No cross-match, cross-team, or
cross-season player linkage was performed. A2, A7, A8, A9, playing minutes,
appearance state, substitutions, cards, goals, score state, and match result
were not used.

## Target-match pre-match provenance

The target match's own A5/A6 is **not proven pre-kickoff information in this
repository**.

All 3,208 metadata files have exactly these fields:
`bytes`, `fetched_at_utc`, `final_url`, `match_id`, `requested_url`, `sha256`,
and `status`. Their cache retrieval timestamps range from
`2026-09-19T23:58:26.283725+00:00` to
`2026-09-20T00:36:05.854605+00:00`, after the historical match date in all
3,208 cases. They contain no source publication timestamp, pre-kickoff capture
timestamp, or equivalent point-in-time publication provenance. URL, match ID,
and HTTP status checks had zero failures, but those checks prove cache
identity, not historical availability before kickoff.

Consequently, the target match's own starter list, bench list, starter count,
bench size, squad size, and position composition are prohibited as pre-match
features. A roster structure from a strictly earlier match is usable after
that earlier match and is the only future-candidate boundary considered here.
General knowledge about when lineups are usually announced is not used to
fill the provenance gap.

## Raw DOM and field-shape audit

Each of the 3,208 files contains exactly two A5 sections and two A6 sections,
one per side. Thus A5 and A6 each have 6,416 complete side sections.

| Section | Raw player rows | Unique row shape | Shape frequency | Season coverage |
|---|---:|---|---:|---|
| A5 | 70,576 | `position, number, name, time` | 70,576 | 2015–2024 |
| A6 | 44,892 | `position, number, name, time` | 44,892 | 2015–2024 |

The four cell classes occur once on every player row. Every A5/A6 `time` cell
is empty, confirming the existing roster-time contract. No row has an empty
`position`; the observed values are only `GK`, `DF`, `MF`, and `FW`. No blank
`number` cell was found. The position frequencies are:

| Section | GK | DF | MF | FW |
|---|---:|---:|---:|---:|
| A5 | 6,416 | 23,935 | 27,004 | 13,221 |
| A6 | 6,420 | 10,086 | 16,951 | 11,435 |

Direct source support is therefore:

- name: **YES**, `td.name`
- time: **YES**, `td.time`, but empty on every A5/A6 row
- shirt number: **YES**, `td.number`
- position: **YES**, `td.position`
- separate role field: **NO — UNSUPPORTED**
- separate captain field: **NO — UNSUPPORTED**
- separate goalkeeper flag: **NO — UNSUPPORTED**; `GK` exists only as an
  explicit value of the position field
- formation field: **NO — UNSUPPORTED**
- change field: **NO** in A5/A6

No tactical formation is inferred from row order or from a position-string
pattern. Shirt number is match-local source data, not player identity and not
a recommended feature in this audit.

## Source integrity and artifact reconciliation

| Check | Result |
|---|---:|
| A5 sections missing or other than two per match | 0 |
| A6 sections missing or other than two per match | 0 |
| A5 sides with other than 11 rows | 0 |
| Unexpected/malformed A5/A6 player rows | 0 |
| Nonempty A5/A6 roster time cells | 0 |
| Blank player names | 0 |
| Replacement-character player names | 0 |
| Duplicate exact names within one team-match roster | 0 |
| A5/A6 exact-name overlap within one team-match | 0 |
| Duplicate raw `(match_id, team_id, name, section)` keys | 0 |

The raw roster keys reconcile one-to-one to the existing player-minute
artifact:

| Reconciliation item | Count |
|---|---:|
| Matches | 3,208 |
| Team-match sides | 6,416 |
| Artifact rows | 115,468 |
| A5 / starter rows | 70,576 |
| A6 / listed-substitute rows | 44,892 |
| Raw keys absent from artifact | 0 |
| Artifact keys absent from raw | 0 |
| Artifact rows violating `starter XOR listed_substitute` | 0 |
| Duplicate artifact `(match_id, team_id, player_name_raw)` keys | 0 |

The artifact was used only for this reconciliation and roster-count audit.
Entered minute, minutes played, appearance type, and actual substitution use
were not inspected as candidate inputs.

## Starter count distribution

| Season | Team-sides | Min | Median | Mean | Max | Exact distribution |
|---:|---:|---:|---:|---:|---:|---|
| 2015 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2016 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2017 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2018 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2019 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2020 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2021 | 760 | 11 | 11 | 11 | 11 | `11:760` |
| 2022 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2023 | 612 | 11 | 11 | 11 | 11 | `11:612` |
| 2024 | 760 | 11 | 11 | 11 | 11 | `11:760` |

Globally, the only value is 11; its dominant share is 6,416/6,416 (100%),
and population variance and standard deviation are both 0. Starter count is
source-safe but completely constant and therefore degenerate as a feature.

## Bench size distribution

| Season | Sides | Min | Median | Mean | Max | Exact distribution | Home distribution | Away distribution |
|---:|---:|---:|---:|---:|---:|---|---|---|
| 2015 | 612 | 6 | 7 | 6.998366 | 7 | `6:1, 7:611` | `7:306` | `6:1, 7:305` |
| 2016 | 612 | 6 | 7 | 6.998366 | 7 | `6:1, 7:611` | `7:306` | `6:1, 7:305` |
| 2017 | 612 | 7 | 7 | 7.000000 | 7 | `7:612` | `7:306` | `7:306` |
| 2018 | 612 | 6 | 7 | 6.996732 | 7 | `6:2, 7:610` | `6:1, 7:305` | `6:1, 7:305` |
| 2019 | 612 | 6 | 7 | 6.991830 | 7 | `6:5, 7:607` | `7:306` | `6:5, 7:301` |
| 2020 | 612 | 6 | 7 | 6.995098 | 7 | `6:3, 7:609` | `6:1, 7:305` | `6:2, 7:304` |
| 2021 | 760 | 6 | 7 | 6.994737 | 7 | `6:4, 7:756` | `6:1, 7:379` | `6:3, 7:377` |
| 2022 | 612 | 5 | 7 | 6.993464 | 7 | `5:1, 6:2, 7:609` | `7:306` | `5:1, 6:2, 7:303` |
| 2023 | 612 | 6 | 7 | 6.996732 | 7 | `6:2, 7:610` | `7:306` | `6:2, 7:304` |
| 2024 | 760 | 7 | 7 | 7.002632 | 8 | `7:758, 8:2` | `7:379, 8:1` | `7:379, 8:1` |

Globally, bench size has values 5, 6, 7, and 8 with distribution
`5:1, 6:20, 7:6,393, 8:2`. Seven is dominant on 6,393/6,416 sides
(99.6415%). Min/median/mean/max are 5/7/6.996883/8; population variance is
0.00404265 and population standard deviation is 0.0635819. There are zero
zero-bench sides. The 23 nonmodal sides are rare source observations, not a
broadly varying count feature.

The home/away split is reported only as an integrity check. It is not a
predictive comparison.

## Total listed squad size

Because A5 always contains 11 rows, listed squad size is exactly
`11 + bench size` on all 6,416 sides.

| Season | Min | Median | Mean | Max | Exact distribution |
|---:|---:|---:|---:|---:|---|
| 2015 | 17 | 18 | 17.998366 | 18 | `17:1, 18:611` |
| 2016 | 17 | 18 | 17.998366 | 18 | `17:1, 18:611` |
| 2017 | 18 | 18 | 18.000000 | 18 | `18:612` |
| 2018 | 17 | 18 | 17.996732 | 18 | `17:2, 18:610` |
| 2019 | 17 | 18 | 17.991830 | 18 | `17:5, 18:607` |
| 2020 | 17 | 18 | 17.995098 | 18 | `17:3, 18:609` |
| 2021 | 17 | 18 | 17.994737 | 18 | `17:4, 18:756` |
| 2022 | 16 | 18 | 17.993464 | 18 | `16:1, 17:2, 18:609` |
| 2023 | 17 | 18 | 17.996732 | 18 | `17:2, 18:610` |
| 2024 | 18 | 18 | 18.002632 | 19 | `18:758, 19:2` |

Globally, squad size has distribution
`16:1, 17:20, 18:6,393, 19:2`. Eighteen is dominant on 99.6415% of sides;
population variance and standard deviation are the same as bench size. Squad
size and bench size are duplicate information and must not coexist as separate
candidate inputs.

## Structural break and degeneracy

No sustained artifact-level structural break is present in roster count. The
modal bench size is 7 in every season and its seasonal share ranges from
99.1830% to 100%. Seasonal maximum is 7 through 2023 except for rare reduced
rosters, and two size-8 sides appear in one 2024 match. That isolated 2024
observation is not evidence of a new regime. No official rule-change cause is
asserted.

The count-only candidates are materially degenerate:

| Candidate | Unique values | Dominant count/share | Variance | Std. dev. | Min / median / mean / max |
|---|---|---|---:|---:|---|
| Starter count | `11` | 6,416 / 100% | 0 | 0 | 11 / 11 / 11 / 11 |
| Bench size | `5,6,7,8` | 6,393 / 99.6415% | 0.00404265 | 0.0635819 | 5 / 7 / 6.996883 / 8 |
| Squad size | `16,17,18,19` | 6,393 / 99.6415% | 0.00404265 | 0.0635819 | 16 / 18 / 17.996883 / 19 |

This is a source-variation assessment only. No association with match result
was calculated.

## Position structure

A5 position composition is nontrivial even though starter count is fixed. All
6,416 starter rosters have exactly one `GK`, while the complete
`(GK, DF, MF, FW)` vector has 22 observed shapes. The most common complete
shape, `GK:1, DF:4, MF:4, FW:2`, occurs on 2,226/6,416 sides (34.6945%).

The A5 `DF` count alone has global distribution
`2:20, 3:1,928, 4:4,238, 5:221, 6:9`. Its dominant value 4 has a 66.0536%
share, materially below the 99.6415% bench-size dominance. This variation is
directly based on explicit position values; it is not an inferred formation.

The full composition is internally redundant: with 11 starters and one GK,
`DF + MF + FW = 10`. A future minimal family should therefore not introduce
all position counts at once.

## Strict-prior history feasibility

History was reset by season and keyed only by team. Every target side on a
date was read from date-start state, then all A5/A6 observations from that
date were added after emission. There are zero cases of one team appearing in
multiple scoped J1 matches on the same date, so conservative same-date
batching is implementable without inferred kickoff ordering.

For previous-match bench size, current-season prior mean bench size, previous
squad size, and current-season prior mean squad size, availability is
identical: 6,232/6,416 sides (97.1322%). The unavailable 184 sides are exactly
the first current-season observation for each team and must remain null.

| Season | Available / unavailable | Previous bench: unique; dominant | Prior mean bench: unique; dominant |
|---:|---:|---|---|
| 2015 | 594 / 18 | 2; `7` 593/594 (99.8316%) | 30; `7` 565/594 (95.1178%) |
| 2016 | 594 / 18 | 2; `7` 593/594 (99.8316%) | 8; `7` 587/594 (98.8215%) |
| 2017 | 594 / 18 | 1; `7` 594/594 (100%) | 1; `7` 594/594 (100%) |
| 2018 | 594 / 18 | 2; `7` 592/594 (99.6633%) | 23; `7` 570/594 (95.9596%) |
| 2019 | 594 / 18 | 2; `7` 590/594 (99.3266%) | 38; `7` 535/594 (90.0673%) |
| 2020 | 594 / 18 | 2; `7` 591/594 (99.4949%) | 31; `7` 548/594 (92.2559%) |
| 2021 | 740 / 20 | 2; `7` 736/740 (99.4595%) | 36; `7` 607/740 (82.0270%) |
| 2022 | 594 / 18 | 3; `7` 591/594 (99.4949%) | 31; `7` 563/594 (94.7811%) |
| 2023 | 594 / 18 | 2; `7` 592/594 (99.6633%) | 26; `7` 558/594 (93.9394%) |
| 2024 | 740 / 20 | 2; `7` 738/740 (99.7297%) | 3; `7` 736/740 (99.4595%) |
| **Total** | **6,232 / 184** | **4; `7` 6,210/6,232 (99.6470%)** | **52; `7` 5,863/6,232 (94.0789%)** |

The many exact prior-mean fractions mostly propagate and dilute the 23 rare
non-seven rosters; they do not create broad underlying roster-size variation.
Previous squad size is exactly previous bench size plus 11. Prior mean squad
size is exactly prior mean bench size plus 11. Their availability, unique
counts, and dominant shares are therefore identical to the corresponding
bench candidate and they are duplicate candidates.

By contrast, the proposed strict-prior previous-match starter `DF` count has
the following source-only distribution:

| Season | Available / unavailable | Exact previous-match DF-count distribution |
|---:|---:|---|
| 2015 | 594 / 18 | `3:195, 4:384, 5:15` |
| 2016 | 594 / 18 | `3:147, 4:446, 5:1` |
| 2017 | 594 / 18 | `2:3, 3:133, 4:443, 5:15` |
| 2018 | 594 / 18 | `3:166, 4:405, 5:23` |
| 2019 | 594 / 18 | `3:275, 4:315, 5:4` |
| 2020 | 594 / 18 | `3:193, 4:383, 5:18` |
| 2021 | 740 / 20 | `2:3, 3:170, 4:523, 5:36, 6:8` |
| 2022 | 594 / 18 | `3:167, 4:393, 5:34` |
| 2023 | 594 / 18 | `2:9, 3:184, 4:368, 5:33` |
| 2024 | 740 / 20 | `2:3, 3:239, 4:464, 5:33, 6:1` |
| **Total** | **6,232 / 184** | **`2:18, 3:1,869, 4:4,124, 5:212, 6:9`** |

The total dominant share is 4,124/6,232 (66.1746%), with min/median/mean/max
2/4/3.731226/6. Every season has at least three observed values. Current-season
reset prevents season carry-over; it does not manufacture variation or rely on
a presumed rule regime.

## Chronology and missing semantics

A future specification may use only:

1. current-season prior history;
2. season reset;
3. same-date conservative batching;
4. the immediately previous match strictly before the target date.

All targets on one date must be generated from state at the start of that
date. That date's roster data may be added only after all targets have been
emitted. Target-own and same-date peer rosters are prohibited, and kickoff
order must not be inferred.

For a previous-match candidate, no previous current-season match means
unavailable/null. For a prior-mean candidate, prior observation count zero
means unavailable/null. Zero bench, an 11-player squad, or any other default
must not be used as imputation. This audit does not freeze an imputation or a
model-facing missing-value policy.

## Candidate ratings

`A` means a source-safe, nontrivially informative structure exists; `B` means
source-safe but materially limited, regime-sensitive, or near-degenerate;
`C` means unsuitable, unsupported, unsafe, or redundant.

| # | Candidate | Rating | Reason |
|---:|---|:---:|---|
| 1 | Current-season prior previous-match bench size | B | Strict-prior safe and 97.13% available, but `7` is 99.6470% of available values. |
| 2 | Current-season prior mean bench size | B | Strict-prior safe, but apparent fractional variety only propagates rare non-seven rosters; exact `7` still dominates 94.0789%. |
| 3 | Current-season prior listed squad size | C | Deterministically previous bench size plus 11. |
| 4 | Current-season prior mean listed squad size | C | Deterministically prior mean bench size plus 11. |
| 5 | Starter count | C | Exactly 11 on all 6,416 sides. |
| 6 | Starter-to-bench ratio | C | With starter count fixed at 11, it is only a transform of near-degenerate bench size. |
| 7 | Target-match bench size | C | Historical pre-kickoff availability is not proven by repository provenance. |
| 8 | Target-match squad size | C | Same provenance failure as #7 and redundant with target bench size. |
| 9 | Position composition | A | `td.position` is complete and explicit; strict-prior starter DF count has five values and only 66.17% dominance. No player identity is needed. |
| 10 | Captain / GK / role composition | C | Captain and role fields are absent; no separate GK flag exists, and A5 has exactly one `GK` position value per side. |
| 11 | Cross-match starter continuity | C | Requires player identity and belongs to the closed lineup-continuity lane. |
| 12 | Cross-match bench continuity | C | Requires player identity and belongs to the closed lineup-continuity lane. |

## Redundancy and closed-lane boundaries

The following deterministic relations must be preserved in any later review:

- `starter_count = 11`;
- `listed_squad_size = 11 + bench_size`;
- `prior_mean_squad_size = 11 + prior_mean_bench_size`;
- starter-to-bench ratio is a one-to-one transform of bench size while
  starter count is fixed;
- with one A5 GK and 11 starters, `DF + MF + FW = 10`.

Accordingly, bench and squad size must not both enter a family, and a complete
position-count vector must not be presented as four independent quantities.

Closed boundaries remain unchanged:

- PLAYER WORKLOAD: `CLOSE_RETROSPECTIVE_LANE`
- LINEUP CONTINUITY: closed / do not reopen
- SUBSTITUTION TIMING: `CLOSE_RETROSPECTIVE_LANE`

This audit did not revisit player minutes, who played, who started again, who
entered, who left, or substitution usage. The recommended candidate uses no
name comparison and is not a repackaged continuity or workload feature.

## Limitations

- The cache proves historical page content as later retrieved, not target-time
  pre-kickoff availability.
- The meaning of `DF` is limited to the explicit source position token. It is
  not proof of an actual formation, role, or in-match tactical behavior.
- Position values may reflect the source's roster classification conventions;
  no external rule or semantic ontology was consulted.
- Current-season reset makes the first team observation unavailable and
  intentionally discards prior-season structure.
- Only ordinary J1 2015–2024 is covered. Cups, J2/J3, AFC, 2025, and 2026/27
  are outside scope.
- No predictive value has been established by this source-only audit.

## Final verdict and next boundary

**`PROCEED_TO_STARTER_BENCH_STRUCTURE_FEATURE_SPEC`**

If a separate task authorizes a freeze specification, it should consider one
coherent minimal family only:

> Home and away current-season immediately previous-match A5 starter `DF`
> count, with null/unavailable when no previous current-season match exists.

The choice is based only on source stability, nontrivial variation,
redundancy control, and chronology. It is not based on predictive expectation.
Previous-match bench size and prior mean bench size should not be carried into
that specification merely to try alternatives: both are near-degenerate.

No feature builder, feature dataset, tests, model fitting, predictions,
predictive metrics, feature selection, or parameter tuning were produced.
