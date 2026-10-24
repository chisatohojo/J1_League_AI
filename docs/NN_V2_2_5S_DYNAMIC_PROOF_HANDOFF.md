# NN v2 Phase 2.5S — 動的実証へ進む条件

オフラインゲートは `NN_V2_2_5S_OFFLINE_QUALIFICATION_READY`。実Windows隔離・Job/ACL・複数process・TLS・transportの動的Qualificationを実施・承認した状態ではない。今回のstagingやfake Job結果を実証PASSへ昇格せず、RのBLOCKEDと6 URLのterms UNKNOWN・permit HOLDを維持する。

## G3に残る条件

| 区分 | 未証明部分 | 必要な次工程 |
|---|---|---|
| P0 | A1現在性または限定再利用根拠、研究独自鮮度方針、適用terms・保存加工scope | 原本・方針の審査。新A1 GETが必要なら別のexact URL承認 |
| P0 | 専用workerの最終contract/code/config SHA、proxy・E3方針、保存先identity、時刻窓・予算・STOP条件 | DRAFT 5s/15s/全体deadline案を審査して凍結。旧G/I permit再利用禁止 |
| P1 | Job membership・wall-clock watchdog・子孫停止・breakaway/handle漏洩 | 承認された非本番Windows環境で実process試験 |
| P1 | token・owner/group・DACL・reparse・volume・OS write/modify/delete拒否 | 非本番の保護mirrorを使った実ACL試験 |
| P1 | 永続reservationの実process競合・real crash・storage fault・trusted head | 隔離stagingを使い、故障点と復旧責任を固定して実証 |
| P2 | 承認取得時のE2/E3/E4、TLS・送信・原本保存 | 事前に機構をqualificationし、後日別承認の実通信時にのみ観測 |

P2の実観測が初回send前に存在しないことだけで循環停止させない。必要なのは事前の観測機構・独立性・保存境界のqualificationであり、実E2/E3/E4を合成fixtureで埋めない。

## 次に承認する具体的な動的試験単位

以下は提案であり、今回の指示で自動承認しない。環境やworkerは作成・起動していない。

1. **専用worker／Job試験**：非本番の実行identity、code/fixture SHA、許可exeと子孫数、専用Jobの作成・設定、parent/watchdog・kill/cleanup、結果保持rootを承認対象とする。suspended状態でJobへ割当て、PID・creation time・exe SHA・membershipを確認してからresumeする。DNS相当のblocking、TLS/read相当の遅延、保存停止、worker/parent異常終了、子孫escapeを故障注入する。受入条件は指定wall-clock内の停止、cleanup予算内にowned active count 0、未知の終了はUNKNOWN_OUTCOME、無断再送0。CPU時間制限をwall-clock制限と呼ばない。未所有PIDや既存GUI/serverを終了対象にしない。
2. **token／ACL／パス境界試験**：新規test rootにstaging/raw/ledgerと、予測・モデル・公式原本・GUI・task・他worktreeを模した非本番mirrorを作る操作を別承認する。現在のproduction pathへのwrite probeや本番DACL変更は含めない。同一ユーザーでは書けてしまう対照と、選定した制限identity/token/環境でOSがcreate/append/overwrite/modify/rename/deleteを拒否する結果を区別する。owner・継承group・privilege・DACL変更権、junction/symlink・別volume・ADS・path差替え競合も対象にする。許可rootへの正常保存、禁止mirrorへのOS access-denied、逸脱時の即時STOP、元データ不変を受入条件とする。VMや別ユーザーが必要かは構成審査で決め、無断で構築しない。
3. **永続attempt実process試験**：新規stagingと独立trusted-head保持先、複数process identity・起動上限、同時reservation/CAS、claim/state/head置換の各点のreal crash、ENOSPC/EACCES相当の故障注入、部分保存・手動復旧ルールを承認対象とする。受入条件は一つのreservationだけが有効になること、消費の巻戻し・ID再利用・自動再送0、曖昧なcommitは手動審査HOLD、完全なchain/readback保持。今回の論理instance競合を実process競合の代わりにしない。電源断保証まで必要なら、directory flush・Windows/storage stackの仮定と専用媒体での試験を別途審査する。
4. **必要なTLS/capture試験**：実TLSのqualificationが必要なら、許可した非本番endpoint・証明書fixture・privacy・E3独立性・通信上限を別承認する。正しいCA/hostnameの場合と、期限・hostname・chain異常を拒否する場合を確認する。TLS検証の無効化、global trust store変更、外部公式siteへの接続を一般的な試験承認へ混ぜない。今回のSはloopbackを含むsocket通信0である。

## 次回の取得審査との分離

A1のキャッシュ適格性だけで現在内容不変とは認定しない。A1の新規観測または限定利用根拠、採用する鮮度方針、アクセス条件を別に確定する。A3/A4に進む場合も、必要条件成立後の新しい単一セッション・exact subset・最大試行数・保存先・時刻窓を承認する。Rの未使用2回を復活させない。

その後もG3本審査・permit発行・G4開始は別単位である。Sでは新規本番attempt ledgerを作成せず、取得用permit ID、G4 authority、HISTORY/PREDICTION admission、B/C/DのHOLD解除を生成しない。

## 停止・証拠保持

原本・code・identity・clock・path・head SHA不一致、期限超過、cleanup不完了、予期しないwrite/通信、reparse/volume逸脱、ledger破損・部分保存、未確定outcomeで停止する。新しいJobやfixtureの後始末も承認された所有scopeだけに限定する。旧原本・既存worktree・旧ledgerを修復せず、未使用予算の返却・lock強制回収・自動再送は行わない。

今回のGit操作はローカルcommitまで。Rの未push commitを保全し、Sでもpush/fetch/pull/ls-remoteは0、remote整合性は未検証で終了する。
