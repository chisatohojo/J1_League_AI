# Phase 2.5J：残り11項目の独立再照合

判定：**`NN_V2_ROBOTS_NORMATIVE_REVIEW_PARTIAL`**。

基準：Phase I `d96bca40a460eb8dcc75f0cfa932a3fb9ddd90ef`。
専用branch：`feature/nn-v2-robots-normative-review`。
Study：`nn_v2_residual_20261020_01`。

新規GET・HEAD・DNS probe・permit発行・旧run再実行は0。
封印済みS1/S2/A1を読み取り専用で照合し、旧H/I版と通信原本は変更していない。
Git transportは明示承認された成果保存として、証拠取得通信とは区別する。

## 原本と参照の確認

Iの`SPEC_FETCH_LEDGER.json`からpermit SHA、非公開原本台帳へ辿り、
推測パスを使わずS1/S2を特定した。
各raw・metadata・request・worker/parent receipt・seal・全28原本ファイルを
SHA照合し、既存32 section anchorのbyte位置・tag SHAも確認した。
A1はGの原本台帳から特定し、Gの全原本・通信台帳SHAと応答契約を照合した。
新しい原本・HTTP応答は取得していない。

| 原本 | bytes | SHA-256 |
|---|---:|---|
| S1：RFC 9309 | 82,367 | `bbaa280636d3e38f0a1a130a5ce40e9753db1ed18c860945b0bf795ff8dc1a87` |
| S2：Google公式仕様（日本語） | 107,151 | `ead8ce5275092f57333ac66bc47c1cd4551717b8d69f2bb34f76c09ac3a89581` |
| A1：www robots | 646 | `3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c` |

検証時刻と実取得時刻は別fieldで保存した。
[INPUT_EVIDENCE.json](INPUT_EVIDENCE.json)を参照。
原本・headers全文・個人パスは非公開領域に保持する。

## 正式な11項目

既存台帳からUNKNOWNの11 IDを順序どおり抽出し、問題文も変更せず
`inherited_item`へ保存した。結果は**2 PASS／0 FAIL／9 UNKNOWN**。
前工程の13 PASSはそのまま保持し、新しい24項目集計は15 PASS／9 UNKNOWN。
これは完全なRFC/Google準拠の主張ではない。

| 既存ID | 結果 | 根拠・残件 |
|---|---|---|
| agent_grammar | UNKNOWN | RFC §2.2.1の文法自体は明確。固定HTTP headerに対応するproduct-token宣言が未確定。別identityを推測しない。 |
| rule_grammar | UNKNOWN | §2.2 ABNFのslash必須と§5.1例示に不整合。例示からALLOW fallbackを作らず、不正defined ruleはUNKNOWN。 |
| longest_rule | UNKNOWN | §2.2.2のoctet最長とGoogleのmarkerを含む順位を区別。結論が分かれる場合は保留。wildcardの展開文字数を規則長へ採用しない。 |
| reserved_octets | UNKNOWN | §2.2.2/Figure4・6の確認済み部分を維持。参照先RFC3986の未取得部分を補完せず、reserved全体や複数escape順位は未実証。 |
| query | UNKNOWN | Figure4の単一ASCII `key=value`だけ新たに照合。reserved値・複数pair・percent queryの一般化はしない。 |
| unknown_directives | PASS | §2.2.4のdefined recordへの非干渉と、Googleの非対応fieldを確認。仕様層でのみ無視し、J1AI条件はUNKNOWNを維持。 |
| encoding_errors | UNKNOWN | §2.3.1.5の行別回復処理は完全実装していない。不正UTF8や不正defined lineを安全側に停止する挙動を完全準拠と呼ばない。 |
| empty_body | PASS | §2.2.1/2.2.2のgroup・rule不在の扱いを確認。成功応答の空原本は仕様層ALLOW、J1AI証拠層UNKNOWN。失敗応答を空の成功原本にしない。 |
| parse_limits | UNKNOWN | RFC §2.5は最低500 KiB。64 KiBは独自資源制約であり、I/Jの実装能力不足を残す。取得器・permit上限を変更しない。 |
| standard_examples | UNKNOWN | §5.1のslashなし規則、§5.2のrule/URIのファイル名差を原文どおり保持。外部errataを取得・推測していない。 |
| sealed_A1_replay | UNKNOWN | `/robots.txt`の仕様上の暗黙許可は確定。他3対象はtoken未宣言でUNKNOWN、aboutjは原本未取得。 |

