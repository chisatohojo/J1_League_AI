# Model Architecture Phase 0 Feasibility

- Status: **FEASIBLE_TO_FREEZE_A_P_G_BENCHMARK**
- Audited: **2026-10-02 (JST)**
- Scope: repository内のread-only source/implementation audit
- Model fit / prediction / metric calculation: **NOT RUN**

## 1. 目的と境界

このPhase 0は、Elo Logisticへfeature familyを追加してきた過去のretrospective cycleとは分離し、architectureそのものを比較する次cycleのcontractを結果確認前に固定する。候補は次の3つだけである。

| Candidate | Architecture | Feasibility verdict |
|---|---|---|
| A | Frozen Model A: Elo-only multinomial Logistic | **PROCEED** |
| P | Independent Poisson score model | **PROCEED** |
| G | LightGBM multiclass classifier with one fixed basic state vector | **PROCEED** |

2025 ordinary J1は`SPENT TEST`、opened 2026/27はselection/tuning禁止である。2026-09-22時点のfuture 300はprospective cohortであり、途中結果を仕様変更に使わない。本taskではfit、prediction、evaluation、data collectionを行っていない。

過去の[MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md)にはIndependent Poisson、CatBoost、Recent Form等のexploratory experimentがclosedとして記録されている。本cycleはその結果を再採点・tuningするものではない。新たに事前固定するA/P/G contractを一度だけarchitecture sanity benchmarkへ進める別cycleであり、old scriptや未記録performanceをcandidate selectionには使用しない。

## 2. Existing assets

| Asset | Repository evidence | Audit result |
|---|---|---|
| Ordinary J1 completed matches | `data/processed/jleague/{2015..2025}_matches_probe.csv` | 2015–2024は3,208 rows、2015–2025は3,588 rows。`match_id`重複なし、score/result欠損なし |
| Score targets | `home_score`, `away_score`, `result` | 非負integer scoreと`0/1/2` resultの整合validationが[src/collect/matches.py](../src/collect/matches.py)に存在 |
| Stable team identity | `data/master/teams.csv` | 49 stable Team IDs / 103 aliases。source/date-aware exact resolution、fuzzy fallbackなし |
| Elo | [src/features/elo.py](../src/features/elo.py)およびModel A replay | Initial 1500、formal contractはK=30 / home advantage=175、pre-match `elo_diff`を再現可能 |
| General form | [src/features/form.py](../src/features/form.py) | last five completed matchesのpoints/W/D/L/GF/GA。target追加前にfeatureをemitし、5未満はavailable分だけ使用 |
| Cross-period form loader | [src/features/form_history.py](../src/features/form_history.py) | historical → Hyakunen → ongoingをverified chronologyで連結可能 |
| Model A artifact | [MODEL_A_ARTIFACT.md](MODEL_A_ARTIFACT.md) | Frozen scaler/model/checksum/class orderあり。新規fit不要 |
| Prospective discipline | [XG_CHALLENGER_PREDICTION_RUNBOOK.md](XG_CHALLENGER_PREDICTION_RUNBOOK.md) | one-date batch、official ID必須、append-only `(match_id, model_version)`、outcome非参照 |
| Dependencies | `requirements.txt`, `requirements-lock.txt` | scikit-learn `1.9.1`、LightGBM `4.7.0`、CatBoost `1.2.8`、NumPy/Pandas/SciPyあり。追加dependency不要 |

Local prospective prediction artifactはheaderとrow countだけを確認し、2 recordsがappend済みであることを確認した。Probability値およびoutcomeは閲覧・評価していない。

## 3. Candidate A feasibility — PROCEED

Model Aは変更せずreferenceとして再利用できる。

- `elo_diff = pre-match home Elo - pre-match away Elo`
- Initial Elo `1500`
- K `30`
- Home advantage `175`はexpected-score update内のみ
- `StandardScaler`
- `LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000, random_state=0)`
- Class order `[0,1,2] = Away / Draw / Home`
- Historical architecture benchmarkでは各foldのtraining rowsだけでscaler/modelをfit
- Prospective operationでは既存`operational_champion_20260922_v1` artifactをchecksum validation後に再利用し、refitしない

