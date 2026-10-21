# 未実証事項と承認境界

| 項目 | 今回の証拠 | 残る未実証事項 |
|---|---|---|
| 実HTTP | 固定3件、TLS/hostname、完了UTC、SHA、5秒間隔、封印・解析・receipt・Job終了 | 他ページ・長時間・大規模取得への普遍的保証 |
| 実HTTP隔離 | 今回3件は全てPASS | 実HTTP未知備考の隔離例は未観測。過去4件のオフライン再現を実HTTP実証と呼ばない |
| 通信異常 | 403/429、TLS、timeout、redirect、本文超過等の合成試験で停止 | 公式サイトに故障を起こした実通信試験ではない |
| Process | 実Job所属・kernel identity、正常/異常終了・親終了・cleanup・非所有peer保全 | kernel停止や終了不能driverに対する普遍的保証 |
| Windows保存 | DACL/owner、reparse拒否、保持handle、実rename/junction/ACL競合、fsync/readback/SHA | owner/admin/kernel等の特権的操作、全filesystem/filterの競合に対する完全な原子的保証 |
| ACL | 入出力前後に検証しcommit前STOP | ACL変更そのものの原子的禁止。未確定bytesが新root内に残る場合がある |
| 永続化 | process異常終了とseal/receipt境界を検証 | 電源断・storage故障・directory metadataの電源断耐性 |
| robots | 正確なURLの取得証拠と本文SHA | 404はサイト全体のアクセス許可証明ではない |
| 履歴 | 最終詳細のidentity・90分結果・備考 | 開始/中断/再開/完了/結果利用可能時刻、当初日程と変更告知、予測cutoffでの取得証明 |

本工程の合格は3件限定。残り169件の取得は未承認であり、旧permitを再利用しない。新しい対象集合・executor・permitの固定と別の明示承認が必要。履歴admissionと実予測利用は引き続き禁止する。
