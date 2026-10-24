# NN v2 Phase 2.5L — User-Agent候補と送信header証跡契約

判定：`NN_V2_UA_EVIDENCE_CONTRACT_DESIGN_VERIFIED`

基準：Phase K `8a89ddd83e1cd1e210e0a55ac8218d0712f3ed3f`。
専用branch：`feature/nn-v2-ua-evidence-contract`。
今回の合格はオフラインの設計・純粋関数・合成検証に限定する。
正式UA採用、実E2／E3観測、permit発行、取得再開の承認ではない。

## 1. 設計上の固定候補

| 項目 | 固定値 |
|---|---|
| HTTP User-Agent | `J1AI-Research-Timing-Pilot/1.0` |
| robots product-token | `Research-Timing-Pilot` |
| 状態 | `CANDIDATE_FROZEN_NOT_ACTIVATED` |
| 設定revision | `NNV2_L_UA_CANDIDATE_V1` |
| 証跡schema | `NNV2_UA_EVIDENCE_V1` |
| request表現 | `NNV2_UA_PREPARED_V1` |

保存済みS1 RFC9309の2.2／2.2.1とKの審査を再確認した。
tokenはASCII英字・underscore・hyphenだけで構成され、上記header内に含まれる。
RFCの包含SHOULDを、J1AIでは明示tokenとheaderの必須bindingとして扱う。
header全文にはdigit・versionがあるため、全文をproduct-tokenにしない。
抽出・digit削除・改名・別tokenへのfallbackは行わない。
S2のGoogle固有の名前照合をJ1AIへ一般化しない。
根拠の原本SHA・取得UTC・request/metadata SHA・節anchorの読戻し照合は `INPUT_EVIDENCE.json` に記録した。

`USER_AGENT_CANDIDATE.json` は設計候補の固定記録である。
既存取得器・HTTPライブラリの設定・本番config・旧permit・旧parserを変更していない。
候補objectのcanonical hashを `header_configuration_hash` として使用する。
実送信User-Agentは引き続きUNKNOWN。

## 2. E0〜E4の証明範囲

E0〜E4は別々の証拠facetであり、数字の大きい記録から小さい記録の存在を推定しない。

| facet | 必要な証拠 | 証明しないこと |
|---|---|---|
| E0 設定 | 候補・revision・設定hash・request/permit IDとの対応 | request構築、送信、permit承認 |
| E1 構築 | method・完全URL・header・ID・canonical bytesとSHA | clientが送信したこと、wire上の値 |
| E2 送信処理 | adapter identity/revision/code SHA、開始と完了／失敗イベント、最終header、UTCとoutcome | 独立したwire観測、server到達 |
| E3 独立観測 | 別observer、成立した観測方法、method/URL/header/ID照合、UTC、観測hash | E1/E2の自己記録だけによる独立性、暗号化pcapからの平文header読取り |
| E4 応答・保存 | status、限定metadata、raw SHA、保存identity、readback SHA | 実際の送信User-Agent、E3、先行facetの自動成立 |

`EVIDENCE_LEVEL_MATRIX.json` に要件・限界・今回の検証範囲を分離した。
全facetについてschemaと合成入力の整合性を検証したが、実環境のE2／E3／E4 filesystem動作は未実施である。
合成E3のobserver名が異なることを検査しても、実際の組織・process・capture経路の独立性を立証したとは扱わない。
hashは改変検出とbindingの材料であり、署名・信頼できる取得主体・絶対的な時計真正性を保証しない。

## 3. SchemaとUNKNOWN

`REQUEST_EVIDENCE_SCHEMA.json` はJSON Schema draft 2020-12形式。
`$schema` URIは仕様識別子として記録し、今回取得していない。全`$ref`はローカル`$defs`である。
schema形状検査に加え、`verify_record` によるhash・identity・時刻・facet固有の意味検査を必須とする。
JSON Schemaの形状検査だけで証跡を合格にしない。

