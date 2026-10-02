# Frozen Model Architecture Benchmark Specification

- Specification status: **FROZEN_FOR_IMPLEMENTATION_PREFLIGHT**
- Frozen candidates: **A / P / G only**
- Model fit / prediction / evaluation performed by this document: **NO**
- Source feasibility: [MODEL_ARCHITECTURE_FEASIBILITY.md](MODEL_ARCHITECTURE_FEASIBILITY.md)

## 1. Global scope

| Contract | Frozen value |
|---|---|
| Retrospective source | Completed ordinary J1 only |
| Source seasons | 2015–2024 |
| Total source rows | 3,208 |
| Validation seasons | `(2020, 2021, 2022, 2023, 2024)` |
| Validation rows | `306 + 380 + 306 + 306 + 380 = 1,678` |
| Class order | `[0, 1, 2] = Away / Draw / Home` |
| Primary metric | Pooled multiclass Log Loss |
| Secondary metric | Pooled multiclass Brier |
| Descriptive metric | Accuracy |
| Retrospective forbidden inputs | 2025 outcomes、Hyakunen、opened 2026/27 outcomes、future cohort outcomes、cups、J2/J3、AFC |
| Candidate list | `A`, `P`, `G`。追加・subset・variantなし |

2020–2024はreused research populationであり、untouched holdoutではない。Benchmarkはarchitecture sanity / historical comparison専用で、prospective evidenceを代替しない。

## 2. Shared source validation

Evaluatorはfit前に以下をhard-failで確認する。

1. Seasons 2015–2024だけでexact 3,208 rows。
2. Season counts: 2015–2020各306、2021 380、2022–2023各306、2024 380。
3. Unique/nonblank `match_id`。
4. Nonmissing exact `home_team_id` / `away_team_id`、home != away。
5. Nonnegative integer `home_score` / `away_score`。
6. `result`が`0/1/2`でscoreとexact一致。
7. `match_date`がnonmissingで、stable orderは`match_date, match_id`。
8. Team IDsがTeamMasterに存在し、name joinやfuzzy fallbackを行っていない。
9. 全candidateが同じvalidation match IDs・row orderを使用。
10. Probabilityがfinite、各要素`[0,1]`、各row sumが`1`（absolute tolerance `1e-12`）。

## 3. Fold contract

| Validation | Training seasons | Train rows | Validation rows |
|---:|---|---:|---:|
| 2020 | 2015–2019 | 1,530 | 306 |
| 2021 | 2015–2020 | 1,836 | 380 |
| 2022 | 2015–2021 | 2,216 | 306 |
| 2023 | 2015–2022 | 2,522 | 306 |
| 2024 | 2015–2023 | 2,828 | 380 |

各foldでpreprocessor/estimatorをfresh fitし、validation seasonはtransform/predictだけに使う。Shuffle、random split、row drop、imputationは禁止。

## 4. Shared Elo and chronology

| Elo contract | Frozen value |
|---|---|
| Initial rating | `1500.0` |
| K-factor | `30.0` |
| Home advantage | `175.0`、expected-score update内のみ |
| Feature | `elo_diff = home pre-match Elo - away pre-match Elo` |
| Update ordering | 同一日の全target Eloを先にemitし、その日の全resultを後でapply |
| Season reset | なし |
| New/unseen team | `1500.0`から開始 |

Target自身とsame-date peerのresultはtarget pre-match stateへ入れない。Formも同じdate-batch ruleを使用する。

## 5. Candidate A — frozen reference

### Inputs and target

- Ordered input: `("elo_diff",)`
- Target: `result`
- Class order: `[0,1,2]`

### Preprocessing and estimator

```text
StandardScaler()
LogisticRegression(
    C=1.0,
    solver="lbfgs",
    max_iter=1000,
    random_state=0,
)
```

Scalerは各fold training rowsだけでfitする。Candidate Aは[MODEL_FREEZE_BEFORE_2026.md](MODEL_FREEZE_BEFORE_2026.md)から変更しない。

## 6. Candidate P — Independent Poisson

### 6.1 Training observations

各training matchを次の2 observationsへ展開する。

| Observation | `attacking_team_id` | `defending_team_id` | `is_home` | `attacker_elo_diff` | Target `goals` |
|---|---|---|---:|---:|---:|
| Home attack | `home_team_id` | `away_team_id` | `1` | `elo_diff` | `home_score` |
| Away attack | `away_team_id` | `home_team_id` | `0` | `-elo_diff` | `away_score` |

Observation orderはmatch order内でhome、awayの順。Targetはnonnegative integer。Home/Away score modelsを別々にfitせず、同じpipelineを1つだけfitする。

### 6.2 Exact preprocessing

```text
ColumnTransformer(
    transformers=(
        ("teams", OneHotEncoder(
            categories="auto",
            drop=None,
            sparse_output=True,
            dtype=float64,
            handle_unknown="ignore",
        ), ("attacking_team_id", "defending_team_id")),
        ("elo", StandardScaler(), ("attacker_elo_diff",)),
        ("home", "passthrough", ("is_home",)),
    ),
    remainder="drop",
    sparse_threshold=1.0,
)
```

