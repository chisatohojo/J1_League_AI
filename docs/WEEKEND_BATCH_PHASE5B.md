# Weekend Batch Phase 5B-1：host上の純粋契約・静的検証

今回の分離後判定は `PHASE5B1_HOST_STATIC_VERIFIED`。検証台帳の保護監査と最終テストを根拠とする。
Phase 5B-2の動的検証は未実施であり、Phase 5B全体の隔離mock合格ではない。
以下の初回停止記録は経緯として保持し、Phase 5B-1の結果で置き換えない。

分離前のゲート：`PHASE5B_BLOCKED`。
停止位置はStep 0／Step 2。OSレベルの通信遮断と本番領域からの書込み隔離を確認できる実行環境が
未確定のため、mock childを起動せず停止した。利用者の追加指示により、hostで安全に行える
静的・純粋関数・契約検証だけを追加実装した。未実行のOS検証をPASSに数えない。
初回の停止文書・台帳はprivate領域へSHA付きで別保存してから、本書を更新した。

基準：[Phase 4](WEEKEND_BATCH_PHASE4.md)の`af776d2c7569d491200ab96509047e7d8ea178fc`、
[Phase 5A](WEEKEND_BATCH_PHASE5A.md)の`dc03d498831033a1cfab29d8597f98c4ee807019`。
専用branch：`feature/weekend-phase5b-mock`。別の新規worktreeを作成し、既存worktreeは再利用していない。
観測・保護監査・SHAの集計は[検証台帳](WEEKEND_BATCH_PHASE5B_VALIDATION.json)へ保存する。

## 1. 停止根拠と環境の観測

今回の指示は「実行環境のネットワーク遮断が確認できない場合、動的検証は中止する」と要求している。
Phase 5A第6節は、使い捨てWindows VM・非特権account、本番volume/profile非共有、VM外側の通信遮断を推奨する。
VMだけが唯一の方式だと解釈してはいないが、別方式でも同じ保護境界とOS上の証拠が必要である。
Python socket mockやaudit hook、Job ObjectだけをOSの通信遮断と認定しない。

| 読取り専用の確認 | 観測結果 | 認定できる範囲 |
| --- | --- | --- |
| 実行token | 非昇格、通常のmedium権限 | 管理者昇格はしていない。mock専用のrestricted token／OS隔離が成立した証拠ではない |
| Windows登録情報 | EditionID=Core、DisplayVersion=25H2、build=26200、UBR=9711 | ProductName文字列はWindows 10 Home。文字列差から製品や機能を推測せず、記録値として保持 |
| Firewall/BFE service | bfe、mpssvcはRunning | serviceの稼働だけでは通信遮断にならない |
| Firewall profile | Domain／Private／Publicが有効。COMの既定送信動作はいずれも1（ALLOW） | Firewallが有効であることを、子processの外部接続拒否と解釈しない。個別全ruleの不在や全通信成功まで主張しない |
| Hyper-V管理 | Get-VM／Start-VMが見つからず、virtualization/v2のqueryは0x8004100e | 当該query経由でVMを確認できない。別hostや別製品のVMが存在しないという証明ではない |
| Sandbox／他管理CLI | WindowsSandbox、VBoxManage、vmrun、vmware、docker、podmanがPATHから見つからない | インストール全領域を調べ尽くしたとは扱わない |
| WSL | commandは存在 | 起動していない。Linux環境の有無・遮断状態も未検証で、Windows Job／ACL検証の代替としない |
| Python／pytest | Python 3.12.14、pytest 9.1.1 | 初回preflightはdist-infoだけを確認。後の明示指示によりpytestで純粋契約を検証。worker／model moduleはimportしていない |

既存hostのFirewall rule、ネットワークadapter、task、account、ACLは変更していない。
AppContainer等も本用途で未構成・未検証であり、暗黙の代替として起動していない。
外部HTTP／DNSを投げて到達性を試すnegative-controlも行っていない。
利用者回答により、実証済み隔離環境は未準備と確認した。OS機能有効化、管理者権限、再起動、
VM作成は別承認とし、hostの純粋検証をworker起動の承認へ読み替えない。

## 2. 実装・起動入口・通信schemaの状態