共通必須fieldには、schema/version、request/execution/permit ID、source revision、完全URL、method、
intended UA、token、configuration/prepared hash、adapter identity、evidence level、UTCと時計源、
outcome、response status/hash、storage identity、readback、failure reasonを含む。
さらにscope・simulated・retroactive・run開始UTC・facet payload・record hashを固定する。

そのfacetで未観測の値は明示的null。空文字や成功値でUNKNOWNを代用しない。
例としてE1ではresponse/storage/transport値はnullでなければならない。
各facetを成立させる必須証拠がnullなら不完全記録として拒否し、該当facetを成功と数えない。
capture UTC自体が不明な記録も合格にできない。将来の保存層は不完全artifactと失敗理由を保持し、値を推定補完しない。
`evaluate_chain` は欠落facetを `missing_levels` に残し、UNKNOWNを伝播する。
E4には応答受領UTCと保存検証UTCを分けて持たせる。単にreceipt順が昇順でも、構築が送信開始後、観測・応答が送信開始前、
保存検証が応答や送信完了より前、といったfacet間の矛盾は拒否する。保存検証に失敗した場合、その完了UTCはnullとする。

今回のschemaとvalidatorは `SYNTHETIC_ONLY`、`simulated=true`、`retroactive=false` に限定する。
IDには `syn-` namespace、URLには `synthetic.invalid`、storageには `SYNTHETIC_MEMORY` を要求する。
実URL、旧G/I permit、旧request ID、実保存先を指定して動かす機能はない。
実用化には別審査のlive schema／adapterが必要であり、scope文字列の置換だけで本番化しない。

## 4. Canonicalizationとhash対象

共通bytes形式は、キー昇順・空白separatorなし・ASCII escape・NaN禁止のJSONにLFを1個付加したもの。
ASCII／UTF-8で同一bytesとなり、SHA-256を計算する。

| hash | 対象 |
|---|---|
| `header_configuration_hash` | 固定候補object（revision、UA、token、state、activated） |
| prepared request `sha256` | `canonical` objectのみ。schema、method、URL literalと構成要素、headers、各ID、source、候補と設定hash |
| `record_hash` | `record_hash` 自身を除くrecord全体 |
| `observation_hash` | 自身を除くobservation payload全体 |
| `response_hash`／readback hash | 合成response bytes／合成readback bytesそのもの |

- methodは厳密なGETのみ。URLのscheme/host/effective port/path/queryと元literalを保持する。
- percent escapeの大小・encoded/unencoded表記・query順・明示`:443`・末尾`?`等を黙って同一化しない。
- fragment、userinfo、制御文字、CR/LF、dot segment、不正percent、未承認originを拒否する。
- header名はASCIIで検査し、小文字化して昇順にする。入力順と名前のcaseだけは同一canonicalとなる。
- 値は変更しない。先頭末尾空白、tab、CR/LF、非ASCII、不正文字はtrimせず拒否する。内部空白の違いはhashに残す。
- 大小文字を無視した全header重複を拒否する。特にUser-Agentは唯一かつ固定値完全一致を必須とする。
- HostとURL、X-J1AI-Request-IDとrequest IDを照合する。実行・permit・source IDもhashに結合する。
- proxy/clientがheaderを追加・変更した最終表現はE1と再照合し、想定外ならSTOP。暗黙の差し替えを受容しない。

canonical JSONはHTTP/1 serializationやHTTP/2 framingのwire bytesではない。
hash一致は、ネットワーク上のheader一致を独立に証明しない。
URLのcanonicalizationとrobotsのpath規則を混同せず、K parserが未対応query等をUNKNOWNにした場合は通信候補も不成立とする。

## 5. 秘密情報の境界

