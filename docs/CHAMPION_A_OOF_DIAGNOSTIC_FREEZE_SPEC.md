# Champion A OOF Diagnostic Freeze Specification

Freeze date: **2026-10-05 (JST)**。

Reviewed source HEAD: **`376973e1f2238bbd29799386ec100dd400648ce4`** (`docs: audit Champion A residual information gaps`)。

Final freeze gate: **`FROZEN_FOR_ONE_CHAMPION_A_OOF_DIAGNOSTIC_IMPLEMENTATION`**。

これはdocs-only freezeである。**次の実装とsynthetic testsだけ**を対象とし、real-data fit / row-level OOF生成 / diagnostic calculationはまだ承認しない。実装reviewと、その後の一度だけの実データ再構成は別taskに分離する。

## 1. Scope

Authoritative audit: [CHAMPION_A_RESIDUAL_INFORMATION_GAP_AUDIT.md](CHAMPION_A_RESIDUAL_INFORMATION_GAP_AUDIT.md)。既存gate `NO_LANE_OPENED_NEED_TARGETED_DIAGNOSTIC`を解決するため、frozen Aの既存2020–2024 OOFを後日再構成するcontractを固定する。Champion/challenger選択やcalibratorの評価ではない。

- Sourceはordinary J1 2015–2024の3,208 completed matchesとexact TeamMasterだけ。
- Validationは2020–2024の1,678 matches。Unavailable除外、imputation、追加featureなし。
- 2025、Hyakunen、ongoing/opened 2026/27、Cup、J2/J3、AFC、external dataをロードしない。
- このtaskの実行はdocs/code/resultのread、限定path検索、byte-level SHA照合、static document validation、commitだけ。CSV parsing、Elo replay、fit、`predict_proba`、diagnostic集計は実行していない。
- Artifact/source/test/model codeは変更しない。Full pytest、formal/preflight再実行、closed-lane再開、HTTP、collection、production prediction、ongoing-v2 activation、pushは禁止。

## 2. Evidence status

**Existing exact row-level A OOF found: NO（限定検索の範囲）**。不存在をrepository全体に一般化しない。

| Checked location / evidence | Findings / disposition |
|---|---|
| `data/processed/modeling/` | Opened interim predictionsだけ。内容は読まない。Historical A OOFではない |
| `data/processed/model_architecture/` | `formal_benchmark_attempt.json`だけ。Pathの存在のみ確認し、内容を読み書きしない |
| `data/processed/predictions/` | Prospective prediction/binding filesだけ。内容を読まない |
| `models/`（ignored filesも含むfile-name検索） | Operational A/xG/P/G bundlesのみ。A fold arrays/bundlesなし。Joblibやtraining manifestはロードしない |
| [Asset inventory](DATA_ASSET_INVENTORY.md)、[architecture runbook](MODEL_ARCHITECTURE_EVALUATION_RUNBOOK.md)、audit | Exact saved A row probabilitiesの記載なし |
| `src/modeling/model_architecture_evaluation.py` | `_fold_output()` / `_evaluate_a()`はIDs/labels/probabilitiesをmemory内に作る。Result writerはaggregate metricsだけを保存する |
| `src/modeling/h2h_evaluation.py` / [H2H result](H2H_EVALUATION.md) | Baseline S0はfresh A-only fit。結果文書には高精度metricsがあるがrow probabilitiesはない |

検索は上記high-signal locations、関連docs/codeだけ。Raw archive、大きなraw directory、全processed sourceの探索はしない。Operational Aは2015–2025 trainingを含み、historical fold代用にはならない。集計値からrow probabilitiesを逆算しない。

よって後続でdedicated A-only reconstructionが必要。将来exact saved OOFが別に発見された場合、生成を自動skip/reuseせず、path/schema/rows/hash/provenance/reference一致を別reviewで確認する。本specの経路を結果に合わせて差し替えない。

## 3. Champion A exact contract

Sources: [Model freeze](MODEL_FREEZE_BEFORE_2026.md)、[architecture spec §§2–5](MODEL_ARCHITECTURE_BENCHMARK_SPEC.md)、reviewed HEADの`elo.py`、`player_workload_evaluation.py::_add_elo()`、architecture evaluatorのA関数。

### Elo replay

1. §4の10 CSVをyear ascendingで、既存`load_matches(path)`と`load_team_master(exact_path).add_team_ids()`により読む。Exact source aliasとinclusive validity datesを使用。Fuzzy join、name normalizationの追加、team ID推定は禁止。
2. Full sourceをstable `match_date, match_id` ascendingでsortし、indexをresetする。Match IDsはstringで保持。Score/result、unique ID、date、TeamMaster ID、home != awayを既存contractと同じくvalidateする。
3. Full 2015–2024 stream上でEloを**一度だけ**replay。Team rosterはsourceのhome/away stable IDsのsorted union。全teamを1500.0で初期化。
4. `EloRatings(ids, k_factor=30.0, home_advantage=175.0)`を明示使用。Module default K=20 / HA=0に依存しない。
5. Calendar-date batch内の全targetを先にreadし、`elo_diff = home_rating - away_rating`をemit。その後、その日のresultをcanonical orderでapply。同じteamのsame-date二重出現はhard failure。
6. Update expectationは既存`expected_score(home_rating + 175, away_rating)`の分岐実装（scale 400）。`delta = 30 * (result / 2 - home_expected)`、homeに+delta、awayに−delta。式を別のnumerical implementationへ整理し直さない。
7. HAはupdate expectation内部だけ。Featureへ175を足さない。No season reset。J1不在期間のratingは保持。新出現teamは未更新1500から開始。
8. Validation年内もprior datesのcompleted resultsは後続target stateへapplyする。Fold境界でEloをresetしない。未来のteam ID rosterはlookupだけで、未来result/strengthをprematch stateに使わない。

