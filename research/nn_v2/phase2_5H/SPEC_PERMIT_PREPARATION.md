# Phase 2.5H — 公式仕様URLと独立した取得permit案

判定：`NN_V2_ROBOTS_PARSER_PARTIAL`。
今回の作業は、ユーザー指定URLの記録、未発行のpermit案、原文取得後の検証計画、
既存ローカル実装・証拠を使ったオフライン検証に限定する。
RFC 9309準拠やGoogle互換を検証済みとは宣言しない。

## 既存13ファイルの保全と現在のGit方針

開始時に未commitの13ファイルをすべてSHA-256照合し、非公開領域へ別コピーして読戻しを確認した。
元の9ファイルと継続確認4ファイルは、今回も1 byteも変更していない。
旧parser、旧取得器、Gの正式STOP、失効permit、A1原本・旧receiptも不変。
保全記録SHAは[SPEC_PREPARATION_STATUS.json](SPEC_PREPARATION_STATUS.json)に保存する。

旧文書の「PARTIALなのでcommitしない」「commit=false」は、その時点の方針・実績として保持する。
今回の新しい明示指示では、検証済みのPARTIAL成果を専用H branchへcommit・通常pushすることが認められた。
現在の方針はこの文書と[SPEC_PREPARATION_STATUS.json](SPEC_PREPARATION_STATUS.json)、
[SPEC_PREPARATION_VALIDATION.json](SPEC_PREPARATION_VALIDATION.json)を優先して参照する。
旧記録を書き換えて、過去にcommit/pushしたことにはしない。

## 将来の参照候補と通信枠

完全な案は[SPEC_FETCH_PROPOSAL.json](SPEC_FETCH_PROPOSAL.json)。
現在の許可は0 GET、permit ID・承認UTC・有効期限はnull、issued/activatedはfalse。
実行器や有効化スイッチを追加していない。案が整合しても実取得権限を返すAPIはない。

| 順序 | ID | 正確な候補URL | 用途 |
| --- | --- | --- | --- |
| 1 | S1_RFC9309 | `https://www.rfc-editor.org/rfc/rfc9309.html` | RFC 9309の規範原文候補 |
| 2 | S2_GOOGLE_ROBOTS_JA | `https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec?hl=ja` | Google仕様・互換性差分の参考候補 |

両URLの根拠は今回のユーザー明示指定であり、実HTTP応答・現在の適用条件の確認ではない。
scheme=https、hostは上表どおり、暗黙port 443、fragmentなし。
RFCのpathは`/rfc/rfc9309.html`、queryなし。
Googleのpathは`/crawling/docs/robots-txt/robots-txt-spec`、queryは完全一致で`hl=ja`。
言語queryの削除・変更・追加、percent表現の差替え、旧Google URL、RFC txt版への置換も禁止する。
同一hostや正規化先・翻訳先を含めredirectは追わない。

将来承認を求める上限案：

- **最大2 GET、各URL1回**、固定順序S1→S2。
- 本文2 MiB/件、合計4,194,304 bytes。header/status上限32 KiB/応答。
  本文＋header上限4,259,840 bytes。TLS等を含む全wire量の保証とはしない。
- retry0、redirect追従0、並列0。前件の通信完了から次開始まで最低5秒。
- socket 10秒、親worker 12秒、cleanup 2秒、全体90秒の有限deadline。
- TLS証明書・hostname検証必須。直接接続、proxy/環境設定の事前検査。
  User-Agentは既存研究用文字列、Accept-Encodingはidentity。認証/Cookie jar/ブラウザ/JSなし。
- 接続intentを事前に永続化し、失敗・timeout・完了不明も消費する。返却、再試行、後日再利用しない。

S1の原本・receipt・読戻し・アクセス条件を確認してからS2へ進み、
3xx、非200（404/403/429等）、認証/CAPTCHA、アクセス拒否・不明な条件、TLS/通信異常、
上限・deadline・間隔違反、保存/owner/ACL/reparse/SHA不整合で全体STOPする。
2件を使い切る義務はなく、途中停止後は残件を実行しない。

公式仕様2 URLの実取得は未承認である。
新しいhostのアクセス条件も未確認で、公式URLというだけで自動取得許可とは扱わない。
将来の通信前に既存の適用条件証拠を確認する。条件確認にrobots/規約等の追加通信が必要なら、
この2 GETへ紛れ込ませず、別の限定案・明示承認を要する。
リンク先のRFC、sitemap、CSS、JS、画像、API、翻訳ページ等を自動取得しない。
HEAD、OPTIONS、独立DNS probe、接続テストも追加しない。