証拠headerはUser-Agent、Host、Accept、Accept-Encoding、Connection、専用request IDだけを許可する。
Cookie、Authorization、Proxy-Authorization、API key、Set-Cookie、未知headerは構築前に拒否し、値を証跡やエラーへ出さない。
response metadataもstatus/content-type/bytes/request IDだけで、任意response headerを複製しない。
query名は合成用allowlistに限定し、認証token等を含む未審査queryを拒否する。
これらは一般的な秘密情報検出器ではない。許可fieldに秘密を埋め込めば自動検出できる、とは主張しない。
将来のlive記録では完全URLと許可field内容を事前審査し、機密原本は非公開領域、Gitは仕様・集計・SHAに限定する。

## 6. 将来の送信・保存順序（未実装・未承認）

1. 新しい限定permitと明示候補設定を照合し、source/robots/期限/予算/保存先/code identityを固定する。
2. E0設定証拠を封印し、E1構築表現を作る。clientが実際に使う最終headerを送信直前に再照合する。
3. 一度きりattemptを、接続状態が不明になっても消費済みと扱う。E2開始を保存してから送信処理へ進む。
4. 開始のみ・timeout・途中切断はCOMPLETEDにしない。失敗／UNKNOWNを保持し、自動retry・再実行で補完しない。
5. 実E3を主張する場合は、別承認された観測方式・独立性・IDと時刻の対応を証拠化する。
6. E4はraw、限定metadata、request/transport証跡、storage identityと各hashをcreate-newで保存する。
7. flush/fsync、読戻し、SHA、seal／receipt確定を確認してから次の処理へ進む。保存不全ならSTOPし証拠を残す。

現在のE2 payloadは合成イベント列の閉じたsnapshotであり、実adapterのappend-only journal実装ではない。
実装時は開始ログ・完了ログ・異常終了の不確定状態を不変artifactとして関連付け、旧記録を上書きしない。
UTC／時計源とmonotonic時計の対応、逆行、observer間の時計整合は将来の動的ゲートで検証する。
ローカルUTCだけで絶対時刻真正性を証明しない。

E4のメモリbytes比較を、実ファイルのflush/readback検証とは呼ばない。
ACL・reparse防御・exclusive-create・所有権・receipt crash整合・Windows永続性は、次の独立した結合試験で確認する。
本工程ではfilesystem保存adapterも実transportも起動していない。

## 7. TLSと独立観測

HTTPSの暗号化pcapだけでは平文のHTTP headerを確認できない。
E2のclient内部header記録を、そのままE3へ昇格させない。E4応答もUA実送信の証明にはしない。
現在受け付けるE3 methodは合成fixtureの `SYNTHETIC_INDEPENDENT_OBSERVER` だけである。
実観測の方式はUNKNOWN。TLS復号、MITM、証明書変更、proxy、key log、外部echoへの通信は承認されていない。
必要性・機密情報・独立性・変更範囲・復旧・正確な通信予算を別途審査する。

## 8. 三層の結合とA1

`evaluate_layers` は同じ合成prepared requestからKの規範評価、証拠chain、synthetic plan検査を再計算する。
裸のALLOW要約を受け取って有効化する方式にしない。

| 層 | 条件 |
|---|---|
| Layer 1 | 固定UA/token・原本SHA/spec pin・group/pathのK評価がALLOW。unknown pathや安全STOPを迂回しない |
| Layer 2 | schema・hash・identity・時刻・全必須facetの合成整合が成立。欠落はUNKNOWN、矛盾／失敗はDENY |
| Layer 3 | synthetic planの完全URL・method・UA/token・各ID・設定hash・期限・未使用予算・redirect/retry/parallel=0・保存先が一致 |

全条件成立時のALLOWは合成上のlogical candidateだけで、execution/B/history権限は常にfalse。
planは検査用入力であり、発行・消費・保存・署名・live permit受理を行う機能はない。
旧G/I permitを新契約に拡張せず、A2〜A4やB枠に対する通信承認を生成しない。
実運用の事前gateはその時点で取得可能な証拠とadapterの資格を確認し、送信後のE2/E3を「送信前に存在した証拠」として要求・捏造しない。
今回の全facet合成行列は契約整合性試験であり、live事前許可algorithmではない。

