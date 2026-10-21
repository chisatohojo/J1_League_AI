# Phase 2.5B-11 監督退場注記の独立オフラインレビュー

判定：**READY_FOR_NEW_BOUNDED_ACQUISITION_APPROVAL**。保存済み116件の独立解析は **116 PASS / 0 HOLD**。従来115件は外側version以外の全semantic fieldが一致し、停止対象1件だけを新しい個別規則で再分類した。残り172件の取得実行は未承認。

開始branchは`feature/nn-research-v1`、HEAD `4e3ae5a33e1256b3762362be396765f80847f6be`、study `nn_v2_residual_20261020_01`。モデルは`TRAINED_AND_SEALED_RESEARCH_ONLY`。モデルsealと53 payload、固定入力、旧parser・v2〜v4・3 review-rule、原本、停止receipt、main、他worktreeを照合した。[入力SHA](input-sha256.json)。

原文の唯一のA11備考paragraphは、明示された監督役割と退場表現、分表示、literal code、所属・人物を一つの記録として示す。A10ホーム監督欄の人物と一致し、A9の選手退場欄とは人物・分表示・構造が異なる。これを試合自体の中断・再開・打切りと同一視しない。懲戒コードの詳細な意味や結果反映時刻は推測せず、中断が存在しなかったことも立証していない。[レビュー集計](review-summary.json)。

新v5は原本・metadata・request SHAと実取得UTC、試合全identity、日時・90分結果、A11全文・HTML・byte位置・SHA、唯一のparagraphを完全一致で固定する。旧v4でUNKNOWN_FORMAT、packet/strict検証成立、時刻注記なしという前提を満たす特定packetだけを追加審査する。既存ファイルは変更せず、汎用化・部分一致・同値正規化fallbackを導入していない。[契約](A_REMARK_CONTRACT.md)、[差分](CONTRACT_DIFF.md)、[実装SHA](implementation-sha256.json)。

合成・関連回帰テストは **617 PASS / fail0 / error0 / skip0、warnings-as-errors**。新規100件（監督規則66件、設計比較34件）と既存517件で、役割・警告/退場・試合中断の区別、混在・別試合・identity/日時/クラブ/結果/SHA/HTML/原文/byte位置の改変拒否、旧3規則の不変、共通分類器未接続、ネットワーク・モデル処理・運用書込みを持たないadapterを検証した。[テスト](synthetic-test-results.json)。初回の警告回帰fixtureは警告文に退場コードを組み合わせていたため、従来の警告文型へ修正して再検証した。adapterや原本を変えてテストを通していない。失敗時のJUnitも別途保存した。

開始監査scriptの移植時に原本照合のbaseディレクトリを取り違えたため、正しい同工程の原本へ修正した。修正後は全SHA一致であり、実入力の改変ではなかった。レビューrunnerの入力rule参照先の移植ミスも出力作成前に修正した。これらは新規オフライン監査の実装過程として記録し、旧停止runを変更していない。

二段階方式は **TWO_STAGE_DESIGN_CANDIDATE_SYNTHETIC_ONLY**。未知備考だけを隔離して他URLの証拠取得を継続する案と、現行の全体停止方式を純粋な合成モデルで比較した。通信・403/429・アクセス制限・TLS・timeout・identity/結果/SHA矛盾・上限超過・重複等は候補でも全体STOP。隔離した未知時刻注記を通常試合へ採用する機能はなく、履歴admissionは常に0。正式取得経路にはimport・接続していない。実HTTP・crash復旧・隔離運用の安全性は未立証であり、導入は別承認。[設計とリスク](TWO_STAGE_DESIGN.md)。未実証の共通備考分類器の判定も変更していない。

元288件＝既取得116件＋未取得172件を完全照合し、URL/ID重複・集合重複0。未取得台帳SHAは指定値に一致し、保存済み公式実リンクを検証済みの前工程209件の不変suffixである。計画は12件×14バッチ＋4件×1バッチ。新executorとpermitは作成していない。[次回計画](remaining-acquisition-plan.json)。

保護対象14,116ファイルとモデル53 payloadのSHAは不変。今回の運用出力差分0、タスク重複なし、07:00/22:00タスク定義とmain・他worktreeも不変。過去の未帰属11件と前工程で独立確認した07:00タスクの10件の可変出力を区別し、通常更新や研究変更へ根拠なく一括帰属しない。[保護監査](protection-verification.json)。

旧Phase 2.5B-10の正式 **36 PASS / 1 HOLD / 172未取得** は不変。今回の116件は別artifactにSHA封印し、原本コピー・全解析・規則・時刻・入力SHA・停止証拠とともに別ドライブbackupした。ZIP CRC・全payload SHA・独立展開・独立読戻しは一致。[backup検証](backup-verification.json)。個別identity、実名、raw、metadata、個人パス、モデルartifactはGitへ追加していない。

最終詳細Aの独立合格は、Bの実イベント/結果利用可能時刻、Cの当初日程・変更告知、Dの予測時点までの取得証明を代替しない。B〜Dと実結果event admissionは引き続きHOLD。

**HISTORY / PREDICTION：HOLD**。新規ネットワーク取得0、通信permit0、実fit0、性能評価0、実確率計算0、T0登録0、対象登録0、将来予測保存0。Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
