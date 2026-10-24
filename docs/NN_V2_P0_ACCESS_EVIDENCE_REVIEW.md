# NN v2 Phase 2.5Q — P0アクセス条件の証拠整理

判定は `NN_V2_P0_ACCESS_EVIDENCE_REVIEW_READY`。これは固定6 URLの証拠所在、UNKNOWNの原因、追加証拠候補と承認事項の整理が完了した状態を表す。6 URLのアクセス・実permitはすべてHOLD。G3本審査・permit発行・G4開始は未承認である。

基点はPhase 2.5P `d57e182521dbf354b41b536a67e27b17440d2950`。独立branchは `feature/nn-v2-p0-access-evidence-review`。G1 `5eefeec9fe2f7b7cd93fa6820097353bdab96e9c`、G2 `665f0144cffa3b1b569cabf79e41394de9f3914d` も既存worktreeのHEADと一致する。過去phaseの原本・判定・台帳は変更していない。

## 6 URLの証拠

URL、host、目的、原本所在、SHA-256、取得・保存時刻、UA、robots、terms、権利、鮮度、最小scopeを記録した正本は [ACCESS_EVIDENCE_INVENTORY.json](../research/nn_v2/phase2_5Q/ACCESS_EVIDENCE_INVENTORY.json)。取得許可は全行false、permit_idは全行nullである。

| ID・完全URL | 保存済み原本 | 固定原本によるrobots評価 | terms・主な不足 | 必要性・次の候補 |
|---|---|---|---|---|
| A1 `https://www.jleague.jp/robots.txt` | 検証済み、646 bytes | 条件付きALLOW | UNKNOWN。www規約、鮮度方針、実送信UAの証拠が不足 | オフライン再現には既存原本を使用。更新は必要性と鮮度方針次第 |
| A2 `https://aboutj.jleague.jp/robots.txt` | `NO_VERIFIED_ORIGINAL` | UNKNOWN | UNKNOWN。host固有robots、運営者・適用条件の正本が不足 | aboutj採用時のみ候補。www先行なら延期 |
| A3 `https://www.jleague.jp/general/kiyaku/` | `NO_VERIFIED_ORIGINAL` | 条件付きALLOW | UNKNOWN。規約本文・版・適用対象・研究自動取得・保存加工条件が不足 | 優先する条件原本候補 |
| A4 `https://www.jleague.jp/general/copyright/` | `NO_VERIFIED_ORIGINAL` | 条件付きALLOW | UNKNOWN。著作権・内部保存・加工・再利用条件の正本が不足 | A3と併せて優先する条件原本候補 |
| B1 `https://www.jleague.jp/j1/news/` | `NO_VERIFIED_ORIGINAL` | 条件付きALLOW | UNKNOWN。www条件、入口選定・時刻証拠への寄与が未確認 | 条件確定と必要性審査まで延期 |
| B2 `https://aboutj.jleague.jp/corporate/pressrelease/` | `NO_VERIFIED_ORIGINAL` | UNKNOWN | UNKNOWN。aboutj条件、robots、入口選定根拠が不足 | aboutj採用・条件確定まで延期 |

「原本なし」は、照合対象のG/I取得台帳とDの保存済み502原本で検証済み原本が見つからないことを意味する。個人disk全域の不存在を断定しない。Dの502原本もrawとmetadataのhashを再照合した。規約・著作権ページへのリンク、aboutjへの参照は本文取得や適用条件の証拠に数えない。

A1原本の実保存場所は `%LOCALAPPDATA%/J1AI/NNResearch-phase2_5F-A-approval-pending-20261023-01/A/access-0001/raw.bin`。`%LOCALAPPDATA%` は作業ユーザーのWindows環境変数で解決する。原本を新しい領域へコピーしていない。

- SHA-256：`3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c`
- 取得完了UTC：`2026-10-23T09:46:47.645062+00:00`
- 保存UTC：`2026-10-23T09:46:47.663444+00:00`
- 同ディレクトリのmetadata、request、seal、worker receipt、parent receiptを既存pinと照合した。sealのraw／metadata／request hash、URL、時刻の関係も検証する。

