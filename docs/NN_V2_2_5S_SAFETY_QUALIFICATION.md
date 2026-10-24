# NN v2 Phase 2.5S — 取得前安全境界のオフラインQualification

最終ゲート：`NN_V2_2_5S_OFFLINE_QUALIFICATION_READY`。4 Trackの保存原本・静的契約・合成モデル・staging I/O検証と、動的実証へ進む条件を整理した状態である。実Windows隔離、実Job/ACL、実process競合、transport、新規GET、permit、G4の承認・実証完了を意味しない。

基点は未pushのR `4acaf75b7fab4517508d3d174b82e70a642cb09b`。独立branchは `feature/nn-v2-offline-safety-qualification`。R、Q、P、G1/G2と規範評価Mのmanifestを照合し、過去成果物と旧permit/attemptを変更していない。HTTP UA `J1AI-Research-Timing-Pilot/1.0`、robots product-token `Research-Timing-Pilot` を維持する。Git remote設定をローカルで読み取ったが、実remote一致は未検証で、Git通信は0件。

## Qualificationの区分

正本は [QUALIFICATION_MATRIX.json](../research/nn_v2/phase2_5S/QUALIFICATION_MATRIX.json)。各項目にrevision・hash・方法・未証明部分・次操作・追加承認・STOP条件・G3への影響を付した。

| Track | 今回立証した範囲 | 状態 | 残る動的・外部証拠 |
|---|---|---|---|
| A robots | 保存原本・headers・規範段落・契約の静的照合 | PROVEN_STATIC_ONLY | 現在性・採用済み研究鮮度方針はUNKNOWN |
| B timeout/Job | 期限階層、連続read遅延、保存期限、停止の仮想時計モデル | PROVEN_OFFLINE | 実Job・ブロッキング呼出しの中断・子孫停止はREQUIRES_DYNAMIC_APPROVAL |
| C write境界 | 実ACLの読取り、合成Windowsパス制限のnegative-control | PROVEN_STATIC_ONLY／合成モデル検証済み | OS強制のwrite/modify/delete拒否はREQUIRES_DYNAMIC_APPROVAL |
| D attempt | 新規stagingの排他claim、fsync/readback、atomic replace、論理CAS・再open・故障注入 | PROVEN_OFFLINE | 実process競合・実crashはREQUIRES_DYNAMIC_APPROVAL、電源断耐性はUNKNOWN |

全項目で `actual_OS_or_transport_proven=false` を固定した。静的ACLやfake Jobを動的PASSへ昇格する入力、terms UNKNOWNを総合ALLOWとする入力、未定義のauthority追加を拒否する。

## Track A：キャッシュ適格性と現在性

A1の取得UTCは `2026-10-23T09:46:47.645062+00:00`、646 bytes、SHA-256は `3f41d473ef69f00cd9eb1cd8f3e2c1f7a053bb21b75bef16a268cd3af242228c`。S審査時点の経過時間は約36.7時間であり、正確なUTC・秒数を [ROBOTS_FRESHNESS_REVIEW.json](../research/nn_v2/phase2_5S/ROBOTS_FRESHNESS_REVIEW.json) に記録した。R時点の約29時間という過去記録はそのまま保持する。

HTTP 200、metadata、status/header bytesの保存を照合した。保存headerにはDateと `Cache-Control: s-maxage=31536000` があり、Expires・Age・Last-Modified・ETagは当該保存headerにない。不存在と未保存を区別し、原本以外から補完しない。

保存済みRFC 9309のSHA-256は `bbaa280636d3e38f0a1a130a5ce40e9753db1ed18c860945b0bf795ff8dc1a87`。§2.4、取得不能に関する§2.3.1.3/§2.3.1.4をbyte範囲・段落hashと取得台帳に結び付けた。キャッシュを許容する規定、通常24時間超の利用を避けるSHOULD NOT、到達不能時の例外、標準cache controlへの参照を分けた。RFC 9111は保存RFC内の参照であり、今回は新規取得や全面的な規範照合をしていない。