各項目のRFC/Google参照、規範本文、例示との関係、Iの現行動作、解釈、
根拠の強さ、テスト名、未解決点は
[NORMATIVE_REVIEW.json](NORMATIVE_REVIEW.json)に記録した。
Google独自のUA suffix処理・error/cache方針・回復処理をRFC MUSTへ読み替えない。

## 新版と3レイヤー

`robots_layers.py`は`nn_v2_robots_offline_layers_v3`、出力schemaは
`NNV2_ROBOTS_OFFLINE_LAYERS_V3`。
Iの純粋関数を再利用し、旧APIやコード・取得器を変更していない。
HTTP workerへのimport・自動接続、有効化スイッチ、permit発行機能はない。
`layer1.requested_parser_version`は内部で呼び出したIエンジンの版、
返却側の`parser_version`はJ解析版を示す。Iの返却結果も
`legacy_I_result`へ別に保持し、両者を同じ版として扱わない。

1. **Layer 1：robots仕様判定**。ALLOW／DENY／UNKNOWN。
   raw/spec SHA・URL・origin検証を通過した範囲だけで、暗黙robots URI、
   空/comment-only成功原本、未知fieldの非干渉、単一ASCII queryを区別する。
   不正defined rule・仕様競合・未対応encodingはUNKNOWNを維持する。
2. **Layer 2：permit条件**。実permitは今回未発行・未承認。
   純粋な`permit_check`は合成専用planしか受理せず、実hostには使えない。
   URL/host/port/method、scope、予算・期限、redirect/retry/parallel、
   保存先・本文量を確認する。planの検証はpermitの発行や消費ではない。
3. **Layer 3：最終通信候補**。Layer1 ALLOW・Layer2 ALLOW・
   J1AI証拠制約の合格・サイト条件の確認がすべて必要。
   純粋関数は論理的な候補だけを返し、全結果の`execution_authorized`、
   `B_authorized`、`history_admission`はfalse。実通信はできない。

Layer1の新しい結論で、Iの証拠制約を上書きしない。
未知fieldにrate/access条件が含まれる可能性はJ1AI層で残す。
呼出側が渡すSHAやstatusを、それだけで真正な証拠・承認とみなさない。
今回の実原本は別の独立監査でrequest/metadata/sealまで照合している。

### 最小限の差分

- 空の成功原本とcomment-only：Layer1 ALLOW／証拠層UNKNOWN。
- 未知field：defined group/ruleを変えず評価。ただし証拠層UNKNOWN。
  不正なAllow/Disallow等が混在すればLayer1もUNKNOWN。
- ASCIIの単一 `key=value` query：RFC Figure4に基づく比較だけ追加。
  HTTPS文字列を値に含む場合、`&`、percent query等へ拡張しない。
- 暗黙robots URI：正しいraw/spec SHAとoriginを確認したA1では、
  tokenを捏造せずLayer1だけALLOWへ分離できる。
- Iで未対応の64 KiB超過、複雑なreserved/query、競合順位、
  不正構文の回復処理は引き続き保留。生の原本を変換して再入力していない。

## 差分検証

[PARSER_DIFF.json](PARSER_DIFF.json)は合成28ケースを再現可能なrecipe・
入力SHA/bytes・URL・各版結果・適用group/rule・根拠とともに保存する。

| 分類 | 件数 |
|---|---:|
| 旧版と一致 | 11 |
| 根拠付き修正／レイヤー分離 | 8 |
| 仕様解釈・実装が未完了で保留 | 4 |
| J1AI独自制約による意図的拒否 | 5 |
| 新版に不整合 | 0 |

旧Hのsynthetic候補は、過去の正式通信許可ではない。
H/Iのraw parserはHTTP statusを引数に取らないため、取得失敗の実行結果を
捏造して比較していない。Gの非200 STOP契約の回帰と、Jのstatus受渡し拒否を
別のmockテストで確認した。
観測した誤ALLOWは0だが、あらゆる入力に対する不存在証明とはしない。

