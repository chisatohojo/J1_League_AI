# Weekend Batch Phase 5：Windows production staging candidate

判定：**`WEEKEND_PRODUCTION_STAGING_READY`**。本番は無効。
追加承認された専用テストprocessによる競合・Job管理・異常終了の主要ゲートが合格した。
実source worker、実モデル、公式通信、本番予測・feed・予約・taskは実行していない。
電源断・あらゆるTOCTOU・特権攻撃者への完全防御は未実証のままであり、READYの達成事項に含めない。
集計とSHAは[検証台帳](WEEKEND_BATCH_PHASE5_STAGING_VALIDATION.json)を参照する。

基準は[Phase 4](WEEKEND_BATCH_PHASE4.md)の`af776d2c7569d491200ab96509047e7d8ea178fc`。
独立branchは`feature/weekend-production-staging`。Phase 1〜4の実装・updater・readerは変更していない。
中断時の未コミット4ファイル846行と旧ログを、再開前にSHA付きで別保存した。4件目は新規テストファイルだった。
既存613 PASS／1 skip、作業途中46 PASS、今回の最終実行はそれぞれ別証跡であり合算しない。

## 実装とPhase 4の再利用

| ファイル | 実装した責務 |
| --- | --- |
| `weekend_production_staging.py` | 22:00 sourceの明示選択、mock HTTPの有限契約とHOLD記録、固定Champion bundleの静的検査、mock transform/predict adapter、Phase 4 backendの派生 |
| `weekend_staging_windows.py` | 新規temp NTFS arena、Owner/DACL、reparse拒否、directory handle、同時writer lock、fsync/readback、create-newとdirectory rename、共有する標準ライブラリ専用の封印・receipt I/O |
| `weekend_staging_publication.py` | 既存Phase 4 saved batchを検証して封印するstaging envelope、公開後receipt/seal、保存値reader、不明runの読取り専用調査 |
| `test_weekend_production_staging.py` | mock契約、Windows実I/O、失敗保存、旧readerへの誤混入拒否。既存fixtureとE2Eを再利用 |

`StagingReceiptBackend`は既存`ReceiptBoundBackend`を継承する。sourceは既存`Workspace`／`Reference`／`Provider`で検証し、
共通Elo・予測前／保存前checkpoint・時刻検査・既存manifestをそのまま使う。Phase 4アルゴリズムを複製しない。
mock adapterは`elo_diff`のfloat `(N,1)`が固定snapshotの全targetと一致すること、transform後のshape/有限性、
class順 `(0,1,2)`、witness SHAを検査する。確率のshape・範囲・和は既存Champion入力関数で検証する。
fit APIや実model loaderを呼ぶ経路は追加していない。

`inspect_champion_bundle`は既存`FILE_PINS`を再利用し、5 payloadのSHA、feature/class/metadata/model/scaler/trainingリンクを読むだけ。
実model/scalerのdeserializeや推論は行わない。staging envelopeの`model_contract_pins`は期待する固定契約であり、
その実modelで出力を生成したという証拠ではない。mock実行witnessは別fieldで保持する。

## Source worker候補

`select_previous_night`は一つの明示Referenceだけを受け、既存verifierでmanifest・raw・metadata・request UTC・receipt・seal・Reference・
fixture／結果／全履歴を照合する。前夜22:00〜24:00の観測を候補として要求し、不適格ならHOLD。
latestや他revisionへ自動fallbackしない。00:00以降の結果が必要なら、この夜間候補を成功扱いにしない。

独立06:45実取得の入口は常に拒否する。今回実装した`MockHTTP`はliteral responseだけで、socket／DNS／URL openerを持たない。
固定URL集合、各URL一度、最大12件、timeout最大10秒、retry 0、間隔5秒以上、本文2 MiB／件・24 MiB合計、有限global deadlineを要求する。
07:00:00より後の取得完了、403／429／TLS／redirect／body不整合で停止。requestは応答前に記録し、失敗もHOLD receiptへ保存する。
mockの時刻とTLS表示は仮想証拠であり、実取得・実TLS検証とは呼ばない。