SHA一致はbytesの同一性であり、時計の独立真正性や利用許諾を証明しない。原本経過秒数を記録したが、承認TTLは未設定である。現在のサイト状態をfresh／staleと確定せず、`STALE_EVIDENCE` は現在性未立証のギャップ分類として使用する。Cache-Controlを取得・保存・再利用の許諾と扱わない。

## robotsとUAの区別

正式採用UAは `J1AI-Research-Timing-Pilot/1.0`、product-tokenは `Research-Timing-Pilot`、採用状態は `G1_ADOPTED_OFFLINE_ONLY`。G1採用manifestとG2の6 E1記録を照合した。

wwwの固定A1原本については、対象host・path・採用識別子を固定した過去オフライン評価が成立する。A1はrobots自身のURIに対する扱い、A3/A4/B1は既存subset評価であり、一般的な規範適合や現在のサイトのALLOWではない。aboutjには適用できない。

評価は①原本保存の立証、②hostへの適用、③採用UAでの固定評価、④規範解釈の完全性、⑤現在有効性を分離した。www側の①〜③は固定contextで確認、④は未解決、⑤はUNKNOWN。aboutj側は原本から不足する。

旧A1のrequest.jsonにはUser-Agent実値が記録されていない。旧workerソースのheader設定をASTで確認しても、実最終送信headerや独立観測の代わりにはならない。旧workerはimport・実行していない。G2 E0/E1はOFFLINE_VERIFIED、E2/E3はUNKNOWN、新E4取得は0を維持する。

## terms UNKNOWNの内訳

6 URLすべてで、適用する規約正本、研究利用、自動アクセス、保存、加工、再配布、公開、商用利用、版・時点、robotsとの関係がUNKNOWN。URLごとのsource候補と理由は台帳に保持した。A3/A4を取得しても、それがwwwの4 URLに適用する根拠が必要であり、aboutjへの適用は別途確認する。

robotsの条件付きALLOWだけでアクセス・転載・再配布を認めない。禁止文言が見つからないことを許諾と扱わない。今回は原本未保存のため、条文解釈や法的結論は出していない。正本を得た後に解釈が必要な条件だけ専門確認へ回す。

取得データの外部再配布を計画しない最小案でも、内部保存・加工の条件は未確認である。原本・hash・metadataを独立研究領域へ保存する案、実保存先identity、容量上限、保管期間、加工範囲も本審査で確定する。

## UNKNOWNと解消可能性

[TERMS_GAP_MATRIX.json](../research/nn_v2/phase2_5Q/TERMS_GAP_MATRIX.json) は正式9 UNKNOWNと横断7ギャップを分離し、9分類すべてを使用する。合計16行は規範UNKNOWNが16件になったことを意味しない。**規範15 PASS／9 UNKNOWN、完全解消0を維持する。** Mのscope優先度と今回の証拠準備P0/P1/P2は別軸である。

| 正式UNKNOWN | オフラインで確定した部分／残る解消経路 |
|---|---|
| agent_grammar | G1採用・G2 E1の所在を確認。実最終UAと独立観測は承認G4で初めて観測 |
| rule_grammar | 保存済みABNF・公式例・recoveryの比較対象を特定。解釈問題は未解消 |
| longest_rule | 保存済み順位解釈の比較対象を保持。固定pathで競合がないことを一般解消としない |
| reserved_octets | 参照仕様不足を追加正本候補へ。unquote-allで補完しない |
| query | 現6 URLにqueryなしを確認。一般query規範の解消・scope拡張は未実施 |
| encoding_errors | 保存済み仕様比較と、異常bytes保持の別承認隔離試験が必要 |
| parse_limits | 取得上限とparser規範容量を区別。変更版の資源・保存実証が必要 |
| standard_examples | 保存された公式例の出典を保持。未確認の説明を補作しない |
| sealed_A1_replay | bytes・保存時刻・hashを確認。terms、鮮度、実UA、隔離保存、承認、独立観測は残る |

この工程で確定したP0-Aは、6 URLとhost、保存原本1件と未検証原本5件、取得時刻・hash、証拠レベルの区別、適用scopeと不足の所在である。正式UNKNOWNをPASSに書き換える作業は行っていない。