## 原本・SHA・保存契約

新しい独立研究rootを明示承認後に固定する。現在、保存rootの実パスは未割当、未作成。
接続前にexclusive-create、Owner SID/DACL、祖先/root identity、reparse/junction/symlink、
既存runtime/source/publication/model/predictionとの非重複を検証する。
コード・入力・対象集合・root・新一回限りpermitのSHAを通信前に封印する。
実worker・保存/停止の合成検証と保護監査も改めて必要であり、今回の純粋な案検証で代用しない。

各資料はraw.html、request、metadata、status/header bytes、seal、receiptを新規ファイルとして保存する。
実取得bytesからraw SHA-256を計算し、request/metadataもSHA結合する。
未知の将来原本SHAを推測したり、別版のSHAを流用したりしない。
flush/fsync・保存後読戻し・SHA再計算が完了してから成功receiptを確定する。
不完全な本文・途中失敗の証拠も保持し、完全取得へ書き換えたり自動削除したりしない。
Windowsでの電源断耐性をこの案だけで実証したとはしない。

request開始、取得完了、snapshot保存、seal検証、原文審査の実UTCを分ける。
HTTP Date/Last-Modifiedや取得時刻を初回公開時刻・過去のPIT成立の証明へ転用しない。
原本、個別metadata/request、機微header、個人パスは非公開保存し、公開は仕様・集計・SHAのみ。
現在のA1保存領域やGのpermit・残予算は再使用しない。

## 取得後に準備する仕様照合

[NORMATIVE_REVIEW_TEST_PLAN.json](NORMATIVE_REVIEW_TEST_PLAN.json)に24軸を固定した。
すべて`PENDING_AUTHORITATIVE_SOURCE`、section参照・規範期待値はnull、規範test実行数は0。
今回の合成テストをRFC標準例実行済みとは記録しない。

確認するのはUA/product-token文法・適用・優先順位・group結合、Allow/Disallow文法、
最長一致・同長競合、wildcard/末尾anchor、percent/予約octet/Unicode/query、
未知directive・encoding・空原本・origin範囲・取得エラー/redirect・解析上限、
J1AI安全契約との優先順位、Googleとの差分、出典付き標準例、A1の再評価である。

取得後は各規則・例へ原本SHA、節/paragraph/byte位置またはanchor、言語・版・取得UTCを結合する。
RFCとGoogleの違いは実原文で確認し、互換profileの明示採用なしにGoogle動作へ差し替えない。
規範が許容する動作があっても、J1AIのredirect0/retry0/未知時STOP等を緩和しない。
規範根拠が不明ならUNKNOWNを維持し、候補診断ALLOWを正式ALLOWへ昇格しない。

## 今回の検証と状態

新規実行：**231 PASS**（新規案テスト78＋関連回帰153）、FAIL/error/skip 0、warnings-as-errors。
回帰153はH評価器84＋G取得証拠契約69。
URL/query完全一致、対象・上限・権限の拡張拒否、保存/SHA/readbackの必須性、
未実行規範testをPASSに見せる変更の拒否等を検証した。
これは通信実行器の実HTTP試験ではない。
過去641 PASSのJUnit・コード・test SHAは一致を確認し、履歴証拠として別に保持する。
231と641を合算した件数や、今回641件を再実行したとの報告はしない。

保存原本・新旧実装・規範未確認状態の整合検証と保護監査を実施する。
新baselineは54,274ファイルで、既存13ファイルは追加の保全コピーSHAでも検査する。
モデル53 payload、A1原本・G全receipt、既存予測、公式原本/witness、ID30700、旧隔離9件、
運用タスク定義/状態、main、他worktreeを保護する。

詳細な新規検証・保護SHAは[SPEC_PREPARATION_VALIDATION.json](SPEC_PREPARATION_VALIDATION.json)、
現行全ファイル集合は[SPEC_PREPARATION_SHA256.json](SPEC_PREPARATION_SHA256.json)に保存する。
過去の各manifest・VALIDATION・テストログは上書きしない。

wwwの4対象はUNKNOWN、aboutjは原本未取得でUNKNOWNを維持。
新規GET/HEAD/DNS probe、permit発行/有効化、旧run再実行、モデルload/fit/推論、
性能評価、確率計算、履歴admission、T0/対象登録、将来予測保存、運用タスク操作は0。
B/C/D各288 HOLD、HISTORY/PREDICTION：HOLD、Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
今回のcommit/push承認は、公式仕様の実取得、A2〜A4、B枠、モデル評価の承認を含まない。
