# 固定48件・4バッチの二段階実HTTP契約

元288件＝既取得131件＋未取得157件。指定SHAの157件台帳と計画から、固定順序先頭48件を12件ずつ4バッチへ分割する。公式一覧の保存済み実anchor、URL/公式ID/namespace、大会/年度/節、TeamMaster、日時、90分結果、PK/延長とsource revisionを事前照合する。追加探索、差し替え、既取得131件への接続は禁止。

前工程の[12件契約](../phase2_5B_15/SPEC.md)と旧実装・permitは不変。新[worker](multibatch_http_worker.py)は48件専用schema/cap、新[統合層](multibatch_http_integration.py)は独立moduleをimportする。Windows Job/ACL/保存機構、B12 Stage A/B、strict parser、v5 adapter、4個別ruleを維持する。新[executor](multibatch_executor.py)が4バッチの進行と再監査を所有する。[差分と新旧SHA](implementation-delta.json)を初回GET前に固定する。

全体permitは48 URL・48 GET・各URL1回。本文各2 MiB/合計96 MiB。4個のバッチpreflightは各12件・24 MiB、全体選定SHA・順序・既取得禁止・停止条件を固定し、全体permitの入力SHAへ結合する。permit共有消費claimとURL intentを接続前にexclusive-createし、通信未確定でも消費済みとする。二重実行・無断再開・旧permitは拒否する。

HTTPの許可hostは`data.j-league.or.jp`、HTTPS/443、証明書・hostname検証必須。DNS先頭アドレスへ一度だけ接続し、代替IPの自動再試行も行わない。GET1回、retry0、redirect0、parallel0。通信完了から次開始まで最低5秒をバッチ境界でも維持する。実装はより遅いworker終了確認時点から待つ。socket/通信wall deadline10秒、親worker12秒、全体進行900秒、外側process1020秒、cleanup2秒を固定する。

robotsは既知の正確なURLの保存原本・metadata・SHAを用い、各バッチ前に24時間の鮮度と既知アクセス条件を再確認する。開始時にstaleの場合だけ、独立permit最大1 GET/64 KiBを作成できる。実行中の条件不明・鮮度切れは停止し、未封印のrefreshを行わない。404はそのURLに公開robots規則が確認できなかった意味だけで、サイト全体の許可証明ではない。厳しい既知の条件を優先し、日程・告知・indexへは接続しない。

Windowsのsuspended起動→所有Job所属→kernel PID/親PID・creation FILETIME・image/SHA確認→resumeを維持する。保持したJobだけを停止し、他processは終了しない。新規制限owner/DACL領域、ancestor/root DirectoryLease、reparse拒否、CREATE_NEW、FlushFileBuffers、readback、SHAを使用する。既存出力へ追記しない。

親がHTTP応答とrequest/worker/task/permit/receipt・SHA・URL・TLS・本文budgetを確認してStage Aへ渡す。Stage Aはidentity/結果/取得証拠を検証・封印する。Stage Bは封印済みbytesだけで備考を審査する。未知備考・未分類時刻注記だけならHOLD隔離し、packet/seal/receiptの独立readbackが確定してから次GETへ進める。identity・結果・未知HTMLの事実欄・SHA・Stage A/B矛盾・隔離保存・所有権/ACL・HTTP403/429/TLS/timeout/redirect等は全体STOP。規則をその場で追加しない。

12件ごとの境界では、全累積source/review/quarantine seal・receiptと件数を再確認する。取得済み集合、PASS集合、隔離HOLD集合、未取得集合を分離し、PASS＋HOLD＝確定receipt数、隔離数＝HOLD数、未確定0、admission falseを要求する。全累積HTTP raw/metadata/request/worker receipt/parent receiptを再読込みし、SHA・PID/task/permit・URL集合・UTC/rate・本文総量・残存worker0を再照合する。

境界packet・transport ledger・累積aggregateを封印し、detached batch receiptをreadbackする。前境界receipt SHAを次境界へ連結する。次バッチのGETは、前境界sealの再確認と新しいaccess observationの確定後だけ開始する。最終48件目がHOLDでも隔離が完全確定すれば第4境界を確定して終了する。未確定receiptや不整合があれば残りを`NOT_STARTED_AFTER_GLOBAL_STOP`等で記録し、自動再開しない。

実HTTP未知備考件数、隔離packet/seal/receipt確定数、隔離後に別URLへ進んだ件数を独立集計する。末尾隔離には後続URLがないため、観測された継続数を水増ししない。過去原本/合成の隔離を実HTTP観測とは呼ばない。備考原文・個別identity・氏名はローカルだけに保存する。

`source_acquired`、`source_integrity_verified`、`detail_analysis_status`、`quarantine_status`、`timing_evidence_status`、`history_admission_status`を分離する。B12 byte検証器のnetwork counter 0はその検証器自身の副作用であり、実GET数は外側receiptで報告する。取得UTCを過去へ遡らせない。最終詳細Aと時系列B・当初日程/告知C・予測cutoffでの取得証明Dを分離し、B〜DとadmissionはHOLD/falseのまま。

通信前に保存131件の全SHA/Stage A/B/semantic field、過去4件の旧契約隔離、48件/49件目拒否、複数/末尾隔離、境界とアクセス条件、各種STOP、実Windows所有権/ACL/reparse/crash等を検証する。共通分類候補・モデル処理・運用collector・予測器へ接続しない。

今回の許可は48件で終了する。残り109件の自動取得・履歴admission・実予測利用は未承認。運用タスクは変更・停止せず、前後の可変出力を独立証拠で監査する。旧停止run・原本・モデル・固定source・main等は保持する。
