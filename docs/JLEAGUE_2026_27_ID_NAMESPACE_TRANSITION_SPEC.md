# 2026/27 J1 identifier namespace transition specification

## 1. Problem statement

2026/27 ongoing scheduleには、同じfixtureを指し得る2種類のofficial identifier sourceがある。

- official J.League match-page URL suffix
- J.League Data Site `SFMS02` の `match_card_id`

現在は両方をstate-dependentに単一の`match_id`へ格納する。scheduled時にmatch-page IDを付与したfixtureへ、candidate/completed時に異なるData Site IDが現れると、単なるID変更に見えて`identity_conflict`となる。この保留は現行contractとして正しいが、2つのsource identityを失わずに同一fixtureへ結ぶ明示的なnamespace transition contractがない。

本書はdocs-only designである。production code、test、data、prediction artifactを変更せず、implementationをauthorizeしない。

## 2. Existing identifier sources and repository evidence

### 2.1 Match-page identity

operatorが明示した次のURLだけを取得対象にできる。

```text
https://www.jleague.jp/match/j1/{2026|2027}/{6-digit-id}/
```

`canonical`、ordinary J1、`match_date`、`round`、`home_club`、`away_club`をexact validationしたときだけ、URL suffixをscheduled identityとして使用する。pre-match pageでは`status=scheduled`、score/resultはnull、`evidence_type=official_completion_unconfirmed`である。

### 2.2 Data Site identity

Data Site listingの次のlinkから`match_card_id`を読む。

```text
/SFMS02/?match_card_id=...
```

numeric scoreにはこのIDが必須で、candidate/completedの現在の`match_id`はData Site namespaceである。match-page evidenceがcandidateをcompletedへpromoteしても、`apply_completion_evidence()`はData Site `match_id`をURL suffixへ置換しない。

### 2.3 What the repository proves

read-only audit時点のlatest accepted revisionは次の状態だった。

```text
revision = 71f77a41aedf95913c7e736b41a0f391bab2d843170f90729b1e4b21d0924538
scheduled = 300
candidate = 0
completed = 80
nonblank operational match_id = 87
```

80 completed rowsすべてがData Site `match_id`とofficial match-page evidence URLを併持し、全80件でData Site IDとURL suffixが異なる。例えば同一fixtureに対し、Data Site ID `34517`とmatch-page ID `080701`がexact completed evidenceとして共存する。source parser testもcandidate `match_id=34583`を維持しながらmatch-page evidence ID `091302`でcompletionを確認する。

残る7 rowsはscheduledで、match-page URL suffixを現行`match_id`へコピーしたものなので、2 source IDの一致例ではない。したがってrepository evidenceは「常に同一namespace」を否定し、separate source namespacesとして扱う設計を支持する。個々の値が偶然一致する可能性までは否定しない。

## 3. Current behavior

現在のsingle-field policyは次のとおり。

| State | `match_id` source | Behavior |
| --- | --- | --- |
| scheduled、Data Site IDなし | verified match-page suffix、またはblank | exact evidence時だけlinkし、安全条件付きでcarry-forward |
| scheduled、Data Site IDあり | Data Site listing | previous IDとの差は通常のidentity比較対象 |
| candidate | Data Site `match_card_id` | match-page IDでは置換しない |
| completed | Data Site `match_card_id` | exact game-over evidenceはcompletionを証明するがIDを置換しない |

`_changes()`はnonblank ID同士の変更、またはnonblankからblankへの変更を`identity_conflict`とし、publicationをholdする。これはbridgeが存在しない現在の安全なdefaultであり、implementation完了までは維持する。

## 4. Risks

- single field replacementだけではoriginal scheduled IDのsource namespaceがrowから失われる。
- change logだけにold IDを残す設計は、current-state joinで毎回revision history replayを必要とする。
- prediction artifactは`(match_id, model_version)`がimmutable keyであるため、schedule側のID replacement後に同じfixtureを別IDで再予測する危険がある。
- Data Site consumersはcompleted `match_id`をSFMS02 cache、xG、player data等とのjoin keyとして使うため、match-page IDへ固定すると既存contractを破る。
- 値が偶然同じ場合、scalar比較だけではnamespace transitionを検出できない。
- date/round/home-awayの変更をID bridgeで隠すと、古いofficial evidenceを別のschedule stateへ流用することになる。

