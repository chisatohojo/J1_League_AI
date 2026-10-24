# NN v2 — G3隔離実証計画

関連判定：`NN_V2_G3_PRE_REVIEW_READY`。本書は設計のみで、試験用process・VM・通信を起動していない。
実transportに関する以下の試験は、環境構築・対象コード・操作範囲を固定した別承認を要する。

## 現在確認できる範囲

2026-10-24の読取り専用CIMでWindows 11 Home、x64、build 26200、HypervisorPresent=trueを再確認。
詳細は [ENVIRONMENT_REVIEW.json](../research/nn_v2/phase2_5P/ENVIRONMENT_REVIEW.json)。
HypervisorPresentは隔離VM利用可能性やnetwork denyの証明ではない。
既存Phase 5B-2のHome/Sandbox非対応、VBS稼働、WHP/VM利用可否UNKNOWNを、取得日付きの過去調査として引き継ぐ。
今回はoptional feature・UEFI・VBS・Firewallの変更/管理者queryを行わず、昇格・再起動も0。

現hostには本用途のOS隔離が実証されていない。G2のapplication guardはOS network denyと同じではない。
旧Gの封印TLS1.3/Job終了/保存成功は、その旧runだけの履歴。新adapter・新policyのqualificationへ流用しない。
旧workerはSSL default context、hostname/CERT_REQUIRED、単一接続、Connection: close、retry/redirectなしをコードで確認できるが、
将来workerの最低TLS版・trust store・proxy継承・native経路・終了保証までは成立していない。

## 試験環境の準備（別承認）

第一案は使い捨てWindows検証VMまたは同等の専用検証機。製品/版の現行対応・guestライセンス・構築権限は別確認とする。
本番repo、runtime、model、raw、browser profile、GUI、タスクを共有しない。
VMのNICだけでなくhost-only/NAT/bridge、共有folder、clipboard、drag/drop、USB、guest統合、remote endpointも点検する。
合成code/Python/wheels/fixtureはSHA付きread-only媒体で投入し、出力はguest専用領域へ限定する。
結果搬出は許可された集計・code/fixture SHA・receiptのみを検証してから行い、guest scriptをhostで自動実行しない。

既存計画の6 GiB guestならhost空き9 GiB以上を安全余裕として再確認する。この数値はvendor要件ではない。
今回の観測はこの計画gate未達。メモリを空けるために運用taskやbrowserを停止しない。
環境準備ができなければP1試験はHOLD。既存hostを便宜的に代用し、無断でACL/Firewallを変えない。
ソフト導入、VM作成/起動/破棄、OS機能変更、管理者操作、再起動は今回承認されていない。

## 隔離試験の順序と受入条件

| 試験群 | 後続の限定試験 | 必須の受入証拠／STOP |
|---|---|---|
| OS隔離 | 承認した専用endpoint以外のIPv4/IPv6・DNS・UDP/TCP・外部process経路をnegative-control | OS policy/VM構成・観測logと拒否結果。Python mockだけでは不可。結果不明なら起動前HOLD |
| TLS policy | 隔離環境内の専用TLS相手でtrust chain、期限、不正CA、hostname違い、version下限を試験 | 明示的なversion floor案はTLS1.2以上、詳細は別審査。失敗は全体STOP、verify無効化fallbackなし |
| Proxy | inherited env/system proxyを記録し、非使用または承認済経路に固定 | 勝手なproxy/MITM/証明書追加なし。未確定routeはSTOP |
| Headers/URL | G1値、method/完全URL/path、最終client headersを固定し、追加/変更を故障注入 | E0/E1と最終header一致、秘密field拒否。HTTP wire証拠やE3とは区別 |
| Lifecycle | poolingなし・単一connection、keepalive禁止、redirect/retry/parallel=0、DNS/TLS失敗、timeout、body/header/type上限 | 不明完了も1 attempt消費。自動別IP/別host/再接続なし。本文切捨てを完成原本としない |
| Job所有権 | 親がsuspended childを作りJob割当・所属を確認してからresume。子孫・escape・cancel/timeout/crash | PID+生成時刻+image/hash+SID+親子/Job membership。割当失敗なら未実行。owned childだけ停止、有限settle後active0 |
| ACL/storage | guest専用新規root、Owner SID/DACL、reparse/junction、親/保存先identityを保持/再検証 | ACL拒否、path差替え、rename/replace/delete共有modeのnegative-control。領域外write不可。原因不明ならHOLD |
| 永続reservation | 2つ以上の専用processでexclusive-create/lock/CAS、同じpermit/slotへ競合 | 同時発行1、二重send0。PIDだけでなく所有marker/creation identity。stale lockを強制削除しない |
| 保存順序 | consume intent→flush/fsync/readback→STARTED→worker、応答→raw/md/request/receipt→seal/readback | reserve読戻し前にDNS/connectを始めない。raw/md/request/receipt相互SHA・実UTC順序一致 |
| Crash/復旧 | intent保存前後、起動直前、send完了不明、raw/receipt/seal途中、完了後を模擬 | partialを成功としない。STARTED/SENTはUNKNOWN_OUTCOME、手動所有審査。attempt・lock・証拠を残し再送しない |

ここでのTLS相手や通信negative-controlも、専用fixture/endpoint・予算・隔離設定を別承認してから行う。
公式6 URLへのG4通信をP1試験に混ぜない。実TLS handshakeを今回行ったとは報告しない。
hostの07:00/22:00タスクは変更せず、重なる場合は実行証跡・時刻・SHAを研究結果と分離する。

## 耐障害性と限界

file fsync/readback、directory rename可視性、directory metadata永続性、receipt順序を個別に検証する。
process kill/crashはOS停止・電源断と区別する。実電源断は別の使い捨て環境/媒体・明示承認でのみ試験し、本計画でも自動実施しない。
read handleがmetadata-onlyではrenameを防げなかった旧staging事象を踏まえ、access rights/share modeを実測する。
全TOCTOUや特権攻撃者への防御、VM結果のhost上動作保証へ拡張しない。
証拠搬出・VM復元/破棄はbackup/CRC/SHA/readbackと保持対象を決めた後の別承認。失敗証拠をcleanupで消さない。

G4でしか観測できない実E2/E3/E4、実hostのTLS応答・本文は未観測のままとする。
事前に求めるのは記録・制限・停止機構のqualificationであり、同じ初回sendの結果そのものではない。