| 出力 | 現判断 | 意味 |
|---|---|---|
| NORMATIVE_CACHE_ELIGIBILITY | UNKNOWN | 24時間超でも絶対失効と断定しない。ただし到達不能例外や別の審査根拠は未立証 |
| PROJECT_FRESHNESS_POLICY | UNKNOWN | 既存契約に承認TTLなし。RFCの推奨値やs-maxageを独自TTLとして自動採用しない |
| SOURCE_CURRENTNESS_EVIDENCE | UNKNOWN | 原本がキャッシュ適格でも現在の内容不変は証明しない |
| FETCH_ELIGIBILITY | BLOCKED／HOLD | Sはオフライン限定。今回の結果で取得・permitを許可しない |

経過時間だけで原本そのものを失効・無効としない。保存時点の固定A3/A4 path評価には使用できるが、ライブrobotsと同等ではない。取得不能という観測も今回0であり、例外を仮定しない。4xxのunavailableとnetwork/5xx等のunreachableの規範上の扱いを混同せず、現在の実サイトの応答を推測しない。規範15 PASS／9 UNKNOWNは変更しない。A1再GETは0。

## Track B：read timeoutは総時間ではない

[TIMEOUT_JOB_MATRIX.json](../research/nn_v2/phase2_5S/TIMEOUT_JOB_MATRIX.json) に旧worker・parent・Windows primitiveのsource SHAを記録した。旧workerの10秒は、DNS後の残時間、TCP/TLS、read loopで再計算する期限。同期getaddrinfoが返る前にはworker自身で期限を検査できない。親は12秒の有限待機、cleanupは2秒、旧セッション全体は120秒という別の契約である。

旧OwnedJobはkill-on-closeとactive-process上限4を設定するが、独立したJob wall-clock期限は設定していない。JobのCPU時間制限、親のwall-clock待機、workerの単調時計期限は別である。sourceをimport・実行せず静的に照合しただけで、実Jobの終了・子孫停止をPASSにしていない。

比較した方式は①旧10秒契約維持、②新しい全体deadline定義、③限定取得専用worker。推奨する設計案は③と期限階層の組合せである。**未採用のDRAFT**として、TCP connect 5秒、TLS handshake 5秒、各readの無通信待ち15秒、worker全体60秒、hash/fsync/readbackの共有保存予算10秒、cleanup 5秒、parent 70秒をモデル化した。

readが14秒ずつ成功し続ける場合でも、worker残時間で停止する。保存の3操作に10秒ずつを配らず、共有保存予算と全体予算の双方で制限する。単に5＋15秒を総上限としない。DNS・native呼出しがブロックした場合の実中断は親watchdog/Jobの動的実証が必要であり、仮想STOPで代替しない。将来の単一セッション全体の予算・時刻窓も別承認で固定する。

予約後はtimeout・停止・不明終了でも消費を維持し、自動再送しない。旧運用Job・workerは変更していない。

## Track C：同一ユーザーのパス制限はOSのwrite拒否ではない

[ACL_WRITE_BOUNDARY_MATRIX.json](../research/nn_v2/phase2_5S/ACL_WRITE_BOUNDARY_MATRIX.json) は、staging、raw/attemptの親、予測batch、Championモデル、公式原本、GUI snapshot、タスク領域、他worktreeを区分する。owner/group・実行identity・継承ACE・rootのreparse属性を読取り専用で調査し、読取り失敗はUNKNOWNにした。SID・proxy等の環境情報は私有記録のhashだけを公開する。

同一ユーザーにFullControl ACEがある領域、ownerのDACL変更可能性、effective token/privilegeの未確認部分を残す。ACE一覧をeffective-access完全証明とは扱わない。write/modify/delete権限の動的拒否、privilege escalation防止、path差替え競合は未実証。現在のproduction pathへのwrite probeは0、本番ACL変更も0。

合成パスモデルでは、staging/raw/ledgerの範囲外、`..`、drive-relative、UNC、ADS、別volume、symlink/junction/reparse到達を拒否した。これは入力・パスpolicyであり、同一ユーザーのnative writeやTOCTOUをOSで拒否できる証明ではない。実raw領域は作成していない。