Source: [MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md)、[MODEL_A_ARTIFACT.md](MODEL_A_ARTIFACT.md)。

## 4. Candidate P feasibility — PROCEED

### Data and target

`home_score`と`away_score`は全3,208 retrospective rowsで利用でき、score/result consistencyも既存loaderで検証可能である。各matchをhome攻撃・away攻撃の2 goal observationsへ変換し、同一Poisson regressorから`lambda_home`と`lambda_away`を得られる。

### Fixed input concept

長形式1 observationの入力は以下だけで十分である。

1. `attacking_team_id`
2. `defending_team_id`
3. `is_home`
4. `attacker_elo_diff`（home observationは`elo_diff`、away observationは`-elo_diff`）

Team identityはTeamMasterのexact IDを使用する。One-hotでtraining未出現のpromoted/new teamは`handle_unknown="ignore"`とし、未知team coefficientを捏造せず、intercept・home role・pre-match Eloだけでlambdaを生成する。Elo側のunseen teamは既存規則どおり1500から開始する。

### Implementation

既存scikit-learnの`OneHotEncoder`、`StandardScaler`、`ColumnTransformer`、`PoissonRegressor`で実装可能で、新dependencyは不要。Independent Poissonを1候補だけ採用し、Dixon–Coles、time decay、dynamic update、別alphaは同時に候補化しない。

### Score conversion

Repositoryには`MAX_GOALS=15`の既存実装資産がある。0–15のhome/away exact-score gridを作り、grid外tailを捨てた後、retained massでAway/Draw/Homeを1へ正規化する決定的規則を固定できる。詳細は[MODEL_ARCHITECTURE_BENCHMARK_SPEC.md](MODEL_ARCHITECTURE_BENCHMARK_SPEC.md)に定義する。

## 5. Candidate G feasibility — PROCEED

LightGBM `4.7.0`がdirect dependencyとしてlock済みで、追加packageは不要。CatBoostとのparallel comparisonは行わない。

### Redundancy audit

`form.py`の1 sideあたり6 fieldsには次のdeterministic relationshipがある。

- `points = 3 × wins + draws`
- `matches_available = wins + draws + losses`

W/D/L、points、availabilityを同時投入すると冗長になる。Goals totalはW/D/Lからは決まらない。5試合未満のraw totalsはsample sizeが異なるため、availabilityを明示しないと0 priorと低いformを区別しにくい。

### One fixed state vector

このためCandidate Gは次の9 columnsだけに固定可能である。

```text
elo_diff
home_last5_matches_available
away_last5_matches_available
home_last5_points
away_last5_points
home_last5_goals_for
away_last5_goals_for
home_last5_goals_against
away_last5_goals_against
```

`*_last5_matches_available`は既存`wins + draws + losses`からdeterministically導出する。W/D/L自体、H2H、discipline、first-score、goal-timing、substitution、draw-propensity、xG等は投入しない。これはclosed feature laneの再探索ではなく、一般的なrecent team stateを1 vectorに固定するものとする。

### Sparse and early-history semantics

- Historyは各team共通home/away streamで、last five completed matches。
- Retrospective benchmarkはordinary J1のみをcross-season continuationする。
- 2015 left edgeおよびnew teamはavailable count `0..4`を保持し、存在しないmatchをzero-resultとして埋めない。
- Raw totalsはimputeしない。0 priorの場合だけ既存builder出力どおり全total 0、availability 0。
- Prospective operationでは既存verified history chainを用い、target dateより前だけを読む。

## 6. Chronology / PIT risks

| Risk | Frozen control |
|---|---|
| Target result leakage | target score/resultをfeature/history/model fitへ入れない |
| Same-date peer leakage | 同一日の全target featureを先にemitし、その後にその日のcompleted resultsをstateへapply |
| Fold leakage | validation seasonより前のseasonだけでpreprocessor/estimatorをfit |
| Current page leakage | historical ordinary-J1 processed results以外をretrospective inputにしない |
| 2025 reuse | retrospective selection/evaluationから除外。prospective artifact fitではcontract freeze後のtraining rowsとしてのみ使用 |
| Opened 2026/27 | model/feature/parameter selectionには使わない。prospective prediction時のstrictly-prior historyに限定 |
| Prospective adaptation | cohort途中のoutcome・metricを見てspec/refit ruleを変更しない |

