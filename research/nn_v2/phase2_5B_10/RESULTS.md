# Phase 2.5B-10 公式詳細証拠の限定取得

判定：**HOLD_BOUNDED_EVIDENCE_ACQUISITION**。新規 **37 GET / 36 PASS / 1 HOLD / 172 未取得**。第4バッチの1件目に未登録の監督退場注記を検出し、全体は規定の停止条件で終了した。既知のスタッフ警告へ一般化せず、独立オフラインレビューへ切り出す。未開始バッチへは進んでいない。 自動再開・再取得・規則のその場変更は0。

累計 **116 / 288件取得、独立解析115 PASS**。既取得79件は通信前後にv4契約で再解析し、全semantic fieldが不変だった。過去の正式な停止記録は変更していない。詳細なidentity・備考原文・個人情報・URL台帳はローカル証拠に保持し、ここには集計とSHAのみを保存する。

開始branchは`feature/nn-research-v1`、HEAD `00e63efcff4768319ee0dcd5a697e961f4d04f17`、study `nn_v2_residual_20261020_01`、モデル`TRAINED_AND_SEALED_RESEARCH_ONLY`。指定された209件の台帳・完全計画SHA、元288件との差集合、URL/ID重複0、保存済み公式実リンク、固定source revisionを照合済み。

| バッチ | 計画 | 試行 | PASS | HOLD | 未試行 | 状態 |
|---|---:|---:|---:|---:|---:|---|
| 1 | 12 | 12 | 12 | 0 | 0 | PASS |
| 2 | 12 | 12 | 12 | 0 | 0 | PASS |
| 3 | 12 | 12 | 12 | 0 | 0 | PASS |
| 4 | 12 | 1 | 0 | 1 | 11 | HOLD |
| 5 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 6 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 7 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 8 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 9 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 10 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 11 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 12 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 13 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 14 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 15 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 16 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 17 | 12 | 0 | 0 | 0 | 12 | NOT_STARTED_AFTER_GLOBAL_STOP |
| 18 | 5 | 0 | 0 | 0 | 5 | NOT_STARTED_AFTER_GLOBAL_STOP |

外側processはexit 0、timeoutなし。新規37件はすべてHTTP 200。停止ページもidentity・日時・90分結果のstrict照合に合格し、単一の備考paragraphで個別adapterがHOLDした。時刻注記は検出されていないが、物理的中断がなかったことや警告コードの意味を推測していない。原本とmetadata/requestのSHA、GET回数、実UTC順序、snapshot・解析結果、各バッチsealと外側exitを独立照合した。本文総量は **4,564,860 bytes**、観測した通信完了から次開始までの最小間隔は **5.18904秒**。既取得79件、robots、日程・告知ページへの研究GETは0。取得時のexecutor/launcher/permitは封印状態と一致し、共通分類器はimport・接続していない。[通信receipt](communication-receipt.json)、[実装SHA](implementation-sha256.json)。

合成・関連回帰テストは **517 PASS、fail/error/skip 0、warnings-as-errors**。新executor54件と既存463件で、正常209件・最終5件、途中/最終HOLD、バッチ境界のレート制限、timeout/403/429、二重実行・旧permit拒否、改変・領域外書込み・モデルdeserialize拒否、個別review-ruleの限定適用を検証した。[テスト結果](synthetic-test-results.json)。

開始監査scriptの照合先ディレクトリ指定ミスは通信前に修正した。正しい原本同士の照合では不一致0であり、固定入力の改変ではなかった。修正前後の事実はローカル監査に保存し、実取得コードの封印・初回GETとは分離した。

モデルsealと53 payload、固定入力・旧原本・保存予測・運用コード・タスク定義・main・他worktreeをSHA再照合した。今回の運用出力差分は0、タスク実行との重複もない。過去の未帰属11件と、前工程で独立に確認した07:00タスクの可変出力10件は区別して保持した。通常更新・研究変更のいずれにも根拠なしで一括帰属していない。[保護監査](protection-verification.json)。

取得成功分とHOLD原本、既取得79件の原本コピー、全解析、UTC・SHA台帳、コード・permit・停止receiptを別ドライブへbackupした。ZIP CRC、全entry SHA、独立展開、独立読戻しは一致。[backup検証](backup-verification.json)。Raw、metadata、個人パス、氏名、個別履歴、学習済みartifactはGitへ追加していない。

詳細Aの取得・解析と、Bの実際の開始/中断/再開/完了/結果反映時刻、Cの当初日程・変更告知、Dの予測時点までの取得証明は別判定。全288件のB〜DはHOLDのままであり、今回の取得時刻を過去へ遡らせていない。[証拠集計](source-witness-summary.json)、[次工程](next-evidence-plan.json)。

**HISTORY / PREDICTION：HOLD**。実fit・性能評価・実確率計算・T0登録・対象登録・将来予測保存はすべて0。Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
