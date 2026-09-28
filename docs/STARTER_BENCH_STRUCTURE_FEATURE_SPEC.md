# Ordinary J1 previous-match starter DF count feature specification

Status: **READY_FOR_STARTER_DF_FEATURE_MATERIALIZATION**.

This document freezes one identity-free, source-position feature family from
the reviewed `STARTER_BENCH_STRUCTURE_FEASIBILITY.md`. It does not create a
feature builder, feature dataset, tests, generated CSV, model, prediction, or
predictive metric.

## 1. Source and scope

Sources of truth:

- `docs/STARTER_BENCH_STRUCTURE_FEASIBILITY.md`
- `src/collect/sfms02_player_minutes.py`
- `docs/SFMS02_PLAYER_MINUTES_DATASET.md`
- `docs/PLAYER_WORKLOAD_FEATURE_DATASET.md`
- `docs/J1_MATCH_EVENT_DATASET_SPEC.md`
- `docs/J1_MATCH_EVENT_DATASET.md`
- `docs/JLEAGUE_PLAYER_IDENTITY_FEASIBILITY.md`
- `docs/LOCAL_PLAYER_IDENTITY_WORKLOAD_FEASIBILITY.md`
- `docs/J1_LAGGED_LINEUP_CONTINUITY_FEASIBILITY.md`

Frozen source boundary:

- competition: ordinary J1 only;
- seasons: 2015–2024;
- target matches: 3,208;
- team-match sides: 6,416;
- raw source: `data/raw/jleague_match_stats/{match_id}.html`;
- source metadata:
  `data/raw/jleague_match_stats/{match_id}.metadata.json`;
- target identity:
  `data/processed/jleague/{season}_matches_probe.csv`,
  `data/processed/jleague_match_stats/{season}_match_stats.csv`, and the
  existing TeamMaster; and
- source section: A5 only.

Expected match counts are 306 in each of 2015–2020, 380 in 2021, 306 in
2022–2023, and 380 in 2024. The total is 3,208.

A6, A7, A2, A8, A9, player minutes, substitution use, goals, cards, score
state, and results are excluded. So are 2025, 2026/27, Hyakunen, League Cup,
Emperor's Cup, J2/J3, and AFC. External HTTP is prohibited.

## 2. Frozen feature family

The family is **previous-match starter DF count**. The exact two future model
candidates are:

```text
home_previous_match_starter_df_count
away_previous_match_starter_df_count
```

For each target side, the candidate is the count of A5 starter rows whose
explicit source field satisfies:

```text
position == "DF"
```

in that team's latest ordinary-J1 match with a date strictly earlier than the
target date and in the same season.

Home and away histories are independent. This is a source-listed A5 starter
DF count. It must not be called a formation, defensive shape, back line, or
number of defenders actually deployed.

No other value is a model candidate under this specification.

## 3. Explicit exclusions

The future builder, dataset, tests, and downstream evaluation must not add:

- GK, MF, or FW count or the full GK/DF/MF/FW vector;
- position ratios, DF share, DF–MF difference, DF/FW ratio, interactions, or
  other transforms;
- bench position composition or any A6 position count;
- bench size, squad size, or starter count;
- shirt number;
- target-match roster or target-match DF count;
- prior mean DF count, rolling DF count, last-N mean, EWMA, trend, change, or
  variance;
- player identity, starter continuity, bench continuity, or player workload;
- A7 substitution usage, goals, cards, results, or score state; or
- any other exploratory feature variant.

The immediately previous current-season match's A5 starter DF count is the
only frozen family.

## 4. A5 source semantics

A5 is the starter roster. The audited row shape is exactly, in order:

```text
position
number
name
time
```

This shape occurs on all 70,576 A5 rows. The observed position tokens are
exactly `GK`, `DF`, `MF`, and `FW`. Every A5 roster `time` cell is empty.

The candidate calculation may inspect only the `position` value. `name` and
`number` may be inspected only for source-integrity validation within the
same team-match. A player name or shirt number must never enter cross-match
state, identity, joining, or calculation.

The source token must be compared case-sensitively after the existing parser's
deterministic HTML text extraction. Position values must not be normalized,
mapped, guessed, clipped, or inferred from row order.

## 5. Frozen source references

The future builder must rederive these values from the raw source before
asserting them:

| Reference | Value |
|---|---:|
| A5 sections per match | 2 |
| A5 side sections | 6,416 |
| A5 rows | 70,576 |
| A5 rows per side | 11 |
| A5 GK rows | 6,416 |
| A5 DF rows | 23,935 |
| A5 MF rows | 27,004 |
| A5 FW rows | 13,221 |
| GK rows per side | 1 |

