# NN v2 Phase 2.5N — G1識別子の正式採用

判定：`NN_V2_G1_UA_ADOPTED_OFFLINE_VERIFIED`。
対象branch：`feature/nn-v2-g1-ua-adoption`。
基準：M `ce39d7e3f868b33a14d657f433feeeafc96a5c87`。
採用は研究識別子の文書・オフライン契約に限る。通信許可、実adapter接続、本番適用ではない。
最終検証実績は [VALIDATION.json](../research/nn_v2/phase2_5N/VALIDATION.json) を正本とする。

| 役割 | 正式値 |
|---|---|
| HTTP User-Agent headerの予定値 | `J1AI-Research-Timing-Pilot/1.0` |
| robots group選択用の明示product-token | `Research-Timing-Pilot` |
| 新状態 | `G1_ADOPTED_OFFLINE_ONLY` |
| 採用日 | 2026-10-24 JST |
| 採用記録UTC | 2026-10-24T08:34:09.894465+00:00 |

根拠は今回のユーザーによるG1限定の明示指示。非公開指示のSHAはmanifestに記録した。
Lの固定候補と完全一致する。全文headerからtokenを抽出したり、version/digitを削除して生成したりしない。
採用値の比較はASCII bytesの完全一致で、trim・大小文字変換・Unicode正規化・別候補へのfallbackを行わない。
既存K parserが行うrobots group名のcase-insensitive比較は別の処理であり、変更していない。

適用対象は、今後別途承認されるNN v2の限定研究・取得計画。
Champion A、Weekend Batch、GUI、定時worker、運用設定、live transport、permit発行を対象外とする。
値・役割・scope・状態を変更する場合は、別versionと再審査・承認を必要とする。
Python定数やhashは、特権利用者による変更を防ぐ仕組みや署名ではない。

## 契約と旧schemaの互換性

[UA_ADOPTION_MANIFEST.json](../research/nn_v2/phase2_5N/UA_ADOPTION_MANIFEST.json) は
`NNV2_G1_UA_ADOPTION_V1`、証拠記録は `NNV2_G1_UA_ADOPTION_EVIDENCE_V1`。
[ADOPTION_SCHEMAS.json](../research/nn_v2/phase2_5N/ADOPTION_SCHEMAS.json) は、この不変の採用記録を別schemaで定義する。
全項目必須・追加field禁止・固定値の型と値を検証する。schema URIは識別文字列で、取得していない。

Lの `NNV2_UA_EVIDENCE_V1` は合成request専用で、E0 payloadも旧candidate stateに固定されている。
新状態を代入して使うと旧schema/validatorに適合しないため、旧schemaを拡張・書換えせず独立記録にした。
旧L候補の `CANDIDATE_FROZEN_NOT_ACTIVATED` は当時の事実として保持する。
旧G/Iのpermit、送信記録、A1/S1/S2原本、K/L/Mの正式結果は変更していない。

純粋validatorは [ua_adoption.py](../research/nn_v2/phase2_5N/ua_adoption.py)。
I/O、HTTP、adapter、model、permit発行APIを持たず、runtimeからimportされていない。
schema検証に加え、候補原本SHA、固定項目、UTC順序、MのURL台帳SHAと意味を検証する。
JSONの重複key・非有限数・不正UTF-8を拒否する。boolとintegerを同一視しない。
採用証拠より前の時刻の記録を採用済みと判定せず、実時計の絶対的真正性までは主張しない。

manifestのcanonical SHAはキー昇順・ASCII escape・compact JSON・LFのbytesを対象とする。
ファイルそのもののSHAとは別fieldで記録し、成果物全体は `SHA256-MANIFEST.json` で封印する。
検証にはschema・純粋validator・外部SHA台帳の照合を併用する。hash再計算だけを承認や実送信証明と扱わない。

## E0〜E4の証明範囲

