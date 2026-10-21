# Phase 2.5B-15 二段階実HTTP拡張パイロット

判定：**TWO_STAGE_REAL_HTTP_EXPANDED_PILOT_VERIFIED_RESEARCH_ONLY**。固定先頭12 URLへの **12 GET / HTTP 200が12件 / Stage A封印12件 / Stage B 12 PASS・0 HOLD / 隔離0件**。累計131/288件取得、未取得157件。12件で実行終了し、他の詳細・日程・告知・indexには接続していない。実HTTP隔離は **REAL_HTTP_QUARANTINE_NOT_OBSERVED**。[通信](communication-summary.json)、[Stage状態](stage-summary.json)。

開始branch `feature/nn-research-v1`、HEAD `f57c1e646e755c058a11fb6fd9e789f80bf34b08`、study `nn_v2_residual_20261020_01`。モデルは`TRAINED_AND_SEALED_RESEARCH_ONLY`。model sealと全53 payload、原本、実装、過去正式停止記録、固定入力と27,494保護ファイルのSHAを照合した。169件台帳SHA・計画SHAは指示値に一致。元288件から既取得119件を除いた集合と完全一致し、固定順序先頭12件の公式実anchor・大会/年度/節・TeamMaster・日時・90分結果・PK/延長を凍結sourceへ事前照合した。[入力SHA](input-sha256.json)、[集合](fixed-set-verification.json)。

通信前に保存済み119件を新統合層のオフラインworker経由でStage A/B再生し、**119 PASS / 0 HOLD、全v5 semantic field不変**。過去4件は当時の旧契約による正式HOLDを完全再現し、隔離packet/seal/receipt読戻し後に後続正常原本へ進行した。現在の未解決件数には加えず、旧記録を維持した。[互換性](compatibility-summary.json)、[旧正式記録](old-formal-records-verification.json)。

新58ケースと既存798ケースの **856 PASS / failure0 / error0 / skip0、warnings-as-errors** を実HTTP前に確認した。12件の上限/13件目拒否、旧3件permit拒否、前工程からのコード差分完全一致、実workerのJob所属・所有権・終了、ACL/reparse/path競合、Stage Aの事実/SHA、未知備考HOLD・隔離receipt後の継続、403/429/timeout、隔離保存失敗、二重実行、履歴admission・運用領域書込み拒否等を検証した。実Windows故障46ケースも再実行し、45領域703ファイルを読取り専用保存した。テストによる公式通信0。[テスト](synthetic-test-results.json)。

前工程のコード・旧executor/permit・B12/B13・strict parser/v5/個別ruleは変更しない。新workerは12件専用schema/cap、統合層は独立module importとし、それ以外の通信/所有権/保存/Stage A/Bの振舞いを維持した。差分・理由・新旧SHAを通信前に固定し、コード差分の完全一致テストに合格した。新executor/launcher、全入力、source revision、選定集合、通信設定、出力領域、detail permitもSHA封印した。[差分](implementation-delta.json)、[実装SHA](implementation-sha256.json)、[仕様](SPEC.md)。

robotsは前工程の取得原本が24時間の鮮度条件内であり、raw/metadata SHAとアクセス条件を再検証した。**新robots GET 0、新robots permit 0**。既知の正確なrobots URLの保存済み404は、そのURLに公開規則が確認できなかった意味に限定し、サイト全体の許可証明としない。保存済みprotocol上、別の既知の厳しい適用条件は見つからなかった。

実取得UTCは **2026-10-21T12:47:12.804079+00:00〜2026-10-21T12:48:14.339989+00:00**。全12件でrequest/response UTC・raw/metadata/request SHA・PID/task/permit/receipt・TLS証明書とhostname検証を照合した。TLSはTLSv1.2。詳細本文合計 **1,474,601 bytes**、最大126,880 bytesで24 MiB/2 MiB上限内。通信完了→次開始の最小値 **5.197389秒**。retry0、redirect0、parallel0、自動再開0。socket/worker wall期限10秒、親worker12秒、親進行budget180秒、外側240秒、cleanup2秒。全12 workerと外側親の所有Jobは最終process0。[通信receipt集計](communication-summary.json)、[process/保存](process-storage-summary.json)。

親がworker終了と証拠結合を確認した後、Stage Aで原本を封印し、Stage Bは封印済みbytesだけを再読込みした。identity・日付/kickoff・90分結果・PK/延長数値とsourceの一致、全seal/receiptの読戻しSHA、各receipt確定後に次URLを開始した順序を監査した。B12 byte検証器のnetwork counter 0はその検証器自身の副作用であり、外側の実取得数12 GETとは分離して記録する。新しい原本のSHAは実取得後のworker receiptとの照合で固定し、通信前に取得済みだったとは主張しない。

今回は未知備考が発生しなかったため、実HTTP隔離・隔離後の実HTTP継続は未観測。過去4件のオフライン隔離再現を実HTTP実証とは呼ばない。最終詳細AのPASSとは別に、開始/中断/再開/完了/結果利用可能時刻B、当初日程/変更告知C、予測cutoffでの取得証明Dは全12件HOLD、history admission=false。共通備考分類候補と予測器へ未接続。

取得原本12・Stage A封印12・Stage B PASS12・隔離HOLD0・未取得157を独立集計した。元288件＝取得済み131件＋未取得157件、URL重複/overlap/公式ID衝突0。既存119件、旧正式停止記録、元169件台帳・計画は不変。157件の次回計画はローカルへ別versionで保存し、通信無効・permitなし・未承認とした。

27,494保護ファイル、モデル53 payload、Champion A、保存予測、固定source/研究入力/運用コード、タスク定義2件、main、他worktree2件は不変。今回の新しい運用差分0。07:00/22:00タスクとの時間重複なし。過去11件の未帰属差分と、前工程の07:00タスクで確認済み10件は別に保持し、根拠なく研究変更や通常更新と認定しない。[保護監査](protection-verification.json)。

取得原本・metadata/request・receipt・Stage A/B・旧隔離再現・合成故障証拠・実装/入力/出力SHAを別ドライブへbackupし、ZIP CRC・全entry SHA・独立展開後SHA・読戻しが一致した。公開はコード・仕様・合成テスト・SHA・集計のみで、個別raw/metadata、氏名、個人パス、学習済みartifactは含まない。[backup](backup-verification.json)。

合格はこの12件に限定する。実HTTP隔離、全filesystem/特権的競合への普遍的原子性、ACL変更自体の原子的禁止、電源断耐性、他ページ・長期間取得の安全性は未実証。[未実証事項](UNPROVEN.md)。残り157件には新しい対象集合・executor・permitと別承認が必要。[次工程](next-stage.json)。

**HISTORY / PREDICTION：HOLD**。実fit0、性能評価0、実確率計算0、T0登録0、対象登録0、将来予測保存0。Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
