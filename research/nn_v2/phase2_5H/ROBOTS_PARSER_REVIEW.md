# Phase 2.5H — robots評価器のオフライン候補実装

最終判定：`NN_V2_ROBOTS_PARSER_PARTIAL`。
基準：Phase 2.5G `2d5a1bd85e226c66517db5a7ae84dcd11b2e1b20`。

ワイルドカード等を扱う純粋関数の候補実装・合成検証・A1原本照合を完了した。
ただしRFC 9309とGoogle仕様の保存原文を確認できず、規範仕様との照合は未完了。
記憶やローカルCPythonを規範原文の代用にせず、実原本の正式判定はUNKNOWNとした。
したがってOFFLINE_VERIFIEDとせず、commit/pushもしない。作業と証跡は保持する。

## 採用していない仕様・現在の適用範囲

version：`nn_v2_robots_offline_draft_v1`。
新規実装は[robots_offline.py](robots_offline.py)。旧parser、取得器、permitは変更しない。
実原本用profile `J1AI_EVIDENCE_FAIL_CLOSED_DRAFT_V1`は新しいネットワーク権限を持たず、
仕様根拠が未確認の現在は、候補計算がALLOWでも外部向けdecisionをUNKNOWNとする。
`J1AI_SYNTHETIC_PATTERN_EXPERIMENT_V1`は`synthetic.invalid`の合成試験専用。
実hostや封印A1原本を合成扱いへ付け替えてALLOWを得ることも拒否する。

規範の優先順位はJ1AI安全契約→RFC 9309→必要な場合のGoogle互換で維持する。
今回は次の資料状態であり、RFC/Googleの正式な差分を確定できていない。

| 項目 | J1AI候補実装 | RFC 9309との照合 | Google互換との照合 |
| --- | --- | --- | --- |
| 本文サイズ | 64 KiB超・空原本はUNKNOWN | 原文未確認 | 原文未確認 |
| UTF-8/BOM/改行/コメント | strict UTF-8、先頭BOM、CR/LF、コメントを処理 | 規範原文への項目別照合未完了 | 未採用 |
| `*`/`$` | prefix globと末尾アンカーの候補 | 規範原文への照合未完了 | 未採用 |
| 最長規則・同長競合 | 正規化octet数、Allow優先の合成候補 | specificityの根拠確認が必要 | 未採用 |
| UA適用 | 既存CPython helperを合成実験のoracleに使用 | 最終UA契約は未確定 | 未採用 |
| 同じ具体性のgroup | 合成候補では結合 | 正式な組合せ規則を要確認 | 未採用 |
| 未知directive | UNKNOWN。sitemapは記録のみ、取得0 | 無視可否等を未確認。安全側へ固定 | 未採用 |
| 不明・壊れた入力 | UNKNOWN、権限なし | 安全契約を優先 | 緩和しない |

既存repo・保存研究資料、Documents/Downloadsのファイル名、ローカルPython source/testsを調査した。
保存された公式仕様は見つからなかった。全ドライブに存在しないと立証したものではない。
一部ProgramDataの列挙は権限拒否で未確認。管理者昇格やACL変更をしていない。
ユーザーへ既存資料のパスを確認したが、資料が得られるまでは未確認として扱う。

実際のruntimeはCPython 3.12.14。`urllib.robotparser`の先頭説明が参照するのは
`http://www.robotstxt.org/norobots-rfc.txt`であり、RFC 9309原文とは扱わない。
同URLへはアクセスしていない。別途見つかったCPython 3.10 source/testもRFC根拠へ昇格しない。
runtime moduleのSHAと確認範囲は[SPECIFICATION_STATUS.json](SPECIFICATION_STATUS.json)へ保存した。

## 候補照合器と安全境界

`evaluate`はbytes、source host、対象URL、固定UA、version、profile、期待原本SHAを入力とする純粋関数。
decision、候補診断、適用group、合致規則・line、理由、version、原本SHAを返す。
新規ファイルI/O、ネットワーク、HTTP入口、モデル、permit機能は持たない。
どの戻り値でも`execution_authorized=false`、`B_authorized=false`、`history_admission=false`。
UNKNOWNをALLOWへ変換するfallbackはない。

候補の照合対象はpathとqueryを含むoctet列。
unreserved percent-encodingは同一octetにし、encoded reserved文字は生の区切りと区別する。
非ASCII文字はUTF-8 octetに対応させる。Unicode NFC/NFDの曖昧な同一視や全unquoteは行わない。
patternのliteral `*`は0文字以上、末尾のliteral `$`は終端として実験する。
`%2A`・`%24`はwildcard/anchorへ変換しない。
逐次集合計算にwork/サイズ上限を設け、正規表現の無制限backtrackingへfallbackしない。

UA一致を新しい単純部分一致として独自実装していない。
検査した既存CPython `Entry.applies_to`を候補実験の適用oracleとして再利用し、
その上で最長token・同長group結合を合成的に試験した。
このlegacy helperがRFC 9309またはGoogleに適合するとは未立証であり、正式UA選択としては未採用。
規範資料のproduct-token文法・適用規則・優先順位の確認が完了するまで実判定はUNKNOWNのままにする。

