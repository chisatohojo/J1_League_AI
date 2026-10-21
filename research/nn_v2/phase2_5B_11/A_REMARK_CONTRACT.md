# 監督退場の個別備考解析契約

新adapterは `reviewed_disciplinary_exact_witness_v5`。既存v4の上に、レビュー済みの保存packet1件だけを対象にした完全一致規則を追加する。旧strict parser、v2・v3・v4、通訳・コーチ・GKコーチの3規則を変更しない。汎用分類器をimport・呼出ししない。

新規則はfixture identity・namespace・正規公式URL、大会・年度・節の完全見出し、TeamMaster両クラブ、日付・kickoff、90分結果とPK/延長分離、固定CSV・行・一覧のSHAを固定する。raw/metadata/request SHA、実request/response UTC、A11の全HTMLとbyte範囲・SHA、A10/A12との位置関係、見出し、唯一のparagraphのHTMLと原文、明示された監督役割・退場表現・分表示・コードを固定する。

肯定的根拠は、監督役割を明記する退場文型と、隣接するホーム監督欄の人物名の一致である。選手退場の別テーブルには異なる人物・分表示があり、監督個人の退場、選手の退場、試合自体の中断・再開・打切りを区別する。実名・原文・個別identity・取得URLと全証拠はローカル封印artifactに保持し、公開文書には集計とSHAだけを記す。

分表示は記録上の試合中の分ラベルとして扱い、壁時計時刻、試合終了時刻、結果利用可能時刻へ変換しない。詳細な懲戒コードの意味は推測しない。原文に試合中断等の記述が見当たらないことから、物理的な中断が存在しなかったとは結論しない。

既存v4でPASSした115件はversion以外の全semantic fieldを保持する。新規則は別試合、監督警告、選手退場、未知の退場文型、複数注記、未知時刻注記へ一般化しない。今回の独立116件の合格は、旧runの正式36 PASS / 1 HOLD / 172未取得を書き換えない。

ネットワーク取得0、通信permit0、新executor0。旧取得経路は未知備考で全体停止する契約のまま。二段階候補は合成設計検討だけであり、導入・取得再開には別承認が必要。HISTORY/PREDICTIONと実結果event admissionはHOLD。
