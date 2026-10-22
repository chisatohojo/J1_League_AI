# 週末一括予測 Phase 3：事前sourceとpublication receipt（オフライン限定）

基準：`a3833d75e97970912d99a815eb76dd056b0e4a96`。
専用branch：`feature/weekend-source-receipt`。
判定：`WEEKEND_PRE_CUTOFF_SOURCE_OFFLINE_READY`。

新実装は`src/modeling/weekend_source.py`だけに分離した。既存collector、publisher、
updater、週末backend、モデルローダー、UI、運用設定は変更していない。
通常CLIへの接続・有効化スイッチはない。全ての書込みは新規作成したsystem temp配下の
専用scope markerを持つ合成workspaceに限られる。実データをこの仕組みで再公開していない。
この判定は本番取得・本番receipt・実予測を実証したものではない。

## A/B比較と優先順位

| 観点 | A：前夜22:00の確定source | B：独立した事前確保 |
| --- | --- | --- |
| 優先 | 全条件とreceiptが成立する場合に優先 | Aが未完了・古い・receipt不足なら別承認で候補とする |
| 通信 | 既に封印済みなら追加取得不要 | 別途、正確な対象と通信上限を固定した取得承認が必要 |
| 履歴 | 木曜深夜までの未終了試合が残ればHOLD | 06:45でも結果が確定しなければHOLD |
| 締切 | 全取得・公開・receipt検証が金曜07:00以下 | 同じ。06:45開始は成功保証ではない |
| 所有 | 完成済みの明示revisionを固定 | 通常updaterと別laneで一度だけ公開する |
| 障害 | 欠損や矛盾を修復・時刻補完しない | timeout、上限、部分公開、時計異常はHOLD |

**Aを条件付きで優先し、Bを必要時の独立候補とする**。追加通信を減らせる一方、木曜の
遅い試合などでAが成立しない場合がある。優先順位による自動fallbackは実装していない。
明示的に選択したsourceがSHA不一致になった場合、別revisionへの自動差替えで隠さない。

保存済み運用証拠も読取りで再照合した。10/22朝の一覧取得は07:00:04.509460 JST、
最終観測は07:00:30.807718、snapshot作成は07:00:41.691273。
専用publication完了UTCは依然存在しない。これらを過去の完了receiptへ変換していない。
旧22:00タスクの失敗も修復・再実行していない。今後の22:00成功を予定時刻から推定しない。

将来、Aを使う場合も当夜の実処理でreceiptを残す必要がある。過去の確定revisionを別途
再封印するなら、その**新しい公開の実UTC**を記録し直して全ゲートを通す。元publicationの
不明な完了時刻を補ったことにはしない。本工程ではいずれも実データで行っていない。

## Receipt契約

版：`weekend-source-publication-receipt-v1`、scope：`SYNTHETIC_ONLY`。
`publish`は取得済みの合成candidateを独立laneへcopy・fsync/readback・検証して、単一の
同一volume directory renameで公開する。その後、公開先の全入力を再読込みしてから、
公開完了UTCとreceiptを記録する。ここでの公開時刻は**独立laneの公開・読戻し完了時刻**であり、
candidateを最初に作ったpublisherの時刻やkernel renameの瞬間を代用したものではない。

receiptには次を含める。

- 版/scope、明示revision、公式manifest SHA、現在および継承結果の元snapshot SHA。
- TeamMaster・全publication payload・全raw/metadataのSHA集合。
- sourceごとのURL、request開始/取得完了UTC、raw/metadata SHA、bytes。
- source観測/取得時点、snapshot作成UTC、公開開始/完了UTC、receipt作成UTC。
- 金曜00:00の履歴cutoffと07:00の情報cutoff、全fixture件数、完了履歴件数、対象全identity。
- 公式事実/結果/fixture完全性、payload fsyncと公開先readbackの結果、wall/monotonic観測列。
- `receipt_sha256`：そのfield自身を除いたcanonical JSON payloadのSHA。

`receipt.json`は公開の検証完了**後**にexclusive-createする。fsync・readback後に`seal.json`を
作成し、sealもfsync・readbackする。返却する`Reference`はreceiptファイル全体SHA、seal全体SHA、
その検証完了の実UTCを固定する。この観測を`reference.json`へ保存し、読取りでも一致を要求する。
Referenceは新しいsource情報を加えるものではなく、既に確定した証拠への明示的なanchorである。
receipt欠落、seal/Reference欠落、改変、不明UTC、未完了の公開は全てHOLD。
mtimeを時刻へ代用するコードはない。

失敗したstaging、公開済みだがreceipt未完成の原本、開始attemptは削除しない。
attemptはrevision単位で一度限り。同じworkspaceで失敗runを再実行しても拒否し、
既存publicationへreceiptだけを後付けするentry pointも設けていない。

## 入力検証と境界

`inspect`は明示revisionだけを読む。変更していない既存公式reader、snapshot reader、
HTML parserを使い、次を追加確認する。

- 普通J1 20クラブ・380 fixture・38節、typed identity、TeamMaster、日時、90分結果。
- snapshotのrun/manifestへのSHA結合、全raw/metadataとrequest UTC、redirectなし/HTTP 200。
- 元rawから解析した全fixtureとpublicationの一致。完成結果は元snapshotのgame-over証拠とも
  スコア・原本SHA・取得UTCを完全照合する。継承結果の元snapshotも省略しない。
- 金曜00:00前の全fixture完了。期間内の結果を混入させず、全targetが未開始・scheduled・結果空欄。
- 現sourceの鮮度は07:00から24時間以内。履歴の古い証拠を24時間以内だったと改変しない。
- 全取得完了/snapshot作成/公開完了/receipt検証≤金曜07:00。UTC必須。不明ならHOLD。