Target自身、same-date peer、later resultを当該targetへ入れない。Sourceの延期・中断/再開dateを独自修正しない。Kickoff順へ置き換えない。

### Fold pipeline

Exactly fresh pipeline per fold:

```python
Pipeline([
    ("scaler", StandardScaler()),
    ("logistic", LogisticRegression(
        C=1.0, solver="lbfgs", max_iter=1000, random_state=0,
    )),
])
```

Ordered Xは`["elo_diff"]`だけ、yは`result`。Scaler/logisticともtraining rowsだけでfit。Validationはtransform/predictだけ。No inner CV、shuffle、sample/class weights、warm start、parameter変更、calibration、additional scaler。

Classesはexact `(0, 1, 2) = Away / Draw / Home`。`classes_`がこの順序でない場合STOPし、黙って並べ替えて通さない。Float64を使用。

Constructorに指定していない値はreviewed dependency lockのdefaultsのまま。StandardScalerはcopy/with_mean/with_std=True。Logisticはtol=1e-4、fit_intercept=True、class_weight=None、warm_start=False（実効L2、現行1.9.1のdefault l1_ratio=0.0）。追加parameterを設定して「同等」実装にしない。ConvergenceWarningまたはfit failureはSTOP、retry/tolerance変更なし。

RuntimeはrepositoryのWindows Python 3.12.14とreviewed lock（numpy 2.5.3、pandas 3.0.5、scikit-learn 1.9.1、scipy 1.18.1）に従う。別環境へ移す場合はreviewが必要。Manifestへ実際のversionsを記録し、metric mismatchをenvironment理由で許容しない。

## 4. Frozen inputs

下記は既存auditのSHAを転記し、今回bytesからstaticに再照合したもの。全11件一致。Missing/hash mismatchはfit前STOP。Pathはrepository root relativeで、globや自動season discoveryを使わない。

| Path | Expected rows | SHA-256 |
|---|---:|---|
| `data/processed/jleague/2015_matches_probe.csv` | 306 | `ea0ab9e1788373702d9ce425f83c74bae21a7afd35752d9c24481f4bc9400353` |
| `data/processed/jleague/2016_matches_probe.csv` | 306 | `4a3bcd4f0beaa20192abc60071e5153c846c1ca132b1876d174a2e46a5dde45f` |
| `data/processed/jleague/2017_matches_probe.csv` | 306 | `d2f8ae9959762d172c4afb209e1916afd2dfadbcb0955a99b281aab2fb07f59b` |
| `data/processed/jleague/2018_matches_probe.csv` | 306 | `f6d90f5dec3461fca230ca487233c63273fb69156970af3940d32b1455672681` |
| `data/processed/jleague/2019_matches_probe.csv` | 306 | `3b2090ec38e064457ec4ae0f9981ae457350af268f75886150b6f05d95d6fe2f` |
| `data/processed/jleague/2020_matches_probe.csv` | 306 | `fd295aca0097ee0041659cdbe42ec9375227969e9b0c51efa8993753cccbfe17` |
| `data/processed/jleague/2021_matches_probe.csv` | 380 | `298c3d4c4eb66fa6d6d00748e19382e5f304899355297acdbf42f251e11114b6` |
| `data/processed/jleague/2022_matches_probe.csv` | 306 | `d4861930524d5e171b3c93f18361af7b17c6055ae27d9055a6e9a9ab266ba2c2` |
| `data/processed/jleague/2023_matches_probe.csv` | 306 | `6a1e002dd7e9d0187d014e517057ad3d79430eece66fcb6b5239e9db590085c9` |
| `data/processed/jleague/2024_matches_probe.csv` | 380 | `4b2fa48f762e04316c7ded093d3919642d62d3c2b5edc92a55e012cf6ce410d1` |
| `data/master/teams.csv` | TeamMaster | `ec255eb65e9fa2c310e3fbcfeecf7a7d201ca4f458a15bb0d129fa0ca9e1b89f` |

Reviewed implementation/dependency provenanceも固定する。後続でこれらに変更があればsilentに取り込まずSTOP/review。Dedicated new generatorとそのtestsは別ファイルに実装する。

