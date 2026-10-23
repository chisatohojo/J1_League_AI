# Phase 2.5F — アクセス条件URL固定・A枠承認準備

判定：`NN_V2_BCD_PERMIT_DESIGN_PARTIAL`。基準はPhase 2.5Eの
`05789d0c422a6bdbbb2aee1a4fdbd1648d729539`。E成果物は変更しない。
URL・順序・上限・保存先設計を固定したが、現行の規約、robots内容、aboutj運営主体・適用範囲は未確認。
今回の成果は実行permitではなく、実取得はユーザーの別途明示承認を待つ。

## 固定したA枠（最大4 GET・各URL1回）

| 順序 | 正確な候補URL | 役割 | 本文上限 | 候補の根拠 |
| --- | --- | --- | --- | --- |
| A1 | `https://www.jleague.jp/robots.txt` | wwwのrobots確認先 | 64 KiB | 今回指定した静的な確認endpoint。保存href・実応答の証拠ではない |
| A2 | `https://aboutj.jleague.jp/robots.txt` | aboutjのrobots確認先 | 64 KiB | 同上。wwwの規則を流用しない |
| A3 | `https://www.jleague.jp/general/kiyaku/` | Jリーグ公式利用規約の既知候補 | 1 MiB | ユーザー指定と保存済み公式HTMLのliteral href |
| A4 | `https://www.jleague.jp/general/copyright/` | 著作権・利用案内の補助確認先 | 1 MiB | 保存済み公式HTMLのliteral href。自動取得許可の証明ではない |

全件HTTPS、正確なhost、暗黙port 443、query/fragmentなし。pathは上表のliteralを固定する。
明示`:443`、別scheme、別host、path/query違いへの置換も認めない。
redirectは同一hostを含め追従0。TLS証明書・hostname検証必須。
候補ごとのscheme/host/port/path・根拠SHAは[A_ACCESS_PLAN.json](A_ACCESS_PLAN.json)を参照。
HTTP status・応答SHA・初回公開時刻は未観測のためnull。現存、現行適用範囲、automated access許可はUNKNOWN。

Eでnullだったrobots URLを今回はユーザー指示に基づく設計候補として固定した。
これは実在・疎通・内容確認ではなく、既存原本やEの記録の訂正でもない。
aboutjの規約URLを推測で生成しない。別hostのプライバシーポリシーもAへ含めない。

## 保存済み資料とaboutjの未確定事項

502原本のraw/metadata SHAを再照合し、reference-only資料を含むHTMLをオフライン解析した。
aboutj自身の保存原本は0件、aboutjへのliteral参照は2,464箇所・7種類だった。
保存された公式wwwフッターの「プレスリリース」リンクは同hostへの参照を裏付けるが、
aboutjの運営主体による宣言、現在の利用規約、www規約のaboutjへの適用を裏付けない。
ドメイン接尾辞、ブランド、corporateというpathだけでは認定しない。
対象原本・metadata・HTML位置と全文は非公開台帳に保持し、公開物は集計とSHAのみとした。

[SAVED_HOST_EVIDENCE.json](SAVED_HOST_EVIDENCE.json)の7リンクは既存HTMLからの参照一覧であり、
新たなアクセス対象でも許可URLでもない。
初回監査scriptはDの候補抽出済み1 URLと原本全体の参照集合を同一視するassertionで停止した。
別versionの監査で全7種類を記録した。初回scriptを保持し、原本を変更していない。

必要な追加確認は、両hostの現在のrobots、利用規約本文と適用範囲、rate/UA等の制限、
aboutjの明示的な運営主体・規約である。Aの4候補だけでは全て解決しない可能性がある。
その場合はPARTIAL/HOLDを維持し、追加候補は別計画・別承認とする。
data.j-league.or.jpの過去robots 404は両hostに適用しない。

## 通信予算・実行順序・停止

現在の許可回数は0。以下は承認用の上限設計であり、通信コード・permit・有効化機構は作らない。

- A1→A2→A3→A4の固定順序。前件の原本・seal・receiptの読戻し、制限確認が終わってから次へ進む。
- 最大4 intent、各URL1回、retry0、parallel0、redirect追従0。失敗・timeout・完了不明も消費し、返却しない。
- 完了から次開始までhostをまたいでも最低5秒。より厳しいサイト条件を優先する。
- socket 10秒、親worker 12秒、cleanup 2秒、A全体120秒の有限deadline。
- 本文合計2,228,224 bytes、header上限32 KiB/応答、本文＋header上限2,359,296 bytes。
  TLS等を含む全wire量の保証とはしない。Accept-Encodingはidentity、不明encodingは停止。