## A1の再評価

固定HTTP User-Agentは`J1AI-Research-Timing-Pilot/1.0`のまま。
RFC product-tokenは未宣言。新しいtokenやHTTP identityを採用していない。

| 対象 | Layer1 | Layer2 | 最終通信候補 |
|---|---|---|---|
| `https://www.jleague.jp/robots.txt` | ALLOW | UNAPPROVED | false |
| `https://www.jleague.jp/general/kiyaku/` | UNKNOWN | UNAPPROVED | false |
| `https://www.jleague.jp/general/copyright/` | UNKNOWN | UNAPPROVED | false |
| `https://www.jleague.jp/j1/news/` | UNKNOWN | UNAPPROVED | false |

robots URIの変更根拠はRFC §2.2.2の明示的な暗黙許可であり、groupの推測ではない。
適用group・一致規則はこの例外に不要なので空とし、根拠を別fieldへ記録した。
他3対象も、groupを推測せずUNKNOWN理由を保存する。
Iの正式4 UNKNOWN記録、Gの停止記録・失効予算は不変。
`aboutj.jleague.jp`は当該host原本未取得のためUNKNOWN。
利用規約・著作権・自動取得条件が確認済みになったとは扱わない。

[ROBOTS_REEVALUATION.json](ROBOTS_REEVALUATION.json)を参照。

## 検証・保護

最終実行：**572 PASS／0 FAIL／0 skip**、warnings-as-errors。
新規228＋今回再実行した関連回帰344。明示的な拒否negative-controlは113件。
3レイヤーの54通りの組合せ試験も別に含む。
途中の531 PASS、Iの過去344 PASS、Hの過去641 PASSは独立した過去証跡であり、
今回の572へ足していない。

テストprocessでは通信/DNS・子起動・実モデル/deserialize・領域外書込みを
application guardで拒否し、禁止呼出し0。OS隔離の実証とは呼ばない。
実原本SHA・receipt・anchor照合は、合成pytestとは別の読み取り専用監査である。

新baselineは56,756ファイル。Iの終了後からの10差分は、Iで照合済みの22:00
運用更新と完全一致し、今回の開始以後の変更と分けた。
今回の前後比較ではモデル53 payload、予測、原本、旧witness/隔離9件、
ID30700方針、旧H/Iコード・通信台帳、main・他worktree・タスク定義/状態を確認する。
原因不明の差分は復元・削除せずSTOPする。
結果とSHAは`VALIDATION.json`と`PROTECTION.json`へ記録する。
原本・非公開監査と公開成果物は別ドライブへ保存し、CRC・SHA・独立展開を検証する。

## 実取得再開の条件とSTOP

- product-token/header bindingを明示的に審査する。既存HTTP headerから推測しない。
- 残る9項目、特に順位・reserved/query・回復処理・500 KiB能力を再審査する。
  追加の外部資料が必要なら、保存済み資料の確認または別途限定取得の承認を受ける。
  今回はRFC3986・errataを含め、追加資料への通信をしていない。
- A2〜A4、aboutj、B枠は、URL・host・予算・期限・scope・保存先を
  別工程で固定し、新しい明示承認を得る。旧G/I予算を復活させない。
- robotsだけでなくサイト条件・既知rate制限を確認する。
  UNKNOWN/DENY、未承認permit、証拠不整合、origin/identity不一致、
  予算・期限・保存先違反、説明不能な保護差分は通信不可/STOP。
- J版を実HTTP経路へ自動接続しない。旧版へrollbackするために新旧原本や
  receiptを削除しない。今回は配備・有効化・mergeをしていない。

B/C/D、HISTORY/PREDICTIONはHOLD、Phase AはBLOCKED、Phase BはNOT_AUTHORIZED。
モデルload/fit/推論・実確率計算・性能評価・T0・対象登録・将来予測保存は0。
本番collector・タスク・feed・Desktopの操作は0。
PARTIALでの調査成果保存は明示承認範囲であり、通信や予測の承認ではない。
