# Phase 2.5B-8 限定取得契約

封印済み245 URLだけを対象とし、保存済み公式一覧の実anchor、公式ID、元CSV全文SHA・行SHA、TeamMaster ID、大会・年度・節、日時、90分結果とPK/延長属性を通信前に照合した。取得済み43 URLは除外し、12件×20＋5件×1の固定計画とした。

実行executor、外側launcher、全入力、parser、v3/v2 adapterと両review-rule、permit、バッチ計画を最初のGET前にSHA封印した。旧executor・旧permitは実行していない。初期preflight版は通信なしのWindows実process確認で起動ガードの不具合を検出し、未使用で失効記録を残した。WindowsのPopen auditでexecutableがNoneになる場合を安全に拒否し、worker起動時はbase interpreterを明示する別ファイルの最終版へ修正。403件の合成・関連テストと43件のsemantic field不変を再確認して再封印した。初期版と最終版のSHA・時刻を区別し、実取得開始後のコード・規則変更はない。

HTTPS/TLS証明書・hostname検証、許可host data.j-league.or.jp、各URL最大1 GET、socket timeout10秒、親worker deadline10秒、外側process4550秒、内部全体4500秒、通信完了から最低5秒、並列/retry/redirect 0。本文は各2 MiB、全体490 MiBを上限とし、本文上限到達時は超過読込みをせず安全側にHOLDとする。保存済みrobots証拠は24時間のローカル鮮度条件内で各開始バッチにも再検証し、追加robots GETは0。

親processの通信、研究領域外への書込み、モデルdeserialize、許可した単一worker以外の子processをaudit guardで拒否する。workerはbase interpreterを直接起動し、permitと親のallocation/preflightの対応、空の新規出力先を検証する。execution-startedのcreate-newで全体を一度きりとし、403/429/timeout/unknown structure/identity・結果・SHA不一致/未知注記で全体停止する。停止後の再開・再取得・その場での規則拡張は行わない。

既存43件は封印済みwitness規則だけで再解析する。通訳とコーチの既存例外はそれぞれ固定された1件に限定する。別役割や別試合へ一般化しない。Aの最終詳細解析PASSは、Bの実イベント/結果利用可能時刻、Cの当初日程・変更告知、Dの予測時点の取得証明を代替しない。