Encoder/scaler categories/statisticsはfold training observationsだけから得る。Missing category、blank ID、nonfinite Eloはhard failure。Unknown categoryはall-zero team blockとなり、intercept・home role・Eloだけを使用する。

### 6.3 Exact estimator

```text
PoissonRegressor(
    alpha=1.0,
    fit_intercept=True,
    solver="lbfgs",
    max_iter=1000,
    tol=1e-4,
    warm_start=False,
    verbose=0,
)
```

Sample weight、time decay、Dixon–Coles correction、separate home/away model、dynamic updateは使用しない。Convergence warning/failureはformal run failureであり、parameter変更やretryを行わない。

### 6.4 Lambda generation

Validation matchごとにtrainingと同じ2-row transformationを作り、pipelineの出力を順に`lambda_home`, `lambda_away`とする。両方がfiniteかつstrictly positiveでなければhard failure。

### 6.5 Exact score-to-W/D/L conversion

1. `MAX_GOALS = 15`。Score axisはinteger `0..15` inclusive。
2. 各lambdaについて`p(0)=exp(-lambda)`、`p(k)=p(k-1)*lambda/k`でPoisson PMFを作る。
3. `M[h,a] = P(Home=h) × P(Away=a)`の16×16 outer-product matrixを作る。
4. Grid外（homeまたはawayが16以上）のtail massは捨てる。Grid内retained mass `M.sum()`がfiniteかつpositiveでなければhard failure。
5. Raw class massを以下で集約する。
   - Away: `a > h`（matrix upper triangle、diagonal除外）
   - Draw: `a == h`（diagonal）
   - Home: `h > a`（matrix lower triangle、diagonal除外）
6. `[away, draw, home] / retained_mass`でnormalizationする。
7. 出力がfinite、各値`[0,1]`、sum `1`をabsolute tolerance `1e-12`で確認する。

Tailを最終bucketへ移すvariant、Skellam shortcut、grid変更は試さない。

## 7. Candidate G — frozen LightGBM state classifier

Targetはordinary-J1 matchの`result`で、class orderは`[0,1,2]`。

### 7.1 Exact ordered state vector

```text
(
    "elo_diff",
    "home_last5_matches_available",
    "away_last5_matches_available",
    "home_last5_points",
    "away_last5_points",
    "home_last5_goals_for",
    "away_last5_goals_for",
    "home_last5_goals_against",
    "away_last5_goals_against",
)
```

`home_last5_matches_available = home_last5_wins + home_last5_draws + home_last5_losses`、awayも同様。W/D/L columns自体はmodelへ渡さない。

### 7.2 Form semantics

- 各teamのhome/awayを統合したprevious five completed ordinary-J1 matches。
- Cross-season continuationあり、season resetなし。
- Retrospective sourceの2015 left edgeにはpre-2015 historyを追加しない。
- `matches_available`はinteger `0..5`。
- Available 5未満は存在するmatchのraw sumだけを使用し、missing matchをzero-resultとして追加しない。
- 0 priorではavailability 0かつpoints/GF/GA 0。これはimputationではなくempty sumの既存builder semantics。
- Training historyに未出現のteamはElo 1500、form availability 0から開始する。Team IDはmodel inputではなくstate lookup keyとしてのみ使用する。
- Featureはdate batchごとに全targetをemit後、その日のresultsをhistoryへapply。

### 7.3 Missingness and preprocessing

全9 fieldsを必須とし、NaN、infinite、non-numeric、availability範囲外、negative form totalsはhard failure。Imputation、scaling、normalization、categorical feature、class weightは使用しない。

### 7.4 Exact estimator

```text
LGBMClassifier(
    boosting_type="gbdt",
    objective="multiclass",
    num_class=3,
    n_estimators=100,
    learning_rate=0.05,
    num_leaves=4,
    max_depth=2,
    min_child_samples=40,
    min_child_weight=0.001,
    min_split_gain=0.0,
    subsample=1.0,
    subsample_freq=0,
    colsample_bytree=1.0,
    reg_alpha=0.0,
    reg_lambda=1.0,
    class_weight=None,
    random_state=0,
    n_jobs=1,
    verbosity=-1,
    deterministic=True,
    force_col_wise=True,
)
```

Early stopping、validation callback、feature importance selection、threshold、calibrationは使用しない。`classes_`がexact `[0,1,2]`でなければhard failure。

## 8. Metrics

各foldおよびpooled matched 1,678 rowsについてcandidate別に以下だけを計算する。

1. Multiclass Log Loss、labels `[0,1,2]`
2. Multiclass Brier = `mean(sum((p - one_hot_y)^2, axis=1))`
3. Accuracy = class order `[0,1,2]`上のplain probability argmax

Primaryはpooled Log Loss、secondaryはpooled Brier。Accuracyはdescriptiveでdecisionには使わない。Calibration curve、class threshold、feature importance、subgroup selectionは計算しない。

## 9. Predeclared decision rule