欠落UA、未知version/profile、不正URL、異なるhost、明示port、fragment、path traversal、
不正percent/UTF-8、未知directive、壊れたpattern、サイズ・計算上限等はUNKNOWN。
原本SHAや封印原本のhostの不一致はsafety_stopも明示する。
今回のA1監査では純粋関数を呼ぶ前にも原本SHAを照合し、不一致なら即STOPする。

## A1原本の独立照合と再評価

原本：646 bytes。
SHA-256：`3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c`、一致。
metadata/request/seal/旧receipt、Gの証拠SHA台帳全体も一致。
取得UTCはGの実取得時刻をそのまま継承し、今回の監査UTCと分けた。

| 対象URL | 正式decision | 合成候補ロジックの診断 | 判定理由 |
| --- | --- | --- | --- |
| `https://www.jleague.jp/robots.txt` | UNKNOWN | matched ruleなし、候補ALLOW | 規範仕様・UA契約が未確認 |
| `https://www.jleague.jp/general/kiyaku/` | UNKNOWN | 同上 | 同上 |
| `https://www.jleague.jp/general/copyright/` | UNKNOWN | 同上 | 同上 |
| `https://www.jleague.jp/j1/news/` | UNKNOWN | 同上 | 同上 |

使用UAは全件`J1AI-Research-Timing-Pilot/1.0`。
候補の適用groupは`*`だが、この診断を正式ALLOWや取得許可へ昇格しない。
規則・version・原本SHAと候補診断を[ROBOTS_EVALUATION.json](ROBOTS_EVALUATION.json)に保存した。
aboutj原本は未取得でUNKNOWN。wwwの結果を流用しない。
利用規約、著作権、aboutj運営主体・適用hostも未確認。

Gの正式実績はA1 GET1/HTTP200、A2/A3/A4 GET0、B GET0、審査STOPのまま。
Gの未使用3回は失効済み。新規GET/HEAD/DNS probe、permit発行・有効化、run再実行は0。
旧parserをA1に適用したHOLD結果を、今回の候補診断で書き換えない。

## 新規テスト・回帰

最終版は新規84件＋関連回帰557件＝**641 PASS**、FAIL/error/skip 0、warnings-as-errors。
新規45 test caseはUNKNOWN/拒否/計算上限等のnegativeまたは混合negative-controlを含む。
残るcaseは合成候補照合、group/正規化、旧互換性、静的非接続等を検証する。
標準原文を確認していないため、RFCの公式例を実施済みと偽らず、すべて独自の合成例として識別する。

初回は巨大parameter値がWindowsの環境変数長上限を超え、49 PASS/2 ERRORでテスト基盤が停止した。
parameterへ短いIDを付けて解消した。初回JUnit/log/sourceを削除せず保持する。
途中635 PASSは保存し、最終版では空規則後のgroup境界とhost/profile等を追加検証して641 PASSとなった。
これらの実行件数を合算しない。
実原本の純粋評価は別のオフライン監査成果物であり、合成JUnitへ二重計上しない。

旧G `review_robots`は変更せず、単純な既知形式の従来判定とwildcard HOLDの両方を回帰確認した。
旧parentは証拠検証器のみimportし、旧robots判定は内容審査・テスト側の利用だったことを静的確認した。
H評価器へのimport接続、旧HTTP worker/parentへの変更、既存permitのversion差替えは行わない。
関連回帰の一部は従来からの専用一時領域Windows保存テストを含むが、ネットワークやchildは起動しない。

## 保護・保存・次工程

開始時に新たに54,231保護ファイルのbaselineを取得した。Gの専用取得原本・全receipt・失効permitも対象へ追加した。
モデル53 payload、既存予測、公式原本/witness、ID30700、旧隔離9件、
タスク定義・状態、main、Gを含む他worktreeを保護する。
前後監査は[PROTECTION.json](PROTECTION.json)、検証は[VALIDATION.json](VALIDATION.json)、
新規成果物SHAは[SHA256-MANIFEST.json](SHA256-MANIFEST.json)を参照。
原本・metadata・個人パス・log・モデルは公開候補へ追加しない。
PARTIALのため新規branchに未commitで保持する。旧GのHEAD・worktreeは不変。

次に必要なのは、保存済みRFC 9309原文の提示と、そのSHA・由来に基づく項目別仕様レビュー。
Google互換を採用する必要がある場合は、同様に保存済み仕様を確認する。
規範のUA・最長一致・正規化・group・例外の検証が完了した新しい不変versionで、A1を再評価する必要がある。
これは追加のHTTP承認を求める工程ではない。今回Web取得は行わない。

A2〜A4の実取得は、parser/条件審査が成立しても**新しい限定計画と別の明示承認**を要する。
B枠は両hostのrobots・規約・著作権等が未確認で、permit未発行のまま。
HISTORY/PREDICTION：HOLD、B/C/D各288 HOLD、Phase A：BLOCKED、Phase B：NOT_AUTHORIZEDを維持する。
