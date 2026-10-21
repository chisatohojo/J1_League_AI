# 未実証事項

| 項目 | 今回の検証範囲 | 残る限界 |
|---|---|---|
| HTTP | 固定先頭12件、TLS、通信間隔、本文、封印、審査、receipt、Job終了 | 他のページ・長期間・残り一括取得への一般化は未承認 |
| 実HTTP隔離 | 今回は全12件PASS | 未知備考がなく実隔離は未観測。旧4件のオフライン再現は別証拠 |
| 通信異常 | 403/429、TLS、timeout、redirect、本文・回数・rate等の合成停止試験 | 公式サイトに実障害を起こした検証ではない |
| Process | 実Windows所有Job・kernel identity・異常終了・cleanup・peer保全 | kernel停止や終了不能driverへの普遍的保証は未実証 |
| 保存 | 制限ACL、reparse拒否、保持handle、実namespace/ACL競合、fsync/readback/SHA | owner/admin/kernel等の特権的操作、全filesystem/filterへの原子的保証は未実証 |
| ACL | commit前の再検証とSTOP | ACL変更自体を原子的に禁止しない。未確定bytesが新root内に残り得る |
| 永続化 | process終了・seal/receipt境界試験 | 電源断やstorage故障時のdirectory metadata永続性は未実証 |
| robots | 鮮度内の既知404原本・metadata・SHAを再検証 | 404はサイト全体の許可証明ではない |
| 履歴 | 最終詳細のidentity・結果・備考 | 実開始/中断/再開/完了/結果利用可能時刻、当初日程/変更告知、予測cutoffでの取得証明はHOLD |

残り157件には新対象集合・executor・permitと別の明示承認が必要。今回のpermitは消費済みで再実行しない。共通備考分類候補と履歴admissionは未接続。
