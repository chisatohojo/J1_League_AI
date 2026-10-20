# Phase 2.5B-7 備考解析契約

新adapterは `reviewed_staff_warning_exact_witness_v3`。旧strict parser、v2 adapter、既存の通訳警告規則を変更しない。旧契約がPASSした入力は、version以外の全semantic fieldを保持して返す。

新しいコーチ警告規則は、独立レビューした一つの保存snapshotだけを許可する。fixture identity・namespace・公式URL・大会・年度・節・両TeamMaster ID・日付・kickoff・90分結果・PK/延長属性、raw/metadata/requestのSHAと取得UTCを固定する。A11全体の原文HTML、開始/終了byte位置、SHA、A10/A12との位置関係、備考見出し、唯一のparagraphのHTMLと原文も完全一致を要求する。

肯定的根拠は、試合中の分表示、明示的な警告表現とliteral code、クラブ・氏名、明示されたコーチ役割が一つの全文として結び付く構造である。時刻語がないことだけでは許可しない。警告コードの詳細な競技規則上の意味は推測しない。

旧契約HOLDを再検討できるのは、packet照合とstrict parserがPASSし、時刻注記がなく、旧備考分類がUNKNOWN_FORMATの場合だけ。新規則の全文・構造・位置・証拠SHA・identityをすべて検証し、失敗時に部分一致や正規化文字列一致へfallbackしない。複数paragraph、未知注記、時刻注記はHOLD。他試合、別役割、別文型へ一般化しない。監督・通訳・コーチを同一役割として扱わない。

規則と実装のSHAはimplementation-sha256.jsonを参照。個別証拠と規則全文はローカルおよび別ドライブbackupに保存し、公開するテストは合成例だけとする。adapterに通信・取得executor・モデル・fit・推論・ファイル書込みのentry pointはない。

初期オフライン検証で、将来計画validatorが通常J1のidentity namespaceを詳細サイトのnamespaceと同一視する不具合を検出した。公式URL-IDの厳密照合を維持し、元台帳のidentityを保持する最終版へ修正。初期コード・失敗記録に対応するコードsnapshotを別保存し、最終版で43件の解析結果の一致と245件の計画を再検証した。通信・旧成果物への書込みは発生していない。