P0-Bは条件原本・適用許可scope・鮮度方針。P1はアクセス条件整理後の隔離実証・永続attempt。P2は承認G4での実E2/E3/E4観測とする。同じwww条件原本で複数URLの不足を減らせる場合も、適用根拠の確認が前提である。UA実観測と独立観測を同じ証拠として数えない。

## 最小取得候補と承認

[P0_EVIDENCE_PRIORITY.json](../research/nn_v2/phase2_5Q/P0_EVIDENCE_PRIORITY.json) に重要度、取得対象数、通信の要否、鮮度、運用・専門確認、残るUNKNOWNを比較した。

1. まず運営者／利用者提供のA3/A4正本と、適用対象・取得UTC・版・出典を確認する候補。今回の新規資料受領・取得は0。
2. 提供正本で代替できない場合だけ、A3/A4各1 GET、合計最大2 GETを将来の条件確認候補にする。未確認条件を通すbootstrap policyは未承認で、一般permitのUNKNOWN例外は追加していない。
3. A1は旧原本でオフライン確認する。現在性の審査で必要と判断し、鮮度方針が定まった場合のみ、別枠1 GETの更新候補。
4. A2とaboutjの条件確認は採用理由が成立した場合だけ。適用規約の正本URLも未確定で、現scope外URLを自動追加しない。B1/B2の探索は延期する。

一度限り・queryなし・redirect/retry/parallel各0の候補とし、定期取得は提案しない。既存の原本・試合資料で代替できる部分を先に使う。各候補は取得許可ではなく、旧G/Iの未使用枠や旧permitを再利用できない。

## 検証・保護

実装は [access_evidence.py](../research/nn_v2/phase2_5Q/access_evidence.py) のpureな検証関数だけ。exact URL、独立pinと原本bytes、provenanceの結合、terms、gap、review readinessを検証する。JSON schemaは閉じた固定baseline用で、追加fieldや未承認の状態変更を拒否する。READYの出力もaccess／permit／G3／G4 authorityをすべてfalseに固定する。

最終テスト・negative-control件数、schema・provenance・静的検査、保護監査の結果は [OFFLINE_VALIDATION.json](../research/nn_v2/phase2_5Q/OFFLINE_VALIDATION.json) を正本とする。新規154 PASS、G1/G2/G3を含む回帰1,363 PASS。初回schema検証で空配列のprefixItems定義に1 FAILがあり、修正後の全件試験結果と分けて保持した。skip・deselectは0。外部通信が必要なテストは選択していない。

専用テストprocessのapplication guardでsocket生成・DNS・通信・外部process・実モデル操作・許可範囲外writeを拒否した。遮断probe自体は実行していない。OS全体の隔離やJob/ACL/TLS・永続化の動的実証とは区別する。

保護開始baselineは118,770ファイル・32既存worktree。モデル53 payload、既存予測・公式原本、過去research raw・permit/evidence、GUI code/snapshot、定時タスク、mainを含めた。GUI/serverはlocal CIMとlistener表を読み取り、HTTP probeやsocket接続は行っていない。定時タスクは定義・状態・実行履歴時刻を読み取った。最終照合は [PROTECTION_VERIFICATION.json](../research/nn_v2/phase2_5Q/PROTECTION_VERIFICATION.json) を参照する。

旧Gの1 GET・1 DNS・1 TCP接続は過去の取得記録である。Phase 2.5QのHTTP・DNS・socket、新規取得、transport、新permit、モデル実行、GUI／task／OS policy変更は0。利用者の明示指示により完全オフラインを優先し、Git push・fetch・pull・ls-remoteを含むリモート通信を禁止する。push未実施は後日の別承認までの意図した保留であり、研究成果の検証失敗ではない。実remoteとの一致は未検証。ローカルcommit・remote設定表示・ローカル追跡ref確認だけが許可されている。

B/C/D、HISTORY/PREDICTIONはHOLD、Phase AはBLOCKED、Phase BとG4はNOT_AUTHORIZEDを維持する。次工程の具体的条件は [G3への引継ぎ](NN_V2_P0_TO_G3_REVIEW_HANDOFF.md) に記す。
