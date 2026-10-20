# Phase 2.5B-4 段階取得の停止結果

判定は **HOLD_BOUNDED_EVIDENCE_ACQUISITION**（2026-10-20 JST）。第3バッチの3件目で、パイロットの既知形式に含まれない「通訳への警告」の備考を検出し、全体を停止した。**27 GET / HTTP 200が27件 / 26 PASS / 1 HOLD / 未取得249件**。停止後の取得・retry・自動再開は0。

開始branchは `feature/nn-research-v1`、HEADは `31a0de9c6e6d91728f8507a7097225e828321938`、作業ツリーclean。Study `nn_v2_residual_20261020_01`、モデル `TRAINED_AND_SEALED_RESEARCH_ONLY`。既存モデルの53 payload、研究入力、実装SHA、保存12件、保護対象10,227ファイルを照合し、不一致0で開始した。

## 固定した対象と実行結果

元の不足候補288件から封印済み12件を除き、**276件（百年構想183 / 2026/27 J1 93）**を固定した。保存済み公式一覧の実anchorで全276 URLを照合し、URL重複・ID衝突0。TeamMaster対戦、大会・年度・節の全文見出し、日時、規定時間結果、source SHAを通信前に固定した。系列・日付・数値IDの安定順序で12件ずつ23バッチへ分割した。

| バッチ | 計画件数 | GET | PASS | HOLD | 未取得 |
|---|---:|---:|---:|---:|---:|
| 1 | 12 | 12 | 12 | 0 | 0 |
| 2 | 12 | 12 | 12 | 0 | 0 |
| 3 | 12 | 3 | 2 | 1 | 9 |
| 4〜23 | 240 | 0 | 0 | 0 | 240 |
| 合計 | 276 | 27 | 26 | 1 | 249 |

23バッチ全ての状態を記録した。取得済みの3バッチはそれぞれ新規ディレクトリへ保存・封印し、残り20バッチは `NOT_STARTED_AFTER_GLOBAL_STOP`。元のsnapshotへ追記していない。既存12件と今回27件は重複0で、元の288件の範囲内にある。既存12 URLへの再アクセス0、新しい対象追加0。[batch-execution-summary.json](batch-execution-summary.json) と [set-reconciliation.json](set-reconciliation.json) を参照。

## 停止原因と解析

27件ともHTTP 200。公式ID、URL、TeamMaster両クラブ、年度付き大会見出し、日付・kickoff、規定時間スコアは既存strict parserと保存済みsourceで一致した。26件は既知の空欄構造だった。残る1件の備考は警告の対象役割が「通訳」で、パイロットで確認済みの「監督への警告」等の既知形式へ無断で拡張できないため、上位の備考契約が `UNKNOWN_FORMAT` としてHOLDした。

停止コードは `UNKNOWN_NON_TIMING_REMARK_REQUIRES_REVIEW`。元のstrict parserが照合できたidentity・結果と、新しい備考形式の採用可否は別に記録した。この備考から中断・再開を示す時刻シグナルは検出されておらず、新しい中断例外が立証されたとは扱わない。生の備考、対象ID、raw/metadata SHA、取得時刻、停止receiptはローカルに保持する。取得実装・parser・allowlistを停止後に変更していない。

PASS26件ではPKあり11ページのPK得点を90分結果と分離し、延長は0。HOLDしたページもrawと解析を保持した。未取得249件について例外の有無を推定しない。

未解決の取得対象は **250件＝未取得249＋備考HOLD1**。ネットワーク障害0、identity/結果矛盾0、未解決の実装不具合0、未採用の備考形式1を区別する。次の調査は、保存済み停止ページの全文と備考構造・役割表記をオフラインでレビューし、非時刻注記の契約を拡張する妥当性とテストを確認すること。今回のHOLDを後からPASSへ書き換えない。残り249 URLの再開は新しい独立承認が必要であり、この工程では実行しない。

## 通信・時刻監査

10月20日18:46 JSTに取得したrobots証拠が24時間のローカル鮮度条件内にあり、各バッチ前にオフラインで再検証した。新しいrobots GETは0、告知・日程・index GETも0。

HTTPS・証明書/hostname検証、各URL1 GET、timeout10秒と親worker deadline10秒、本文2 MiB/件、全体552 MiB、retry0、redirect0、並列0を維持した。全体processには4500秒の有限timeoutを設け、実行は約142.4秒で停止した。本文合計3,356,435 bytes、実測最小通信間隔 **5.178071秒**。バッチ境界も含め5秒以上を確認した。[communication-receipt.json](communication-receipt.json) に集計とseal SHAを保存した。

request開始、response完了、snapshot保存、監査完了の実UTCを別fieldで保存し、順序を検証した。取得日は2026年10月20日で、過去の試合当日に取得済みだったとは主張しない。

## A〜Dの証拠と次工程

| 証拠項目 | 今回の結論 |
|---|---|
| A 最終詳細のidentity・結果・備考 | 26 PASS / 1備考HOLD / 249未取得 |
| B 開始・中断・再開・完了と結果反映の実時刻 | 最終ページのkickoff表記と、完全な物理時系列・公開境界は区別しHOLD |
| C 当初日程と変更告知の来歴 | 今回の276件は未立証でHOLD |
| D 予測時点までの取得済み証明 | 276件とも今回の取得で過去へ遡って立証できずHOLD |

対象ID別の必要証拠をローカル `A-B-C-D-evidence-audit.json` に保存した。必要資料は当初日程の公開・取得時刻、identityに対応する変更・延期・再開告知、最終完了境界、指定した予測時点までの取得証明。前工程で保存した公式日程・お知らせindex候補2件を参照するが、直接の告知資料や必要取得件数は未確定。追加アクセスは行っていない。[next-evidence-plan.json](next-evidence-plan.json) を参照。

**HISTORY / PREDICTIONはHOLD**。詳細取得の完了判定にも未到達であり、結果イベントのadmission、adapterのREADY化、予測実行へ進まない。

## テスト・保護・保存

通信前 **215 PASS**。全276件の模擬成功、バッチ境界の間隔、429/timeout/未知注記、第2バッチでの失敗による全体停止、二重実行拒否、上限・host・TLS・SHA・保護sourceへの書込み拒否を検証した。停止後は未確認の役割表記と既知/未知混在の拒否を追加し、最終 **217 PASS / skip0**。テスト中の通信0、warnings-as-errors。[synthetic-test-results.json](synthetic-test-results.json) を参照。

保護対象10,227ファイルのSHA不一致0。NN v1/v2、Champion A、予測14件・再現98件、公式publication、運用runtime、Windowsタスク2件、main、他worktree2件は不変。研究モデル53 payloadも照合した。[protection-verification.json](protection-verification.json) に集計を保存した。

27ページのraw、metadata、request/response、解析、バッチpreflight/receipt/seal、全276 URL台帳、個別不足証拠、コード、テスト、SHAをローカル研究領域へ保存した。別ドライブの新規ZIPをCRC・全entry SHA・独立展開後SHAで検証し、公開集計も別途コピーして読み戻す。[backup-verification.json](backup-verification.json)、[local-evidence-index.json](local-evidence-index.json)、[SHA256-MANIFEST.json](SHA256-MANIFEST.json) を参照。GitHubへは集計・仕様・SHA・テストだけを追加し、raw、metadata、個別履歴、個人環境パス、学習済みartifactは追加しない。

実fit **0**、性能評価 **0**、実試合確率計算 **0**、T0登録 **0**、対象登録 **0**、将来予測保存 **0**。

**Phase A: BLOCKED / Phase B: NOT_AUTHORIZED。**
