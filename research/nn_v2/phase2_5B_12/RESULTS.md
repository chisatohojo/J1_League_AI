# Phase 2.5B-12 二段階証拠取得方式のオフライン実装・検証

判定：**TWO_STAGE_OFFLINE_VERIFIED_RESEARCH_ONLY**。保存済み116件は **Stage A封印116件、Stage B 116 PASS / 0 HOLD** で、既存v5の全semantic fieldと一致した。過去4件は当時の旧契約による正式HOLDを完全再現し、隔離確定後に架空の正常ページ各1件だけを後続処理できた。現在のv5では4件ともPASSであり、旧HOLDを現在の未解決件数へ加えていない。[互換性](compatibility-summary.json)、[隔離再現](historical-quarantine-summary.json)。

開始branchは`feature/nn-research-v1`、HEAD `62e869523addfc6d619cb552660a7b63c8cf8331`、study `nn_v2_residual_20261020_01`。モデルは`TRAINED_AND_SEALED_RESEARCH_ONLY`。モデルseal・53 payload、旧原本・parser・v2〜v5・4個別rule、正式停止記録、固定入力、172件の台帳・完全計画を開始前と終了時に照合した。[入力SHA](input-sha256.json)。

研究用実装は実通信の入口・有効化スイッチ・CLI・実worker・通信permit・運用collector・タスク・予測器との接続を持たない。既存のstrict parserと個別規則による解析だけを呼び、共通備考分類候補はimport・呼出ししていない。[実装](offline_two_stage.py)、[境界監査](boundary-verification.json)。

Stage AではHTTP・raw/metadata/request・SHA・実UTC・公式URL/ID・fixture・revisionを照合し、strict parserで大会・年度・節・TeamMaster・日時・90分結果・PK/延長分離・最終詳細状態を確認する。不整合や事実を検証できない未知HTMLはSTOP。原本bundleを新規保存・fsync・readback・sealした後だけ、Stage Bが封印bytesを再読して審査する。未知備考・未分類時刻注記だけが残る場合はHOLDで隔離し、identity/結果/SHA等の異常を隔離対象として隠さない。[契約](CONTRACT.md)、[状態遷移](STATE_TRANSITIONS.md)。

隔離packetはidentity・URL/ID・namespace・source revision・元原本SHA・実取得UTC・Stage A/Bの結果と参照・停止理由・未確認分類・履歴admission禁止を保持する。packet自体のSHAはseal/receiptへ分離した。全ファイルのexclusive-create・flush・file fsync・readback・SHA、sealとreceiptの再照合が終わるまで、次の入力へ進まない。部分source/quarantineやreceipt欠落を無視する集計、同じrunの二重実行・停止後再開、隔離packetの除外による全件PASSを拒否する。

合成・関連回帰は **696 PASS、fail/error/skip 0、warnings-as-errors**。新規79件と既存617件で、未知1件＋後続正常11件、複数未知、未分類時刻注記、未知後の403/429・identity不整合、SHA・revision・HTTP/TLS/timeout/redirect・本文/GET/deadline/rateの異常、fsync/readback失敗、部分packet保存中とreceipt前の異常終了、二重実行、再利用、誤集計、履歴admission拒否を検証した。仮想clockは合成入力だけで使用し、公式原本や運用側へ注入していない。[テスト結果](synthetic-test-results.json)。

初期テストでPASSのreasonがnullの場合の例外を検出し修正した。また、Stage A完了数とStage B審査数を別管理にし、GET回数はbooleanを除く整数1だけを受理するようにした。修正後の最終コードで116件と過去4件を新しい出力先へ再生し、全テストを実行した。過去契約を選ぶrunnerの定数参照ミスも別版で修正し、完了済み出力と初期JUnitは上書きせず保存した。旧研究成果物・停止記録を修正して合格にしたものではない。

取得状態と審査状態は別field。詳細PASSでも`timing_evidence_status=HOLD_B_C_D`、`history_admission_status=false`。隔離中の試合を除外して完全履歴を作る機能もなく、履歴admission要求は常に拒否する。最終詳細Aの検証は、Bの実際の開始/中断/再開/完了/結果利用可能時刻、Cの当初日程・変更告知、Dの予測cutoffまでの取得証明を代替しない。

元288件＝保存116件＋未取得172件、URL/ID重複・集合重複0。未取得台帳SHAと完全計画SHAは指定値に一致し、計画変更なし。172件への通信も、新規通信permit作成も0。[集合照合](fixed-set-verification.json)。旧正式結果B4・B6・B8・B10のPASS/HOLD/未取得数と全原本は不変。[旧記録](old-formal-records-verification.json)。

保護対象15,014ファイルとモデル53 payloadは不変。今回の運用出力変化0・タスク重複なし。過去の未帰属11件と、独立確認済み07:00タスク由来の10件を区別し、根拠なしに帰属を変更していない。07:00/22:00タスク定義、運用runtime、保存予測、main、他worktreeも不変。[保護監査](protection-verification.json)。

再生原本、Stage A/B、隔離packet・seal・receipt、旧正式記録コピー、固定コード・rule、入力/出力SHA台帳を別ドライブへbackupした。ZIP CRC、全payload SHA、独立展開、独立読戻しは一致。[backup検証](backup-verification.json)。Raw・metadata・実名・個人パス・個別履歴・学習済みモデルはGitへ追加していない。

今回の合格はオフライン処理の成立のみ。実HTTP workerの所有権・ACL・path競合・電源断/crash復旧・receipt統合・通信制限やネットワークでの安全性は別工程で検証し、新しい取得許可が必要。今回のコードへ実通信を接続していない。[次工程](next-stage.json)。

**HISTORY / PREDICTION：HOLD**。ネットワーク取得0、通信permit0、実fit0、性能評価0、実確率計算0、T0登録0、対象登録0、将来予測保存0。Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
