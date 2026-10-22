# 週末一括予測 Phase 2：本番接続前の安全性確認

調査日：2026-10-22 JST。基準：`33b2108e2b618e603f94e280746763af0f1ff56a`。
独立branch：`feature/weekend-batch-preflight`。

**判定：`HOLD_WEEKEND_BATCH_PRODUCTION_PREFLIGHT`。本番は未有効化。**

Phase 1のオフライン実装を維持し、保存済み証拠の読取り、readerの防御修正、合成検証を行った。
07:00以前に完了した公式publicationの専用証跡と、本番用backendの結合は未成立である。
テスト合格は、実予測・タスク・収集・feed更新の承認ではない。

| 項目 | 今回の結果 |
| --- | --- |
| 07:00以前のsource確保 | 現行朝処理では不成立。別の事前確保経路が必要 |
| 日別/v2 reader | 合成検証PASS。運用worktreeへは未反映 |
| Champion A入力 | 固定metadata・SHA・コードとmock入力の整合を確認。実モデルは未ロード |
| 週末予約 | 水曜07:00前の導入手順を設計。本番予約なし |
| feed・UI再読込 | 既存経路と改善契約を整理。実feed・入口は変更なし |
| 保護監査 | 別添validation JSON。元の全worktree・タスク・保存データを照合 |

## 1. 公式sourceの実時刻

現行07:00タスクの実行先は運用専用worktreeの`5ac9052`。
`scripts/update_champion_dashboard.py`は、排他・既存batch読取りの後にcollectorを呼び、
collectorが一覧・詳細を取得してsnapshotと公式publicationを作る。
22:00処理も公式更新・表示更新を行うが、予測生成は行わない。
両タスクはInteractiveToken、StartWhenAvailable、IgnoreNew、15分上限であり、予定時刻は
実際の開始・取得・公開完了の証明にはならない。XML・設定・実行状態は読取りのみ。

保存済み10/22朝の証拠は次のとおり。これは**木曜の実行例**であり、金曜の成功実績ではない。
同じ処理順序を金曜に用いても、07:00以後の取得を締切以前として扱えない。

| 事象 | UTC（2026-10-21） | JST（2026-10-22） |
| --- | --- | --- |
| update開始 | 22:00:03.831707 | 07:00:03.831707 |
| 公式一覧request開始 | 22:00:04.068547 | 07:00:04.068547 |
| 公式一覧取得完了 | 22:00:04.509460 | 07:00:04.509460 |
| snapshot内の最終source観測/取得完了 | 22:00:30.807718 | 07:00:30.807718 |
| snapshot manifest作成 | 22:00:41.691273 | 07:00:41.691273 |
| 既存土曜batchの生成UTC | 22:00:52.920618 | 07:00:52.920618 |
| update全体完了 | 22:00:53.383266 | 07:00:53.383266 |

公式revision：`d179144f38ec64a43ef6bd860ca8802a19c89399a69e29c4e20c8cde1d15dc23`。
manifest SHA：`14ebc385fd3e45597895700abf8b524c6faf71f339c99cb653ebdd8c9a474184`。
snapshot manifest SHA：`12dafa20bcc517e814d2ddf9278ac9c75c0d4012c69fc671def8eea597022336`。
manifestの全payloadとsnapshot内16 sourceのraw/metadata SHA、HTTP 200、URL、bytes、
request開始≤取得完了を照合した。実際のネットワーク取得は行っていない。

`src/collect/jleague_ongoing.py:create_snapshot`の`observed_at_utc`は、source取得完了UTCの最大値。
試合終了時刻、公式が最初に結果を公開した時刻、publication完了時刻とは異なる。
`_publish`はprojectionの後にlatest pointerを切り替えるが、専用の公開完了UTCを残していない。
このrunの公開はコード上snapshot作成後・予測生成前に位置するが、正確な完了UTCは**不明**。
ファイルmtimeやupdate完了UTCを公開完了の実測値へ置き換えない。
取得済み結果ページは「その取得時点で確認できた」根拠であり、最初の利用可能時刻は立証しない。