- mock worker実装：未着手（preflight STOP）。純粋なpacket契約だけを別moduleで実装。
- 起動したmock child／孫process：0。
- 実行時mock entrypoint：なし。運用collector、研究worker、実Championへのfallbackも0。
- endpoint：なし。localhost socket、named pipe、外部socketを作成していない。
- 入出力schema／request ID／batch ID／source revision：純粋関数で検証済み。実process間検証は未実証。

Phase 5AのG0〜G2計画を維持する。再開時には、合成専用namespaceと版、完全一致するrequest/response、
重複・途中切断・schema不一致の拒否、有限deadline、固定mock entrypoint、入力/code/executable SHAを
先に確定する。本番root指定やscope文字列の書換えだけで使える入口を作らない。

追加指示後はprivate監査scriptと、同一process内の純粋契約テストだけを実行した。
これらをmock worker／OS隔離検証として計上しない。
report保存先とsource/worktree等の個人環境の絶対pathはprivate evidenceだけに保持する。

## 3. 所有権・ACL・保存先・receipt

| 項目 | 今回の状態 | 再開後に必要な実証 |
| --- | --- | --- |
| process／Job | mock未起動、Job未作成、他process終了0 | suspended create、専用image/PID/kernel親の一致、Job割当後resume、timeout/cancel/Stop競合、孫process残存、handle解放 |
| ACL／Owner | 既存保護directoryのOwner/DACLを読取り保存。ACL変更0 | 新規sandbox内だけでOwner/DACL、権限拒否、変更・path差替え、reparse/Junction/symlinkのnegative-control |
| 保存先identity | 既存保護fileのdevice/file ID、size、mtime、creation time、SHAを新baselineへ保存 | workerの専用出力をexclusive-createし、書込み前と公開直前にhandle/path identityを照合 |
| mock receipt | 実worker receiptは未生成。純粋simulation用の別形式だけを検証 | 合成scope、request/batch/revision/mock identity、UTC・状態・理由・SHA、flush/readback/commit、重複拒否 |
| 部分保存・異常終了 | 故障注入なし | 保存前後のcrash、receipt欠落/改変、不明runからの再試行拒否を検証 |

ネットワークと書込みのOS境界が不明なまま、通常tokenのmock childで先行試験しない。
単一fileのreplace、batch directory rename、process crashからの検査と、Windowsの電源断永続性は分離する。
本Phaseの電源断耐性は未実証であり、VM／実機の破壊的試験を実施していない。

## 4. Phase 4の互換性と試験実績

Phase 1〜5Aの契約・コードSHAを読取りで照合した。Phase 4の8変更ファイル、旧日別／旧v2 reader、
固定source→共通Elo→10件保存→canonical読戻し→feed投影の実装を変更していない。
実workerを接続した同経路は未検証。後続source更新、feed復旧、二重推論防止についても今回は再実行していない。

| 区分 | 今回の件数／状態 |
| --- | --- |
| 新規純粋関数／契約テスト | 108 PASS、warnings-as-errors。worker／file公開なし |
| 静的回帰 | 6 PASS。Phase 4／5Aの既存コードSHA、列名・scope、非接続を検査 |
| 隔離process／OS動的テスト | 0、preflight STOPで未実行 |
| 既存613件の動的回帰 | 0、再実行していない |
| 通信／ACL／process／receipt negative-control | 0、未実行。サービスqueryやhash一致を代用品にしない |
| Phase 4の613 PASS／1 skip | 既存証跡。今回のPASSへ加算しない |
| Phase 5Aの69静的PASS | 既存証跡。今回再実行した件数へ加算しない |
| 今回の契約SHA照合 | Phase 4／5Aの固定入力とコードに一致。worker動作の証明ではない |

今回、合成予測も生成していない。実モデルload／fit／predict、実HTTP、実予測保存、本番feed更新、実予約は0。

## 5. 保護監査とGit

Phase 5Aの44,370件を固定期待件数とせず、現時点のprotected file集合を再構成して新baselineを保存した。
model seal／53 payload、実保存19予測、公式source、Phase 4・5Aを含む全旧worktree／branch、main、
task XML／実行状態、Desktop、GUI／browserの取得可能なprocess identityと既存directory ACLを監査する。
個人browser profileの履歴・内容を公開資料へ取得せず、既存GUIを表示・操作・終了しない。
監査の範囲外まで無影響が実証されたとは主張しない。差分があれば自動復元や原因の推定をしない。

