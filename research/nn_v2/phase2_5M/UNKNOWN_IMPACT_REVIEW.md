# NN v2 Phase 2.5M — UNKNOWNの影響と通信再開条件

判定：`NN_V2_UNKNOWN_IMPACT_REVIEW_READY`

基準：Phase L `17017b6cce031f26347b3dd4aeef4a2c188d2ff0`。
専用branch：`feature/nn-v2-unknown-impact-review`。
本判定は影響分類・STOP条件・承認順序の整理完了を表す。通信再開や規範PASSへの昇格ではない。
新規通信、permit発行、UA採用、実adapter接続、設定変更は行っていない。

## 1. 結論と分類の範囲

**対象6 URL全体での最も強い優先度は2 P0／7 P1／0 P2／0 P3**。
wwwの固定A1原本と4 URLだけに限定すると **2 P0／0 P1／7 P2／0 P3** となる。
aboutjにはrobots原本がなく、wwwのP2証明は使えないため2 P0／7 P1を維持する。

分類の単位は「項目×原本SHA×完全URL×UA/token×parser/spec version」である。
P2はこの固定範囲で当該未解決機能に依存しないことを確認したという意味で、一般的な正しさを表さない。
原本・URL・UA・token・versionが変われば証明を再計算し、不成立ならP1、現に判定を壊す異常ならP0へ戻す。
P3には未使用と影響除外の両方の証明を要求するが、今回の正式9項目に該当項目はない。

| 正式ID | 6 URL全体 | www固定A1の4 URL | aboutjの2 URL | 現在の位置付け |
|---|---|---|---|---|
| `agent_grammar` | P0 | P0 | P0 | 候補は適合するが正式採用・実adapter binding未承認 |
| `rule_grammar` | P1 | P2 | P1 | A1の定義済み規則は対応構文。未知の次原本は証明なし |
| `longest_rule` | P1 | P2 | P1 | 四pathは一致規則0で順位選択に入らない |
| `reserved_octets` | P1 | P2 | P1 | A1規則と四URLにpercent escapeなし |
| `query` | P1 | P2 | P1 | 四URLとA1規則にqueryなし |
| `encoding_errors` | P1 | P2 | P1 | A1はASCII/valid UTF8、未対応recordなし |
| `parse_limits` | P1 | P2 | P1 | A1は全646 bytesを検証済み。64 KiB等の上限内 |
| `standard_examples` | P1 | P2 | P1 | 未解決例を修正せず、今回の判定で依存しない範囲を確認 |
| `sealed_A1_replay` | P0 | P0 | P0 | 候補付き規範結果と新requestの証拠・host適用・承認は別 |

正式ID・定義・RFC/Google section・旧挙動・判定履歴は `UNKNOWN_IMPACT_MATRIX.json` に元台帳のまま保持した。
元台帳には独立したname欄がないため、nameには正式IDをそのまま使い、名称を創作していない。
9項目は全てUNKNOWN、全24項目は **15 PASS／0 FAIL／9 UNKNOWN** のままである。

## 2. 限定範囲の証拠

A1 SHA：`3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c`。
Gのrequest/metadata/receipt/sealと、IのS1/S2原本・通信台帳・節anchorのSHAを再確認した。
原本は再取得・改変していない。`INPUT_EVIDENCE.json` に今回の読取り専用監査を記録した。

A1は646 bytes、25行、2 group、計20規則。固定token候補ではgroup1の`*`、19規則が適用される。
4 URLとも一致規則0。既存matcherのwork計測はA1=39、A3=38、A4=38、B1=40で有限上限内。
`/robots.txt` の暗黙URI結果は変更せず、work計測だけ既存の純粋matcherで再確認した。
個別規則全文は公開せず、group・件数・判定・context hashを保存した。

`impact_review.py` は既存K v4とLの候補/hash契約を再利用する分析専用コードである。
参照SHA・完全URL・UA/token・spec pin・parser versionと測定結果をhashに結合する。
これは分析を再現するための記録であり、署名された証明書や実行能力ではない。
正しいrawでも、別URLや別hostに同じ証明を流用することを拒否する。

