# v6 独立オフライン個別備考契約

既存strict parser、v2〜v5 adapter、既存4個別ruleは不変。[v6 adapter](exact_quarantine_review.py)はI/O、HTTP worker、通信permit、モデル、履歴採用へ接続しない。未実証の共通分類器もimportしない。

原本のSHAと既存v5解析を先に検証する。従来PASSの176件は結果全体をそのまま返す。新規則は、v5がUNKNOWN_FORMATでHOLDとなり、strict parserでidentity・結果・備考構造の検証が成立した3つの封印witnessだけに適用する。rule registry自体のSHA、正式fixtureの全row・URL・namespace・大会見出し・年度/節・TeamMaster・日時・90分結果・PK/延長・source revision・入力pinsを完全一致で要求する。

Raw／metadata／request SHAと実取得UTC、A11全HTML・byte範囲・SHA・隣接A10/A12位置、全paragraphのHTML・原文・正規化結果、肯定的な対象/役割/イベント文型を固定する。生HTMLや原文が変われば、正規化後に同じ文字列でも拒否する。コーチと全角表記のGKコーチは異なる役割のまま扱う。分表示と試合終了後という相対表現から実時刻を算出しない。

1件には確認済みの2段落があり、両方の交代対象を対応するA7交代イベント欄とも照合した。2段落そのものを順序込みで固定する。他の2件はそれぞれ1段落を固定する。複数段落を一律許可せず、未確認段落の追加・重複・入替・欠落・未知注記や時刻例外との混在はHOLDとする。

全文・位置・SHAによる一致と、肯定的に確認した文型の一致を両方要求する。時刻キーワードの不在だけを根拠にしない。別試合・別role・別文型へのfallbackは持たない。警告コードや交代記号の競技規則上/医学上の意味、物理的中断の不存在、結果利用可能時刻は推測しない。

新しい独立解析PASSは最終詳細Aの審査結果だけである。元の隔離packet・seal・receiptとPhase 2.5B-16の正式45 PASS／3 HOLDは保持する。時刻B・日程/告知C・予測時点取得証明DはHOLD。history admissionは常に拒否し、残り109件の取得許可にもならない。