変更は本書・検証台帳と、新規純粋契約module・そのテスト2件の計5ファイル。
既存Phase 4／5A module、reader、runtime、worker起動入口は変更していない。
分離前は全ゲート未達のため未コミットで保持した。今回の指示はPhase 5B-1の全ゲート合格時に限り、同じ専用branchでのcommit／通常pushを承認している。
main・Phase 4・Phase 5Aへのmergeは0。再開時の専用branchのHEADはPhase 5A基準のままであった。

## 6. 再開条件とPhase 5Cの境界

1. 通信遮断・本番volume/profile非共有を確認できるWindows隔離環境の名前、接続方法、所有範囲を確定する。
2. network adapter／OS policy・共有folder・read-only input・write allowlistの証拠を接続前に保存する。
   現行hostへの昇格やglobal Firewall変更で代用しない。
3. 専用mock entrypointとschema／code SHAを固定し、Step 1〜7を合成データだけで実装・実証する。
4. Phase 5B-2の通信negative-controlを含む全試験と保護監査がPASSして初めて、隔離mock全体の合格を判定する。Phase 5B-1のGit保存とは別ゲートとする。
5. Phase 5Cで実model loadや合成入力での実推論を行う場合も別の明示承認が必要。
   実HTTP、公式収集、実fixtureへの予測、runtime/task配備、feed/UI有効化はさらに別承認とする。

`PHASE5B_BLOCKED`は隔離mockの安全性に合格したという意味ではない。境界未確立の段階で
実行しなかった結果であり、未実装・未検証事項を保持したまま次の環境確認を待つ。

## 7. 追加のWindows読取り調査

| 項目 | 保存した観測 | 判断 |
| --- | --- | --- |
| OS | CIM Caption=`Microsoft Windows 11 Home`、SKU=101、64 bit、version=10.0.26200、EditionID=Core | registryの古いProductNameだけでWindows 10と判断しない |
| Sandbox | `Containers-DisposableClientVM`相当の機能が当該CIM検索に現れず、System32のWindowsSandbox.exeも存在しない | **現状、利用可能なSandboxとは認定できない**。非公式なHome向け有効化scriptは使用しない |
| Hyper-V | 管理command／管理namespaceを確認できない | このhostに利用可能な独立Windows guestがあるとは認定しない |
| 仮想化 | HypervisorPresent=true。一方、ProcessorのVirtualizationFirmwareEnabled／VMMonitorModeExtensions／SLAT表示はfalse | hypervisorが動作する観測とCPU featureの表示を区別する。BIOS無効・CPU非対応と断定せず、設定変更もしない |
| OptionalFeature | VirtualMachinePlatform／HypervisorPlatformのInstallStateはraw値2 | この状態をSandbox利用可能という根拠にしない。機能追加・管理者queryは実行していない |
| 資源 | 論理CPU 24、物理memory約16 GB | 資源量だけでエディション・機能・隔離境界の成立を判定しない |

すべてlocal CIM／registry／file存在確認による観測であり、Windows機能を変更していない。
公式HTTP／外部DNSは0を維持し、外部文書の新規取得も行っていない。

## 8. hostで実装・検証した純粋な契約

`src/modeling/weekend_mock_contract.py`はstdlibだけを使う。file IO、socket、process生成、
wall clock取得、model import、CLI／main、有効化switchを持たない。現在のupdaterからimport・接続していない。