The current-match A5 DF-count distribution across all 6,416 source sides is:

```text
2:20
3:1,928
4:4,238
5:221
6:9
```

These are validation references. The implementation must not change parsing,
scope, filtering, or classification to make counts agree.

## 6. Raw source and metadata validation

For every one of the 3,208 matches, the future builder must read the cached
HTML and metadata without modifying either. It must hard-fail unless:

- `requested_url` and `final_url` both equal the exact expected SFMS02 URL for
  the match ID;
- `status == 200`;
- metadata `match_id` equals the target match ID;
- metadata `bytes` equals the raw byte length;
- metadata `sha256` equals a newly calculated SHA-256 of the raw bytes;
- exactly two A5 side sections exist;
- each side contains exactly 11 player rows;
- each row has exactly the cell-class sequence
  `position, number, name, time`, with no duplicate or extra cell class;
- position is nonblank and one of `GK`, `DF`, `MF`, `FW`;
- number is nonblank;
- name is nonblank and contains no Unicode replacement character;
- time is empty;
- exact extracted player names are unique within the team-match roster;
- each A5 side contains exactly one `GK` position token; and
- the global A5 row and position references in Section 5 are reproduced.

Missing, duplicate, malformed, or contradictory source structures are hard
failures. No external fetch, source repair, count coercion, or silent row drop
is permitted.

## 7. Target and team identity

Target identity must be keyed and joined by `match_id`, never by file or row
position. The future builder must validate:

- exactly 3,208 unique target match IDs;
- the exact season counts in Section 1;
- season values exactly 2015–2024;
- ISO match date and its season agreement;
- exact home and away team IDs from the existing match identity and
  TeamMaster contract;
- nonblank `home_team_id` and `away_team_id`;
- `home_team_id != away_team_id`;
- exact equality of the probe, match-stat, metadata, raw-page, and target
  match-ID sets; and
- exact side mapping within the matched SFMS02 page under the existing parser
  contract.

The first and second A5 side fragments may be interpreted as home and away
only inside the already matched page and validated parser contract. Separate
files or tables must not be aligned by ordinal row position. Fuzzy team-name
matching, newly inferred aliases, and TeamMaster modification are prohibited.

## 8. Target-match provenance boundary

The cached target match's own A5 is never a candidate input for that target.
The cache metadata records later retrieval and does not prove historical
pre-kickoff publication. General knowledge about lineup announcement timing
must not be used to fill that provenance gap.

For a target dated `D`, only a scoped match for the same team and season with
`previous_match_date < D` may supply the candidate. The target's A5 may update
history only after all targets on date `D` have been emitted, making it
available to a target on a strictly later date.

“Completed prior match” in this historical reconstruction therefore means a
scoped match on a strictly earlier date. Same-date kickoff ordering is not
available and must not be inferred.

## 9. History state and replacement semantics

Maintain one state independently for each exact key:

```text
(season, team_id)
```

The state contains only:

```text
previous_match_id
previous_match_date
previous_match_starter_df_count
```

At the beginning of every season, all team states are reset. For a target:

- if state exists, emit its three values and mark the side available;
- if state does not exist, emit null for all three values and mark the side
  unavailable.

After every target on a date has been emitted, replace each participating
team's state with that date's match ID, match date, and A5 starter DF count.
State is replacement-only: it always represents the latest strictly prior
current-season match. It is not accumulated, averaged, smoothed, or retained
as a multi-match window.

## 10. Same-date chronology

Deterministic output order is:

```text
(match_date, match_id)
```

with `match_id` treated as a string. Information availability is governed by
same-date conservative batching, not that order:

1. read every target on a date from state as it existed at the start of the
   date;
2. emit every target on that date;
3. only then replace history with that date's A5 observations.

Target-own and same-date peer A5 data are prohibited. Kickoff order must not
be inferred. The frozen source has zero cases of one team appearing in more
than one scoped ordinary-J1 match on the same date. Any such case in the
frozen build is a hard failure rather than an ordering problem to resolve.

## 11. Missingness and side availability

For each side independently:

```text
starter_df_available == false
  => previous_match_id is null
  => previous_match_date is null
  => previous_match_starter_df_count is null

starter_df_available == true
  => previous_match_id is non-null
  => previous_match_date is non-null
  => previous_match_date < target match_date
  => previous match season == target season
  => previous_match_starter_df_count is an integer
```

For this frozen source, an available DF count must be in the observed domain
2–6. That domain is a frozen-source validation reference, not a universal
football rule.

Imputation is prohibited. In particular, unavailable values must not be
replaced by 0, 4, a season mean, or any other default. Home and away
availability are independent, and a future row with only one available side
would be structurally valid. The current frozen source happens to contain no
home-only or away-only rows.