| Reviewed file | SHA-256 |
|---|---|
| `src/features/elo.py` | `f5ae27723e603c81ab5757654522a1bc207f93d21c32c74c43ccf6022b0923c4` |
| `src/modeling/player_workload_evaluation.py` | `7517880be643e7891eb7d0eb426d1dd57744ef5f7b730ce7713457e953457d76` |
| `src/modeling/model_architecture_evaluation.py` | `b610cb52e3fc136bb6ab1fa303102d2413b4357ea5cc7bd899d24aad9d3105c5` |
| `src/collect/matches.py` | `0b2f2916131a54e413fb7347a16960f1c59880c24741584a4bd491a43821842c` |
| `src/collect/teams.py` | `b0b77a3b2a583a047a8d3399076e083ad5d5f2699aa8c6cd0c6fe82515128e6c` |
| `requirements.txt` | `887f566527f6a10da4e1ac6fcfc66810634c5e82f0ddc2b232084c9880753eda` |
| `requirements-lock.txt` | `3aea21392b63f9fc3dfbcf00e44cb825a3eb7453d130492dde8bcb5da14ddc04` |

## 5. Frozen folds

| Validation year | Training seasons | Train n | Validation n |
|---:|---|---:|---:|
| 2020 | 2015–2019 | 1530 | 306 |
| 2021 | 2015–2020 | 1836 | 380 |
| 2022 | 2015–2021 | 2216 | 306 |
| 2023 | 2015–2022 | 2522 | 306 |
| 2024 | 2015–2023 | 2828 | 380 |

Trainingはsource `season < validation_year`、validationは`season == validation_year`。両方canonical streamのrelative row orderを保持。全5foldにfresh Aを各1回fitし、各validation rowを1回predict。Pooledはyear 2020→2024順にfold validation arraysをconcatenate、n=1678、unique IDs。

Expected target IDs/order/metadataはhash固定sourceを同じload/sort/filterで得た列とelementwise exact比較する。Metric一致だけでidentity一致を代替しない。Pooled canonical orderは`validation_year, match_date, match_id`。独立した未知のhistorical probability hashがあるとは主張しない。

## 6. Reconstruction vs formal evaluation

| Formal architecture benchmark | A-only diagnostic reconstruction |
|---|---|
| 既に完了したA/P/G comparison | 既にfreezeされたA probabilitiesの行別再現だけ |
| 正式one-shot attempt/resultを持つ | Challenger attemptを消費しない |
| Closed P/Gの採否 | Calibration/transitionのhypothesis evidence |
| 再実行禁止 | 実装review後、別taskの明示承認で一度だけ |

後続reconstructionも**fittingである**。本freeze gateだけでは実データfitを開始できない。

`data/processed/model_architecture/formal_benchmark_attempt.json`とのinteractionは**NONE**。Dedicated generatorはこのmarkerをopen/read/write/delete/recreate/reuseしない。Architecture evaluatorのCLI、`preflight()`、`formal()`、`_preflight_context()`、P/G runnerを呼ばない。既存formal resultやother one-shot markersにも触れない。

## 7. Row-level schema

Schema version: **`champion_a_oof_diagnostic_v1`**。Exactly次の**34 columns / order**。モデルinputと診断metadataを明確に分離し、result/prediction由来列をfeature候補として再利用しない。

```text
validation_year
match_id
match_date
home_team_id
away_team_id
result
elo_diff
p_away
p_draw
p_home
predicted_class
max_p
p_true
nll
brier
abs_elo_diff
round
home_team
away_team
season_phase
home_season_appearance
away_season_appearance
home_first5
away_first5
any_team_first5
both_team_first5
home_status
away_status
promoted_involved
returning_involved
established_only
home_favorite
away_favorite
near_even
```

- Integer fields: validation_year/result/predicted_class/round/appearance ordinals。FlagsはCSV integer `0/1`。IDs/source team names/status/phase/dateはstring。
- `match_date`はsource calendar date `YYYY-MM-DD`。`home_team`/`away_team`はsource nameそのまま。追加`home_club`/`away_club`は重複なので作らない。
- Float fieldsはbinary64。`p_true = probabilities[row, result]`、`predicted_class = CLASS_ORDER[np.argmax(p)]`（exact tieは最初のindex、0→1→2）、`max_p = max(p)`、`abs_elo_diff = abs(elo_diff)`。
- `brier = sum((p - one_hot(result))**2)`、range `[0,2]`。3で割らない。
- NLLは既存sklearn `log_loss`の数値semanticsに合わせて `-log(clip(p_true, eps, 1-eps))`、`eps = np.finfo(np.float64).eps`。Raw p/p_true自体をclip/renormalizeしない。これはloss評価のnumerical clippingで、smoothing/calibrationではない。通常のinterior probabilityでは`-log(p_true)`そのもの。Mean row NLLとreference LLの一致を§9で確認する。
- No missing/nonfinite values。Probabilityは`[0,1]`、row sum `rtol=0, atol=1e-12`。補正してgateを通すことは禁止。
- Ordinals/flags/status/phaseの定義は§10。Favorite flagsは予測由来の**diagnostic-only labels**。

## 8. Artifact/manifest contract

固定output paths（現taskで作成しない）:

```text
data/processed/model_diagnostics/champion_a_oof_2020_2024.csv
data/processed/model_diagnostics/champion_a_oof_2020_2024_manifest.json
```

