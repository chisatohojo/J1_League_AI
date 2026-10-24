# 週末予想GUI：停止・切戻し条件

状態：新版稼働中、**切戻しは実行していない**。
本書は承認済みの配備対象に検証失敗が生じた場合の手順であり、正常稼働中に試す操作ではない。
実パス、引数、shortcut SHA、process identityは非公開の配備台帳を正本とする。

## 保持済みの復元元

- 旧UI revision `b57454857e779bd4b4a16d620decc9a125423cce` は元worktreeに不変のまま保持。
- 旧コード・設定・元 `J1AI.lnk`・旧ディスクJSON・旧実配信APIを323ファイルとして保存。
- 独立した読戻し領域で全SHAを照合。元shortcutとprepared rollback shortcutは別ファイル。
- 旧実配信APIのSHAは `e814f6350ce26d94b28f2729031111d79efe0a009ce20fef7d5713f8554d2c2b`。
- 旧ディスクJSONと旧APIは不一致だったため、旧画面の再現には保全した**旧API snapshot**を使う。
  運用JSONの上書き、古いデータによる運用runtimeの巻戻しはしない。
- 事前検証済みrollback shortcutは旧rootのlauncherへ、旧API snapshotの `--data` と
  既存Python、`--browser-mode default` を明示している。sidecarを旧readerへ渡さない。

## 実行前のSTOP条件

所有権不一致、バックアップ改変、復元元不足、未確認のshortcut変更、保護差分、
タスクとの競合、正式Stop未完了では操作せずHOLDする。将来のPID/portを本書の観測値で決め打ちしない。
強制kill、lock削除、他rootのStop、既存ファイルの無条件コピー、Git reset/cleanは禁止。

## 承認済み失敗時の切戻し順序

1. 現在の新版processについてPID・creation time・実行ファイル・引数・SID/session・親子関係、
   mutex/Stop event、listenerを照合する。新規の変更前保護baselineとタスク状態も確認する。
2. 新版rootだけを対象に既存の `python -B -m scripts.launch_dashboard --stop` を使用する。
   引数・作業rootを実体と照合してから送信し、exit、全所有process、port、mutex/Eventの解放を確認する。
   確認不能なら停止し、別serverを立てない。execution policyを変更しない。
3. 元の旧worktree・snapshot・prepared rollback shortcutと独立コピーのSHAを再確認する。
   元Desktop shortcutも別途保全したまま、所有確認済みのDesktop `J1AI.lnk` だけを
   prepared rollback shortcutへ原子的に切り替える。稼働コードの上書きはしない。
4. Desktop入口から旧rootを1回起動する。新しいprocess所有権とendpointを改めて検証する。
5. 旧APIと保全snapshotの一致、前節10件と旧次節5件、ナビゲーション、モデル・原予測・
   公式source・タスク・対象外serverの不変性を確認する。
6. 成否と実際のrevisionを別receiptへ記録する。新版release、隔離/失敗証跡、backupを削除しない。

元のshortcut定義をそのまま戻す案と、旧**画面**を固定snapshotで再現する案は同じではない。
元のruntimeデータを後者のために書き戻さない。未確認の状態で自動復旧・再推論しない。

## 停止と未実証範囲

通常の停止も、その時点の稼働root所有確認と正式Stopによる。検証再開時点では正常稼働していたため、
Stop・再起動は追加実施していない。backup/readbackは再確認済みだが、切戻しの実動作は未実施。
電源断耐性・無制限の競合への耐性・将来のOS更新後の再現性を保証しない。