取得済み原本からのpublicationとProviderは既存Phase 3を利用する。mock収集の成功だけでpublication完了にはしない。
実publicationのscope・実worker所有権・通信監督・公開receiptの本番producerは、承認済み本番契約へ接続する別工程が必要。
`PRODUCTION_CONTRACT`は必要fieldを列挙する未受理の設計版であり、稼働readerが受け付ける形式ではない。
`production_entrypoint`は常に拒否し、設定値やroot指定で有効にするswitchはない。

## Windows実I/Oの契約と限界

arenaはsystem temp直下にexclusive-createし、NTFSを要求する。新規rootだけに現Owner SIDとSYSTEMのDACLを設定する。
既存directoryへattachするAPIはなく、既存の本番ACLは変更しない。rootをhandleで保持してから新規DACLを設定する。
parent／saved fileのidentity・Owner/DACLを記録して再照合し、path traversal・ADS・予約device名・junction/reparseを拒否する。
書込み中は親directoryを保持する。保持handleは`GENERIC_READ | READ_CONTROL`、share read/write、share deleteなし。

初期negative-controlではREAD_CONTROLだけのhandleでrenameが通った。実際の失敗を保持し、GENERIC_READを加えた修正版で拒否を確認する。
親の保持中と保持終了後を混同した途中テスト失敗も残した。テストrunnerのtemp/capture/log配置失敗もアプリ実績から分離する。

lockは`CREATE_NEW`、read/write/delete access、share 0で取得し、request／nonce／実UTCをflushする。
成功時はまだexclusiveな同じkernel handleでfile identityとtokenを確認し、`FileDispositionInfo`で所有lockだけをclose時削除する。
close後のpath確認→unlinkという競合窓は使わない。途中失敗はhandleだけを閉じ、lock・attempt・pendingを残す。
scope marker、root/parent identity、Owner/DACLの変更や不明runはHOLD。ロック強制回収・自動再開はしない。

実証対象は、このhostのNTFS・専用新規領域でのAPI動作である。Python audit guardはnetwork/process/model importと
通常file書込みを制限するが、OS sandboxではなく、ctypes全呼出しを監視するものでもない。
native APIの書込み先はArenaの確認済み新規pathへ限定し、既存保護fileは前後SHA/identityで照合する。
全side effect・悪意ある管理者・任意の同一user攻撃・全TOCTOU窓の不存在を保証しない。

## Publication／reader

staging形式は`weekend-production-staging-envelope-v1`、scopeは`STAGING_MOCK_ONLY`、`production_admission=false`。
内側は未変更の`champion-weekend-v2-source-v1`／`SYNTHETIC_ONLY` batchで、旧形式への偽装をしない。
Phase 4の完全なsaved batchを再検証し、専用pending内へ全payloadをfsync/readbackしてから、同一NTFSでdirectory renameする。
コピー元のPhase 4 mock batchは保持する。Windows envelope公開前の失敗で、コピー元まで消して公開0件と偽らない。

rename後に内側全体を再読込みし、その完了の**実UTC**をreceiptへ保存し、receipt／sealもcreate-new・flush・readbackする。
これは合成source/予測cutoffの仮UTCとは別であり、過去の公開時刻へ遡及させない。
rename済みでもreceipt/sealが未完成なら、物理directoryは存在するがstaging readerはHOLDする。
atomic directory visibilityと、公開後receiptまでのtransaction永続性は別である。

同じ完了requestの再表示はsaved readerだけを使い、updater/modelを再呼出ししない。残存lockがあれば、sealがあっても自動再開しない。
feed失敗時はPhase 4の保存batchとlast-good表示を保持する。旧日別・旧v2・source-v1 readerはそのまま維持し、
staging envelopeをoperational saved readerへ置いた場合は拒否させる。今回は本番feed生成・reader配備をしない。

## 最終検証と未実証事項の区分

正確な最終件数・negative-control・JUnit SHAはJSONに記録する。実証はmockと専用実I/Oに限定する。

