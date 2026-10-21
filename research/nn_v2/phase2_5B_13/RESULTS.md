# Phase 2.5B-13 Windowsローカル結合・異常終了検証

判定：**TWO_STAGE_LOCAL_INTEGRATION_VERIFIED_RESEARCH_ONLY**。実Windows子processのlocal byte worker、親の所有権・期限・停止管理、変更していない二段階Stage A/B、制限ACLの保存・隔離・receiptを結合した。判定は本環境で実施したローカル検証の範囲に限り、実HTTPや残り172件への取得許可を意味しない。

開始branchは`feature/nn-research-v1`、HEAD `69d15ba886c6add214afdfaf28bf334c61a3d806`、study `nn_v2_residual_20261020_01`。モデルは`TRAINED_AND_SEALED_RESEARCH_ONLY`。モデルseal・53 payload、旧原本、旧parser・v5契約・4個別rule、旧executorと正式停止記録、全入力と保護対象を照合した。[入力SHA](input-sha256.json)。

保存済み116件を実worker経由で再生し、**Stage A封印116件、Stage B 116 PASS / 0 HOLD**、v5の全semantic field不変を確認した。旧原本への書込み0。過去4件はそれぞれ旧契約の正式HOLDを完全再現し、隔離receipt確定後に別の保存済み正常原本各1件へ進めた。現在のv5での未解決件数には加えていない。履歴admissionはすべてfalse。[互換性](compatibility-summary.json)、[隔離再現](historical-quarantine-summary.json)。

通常再生116 workerと過去例8 workerで、kernel PID/親PID、creation FILETIME、image pathとSHA、suspended起動→Job Object所属確認→resume、終了確認→bytes採用の順序を確認した。全jobは終了時に所属process 0。KILL_ON_JOB_CLOSE、実timeout停止、実親process異常終了時のworker停止、実残存子processの停止、Job外peerの保全を検証した。PID探索で他processを終了していない。cleanup timeoutケースは0秒budgetを注入し、保持jobへの実停止と有限rescueを確認したもので、OSが応答不能になる障害の実証ではない。[process監査](process-ownership-summary.json)。

保存先はowner/DACLをnative APIで確認した新規研究領域。exclusive-create、junction/symlink/reparse拒否、traversal・衝突・二重使用拒否、保持したfile handleによるFlushFileBuffers/readback/SHAを検証した。実directory rename競合、path確認後のjunction差替え、handle取得後の差替え、ACLの実並行変更を試験した。初期試験で属性読取りhandleではrenameを防げないことを検出し、GENERIC_READでFILE_SHARE_DELETEを付けずに保持する方式へ修正後、同じ競合に合格した。[保存監査](storage-safety-summary.json)。

ACL変更自体の原子的禁止、全filesystem/driver/特権的攻撃に対する普遍的な原子性、電源断時のdirectory metadata永続性は未実証。ACL競合ではroot内に未確定bytesが残り得るが、commit前検出でSTOPし、seal/receiptとして採用しない。これらをPASSと推定せず、[未実証事項](UNPROVEN.md)に分けた。

合成・関連回帰は **742 PASS / fail0 / error0 / skip0、warnings-as-errors**。新規Windowsローカル46ケースと既存696ケース。起動失敗・異常終了・親終了・timeout・cleanup期限・子残存、途中raw/metadata、seal前・receipt前・receipt後次入力前の実process終了、隔離欠損、Stage A/B矛盾、SHA/URL/ID/結果/403/429/redirect/TLS/GET/本文/rate異常、二重実行・再利用・無断再開・誤集計・admission拒否を検証した。ネットワーク監査probeはsys.auditの合成イベントであり実socket接続ではない。[テスト](synthetic-test-results.json)。

初期の再生runnerで関数名がmanager退場ruleを上書きし、116件中1件が安全側のHOLDとなった。既存出力を保持し、別版runnerで名称を修正して最終116件を新領域へ再生した。さらに、TypeError等の解析契約エラーを備考HOLDへ落とさず全体STOPにする防御を結合層へ追加した。旧二段階コード・旧rule・旧原本を変更して合格にしたものではない。初期の失敗JUnitと途中runも別証拠として保存した。

実OS故障試験の45領域・703ファイルを終了後に読取り専用で保存し、異常終了したrunを再開していない。試験で作ったreparse objectは追跡せず属性・リンク先の記録として保持した。正式な過去B4/B6/B8/B10のPASS/HOLD/未取得記録は不変。[旧正式記録](old-formal-records-verification.json)。

元288件＝原取得済み116件＋未取得172件を維持。未取得台帳と完全計画SHAは指定値に一致し、対象変更なし。workerは保存byte列を扱うだけで、公式URLを通信先として使わない。実HTTP client・通信permit・運用collector・タスク・共通分類候補・モデル処理・予測器には接続していない。[仕様](SPEC.md)、[集合照合](fixed-set-verification.json)。

保護対象17,619ファイル・モデル53 payloadは不変。今回の運用出力変化0、タスク重複なし、07:00/22:00タスク定義・main・他worktree不変。過去の未帰属11件と、根拠確認済み07:00タスクの10件の可変出力を区別して保持し、帰属を推測していない。[保護監査](protection-verification.json)。

worker/Stage A/B/quarantine/receipt、実OS故障証拠、固定実装・入力/出力SHAを別ドライブへbackupし、ZIP CRC・全payload SHA・独立展開・読戻しが一致した。Raw、metadata、実名、個人パス、学習済みモデルは公開していない。[backup](backup-verification.json)、[実装SHA](implementation-sha256.json)。

実HTTP統合には新しい対象集合・permit・別の明示承認が必要。詳細PASSでも、時刻証拠B〜Dの監査と履歴admissionはHOLD。[次工程](next-stage.json)。

**HISTORY / PREDICTION：HOLD**。公式ネットワーク取得0、通信permit0、実fit0、性能評価0、実確率計算0、T0登録0、対象登録0、将来予測保存0。Phase A：BLOCKED、Phase B：NOT_AUTHORIZED。
