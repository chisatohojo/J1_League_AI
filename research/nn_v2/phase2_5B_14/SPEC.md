# 3件限定の実HTTP二段階パイロット契約

対象は既存172件台帳の固定先頭3件。URL・identity・年度付き大会見出し・TeamMaster・日時・90分結果・PK/延長と元CSV行・公式一覧実リンクを通信前に照合し、選定順序とSHAを固定する。追加探索や差し替えを行わない。旧116件・旧executor・旧permit・B12/B13実装は変更しない。

新実装は[HTTP worker](http_worker.py)と[親統合層](http_integration.py)。Windowsのprocess/保存層は固定SHAのB13実装を利用する。workerを直接base Python executableでsuspended起動し、KILL_ON_JOB_CLOSEのJob Objectへ所属させ、kernel PID/親PID・creation FILETIME・image path/SHAを確認してresumeする。起動済みprocessのhandleと所属Jobだけを停止対象とし、PID一覧から他processを終了しない。

詳細permitは3 URL・3 GET・本文各2 MiB/合計6 MiB。robots permitは保存済みの正確なrobots URLのみ1 GET・64 KiBで独立する。permit/コード/入力SHA・出力先・通信設定を固定し、共有のpermit消費claimとURLごとのintentを接続前にexclusive-createする。同一permit・URL・既存出力を再使用しない。未確定の通信も消費済みとし、再試行・無断再開しない。

workerには実HTTPの入口だけがあり、CLIの合成応答・local replay・retry・redirectモードは存在しない。HTTPS接続先は固定hostの443だけ。DNSの先頭アドレス1個へ接続し、代替アドレスへの自動fallbackも行わない。`ssl.create_default_context()`の証明書必須・hostname検証を要求し、SNI、交渉TLS version/cipher、証明書SHAをreceiptと結合する。HTTP requestはGET1回、Accept-Encoding identity、Connection close。Cookie等を公開成果物へ保存しない。

socket timeoutとworker内通信wall deadlineは10秒、親worker deadlineは起動・保存を含む12秒、全体外側processは240秒、cleanupは2秒。親側の通信進行budgetも180秒に制限する。通信終了後から次開始まで5秒以上待ち、robots後にも適用する。実装はresponse完了より遅いworker終了確認時点から待つ。並列・自動retry・redirect追従は0。403/429・TLS・通信・timeout・未確定状態・本文超過は全体STOPする。

robotsのローカル鮮度は24時間。staleの場合だけ独立permitで1回確認する。200は既知のrobots構造を要求し、User-agentのallow/disallow・crawl-delay・request-rateを確認する。不明な指令・構造・厳しいrateはHOLD。404は既知の保存済み404本文とのSHA一致を要求し、**その正確なURLに公開規則が確認できなかった**という意味だけで扱う。サイト全体の許可証明にはしない。別の既知制限がある場合は優先する。追加index・日程・告知には接続しない。

親がworker正常終了・Job空・task/permit/PID・request/raw/metadata/receiptのSHAとURL・TLS記録・body budgetを検証してからStage Aへ渡す。新しい取得時点のraw/metadata/request SHAはworker receiptとの検証後に固定するもので、通信前にraw SHAが分かっていたとは扱わない。source revisionとfixture期待値は通信前に固定済みである。

Stage A/Bは変更していないB12の封印byte検証器を使う。Stage Aで事実と証拠を検証・封印し、Stage Bはその封印済みbytesを読戻してv5で審査する。未知備考・時刻注記だけならHOLD隔離し、packet/seal/receiptのFlushFileBuffers/readback/SHA確認完了後だけ次URLへ進める。identity・結果・未知HTML・SHA矛盾・保存失敗・解析契約エラーは全体STOP。隔離HOLDへ格下げしない。

旧封印byte検証器の`network_GET: 0`、`communication_permits_created: 0`は、そのbyte検証器自身の副作用の値である。外側の実通信件数は独立した[通信台帳集計](communication-summary.json)で報告し、旧検証器のcounterを実HTTP全体の件数として用いない。各packetに残る`SAVED_OFFICIAL_WITNESS`も封印済みbytesの入力種別であり、当日以前に取得済みだったという主張ではない。実取得UTCとtransport `LIVE_HTTP`は独立receiptに保存する。

`source_acquired`、`source_integrity_verified`、`detail_analysis_status`、`quarantine_status`、`timing_evidence_status`、`history_admission_status`を分離する。最終詳細AのPASSでも時系列B・当初日程C・予測cutoffでの取得証明DはHOLD、admissionはfalse。共通備考分類候補、モデル、collector、タスク、予測器との接続はない。

保存には新規の制限DACL領域、ancestor/rootのreparse拒否・DirectoryLease、CREATE_NEW、file handleによるFlushFileBuffers/readback/SHAを使用する。Windows競合・process異常終了・隔離/receiptの故障試験は実通信前に実行する。普遍的な原子性や電源断耐性は[未実証事項](UNPROVEN.md)の範囲を超えて主張しない。