## 3. 各UNKNOWNの依存と解消範囲

詳細なfalse-ALLOW／過剰拒否リスク、追加証拠、I/J/Kの差分はmatrixの項目別記録を正本とする。
過剰拒否はUNKNOWNによる運用停止を含み、規範判定を誤ってDENYと記録する意味ではない。

- `agent_grammar`：文法と候補bindingは検証済み。G1の採用とG2の新request構築/最終header検査が必要。
  実送信値の証明は別であり、過去のUA UNKNOWNを現在のコードから補完しない。
- `rule_grammar`：RFC2.2 ABNFと5.1例の矛盾、tolerant recoveryを未解決として保持する。
  A1全定義規則が対応構文であることはオフラインで確認可能だが、矛盾そのものの和解ではない。
- `longest_rule`：literal長とGoogle marker寄与の順位が一致しなければ従来どおりUNKNOWN。
  一致0の現pathは隔離できるが、競合規則を含む別pathは再審査が必要。
- `reserved_octets`：unquote-allを採用せず、未対応reserved contextをUNKNOWNで止める。
  S1が参照するRFC3986等の不足原文が必要なら、実リンク候補の固定と別取得承認が必要。
- `query`：J/Kの検証済みASCII key=value subsetを維持し、複雑なqueryの一般化を行わない。
  Bのpaginationや検索parameterを現URL集合に追加してはならない。
- `encoding_errors`：不正UTF8/HTML/不正行のtolerant recoveryは未完了。
  A1の正常encodingを次の未知原本へ流用しない。
- `parse_limits`：64 KiB capはRFCの最低500 KiB parser能力を満たさない。今回もfull conformanceは宣言しない。
  上限を増やす場合は別版・資源試験・取得上限の独立審査が必要。切捨てた先頭部分を全原本と扱わない。
- `standard_examples`：RFC5.1/5.2の不整合を保持する。必要な公式clarification等は未取得であり、読んだことにしない。
  `rule_grammar`／`longest_rule`／`reserved_octets`との関連を記録する。
- `sealed_A1_replay`：固定候補での再計算は可能だが、host証拠・新request capture・site条件・新permitが必要。
  aboutj原本欠落と過去UA欠落は別問題。新規取得で過去のPIT/送信値を遡及立証できない。

matrixの依存graphは完全な規範能力の調査順序である。
限定scopeの承認に、全9項目の規範PASSを無条件に要求するgraphとは区別する。
未知の影響を限定範囲から除外できなければP0/P1として停止し、P2ラベルだけで通さない。
旧K/Lの証拠層UNKNOWNや判定履歴も変更していない。限定scope証明を将来の証拠gateへ採用すること自体、G2/G3の別審査事項である。

## 4. URL別の現在状態

UA/tokenはLの固定候補で、状態は `CANDIDATE_FROZEN_NOT_ACTIVATED`。
実送信UAはUNKNOWN。candidate指定での仕様判定と実行権限を分離する。

| ID・完全URL | 規範層 | group・規則 | 証拠層 | permit層 | 最終通信 |
|---|---|---|---|---|---|
| A1 `https://www.jleague.jp/robots.txt` | 条件付きALLOW | `*`、一致0、暗黙URI例外 | UNKNOWN | UNAPPROVED | 不可 |
| A3 `https://www.jleague.jp/general/kiyaku/` | 条件付きALLOW | `*`、一致0 | UNKNOWN | UNAPPROVED | 不可 |
| A4 `https://www.jleague.jp/general/copyright/` | 条件付きALLOW | `*`、一致0 | UNKNOWN | UNAPPROVED | 不可 |
| B1 `https://www.jleague.jp/j1/news/` | 条件付きALLOW | `*`、一致0 | UNKNOWN | UNAPPROVED | 不可 |
| A2 `https://aboutj.jleague.jp/robots.txt` | UNKNOWN | host原本なし | UNKNOWN | UNAPPROVED | 不可 |
| B2 `https://aboutj.jleague.jp/corporate/pressrelease/` | UNKNOWN | host原本なし | UNKNOWN | UNAPPROVED | 不可 |

