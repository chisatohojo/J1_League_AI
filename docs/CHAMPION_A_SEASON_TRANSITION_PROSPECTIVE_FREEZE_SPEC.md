# Champion A Season Transition ST2 Prospective Freeze Specification

Freeze date: 2026-10-06 (JST). Task: SPEC FREEZE ONLY / docs-only.
Initial reviewed HEAD: `44f1134de1394104019c2084c3fadd0e9e6ccca9`.
Initial working tree: clean. Authorizing task attachment:
`a8ab39c2-4ffd-4195-968a-2804fff71481`.

## 1. Authority, retrospective decision, and authorization boundary

The unchanged [formal result](CHAMPION_A_SEASON_TRANSITION_EVALUATION_RESULT.md),
commit `44f1134de1394104019c2084c3fadd0e9e6ccca9`, selected ST2 with
tied set `['ST2']` and exact decision
`PROCEED_TO_SEASON_TRANSITION_PROSPECTIVE_FREEZE`.
ST2 passed pooled LL improvement, LL improvement in 4/5 folds, and pooled Brier
nonworsening. These are already-published retrospective findings, not recomputed
in this task and not unseen confirmation or automatic Champion promotion.

Reviewed implementation authority:
`83754a50f016f45a012b147154fb32ab637f6a71`.
Corrected retrospective spec authority:
`88b6d28ac12ae2232f29d5084e8d9ebf395292a9`.
The retrospective spec/result/evaluator and consumed one-shot marker remain
unchanged. Never rerun the retrospective evaluator to build a prospective artifact.

This document freezes only the next ST2 lane. It authorizes NO real-data replay,
fit, artifact generation, probability generation, prediction append, outcome
evaluation, network collection, ongoing-v2 activation, or production promotion.
The final gate authorizes only a separately reviewed artifact-builder plus
synthetic/unit implementation. Real artifact creation, prediction implementation
and production execution, final evaluation, and promotion each require separate
reviewed tasks. No pytest is run in this docs-only task.

## 2. Exact prospective boundary

```text
Asia/Tokyo: 2026-10-06T18:24:19+09:00
UTC:        2026-10-06T09:24:19Z
```

This is the reviewed formal-result commit timestamp, after ST2 selection, checked
read-only against that commit. No match whose kickoff OR result is at or before
this boundary can enter the prospective evaluation cohort. Historical/opened
observations before the boundary are allowed only in the explicitly separated
training/history roles below. No prospective outcome was inspected in this task.

## 3. Published local ongoing state and immutable provenance

The reviewed current production state is still ongoing-v1. This task neither
fetches nor publishes data, migrates IDs, creates bridges, nor activates v2.

| Field | Frozen value |
| --- | --- |
| Published revision | `71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538` |
| Immutable revision directory | `data/processed/jleague/2026_27/revisions/71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538` |
| Manifest SHA-256 | `c7613eac2067f6bebb12203ff5a8cade3b149c2ac5495aa39d968f2b30073f34` |
| Snapshot ID | `20261003T230410579984Z-794e906d` |
| Raw snapshot manifest | `data/raw/jleague/2026_27/snapshots/20261003T230410579984Z-794e906d/manifest.json` |
| Raw snapshot manifest SHA-256 | `dfbb3fd9ddaaf066bb4e8da027e2dda304b9dc0569cf406d15f05c9d1d1ab27e` |
| Format / sequence / publication | ongoing-v1 / 8 / published |
| Listing observed_at UTC | `2026-10-03T23:03:58.523841+00:00` |
| Final evidence observed_at UTC | `2026-10-03T23:04:09.053484+00:00` |
| Total fixtures | 380 |
| Completed before boundary | 80 |
| Unfinished | 300 (all scheduled; candidate 0) |
| Unexplained extra fixtures | 0 |
| Latest completed calendar date | `2026-09-20` |
| Nearest unfinished calendar date | `2026-10-09` |

The latest pointer matched the immutable manifest SHA; every file listed by that
manifest matched its byte SHA. Exact relevant published file hashes:

| Revision file | SHA-256 |
| --- | --- |
| `schedule.csv` | `599ad3dad9b30bf440d5e50b9867fd55d796b0a5a7bcc5a9d13a5b44526f1bd0` |
| `completed_matches.csv` | `ba9f96d4cbdf4a85e57a578ef46b358d77fbd94669c8c849bfdbf26bd262614d` |
| `fixture_identity.csv` | `953537cdc3418dad978b0ddbc0cf289876bade1ebb35a1adbdb6af53edc1d739` |
| `observations.json` | `5b7936e2886848d4408b43c9d2830f29254833fb30cadc2ee02469112f3173fc` |
| `update_summary.json` | `7e5b4d0f0fb27be566cdfdd286ab73ace56cf59931bd73767beb76a78510cbcb` |

