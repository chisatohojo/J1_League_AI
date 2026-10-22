# 週末一括予測 Phase 4：オフライン結合検証

基準commit：`4ca8a343582099ca5f7164a16d318420ce5ed9c7`。
専用branch：`feature/weekend-e2e-integration`。
Scopeは引き続き`SYNTHETIC_ONLY`。本番CLIの有効化経路は追加していない。
最終判定・テスト件数・各SHAは[検証台帳](WEEKEND_BATCH_PHASE4_VALIDATION.json)に記録する。

最終判定：`WEEKEND_BATCH_E2E_OFFLINE_VERIFIED`。
最終コード状態で**613 PASS / 1 skip / 0 failure / 0 error**（warnings-as-errors）。
新規E2Eは37件、関連回帰のPASSは576件。skipは配布されていないローカル公式原本を必要とする
既存の`test_jleague_ongoing_source.py`の1件であり、実原本検証をPASSと数えていない。
初期失敗、修正後13 PASS、603 PASS、追加検査後611 PASSの証跡も上書きせず区別して保持した。

変更ファイルは次の8件。

- `src/modeling/weekend_integration.py`：receipt付き結合adapterと派生版reader。
- `src/modeling/weekend_batch.py`：結合checkpoint、保存境界の再検証、共通semantic validator。
- `src/modeling/weekend_source.py`：埋込みreceipt検証の分離とrequest結合検査。
- `scripts/update_champion_dashboard.py`：合成専用の固定source分岐、予約保護、保存値からのfeed再投影。
- `tests/test_weekend_integration.py`：新規37件の合成E2E・障害試験。
- `tests/test_weekend_batch.py`：予約を無視する競合writerの既存試験を維持。
- `docs/WEEKEND_BATCH_PHASE4.md`：契約・結果・未実証事項。
- `docs/WEEKEND_BATCH_PHASE4_VALIDATION.json`：JUnit集計、SHA、保護監査、禁止操作0の記録。

## 接続方式

`ReceiptBoundBackend`はPhase 1の`OfflineWeekendBackend`を継承し、Phase 3の明示的な
`Workspace`と`Reference`を要求する。両方の専用一時workspace、mock estimator/scaler、
合成入力witnessが必要で、本番rootを指定するだけでは起動できない。

処理順序は次のとおり。

1. 水曜07:00 JSTより前に、金曜〜月曜のfixture集合を予約する。
2. 合成公式原本から前夜22:00のrevisionを公開し、receipt、seal、Referenceを封印する。
3. updaterの週末分岐は通常collectorを呼ばず、選択済みReferenceだけを解決する。
4. Providerで実freeze時刻を観測し、予約・全履歴・sourceの証拠を検証する。
5. 共通Eloを一度だけreplayし、全targetの`elo_diff = home_rating - away_rating`を固定する。
6. `before_prediction` checkpoint、snapshot不変確認、全入力SHA、実時刻とkickoffを再検証する。
7. 既存Champion入力関数にmock scaler/estimatorを渡し、実際の合成生成UTCを記録する。
8. `before_save` checkpointへその生成UTCを渡し、receiptと日程の適用可能性を再確認する。
9. 全件をstagingで検証し、公開lock内で入力・source・staging全体・時刻を再照合してdirectory renameする。
10. 保存済みbatchをreaderで再読込みし、schema v1の`champion_home.json`へ投影する。

Eloは既存仕様の初期1500、K30、home advantage175、season resetなしを維持する。
金曜00:00前の履歴だけを使用し、全対象が未開始・scheduledであることを要求する。
土曜の結果を日曜の入力へ渡す処理はない。scalerのfitやモデルloaderも呼ばない。

## Sourceと時刻の境界

Referenceのrevision、receipt/seal全体SHA、原本・metadata・request UTC、公式manifest、
元snapshotと継承結果の証拠を実際に再読込みする。予約の全fixtureとsourceの全targetを照合し、
TeamMasterのSHAも固定する。入力は明示revisionであり、`latest`への自動差替えはしない。

runtimeの`latest`は、既知の日程・kickoff・typed identity・対象集合変更を拒否するためだけに読む。
処理時点より未来の観測は拒否する。新しいsourceの結果は共通Eloへ混ぜない。
保存後の自然なcompleted遷移は再予測を起こさず、予約・保存値・元identityを照合する。
週末外への改日程もHOLDする。

取得・publication・receipt確定は金曜07:00以下、source鮮度は同cutoffから24時間以内。
freezeは07:00以降、checkpoint・公開は設定上限（最大07:15）と全kickoffより前を要求する。
Providerのwall/monotonic検査と、予測前・生成・公開境界の時刻検査を維持する。
保存済みbatchの後日表示は元cutoffの証拠を検証し、現在時刻から24時間を超えたという理由で
再予測することはない。新規推論に対する期限・履歴完全性は解除していない。
ローカル時計から絶対的な時刻真正性を証明したとは扱わない。

## Manifestとreader互換性

