# Phase 2.5B-6 独立249件permitによる限定取得

判定は **HOLD_BOUNDED_EVIDENCE_ACQUISITION**。第1バッチ4件目に、許可されていない役割「コーチ」への警告備考を検出し、全体を停止した。**新規4 GET / HTTP200が4件 / 3 PASS / 1 HOLD / 未取得245件**。停止後の継続・retry・再取得は0。

開始branchは `feature/nn-research-v1`、HEADは `bff8c63efcdb4fada9f75fb7806a4789b91a9af4`、作業ツリーclean。Study `nn_v2_residual_20261020_01`、モデル `TRAINED_AND_SEALED_RESEARCH_ONLY`。モデルsealと53 payloadの生bytes SHA、全入力、既存snapshot、実装、保護対象10,973ファイルを照合し、不一致0で開始した。学習済みモデルのdeserialize・load・推論・fitは0。

## 利用制限後の後処理再開

取得processは2026-10-20 **11:00:43 UTC（20:00:43 JST）**にHOLDを保存し、外側processもexit0・timeoutなしで正常終端していた。これと、ユーザーから報告されたCodex利用制限による後処理中断は別事象として記録した。利用制限そのものは取得エラーや解析失敗として扱わない。

再開時に関連Python processは0件、終了させたprocessも0件。既存の最終監査artifact、SHA台帳、A〜D監査、未取得245件台帳、290 PASSのJUnitは完成済みだったため、SHAを確認して再利用した。`final-audit.py`自体を再実行・上書きせず、新しい読取専用の再開監査で4ページの結果を照合した。再開後の証拠取得、executor再実行、新規permit、備考規則の追加は全て0。

実行時固定のexecutor SHA `6627cc2db07ddedf2e33985a1444b866ffaa7c99021061432b98916d0d5ddc9e` と現在のファイルは一致した。parser・adapter・review-ruleと全150入力も一致し、取得コードの事後変更は検出されなかった。`final-audit.py`は取得開始後に追加された別のオフライン後処理コードで、取得時permitの入力には含まれていない。これを取得時executorと混同せず、SHA・mtime・用途を別に記録した。[resume-verification.json](resume-verification.json) と [implementation-sha256.json](implementation-sha256.json) を参照。

未完了だったバックアップと公開用成果物・Git保存をこの再開工程で仕上げた。元のraw/metadata、停止receipt、HOLD判定を変更していない。

## 独立した実行範囲

元の不足候補288件から取得済み39件を除いた249件が、前工程の完全台帳と一致した。百年構想156件・2026/27 J1 93件。URL重複・公式ID衝突・取得済み39件との重複は0。全249 URLを保存済み公式一覧の実anchorに戻し、大会・年度・節、TeamMaster対戦、日付・kickoff、90分結果、元source SHAを照合した。

前工程の39件は、固定adapterへの直接再解析と、新executorの読取専用解析経路の両方で **39 PASS**。既存結果と一致した。追加通信0。

新しい研究領域、新しい249件用executor、新しい全体permitを作成した。旧276件permitの再実行・継続は0。通信前に対象集合、executor、strict parser、adapter、review-ruleと150点の依存SHAを固定した。21バッチの計画は12件×20＋9件。各開始バッチは別のSHA付きpreflight・新規出力先を持つ。

## 取得結果と停止

| バッチ | 計画 | GET | PASS | HOLD | 未取得 |
|---|---:|---:|---:|---:|---:|
| 1 | 12 | 4 | 3 | 1 | 8 |
| 2〜20 | 228 | 0 | 0 | 0 | 228 |
| 21 | 9 | 0 | 0 | 0 | 9 |
| 合計 | 249 | 4 | 3 | 1 | 245 |

第1バッチをHOLDとして封印し、残り20バッチを `NOT_STARTED_AFTER_GLOBAL_STOP` と記録した。停止ページのraw・metadata・実取得UTC、対象ID、全文context、停止段階、executor/parser/permit SHA、内側workerと外側processのexit/receiptを保存した。[batch-execution-summary.json](batch-execution-summary.json) と [communication-receipt.json](communication-receipt.json) を参照。

停止段階は `reviewed_remark_adapter`。strict parserでは全4件のURL/ID、大会・年度・節、両クラブ、日時、規定時間結果・終了状態が保存済みsourceと一致した。3件は既知の空欄構造。残る1件は備考paragraph内のコーチ警告で、既知の「監督」警告でも、前工程で厳密に検証した1試合の通訳警告でもない。