## Track D：一度限りの予約とexactly-once配送を分ける

[attempt_staging.py](../research/nn_v2/phase2_5S/attempt_staging.py) は `syn-*` の新規test stagingだけを使う。immutable revision、排他的なrevision claim、時刻・request hash・targetを束縛したattempt identity、append-only historyを検査する。claimとstateを新規作成し、fsync/readback後、同じdirectory内のpending headを `os.replace` で置き換えて読み戻す。

二つのstore instanceが同じsnapshotを持つ論理競合を作り、stale head／revisionのCASを拒否した。claim/state/pendingの途中中断、partial write、ENOSPC/EACCES故障、replace拒否、JSON/hash/bytes改変、時計逆行、重複ID・request・target、UNKNOWN_OUTCOMEからの再利用を拒否する。orphanや壊れた状態は保持し、自動修復・予算返却をしない。replace後・応答前の中断でも再openすると予約は消費済みである。

立証範囲はテストしたモデルにおけるat-most-once reservationであり、サーバーへのexactly-once配送ではない。`syn-*` という名前自体もOS安全境界ではない。実process起動・競合・crash、directory metadataの電源断耐性、Windows/storage stack全体のatomicityは未実証。hashは署名ではなく、同一ユーザーが再hashできるため、将来は独立に信頼するheadと所有境界が必要である。

## テスト・監査

最終試験は新規80 PASS、R/Q/P/G1/G2等の関連回帰1,611 PASS、合計1,691 PASS。新規negative-controlは68テストで、要求26項目の対応は [NEGATIVE_CONTROL_COVERAGE.json](../research/nn_v2/phase2_5S/NEGATIVE_CONTROL_COVERAGE.json)。全件warnings-as-errors、FAIL/ERROR/skip/deselectは0。

初期2回はローカル変数名 `requests` を静的境界検査がlibrary名と誤認し、各76 PASS／1 FAILだった。明確な `seen_request_hashes` へ改名し、その後のbyte改変拒否・authority schema強化も含めて最終版を再検証した。中間PASSを最終件数へ加えていない。

197 pytestモジュール中、Sと既存関連の15モジュールを実行。server/socket境界を含む3モジュール（constructorを呼ぶ4ソースtest関数、validation caseを含む）を保守的に除外し、他179モジュールもscope外として未収集。未収集のparameter展開件数は推測していない。通信・socket/DNS遮断probe、実モデル、実process競合、Job/ACL動的試験は0。

開始baselineは121,541ファイル・既存34 worktree。開始前の07:00定時更新13件は成功履歴・公式revision・表示generationのhash連鎖で照合し、[PREEXISTING_OPERATIONAL_EVENT.json](../research/nn_v2/phase2_5S/PREEXISTING_OPERATIONAL_EVENT.json) へ分離した。

作業中にはGUI launcher.logに `already_running` 1行の追記を検出してcommitを停止し、変更前142 bytesのhash維持、同一file identity、既存launcherの多重起動拒否経路、既存GUI/server・listener不変を読み取りで照合した。起動要求者は独立には特定していない。既存運用イベントとして [OPERATIONAL_LOG_EVENT.json](../research/nn_v2/phase2_5S/OPERATIONAL_LOG_EVENT.json) に限界付きで分離し、初回の差分検出監査も保持した。修復・baseline書換えは0。

全体では121,540ファイル不変、1ログ追記を照合済み。モデル53 payload、過去raw/permit/evidence、旧Phase、予測、Weekend、GUI code/snapshot、34 worktree、main・他ref、タスク定義・状態は不変。研究HTTP/DNS/socket・Git通信・permit発行は0。最終静的件数・hash・保護監査は [VALIDATION.json](../research/nn_v2/phase2_5S/VALIDATION.json) と [PROTECTION_VERIFICATION.json](../research/nn_v2/phase2_5S/PROTECTION_VERIFICATION.json) を参照する。

terms全6 UNKNOWN、6 permit HOLD、B/C/D・HISTORY/PREDICTION HOLD、Phase A BLOCKED、Phase B NOT_AUTHORIZED、G3/G4未承認を維持する。
