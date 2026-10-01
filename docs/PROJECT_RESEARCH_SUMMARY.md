# J1 League AI 研究サマリー

- 最終更新: **2026-10-02 (JST)**
- Project purpose: ordinary J1の試合前に`0=Away / 1=Draw / 2=Home`の3-class確率を再現可能な形で出力する。
- Current research phase: **new information layer / data platform**。2020–2024 OOFでの小さなretrospective feature探索を閉じ、PIT provenanceを持つprospective dataを蓄積する段階。
- Current baseline/champion: **Model A — Elo-only Logistic**。
- Current data discipline: exact identity、strictly-prior chronology、same-date conservative batching、immutable raw evidence、artifact SHA freeze、freeze → implementation → one-shot evaluation。

現在のChampionはModel A、既存ChallengerはDomestic Competitive Restを加えたModel Bである。2025はspent test、最初の70件の2026/27 ordinary J1はopened interim lockboxであり、どちらも新しいfeature選択やtuningには使わない。直近までにformal retrospective evaluationへ進んだ10 feature laneはすべてclosed decisionとなった。一方、J Stats team cumulative snapshots、suspension notices、rolling xGは、historical backfillと混同しないprospective/operational資産として管理されている。詳細なdata pathは[DATA_ASSET_INVENTORY.md](DATA_ASSET_INVENTORY.md)、運用順序は[NEXT_DATA_RESEARCH_ROADMAP.md](NEXT_DATA_RESEARCH_ROADMAP.md)を参照する。

## A. 現行baselineとevaluation discipline

### Model A

| Contract | Frozen value |
|---|---|
| Model role | Champion / reference |
| Inputs | `elo_diff` only |
| Initial Elo | `1500` |
| K-factor | `30` |
| Home advantage | `175`、expected-score update内のみ |
| Feature value | pre-match home Elo − pre-match away Elo |
| Preprocessing | training rowsだけでfitした`StandardScaler` |
| Estimator | `LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)` |
| Classes | `[0,1,2]` = Away / Draw / Home |
| Historical OOF metrics | 1,678 rowsでAccuracy `0.466626936829559`、Log Loss `1.056065401323764`、Brier `0.6357323419292724` |

Operational artifactは[MODEL_A_ARTIFACT.md](MODEL_A_ARTIFACT.md)に記録されている。Model BはDomestic Competitive Restの4 fieldsを追加したfrozen Challengerであり、Championを置き換えていない。Source: [MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md)、[PROJECT_STATUS_2026_09_20.md](PROJECT_STATUS_2026_09_20.md)。

### Evaluation boundaries

- **2025 = spent test**。新しいmodel/feature選択、parameter変更、missing-value rule決定には使わない。
- Immutable opened interim targetは、**最初の70 completed 2026/27 ordinary-J1 IDs**。最新document上のlocal publicationは2026-09-29時点で**80 completed / 300 scheduled**だが、追加10件はlive historyであり、frozen 70-ID targetを拡張しない。
- Opened 70-match resultはdiagnostic専用で、feature選択やtuningには使わない。将来のfull 380-match checkでもfrozen specificationを維持する。
- 今後のformal evaluationは**freeze → evaluator implementation/preflight → explicit one-shot run**の順とする。Formal rerunと結果を見たadaptive tuningは禁止。
- Retrospective evaluationとprospective collectionを分離する。現在pageやcumulative valueはhistorical PIT evidenceではない。
- 同一calendar dateは、全targetのstateを先に読み、その日の全targetをemitした後でresult/eventをhistoryへ反映する。
- Generated evaluation artifactはexact schema、identity、count、chronology、および指定済みSHA-256に拘束される。

Source: [2026_27_INTERIM_LOCKBOX_EVALUATION.md](2026_27_INTERIM_LOCKBOX_EVALUATION.md)、[2026_LOCKBOX_PROTOCOL_CORRECTION.md](2026_LOCKBOX_PROTOCOL_CORRECTION.md)、[PROJECT_STATUS_2026_09_20.md](PROJECT_STATUS_2026_09_20.md)。

## B. Core historical datasetの状態

### Ordinary J1

