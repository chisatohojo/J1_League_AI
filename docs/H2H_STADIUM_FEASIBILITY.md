# Ordinary-J1 H2H and stadium source feasibility audit

Status:

- H2H: **PROCEED_TO_H2H_FEATURE_SPEC**
- Stadium: **DEFER_STADIUM**

This is a read-only, label-free audit of source identity, chronology,
coverage, sparsity, recency, orientation, and deterministic redundancy for
two possible information families not directly represented by team-level
Elo. It does not create features or evaluate predictive value. No model was
fit, no prediction was generated, and no Accuracy, Log Loss, Brier, AUC,
correlation, mutual information, coefficient, feature importance, or tuning
result was calculated.

## 1. Scope and sources

The target universe is exactly 3,208 ordinary-J1 matches from 2015–2024:
306 matches in each of 2015–2020 and 2022–2023, and 380 in 2021 and 2024.
Target identity is the existing `match_id`, `match_date`, `season`,
`home_team_id`, and `away_team_id` contract. Team IDs come only from the
existing TeamMaster exact mapping; no fuzzy team matching or new alias was
introduced.

The audited match sources are:

- `data/processed/jleague/{season}_matches_probe.csv`;
- cached `data/raw/jleague/{season}_j1_search.html` and metadata;
- `src/collect/jleague.py` for the SFMS01 search-table parser;
- `src/collect/matches.py` for the completed-match schema; and
- existing source/research documents for 2015–2024.

Repository inspection also found older H2H/stadium implementations in
`src/features/matchup_context.py` and `src/features/stadium_window.py`.
Their fixed last-five/window choices and any downstream model results were
not used in this audit. They are not evidence of predictive value, venue
identity stability, or target-time venue availability.

Excluded completely: 2025, 2026/27 first 80, future 300, Hyakunen, League
Cup, Emperor's Cup, J2/J3, AFC, and external HTTP.

## 2. Point-in-time chronology

H2H uses the unordered exact pair:

```text
tuple(sorted((home_team_id, away_team_id)))
```

The target home/away orientation and every historical match's home/away
orientation remain available separately. For a target on date `D`, only
ordinary-J1 matches with `match_date < D` enter history. All targets on a date
are inspected before any result from that date updates state. Target-own
results, same-date peer results, inferred kickoff order, and row-position
joins are prohibited. The source has zero cases of one team appearing twice
on the same date.

History in this audit crosses season boundaries but begins at the left edge
of the scoped data in 2015. Of 2,832 targets with some prior pair history,
1,228 have prior history only from an earlier season at that point; 1,604 also
have current-season pair history. A future feature specification must decide
and freeze the cross-season rule. A zero in this audit means zero meetings in
the available 2015–2024 prefix, not zero meetings in all historical football.

## 3. Strict-prior H2H coverage

The bins below are mutually exclusive; `5–9` and `10+` together form `5+`.
Every value is `target count (share of that season)`. No target result was
read when assigning a target to a coverage bin.