## 5. Option comparison

| Design | Simplicity | Auditability | Prediction stability | Compatibility | Verdict |
| --- | --- | --- | --- | --- | --- |
| Option 1: one `match_id` with controlled replacement | schema変更が小さい | old IDはhistory replayなしでは見えない。namespaceも曖昧 | ID変更後のduplicate prediction防止に別対策が必要 | completed側には合わせやすいがprediction keyに危険 | Reject |
| Option 2: `match_page_id`と`data_site_match_id`を別保持 | migrationが必要 | source/provenanceが明確 | fixture bridgeを通じて旧prediction keyを保持できる | existing `match_id`をcompatibility projectionにすれば段階移行可能 | Recommend |
| Option 3: normalized identifier registryのみ | alias追加に強い | 最も一般的 | registry joinが必須 | 全consumerを一度にregistry-awareにする負担が大きい | Future extension |

推奨はOption 2に小さなappend-only bridge ledgerを組み合わせる。wide fieldsは日常的なCSV consumerを単純に保ち、ledgerはimmutable provenanceとprediction reconciliationを担う。`fixture_key`をexternal IDで置換しない。

## 6. Recommended design

### 6.1 Stable logical identity

```text
fixture_key = j1_2026_2027:<home_club>:<away_club>
```

`fixture_key`を2026/27 ordinary J1内のlifecycle identityとする。match-page IDとData Site IDはtyped aliasesであり、どちらも`fixture_key`の代替canonical keyではない。

### 6.2 Typed identifier fields

概念上、current observationに次を持つ。

```text
match_page_id
data_site_match_id
match_id                 # backward-compatible operational projection
match_id_namespace       # jleague_match_page | jleague_data_site | blank
```

最終field名はimplementation freezeで確定する。`match_page_id`はexact official page provenanceからだけ、`data_site_match_id`はcurrent/accepted Data Site linkからだけ設定する。一方から他方を生成しない。

operational projectionは次のように固定する。

| State | Operational `match_id` | Namespace |
| --- | --- | --- |
| scheduled、verified match-page IDあり | `match_page_id` | `jleague_match_page` |
| scheduled、match-page IDなし・Data Site IDあり | `data_site_match_id` | `jleague_data_site` |
| scheduled、両方あり | `match_page_id` | `jleague_match_page` |
| candidate | `data_site_match_id`必須 | `jleague_data_site` |
| completed | `data_site_match_id`必須 | `jleague_data_site` |

この`match_id`はlegacy compatibility projectionであり、fixture lifecycle全体でstableとは定義しない。新規consumerは`fixture_key`とtyped IDを使う。

### 6.3 Identity bridge ledger

new revisionは概念上、次を含むappend-only bridge artifactを持つ。

```text
fixture_key
competition_key
match_page_id
data_site_match_id
bridge_status                 # ESTABLISHED only in accepted state
match_page_evidence_url
match_page_origin_snapshot
match_page_origin_revision
data_site_listing_url
data_site_origin_snapshot
established_revision_id
```

accepted bridgeを後のlisting omissionで削除しない。訂正が必要なら既存revisionを変更せず、新revisionにconflict/withdrawal reviewを記録する。`fixture_identity.csv`のlegacy projectionは当面維持し、typed bridgeは別artifactにする方が既存readerへの影響が小さい。

## 7. Exact transition evidence gate

bridge establishmentには以下をすべて要求する。

1. previous accepted immutable revisionが存在する。
2. previous rowは同じ`fixture_key`のscheduled rowである。
3. previous `match_page_id`はnonblankで、`evidence_type=official_completion_unconfirmed`を持つ。
4. previous evidence URLはexact official J1 match-page URLで、suffixが`match_page_id`と一致する。
5. current raw Data Site rowに実在するnonblank `match_card_id` linkがある。carry-forward、URL construction、ID enumerationは不可。
6. previous/currentの`fixture_key`、`competition_key`、`home_club`、`away_club`、`match_date`、`round`がexact一致する。
7. current explicit match-page evidenceがある場合、canonical、page ID、competition、date、round、home/awayのすべてがprevious identityおよびcurrent rowと一致する。
8. `match_page_id`と`data_site_match_id`は、それぞれのnamespace内で他fixtureに使用されていない。
9. bridge pairが別fixtureへ既に割り当てられていない。
10. snapshot chronology、raw SHA、accepted baselineが既存のfreshness/replay rulesを満たす。
11. candidate/completed publicationはidentity gateとは別に既存score/completion gateも満たす。

