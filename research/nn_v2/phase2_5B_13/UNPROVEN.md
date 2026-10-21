# 未実証事項と次の承認境界

| 項目 | 今回確認した範囲 | 未実証 |
|---|---|---|
| Process | 実WindowsでJob所属・kernel親子identity・正常/異常終了・timeout・親終了・残存子停止・peer保全 | kernel自体が停止する状況、終了不能なdriver等に対する普遍的cleanup保証 |
| Cleanup timeout | 0秒budgetを注入し、実job停止と有限rescueを検証 | OSが継続的に応答しない実障害の再現 |
| Namespace競合 | 実directory rename、実junction差替え、実symlink/reparse拒否 | 全filesystem・filter driver・特権的攻撃に対する完全な原子的保証 |
| ACL | owner/DACLのnative確認、実並行変更の検出とcommit前STOP | ACL変更そのものの原子的禁止、悪意あるowner/admin/kernelからの完全隔離 |
| 永続化 | CREATE_NEW、FlushFileBuffers、readback、SHA、process異常終了、seal/receipt境界 | 電源断・storage故障・directory metadataの電源断耐性 |
| 実HTTP | 機能なし、通信permitなし、公式取得0 | DNS/TLS/host/robots/redirect/rate/retry/body budgetと実workerの統合 |
| 履歴利用 | 詳細審査と時刻証拠/admissionを分離 | 実際の開始・中断・再開・完了・結果利用可能時刻、当初日程・変更告知、予測cutoff時の取得証明 |

ローカル検証の判定は、今回のWindows・保存領域・固定コードで実施した故障試験の範囲に限る。未実証項目をPASSへ読み替えない。ACLの並行変更等では、root内に未確定bytesが残る可能性を認め、receipt未確定状態として保持する。これを通常試合・完全な履歴・再取得可能なrunとして扱わない。

次の実HTTP検証には、独立したworker統合・所有権/ACL/競合/復旧/receipt監査、新しい対象集合・新しい通信permit・明示的な取得承認が必要。残り172件の固定計画は不変であり、この工程の合格だけでアクセスを開始しない。
