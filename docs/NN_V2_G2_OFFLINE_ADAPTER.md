# NN v2 Phase 2.5O — G2 offline request adapter

判定：`NN_V2_G2_OFFLINE_ADAPTER_VERIFIED`。
基準commit：G1 `5eefeec9fe2f7b7cd93fa6820097353bdab96e9c`。
専用branch：`feature/nn-v2-g2-offline-adapter`。
今回実証したのは、G1採用識別子からcandidate request・最終client入力・E1証拠・メモリsinkまでのオフライン契約である。
実transport接続、G3 permit審査・発行、G4通信は承認していない。

```text
sealed G1 manifest / schema / candidate / M URL matrix bytes
        -> IdentityProvider (hash + schema + scope + adoption UTC)
        -> build_request / OfflineSession (fixed six URLs, one-use IDs)
        -> actual_gates (robots / terms / permit separate)
        -> final client-input equality + E1 record
        -> explicit synthetic gate fixture only
        -> fixed MemorySink -> byte readback + E1 revalidation

Real transport: absent; no callback, CLI, environment override or fallback
```

## 結合点と既存実装

G/Iの研究workerは `fetch_once` 内でTLS接続後に `conn.request('GET', PATHS[i], headers=...)` を呼ぶ。
UAは旧worker内の定数で、既存のfactory注入も接続処理を含む。今回この関数・main・旧permit検証を起動していない。
代わりにASTでmethod/path/header形状・UA定数・コードSHAを照合し、同じ送信引数の**データ境界**を新しい別実装へ切り出した。
`client_input` はmethod、request target、Host/User-Agent/Accept-Encoding/Connectionの値だけを返す。
旧workerの変更・import・factory呼出しや、本番collectorへの結合はない。B入口用のlive workerも新設していない。

[offline_adapter.py](../research/nn_v2/phase2_5O/offline_adapter.py) はG1 validator、Mの固定URLとK parser、Lの合成request/plan checkerを再利用する。
Lは `synthetic.invalid` 専用のままで、実URLや新G1 stateを代入してlive化していない。
G2の実URLは封印済みscopeとの照合文字列。旧workerへ渡すtaskや実行可能permitではない。

## Identity providerとrequest契約

正式値は `J1AI-Research-Timing-Pilot/1.0` と `Research-Timing-Pilot`。
providerはG1 manifest/schema・旧候補・M matrixのbytesを受け取り、固定SHAを先に検証する。
G1 JSON Schemaと純粋validatorでstate/scope/時刻を再検証し、値はmanifestから取得する。
送信引数の再検証でも同じproviderを照合する。環境変数・CLI・UA引数・任意transportの注入機能はない。

requestは `NNV2_G2_CANDIDATE_REQUEST_V1`、scopeは `NN_V2_G2_OFFLINE_ONLY`。
request/run IDは `syn-` namespace。source evidence revisionはM commit、matrix SHAも固定する。
requestには完全URL、origin/host/443/path/query、method、UA/token、作成UTC、G1 file/canonical SHA、
adapter revision、robots reference SHA、robots/terms/permitの実状態、redirect/retry/parallel=0を含める。
URLはMの6件との完全一致で、query追加、明示port、大文字host、percent表記、dot segment、末尾`?`等を正規化で救済しない。
作成時刻は採用以後かつ検証時刻以前を要求する。時計の絶対的真正性は別問題。

`OfflineSession` は同一run内のrequest ID・URL重複、二重deliveryを拒否する。
sinkの既存IDも上書きしない。故障時はattemptを保持してterminal STOPとし、再送・自動再開しない。
これはメモリ上の試験契約で、processをまたぐ永続的な一度限りのpermit/lock管理を実証したものではない。

## 独立ゲート

順序はG1、request schema、method、URL scope、robots、terms、permit、identity、redirect/retry、final pre-send。
不正schema・identity・値の不一致は例外で即STOPし、UNKNOWNとして隠さない。
正常なrequestのgateはPASS/DENY/UNKNOWNを別記する。final pre-sendは実送信の可否で、E1表現検査の合格と区別する。

| 固定対象 | robotsの参照結果 | terms | 新permit | 実通信 |
|---|---|---|---|---|
| A1 `https://www.jleague.jp/robots.txt` | 固定A1・識別子に条件付きALLOW | UNKNOWN | UNAPPROVED | 不可 |
| A3 `https://www.jleague.jp/general/kiyaku/` | 同上 | UNKNOWN | UNAPPROVED | 不可 |
| A4 `https://www.jleague.jp/general/copyright/` | 同上 | UNKNOWN | UNAPPROVED | 不可 |
| B1 `https://www.jleague.jp/j1/news/` | 同上 | UNKNOWN | UNAPPROVED | 不可 |
| A2 `https://aboutj.jleague.jp/robots.txt` | UNKNOWN、host原本なし | UNKNOWN | UNAPPROVED | 不可 |
| B2 `https://aboutj.jleague.jp/corporate/pressrelease/` | UNKNOWN、host原本なし | UNKNOWN | UNAPPROVED | 不可 |

