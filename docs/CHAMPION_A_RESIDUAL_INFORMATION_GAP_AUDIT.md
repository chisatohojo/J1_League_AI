# Champion A Residual & Information-Gap Audit

監査日: **2026-10-04 (JST)**。成果物は本書のみ。

Final gate: **`NO_LANE_OPENED_NEED_TARGETED_DIAGNOSTIC`**。

推奨する次の作業は、**frozen Champion Aの行別OOF evidenceを確保し、class calibrationとseason-transitionを年度別に区別する限定診断**である。新しいfeature/model laneは開かない。現存する診断ではdrawの損失と平均確率の偏りは確認できるが、条件付きcalibration、season opening、club concentrationの年度横断の再現性が不足している。

## 1. Scope and firewall

- 新しい集計入力はordinary J1 **2015–2024の3,208試合**とexact TeamMasterだけ。Validationは2020–2024の**1,678試合**。
- 2025とopened 2026/27はselection、ranking、threshold、calibration設計の根拠に使用していない。新規分析ではこれらのmatch、prediction、model artifactをロードしていない。
- 既存のformal resultと診断文書を再利用。Model fit、calibrator fit、parameter tuning、challenger prediction、formal/preflight CLI、closed-lane再評価は実行していない。
- 既存`_add_elo()`による2015–2024のhistory replayと、結果・metadataの集計だけを実施。これはestimator fitでも新feature implementationでもない。Predictionは再計算していない。
- Raw HTML archive、live HTTP、data collection、production artifact、ongoing-v2 activation、full pytestは使用・実行していない。Raw/processed/model/prediction filesは書き換えていない。
- 補助Pythonはrepository外のtemporary directoryで実行し、dataはmemory内だけで扱った。Permanent analysis datasetやreusable moduleは作成していない。

本書の表記は、**既存事実**（source document）、**新規記述集計**（scoped dataの件数・頻度）、**推論**（説明候補）、**未確認**（不足する診断）を区別する。新規集計は新しいpredictive metricsやcandidate comparisonではない。

参照の優先順位はcurrent summary/result、frozen spec、既存code、古いroadmap/READMEの順とする。[Roadmap](NEXT_DATA_RESEARCH_ROADMAP.md)にはdraw-propensity未実行という古い段落が残るが、[正式result](TEAM_DRAW_PROPENSITY_EVALUATION.md)が優先する。Repositoryに`roadmap/` directoryはなく、root READMEと上記roadmapを確認した。README内の初期K=20等を現在のChampion contractと混同しない。

## 2. Champion A assumptions

Source: [Model freeze](MODEL_FREEZE_BEFORE_2026.md)、[Architecture benchmark spec](MODEL_ARCHITECTURE_BENCHMARK_SPEC.md)、`src/features/elo.py`、`src/modeling/player_workload_evaluation.py::_add_elo()`、`src/modeling/model_architecture_evaluation.py`。

Aはinitial 1500、K=30、update expectation内のhome advantage=175、no season reset。入力はpre-match home Elo minus away Eloの1列。Training foldのみでStandardScalerをfitし、`LogisticRegression(C=1, solver="lbfgs", max_iter=1000, random_state=0)`でclass `[0,1,2] = Away/Draw/Home`の確率へ写像する。

| Assumption | Residual evidence / uncertainty | Adjacent prior research | Relaxationのprimary type / clean evaluation条件 |
|---|---|---|---|
| Constant K=30 | Strength shockに追随しない可能性はあるが、変化速度とlossの対応は未確認 | Recent form、Gのlast-five state | TYPE 2。過去だけからshock indicatorを定義し新しいholdoutが必要 |
| Constant home advantage=175 | Away-favorite LLとHome-favorite LLに差はある。ただしdifficulty/compositionを統制しておらずHAの誤りとは言えない | Elo-only mapping、Pのhome indicator | TYPE 2。年度別signed-Elo conditional reliabilityが先 |
| Continuous strength across seasons | Returning clubのJ1離脱中rating freezeは既存事実。全club openingの問題は未確認 | Reset、J2 variants、Cup bridgeはclosed | TYPE 2。単純reset/priorの再探索不可。別の未検証問題を証明してから |
| One-dimensional team strength | Attack/defence、shot qualityを別々には持たない。残差による識別は未確認 | P、G、previous-season J Stats | TYPE 2ならstate、外部xG追加ならTYPE 3。複雑さだけは情報増加ではない |
| Symmetric rating update | 同じpre-match expectationからhomeにdelta、awayに-minus delta。asymmetric weaknessの証拠はない | Pのgoal modelは隣接するが同じ問いではない | TYPE 2。新state探索より対応する残差の確認が先 |
| No uncertainty state | Newly appearing/returning clubのratingはpoint estimate。group LL差だけではuncertainty不足を証明しない | Promotion/J2研究で近接問題を検討済み | TYPE 2。promoted flagを結果に合わせて追加することは禁止 |
| No class-specific latent process | Drawは高loss、argmax Drawは0。Draw latent processの欠落とcalibrationは未分離 | Draw propensity、P、Elo parity、Davidson関連の既存closed探索 | TYPE 1ならmapping、TYPE 2ならstate。closed variant再試行不可 |
| Logistic mapping on Elo difference only | Pooled draw probability bias、Away reliabilityの一部にずれ。fold安定性が足りない | Architecture A/P/G、Elo parity | TYPE 1。行別OOFとtraining-only calibration設計が必要 |

すべて2015–2024内で問いを設計することは可能だが、繰り返し使用されたOOFはfresh holdoutではない。将来の採用判断には別途freezeした評価期間が必要で、2025/opened 2026/27はその代替にならない。

## 3. Prior research map

以下は**既存immutable resultの転記**。Deltaは各laneのmatched baselineに対するchallenger minus baseline。異なるeligible populationsを同一rankingにはしない。Pooled LLの正値は悪化。Accuracyは採否の根拠にしない。