Production prediction directoryから分離する。CSVはUTF-8 without BOM、comma、LF、indexなし、headerあり、exact §7 order、no missing values。Floatは`%.17g`のround-trip precision、read時はround-trip float parsingとIDs string保持。Serialized memory bufferを再parseし、float値・row IDs/order・derived values・metricsを再確認してからwrite。CSV header/bytes/hashを後から変更しない。

Manifest versionも`champion_a_oof_diagnostic_v1`。Exactly以下のtop-level keysを要求する:

```text
schema_version
purpose
reviewed_source_commit
freeze_spec
generation_authorization
generator
runtime
inputs
team_master
champion_a_contract
folds
class_order
columns
column_dtypes
row_count
csv
references
observed_metrics
diagnostic_contract
gates
generated_at
```

| Key | Required content |
|---|---|
| `purpose` | Literal `diagnostic_only_not_formal_evaluation_not_model_input` |
| `reviewed_source_commit` | 本書冒頭のreviewed HEAD |
| `freeze_spec` | 本書path、committed spec SHA-256、freeze commit SHA（commit後にmanifestへ記録。本文に自身のcommit/hashを埋め込まない） |
| `generation_authorization` | 後続reviewed implementation commit SHAと、実データone-time generationの別承認task/reference。Self-authorization不可 |
| `generator` | 固定module path、実行時commit、generator file SHA-256、git dirty=false、fits=5、prediction batches=5、automatic retries=0 |
| `runtime` | Python/platform/numpy/pandas/sklearn/scipy versions、requirements/lock hashes |
| `inputs` | §4順の10 entries `{path, season, rows, sha256}`。TeamMasterは下記に分離 |
| `team_master` | Exact path/SHA |
| `champion_a_contract` | Elo initial/K/HA/feature/reset/batching、pipeline constructor/default semantics、metrics formulas/numerical tolerances |
| `folds` | Year順の5 entries：training seasons/count、validation count、ordered train/validation ID list hashes |
| `class_order`, `columns`, `column_dtypes`, `row_count` | `[0,1,2]`、§7、exact dtype map、1678 |
| `csv` | 固定path、SHA-256、UTF-8/LF/`%.17g` encoding、pooled ordered-ID list hash |
| `references` | §9のexact reference numbers、source document paths、rtol/atol |
| `observed_metrics` | 各foldとpooledのn/Accuracy/LL/Brier（actual full precision） |
| `diagnostic_contract` | §10–16の固定bins、flags、group comparisons、sparse rule、decision hierarchy。Spec SHAに加えて値をJSON化 |
| `gates` | input/source/chronology/folds/identity/classes/probabilities/references/serializationを全て`PASS` |
| `generated_at` | UTC ISO 8601 with `Z`。Diagnostic対象日とは別のprovenance |

ID list hashはordered string listを`json.dumps(ids, ensure_ascii=False, separators=(",", ":"))`でUTF-8 encodeしてSHA-256。Source probabilitiesの未知の既存hashと混同しない。

全gatesとmemory serialization check後にだけCSV/manifestをexclusive create（`xb`、overwriteなし）。Pairの一方でも存在する場合、fit前にrefuse。Partial pairをacceptedとしない、rollback削除/再生成もしない。Interrupted creation/failure/retryには新reviewed taskが必要。入力SHAはload前とpublish前に再確認。Accepted pairはimmutableであり、将来read-only consumerもmanifest SHA/CSV schema/referenceをvalidateする。

## 9. Reference metric gate

Sourceは[H2H S0 full-population baseline](H2H_EVALUATION.md)のunrounded primary fold/pooled values。S0はsame frozen Aをfull ordinary-J1 trainingにfitしたもの。[Architecture result](MODEL_ARCHITECTURE_BENCHMARK_RESULT.md)の15-decimal出力と、reviewed architecture codeのreference constantsに一致する。Filtered DP0/W0等を使わない。

| Validation year | n | Accuracy | Log Loss | Brier |
|---:|---:|---:|---:|---:|
| 2020 | 306 | 0.5065359477124183 | 1.023119734659012 | 0.6117572218710644 |
| 2021 | 380 | 0.5078947368421053 | 1.0253437210487792 | 0.6149829138674616 |
| 2022 | 306 | 0.4019607843137255 | 1.0940186385371449 | 0.6610224339161608 |
| 2023 | 306 | 0.46078431372549017 | 1.0604285568595655 | 0.638530529273072 |
| 2024 | 380 | 0.45 | 1.079241181120235 | 0.6531695943664019 |
| Pooled | 1678 | 0.466626936829559 | 1.056065401323764 | 0.6357323419292724 |

Metricsは既存architecture `calculate_metrics()`と同じ定義：Accuracy=`mean(argmax(p)==result)`、LL=`sklearn.metrics.log_loss(result, p, labels=[0,1,2])`（normalize=True、no sample weights）、Brier=`mean(sum((p-one_hot)**2, axis=1))`。Pooledはfold meansの単純平均でなく全1,678 rowsに対する計算。

数値toleranceは**`rtol=0, atol=1e-12`**。Row/season/fold count、ID/order/metadata、schema、class orderはexact equality。各foldの全3metricsとpooled全3metricsをgate。Row nll/brier/max-p/p_true等もformula一致を同じabsolute toleranceで確認する。Probability sumも同じtolerance。