Prospective estimatorは**boundary-fixed**を選ぶ。P/Gのprospective artifactは2015–2025 ordinary J1だけで一度fitし、future 300の途中ではrefitしない。これは既存Model A/XG artifactのfreeze・checksum・no-refit disciplineと一致し、cohort途中のoutcomeがmodel stateへ入る余地をなくす。

## 7. Identity risks

- Poisson team effectsはexact TeamMaster IDsだけを使用し、alias textやfuzzy joinを使用しない。
- Fold trainingに未出現のteamはunknown one-hotとして処理し、他team coefficientを流用しない。
- Candidate Gはteam IDをmodel inputにしないが、form history stateのkeyにはstable TeamMaster IDを必須とする。
- Prospective targetはofficial nonblank `match_id`を必須とし、`fixture_key`やsynthetic IDで代替しない。

現行TeamMasterとordinary-J1 rowsについてidentity blockerはない。将来official fixture IDが未取得ならpredictionだけを停止する。

## 8. Training population options and decision

複数optionは残さず、次を採用する。

| Use | Population |
|---|---|
| Historical benchmark | Expanding folds: train 2015..Y-1、validate Y、Y=2020..2024 |
| Pooled historical validation | 2020–2024、1,678 rows |
| Prospective P/G artifact fit | 2015–2025 ordinary J1、3,588 rows、training cutoff `2025-12-06` |
| Excluded from estimator fit | Hyakunen、opened 2026/27、future 300、cups、J2/J3/AFC |

2020–2024は何度も研究に使われたpopulationでuntouched holdoutではない。Architecture sanity/historical comparisonに限定し、final prospective evidenceの代替にしない。

## 9. Prospective compatibility

技術的にはA/P/Gを同じfuture-300 cohortへappend-onlyで記録できる。ただし有効なprospective recordには、対象kickoff前に以下が完了している必要がある。

1. このspecのfreeze
2. code/tests implementation
3. P/G artifactの一度だけのfitとhash freeze
4. official `match_id`取得
5. prediction generation/write

既にRolling-xGの最初の2 recordsが別artifactへappend済みである。Architecture outputは別path・別`model_version`を使い、既存recordsをoverwriteしない。期限に間に合わないmatchを後からbackfillしてprospective扱いしない。

## 10. Dependency status

| Dependency | Version | Candidate use |
|---|---:|---|
| scikit-learn | `1.9.1` | A、P preprocessing/Poisson |
| LightGBM | `4.7.0` | G |
| NumPy | `2.5.3` | probability grid / validation |
| Pandas | `3.0.5` | exact schema/history assembly |
| CatBoost | `1.2.8` | Installedだが本cycleでは**使用禁止** |

## 11. Open questions / operational blockers

性能に関するopen questionは、このPhase 0では回答しない。Source feasibilityを妨げるblockerはない。

| Item | Status |
|---|---|
| 2026-10-09 batchへ間に合うか | **OPERATIONAL DEADLINE**。kickoff後のbackfillは禁止 |
| P/G implementation correctness | 次taskのcode/tests preflightで検証。現時点ではartifactなし |
| Formal benchmark | 未実行。one-shot command/evaluatorは別taskでfreeze後に実装 |
| Prospective performance | cohort完了まで未開封。途中評価禁止 |
| Generation 2 information | Rolling xG、FULL_37、suspension等は別cycle。Phase 0へ混ぜない |

## 12. Feasibility conclusion

- Candidate A: **PROCEED**
- Candidate P: **PROCEED**
- Candidate G: **PROCEED**
- Next gate: **READY_FOR_MODEL_ARCHITECTURE_IMPLEMENTATION_PREFLIGHT**

このverdictはimplementation/performance approvalではない。次の正式gateはspecどおりのimplementation、read-only preflight、明示one-shot benchmarkである。