| Season | Matches | Format note |
|---:|---:|---|
| 2015–2020 | 各306 | 18 clubs。2015–2016はtwo-stage source semanticsを保持 |
| 2021 | 380 | 20 clubs / 38 rounds。固定306-row前提は禁止 |
| 2022–2023 | 各306 | 18 clubs |
| 2024 | 380 | 20 clubs / 38 rounds |
| **2015–2024** | **3,208** | retrospective ordinary-J1 target universe |
| 2025 | 380 | spent test。frozen artifact contract下ではModel A operational trainingに使用 |
| **2015–2025** | **3,588** | 現行Model A operational training population |

Season別sourceはrepository内J.League cacheに裏付けられた`data/processed/jleague/{season}_matches_probe.csv`である。Frozen operational buildの2015–2025 concatenationでは、`match_id`重複なし、date/result/team ID欠損なし、TeamMaster exact resolution済み、drop rowなし。Result classとscoreも整合する。TeamMasterは現在**49 stable teams / 103 alias rows**で、source/date-aware exact matchingを使い、fuzzy fallbackは行わない。Source: [DATA_PIPELINE_STATUS.md](DATA_PIPELINE_STATUS.md)、[PROJECT_STATUS_2026_09_20.md](PROJECT_STATUS_2026_09_20.md)、[J2_TEAM_IDENTITY_INVENTORY.md](J2_TEAM_IDENTITY_INVENTORY.md)。

### Core外の期間・competition

| Dataset | 役割 | 明示的な境界 |
|---|---|---|
| 2025 ordinary J1 | frozen operational training / spent test | 新しい選択・tuningには再利用しない |
| 2026 J1 Hyakunen、200 rows | 各contract下のElo/Rest・rolling-xG history | ordinary-J1 Logistic targetではない。regulation-time semanticsのみ |
| 2026/27 ordinary J1 | ongoing schedule/revision stream | frozen interim targetは70 IDsのまま。後続live rowsは新しいselection setではない |
| Rolling-xG freeze時点のfuture 300 | prospective cohort | 最初の80はopened history。future outcomeの早期確認は禁止 |
| J2 2015–2024、4,538 rows | lower-division history/data research | J2/promotion model-selection laneはclosed。J3 prehistoryはない |
| Domestic cups | Rest historyおよび別途validated bridge evidence | generic processed Cup resultを90-minute Elo resultとみなさない |

## C. Formal evaluation lane一覧

下表は、現行`docs/*_EVALUATION.md`のうちfrozen feature-family formal runに該当するものを全件収載する。Log Loss/Brier deltaが正ならchallengerが悪化したことを表す。Accuracyはdecision criterionではないため省略する。