追加検証前の証跡は **332 PASS / 0 FAIL / 0 ERROR / 0 skip**（warnings-as-errors）。
内訳は今回のstaging試験59件と、既存結合37件・source 63件・batch 61件・preflight 20件・
日別updater 92件の関連回帰273件。Phase 4既存の613 PASS／1 skipへ加算しない。
途中のnegative-control失敗、テスト補助コードの失敗、runner初期化・temp配置の失敗は保存しており、
最終PASSへ読み替えない。そのrunnerの禁止操作検出記録は0件だが、OSレベル通信遮断の証明ではない。

開始時baselineと最終監査を照合し、45,618保護ファイルのSHA・identity/metadata差分は0。
モデルsealの53 payload、既存19予測を含む保護集合、タスク定義・照会状態、main・他worktreeは不変。
Champion固定bundleの5 payloadもSHAと保存済みmetadataリンクだけを検証し、load・fit・推論は0。
開始前からのserver群は停止せず、最終照会で関連テストprocessの残存は観測されなかった。
システム全handleの不存在は未実証であり、失敗lock・attempt・旧ログを削除していない。

| 項目 | 今回の証拠範囲／残る条件 |
| --- | --- |
| NTFS/create-new/rename/fsync/readback | 新規arenaで実API検証。電源断永続性はNOT_PROVEN |
| Owner/DACL | 実SID読取り、新規DACL、DACL改変検出・OS write拒否。管理者によるowner奪取や本番ACL変更は未実施 |
| reparse/parent置換 | 新規test junctionの拒否、保持中rename拒否、保持前の通常directory差替え検出。全競合順序の網羅保証ではない |
| writer排他 | 2個の独立processで同一lockへの競合を実証。競合側拒否・正常終了後の別request取得・異なるrequestでも重複fixture拒否を確認 |
| process/Job | 生成時刻・exe SHA・kernel command line・markerを記録。停止状態で作成し、明示Job所属確認後だけ再開。割当失敗注入時は未再開のまま停止 |
| 正常終了／途中終了 | Job強制終了を5か所で実証。lock/attempt/pending・公開済みbytes保持、無断再実行拒否、Job内process 0・handle解放を確認。親OS停止は未実証 |
| source/model候補 | mock HTTP・mock estimator・固定bundle SHA/metadata。実worker・実モデル・実通信は未実証かつ禁止 |
| 実本番source receipt | 本番producer・本番scope readerへ未接続。07:00以前の実publication成功を主張しない |

## 追加の別process検証

最終コードで **345 PASS / 0 FAIL / 0 ERROR / 0 skip**、warnings-as-errors。
今回追加した実process試験13件と、前回332件の全件再実行（staging 59件＋関連回帰273件）を含む。
既存Phase 4の613 PASS／1 skipは過去証跡であり、この件数へ加算しない。

テスト専用[helper](../tests/weekend_staging_process_helper.py)と
[試験](../tests/test_weekend_staging_processes.py)を追加した。
helperは停止状態の固定Python executableを作成し、生成時刻・実行ファイルSHA・実kernel command line・
request/owner markerを照合してから新しい専用Jobへ割り当て、所属を確認して再開する。
任意のentrypoint・PID指定の終了・既存workerへのfallbackはない。
JobはKILL_ON_JOB_CLOSEとactive process数上限を設定する。停止対象は、保持kernel handleでidentityを確認した今回の子だけ。
終了したprocessのimage照会がWindowsで失敗した初期試験を保持し、終了後は保持handleとGetProcessTimesの生成時刻で照合する。

取得済み合成batchの意味検証には従来のPhase 4 readerを親側で使う。
封印・rename・receipt/readback処理だけを`weekend_staging_windows.py`の共通関数へ抽出し、
親Publisherと子の両方から同じ実装を呼ぶ。子は標準ライブラリだけで、親が完全検証した合成packetの
全payload SHAを検証する。子のbyte検証をPhase 4の意味検証の代わりとは扱わず、完了後も親readerで再検証する。
Phase 4 E2E・旧日別/v2/source-v1 readerは改変していない。

初期の広いupdater importは子の通信/process禁止guardで停止した。初期結果はHOLDとして保持し、
第三者ライブラリのimportを子から除去した。またCREATE_NO_WINDOWでもconhostがJob内に生成されることを、
別の所有限定probeで実行ファイルidentityから確認した。最終版はDETACHED_PROCESSを使い、
Job memberが明示的に生成した子だけであることを確認してから強制停止する。初期不明PIDを遡及してPASSにはしない。