現revisionは110 completed、10/23金曜00:00より前の未完了0件。
直前の承認revision `4d5e1052a2e8a7205f4e570037091eec19ede1fa69e241f58184d6854dc46fc6`
（manifest SHA `08770c038308f3da29b76bf9d5b2a4dc01fb8f91c352de5636c153d6789ba932`）は
10/21 07:00:20 JST観測、100 completedで、10/23以前に10件の未完了が残る。
古い承認revisionを選ぶだけではこの履歴完全性を満たさない。
次候補10/30についても、現在のrevisionではその前に10件未完了があり、将来の合格を主張しない。

### 事前確保案（設計のみ）

別承認で、例えば06:45から有限時間内に完了する独立source確保を用意する。
実際の開始・完了、アクセス条件、通信量・対象上限は別途定義し、遅延時はHOLDとする。
06:45に設定すれば必ず成功するという保証ではない。22:00取得済みpublicationを使う場合も
同じ鮮度・全履歴完了・fixture identity・取得証拠ゲートを通す必要がある。

- 全raw/metadata、request開始/取得完了UTC、snapshot作成、公式revision/manifest/全入力SHAを固定する。
- pointer公開・fsync/readback完了を実UTC付きで独立receiptに封印し、**公開完了も金曜07:00以下**とする。
- 金曜00:00より前の全公式fixtureが完了・90分結果確定、証拠取得≤07:00、鮮度24時間以内を検証する。
- 結果の実際の利用可能時刻が不明な場合に時刻を補わない。未完了・未知中断・矛盾はHOLD。
- 07:00時点までに選んだimmutable publicationを別laneで固定する。朝collectorによるその後の
  latest更新をそのsnapshotへ取り込まない。binding/feedからも固定revisionへ安全に到達可能にする。
- 情報cutoff 07:00、履歴cutoff 00:00、実freeze、生成、保存前確認、公開完了を別field/receiptにする。
  `取得/観測/公開完了≤07:00≤実freeze≤生成≤保存確認<全kickoff`を検証する。
- 現Phase 1の`prepare`は観測UTCと結果証拠UTCを検査するが、公開完了receiptを要求していない。
  さらにupdaterは先に通常collectorを呼ぶ。事前sourceを採用するprovider/receiptの結合は未実装。

新規GET、収集コマンド、publication再生成、新タスク作成・時刻変更は今回0件。

## 2. 日別/v2 readerとrollback

現在の運用readerは64桁hexの旧directory名と2 CSV SHAだけのmanifestを要求する。
正規の`weekend-v2-<manifest SHA>`は`invalid_batch_directory`で拒否し、誤って取り込まない。
旧readerの関数を`5ac9052`から固定したテスト用コピーとし、そのASTが現運用/基準commitと同一で
あることをローカル監査した。旧日別を読めること、v2を拒否してbyte変更しないことを合成実行した。

新readerは旧日別と`champion-weekend-v2`を明示分岐し、v2ではmanifest/context/snapshot、
CSV、binding、fixture集合、共通feature、取得/生成/保存確認UTC、全SHAを検査する。
今回、前工程のreaderで再現した不足を次の範囲に限り修正した。

- 日別directoryはmanifestと2 CSV以外を拒否。v2のcontextを無視した旧形式への格下げを拒否する。
- 旧manifestの重複JSON keyを拒否し、batch/fileのsymlink・junctionを検査する。
- 日別reader自身がbinding件数・artifact・identity・生成UTCを検査する。feed検証まで待たない。
- 混在batch全体でfixtureと保存prediction IDの重複を拒否する。namespaceを口実にID衝突を許可しない。
- v2読取りでもsource鮮度24時間と、既存writerの最大900秒の保存確認期限を要求する。
  SHAを整合させ直しただけの期限超過・古いsnapshotも拒否する。

有効な既存形式・CSV列・確率・生成時刻は変更しない。新形式もまだ`SYNTHETIC_ONLY`であり、
本番形式が完成したとは扱わない。実runtimeの4日別batch計19件はSHA照合のみ。
readerはmanifestとローカルSHAの整合を検査するが、署名された信頼起点ではない。
権限を持つ者がv2 contextと履歴をすべて削除し、旧CSV/manifestまで作り直す攻撃を形式検査だけで
識別できるとは主張しない。本番では承認batch inventory/receiptの固定とACL監査が別途必要。

