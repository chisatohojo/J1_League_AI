# 12件限定拡張パイロット

元288件＝取得済み119件＋未取得169件を照合し、169件の固定先頭12件だけを選定する。URL・ID・大会/年度/節・TeamMaster・日時・90分結果・PK/延長を凍結sourceと照合し、保存済み公式一覧の実anchorの存在を検証する。内容や未知備考の可能性で対象を交換しない。

前工程の[仕様](../phase2_5B_14/SPEC.md)、worker・親統合層・B12/B13・strict parser・v5 adapter・個別ruleは不変。新しい[worker](expanded_http_worker.py)は、詳細permitを12 URL・12 GETへ固定した独立schema `real_http_expanded_pilot_v1`を要求する。新しい[親統合層](expanded_http_integration.py)はそのworkerだけをimportする。変更は件数/schema・module分離・説明文に限定し、[新旧差分とSHA](implementation-delta.json)を通信前に固定した。合成テストで差分の完全一致と旧3件permit拒否を確認する。過去permitは使わない。

詳細は各URL1 GET、全体12 GET、本文各2 MiB/合計24 MiB。別枠robotsは正確な既知URLのみ最大1 GET/64 KiBを許可されているが、保存済み証拠が24時間以内なら新permit作成も新GETも行わない。200のrobots制限と既知の他の厳しい条件を優先する。404はその正確なURLに公開規則が確認できなかったことに限定し、サイト全体のアクセス許可とは解釈しない。

HTTPS、host `data.j-league.or.jp`、443、証明書・hostname検証、DNS先頭アドレスへの一度の接続、GET1回、retry0、redirect0、parallel0。通信完了後から次開始まで最低5秒。実装はより遅いworker終了確認から待つ。socket/worker内wall deadline10秒、親worker12秒、親進行budget180秒、外側process240秒、cleanup2秒。403/429・TLS・通信・timeout・不明な接続状態・本文超過は全体STOP。URLは接続前に消費intentを保存し、失敗・未確定でも無断再取得しない。

Windows Job Objectへsuspended workerを所属させ、kernel PID/親PID・creation FILETIME・image path/SHA・Job所属を確認してresumeする。保持した所有Jobだけを停止対象とする。新しい制限owner/DACL領域をexclusive-createし、reparse拒否・ancestor/root DirectoryLease・CREATE_NEW・FlushFileBuffers・readback・SHAを適用する。旧出力・停止run・raw/metadataへ追記しない。

親が実HTTP応答とrequest・metadata・worker/task/permit/receiptを照合した後、Stage Aは事実と原本を検証・封印する。Stage Bは封印済みbytesだけでv5審査する。未知備考/時刻注記だけならHOLD隔離し、隔離packet・seal・receiptの読戻し確定後だけ次URLへ進む。identity・結果・事実欄が不明なHTML・SHA・Stage A/B・隔離保存・所有権/ACL異常は全体STOP。未知備考を通常結果へ採用しない。

`source_acquired`、`source_integrity_verified`、`detail_analysis_status`、`quarantine_status`、`timing_evidence_status`、`history_admission_status`を分離する。B12のbyte検証器内counter `network_GET:0`はその検証器自身の副作用であり、外側実通信数は独立した[receipt集計](communication-summary.json)で報告する。封印入力種別`SAVED_OFFICIAL_WITNESS`も過去取得済みの主張ではなく、実取得UTCと`LIVE_HTTP`を別receiptで保持する。

実HTTPの未知備考を隔離・receipt確定し、その後の別URL取得まで検証できた場合だけ`REAL_HTTP_QUARANTINE_OBSERVED_AND_VERIFIED`とする。未知備考がなければ`REAL_HTTP_QUARANTINE_NOT_OBSERVED`。過去原本・合成データの隔離再現を実HTTP観測と呼ばない。

既存119件の新統合層によるStage A/B再生・全semantic field一致と、過去4件の旧契約HOLD/隔離/後続正常処理を通信前に確認する。モデル・運用領域への書込み、旧permit、二重実行、SHA/identity/結果矛盾、403/429/timeout、隔離保存失敗等を合成/実Windowsローカル試験で検証する。共通分類候補・運用collector・タスク・予測器には接続しない。

12件で必ず終了する。成功後も未取得157件の取得、履歴admission、HISTORY/PREDICTIONのREADY化は未承認。最終詳細AがPASSでも、時系列B・当初日程/告知C・予測cutoffでの取得証明DはHOLD。実UTCを過去へ遡らせない。
