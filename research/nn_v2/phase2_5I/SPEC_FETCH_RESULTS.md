# Phase 2.5I：公式robots仕様の限定取得と規範照合

判定：**`NN_V2_ROBOTS_SPEC_CONFORMANCE_PARTIAL`**。

基準commit：`8b562c028bba104b798c86ccaf66a2614564b657`。
研究branch：`feature/nn-v2-robots-spec-conformance`。
Study：`nn_v2_residual_20261020_01`。

## 承認済み取得の完了

| ID | 完全一致URL | HTTP | bytes | SHA-256 |
|---|---|---:|---:|---|
| S1 | https://www.rfc-editor.org/rfc/rfc9309.html | 200 | 82,367 | `bbaa280636d3e38f0a1a130a5ce40e9753db1ed18c860945b0bf795ff8dc1a87` |
| S2 | https://developers.google.com/crawling/docs/robots-txt/robots-txt-spec?hl=ja | 200 | 107,151 | `ead8ce5275092f57333ac66bc47c1cd4551717b8d69f2bb34f76c09ac3a89581` |

2026-10-23にS1→S2の順に各1 GETを実行し、合計189,518 bytesを
原本のまま非公開領域へ封印した。GET内の名前解決以外の独立DNS probe、
HEAD、追加リソース、redirect、retry、並列通信は0。
S1完了からS2開始までは33.544024秒。全体35.29599999997299秒で終了し、
socket 10秒・親worker 12秒・全体90秒の期限内だった。
S1の保存・読戻し・オフライン確認を確定してからS2へ進んだ。

request・metadata・headers・worker receipt・seal・parent receipt・
intent/response台帳・最終receipt・外側exitを独立に再読込みした。
全SHA、累積台帳の前方一致、UTC順序、TLS証明書/hostname検証、
実行時コードSHA、Job所属・終了を照合した。外側exit0、timeoutなし、
最終所有process数0。取得PIDの後続読取り専用照合でも残存を認めなかった。
取得時UTCと監査UTCは別fieldで保持する。

完全URL、実UTC、request/metadata/receipt/seal SHA、コードSHAは
[SPEC_FETCH_LEDGER.json](SPEC_FETCH_LEDGER.json)を参照。
原本、応答headers全文、permit実体、個人環境パスは公開しない。
このpermitは消費済み・再利用禁止。再実行、A2〜A4、B枠への権限拡張はない。
取得コードと後処理コードは分離し、取得後にworker/parent/contractを変更していない。

## 24項目の規範照合

既存24 IDを順序も含めて維持し、S1/S2の原本SHA・実在anchor・byte位置・
tag SHA、期待動作、旧挙動、差分、テスト名、未解決点を
[NORMATIVE_CONFORMANCE.json](NORMATIVE_CONFORMANCE.json)へ記録した。
[SOURCE_SECTIONS.json](SOURCE_SECTIONS.json)は原本内の参照先台帳。

結果は**13 PASS／0 FAIL／11 UNKNOWN**。PASSは記載した比較範囲と安全契約に
ついての根拠確認であり、parser全体のRFC/Google完全準拠を示さない。
Google固有動作をRFCのMUSTへ読み替えていない。

主な未解決点：

- RFCのproduct-tokenは英字・`_`・`-`。固定HTTP User-Agent
  `J1AI-Research-Timing-Pilot/1.0`と別に、明示的なtoken宣言が必要。
  数字を含むproduct名から別identityを自動生成しない。
- wildcard/anchorを含む規則の長さ、複数encoded規則、reserved octet、
  複雑なqueryについて、完全なRFC比較を主張できない。
- RFC §2.2 ABNFと§5.1のslashなしwildcard例、§5.2のruleとURIの
  ファイル名に不整合を確認した。原文を訂正・補完せずUNKNOWNとした。
- 既存64 KiB上限はRFC §2.5の最低500 KiBを満たさない。
  既存資源上限を無断で拡大せず、完全準拠の主張を保留した。
- 不正行・未知directive・空の原本に対するJ1AIの厳しいUNKNOWNは、
  規範の寛容な回復処理との差として残る。Sitemapはgroupを終了せず、取得もしない。
- RFC/Googleのredirect推奨やHTTPエラー時の取得方針は、今回の
  redirect0・非200 STOPという承認済み安全契約を上書きしない。

## 新しいオフライン解析版

`robots_normative.py`：`nn_v2_robots_spec_bound_subset_v2`。
旧Hの`robots_offline.py`、Gの取得器、旧permitは変更していない。

新しい純粋関数では明示tokenの大文字小文字を無視した完全一致・group結合、
RFC Figure6のliteral `%2A`/`%24`とURIの`*`/`$`の対応を検証する。
旧Hのliteral長だけの優先度とGoogleのmarkerを含む優先度で結論が異なる場合、
旧候補ALLOWを採用せずUNKNOWNとする。
Googleの`/page.htm`例では旧合成候補ALLOWとの差を検出し、
`/page.php5`例では両解釈のALLOW一致を確認した。
複雑なreserved escape/queryは対応外としてUNKNOWN。