All 380 fixture_keys are unique, have competition_key `j1_2026_2027` and
season label 2026, and agree with fixture_identity.csv on fixture_key, match_id,
home_club and away_club. The completed file has the same 80 fixture identities
as the completed schedule subset. All 80 dates precede the boundary; all 300
unfinished dates follow it. No same-calendar-date club duplicate occurs in the
frozen unfinished schedule. The 380 = 80 + 300 reconciliation leaves no extra row.

Identity provenance is the reviewed directional key
`j1_2026_2027:<home_club_slug>:<away_club_slug>`, with official Data Site club
profile URL slugs; date, kickoff, stadium and round are NOT identity.
The published fixture_identity.csv and schedule evidence_url/evidence_type,
raw snapshot manifest and immutable earlier origin evidence retain the provenance.
Seven unfinished fixtures already have official match-page IDs with
`official_completion_unconfirmed` identity evidence; 293 have blank match_id.
This is NOT completion evidence and does not select eligibility for the cohort.

| Frozen fixture_key | Existing official match-page ID | Frozen date |
| --- | --- | --- |
| j1_2026_2027:kashima:gosaka | 100903 | 2026-10-09 |
| j1_2026_2027:kashiwa:kobe | 100901 | 2026-10-09 |
| j1_2026_2027:cosaka:yokohamafm | 101008 | 2026-10-10 |
| j1_2026_2027:ftokyo:urawa | 101009 | 2026-10-10 |
| j1_2026_2027:fukuoka:okayama | 101010 | 2026-10-10 |
| j1_2026_2027:kyoto:machida | 101012 | 2026-10-10 |
| j1_2026_2027:machida:fukuoka | 101812 | 2026-10-18 |

Their recorded evidence URLs have the reviewed form
`https://www.jleague.jp/match/j1/2026/<match_page_id>/`.
The common prediction binding bootstrap already exists; its origin witness is
revision `2758a644ff46888993f79fa44987079b187196e0ed204fb863ea645ff647dd3c`,
manifest SHA `c7bfa3b9bd113c1c34e016625a23935ce6bb712de4cdcc9b47bd5187fce044c2`.
See [binding bootstrap](JLEAGUE_2026_27_PREDICTION_BINDING_BOOTSTRAP.md) and
[reviewed namespace contract](JLEAGUE_2026_27_ID_NAMESPACE_IMPLEMENTATION_FREEZE_SPEC.md).
Those previously published identity authorities are not changed or re-created now.

Any missing/inconsistent source, changed frozen bytes, cohort/count discrepancy,
or unexplained fixture is technical STOP, not permission to choose another boundary.

## 4. Frozen 300-fixture cohort and exact hash serialization

Read ONLY the exact immutable revision's schedule.csv after its byte checks.
Select its 300 rows with status `scheduled` (all unfinished rows), excluding the
80 completed rows. Sort by match_date ascending, fixture_key ascending using
ordinal string ordering. ISO YYYY-MM-DD dates and unchanged ASCII fixture_keys
are used; no normalization, inferred ID, deduplication or result-based ordering.

Freeze membership and canonical indices from THIS revision, not a future latest
schedule. Exact full-cohort fixture_key-sequence SHA-256:

```text
b63bce0289b80d096599a2f6343c48073c3617d919b3bf7153683e2089dfdcbf
```

Hash serialization, for the cohort and EACH block identically:
UTF-8 without BOM; each exact fixture_key followed by one LF byte; concatenate
in frozen canonical order, INCLUDING the final LF. No header, quotes, CSV commas,
CRLF, whitespace trimming, dates or match_id in the hashed sequence. Equivalently:

```python
hashlib.sha256(
    ("\n".join(ordered_fixture_keys) + "\n").encode("utf-8")
).hexdigest()
```

Exact row count: 300. First frozen date: 2026-10-09.
Last frozen date: 2027-06-06. Exact frozen calendar-date counts:

| Calendar date | Fixtures |
| --- | --- |
| 2026-10-09 | 2 |
| 2026-10-10 | 4 |
| 2026-10-11 | 4 |
| 2026-10-17 | 8 |
| 2026-10-18 | 2 |
| 2026-10-21 | 10 |
| 2026-10-24 | 5 |
| 2026-10-25 | 5 |
| 2026-10-31 | 6 |
| 2026-11-01 | 4 |
| 2026-11-07 | 6 |
| 2026-11-08 | 4 |
| 2026-11-20 | 3 |
| 2026-11-21 | 7 |
| 2026-11-25 | 7 |
| 2026-11-28 | 5 |
| 2026-11-29 | 5 |
| 2026-12-04 | 1 |
| 2026-12-05 | 5 |
| 2026-12-06 | 4 |
| 2026-12-12 | 3 |
| 2026-12-13 | 7 |
| 2026-12-16 | 2 |
| 2026-12-19 | 10 |
| 2027-02-13 | 9 |
| 2027-02-14 | 1 |
| 2027-02-20 | 10 |
| 2027-02-27 | 10 |
| 2027-03-06 | 10 |
| 2027-03-10 | 10 |
| 2027-03-13 | 9 |
| 2027-03-14 | 1 |
| 2027-03-20 | 9 |
| 2027-03-21 | 1 |
| 2027-04-03 | 10 |
| 2027-04-09 | 1 |
| 2027-04-10 | 9 |
| 2027-04-14 | 1 |
| 2027-04-16 | 1 |
| 2027-04-17 | 9 |
| 2027-04-24 | 10 |
| 2027-04-29 | 10 |
| 2027-05-03 | 10 |
| 2027-05-09 | 10 |
| 2027-05-15 | 10 |
| 2027-05-22 | 10 |
| 2027-05-29 | 10 |
| 2027-06-06 | 10 |

The date counts sum to 300. Later official postponements may change execution
dates only through reviewed official updates while retaining the exact fixture_key.
They do not change cohort membership, canonical frozen indices or block membership.
No fixture substitution, silent removal or addition is allowed. Cancellation or
identity replacement is technical STOP requiring a separate protocol amendment.
Binding future official IDs is allowed through reviewed infrastructure, not cohort
editing. If a date correction crosses the prospective boundary, STOP.

## 5. Five immutable prospective stability blocks

These are evaluation-only, not training/prediction windows. Their row indices are
one-based indices from section 4's frozen order, NEVER re-sorted after postponement.
Every block contains exactly 60 distinct fixtures, covers its declared interval,
and uses the exact same fixture_key/LF serialization as the full cohort.

| Block | Frozen rows | n | Ordered fixture_key SHA-256 |
| --- | --- | --- | --- |
| 1 | 1-60 | 60 | `7f10f87101a4cab649b19016bbf0997d8202eca0b9022d38d235d1342e5c3a51` |
| 2 | 61-120 | 60 | `6acd07c12ccbbf395cd76fd1f10607dd68b74fb764b15b4a6d94e8e0ba41c2f2` |
| 3 | 121-180 | 60 | `0c92f00fc73a167e7014865a4e473a3b3fe346221a78ef3a867c4dc0dd803b40` |
| 4 | 181-240 | 60 | `0dbece0019382a1c6815b9cce1878b4942955e166620ae8a560292bb9deb4e61` |
| 5 | 241-300 | 60 | `6abaff788dc2d62659be7e41cccae7808585b2497f91b2707156fe428edd4873` |

The five ordered sequences concatenate to the exact 300-fixture ordered sequence.
No outcome-dependent block change, alternative first-N threshold or subgroup
selection is permitted.

## 6. ST2 state contract: selected already, no new selection

Initial Elo = float64 1500 for exact registered TeamMaster IDs.
Home advantage = 175 in the expected-score UPDATE ONLY; scale = 400.
Feature exactly `("elo_diff",)`, raw home_rating - away_rating without HA.
No regression toward 1500, carry adjustment, promotion reset or cold-start offset.
Absent clubs retain ratings; newly appearing registered clubs start at 1500 until
their first update. Unknown/unregistered IDs fail, never alias-remap or infer IDs.

For each ordinary J1 season, current-match appearance ordinal is
1 + strictly earlier ordinary-J1 appearances for that team in that season,
counting home/away equally. Reset counters at EVERY ordinary season boundary;
2015/2016 first/second stages do not reset the same season counter.
2026/27 is ONE ordinary season (season=2026): do not reset on January 1, 2027.

```text
match_K = 45 iff home_ordinal <= 5 OR away_ordinal <= 5; otherwise 30
E_home  = expected_score(R_home + 175.0, R_away)  # scale 400
delta   = match_K * (result / 2.0 - E_home)
R_home_after = R_home + delta
R_away_after = R_away - delta
```

One shared symmetric match K/delta, unchanged float64 operation order.
Ordinal 5 qualifies; ordinal 6 does not unless the opponent qualifies.
Round number is not an ordinal. Same-date reads precede all same-date updates.
90-minute result mapping is exactly 0=Away, 1=Draw, 2=Home.
PK/ET/tie winners are never substituted for regulation-time result.

No K/carry/threshold tuning, calibration, added feature, interaction, class weight,
alternative ST candidate or further candidate selection. Generic EloRatings
defaults K20/HA0 are NOT this contract: future callers must explicitly supply
K30/HA175 for A and the above match-specific K/HA175 for ST2.