ID文字列の等値はgateを省略する理由にならない。値が同じでも2 source provenanceを別々に記録する。

`kickoff_time`、stadium、attendance、broadcast、display labelsだけの変更はbridgeを拒否しない。既存`schedule_changed`または`metadata_changed`は別に記録する。team display nameだけをidentity evidenceに使わない。

score/resultはbridge establishmentに使用しない。completed evidenceのscore exact-matchは、bridgeとは独立した既存completion verificationとしてのみ使用する。

## 8. State-transition table

| Previous accepted state | Current observation | Gate | Publication | Identity result |
| --- | --- | --- | --- | --- |
| scheduled、no IDs | scheduled、no IDs | n/a | existing rules | no typed IDs |
| scheduled、match-page only | scheduled、listing IDなし | carry gate | publish | match-page IDをprovenance付きcarry |
| scheduled、match-page only | scheduled、Data Site IDあり | bridge gate | passならpublish | both IDs、operationalはmatch-page |
| scheduled、match-page only | candidate、Data Site IDあり | bridge gate | passならpublish | both IDs、operationalはData Site |
| scheduled、match-page only | completed、Data Site IDとgame-over evidenceあり | bridge gate + completion gate | 両方passならpublish | both IDs、operationalはData Site |
| scheduled、match-page only | candidate/completed、bridge gate fail | fail | HOLD | previous accepted stateをlatestとして維持 |
| scheduled、no prior ID | candidate、Data Site IDあり | no cross-namespace bridge needed | existing rules | Data Site only |
| candidate、bridge established | completed、same Data Site ID | completion gate | passならpublish | bridgeを維持、operationalはData Site |
| any accepted bridge | later source omits one ID | provenance remains; state rules apply | ambiguity時HOLD | accepted bridgeを消去しない |

## 9. Conflict and hold cases

| Case | Required behavior |
| --- | --- |
| 1. Same fixture, differing IDs | exact bridge gate pass時だけ両方保存してtransition。単純replaceは禁止 |
| 2. Same fixture, equal scalar IDs | namespacesを統合しない。両typed fieldsと両provenanceを保存し、bridge eventを記録 |
| 3. Date changed before Data Site ID | ordinary bridge gate fail。`schedule_changed` + `identity_conflict`でHOLD。fresh exact page evidenceを含む別のreviewed correction contractが必要 |
| 4. Round changed | date changeと同じくHOLD |
| 5. Home/away changed | fixture_keyも変わるためbridge禁止。missing/new fixtureまたはidentity conflictとしてHOLD |
| 6. Data Site ID used by another fixture | duplicate/cross-fixture conflictでHOLDまたはhard failure |
| 7. Previous scheduled provenance missing | old IDをtyped match-page IDとみなさずHOLD。文字列形式だけでは補えない |
| 8. Current match-page evidence conflicts | hard failureまたはHOLD。Data Site rowでprevious identityを上書きしない |
| 9. Candidate without valid bridge | previous alternative IDがある場合HOLD。previous IDがblankならexisting Data Site-only candidate pathを使用可能 |
| 10. Completed without valid bridge | previous alternative IDがある場合HOLD。加えてexisting game-over evidenceがなければ必ず未確認 |
| 11. Identifier later disappears | established bridgeは保持。candidate/completed Data Site ID消失やstatus regressionはHOLD。scheduled listing omissionは既存safe carry rulesを適用 |
| 12. Stale snapshot rollback | current latest/bridgeを変更しない。既処理snapshot replayは同じsummary/revisionを返し、新IDで巻き戻さない |

全ambiguous caseでHOLDをdefaultとする。

