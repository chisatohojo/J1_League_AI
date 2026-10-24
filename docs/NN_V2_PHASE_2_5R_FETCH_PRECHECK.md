# NN v2 Phase 2.5R — A3/A4取得前審査

判定：`NN_V2_2_5R_FETCH_BLOCKED`。A3/A4とも未送信、消費attemptは0、HTTP/DNS/socketは0。予期しない通信や保護違反によるSAFETY_STOPではなく、送信前必須条件を確認できなかったための停止である。

今回の利用者指示は規約確認用の限定取得を条件付きで承認している。Jリーグの利用許諾、G3本番permit、G4、研究データ収集への承認とは区別する。terms本文がないことを既知の禁止と認定せず、robotsの現在性と今回の実行経路を個別に審査した。

## 正本とscope

基点はQ `bd424d86fe56ddb20adfb5ff40fc41b62e1f21bf`。独立branchは `feature/nn-v2-a3-a4-terms-fetch`、新規worktree内のR成果物だけを追加する。既存worktreeの変更、原本・旧ledgerの上書き、Git通信は行わない。

G1 `5eefeec9fe2f7b7cd93fa6820097353bdab96e9c`、G2 `665f0144cffa3b1b569cabf79e41394de9f3914d`、G3事前審査 `d57e182521dbf354b41b536a67e27b17440d2950`、Qのcommitとmanifest・hashを照合した。QのGit同期は前工程の `NN_V2_P0_GIT_PUSH_VERIFIED` 記録を参照し、今回はls-remote等で再確認していない。機械可読な証拠pinは [INPUT_EVIDENCE.json](../research/nn_v2/phase2_5R/INPUT_EVIDENCE.json)。

| 対象 | exact URL | 承認上限 | 今回の実績 |
|---|---|---|---|
| A3 | `https://www.jleague.jp/general/kiyaku/` | 1 GET・1 MiB | 未送信 |
| A4 | `https://www.jleague.jp/general/copyright/` | 1 GET・1 MiB | 未送信 |

UAは `J1AI-Research-Timing-Pilot/1.0`、robots product-tokenは `Research-Timing-Pilot`。connect 5秒、read 15秒、redirect/retry/外部resource取得各0、Cookie・認証なし、A3→A4の順序、単一セッション、合計最大2試行を予定仕様として固定した。これらの上限を実送信で検証したという意味ではない。

## R-0〜R-3の結果

| 段階 | 結果 | 証拠・残る条件 |
|---|---|---|
| R-0 | ローカル確認PASS | Q/G1/G2/P、58公開pin・47私有pin、A1と保存済み規範原本、既存permit終端状態、既存33 worktreeを確認 |
| R-1 | HOLD | 固定A1のA3/A4 path一致は条件付きALLOW。ただし現在有効性・使用方針が未立証 |
| R-2 | 実経路未qualification | 旧workerの条件、今回のtimeout・運用write禁止・proxy方針・保存先が一致する証拠なし |
| R-3 | 実送信用ledger未初期化 | 合成storeで排他作成・fsync/readback・再open後の重複拒否を試験。実attemptは予約・消費していない |
| R-4以降 | 未実施 | raw取得・実TLS・実E2/E4・本文評価なし |

詳細は [FETCH_PRECHECK.json](../research/nn_v2/phase2_5R/FETCH_PRECHECK.json) と [ENVIRONMENT_REVIEW.json](../research/nn_v2/phase2_5R/ENVIRONMENT_REVIEW.json)。

## R-1：固定評価と現在性を分離

A1原本は `%LOCALAPPDATA%/J1AI/NNResearch-phase2_5F-A-approval-pending-20261023-01/A/access-0001/raw.bin`。
SHA-256は `3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c`、取得UTCは `2026-10-23T09:46:47.645062+00:00`。取得UTCと審査UTCを直接比較した経過時間は審査時点で約29時間である。時刻、秒数、hashをJSONへ記録した。

採用UA/tokenと既存Kのpure parserで固定bytesを再評価し、A3/A4とも適用groupの一致規則数0、固定path結果ALLOWを確認した。これは現在公開されているrobotsのALLOW、規範全体のPASS、規約上の許諾ではない。

保存済みRFC 9309 §2.4は、通常24時間を超えるキャッシュ使用を避ける推奨と到達不能の場合の例外を記載している。参照した保存原本SHA-256は `bbaa280636d3e38f0a1a130a5ce40e9753db1ed18c860945b0bf795ff8dc1a87`。段落 `section-2.4-1` のbyte範囲とSHAをJSONに結び付けた。新しい仕様取得はしていない。