Candidate P/Gごとに、Aに対して次の3条件をすべて満たす場合だけ`QUALIFIES_FOR_PROSPECTIVE_ARCHITECTURE_TRACK`とする。

1. Pooled Log Loss `<` A pooled Log Loss。
2. Fold Log LossがAより良いfoldが`>= 3/5`。
3. Pooled Brier `<=` A pooled Brier。

条件を満たさないcandidateは`CLOSE_ARCHITECTURE_CANDIDATE`。Fit/convergence/schema/identity/probability gate failure時はretryせず`INCONCLUSIVE_NO_TUNING`。

P/Gの両方がqualifyした場合はpooled Log Lossが小さい方だけをprospective challengerとしてretainする。Absolute LL differenceが`<=1e-12`ならpooled Brierが小さい方、Brierも`<=1e-12` tieならsimpler score-distribution candidate Pをretainする。Aは結果にかかわらずChampion/referenceのままで、このreused historical populationだけでは置換しない。

Formal benchmarkは明示one-shotで1回だけ実行する。結果確認後にdecision ruleを変更しない。

## 10. Prospective artifact contract

### 10.1 Training

| Candidate | Prospective training |
|---|---|
| A | Existing `operational_champion_20260922_v1`。refitなし |
| P | Contract freeze後、2015–2025 ordinary J1 3,588 rowsで1回だけfit |
| G | Contract freeze後、2015–2025 ordinary J1 3,588 rowsで1回だけfit |

P/G training cutoffは`2025-12-06`。2025はparameter/feature/model selectionには使わず、frozen prospective artifactのtraining rowsとしてだけ使用する。Hyakunen、opened 2026/27、future 300はestimator fitから除外する。

### 10.2 Prospective pre-match state

- Targetはfrozen future-300 cohort membershipとofficial nonblank `match_id`を必須とする。
- A/P/Gの`elo_diff`は既存operational Elo chronologyを共有する。
- G formはexisting verified history chain（2015–2025 ordinary J1 → 2026 Hyakunen → strictly-prior completed 2026/27 ordinary J1）を使用し、target dateより前のcompleted matchesだけを読む。
- 同一dateはone batch。Batch内targetは互いのresultをhistoryへ入れない。
- P/G artifactはcohort中にrefitしない。
- 2026/27 outcome、interim metric、prospective metricをspec変更に使わない。

### 10.3 Output

Path:

```text
data/processed/predictions/model_architecture_prospective.csv
```

Exact ordered schema:

```text
match_id
match_date
kickoff
home_team_id
away_team_id
prediction_generated_at
prospective_boundary
model_version
training_cutoff
history_cutoff_exclusive
artifact_hash
p_away
p_draw
p_home
predicted_class
```

`history_cutoff_exclusive`はtarget `match_date`と同じdate文字列で、`match_date < history_cutoff_exclusive`だけがhistoryに入る。Immutable keyは`(match_id, model_version)`。Existing keyはskip/reportし、overwriteしない。Class probabilityとargmaxは`[Away, Draw, Home]`順。

Frozen model versions:

```text
A = operational_champion_20260922_v1
P = architecture_independent_poisson_v1
G = architecture_lightgbm_form_v1
```

`artifact_hash`はcandidate artifact directoryのcanonical checksum manifest bytesのSHA-256とする。Artifactはmodel/preprocessor、metadata、training manifest、checksumsを含み、source hashes、library versions、feature order、class order、training cutoff、row countをmetadataへ記録する。

既存`xg_challenger_prospective.csv`はread-onlyで、overwrite/mergeしない。対象kickoff後に作成したrecordをprospectiveとしてbackfillしない。

## 11. No-tuning rule

Formal resultまたはprospective outcomeを見た後、次を行わない。

- Candidate追加、CatBoost/MLP/Dixon–Coles投入
- Pのalpha/grid/tail/team encoding変更
- Separate home/away Poisson、time decay、dynamic strength追加
- Gのfeature subset、depth、leaves、estimators、learning rate、regularization変更
- Class weight、sample weight、imputation、calibration、draw threshold変更
- Elo initial/K/home advantage変更
- Validation fold、metric、decision gate変更
- 2025/opened 2026/27を使ったselection

Implementation bugの修正は、formal run前のpreflightでのみ許可する。Formal run後にsemantic outputが変わる修正が必要になった場合は結果を無効化し、自動rerunせず別途governance decisionを要求する。

## 12. Generation 2 separation

Rolling xG、J Stats FULL_37、suspension snapshots、その他PIT-safe future informationはGeneration 2 information-rich modelの別cycleとする。A/P/G Phase 0へ追加しない。これにより将来の`architecture gain`と`information gain`を分離する。

## 13. Freeze conclusion

```text
FROZEN_A_P_G_ARCHITECTURE_BENCHMARK_CONTRACT
```

次taskは、このdocumentを変更せずにevaluator/artifact/prediction implementationとpreflight testsを作る段階である。Fit、formal benchmark、prospective predictionはそれぞれ明示許可されるまで実行しない。