## 10. Event and immutable provenance rules

既存`identity_linked`と`identity_conflict`だけでは、値が同じnamespace transitionと、正当に異なる2 IDのbridgeを表せない。次を追加候補とする。

```text
identity_bridge_established
identity_namespace_transition
```

- `identity_bridge_established`: second typed identifierを同一fixtureへexactに結んだ時に一度記録する。
- `identity_namespace_transition`: operational `match_id_namespace`がmatch-pageからData Siteへ変わった時に記録する。scalar IDが同値でも記録する。
- failed gateは既存`identity_conflict`を維持し、new latestをpublishしない。

eventのbefore/afterには少なくともfixture key、両typed IDs、operational ID/namespace、status、identity-bound fieldsを含める。provenanceにはprevious accepted revision、current snapshot、両source URL/SHA/fetched time、bridge gate versionを含める。scoreはcompletion eventには含められるが、bridge justificationにはしない。

既存raw snapshot、accepted revision、prediction rowは一切書き換えない。later bridgeはnew immutable revisionとしてのみ追加する。

## 11. Prospective prediction compatibility

### 11.1 Existing immutable outputs

`xg_challenger_prospective.csv`と`model_architecture_prospective.csv`は`(match_id, model_version)`をimmutable keyとし、既存rowsを上書きしない。read-only audit時点では両artifactにscheduled match-page IDs `100903`と`100901`を使った2026-10-09のrowsが存在する。

later Data Site IDが異なっても、これらのrowsは次を禁止する。

- `match_id` replacement
- row regeneration
- delete/reappend
- Data Site IDによるsecond prediction

### 11.2 Prediction identity bridge

later evaluationはdirect `prediction.match_id == completed.match_id` joinを行わない。append-only prediction identity mappingを介する。

```text
(prediction_artifact, prediction_match_id, model_version)
    -> fixture_key
    -> data_site_match_id / completed outcome
```

mappingはprediction rowのoriginal ID、namespace、fixture key、schedule identity revision、later bridge revisionを保存する。join時にmatch date、home/away TeamMaster IDsもexact確認する。one-to-oneでなければevaluationを停止する。

current prediction CSV schemaには`fixture_key`もID namespaceもないため、既存fileへcolumnsを追加してはならない。implementationでは次のどちらかをfreezeする必要がある。

1. existing prediction filesを不変のまま保ち、append-only sidecar identity registryを追加する。
2. future-only versioned prediction artifactへ`fixture_key`、ID namespace、identity revisionを追加する。

既存2 rowsをsidecarへ登録する場合も、official match-page provenance、unique original `match_id`、match date、home/away TeamMaster IDsをexact照合する。生成時刻の近さだけでmappingしない。

prediction modulesのduplicate preventionも`(current operational match_id, model_version)`だけでは不足する。bridge済み`fixture_key`に同model_versionのpredictionが存在すれば、新Data Site IDでappendせず`ALREADY_PREDICTED`相当とする。ただしoriginal prediction artifactのimmutable key定義自体は変更しない。

## 12. Required implementation changes

### 12.1 Current consumer assumptions

| Consumer | Current `match_id` assumption | Two-ID impact |
| --- | --- | --- |
| `jleague_ongoing_source.py` | one field may contain either source ID; candidate keeps Data Site ID | parser/apply outputをtyped fieldsへ分離 |
| `jleague_ongoing.py` change/coverage/identity projection | one scalar is stable and globally unique in current schedule | namespace-aware uniqueness、bridge event、legacy projectionが必要 |
| `validate_matches()` | completed ID is nonblank string and unique。namespace自体は検証しない | completed projectionをData Site IDに維持すればinterfaceは維持可能 |
| ongoing Elo、xG history、completed-match consumers | completed `match_id`はData Site-derived assetsと結合可能 | completed operational IDをData Siteに固定し、必要ならnamespace assertionを追加 |
| `xg_challenger_prediction.py` | schedule `match_id`がtarget IDで、`(match_id, model_version)`がappend key | existing output不変。fixture-aware sidecar/deduplicationが必要 |
| `model_architecture_prediction.py` | 上と同じcommon prospective contract | existing output不変。same fixtureのnew ID再予測を防止 |
| prospective evaluation workflow | 将来direct `match_id` joinを行う余地がある | prediction ID -> fixture key -> Data Site outcomeのbridge joinを必須化 |
| `jleague_suspensions.py` / registry | schedule `match_id`を`target_match_id`として長期保存 | fixture keyとnamespaceも保存し、later operational changeを監査可能にする |
| `jstats_snapshot_registry.py` | completed intervalを`match_id`でunique/sort | Data Site typed IDを明示的に選択。match-page IDへ切り替えない |
| `fixture_identity.csv` readers | fixture keyに対しoperational `match_id`が1つ | legacy projectionを維持し、新bridge artifactを別に読む |
| historical feature/model builders | 2015–2025 Data Site `match_id`でstrict join | transition scope外。schemaを変更しない |

