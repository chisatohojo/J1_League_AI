# Phase 2.5B-8 残り245件の限定公式詳細取得

判定は **HOLD_BOUNDED_EVIDENCE_ACQUISITION**。新規 **36 GET / 全36件HTTP 200 / 35 PASS / 1 HOLD / 209未取得**。第3バッチ12件目に未登録のGKコーチ警告備考を検出し、全体を正常停止した。規則のその場変更・再取得・自動再開は0。

開始branchは`feature/nn-research-v1`、HEADは`7a793a5908b0d32f73388d3d7f3794435bfe056e`。Studyは`nn_v2_residual_20261020_01`、モデルは`TRAINED_AND_SEALED_RESEARCH_ONLY`。モデルsealと53 payload、固定入力、43件の原本・SHA・seal・解析結果を照合した。43件は新executorの読取り専用経路でも再解析し、全semantic field不変の43 PASS。

固定245 URLは、元288候補から43件を除く差集合と一致し、重複・ID衝突・既取得との重複は0。保存済み公式一覧の実リンク、元sourceの大会・年度・節・TeamMaster・日時・90分結果を全件照合した。未取得台帳SHAと完全計画SHAは指定値に一致。運用側の新revisionを研究入力へ差し替えていない。

| バッチ | 計画 | GET | PASS | HOLD | 未取得 |
|---|---:|---:|---:|---:|---:|
| 1 | 12 | 12 | 12 | 0 | 0 |
| 2 | 12 | 12 | 12 | 0 | 0 |
| 3 | 12 | 12 | 11 | 1 | 0 |
| 4〜20 | 204 | 0 | 0 | 0 | 204 |
| 21 | 5 | 0 | 0 | 0 | 5 |
| 合計 | 245 | 36 | 35 | 1 | 209 |

バッチ4〜21の18バッチは`NOT_STARTED_AFTER_GLOBAL_STOP`。停止ページはstrict parserの公式identity・日時・90分結果等に合格したが、唯一の備考paragraphに未登録の役割表記があり、adapterが`UNKNOWN_NON_TIMING_REMARK_REQUIRES_REVIEW`でHOLDとした。時刻注記は検出されていないが、その不在だけで既知の非時刻注記へ採用していない。原本、raw/metadata/request SHA、取得UTC、A11全文・構造・位置と停止経路をローカルregistryへ保存した。物理的中断がなかったとは立証しない。

累計は **79 / 288件取得、独立解析78 PASS / 1 HOLD、209未取得**。新規全36ページは保存済み結果とオフライン再解析が一致。既存43件は取得後にも全件不変を確認した。Phase 2.5B-6の正式3 PASS / 1 HOLD / 245未取得、Phase 2.5B-4の正式26 PASS / 1 HOLD / 249未取得を変更していない。

外側processはexit0、timeoutなしでHOLD結果を返した。request開始・取得完了・snapshot保存・解析完了の実UTC順序、通信完了から次requestまでの最小間隔 **5.197060秒**、全本文 **4,449,499 bytes**、全36 URLの一度限りのGET、TLS、SHA、permit・executor bindingを照合した。保存済みrobotsを使用し、追加告知・日程・robots・既取得43件への研究GETは0。[通信receipt](communication-receipt.json)。

合成・関連回帰テストは **403 PASS / skip0 / warnings-as-errors**。新executor47件と既存356件。245件全正常、最終5件、バッチ境界、途中/最終HOLD、timeout/403/429、rate制限、旧permit・二重実行拒否、原文/identity/SHAの改変、既存規則の適用範囲、実Windows起動ガードと領域外書込み拒否を検証した。初期版の通信前不具合と失効permitは、実行時の最終版と区別して封印した。[契約](PROTOCOL.md)、[実装SHA](implementation-sha256.json)。

開始監査は既存07:00タスクと重なった。タスクXML・スケジュール・コードを変更せず、前後の実行状態、終了時刻、公式revisionのmanifestと全export SHA、snapshot source/raw/metadata、discovery receipt、preview generationを独立照合した。開始時点からの既知可変出力10件と追加タスク成果物60件を、この実行に結び付けて記録した。既知可変出力以外の既存保護対象のSHA不一致は0、タスク終了後の運用出力は研究取得後も不変。研究executorは領域外書込みと親process通信を拒否する。過去工程から引き継いだ11件の差分については、通常更新とも研究による変更とも一括認定していない。

保護台帳 **11,790ファイル**を照合した。モデル53 payload、旧43 snapshot、旧parser/rule/executor/permit、保存予測、運用runtimeコード、main、他worktree2件、Windowsタスク2件は保全。可変出力とタスク成果物の個別パス・前後SHA・実行証跡はローカル保存。[保護監査](protection-verification.json)。既存タスクによる独立通信は研究permitのGETに含めず、研究からタスクを呼び出していない。

新規36ページとHOLD証拠、既存43件の原本コピー、全解析結果、permit/コード/入力/SHA台帳、209件の未取得台帳を別ドライブへbackupした。ZIP CRC、全entry SHA、独立展開後SHAは一致。[backup検証](backup-verification.json)。Raw、metadata、個別履歴、個人パス、学習済みartifactはGitへ追加していない。

次工程は、保存済みの未登録備考の独立オフラインレビュー。現在のpermitは停止済みであり、209件の取得再開には別承認と新しい固定permitが必要。Aの詳細解析と、Bの開始/中断/再開/完了/結果利用可能時刻、Cの当初日程・変更告知、Dの予測時点の取得証明は別判定とする。対象別の不足証拠を保存し、実結果eventのadmissionと将来予測へは進まない。

**HISTORY / PREDICTION：HOLD**。実fit0、性能評価0、実確率計算0、T0登録0、対象登録0、将来予測保存0。Phase A：BLOCKED。Phase B：NOT_AUTHORIZED。
