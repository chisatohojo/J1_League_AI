# A：新しい個別備考解析契約

`reviewed_staff_warning_exact_witness_v4`は、一つの保存済みGKコーチ警告だけに追加の完全一致規則を適用する。既存strict parser、v2/v3 adapter、通訳・コーチreview-ruleは変更しない。旧v3がPASSした入力は、外側version以外の全semantic fieldを保持する。新しい役割や他試合へ適用範囲を広げない。

新規則はfixture identity、namespace、公式URL、大会・年度・節を含む完全見出し、TeamMaster両クラブ、日付・kickoff、90分結果、PK/延長を分離したstrict結果、元CSV・行・一覧のSHAを固定する。さらにraw/metadata/request SHA、実request開始・取得完了UTC、A11全文HTML・byte範囲・SHA、A10/A12との位置関係、備考見出し、唯一のparagraphのHTMLと原文を固定する。snapshot保存receiptは別の証拠レビューartifactで照合・保存する。

肯定的根拠は、試合中の分表示、明示的な警告表現とliteral code、クラブ・氏名、明示的な「（ＧＫコーチ）」が一つの原文に結び付くスタッフ警告の構造である。コードの規則上の意味は推測せず、物理的中断がなかったことも立証しない。PK結果を90分結果へ混ぜない。

新規則へ進めるのは、旧契約HOLDのうち、packet integrity・strict parserがPASS、時刻注記なし、旧備考分類UNKNOWN_FORMATの入力だけ。原文・HTML・位置・identity・取得UTC・証拠SHAが全て一致しなければHOLD。部分一致、緩い正規表現、正規化後の文字列一致へのfallbackはない。複数paragraph、未知注記、時刻注記を部分的に許可しない。

監督、通訳、コーチ、ＧＫコーチは別の役割として保持する。Bの候補分類器はimportも呼出しもせず、取得executorや通信permitはこの工程で作成しない。今回の79件PASSは独立artifactへ保存し、旧取得runの35 PASS / 1 HOLD / 209未取得を書き換えない。