IDを整数化するcontractはなく、leading zeroを持つmatch-page IDを保存するため両typed IDsはstringとする。Data Site parser固有のlink syntax validationはそのnamespace内で維持する。

### 12.2 Future implementation scope

将来のseparate implementation taskでは少なくとも次を扱う。

- `src/collect/jleague_ongoing_source.py`: Data Site IDとmatch-page IDを別typed fieldへparse/applyする。
- `src/collect/jleague_ongoing.py`: bridge gate、typed state、new events、bridge artifact、cross-namespace uniquenessを実装する。
- `scripts/update_jleague_ongoing.py`: network boundaryを変えず、review summaryへtyped identity/bridge statusを表示する。
- ongoing update tests/source tests: Section 13を実装する。
- `src/modeling/xg_challenger_prediction.py`: fixture-aware already-predicted checkとsidecar verificationを追加する。
- `src/modeling/model_architecture_prediction.py`: 同じfixture-aware append protectionを追加する。
- prediction runbooks: original prediction IDとlater outcome join contractを明記する。
- `src/collect/jleague_suspensions.py` / suspension registry: long-lived `target_match_id`だけでなくfixture keyとID namespaceを保持する。既存registry artifactは書き換えない。
- `src/collect/jstats_snapshot_registry.py`: completed intervalのoperational IDがData Site namespaceであることを明示的に検証する。
- ongoing Elo/xG/completed consumers: completed `match_id`が引き続きData Site IDであることを検証する。
- `fixture_identity.csv` consumer: legacy projectionかtyped bridgeのどちらを必要とするか明示する。

historical 2015–2025 feature/model codeの`match_id`は既存Data Site identityであり、本transitionによるschema rewrite対象ではない。

ongoing bridge publication、prediction sidecar、fixture-aware duplicate preventionは同じimplementation releaseで有効化する。scheduleだけを先にstate-dependent Data Site IDへ切り替えると、既存predictionを別IDで再生成できてしまうため禁止する。いずれかのconsumer gateが未実装ならtransition revisionはHOLDする。

## 13. Synthetic test plan

実データ取得は行わず、すべてsynthetic immutable snapshots/artifactsで実施する。