A1は既存原本とK v4を使って再計算し、Kの全結果との一致を確認した。

| 完全URL | 固定候補によるLayer 1 | Layer 2 | Layer 3／通信 |
|---|---|---|---|
| `https://www.jleague.jp/robots.txt` | ALLOW（`*`、暗黙URI例外あり） | UNKNOWN | UNAPPROVED／false |
| `https://www.jleague.jp/general/kiyaku/` | ALLOW（`*`、一致規則なし） | UNKNOWN | UNAPPROVED／false |
| `https://www.jleague.jp/general/copyright/` | ALLOW（`*`、一致規則なし） | UNKNOWN | UNAPPROVED／false |
| `https://www.jleague.jp/j1/news/` | ALLOW（`*`、一致規則なし） | UNKNOWN | UNAPPROVED／false |

候補未宣言なら既存の1 ALLOW／3 UNKNOWNを維持する。
正式token未採用、過去の送信header直接記録欠落、未解決規範、未確認アクセス条件、permit未承認は変わらない。
A1/S1/S2に新schemaのE0〜E3記録を遡及作成していない。旧E4相当の応答／保存事実を確認しても送信headerはUNKNOWN。
aboutjはhost固有原本がないためUNKNOWN。

9規範項目はJ/Kの正式IDを引き継ぎ、UNKNOWNを維持する。
`agent_grammar` と `sealed_A1_replay` に候補固定・将来証跡設計を追加したが、過去の実送信証拠を補えたとは扱わない。
全24項目は15 PASS／0 FAIL／9 UNKNOWN。B/C/D各288 HOLD、HISTORY／PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持する。

## 9. 検証と保護

最終 **965 PASS／0 FAIL／0 ERROR／0 skip**、warnings-as-errors。
新規L272件、回帰再実行693件。新規の明示negative-controlは213件、三層組合せ行列は27件。
Canonical hash、URL/header差、重複、CRLF、UA/token/ID/revisionの不一致、証拠欠落・昇格拒否、時計逆行、client最終header変更、
HTTP失敗、保存不完全、旧permit／遡及付与拒否を検証した。
JSON Schemaは同梱meta-schemaとローカルrefで検査し、実通信を使っていない。

初回931 PASSは必須facetのnull拒否等の追加前、958 PASSはfacet間時刻整合の追加前の中間証跡として保持する。
Kの693 PASS／static63は過去証跡であり、今回の回帰再実行と区別する。
テストprocessのapplication guardでnetwork/DNS/子process/実model/許可領域外writeを拒否し、禁止操作試行0を確認した。
OSレベルの通信遮断や実transport安全性を証明したとは扱わない。

新baseline59,264ファイルに対し、SHA・identity・metadata差分0。
モデル53 payload、予測、288原本・旧隔離・receipt・witness、ID30700、旧UA/collector/parser、main／他worktree、タスク定義・状態は不変。
前K baselineからの事前差分も0。Kで分離した07:00タスク失敗は既存記録として保持し、再実行・修復していない。
詳細は `VALIDATION.json`、`PROTECTION_VERIFICATION.json`、private原本監査へ分けて保存した。

## 10. 次工程で必要な承認

1. 正式UA/token採用と実取得器へ組み込む変更範囲・code revisionを、改めて承認する。
2. live request構築・最終header capture・E2 journal・保存層・時計・crash停止を、まず隔離／mockで検証する工程を承認する。
3. E3実観測を行う場合、観測方法と独立性・TLS上の成立性・privacy・変更と復旧を別承認する。
4. 実通信には、新しい限定URL集合・host・GET上限・各1回・UTC期限・redirect/retry・保存先を明示承認する。旧予算は復活させない。

今回はGET/HEAD/DNS probe、資料取得、permit発行、実送信、UA設定変更、collector実行、model load/fit/推論/評価、T0、履歴・予測登録、本番task操作は0。
依頼された通常Git pushは成果物保存に限り、証拠取得や通信permitとは別である。