**Any mismatch => STOP before residual diagnostics and publication**。Near-matchを採用しない。Tolerances、source、order、scaler、solverを調整して通すことは禁止。Fitやpredict後のfailureでも自動retryしない。Aggregate gateはhistoric row probabilitiesの数学的一意性を証明するものではないため、source/code/runtime/identity provenanceを併せて保持する。

## 10. Fixed diagnostic buckets

全viewsは各validation yearとpooled contextに同じruleを適用。空cellを残し、cutoff/bin/flagを後から変更しない。Probability/abs-Elo/max-pは[既存error analysis](ELO_OOF_ERROR_ANALYSIS.md)、signed-Elo/phase/appearanceはauthoritative auditのviewsを固定する。

| Axis | Exact rule |
|---|---|
| Year | 2020, 2021, 2022, 2023, 2024。Pooledは別context |
| True/predicted class | 0 Away、1 Draw、2 Home。Predictedは§7 argmax |
| One-vs-rest p bins | `[0.0,0.1)`, `[0.1,0.2)`, `[0.2,0.3)`, `[0.3,0.4)`, `[0.4,0.5)`, `[0.5,0.6)`, `[0.6,0.7)`, `[0.7,0.8)`, `[0.8,0.9)`, `[0.9,1.0]`。同じliteral edgesを全classに使用 |
| Max-p bins | `[0,0.4)`, `[0.4,0.5)`, `[0.5,0.6)`, `[0.6,0.7)`, `[0.7,1.0]` |
| abs Elo bins | `[0,50)`, `[50,100)`, `[100,200)`, `[200,300)`, `[300,+infinity)` |
| Signed home−away Elo bins | `(-infinity,-200)`, `[-200,-50)`, `[-50,50)`, `[50,200)`, `[200,+infinity)`。±200境界を含む向きも固定 |
| Phase | `opening` round 1–5、`middle` round 6–29、`closing` round 30+。Roundをchronologyに置換しない |
| Team appearance | 各season/teamについてcanonical date/ID順のhome+awayを数え、target自身のordinalを1-basedで付与。2015から全streamで算出してからvalidation抽出。No score use |
| First-five flags | `home_first5 = home_season_appearance <= 5`、away同様。`any_team_first5 = OR`、`both_team_first5 = AND`。Mixed caseはany=1/both=0。Neitherはany=0。Home/awayそれぞれ1–5と6+も報告 |
| Club status | 下記membership定義でhome/away別に固定 |
| Favorites | §13 independent flags。Raw Elo signとは異なる |

Membershipを`M_y = year yに現れるhome/away TeamMaster IDsのset`とする（result/standingsは使用しない）。`E_y = M_y - M_(y-1)`。

- `home_status` / `away_status`: `ESTABLISHED`は`M_(y-1)`に存在。Entrantかつ`union(M_2015,...,M_(y-1))`に既出なら`RETURNING`、それ以外は`FIRST_TIME_IN_SCOPE`。
- `promoted_involved`は少なくとも一方が`E_y`。これはauditと同じmembership-derived entrantで、official J2 promotion経路を推定しない。
- `returning_involved`は少なくとも一方が`RETURNING`。
- `established_only`は両方`ESTABLISHED`（not promoted-involvedと同義）。Returningはpromotedのsubset。両teamのstatusが異なるmatchを無理に一つのclub-statusへ押し込まない。
- Pre-2015 appearanceを推定しない。2015自体はOOF対象外で、boundaryのentrant classificationをdiagnosticに報告しない。2020–2024では前年membershipが必ず存在する。

Side-level status/appearanceのcross-tabsもcountsを保持。Model fitにこれらを入力しない。Membershipのseason-participant metadataをfuture-strength labelとして使わない。

## 11. Calibration diagnostic

Exactly各class × year × probability binについて：`n`, `mean_predicted_probability`, `empirical_class_frequency`, `bias = empirical - predicted`, `total_nll`, `mean_nll`をreport。最後にpooled版。NLLはそのbinに入るmatchの**actual true-class NLL**であり、class c以外のmatchにも`-log(p_c)`を割り当てない。

各class/year全体にも上記を計算し、biasのsign recurrenceを表にする。`sign(x)`は`x > 1e-12`をpositive、`x < -1e-12`をnegative、それ以外neutral。これはnumerical zero判定だけでeffect-size/significance基準ではない。

Max-p reliabilityは各year/binとpredicted-class × year/binの2views：n、mean confidence、empirical argmax accuracy、その差、total/mean NLL、mean Brier。Predicted Drawが0件ならemptyと報告。One-vs-restとpredicted-class reliabilityを混同しない。

Signed/absolute Elo binsごとにclass counts/frequencies、mean p各class、class bias、Accuracy/LL/Brierを報告。Eloの強弱とintrinsic outcome difficultyを区別し、単純なLL大小をcalibration errorとしない。

ECE/MCE、reliability score、p-values、calibrator、temperature/class-weight/threshold optimizationは**含めない**。Argmax Draw=0や高いDraw class NLLだけでmiscalibrationと結論しない。Primary interpretationはyear間の方向/coverageでありpooled gapだけではない。