Availability must be derived from state existence under the chronology; it
must not be hard-coded from a “season opener” label or expected count.

Any partial state or disagreement between availability and its three audit
fields is a hard failure.

## 12. Frozen candidate distributions

The strictly prior previous-match DF-count reference is:

| Season | Available sides | Unavailable sides | Exact available-side distribution |
|---:|---:|---:|---|
| 2015 | 594 | 18 | `3:195, 4:384, 5:15` |
| 2016 | 594 | 18 | `3:147, 4:446, 5:1` |
| 2017 | 594 | 18 | `2:3, 3:133, 4:443, 5:15` |
| 2018 | 594 | 18 | `3:166, 4:405, 5:23` |
| 2019 | 594 | 18 | `3:275, 4:315, 5:4` |
| 2020 | 594 | 18 | `3:193, 4:383, 5:18` |
| 2021 | 740 | 20 | `2:3, 3:170, 4:523, 5:36, 6:8` |
| 2022 | 594 | 18 | `3:167, 4:393, 5:34` |
| 2023 | 594 | 18 | `2:9, 3:184, 4:368, 5:33` |
| 2024 | 740 | 20 | `2:3, 3:239, 4:464, 5:33, 6:1` |
| **Total** | **6,232** | **184** | **`2:18, 3:1,869, 4:4,124, 5:212, 6:9`** |

The future builder must rederive this distribution from raw A5 history under
the frozen chronology. It must not clip, coerce, filter, or change
availability to meet the reference. The distribution is a validation gate,
not a model-selection result.

## 13. Frozen match-level pair availability

Pair availability means both side availability flags are true. Pair
unavailable means at least one flag is false. The actual chronology produces:

| Season | Matches | Pair available | Pair unavailable | Home-only available | Away-only available | Both unavailable |
|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2016 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2017 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2018 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2019 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2020 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2021 | 380 | 370 | 10 | 0 | 0 | 10 |
| 2022 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2023 | 306 | 297 | 9 | 0 | 0 | 9 |
| 2024 | 380 | 370 | 10 | 0 | 0 | 10 |
| **Total** | **3,208** | **3,116** | **92** | **0** | **0** | **92** |

These counts reconcile to 6,232 available and 184 unavailable team-sides.
They were derived from match chronology, not inferred from side totals. The
future builder must reproduce them without changing filters or availability
semantics.

Pair availability is a materialization audit result, not an output feature or
an additional model candidate.

## 14. Frozen output schema

