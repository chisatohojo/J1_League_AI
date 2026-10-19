# 研究専用保存経路・障害復旧設計

状態: **DESIGN_AND_SYNTHETIC_CONTRACT_ONLY**。real writer／実登録／実T0は未実装・未設定。既存の `nn_v2_paired_prediction_v1` は変更しない。

## 独立経路と事前確認

候補は `%LOCALAPPDATA%/J1AI/NNResearch-v2-future-20261020-01`。今回このディレクトリは作成していない。参照はNN v2封印モデル、承認済み公式revision、固定した歴史入力へ限定し、運用runtime／モデル／予測batchを出力先にしない。

将来create-newする際は、親の実path、Owner・書込み権限、reparse、Volume／File IDを再検証する。root・lock・key・台帳・receiptの所有関係と作成時identityを保存し、読戻す。既存候補や不明な所有者・ACL・リンクはHOLD。個人ブラウザーprofileや運用タスクの状態は操作しない。sourceとartifactは読み取り専用にする。

```text
store.json                    # 外部SHAでpinするstudy/role/path契約
enrollment/identity.json       # 実T0、20節200のidentity（今回は未作成）
bindings/                     # ID/kickoff pending・公式改訂の不変version
artifact-reference.json       # 封印済み基準・NN・Scaler・schema SHA
source-witness/               # raw、metadata、取得時刻、revision、訂正lineage
attempts/                     # create-new、失敗でも保持
keys/                         # (model_version, namespace, official_id)の排他予約
staging/                      # 未公開の完全batch
commits/                      # 2モデル一体の不変paired records＋manifest
ledger/                       # 連番・前entry SHAを持つ追記専用台帳
receipts/                     # 公開成功receipt（外部SHA pin）
diagnostics/                  # 部分障害・期限切れ・復旧判断
```

上記は将来の設計。今回の実装 `nn_v2_synthetic_store` は架空study／fixtureのみを受け付け、real originを拒否するreference transactionである。実データへ切り替えるスイッチはない。

## Paired batchの契約

1. source witnessのraw／metadata SHA、取得時刻、fixture identity、公式revision、結果完全性を確認する。NN専用EloとFormは同一のstrictly-prior結果集合から作る。モデルとScalerはfitせず、封印SHAに一致するものだけを使用する。
2. 同一日付の登録対象全試合について、scheduled、公式ID／kickoff確定、未予測、対象fixture集合完全一致を確認する。将来のpendingや延期を無視して件数を減らさない。
3. 基準と残差は一つのpaired-v1 recordへ保存する。全recordでstudy／モデル版／source witness／revision／cutoff／取得時刻／artifact SHA／run IDを一致させる。片側の成功だけでは公開しない。
4. 単一writer lockをcreate-newし、attemptと各公式identity keyを排他的に予約する。異なるrun IDでも同じkeyは再保存しない。既存lock／途中entry／attempt／予約keyは停止条件。処理名やPIDだけでlockを回収しない。
5. 新しいstagingへ全record、source witness、manifestを書き、flush／fsync／readbackする。二つの確率列を含む全payloadの読戻しが最早kickoffより前であることを外側の実時計で確認する。
6. 不変commitディレクトリへrenameし、前entry SHA付きledgerをcreate-new／fsync／readbackする。再度実時計を確認する。clock逆行・締切と同時・締切後は失敗とする。
7. payload／ledgerの読戻し成功時だけ、fsyncした成功receiptをrenameして公開する。**成功receiptだけを可視性の境界**とする。receiptの時刻はpayload／ledgerの読戻しを表し、receipt自身のflush完了時刻と偽装して混同しない。外側processの終了と成功receiptを突合する。
8. readerは外部pinしたreceipt SHAからstore header、ledger chain、commit manifest、source witness、全payload SHAを検証する。成功receiptのないstage／孤立ledger／壊れたreceiptは採用しない。直前の正常batchを保持する。

OSの複数ファイルを一度に原子的に変更できるとは主張しない。可視性を最後のreceiptに集約し、途中のファイルが残っても成功とみなさない。実環境のfilesystem／電源断耐性・外側の実時計／receipt監督は、real writer導入前に検証が必要。合成用の注入clockをlive predictorへ渡す機能は作らない。

## Pending・日程変更

現行登録v1は全200件のkickoffを必須としており、未公表100件を登録できない。00:00で代替したり、検査用planから未公表試合を落としたりしない。

次の仕様候補は、T0で固定するfixture identity・節集合と、後から証拠付きで解決するID／kickoff bindingを分けること。実T0では全380日程を参照し、最初の全試合未開始節から連続20節を選ぶ。日付だけの未開始証拠と実kickoffを区別する。足りなければ計画HOLDで、期間を後から延長しない。

固定identityのhome／away／節／fixture_key／namespaceは勝手に変えない。IDのpending解決やkickoff変更は旧新公式revision・raw SHA・取得時刻・不変identityの照合を要求し、不明ならHOLD。延期試合を除外・交換しない。新しい登録contextを受けるvalidatorの設計承認が必要だが、paired-v1 recordの確定ID、同一情報、完全batch、開始前保存の条件は維持する。

## 復旧・rollback

自動再試行0。失敗attempt、key予約、stage、診断、孤立ledgerは削除せず保持する。成功receiptのない候補をreaderへ渡さない。lock解除は所有token一致を確認して自分の正常終了処理が行う。未知の残存lockをPID照合だけで削除しない。

次のwriterは不明な孤立ledgerや未完了receiptがあれば停止する。人による調査では入力／モデル／source／manifest／外側exit／時計証跡を検査し、「未保存」「payload保存済みだが未公開」「正式commit済み」を区別する。締切後の新しい予測生成や保存成功への変換は行わない。

切り戻しはconsumerが参照する最後の正常な外部receipt pinを維持する。過去commit、台帳entry、確率、生成時刻は上書き・削除しない。新しい診断・復旧判断を追記し、運用Champion Aのpublication／予測／タスクへ巻き戻しを伝播させない。同じ公式keyの再生成や再予約が必要なら別の承認を要し、期限後の補完は認めない。

## 研究sourceの取得案（今回は実行しない）

将来予測ごとに、最後の承認済みrevisionを不変の研究用source witnessとしてpinする。取得時刻と生成時刻を実UTC/JSTで記録し、公式の未立証な公開時刻を推測しない。訂正は新しいversionで保持する。

保存sourceが古い場合は、別承認の研究用collectorで、既存の公式一覧・実リンク抽出・strict parserと通信上限を再利用する。明示した大会・日付window・ページ数・総時間・timeoutを制限し、再試行0、出力は研究source領域のみ。運用タスクを強制実行せず、production publicationを更新しない。既知実IDからの公式参照以外に連番URLを作らない。

4件の証拠参照は、既存rawとmetadataのSHA／URL／取得時刻／canonical／日付／対戦／終了状態を再照合し、研究側の明示bindingとして封印する案。元publicationを修正したことにはしない。2026時刻例外とfuture Elo/Form adapterが整うまで予測へ利用しない。