**規範15 PASS／9 UNKNOWNは不変**。現行sourceの鮮度や規約を新たに確認したとは扱わない。
この4 URLの条件付き結果は固定原本・固定parser/spec contextだけの既存証拠。
aboutjへwwwの原本を流用しない。A1再取得・A2〜A4・B探索の通信権限は全て0。

## 合成fixtureとメモリsink

`G2_SYNTHETIC_GATE_FIXTURE_V1` はrequest ID/hashを結合した試験入力のみ。
合成robots bytesを既存K parserで評価し、termsの合成状態と、Lの `synthetic.invalid` subviewに対する合成planを検査する。
planの期限、scope、対象、ID、予算、redirect/retry/parallelをLの変更なしで拒否できることを検証した。
このsubviewは架空hostへの対応関係を明示した計算用入力であり、新しい実URLや取得候補を追加しない。

合成の全ゲートPASSでのみ固定MemorySinkへ進む。DENY/UNKNOWN、plan欠落、faultでは進行を拒否する。
**合成PASSは実robots/terms/permitの状態を一切書き換えない**。aboutjの合成例でも実状態UNKNOWNを保持する。
sinkはrequest証拠bytesの保持とreadbackだけを行い、responseを返す機能を持たない。
任意callback・subclassをtransportとして受け入れず、読戻しのbyte/SHA不一致や受領前後故障をSTOPにする。
記録は6固定URL分の候補request/E1、合成sink例6件。HTTP送信数ではない。

## E0〜E4とschema互換性

| facet | 今回の証明 |
|---|---|
| E0 | G1正式manifestをoffline providerが検証・読込み。実HTTP workerの設定読込みではない |
| E1 | 予定request・最終client引数の一致、hash/identity/time、メモリsink読戻しを検証 |
| E2 | UNKNOWN。実送信なし |
| E3 | UNKNOWN。独立観測なし。fake sinkは独立した実通信観測ではない |
| E4 | 新規response/raw取得なし。response/status/hash/outcomeはnull |

[E1_REQUEST_EVIDENCE.json](../research/nn_v2/phase2_5O/E1_REQUEST_EVIDENCE.json) と
[REQUEST_EVIDENCE_SCHEMA.json](../research/nn_v2/phase2_5O/REQUEST_EVIDENCE_SCHEMA.json) を公開する。
G2 E1の版は `NNV2_G2_E1_OFFLINE_V1`。Lの `NNV2_UA_EVIDENCE_V1` のfacet意味を維持し、
実URL・採用manifestの証拠を旧synthetic-only recordと偽装しないよう別representationにした。
旧schema/validator/候補状態・旧E0〜E4原本は変更しない。schemaだけでなく純粋検証とSHA台帳の照合を必須にする。
adapter revisionは契約versionを示し、実コードSHAは契約・成果物SHA台帳に結合する。
canonical JSONはHTTP wire bytesではない。古いA1/S1/S2へ新UAの送信属性を後付けしない。

## 検証と保護

今回の新規108 PASS（明示negative-control93件）、関連回帰再実行1,160 PASS、合計1,268 PASS。
FAIL/ERROR/skip/deselectは0、warnings-as-errors。過去G1の68+1,092 PASSは別証跡として保持する。
実通信・原本依存の新規試験を混入させていない。回帰にあるHTTP worker試験は全て合成factory/bytesのみと確認した。

専用テストprocessでsocket生成・DNS・外部process起動・HTTP境界・許可領域外write・実model実行をaudit guardで拒否する。
3件の意図的negative-controlはsocket.__new__、socket.getaddrinfo、subprocess.Popenで拒否された。
socket、DNS結果、子processは返されていない。実fixture試験中の予期しない禁止操作試行は0。
**application guardのみであり、OS全体のFirewall隔離、任意native codeへの防御、実transport/TLS/Job/ACLの安全性は未実証**。
対象コードの静的import制限と組み合わせた、このオフライン実装の検証範囲に限定する。

新baselineは73,977ファイル、30既存worktree。モデル53 payload、既存19予測、公式288詳細原本、
G/I raw・台帳・permit、旧phase、Champion/Weekend/GUI、稼働server、2タスク、mainを照合する。
最終実績・静的検証・保護結果は [OFFLINE_INTEGRATION_VALIDATION.json](../research/nn_v2/phase2_5O/OFFLINE_INTEGRATION_VALIDATION.json) と関連SHAを参照する。
研究HTTP/HTTPS・DNS・socket接続・新permit・実モデルload/fit/推論/評価・GUI/タスク操作は0。
通常Git pushは承認された成果物保存に限定する。

B/C/D各288 HOLD、HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDを維持。
次工程の承認材料は [G3 handoff](NN_V2_G2_TO_G3_HANDOFF.md)。G2から自動的に通信へ進まない。