| Lane | Feature family | Artifact / dataset | Primary validation | Final decision | Pooled LL delta | Pooled Brier delta | Improved LL folds | Status / reopen rule |
|---|---|---|---:|---|---:|---:|---:|---|
| H2H | Strictly-prior exact-pair match/win/draw counts | [H2H_FEATURE_DATASET.md](H2H_FEATURE_DATASET.md) | 1,678 | `CLOSE_RETROSPECTIVE_LANE` | `+0.0016096205037983147` | `+0.0007905102097728323` | 1/5 | **CLOSED**。subset/transform retryなし。[Result](H2H_EVALUATION.md) |
| Cup bridge | J1+J2 Eloと145 regulation-time Cup bridge events。formal comparison C−A | [CUP_J1_J2_REGULATION_RESULT_DATASET.md](CUP_J1_J2_REGULATION_RESULT_DATASET.md) | 1,678 | `CLOSE_CUP_BRIDGE_LANE` | `+0.0005008384174258751` | `+0.0005719612389700757` | 2/5 | **CLOSED**。dataは再利用可能だがtuning/adaptive follow-upは禁止。[Result](CUP_BRIDGE_EVALUATION.md) |
| Player workload | Previous-match XI/squad rolling normalized minutes | [PLAYER_WORKLOAD_FEATURE_DATASET.md](PLAYER_WORKLOAD_FEATURE_DATASET.md) | 1,631 | `CLOSE_RETROSPECTIVE_LANE` | `+0.008710` | `+0.005292` | 1/5 | **CLOSED**。local-name/minute制約を保持。[Result](PLAYER_WORKLOAD_EVALUATION.md) |
| Previous-season J Stats | 前completed-seasonのteam xG/xGA、SOT、possession、pass success profile | [PREVIOUS_SEASON_JSTATS_FEATURE_DATASET.md](PREVIOUS_SEASON_JSTATS_FEATURE_DATASET.md) | 1,058、4 folds | `CLOSE_RETROSPECTIVE_LANE` | `+0.019729` | `+0.010068` | 0/4 | **CLOSED**。season-final profileはhistorical in-season PITではない。[Result](PREVIOUS_SEASON_JSTATS_EVALUATION.md) |
| Team discipline | Prior yellow/red cards per match | [TEAM_DISCIPLINE_FEATURE_DATASET.md](TEAM_DISCIPLINE_FEATURE_DATASET.md) | 1,631 | `CLOSE_RETROSPECTIVE_LANE` | `+0.004739` | `+0.003111` | 0/5 | **CLOSED**。weighted-card/timing variantなし。[Result](TEAM_DISCIPLINE_EVALUATION.md) |
| First score | Prior scored-first / conceded-first rates | [FIRST_SCORE_FEATURE_DATASET.md](FIRST_SCORE_FEATURE_DATASET.md) | 1,631 | `CLOSE_RETROSPECTIVE_LANE` | `+0.004805693038947512` | `+0.0026472701792192854` | 1/5 | **CLOSED**。結果を見たcandidate subsetなし。[Result](FIRST_SCORE_EVALUATION.md) |
| Goal timing | Prior first/scoring/conceding mean normalized minutes | [GOAL_TIMING_FEATURE_DATASET.md](GOAL_TIMING_FEATURE_DATASET.md) | 1,576 | `CLOSE_RETROSPECTIVE_LANE` | `+0.0029941314077723824` | `+0.0018687172632801952` | 2/5 | **CLOSED**。timing split/window retryなし。[Result](GOAL_TIMING_EVALUATION.md) |
| Substitution timing | Prior mean normalized substitution minute | [SUBSTITUTION_TIMING_FEATURE_DATASET.md](SUBSTITUTION_TIMING_FEATURE_DATASET.md) | 1,631 | `CLOSE_RETROSPECTIVE_LANE` | `+0.000850378085562431` | `+0.0006754869931211438` | 1/5 | **CLOSED**。count/regime/first-last variantなし。[Result](SUBSTITUTION_TIMING_EVALUATION.md) |
| Starter DF | Previous same-season matchのsource-listed starter DF count | [STARTER_DF_FEATURE_DATASET.md](STARTER_DF_FEATURE_DATASET.md) | 1,631 | `CLOSE_RETROSPECTIVE_LANE` | `+0.000314581871201147` | `+0.0000733046601537619` | 2/5 | **CLOSED**。formation inferenceではない。[Result](STARTER_DF_EVALUATION.md) |
| Team Draw Propensity | Last-five / current-season symmetric draw-rate family | [TEAM_DRAW_PROPENSITY_FEATURE_DATASET.md](TEAM_DRAW_PROPENSITY_FEATURE_DATASET.md) | 1,631 | `CLOSE_RETROSPECTIVE_LANE` | `+0.006618984725184074` | `+0.003922592128068669` | 2/5 | **CLOSED**。smoothing/window/subset/imputation follow-upなし。[Result](TEAM_DRAW_PROPENSITY_EVALUATION.md) |

Formal laneは**10**、closed formal laneも**10**。Adaptive retrospective follow-upが承認されたformal feature laneはない。

`ELO_PROMOTION_RESET_EVALUATION.md`は完了済みのexploratory Elo-transition experimentで、上記10 feature-family one-shot laneには含めない。`2026_27_INTERIM_LOCKBOX_EVALUATION.md`はopened operational lockbox reportであり、再利用可能なfeature-selection evaluationではない。

## D. その他の完了済みmodel/data調査