合成検証では、新旧混在、重複公開、部分保存、SHA/欠落、context格下げ、保存前失敗、
commit後feed失敗、再実行時の推論0/byte不変、無効モードでのv2維持を確認した。
失敗staging・attempt・HOLDは保存し、自動回収・再推論しない。
保存manifestの`committed_at`はrename前の保存確認時刻であり、OS公開完了の実測receiptではない。
本番結合では実公開後の独立receiptと障害時照合、Windowsの永続化・所有権を追加検証する。

rollbackは新規週末書込みだけを停止する。公開済みv2、reservation、staging、HOLD証跡を削除しない。
互換readerを残した日別モードかlast-good表示へ戻す。v2があるruntimeを旧readerへ戻すとHOLDとなる。
予約解除・日別再開は既保存集合と日別完全性を検査して別承認で行う。

## 3. Champion A入力契約

モデルをdeserializeせず、固定bundleのSHA、metadata、source dataset SHAとコードを照合した。
Champion A版は`operational_champion_20260922_v1`。bundle識別SHAは
`2d2e50dbfc4d71ec2cdaf5fe1a6e48953c160c388f1740cfe538f29f593646d1`。
metadata SHAは`bd1eb92c25bdb56a836ef7bfe3fcb13b0137a2ece01b6095e7d100e1f5afdd19`。
`champion_prediction.py`、`elo.py`、`elo_history.py`は運用版とbyte同一。

| 入力/処理 | 固定契約 |
| --- | --- |
| 学習履歴 | 2015〜25の3,588件と固定training manifest/source SHA |
| 後続履歴 | 承認済み百年構想200件、金曜00:00前の公式完了90分結果のみ |
| Elo | 初期1500、K=30、HA=175、season resetなし。汎用Elo default K=20を使用しない |
| HA | Elo期待値/更新でhome側へ適用。モデル入力`home_rating-away_rating`へ175を加算しない |
| 列順・型 | `elo_diff`だけのfloat行列 `(N,1)`。Form・ST2・NN研究値を含めない |
| target API | fixture/typed ID/日付/kickoff/両TeamMaster/namespaceの7列。結果列は拒否 |
| 前処理 | 固定StandardScalerのtransformのみ、fit禁止 |
| 出力 | classes `(0,1,2)` = Away/Draw/Home、有限の3確率、各0〜1、和1 |
| 順序 | 履歴は日付/ID順で一度replay。全対象は同じrating mapを読むだけ。週末中updateなし |
| 時刻 | 情報は金曜07:00以下。実生成/保存確認/公開完了を記録し、全試合開始前を要求 |

固定training replayとID30700の既存運用処理は変更せず、NN研究の時刻処理を移植しない。
合成履歴とmock scaler/modelで、float1列、HA二重加算なし、対象順序不変、未来結果列拒否、
classes順序矛盾拒否、土曜結果の混入拒否を検証した。
実scaler属性・実estimator実行は検証していない。既存ローダーにはtype/shape/finite/hash検査が
あるが、今回は呼び出していない。そのコードが存在することを実ロード成功とは報告しない。

Phase 1 backendは一時領域と明示されたmock artifactのみを受け付け、通常CLIは有効化を拒否する。
本番backend、実model/scalerを別々に封印する証跡、取得来歴、公開後receiptの接続は別工程。
合成scopeを本番へ書き換えたり、scalerを再fitして合わせたりしない。

## 4. 予約と移行手順（未実行）

1. 独立承認後に、本番用reader/provider/backendと失敗時receiptをオフライン結合検証する。
   旧形式の読取りを維持し、runtime/model/source/既保存/タスク定義のbackupとSHAを固定する。
2. 当時の公式revisionから**全未保存・未予約**の将来金〜月を選ぶ。開始時刻不明、未確定、
   期間内同クラブ複数出場、部分既保存、source不整合はHOLD。
3. 水曜07:00より前、かつ最初の日別保存より前に対象期間・全fixture・予約実UTC・source SHAを
   排他的に確定する。遅延した予約を過去時刻で登録せずHOLD。火〜木の日別対象は維持する。
4. 金曜前にsourceを確保し、07:00時点の完全性を検証する。朝実行ではその封印sourceを使用し、
   後から取得したrevisionへ自動置換しない。日程変更/延期/中止/追加は再審査HOLD。
5. モデル/入力/予約/公式pointer/既保存集合を保存直前にも検査し、共通snapshotの全件を
   同一volumeの単一directory renameで公開する。競合・期限超過・部分失敗は公開0件。
   公開後receipt/feed失敗は予測の再生成に結び付けない。