adapterは `UNKNOWN_FORMAT` とし、停止理由 `UNKNOWN_NON_TIMING_REMARK_REQUIRES_REVIEW` を返した。内部の `REVIEW_FIXTURE_SCOPE` は、別試合向けのreview-ruleを流用できないことを示す。公式identityとsourceが矛盾したという意味ではない。役割・文型の許可をこの工程で拡張せず、次の独立オフラインレビュー対象として保存した。

この備考から中断・再開・延期の時刻シグナルは検出されていないが、それだけで通常試合として採用しない。新しく立証された物理的中断例外0、未確認備考形式1、通信障害0、SHA/identity/結果矛盾0、未解決の実装不具合0を区別した。今回の4ページにはPK・延長とも0。

## 集合・既存停止記録

元の288件は **既存39＋新しい選定249** に正確に分割される。今回までのraw保存は **43件**、独立解析のPASSは **42件**、備考HOLD1件、未取得245件。合計288件と整合し、重複・範囲外URLは0。[set-reconciliation.json](set-reconciliation.json) を参照。

Phase 2.5B-4の正式結果 **26 PASS / 1 HOLD / 249未取得** は不変。Phase 2.5B-5の独立39 PASSと今回の3 PASS / 1 HOLDは別artifactとして扱い、過去の停止済みrunを書き換えない。

## 通信・時刻

保存済みrobots証拠は24時間のローカル鮮度条件内で、通信前と開始バッチ前にオフライン再確認した。新規robots、告知、日程、index、取得済み39 URLへのGETは全て0。

HTTPS・許可host `data.j-league.or.jp`、証明書/hostname検証、各URL1 GET、timeout10秒と親worker deadline10秒、本文2 MiB/件・全体498 MiB、retry/redirect/並列0を維持した。全体process上限4500秒、実行は約17.66秒で停止。外側processはexit0・timeoutなしで停止結果を返した。本文計491,328 bytes、実測最小間隔 **5.240856秒**。

request開始、response完了、snapshot保存、監査完了の実UTCを別fieldで保存して順序を検証した。取得は2026年10月20日であり、過去の試合日や予測時点までに取得済みだったとは主張しない。

## A〜Dと次工程

A（最終詳細identity・結果・備考）は3 PASS / 1備考HOLD / 245未取得。B（実際の開始・中断・再開・完了・結果反映境界）、C（当初日程・変更告知）、D（予測時点までの取得証明）はAから自動合格させない。249件の対象ID別に必要証拠をローカル `A-B-C-D-evidence-audit.json` に記録した。

必要な次工程は、今回保存した未知備考の独立オフラインレビュー。現在の契約・review-ruleを無断で拡張せず、根拠を確認し、別バージョンでの合成・保存ページ回帰に進む必要がある。その後の245件取得には、新しい独立承認とpermitが必要。本工程で再開しない。[next-evidence-plan.json](next-evidence-plan.json) を参照。

当初日程、変更・延期・再開告知、完了と結果反映時刻、予測時点での取得証明は、詳細取得とは別の証拠監査として未解決のまま残る。HISTORY / PREDICTIONはHOLD。

## 検証・保護・保存

通信前テストは **290 PASS / skip0 / warnings-as-errors**。新規29件と既存関連261件。249件全模擬成功、最終9件、最終ページでの失敗、バッチ境界5秒間隔、429/timeout/未知注記による全体停止、二重実行拒否、旧276件permit拒否、code/parser/adapter/rule SHA、他試合の通訳警告の拒否、packet改変時のparser未到達を確認した。テスト中の通信0。[synthetic-test-results.json](synthetic-test-results.json) を参照。

取得後に全4件を再解析し、保存した結果と一致した。新executor・parser・adapter・review-ruleは取得開始後も不変。保護対象10,973ファイルのSHA不一致0、Windowsタスク2件・main・他worktree2件は不変。[protection-verification.json](protection-verification.json) を参照。

独立研究領域へraw/metadata、解析、停止receipt、全249件台帳、21バッチ計画・状態、未取得245件、A〜D不足一覧、実装とSHAを保存した。停止ページも含め別ドライブへバックアップし、ZIP CRC・全entry SHA・独立展開後SHAを照合した。公開するのは集計・仕様・テスト・SHAだけで、raw・個別履歴・氏名・個人パス・モデル成果物はGitHubへ追加しない。[backup-verification.json](backup-verification.json)、[local-evidence-index.json](local-evidence-index.json)、[SHA256-MANIFEST.json](SHA256-MANIFEST.json) を参照。

実fit **0**、性能評価 **0**、実確率計算 **0**、T0登録 **0**、対象登録 **0**、将来予測保存 **0**。

**HISTORY / PREDICTION: HOLD。Phase A: BLOCKED / Phase B: NOT_AUTHORIZED。**
