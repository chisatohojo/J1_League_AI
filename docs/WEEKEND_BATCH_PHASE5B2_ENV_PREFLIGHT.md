> 現在の設計判定：`PHASE5B2_ENV_STRATEGY_READY`。実行環境の成立は引き続き`PHASE5B2_ENV_PARTIAL`。
> 1〜10節は前回までの調査・承認条件の履歴。今回の判断とGit保存条件は11節を正本とする。動的検証は0。

# Weekend Batch Phase 5B-2：Windows隔離環境preflight

判定：`PHASE5B2_ENV_PARTIAL`。調査日：2026-10-23 JST。
実施したのは読取り専用の環境調査、公式資料の参照、方式比較、構築計画の作成だけである。
**VMware Workstation Proを条件付き第一候補に選ぶが、構築・起動可能とはまだ認定しない。**
空きRAM、現行版の正確な隔離設定、WHP利用可否、guestライセンス／offline準備経路の確認が残る。
VM構築、OS変更、昇格、再起動、mock child、接続試験、実モデルはすべて未実施。

基準は[Phase 5A](WEEKEND_BATCH_PHASE5A.md)と[Phase 5B-1](WEEKEND_BATCH_PHASE5B.md)。
Phase 5B-1のcommitは`2badf8f3f46c7e1a9c18d256ba8207f0dc3dfc2a`。
開始時のlocal／origin／実remoteが一致し、旧worktreeはcleanだった。
新規branchは`feature/weekend-phase5b2-env-preflight`。旧成果物・実装は変更していない。
機械可読の観測、確認方法、SHA、未確認事項は[調査台帳](WEEKEND_BATCH_PHASE5B2_ENV_PREFLIGHT.json)に記録する。

## 1. 調査方法と実行境界

利用したのは`Get-CimInstance`、`Get-ItemProperty`、`Test-Path`、`Get-Item`のfile version、
`Get-Command`による存在確認、`Get-Service`、限定directory列挙、SHA、Git／task queryである。
MSI修復を誘発し得る`Win32_Product`は使わない。VBoxManage／vmrun／wsl.exeは起動しない。
VM登録情報は既定位置の存在と件数だけを対象にし、全diskのVM探索や設定変更はしていない。
個人browser Profile／UDFは調査対象にしない。既知の異常は前工程の封印済み証跡だけで評価した。

最初のprivate PowerShell fileの実行は既存execution policyに拒否された。
policy変更・Bypass・昇格を使わず、許可された対話型の読取りcmdletを個別に実行した。
file版を実行済みとせず、実際に得た観測を別JSONへ保存している。
`Get-WindowsOptionalFeature -Online`等の管理者確認、BCD／UEFI設定の直接確認は実施せずUNKNOWNとした。

公式資料のWeb参照は今回の調査範囲であり、外部到達性の接続試験ではない。
installer、ISO、VM applianceはdownloadしていない。JリーグHTTP、collector、worker、modelの実行は0。
Web toolが返す資料抽出結果をprivate保存したが、署名付きraw HTTP snapshotやVM実証とは扱わない。

## 2. OS・CPU・RAM・ストレージ

以下は一時点の観測であり、将来の空き容量や性能の保証ではない。GiBは2^30 bytes。

| 項目 | 観測 | 判断 |
| --- | --- | --- |
| OS | CIMはWindows 11 Home x64、25H2、10.0.26200、UBR 9711、SKU 101 | registryのProductNameはWindows 10 Homeだが、現在のOS名にはCIMを採用する |
| CPU | Intel Core i9-12900K、16 core／24 logical processor、Architecture=9 | x64。CPU型式とIntelの仕様を照合 |
| RAM | DIMM合計16.00 GiB、OS可視15.65 GiB、空き4.879 GiB | 推奨guest 6 GiBを直ちに割り当てない。後述の9 GiB空きgateを満たさない |
| C: | NTFS、全476.29 GiB／空き33.40 GiB | VM配置には採用しない。通常OS処理用の余裕を保護 |
| D: | NTFS、全930.77 GiB／空き793.24 GiB | 新規VM領域の容量候補。物理disk独立性・性能・所有者は別確認 |
| E: | NTFS、全1863.02 GiB／空き632.20 GiB | 証跡backupの容量候補。D:と別物理diskかはUNKNOWN |
| firmware | AMI、BIOS version 8.03 | 設定画面は開かず、更新・再起動なし。VT設定そのものはUNKNOWN |