Statusはsource documentにある最も強い確定結論を維持する。`DEFERRED`/`BLOCKED`はsourceが無価値という意味ではなく、現時点でproduction/PIT/identity gateを満たさないという意味である。

| Investigation | Status | 確立済みの結論と境界 | Source |
|---|---|---|---|
| Promotion transition/reset | **CLOSED** | Resetはpooled LLを小幅改善したが2/5 foldsのみで、early promoted matchesは悪化。reset ruleは不採用。 | [ELO_PROMOTION_RESET_EVALUATION.md](ELO_PROMOTION_RESET_EVALUATION.md) |
| J2 Elo / promotion variants | **CLOSED** | Equal J1+J2、fixed 1400 prior、calibrated prior、returning-history variantsは現行Eloを置換せず、promotion/J2 handlingは当面closed。 | [ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md](ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md) |
| Lagged lineup continuity | **CLOSED** | Short-term raw-name coverage 99.06%はfeasibleだがmodel laneはclosed。stable player identityは未確立。 | [J1_LAGGED_LINEUP_CONTINUITY_FEASIBILITY.md](J1_LAGGED_LINEUP_CONTINUITY_FEASIBILITY.md)、[MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md) |
| J Stats / J.LEAGUE.jp historical match-level advanced stats | **DEFERRED** | Late-2024 partial xG/SOT evidenceはあるが、2018–2023 production routeと完全なhistorical PIT coverageがない。 | [J_STATS_MATCH_LEVEL_ROUTE_DEEP_AUDIT.md](J_STATS_MATCH_LEVEL_ROUTE_DEEP_AUDIT.md) |
| FootyStats historical xG | **DEFERRED** | Historical full coverage、stable identity、methodology consistency、licensing、approved bulk pathが未確認。 | [FOOTYSTATS_J1_XG_FEASIBILITY.md](FOOTYSTATS_J1_XG_FEASIBILITY.md) |
| SofaScore lineup/rating/minutes | **DEFERRED** | Supported official structured feedおよびhistorical player-ID/rating/minutes coverageを確認できていない。 | [SOFASCORE_J1_API_DATA_PATH_AUDIT.md](SOFASCORE_J1_API_DATA_PATH_AUDIT.md) |
| Referee history | **DEFERRED** | Historical final pageのreferee identityはpre-kickoff assignment availabilityの証明にならない。 | [J1_REFEREE_HISTORY_FEASIBILITY.md](J1_REFEREE_HISTORY_FEASIBILITY.md) |
| Stadium/venue history | **DEFERRED** | Stable venue identity、neutral-site semantics、pre-match provenanceが未確立。 | [H2H_STADIUM_FEASIBILITY.md](H2H_STADIUM_FEASIBILITY.md) |
| Prematch weather | **DEFERRED** | Venue identityが未解決で、historical pre-kickoff forecast archiveも未確立。 | [J1_PREMATCH_WEATHER_FEASIBILITY.md](J1_PREMATCH_WEATHER_FEASIBILITY.md) |
| AFC schedule/rest | **DEFERRED** | Report/PDF/articleにdeliveryが分散し、2015–2024 Japanese-club scheduleの完全性とidentity provenanceがない。 | [AFC_DELIVERY_MATRIX_2015_2024.md](AFC_DELIVERY_MATRIX_2015_2024.md) |
| Roster/injury availability | **DEFERRED** | Current official roster/noticeはあるが、historical complete as-of roster/availability stateがない。 | [J1_ROSTER_AVAILABILITY_FEASIBILITY.md](J1_ROSTER_AVAILABILITY_FEASIBILITY.md) |
| J Stats player snapshots | **DEFERRED** | Direct href/photo IDsは1,110/1,110一致。ただし5 embedded candidatesにperson-specific profile evidenceがなく、collector authorizationはNO。 | [J_STATS_PLAYER_SNAPSHOT_IDENTITY_CLARIFICATION.md](J_STATS_PLAYER_SNAPSHOT_IDENTITY_CLARIFICATION.md) |
| Manager identity | **DEFERRED** | 6,058/6,416 appearances（94.42%）はstable ID解決済み。文字化けを含む9 raw names / 358 appearancesはofficial evidenceなしに補完しない。 | [JLEAGUE_MANAGER_IDENTITY_AUDIT.md](JLEAGUE_MANAGER_IDENTITY_AUDIT.md)、[JLEAGUE_MANAGER_UNRESOLVED_AUDIT.md](JLEAGUE_MANAGER_UNRESOLVED_AUDIT.md) |
| Stable longitudinal player identity | **BLOCKED** | Match-local namesとsampled numeric candidatesはあるが、cross-season/cross-teamのofficial person identityが未確立。 | [J1_PLAYER_IDENTITY_LINKAGE_PROTOTYPE.md](J1_PLAYER_IDENTITY_LINKAGE_PROTOTYPE.md)、[LOCAL_PLAYER_IDENTITY_WORKLOAD_FEASIBILITY.md](LOCAL_PLAYER_IDENTITY_WORKLOAD_FEASIBILITY.md) |
| SFMS02 basic team match stats | **RESEARCH_COMPLETE** | 2015–2025の3,588 rowsをmaterialize済み。Documented source fieldsを越えてxG、possession、SOTを補わない。 | [DATA_PIPELINE_STATUS.md](DATA_PIPELINE_STATUS.md)、[J1_2024_OFFICIAL_MATCH_STATS_AUDIT.md](J1_2024_OFFICIAL_MATCH_STATS_AUDIT.md) |
| SFMS02 match events | **RESEARCH_COMPLETE** | Deterministic IDを持つ39,987 normalized match-local eventsをmaterialize済み。longitudinal player identity sourceではない。 | [J1_MATCH_EVENT_DATASET.md](J1_MATCH_EVENT_DATASET.md) |
| SFMS02 normalized player minutes | **RESEARCH_COMPLETE** | 0–90 conventionで115,468 matchday-squad rowsをmaterialize済み。official elapsed minutesでもstable player masterでもない。 | [SFMS02_PLAYER_MINUTES_DATASET.md](SFMS02_PLAYER_MINUTES_DATASET.md) |
| Rolling xG challenger | **PROSPECTIVE_ONLY** | Frozen v1 feature/model artifactあり。最初の80はhistory、future 300はprospective cohortで、prospective metricは未開封。 | [ROLLING_XG_FEATURE_SPEC.md](ROLLING_XG_FEATURE_SPEC.md)、[XG_CHALLENGER_MODEL_ARTIFACT.md](XG_CHALLENGER_MODEL_ARTIFACT.md) |
| J Stats team cumulative snapshots | **PROSPECTIVE_ONLY** | Append-only BASE_10/FULL_37 observationsとregistryあり。match-level reconstructionは禁止。 | [J_STATS_PROSPECTIVE_SNAPSHOT_REGISTRY.md](J_STATS_PROSPECTIVE_SNAPSHOT_REGISTRY.md) |
| Suspension snapshot capture | **OPERATIONAL** | Operatorが指定したofficial notice URLをpublication/retrieval timestamp付きでprospective capture可能。historical completenessとplayer identityは未解決。 | [JLEAGUE_SUSPENSION_SNAPSHOT_RUNBOOK.md](JLEAGUE_SUSPENSION_SNAPSHOT_RUNBOOK.md) |
| Ongoing 2026/27 schedule/result revision pipeline | **OPERATIONAL** | Immutable snapshot/revisionとvalidated `latest` stateでlive chronologyを管理。selection datasetではない。 | [JLEAGUE_2026_27_UPDATE_DESIGN.md](JLEAGUE_2026_27_UPDATE_DESIGN.md) |
| Earlier interim lockbox reports | **SUPERSEDED** | Missing-input/wrong-Brierのinvalid runと36/70 chronology-bug reportは現行結果ではない。公式corrected resultは40/70 vs 38/70。 | [PROJECT_STATUS_2026_09_20.md](PROJECT_STATUS_2026_09_20.md) |