## 7. Prospective classifier training population and exact source pins

Exactly ordinary J1 2015-2025 inclusive: 3,588 matches / 7,176 team sides.
All eleven exact source paths below are required; no globbing, alternate fallback,
Cup/J2/J3/AFC, Hyakunen, completed 2026/27 or prospective fixtures in fitting.

2025 is SPENT. It was forbidden for ST2 selection/tuning and is now permitted
ONLY as additional training data after the already-frozen 2015-2024 selection.
Use it in exactly one separately authorized ST2 prospective artifact fit.
No 2025 ST2 performance metric, delta, threshold change, parameter choice, tuning
or selection is allowed. No 2025 predictions are generated during artifact creation.

Source bytes and exact row/season identities were checked read-only against the
existing operational A source manifest; no feature replay, fit or metric occurred.

| Season | Exact source path | Matches | SHA-256 |
| --- | --- | --- | --- |
| 2015 | `data/processed/jleague/2015_matches_probe.csv` | 306 | `ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353` |
| 2016 | `data/processed/jleague/2016_matches_probe.csv` | 306 | `4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f` |
| 2017 | `data/processed/jleague/2017_matches_probe.csv` | 306 | `d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b` |
| 2018 | `data/processed/jleague/2018_matches_probe.csv` | 306 | `f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681` |
| 2019 | `data/processed/jleague/2019_matches_probe.csv` | 306 | `3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f` |
| 2020 | `data/processed/jleague/2020_matches_probe.csv` | 306 | `fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17` |
| 2021 | `data/processed/jleague/2021_matches_probe.csv` | 380 | `298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6` |
| 2022 | `data/processed/jleague/2022_matches_probe.csv` | 306 | `d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2` |
| 2023 | `data/processed/jleague/2023_matches_probe.csv` | 306 | `6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9` |
| 2024 | `data/processed/jleague/2024_matches_probe.csv` | 380 | `4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1` |
| 2025 | `data/processed/jleague/2025_matches_probe.csv` | 380 | `c94411ed299ff90d86c3b55a3b17bd3e0dfc127d58c060109658d235bb24d18d` |

Relevant exact TeamMaster, dependencies, reviewed code and document authorities
at the initial reviewed HEAD (byte SHA-256):

