# Phase 2.5B-10 限定取得契約

対象は封印済み209 URLのみ。既取得79 URLを除外し、保存済み公式一覧の実anchor、固定CSV全文・行SHA、公式ID、namespace、大会・年度・節、TeamMaster、日時、規定時間結果とPK・延長属性を通信前に照合した。17バッチ各12件、最終5件とした。

新executor・launcher、v4/v3/v2 adapterと3件の個別review-rule、strict parser、全入力、対象、通信設定、専用出力・別ドライブbackup先、permitとバッチ計画を最初のGET前にSHA封印した。共通分類器候補はimportも接続もしていない。旧executorと旧permitは実行していない。

HTTPS、証明書・hostname検証、host data.j-league.or.jp、各URL最大1 GET。socketと親workerのdeadlineは10秒、全体4500秒、外側4550秒、cleanup35秒。通信完了から次開始まで最低5秒。並列・retry・redirectは0。本文2 MiB/件、全418 MiB以下。上限到達時は超過読込みをせず保守的に停止する。保存済みrobots証拠は24時間のローカル鮮度条件を各開始バッチで再確認した。追加robots GETは0。

親processの通信、研究領域外への書込み、モデルdeserialize、指定した単一worker以外の子processをaudit guardで拒否する。workerはbase interpreterを直接起動し、permit、allocation、preflight、新規空フォルダを検証する。全体のexclusive-create claimにより二重実行を拒否する。不整合・未知備考・アクセス制限・timeoutで全体停止し、その場の規則変更、再取得、自動再開をしない。

通訳・コーチ・GKコーチの既存例外は、それぞれ封印された1試合のidentity、原文構造、raw/metadata/request SHAにだけ適用する。未知役割や未知時刻注記へのfallbackはない。request・response・snapshot保存・監査完了の実UTCを分離し、過去の取得時刻へ変更しない。

A（最終詳細）、B（実イベント・結果利用可能時刻）、C（当初日程・変更告知）、D（予測cutoffまでの取得証明）を独立判定する。AのPASSはB〜Dを代替しない。実結果event admissionと将来予測利用は未承認。

最終後処理は保存済み証拠の読取り・解析・SHA照合のみ。運用タスクは呼出し・変更・停止しない。新baselineと過去の11件の未帰属差分、前工程で根拠が確認された07:00タスクの10件の可変出力を別々に保持する。