仕様SHA・raw SHA・version・profile・originの照合を必須にし、全結果の
`execution_authorized`、`B_authorized`、`history_admission`はfalse。
HTTP entrypoint・permit生成・collector・モデルへの接続はない。
仕様SHAの純粋関数引数だけで真正性を証明する設計ではなく、別の保存原本監査で
request/TLS/receiptまで照合した結果を参照する。
ローカル時計とTLS証跡で、絶対的な時刻真正性まで証明したとはしない。

## A1の再評価

旧A1原本のSHAを再照合し、固定User-Agentで4対象を個別に評価した。

| 対象 | 判定 |
|---|---|
| `https://www.jleague.jp/robots.txt` | UNKNOWN |
| `https://www.jleague.jp/general/kiyaku/` | UNKNOWN |
| `https://www.jleague.jp/general/copyright/` | UNKNOWN |
| `https://www.jleague.jp/j1/news/` | UNKNOWN |

理由は明示的なRFC product-tokenとheaderのbinding未確定。
適用group/ruleを推測して割り当てていない。
RFC §2.2.2のrobots URIの暗黙許可は確認済みだが、本研究の証拠処理は
identityゲートが未確定のため同URIもUNKNOWNを維持する。
これはRFCの暗黙許可を否定する判断ではない。

`aboutj.jleague.jp`は当該hostの原本未取得のためUNKNOWN。
利用規約・自動取得条件も未確定。
[ROBOTS_REEVALUATION.json](ROBOTS_REEVALUATION.json)に各判定の根拠を記録した。
robotsの判定とサイトの取得許可、ユーザーの通信承認は別である。

## 今回の検証と過去証跡

- 最終：**344 PASS／0 FAIL／0 skip**、warnings-as-errors。
  新規113（規範parser・台帳88、取得契約25）＋関連回帰231。
- 通信前：256 PASS（新規取得契約25＋回帰231）。最終337へ重複加算しない。
- 開発途中の新規テストでは33 PASS／1 FAILがあった。
  `/page.php5`の両解釈がALLOW一致するケースを誤ってUNKNOWNと期待したため、
  仕様と再照合してテスト期待値を修正した。旧ログを保持した。
- その後の334 PASS・337 PASSは別実行。encoded UTF8不正・dot segmentの
  negative-control7件を加えた最終状態の件数だけを上記へ計上。
- Hの641 PASSは既存JUnit SHAを伴う過去証跡として保持し、今回の再実行とは区別。
- テストprocessには通信/DNS・子起動・実モデル/deserialize・領域外書込みを拒否する
  application guardを適用した。禁止呼出し0。OSネットワーク隔離の実証とはしない。
- `VALIDATION.json`、各JUnit/log/guard receiptのSHAを保存。個人情報を含むJUnitは非公開。

## 保護と22:00の独立運用事象

新baseline55,469ファイル。GET前・GET後（22:00前）はSHA/metadata差分0。
その後、既存22:00タスクが2026-10-23 22:00:01 JSTに実行され、終了値0となった。
研究からタスクを実行・修復・変更していない。

運用可変出力はSHA10件・metadata13件が変化した。
タスク状態、取得UTC、revision manifest全payload SHA、flat出力とrevisionの一致、
表示更新時刻、preview generationと既存updaterコードを読取り専用で照合した。
定時処理の公式一覧GET1件は独立した運用証跡であり、研究のS1/S2 permitや実績へ混ぜない。
この対応確認をホスト全書込みの完全な因果証明とはしない。

残る固定55,456ファイルはSHA/metadata差分0。モデル53 payload、旧A1/G証跡、
288詳細原本・旧隔離9件、固定研究入力、予測、main・他worktree、タスク定義は不変。
直前preview generationは継承ファイル台帳に直接列挙されていなかったため、
旧pointerのbaseline SHAとcontent-addressed manifestで連鎖照合した。
直接baseline照合したと装っていない。過去の未帰属差分・07:00失敗の記録も保持し、
解決済みとは扱っていない。

[PROTECTION_SUMMARY.json](PROTECTION_SUMMARY.json)に集計・証拠SHAを保存。
私的原本・監査証跡と公開成果物は別ドライブへ保存し、ZIP CRC、全entry SHA、
独立展開後SHA・読戻しを確認する。境界と実測結果は`BACKUP_VERIFICATION.json`を参照。

## 次工程

未解決のproduct-token、規則順位、reserved/query、回復処理・資源上限を
オフライン設計で再審査する。RFC例示の追加確認に外部資料が必要なら、
対象URLを別途固定して新しい明示承認を得る。今回の2 URLは再取得しない。
A2〜A4、aboutj、B枠についても新しい個別承認とアクセス条件の解決が必要。
G/Iの消費済み・失効permitを再利用しない。

B/C/Dは各288 HOLD、HISTORY/PREDICTIONはHOLD、Phase AはBLOCKED、
Phase BはNOT_AUTHORIZEDを維持。
研究の実モデルload/fit/推論・性能評価・実確率計算・T0・対象登録・将来予測保存は0。
本番collector・タスク・feed・Desktopを研究から操作していない。
PARTIALでの成果保存は今回の明示承認の範囲で行い、merge・配備・通信再開は行わない。