| 契約 | 実装した条件 |
| --- | --- |
| Request | `weekend-mock-request-v1`／SYNTHETIC_ONLY。64 KiB以下のcanonical UTF-8 JSON、exact key、重複key・不完全body・非有限値拒否 |
| identity | request ID／batch ID／source revision／receipt／予約／snapshot SHA。callerが明示固定したexpected source revisionと完全一致 |
| fixture | 既存と同名の7列。ただしmock専用ID・TeamMaster風ID・`synthetic_mock` namespaceだけを受け付け、実公式fixtureへ適用しない |
| snapshot | 共通rating map/SHA、全対象features、source/予約/実時刻を結合。全targetのelo_diffは同じmapのhome-away差分で、175を加えない |
| 時刻 | 仮UTCを明示入力。金曜07:00以前のsource ready、freeze後のrequest、最大30秒のdeadline、全target kickoff前。実時計の真正性を証明しない |
| Response | `weekend-mock-response-v1`。mock identity、request bytes SHA、request/batch/source/snapshotの一致、件数・順序・3確率の有限性／範囲／和を検査 |
| Ledger | immutable tupleでCLAIMED→RESPONSE_VERIFIED→COMMITTEDまたはFAILEDを論理模擬。STOP／CANCEL／TIMEOUT／CRASHは理由を持つFAILEDとなる。terminal後の再実行、同じbatchの別request、重複commitを拒否 |
| Receipt | `weekend-mock-contract-receipt-v1`は**PURE_FUNCTION_SIMULATION専用**。worker_started／batch_published／os_isolation_verified／durability_verified／history_admissionは全てfalse。実OS receiptへ流用しない |
| Sandbox案 | 下記の閉じたXML templateだけを返す。設定追加・network有効化・MappedFolders／LogonCommandの混入を拒否。file保存・起動はしない |

論理COMMITTEDはfile／batchが公開されたことを意味しない。in-memory ledgerに耐crash性はなく、
receipt生成・flush・replace・readback・lock・二重process間競合は未実装である。
現在のPhase 4のsynthetic source parser／bindingへ新しいmock namespaceを直接渡すadapterも未実装。
既存の列名・reader SHAの一致は確認したが、worker経由のPhase 4結合PASSとは呼ばない。

前回実行は93 PASS（87純粋契約＋6静的回帰）。今回の最終実行は**114 PASS／0 failure／0 error／0 skip**（108純粋契約＋6静的回帰）。
plugin自動loadを無効にし、network／process呼出しと実model／collector importを拒否するprivate harnessで実行した。
禁止呼出し試行・禁止module importは0。これは**アプリ内guard**であり、OS通信遮断のnegative-controlではない。
初回には大きなparam IDがWindows環境変数上限を超えたtest harness errorがあり、短いIDへ修正した。
private runnerの初回もrepo検索path不足でcollection errorとなり、承認されたworktreeだけを明示して修正した。
これらの旧ログ／JUnitは保存し、修正後の93 PASSと混ぜて合算しない。

## 9. Sandboxが利用可能な環境を準備する場合の案

このhostでは実行しない。まず対応OS／実際のfeature提供・仮想化設定を確認し、必要なエディション変更、
管理者権限、機能有効化、再起動、VM作成は**具体的な対象を確定してから別承認**とする。
有効化できると確認した環境でのみ、承認後の管理者操作案は次になる（未実行）。

```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All -NoRestart
```

再起動も自動では行わない。機能・実行ファイル・隔離対象を再確認した後、次の設定を新しい専用`.wsb`へ
保存する案とする。現在は文字列templateの生成・検査だけで、`.wsb`fileの作成や起動をしていない。

```xml
<Configuration>
  <Networking>Disable</Networking>
  <ClipboardRedirection>Disable</ClipboardRedirection>
  <VGpu>Disable</VGpu>
</Configuration>
```

- MappedFolders／HostFolderを一切設定せず、hostのrepo・profile・runtime・Desktopを共有しない。
- LogonCommandを設定せず、起動だけでworker／installerを実行しない。
- 承認済みのguest起動後も、network設定・共有無し・guest owner／ACLを確認してからmock試験へ進む。
- **この無共有・無通信設定だけでは、Python／テスト入力の搬入とreceipt／JUnitの搬出方法は成立していない。**
  標準Sandboxに必要なPythonが存在すると仮定しない。clipboard／network／folder共有を勝手に有効化して補わない。
- 認証可能なオフライン搬入・搬出を別途設計できなければ、このSandbox案だけで検証を開始しない。
  専用Windows VMでread-only入力mediaと独立した試験出力diskを使う案も、VM作成・接続・証拠読戻しまで別承認で具体化する。
- 設定XMLの純粋テストを、guestでの有効性・実際の通信遮断・Windows保存耐性の実証と呼ばない。

## 10. 完了範囲と未実施範囲の分離