Intelの当該型式の仕様にはVT-xとEPTの対応が記載される。これはCPUの能力の確認であり、
現在のfirmware設定や特定hypervisorの起動成功ではない。
[Intel i9-12900K仕様](https://www.intel.co.jp/content/www/jp/ja/products/sku/134599/intel-core-i912900k-processor-30m-cache-up-to-5-20-ghz/specifications.html)

## 3. 仮想化・Windows機能

| 確認方法 | 観測 | 解釈と限界 |
| --- | --- | --- |
| Win32_ComputerSystem | HypervisorPresent=true | Windowsからhypervisorが見える。user用VMやHyper-V Managerがあるとは限らない |
| Win32_Processor | VirtualizationFirmwareEnabled／VMMonitorModeExtensions／SLATはfalse | CPU仕様と区別してraw値を保持。稼働hypervisor下の公開値だけで「BIOS無効」「CPU非対応」と断定しない |
| Win32_DeviceGuard | VBS status=2、SecurityServicesConfigured=[2]、Running=[2,7] | VBS、メモリ整合性、Hypervisor-Enforced Paging Translationの稼働を示す |
| HVCI registry | Enabled=1 | 上の実行時観測と整合。値の書換えなし |
| Win32_OptionalFeature | VirtualMachinePlatform、HypervisorPlatform、Microsoft-Windows-Subsystem-LinuxはいずれもInstallState=2 | CIM上はDisabled。完全な管理者CBS確認やpending状態の確認ではない |
| Sandbox | 機能entry／実行fileを確認できず | Homeは公式の対応edition外。非公式な有効化方法を採らない |
| WinHvPlatform.dll | file存在、version 10.0.26100.9711 | DLLはloadせず、WHP capability／partition APIも呼ばない。利用可否はUNKNOWN |
| service | HvHostはRunning | Microsoft hypervisorを使うVBSの観測と整合するが、VM作成能力を保証しない |
| WSL | wsl.exeは存在、現userのLxss登録keyなし、WSL featureはDisabled | WSL2が利用可能とは認定しない。他user／非標準位置の不存在も証明しない |
| Hyper-V管理 | Get-VMなし、root/virtualization/v2 queryは0x8004100e | 当該管理経路は利用不可／未確認。HypervisorPresentとの矛盾として修復しない |

VBSはWindows hypervisorを利用する。今回の値はその構成と整合するが、BIOS設定の全項目を取得したわけではない。
Intelも、別softwareが仮想化を使用中の場合、確認toolの表示だけでは対応有無を断定できないと説明している。
[Microsoft VBS／メモリ整合性の値](https://learn.microsoft.com/en-us/windows/security/hardware-security/enable-virtualization-based-protection-of-code-integrity)、
[CIM featureの列挙値](https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-optionalfeature)、
[Intel確認上の注意](https://www.intel.com/content/www/us/en/support/articles/000005486/processors.html)

HomeでのSandbox非対応は[Microsoft公式説明](https://learn.microsoft.com/en-us/windows/security/application-security/application-isolation/windows-sandbox/)による。
Client Hyper-VはPro以上という[Windows 11要件](https://learn.microsoft.com/en-us/windows/whats-new/windows-11-requirements)とも区別する。
VBS／HVCIは運用hostの保護として維持し、性能向上のための無効化やBCD変更を計画の前提にしない。

## 4. 既存ソフトウェア・VMの存在確認

HKLM 64／32 bitとHKCUのuninstall登録、既知のProgram Files位置、PATH、対象service／driver／processを確認した。
VirtualBox、VMware Workstation、QEMUの導入を示すものは見つからず、versionはUNKNOWN。
CLI不在だけから未導入と断定したわけではないが、portable版・非標準位置・他userを含む全体の不存在は証明しない。
VirtualBoxの既定登録fileとVMware inventory、二つの既定VM directoryも存在しなかった。
Hyper-VのVM列挙は失敗したため、利用可能な既存VMは**確認できていない**。起動して試してはいない。

## 5. 方式比較

| 比較項目 | A：VirtualBox | B：VMware Workstation Pro | C：QEMU／TCGまたはWHPX | D：host制限process |
| --- | --- | --- | --- | --- |
| Home互換性 | OracleはWindows 11 x64 hostを列挙。Home・当該build個別の実証なし | BroadcomはWindows 11 hostを列挙。Home／26200.9711個別の実証なし | QEMUはWindowsのTCG／WHPXを列挙。Windows guestの具体構成は未検証 | OS自体で可能でも、本番領域非共有の境界が未成立 |
| 現CPU／VBS | CPU能力はあるが、OracleにHyper-V競合の注意あり | VBS hostでWHPを使う説明があり、host保護を残す第一候補 | TCGはsoftware emulationで遅延が懸念。WHPXはAPI利用可否が未確認 | guest OSを持たず、既存hostのuser環境を共有する |
| 導入・ライセンス | base GPLv3。Extension Packは別条件で今回は不要 | 対象版は個人・教育・商用無償、portal登録と条件確認が必要。guest Windowsは別 | open sourceだが採用build／依存／配布元の審査が必要。guest Windowsは別 | 実行token／policy実装が別途必要 |
| RAM・disk | guest OSの要求に加えhost余裕。今回の提案は6 GiB／160 GiB枠 | 同左。今の空きRAMは不足 | Windows guest資源に加えTCGのCPU／deadline影響 | 少ないが資源量を隔離の代替にしない |
| OS network遮断 | 全NIC無効＋共有・デバイス経路の点検、実negative-controlが必要 | 同左。NAT／bridge／host-only／remote accessを禁止 | 明示NICなし。QEMUの既定user networkに注意。socket／chardev等も審査 | OSによるdeny policyが未構築。Python mockでは不足 |
| host folder | share／Guest Additions機能を使わない | shared folders／guest操作経路を使わない | virtiofs／9p／SMB／raw host diskを渡さない | hostのmodel・runtime・profileが見える危険が残る |
| clipboard／D&D | 双方向とも禁止 | 双方向とも禁止 | agent／SPICE／display clipboardを禁止 | 個人sessionとの混在を排除できていない |
| USB等 | USB／webcam／remote display／passthroughを禁止 | USB／Bluetooth／printer／camera／audio／VMCI等を検査し不要経路を閉じる | emulated devices／USB／chardev／monitor／VNCもallowlist化 | host devicesへの権限を別途denyする必要 |
| Windows ACL／Job | guest内で検証可能という設計。未実施 | 同左 | 同左。Windows guestが必要 | host上の試験になり、本番保護条件と衝突し得る |
| snapshot／復元 | 支援あり。snapshotはbackupや電源断証明ではない | 対応版のsnapshot／clone手順を確認後に採用 | disk overlay／snapshot構成の追加設計が必要 | process終了で状態が元に戻るとは限らない |
| host影響 | driver・service・network component追加とhypervisor競合 | driver・service・network component追加とVBS時性能の確認が必要 | package・backendによる影響と負荷 | 本番hostのpolicy／ACL変更を要する可能性が高い |
| 再現性 | code／OS／VM設定／入力SHAを固定 | 同左、WHP modeもreceiptへ記録 | machine／device model／backendも固定 | host運用状態に依存し、今回は採用しない |

Cの別案として専用の別Windows VM hostも成立候補だが、所有者、資源、接続、搬入条件が未提示であり自動切替しない。
WSL2／Linux containerはWindows kernelのJob／ACL検証を代替しない。Home上の非公式Hyper-V有効化も採用しない。

Oracleの[host対応](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/installation.html)と
[Hyper-V競合の注意](https://docs.oracle.com/en/virtualization/virtualbox/7.2/user/Troubleshooting.html)を比較し、
host VBSを無効化する回避策は採らない。Broadcomの[host一覧](https://knowledge.broadcom.com/external/article/315653)、
[VBS時のWHP経路](https://knowledge.broadcom.com/external/article?legacyId=76918)、
[無償版の条件](https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hyper.html)を選定根拠とする。
この選定は推論であり、本PCでの起動試験による優劣評価ではない。
QEMUの[backend一覧](https://www.qemu.org/docs/master/system/introduction.html)と
[明示network設定](https://www.qemu.org/docs/master/system/invocation.html)は代案の検討に用いた。

## 6. 条件付き推奨構成

| 設計項目 | 計画値・制約 |
| --- | --- |
| 製品 | VMware Workstation Pro 26H1系列。候補patchは26H1u1。公式installerの正確な版・SHA・署名・条件を採用前に固定 |
| host mode | 現VBS／HVCIを保持するWHP経路を候補とする。実利用可否はUNKNOWN。失敗時にVBSを自動解除しない |
| guest OS | Windows 11 Pro x64、25H2を第一候補。hostに近いbuild／patchを固定し、guest用の正当なライセンス・媒体を別確認 |
| firmware | guest UEFI、Secure Boot、vTPM 2.0。鍵／暗号化／snapshot復元方法も版に応じて確認 |
| CPU／RAM | 2 vCPU、6 GiB固定。nested virtualizationは不要。host空き9 GiB以上を起動前に再確認する計画gate |
| disk | 新しいdata volume領域にsystem 100 GiB＋output 8 GiB、ISO／snapshot／backupを含め160 GiB以上の空きを予約する計画 |
| network | test guestの全NICを削除または無効として固定し、接続先なし。NAT／bridge／host-only／USB NIC／RDP／remote console networkを禁止 |
| integrations | shared folders、clipboard、D&D、guest control／Tools file transfer、USB／Bluetooth／printer／camera／audio／physical disk passthroughを禁止 |
| guest tools | 不要なTools／agentsを入れない。必要driverを分離できるかを確認。VMCI／vsock等の残存経路は版別に確認できなければSTOP |
| accounts | guestの専用非特権userでmockを実行。guest内adminは環境準備だけに分け、host管理権限をworkerに渡さない |
| IO | 検証済みread-only ISOから合成code・Python・wheel・fixtureを搬入。出力は専用guest volumeのみ。host repo／runtime／profileを共有しない |

RAM／diskの計画値と9 GiB gateは本工程の安全余裕案であり、vendor最小要件や実測性能ではない。
Windows 11の最小RAM 4 GB・disk 64 GB・2仮想CPU等は[Microsoft要件](https://learn.microsoft.com/en-us/windows/whats-new/windows-11-requirements)を参照した。
16 GiB機で現在の空き4.879 GiBのまま起動しない。プロセスを勝手に終了して資源を空けず、利用者が実行時間帯や別機を選ぶ。

hostのHomeライセンスだけでguest使用権があると仮定しない。Pro媒体のOOBE／activationをofflineで準備できるかも未確認。
Enterprise評価版は[公式の対象者・90日期限・activation／account要件](https://www.microsoft.com/en-us/evalcenter/evaluate-windows-11-enterprise)があり、
無条件に使えるoffline代替とはしない。個人Microsoft account／host profileをguestへコピーしない。
online準備が必要なら、試験guestとは区別した準備工程の通信先・回数・account扱いを別承認にし、今回の許可で行わない。

## 7. 構築と実証の段階計画（すべて未実施）

| 段階 | 次回行うこと | 成功条件 | STOP条件・証跡 |
| --- | --- | --- | --- |
| P0：情報確定 | 正確な製品版、公式設定資料、ライセンス、署名済みinstaller／ISO、容量・鍵・搬出方法を固定 | 説明可能な採用版と承認範囲 | 403で未取得の設定手順、利用条件不明、署名／SHA不整合、OOBE不明ならSTOP |
| P1：準備承認 | 管理者操作、driver／service／adapter追加の有無、再起動、VM配置、復元を利用者へ提示 | 個々の変更への明示承認と新baseline | 既存task／network／VBSを暗黙変更するinstallerならSTOP。権限昇格やrebootは自動承認しない |
| P2：guest構築 | 新規空領域へ一台だけ作り、合成入力ISOと専用diskだけを接続 | ライセンスと準備済みguest、全共有経路の設定証拠 | 本番volume・既存VM・個人profileの接続、資源不足、未知deviceでSTOP |
| P3：外側境界 | guest開始前後のVM設定SHA、NIC、共有、USB／VMCI、backend modeを照合 | 許可したconsole入力／ISO／output以外の経路なし | NICだけを根拠に合格にしない。不明経路、WHP／VBS競合、clock異常でSTOP |
| P4：内側境界 | guestのroute／adapter／share／device、SID／DACL、書込みallowlistを観測 | guest内から本番資源が見えず、OS negative-controlが拒否を示す | 外部疎通試験の対象と上限は別承認。公式サイトは使わない。拒否を確認できなければmock未起動のままSTOP |
| P5：mock試験 | guest内親controller→固定mock entrypoint。stdin／stdout等の限定IPCだけで版付きpacketを渡す | Job所有権、子孫停止、timeout／cancel／crash、path差替え拒否、receipt fsync／replace／readbackが実証 | 未所有processを終了しない。保存不明・receipt欠損・残存・二重requestはSTOPし、失敗runを再開しない |
| P6：E2E | guest内で予約→前夜receipt→固定source→共通Elo→10件mock保存→saved reader→feed投影 | 同じsnapshot、再表示worker起動0、旧reader不変 | 実artifact、実collector、モデルloader、実fixture、運用rootが見えたらSTOP |
| P7：搬出 | guest終了後、専用output diskをread-onlyの独立検証環境へ渡す | manifest／全SHA／CRC、receiptとJUnitが一致し、host側受入れが限定される | hostへの無条件mount／Autorun／任意path書込みをしない。安全な読戻し手順が未確定なら搬出もSTOP |
| P8：復元・破棄 | 電源off状態の基準cloneへ戻す。失敗diskと証跡は保存 | backup読戻し後の個別承認 | snapshotだけでbackup済みとしない。VM解除・disk削除は明示承認後に専用rootを再確認 |

今のPhase 5B-1は純粋packet契約だけであり、実mock controller／worker／耐障害receiptはまだない。
上のP5用コードを設計・実装する別工程が必要。計画表は動作するlauncherや通信permitではない。
将来のtest runnerは`SYNTHETIC_ONLY`の入力とmock identityを強制し、real entrypointへのfallbackを持たせない。
承認済みtest一覧、Python／wheel／code SHAをISOのmanifestへ固定し、pipのonline取得・user-siteを使わない。
Phase 5B-1の114 PASSやPhase 4の613 PASS等の過去件数を次のguest実績に加算せず、新JUnitと全receiptを採る。

搬出手順の第一案は、専用output仮想diskを停止後にread-onlyの独立した検証guestへ接続する方式。
hostでの直接mountの安全性は未実証であり、今回承認しない。検証guestからhostへの最終report転送には、
新規の限定受信先、byte／file数上限、allowlist、SHA照合、実行禁止を持つ別の受入れ設計が必要である。
未設計の隙間を共有folder・clipboardの一時有効化で埋めない。この未確定点もPARTIALの理由である。

## 8. 既知異常の独立評価

| 事象 | 既存証拠で分かること | 既存運用への扱い | 隔離VMへの扱い |
| --- | --- | --- | --- |
| 07:00タスク | 2026-10-23 07:00:01 JSTに自動実行。updater記録は07:00:03.585656〜07:00:33.811992。終了1、prediction_history_incomplete。10/25に先行する10/24のscheduled 5試合 | 運用の失敗／HOLDとして保持。修復・再実行なし。研究原因とも正常成功とも認定しない | 隔離方式の互換性を示す事象ではない。shared hostのCPU／RAM／IO競合はあり得るので将来の試験時間帯を別指定し、taskを止めて回避しない |
| Chrome renderer | 観測22件中21 identity一致。同じ既存親に対するrenderer1件の置換。原因は未特定 | 起動・終了・profile操作・自動修復なし。全browser環境の不変を認定しない | guestへprofile／UDFを渡さない。VMの正常性／異常性の証拠にはしない。host crash等の独立兆候が後にあれば構築前STOP |

Phase 5B-1の証拠SHAと既存private記録を再照合した。taskやChromeを再現してはいない。
07:00／22:00直近の動的試験は避ける計画とするが、taskの定義・状態は変更しない。

## 9. 未確認事項・判定・承認境界

未確認はBIOSの詳細設定、WHP実利用、Home／当該full buildの製品別適合、正確なinstaller SHA／署名、
現行版の全共有・VMCI設定、guestライセンス／OOBE／activation、空きRAM再確保、data volumeの物理独立性、
安全な最終搬出の実装、全dynamic試験である。実行禁止の調査からこれらを推測でPASSにしない。
現行版のWorkstation詳細HTMLと旧版公式PDFは403、Oracleの一つの旧URLは404だった。
制限への再試行・proxy回避はせず、取得可能な一次資料と取得できなかった範囲を台帳で区別した。
ESXi／VMRC用のUSB／clipboard記事をWorkstation 26H1の設定保証として流用していない。

今回の成果物は本書とJSONだけ。静的整合検査・JSON構文・差分・保護監査を行い、旧114 PASSは再実行扱いにしない。
前回45,019を固定期待件数にせず、Phase 5B-1 worktreeも含めた新baselineを採った。最終件数とSHAはJSONに記録する。
今回の静的整合検査は45項目PASS／0 FAIL。dynamic試験は0件。JSONの構文とSHA、文書参照、UNKNOWNの保持を確認した。
新baselineは45,616ファイルで、SHA・file identity・size・mtime・creation timeの差分0。
モデル53 payload、既存19予測、タスク定義・実行状態、mainと全旧worktreeの不変を照合した。
環境選定の未確定点が残るため`PHASE5B2_ENV_PARTIAL`とし、commit／pushの完了条件を満たしたとは扱わず、
二つの文書を新branchの未コミット変更として保持する。main／Phase 4／5A／5B-1へmergeしない。

**次に承認を求める対象は情報・資材の確定だけ**：Workstation採用版の公式手順／installerとguest用Windowsの
使用権・準備方法、限定搬出設計を揃える工程。installer／ISOの取得やportal loginが必要なら、その操作を個別に提示する。
その後でRAM／diskを再確認し、VMソフト導入、必要な管理者変更・再起動、VM作成、guest起動、dynamic negative-controlを
それぞれ別承認にする。今回の調査完了をそれらの承認へ読み替えない。
VM内で得る将来の結果もguest OS／製品版／設定／diskに限定し、host Windows上の動作や電源断永続性へ拡張しない。

## 10. 追加調査（2026-10-23、既存2文書を保全後に追記）

本節は初回preflightを置き換えず、追加依頼7項目の調査結果を記録する。上記45項目PASSは初回の静的検証実績であり、今回の再実行件数へ加算しない。追記前のMarkdown／JSONをprivate領域へ複製し、両方のSHA一致を確認した。追記前SHAはJSONの`additional_investigation.preserved_reports`に記録する。

### 10.1 Workstation Pro 26H1の入手・対応・導入条件

Broadcomの26H1発表は、Windows用アプリケーションの64-bit化とSupport Portalからの提供を明記する。商用・教育・個人の無償利用と、ゲストWindowsのライセンスは別である。[26H1公式発表](https://blogs.vmware.com/cloud-foundation/2026/05/14/announcing-vmware-workstation-and-fusion-26h1/)

将来の入手手順は、公式KB 368667のWorkstationリンクからSupport Portalへ進み、本人が登録／ログインし、正しいprofile・Trade Compliance情報と利用条件を確認して、Windows x64の採用版を一つ選ぶ。第三者mirror、共有account、推測したbinary URLを使わない。portal手続き、installer入手、署名・SHA検査は今回は未実施で、正確なpatch／build／installer SHAはUNKNOWN。26H1u1はホスト対応表にある候補にとどめる。[公式入手案内](https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hyper.html)

対応表は26H1／26H1u1にWindows 11を挙げるが、Home 25H2 build 26200.9711を個別認証した表ではない。VBS有効hostのWHP経路を説明するKB 315420は、15.5.5以降、Windows build 19041.264以降、所定CPUを条件にする一方、Environment欄は15／16系列である。i9-12900Kの能力と現行OSはこの古い最低条件を上回るが、WHP optional featureの観測はDisabledであり、DLLの存在だけで26H1の利用成功を認定しない。VBS／HVCI／Windows機能を変更して回避しない。現行版の追加要件と実backendはUNKNOWN。[対応host](https://knowledge.broadcom.com/external/article/315653)、[WHPとVBSの条件](https://knowledge.broadcom.com/external/article/315420)

一般導入KBは、管理者によるinstaller実行とhost再起動を手順に含む。Typical／Customの説明にはhost統合機能も含まれる。これは26H1の全component一覧ではない。採用installerのdriver・service・仮想adapter・自動起動・shortcutの変更内容を事前確定し、個別承認が必要。既存J1AI入口・task・runtimeを変更しないことを導入前後で監査する。現行版の完全なprocessor／component／隔離設定資料は未取得なので、導入要件を全部確認済みとはしない。[公式インストール案内](https://knowledge.broadcom.com/external/article?articleNumber=387947)

### 10.2 Windows 11 Pro x64ゲストの使用権と準備

MicrosoftのWindows 11使用許諾（April 2024）は、2(a)(b)で許諾対象deviceと一instance、2(d)(iv)で仮想利用とinstanceごとの追加ライセンス、4で移転条件、5で正規使用とactivationを扱う。OEM掲載先の文書だが本文1(a)はpreinstalled／retail双方を対象に含み、volume契約は別と明記する。**hostのHomeライセンスから、並行稼働するProゲストの権利を自動付与されたとは扱わない。** 購入経路・地域・edition・譲渡／再利用条件に対応する実際の許諾と正当なProゲスト権利の提示が必要で、現時点の保有権利はUNKNOWN。keyだけの出所不明品、未認証の継続利用、Enterprise／VDAの別契約を代用根拠にしない。[Windows 11使用許諾・2／4／5節](https://www.microsoft.com/content/dam/microsoft/usetm/documents/windows/11/oem-%28pre-installed%29/UseTerms_OEM_Windows_11_English.pdf/)

正規メディアの入口はMicrosoftのx64 ISOページ。VM向けmulti-edition ISOで、正しいeditionは対応keyに従う。今回観測した日本語ページの提供表示は**26H2**であり、初回計画の25H2と異なる。ページ表示は取得時の資料観測に限定する。25H2の正当な保有メディアか公式提供経路を確認する、または26H2への計画変更とVMware側guest対応を改めて審査する必要がある。自動的に26H2へ変更しない。ISOの実SHA／言語／版／署名内容は未取得。将来は公式表示のSHA256と照合し、ISOをguestの仮想光学driveへ接続する。hostを書き換えるInstallation Assistantやhost boot変更、USB初期化を使わない。[Microsoft公式ISO入口](https://www.microsoft.com/ja-jp/software-download/windows11)

MicrosoftはPro個人利用の初期設定にInternetとMicrosoft accountを要求する。従って、空のPro VMを最初からNICなしで正式に準備できるとは確認できない。準備済み・適法なoffline guest imageを用意する経路、または**試験とは別の承認済み初期準備**でOOBE／activation／更新を済ませ、その後完全停止・共有解除・NIC除去・新baseline・clone封印を行う経路を審査する。後者の通信・account・VM起動は今回未承認。host個人profileや既存認証情報をguestへコピーしない。回避commandや架空のoffline例外は提案しない。cloneと独立検証用guestの使用権も別確認する。[Microsoft初期設定要件](https://support.microsoft.com/en-us/windows/experience/compatibility/windows-11-system-requirements)

### 10.3 隔離構成の設計と確認待ち項目

以下は要求値であり、26H1設定を実操作して確認した値ではない。正確なUI／設定項目は採用版の公式資料と将来の設定readbackで立証する。不明なVMX keyを生成しない。

| 経路 | 構築時に要求する状態 | 承認後の確認・STOP条件 |
| --- | --- | --- |
| network | 全virtual NICを構成から外す。NAT、bridge、host-only、USB NIC、RDP等なし | powered-off設定とguest側adapter／route双方を記録。未知deviceや到達可能経路があればmock未起動でSTOP |
| host folder | shared folderを0件、無効。host disk／repo／runtime／profileのmappingなし | GUIと保存設定、guest側mount／shareを照合。空のshare一覧だけで全経路なしと認定しない |
| clipboard／D&D | 双方向とも無効。Guest Isolationの各操作を採用版の資料で確認 | 実hostのclipboardや個人fileを使わず、専用markerだけでnegative-control。未実証ならSTOP |
| USB／他device | USB controller・auto-connect・passthroughなし。Bluetooth、printer、camera、audio、physical diskも不要なのでなし | host物理deviceを接続して試さない。設定とguest device inventoryで確認 |
| guest integration | 原則Tools／guest-control agentを導入しない。VMCI／vsock／remote制御も未承認 | Toolsなしを全遮断の証拠にしない。残存経路を採用版で確認できなければSTOP |
| storage／console | 専用virtual diskとread-only合成ISO、local consoleだけを明示許可 | 既存host領域へ広いwrite権やfolder共有を与えない。出力ACL／Owner確認は将来guest内で実施 |

公式Tools資料は共有folder componentを説明するが製品欄はvSphere ESXiであり、Workstation 26H1のGUI設定証拠へ転用しない。ESXi／VMRCのclipboard・USB手順も代用しない。[Tools資料と適用範囲](https://knowledge.broadcom.com/external/article/415374/customizing-vmware-tools-for-automated-w.html)

### 10.4 合成入力・限定搬出・復元／破棄の手順案

1. 専用領域に採用commitのallowlistだけを複製する。合成fixture、mock契約、将来の承認済みmock controller、Python installer／offline wheels、テスト仕様を入力manifestへ記録する。モデル・実source・予測・認証情報・Git履歴・個人pathを含めない。各SHAと総bytesを固定し、read-only ISOにする。今はmanifest／ISOを作成しない。
2. 適法に準備済みのguestを完全停止した状態でclean baselineとbackupを封印する。設定SHA、OS／Python／code版、時刻、全device一覧を記録する。test cloneへ入力ISOと専用output diskだけを付ける。暗号化／vTPM情報はprivate保管し公開しない。
3. 承認後guest内で入力全SHA、非特権user、専用write allowlist、ネットワーク非接続と共有経路を検証してからmockを開始する。Phase 5B-1の114 PASSやPhase 4の613 PASSをguestの新実績へ足さない。新JUnitとrequest／batch／receiptを採取する。
4. 終了時はworker残存を確認し、guest内で全entry SHAとCRCを計算する。異常runも保存して再試行しない。guestを完全停止し、outputを含むVMファイルをhostの新規private backup先へ**不透明なbytesとして**複製・SHA読戻しする。guest filesystemをhostへmountしたことにはしない。backup bytesの一致はguest各fileの意味検証とは別である。
5. 最小搬出案はlocal consoleから**4 KiB以下の固定schemaの集計・gate・証拠digestだけ**を人が新規専用reportへ転記し、2回の読取りで照合する。実行file、任意path、個別原文、ログ全文を搬出しない。これは全payloadの独立検証に代わらない。
6. 完全な機械可読搬出は、試験VM停止後、outputのcopyを独立検証環境でread-only審査し、別実装の限定receiverへ送る設計を別承認する。候補契約は固定名のJSON／JUnit／SHA台帳のみ、合計16 MiB・最大128 files・各2 MiB・有限deadline。UTF-8とschema、path traversal、reparse、重複名、SHA、XML外部参照の拒否、exclusive-createを要し、失敗時は公開0件。転送方式の採用版対応とreceiver実装は**UNKNOWN／未実証**であり、共有folderやclipboardの一時有効化で穴埋めしない。
7. 有効なbackupと結果readbackを確認するまでVMや失敗diskを削除しない。再試験は封印したclean baselineから新clone・新run IDを作る承認で行い、失敗runを無断再開しない。破棄時は電源off・所有関係・専用root・backup SHAを確認し、VM登録解除とその専用ファイル削除を個別承認後に行う。hypervisorのuninstall／host復元も別操作であり自動実行しない。

上記は静的な手順案である。ISO投入、device非共有、限定搬出、復元、破棄を実証したとは扱わない。特に完全搬出は依然U06でHOLD。

### 10.5 16 GiB hostと6 GiB guestの資源条件

追加の読取り観測は2026-10-23 07:45:36 JST。OS可視RAMは15.646 GiB、availableは**5.158 GiB**、OSが返すfree virtual memoryは25.089 GiBだった。後者はpagefile等を含む値であり、空き物理RAMやVMの予約保証として使わない。初回4.879 GiBから変化したが、起動gateの9 GiBには届かない。

次はvendor最低条件ではなく、本試験向けの**保守的な計画閾値**で、未ベンチマークである。

| 時点 | 条件 | 不成立時 |
| --- | --- | --- |
| 起動前 | 6 GiB guestに対しhost available 9 GiB以上を30秒間、3回の読取りで確認。約3 GiBをhypervisor overhead／host余裕として残す計画 | 1回でも不足ならVM未起動でSTOP。pagefile増量、host app／task終了、RAM自動減量で回避しない |
| disk | VM用新規data領域に160 GiB以上、host system volumeに20 GiB以上の空き。backup容量は別確保 | 同一物理diskか不明なら冗長backup認定せず記録。容量不足ならSTOP |
| 実行中 | guestは1台のみ。host availableが2 GiB未満で10秒持続、commit使用率90%以上、低メモリ通知、観測欠損、host応答異常で新test開始を停止 | 所有するmockだけを有限時間で停止しreceiptを保存、guestを正常shutdownする手順を次工程で実装。無関係processは終了しない |
| cleanup不能 | guest shutdown／owned child停止が期限内に完了しない | 結果HOLD。無関係processのkill、host reboot、VMファイル削除をせず証跡と状態を残す |

現在のRAMでは開始不可。利用者が選ぶ静かな時間帯／別host／承認済み容量計画で再確認する。今回資源解放、VM予約、監視worker起動は0。

### 10.6 既知異常と追加調査の正式結論

07:00タスクのexit 1、`prediction_history_incomplete`、先行5試合未完了、8可変出力変更と40追加fileは旧証跡の記録どおりである。旧publicationと19保存予測の不変を別評価しており、正常成功とも研究原因とも認定しない。Chrome renderer置換1件も原因UNKNOWNのまま。追加調査では再現・修復・profile調査をしていない。

両件は26H1／WHPの可否を示さない。shared hostのRAM／CPU／IO圧迫による干渉の可能性はあるので、将来のVM準備・試験時間帯を07:00／22:00と重ねない計画とする。ただし時刻だけで資源非干渉を証明せず、task定義を変更せず、開始前と終了後の独立証跡・SHAで区分する。説明不能な固定保護対象変更や新host異常なら開始STOP。Chrome停止やtask修復による資源確保は行わない。

追加7項目の調査は文書化したが、正確な26H1版・Home／WHP動作と隔離設定、ゲストの実際の使用権／25H2媒体または版変更／OOBE準備、RAM、完全搬出が未確定なので、判定は**`PHASE5B2_ENV_PARTIAL`を維持**する。VM内のJob／ACL／通信遮断／receipt／crash等はすべて未実施で、PASSに含めない。

次に必要な承認は段階別に分ける。まず採用patchとguestの使用権・版・準備方式・搬出方式を確定し、本人によるportal手続きとinstaller／ISO取得、購入が必要ならその費用を承認する。その後、変更component一覧を提示して管理者導入・必要な再起動を別承認し、さらにVM作成／初期準備通信／完全offline化／mockとnegative-control／限定搬出／復元・破棄を個別承認する。VBS・Firewall・Windows機能の変更は本案の回避策に含めず、必要性が出た時点でSTOPする。**この追加調査からVM構築へは進まない。**

## 11. 検証環境の再評価と必要最小構成（2026-10-23）

### 11.1 現在の判定・前段との関係

設計判定は **`PHASE5B2_ENV_STRATEGY_READY`**。検証項目の分類、選定理由、実行順序、未実証条件と承認境界を確定したという意味である。**実行環境の成立は`PHASE5B2_ENV_PARTIAL`、Phase 5B全体の動的合格はNOT_VERIFIEDのまま**。実装済み・動作済みのworker、利用可能なVM、検証済み搬出経路を新たに認定していない。

今回の指示は、静的検証と保護監査が合格し、調査成果物が完結していれば、PARTIALを保持した文書でもcommit・通常pushしてよいと明示した。これは前回の「READYの場合だけGit保存」の条件を今回の文書保存について更新する。1〜10節の旧判定・旧Git条件は履歴であり、書き換えて成功扱いにしない。Phase 4／5A／5B-1は不変、変更はこの調査書とJSONだけである。

開始時HEADは`2badf8f3f46c7e1a9c18d256ba8207f0dc3dfc2a`、専用branchは`feature/weekend-phase5b2-env-preflight`。未コミット2件の原本をSHA-256・bytes・Git status/diff付きで別private領域へ保全した。以前の保存copyと75静的PASSのreceiptも保持した。OS、RAM、diskの記載値は前回までの観測であり、今回の現在値を推測していない。

### 11.2 分類原則と脅威モデル

- **A：hostで安全な読取り・純粋契約**。packet/schema/ID/revision、仮時計、論理状態、重複、禁止経路AST、既存証拠SHA。必要な文書・監査保存とGit以外の機能実行はしない。
- **B：host動的実行の条件付き候補**。合成file、receipt、flush/replace/readback、専用sandboxのOwner/DACL等。既存本番と別namespaceを作るだけでは不足し、OSの権限・保存先identity・network境界を独立立証した後に限る。**今は未立証・未承認なので実行0**。
- **C：Windows隔離環境で優先実証**。通信遮断、mock/子孫、Job、ACL・path競合、crash/Stop、非共有。現在のhostで安全性を立証する追加作業より、専用Windows環境での実証を選ぶ。APIそのものが必ずVMを要求するという分類ではない。
- **D：将来の別承認**。実worker、実Champion、モデル、HTTP、本番保存/feed、電源断、本番導入。mock合格から承認しない。

想定する失敗は、誤ったentrypoint/import、環境変数・依存による副作用、子孫の逃走、同一user権限での本番読書き、ネット接続、PID再利用、ACL/reparse/path競合、状態不明なcrash、重複request、成功receiptの誤集計である。Pythonのguardと専用folderだけでは、これらのOS境界を確立できない。VMもhypervisorの欠陥や全side channelの不存在を保証しない。承認したconsole／入力media以外のdevice・共有経路を個別に確認する。


### 11.3 全検証項目の分類台帳

分類数：A=42、B=11、C=25、D=8。行政的preflight／Git項目も落とさず含める。Dはmock合格対象の外であり、新しい承認を要する。各行のhost実行条件・Linux代替範囲・必要証拠・原指示対応はJSONにも保持する。

| ID | 検証・管理項目 | 分類 | 必要OS／host判断の根拠 |
| --- | --- | --- | --- |
| P0.01 | Git branch/HEAD/status/remote読取り | A | 環境の読取り・設計でworkerを実行しない |
| P0.02 | Phase1-5A/5B1契約の読取り | A | 環境の読取り・設計でworkerを実行しない |
| P0.03 | 設計との矛盾確認 | A | 環境の読取り・設計でworkerを実行しない |
| P0.04 | Phase4/5A依存関係確認 | A | 環境の読取り・設計でworkerを実行しない |
| P0.05 | 専用branch/worktree境界 | A | 環境の読取り・設計でworkerを実行しない |
| P0.06 | 未コミット変更保全 | A | 環境の読取り・設計でworkerを実行しない |
| P0.07 | 保護baseline | A | 環境の読取り・設計でworkerを実行しない |
| P0.08 | Python/pytest/OS依存情報 | A | 環境の読取り・設計でworkerを実行しない |
| P0.09 | 専用directory/entrypoint指定 | A | 環境の読取り・設計でworkerを実行しない |
| P0.10 | 境界不明時STOP | A | 環境の読取り・設計でworkerを実行しない |
| P1.01 | 独立mock process起動 | C | process実行にはOS通信/書込み境界が必要 |
| P1.02 | 実worker/Champion/model import禁止 | A | 純粋moduleのAST・依存固定を読む |
| P1.03 | source/fixture/Elo/outputの合成scope | A | data契約はOS非依存 |
| P1.04 | request/response schema・ID・revision・timeout値 | A | bytesと仮時刻の純粋検査 |
| P1.05 | 終了code/例外/途中切断の実transport | C | 純粋packet拒否とpipe切断/child exitは別 |
| P1.06 | 重複response/request/不正状態遷移 | A | in-memory契約の証明に限定 |
| P1.07 | mock以外entrypointの実起動拒否 | C | 実executable identityの確認が必要 |
| P1.08 | Phase4互換readerの静的固定 | A | 既存readerを変更しない |
| P2.01 | OSレベル通信遮断 | C | socket mockはOSポリシーではない |
| P2.02 | 専用IPCだけを許可 | C | loopback/network/任意named pipeへ広げない |
| P2.03 | HTTP/DNS/API外向き接続拒否 | C | OS negative-controlが必要 |
| P2.04 | 遮断方式/適用範囲証拠 | C | 設定なしや観測欠損は安全としない |
| P2.05 | 本番volume/profile非共有 | C | network無効だけではfile共有は残る |
| P3.01 | 所有child限定・PID再利用対策 | C | Windows process所有権と故障注入はVM内へ集約 |
| P3.02 | 起動前専用entrypoint検証 | C | Windows process所有権と故障注入はVM内へ集約 |
| P3.03 | Windows Job割当・nested条件 | C | Windows process所有権と故障注入はVM内へ集約 |
| P3.04 | 正常exit/timeout/cancel | C | Windows process所有権と故障注入はVM内へ集約 |
| P3.05 | Stop競合・worker crash | C | Windows process所有権と故障注入はVM内へ集約 |
| P3.06 | 子孫の残存・breakaway検出 | C | Windows process所有権と故障注入はVM内へ集約 |
| P3.07 | 他process非終了 | C | Windows process所有権と故障注入はVM内へ集約 |
| P3.08 | handle解放 | C | Windows process所有権と故障注入はVM内へ集約 |
| P4.01 | 専用合成保存領域 | B | 既存本番と非共有/書込み制限が別立証ならhost候補 |
| P4.02 | Owner SID/DACL/ACL意味 | B | 専用sandboxだけなら条件付きhost候補、現状は読取りのみ |
| P4.03 | reparse/junction/symlink拒否 | C | Windows再解析とidentityの実OS試験 |
| P4.04 | 書込み前/公開直前identity | B | 固定handle/path identityが必要、現在のsafe()はprecheck |
| P4.05 | 領域外への書込み拒否 | C | 同一userの専用folderだけでは本番書込拒否にならない |
| P4.06 | ACL変更・権限拒否negative | C | 権限故障は実OS隔離で実施 |
| P4.07 | 親directory/symlink競合差替え | C | 攻撃的競合をhost本番と同居させない |
| P4.08 | 昇格/既存ACL変更禁止 | A | 禁止境界を静的に確認 |
| P5.01 | schema/request/batch/revision/mock/UTC/理由 | A | 純粋なreceipt内容は既存契約 |
| P5.02 | receipt新規fileと合成namespace | B | 仮領域の保存は境界立証後host候補 |
| P5.03 | temp/flush/fsync/replace/readback | B | 同名APIでもOS/FSの動作差がある |
| P5.04 | receiptと保存batch対応 | B | persisted batchとrequest/receipt結合を確認 |
| P5.05 | 二重実行・二重commit競合 | C | tuple ledgerは実process間排他ではない |
| P5.06 | receipt保存前後crash | C | process kill時の保存境界を実証 |
| P5.07 | receipt欠損/改変/不完全拒否 | B | 保存byteの読戻しも必要 |
| P5.08 | 失敗後再試行/不明run非再開 | C | durable consumed intentと実子起動を結合 |
| P5.09 | receipt生成失敗を黙殺しない | B | 例外処理は保存failureを反映する |
| P6.01 | Phase4予約→receipt→source→Elo→10件→reader→feed | B | 純粋mockのみだが合成file保存を伴う |
| P6.02 | worker出力と固定source revision | C | worker経由のsnapshot/bindingは未実装 |
| P6.03 | 保存後feed再投影worker起動0 | C | 実worker起動countを親receiptで検証 |
| P6.04 | latest更新/改日程/保存値不変 | B | 合成registryと既保存batchの検証 |
| P6.05 | 旧日別/旧v2 reader不変 | A | コード/契約SHAを固定 |
| P6.06 | feed失敗時batch保持・改変検出 | B | 書込みfailureとbefore_save/visibilityを検証 |
| P6.07 | 実モデル接続をPhase5Cへ分離 | A | scopeとimport経路を静的に拒否 |
| P8.01 | モデル53 payload | A | 読取り監査だけで設定/状態を変更しない |
| P8.02 | 既存19予測 | A | 読取り監査だけで設定/状態を変更しない |
| P8.03 | 公式source/publication | A | 読取り監査だけで設定/状態を変更しない |
| P8.04 | Phase4 branch/worktree | A | 読取り監査だけで設定/状態を変更しない |
| P8.05 | Phase5A branch/worktree | A | 読取り監査だけで設定/状態を変更しない |
| P8.06 | main | A | 読取り監査だけで設定/状態を変更しない |
| P8.07 | 全他worktree | A | 読取り監査だけで設定/状態を変更しない |
| P8.08 | 運用task定義/状態 | A | 読取り監査だけで設定/状態を変更しない |
| P8.09 | GUI/browser保護範囲 | A | 読取り監査だけで設定/状態を変更しない |
| P8.10 | 新baseline/差分帰属と非修復 | A | 読取り監査だけで設定/状態を変更しない |
| P9.01 | 構成/通信schema/endpoint/隔離仕様 | A | 文書化は実行承認ではない |
| P9.02 | Job/ACL/receipt/negative-control記録 | A | 文書化は実行承認ではない |
| P9.03 | Phase4互換性/保護/未実証の区分 | A | 文書化は実行承認ではない |
| P9.04 | Phase5C承認条件と新旧実績の区別 | A | 文書化は実行承認ではない |
| P10.01 | 差分精査 | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.02 | diff --check | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.03 | 静的検証/回帰の実績区分 | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.04 | 保護監査 | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.05 | 証拠文書化 | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.06 | 専用branchへ条件付きcommit | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.07 | 通常push/local-origin-remote一致 | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.08 | worktree clean | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| P10.09 | main/Phase4/5A/5B1非merge | A | 今回の新指示は調査成果物のPARTIAL保存も明示許可 |
| D.01 | 実worker接続 | D | 今回およびmock検証の承認外 |
| D.02 | 実Champion接続 | D | 今回およびmock検証の承認外 |
| D.03 | 実モデルload/推論 | D | 今回およびmock検証の承認外 |
| D.04 | 公式HTTP/robots | D | 今回およびmock検証の承認外 |
| D.05 | 本番予測保存 | D | 今回およびmock検証の承認外 |
| D.06 | 本番feed更新 | D | 今回およびmock検証の承認外 |
| D.07 | Windows実電源断耐性 | D | 今回およびmock検証の承認外 |
| D.08 | 本番runtime/task導入 | D | 今回およびmock検証の承認外 |

Step 7の正常5ケース・異常19ケースは上記該当行へ一対一に参照を付けた。実行済み件数ではない。正常・異常をまとめた行の詳細な期待証拠はJSONの`Step7_scenario_coverage`と`requirements`を参照する。


### 11.4 Windows固有機能と共通部分

| 境界 | host／Linuxで扱える共通部分 | Windows上で必要な実証 |
| --- | --- | --- |
| process群 | request/exit/timeout/Stopの仕様、汎用pipeやprocess群の概念 | Job handle、nested制約、suspended作成後のassign、kernel identity、孫process、handle解放 |
| file権限 | allowlist/path検査の仕様、Linux UID/GID/mode等の別実装 | tokenとOwner SID、ACE/DACL継承、NULL/empty DACL、NTFS file ID、junction/reparse、実アクセス拒否 |
| 永続化 | staging→検証→公開→receiptの論理、schema/SHA | 採用Windows/Python/NTFS/virtual diskでflush、共有mode、rename/replace、ACL/fileID、失敗後readback |
| packet／transport | canonical JSON、サイズ、SHA、request/batch/revision、重複、terminal | Windows pipe handle、部分read/write、切断、child exitとの結合。純粋receiptは実OS receiptへ昇格させない |
| 通信遮断 | 禁止API/importの静的確認、アプリ内guardの拒否 | OS・VM境界と承認済みnegative-controlによる拒否証拠。DNS/HTTPがguardを迂回しても拒否できること |
| crash | 不明runを再開しない論理、file failureの合成模擬 | process強制終了後のreceipt/lock/残存/公開groupの読取り確認。OS停止・実電源断は別Dゲート |

MicrosoftのJob資料はprocess群の管理機能であり、子の継承とbreakaway条件、最後のJob handleに関する終了条件を説明する。したがってPID killだけの一般process testをJob合格としない。Job割当失敗や既存parent Jobとの競合はSTOPし、escape flagを追加して回避しない。Jobを作ってもnetwork/fileアクセスが自動的に遮断されるとは扱わない。[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)、[割当と権限・nested条件](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)

Windows ACLはACEをDACLで評価する。Linuxのpermission拒否をOwner SID/DACL/NTFS合格へ読み替えない。[Windows ACL](https://learn.microsoft.com/en-us/windows/win32/secauthz/access-control-lists)

Python 3.12の`os.fsync`はWindowsでMS `_commit`を使う。`flush`、OS bufferのflush、単一renameの可視性、directory/device cacheの電源断永続性は別である。Windows `ReplaceFileW`にはACL/fileID/同volume/失敗時状態の規則があり、WRITE_THROUGH flagは未対応。**現在のPython呼出しがReplaceFileWを使うとは主張しない**。API一般資料から週末batchの永続性を認定しない。[Python os](https://docs.python.org/3.12/library/os.html)、[Windows buffer](https://learn.microsoft.com/en-us/windows/win32/fileio/flushing-system-buffered-i-o-data-to-disk)、[ReplaceFileW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-replacefilew)

Linux cgroupはLinux側process群やresource制御の資料であり、Windows Jobの互換証拠ではない。Linux VMは共通packet／汎用transport／論理的な障害手順の試作には使えるが、Windows Job、SID/DACL、reparse、NTFS、Windows pipe/handle/replaceを代替しない。WineやWSLでもWindows kernel試験の代替としない。[Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)

### 11.5 6方式の比較と選定

以下のmemoryは性能測定ではなく計画値。実際の容量・license・設定・negative-controlを通過するまで起動しない。

| 方式 | memory／準備 | Windows範囲と隔離 | 入出力・rollback／費用・主なrisk |
| --- | --- | --- | --- |
| 1 host純粋／file sandbox | guest予約なし。Aは低負荷、Bは境界実装が別途必要 | Aは実施候補。sandbox folderだけで本番非共有や通信拒否は成立しない | Aはbytes、Bは新規専用root。失敗証拠を保持。新guest license不要だがhostへの動的副作用が残る |
| 2 制限付きhost mock | guest RAM不要。token/IPC/network/file policyを新規実装・実証 | Windows APIは使用候補だが、現在の通常tokenやJobは強い隔離ではない | AppContainer候補も現在未構成。環境を増やさなくても独立した境界試験が増え、task/browser資源と同居 |
| 3 Linux VM | headless 1〜2 GiBは未測定の候補。hypervisor/OS/Python準備が追加 | no-NIC/no-share設計は可能だが未実証。Windows固有の代替は不可 | ISO／限定搬出が必要。distribution条件を確認。さらにWindows環境が必要なので主経路から除外 |
| 4 VMware＋Windows | guest 6 GiB、host available 9 GiBの従来計画。現在値は未取得 | Windows機能を同じguestで実証できる。Home/WHP/VBSと正確なdevice隔離は未確認 | 正規guest/ISO/準備と搬出が必要。Workstation利用条件とWindows権利を別確認。RAM不足ならlocal起動不可 |
| 5 VirtualBox＋Windows | 同じWindows RAM要件、製品overheadは未測定 | Windows機能はguestで実証。VBS/Hyper-V併用と性能に未解決risk | 入出力・guest license課題は同じ。host保護を下げるVBS無効化は採用しない |
| 6 外部の専用Windows環境等 | 現PCのguest RAM予約0。外部容量/所有権/費用はUNKNOWN | 本番非共有のWindows VMか専用機なら候補。remote consoleとguest egressを分離して審査 | 利用可能な環境は未確認。遠隔console/投入/搬出とlicense・責任範囲を別承認。今は接続しない |

Windows HomeではSandboxは非対応。WSL2／Linux containerはWindows kernel固有試験を満たさず、現時点で起動可能な環境も未確認である。AppContainerは公式にresource隔離を提供するが、現在のPython mock用に適切なcapability/token/IPC/bootstrapが成立した証拠はないのでhost代替として先行起動しない。[AppContainer](https://learn.microsoft.com/en-us/windows/win32/secauthz/appcontainer-isolation)

**推奨は案C：hostはAの静的・純粋契約、動的検証は追加する1つのWindows隔離環境へ集約。** Bは「技術上hostでも条件付きで可能」という分類を維持するが、今回選ぶ実行場所はCと同じWindows環境とする。Windows OS必須と、VMを選ぶ安全上の判断を分ける。

案Aを採らない理由は、hostのnetwork/write境界が未立証で、host動的用の制限実装とVM用の隔離実装を二重に証明することになるため。案Bを採らない理由は、純粋契約はhostで既に検証でき、Linuxを追加してもWindows固有試験が残り、導入・搬入出・回帰の重複が増えるため。VM構築を目的化せず、**Windows動的環境1つ、Linux追加0、guest同時稼働1**を最小の選定構成とする。

local softwareはVMware 26H1を条件付き候補として維持する。ただし、16 GiB機に無理に載せることは選定条件ではない。過去の空き5.158 GiBでは9 GiB開始gate未達だった。現在値を推測せず、容量を確保できないなら本番環境を停止して捻出せず、利用可能性・費用・権利を確認した外部専用Windows環境を同じ案Cの配置候補として別承認する。旧25H2案と公式ページの26H2表示、ゲスト使用権/OOBE、WHP、隔離設定、完全搬出の未確定事項は残る。

### 11.6 次段階の実装・実証順序と承認

| 順序 | 作業／環境 | 次へ進む条件 | 別承認 |
| --- | --- | --- | --- |
| G0 現工程 | 分類・AST・契約/SHA・文書検証、host読取り監査 | 文書とJSON一致、旧実績/未実証を区別、保護差分0 | 今回はここまで。文書commit/pushだけ許可 |
| G1 非起動実装 | mock/controller/OS receipt adapterを別実装し、hostで純粋検証 | 固定entrypoint・依存SHA・禁止経路、packet→Phase4への明示mapping | 新規実装計画。child起動や本番scopeへのswitchを含めない |
| G2 環境準備 | 1つのWindows隔離環境、正規image、capacity、非共有input/output | 版・license/OOBE・全device・WHP・RAM・搬出が確定 | installer/ISO取得、導入、必要admin/reboot、VM/外部資源、初期準備通信を個別承認 |
| G3 外側境界 | 合成markerによるdeny-network/deny-writeを先に実証 | guest/OS/外側設定と拒否receipt、未知経路なし | negative-control対象と上限。公式hostや実本番pathをprobeにしない |
| G4 OS動的 | 同じWindows環境内でJob/子孫/handle/ACL/receipt/Stop/crash | 所有範囲・期限・領域外拒否・残存0・不明run非再開 | 具体的mockと故障注入計画。昇格権限をworkerへ渡さない |
| G5 合成E2E | 予約→前夜receipt→固定source→共通Elo→10件保存→reader→feed | 固定snapshot、二重保存/再推論0、feed失敗時batch保持、全A/B/C証拠 | 合成入力だけの結合計画。Dへの接続なし |
| G6 最終監査 | bounded搬出・CRC/SHA/readback・保護照合 | 旧JUnitを加算せず新実績を確定。電源断/host動作保証と区別 | 搬出、backup復元、後日のVM破棄は別々に承認 |

現コードは`weekend_mock_contract.py`の純粋packet/ledger/simulation receiptと、Phase 4の合成file公開が別々に存在する。実mock process、controller、実OS receipt、mock namespaceからPhase4へのadapterはまだない。`advance`のCOMMITTEDはin-memory状態であり、disk commitではない。`weekend_batch.safe`の事前path検査だけで競合中のhandle安全性が立証されたとはしない。新たなコード実装・子起動を本調査の副作用で行わない。

後続実装候補は新しいmock専用controller/worker/receipt・Windows境界層・専用testsである。既存`weekend_mock_contract.py`とPhase4の`weekend_batch.py`／`weekend_integration.py`を読取り基準にし、安全gateや旧readerを緩めない。名前とcode SHAはG1で固定する。updater、公式collector、real Champion、研究worker、運用taskへ接続しない。

### 11.7 既知異常、残存risk、STOP

07:00タスク失敗とChrome renderer置換は、前工程の封印済み証拠だけで評価した。taskのexit 1・履歴不完全と、renderer置換1件・原因UNKNOWNはそのままである。再現・修復・browser/profile/task操作は0。これらの事象からVMの互換性や因果関係を決めない。

hostでの強制停止・child/ACL故障注入を先行するための「問題なし」の証拠はなく、shared RAM/CPU/IOやGUIへの干渉を避けるため、該当行を選定上Windows隔離環境へ送る。通常taskを止めて試験時間を作らない。local VMの場合もhypervisorとtaskはhost資源を共有するため、静かな時間帯と実際の資源gate、前後SHAを別確認する。新しい固定保護差分、所有不明、通信/共有不明、領域外write、receipt不明、容量不足ではSTOPし、自動repair/retry/lock回収をしない。

guest OS/build/NTFS/virtual diskでの成功は、そのguest構成に限定する。LinuxのPASS、process crashのPASS、CRC/SHA一致を、Windows JobのPASS、電源断永続性、host安全性へ読み替えない。Dの実モデル・HTTP・本番導入を承認しない。

今回の静的検証件数・保護件数・SHAはJSONの`strategy_validation`と`strategy_protection`を正本とする。既存114契約PASS・104 negative-bearing cases、前回75静的PASSは履歴であり、新規実行分へ加算しない。OS通信／process／ACL／crashのnegative-control実施は0。

**次に承認すべき操作はG1の「起動しないmock/controller/receipt結合実装」と、並行するG2の環境条件の確定である。** VM導入・作成・起動、設定変更・admin・reboot、初期準備通信、mock起動、動的negative-control、搬出、破棄はまだ実行しない。調査のSTRATEGY_READYと、環境のPARTIAL／動的未実証を分けて維持する。