この推奨を法的禁止や新たな承認TTLに置き換えていない。保存済みCache-Controlのs-maxageも利用許諾・独自TTLとして採用しない。標準cache controlの解釈を含む今回の利用方針と、到達不能例外の適用根拠は未確定である。QでUNKNOWNだった現在有効性を、今回の条件付き承認だけでPASSへ昇格しない。

利用者指示「対象URL：A3・A4の2件のみ」によりA1再取得はscope外であり、GET/HEADで鮮度を補完していない。今回の原本だけを使う具体的な根拠、または別承認での現行性確認が必要である。R-1をPASSにできないためR-4へ進まない。

## R-2：今回の制約下での実経路評価

旧GのHTTP workerはsource/ASTだけを読み、import・実行していない。基盤は既存の `http.client`／`ssl` で、ローカルの現Python・clientファイルSHA、TLS contextの `CERT_REQUIRED` と `check_hostname=True` を確認した。これは実サーバーの証明書・hostname検証結果ではない。

旧Gは4 URL用の旧permit、10秒期限、親のOwnedJob、専用DACLの作成・確認を前提とする。旧permitは終端済みで再利用禁止であり、その成功を今回の5秒connect／15秒read・2 URL用経路のqualificationとして扱えない。旧parent、worker、Windows primitiveのSHAと該当実装を照合した。

読み取り専用ACL確認では、現在ユーザーに運用official rootとChampion AモデルrootのFullControl ACEがあり、拒否ACEはなかった。書込みprobeは実行していない。この権限状態だけでは「研究環境から運用ファイルへ書込み不可」を立証できない。今回の合成テストprocessにはapplication guardをかけたが、実transportのwrite拒否やOS隔離とは呼ばない。

環境proxy変数は未設定、Windowsの明示proxyは無効、PAC URL設定は存在した。PACの取得・実行はscope外なので行っていない。旧Gは直結socketを使いproxy_used=Falseとしていたが、今回の直結可否・PAC運用影響は未審査である。

監査・合成fixture領域の所有者と継承DACLは読み取った。実raw専用rootは未作成で、実保存先identity・アクセス境界をPASSにしていない。Windows Firewall／ACL／Job／VM設定を変更せず、OS隔離が未実証でも安全に流用できるかを、timeout・permit・権限・proxy・保存先ごとに検討した結果、今回の経路を安全と認定する証拠が不足した。

## R-3：合成永続attemptの試験範囲

[offline_review.py](../research/nn_v2/phase2_5R/offline_review.py) はHTTP/DNS/socket/process/model/ACL/Job APIを持たない。ライブ送信を許可する出力やcallbackを設けず、仮に合成審査が全PASSでも実送信は不可とする。

合成storeは `syn-` namespaceの専用fixture内に限り、intentを排他的新規作成し、fsync後に同じbytesを読み戻す。別instanceで再openしても同じURLの消費を保持する。timeout、保存失敗、crash相当の未完了intentは再送・返却・A4進行を拒否し、壊れたledgerを修復しない。実process crash、複数process競合、電源断・親directory永続性、OS境界は未実証である。

実状態の [FETCH_ATTEMPT_LEDGER.json](../research/nn_v2/phase2_5R/FETCH_ATTEMPT_LEDGER.json) は予定A3/A4のrequest SHAと未送信状態を保持する。attempt ID・送信時刻はnull、予約・消費はfalse、実attempt配列は空。合成storeの消費を実試行数へ混ぜない。今回の単一セッションは未送信で終了し、未使用枠を次回へ持ち越さない。

## 検証と保護

新規94 PASS、関連回帰1,517 PASS。新規の明示negative-controlは86テスト。初回は1 MiB超fixtureの自動test IDがWindows環境変数の長さ上限に達し、setup/teardownで2 ERRORとなった。短いIDに修正し、新規全件を再試験した。初回記録は最終PASS件数に加えていない。

実行した14モジュールはRと既存Q/G1/G2/G3/robots/accessのオフライン関連に限る。server/socket境界を含む3既存モジュール（constructorを呼ぶ4ソースtest関数、validation caseを含む）を保守的に除外し、他の179モジュールも今回の回帰scope外として未収集。未収集のパラメータ展開後件数は推測していない。実行対象内skip・deselectは各0。外部通信テスト、モデル学習・評価、GUI操作試験は実行していない。

保護開始baselineは120,156ファイル・既存33 worktree。前Git工程の保護対象に差分0を確認して引き継いだ。新しいRのraw/attempt・fixtureと、既存原本・モデル53 payload・予測・旧research・permit・Weekend・GUI・mainを分離する。最終結果は [VALIDATION.json](../research/nn_v2/phase2_5R/VALIDATION.json) と [PROTECTION_VERIFICATION.json](../research/nn_v2/phase2_5R/PROTECTION_VERIFICATION.json)。Git通信、実GET、DNS/socket、実モデル、GUI／タスク／OS policy変更は0である。