| 現行hostで完了 | 隔離環境が必要で未実施 |
| --- | --- |
| OS／feature／仮想化状態のlocal読取り | 実mock childとJob／kernel ownership、子孫・handle解放 |
| 厳密な合成request／response・source pin・共通features検査 | DNS／HTTP／localhost／専用IPCとOS拒否のnegative-control |
| 論理状態の重複／再開拒否、simulation receiptの改変拒否 | Owner／DACL変更・path/reparse差替え・権限拒否・書込み遮断 |
| 既存Phase 4／5AのSHA・schema列名の静的回帰 | 実worker receiptのfsync／readback／公開、故障・cancel・Stop競合 |
| 閉じたSandbox XML templateと段階的手順案 | worker経由の10件batch保存・feed再投影、二重起動0の実証 |

上記の純粋検証部分はPhase 5B-1として独立判定する。Phase 5B全体の隔離合格は未成立のままである。
実model／実HTTP／本番操作0、OS機能変更・管理者使用・再起動・VM作成0を維持する。
今回の分離指示に従い、Phase 5B-1の検証・保護監査合格後だけ専用branchへcommit／通常pushする。Phase 5B-2は実行しない。

## 11. Phase 5B-1の再開・検証記録

再開時の未コミット5ファイルを、編集前にprivate領域へコピーし全SHAを照合した。
worktreeの作り直し、reset、既存変更の破棄、cleanup、旧監査・JUnitの上書きはしていない。
基準HEADは`dc03d498831033a1cfab29d8597f98c4ee807019`、branchは`feature/weekend-phase5b-mock`。
新しい保護baselineを採り、前回baselineとの間の差分は研究再開前の事象として別記録する。
07:00／22:00の自動タスクは停止・変更・再実行しない。実行が重なれば独立した時刻・証跡で審査する。

追加21件はStop／cancel／timeout／crashの論理終端、終端後の再開・commit拒否、不明request、偽造failure理由を検証する。
これらは実processの停止、実timeout、Stop競合やcrashからの復旧を証明しない。
108件の純粋契約はID・revision・全対象集合・時刻・SHA・確率形状・重複・異常状態を検査し、6件の静的回帰は
Phase 4／5Aのコード・契約SHA、7列名、純粋moduleのimport／呼出し制限を照合する。
旧613件のE2Eは運用moduleのimportや一時保存を伴うため今回の非実行範囲では再実行していない。
過去613 PASS／1 skip、前回93 PASS、今回114 PASSは別の実績であり、合算しない。

negative-controlは改変packet・schema／identity／revision不一致・再実行・不正状態の拒否である。
application内guardの禁止呼出し試行0と禁止module読込み0を記録する。OS通信遮断やACL拒否のnegative-controlは0件・未実施。
receiptの値は論理simulationだけであり、実worker・本番保存・履歴admissionの証拠には使えない。

変更は新しい純粋契約module、契約テスト、静的テスト、本書、検証JSONの5ファイルに限る。
既存reader、Phase 4結合層、運用updaterは変更しない。最終件数、コードSHA、JUnit SHA、保護監査SHAは検証JSONへ記録する。

再監査中に既存07:00タスクが自動実行された。取得したtask情報、親子processの実行file・引数、
開始・終了UTC、source revision／manifest、更新status、診断JSONを独立したprivate証拠として保存した。
タスクは終了コード1で終了し、診断は`prediction_history_incomplete`。10/25に先行する10/24の5試合が
scheduledのままという記録である。研究が原因とも、正常更新だったとも推測せず、運用障害として保持する。
タスク定義と運用コードは変更せず、停止・再実行・修復もしていない。
タスクが追加したsource／取得証拠と可変statusを、研究による書込みや既存予測の変更に混同しない。
タスク終了後の安定baselineで固定保護対象を再照合する。既存publicationと19予測のSHAは別途照合する。
本書の「実GET・モデル実行0」は今回の研究操作の件数であり、独立した定時処理が実行されなかったという意味ではない。