この主要investigation表のstatus countは、CLOSED 3、DEFERRED 10、BLOCKED 1、RESEARCH_COMPLETE 3、PROSPECTIVE_ONLY 2、OPERATIONAL 2、SUPERSEDED 1。

## E. Prospective data collectionと運用

### J Stats team cumulative snapshots

- Official J.LEAGUE.jp 2026/27 club-ranking pageをcumulative observationとして収集する。
- `BASE_10`はdefault 10-stat profile、`FULL_37`はexact 37-stat allowlistで、20 clubsについて740 `(team_id, stat_name)` rowsを生成する。
- Physical snapshotは1 retrieval event。Logical stateはuniformで既知の`source_state_date`、exact stat profile、exact 20-team identity、有効なraw/processed hashを満たす場合だけ採用する。
- 最新registry auditのdocumented countはphysical retrieval 6件（COMPLETE 4、INCOMPLETE 2）、logical FULL_37 observation 3件、distinct source-state date 2日（`2026-09-14`、`2026-09-21`）。
- One-page source-state probeは`SOURCE_STATE_ADVANCED`、`SOURCE_STATE_UNCHANGED`、`SOURCE_STATE_REGRESSED`、`SOURCE_STATE_UNKNOWN`を返す。`SOURCE_STATE_ADVANCED`だけが1回のFULL_37 captureをtriggerでき、automatic retryはしない。
- Snapshot deltaはstructural audit evidenceに限定し、match-level valueの復元、stat選択、Champion/Challenger decision変更には使わない。
- Runbook: [J_STATS_TEAM_SNAPSHOT_RUNBOOK.md](J_STATS_TEAM_SNAPSHOT_RUNBOOK.md)。