従来の`champion-weekend-v2`は変更せず、証拠結合を追加した派生形式を
**`champion-weekend-v2-source-v1`**として明示する。保存先は`weekend-v2-source-<manifest SHA>`。
新形式を旧形式と偽って読ませるfallbackはない。

| ファイル | 契約 |
| --- | --- |
| `predictions.csv` / `bindings.csv` | 既存列・確率・生成UTC・公式fixture bindingを維持 |
| `snapshot.json` | 既存共通Elo・rating map SHA・対象・入力・コード・モデル識別子にsource bindingを追加 |
| `source-proof.json` | ReferenceとSHA、receipt、seal、両checkpoint、source snapshot ID、予約ID/SHA、Elo snapshot ID、入力特徴量SHA、出力CSV SHA |
| `manifest.json` | 版、全file SHA、元revision/manifest SHA、全件数、生成・commit UTC、完全性、COMMITTED、source binding SHA |

readerは正確な版・列集合・ファイル集合・ディレクトリ名・全SHAを検証し、埋込みreceiptの
時刻・request・seal・Reference・予約・特徴量・出力結合を確認する。その後、旧v2と共通の
semantic validatorで全確率・identity・fixture・snapshot・時刻規則を検証する。
既存の日別batchと旧v2も同じaggregate readerから読める。

保存batchだけのreaderは封印時の証拠表現を検証する。元rawが現在も存在することや
外部署名・絶対時刻まで再証明するものではない。推論・保存・公開直前のbackend検証では、
別途保存sourceの全原本を再解析する。両責務を混同しない。

古い運用readerは新形式を拒否する。rollback時も新batchを削除・降格・日別へ分割しない。
新readerを維持するか、明示的にHOLDして互換性を回復する。

## 日別処理・表示・障害時の扱い

通常の日別処理は従来どおりcollectorを使用する。保存済み週末予約を読み、対象期間を日別選択から
除外する。日別publisherも共通lock内で予約fixtureへの保存を拒否する。火〜木の対象は除外しない。
既存競合テストは、予約を無視する外部writerをprivate publisherで模擬するよう調整した。
公的な日別publisherによる予約拒否は別の結合テストで検証する。
22:00相当のevening分岐は適用可能性審査と保存値の表示だけを行い、推論しない。

公開前の故障・改変は可視予測0件。未完了attempt、staging、競合lockを自動回収・再開しない。
一度成功したbatchの再実行は同じ保存bytesを返し、Elo replay・推論を再実行しない。
保存後のfeedエラーではbatchを保持し、表示は最後の有効値を維持する。次の表示再投影も推論0。
feedはcanonical saved readerを通った値だけで構築し、receipt・rating map・合成scopeをUIへ漏らさない。

単一同一volumeのdirectory renameでbatchの可視性を切り替える。電源断後の永続性、
Windowsの全ACL/TOCTOU/実worker異常終了に対する保証をこの試験から主張しない。

## 検証範囲

新しいE2E試験は合成公式HTML・仮UTC・専用一時runtime・mock estimatorを使用する。
前夜source、金曜〜月曜10件、月またぎ、12月31日のsourceから1月1日のfreezeへの年またぎ、
後続source、土曜結果、日程変更、部分既保存、証拠改変、時計逆行・期限・競合・公開障害、
feed復旧、再読込み・二重推論防止を検証する。公式シーズンの許可範囲を拡張していない。
Phase 1〜3、日別updater、feed/server、binding、公式parser/publisherの回帰もwarnings-as-errorsで実行する。
既存serverの合成loopback試験を除き、公式通信・外部接続はテストfirewallで禁止する。
実原本が必要な旧任意テストのskipはPASSに加えない。中間失敗・修正後実行・最終実行を別記録とする。

## 保護と本番導入前の残件

開始時の新baselineに対し固定43,780ファイル、NN sealの53 payload、実保存19予測、
公式source/publication、運用runtime、Desktop、タスクXML/実行状態、main・UI・NN・他worktreeを照合する。
10/24の保存済み5件と10/25の未保存5件は変更しない。実モデルはhash/仕様の読取りだけでloadしない。
07:00/22:00タスクは実行・停止・修復・変更しない。

本番導入には次の独立した確認・承認が必要。

1. 実source workerの通信許可・有限期限・所有権・ACL・clock監視・receipt永続化・crash後の状態確認。
2. 実Champion/scalerと本番scopeの設計・契約検証。合成scope文字列の単純変更で代用しない。
3. 旧日別と新形式を扱うreaderの配備、保存先backup・rollbackと競合・電源断試験。
4. 全未保存の将来週末を水曜07:00前に予約する個別承認。既存部分保存週末には適用しない。
5. cutoff前source確保と全件予測・公開を行う別承認。失敗時のHOLDを維持する。
6. feed定時生成・運用UIへの反映・画面自動再読込みの別承認。

本工程の実公式GET、実model load/fit/推論/評価、実予測保存、実feed更新、実予約、
タスク実行/変更、Desktop変更、本番有効化はすべて0。