- 取得予定UAは既存研究用文字列`J1AI-Research-Timing-Pilot/1.0`。Cookie保存・認証・ブラウザ操作なし。

Aは未知のアクセス条件を調べるための限定したbootstrap確認である。
事前の未知状態をサイト側の許可とみなさず、人による限定確認承認と、実worker/保存先/期限の再検証を必要とする。
robots 200でも本文審査なしに次へ進めない。404はそのURLに公開されたrobots規則を確認できなかったという意味に限り、
サイト全体の取得許可ではない。既知の拒否条件、適用制限の曖昧性があれば停止する。
この順序がサイトの条件と矛盾する場合も黙って並べ替えずHOLDする。

3xx、403/429、認証・CAPTCHA、アクセス拒否、不明な制限、TLS異常、timeout・完了不明、
上限・deadline・間隔違反、入力SHA変化、時刻逆行、保存先の異常、SHA/receipt不一致で全体STOP。
停止後の再開・再取得・URL代替・その場での規則変更をしない。失敗証拠を保持する。

ニュース`https://www.jleague.jp/j1/news/`と
プレスリリース`https://aboutj.jleague.jp/corporate/pressrelease/`はB枠入口であり、Aで取得しない。
A余剰をBへ移すことも認めない。EのB候補上限2回は設計参照だけで現在許可0。
A終了後は必ず停止し、Bは条件審査・別途明示承認を要する。
Eの全体最大6回という設計を、今回の6回取得承認と解釈しない。

## 固定した保存先設計

将来の保存root識別名は`NNResearch-phase2_5F-A-approval-pending-20261023-01`。
非公開台帳に正確な絶対rootとそのSHAを固定した。公開物にはroot識別名・台帳SHAのみを記載する。
今回はrootを作成していない。今回のオフライン監査領域とは別領域である。
各slotは`A/access-0001`〜`A/access-0004`、各々raw.bin、metadata.json、request.json、seal.json、receipt.jsonを保持する。

実通信前に、専用rootの未存在、owner/DACL、reparse/祖先identity、
runtime/model/source/predictionとの非重複を確認しexclusive-createする。
実行中も保存前・確定前に再照合する。既存出力の再使用・衝突時はHOLD。
新規owner/DACL等の実OS安全性を今回実証したとはしない。
UTCはrequest開始・応答完了・snapshot保存・監査完了を分離し、fsync/readback/SHAを必要とする。
旧原本・metadata・モデルへ書き込まず、新原本も取得後は不変保存する。
実worker・一度限りpermit・有効期限・コードSHAの封印は、明示承認後の別の接続前ゲートである。

## 検証と保護

新規86 PASS、関連回帰402 PASS、計488 PASS、FAIL/error/skip 0、warnings-as-errors。
このうち新規83件は拒否・STOPまたは混合negative-controlを含む。残る3件は正常な設計/合成記録と静的非接続検査。
HTTP応答は合成記録であり、実HTTP・DNS・TLS・OS隔離の実証ではない。
Python application guardでネットワーク・子process・実モデル処理・許可外書込みを拒否し、禁止操作試行0件だった。
Eの過去402 PASSを再計上したのではなく、今回の488件中に関連回帰として実際に再実行した。

新baseline 51,890保護ファイル。開始前との差分確認は[PROTECTION.json](PROTECTION.json)、
今回の静的検証・JUnit/実装SHAは[VALIDATION.json](VALIDATION.json)、入力根拠は[INPUT_PROVENANCE.json](INPUT_PROVENANCE.json)。
最終ファイルSHAは[SHA256-MANIFEST.json](SHA256-MANIFEST.json)。
main、モデル53 payload、旧288原本・旧隔離9件、公式publication、既存予測、
運用タスク定義/状態、他worktreeを保護する。過去のタスク失敗を修復・正常認定しない。
Git保存はユーザーが許可した通常commit/pushであり、証拠取得GET/HEAD/DNS probeとは分ける。

## 維持するゲート・承認対象

詳細Aの既存288 PASSと、証拠B/C/D各288 HOLDは不変。
HISTORY/PREDICTION：HOLD、Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
新規証拠GET/HEAD/DNS、permit発行/有効化、取得run再実行、モデルload/fit/推論、
性能評価、確率計算、履歴admission、T0/対象登録、将来予測保存はいずれも0。

次に承認対象となるのは**上表A1〜A4だけへの条件確認、合計最大4 GET・各1回**。
URL/順序/本文・header上限/停止条件/保存先を含めて明示承認を受け、その後に接続前ゲートを満たす必要がある。
今は承認を取得していない。B枠探索、記事、追加のaboutj資料取得、モデル・履歴採用は承認対象に含まない。