### J Stats player snapshots

Current verdictは**`DEFER_PLAYER_SNAPSHOT_IDENTITY`**。保存済み3 ranking pagesは1,122 rowsで、1,110 direct profile href IDsがphoto-lookup IDsと完全一致する。残る5 routesはgeneric profile skeletonを返し、person-specific identity fieldがない。Production collector authorized = **NO**。5件すべてにofficial person-specific identity evidenceが得られた場合のみ、最初のconditional familyは`time`とする。Ranking absenceはzeroではなく`NOT_OBSERVED_IN_RANKING`を維持する。

### Suspensions

Historical 2015–2024 production featureは、archive completeness、PIT page state、player linkageが未確立のためinsufficientのまま。Prospective collectorはoperatorが手動指定したcanonical official notice URLに対して運用可能で、`retrieved_at`、official `published_at`/`updated_at`、raw bytes、URL、SHAを保存する。Kickoff後に観測したnoticeをretroactive pre-kickoff evidenceにはしない。Match linkageはexact、player linkageは別途evidenceがない限り未解決。Runbook: [JLEAGUE_SUSPENSION_SNAPSHOT_RUNBOOK.md](JLEAGUE_SUSPENSION_SNAPSHOT_RUNBOOK.md)。

### Rolling xG prospective pipeline

Official match-level sourceは660 observations（2025 ordinary J1 380、Hyakunen 200、opened first 80 of 2026/27）。Fixed last-five / four-xG-field specificationとX0/X1 artifactが存在する。Predictionは同一日を1 batchとしてappend-onlyで行い、いずれかのteamにeligible prior observationが5件なければexact Model Aへfallbackする。現行runbookではprediction write前にpublished official match IDsが必要。Prospective Accuracy/Log Loss/Brierは未計算。Source: [ROLLING_XG_FEATURE_SPEC.md](ROLLING_XG_FEATURE_SPEC.md)、[XG_CHALLENGER_PREDICTION_RUNBOOK.md](XG_CHALLENGER_PREDICTION_RUNBOOK.md)。

## F. Identity / provenance blocker

