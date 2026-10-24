# NN v2 — G2からG3への引継ぎ

今回の判定：`NN_V2_G2_OFFLINE_ADAPTER_VERIFIED`。
これはオフラインE0/E1・gate・固定メモリsinkだけの合格で、G3 permit審査・発行、G4通信の承認ではない。

## G3審査に不足する証拠

| 項目 | 次に必要な確認と別承認 |
|---|---|
| 実worker結合 | G2コードには実transportがない。将来のsend adapter/launcherを別途実装・pinし、設定読込み・最終headerをmockでqualified化 |
| 安全機構 | TLS/hostname、redirect/retry/parallel禁止、timeout/body cap、親deadline/cleanup、Job所有権、ACL/reparse、fsync/readbackを対象実装で再検証 |
| 実行分離 | OS隔離/通信制限の適用範囲、外部プロセスやnative経路、model/runtime非共有境界を審査。今回のapplication guardを実HTTP環境保証に転用しない |
| 原本・scope | URL/host/port/method/UA/token、raw/spec/parser/code/config SHA、source revision、freshness policyと時計を固定 |
| www | A1の固定4 path限定評価だけ。規約・copyrightの現行内容と自動取得条件は未確定 |
| aboutj | host固有robots・運営主体・規約適用範囲がUNKNOWN。wwwの証拠で代用しない |
| 条件確認A | 未読規約や初回robotsを確認する限定bootstrap scopeを明示審査。既知の禁止・厳しい条件を優先。一般UNKNOWN回避にはしない |
| 探索B | 条件確認Aと分離。host固有条件が成立した入口だけを別permitで審査し、article追加や検索・paginationを黙って含めない |
| 一度限りの試行 | 永続permit消費、request/run ID一意性、二重実行拒否、完了不明でも消費済み、異常終了時receipt整合を検証 |
| E2/E4 | 最終header、開始/終了/outcome、実UTC、response/raw/metadata/request/receiptと読戻しを記録する機構をqualified化 |
| E3 | 要否と独立観測方法・TLS/privacyをscopeで明示。暗号化pcapだけをheader証拠としない |

G2は予定requestの入力契約を実証したが、上表のWindows動的保護・実HTTP耐障害性を全て試験したとは扱わない。
これらを満たすための追加オフライン/隔離qualificationも、実transport接続を伴うなら別の明示承認を必要とする。
必要証拠が揃わない状態ではpermitを発行しない。

## 新permitで固定すべき項目

新しいpermit ID、完全URL集合と順序、host/443/GET、正式UA/token、code/source/manifest/schema SHA、
保存先identity/所有者、開始・失効UTC、URL毎/合計回数、本文/headers上限、timeout/間隔/全体deadline、
redirect/retry/parallel=0、E3要否、STOP・保存・復旧条件を審査する。
この文書は設計上の必要fieldの一覧であり、permit本体や新しい通信予算を作成していない。

正式UAは `J1AI-Research-Timing-Pilot/1.0`、tokenは `Research-Timing-Pilot`。
旧G/I permitは終端状態のまま。未使用枠を復活させない。A1 refreshも別の正確な再取得承認が必要。
G2の合成planを、scope書換えや保存先変更で実permitへ転用しない。

## 通信前後のゲート

通信前：G1採用、対象実装のG2 qualification、別途G3承認、G4開始承認、当該requestのE0/E1を要求する。
同じ初回requestの実E2/E3を送信前に要求する循環は作らず、事前にはcapture機構の成立性を検証する。
通信後：実E2/E4、承認scopeに従うE3の観測状態を検証してから次URLへ進む。
E3が対象外と明示承認された場合もNOT_OBSERVED/UNVERIFIEDを残し、E2/E4から独立観測へ昇格しない。

403/429・TLS/timeout・完了不明・identity/SHA/receipt不一致は全体STOP。
attemptと不完全証拠を保持し、再試行・budget巻戻し・自動再開・lock強制回収を行わない。
G2のmemory readbackはfilesystem永続性・電源断耐性の証明ではない。

規範15 PASS/9 UNKNOWN、B/C/D・HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZEDは不変。
履歴admission、T0、評価、NN/Champion実予測も承認対象外。