## 12. Season-transition diagnostic

共通bucket summary（year別をprimary、pooledはcontext）：n、A/D/H counts、各class mean p、Accuracy、LL、Brier、total NLL/Brier、true-class conditional n/mean NLL。True-class cell nも表示し、0件はnull、n<30はSPARSE。

Exactly以下を報告する:

1. Phase opening/middle/closing。
2. Any first-five / neither、both first-five、およびhome/away別1–5 / 6+。
3. Promoted-involved / not、returning-involved / not、established-only。
4. Promoted-involved × phase（全3phase）、returning-involved × phase（全3phase）、established-only × phase。
5. Promoted-involved × any-first-five、returning-involved × any-first-five、established-only × any-first-five（各true/false）。
6. `established_only AND NOT any_team_first5`のcore subgroup（§16のcalibration localization検査）。

Opening-vs-middle、any-first5-vs-neitherのLL/Brier mean deltasは**同year内のdescriptive group difference**でありcausal excess lossではない。各groupのclass mix/mean probabilitiesを必ず併記。Year count、n、fold recurrenceを優先。Nonexclusive groupsを合算してpopulation sizeを作らない。

Offseason shockをfuture wins/final standingsからtarget inputへ逆算しない。No reset/dynamic K/promoted prior/roster feature。First Nは5で固定。

## 13. Favorite failure

Independent flags:

```text
home_favorite = (p_home > p_away)
away_favorite = (p_away > p_home)
near_even = (abs(p_home - p_away) < 0.05)
```

Exact directional tieではhome/away favoriteは両方0、near_evenは1。差がexact 0.05ならnear_even=0。Directional favoriteとnear_evenは重なってよい。これは旧exclusive favorite-type countsを再現する分類とは異なるため、独立flagsのcountsを旧826/593等と同一視しない。

固定viewsはhome-favorite × all true classes、away-favorite × all true classes、near-even × all true classes。したがって必須のHome favorite loses/Draw、Away favorite loses/Draw、near-even each outcomeを漏らさない。共通summaryは§12。Other preferred groupやthresholdを追加しない。LossとDraw率をclub固有補正/threshold研究の根拠にしない。

## 14. Club concentration

各year × stable team IDでhome+away appearances、actual class composition、total/mean NLL、total/mean Brierを報告。Class compositionは**matchのAway/Draw/Home**で、away sideのteam-relative W/D/Lへ反転しない。Row orderはyear ascending / TeamMaster ID lexical ascending。

同じmatch lossを両clubへattributeする。従って各yearのattributed n/loss totalはmatch-level totalの2倍。Club-year NLL shareはpooled **attributed** total `2 * pooled_match_nll_total`をdenominatorにする。Year内shareも`2 * year_match_nll_total`。Unattributed pooled loss shareと取り違えない。

Exactly concentration summaries:

- 全club-year cellsをtotal NLL descendingで並べたtop 5のattributed pooled NLL share（tieはyear/ID ascending）。
- 各year内top 5 clubsのattributed year NLL share。
- Club-year mean NLLのunweighted median、Q1/Q3/IQR。Quantile interpolationはlinear。Pooledと各yearを報告。

Total lossにはappearance数とclass mixの影響があるため、少数cellが高shareでもclub-specific defectとは呼ばない。全cellsを報告し、top5だけをtuning対象として選択しない。Group mean/attributed lossであり、counterfactual「回避可能excess」を推定したものではない。

## 15. Sparse/uncertainty rules

Limited approachは**raw n + point estimates + fold recurrence + direction consistencyのみ**。Wilson/LL/Brier CI、bootstrap、p-value、multiple-testing/significance探索は計算しない。Team/date依存を無視したindependent-sample CIを付けない。

- n=0: `EMPTY`、counts=0、means/rates/deltas=null。No zero-valued mean。
- 0<n<30: `SPARSE`。全point estimateは残すが単独でlane openingを支持しない。
- n>=30: `NONSPARSE`。Reliable/informativeという保証ではない。
- Paired group comparisonは両group n>=30の場合だけrecurrence判定にcount。Class conditional cellはそのtrue-class nで判定。
- All five yearsを固定。Sparse/逆符号/neutral年を削除して分母を減らさない。Adaptive merge、sample-dependent cutoff、subgroup追加なし。

## 16. Decision gates

Source/reference failureは**technical STOP**でありdiagnostic gateを出さない。Accepted reconstructionの後だけ、以下のhierarchyを適用する。Exactly三つのpossible diagnostic gates。他のgates、新しいcandidate、calibrator familyは結果を見て追加しない。

Recurrence requirements、SPARSE n<30、下記localization 0.80は**今回事前採用するdiagnostic design rules**であり、既存結果から最適化した値でも効果の既存事実でもない。Elo/model/reference contractとは区別する。新しいrow-level診断を見てこれらを調整しない。

### A. `PROCEED_TO_CALIBRATION_RESEARCH_SPEC`

少なくとも一つの**同じclass c / 同じbias direction s**で以下を全て満たす場合だけ:

1. Class全体mean biasの同符号sが>=4/5 years。
2. **同一固定p bin**でn>=30かつconditional bias符号sが>=3/5 years。Yearごとに都合のよいbinを選び替えない。
3. そのbin群だけのsparse-tail/single-year artifactではない：n>=30のbinsを合わせたclass biasもsで>=4/5 years。Sparse binsを含むfull-population biasとの比較も報告する。
4. Narrow transition localizationを排除：core subgroup `established_only AND NOT any_team_first5`でn>=30かつclass bias符号sが>=3/5 years。さらに§12のphase/entrant/first5 cross-tabsを使い、ほぼ全biasがnarrow subgroupだけの現象ではないことを下記固定ruleで確認する。

Localizationの固定rule：narrow subgroup `T = promoted_involved OR any_team_first5`。Class cについて各rowの`r_i = 1[result=c] - p_c`、direction sへ向くmassを`m_i = max(s * r_i, 0)`とし、`sum_T(m_i) / sum_all(m_i)`をyear別に報告する。>=0.80は`TRANSITION_CONCENTRATED`と表示。Gate Aには**<0.80かつcore subgroup条件を満たすyearが>=3/5**必要。これはbiasの正負相殺を避けたlocalization vetoで、calibrator改善幅のthresholdでもcausal attributionでもない。Denominator=0はundefinedとして支持年に数えない。

全class/全binsをreportし、複数classが満たしてもgateは一つ。Class/binをfuture calibrator parameterとして選ぶ権限はない。No numeric predictive improvement threshold（calibratorを試していない）。Weak/small biasは仮説に留まり、ここでunseen-performance改善を主張しない。

### B. `PROCEED_TO_SEASON_TRANSITION_DIAGNOSTIC_SPEC`

Gate Aが成立しない場合だけ検討。以下を全て満たす必要がある:

1. 全populationでopening LL > middle LLが>=3/5 years、各比較両group n>=30。
2. 全populationでany-first5 LL > neither LLが>=3/5 years、各比較両group n>=30。
3. **Established-only**でも上記両comparisonが同じyear内でともにpositive、両group n>=30で>=3/5 years。Promoted/returningだけの既存closed問題ではないことが必要。
4. Established-onlyの上記支持年ではBrier deltasも両comparisonともnonnegative（−1e-12以内はnumerical zero）。Class-conditional NLL、class frequencies、mean-pを必ず併記し、LL差とclass mix/entropyを分離できない場合を限界として記す。

LL差positiveも§11のnumerical sign ruleによる。Fixed differences以外のoptimal first-N/season phase/subsetを探索しない。これは**さらなる診断spec**に進むだけで、continuous Eloのcausal defectや修正ruleの有効性を証明しない。Reset/dynamic K/promoted priorの実装を承認しない。

### C. `NO_LANE_OPENED_DIAGNOSTIC_INCONCLUSIVE`

A/Bのどちらも成立しない場合。Single-year、sparse-bin、club-tailだけのpatternはこれに含む。Favorite/club viewsはinterpretation contextであり、別lane/gateを発明するtriggerではない。A/Bが両方相当のevidenceを持つ場合もhierarchy Aを優先し、mixed evidenceをreportする。

## 17. Interpretation firewall

2020–2024 OOFはreused historical research evidence。Diagnostic gatesはhypothesis-generation / research-spec evidenceだけ。Calibration効果、unseen generalization、champion昇格の証拠ではない。

同じOOFでcalibrator family/parametersを選び、そのOOFでconfirmed improvementを主張しない。Future calibration evaluationは別途freezeしたtraining/calibration/validation protocolが必要。2025はspent、opened 2026/27はselection禁止のまま。Tie-break、bucket/threshold/parameter選択にも使用しない。

今回はarchitecture complexity、external information、strength-stateの改善を混同しない。Closed H2H/Cup/workload/J Stats/discipline/first-score/goal/SUB/DF/draw propensity/P/G/promotion/J2は再開しない。

## 18. Future generator design

Proposed fixed module（**今は作成しない**）: `src/modeling/champion_a_oof_diagnostic.py`。

Future authorized commandはno arguments:

```text
.\.venv\Scripts\python.exe -m src.modeling.champion_a_oof_diagnostic
```

No data/model/parameter/season/output overrides、no real-data `--dry-run`/preflightでの先行fit、no `--force`/overwrite。Synthetic pure functions/testsは別で呼べる。Module importと`--help`はno fit/read/write/network。

実装taskではこのcommandを実データで呼ばない。Review後の別実行taskだけがone-time production reconstructionを承認する。既存正式attemptを消費しないが、実データcommandは一回だけ、automatic retry=0。失敗後の再実行は新reviewed taskなしで行わない。

Future flow:

1. Authorized task、clean git tree、committed spec/generatorを確認。Pair存在をfit前にrefuse。同じoutput pairの同時実行もfit前に拒否するprocess-level exclusive lock（OS mutex等、formal markerではない）を保持。新persistent attempt markerは作らない。
2. §4のinput/code/dependency hash gates。Exact loadersでsource validation、row counts/order/team IDs/score/resultを検証。Forbidden fileを開かない。
3. `_add_elo()`をreuseしてEloを一度replay。同じordered sourceから診断metadataを決定。Architecture `build_shared_state()`はG formを作るため使わない。
4. Dedicated module内で§3のpipelineを構築し、exact five fold fit/predict。A contract/metricsを既存sourceから再現するがarchitecture evaluator execution関数は呼ばない。P/G、production predictors/model artifactsに依存しない。
5. Identity/class/probability gate、全fold/pooled reference gate。FailureはSTOP、diagnosticsなし、artifactなし、retryなし。
6. Fixed schema/derived columnsをmemory内に構成。Serialization round-trip gate、input nonmutation/hash再確認、manifest buffer完成後、exclusive pair publication。
7. Fixed diagnosticsはreference gate後だけ。Accepted CSV/manifestをread-onlyで利用し、fitやpredictionを追加実行しない。診断reportの正式実行/保存も別の明示承認task範囲内に限る。

Reconstructionとdiagnostic reportingを同じ実行taskで行う場合もfitは5fold一巡だけ。Artifact write途中のfailureはpartialを残してrefuse状態にする。Accepted pairの修正・削除・regeneration、source/model保存は禁止。

## 19. Future test contract

今はtest fileを作らず、testも実行しない。後続実装のtestsはsynthetic/local temporary fixturesだけを使用。Actual historical 3,208 rowsのfitはintegration testに含めない。

1. Exact five folds/train seasons/count definitions。
2. 2025 pathを開かない（file-open guard）。
3. Hyakunen/2026/27を開かない（file-open guard）。
4. Class order `(0,1,2)`とmismatch failure。
5. StandardScaler statisticsはtraining rowsのみ。
6. Logistic fitはtraining X/yのみ、fresh model per fold。
7. Validation rowsをfitへ渡さない。
8. Target/same-date result漏洩なし。Date batchを先read後apply、same-team same-dateはreject。
9. Exact 34-column order、canonical fold/pooled ID order、source string IDs/metadata保持。
10. Probability finite/range/sum `rtol=0, atol=1e-12`とno silent renormalization。
11. Raw p_true class lookup correctness。
12. NLL correctness（interior、0/1 loss-only machine-epsilon clipping、mean一致）。
13. Brier correctness（sum over3、no /3）。
14. Argmax/tie correctness、max_p/abs_elo_diff。
15. All fixed probability/max-p/abs/signed-Elo bin edge inclusions、p=1、difference=0.05。
16. Phase 5/6/29/30 boundaries、no postponed-date rewrite。
17. Appearance 5/6、mixed home/away first-five、any/both/neither flags。
18. Prior membership entrants/returning/established、left-edge unknown-history semantics。
19. Independent favorite flags、exact p_home=p_away tie。
20. Club double attribution、class composition、correct share denominator、top5 tie/quantile rules。
21. Empty null/SPARSE n=29/NONSPARSE n=30。
22. Each fold metric gate、just-inside/outside tolerance、mismatch STOP before diagnostics/write。
23. Pooled reference gate、weighted row pooling、ID permutation拒否。
24. Formal marker read/write/delete/recreate呼出しが一切ない（guard/sentinel）。
25. Exclusive pair creation、preexisting either file/partial拒否、concurrent fit禁止。
26. Manifest schema/path/input/code/runtime/spec/ID/CSV hash coverage、serialized float round-trip。
27. Replay/refusal、failure no automatic retry/no fallback/no artifact cleanup。
28. Network call guard。
29. Production model/prediction path dependencyなし。
30. Calibration fit/tuning/class weights/additional featuresなし。
31. §16 decision hierarchyをsynthetic summariesで検証：4/5・3/5 thresholds、同じbin/class/sign、localization 0.80、core/SPARSE/neutral failures、Bのestablished-only/Brier条件。
32. Import/helpはno fit/source read/artifact writes、warning/fit failureはSTOP。

## 20. Explicit non-goals

このfreezeではsource/test実装、fit、predict_proba、row OOF生成、Elo replay、metric/diagnostic再計算、calibrator fit、新feature、parameter tuningをしない。Raw/processed/model/prediction artifactsを変更しない。

Formal architecture/default-preflight/evaluation再実行、closed-lane再評価、2025/2026+ selection、production prediction、HTTP、collection、activation、full pytest、pushは実行しない。既存freeze/result/auditも編集しない。

## 21. Final gate

**`FROZEN_FOR_ONE_CHAMPION_A_OOF_DIAGNOSTIC_IMPLEMENTATION`**。

Exact A contract、input hashes、folds、高精度reference metrics、row schema、artifact policy、bins、sparse/decision rulesをfreezeできた。Reference ambiguityは未解決として残っていない。Saved row-level OOFは限定検索で未発見だが、既存A reconstruction contractを固定する妨げではない。

このgateが認めるのは**後続dedicated generator実装とsynthetic testsだけ**。実データfit/one-time reconstruction/diagnostic executionはimplementation review後の別task承認が必要。本書作成中のfit/prediction/diagnostic executionsは0。

Static validation：reviewed HEAD/clean starting tree、11 input SHA一致、reference転記一致、document links/schema/sections/hash tablesを確認。`git diff --check`と`git status --short`で本書だけの変更を検証。Full pytestはNOT RUN。Commit messageは`docs: freeze Champion A OOF diagnostic`、pushしない。