安定baselineからの最終監査は45,019ファイルのSHA・file identity・size・mtime・creation timeで差分0。
モデル53 payload、既存19予測、既存publication、他worktreeとmain、運用コード・タスク定義を照合した。
監査中の自動タスクについては、可変出力8ファイルの変更と新規40ファイルを別証跡に記録した。
前回baselineから再開までの差分は別集計であり、原因を一律に通常更新や研究へ帰属させない。
5つの既存directoryのOwner／DACLは不変。GUI観測22 process中21 identityは一致したが、
同じ既存Chrome親のrendererが1件入れ替わった。原因は未特定のまま保持する。
純粋moduleはGUI・process操作を持たず、研究によるGUI操作は0。browser profile内容や全processの不変は認定しない。
これは固定保護ファイルの不一致ではなく、制御対象外の実行時観測であり、OS隔離の実証には使用しない。

## 12. Windows 11 Home上の隔離VM候補と次工程の手順案

現hostには検証済みguestがない。以下は**選定候補と構築計画**であり、現在のbuildでの利用可能性を認定したものではない。
通信禁止のためvendorサイト・配布物へアクセスしていない。対応版、利用条件、署名、必要driverと既存hypervisorとの併用条件は
導入候補を確定した後、提供された公式資料または別途承認した調査で確認する。

| 候補 | 必要条件・選定時の確認 | 現在の扱い |
| --- | --- | --- |
| Oracle VirtualBoxのWindows host向け版 | Windows 11 Home／現build／CPU／稼働hypervisorの対応、署名済みinstaller、Windows guestライセンス、十分なdisk／RAM | 未導入・互換性未確認。Homeでの候補として比較するが実行可能とは断定しない |
| VMware WorkstationのWindows host向け版 | 同じOS／CPU／hypervisor確認、現行の配布・利用条件、仮想NICの完全無効化、共有機能の無効化 | 未導入・互換性未確認。VirtualBoxと同様に別承認で選定する |
| 別の専用Windows VM host | 管理者の所有範囲、非共有volume、到達経路、guest OSと隔離policyの証跡 | 現hostを変更しない代案。接続・資材搬入も別承認 |
| Windows Sandbox | 対応エディション／feature提供が確認できる別環境 | 現Home hostの入口には採用しない。第9節は条件付き案のまま |

次工程では以下を一つずつ承認・実証する。今回はどれも実行していない。

1. 製品／版／installer SHA／署名／ライセンス、guest OS、資源配分、保存disk、入力・出力経路を確定する。
   必要な管理者操作、機能変更、driver、再起動、VM作成を具体化して別承認を得る。HypervisorPresentだけを対応証明にしない。
2. 本番volumeや個人profileを接続しない使い捨てguestを作る。NAT・bridge・host-onlyを含め仮想NICを接続せず、
   host folder共有、clipboard、drag/drop、USB自動接続、drive redirectを無効にする。hostのFirewallは変更しない。
3. 合成code／固定Python／依存物を検証したread-only ISOで搬入し、出力は専用の仮想diskへ限定する。
   本番model・source・予測を媒体へコピーしない。入力SHA、guest非特権SID、Owner／DACL、専用rootを固定する。
4. guest起動後、外側設定とguest NIC／route／共有一覧を照合する。合成の通信negative-controlで拒否を確認する。
   公式サイトへはアクセスしない。遮断の根拠が不明ならmock childを起動しない。
5. mock専用entrypoint／実行file SHA、Job所有権、子孫停止、ACL／path差替え、receipt永続化、Stop競合をguest内で検証する。
   Phase 4経路との結合・再表示時のworker起動0もこの段階で実証する。不明runは再実行しない。
6. guest停止後に専用出力diskだけをread-onlyで回収し、全SHAと外側receiptを照合する。
   回収時のhost parser・mount権限・untrusted出力の扱いも承認対象とし、共有folderを後から有効にして代用しない。
7. 失敗証跡とpartial receiptは保持する。VMの破棄・disk削除は今回のcleanupとして行わず、保存確認後の別承認とする。

この方式でもhypervisor自体の安全性、OS電源断・物理storage耐性まで保証しない。
入力搬入と出力読戻しを設計できない無共有Sandbox案では、動的試験を開始しない。
Phase 5B-2の未実証項目は通信遮断、実mock起動、Job／子孫／handle、Owner／DACL／path競合、
実receiptのflush／replace／readback、crash／timeout／Stop競合、領域外書込み拒否、worker経由E2Eである。
その合格にも、実Champion・実HTTP・本番移行の承認は含まれない。