One row represents one ordinary-J1 target match. The exact column order is:

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
home_starter_df_available
away_starter_df_available
```

Previous-match audit identity:

```text
home_previous_match_id
away_previous_match_id
home_previous_match_date
away_previous_match_date
```

Model candidates:

```text
home_previous_match_starter_df_count
away_previous_match_starter_df_count
```

This is exactly 13 columns. `match_id`, previous match IDs, and team IDs are
strings; dates are ISO `YYYY-MM-DD`; season and available DF counts are
integers; availability fields are logical booleans; and previous-match audit
fields and candidate counts are nullable only when their side is unavailable.

Only the final two columns are future model candidates. Availability and
previous-match identity/date columns are audit fields. Do not add pair
availability or any position variant to the output schema.

## 15. Output invariants

The future output must hard-fail unless:

- it contains exactly 3,208 rows and 3,208 unique match IDs;
- row order is exactly `(match_date, match_id)`;
- identity columns equal the validated target universe;
- both side states independently satisfy Section 11;
- every available previous match is the exact latest match for that team with
  the same season and a strictly earlier date;
- every available candidate is an integer in the frozen source domain 2–6;
- unavailable candidates and all associated audit fields are null;
- no candidate is imputed, clipped, coerced, or derived from the target A5;
- all season/global side availability, pair availability, and DF-count
  distributions are reproduced;
- partial-invalid rows equal zero; and
- rebuilding identical inputs produces identical rows, values, order, and
  bytes.

An implementation must use a single deterministic CSV encoding, dialect,
null representation, boolean representation, and line ending so byte-level
rebuild equality is meaningful. Those serialization choices must not change
the logical schema or values frozen here.

## 16. Identity-free contract

History state uses only `(season, team_id)`. The only value copied forward is
the prior match's count of rows with explicit `position == "DF"`.

The following are prohibited:

- player-name equality across matches;
- shirt-number identity;
- position-plus-number identity;
- normalized or fuzzy names;
- manual player merges;
- generated player IDs; and
- cross-team or cross-season player linkage.

No longitudinal player identity is required or used.

## 17. Semantic and redundancy boundaries

`DF` means only the explicit SFMS02 A5 source token. It is not evidence of a
back three, back four, actual defensive line, tactical role, in-possession
role, or out-of-possession role. A DF count of 4 must never be labeled
“four-at-the-back.”

The audited A5 invariants are:

```text
starter count = 11
GK count = 1
DF + MF + FW = 10
```

After selecting DF count, MF, FW, combined counts, ratios, differences, or
the full vector must not be introduced in response to future results. Bench
and squad counts are also outside this specification.

Closed lanes remain closed:

- PLAYER WORKLOAD: `CLOSE_RETROSPECTIVE_LANE`
- LINEUP CONTINUITY: closed / do not reopen
- SUBSTITUTION TIMING: `CLOSE_RETROSPECTIVE_LANE`

This family does not evaluate player minutes, who started previously and
again, player turnover, substitution use, or bench use.

## 18. Required future fixture tests

The future implementation must include at least these 25 tests:

1. A first current-season target emits unavailable, with null previous-match
   ID, date, and DF count.
2. A prior A5 side with `GK:1, DF:4, MF:4, FW:2` makes the next target's DF
   count 4.
3. A prior A5 side with three DF rows makes the next target's count 3.
4. With older DF count 3 and latest DF count 5, the next target receives 5,
   not mean 4.
5. The target's own A5 is excluded from its candidate.
6. Same-date peer A5 is excluded.
7. A prior-day A5 is usable on the next date.
8. A season boundary resets state.
9. Home and away histories update independently.
10. Player names do not participate in cross-match identity.
11. An A5 side with other than 11 rows hard-fails.
12. A blank or non-`GK`/`DF`/`MF`/`FW` A5 position hard-fails.
13. An A5 side with other than exactly one GK hard-fails.
14. Any A5 row shape other than exact
    `position, number, name, time` hard-fails.
15. A nonempty A5 time cell hard-fails.
16. A duplicate exact player name within one team-match roster hard-fails.
17. A missing or duplicate A5 side section hard-fails.
18. A raw metadata SHA-256, URL, status, byte-length, or match-ID mismatch
    hard-fails.
19. A duplicate target match ID hard-fails.
20. One team appearing twice on one date hard-fails.
21. Available state requires a strictly earlier, same-season previous match
    and the exact latest such match.
22. Unavailable state requires all previous-match audit fields and the
    candidate to be null.
23. Every frozen season side-availability reference is reproduced.
24. Every frozen season and global previous-match DF distribution is
    reproduced.
25. Rebuilding identical input produces identical rows, values, order, and
    bytes.

Tests must not add feature variants.

## 19. Future materialization audit

The future builder and report must publish at least:

Source reconciliation:

- matches and team-match sides;
- raw A5 side sections and rows;
- row-shape failures;
- malformed names and nonempty time cells;
- invalid position rows;
- sides with other than 11 starters;
- sides with other than exactly one GK;
- metadata URL/status/match-ID/byte/SHA failures; and
- A5 GK, DF, MF, and FW totals plus current-source DF-count distribution.

Output reconciliation:

- output rows and unique match IDs;
- available and unavailable team-sides;
- season side availability;
- season pair available, pair unavailable, home-only available, away-only
  available, and both unavailable;
- season and global previous-match DF-count distributions;
- invariant failures and partial-invalid rows; and
- output SHA-256.

Determinism requires a byte-identical rebuild from identical inputs. Frozen
references are assertions after source derivation, never targets for source
repair or filter adjustment.

## 20. No predictive evaluation

This specification does not calculate or inspect Accuracy, Log Loss, Brier,
AUC, result correlation, mutual information, coefficient, feature importance,
or any other target-label relationship. Result-class comparison, model
fitting, prediction, feature selection, parameter tuning, and adaptive
follow-up are prohibited.

Availability and source distributions must not be interpreted as predictive
evidence or used to expand the family.

## 21. Final gate

**READY_FOR_STARTER_DF_FEATURE_MATERIALIZATION**

The source scope, exact two candidates, A5 semantics, raw and metadata gates,
target identity, target-roster prohibition, replacement-only history,
same-date batching, missingness, side and pair availability, output schema,
identity-free contract, semantic limitations, validation references, and 25
required fixture tests are fully frozen.

- Model candidates: **EXACTLY TWO**
- Required future fixture tests: **25**
- Metrics: **NOT COMPUTED**
- Model fitting: **NO**
- Predictions: **NO**
- Feature dataset: **NOT CREATED**
- Production builder: **NOT CREATED**
- Tests: **NOT CREATED**
- 2025: **NOT USED**
- 2026/27: **NOT USED**
- external HTTP: **NO**