07:00:00ちょうどは許可し、1 microsecond超過は拒否する。実freezeは07:00以降、
予測前・保存前checkpointは同じ金曜の07:15以下かつ全target kickoff前を要求する。
これはPhase 1の最大900秒契約を維持するもので、締切変更ではない。
予約は水曜07:00より**前**で、対象集合・期間・SHAを固定する。

publisher全体とprovider sessionそれぞれのmonotonic deadlineは600秒。wallの逆行、monotonicの逆行/非有限値、
両時計の差が区間または累積で2秒を超える変化は拒否する。保存済みrequestの有限上限は30秒、
snapshot内の重複した同時通信を拒否する。これはローカル時計に基づく観測であり、
時刻の絶対的な真正性や外部時刻認証を証明していない。
deadlineは処理境界で検査する。OSによるworker強制終了・cleanup期限はこのオフラインAPIの
機能ではなく、実workerとの別工程で検証する。

archiveの上限は512 response、2 MiB/body、64 MiB/body合計、64 KiB/metadata。
これは継承証拠を含む**保存済み入力の上限**であって、新規GETの許可ではない。
Bの実workerでは別承認でURL/GET上限、TLS/redirect/retry/rate、親worker/cleanup期限を固定する。
06:45〜07:00の間に取得・解析・永続化を完了できなければHOLD。全体deadlineの無条件延長はしない。

## Immutable providerと週末backendの接続点

`Provider`はWorkspace、明示Reference、金曜、SHA固定の予約を入力とする。
初回freezeでreceipt・raw・metadata・snapshot・publication・全fixtureを検証する。
`checkpoint("before_prediction")`と`checkpoint("before_save")`で同じ検証をやり直し、
新しい読取り専用のsource値、同じsource snapshot ID、receipt SHA、実freeze/checkpoint UTCを返す。
検証の終了時点でも時計を再確認する。保存前には明示的な`generated_at_utc`を要求し、
予測前検証完了≤生成UTC≤保存前検証完了<全kickoffを検査する。生成UTCを推定せず、
合成テストでは仮の値だけを渡す。本工程で予測生成callbackを呼ぶことはない。
source snapshot IDはReference、対象集合、予約、実freeze、policy/scopeを含む。
全targetへ同じsourceを渡すためのhandoffであり、Elo特徴量を計算したsnapshot IDとは区別する。

`latest.json`は読まない。通常collectorが後続revisionを公開しても選択sourceは変化しない。
後続の既知日程を`applicability`として明示すると、対象追加・日付/kickoff/identity等の差異はHOLD。
その新しいrevisionを特徴量入力へ代入しない。source値を受け取った側がDataFrameを変更しても、
次checkpointは封印原本を再読込みする。失敗したsessionの再開・checkpoint順序違反・二重使用は拒否。

新source laneは専用lockで所有する。競合owner/残存lockを回収せず、同じlaneの並列publisherを拒否する。
実runtimeは入力/出力として受け付けず、通常updaterの所有領域と共有して書かない。
実際の07:00処理と同時稼働したWindows所有権/ACL/TOCTOU/power-loss安全性を認定したものではない。

将来の結合位置は、週末処理のsource解決を朝collectorから分離した後の**予測直前**と
**保存直前**である。日別処理は従来のcollector経路を維持する。
現在の`_run_update`は引き続きcollectorを先に呼び、Phase 1 backendも既存pointer検査を持つ。
それらへproviderを無条件に差し込む修正はしていない。Elo/manifestへreceiptとsource snapshotを
結合するbackendアダプターは次工程の対象。モデル実行や保存のcallbackも今回は呼ばない。

## 検証・保護・本番前の残件

合成検証は金1・土4・日4・月1の全10target、前夜再利用、未完了履歴、06:45/06:59、
07:00境界/微小超過、公開後の遅延、receipt欠落/改変、部分公開、raw/TeamMaster/manifest変更、
継承結果原本、latest更新、既知の日程変更、再hashした結果矛盾、予約期限、時計逆行/累積drift、
同時owner競合、書込み/readback故障、無断再実行・session再開拒否を含む。
日別、v2 reader、feed/server、binding、公式parser/publisherの既存合成回帰も実行した。
最終結果は**576 PASS（新規source 63件＋既存回帰513件）、1 skip、failure/error 0**、
warnings-as-errors。skipは配布されないローカル公式原本を必要とする既存テスト1件である。
実行結果・JUnit・コード/入力SHA・保護件数は[validation](WEEKEND_BATCH_PHASE3_VALIDATION.json)に記録する。
実原本を必要とする任意の旧テストのskipは、合成PASSや実原本検証へ数えない。

保護baselineは開始時に新規保存し、モデルseal/53 payload、運用タスクXML/状態、実runtimeと
既保存19予測、既存worktree/branch、公式source/publication、Desktopを終了時にも照合する。
10/24の5件は再計算せず、10/25の5件は未保存のまま。07:00/22:00の実行・修復・変更は0。

本番前に必要な別承認と検証：

1. 本番用のsource所有領域・ACL・外部時刻監視、実worker/有限通信/receipt/crash復旧の結合。
2. Aの当夜receipt生成、またはBの事前取得を実施するための取得対象・通信許可。実タスク変更も別承認。
3. 本番版manifest/backendへのreceipt結合、source registryへの参照維持、Windows永続化・競合検証。
4. 全未保存の将来週末を期限内に予約し、その時点の完全性を再確認すること。
5. 実モデル結合・初回予測・全件保存・feed/UI更新の明示承認。現在の部分既保存週末は対象外。

新規公式GET/収集、本番model load/fit/推論/評価、予測保存/変更、feed更新、
本番予約、タスク実行/変更、Desktop変更はいずれも0。Gitの通常pushのみ実施する。
