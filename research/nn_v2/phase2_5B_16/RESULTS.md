# Phase 2.5B-16 二段階実HTTPマルチバッチ・後処理最終確定

正式判定：**TWO_STAGE_REAL_HTTP_MULTIBATCH_VERIFIED_RESEARCH_ONLY**。保存済み48件の取得・封印・4境界の累積通信台帳・45 PASS／3隔離HOLD・隔離後の実GET継続・集合・所有権・保護監査・別ドライブbackup/復元が成立した。**累計179件取得＝176 PASS＋3 HOLD、未取得109件。176＋3＋109＝288。** [正式状態](readiness.json)、[独立監査](final-audit-summary.json)。

本取得は2026-10-21の固定48 URLに限定され、2026-10-21T13:25:10.206313+00:00〜2026-10-21T13:29:32.926599+00:00に完了した。実GET48、各URL1回、全件HTTP200、Stage A封印48、Stage B 45 PASS／3 HOLD。robotsは鮮度内の既知の正確なURLの保存証拠を各バッチ前に再検証し、新GET/permitは0。404はそのURLに公開規則が確認できなかった意味に限定し、サイト全体の許可とは扱わない。48件で終了し、残り109件・告知・日程・indexには接続していない。[通信](communication-summary.json)。

| バッチ | GET | PASS | 隔離HOLD | 未確定 |
|---|---:|---:|---:|---:|
| 1 | 12 | 10 | 2 | 0 |
| 2 | 12 | 12 | 0 | 0 |
| 3 | 12 | 12 | 0 | 0 |
| 4 | 12 | 11 | 1 | 0 |

各境界に保存された累積通信台帳を再読込みし、独立に原本から作った最終48件台帳の先頭12/24/36/48件と完全一致した。各raw/metadata/request/worker receipt/parent receiptのSHA、PID/task/permit、URL/identity、HTTP/TLS、UTC、本文を再計算した。前境界receipt SHAの連結、source/review/quarantine seal、累積PASS＋HOLD、未確定0、access observation、境界receipt確定後の次GET開始も成立した。[バッチ](batch-summary.json)、[前方一致の追加契約](postprocess_contract.py)。

実HTTP隔離の正式独立結果：**REAL_HTTP_QUARANTINE_OBSERVED_AND_VERIFIED**。3件はStage Aの事実・結果・原本整合が成立し、Stage Bが未知備考HOLD。原本・metadata/request・隔離packet/seal/receiptのSHA・readback・実UTC・順序とhistory admission=falseを確認した。3件すべてで隔離確定後の別URLへの実GETが存在した。未知備考の許可規則を追加せず、正常試合へ再分類していない。原文・個別identity・氏名はローカルのみ。[隔離集計](quarantine-summary.json)。

利用制限後の2026-10-22の再開は、**新規証拠GET0、通信permit0、取得run再実行0、規則追加0**。取得executor/launcherを実行していない。バックグラウンドの旧独立監査は10月21日22:39（13:39 UTC）に正常終了していたことを、保存artifactと旧process exit0から確認した。今回はその出力を上書きせず、保存原本による別versionの独立監査、未完だったbackup/公開/Git保存を完了した。取得時固定のexecutor/launcher全依存SHAは現在と一致し、新しい後処理コードの役割/SHAを分離した。[再開監査](resume-verification.json)、[実装SHA](implementation-sha256.json)。

旧runの48 workerと外側Jobは終了時process0で、再開時も取得process残存0。所有関係不明のprocessを終了していない。出力owner/DACL・reparse/ancestor leaseを読取り専用で確認した。TLS証明書・hostname、retry0/redirect0/parallel0、通信完了→次開始の最小5.199966秒、各2 MiB/合計96 MiB、実本文合計5,940,271 bytesを再照合した。通信wall/socket10秒、親worker12秒、進行900秒、外側1020秒・cleanup2秒と保存終了時刻は整合する。[process/保存](process-storage-summary.json)。

