# 個別規則の差分

| 項目 | v4 | 新しいv5 |
|---|---|---|
| 元strict parser・v2〜v4・3 review-rule | 封印済み | ファイル・適用範囲とも不変 |
| 従来のPASS | 115件 | 外側version以外の全semantic fieldを保持 |
| 新しい審査対象 | 監督退場注記1件がUNKNOWN_FORMAT | 原本とidentityの完全一致で、この1件だけ追加レビュー |
| 許可する意味 | 既存の最終詳細備考分類 | 保存済みの特定の監督個人の退場注記を非時刻注記として分類 |
| 時刻証拠・履歴採用 | 別監査が必要 | 同じくHOLD、結果event admissionなし |
| 未知の退場・別試合 | HOLD | HOLD |
| 共通分類器・二段階候補 | 未接続 | 未接続 |

v5は、既存v4でHOLDとなった対象のうち、証拠packet検証とstrict最終詳細検証が成立し、備考がUNKNOWN_FORMATで時刻注記を含まない対象だけを再検討する。肯定的な監督役割・退場文型に加え、封印した試合・URL・大会・年度・節・TeamMaster・日時・90分結果・原本SHA・取得UTC・A11全文とbyte位置・唯一のparagraphが一致する必要がある。部分一致や正規化後の同値へのfallbackはない。