| Blocker | Affected lanes | 確立済み | 未確立 | Unblockに必要なevidence |
|---|---|---|---|---|
| Stable player identity | workload、player snapshots、suspensions、roster/injury、lineup/rating | match-local exact names、1,110 href/photo ID一致、exact club IDs | embedded IDsのofficial person identity、transfer/cross-team continuity | official person-specific profile/crosswalkとconflict-free same-state club semantics |
| Historical PIT provenance | J Stats profiles、injuries、rosters、referee、weather | current/final pagesとprospective timestamp rules | 各kickoff前に既知だったarchived state | publication/observation timestampとrevision historyを持つimmutable historical snapshot |
| Venue identity | stadium、travel、weather | listing/page上のvenue text | stable venue ID、alternate/neutral-site semantics、exact location | official venue registryとdated fixture-to-venue mapping |
| Referee assignment time | referee profiles | final pageのreferee identity | kickoff前公開の証明とrevision handling | timestamp付きofficial assignment notice/archive |
| Forecast archive | weather | issue/valid timeを持つprospective forecast product | kickoff前に発行されたhistorical forecast | issue timeとstable venueでkeyedされたlicensed/official archive |
| AFC completeness/provenance | Domestic Rest、travel | representative official reports/PDF/articlesと2024 prototype | stable identity/time付きcomplete 2015–2024 Japanese-club fixtures | year-complete official schedule feed、またはcompletenessを証明できるauditable adapters |
| Historical roster/injury state | availability、continuity | current registration routeとtimestamped notices | complete registrations、effective dates、return status、archive completeness | official as-of roster ledgerとcomplete dated availability notices |
| Archive completeness | FootyStats、SofaScore、official advanced stats、suspension archive | bounded samples/routes | full target-period coverageとlawful reproducible access | licensed bulk feed、またはidentity/methodology contractを持つofficial complete archive |

## G. Projectで確立したresearch discipline

1. Retrospective current pageはhistorical point-in-time evidenceではない。
2. Completenessを証明できないsource archiveはproduction feature sourceにしない。
3. Match-local player nameはstable longitudinal player identityではない。
4. Team/match joinはexact stable IDで行い、fuzzy/name-only repairは禁止する。
5. Pre-match historyはstrictly priorかつsame-date conservative batchで構築する。
6. Current targetのresult/eventは自身のfeatureへ入れず、post-match dataは後続historyだけへ反映する。
7. Generated datasetはevaluation前にschema、identity、count、serialization、およびdocumented SHA-256をfreezeする。
8. Formal evaluationはpredeclared one-shotとする。Closed laneをparameter、window、subset、threshold、calibration searchで再開しない。
9. Missingnessは明示し、zero、league mean、その他synthetic valueを黙って代入しない。
10. Historical PIT stateは安全に後から復元できないため、prospective snapshotを今から蓄積する。
11. Model laneがclosedでも、data artifactはdocumented semantics内で再利用価値を持ち得る。

## H. 現在のproject state

| 区分 | 現在地 |
|---|---|
| Production-safe today | Model A operational artifact、exact TeamMaster、validated ordinary-J1/J2/basic domestic data、ongoing revision pipeline。Match events/minutes等は各documented semantics内だけで使用可能。 |
| Research-only | Retrospective feature artifacts、historical profiles、manager assets、Cup bridge evidence、feasibility prototypes/audits。Formal decisionはこれらをChampion featureへ昇格させていない。 |
| Prospective and accumulating | J Stats team FULL_37 snapshots、suspension notice snapshots、ongoing schedule revisions、rolling-xG prospective inputs/cohort。 |
| Blocked/deferred | Stable player identity、referee/venue/weather/AFC/roster provenance、FootyStats/SofaScore/official historical advanced-stat coverage、J Stats player snapshots。 |
| Closed | 10 formal retrospective feature lanesすべて、promotion/J2 Elo variants、lineup continuity model use、2020–2024小規模feature探索の反復。 |

### 承認済みのimmediate next actions

1. Completed matchday後にofficial pageが更新されたらJ Stats source-state probeを実行し、`SOURCE_STATE_ADVANCED`の場合だけFULL_37を1回captureしてregistryをvalidateする。
2. Operatorがcanonical official URLを指定したnew suspension noticeだけをprospective captureし、PIT timestampと未解決player identityを保持する。
3. Append-only 2026/27 schedule/result revision workflowを維持する。
4. Frozen rolling-xG prospective cohortでは、次のofficial match IDsとprior-date xGをpublishし、documented dry-run後にrefitなしで1 date batchを書く。
5. Deferred identity/provenance laneは、documented exit conditionを満たすnew official evidenceが出た場合だけ再監査する。

Closed retrospective laneはこのaction listに含めない。