| Authority path | SHA-256 |
| --- | --- |
| `data/master/teams.csv` | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` |
| `requirements.txt` | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` |
| `requirements-lock.txt` | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` |
| `src/features/elo.py` | `f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4` |
| `src/features/elo_history.py` | `e9a66cb8e6d905780fcd8dc88867b21a3de16865eb3c1ef35e3ae0cc5cc1c86a` |
| `src/modeling/champion_a_season_transition_evaluation.py` | `4c7a32be6d8f9d850c52b974bfb4d3117fb0ff8ba7ba6c908cd50ece5b27d32e` |
| `src/modeling/champion_a_oof_diagnostic.py` | `40bfb9f724deb0dc8ec4e6f0b9ee04fdd0a36f6addc4faa0318f416eaf3bae78` |
| `src/modeling/model_a_artifact.py` | `69ff3712d5e286b131687fa21b7804cdcc63abb7478bf218fe10a53f77800e8c` |
| `src/modeling/xg_challenger_prediction.py` | `d9a4fa3db1d4fa6ac090371cee4e0bc10918029de6c43be40af2934674b1aec4` |
| `src/modeling/prediction_identity.py` | `e9e31ce7b7cf079d8b10dd96a173d8fa31435196982361f2e612524f94177b41` |
| `src/collect/matches.py` | `0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c` |
| `src/collect/teams.py` | `b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c` |
| `src/collect/jleague_ongoing.py` | `5e91025142d583d09f2417724f9cbaeed50339275390d46000d3a73179cbe956` |
| `src/collect/jleague_ongoing_source.py` | `573a8c6fa4ada4d7d1c7efd64885c9caadb98faf142934e632c41a12811da1d2` |
| `docs/CHAMPION_A_SEASON_TRANSITION_RESEARCH_SPEC.md` | `efbf7995d2a8f5611d4002f5f9fe2299201d1d24c6e100dbf8662081e163cdd2` |
| `docs/CHAMPION_A_SEASON_TRANSITION_EVALUATION_RESULT.md` | `a081dde3f975e94973fbb63c0fcfa3f5b8a773dc28521e6ffaa40ed4f561196a` |
| `data/processed/predictions/2026_27_prediction_fixture_bindings.csv` | `f32d34931dc0c253a885b2a862f825d8aaf462f86c18a881a5b6fb91183de7c5` |

Use exact stable string TeamMaster IDs and existing alias/date resolution without
case/Unicode/ID normalization, inferred IDs or name-based state resetting.
The role of xg_challenger_prediction.py here is ONLY its persisted Model A loader
contract; no xG lane data, model, feature, evaluator or predictor is authorized.
The historical OOF generator/evaluator pins document semantic authority only;
never invoke those execution paths in a prospective build/prediction task.

Runtime for a future real artifact must match the reviewed locked stack:
Python 3.12.14, NumPy 2.5.3, pandas 3.0.5, SciPy 1.18.1,
scikit-learn 1.9.1, joblib 1.6.0. No dependency/default substitution or upgrade.

## 8. Training feature replay, separate from live state

After hash validation of ALL exact eleven sources and TeamMaster, validate each
season's schema, count, season/date semantics, completed score/result consistency,
unique official match IDs, teams, competition/stage and no self-match.
Physical file order need not already be canonical. Concatenate seasons
2015 through 2025, stable-sort match_date then exact lexical match_id, and reset
the index. Require 3,588 globally unique targets, exact season counts and no
(date, team ID) duplicate. No dropped, repaired, imputed or eligible-subset rows.

Replay ONLY this ordinary population under exact ST2 rules to build training
elo_diff. The first-five K45 rule applies independently to EVERY ordinary season,
including 2025. At each date capture all features/ordinals/expectations/K before
any results, then update in canonical match-ID order. Duplicate-team rejection
makes same-date result updates disjoint. Neither target nor peer result may
influence a same-date feature. No Hyakunen or ongoing history enters these features.

Training columns fed to the classifier are exactly `("elo_diff",)`.
Target classes are `[0,1,2]` (Away/Draw/Home). Training replay is not a prediction
or a performance evaluation and must not generate probabilities/metrics.

## 9. Exactly one future prospective artifact fit

Frozen ST2 model version: `season_transition_st2_20261006_v1`.
Frozen future directory:
`models/model_season_transition/season_transition_st2_20261006_v1/`.
This directory and its contents are NOT created in this docs-only task.

```python
StandardScaler(copy=True, with_mean=True, with_std=True)
LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)
```

Otherwise use locked sklearn defaults unchanged, without sample weights or added
preprocessing. The scaler sees ONLY the 3,588 training rows; classifier fits once
on their scaled single feature. Expected successful artifact-creation counts:
scaler fits=1; classifier fits=1; prediction batches=0; performance metrics=0;
retries=0; multistart=0; tuning=0. No second synthetic-style determinism fit on
real data, validation prediction, winner refit or model search.

ConvergenceWarning/nonfinite fitted state/fit failure is technical STOP.
Persist one-shot attempt evidence before the first real fit under a separately
reviewed exclusive-creation protocol; never retry or overwrite a partial version.
An existing version/consumed attempt fails closed. No prospective outcome permits
refitting. Missing/corrupt artifacts are not reconstructed by prediction code.

A later authorized builder may exclusively publish scaler.joblib, model.joblib,
training_manifest.csv, metadata.json and checksums.sha256. Freeze manifest order:

```text
season,match_id,match_date,home_team_id,away_team_id,target_class,elo_diff
```

Metadata must bind model version, this spec's committed byte identity, reviewed
builder/code HEAD and hashes, all eleven source hashes, TeamMaster, requirements/
lock, exact population/counts/ordered training IDs, ST2 parameters, class/feature
order, training-only scaler statistics, estimator parameters/defaults and finite
state/convergence, runtime, creation UTC and attempted/completed fit counts.
Serialize checksums.sha256 as sorted filenames with lowercase byte SHA-256;
include exactly metadata.json/model.joblib/scaler.joblib/training_manifest.csv,
not itself. Artifact hash = SHA-256 of the exact checksums.sha256 bytes.
Require immutable checksums and exact reloaded state/class/width integrity;
reloading must not call fit or predict. No production artifact is created now.

## 10. Persisted Champion A comparator: never refit

Exact version: `operational_champion_20260922_v1`.
Exact directory: `models/model_a/operational_champion_20260922_v1/`.
Its operational classifier remains the already-persisted 2015-2025 ordinary-J1
A trained on 3,588 rows. Sole feature elo_diff; classes [0,1,2]; persisted
StandardScaler and LogisticRegression. Live state remains K30/HA175, independent
of the fitted classifier. No new A fit/refit/reconstruction/determinism fit.

All five required files exist. Each checksums entry and metadata's model/scaler/
training-manifest hash matches current bytes. Metadata version, role, training
count, feature/class order and frozen contract were inspected without predicting.
Exact byte pins:

| Existing A file | SHA-256 |
| --- | --- |
| `models/model_a/operational_champion_20260922_v1/checksums.sha256` | `2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1` |
| `models/model_a/operational_champion_20260922_v1/metadata.json` | `bd1eb92c25bdb56a836ef7bfe3fcb13b0137a2ece01b6095e7d100e1f5afdd19` |
| `models/model_a/operational_champion_20260922_v1/model.joblib` | `60636e4652bce98b76c394310947b1b8923a8bf18a640d9e7976497989ed54be` |
| `models/model_a/operational_champion_20260922_v1/scaler.joblib` | `a8a5f176944049c6825071b580c5fe40f5a5fb28f504f8880d028deaf2494750` |
| `models/model_a/operational_champion_20260922_v1/training_manifest.csv` | `eea7498fabac6acc79a9c297468b470702288b61736b63d90214d741ab8fb32a` |

Champion A artifact hash in prediction rows is
`2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1`,
the SHA-256 of checksums.sha256, NOT model.joblib alone.
Metadata created_at: `2026-09-22T00:31:10.064149+00:00`.
Its recorded creation repository commit is
`4e7f6e41fafd08f5971c1c75e80e3e948da57b6d` with dirty=true at that historical
creation; preserve that original provenance, do not rewrite it to today's clean
HEAD or recreate A. This does not change today's initial clean-tree gate.

Future prediction-time validation uses the reviewed
`validate_model_a_artifact` semantics: exact file set/checksums, metadata
version/role/training population/feature/target contract, zero future training,
no creation-time prediction/metrics, model/scaler/manifest hashes, serialized
one-feature width and class order. Additionally require the exact pins above.
If missing or integrity fails: technical STOP, never rebuild/fallback/refit.
Prediction operations are transform then predict_proba ONLY.

## 11. Live Elo chronology and allowed history roles

Classifier training population is NOT the live Elo state population.
Construct independent A and ST2 states with exact IDs, 1500 initialization,
HA175 expectation only, raw difference and strict-date batching.

| Segment | Champion A | ST2 | Classifier fitting / prospective scoring |
| --- | --- | --- | --- |
| Ordinary J1 2015-2025 | K30 throughout | K45 iff either same-season ordinal <=5; else K30; yearly counters reset | Fitting population only; no 2025 performance |
| Completed 2026 Hyakunen | Existing K30 regulation-time behavior | K30 ONLY; no early-K mechanism, no ordinal contribution to ordinary 2026/27 | State history ONLY; never fit/retrospective ST2 score |
| First 80 completed ordinary 2026/27 at boundary | K30 | Reset ordinary ordinals at season start; K45 iff either ordinal <=5 else K30 | State history ONLY; never fit or prospective score |
| Later frozen 300 | Prior completed dates may update later-date state at K30 | Prior completed dates may update later-date state under ordinary ST2 rule | Pre-match comparison records; final scoring only after all 300 complete |

Exact existing Hyakunen history source is
`data/processed/jleague/2026_hyakunen/matches.csv`,
byte SHA-256 `9f871594e5216c1c89e69fcef835c641f3a4b5dbefce8d138e79881494c71f8c`.
It was hashed/header-inspected only here; no outcomes or performance were inspected.
Require its existing completed competition/schema/90-minute semantics; never read
playoff_ties.csv or substitute PK/ET winner. No Hyakunen early-K extension.

State history sequence is ordinary 2015-2025 -> completed Hyakunen -> strictly
prior completed ordinary 2026/27. Carry ratings without regression between segments.
At 2026/27 start reset ST2 ORDINARY appearance counters, NOT ratings.
Reconstruct the first 80's ordinal/state contribution, without scoring them.
For a target date D, only officially completed matches with match_date < D enter
history; candidate/unconfirmed/target/same-date result fields cannot enter state.
Require identities/provenance/chronology and no duplicate-date team; never silently
exclude unexplained history. Source revisions/evidence must be available before
the prediction-generation timestamp and validated for freshness/integrity.

Prediction runs process ONE nearest unfinished calendar date at a time,
all fixtures on that date as one conservative batch. Capture all A/ST2 state
features before any result update on that date. Later officially completed
outcomes may update state for later dates, operationally separated from scoring.
Do not precompute probabilities for all remaining future fixtures at once.

Existing generic history helpers' default Elo configuration is NOT sufficient
to establish the required operational A/ST2 state. Reuse validated source/identity
semantics, but explicitly honor the two frozen K/HA configurations; do not change
the existing helpers or Champion contract in this task.

## 12. Dedicated comparison artifact and exact ordered schema

Future append-only path:
`data/processed/predictions/season_transition_st2_prospective.csv`.
Comparison version:
`season_transition_st2_vs_a_20261006_v1`.
Exactly one comparison row per frozen fixture, containing BOTH model branches;
no fallback branch, missing-model imputation or substitution.

Exact 28-column order (no additional columns):

```text
fixture_key
match_id
match_date
kickoff
home_team_id
away_team_id
home_team_name
away_team_name
prediction_generated_at
prospective_boundary
comparison_version
model_version
source_revision
source_observed_at
champion_a_model_version
champion_a_artifact_hash
st2_model_version
st2_artifact_hash
a_elo_diff
st2_elo_diff
a_p_away
a_p_draw
a_p_home
st2_p_away
st2_p_draw
st2_p_home
a_predicted_class
st2_predicted_class
```

`model_version` is the common prediction/binding compatibility field and MUST
equal `comparison_version` exactly. It identifies this comparison, not a third
model; champion_a_model_version and st2_model_version identify the branches.
This explicit alias lets reviewed append/binding helpers retain their existing
model_version contract without altering the frozen sidecar schema.

IDs/names/fixture_key are exact TeamMaster/current validated official identities.
match_id is a nonblank official string in its recorded namespace, NEVER fixture_key.
match_date is YYYY-MM-DD; kickoff is verified official local HH:MM (mapped from
schedule kickoff_time); timestamps are timezone-aware ISO-8601. Boundary is exactly
section 2's +09:00 string. source_revision is the immutable published input revision;
source_observed_at is that revision's evidence observed_at. Artifact hash is the
SHA-256 of each immutable bundle's checksums.sha256. Model versions are exactly
sections 9/10's versions. Elo differences are finite float64.

Branch probabilities are finite [0,1], sum to 1 (rtol=0, atol=1e-12),
with model classes exactly [0,1,2] = Away, Draw, Home. Predicted class is argmax
in that class order (first maximum breaks exact ties).
Preserve generated probability values; no calibration, renormalization or threshold.
CSV is UTF-8 without BOM, LF, exact header/order, immutable appended rows.

prediction_generated_at MUST be strictly after the boundary and strictly before
each fixture's verified official kickoff and outcome, with trusted current time.
Unknown/ambiguous kickoff, elapsed kickoff, already-completed target or stale/
conflicting identity is technical STOP; do not backdate timestamps. Publish the
entire selected date batch before kickoff under reviewed append/binding validation;
do not silently choose an ID-available subset. Missing official match_id requires
waiting for separately authorized official binding BEFORE kickoff, never invented ID.
No actual result, score, winner, loss, Brier, correctness or outcome column is
permitted in the prediction-generation API or output.

## 13. Append and official identity binding

Use `src/modeling/prediction_identity.py` reviewed identity/duplicate/append
contract and the common sidecar:
`data/processed/predictions/2026_27_prediction_fixture_bindings.csv`.
Initial sidecar SHA is pinned in section 7; it remains unchanged here.
Future authorized append may add rows only, retaining all existing bytes/rows.
Freeze prevention by BOTH:
`(match_id, comparison_version)` in this CSV and
`(prediction_artifact, fixture_key, comparison_version)` in the sidecar.
Also enforce its existing official-ID binding primary key.

Sidecar's exact unchanged columns:

```text
prediction_artifact,prediction_match_id,model_version,fixture_key,prediction_id_namespace,identity_witness_revision_id,identity_witness_manifest_sha256,match_date,home_team_id,away_team_id,prediction_generated_at
```

Set prediction_artifact to the section 12 relative CSV path,
prediction_match_id to the published official match_id, and sidecar model_version
to comparison_version (identical to prediction row model_version).
Record the exact current immutable identity witness revision/manifest SHA,
official namespace (`jleague_match_page` or `jleague_data_site`), fixture/date/
team IDs and generation timestamp. Require one exact binding per comparison row,
unique fixture/ID identities and no orphan/mixed-namespace ambiguous join.

Future official match_id may bind to the same frozen fixture_key through reviewed
namespace/bridge evidence. Never rewrite historical prediction_match_id to the new
Data Site ID; only the reviewed sidecar/bridge resolves namespaces at final scoring.
No inference from numeric shape or invented fixture_key-as-ID.
v2 activation/bridge materialization is separately authorized operational work,
not an action authorized by this specification task.

Existing comparison rows and bindings are immutable: no overwrite/update/delete.
Repeat invocation only reports existing keys and appends zero duplicates; conflicting
existing binding/partial append is technical STOP, never regenerated probability
or replacement row. Use reviewed writer-lock/journal and suffix-only recovery
semantics, preserving already-published rows. Recovery must not refit/predict.
A namespace transition must not produce a second row for the same fixture/version.

## 14. Prediction-time fit and other-lane firewall

Once ST2 artifact is frozen, prediction code MUST NOT call StandardScaler.fit,
LogisticRegression.fit, fit_transform, partial_fit, calibration fit, optimizer or
hyperparameter search. Allowed operations only: validate artifacts; construct
strict-prior A/ST2 state; transform; predict_proba; append immutable records.

No xG, J Stats, suspension, player availability, architecture P/G, calibration,
workload, H2H, Cup bridge, rest or another research lane is combined with this
comparison. Only the first-five ordinary-J1 Elo UPDATE K changes; classifier
coefficients arise from each branch's fixed training trajectory, not extra features.
Existing Champion A, other predictions, research closures and consumed markers
remain unchanged. No production promotion follows artifact/prediction creation.

## 15. Collection-period no-peeking firewall

Throughout prospective collection, do NOT calculate/display Accuracy, Log Loss,
Brier, candidate deltas, winner counts, rolling performance, leaderboard, ST2-vs-A
advantage, confidence intervals, per-date performance or partial prospective score.
Do not inspect actual prospective outcomes together with stored probabilities.
No early/optional stopping or model/parameter change based on prospective results.

Operational outcome collection may separately validate completed regulation-time
results for source integrity and later-date state. It must not join to probabilities
or score predictions. Collection coverage/status may be checked WITHOUT performance.
The first 80 are history only, never ST2 retrospective/prospective evaluation rows.
A missed pre-match comparison cannot be filled after kickoff/result.

## 16. Final prospective one-shot and exact metric/gate contract

Final evaluation is a SEPARATE formal one-shot workflow requiring review and
explicit authorization, ONLY after all frozen 300 fixtures have official completed
90-minute outcomes AND all 300 have valid immutable pre-match A/ST2 comparisons.
Verify exact pinned cohort/order/block hashes, both artifact hashes/versions,
pre-kickoff timestamp validity, boundary, official outcome/identity provenance,
exact one-to-one binding/bridge joins and no extra/missing/duplicate predictions.

Use saved probabilities ONLY; no regenerated historical predictions, model call,
refit, backfill, rescoring subset for promotion or imputation. Any fixture without
a valid pre-match pair, cancellation/identity replacement or inconsistent source
is technical STOP, NOT an eligible smaller n or a research FAIL decision.
A separate reviewed evaluator must consume its exclusive immutable attempt marker
before metric computation, publish a result exclusively, retain failure evidence
and never retry/overwrite a consumed attempt. No final evaluator is run now.

For BOTH A/ST2 compute exactly n, Accuracy, multiclass Log Loss with labels [0,1,2],
and multiclass Brier (mean over matches of SUM over all three classes, NO division
by 3). Use float64 probabilities, sklearn locked-runtime log_loss semantics
(internal float64-epsilon clipping for loss only, never modifying records),
argmax Accuracy and saved class order. Report pooled n=300 and each fixed block
n=60, and ST2-minus-A deltas for those exact metrics; no additional subgroup,
rolling, CI or performance search. Accuracy is context only.

ST2 confirmation PASS requires ALL at full precision, no epsilon/minimum margin:

1. Pooled ST2 Log Loss < pooled Champion A Log Loss.
2. ST2 Log Loss < A Log Loss in at least 3/5 fixed 60-fixture blocks.
3. Pooled ST2 Brier <= pooled Champion A Brier.

No Accuracy/context-subgroup gate and no tuning after results.
Only valid final RESEARCH decisions:

```text
PASS: PROCEED_TO_ST2_CHAMPION_PROMOTION_REVIEW
FAIL: CLOSE_SEASON_TRANSITION_PROSPECTIVE_RETAIN_CHAMPION_A
```

Technical STOP is neither decision. PASS is not automatic activation; promotion
requires a separate reviewed task. FAIL retains Champion A and closes this
season-transition prospective lane without adaptive follow-up.

## 17. Docs-only audit and final implementation gate

Read-only structural/provenance inspection checked boundary timestamp, published
local revision/hash integrity, identity/count/date reconciliation, ordered cohort/
block hashes, eleven source/count/hash pins and persisted A byte/metadata checks.
It did not replay Elo, deserialize/fit models, create artifacts/probabilities/CSV,
calculate any performance metric, inspect 2025 performance or prospective outcome,
run evaluator/preflight/pytest, modify source/tests/data/requirements/sidecar,
collect network data, activate v2, begin production prediction or promote a model.

Only new file:
`docs/CHAMPION_A_SEASON_TRANSITION_PROSPECTIVE_FREEZE_SPEC.md`.
Validate git diff --check and the staged document; commit only this file as
`docs: freeze ST2 prospective evaluation`. No push.

```text
FROZEN_FOR_ONE_ST2_PROSPECTIVE_ARTIFACT_IMPLEMENTATION
```

This gate authorizes ONLY the next artifact-builder + synthetic/unit implementation.
It does NOT authorize real training artifact generation, production prediction,
prospective evaluation or production promotion. Review status:
`ST2_PROSPECTIVE_FREEZE_SPEC_AWAITING_REVIEW`.
