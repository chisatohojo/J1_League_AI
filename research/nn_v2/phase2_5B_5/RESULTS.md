# Phase 2.5B-5 未知備考のオフライン解決

判定は **READY_FOR_NEW_BOUNDED_ACQUISITION_APPROVAL**。検証対象の備考は、公式備考欄の全文構造と文脈から、通訳という試合スタッフへの懲戒・警告注記として分類できた。新しい研究用契約による保存済み39ページの独立再解析は **39 PASS / 0 HOLD**、合成・既存関連テストは **261 PASS**。

**新規の証拠ネットワーク取得0、通信permit作成0、残り249件の取得再開0**。この判定は次の限定取得について承認を受ける準備判定であり、実行許可ではない。HISTORY / PREDICTIONはHOLDを維持する。

開始branchは `feature/nn-research-v1`、HEADは `9fe7962aca64b0f58d4bf2d54daebd26ed94523f`、作業ツリーはclean。Study `nn_v2_residual_20261020_01`、モデル `TRAINED_AND_SEALED_RESEARCH_ONLY`。前工程の停止receipt・batch seal・raw/metadata、パイロット12件、解析実装SHA、研究モデルsealと53 payloadの生bytes SHAを照合した。モデルのdeserialize・load・推論・fitは実行していない。

## 原因と根拠

対象のnamespaceはJ.LEAGUE Data Siteの試合カードで、公式URLとID、百年構想リーグの大会・年度・節、両クラブ、日時、90分結果を保存済みsourceとstrict parserで照合した。個別identity、raw/metadata/request SHA、実取得UTC、全文・HTML・byte位置はローカルの `target-context.json` に保存した。

公式の `A11 備考` ブロックは、監督欄の後、試合情報欄の前に1つだけあり、見出しは「備考」。paragraphは1件で、別注記はない。全文は「試合分数 → 警告とコード → クラブ → 氏名 → 役割（通訳）」という明示的なスタッフ警告構造だった。時刻キーワードの不在だけを採用理由にはしていない。警告コードの詳細な規則上の意味を新たに推定することもない。

この備考自体に中断・再開・延期や日程変更を指示する記述はない。strict parserの時刻シグナル検査にも該当しなかった。ただし、この最終ページだけで試合全体の時刻例外不在や当初日程の来歴まで立証したとは扱わない。

旧HOLDの経路は、strict parserによるidentity・日時・結果・備考抽出はPASSした後、パイロットで許可済みだった監督警告等の形式に「通訳」が含まれず、備考gateが `UNKNOWN_FORMAT` を返し、停止済み取得runが `UNKNOWN_NON_TIMING_REMARK_REQUIRES_REVIEW` を記録した、というものだった。

## 新しい契約

旧取得実装・parser・原本・監査結果を変更せず、ネットワーク機能を持たない新しい研究用adapter `reviewed_staff_warning_exact_witness_v2` を分離した。詳細は [REMARK_CONTRACT.md](REMARK_CONTRACT.md)、SHAは [implementation-sha256.json](implementation-sha256.json)。

| 備考 | 新しい扱い |
|---|---|
| 既知の空欄・監督警告・脳振盪交代等 | 旧契約の判定を維持 |
| 今回検証した通訳への警告 | 1つの試合identity、全文・構造・位置、証拠SHAが完全一致した場合だけ非時刻注記 |
| 他試合の通訳警告、未登録役割、未知文型 | 個別にレビューされるまでHOLD |
| 既知注記と未知注記の混在、中断・再開等 | HOLD。既知部分だけでPASSにしない |

新しい許可には、scope内の全identity field、大会・年度・節の全文見出し、strict parserの結果全体、備考全文、A11ブロックのSHAと位置、paragraph HTML、raw/metadata/request SHA、取得UTCを要求する。Unicode正規化された抽出文字列も照合するが、それだけで原文の相違を許可しない。部分一致・警告文字の有無・他の備考へのfallbackはない。

## 独立回帰と停止記録

パイロット12件と前工程の保存27件、合計39件を再検証した。従来PASSだった38件はstrict解析結果と分類が同一。対象1件もidentity・日時・スコア・PK/延長・備考抽出結果を維持し、検証済みの非時刻注記分類だけを追加した。[offline-regression-summary.json](offline-regression-summary.json) に集計と個別結果artifactのSHAを保存した。

Phase 2.5B-4の正式記録 **26 PASS / 1 HOLD / 249未取得**、取得状態 `HOLD_BOUNDED_EVIDENCE_ACQUISITION` は不変。新しい39 PASSは別artifactであり、停止済みrunを成功へ書き換えない。新しい結果イベントのadmissionや特徴量更新も行っていない。

合成テスト44件を追加し、関連217件と合わせて **261 PASS / skip0 / warnings-as-errors**。通訳と監督の別経路、未登録役割、別試合・大会・日時・クラブ・スコア、混在注記、中断・再開・延期、未知文、証拠とreview-ruleの改変、同じ正規化結果になる原文変更、部分一致fallbackの拒否を検証した。テスト中の通信0。[synthetic-test-results.json](synthetic-test-results.json) を参照。

## 残り249件の計画

元の276件の固定台帳から取得済み27件を除いた249件が、停止時の未取得台帳と完全一致した。取得済み39 URLとの重複0、全249件が保存済み公式一覧の実anchorに存在する。安定順序を維持し、12件×20バッチ＋9件の **21バッチ**を計画した。[remaining-acquisition-plan.json](remaining-acquisition-plan.json) を参照。

新しい備考adapterとreview-rule、変更しないstrict parser、既存transportの参考SHAを固定した。計画自体は `network_enabled=false / permit_created=false / execution_authorized=false`。次の工程では別の明示承認、新しい249件用executorのSHAと全体permit、最新アクセス証拠・preflightが必要であり、古い276件permitを実行しない。

通信条件はHTTPS・許可host限定・証明書/hostname検証、各URL1 GET、完了後最低5秒、timeout10秒・有限worker/global deadline、retry/redirect/並列0、本文2 MiB/件、未知注記・通信異常で全体停止を維持する。robotsの追加取得が必要なら別承認とする。本工程で取得・再開や通信permit作成は行っていない。

当初日程・変更告知・物理的な完了境界・予測時点までの取得証明は別途必要。今回の備考解決でHISTORY全体をREADYにしない。

## 保護・保存

保護対象10,613ファイルのSHA不一致0、既存snapshotと停止記録の不変、Windowsタスク2件・main・他worktree2件の不変を確認した。[protection-verification.json](protection-verification.json) を参照。

39件の原本コピー、新旧解析結果、全文context、限定review-rule、249件計画、実装、テストとSHAを研究専用領域に保存した。別ドライブのZIPについてCRC、全entry SHA、独立展開後SHAを検証し、公開集計もコピーして読み戻す。[backup-verification.json](backup-verification.json)、[local-evidence-index.json](local-evidence-index.json)、[SHA256-MANIFEST.json](SHA256-MANIFEST.json) を参照。GitHubには集計・仕様・SHA・テストだけを追加し、raw/metadata・個別履歴・氏名・個人環境パス・学習済みartifactは含めない。

証拠のネットワーク取得 **0**、実fit **0**、性能評価 **0**、実確率計算 **0**、T0登録 **0**、対象登録 **0**、将来予測保存 **0**。

**HISTORY / PREDICTION: HOLD。Phase A: BLOCKED / Phase B: NOT_AUTHORIZED。**