| Season | Targets | 0 | 1 | 2 | 3 | 4 | 5–9 | 10+ |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 153 (50.0%) | 153 (50.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| 2016 | 306 | 48 (15.7%) | 48 (15.7%) | 105 (34.3%) | 105 (34.3%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| 2017 | 306 | 35 (11.4%) | 35 (11.4%) | 40 (13.1%) | 40 (13.1%) | 78 (25.5%) | 78 (25.5%) | 0 (0.0%) |
| 2018 | 306 | 21 (6.9%) | 21 (6.9%) | 32 (10.5%) | 32 (10.5%) | 45 (14.7%) | 155 (50.7%) | 0 (0.0%) |
| 2019 | 306 | 20 (6.5%) | 20 (6.5%) | 17 (5.6%) | 17 (5.6%) | 30 (9.8%) | 202 (66.0%) | 0 (0.0%) |
| 2020 | 306 | 18 (5.9%) | 18 (5.9%) | 15 (4.9%) | 15 (4.9%) | 6 (2.0%) | 144 (47.1%) | 90 (29.4%) |
| 2021 | 380 | 24 (6.3%) | 24 (6.3%) | 31 (8.2%) | 31 (8.2%) | 15 (3.9%) | 83 (21.8%) | 172 (45.3%) |
| 2022 | 306 | 17 (5.6%) | 17 (5.6%) | 4 (1.3%) | 4 (1.3%) | 12 (3.9%) | 54 (17.6%) | 198 (64.7%) |
| 2023 | 306 | 3 (1.0%) | 3 (1.0%) | 19 (6.2%) | 19 (6.2%) | 18 (5.9%) | 62 (20.3%) | 182 (59.5%) |
| 2024 | 380 | 37 (9.7%) | 37 (9.7%) | 2 (0.5%) | 2 (0.5%) | 20 (5.3%) | 82 (21.6%) | 200 (52.6%) |
| **Global** | **3,208** | **376 (11.7%)** | **376 (11.7%)** | **265 (8.3%)** | **265 (8.3%)** | **224 (7.0%)** | **860 (26.8%)** | **842 (26.2%)** |

Thus 2,832 / 3,208 targets (**88.3%**) have at least one strictly prior exact-
pair meeting, 1,702 (**53.1%**) have at least five, and 842 (**26.2%**) have
at least ten. In the intended 2020–2024 validation seasons, any-history
coverage is respectively 288/306 (94.1%), 356/380 (93.7%), 289/306 (94.4%),
303/306 (99.0%), and 343/380 (90.3%). The 2024 reduction reflects pair
participation structure visible in the target universe; no external cause is
inferred.

## 4. Pair history depth

Across the full 2015–2024 scope there are **376 unique unordered team pairs**.
Total meetings per pair have min 2, median 6, mean 8.532, and max 20.

| Full-scope meetings per pair | Unique pairs |
|---:|---:|
| 1 | 0 |
| 2 | 111 |
| 3–4 | 41 |
| 5–8 | 68 |
| 9+ | 156 |
| **Total** | **376** |

The wide 2–20 depth is real competition-participation sparsity within the
scope. It must not be repaired by fuzzy pair identity or by importing other
competitions. The 376 no-history target rows correspond to each scoped pair's
first observed meeting.

## 5. Latest-H2H recency

Recency is calculated only for the 2,832 targets with a strictly prior pair
meeting. Summary entries are `min / median / mean / max` days. Bucket shares
use that season's recency-available denominator.

| Season | n | Days: min / median / mean / max | ≤180 | 181–365 | 366–730 | 731–1095 | >1095 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | 153 | 39 / 127 / 125.686 / 245 | 134 (87.6%) | 19 (12.4%) | 0 | 0 | 0 |
| 2016 | 258 | 36 / 158 / 167.004 / 346 | 148 (57.4%) | 110 (42.6%) | 0 | 0 | 0 |
| 2017 | 271 | 53 / 189 / 204.207 / 668 | 123 (45.4%) | 134 (49.4%) | 14 (5.2%) | 0 | 0 |
| 2018 | 285 | 28 / 179 / 220.800 / 1,011 | 143 (50.2%) | 114 (40.0%) | 24 (8.4%) | 4 (1.4%) | 0 |
| 2019 | 286 | 48 / 176 / 229.360 / 1,403 | 145 (50.7%) | 128 (44.8%) | 0 | 0 | 13 (4.5%) |
| 2020 | 288 | 4 / 160.5 / 216.698 / 753 | 149 (51.7%) | 93 (32.3%) | 45 (15.6%) | 1 (0.3%) | 0 |
| 2021 | 356 | 3 / 165 / 215.601 / 1,764 | 216 (60.7%) | 127 (35.7%) | 0 | 0 | 13 (3.7%) |
| 2022 | 289 | 42 / 161 / 213.623 / 2,005 | 163 (56.4%) | 109 (37.7%) | 1 (0.3%) | 14 (4.8%) | 2 (0.7%) |
| 2023 | 303 | 21 / 196 / 298.805 / 2,520 | 130 (42.9%) | 143 (47.2%) | 15 (5.0%) | 0 | 15 (5.0%) |
| 2024 | 343 | 35 / 180 / 202.490 / 2,356 | 172 (50.1%) | 154 (44.9%) | 16 (4.7%) | 0 | 1 (0.3%) |
| **Global** | **2,832** | **3 / 169 / 214.362 / 2,520** | **1,523 (53.8%)** | **1,131 (39.9%)** | **115 (4.1%)** | **19 (0.7%)** | **44 (1.6%)** |

Most available histories are recent: 93.7% have a latest meeting within 365
days. Nevertheless, the 44 gaps over three years and 2,520-day maximum make
recency a material semantic qualifier; availability alone must not imply
freshness.

## 6. Home/away orientation

“Same” means the target home team was also home in at least one prior pair
meeting. “Reverse” means the target home team was away in at least one prior
meeting. “Either” is any prior pair meeting; “both” requires both histories.

| Season | Targets | Same available | Reverse available | Either available | Both available |
|---:|---:|---:|---:|---:|---:|
| 2015 | 306 | 0 (0.0%) | 153 (50.0%) | 153 (50.0%) | 0 (0.0%) |
| 2016 | 306 | 210 (68.6%) | 258 (84.3%) | 258 (84.3%) | 210 (68.6%) |
| 2017 | 306 | 236 (77.1%) | 271 (88.6%) | 271 (88.6%) | 236 (77.1%) |
| 2018 | 306 | 264 (86.3%) | 285 (93.1%) | 285 (93.1%) | 264 (86.3%) |
| 2019 | 306 | 266 (86.9%) | 286 (93.5%) | 286 (93.5%) | 266 (86.9%) |
| 2020 | 306 | 270 (88.2%) | 288 (94.1%) | 288 (94.1%) | 270 (88.2%) |
| 2021 | 380 | 332 (87.4%) | 356 (93.7%) | 356 (93.7%) | 332 (87.4%) |
| 2022 | 306 | 272 (88.9%) | 289 (94.4%) | 289 (94.4%) | 272 (88.9%) |
| 2023 | 306 | 300 (98.0%) | 303 (99.0%) | 303 (99.0%) | 300 (98.0%) |
| 2024 | 380 | 306 (80.5%) | 343 (90.3%) | 343 (90.3%) | 306 (80.5%) |
| **Global** | **3,208** | **2,456 (76.6%)** | **2,832 (88.3%)** | **2,832 (88.3%)** | **2,456 (76.6%)** |

Orientation-specific state is source-derivable without losing unordered pair
identity, but it fragments a family that already has coherent orientation-
agnostic coverage. It is therefore not the recommended first family.

## 7. Result and draw-state feasibility

For every prior pair event, the stored 0/1/2 result can be reoriented to the
current target's home-team perspective. Strictly prior state can therefore
contain:

- prior exact-pair match count;
- prior target-home-team wins;
- prior draws; and
- prior target-away-team wins.

All four values are available together for 2,832 targets and unavailable
together for 376. Reconciliation failures for
`wins + draws + losses == prior match count` are **0**. Among covered targets,
768 have zero prior draws and 2,064 have one or more; a zero draw count is a
valid observed state, not missingness.

A prior draw rate is source-safe only when the prior match denominator is
positive. Its availability is therefore also 2,832 / 3,208, but 376 covered
targets have denominator 1, 265 have 2, 265 have 3, and 224 have 4. The rate
is a deterministic transform of draw count and match count, and small
denominators make it less suitable as a separate initial family. Nothing in
this audit tests whether draw history predicts the target draw class.

## 8. H2H redundancy and relation to Elo

Deterministic redundancies are explicit:

```text
prior home-team wins + prior draws + prior away-team wins
    = prior exact-pair match count

prior draw rate = prior draws / prior exact-pair match count
```

The future specification must not include all redundant counts and rates as
separate variants. H2H result summaries and Elo are both derived from prior
match results, so their information sources partly overlap. Elo maintains
team-level strength state; it does not directly retain an exact-pair
conditional state. That semantic distinction establishes non-degeneracy, not
predictive improvement.

## 9. Stadium source discovery

An explicit stadium field was found: **YES**.

| Audit item | Finding |
|---|---|
| Raw field | SFMS01 search-table header `スタジアム` |
| Parser path | `_SearchTableParser` → `parse_matches_html()` → ninth data cell `values[8]` → `stadium` |
| Processed field | `stadium` in every 2015–2024 match probe CSV |
| Nonblank / total | 3,208 / 3,208 |
| Null / blank | 0 / 0 |
| Unique raw tokens | 51 |
| Unicode replacement-character rows | 0 |
| Stable venue ID | **NO** |
| Venue link or venue master | **NO** |
| Neutral-site flag | **NO** |
| Home/away venue designation | **NO** |

The parser strips surrounding cell whitespace. Its NFKC handling is limited
to numeric syntax and explicitly does not normalize club or stadium names.
`validate_matches()` also strips surrounding whitespace but performs no venue
alias mapping. Fuzzy merge, manual venue mapping, club-to-home-stadium
inference, and city-name inference are prohibited.

Raw-token counts by season are 23, 23, 24, 23, 23, 20, 24, 22, 22, and 25
for 2015 through 2024. Across the 51 exact tokens, the number appearing in
exactly 1 through 10 seasons is respectively:

```text
1:13, 2:4, 3:7, 4:5, 5:4, 6:4, 7:4, 8:1, 9:3, 10:6
```

Exact-token persistence exists, but it is not a stable venue identity
contract. Repository research deliberately preserves changes such as
`万博`/`吹田Ｓ`/`パナスタ`, `ベアスタ`/`駅スタ`, and
`ＢＭＷス`/`レモンＳ` as distinct source tokens and does not certify whether
they are spelling variants, renames, or different facilities. No fuzzy or
manual merge was performed here.

## 10. Stadium point-in-time provenance

The cached annual SFMS01 pages are final retrospective result listings. Their
metadata shows retrieval between 2026-09-11 and 2026-09-14, after every
2015–2024 target match. The repository contains no pre-kickoff snapshot or
other local evidence proving that each target's source-listed venue token was
available at the prediction point. General knowledge about schedule
publication cannot fill that gap.

**STADIUM_PREMATCH_PROVENANCE_UNPROVEN**

The field itself is fully covered, but qualifying same-venue and team×venue
historical coverage is **not authorized**: there is neither a stable venue ID
nor proven target-time venue availability. Existing code that keys history by
the exact raw string does not cure either issue. Neutral, home-stadium,
away-stadium, and relocated-venue labels cannot be inferred from the source.

This is not `STADIUM_SOURCE_UNAVAILABLE`: an explicit field exists. It is a
provenance- and identity-limited source that must be deferred before any
feature specification.

## 11. Candidate-family ratings

Ratings use only source safety, point-in-time safety, coverage, sparsity, and
semantic non-degeneracy.

| Candidate family | Rating | Reason |
|---|:---:|---|
| 1. Prior exact-pair match count | **A** | Exact TeamMaster pair identity, strictly-prior construction, 88.3% global and 90.3–99.0% 2020–2024 coverage |
| 2. Prior exact-pair target-home W/D/L counts | **A** | Same safe coverage; coherent result state from past matches, with deterministic redundancy controllable |
| 3. Prior exact-pair draw rate | **B** | Source-safe when denominator >0, but redundant with count/draw state and many denominators are 1–4 |
| 4. Latest H2H result | **B** | 88.3% available, but 6.3% of covered targets have gaps over 365 days and maximum gap is 2,520 days |
| 5. Same-orientation prior H2H summary | **B** | Safe but fragments coverage to 76.6% globally |
| 6. Reverse-orientation prior H2H summary | **B** | Safe and 88.3% available, but adds an orientation split rather than a minimal first family |
| 7. Recency of latest H2H | **B** | Safe for covered rows, but missing for 11.7% and has a long-gap tail |
| 8. Target venue identity | **C** | Explicit raw token but no stable venue ID and target-time provenance unproven |
| 9. Same-venue historical match count | **C** | Cannot establish stable same-venue identity or PIT-safe target venue |
| 10. Target-home-team × venue history | **C** | Same venue-identity/provenance blockers; home-stadium inference prohibited |
| 11. Target-away-team × venue history | **C** | Same venue-identity/provenance blockers |
| 12. Home-team identity itself | **C** | Existing TeamMaster/Elo identity, not a new source family |

## 12. Verdicts and recommended next step

### H2H: PROCEED_TO_H2H_FEATURE_SPEC

Exact unordered team-pair identity is stable, strict-prior chronology is
straightforward, same-date batching is enforceable, and coverage is
meaningful without fuzzy matching. Sparsity and recency are measurable and
manageable, though the 2015 left boundary and long-gap tail must remain
explicit.

Recommend at most **one coherent minimal family** for the next specification:
strict-prior exact-pair W/D/L count state from the target-home-team
perspective, represented without deterministic duplication—for example,
prior match count plus target-home win count and draw count, with target-away
win count derived rather than added. This recommendation is based on source
coherence and coverage only. The feature specification, missingness rule,
cross-season rule, and exact columns remain future work.

Do not add latest-result, recency, orientation splits, rates, last-3/last-5,
year windows, decay, EWMA, home-only weights, or draw weights as parallel
variants.

### Stadium: DEFER_STADIUM

The raw field has complete coverage, but the proceed conditions fail because
stable venue identity and PIT-safe target availability are not established.
No stadium family is recommended and no stadium feature specification should
be created from the current evidence. Reconsideration would require local,
reviewable evidence of pre-match venue availability and a stable venue
identity contract; it must not begin with a manual alias map or external
completion in this lane.

## 13. Closed lanes and limitations

The following reviewed decisions remain closed and none of their features is
reintroduced:

- PLAYER WORKLOAD — `CLOSE_RETROSPECTIVE_LANE`
- LINEUP CONTINUITY — closed
- DISCIPLINE — `CLOSE_RETROSPECTIVE_LANE`
- FIRST SCORE — `CLOSE_RETROSPECTIVE_LANE`
- GOAL TIMING — `CLOSE_RETROSPECTIVE_LANE`
- SUBSTITUTION TIMING — `CLOSE_RETROSPECTIVE_LANE`
- STARTER DF — `CLOSE_RETROSPECTIVE_LANE`

This audit is restricted to local ordinary-J1 2015–2024 history. It does not
claim complete pre-2015 pair history, explain club participation changes,
certify venue aliases, identify neutral matches, or test any association with
the target result. No feature builder, feature dataset, test, evaluation code,
prediction, or model artifact was created.
