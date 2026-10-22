# 固定109件・10バッチの二段階収集

指定SHAの109 URL全件を元順序で固定し、12件×9バッチ＋1件×1バッチとする。保存済み公式実anchor・ID/namespace・年度/大会/節・TeamMaster・日時・90分結果・PK/延長・凍結sourceを通信前に照合する。既取得179 URLを禁止集合とし、対象追加・URL生成・旧executor/permitの再使用を禁止する。

新しい109専用schema、worker、統合層、executor、launcher、単回permitを別作成し、全依存コード・入力・source・対象・出力先をSHA固定する。v5を実取得に用いる。v6は別processの保存原本オフライン回帰だけであり、liveコード依存・workerへimportしない。共通分類器も接続しない。

HTTPS/公式host/443、TLS証明書・hostname検証、詳細最大109 GET・各URL1回、retry0/redirect0/parallel0、通信完了から次開始まで5秒以上、socket/wall10秒・親worker12秒・進行2100秒・外側2280秒・cleanup2秒を固定する。本文各2 MiB・合計218 MiB。DNS先頭addressへ一度だけ接続する。接続intentを先に消費し、不明な終了でも再試行しない。

各バッチ前に既知の正確なrobots証拠をSHA/24時間鮮度/適用条件で再検証する。必要時だけ別枠の最大1 GET/64 KiB permitを用い、失敗/不明/拒否では詳細をSTOP。404はそのURLの公開規則が確認できなかった意味だけとし、サイト全体の許可とは扱わない。

Windows suspended起動→所有Job→kernel PID/親PID・creation FILETIME・image SHA→resumeを維持する。制限owner/DACL、新規exclusive-create、ancestor/root lease、reparse拒否、fsync/readback/SHAを用いる。所有しないprocessを終了しない。

Stage Aのidentity/日時/結果/PKET/source/HTTP/request/raw/metadata/SHA/UTCの整合と原本封印が先である。Stage Bは封印済みbytesだけを解析する。未知備考/未分類時刻注記だけならHOLD隔離し、packet/seal/receiptの保存・独立readback後だけ次URLへ進める。通信・証拠・事実欄未知HTML・保存・所有権・ACL異常は全体STOP。未知備考をその場でPASSへ変更しない。

各境界で全累積source/review/quarantine/transportを再読込みする。全GET集合と順序・SHA・UTC/rate・本文量・全receipt・未確定0・history admission=false・worker残存0を確認する。前境界receipt SHAを連結し、最後の1件も同じ境界規則で処理する。独立監査では12/24/36/48/60/72/84/96/108/109件の累積台帳を最終台帳の前方部分と比較する。

既存のv5取得時176 PASS/3 HOLDと、後日のv6独立179 PASS/0 HOLDを別に記録する。新109件のv5 PASS/HOLDも別に保存し、既存原本・旧隔離packet・正式停止記録は不変とする。取得数と解析PASS数を混同せず、Aの収集完了で時刻B・日程/変更告知C・予測時点取得証明Dや履歴admissionを許可しない。

本Windows環境での検証範囲に限る。特権owner/admin/kernel・全filesystem競合の普遍的原子性、電源断でのdirectory metadata永続性、全HTML/備考の汎用分類は未実証。故障注入の403/TLS等を公式サイト上で起こして検証したとは扱わない。