通信前の**935 PASS／fail0・error0・skip0**は再利用した。元JUnitのoffset付きtimestamp・duration、permit前の入力SHA、実装SHA、元test source SHAを照合し、今回935件を再実行したとは記録しない。新しい後処理契約の前方一致、順序/重複/件数/隔離の誤集計、未取得扱いへの逆戻し、admission、過剰継続の拒否は、ネットワーク禁止下で別実行して**9 PASS**。元935と新9のJUnitを別々に保存した。[テスト証跡](synthetic-test-results.json)。

旧131件の原本SHAと既存131 PASSの入力/結果SHA、48件のv5独立再解析、公式identity・大会/年度/節・TeamMaster・日時・90分結果・PK/延長と凍結CSVを確認した。元288集合を179取得＋109未取得へ再計算し、URL重複/overlap/ID衝突0。隔離3件をPASSへ加算せず、未取得へ戻していない。109件台帳/計画は既存の不変versionを再確認・backupし、取得は未承認のまま。[集合](fixed-set-verification.json)、[入力SHA](input-sha256.json)。

保護baseline 30,729件のうち**固定30,716件は不変、13件は07:00運用タスクの可変projectionとして独立照合**した。モデルseal/53 payload、既取得131件、旧parser/v5/4個別rule、旧executor/permit/停止記録、Champion A成果物、既存14予測・再現98件、凍結研究source/過去publication、運用コード、タスク定義2件、main、他worktreeは保持した。説明不能な固定差分0。[保護監査](protection-verification.json)。

22:00タスク失敗と07:00タスクは別事象である。10月21日22:00は失敗終了（Last Result1）、表示status1件・取得証跡25ファイルを保存した記録を維持し、成功更新とも研究原因とも推測しない。10月22日07:00はLast Result0で、タスクUTC/定義/保存discovery/公式revision manifest/exports/previewを照合した。可変出力13件・新規証跡85ファイルに加え、その中の運用予測batch5件をmanifest・fixture集合hash・生成UTC・公式revision bindingで確認した。旧保存予測は不変。これらは研究のモデルload/推論/予測保存へ計上せず、研究の凍結revisionへも採用しない。運用タスクを変更・停止・再実行・修復していない。過去未帰属11件と既知の前工程07:00由来10件も別に保持した。[運用事象](operational-events-summary.json)。

後処理監査の初版は、新しい運用batchを初期allowlist外として停止した。別versionでmanifest/UTC/revision bindingを検証した後に許可対象を限定した。次版ではpreviewの保存mtimeがJSON内終了UTCより1µs後であることを検出し、原記録を保持したまま、時計採取後の原子的保存の順序を確認して監査の時刻比較に1ms以内の保存差を明示した。元取得・parser・備考規則を変更したものではなく、途中の監査コードも削除・上書きせずbackupした。

48原本、3隔離packet、request/metadata、worker/Stage A/B/通信receipt、4累積台帳、取得時コード/permit/入力SHA、旧/新監査、テスト、109件台帳を別ドライブへ保存した。ZIP CRC・全entry SHA・独立展開後SHA・読戻し一致、差分0。公開はコード・仕様・合成テスト・集計・SHAのみ。raw/metadata、備考全文、氏名、個人パス、学習済みartifactは非公開。[backup](backup-verification.json)。

詳細証拠Aの解析PASS45／備考HOLD3と、実開始/中断/再開/完了/結果利用可能時刻B、当初日程/変更告知C、指定予測時点での取得証明Dは分離する。B〜Dとhistory admissionはHOLD/false。全filesystem/特権的競合の普遍的原子性、電源断耐性、備考汎用分類、残り一括取得の安全性は未実証。[仕様](SPEC.md)、[限界](UNPROVEN.md)。残り109件の取得と未知備考3件の独立レビューは別承認。[次工程](next-stage.json)。

**HISTORY / PREDICTION：HOLD**。本研究・後処理のモデルload0、実fit0、性能評価0、実確率計算0、T0登録0、対象登録0、将来予測保存0。Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
