# v7 個別備考解析契約

新しいv7は保存原本の純粋なオフライン解析関数であり、I/O・HTTP entry point・permit・worker・モデル・運用処理を持たない。strict parserとv2〜v6、旧個別ruleは不変である。共通分類器は未接続。

6件を独立に検討し、原文の肯定的な警告・交代記載と、該当する選手名簿・警告欄・交代欄・監督欄の対応を非公開registryへ記録した。1段落の警告だけでなく、複数の警告や交代説明の継続段落を全件審査する。コード・記号の競技規則上の意味、物理的中断の不存在、絶対的な終了・結果反映時刻は推測しない。

対象はregistry SHAと6個別rule SHAで固定する。fixture namespaceは百年構想とordinaryで異なり、公式詳細namespaceと混同しない。URL/ID、大会・年度・節、TeamMaster、日時・90分結果・PK/延長、source revision・元行、raw/metadata/request SHA、実取得UTC、A11全文・HTML・byte範囲・SHA、全paragraphの原文・順序・構造、対応欄のbyte範囲とSHAを完全一致で要求する。交代説明の継続文も全文を非公開の固定literalとして照合し、文型を一般化しない。

旧契約がUNKNOWN_FORMATとしてHOLD、strict parserと証拠整合が成立し、未確認の時刻注記がないケースだけ個別再審査する。旧PASSは結果全体をそのまま返す。未知paragraph・時刻注記の混在、意味・形式の不足はHOLD。原本SHA、identity、source revision、A11/対応欄の位置・原文等の証拠矛盾はEvidenceStopであり、備考HOLDへ格下げしない。文字列正規化・部分一致・緩い正規表現によるfallbackはない。文法チェックは固定済み証拠の追加検査であり、別試合を許可する分類器ではない。

新結果は旧取得・隔離とは別artifactとする。原本、packet、receipt、旧HOLDは保持する。詳細AがPASSでもB〜DはHOLDで、history admission要求を常に拒否する。v7を実HTTP取得や将来予測へ接続しない。