| facet | G1の状態 | 未成立の事項 |
|---|---|---|
| E0 | 採用定数と意思決定記録のオフライン照合済み | 実adapterによる設定読込み・request/permit binding |
| E1 | 既存Lのオフライン設計のみ | 新request構築・実clientへの受渡し |
| E2 | UNKNOWN／未実施 | 実送信の開始・最終header・終了・outcome |
| E3 | UNKNOWN／未実施 | 独立観測・成立した方法・TLS/privacyの審査 |
| E4 | 新規取得なし | 新response/storage証拠。旧原本の送信UAはUNKNOWNのまま |

新しいE0は「採用された設定契約の証拠」であり、「実adapterが読んだ設定の証拠」とは区別する。
旧原本へ新UAで取得した属性を後付けしない。E4からE2/E3へ昇格しない。
G1/G2/G3/G4は別ゲートで、今回成立するのはG1のみ。

## 六つの固定URLと9 UNKNOWN

封印済みA1を再取得せず、Mの純粋scope解析を再生し、6件すべてのcontext/certificate SHA一致を確認した。

| ID | URL | 過去Mのrobots仕様判定 | G1後の総合通信 |
|---|---|---|---|
| A1 | `https://www.jleague.jp/robots.txt` | 固定A1・固定識別子に条件付きALLOW | 不可。再取得承認なし |
| A3 | `https://www.jleague.jp/general/kiyaku/` | 同上 | 不可 |
| A4 | `https://www.jleague.jp/general/copyright/` | 同上 | 不可 |
| B1 | `https://www.jleague.jp/j1/news/` | 同上 | 不可 |
| A2 | `https://aboutj.jleague.jp/robots.txt` | UNKNOWN（host原本なし） | 不可 |
| B2 | `https://aboutj.jleague.jp/corporate/pressrelease/` | UNKNOWN（host原本なし） | 不可 |

URLは出典と計画のidentity文字列であり、今回アクセスしていない。
wwwの4件はgroup1の `*`・一致規則0の固定原本範囲だけの結果。
aboutjへwwwの原本を流用しない。両hostの規約・自動取得条件は未確定。
新permit/G4開始承認、実adapter qualification、freshness/scope policyも不足している。

**規範集計は15 PASS／0 FAIL／9 UNKNOWNを維持**。G1で完全解消した正式項目は0。

- `agent_grammar`：識別子の選択・正式採用だけ成立。実adapter binding／実送信の未確認が残る。
- `sealed_A1_replay`：採用識別子による固定範囲再生は成立。新requestの証拠、host適用、アクセス条件、鮮度、別承認は残る。
- `rule_grammar`、`longest_rule`、`reserved_octets`、`query`、`encoding_errors`、`parse_limits`、`standard_examples`：G1では規範不足・実装制約を解消しない。

MのP0/P1/P2は当時の複合条件に対する分類として保持する。新記録ではG1未承認という停止理由のみを充足済みと分離し、
規範UNKNOWNや残りのSTOP条件を消さない。RFC/Google完全準拠は宣言しない。

## 検証と保護

今回の新規68 PASS（明示negative-control 56件）、既存回帰再実行1,092 PASS、合計1,160 PASS。
FAIL／ERROR／skipは0、warnings-as-errors。過去のM 1,092 PASSは別の歴史的証跡として保存する。
negative-controlは識別子・scope・schema・時刻・証拠昇格・過去原本帰属・他用途流出・旧fixture改変を対象とする。
L/Mのheader検査と重なるが、今回はG1意思決定記録と旧状態との境界を検証する。
application guardの範囲は対象Pythonテストprocessのみで、OSネットワーク隔離や実HTTP adapter安全性の証明ではない。

開始baselineは72,708ファイル、29既存worktree。最終SHA・identity・metadata差分0。
モデル53 payload、既存19予測、288詳細原本、
A1/S1/S2・旧台帳、既存GUIのコード・snapshot・process所有関係・endpoint、2タスク、mainを監査する。
既知の独立運用事象は過去証拠を保持し、正常更新・研究起因のいずれとも推定しない。
新規HTTP全method／DNS probe／permit発行更新／実adapter接続／model実行／タスク操作は0。
通常Git pushのみ成果物保存の明示許可範囲で行う。

B/C/D各288 HOLD、HISTORY／PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持する。
次の別承認条件は [G2 handoff](NN_V2_G1_TO_G2_HANDOFF.md) を参照する。