全URLで、正式候補採用未承認、実adapter capture未qualified、新permit/G4開始承認なし、
適用条件または限定条件確認scope未審査、新requestの鮮度/scope policy未固定が直接STOP理由となる。
aboutjはさらにrobots原本・運営主体・規約適用範囲がUNKNOWN。
wwwの条件付きALLOWでこれらを代用しない。A3/A4本文、B入口本文も未取得で現在の存在・内容を断定しない。
各層の入力・停止理由・解除条件は `URL_STOP_MATRIX.json` に完全URL単位で記録した。

**Aの条件確認とBの探索を分ける。**
Fの既存設計には、別の明示的・限定的な承認を得てから条件確認だけを行うbootstrap原則がある。
これは旧承認の再利用や一般的なUNKNOWN→ALLOW規則ではない。
aboutj初回robotsや未読規約の確認を検討するなら、G2/G3で新しい条件確認scopeとして扱いを明示審査する。
既知の禁止・より厳しい条件を優先し、扱いを承認できなければHOLD。
現在のK parserのaboutj UNKNOWNを変更する機能や、bootstrap実行profileは今回実装していない。
条件確認Aで許可候補を確認できても、Bにはhost固有の規約・自動取得条件の審査と別permitが必要である。
B1の前提に無関係なaboutj取得を自動で追加せず、B2にwww原本を流用しない。

旧Gは終端STOPのまま。A2〜A4の未実行分を残予算として復活させず、仕様取得Iの承認も流用しない。
A1の再取得は今回も次の残りA計画にも含めない。鮮度policyがrefreshを必要と判断した場合、同URLの再取得を別途明示承認する。
404は当該robots URLに公開規則が確認できなかったという意味に限り、サイト全体の許可と解釈しない。

## 5. E0〜E4と循環しない通信前後のgate

| 時点 | 必要なもの | まだ存在しなくてよいもの |
|---|---|---|
| 通信前 | G1採用判断、G2でcapture/保存/停止mechanismをmockでqualified化、新G3 permit、G4開始承認、そのrequestのE0/E1 | そのrequestの実E2/E3 |
| 通信後 | 実E2開始/最終header/outcome、実E4原本・receipt読戻し、承認scopeに応じたE3観測状態 | 過去の欠落headerの遡及証明 |

E0設定値、E1構築入力、E2 client送信処理、E3独立観測、E4応答保存の区別を維持する。
実E2/E3が必要だからといって、同じrequestの初送信より前にその実証を要求する循環を作らない。
事前に確認するのは、送信直前の最終header照合、attempt課金、開始/完了の不変記録、保存検証、異常時停止の仕組みである。
現在のE2/E3は未実証であり、今回の合成試験を実送信証明と呼ばない。

G3ではE3が必要か、その観測方法と成立条件を明示する。
必要なら方法の成立性・独立性・TLS/privacyを先に審査し、実観測はG4後に検証する。未成立ならSTOP。
E3を取得scopeに含めないことを明示承認した場合は、E3をNOT_OBSERVED/UNVERIFIEDと記録し、E2やE4から独立送信観測へ昇格しない。
要求E3をその場で任意化しない。暗号化pcapのみ、MITM、復号、証明書変更等を無条件に認めない。
Lの5 facet全てを揃える合成整合性試験と、将来live取得前後に必要な証拠の選択を混同しない。
Lのschema/validatorを変更・本番化していない。live適用は別設計・別承認である。

E2 STARTEDだけ、timeout、送信完了不明、raw/receipt/readback欠落ではSTOPし、attemptと不完全証拠を保持する。
予算を未消費に戻さず、自動retry・自動再開で補わない。

## 6. G1〜G4の独立承認