| Lane / question | Source / history and PIT boundary | Primary validation | Pooled LL / Brier delta | LL improved folds | Frozen decision / targeted failure mode |
|---|---|---:|---|---|---|
| [H2H](H2H_EVALUATION.md): pair-specific tendency | Prior J1 exact-pair counts、same-date excluded | 1,678 / 5 folds | +0.0016096205 / +0.0007905102 | 1/5、2023 | `CLOSE_RETROSPECTIVE_LANE`。狭いpair matchupを狙う |
| [Cup bridge](CUP_BRIDGE_EVALUATION.md): division-scale linkage | J1/J2 history + 145 verified regulation Cup events。generic Cup winner不可 | 1,678 / 5 | +0.0005008384 / +0.0005719612、C−A | 2/5、2021/2023 | `CLOSE_CUP_BRIDGE_LANE`。promotion/strength scaleを狙う |
| [Player workload](PLAYER_WORKLOAD_EVALUATION.md): fatigue/rotation | Prior J1 XI/squad normalized minutes。local raw-name key、Cup/AFC/J2/injuryなし | 1,631 / 5 | +0.008710 / +0.005292 | 1/5、2023 | `CLOSE_RETROSPECTIVE_LANE`。短期負荷だが実際の欠場ではない |
| [Previous-season J Stats](PREVIOUS_SEASON_JSTATS_EVALUATION.md): broader team profile | Prior-season final/restated profile、2026 retrieval。Historical PIT production proofなし | 1,058 / 4、2021–2024 | +0.019729 / +0.010068 | 0/4 | `CLOSE_RETROSPECTIVE_LANE`。広い前年strength/styleを狙う |
| [Team discipline](TEAM_DISCIPLINE_EVALUATION.md): card propensity | Prior J1 yellow/red rates。suspension eligibilityではない | 1,631 / 5 | +0.004739 / +0.003111 | 0/5 | `CLOSE_RETROSPECTIVE_LANE`。discipline/riskを狙う |
| [First score](FIRST_SCORE_EVALUATION.md): start/lead propensity | Prior events scored-first/conceded-first rates、target event禁止 | 1,631 / 5 | +0.0048056930 / +0.0026472702 | 1/5、2020 | `CLOSE_RETROSPECTIVE_LANE`。game-state傾向を狙う |
| [Goal timing](GOAL_TIMING_EVALUATION.md): scoring/conceding timing | Prior normalized goal minutes、availability exclusionあり | 1,576 / 5 | +0.0029941314 / +0.0018687173 | 2/5、2020/2024 | `CLOSE_RETROSPECTIVE_LANE`。temporal styleを狙う |
| [Substitution timing](SUBSTITUTION_TIMING_EVALUATION.md): intervention timing | Prior mean normalized SUB minutes。意図/選手strengthは非観測 | 1,631 / 5 | +0.0008503781 / +0.0006754870 | 1/5、2023 | `CLOSE_RETROSPECTIVE_LANE`。bench/management contextを狙う |
| [Starter DF](STARTER_DF_EVALUATION.md): defensive deployment | Previous same-season source-listed DF count。target XI/formation inferenceなし | 1,631 / 5 | +0.0003145819 / +0.0000733047 | 2/5、2020/2023 | `CLOSE_RETROSPECTIVE_LANE`。粗いlineup/style表現 |
| [Team draw propensity](TEAM_DRAW_PROPENSITY_EVALUATION.md): recurring draw tendency | Last-five/current-season symmetric raw draw rates、strictly prior、unsmoothed | 1,631 / 5 | +0.0066189847 / +0.0039225921 | 2/5、2023/2024 | `CLOSE_RETROSPECTIVE_LANE`。draw/near-evenを直接狙う |

Availability-filtered laneのS0/DP0/W0はall-row Aとは違うtraining population。1,631群はfull 1,678から47件、goal timingは102件を除く。差を同じAのresidualとして比較しない。

### Architecture cycle and adjacent experiments

| Candidate / lane | Existing result | Boundary and interpretation |
|---|---|---|
| [A reference](MODEL_ARCHITECTURE_BENCHMARK_RESULT.md) | n=1,678、Accuracy 0.466626936829559、LL 1.056065401323764、Brier 0.635732341929272 | Champion/reference gate PASS |
| P independent Poisson | LL delta +0.001562503284968、Brier +0.001778814919845、3/5 folds改善（2022–2024） | `CLOSE_ARCHITECTURE_CANDIDATE`。team attack/defence categorical blocks + Elo/home、independent score process |
| G fixed LightGBM form | LL delta +0.009111421708431、Brier +0.005858678190648、0/5 | `CLOSE_ARCHITECTURE_CANDIDATE`。Eloを含むexact nine-field state vector、last-five form |
| [Promotion/J2](ELO_PROMOTION_J2_EXPERIMENT_SUMMARY.md) | ResetはLL −0.000394だが2/5。Equal J1+J2、1400 prior、calibrated、hybridはpooled Aに届かない | `CLOSED FOR NOW`。retained stale ratingの存在と有効な修正ruleを区別 |
| [Lagged lineup continuity](J1_LAGGED_LINEUP_CONTINUITY_FEASIBILITY.md) / [model freeze](MODEL_FREEZE_BEFORE_2026.md) | Raw-name short-term coverage 99.06%。modelはpooled LL改善せずclosed | overlap countはplayer quality/availabilityではない |
| [Domestic Competitive Rest](MODEL_FREEZE_BEFORE_2026.md) | B−A LL −0.000527、Brier −0.000681、3/5 | Bは既存frozen Challenger。schedule congestionを未検証情報と扱わない。A remains Champion |

P/Gはretainedでなく、`retained_candidate = null`。これらの不採用は全architectureや全football informationが無価値という証明ではない。New P/G variant、smoothing、subset、model combinationは推奨しない。

### Deferred information map

