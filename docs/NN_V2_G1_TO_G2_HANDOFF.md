# NN v2 — G1からG2への引継ぎ

G1識別子採用の判定：`NN_V2_G1_UA_ADOPTED_OFFLINE_VERIFIED`。
HTTP UAは `J1AI-Research-Timing-Pilot/1.0`、robots product-tokenは `Research-Timing-Pilot`。
本書は次工程の承認材料であり、G2の実adapter接続、G3 permit、G4通信を許可しない。

## 次のオフライン設計で確認すべきこと

別途G2の範囲を承認した後に、固定code/設定SHA、manifest/schema照合と適用scopeを設計する。
旧Lのrequest schemaを状態文字列の置換でlive化せず、新しい実装・schema versionを明示して互換性を審査する。
本番Champion、Weekend Batch、GUI、定時workerへ設定を伝播させない。

| 項目 | G2で証明すべき境界 |
|---|---|
| E0 | 実際に読み込む採用manifestのSHAと設定revision、request/permit identity。G1の意思決定証拠とは別 |
| E1 | 唯一のUA、明示token、method/URL/header、prepared hash、秘密field拒否、最終client入力照合 |
| E2 | 固定adapterの送信開始・完了/失敗・最終header・UTC・outcomeを保存する仕組みのmock qualification |
| E3 | 独立観測が必要かをscopeで決定。要求する場合は方法・独立性・TLS/privacyを別審査 |
| E4 | response/raw/metadata/request/receiptの保存・fsync・readback・SHA・所有権と有限cleanup |
| attempt | 完了不明でも1回消費、retry/redirect/parallel禁止、403/429/TLS/timeout時STOP、旧予算復活禁止 |
| robots | 固定原本・host・完全URL・UA/token・parser/spec SHA・freshnessの再照合。未知影響の除外証明を更新 |
| A/B | 条件確認Aと探索Bの予算・目的を分離。bootstrapは限定承認の対象、一般UNKNOWN迂回機能にしない |

事前に必要なのはE2/E4等を記録できる仕組みのqualificationであり、同じ初回requestの実E2/E3を送信前に要求しない。
実記録は承認されたG4通信後に検証する。E2 STARTEDだけでは完了としない。
E3不要を明示承認した範囲ではNOT_OBSERVED/UNVERIFIEDを残し、E2/E4で代用して独立観測済みとしない。
暗号化pcapだけでHTTP headerを証明しない。MITM・復号・証明書変更は承認されていない。

www固定4 URLへの7項目のP2除外は、Mの固定contextだけの既存証拠。新原本・URL・version変更へ流用しない。
aboutjはhost原本・運営主体・規約適用範囲が不足する。A2を含む初回条件確認の安全な扱いは別scopeとして審査する。
既知の禁止・より厳しい条件を優先し、扱いが決まらなければHOLD。
G1は規範9 UNKNOWNを消していない。原本不足や仕様矛盾が必要範囲へ影響する場合は取得前にSTOPする。

## 別承認が必要な操作

1. **G2**：実adapterを結合する範囲、offline/mock検証、schema/capture/所有権・保存・停止設計。
2. **G3**：新しい完全URL集合、host/port/method、UA/token、code/input SHA、保存先、時刻窓、回数・本文・timeout上限、E3要否を固定した新permit。
3. **G4**：そのpermitによるrun開始。通信後の実E2/E4とscopeに従うE3を独立監査。

旧G/Iのpermitは終端状態のまま、未使用枠も再利用しない。A2〜A4取得・B探索・A1再取得は今回許可していない。
G2の設計完了からG3/G4へ自動的に進めない。HISTORY admission、モデル性能評価、T0／予測登録も別工程。

失敗時はattempt・不完全receipt・原本を保存して停止する。自動再開・budget巻戻し・不明lock強制回収をしない。
今回のコードは純粋validatorのみで、上記adapterや停止workerを実装・接続していない。