1. **G1：正式UA/token採用判断**。候補hashと根拠を確認する。運用設定への反映は別承認で、GETやpermitを許可しない。
2. **G2：実adapter結合準備**。固定code、E0/E1/最終header、E2/E4 capture、保存identity、時計、競合・停止、scope証明と鮮度policyを審査する。
   実通信は行わない。E3を要求する場合は独立観測方式のqualification、条件確認Aではbounded bootstrap境界も審査する。
3. **G3：新しい限定permit**。完全URL・host/443/GET・UA/token・code/source hash・UTC期限・回数/body cap・保存先・証拠要件・STOP条件を固定して承認する。
   旧G/Iを再使用しない。Aは条件確認のみ、Bは別承認。未確定fieldがあれば発行しない。
4. **G4：承認済みrunの開始と通信後監査**。G3等を再照合し、明示的な開始承認の範囲だけを一度実行する。
   request単位でE2/E3/E4の成立範囲と原本保存を確認し、次URL前のcheckpointを設ける。

順序はG1→G2→G3→G4開始→G4通信後審査。
新しい指示がG3発行とG4実行を明示的に両方承認する場合も、各scope・判定・証跡を分ける。一方だけの承認を他方へ流用しない。
現時点では全gate未承認である。

`APPROVAL_GATES.json` の上限は承認準備用の設計値で、permitではない。
残りAはA2/A3/A4の最大3件、B入口はB1/B2の最大2件を別枠で検討できるが、現authorityは全て0。
各URL1回、redirect/retry/parallel=0、完了後最低5秒、socket10秒、parent12秒、cleanup2秒、global120秒の有限枠を提案する。
body capはA2=64 KiB、A3/A4=各1 MiB、B1/B2=各2 MiB。条件が厳しければそちらを優先し、枠を黙って拡張しない。
新しいpermitで対象・順序・鮮度・保存先・期限を固定するまで実行不可。A失敗後の自動skipやBへの予算移送も許可しない。

## 7. 検証と保護

最終 **1,092 PASS／0 FAIL／0 ERROR／0 skip**、warnings-as-errors。
新規M127件、回帰再実行965件。新規の明示negative-controlは87件。
P0/P1/P2/P3の証明要件、scope不一致、UA/token変更、不正規則、順位競合、query/escape、上限超過、
承認不足、旧予算再利用、E2/E3の事前捏造、送信後証拠不足、未承認URLを検証した。
JSON Schema形状検査に加え、正式ID/定義/履歴、source SHA、各scopeの件数・参照、承認graphを静的検査した。

中間の1,086 PASSは公開matrix/schema参照試験6件の追加前の証跡として保持する。
Lの965 PASS／static62は過去証跡であり、今回の965回帰再実行と分けて記録した。
application guardで通信/DNS/子process/実model/許可領域外writeを拒否し、禁止操作試行0。
OS network隔離や実E2/E3、安全なlive adapterを実証したとは主張しない。

新baseline **60,515ファイル**、SHA・identity・metadata差分0、モデル53 payload検証済み。
L baselineからの事前差分0。既存予測、288原本、A1/S1/S2、台帳・witness・旧隔離9件、ID30700、UA契約、旧新版parser/collector、
タスク定義・状態、main/他worktreeを維持した。定時処理・ブラウザ・既存processを操作していない。
過去の独立運用事象は既存記録のまま保持し、修復・cleanupをしていない。

## 8. 次工程

まずG1の候補採用判断と、G2のオフラインadapter結合・capture/保存/停止のqualification設計を別承認で進める。
aboutjや規約の条件確認を行う場合は、そのbootstrap境界・対象集合・順序を明示審査する。
まだG3 permitを作成せず、G4通信も開始しない。
一般化した規範能力については、残る原文不足・不整合・未実装を項目別に継続審査する。

新規GET/HEAD/DNS probe・資料取得・permit発行/有効化・失効予算復活・正式採用・実adapter接続・設定変更・model実行/評価・T0・履歴/予測登録は0。
通常Git pushは依頼された成果物保存に限り、証拠取得やpermitとは別である。
B/C/D各288 HOLD、HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持する。