| 実証項目 | 結果 |
| --- | --- |
| 2 writer＋別process reader | 競合writer拒否、公開前・receipt未完成はHOLD、完全確定後だけ全10件。二重公開0件 |
| 正常終了後の後続操作 | 所有lockの正常解放後、別requestが取得成功。既存fixtureの別request保存は拒否 |
| 別processによるrename/delete/file replace | 保持handle中は拒否、解放後は成功。既存directoryのreplaceはOS自体が拒否するため、lock証明とは区別 |
| Job強制終了 | payload途中／rename前／rename直後／receipt前／seal後の5か所で実停止。公開前・未確定はreader受理0件、確定済みbatchは不変 |
| 再試行・手動調査 | stale lockとattemptを保持し再取得・再推論拒否。root/marker・request・保持process handle・生成時刻・終了・lock SHAの所有照合後だけ読取り専用調査 |
| Jobとhandle | 最終runの13 Job、23子（22再開、1割当拒否注入で未再開）。全Job active 0、process/Job handle解放、親handle数の前後一致 |

receipt中の`process_crash_verified=false`は既存形式を維持する。このフラグを過去batchへ書き戻さず、
今回の実process実証を独立した試験証拠としてJSONへ記録する。
lockのshare 0中にpathから読もうとした試験も拒否された。保持中は子の所有token SHAを記録し、
停止後にpathの原本SHAと比較する。読み出しのために共有モードを緩和しない。

Python audit guardはOS sandboxではない。native APIは新規arenaと所有processに限定する。
本試験は明示的なJob終了・process異常終了であり、親process突然死・OS停止・電源断、全競合順序、
特権によるowner奪取・ネットワーク隔離の普遍的保証は別ゲートに残す。
実worker/source receipt producer、実モデルとread-only capability、本番scope readerの接続も別承認とする。

## 配備・停止・手動rollback計画（全て未実施）

1. source worker、実model、保存writer、readerの採用SHAとscopeを別承認する。モデル/sourceは固定revisionのread-only参照。
   現22:00 publicationを優先するが、全原本・UTC・receipt・履歴が不適格ならHOLD。06:45取得へ自動切替しない。
2. 運用readerを先に更新する計画とbackupをレビューする。既存日別／旧v2／source-v1を読めることを合成検証し、
   新scopeを誤受理しないことを確かめる。reader配備自体は別承認。既存batchの全SHA／CRC／読戻しを取る。
3. 初回対象は将来の全件未保存週末を、その時点の公式日程と全batchから確認する。水曜07:00 JSTより前の予約を個別承認。
   2026-10-23〜26の部分既保存週末には適用しない。予約遅延、部分保存、fixture変更ではHOLD。
4. 本番のsource取得・実model非公開検証・予測保存・feed/UI反映はそれぞれ別承認。
   07:00/22:00既存taskは今回変更しない。22:00は保存値の審査/表示だけで、予測生成を追加しない。
5. 停止は新しい起動要求の拒否から行う。現在のstagingには常に拒否する本番入口しかない。
   稼働task・他serverを止めない。将来のworker停止は所有Job/identityを確認する承認済み手順だけを使う。
6. 失敗時はlockを削除せず、run/request/入力SHA、全pending、公開directory、receipt/sealを読取り専用で照合する。
   公開後不明なら存在しないと断定しない。batchの再生成、lock強制解除、staging一括cleanupをしない。
7. rollbackは新writerへの入口停止、互換readerとlast-good表示の維持を別操作として承認する。
   完成済みbatch/予約/原本/receiptを削除・分割・旧format化しない。表示復旧はsaved reader再投影だけとし、推論0。

追加承認されたstaging主要ゲートが合格したため、この独立branchへのcommit・通常pushだけを行う。初期失敗・未確定runの証拠は保持する。
main、UI、NN研究、運用worktree、Desktop、既存19予測、モデル、source/publication、既存taskを変更していないことを監査する。
本番有効化、実GET、実model load/fit/推論、本番予測/feed保存、実予約、task変更/実行は0。