| Case | Setup | Expected publication | Expected identity state | Expected events / audit |
| --- | --- | --- | --- | --- |
| A. URL ID -> same Data Site ID | previous scheduled exact match-page ID `123456`; current exact Data Site ID `123456` | published | both typed fields=`123456`; candidateならoperational Data Site | `identity_bridge_established`; namespace change時は`identity_namespace_transition`。scalar equalityで省略しない |
| B. URL ID -> different Data Site ID | previous page `123456`; current Data Site `999`; all bound fields exact | published | both values preserved; candidate/completed operational=`999` | bridge + namespace transition; no`identity_conflict` |
| C. Missing previous provenance | previous nonblank IDだがevidence URL/type不正または欠落 | held | no bridge; latest unchanged | `identity_conflict` with failed gate reason |
| D. Date change | previous verified page ID; current Data IDとdifferent date | held | no bridge; old accepted state remains latest | `schedule_changed` + `identity_conflict` |
| E. Round change | Dのround版 | held | no bridge | `schedule_changed` + `identity_conflict` |
| F. ID reused by another fixture | current Data IDまたはpage IDが別fixtureに既存 | held/hard failure | duplicateを作らない | cross-fixture `identity_conflict`; previous latest unchanged |
| G. Candidate transition | previous page-only scheduled; current exact Data ID + numeric score | published only after bridge gate | status candidate、both IDs、operational Data Site | `result_candidate` + bridge + namespace transition |
| H. Completed transition | Gにexact official game-over evidenceを追加 | published only after bridge and completion gates | completed、both IDs、operational Data Site | `completed` + bridge + namespace transition; completion provenance別保持 |
| I. Stale snapshot | bridge publication後にolder listingをnew snapshot IDでprocess | held/no rollback | accepted bridge/current latest unchanged | stale-observation block; no bridge withdrawal |
| J. Replay/idempotency | same immutable transition snapshotを再process | same prior result | byte-identical revision/projections | no duplicate event、bridge、history row |
| K. Prediction immutability | page ID keyed prediction exists; later differing Data ID bridge | update publication may pass; prediction file untouched | prediction keeps original ID; sidecar links fixture | prediction bytes unchanged、no second prediction、fixture-aware already-predicted |
| L. Evaluation join | prediction page ID、accepted bridge、completed Data Site outcome | n/a/read-only | one prediction -> one fixture -> one outcome | exact namespace-aware one-to-one join; direct ID join prohibited; mismatch/ambiguity fails |

追加regressionとして、kickoff/stadium/display metadata change、explicit current evidence agreement/conflict、identifier disappearance、completed provenance inheritance、raw tamper、writer lock、missing fixture、coverage、same-input replayを維持する。

## 14. Migration and backward compatibility

これはmaterial schema/identity semantic changeである。`ongoing-v1`のままsilent migrationすることは推奨しない。implementation freezeでは`ongoing-v2`等のnew formatと明示的なv1-to-v2 bootstrapを検討する。

read-only audit時点のv1 latestはdeterministically分類できる。

- 80 completed: operational `match_id`を`data_site_match_id`へ、validated evidence URL suffixを`match_page_id`へ保持する。全80 pairsは異なる。
- 7 scheduled exact pre-match provenance rows: operational `match_id`を`match_page_id`へ保持し、Data Site IDはblank。
- 残るscheduled rows: typed IDsはsource evidenceどおりblank。

この分類はmigration codeとfixture-by-fixture auditで再検証し、既存revisionを編集しない。新formatのbootstrap revisionがold latest revision ID、source SHA、migration policy versionを依存関係として記録する。provenanceが不完全なv1 rowは形式や日付から補完せずunresolvedにする。

既存prediction、suspension registry、raw snapshot、historical match artifactsはmigrationしない。必要な対応はnew append-only bridge/sidecarで表す。

## 15. Explicit non-goals

- production implementationまたはtest implementation
- live HTTP、real snapshot capture、URL discovery、ID enumeration
- match-page IDとData Site IDの算術変換・同値仮定
- fixture keyからのID生成
- fuzzy team matching、home/away swap、date/round inference
- score/resultによるidentity bridge推測
- existing revision、raw、prediction、model、suspension artifactのrewrite
- model fit、prediction generation、performance evaluation
- historical 2015–2025 match identity migration

## 16. Decision status

The exact implementation contract is frozen separately in
[JLEAGUE_2026_27_ID_NAMESPACE_IMPLEMENTATION_FREEZE_SPEC.md](JLEAGUE_2026_27_ID_NAMESPACE_IMPLEMENTATION_FREEZE_SPEC.md).

```text
DESIGN_READY_FOR_REVIEW
```

Repository内の80 exact completed observationsとsource/test contractにより、match-page URL suffixとData Site `match_card_id`がseparate source namespacesであり、同一fixtureに異なる値で共存し得ることは十分に裏付けられている。このためdesign自体はexternal identifier evidence待ちではない。

ただしimplementationは本taskでは**NOT AUTHORIZED**である。別taskでschema/version、migration、prediction sidecar、event contractをfreezeしてから実装する。各live transitionのpublicationには、その時点のnew immutable Data Site listing observationとSection 7の全gateが必要であり、未来のIDを事前に推測してはならない。