| Area / source | Established blocker | Meaning for residual research |
|---|---|---|
| [Manager identity](JLEAGUE_MANAGER_IDENTITY_AUDIT.md)、[unresolved audit](JLEAGUE_MANAGER_UNRESOLVED_AUDIT.md) | 6,058/6,416 resolved、358 appearances / 9 namesはreplacement-character未解決。historical assignment availabilityも別問題 | System-change shockの候補だが、target final-page managerをpre-match通知とみなさない。old Manager modelもclosed |
| [Historical suspension](JLEAGUE_SUSPENSION_DATA_FEASIBILITY.md) | Historical completeness/as-of body/player identity不足。既存overall判定C（historical productionは未安全） | Actual availabilityはcard-rate laneと別。current noticesの後付けでhistorical featureを作れない |
| [Stadium/travel](H2H_STADIUM_FEASIBILITY.md) | `DEFER_STADIUM`、stable venue/neutral-site/PIT不足 | Signed-Elo biasをvenue/travelの原因と断定不可 |
| [AFC](AFC_DELIVERY_MATRIX_2015_2024.md) | Year-complete identity/time coverageなし、reports/PDF/article混在 | Domestic Restの欠けたcompetition context候補。ただし全historyを補完できない |
| [Referee](J1_REFEREE_HISTORY_FEASIBILITY.md) | `DEFER_REFEREE_ASSIGNMENT_PROVENANCE` | Final-page referee nameはkickoff前assignmentの証拠ではない |
| [Weather](J1_PREMATCH_WEATHER_FEASIBILITY.md) | `DEFER_WEATHER_VENUE_IDENTITY`、issued-before forecast archiveも未確立 | Realized weatherをpre-match forecastへ置換不可 |
| [Roster/injury](J1_ROSTER_AVAILABILITY_FEASIBILITY.md) / player identity | `DEFER_PLAYER_IDENTITY`、effective-dated complete roster/return archiveなし | Raw namesやnotice absenceをavailability stateへ変換できない |
| [Player snapshots](J_STATS_PLAYER_SNAPSHOT_IDENTITY_CLARIFICATION.md) | 1,110 direct/photo ID一致、残る5 candidatesはperson evidenceなし、collector authorization NO | Complete player layerに進めない。ランキング非掲載はzeroではない |
| [Historical xG](J_STATS_MATCH_LEVEL_ROUTE_DEEP_AUDIT.md) | 2018–2023 production match-level routeなし。2024後半96試合のpartial evidenceだけ | Full OOF xG研究は現状不可。previous-season aggregateの失敗はrecent xGの検証ではない |

最新summary/DECISIONSにあるprospective suspension/PIT registryの到達点はdata-platform上のhistorical factとしてのみ確認した。2026/27 evidenceやperformanceは上記rankingの根拠に用いていない。

## 4. Closed-lane interpretation

分類候補はA=no signal、B=weak signal、C=wrong representation、D=rare signal、E=temporal/PIT limitation、F=architecture interaction、G=unknownである。

**全closed laneで因果的な結論はG**。単一representationのpooled不改善はunderlying conceptのzero informationを証明しない。B/C/D/Fは下記の可能性に留める。isolated fold改善をrobust signalとしない。

| Lane group | Supported fact | B/C/D/E/Fを論じられる範囲 |
|---|---|---|
| H2H | Broad pair-count追加はpooled悪化、1foldだけ改善 | Pair interactionのsparsity/representationはC/D候補。真のtactical matchupは未測定 |
| Cup bridge / J2 | Verified cross-division resultsでもpooled Aに届かない | B/C/D候補。returning subgroup改善が全体改善に直結しない。PIT解決だけではpredictive採用にならない |
| Workload / continuity / DF / SUB | 過去負荷・人数・overlap・timingのexact表現が採用条件を満たさない | C候補。target選手quality/absenceと過去minutesは別。D/Fは未検証 |
| Previous-season J Stats | 全4foldでpooled matched LL悪化、PIT productionにも限界 | Eは明示的source limitation。C/B/Fは仮説。recent rolling xGへの否定ではない |
| Discipline / first-score / goal timing | Historical raw event propensityでpooled LL悪化 | C/D候補。actual target suspensionや将来red cardは観測していない |
| Draw propensity | DP1は2/5改善でもpooled悪化、matched mean Draw確率も低下 | C/Fは未検証。Draw biasを実際に修復した実験とは言えない |
| P / G | Pは3/5、Gは0/5、両方pooled LL/Brier悪化 | Frozen score assumptions/form representationの失敗。Architecture complexityがincremental informationを作った証拠はない |

Small positive/negative deltaにはfold間依存、season composition、sample uncertaintyがある。本taskはpaired uncertainty testやmodel比較を再計算していない。New challengerを「promising」と判定しない。

## 5. Residual audit methodology

### Evidence availability and fit boundary

Scoped storage inspection: `data/processed/modeling/`にはopened interim predictionsのみ、`data/processed/model_architecture/`にはattempt markerのみ。Prediction directoryにはprospective filesのみ。Model A directoryにはoperational bundleのみで、fold bundleは見つからない。これらのexcluded predictions/bundlesの内容はロードしていない。検索した保存領域とasset inventoryの範囲で**exact retrospective A row probabilitiesは未発見**であり、repository全体の全隠しfileが不存在という主張ではない。

`model_architecture_evaluation.py::_evaluate_a()`はfresh fold fitからprobability arraysをmemory内に作る。Formal writerはmetricsだけを保存し、fold coefficients/scaler/row probabilitiesを保存しない。既存H2Hも同様にfit/aggregate/reportする。Formal markerとresultは既に存在するのでCLIを呼ばない。

A operational bundleは2015–2025 trainingを含み、2020–2024 targetsのretrospective A_Y代替にはならない。Aggregate metricsから1678×3確率を一意に逆算することもできない。したがって**A fit/reconstructionを今回行う安全な経路はない**。後続診断を行うなら、新たな明示的A-only diagnostic authorizationまたはoriginal OOF evidenceの受領が必要。

### Source validation and descriptive pass

`load_matches()` + `load_team_master().add_team_ids()`で2015–2024の10 CSVを読み、unique IDs、score/result consistency、exact aliases、season countsを確認。`_add_elo()`をそのまま再利用し、全streamのdate/match_id順とsame-date conservative batchを維持した。Source DataFrameの非変更とinput file SHA一致をassertした。Elo以外のfeature artifacts、J2/Cup/raw HTMLはロードしていない。

| Validation year | Train n | Validation n | Actual Away/Draw/Home |
|---:|---:|---:|---|
| 2020 | 1,530 | 306 | 120 / 68 / 118 |
| 2021 | 1,836 | 380 | 126 / 94 / 160 |
| 2022 | 2,216 | 306 | 87 / 97 / 122 |
| 2023 | 2,522 | 306 | 99 / 78 / 129 |
| 2024 | 2,828 | 380 | 130 / 104 / 146 |
| Pooled | — | 1,678 | 562 / 441 / 675 |