6. 実予測の初回実行・設定/タスクへの反映・表示更新はそれぞれ承認範囲を固定して実施する。
   22:00処理へ予測生成を追加しない。

10/24保存済み5件と10/25未保存5件は移行対象外。再計算・補完・同一snapshot認定はしない。
10/30〜11/2は現在全10件未保存だが、本番導入対象として決定していない。
その場合でも予約期限は10/28 07:00 JSTより前で、実行時の履歴完了証拠が別途必要である。

## 5. feed更新と画面再読込の設計

運用朝/夜は`build_display_feeds`で同じ公式pointerからhome schema v1とrounds schema v2を
検証し、予測batch commit後に`publish_display_feeds`で各JSONをreplaceする。
handled failureは復元するが、2ファイルをまたぐcrash原子性は保証しない。
したがって予測commit成功と表示更新失敗を分離し、表示失敗で予測を再実行しない。

Desktopの現在の正式入口はUI branchの通常ブラウザlauncherで、明示指定Champion JSONを読む。
そのserverは起動時bytesを保持し、browserも初回fetchのみ。ブラウザF5だけではserver内の
snapshotは更新されない。運用branchにはreload/status/60秒pollがあるが、この入口には未接続。
既存reloadのlast-good回帰テストは今回再実行したが、現Desktopで動作したとは認定しない。

別の表示改善工程では、次の契約を実装・検証することを推奨する。

- batch確定後だけ、保存済みChampion Aを新旧互換readerで読み、schema v1へ投影する。
  current official applicabilityと日別完全性、改日程、bindingを再検証する。
- JSONを新規immutable display generationへ作成し、schema・入力revision・payload SHA・件数を
  全て検証/readback後にgeneration pointerを1回切り替える。updating/errorの途中JSONは読まない。
- serverは明示された自身のデータ領域だけを読み、pointer前後一致、SHA、schema、generationの
  単調性を検査する。公式observed_atだけでは同sourceの予測追加を検知できないため別のgenerationを使う。
- 不正/途中/後退したfeedはlast-good表示を保持し、stale/errorを明示する。初回不正は停止し、
  demoへ自動fallbackしない。NN・再現予測・未保存試合を予想として補完しない。
- browserは同一originのbounded poll（例60秒）と手動更新を使い、更新失敗で既存DOMを壊さず、
  ページ・scroll・focusを維持する。個人profileや他serverを操作しない。
- snapshot/model/input SHAや個人パスなどをUI JSONへ漏らさない。schema v1の確率・生成UTC・identityを維持する。

上記generation化・UI移植・自動再読込・feed定時生成経路変更は今回実装/有効化していない。
運用branchの研究/再現overlayを含む表示実装全体をUIへコピーしない。

## 6. 実施検証と残る承認

今回の最終検証：**422 PASS、warnings-as-errors、skip/failure/error 0**。
内訳はPhase 1の既存5module計402件を今回再実行、新preflight module20件。
既存402件の過去証跡を新規PASSとして流用していない。
初回の新テストではreader不足5件、追加境界テストでは不足3件を再現し、独立ログを保持した。
修正後の最終JUnit・コードSHA・保護結果は[validation JSON](WEEKEND_BATCH_PHASE2_VALIDATION.json)に保存する。

本番実行前に残る必須事項：

1. 07:00前sourceの実取得・公開完了・readbackを証明する専用receiptと固定lane/provider。
2. mock専用と区別した本番backend/manifest契約、実model/scalerの結合と別承認での検証。
3. 互換readerの運用配置、予約導入、公開後receipt/Windows crash・権限・競合・復旧手順の実証。
4. 将来の全未保存週末の選定と予約、実行時の履歴完全性・全fixture開始前確認。
5. 表示更新の結合・実feed生成、UI再読込を導入する場合の別承認。

新規公式GET/収集、本番model load/fit/推論/評価、実予測変更、実feed生成/上書き、
タスク実行/変更、Desktop適用は全て0。Gitの通常pushだけを行う。
現行運用設定はweekend policyなし（既定無効）のまま。
main/UI/NN研究/Phase 1/運用worktreeと既保存19予測を保持し、10/25の5件も追加していない。