Source countsは2015–2020各306、2021=380、2022–2023各306、2024=380。2015はhistory左端であり、pre-2015のmembership/strengthは推定しない。Core入力SHA-256は以下。Analysis開始/終了で一致した。

| Input | SHA-256 |
|---|---|
| 2015 matches | `ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353` |
| 2016 matches | `4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f` |
| 2017 matches | `d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b` |
| 2018 matches | `f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681` |
| 2019 matches | `3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f` |
| 2020 matches | `fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17` |
| 2021 matches | `298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6` |
| 2022 matches | `d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2` |
| 2023 matches | `6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9` |
| 2024 matches | `4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1` |
| `data/master/teams.csv` | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` |

### Fixed descriptive views / missing row-level quantities

Binsはperformanceを最適化して選んでいない。既存auditのabs-Elo/max-probability/favorite ruleをそのまま採用。Season phaseは単純なround 1–5 / 6–29 / 30+を事前に定義して集計した。38-round seasonはclosingが長いので、同じphaseのnが年度で違う。Roundは延期試合の実chronologyと一致しないため、opening-after-boundaryは別にteamごとのchronological appearance 1–5で記述する。

| Required axis | Available now | Exact targeted diagnostic still needed |
|---|---|---|
| A Season phase | Phase outcome counts、first-five appearance denominators | Phase別A NLL/Brier、各foldとの対照 |
| B Elo confidence | Existing abs binsとpooled LL、新signed Elo outcome頻度 | 各foldの同じbinでA loss/reliabilityが反復するか |
| C Prediction confidence | Existing fixed max-p binsのpooled confidence/accuracy/LL | 年度別・predicted-class別reliability |
| D Outcome class | Existing class NLL/Brierとactual counts | 年度別class conditional NLLと各class mean-p残差 |
| E Favorite failure | Existing probability-based Home/Away/near-even aggregate LL | Home favorite loses、Away favorite loses、favorite draws、near-even各outcomeのn/loss。`abs(p_home-p_away)<0.05`は据置 |
| F Structural transitions | Prior J1 membershipでpromoted/returningを識別、既存first 1–3/4–10/11+診断 | Promotedとestablishedのopening比較、recently promoted（前年entry）との対照、shockの反復 |
| G Club concentration | Exact stable team IDsあり | Club×foldのA loss/n、team両side countの二重計上明示。High-loss clubsを原因やtuning対象としない |
| H Fold stability | Full-fold LL、class means、既存closed-lane fold改善 | 上記bucket全部の年度横断安定性、単年度依存・small nの確認 |

行別auditのschemaは`season, match_id, match_date, home_team_id, away_team_id, result, elo_diff, p_away, p_draw, p_home`が最低限。`predicted_class=argmax`、`max_p=max(p)`、`nll=-log(p_true)`、`brier=sum((p-one_hot)^2)`、`abs_elo_diff`をmemory内で診断する。Probability row sumはrtol=0/atol=1e-12、class order固定。Target/same-date/later resultは当該prematch stateに入れない。

Raw Elo signはprobability favoriteと異なる。Home effectはmappingにも含まれるため、`elo_diff<0`をAway favoriteへ置換しない。No optimal cutoff、no outcome-driven club selection、no calibrator fit。

## 6. Residual findings

### Existing class loss and intrinsic difficulty

Source: [ELO_OOF_ERROR_ANALYSIS.md](ELO_OOF_ERROR_ANALYSIS.md)。以下は既存値で再計算していない。

| True class | n | Mean p(true) | Mean NLL | Share of total NLL | Mean Brier | Share of total Brier |
|---|---:|---:|---:|---:|---:|---:|
| Away | 562 | 0.392722 | 0.980890 | 31.1081% | 0.587605 | 30.9568% |
| Draw | 441 | 0.239007 | 1.433470 | 35.6734% | 0.893757 | 36.9481% |
| Home | 675 | 0.437424 | 0.872084 | 33.2185% | 0.507227 | 32.0952% |

元文書のNLL/Brier contributionはpooled meanへの絶対加算値ではなく、各loss総量のshareとして読む。Drawが441/1678（26.28%）なのにloss share最大なのは重要。ただしrare/nonmodal classはwell-calibrated modelでもconditional NLLが高くなり得る。**高いDraw NLLだけではmiscalibrationも新featureの有効性も証明しない**。

### Elo bins and probability favorites

新規のexact A/D/H countsと既存pooled LLを併記する。同じ全1,678 populationとbin件数が一致した。

| abs Elo diff | n | Actual A/D/H | Existing A LL |
|---|---:|---|---:|
| [0,50) | 470 | 156 / 132 / 182 | 1.090646 |
| [50,100) | 450 | 158 / 120 / 172 | 1.071142 |
| [100,200) | 514 | 169 / 141 / 204 | 1.060399 |
| [200,300) | 188 | 64 / 36 / 88 | 0.928544 |
| [300,infinity) | 56 | 15 / 12 / 29 | 1.033019 |

Near-evenは情報上も難しい。高LLは予測の失敗と高outcome entropyを分離しておらず、追加contextを入れれば改善するという証拠ではない。300+の非単調性は56件だけであり、threshold/K変更の根拠にしない。

既存probability-based near-evenはn=259、LL=1.098304、Home favoriteはn=826/LL=1.026427、Away favoriteはn=593/LL=1.078901。Favorite loses/drawsの内訳と年度反復は未確認。Away-favoriteのLL高値を単独でHA drift、travel、lineupに帰属させない。

### Signed Elo versus actual frequency: new context, not residual proof

| Signed home-minus-away Elo | n | Actual A/D/H |
|---|---:|---|
| <−200 | 117 | 60 / 27 / 30 |
| [−200,−50) | 469 | 203 / 132 / 134 |
| [−50,50) | 470 | 156 / 132 / 182 |
| [50,200) | 495 | 124 / 129 / 242 |
| 200+ | 127 | 19 / 21 / 87 |

Home強度が高いbinでHome頻度が高いというexpected方向は見える。この表にbin別A probabilityがないので、linear mappingの誤りやclass-specific processの必要性は判定できない。

### Season and team concentration

既存fold LLは2020=1.023120、2021=1.025344、2022=1.094019、2023=1.060429、2024=1.079241。2022が難しく2024も高いことは既存事実。ただし連続したmonotonic deteriorationやregime driftは証明していない。

Club別A lossとtail loss concentrationは**未確認**。Match countやdraw countだけでclub-specific excess lossを作らない。二つのclubに同じmatch lossを付与する診断ではtotalが2倍になるため、future reportはmatch単位のloss totalとteam-side meanを分離する必要がある。

## 7. Calibration findings

### Bias recurrence from already-saved full-population diagnostics

Source: [H2H resultのS0 draw diagnostics](H2H_EVALUATION.md)。Countsと平均A Draw確率は既存値、actual frequency/gapは保存済みsummariesの算術でありA predictionの再計算ではない。

| Fold | n | Draw count | Actual Draw frequency | Mean A p_draw | Actual minus predicted |
|---:|---:|---:|---:|---:|---:|
| 2020 | 306 | 68 | 0.222222222 | 0.231154403 | −0.008932181 |
| 2021 | 380 | 94 | 0.247368421 | 0.228307619 | +0.019060802 |
| 2022 | 306 | 97 | 0.316993464 | 0.234957047 | +0.082036417 |
| 2023 | 306 | 78 | 0.254901961 | 0.244686284 | +0.010215677 |
| 2024 | 380 | 104 | 0.273684211 | 0.248152218 | +0.025531992 |
| Pooled | 1,678 | 441 | 0.262812872 | 0.237520170 | +0.025292703 |

**事実:** Draw underprediction-in-the-largeの方向は4/5で反復。2020は逆方向。特に2022のgapが大きく、constant draw upliftが全年度に適切という証拠ではない。Draw頻度の変動がdata-generating regime、sample variation、mapping lagのどれによるかは未分離。

全fold A argmax Drawは0だが、argmax zeroは確率calibration failureとは同義でない。Threshold変更でDraw recallを増やす研究は推奨しない。

### Existing probability reliability

Source: [既存error analysis](ELO_OOF_ERROR_ANALYSIS.md)。全部pooledであり、year安定性は未確認。

- Drawは1,619件がp=[0.2,0.3)に集中し、mean predicted=0.239480、actual frequency=0.265596。低p=[0.1,0.2)の59件では0.183735対0.186441。Broad single binのgapではshape errorとintercept driftを区別できない。
- Awayのp=[0.3,0.4)は529件で0.349113対0.323251、[0.5,0.6)は157件で0.541685対0.490446。[0.6,0.7)は34件で0.637874対0.441176。Away overprediction候補だがsmall tailとyear compositionに注意。
- Homeのp=[0.4,0.5)は466件で0.448695対0.444206。[0.1,0.2)は61件で0.164635対0.262295、[0.6,0.7)は84件で0.639074対0.678571。両tailにunderprediction方向があるが、general Home upliftやglobal temperature ruleは示さない。

| Existing max-p bin | n | Mean confidence | Empirical argmax accuracy | A LL |
|---|---:|---:|---:|---:|
| <0.40 | 249 | 0.387470 | 0.401606 | 1.094142 |
| [0.40,0.50) | 869 | 0.445271 | 0.437284 | 1.077664 |
| [0.50,0.60) | 425 | 0.543518 | 0.517647 | 1.024936 |
| [0.60,0.70) | 118 | 0.638728 | 0.610169 | 0.947725 |
| 0.70+ | 17 | 0.742074 | 0.647059 | 0.924529 |

Highest confidenceの17件はstrong evidenceにならない。Pooled confidenceはmiddle/high binsでaccuracyを上回るが、class-wise reliabilityの符号は一様でなく、**systematic global overconfidenceとは結論しない**。

必要な未実行viewは、(a)各predicted class内のmax-p reliability、(b)Away/Draw/Home one-vs-rest reliabilityのfold別固定0.1 bins、(c)signed-Elo別actual frequency対A mean-p、(d)season phase別class bias。Predicted class=Drawは空cellを明示する。小cellをadaptiveにmergeしてcutoffを選ばない。

CalibrationはTop 1の**診断候補**だが、calibratorをfitすればLLが改善する証拠はまだない。Platt/isotonic/temperature/beta、ECE-minimization、draw prior/threshold/weight変更は実行していない。

## 8. Season-transition findings

### New season-phase outcome context

以下は新規記述集計。Opening/middle/closingの**outcome frequency**であり、phase residual lossではない。

| Fixed round phase | n | A/D/H | Draw frequency |
|---|---:|---|---:|
| Opening, round 1–5 | 235 | 79 / 68 / 88 | 0.289362 |
| Middle, round 6–29 | 1,128 | 375 / 283 / 470 | 0.250887 |
| Closing, round 30+ | 315 | 108 / 90 / 117 | 0.285714 |

| Fold | Opening Draw/n | Middle Draw/n | Closing Draw/n | Any team first-five chronological appearance n |
|---:|---|---|---|---:|
| 2020 | 10/45 = 0.222222 | 43/216 = 0.199074 | 15/45 = 0.333333 | 45 |
| 2021 | 11/50 = 0.220000 | 61/240 = 0.254167 | 22/90 = 0.244444 | 55 |
| 2022 | 20/45 = 0.444444 | 60/216 = 0.277778 | 17/45 = 0.377778 | 50 |
| 2023 | 13/45 = 0.288889 | 52/216 = 0.240741 | 13/45 = 0.288889 | 45 |
| 2024 | 14/50 = 0.280000 | 67/240 = 0.279167 | 23/90 = 0.255556 | 51 |

Opening draw excessは2021では逆、2024ではほぼ同じ。Closingも毎年度の共通patternではない。Round 1–5とchronological first-fiveでは対象が一致しない。Continuous Eloのoffseason weaknessやreset有効性をこの集計から認定できない。

### Promotion / returning history

Promoted flagはcurrent J1 team set minus previous-season J1 set。これはmembership-derived entrantであり、J2/J3のofficial promotion経路を今回再調査したものではない。Returningはpre-current-yearのJ1 appearanceあり。過去membershipだけを使い、future roster/rankingsは使わない。

| Fold | Promoted-involved match n | Returning-involved match n |
|---:|---:|---:|
| 2020 | 66 | 34 |
| 2021 | 74 | 38 |
| 2022 | 66 | 34 |
| 2023 | 66 | 66 |
| 2024 | 108 | 38 |
| Total | 380 | 210 |

New source countsは既存diagnosticの380 promoted / 1,298 otherに一致。Actual A/D/Hはpromoted=131/105/144、other=431/336/531。Draw rateは0.276316対0.258860だが、これはそのgroupのcalibration errorを証明しない。

既存A promoted LL=1.087216、other=1.046946。First-time-in-scoped-history n=170/LL=1.065951、returning n=210/LL=1.104431。Returningで高lossという候補はあるがfold別lossは未確認。両群はclub strength、schedule、class compositionが異なる。

[Existing reset evaluation](ELO_PROMOTION_RESET_EVALUATION.md)のpromoted-season appearance診断ではA first 1–3はn=31/LL=1.103367、4–10はn=75/LL=1.056948、11+はn=274/LL=1.093674。Earlyの小標本だけが問題とは言えない。Resetはfirst 1–3を1.118940へ悪化させ、pooled改善も2/5のみだった。これらは既存resultの引用で、再評価していない。

**結論:** J1離脱中のstale stateはstructural fact。全club offseason shock、recently-promotedとestablishedの違い、opening lossの反復は未確認。単純reset、promoted prior、dynamic K、roster/manager featureへ進む根拠は不足。Strength discontinuityをfuture outcomesから逆算してtargetのfeatureへ入れることも禁止する。

## 9. Residual vs closed-lane map

| Pattern / evidence level | Prior lane | Classification | What remains unanswered |
|---|---|---|---|
| Draw high loss / 4-of-5 average-p deficit | Team draw propensity、H2H draw counts、P、Elo parity/Davidson adjacent exploration | **RESIDUAL ALREADY TARGETED BY CLOSED LANE**（exact propensity/score表現） | Conditional calibrationとyear-specific class driftは別問い。Propensity retry不可 |
| Near-even pooled high loss | H2H、draw propensity、G、parity | **RESIDUAL ALREADY TARGETED BY CLOSED LANE**（broad proxies） | Intrinsic difficultyを超えるexcess loss、target availability/xGの説明力は未証明 |
| Returning/promoted pooled high loss | Reset、J2 variants、Cup bridge、previous-season profiles | **RESIDUAL ALREADY TARGETED BY CLOSED LANE** | 全club openingとuncertaintyのfold安定性は未確認。promotion lane再開不可 |
| Away-favorite loss / Away reliability gaps | A/P/G、Domestic Restは一部adjacent | **RESIDUAL NOT YET EXPLAINED** | Class mapping、home/venue effect、match compositionの区別 |
| 2022 high LL / large Draw gap | 所有するclosed representationはどれも全体改善を示さない | **RESIDUAL NOT YET EXPLAINED** | Outcome mixture、calibration drift、情報不足、samplingの区別 |
| Fatigue/discipline/game-state context | Workload、discipline、first-score、goal/SUB timing | **RESIDUAL ALREADY TARGETED BY CLOSED LANE**（proxy） | 実際の欠場・player qualityとproxyの差。Corresponding stable residual自体は未観測 |
| Club-specific tails / opening shocks | 正確なclub×fold residualは未保存 | **RESIDUAL NOT YET EXPLAINED / NOT YET MEASURED** | Concentration、recurrence、rare-tail loss。Club別tuningの根拠にしない |

「already targeted」は解決済みを意味しない。「not explained」も対応するnew sourceが有効という意味ではない。

## 10. Information-gap map

| Human analystが知りたい情報 | Aにないもの | Evidence linkage / feasibility |
|---|---|---|
| Class uncertainty / probability mapping | Eloだけのsoftmaxがseason mixtureを表せるか | Draw平均biasを一部観測。TYPE 1、row OOFが不足 |
| Recent strength trajectory / chance quality | Win/draw/loss以外のxG/xGA、chance creation/finishing | TYPE 3。Recent form/Gや前年J Statsとは違う。ただし2015–2024 full PIT xGなし |
| Actual lineup quality / availability | 主力のabsence、予想/発表XI、bench quality | TYPE 3。Past workload/DF/continuityだけでは代替不可。Historical identity/PITがblocked |
| Offseason structural changes | Transfer/roster turnover、manager/system change | TYPE 3。Opening残差の安定性未確認、effective-dated source不足 |
| Entry uncertainty / strength volatility | Stale/uncertain Elo state | TYPE 2。Promotion/J2 adjacent branches closed。新しい別問いの証拠なし |
| Market consensus | 多面的informationを集約したodds | TYPE 3。Historical version/time/bookmaker/margin/rights contract未確立。今回source探索・ranking採用なし |
| Congestion / travel / venue | J1外負荷、neutral venue、distance | TYPE 3。Domestic Rest Bで一部既検証。AFC/venue完全性不足 |
| Red-card / suspension context | 実際のeligibility、rare disciplinary shock | TYPE 3。Prior card率の失敗はabsence情報の否定ではない。Future eventを使うことは禁止 |

Finish/shot quality、system change、availabilityは説明仮説であり、現在のresidualとのmatched associationは測定していない。2025/2026情報の良さを見てhypothesisを選んでいない。

## 11. Candidate ranking

### Rubric and opening gate

0=unsupported/blocker/high cost、1=partial/conditional、2=strong/evidenced/low costとする。Bはmultiple fold recurrence、Dはclosed representationとの非重複（2=distinct）、E/FはそれぞれPIT safety/historical availability、Iはleakageを避けられる度合い（2=low risk）。Jはproper-score改善への根拠で、Accuracyだけは0。Unknownを高scoreへ補完しない。

A–Jは順に **residual evidence / fold stability / incremental information / non-overlap / PIT / historical data / low implementation complexity / prospective maintainability / low leakage risk / LL relevance**。Scoresは定性的整理であり、gain予測や新しいmodel rankingではない。A/Bとdata blockerを優先し、合計scoreだけでlaneを開かない。

| Rank / primary type | A | B | C | D | E | F | G | H | I | J | Total / disposition |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 Calibration / probability mapping — TYPE 1 | 1 | 1 | 1 | 2 | 2 | 0 | 2 | 2 | 1 | 1 | 13/20。Targeted diagnostic now、research spec未承認 |
| 2 Recent xG information — TYPE 3 | 0 | 0 | 2 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 8/20。Historical lane deferred |
| 3 Lineup / player availability — TYPE 3 | 0 | 0 | 2 | 1 | 1 | 0 | 0 | 1 | 0 | 1 | 6/20。Identity/PIT deferred |

TYPE 2 season-transition/Elo-state候補は既存closed branchとのoverlap vetoと未測定opening recurrenceによりTop 3へ入れない。これはTYPE 2に情報がないという判定ではない。Dynamic K、uncertainty-aware Elo、home-advantage driftも対応する安定した残差未確認。Market/odds、competition/regime driftもunsupportedのまま。

### 1. Calibration / probability mapping

- **Question:** Class-specific conditional probability errorは複数年度で再現するか。それとも2022のoutcome mixtureやdifficultyだけか。
- **Residual evidence:** Draw gapは4/5だが2020で逆符号、2022最大。Awayのpooled reliabilityも候補。Conditional/year reliabilityは不足。
- **Aの欠落 / closed lanesとの差:** Elo-only logistic mappingの条件付き妥当性。Draw-rate feature/P/G比較はA probabilityのindependent calibration testではない。TYPE 1は新external informationを増やさない。
- **PIT/data:** Exact A_Y row probabilities + match metadata。Training OOFまたはchronological calibration partitionが必要。Operational 2015–2025 bundleは使用不可。
- **Future evaluation design:** 最初は診断だけ。Research specへ進む場合、target yearのlabelを使わずtraining内だけでcalibrationをfitする一意なruleと、別途untouched validation期間をfreeze。Calibrator一覧を今回選択しない。
- **Leakage/failure:** Validation frequencyでp_drawを補正するとleakage。Training calibrationがnext-year regimeに転移せず、sparse high-confidence binやsingle-year anomalyに過適合し得る。
- **STOP / timing:** Row OOF identity/reference mismatchで停止。Conditional biasがyear横断で反復せず、global offsetだけが単年度に依存する場合はspecへ進まない。**Nowは限定診断のみ**。

### 2. Recent xG information

- **Question:** Prior-date shot/chance qualityはW/D/L Eloが追いつかないstrength trajectoryを説明するか。
- **Residual evidence:** One-dimensional outcome strengthの限界は仮説で、xGとのresidual associationもfold安定性も未測定。
- **Aの欠落 / closed lanesとの差:** Recent chance creation/allowedはprior-season final profile、SH count、last-five points/GF/GAとは別。ただしprevious-season J Stats/P/Gに隣接しているため完全なnon-overlapとはしない。
- **PIT/data:** Historical match-level xGのstable identity、methodology、source revision、availability timestamp、lawful accessとyear-complete coverageが必要。Cumulative FULL_37からmatch xGを逆算しない。2024後半96試合だけを選んでOOF研究の代替にしない。
- **Future evaluation design:** Historical sourceが安全になった場合のみ、prior-date feature group/availability ruleとcommon-target baselineをfreezeし、適切なnew validation periodで一度比較。現prospective cohortはfrozenな別cycleとして扱う。
- **Leakage/failure:** Target xG、restated values、missingness-dependent subset selection、source regime change。xGがEloと重複しLL改善しない可能性。
- **STOP / timing:** Full coverage/identity/as-of証拠がなければhistorical specを止める。**Later/deferred**。Prospective data維持の価値は別であり、本taskから新collectionを開始しない。

### 3. Lineup / player availability

- **Question:** Pre-kickoffに知り得た重要playerのabsence/lineup qualityは同じEloでも変わるmatch-specific uncertaintyを説明するか。
- **Residual evidence:** Favorite failure/club-tail bucketとの関係は未測定。現状はfootball explanation hypothesis。
- **Aの欠落 / closed lanesとの差:** Actual availability/qualityとlagged minutes、overlap、DF count、card propensityは異なる。Unknown identityをraw-name mergeで補わない。
- **PIT/data:** Exact longitudinal player IDs、effective-dated rosters、complete availability/return evidence、capture-time fixture/kickoff linkageが必要。No notice=UNKNOWN。Current prospective platformの完成度からhistorical安全性を推定しない。
- **Future evaluation design:** Coverage auditを先行。Separate freezeで一意なgroup/availability ruleを定義し、同じeligible populationのbaselineとnew untouched periodで比較。Target final XIをT−24h predictionに使わない。
- **Leakage/failure:** Published後のcorrection、後から判明したabsence、outcome-dependent retrieval、shirt/name identity誤結合。Coverageが低くrare signalが全体LLに届かない可能性。
- **STOP / timing:** Stable identity、as-of availability、absence semanticsのいずれかが未解決なら止める。**Deferred**。

## 12. Recommended next lane

**`NO LANE OPENED — NEED TARGETED DIAGNOSTIC FIRST`**。

Recommended next actionは一つだけ: **A-only fixed-OOF evidence / calibration-versus-transition diagnostic**。Calibrationはfuture research候補の1位だが、現時点で`PROCEED_TO_CALIBRATION_RESEARCH_SPEC`へ進めない。

理由は(1)最も直接的なprobability証拠がDraw平均bias、(2)conditional reliabilityの年度再現性が未確認、(3)existing draw/promotion proxiesはすでにclosed、(4)external historical sourcesにはPIT/identity/coverage blockers、(5)A row probabilitiesを新fitなしで使う証拠がないためである。

後続taskの具体的なdeliverableと実行条件:

1. Original formal processのexact A fold arraysまたはfrozen A fold bundlesを取得できるかを限定確認。得られなければ別taskで**Aのみのdiagnostic fit**を明示的に承認する必要がある。現在のformal/preflight CLIやP/G runnerを呼ばず、one-shot markerを変更・削除しない。
2. A-only reconstructionが別途承認された場合、同じfull-history Elo、same-date policy、5fold、train-only scalerを一度だけ再現し、各fold LL referenceおよびpooled n/Accuracy/LL/Brierをrtol=0/atol=1e-12でgate。Failureはstop。Source/spec hash、classes、IDs/order、fit scopeのprovenanceを保持する。Current taskでは未実行。
3. 上記§5の固定viewsを全5foldに適用。Year×class probability means、fixed-bin reliability、favorite-failure losses、phase/appearance/promoted/established losses、club concentrationを全体と一緒にreport。Missing/empty/sparse cellsを明示。
4. High NLLとavoidable miscalibrationを区別し、yearごとの方向・件数・loss寄与を示す。Team/date依存を考慮したuncertainty方法はanalysis前にfreezeする。2022のみ、少数clubsのみ、openingのみを結果に合わせてselection setへ昇格させない。
5. Conditional biasが複数年度で反復し、global/class mappingの問いがclosed lanesと区別できる場合だけTYPE 1 specを検討。Season-transitionなら全club/establishedも含む独立した反復証拠とclosed-branchとの非重複が先。どちらも不足ならgateを維持する。

この診断はcalibrator/alternative Elo/feature implementationやformal evaluationを含まない。既存OOFでhypothesisを選ぶ以上、後のeffectiveness判定を同じOOFだけでconfirmed generalizationとはしない。

## 13. Explicit non-recommendations

- Draw propensity再試行、window/smoothing/subset/interaction、draw threshold/class weightでrecallを稼ぐこと。
- H2H/workload/discipline/first-score/goal timing/SUB/DF/previous-season profilesの組合せ・再評価。
- P/Gの再fit、parameter変更、Dixon–Coles、CatBoost/別LightGBM、architecture complexityだけの探索。
- Simple season reset、promoted priors、J2 initial offsets/shrinkage、club別補正、dynamic K/HA sweep。
- 2025/opened 2026/27で候補をtie-breakすること、current operational bundleでhistorical A probabilitiesを作ること。
- Current cumulative snapshotsのhistorical match値復元、final-page referee/roster/manager/weatherをprematch evidenceへ投影すること。
- Market consensus、manager/roster turnover、uncertainty Eloを「高度だから」という理由でlane化すること。
- Champion Aの置換、existing B/rolling-xG/P/G prospective recordの変更、ongoing-v2 activation。

## 14. Data/PIT requirements

**Immediate diagnostic:** 2015–2024 source、TeamMaster、exact frozen A OOF probabilitiesまたはoriginal fold fit state、2020–2024 references。Inputがscoped 3,208、OOFが1,678、output only docsという境界を維持する。Source-level cancelled/postponed/date semanticsは既存contractのまま。2024 suspended/resumed fixtureの日付を独自補正しない。

**TYPE 1:** Calibration trainingにfuture validation labelsを混ぜない。Historical OOF diagnosticはsource informationのpublic-availability proofとは別である。

**TYPE 2:** Season entry、state shock、uncertainty定義をstrictly priorで固定。未来strength/season-final standingsを遡及的state labelとしてinputにしない。Closed promotion/search枝の再開は禁止。

**TYPE 3:** Exact source identity、observation/publication/update/effective timestamps、target fixtureとcapture-time kickoff、raw hash、revision policy、scope completenessを証明。Unknownをzero/league meanとしない。External collection/accessの新承認は別task。

Prospective FULL_37、rolling-xG、suspension/PIT platformの保守は現在の承認済みdata方針を維持する。本taskの残差mapから新collector/featureを追加しない。

## 15. Decision gate

**`NO_LANE_OPENED_NEED_TARGETED_DIAGNOSTIC`**。

Established: Draw high loss、Draw平均biasの4/5年度方向、near-even pooled difficulty、promoted/returning pooled difficulty、all ten formal feature lanes/P/G closed。

Unresolved: Conditional calibrationのyear stability、favorite-loss decomposition、全club opening loss、recently-promoted versus established、club/year loss concentration、missing external informationとの対応。Outcome countsやpooled meansだけではこれらを認定できない。

Validationはsource/date/ID/count/score/alias gate、既存abs-Elo countsの一致、input SHAの非変更、diagnostic scriptのassertions、Markdown diff checkのみ。Full pytestはNOT RUN。Changed tracked scopeは本document一件。Formal benchmark/closed-lane再評価/fit/prediction/calibrator/tuning/HTTP/collectionはすべてNOT RUN、pushは未実施。

### Reviewed evidence index

- Navigation: [PROJECT_RESEARCH_SUMMARY.md](PROJECT_RESEARCH_SUMMARY.md)、[DATA_ASSET_INVENTORY.md](DATA_ASSET_INVENTORY.md)、[NEXT_DATA_RESEARCH_ROADMAP.md](NEXT_DATA_RESEARCH_ROADMAP.md)、[DECISIONS.md](DECISIONS.md)、root [README](../README.md)。
- Core: [MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md)、[ELO_OOF_ERROR_ANALYSIS.md](ELO_OOF_ERROR_ANALYSIS.md)、[MODEL_ARCHITECTURE_BENCHMARK_SPEC.md](MODEL_ARCHITECTURE_BENCHMARK_SPEC.md)、[MODEL_ARCHITECTURE_BENCHMARK_RESULT.md](MODEL_ARCHITECTURE_BENCHMARK_RESULT.md)、[TEAM_DRAW_PROPENSITY_FEATURE_SPEC.md](TEAM_DRAW_PROPENSITY_FEATURE_SPEC.md)。
- Formal result verification: H2H、Cup bridge、Player workload、Previous-season J Stats、Team discipline、First score、Goal timing、Substitution timing、Starter DF、Team draw propensityの上記linked result文書。
- Adjacent/deferred: Promotion Reset、Promotion/J2 Summary、Lineup Continuity、Manager Identity/Unresolved、Historical xG Route、Historical Suspension、Suspension Runbook、Stadium、Referee、Weather、AFC Delivery、Roster Availability、Player Snapshot Identityの上記linked文書。
- Source/code: `src/features/elo.py`、`src/modeling/player_workload_evaluation.py`、`src/modeling/model_architecture_evaluation.py`、H2H evaluatorのfit/serialization箇所、`load_matches`/TeamMaster APIs、2015–2024の10 processed CSVと`data/master/teams.csv`。
